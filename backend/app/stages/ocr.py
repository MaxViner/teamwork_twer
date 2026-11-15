import math
from functools import lru_cache
from pathlib import Path
from typing import Callable

from app.observations import observation
from app.utils.packages import package_version
from app.utils.paths import relative


@lru_cache(maxsize=1)
def ocr_reader():
    import easyocr

    return easyocr.Reader(
        ["ru", "en"],
        gpu=False,
    )


def extract_ocr(
    folder: Path,
    run_folder: Path,
    video: Path,
    duration: float,
    stages: dict,
    options: dict,
    progress: Callable[[str], None],
) -> dict:
    from PIL import Image

    from app.media.ffmpeg import extract_frame

    count = options["max_frames"]
    times = _select_timestamps(duration, count, stages)

    reader = ocr_reader()
    observations = []
    frames = []
    total = len(times)

    for index, timestamp in enumerate(times):
        percent = (index + 1) / total * 100

        progress(
            percent,
            f"OCR: кадр {index + 1} из {total}",
        )
        frame = run_folder / f"frame_{index:03d}.jpg"
        extract_frame(video, frame, timestamp)

        frame_relative = relative(folder, frame)
        recognized = reader.readtext(str(frame))

        with Image.open(frame) as image:
            observations.extend(
                _build_text_observations(
                    folder=folder,
                    run_folder=run_folder,
                    image=image,
                    frame_relative=frame_relative,
                    timestamp=timestamp,
                    recognized=recognized,
                )
            )

        frames.append({
            "timestamp": timestamp,
            "artifact": frame_relative,
        })

    return {
        "frames": frames,
        "observations": observations,
    }


def _select_timestamps(
    duration: float,
    count: int,
    stages: dict,
) -> list[float]:
    times = [
        duration * (index + 0.5) / count
        for index in range(count)
    ]

    times.extend(_scene_centers(stages))

    times = sorted({
        round(min(max(0, value), duration * 0.999), 6)
        for value in times
    })

    return _limit_timestamps(times, count)


def _scene_centers(stages: dict) -> list[float]:
    scene_stage = stages["scenes"]

    if scene_stage["status"] != "completed":
        return []

    intervals = scene_stage["result"].get("intervals", [])

    return [
        (start + end) / 2
        for start, end in intervals
    ]


def _limit_timestamps(times: list[float], count: int) -> list[float]:
    if len(times) <= count:
        return times

    return [
        times[
            min(
                len(times) - 1,
                int((index + 0.5) * len(times) / count),
            )
        ]
        for index in range(count)
    ]


def _build_text_observations(
    folder: Path,
    run_folder: Path,
    image,
    frame_relative: str,
    timestamp: float,
    recognized,
) -> list[dict]:
    observations = []

    for item_index, (polygon, text, score) in enumerate(recognized):
        text = str(text).strip()

        if not text:
            continue

        crop = _save_crop(
            run_folder=run_folder,
            image=image,
            polygon=polygon,
            index=item_index,
        )

        observations.append(
            observation(
                source="ocr",
                start=timestamp,
                end=timestamp,
                text=text,
                artifact=relative(folder, crop),
                frame_artifact=frame_relative,
                bbox=_normalized_bbox(image, polygon),
                recognition_score=_score(score),
                extractor="EasyOCR",
                data={
                    "version": package_version("easyocr"),
                    "languages": ["ru", "en"],
                    "polygon_pixels": [
                        [float(x), float(y)]
                        for x, y in polygon
                    ],
                    "frame_size": list(image.size),
                    "time_is_approximate": True,
                },
            )
        )

    return observations


def _save_crop(
    run_folder: Path,
    image,
    polygon,
    index: int,
) -> Path:
    left, top, right, bottom = _pixel_bbox(image, polygon)
    crop = run_folder / f"crop_{index:03d}.jpg"

    image.crop((left, top, right, bottom)).convert("RGB").save(crop)
    return crop


def _pixel_bbox(image, polygon) -> tuple[int, int, int, int]:
    width, height = image.size
    points = [(float(x), float(y)) for x, y in polygon]

    left = max(0, min(width - 1, math.floor(
        min(point[0] for point in points)
    )))
    top = max(0, min(height - 1, math.floor(
        min(point[1] for point in points)
    )))
    right = max(left + 1, min(width, math.ceil(
        max(point[0] for point in points)
    )))
    bottom = max(top + 1, min(height, math.ceil(
        max(point[1] for point in points)
    )))

    return left, top, right, bottom


def _normalized_bbox(image, polygon) -> list[float]:
    width, height = image.size
    left, top, right, bottom = _pixel_bbox(image, polygon)

    return [
        left / width,
        top / height,
        right / width,
        bottom / height,
    ]


def _score(value) -> float:
    return min(1.0, max(0.0, float(value)))
