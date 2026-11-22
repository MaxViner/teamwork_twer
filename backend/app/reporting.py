"""Компактный Markdown-отчёт для проверки гипотез о месте съёмки."""

import math
import re
from urllib.parse import quote

from app.geo import extract_text_evidence


ARCHIVE = re.compile(
    r"\b(?:царск\w*\s+карт\w*|дореволюционн\w*\s+карт\w*|"
    r"старинн\w*\s+(?:карт\w*|план\w*)|карт\w*\s+шуберт\w*|"
    r"архивн\w*\s+(?:карт\w*|сним\w*|план\w*)|ревизск\w*\s+сказк\w*)\b", re.I,
)
LANDMARK = re.compile(
    r"\b(?:разводн\w*\s+мост\w*|церков\w*|церкв\w*|колокольн\w*|"
    r"памятник\w*|водонапорн\w*\s+башн\w*|маяк\w*)\b", re.I,
)
LABELS = {
    "speech": "речь", "ocr": "текст на экране", "metadata": "метаданные файла",
    "road": "анализ дороги", "objects": "автоматическое распознавание объектов",
}
TYPES = {
    "archive": "Упоминание архивного источника",
    "landmark": "Упоминание ориентира",
    "address": "Возможный адрес",
    "place_mention": "Возможный топоним",
    "coordinates": "Координаты в тексте",
    "link": "Домен или ссылка в кадре/речи",
    "transport": "Транспортная зацепка",
}
ROUTES = {
    "archive": "Исторические карты, архивные планы, старые справочники: уточнить издание и дату, искать топонимы из соседних реплик, сверить со старой дорожной сетью и устойчивыми ориентирами.",
    "landmark": "Фотографии, реестры объектов, местные публикации: сравнить конструкцию, окружение и ракурс. Упоминание в речи не подтверждает присутствие объекта в кадре.",
    "address": "Адресные справочники, карты и местные публикации: проверить написание, одноимённые улицы и вид здания.",
    "place_mention": "Современные и исторические справочники: проверить варианты названия и одноимённые места; привязать название к видимому ориентиру.",
    "coordinates": "Проверить порядок широты и долготы и контекст. Показанная или произнесённая точка может не совпадать с местом съёмки.",
    "link": "Проверить, кому принадлежит домен и связан ли он с конкретным местом, а не с сетью объектов.",
    "transport": "Маршрутные схемы, списки остановок и старые расписания: сверить название, номер маршрута и период.",
}
VISUAL = {"bridge", "tower", "signboard", "church", "monument", "lighthouse"}
SIDES = {"left": "слева в кадре", "right": "справа в кадре", "image_overlap": "перекрытие в кадре"}


def _dict(value):
    return value if isinstance(value, dict) else {}


