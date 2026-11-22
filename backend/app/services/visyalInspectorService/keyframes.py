"""Группировка кадров по локациям.

Берёт уже сохранённые кадры визуальных этапов, объединяет их по
таймкоду и раскладывает в последовательные группы: одна сцена или
непрерывный кусок видео. Эти группы используют интерфейс и отчёт,
чтобы сотни кадров не превращались в одну бесконечную ленту.
"""

from app.utils.timecodes import numeric_time

# Соседние кадры одной сцены не разрываем, даже если между ними
# несколько секунд. Разрыв больше этого значения начинает новую
# локацию, когда сцены не определены.
GROUP_GAP_SECONDS = 30.0


def collect_frames(stages: dict) -> list[dict]:
    """Собирает кадры visual_profile, scene_objects и OCR по таймкоду."""
    collected = {}

    for stage_name in (
        "visual_profile",
        "scene_objects",
        "ocr",
    ):
        stage = stages.get(stage_name) or {}
        result = stage.get("result") or {}

        for frame in result.get("frames") or []:
            if not isinstance(frame, dict):
                continue

            moment = numeric_time(frame.get("timestamp"))

            if moment is None:
                continue

            key = round(moment, 3)
            item = collected.setdefault(key, {
                "timestamp": moment,
                "artifact": None,
                "objects": [],
                "descriptors": {},
                "metrics": {},
            })

            if not item["artifact"] and frame.get("artifact"):
                item["artifact"] = frame["artifact"]

            if isinstance(frame.get("objects"), list):
                item["objects"] = frame["objects"]

            if isinstance(frame.get("descriptors"), dict):
                item["descriptors"] = frame["descriptors"]

            if isinstance(frame.get("metrics"), dict):
                item["metrics"] = frame["metrics"]

    return [
        collected[key]
        for key in sorted(collected)
    ]


def scene_intervals(stages: dict) -> list[list[float]]:
    """Возвращает проверенные интервалы сцен."""
    result = (
        (stages.get("scenes") or {}).get("result") or {}
    )

    intervals = []

    for value in result.get("intervals") or []:
        if not isinstance(value, (list, tuple)):
            continue

        if len(value) < 2:
            continue

        start = numeric_time(value[0])
        end = numeric_time(value[1])

        if start is None or end is None or end <= start:
            continue

        intervals.append([start, end])

    return intervals


def scene_index(
    intervals: list[list[float]],
    moment: float,
) -> int | None:
    for index, (start, end) in enumerate(intervals):
        if start <= moment < end:
            return index

    return None


def group_frames(
    frames: list[dict],
    intervals: list[list[float]],
    gap_seconds: float = GROUP_GAP_SECONDS,
) -> list[dict]:
    """Раскладывает кадры на последовательные локации."""
    groups = []
    current = None

    for frame in sorted(
        frames,
        key=lambda item: item["timestamp"],
    ):
        moment = frame["timestamp"]
        index = scene_index(intervals, moment)
        key = (
            f"scene:{index}"
            if index is not None
            else "free"
        )

        if (
            current is None
            or current["key"] != key
            or moment - current["end"] > gap_seconds
        ):
            current = {
                "key": key,
                "scene_indexes": [],
                "start": moment,
                "end": moment,
                "frames": [],
            }
            groups.append(current)

        current["frames"].append(frame)
        current["end"] = moment

        if (
            index is not None
            and index not in current["scene_indexes"]
        ):
            current["scene_indexes"].append(index)

    for number, group in enumerate(groups, start=1):
        group["number"] = number
        group["scene_numbers"] = [
            index + 1
            for index in group["scene_indexes"]
        ]

    return groups
