"""Структура видео.

Делит запись на смысловые разделы по сценам и речи, даёт каждому
разделу название и короткое описание. Разделы нужны для быстрой
навигации и для поиска момента по смыслу, а не только по времени.
"""

from pathlib import Path

from app.utils.errors import SkipStage
from app.utils.observations import observation
from app.text import (
    best_sentences,
    keyword_set,
    keywords,
    normalize,
)


TARGET_SECTION_SECONDS = 70.0
MAX_SECTION_SECONDS = 140.0


def extract_video_structure(
    folder: Path,
    run_folder: Path,
    stages: dict,
    progress,
) -> dict:
    prepared = stages.get("prepare", {}).get("result") or {}
    duration = float(prepared.get("duration") or 0.0)

    progress(0, "Читаю сцены и расшифровку")

    intervals = _scene_intervals(stages)
    segments = _speech_segments(stages)
    ocr = _ocr_items(stages)
    frames = _object_frames(stages)

    if duration <= 0 and not intervals:
        raise SkipStage("Нет длительности видео для структуры.")

    blocks = _blocks(intervals, duration)

    if not blocks:
        raise SkipStage("Не удалось выделить разделы видео.")

    progress(30, "Собираю разделы")

    sections = []

    for number, (start, end) in enumerate(blocks, start=1):
        progress(
            30 + number / len(blocks) * 60,
            f"Раздел {number} из {len(blocks)}",
        )

        text_parts = [
            item["text"]
            for item in segments
            if _inside(item.get("start"), start, end)
        ]
        text_parts.extend(
            value
            for moment, value in ocr
            if _inside(moment, start, end)
        )

        block_text = " ".join(text_parts)
        block_keywords = keywords(block_text, 6)
        labels = _object_labels(frames, start, end)
        title = _title(block_keywords, labels, number, len(blocks))
        summary = _summary(block_text)

        sections.append({
            "number": number,
            "start": round(start, 3),
            "end": round(end, 3),
            "title": title,
            "summary": summary,
            "keywords": [
                item["word"]
                for item in block_keywords
            ],
            "objects": labels[:6],
        })

    progress(100, "Структура видео готова")

    chapters = [
        {
            "start": section["start"],
            "title": section["title"],
        }
        for section in sections
    ]

    text = "Разделы: " + "; ".join(
        f"{section['title']} ({section['start']:.0f} с)"
        for section in sections
    )

    return {
        "sections": sections,
        "chapters": chapters,
        "section_count": len(sections),
        "observations": [
            observation(
                source="video_structure",
                start=sections[0]["start"],
                end=sections[-1]["end"],
                text=text[:4000],
                extractor="rule-based-structure",
                data={
                    "sections": sections,
                    "chapters": chapters,
                },
            )
        ],
        "note": (
            "Разделы и названия построены по сценам, речи и "
            "объектам. Это навигация по смыслу, а не монтажный "
            "план автора."
        ),
    }


def _scene_intervals(stages: dict) -> list[list[float]]:
    result = stages.get("scenes", {}).get("result") or {}
    intervals = []

    for value in result.get("intervals") or []:
        if not isinstance(value, (list, tuple)):
            continue

        if len(value) < 2:
            continue

        start = float(value[0])
        end = float(value[1])

        if end > start:
            intervals.append([start, end])

    return sorted(intervals)


def _speech_segments(stages: dict) -> list[dict]:
    result = stages.get("speech", {}).get("result") or {}

    return [
        item
        for item in result.get("segments") or []
        if isinstance(item, dict) and item.get("text")
    ]


def _ocr_items(stages: dict) -> list[tuple[float, str]]:
    stage = stages.get("ocr", {})

    if stage.get("status") != "completed":
        return []

    result = []

    for item in stage.get("observations") or []:
        if item.get("review") == "rejected":
            continue

        text = item.get("corrected_text") or item.get("text")

        if not text:
            continue

        try:
            moment = float(item.get("start") or 0)
        except (TypeError, ValueError):
            moment = 0.0

        result.append((moment, str(text)))

    return result


def _object_frames(stages: dict) -> list[dict]:
    result = stages.get("scene_objects", {}).get("result") or {}

    return [
        item
        for item in result.get("frames") or []
        if isinstance(item, dict)
    ]


def _blocks(intervals, duration):
    if not intervals:
        if duration <= 0:
            return []

        count = max(1, round(duration / TARGET_SECTION_SECONDS))
        step = duration / count

        return [
            (index * step, min(duration, (index + 1) * step))
            for index in range(count)
        ]

    blocks = []
    start = intervals[0][0]
    end = intervals[0][1]

    for next_start, next_end in intervals[1:]:
        length = end - start

        if (
            length >= TARGET_SECTION_SECONDS
            and next_start - end > 1.5
        ) or length >= MAX_SECTION_SECONDS:
            blocks.append((start, end))
            start = next_start
            end = next_end

        else:
            end = next_end

    blocks.append((start, end))

    return blocks


def _inside(value, start, end):
    try:
        moment = float(value)
    except (TypeError, ValueError):
        return False

    return start <= moment < end


def _object_labels(frames, start, end):
    counts = {}

    for frame in frames:
        moment = frame.get("timestamp")

        if not _inside(moment, start, end):
            continue

        for item in frame.get("objects") or []:
            label = item.get("label_ru") or item.get("label")

            if label:
                counts[label] = counts.get(label, 0) + 1

    return [
        label
        for label, _ in sorted(
            counts.items(),
            key=lambda pair: -pair[1],
        )
    ]


def _title(block_keywords, labels, number, total):
    names = [
        item["word"]
        for item in block_keywords[:3]
    ]

    if number == 1:
        prefix = "Начало"
    elif number == total:
        prefix = "Финал"
    else:
        prefix = f"Раздел {number}"

    if names:
        return f"{prefix}: " + ", ".join(names)

    if labels:
        return f"{prefix}: " + ", ".join(labels[:3])

    return prefix


def _summary(text):
    if not text:
        return ""

    frequent = keyword_set(text, 30)
    picked = best_sentences(
        [(0.0, text)],
        frequent,
        limit=1,
    )

    if picked:
        return picked[0]["text"]

    return normalize(text)[:240]
