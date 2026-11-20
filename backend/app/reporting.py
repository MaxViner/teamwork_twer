"""Markdown-отчёт для поиска места съёмки.

Собирает уже сохранённые результаты этапов и превращает их в
короткий отчёт: паспорт видео, самые сильные улики, локации с
кадрами, геометрию дороги, текст, речь и готовые поисковые запросы.
В конце добавлена машинно-читаемая сводка для интеллектуального
поиска. Ничего заново не анализируется.
"""

import json
import re
import unicodedata

from collections import Counter
from datetime import datetime, timezone

from app.keyframes import (
    collect_frames,
    group_frames,
    scene_intervals,
)
from app.stages.scene_objects import (
    CATEGORY_LABELS_RU,
    CATEGORY_ORDER,
    unique_objects_from_frames,
)
from app.utils.timecodes import numeric_time, timestamp


MAX_OCR_GROUPS = 160
MAX_EVIDENCE_ITEMS = 80
MAX_GROUP_FRAME_TIMES = 24
MAX_MACHINE_GROUPS = 60
ROAD_MATCH_TOLERANCE_SECONDS = 0.2
GROUP_SPEECH_LIMIT = 4

DIRECT_EVIDENCE_KINDS = {
    "coordinates",
    "address",
    "business",
    "place_mention",
    "phone",
    "transport",
    "link",
    "license_plate",
    "currency",
}

EVIDENCE_RANK = {
    "coordinates": 0,
    "address": 1,
    "business": 2,
    "place_mention": 3,
    "phone": 4,
    "transport": 5,
    "link": 6,
    "license_plate": 7,
    "currency": 8,
    "units": 9,
    "language": 10,
    "device": 11,
    "created_at": 12,
}

COVERED_ELSEWHERE = {
    "visual_profile",
    "audio_profile",
    "road_geometry",
    "scene_profile",
    "repetition",
}

GENERIC_OBJECTS = {
    "road",
    "path",
    "sky",
    "tree",
    "grass",
    "plant",
    "building",
    "house",
    "earth",
    "wall",
    "field",
    "hill",
    "mountain",
    "water",
    "river",
    "lake",
    "sea",
    "car",
    "bus",
    "truck",
    "pole",
    "fence",
    "streetlight",
    "signboard",
    "sand",
    "rock",
    "bridge",
}

STAGE_NAMES = {
    "prepare": "Подготовка",
    "metadata": "Метаданные",
    "scenes": "Сцены",
    "speech": "Речь",
    "audio_structure": "Звуковая структура",
    "ocr": "Текст на кадрах",
    "structure": "Повторы",
    "scene_objects": "Объекты",
    "visual_profile": "Визуальный профиль",
    "road_geometry": "Геометрия дороги",
    "location_evidence": "Географические улики",
}

STATUS_NAMES = {
    "created": "создано",
    "pending": "ожидает",
    "queued": "в очереди",
    "running": "выполняется",
    "completed": "готово",
    "partial": "частично",
    "failed": "ошибка",
    "skipped": "пропущено",
}

KIND_NAMES = {
    "coordinates": "Координаты",
    "address": "Адрес",
    "business": "Бренд или организация",
    "place_mention": "Упоминание места",
    "phone": "Телефон",
    "transport": "Транспорт",
    "link": "Ссылка",
    "license_plate": "Номерной знак",
    "currency": "Валюта",
    "units": "Единицы измерения",
    "language": "Язык",
    "device": "Устройство",
    "created_at": "Дата файла",
}


# ============================================================
# Базовые помощники
# ============================================================

def mapping(value):
    """Возвращает словарь или пустой словарь."""
    return value if isinstance(value, dict) else {}


def records(value):
    """Возвращает только словари из списка."""
    if not isinstance(value, list):
        return []

    return [
        item
        for item in value
        if isinstance(item, dict)
    ]


def block(value, language="text"):
    """Помещает текст в блок Markdown без поломки кавычек."""
    text = str(value)

    longest = max(
        (
            len(match.group())
            for match in re.finditer(r"`+", text)
        ),
        default=0,
    )

    fence = "`" * max(3, longest + 1)

    return f"{fence}{language}\n{text}\n{fence}"


def json_block(value):
    return block(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        language="json",
    )


def effective_text(item):
    corrected = item.get("corrected_text")

    if corrected is not None:
        return str(corrected)

    return str(item.get("text", ""))


def normalized_text(value):
    text = unicodedata.normalize("NFKC", str(value))

    return " ".join(text.casefold().split())


# ============================================================
# Чистка упоминаний места
# ============================================================

PLACE_KEYWORD_RE = re.compile(
    r"^(?:област|обл\.|район|кра[йяю]|республик|деревн|посёл|"
    r"посел|сел[оа]|станиц|хутор|город|полуостров|озер|"
    r"рек[аиу]|гор[аыу]|хребет|залив|порт|станци|вокзал|"
    r"аэропорт|метро)",
    re.IGNORECASE,
)

REGION_KEYWORD_RE = re.compile(
    r"^(?:област|обл\.|район|кра[йяю]|республик)",
    re.IGNORECASE,
)

# Слова, которые не могут быть названием места. Нужны, чтобы
# «вот деревня была» не превращалось в «вот деревня».
PLACE_STOPWORDS = {
    "вот", "там", "тут", "здесь", "эта", "это", "этот", "такая",
    "такой", "была", "был", "было", "были", "будет", "есть",
    "начинается", "заканчивается", "стоит", "видно", "видна",
    "и", "а", "но", "в", "во", "на", "из", "с", "со", "у", "к",
    "ко", "по", "о", "об", "от", "до", "за", "под", "над", "при",
    "для", "что", "как", "где", "когда", "тоже", "ещё", "еще",
    "уже", "очень", "почти", "через", "около", "возле", "рядом",
    "прямо", "сейчас", "потом", "тогда", "туда", "сюда", "назад",
    "вперёд", "вперед", "дальше", "ближе", "самая", "самый",
    "самое", "весь", "вся", "всё", "все", "один", "одна", "одно",
}

