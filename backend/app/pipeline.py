"""Порядок этапов анализа.

Здесь перечислены все этапы и описано, какой анализатор вызывать
для каждого из них. executor передаёт сюда задание, а pipeline
запускает нужную функцию с подготовленными аргументами.
"""

from pathlib import Path
from typing import Callable


from app.stages.metadata import extract_metadata
from app.stages.ocr import extract_ocr
from app.stages.prepare import prepare
from app.stages.scenes import extract_scenes
from app.stages.speech import extract_speech

from app.stages.scene_objects import extract_scene_objects
from app.stages.location import extract_location_evidence
from app.stages.audio_structure import extract_audio_structure
from app.stages.context import extract_structure
from app.stages.road_geometry import extract_road_geometry
from app.stages.visual_profile import extract_visual_profile



STAGES = (
    "prepare",
    "metadata",
    "scenes",
    "speech",
    "audio_structure",
    "ocr",
    "structure",
    "scene_objects",
    "visual_profile",
    "road_geometry",
    "location_evidence",
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
        "metadata": lambda: extract_metadata(
            folder,
            run_folder,
        ),


        "scenes": lambda: extract_scenes(
            folder,
            run_folder,
            video,
            prepared["duration"],
            progress,
        ),


        "speech": lambda: extract_speech(
            folder,
            run_folder,
            video,
            prepared,
            options,
            progress,
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


        "scene_objects": lambda: extract_scene_objects(
            folder,
            run_folder,
            video,
            prepared["duration"],
            stages,
            options,
            progress,
        ),


        "visual_profile": lambda: extract_visual_profile(
            folder,
            run_folder,
            video,
            prepared["duration"],
            stages,
            options,
            progress,
        ),


        "location_evidence": lambda: extract_location_evidence(
            folder,
            run_folder,
            stages,
            progress,
        ),


        "road_geometry": lambda: extract_road_geometry(
            folder,
            run_folder,
            stages,
            progress,
            video,
            prepared["duration"],
            options,
        ),


        "audio_structure": lambda: extract_audio_structure(
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