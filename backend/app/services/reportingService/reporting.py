"""Компактный Markdown-отчёт для проверки гипотез о месте съёмки."""

import math
import re
from urllib.parse import quote

from app.services.geoInspectService.geo import extract_text_evidence
from app.services.geoInspectService.geo_scene import build_geo_scenes
from app.services.geoInspectService.geo_visual import verify_scene_visuals
from app.APIGateway.jobs import job_folder
from app.services.mapService.map_query import generate_map_queries


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


def _geo_payload(job):
    """Read reviewed stages once per export; do not cache edited observations."""
    stages = _dict(job.get("stages"))
    geo = build_geo_scenes(stages)
    job_id = job.get("id")
    if not job_id:
        return geo
    try:
        folder = job_folder(str(job_id))
        geo["visual_verification"] = verify_scene_visuals(folder, stages, geo)
    except (OSError, ValueError):
        # No claim is visually verified on infrastructure error.
        geo["visual_verification"] = {"scenes": [], "metric_mask_ready": False,
                                      "note": "Кадры не удалось прочитать; визуальная проверка недоступна."}
    geo["map_queries"] = generate_map_queries(geo)
    return geo


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
    turns = _speaker_turns(stages)

    from app.services.audioService.transcript import transcript_payload

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
        "geo_scene": _geo_payload(job),
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


# Основной Markdown — только геопоиск. Конспект, вопросы, лица и полная
# расшифровка доступны в интерфейсе и других экспортах, но не засоряют его.
_CLAIM_NAMES = {
    "region": "Регион, названный автором",
    "settlement": "Бывший населённый пункт / число домов",
    "manor": "Усадьба (упоминание в речи или OCR)",
    "church": "Церковь (упоминание в речи или OCR)",
    "river": "Река / ручей (упоминание)",
    "road": "Дорога (упоминание)",
    "historic_map": "Историческая карта (упоминание)",
}


def _geo_claim_line(claim):
    subject = _CLAIM_NAMES.get(claim.get("subject"), "Зацепка")
    value = claim.get("value")
    predicate = claim.get("predicate")
    if predicate == "house_count_on_old_map_mentioned":
        subject = "На старой карте, по словам автора, домов/дворов"
    if predicate == "near_according_to_speaker":
        subject, value = "По словам автора: усадьба рядом с церковью", ""
    if predicate == "possibly_near_according_to_speaker":
        subject, value = "Предположение автора: усадьба рядом с церковью", ""
    if predicate == "co_mentioned_in_utterance":
        subject, value = "Усадьба и церковь названы в одной реплике; расстояние неизвестно", ""
    if predicate == "house_count_mentioned":
        subject = "По словам автора, домов/дворов (связь с картой не установлена)"
    readable = {
        "abandoned_or_former_village": "бывшая или заброшенная деревня",
        "manor_estate": "усадьба",
        "church_or_church_site": "церковь или церковное место",
        "river_or_stream": "река или ручей",
        "road": "дорога",
        "old_map": "историческая карта",
    }
    detail = _md(readable.get(value, value)) if isinstance(value, str) else str(value or "")
    return f"{subject}: {detail}".rstrip(": ")


def _geo_clue(claim, job_id):
    support = _rows(claim.get("support"))
    if not support:
        return []
    chosen = support[0]
    source = "речь" if chosen.get("source") == "speech" else "OCR"
    when = _time(chosen.get("start"))
    quote = _md(chosen.get("quote"))[:350]
    status = "подтверждённая пользователем запись" if chosen.get("review") == "accepted" else "распознавание требует проверки"
    align = " · таймкод правки неизвестен" if chosen.get("alignment") else ""
    return [f"- **{_geo_claim_line(claim)}** — {when} · {source} · {status}{align}.",
            f"  Цитата: «{quote}»." + (f" Ещё упоминаний: {claim['support_count'] - 1}."
                                       if claim.get("support_count", 0) > 1 else "")]