PLACE_ADJECTIVE_RE = re.compile(
    r"(?:ская|ской|скую|ский|ского|скому|ском|ая|ой|ую|ий|"
    r"ого|ому|им|ом|ые|ых|ым|ыми)$",
    re.IGNORECASE,
)

WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9\-]+")


def _looks_named(token):
    """Название места обычно с заглавной или похоже на adjective."""
    if not token or token.casefold() in PLACE_STOPWORDS:
        return False

    if token[:1].isupper():
        return True

    return bool(PLACE_ADJECTIVE_RE.search(token))


def place_tokens(value):
    """
    Достаёт короткие названия мест из длинной фразы.

    «Приехал я в деревню, на дачу, в Тирскую область» даёт
    «Тирскую область», а «ну вот деревня была» не даёт ничего.
    """
    tokens = WORD_RE.findall(str(value))
    found = []

    for index, token in enumerate(tokens):
        if not PLACE_KEYWORD_RE.match(token):
            continue

        previous = tokens[index - 1] if index > 0 else None

        if (
            previous
            and _looks_named(previous)
            and not PLACE_KEYWORD_RE.match(previous)
        ):
            found.append(f"{previous} {token}")

        following = (
            tokens[index + 1]
            if index + 1 < len(tokens)
            else None
        )

        if (
            following
            and following[:1].isupper()
            and following.casefold() not in PLACE_STOPWORDS
            and not PLACE_KEYWORD_RE.match(following)
        ):
            found.append(f"{token} {following}")

    result = []

    for item in found:
        cleaned = " ".join(item.split())
        key = normalized_text(cleaned)

        if key and key not in {
            normalized_text(existing)
            for existing in result
        }:
            result.append(cleaned)

    return result


def clean_place(value):
    """Одно самое конкретное название места или None."""
    found = place_tokens(value)

    if not found:
        return None

    # Сначала регион/район, потом остальное: это полезнее
    # для поиска на карте.
    found.sort(
        key=lambda item: (
            0 if REGION_KEYWORD_RE.match(item.split()[-1]) else 1,
            -len(item),
        )
    )

    best = found[0]

    if best[:1].islower():
        best = best[0].upper() + best[1:]

    return best


def speech_time_for(value, speech):
    """Ищет реплику, где прозвучало упоминание, и берёт её время."""
    key = normalized_text(value)

    if not key:
        return None

    for segment in speech:
        if key in normalized_text(segment.get("text")):
            return segment.get("start")

    return None


def stage_result(stages, name):
    return mapping(
        mapping(stages.get(name)).get("result")
    )


def collect_observations(job):
    observations = []

    for stage_name, raw_stage in mapping(
        job.get("stages")
    ).items():
        stage = mapping(raw_stage)

        for original in records(stage.get("observations")):
            item = dict(original)
            item["_stage"] = stage_name
            item["_stage_status"] = stage.get("status")
            observations.append(item)

    observations.sort(
        key=lambda item: (
            numeric_time(item.get("start")) is None,
            numeric_time(item.get("start")) or 0,
        )
    )

    return observations


def _in_range(value, start, end, pad=1.0):
    moment = numeric_time(value)

    if moment is None:
        return False

    return (start - pad) <= moment <= (end + pad)


def _table_cell(value):
    return str(value).replace("|", "\\|").replace(
        "\n",
        " ",
    )


def _first_stream(info, kind):
    for stream in records(info.get("streams")):
        if stream.get("codec_type") == kind:
            return stream

    return {}


def _video_size(info):
    stream = _first_stream(info, "video")
    width = stream.get("width")
    height = stream.get("height")

    if width and height:
        return f"{width}×{height}"

    return None


def _short_list(values, limit):
    return [
        value
        for value in values
        if value
    ][:limit]


# ============================================================
# Паспорт видео
# ============================================================

def video_passport(job, stages):
    prepared = stage_result(stages, "prepare")
    metadata = stage_result(stages, "metadata")
    source_info = mapping(prepared.get("source_info"))
    preview_info = mapping(prepared.get("preview_info"))

    duration = numeric_time(prepared.get("duration"))
    stream = _first_stream(
        source_info or preview_info,
        "video",
    )

    return {
        "name": job.get("name"),
        "job_id": job.get("id"),
        "status": job.get("status"),
        "created_at": job.get("created_at"),
        "duration_seconds": (
            round(duration, 3)
            if duration is not None
            else None
        ),
        "duration": timestamp(duration),
        "resolution": _video_size(
            source_info or preview_info
        ),
        "fps": stream.get("r_frame_rate"),
        "has_audio": prepared.get("has_audio"),
        "device": metadata.get("device"),
        "file_created_at": metadata.get("created_at"),
        "sha256": prepared.get("sha256"),
        "source_tags": metadata.get("tags") or {},
    }


def gps_items(stages):
    metadata = stage_result(stages, "metadata")
    dossier = stage_result(
        stages,
        "location_evidence",
    ).get("dossier") or {}

    items = []
    seen = set()

    for item in records(metadata.get("gps")):
        try:
            latitude = float(item["latitude"])
            longitude = float(item["longitude"])

        except (KeyError, TypeError, ValueError):
            continue

        key = (round(latitude, 6), round(longitude, 6))

        if key in seen:
            continue

        seen.add(key)
        items.append({
            "latitude": latitude,
            "longitude": longitude,
            "origin": "metadata",
        })

    for item in records(dossier.get("coordinates")):
        try:
            latitude = float(item["latitude"])
            longitude = float(item["longitude"])

        except (KeyError, TypeError, ValueError):
            continue

        key = (round(latitude, 6), round(longitude, 6))

        if key in seen:
            continue

        seen.add(key)
        items.append({
            "latitude": latitude,
            "longitude": longitude,
            "origin": item.get("origin") or "text",
        })

    return items


# ============================================================
# Текст, речь, дорога
# ============================================================

