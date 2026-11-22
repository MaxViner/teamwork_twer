"""Извлечение проверяемых пространственных утверждений из речи и OCR.

Этап 1 геосцены: это утверждения источников, НЕ координаты и НЕ карта.
Положение «рядом» в речи не переводится в метры; «там» без указателя
не превращается в левую/правую сторону или направление на север.

Публичный интерфейс: extract_geo_claims(stages) -> dict.
Модуль не скачивает модели, не читает медиа, не обращается к сети.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

SCHEMA_VERSION = 1
MAX_CLAIMS = 100
MAX_SUPPORT = 8

# «Церковь рядом с усадьбой» и «церковь на другом конце деревни» —
# несовместимые утверждения. Здесь сохраняем исходную связь и её текст.
REGION = re.compile(r"\b(?P<name>Тверск(?:ая|ой|ую|ое|ом)\s+област[ьи]|Тверск(?:ой|ого|ом)\s+губерни[ия]|Тверск(?:ой|ого|ом)\s+район[еа]?)\b", re.I)
VILLAGE = re.compile(r"\b(?:заброшенн\w*|исчезнувш\w*|бывш\w*|покинут\w*|опустевш\w*)\s+(?:деревн\w*|сел\w*|пос[её]л\w*)|\b(?:деревн\w*|сел\w*|пос[её]л\w*)\s+(?:заброшенн\w*|исчезнувш\w*|бывш\w*)", re.I)
MANOR = re.compile(r"\b(?:усадьб\w*|усадебн\w*\s+(?:дом\w*|комплекс\w*))\b", re.I)
CHURCH = re.compile(r"\b(?:церк(?:овь|ви|овью|вей)|храм\w*|колокольн\w*)\b", re.I)
RIVER = re.compile(r"\b(?:рек(?:а|и|у|ой|е)|речк\w*|руч[её]й|ручья|ручью|ручьем)\b", re.I)
ROAD = re.compile(r"\b(?:дорог\w*|тракт\w*|грунтовк\w*)\b", re.I)
OLD_MAP = re.compile(r"\b(?:царск\w*|стар\w*|старинн\w*|дореволюционн\w*|историческ\w*)\s+(?:карт\w*|план\w*)|\b(?:карт\w*|план\w*)\s+(?:царск\w*|стар\w*|старинн\w*|дореволюционн\w*)", re.I)
COUNT_HOUSES = re.compile(r"\b(?P<count>\d{1,3}|двенадцат[ьи]|двенадцать)\s+(?:дом(?:ов|а)?|двор(?:ов|а)?)\b", re.I)
NEAR_WORD = re.compile(r"\b(?:рядом|неподал[её]ку|возле|около|поблизости|рядом\s+с|при\s+усадьбе)\b", re.I)
UNCERTAIN = re.compile(r"\b(?:кажется|возможно|вроде|предполагаю|думаю|может\s+быть|не\s+знаю|могу\s+ошибаться)\b", re.I)
NEGATION = re.compile(r"\b(?:нет|не\s+было|не\s+видно|отсутств\w*|не\s+наш[её]л)\b", re.I)


def _items(value: Any) -> list[dict]:
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if 0 <= number < float("inf") else None
    except (TypeError, ValueError, OverflowError):
        return None


def _stage(stages: dict, name: str) -> dict:
    item = stages.get(name) or {}
    return item if isinstance(item, dict) and item.get("status") in ("completed", "partial") else {}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _source_rows(stages: dict) -> list[dict]:
    """Use reviewed source observations; never read stale location_evidence summaries.

    Whole-transcript corrections have no reliable segment alignment; their
    timestamp is deliberately null. Raw segments are then not reused.
    """
    rows = []
    speech = _stage(stages, "speech")
    source = _items(speech.get("observations"))
    result_segments = _items((speech.get("result") or {}).get("segments"))
    if source:
        for item in source:
            if item.get("review") == "rejected":
                continue
            correction = item.get("corrected_text")
            if correction is not None:
                rows.append({"source": "speech", "text": correction,
                             "start": None, "end": None, "artifact": item.get("artifact"),
                             "review": item.get("review"), "observation_id": item.get("id"),
                             "alignment": "unknown_after_edit"})
            else:
                segments = _items((item.get("data") or {}).get("segments"))
                for segment in segments:
                    rows.append({"source": "speech", "text": segment.get("text"),
                                 "start": segment.get("start"), "end": segment.get("end"),
                                 "artifact": None, "review": item.get("review"),
                                 "observation_id": item.get("id"),
                                 "uncertain": segment.get("uncertain")})
                if not segments:
                    rows.append({"source": "speech", "text": item.get("text"),
                                 "start": item.get("start"), "end": item.get("end"),
                                 "artifact": None, "review": item.get("review"),
                                 "observation_id": item.get("id")})
    else:
        for segment in result_segments:
            rows.append({"source": "speech", "text": segment.get("text"),
                         "start": segment.get("start"), "end": segment.get("end"),
                         "uncertain": segment.get("uncertain")})

    for item in _items(_stage(stages, "ocr").get("observations")):
        if item.get("review") == "rejected":
            continue
        rows.append({"source": "ocr", "text": item.get("corrected_text")
                     if item.get("corrected_text") is not None else item.get("text"),
                     "start": item.get("start"), "end": item.get("end"),
                     "artifact": item.get("frame_artifact") or item.get("artifact"),
                     "observation_id": item.get("id"), "review": item.get("review"),
                     "recognition_score": item.get("recognition_score")})
    return [row for row in rows if _clean(row.get("text"))]


def _speech_context(rows: list[dict], index: int) -> list[dict]:
    """Adjacent turns are context, NOT independent support or spatial proof."""
    base = rows[index]
    start = _number(base.get("start"))
    if start is None or base["source"] != "speech":
        return []
    result = []
    for j in (index - 1, index + 1):
        if not (0 <= j < len(rows)) or rows[j]["source"] != "speech":
            continue
        item = rows[j]
        moment = _number(item.get("start"))
        if moment is not None and abs(moment - start) <= 15:
            result.append({"start": moment, "text": _clean(item["text"])[:220]})
    return result


def _evidence(row: dict, text: str, context: list[dict] | None = None) -> dict:
    item = {"source": row["source"], "start": _number(row.get("start")),
            "end": _number(row.get("end")), "quote": text[:340],
            "artifact": row.get("artifact"), "observation_id": row.get("observation_id"),
            "review": row.get("review"), "alignment": row.get("alignment")}
    if context:
        item["adjacent_speech_context"] = context
    return item


def _sentences(text: str) -> list[str]:
    # Keep ordinary commas together: 'усадьба огромная, и там вот церковь'.
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+|\s*[;\n]+\s*", text) if part.strip()]


def _mentions(text: str) -> list[tuple[str, str, str, dict]]:
    result = []
    for pattern, subject, predicate, value in (
        (REGION, "region", "mentioned_as_region", "Тверская область"),
        (VILLAGE, "settlement", "described_as", "abandoned_or_former_village"),
        (MANOR, "manor", "mentioned", "manor_estate"),
        (CHURCH, "church", "mentioned", "church_or_church_site"),
        (RIVER, "river", "mentioned", "river_or_stream"),
        (ROAD, "road", "mentioned", "road"),
    ):
        if pattern.search(text):
            details = {"region_name_raw": pattern.search(text).group(0)} if subject == "region" else {}
            result.append((subject, predicate, value, details))
    if OLD_MAP.search(text):
        result.append(("historic_map", "mentioned", "old_map", {}))
    for match in COUNT_HOUSES.finditer(text):
        count = match.group("count")
        count = 12 if count.casefold().startswith("двенадцат") else int(count)
        if OLD_MAP.search(text):
            result.append(("settlement", "house_count_on_old_map_mentioned", count,
                           {"unit_raw": match.group(0), "map_edition_unverified": True}))
        else:
            result.append(("settlement", "house_count_mentioned", count,
                           {"unit_raw": match.group(0), "historical_map_link_unverified": True}))
    if MANOR.search(text) and CHURCH.search(text):
        # Mere co-mention is not a metric distance, even when the speaker
        # says «рядом». Preserve which relation was literally asserted.
        relation = "near_according_to_speaker" if NEAR_WORD.search(text) else "co_mentioned_in_utterance"
        result.append(("manor", relation, "church", {"metric_distance_m": None}))
    return result


def extract_geo_claims(stages: dict, *, max_claims: int = MAX_CLAIMS) -> dict:
    """Return small source-backed geo claims, without map coordinates.

    One statement can refer to another scene; do not group sources by
    assumed camera location. A later geo_scene stage can use these IDs.
    """
    if not isinstance(stages, dict):
        stages = {}
    rows = _source_rows(stages)
    merged: dict[tuple, dict] = {}
    max_claims = max(1, min(MAX_CLAIMS, int(max_claims)))
    for index, row in enumerate(rows):
        text = _clean(row["text"])
        if row["source"] == "ocr" and row.get("review") != "accepted":
            score = _number(row.get("recognition_score"))
            if score is not None and score < 0.45:
                continue
        for sentence in _sentences(text):
            uncertain = bool(UNCERTAIN.search(sentence) or row.get("uncertain"))
            denied = bool(NEGATION.search(sentence))
            for subject, predicate, value, details in _mentions(sentence):
                if denied and subject not in {"region", "historic_map"}:
                    # 'рядом нет церкви' cannot support 'church nearby'.
                    continue
                if predicate == "near_according_to_speaker" and uncertain:
                    predicate = "possibly_near_according_to_speaker"
                key = (subject, predicate, value)
                if key not in merged:
                    merged[key] = {"id": "", "subject": subject, "predicate": predicate,
                                   "value": value, "details": details,
                                   "modality": "uncertain" if uncertain else "asserted",
                                   "visually_verified": False, "map_verified": False,
                                   "support": [], "support_count": 0}
                claim = merged[key]
                claim["support_count"] += 1
                if len(claim["support"]) < MAX_SUPPORT:
                    claim["support"].append(_evidence(row, sentence, _speech_context(rows, index)
                                                      if predicate.endswith("old_map_mentioned") else None))
                if not uncertain:
                    claim["modality"] = "asserted"
    ordered = list(merged.values())
    priority = {"mentioned_as_region": 0, "house_count_on_old_map_mentioned": 1,
                "near_according_to_speaker": 2, "possibly_near_according_to_speaker": 3,
                "described_as": 4, "mentioned": 5, "co_mentioned_in_utterance": 6,
                "house_count_mentioned": 7}
    ordered.sort(key=lambda claim: (priority.get(claim["predicate"], 9),
                                   (claim["support"][0]["start"] if claim["support"]
                                    and claim["support"][0]["start"] is not None else float("inf")),
                                   claim["subject"]))
    for i, claim in enumerate(ordered[:max_claims], 1):
        claim["id"] = f"geo-claim-{i:03d}"
    return {"schema_version": SCHEMA_VERSION,
            "source_rows": len(rows), "total_claims": len(ordered),
            "claims": ordered[:max_claims],
            "limitations": [
                "Речь и OCR передают утверждения источника, не удостоверенные факты о точке съёмки.",
                "Отношение 'рядом' не задаёт расстояние, сторону или направление.",
                "Совместное упоминание усадьбы и церкви не подтверждает их физическое соседство.",
                "Класс здания, одинаковый на кадрах, не удостоверяет тождество объекта.",
            ]}
