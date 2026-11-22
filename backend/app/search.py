"""Поиск внутри задания.

Ищет строку по расшифровке речи, надписям, объектам, ориентирам,
конспекту и разделам. Возвращает моменты с таймкодами, чтобы
интерфейс мог сразу перемотать видео.
"""

from app.text import normalize, words


def search_job(job: dict, query: str, limit: int = 60) -> list[dict]:
    normalized = normalize(query)

    if len(normalized) < 2:
        return []

    terms = words(normalized) or [normalized]
    results = []

    for item in _speech(job):
        score = _score(item["text"], normalized, terms)

        if score <= 0:
            continue

        results.append({
            "kind": "speech",
            "label": item.get("speaker") or "Речь",
            "text": item["text"],
            "start": item.get("start"),
            "end": item.get("end"),
            "speaker": item.get("speaker"),
            "score": score,
        })

    for item in _observations(job, "ocr"):
        score = _score(item["text"], normalized, terms)

        if score <= 0:
            continue

        results.append({
            "kind": "ocr",
            "label": "Надпись",
            "text": item["text"],
            "start": item.get("start"),
            "end": item.get("end"),
            "artifact": item.get("frame_artifact"),
            "score": score,
        })

    for item in _observations(job, "location_evidence"):
        text = item["text"]

        if item.get("data", {}).get("kind") in {
            "visual_profile",
            "audio_profile",
            "scene_profile",
        }:
            continue

        score = _score(text, normalized, terms)

        if score <= 0:
            continue

        results.append({
            "kind": "evidence",
            "label": "Улика",
            "text": text,
            "start": item.get("start"),
            "end": item.get("end"),
            "score": score,
        })

    for item in _objects(job):
        score = _score(item["text"], normalized, terms)

        if score <= 0:
            continue

        results.append({
            "kind": "object",
            "label": "Объект",
            "text": item["text"],
            "start": item.get("start"),
            "end": item.get("end"),
            "artifact": item.get("artifact"),
            "score": score,
        })

    for item in _landmarks(job):
        score = _score(item["text"], normalized, terms)

        if score <= 0:
            continue

        results.append({
            "kind": "landmark",
            "label": "Ориентир",
            "text": item["text"],
            "start": item.get("start"),
            "end": item.get("end"),
            "artifact": item.get("artifact"),
            "score": score,
        })

    for item in _faces(job):
        score = _score(item["text"], normalized, terms)

        if score <= 0:
            continue

        results.append({
            "kind": "person",
            "label": "Человек",
            "text": item["text"],
            "start": item.get("start"),
            "end": item.get("end"),
            "artifact": item.get("artifact"),
            "score": score,
        })

    for item in _sections(job):
        score = _score(item["text"], normalized, terms)

        if score <= 0:
            continue

        results.append({
            "kind": "section",
            "label": "Раздел",
            "text": item["text"],
            "start": item.get("start"),
            "end": item.get("end"),
            "score": score,
        })

    results.sort(
        key=lambda item: (
            -item["score"],
            item.get("start") is None,
            item.get("start") or 0,
        )
    )

    return results[:limit]


def _score(text, normalized, terms):
    value = normalize(text)

    if not value:
        return 0

    if normalized in value:
        return 3

    hits = sum(1 for term in terms if term in value)

    if hits == len(terms):
        return 2

    if hits:
        return 1

    return 0


def _stage(job, name):
    return (job.get("stages") or {}).get(name) or {}


def _speech(job):
    result = _stage(job, "speech").get("result") or {}

    return [
        item
        for item in result.get("segments") or []
        if isinstance(item, dict) and item.get("text")
    ]


def _observations(job, stage_name):
    stage = _stage(job, stage_name)

    if stage.get("status") not in ("completed", "partial"):
        return []

    values = []

    for item in stage.get("observations") or []:
        if item.get("review") == "rejected":
            continue

        text = item.get("corrected_text") or item.get("text")

        if not text:
            continue

        values.append({
            "text": str(text),
            "start": item.get("start"),
            "end": item.get("end"),
            "artifact": item.get("frame_artifact"),
            "data": item.get("data") or {},
        })

    return values


def _objects(job):
    result = _stage(job, "scene_objects").get("result") or {}
    values = []

    for frame in result.get("frames") or []:
        if not isinstance(frame, dict):
            continue

        for item in frame.get("objects") or []:
            label = item.get("label_ru") or item.get("label")

            if not label:
                continue

            values.append({
                "text": str(label),
                "start": frame.get("timestamp"),
                "end": frame.get("timestamp"),
                "artifact": frame.get("artifact"),
            })

    return values


def _landmarks(job):
    result = _stage(job, "landmarks").get("result") or {}
    values = []

    for frame in result.get("frames") or []:
        if not isinstance(frame, dict):
            continue

        labels = [
            item.get("label_ru") or item.get("label")
            for item in frame.get("landmarks") or []
            if isinstance(item, dict)
        ]
        signs = frame.get("signs") or []
        text = ", ".join(
            str(value)
            for value in (labels + signs)
            if value
        )

        if not text:
            continue

        values.append({
            "text": text,
            "start": frame.get("timestamp"),
            "end": frame.get("timestamp"),
            "artifact": frame.get("artifact"),
        })

    return values


def _faces(job):
    result = _stage(job, "faces").get("result") or {}
    values = []

    for person in result.get("people") or []:
        if not isinstance(person, dict):
            continue

        label = person.get("label")

        if not label:
            continue

        best = person.get("best_frame") or {}
        timestamps = person.get("timestamps") or []

        values.append({
            "text": f"{label}, появлений: {person.get('frame_count')}",
            "start": person.get("first_start"),
            "end": person.get("last_end"),
            "artifact": best.get("artifact"),
            "timestamps": timestamps,
        })

    return values


def _sections(job):
    result = _stage(job, "video_structure").get("result") or {}
    values = []

    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue

        text = " ".join([
            str(section.get("title") or ""),
            str(section.get("summary") or ""),
            " ".join(section.get("keywords") or []),
            " ".join(section.get("objects") or []),
        ])

        values.append({
            "text": text.strip(),
            "start": section.get("start"),
            "end": section.get("end"),
        })

    summary = _stage(job, "summary").get("result") or {}
    overview = summary.get("overview")

    if overview:
        values.append({
            "text": str(overview),
            "start": 0,
            "end": None,
        })

    for item in summary.get("theses") or []:
        values.append({
            "text": str(item.get("text") or ""),
            "start": item.get("start"),
            "end": item.get("start"),
        })

    return values