def collect_ocr(observations):
    """Уникальные надписи без мусора и повторов."""
    collected = {}

    for item in observations:
        if item.get("source") != "ocr":
            continue

        if item.get("review") == "rejected":
            continue

        text = " ".join(effective_text(item).split())

        if len(text) < 2:
            continue

        if not re.search(
            r"[A-Za-zА-Яа-яЁё0-9]",
            text,
        ):
            continue

        score = item.get("recognition_score")

        if score is not None and float(score) < 0.2:
            continue

        key = normalized_text(text)
        moment = numeric_time(item.get("start"))

        entry = collected.setdefault(key, {
            "text": text,
            "count": 0,
            "times": [],
            "score": None,
            "frame_artifact": None,
            "artifact": None,
        })

        entry["count"] += 1

        if moment is not None:
            entry["times"].append(round(moment, 3))

        if score is not None:
            entry["score"] = max(
                entry["score"] or 0.0,
                float(score),
            )

        if not entry["frame_artifact"]:
            entry["frame_artifact"] = item.get(
                "frame_artifact"
            )

        if not entry["artifact"]:
            entry["artifact"] = item.get("artifact")

    result = []

    for entry in collected.values():
        entry["times"] = sorted(set(entry["times"]))
        entry["first_time"] = (
            entry["times"][0]
            if entry["times"]
            else None
        )
        result.append(entry)

    result.sort(
        key=lambda item: (
            item["first_time"] is None,
            item["first_time"] or 0,
            -item["count"],
        )
    )

    return result


def collect_speech(observations):
    segments = []

    for item in observations:
        if item.get("source") != "speech":
            continue

        stored = records(
            mapping(item.get("data")).get("segments")
        )

        if stored:
            for segment in stored:
                start = numeric_time(segment.get("start"))
                text = str(segment.get("text", "")).strip()

                if start is None or not text:
                    continue

                end = numeric_time(segment.get("end"))

                segments.append({
                    "start": start,
                    "end": end if end is not None else start,
                    "text": text,
                })

            continue

        start = numeric_time(item.get("start"))
        text = effective_text(item).strip()

        if start is None or not text:
            continue

        end = numeric_time(item.get("end"))

        segments.append({
            "start": start,
            "end": end if end is not None else start,
            "text": text,
        })

    return sorted(
        segments,
        key=lambda item: item["start"],
    )


def collect_evidence(observations, speech=None):
    """Читаемые улики из локационного досье без JSON-мусора."""
    speech = speech or []
    collected = {}

    for item in observations:
        if item.get("source") != "location_evidence":
            continue

        data = mapping(item.get("data"))
        kind = str(data.get("kind") or "other")

        if kind in COVERED_ELSEWHERE:
            continue

        text = effective_text(item).strip()
        label = KIND_NAMES.get(kind, "Признак")
        value = text

        if ": " in text:
            prefix, rest = text.split(": ", 1)

            if prefix.strip():
                label = prefix.strip()
                value = rest.strip()

        value = " ".join(value.split())

        if not value:
            continue

        if kind == "place_mention":
            value = clean_place(value)

            if not value:
                continue

        key = (kind, normalized_text(value))
        start = numeric_time(item.get("start"))
        end = numeric_time(item.get("end"))
        confidence = data.get("confidence")

        if (
            data.get("origin") == "speech"
            and speech
        ):
            matched = speech_time_for(value, speech)

            if matched is not None:
                start = matched

        entry = collected.setdefault(key, {
            "kind": kind,
            "label": label,
            "value": value,
            "origin": data.get("origin"),
            "confidence": (
                float(confidence)
                if confidence is not None
                else None
            ),
            "start": start,
            "end": end,
            "count": 0,
            "frame_artifact": item.get("frame_artifact"),
        })

        entry["count"] += 1

        if start is not None:
            entry["start"] = (
                start
                if entry["start"] is None
                else min(entry["start"], start)
            )

        if end is not None:
            entry["end"] = (
                end
                if entry["end"] is None
                else max(entry["end"], end)
            )

    result = list(collected.values())

    result.sort(
        key=lambda item: (
            EVIDENCE_RANK.get(item["kind"], 20),
            -(item["confidence"] or 0.0),
            item["start"] is None,
            item["start"] or 0,
        )
    )

    return result[:MAX_EVIDENCE_ITEMS]


def semantic_road_frames(stages):
    result = stage_result(stages, "scene_objects")
    method = result.get("method")

    if method and method != "segformer":
        return None

    frames = records(result.get("frames"))

    if not frames:
        return None

    evidence = {}

    for frame in frames:
        moment = numeric_time(frame.get("timestamp"))

        if moment is None:
            continue

        percent = 0.0

        for item in records(frame.get("objects")):
            if item.get("label") in {
                "road",
                "path",
                "bridge",
            }:
                percent += float(
                    item.get("area_percent") or 0
                )

        evidence[round(moment, 3)] = percent

    return evidence or None


def road_allowed(evidence, moment):
    if not evidence or moment is None:
        return True

    nearest_key = min(
        evidence,
        key=lambda key: abs(key - moment),
        default=None,
    )

    if nearest_key is None:
        return False

    if abs(nearest_key - moment) > ROAD_MATCH_TOLERANCE_SECONDS:
        return False

    return evidence[nearest_key] >= 1.0


def collect_roads(stages, observations):
    segments = []

    for item in observations:
        if item.get("source") != "road_geometry":
            continue

        data = mapping(item.get("data"))
        stored = records(data.get("segments"))

        if stored:
            for segment in stored:
                segments.append(dict(segment))

            continue

        segments.append({
            "start": item.get("start"),
            "end": item.get("end"),
            "text": effective_text(item),
            "confidence": data.get("confidence"),
            "semantic_road_percent": data.get(
                "semantic_road_percent"
            ),
        })

    evidence = semantic_road_frames(stages)
    result = []

    for segment in segments:
        start = numeric_time(segment.get("start"))

        if not road_allowed(evidence, start):
            continue

        segment["start"] = start
        segment["end"] = (
            numeric_time(segment.get("end"))
            if segment.get("end") is not None
            else start
        )
        result.append(segment)

    result.sort(
        key=lambda item: item["start"] or 0
    )

    return result


