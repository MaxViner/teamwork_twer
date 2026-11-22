"""Экспорт расшифровки речи.

Собирает реплики из готового этапа speech и отдаёт их в JSON,
VTT или SRT. Таймкоды берутся из сохранённых сегментов Whisper;
пословные метки сохраняются, если модель их дала.
"""

from app.utils.timecodes import numeric_time


def transcript_payload(job: dict) -> dict:
    stage = (job.get("stages") or {}).get("speech") or {}
    result = stage.get("result") or {}
    segments = []

    for item in result.get("segments") or []:
        if not isinstance(item, dict) or not item.get("text"):
            continue

        start = numeric_time(item.get("start"))
        end = numeric_time(item.get("end"))

        if start is None:
            continue

        segments.append({
            "start": round(start, 3),
            "end": round(end if end is not None else start, 3),
            "text": str(item["text"]).strip(),
            "speaker": item.get("speaker"),
            "probability": item.get("probability"),
            "uncertain": bool(item.get("uncertain")),
            "words": item.get("words") or [],
        })

    segments.sort(key=lambda item: item["start"])

    return {
        "language": result.get("language"),
        "language_probability": result.get("language_probability"),
        "speaker_method": result.get("speaker_method"),
        "speakers": result.get("speakers") or [],
        "segment_count": len(segments),
        "time_is_approximate": True,
        "segments": segments,
    }


def to_vtt(payload: dict, title: str = "Расшифровка") -> str:
    lines = ["WEBVTT", "", f"NOTE {title}", ""]

    for index, item in enumerate(payload["segments"], start=1):
        text = _line(item)

        lines.append(
            f"{_clock(item['start'], ',')} --> "
            f"{_clock(item['end'], ',')}"
        )
        lines.append(text)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def to_srt(payload: dict) -> str:
    lines = []

    for index, item in enumerate(payload["segments"], start=1):
        lines.append(str(index))
        lines.append(
            f"{_clock(item['start'])} --> {_clock(item['end'])}"
        )
        lines.append(_line(item))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _line(item: dict) -> str:
    speaker = item.get("speaker")
    text = item["text"]

    if item.get("uncertain"):
        text = f"{text} [возможна неточность]"

    return f"{speaker}: {text}" if speaker else text


def _clock(value: float, separator: str = ".") -> str:
    total = max(0.0, float(value))
    milliseconds = int(round(total * 1000))
    seconds, ms = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)

    return (
        f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        f"{separator}{ms:03d}"
    )
