"""Проверка понимания видео.

Строит вопросы и ответы по уже готовым конспекту, структуре,
расшифровке и найденным местам. Это не тест знаний, а способ
быстро проверить, что основные факты извлечены верно.
"""

import re
from pathlib import Path

from app.errors import SkipStage
from app.observations import observation
from app.places import clean_place
from app.utils.timecodes import timestamp


NUMBER_RE = re.compile(r"\b\d{1,4}\b")


def extract_comprehension(
    folder: Path,
    run_folder: Path,
    stages: dict,
    progress,
) -> dict:
    progress(0, "Читаю конспект и структуру")

    sections = _sections(stages)
    summary = stages.get("summary", {}).get("result") or {}
    segments = _segments(stages)
    places = _places(stages)
    objects = _objects(stages)

    if not sections and not summary and not segments:
        raise SkipStage(
            "Нет материала для вопросов: конспект и "
            "структура не готовы."
        )

    questions = []

    overview = summary.get("overview")

    if overview:
        questions.append({
            "kind": "overview",
            "question": "О чём это видео?",
            "answer": overview,
            "time_seconds": 0.0,
        })

    progress(30, "Формирую вопросы по разделам")

    for section in sections:
        answer = section.get("summary") or ""

        if not answer:
            keywords = section.get("keywords") or []
            answer = (
                "Упоминаются: " + ", ".join(keywords) + "."
                if keywords
                else "Содержание раздела не распознано."
            )

        questions.append({
            "kind": "section",
            "question": (
                f"Что происходит в разделе "
                f"«{section.get('title') or 'без названия'}»?"
            ),
            "answer": answer,
            "time_seconds": section.get("start"),
        })

    progress(55, "Добавляю вопросы по фактам")

    for item in (summary.get("theses") or [])[:4]:
        questions.append({
            "kind": "fact",
            "question": (
                "Что говорится около "
                f"{timestamp(item.get('start'))}?"
            ),
            "answer": item.get("text"),
            "time_seconds": item.get("start"),
        })

    if places:
        questions.append({
            "kind": "places",
            "question": "Какие места упоминаются в видео?",
            "answer": ", ".join(places[:8]) + ".",
            "time_seconds": None,
        })

    numeric = _numeric_fact(segments)

    if numeric:
        questions.append(numeric)

    if objects:
        questions.append({
            "kind": "objects",
            "question": (
                "Какие объекты и ориентиры показаны?"
            ),
            "answer": ", ".join(objects[:10]) + ".",
            "time_seconds": None,
        })

    if sections:
        questions.append({
            "kind": "structure",
            "question": "Из каких разделов состоит видео?",
            "answer": "; ".join(
                f"{section.get('title')} "
                f"({timestamp(section.get('start'))})"
                for section in sections
            ),
            "time_seconds": None,
        })

    progress(100, "Вопросы готовы")

    questions = questions[:16]

    return {
        "questions": questions,
        "question_count": len(questions),
        "observations": [
            observation(
                source="comprehension",
                start=0.0,
                end=max(
                    [
                        float(item.get("time_seconds") or 0)
                        for item in questions
                    ] or [0.0]
                ),
                text="\n".join(
                    f"В: {item['question']}\nО: {item['answer']}"
                    for item in questions
                )[:8000],
                extractor="rule-based-questions",
                data={"questions": questions},
            )
        ],
        "note": (
            "Вопросы собраны по фактическим фразам видео. "
            "Они помогают проверить извлечение, а не оценить "
            "человека."
        ),
    }


def _sections(stages: dict) -> list[dict]:
    result = stages.get("video_structure", {}).get("result") or {}

    return [
        item
        for item in result.get("sections") or []
        if isinstance(item, dict)
    ]


def _segments(stages: dict) -> list[dict]:
    result = stages.get("speech", {}).get("result") or {}

    return [
        item
        for item in result.get("segments") or []
        if isinstance(item, dict) and item.get("text")
    ]


def _places(stages: dict) -> list[str]:
    result = stages.get("location_evidence", {}).get("result") or {}
    dossier = result.get("dossier") or {}

    values = []

    for item in dossier.get("place_candidates") or []:
        text = item.get("text") if isinstance(item, dict) else item
        cleaned = clean_place(text)

        if cleaned and cleaned not in values:
            values.append(cleaned)

    return values


def _objects(stages: dict) -> list[str]:
    result = stages.get("scene_objects", {}).get("result") or {}
    values = []

    for item in result.get("unique_objects") or []:
        label = (
            item.get("label_ru") or item.get("label")
            if isinstance(item, dict)
            else None
        )

        if label and label not in values:
            values.append(str(label))

    return values


def _numeric_fact(segments):
    for item in segments:
        match = NUMBER_RE.search(item.get("text", ""))

        if not match:
            continue

        return {
            "kind": "number",
            "question": (
                "Что упоминается в связи с числом "
                f"{match.group(0)}?"
            ),
            "answer": item.get("text"),
            "time_seconds": item.get("start"),
        }

    return None