def road_intervals(segments, gap_seconds=8.0):
    """Склеивает соседние похожие кадры в понятные участки."""
    intervals = []

    for segment in segments:
        start = numeric_time(segment.get("start"))

        if start is None:
            continue

        signature = (
            segment.get("direction"),
            segment.get("width_label"),
        )

        if (
            intervals
            and intervals[-1]["signature"] == signature
            and start - intervals[-1]["end"] <= gap_seconds
        ):
            interval = intervals[-1]
            interval["end"] = start
            interval["count"] += 1
            interval["confidence"] = max(
                interval["confidence"] or 0.0,
                float(segment.get("confidence") or 0),
            )
            interval["curve_labels"].add(
                segment.get("curve_label")
            )
            interval["white"] = (
                interval["white"]
                or (
                    mapping(segment.get("markings")).get(
                        "white",
                        0,
                    ) > 1
                )
            )
            interval["yellow"] = (
                interval["yellow"]
                or (
                    mapping(segment.get("markings")).get(
                        "yellow",
                        0,
                    ) > 1
                )
            )

            for item in segment.get("surroundings") or []:
                label = (
                    item.get("label_ru")
                    or item.get("label")
                )

                if label:
                    interval["surroundings"][label] += 1

            continue

        surroundings = Counter()

        for item in segment.get("surroundings") or []:
            label = (
                item.get("label_ru")
                or item.get("label")
            )

            if label:
                surroundings[label] += 1

        intervals.append({
            "signature": signature,
            "start": start,
            "end": numeric_time(segment.get("end")) or start,
            "count": 1,
            "direction": segment.get("direction"),
            "width_label": segment.get("width_label"),
            "curve_labels": {
                segment.get("curve_label")
            } - {None},
            "white": (
                mapping(segment.get("markings")).get(
                    "white",
                    0,
                ) > 1
            ),
            "yellow": (
                mapping(segment.get("markings")).get(
                    "yellow",
                    0,
                ) > 1
            ),
            "confidence": segment.get("confidence"),
            "surroundings": surroundings,
        })

    result = []

    for interval in intervals:
        result.append({
            "start": interval["start"],
            "end": interval["end"],
            "count": interval["count"],
            "direction": interval["direction"],
            "width_label": interval["width_label"],
            "curve_labels": sorted(
                item
                for item in interval["curve_labels"]
                if item
            ),
            "markings": [
                name
                for name, present in (
                    ("белая", interval["white"]),
                    ("жёлтая", interval["yellow"]),
                )
                if present
            ],
            "confidence": (
                round(float(interval["confidence"]), 2)
                if interval["confidence"] is not None
                else None
            ),
            "surroundings": [
                label
                for label, _ in (
                    interval["surroundings"].most_common(6)
                )
            ],
        })

    return result


def _road_interval_text(interval):
    parts = []

    if interval.get("direction"):
        parts.append(str(interval["direction"]))

    if interval.get("curve_labels"):
        parts.append(", ".join(interval["curve_labels"]))

    if interval.get("width_label"):
        parts.append(str(interval["width_label"]))

    if interval.get("markings"):
        parts.append(
            ", ".join(interval["markings"])
            + " разметка"
        )

    if interval.get("surroundings"):
        parts.append(
            "рядом: "
            + ", ".join(interval["surroundings"])
        )

    return "; ".join(parts)


# ============================================================
# Локации
# ============================================================

def _object_summary(frames, limit=8):
    collected = {}

    for frame in frames:
        seen = set()

        for item in records(frame.get("objects")):
            label = (
                item.get("label_ru")
                or item.get("label")
            )

            if not label or label in seen:
                continue

            seen.add(label)

            entry = collected.setdefault(label, {
                "label": label,
                "frame_count": 0,
                "max_area_percent": 0.0,
            })

            entry["frame_count"] += 1
            entry["max_area_percent"] = max(
                entry["max_area_percent"],
                float(item.get("area_percent") or 0),
            )

    result = list(collected.values())

    for item in result:
        item["max_area_percent"] = round(
            item["max_area_percent"],
            1,
        )

    result.sort(
        key=lambda item: (
            -item["frame_count"],
            -item["max_area_percent"],
        )
    )

    return result[:limit]


VISUAL_NOISE = {
    "",
    "не определено",
    "не определяется",
    "не определён",
    "не определен",
    "выраженные признаки не найдены",
    "признаки не найдены",
    "нет данных",
}


def _visual_value(value):
    """Отбрасывает пустые и служебные значения профиля."""
    text = str(value or "").strip()

    if not text:
        return None

    parts = [
        part.strip()
        for part in text.split(",")
        if part.strip()
        and part.strip().casefold() not in VISUAL_NOISE
    ]

    text = ", ".join(parts).strip()

    if not text or text.casefold() in VISUAL_NOISE:
        return None

    return text


def _visual_summary(frames):
    lighting = Counter(
        item.get("descriptors", {}).get("lighting")
        for item in frames
        if item.get("descriptors")
    )
    weather = Counter(
        item.get("descriptors", {}).get("weather")
        for item in frames
        if item.get("descriptors")
    )
    season = Counter(
        item.get("descriptors", {}).get("season")
        for item in frames
        if item.get("descriptors")
    )
    landscape = Counter(
        value
        for item in frames
        for value in (
            item.get("descriptors", {}).get("landscape")
            or []
        )
        if _visual_value(value)
    )

    def top(counter):
        return _visual_value(
            counter.most_common(1)[0][0]
        ) if counter else None

    return {
        "lighting": top(lighting),
        "weather": top(weather),
        "season": top(season),
        "landscape": [
            _visual_value(value)
            for value, _ in landscape.most_common(4)
            if _visual_value(value)
        ],
    }


def _group_speech(group, speech_mentions):
    return [
        item
        for item in speech_mentions
        if _in_range(
            item.get("start"),
            group["start"],
            group["end"],
            pad=0.5,
        )
    ][:GROUP_SPEECH_LIMIT]


def _group_ocr(group, ocr):
    result = []

    for item in ocr:
        if not any(
            _in_range(moment, group["start"], group["end"])
            for moment in item["times"]
        ):
            continue

        result.append(item)

    result.sort(
        key=lambda item: (
            -(item["score"] or 0.0),
            -item["count"],
        )
    )

    return result[:6]


