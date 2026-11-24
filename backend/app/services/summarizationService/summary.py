"""Конспект видео.

Собирает расшифровку речи, надписи на кадрах и объекты сцены,
затем выделяет темы, тезисы и выводы. Это извлекательный конспект
на основе частот и маркеров речи — без внешней языковой модели.

Файлов этап не читает и не пишет: работает только с stages.
storage принимается для единообразия сигнатур агрегаторов
(как в location и structure) и в теле не используется.
"""

from app.storage import StorageService
from app.utils.errors import SkipStage
from app.utils.observations import observation
from app.text import (
    best_sentences,
    keyword_set,
    keywords,
    normalize,
    sentences,
)


CONCLUSION_MARKERS = (
    "в общем",
    "итак",
    "таким образом",
    "вывод",
    "получилось",
    "в итоге",
    "значит",
    "короче",
    "главное",
    "в заключение",
    "на этом всё",
    "на этом все",
)

FILLER = {
    "всем привет",
    "пока",
    "пока-пока",
    "ну",
    "ладно",
    "спасибо",
}


def extract_summary(
    storage: StorageService,
    stages: dict,
    progress,
) -> dict:
    progress(0, "Читаю расшифровку и надписи")

    segments = _speech_segments(stages)
    ocr_text = _ocr_text(stages)
    objects = _objects(stages)

    if not segments and not ocr_text:
        raise SkipStage(
            "Нет текста для конспекта: речь и надписи "
            "не распознаны."
        )

    transcript = " ".join(
        item["text"]
        for item in segments
    )
    combined = " ".join(
        value for value in (transcript, ocr_text) if value
    )

    progress(40, "Выделяю темы и ключевые слова")

    frequent = keyword_set(combined, 40)
    topics = keywords(combined, 12)

    progress(65, "Отбираю тезисы и выводы")

    items = [
        (item["start"], item["text"])
        for item in segments
        if normalize(item["text"]) not in FILLER
    ]

    theses = best_sentences(items, frequent, limit=8)
    conclusions = _conclusions(items, frequent)

    progress(85, "Собираю краткий обзор")

    overview = _overview(
        topics,
        theses,
        objects,
    )

    progress(100, "Конспект готов")

    observation_item = observation(
        source="summary",
        start=0.0,
        end=max(
            [item["end"] for item in segments] or [0.0]
        ),
        text=overview or "Конспект сформирован.",
        extractor="rule-based-summary",
        data={
            "topics": topics,
            "theses": theses,
            "conclusions": conclusions,
            "object_topics": objects[:8],
            "segment_count": len(segments),
            "method": "частотный отбор предложений",
        },
    )

    return {
        "overview": overview,
        "topics": topics,
        "theses": theses,
        "conclusions": conclusions,
        "object_topics": objects[:8],
        "segment_count": len(segments),
        "observations": [observation_item],
        "note": (
            "Конспект извлекательный: это самые характерные "
            "фразы и темы, а не пересказ языковой модели."
        ),
    }


def _speech_segments(stages: dict) -> list[dict]:
    result = stages.get("speech", {}).get("result") or {}

    return [
        item
        for item in result.get("segments") or []
        if isinstance(item, dict)
        and item.get("text")
        and item.get("start") is not None
    ]


def _ocr_text(stages: dict) -> str:
    stage = stages.get("ocr", {})

    if stage.get("status") != "completed":
        return ""

    values = []

    for item in stage.get("observations") or []:
        if item.get("review") == "rejected":
            continue

        text = item.get("corrected_text") or item.get("text")

        if text:
            values.append(str(text))

    return " ".join(values)


def _objects(stages: dict) -> list[dict]:
    result = stages.get("scene_objects", {}).get("result") or {}

    objects = result.get("unique_objects") or []

    return [
        {
            "label": item.get("label_ru") or item.get("label"),
            "frame_count": item.get("frame_count"),
            "max_area_percent": item.get("max_area_percent"),
        }
        for item in objects[:10]
        if isinstance(item, dict)
    ]


def _conclusions(
    items: list[tuple[float, str]],
    frequent: set[str],
) -> list[dict]:
    found = []

    for moment, text in items:
        for sentence in sentences(text):
            lowered = sentence.casefold()

            if not any(
                marker in lowered
                for marker in CONCLUSION_MARKERS
            ):
                continue

            if len(sentence) < 12:
                continue

            found.append({
                "start": round(float(moment), 3),
                "text": sentence,
            })

    result = []
    seen = set()

    for item in sorted(found, key=lambda entry: entry["start"]):
        key = normalize(item["text"])[:80]

        if key in seen:
            continue

        seen.add(key)
        result.append(item)

        if len(result) >= 4:
            break

    return result


def _overview(topics, theses, objects) -> str:
    parts = []

    if theses:
        parts.append(
            " ".join(
                item["text"]
                for item in theses[:2]
            )
        )

    names = [
        item["word"]
        for item in topics[:6]
    ]

    if names:
        parts.append(
            "Частые темы: " + ", ".join(names) + "."
        )

    labels = [
        item["label"]
        for item in objects[:5]
        if item.get("label")
    ]

    if labels:
        parts.append(
            "В кадре замечены: " + ", ".join(labels) + "."
        )

    text = " ".join(parts).strip()

    return text[:1200]