def render_report(job):
    """Короткий географический бриф из текущих ручных правок и этапов.

    Совпадение временных окон, типов объектов и классов модели не является
    доказательством одной локации или наличия объекта на конкретном кадре.
    """
    job = _dict(job)
    stages = _dict(job.get("stages"))
    job_id = job.get("id")
    geo = _geo_payload(job)
    visual_by_id = {item.get("scene_id"): item for item in
                    _rows(_dict(geo.get("visual_verification")).get("scenes"))}
    by_id = {claim["id"]: claim for claim in geo["claims"]}
    duration = _dict(_stage(stages, "prepare").get("result")).get("duration")
    lines = ["# Геопоиск: проверяемые улики", "",
             f"**Видео:** {_md(job.get('name')) or 'без названия'}"
             + (f" · {_time(duration)}" if duration is not None else ""), "",
             "**Координаты камеры не определены.** Речь — утверждения автора, а не проверенные сведения о местности. Внешние источники не запрашивались.", ""]
    region_claims = [claim for claim in geo["claims"] if claim.get("subject") == "region"]
    if region_claims:
        lines += ["## Регион, указанный в видео", ""]
        for claim in region_claims[:2]:
            lines.extend(_geo_clue(claim, job_id))
        lines.append("")
    lines += ["## Геосцены для проверки", ""]
    if not geo["scenes"]:
        lines += ["Нет локализованных по времени утверждений о месте. Координаты вывести нельзя.", ""]
    for scene in geo["scenes"][:8]:
        lines += [f"### {scene['id']}: {_time(scene['start'])}–{_time(scene['end'])}", "",
                  "Временное окно реплик, **не** доказательство единой точки съёмки.", ""]
        claims = [by_id[key] for key in scene["claim_ids"] if key in by_id]
        # Отношения и карта важнее разрозненных упоминаний.
        priority = {"near_according_to_speaker": 0,
                    "possibly_near_according_to_speaker": 0,
                    "co_mentioned_in_utterance": 1,
                    "house_count_on_old_map_mentioned": 1,
                    "described_as": 2}
        claims.sort(key=lambda c: priority.get(c["predicate"], 3))
        for claim in claims[:6]:
            lines.extend(_geo_clue(claim, job_id))
        if len(claims) > 6:
            lines.append(f"- Ещё связанных утверждений: {len(claims) - 6}; полный перечень — в evidence.json.")
        lines.append("")
        refs = _rows(scene.get("frame_candidates"))[:3]
        if refs:
            links = []
            for ref in refs:
                link = _artifact(job_id, ref.get("artifact"), "кадр")
                links.append(f"{_time(ref.get('timestamp'))} {link}" if link else _time(ref.get("timestamp")))
            lines += ["Кадры рядом с репликой (содержание **не подтверждено**): " + "; ".join(links) + ".", ""]
        visual = visual_by_id.get(scene["id"], {})
        candidates = _rows(visual.get("candidates"))
        pairs = _rows(visual.get("possible_shared_facades"))
        if candidates:
            labels = {"building": "здание", "house": "дом", "church": "церковь",
                      "temple": "храм"}
            samples = []
            for item in candidates[:3]:
                link = _artifact(job_id, item.get("artifact"), "кадр")
                samples.append(f"{labels.get(item.get('label'), 'здание')} {_time(item.get('timestamp'))}"
                               + (f" {link}" if link else ""))
            lines.append("Модель отметила кандидатов (не опознание): " + "; ".join(samples) + ".")
        if pairs:
            pair = pairs[0]
            first, second = _dict(pair.get("first")), _dict(pair.get("second"))
            lines.append("Сходство фрагментов фасада для ручной сверки: "
                         + f"{_time(first.get('timestamp'))} ↔ {_time(second.get('timestamp'))}; "
                         + "совпадение по признакам не удостоверяет, что это одна усадьба.")
        mask = _dict(scene.get("map_query_mask"))
        entities = [item["entity"] for item in _rows(mask.get("candidate_features"))
                    if item.get("entity") and item.get("entity") != "region"]
        relations = _rows(mask.get("relations"))
        if entities:
            lines.append("Проверять в картографических и краеведческих источниках: "
                         + _md(", ".join(entities)) + ".")
        if any(item.get("predicate") == "near_claimed" for item in relations):
            lines.append("Сверить усадьбу и церковь по независимым картам/описям; установить расстояние и затем сравнить фасад с кадрами.")
        elif any(item.get("predicate") == "co_mentioned_only" for item in relations):
            lines.append("Проверить, находятся ли названные усадьба и церковь рядом: речь этого **не устанавливает**.")
        if any(item.get("entity") == "historical_house_count"
               for item in _rows(mask.get("candidate_features"))):
            lines.append("Сверить число дворов на конкретной датированной карте; современное число построек не заменяет историческое.")
        lines.append("")
    unlocated = [by_id[key] for key in geo["unlocated_claim_ids"] if key in by_id]
    if unlocated:
        lines += ["## Ручные правки без привязки к моменту", ""]
        for claim in unlocated[:3]:
            lines.extend(_geo_clue(claim, job_id))
        lines.append("")
    metadata = _stage(stages, "metadata")
    rejected_gps = any(item.get("review") == "rejected"
                       and _dict(item.get("data")).get("kind") == "gps_coordinates"
                       for item in _rows(metadata.get("observations")))
    gps = [] if rejected_gps else [v for item in _rows(_dict(metadata.get("result")).get("gps"))
                                if (v := _coordinates(item))]
    if gps:
        lines += ["## GPS-теги файла (не координаты всех сцен)", ""]
        lines += [f"- `{point}`" for point in dict.fromkeys(gps[:3])]
        lines.append("")
    lines += ["## Что пока не доказано", "",
              "- Координаты, название населённого пункта, расстояние и ориентация объектов на карте.",
              "- Что церковь видна на кадрах, что здание однозначно является именно названной усадьбой или что кадры из разных сцен сняты в одном месте.",
              "- Историческая карта, её дата, число дворов и совпадение фасада с внешней фотографией.", "",
              "Подробные утверждения и опорные данные: `evidence.json`. Полная расшифровка, конспект, вопросы и лица доступны отдельно и не входят в геобриф. Ссылки на кадры требуют работающего сервиса."]
    return "\n".join(lines).rstrip() + "\n"