def _group_roads(group, roads):
    result = [
        item
        for item in roads
        if _in_range(
            item.get("start"),
            group["start"],
            group["end"],
            pad=0.5,
        )
    ]

    return road_intervals(result)


def location_groups(stages, ocr, roads, speech_mentions):
    frames = collect_frames(stages)
    groups = group_frames(
        frames,
        scene_intervals(stages),
    )
    result = []

    for group in groups:
        frames_in_group = group["frames"]
        objects = _object_summary(frames_in_group)
        visual = _visual_summary(frames_in_group)
        group_ocr = _group_ocr(group, ocr)
        group_roads = _group_roads(group, roads)
        group_speech = _group_speech(
            group,
            speech_mentions,
        )

        frame_times = [
            round(frame["timestamp"], 3)
            for frame in frames_in_group
        ]

        result.append({
            "number": group["number"],
            "start": group["start"],
            "end": group["end"],
            "scene_numbers": group["scene_numbers"],
            "frame_count": len(frames_in_group),
            "frame_times": frame_times[
                :MAX_GROUP_FRAME_TIMES
            ],
            "frame_times_total": len(frame_times),
            "objects": objects,
            "visual": visual,
            "ocr": group_ocr,
            "roads": group_roads,
            "speech": group_speech,
        })

    return result


def _group_title(group):
    if abs(group["end"] - group["start"]) < 0.05:
        span = timestamp(group["start"])
    else:
        span = (
            f"{timestamp(group['start'])}–"
            f"{timestamp(group['end'])}"
        )

    title = f"Локация {group['number']} · {span}"

    if group["scene_numbers"]:
        title += " · сцена " + ", ".join(
            str(value)
            for value in group["scene_numbers"]
        )

    title += f" · {group['frame_count']} кадр."

    return title


# ============================================================
# Сводки
# ============================================================

def speech_mentions(evidence):
    return [
        item
        for item in evidence
        if item.get("origin") == "speech"
        and item.get("kind") in DIRECT_EVIDENCE_KINDS
    ]


def strongest_objects(stages):
    result = stage_result(stages, "scene_objects")
    objects = records(result.get("unique_objects"))

    if not objects:
        objects = unique_objects_from_frames(
            records(result.get("frames"))
        )

    interesting = [
        item
        for item in objects
        if item.get("label") not in GENERIC_OBJECTS
    ]

    if not interesting:
        interesting = objects

    return interesting[:8]


def search_queries(stages, evidence, ocr):
    dossier = stage_result(
        stages,
        "location_evidence",
    ).get("dossier") or {}

    queries = []

    for value in dossier.get("search_queries") or []:
        value = " ".join(str(value).split()).strip()

        if value and value not in queries:
            queries.append(value[:160])

    places = [
        item["value"]
        for item in evidence
        if item["kind"] in ("address", "place_mention")
    ]

    for item in ocr:
        if (item["score"] or 0) < 0.45:
            continue

        text = item["text"]

        if len(text) < 4:
            continue

        query = (
            f"{text}, {places[0]}"
            if places
            else text
        )

        if query not in queries:
            queries.append(query[:160])

        if len(queries) >= 12:
            break

    return queries[:12]


def summary_lines(
    passport,
    gps,
    evidence,
    ocr,
    intervals,
    objects,
    countries,
    places,
):
    lines = []

    if gps:
        lines.append(
            "- **GPS в файле:** "
            + "; ".join(
                f"{item['latitude']:.6f}, "
                f"{item['longitude']:.6f} "
                f"({item['origin']})"
                for item in gps[:3]
            )
            + "."
        )

    if countries:
        lines.append(
            "- **Вероятные страны:** "
            + ", ".join(
                f"{item.get('name') or item.get('code')} "
                f"({round(float(item.get('score') or 0) * 100)}%)"
                for item in countries[:3]
            )
            + "."
        )

    place_values = []

    for item in evidence:
        if item["kind"] not in ("place_mention", "address"):
            continue

        value = item["value"]

        if value not in place_values:
            place_values.append(value)

    # Если разбор речи не дал коротких названий, берём
    # кандидатов из досье и чистим их той же функцией.
    for item in places:
        cleaned = clean_place(item.get("text"))

        if cleaned and cleaned not in place_values:
            place_values.append(cleaned)

    if place_values:
        lines.append(
            "- **Места-кандидаты:** "
            + ", ".join(place_values[:5])
            + "."
        )

    direct = [
        item
        for item in evidence
        if item["kind"] in DIRECT_EVIDENCE_KINDS
        and item["kind"] not in (
            "place_mention",
            "address",
        )
    ]

    if direct:
        lines.append(
            "- **Прямые текстовые улики:** "
            + "; ".join(
                f"{item['value']} "
                f"({KIND_NAMES.get(item['kind'], item['kind'])})"
                for item in direct[:6]
            )
            + "."
        )

    strong_ocr = [
        item
        for item in ocr
        if (item["score"] or 0) >= 0.45
        and len(item["text"]) >= 4
    ]

    if strong_ocr:
        lines.append(
            "- **Надписи на кадрах:** "
            + "; ".join(
                f"«{item['text']}»"
                for item in strong_ocr[:6]
            )
            + "."
        )

    if objects:
        lines.append(
            "- **Характерные объекты:** "
            + ", ".join(
                str(item.get("label_ru") or item.get("label"))
                for item in objects[:6]
            )
            + "."
        )

    road_summary = _road_summary(intervals)

    if road_summary:
        lines.append("- **Дорога:** " + road_summary)

    if not lines:
        lines.append(
            "- Прямых улик не найдено. Используйте "
            "визуальные признаки, текст и речь ниже."
        )

    if passport.get("device"):
        lines.append(
            f"- **Устройство:** {passport['device']}."
        )

    return lines


