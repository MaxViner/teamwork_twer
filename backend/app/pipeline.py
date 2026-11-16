from pathlib import Path
from typing import Callable

from app.stages.metadata import extract_metadata
from app.stages.ocr import extract_ocr
from app.stages.prepare import prepare
from app.stages.scenes import extract_scenes
from app.stages.speech import extract_speech
from app.stages.context import (
    extract_visual,
    extract_audio_events,
    extract_structure,
)

STAGES = (
    "prepare",
    "metadata",
    "scenes",
    "speech",
    "ocr",
    "visual",
    "audio_events",
    "structure",
)


def run_stage(
    stage: str,
    folder: Path,
    run_id: str,
    options: dict,
    stages: dict,
    progress: Callable[[float, str], None],
) -> dict:
    run_folder = folder / "runs" / run_id
    run_folder.mkdir(parents=True, exist_ok=True)

    if stage == "prepare":
        return prepare(folder, run_folder, progress)

    prepared = stages["prepare"]["result"]
    video = folder / prepared["preview"]

    handlers = {
        "metadata": lambda: extract_metadata(folder, run_folder),
        "scenes": lambda: extract_scenes(
            folder, run_folder, video, prepared["duration"], progress
        ),
        "speech": lambda: extract_speech(
            folder, run_folder, video, prepared, options, progress
        ),
        "ocr": lambda: extract_ocr(
            folder,
            run_folder,
            video,
            prepared["duration"],
            stages,
            options,
            progress,
        ),
                "visual": lambda: extract_visual(
            folder,
            run_folder,
            video,
            prepared,
            stages,
            options,
            progress,
        ),

        "audio_events": lambda: extract_audio_events(
            folder,
            run_folder,
            video,
            prepared,
            progress,
        ),

        "structure": lambda: extract_structure(
            folder,
            run_folder,
            stages,
            progress,
        ),
    }

    if stage not in handlers:
        raise ValueError(f"Неизвестный этап: {stage}")

    return handlers[stage]()