def _rows(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _number(value):
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def _clean(value):
    return " ".join(str(value or "").split())


def _md(value):
    return re.sub(r"([\\`*_{}\[\]<>#|!])", r"\\\1", _clean(value))


def _time(value):
    value = _number(value)
    if value is None or value < 0:
        return "без таймкода"
    seconds, millis = divmod(round(value * 1000), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def _interval(item):
    start, end = _time(item.get("start")), _time(item.get("end"))
    return start if end == start or end == "без таймкода" else f"{start}–{end}"


def _stage(stages, name):
    stage = _dict(stages.get(name))
    return stage if stage.get("status") == "completed" else {}


def _artifact(job_id, value, label):
    if not isinstance(value, str) or not value.startswith("runs/"):
        return ""
    parts = value.split("/")
    if any(part in {"", ".", ".."} or "\\" in part for part in parts):
        return ""
    path = "/".join(quote(part, safe="") for part in parts)
    if not job_id:
        return f"{label}: {_md(value)}"
    return f"[{label}](/api/jobs/{quote(str(job_id), safe='')}/files/{path})"


def _links(job_id, item):
    frame = item.get("frame_artifact")
    artifact = item.get("artifact")
    links = [_artifact(job_id, frame, "кадр")]
    if artifact != frame:
        links.append(_artifact(job_id, artifact, "артефакт"))
    return "; ".join(link for link in links if link)


def _coordinates(item):
    lat, lon = _number(item.get("latitude")), _number(item.get("longitude"))
    if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
        return f"{lat:.6f}, {lon:.6f}"
    return None


def _text_rows(stages):
    for source in ("ocr", "speech"):
        stage = _stage(stages, source)
        all_items = _rows(stage.get("observations"))
        if source == "speech" and not all_items:
            all_items = _rows(_dict(stage.get("result")).get("segments"))
        for item in all_items:
            if item.get("review") == "rejected":
                continue
            corrected = item.get("corrected_text")
            segments = _rows(_dict(item.get("data")).get("segments")) if source == "speech" else []
            if corrected is not None:
                # A whole-transcript edit does not preserve individual utterance offsets.
                yield {**item, "start": None if segments else item.get("start"),
                       "end": None if segments else item.get("end"), "source": source,
                       "text": _clean(corrected), "edited": True}
            elif segments:
                artifact = item.get("artifact")
                for i, seg in enumerate(segments):
                    context = []
                    if ARCHIVE.search(_clean(seg.get("text"))):
                        for other in segments[max(0, i - 1):i + 2]:
                            if other is seg:
                                continue
                            gap_start = _number(seg.get("start"))
                            gap_other = _number(other.get("start"))
                            if gap_start is not None and gap_other is not None and abs(gap_start - gap_other) <= 15:
                                context.append((_interval(other), _clean(other.get("text"))[:180]))
                    yield {**seg, "artifact": artifact, "source": source,
                           "review": item.get("review"), "context": context}
            else:
                yield {**item, "source": source}


def _excerpt(text, term, radius=95):
    start = text.lower().find(term.lower())
    if start < 0:
        return text[:190] + ("…" if len(text) > 190 else "")
    left, right = max(0, start - radius), min(len(text), start + len(term) + radius)
    return ("…" if left else "") + text[left:right] + ("…" if right < len(text) else "")


def _text_clues(stages):
    selected = {}
    per_kind = {"archive": 0, "landmark": 1, "coordinates": 2, "address": 3,
                "place_mention": 4, "transport": 5, "link": 6}
    for item in _text_rows(stages):
        text = _clean(item.get("text"))
        if not text:
            continue
        candidates = [(kind, match.group(0), match.group(0))
                      for regex, kind in ((ARCHIVE, "archive"), (LANDMARK, "landmark"))
                      for match in regex.finditer(text)]
        for found in extract_text_evidence(text, item["source"]):
            kind = found.get("kind")
            details = _dict(found.get("details"))
            if kind not in {"address", "place_mention", "coordinates", "transport", "link"}:
                continue
            term = _clean(found.get("text"))
            if not term or (kind == "place_mention" and not details.get("place")):
                continue
            label = _coordinates(details) if kind == "coordinates" else term
            if label:
                candidates.append((kind, label, term))
        for kind, label, term in candidates:
            key = (kind, label.casefold())
            score = _number(item.get("recognition_score")) or 0
            rank = (item.get("review") == "accepted", bool(item.get("edited")),
                    bool(item.get("frame_artifact")), score)
            previous = selected.get(key)
            if previous is None or rank > previous[0]:
                selected[key] = (rank, {**item, "kind": kind, "label": label,
                                       "excerpt": _excerpt(text, term)})
    ordered = sorted(selected.values(), key=lambda entry: (
        per_kind[entry[1]["kind"]], *(-float(part) for part in entry[0]),
        _number(entry[1].get("start")) or 0, entry[1]["label"],
    ))
    return [item for _, item in ordered]


def _roads(stages):
    stage = _stage(stages, "road_geometry")
    observations = _rows(stage.get("observations"))
    if any(item.get("review") == "rejected" for item in observations):
        return []
    episodes = _rows(_dict(stage.get("result")).get("episodes"))
    if episodes:
        return sorted(episodes, key=lambda ep: (
            not bool(ep.get("context_clues")),
            -(_number(ep.get("segformer_frames")) or 0),
            -(_number(ep.get("frame_count")) or 0), _number(ep.get("start")) or 0,
        ))
    return [{"start": seg.get("start"), "end": seg.get("end"),
             "bend_label": seg.get("direction"), "frame_count": 1,
             "reference_frames": [{"timestamp": seg.get("start"), "artifact": seg.get("artifact")}],
             "legacy": True}
            for obs in observations for seg in _rows(_dict(obs.get("data")).get("segments"))]


def _visual(stages):
    stage = _stage(stages, "scene_objects")
    if any(item.get("review") == "rejected" for item in _rows(stage.get("observations"))):
        return []
    result = _dict(stage.get("result"))
    if result.get("method") != "segformer":
        return []
    best = {}
    for frame in _rows(result.get("frames")):
        for obj in _rows(frame.get("objects")):
            label = obj.get("label")
            score = _number(obj.get("confidence")) or 0
            if label in VISUAL and score >= 0.5 and (label not in best or score > best[label][0]):
                best[label] = (score, frame, obj)
    return sorted(best.values(), key=lambda item: -item[0])


def _faces(stages):
    stage = _stage(stages, "faces")
    result = _dict(stage.get("result"))
    people = _rows(result.get("people"))
    if not people:
        return None
    return {
        "people": people,
        "frame_count": result.get("frame_count"),
        "face_count": result.get("face_count"),
        "note": _clean(result.get("note")),
    }


def _summary(stages):
    stage = _stage(stages, "summary")
    result = _dict(stage.get("result"))
    if not result or not result.get("overview"):
        return None
    return result


def _structure(stages):
    stage = _stage(stages, "video_structure")
    sections = _rows(_dict(stage.get("result")).get("sections"))
    return sections or None


def _questions(stages):
    stage = _stage(stages, "comprehension")
    return _rows(_dict(stage.get("result")).get("questions"))


def _landmarks(stages):
    stage = _stage(stages, "landmarks")
    result = _dict(stage.get("result"))
    if not result:
        return None
    return {
        "landmarks": _rows(result.get("landmarks")),
        "geometry": _dict(result.get("geometry")),
        "frame_count": result.get("frame_count_total") or result.get("frame_count"),
    }


def _schematic(stages):
    return _dict(_dict(_stage(stages, "road_geometry").get("result")).get("schematic"))


def _speaker_turns(stages):
    """Короткая сводка реплик по спикерам для отчёта."""
    stage = _stage(stages, "speech")
    result = _dict(stage.get("result"))
    segments = _rows(result.get("segments"))
    if not segments:
        return None

    speakers = {}
    for item in segments:
        label = item.get("speaker") or "не разделено"
        entry = speakers.setdefault(label, {"count": 0, "first": None})
        entry["count"] += 1
        start = _number(item.get("start"))
        if start is not None and (
            entry["first"] is None or start < entry["first"]
        ):
            entry["first"] = start

    return {
        "segments": len(segments),
        "method": result.get("speaker_method"),
        "speakers": [
            {
                "label": label,
                "segments": data["count"],
                "first": data["first"],
            }
            for label, data in sorted(speakers.items())
        ],
    }


def _portable(value):
    """Оставляет только переносимый относительный путь артефакта."""
    if not isinstance(value, str) or not value.startswith("runs/"):
        return None
    parts = value.split("/")
    if any(part in {"", ".", ".."} or "\\" in part for part in parts):
        return None
    return value


def render_evidence_json(job):
    """
    Компактный версионированный JSON с уликами.

    Это отдельная выжимка для геопоиска, а не полный job.json.
    Артефакты указаны относительными путями от папки задания,
    поэтому переносятся вместе с ней без запущенного сервиса.
    """
    job_id = job.get("id")
    stages = _dict(job.get("stages"))
    preparation = _dict(_stage(stages, "prepare").get("result"))
    metadata = _dict(_stage(stages, "metadata").get("result"))

    clues = []
    for item in _text_clues(stages):
        clues.append({
            "type": item.get("kind"),
            "label": item.get("label"),
            "source": item.get("source"),
            "start": _number(item.get("start")),
            "end": _number(item.get("end")),
            "excerpt": item.get("excerpt"),
            "review": item.get("review"),
            "edited": bool(item.get("edited")),
            "artifact": _portable(item.get("frame_artifact") or item.get("artifact")),
        })

    roads = []
    for episode in _roads(stages):
        roads.append({
            "start": _number(episode.get("start")),
            "end": _number(episode.get("end")),
            "bend_class": episode.get("bend_class"),
            "bend_label": episode.get("bend_label"),
            "frame_count": episode.get("frame_count"),
            "width_label": episode.get("width_label"),
            "reference_frames": [
                {
                    "timestamp": _number(ref.get("timestamp")),
                    "artifact": _portable(ref.get("artifact")),
                }
                for ref in _rows(episode.get("reference_frames"))[:6]
            ],
            "context_clues": [
                {
                    "label": clue.get("label_ru") or clue.get("label"),
                    "side": clue.get("image_side"),
                    "timestamp": _number(clue.get("timestamp")),
                    "artifact": _portable(clue.get("artifact")),
                }
                for clue in _rows(episode.get("context_clues"))[:6]
            ],
            "legacy": bool(episode.get("legacy")),
        })

    faces = _faces(stages)
    landmarks = _landmarks(stages)
    summary = _summary(stages)
    structure = _structure(stages)
    questions = _questions(stages)
    turns = _speaker_turns(stages)

    from app.transcript import transcript_payload

    transcript = transcript_payload(job)

    evidence = {
        "schema_version": 1,
        "job_id": job_id,
        "video": {
            "name": job.get("name"),
            "duration": _number(preparation.get("duration")),
            "created_at": metadata.get("created_at"),
        },
        "disclaimer": (
            "Наблюдение и совпадение — разные вещи. Координаты камеры "
            "не подтверждены, метки людей анонимны, геометрия дана в "
            "координатах изображения."
        ),
        "artifact_base": f"/api/jobs/{job_id}/files/" if job_id else None,
        "coordinates": {
            "gps": [
                {"latitude": _number(item.get("latitude")),
                 "longitude": _number(item.get("longitude"))}
                for item in _rows(metadata.get("gps"))
                if _coordinates(item)
            ],
            "note": (
                "GPS-тег файла не привязан к кадру. Координаты из речи "
                "и OCR находятся среди текстовых улик."
            ),
        },
        "text_clues": clues,
        "road": {
            "episodes": roads,
            "schematic": _schematic(stages),
            "map_match_ready": False,
        },
        "landmarks": {
            "items": landmarks["landmarks"] if landmarks else [],
            "geometry": landmarks["geometry"] if landmarks else {},
            "frame_count": landmarks["frame_count"] if landmarks else 0,
            "note": (
                "Горизонт, точка схода и симметрия — подсказки для "
                "сопоставления ракурсов, а не координаты."
            ),
        },
        "faces": {
            "available": bool(faces),
            "people": faces["people"] if faces else [],
            "face_count": faces["face_count"] if faces else 0,
            "anonymous": True,
            "note": (
                "Метки «Человек N» анонимны: это разные лица внутри "
                "видео, а не установленная личность."
            ),
        },
        "summary": {
            "overview": summary.get("overview") if summary else None,
            "topics": summary.get("topics", []) if summary else [],
            "theses": summary.get("theses", []) if summary else [],
            "conclusions": summary.get("conclusions", []) if summary else [],
        },
        "structure": {
            "sections": [
                {
                    "number": section.get("number"),
                    "start": _number(section.get("start")),
                    "end": _number(section.get("end")),
                    "title": section.get("title"),
                    "summary": section.get("summary"),
                    "keywords": section.get("keywords") or [],
                }
                for section in structure or []
            ],
        },
        "questions": [
            {
                "question": item.get("question"),
                "answer": item.get("answer"),
                "start": _number(item.get("time_seconds")),
            }
            for item in questions
        ],
        "transcript": {
            "language": transcript.get("language"),
            "speaker_method": transcript.get("speaker_method"),
            "speakers": transcript.get("speakers") or [],
            "turn_summary": turns,
            "segments": [
                {
                    "start": item.get("start"),
                    "end": item.get("end"),
                    "text": item.get("text"),
                    "speaker": item.get("speaker"),
                    "uncertain": item.get("uncertain"),
                }
                for item in transcript.get("segments") or []
            ],
        },
        "limitations": [
            "Координаты камеры не подтверждены.",
            "GPS-тег может относиться к файлу или устройству.",
            "Лица и люди анонимны, личность не устанавливается.",
            "Геометрия дороги и ориентиров дана в координатах изображения.",
            "Автоматическое распознавание речи может содержать ошибки.",
        ],
    }

    return evidence


def render_report(job):
    """Build a fresh Markdown brief from the current completed stages."""
    job_id = job.get("id")
    stages = _dict(job.get("stages"))
    lines = ["# Геопоиск: зацепки из видео", "", f"**Видео:** {_md(job.get('name')) or 'без названия'}",
             "", "Координаты камеры не подтверждены. Ниже — наблюдения из файла и направления проверки; внешние источники сервис не проверял.", ""]
    preparation = _dict(_stage(stages, "prepare").get("result"))
    metadata = _stage(stages, "metadata")
    meta_result = _dict(metadata.get("result"))
    metadata_observations = _rows(metadata.get("observations"))
    rejected_gps = any(item.get("review") == "rejected"
                       and _dict(item.get("data")).get("kind") == "gps_coordinates"
                       for item in metadata_observations)
    gps = list(dict.fromkeys(filter(None, map(_coordinates, _rows(meta_result.get("gps")))))) if not rejected_gps else []
    if preparation.get("duration") is not None:
        lines += [f"**Длительность:** {_time(preparation['duration'])}", ""]
    lines += ["## 1. Координаты из метаданных", ""]
    if gps:
        lines += [f"- `{point}` — GPS-тег файла, без привязки к кадру." for point in gps[:6]]
        if len(gps) > 6:
            lines.append(f"- Ещё записей: {len(gps) - 6}; см. JSON задания.")
        lines += ["", "Сверить точку с видимыми объектами и ракурсом. Тег может относиться к файлу или устройству, а не ко всем сценам."]
    else:
        lines.append("Нет доступных координат из метаданных, пригодных для этой сводки.")
    if meta_result.get("created_at") and metadata:
        lines += ["", f"Дата в метаданных: {_md(meta_result['created_at'])} (не подтверждённая дата съёмки)."]
    lines += ["", "## 2. Что сказано и что написано", ""]
    clues = _text_clues(stages)
    quota = {"archive": 3, "landmark": 3, "coordinates": 3, "address": 4,
             "place_mention": 4, "transport": 2, "link": 2}
    chosen = []
    for item in clues:
        kind = item["kind"]
        if quota[kind] and len(chosen) < 14:
            quota[kind] -= 1
            chosen.append(item)
    for index, item in enumerate(chosen, 1):
        kind = item["kind"]
        check = "пользователь подтвердил наблюдение" if item.get("review") == "accepted" else "проверить распознавание"
        if item.get("edited"):
            check += ", текст исправлен"
        lines += [f"### Т{index:02d}. {TYPES[kind]}: {_md(item['label'])}", "",
                  f"- Опора: {_interval(item)} · {LABELS[item['source']]} · {check}.",
                  f"- Фрагмент: «{_md(item['excerpt'])}».",
                  f"- Где и как проверять: {ROUTES[kind]}"]
        if kind == "archive":
            for when, text in item.get("context", []):
                if text:
                    lines.append(f"- Соседняя реплика ({when}): «{_md(text)}».")
        if kind == "landmark" and re.search(r"разводн\w*\s+мост", item["label"], re.I):
            lines.append("- Для сверки моста: число и форма пролётов, расположение подвижного пролёта, конструкция опор и застройка берегов.")
        links = _links(job_id, item)
        if links:
            lines.append(f"- Материал: {links}.")
        lines.append("")
    if not chosen:
        lines += ["Адресных, архивных и других конкретных текстовых зацепок не найдено или этапы недоступны.", ""]
    elif len(clues) > len(chosen):
        lines += [f"В сводку не вошло ещё {len(clues) - len(chosen)} текстовых зацепок после удаления дублей; исходные наблюдения доступны в JSON.", ""]
    lines += ["## 3. Конспект и структура", ""]
    summary = _summary(stages)
    structure = _structure(stages)
    if summary:
        if summary.get("overview"):
            lines += [f"- Кратко: {_md(summary['overview'])}"]
        topics = _rows(summary.get("topics"))
        if topics:
            lines.append(
                "- Темы: " + ", ".join(
                    _md(item.get("word"))
                    for item in topics[:8]
                    if item.get("word")
                ) + "."
            )
        for label, key in (("Тезис", "theses"), ("Вывод", "conclusions")):
            for item in _rows(summary.get(key))[:4]:
                text = _clean(item.get("text"))
                if text:
                    lines.append(
                        f"- {label} ({_time(item.get('start'))}): «{_md(text)}»."
                    )
        lines.append("")
    if structure:
        lines += ["**Смысловые разделы:**", ""]
        for section in structure[:10]:
            title = _md(section.get("title")) or "Раздел"
            text = _clean(section.get("summary"))
            keywords = ", ".join(section.get("keywords") or [])
            detail = " ".join(filter(None, (
                f"«{_md(text)}»." if text else "",
                f"Ключевые слова: {_md(keywords)}." if keywords else "",
            )))
            lines.append(
                f"- {_interval(section)} — {title}. {detail}".rstrip()
            )
        if len(structure) > 10:
            lines.append(f"- Ещё разделов: {len(structure) - 10}.")
        lines.append("")
    if not summary and not structure:
        lines += ["Конспект и структура недоступны: нет завершённой расшифровки или надписей.", ""]
    lines += ["## 4. Дорога и ориентиры для визуальной сверки", ""]
    roads = _roads(stages)
    bend_names = {"left": "влево", "right": "вправо", "straight": "прямо",
                  "uncertain": "неоднозначно"}
    for index, episode in enumerate(roads[:5], 1):
        lines += [f"### Д{index:02d}. {_interval(episode)} — {_md(episode.get('bend_label')) or 'изгиб не установлен'}", ""]
        source = "кадр из прежней версии анализа" if episode.get("legacy") else f"кадров с дорожными признаками: {_md(episode.get('frame_count')) or 'нет данных'}"
        lines.append(f"- Опора: {source}.")
        counts = _dict(episode.get("bend_counts"))
        breakdown = [f"{label}: {counts[code]}" for code, label in bend_names.items()
                     if isinstance(counts.get(code), int) and counts[code] > 0]
        if breakdown:
            lines.append(f"- Видимые изгибы по кадрам: {'; '.join(breakdown)}.")
        refs = _rows(episode.get("reference_frames"))
        first_refs = refs if len(refs) <= 4 else [*refs[:3], refs[-1]]
        if first_refs:
            labels = [" ".join(filter(None, (_time(ref.get("timestamp")), _artifact(job_id, ref.get("artifact"), "кадр")))) for ref in first_refs]
            lines.append(f"- Опорные кадры: {'; '.join(labels)}.")
        for clue in _rows(episode.get("context_clues"))[:3]:
            side = SIDES.get(clue.get("image_side"), "положение не установлено")
            link = _artifact(job_id, clue.get("artifact"), "кадр")
            lines.append(f"- Возможный ориентир: {_md(clue.get('label_ru') or clue.get('label'))}, {side}, {_time(clue.get('timestamp'))}{(' · ' + link) if link else ''}.")
        lines.append("")
    if roads:
        lines += ["Сравнить последовательность видимых изгибов и положение ориентиров на снимках, панорамах, картах или старых планах. Стороны указаны относительно изображения. Физические примыкания, масштаб и совпадение дорог между ракурсами не установлены.", ""]
        if len(roads) > 5:
            lines += [f"Ещё дорожных записей: {len(roads) - 5}; подробности — в панели кадров и в JSON.", ""]
    image_clues = _visual(stages)
    if image_clues:
        lines += ["**Отдельные визуальные кандидаты** (метки модели, не идентификация):", ""]
        for _, frame, obj in image_clues[:5]:
            link = _artifact(job_id, frame.get("artifact"), "кадр")
            lines.append(f"- {_md(obj.get('label_ru') or obj.get('label'))} · {_time(frame.get('timestamp'))}{(' · ' + link) if link else ''}.")
        if any(obj.get("label") == "bridge" for _, _, obj in image_clues[:5]):
            lines += ["", "Для моста сверить число и форму пролётов, опоры и береговую застройку по фотографиям. Если мост опознан, отдельно проверить точку наблюдения и направление камеры."]
        lines.append("")
    elif not roads:
        lines += ["Нет визуальных зацепок выбранных типов из завершённых этапов. Это не означает, что объектов нет в видео.", ""]
    lines += ["## 5. Люди в кадре", ""]
    faces = _faces(stages)
    if faces:
        lines.append(
            f"- Обнаружено лиц: {faces.get('face_count') or 0} "
            f"в {faces.get('frame_count') or 0} кадрах; разных людей по внешности: {len(faces['people'])}."
        )
        for person in faces["people"][:8]:
            when = _time(person.get("first_start"))
            lines.append(
                f"- {_md(person.get('label'))}: {person.get('frame_count')} кадр., с {when}."
            )
        if len(faces["people"]) > 8:
            lines.append(f"- Ещё людей: {len(faces['people']) - 8}.")
        lines += ["", "Метки «Человек N» анонимны: это разные лица внутри видео, а не установленная личность. Совпадение лиц между кадрами приблизительное.", ""]
    else:
        lines += ["Лица не обнаружены или этап недоступен. Это не значит, что людей в видео нет.", ""]
    questions = _questions(stages)
    if questions:
        lines += ["## 6. Вопросы для самопроверки", ""]
        for index, item in enumerate(questions[:8], 1):
            answer = _clean(item.get("answer"))
            lines.append(
                f"{index}. {_md(item.get('question'))} "
                f"({_time(item.get('time_seconds'))})"
                + (f" — ответ: «{_md(answer)}»." if answer else "")
            )
        if len(questions) > 8:
            lines.append(f"Ещё вопросов: {len(questions) - 8}.")
        lines.append("")
    unavailable = [label for key, label in (("metadata", "метаданные"), ("ocr", "текст на экране"),
                   ("speech", "речь"), ("road_geometry", "дорога"), ("scene_objects", "объекты"))
                   if not _stage(stages, key)]
    lines += ["## 7. Ограничения и материалы", ""]
    if unavailable:
        lines.append(f"- Нет завершённого результата: {', '.join(unavailable)}.")
    lines += ["- Наблюдение и совпадение — разные вещи. Для вывода о месте требуются независимые признаки и сверка ракурса.",
              "- Ссылки на кадры работают через API запущенного сервиса; Markdown сам не содержит изображения. Полные результаты, расшифровка и технические поля остаются в JSON задания."]
    return "\n".join(lines).rstrip() + "\n"