def _road_summary(stages_of):
    """Короткая строка по интервалам дороги."""
    intervals = stages_of or []

    if not intervals:
        return None

    directions = Counter(
        item["direction"]
        for item in intervals
        if item.get("direction")
    )
    parts = []

    if directions:
        direction, count = directions.most_common(1)[0]
        parts.append(f"{direction} ({count} уч.)")

    curves = Counter(
        value
        for item in intervals
        for value in item.get("curve_labels") or []
    )

    if curves:
        parts.append(
            "изгибы: "
            + ", ".join(
                value for value, _ in curves.most_common(3)
            )
        )

    surroundings = Counter(
        value
        for item in intervals
        for value in item.get("surroundings") or []
    )

    if surroundings:
        parts.append(
            "рядом: "
            + ", ".join(
                value
                for value, _ in surroundings.most_common(5)
            )
        )

    return "; ".join(parts) + "." if parts else None


# ============================================================
# Разделы отчёта
# ============================================================

def _passport_section(passport):
    rows = [
        ("Файл", passport.get("name")),
        ("Длительность", passport.get("duration")),
        ("Разрешение", passport.get("resolution")),
        ("Частота кадров", passport.get("fps")),
        ("Есть звук", "да" if passport.get("has_audio") else "нет"),
        ("Устройство", passport.get("device")),
        ("Дата файла", passport.get("file_created_at")),
        ("SHA-256", passport.get("sha256")),
        ("Задание", passport.get("job_id")),
    ]

    lines = [
        "## 2. Паспорт видео",
        "",
        "| Параметр | Значение |",
        "| --- | --- |",
    ]

    for label, value in rows:
        if value in (None, ""):
            continue

        lines.append(
            f"| {label} | {_table_cell(value)} |"
        )

    lines.append("")

    return lines


def _evidence_section(evidence):
    lines = [
        "## 3. Улики",
        "",
        "Прямые улики — то, что можно сразу искать на карте. "
        "Косвенные сужают регион и подтверждают гипотезу.",
        "",
    ]

    direct = [
        item
        for item in evidence
        if item["kind"] in DIRECT_EVIDENCE_KINDS
    ]
    indirect = [
        item
        for item in evidence
        if item["kind"] not in DIRECT_EVIDENCE_KINDS
    ]

    lines.extend(["### Прямые", ""])

    if direct:
        lines.extend([
            "| Тип | Значение | Время | Уверенность |",
            "| --- | --- | --- | --- |",
        ])

        for item in direct:
            confidence = item.get("confidence")

            lines.append(
                f"| {_table_cell(item['label'])} "
                f"| {_table_cell(item['value'])} "
                f"| {timestamp(item.get('start'))} "
                f"| {round(confidence * 100) if confidence is not None else '—'}% |"
            )

        lines.append("")

    else:
        lines.extend([
            "Прямых текстовых улик не найдено.",
            "",
        ])

    lines.extend(["### Косвенные", ""])

    if indirect:
        lines.extend([
            "| Тип | Значение | Время | Уверенность |",
            "| --- | --- | --- | --- |",
        ])

        for item in indirect:
            confidence = item.get("confidence")

            lines.append(
                f"| {_table_cell(item['label'])} "
                f"| {_table_cell(item['value'])} "
                f"| {timestamp(item.get('start'))} "
                f"| {round(confidence * 100) if confidence is not None else '—'}% |"
            )

        lines.append("")

    else:
        lines.extend([
            "Косвенных признаков в досье нет.",
            "",
        ])

    return lines


def _groups_section(groups):
    lines = [
        "## 4. Локации и ключевые кадры",
        "",
        "Кадры сгруппированы по сценам и непрерывным участкам. "
        "Внутри локации показаны самые полезные признаки, "
        "а не повторение одного и того же кадра.",
        "",
    ]

    if not groups:
        lines.extend([
            "Кадры не сохранились: визуальные этапы "
            "не завершены.",
            "",
        ])
        return lines

    for group in groups:
        lines.extend([
            f"### {_group_title(group)}",
            "",
        ])

        if group["objects"]:
            lines.append(
                "- **Видно:** "
                + ", ".join(
                    f"{item['label']} "
                    f"({item['frame_count']} кадр., "
                    f"до {item['max_area_percent']}%)"
                    for item in group["objects"]
                )
                + "."
            )
        else:
            lines.append("- **Видно:** объекты не распознаны.")

        visual = group["visual"]
        visual_parts = _short_list([
            visual.get("lighting"),
            visual.get("weather"),
            visual.get("season"),
        ], 3)

        if visual.get("landscape"):
            visual_parts.append(
                "ландшафт: " + ", ".join(visual["landscape"])
            )

        if visual_parts:
            lines.append(
                "- **Место:** " + "; ".join(visual_parts) + "."
            )

        if group["roads"]:
            for interval in group["roads"][:3]:
                lines.append(
                    "- **Дорога:** "
                    f"{_road_interval_text(interval)} "
                    f"({interval['count']} кадр.)."
                )
        else:
            lines.append("- **Дорога:** признаков не найдено.")

        if group["ocr"]:
            lines.append(
                "- **Текст:** "
                + "; ".join(
                    f"«{item['text']}»"
                    for item in group["ocr"][:4]
                )
                + "."
            )

        if group["speech"]:
            lines.append("- **Речь рядом:**")

            for item in group["speech"]:
                lines.append(
                    f"  - `{timestamp(item['start'])}` — "
                    f"{item['value']}"
                )

        if group["frame_times"]:
            lines.append(
                "- **Кадры:** "
                + ", ".join(
                    f"`{timestamp(moment)}`"
                    for moment in group["frame_times"]
                )
                + (
                    f" и ещё {group['frame_times_total'] - len(group['frame_times'])}."
                    if group["frame_times_total"] > len(group["frame_times"])
                    else "."
                )
            )

        lines.append("")

    return lines


def _road_section(stages, roads, intervals):
    summary = stage_result(
        stages,
        "road_geometry",
    ).get("summary") or {}
    lines = [
        "## 5. Геометрия дороги и придорожные объекты",
        "",
    ]

    if not roads:
        lines.extend([
            "Дорога не подтверждена семантической маской "
            "или геометрия недостаточно надёжна. Это тоже "
            "признак: вероятны сцены без дороги.",
            "",
        ])
        return lines

    sampled = summary.get("sampled_frames")
    detected = summary.get("detected_frames")
    confidence = summary.get("confidence")

    lines.append(
        f"- Подтверждено кадров: {detected or len(roads)}"
        + (f" из {sampled}" if sampled else "")
        + (
            f"; уверенность {round(float(confidence) * 100)}%."
            if confidence is not None
            else "."
        )
    )

    sequence = mapping(summary.get("sequence"))

    if sequence.get("text"):
        lines.append(f"- {sequence['text']}")

    surroundings = records(summary.get("surroundings"))

    if surroundings:
        lines.append(
            "- **Придорожные объекты:** "
            + ", ".join(
                f"{item.get('label')} "
                f"({item.get('frame_count')} кадр.)"
                for item in surroundings[:8]
            )
            + "."
        )

    lines.append("")
    lines.extend([
        "Участки:",
        "",
    ])

    for interval in intervals:
        lines.append(
            f"- `{timestamp(interval['start'])}`–"
            f"`{timestamp(interval['end'])}` — "
            f"{_road_interval_text(interval)} "
            f"({interval['count']} кадр.)."
        )

    lines.append("")

    return lines


def _ocr_section(ocr):
    lines = [
        "## 6. Текст на кадрах",
        "",
        "Уникальные надписи после нормализации. "
        "Низкоуверенные и пустые распознавания отброшены.",
        "",
    ]

    if not ocr:
        lines.extend([
            "Надписей не найдено.",
            "",
        ])
        return lines

    lines.extend([
        "| Время | Текст | Повторов | Уверенность |",
        "| --- | --- | --- | --- |",
    ])

    for item in ocr[:MAX_OCR_GROUPS]:
        score = item["score"]

        lines.append(
            f"| {timestamp(item['first_time'])} "
            f"| {_table_cell(item['text'])} "
            f"| {item['count']} "
            f"| {round(score * 100) if score is not None else '—'}% |"
        )

    lines.append("")

    if len(ocr) > MAX_OCR_GROUPS:
        lines.extend([
            f"Показаны первые {MAX_OCR_GROUPS} "
            f"из {len(ocr)} уникальных надписей.",
            "",
        ])

    return lines


def _speech_section(mentions, speech):
    lines = [
        "## 7. Речь",
        "",
    ]

    if mentions:
        lines.extend([
            "### Упоминания места, адреса и бренды",
            "",
        ])

        for item in mentions[:40]:
            lines.append(
                f"- `{timestamp(item['start'])}` — "
                f"{KIND_NAMES.get(item['kind'], item['kind'])}: "
                f"{item['value']}"
            )

        lines.append("")

    else:
        lines.extend([
            "Упоминаний места, адресов и брендов в речи нет.",
            "",
        ])

    lines.extend([
        "### Транскрипция",
        "",
    ])

    if not speech:
        lines.extend([
            "Доступной транскрипции нет.",
            "",
        ])
        return lines

    for item in speech[:1000]:
        lines.append(
            f"- `{timestamp(item['start'])}` — "
            f"{item['text']}"
        )

    if len(speech) > 1000:
        lines.extend([
            "",
            f"Показаны первые 1000 из {len(speech)} реплик.",
        ])

    lines.append("")

    return lines


def _visual_section(stages, objects):
    profile = mapping(
        stage_result(stages, "visual_profile").get(
            "profile"
        )
    )

    lines = [
        "## 8. Визуальный профиль и объекты",
        "",
    ]

    if profile:
        lines.append(
            "- **Профиль:** "
            + "; ".join(
                _short_list([
                    f"освещённость: {profile.get('lighting')}",
                    f"погода: {profile.get('weather')}",
                    f"сезон: {profile.get('season')}",
                    f"сложность: {profile.get('complexity')}",
                ], 4)
            )
            + "."
        )

        if profile.get("landscape"):
            lines.append(
                "- **Ландшафт:** "
                + ", ".join(profile["landscape"])
                + "."
            )

        sampled = profile.get("sampled_frames")

        if sampled:
            lines.append(
                f"- **Проанализировано кадров:** {sampled}."
            )

        lines.append("")

    if not objects:
        lines.extend([
            "Уникальные объекты не найдены.",
            "",
        ])
        return lines

    lines.extend(["### Уникальные объекты", ""])

    for category in CATEGORY_ORDER:
        items = [
            item
            for item in objects
            if item.get("category") == category
        ]

        if not items:
            continue

        lines.append(
            f"**{CATEGORY_LABELS_RU.get(category, category)}:** "
            + ", ".join(
                f"{item.get('label_ru') or item.get('label')} "
                f"({item.get('frame_count', 0)} кадр.)"
                for item in items[:12]
            )
            + "."
        )

    lines.append("")

    return lines


def _queries_section(queries):
    lines = [
        "## 9. Что проверить на карте",
        "",
    ]

    if not queries:
        lines.extend([
            "Готовых запросов нет: не хватает текстовых улик.",
            "",
        ])
        return lines

    for query in queries:
        lines.append(f"- {query}")

    lines.append("")

    return lines


def _limitations_section():
    return [
        "## 10. Ограничения",
        "",
        "- Отчёт содержит улики и гипотезы, а не "
        "подтверждённый адрес.",
        "- GPS-тег может быть неточным или унаследованным.",
        "- Упоминание места в речи или надписи не "
        "доказывает место съёмки.",
        "- Геометрия дороги и визуальный профиль — "
        "предварительные оценки по кадрам.",
        "- Направления «влево/вправо» относятся к кадру, "
        "а не к сторонам света.",
        "- Похожие кадры не доказывают непрерывность "
        "маршрута.",
        "- Таймкоды и границы локаций приблизительные.",
        "",
    ]


def place_payload(evidence, places):
    """Короткие названия мест без длинных фраз и повторов."""
    result = []
    seen = set()

    for item in evidence:
        if item["kind"] not in ("place_mention", "address"):
            continue

        key = normalized_text(item["value"])

        if key in seen:
            continue

        seen.add(key)
        result.append({
            "text": item["value"],
            "count": item.get("count"),
            "confidence": item.get("confidence"),
            "kind": item["kind"],
        })

    for item in places:
        text = clean_place(item.get("text"))

        if not text:
            continue

        key = normalized_text(text)

        if key in seen:
            continue

        seen.add(key)
        result.append({
            "text": text,
            "count": item.get("count"),
            "confidence": item.get("confidence"),
            "kind": "place_mention",
        })

    return result


def _machine_summary(
    passport,
    gps,
    evidence,
    ocr,
    speech_mentions_list,
    roads,
    intervals,
    groups,
    countries,
    places,
    objects,
    queries,
    stages,
):
    road_summary = stage_result(
        stages,
        "road_geometry",
    ).get("summary") or {}

    return {
        "schema": "video-location-evidence/v1",
        "video": passport,
        "coordinates": gps,
        "countries": [
            {
                "name": item.get("name"),
                "code": item.get("code"),
                "score": item.get("score"),
                "signals": (item.get("signals") or [])[:6],
            }
            for item in countries
        ],
        "places": place_payload(evidence, places),
        "evidence": [
            {
                "kind": item["kind"],
                "value": item["value"],
                "origin": item.get("origin"),
                "time_seconds": item.get("start"),
                "confidence": item.get("confidence"),
                "occurrences": item.get("count"),
            }
            for item in evidence[:60]
        ],
        "ocr": [
            {
                "text": item["text"],
                "first_time_seconds": item["first_time"],
                "occurrences": item["count"],
                "confidence": item["score"],
            }
            for item in ocr[:80]
        ],
        "speech_mentions": [
            {
                "kind": item["kind"],
                "value": item["value"],
                "time_seconds": item.get("start"),
            }
            for item in speech_mentions_list[:40]
        ],
        "road": {
            "summary": road_summary,
            "intervals": intervals[:40],
        },
        "location_groups": [
            {
                "number": group["number"],
                "start_seconds": group["start"],
                "end_seconds": group["end"],
                "scene_numbers": group["scene_numbers"],
                "frame_count": group["frame_count"],
                "frame_times": group["frame_times"],
                "objects": group["objects"],
                "visual": group["visual"],
                "road": group["roads"][:4],
                "ocr": [
                    item["text"]
                    for item in group["ocr"][:6]
                ],
                "speech": [
                    {
                        "time_seconds": item.get("start"),
                        "text": item["value"],
                    }
                    for item in group["speech"]
                ],
            }
            for group in groups[:MAX_MACHINE_GROUPS]
        ],
        "objects": objects,
        "queries": queries,
    }


def _stage_section(stages):
    lines = [
        "## Приложение B. Состояние этапов и поправки",
        "",
        "| Этап | Статус | Наблюдений | Примечание |",
        "| --- | --- | --- | --- |",
    ]

    for name, raw_stage in stages.items():
        stage = mapping(raw_stage)
        status = stage.get("status", "unknown")
        note = stage.get("error") or stage.get("note") or ""

        lines.append(
            f"| {_table_cell(STAGE_NAMES.get(name, name))} "
            f"| {_table_cell(STATUS_NAMES.get(status, status))} "
            f"| {len(records(stage.get('observations')))} "
            f"| {_table_cell(str(note)[:160])} |"
        )

    lines.append("")

    corrections = []

    for name, raw_stage in stages.items():
        for item in records(
            mapping(raw_stage).get("observations")
        ):
            if item.get("corrected_text") is None:
                continue

            corrections.append((
                name,
                item,
            ))

    if corrections:
        lines.extend([
            "### Поправки пользователя",
            "",
        ])

        for name, item in corrections:
            lines.append(
                f"- {STAGE_NAMES.get(name, name)} · "
                f"`{timestamp(item.get('start'))}`: "
                f"{item.get('text', '')!r} → "
                f"{item.get('corrected_text')!r}"
            )

        lines.append("")

    return lines


# ============================================================
# Главная функция
# ============================================================

def render_report(job):
    stages = mapping(job.get("stages"))
    observations = collect_observations(job)
    passport = video_passport(job, stages)
    gps = gps_items(stages)
    speech = collect_speech(observations)
    evidence = collect_evidence(observations, speech)
    ocr = collect_ocr(observations)
    roads = collect_roads(stages, observations)
    intervals = road_intervals(roads)
    mentions = speech_mentions(evidence)
    groups = location_groups(
        stages,
        ocr,
        roads,
        mentions,
    )
    objects = strongest_objects(stages)

    dossier = stage_result(
        stages,
        "location_evidence",
    ).get("dossier") or {}
    countries = records(dossier.get("country_candidates"))
    places = records(dossier.get("place_candidates"))
    queries = search_queries(stages, evidence, ocr)

    lines = [
        f"# Видео: {job.get('name') or 'без названия'} — "
        "отчёт для поиска места съёмки",
        "",
        "> Отчёт собран из сохранённых результатов "
        "анализаторов. Он содержит проверяемые улики, "
        "а не подтверждённый адрес.",
        "",
        "## 1. Краткий вывод",
        "",
    ]

    lines.extend(
        summary_lines(
            passport,
            gps,
            evidence,
            ocr,
            intervals,
            objects,
            countries,
            places,
        )
    )

    lines.extend([
        "",
        f"Сформировано: {datetime.now(timezone.utc).isoformat()}.",
        "",
    ])

    lines.extend(_passport_section(passport))
    lines.extend(_evidence_section(evidence))
    lines.extend(_groups_section(groups))
    lines.extend(
        _road_section(stages, roads, intervals)
    )
    lines.extend(_ocr_section(ocr))
    lines.extend(_speech_section(mentions, speech))
    lines.extend(_visual_section(stages, objects))
    lines.extend(_queries_section(queries))
    lines.extend(_limitations_section())

    machine = _machine_summary(
        passport,
        gps,
        evidence,
        ocr,
        mentions,
        roads,
        intervals,
        groups,
        countries,
        places,
        objects,
        queries,
        stages,
    )

    lines.extend([
        "## Приложение A. Машинно-читаемая сводка",
        "",
        "Компактная структура для интеллектуального поиска. "
        "Содержит те же улики без служебных полей этапов.",
        "",
        json_block(machine),
        "",
    ])

    lines.extend(_stage_section(stages))

    return "\n".join(lines).rstrip() + "\n"
