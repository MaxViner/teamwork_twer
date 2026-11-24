"""Порядок этапов анализа.

Здесь перечислены все этапы и описано, какой анализатор вызывать
для каждого из них. executor передаёт сюда задание, а pipeline
запускает нужную функцию с подготовленными аргументами.

Все файловые операции этапов идут через StorageService — единую
точку, которая знает раскладку папок задания. Этапы, которым файлы
не нужны (например, scenes — он работает с video как с Path),
получают только Path-аргументы.
"""

from pathlib import Path
from typing import Callable

from app.services.aiService.location_prompt import build_location_prompt
from app.services.audioService.audio_structure import extract_audio_structure
from app.services.audioService.speech import extract_speech
from app.services.geoInspectService.location import extract_location_evidence
from app.services.mediaService.metadata import extract_metadata
from app.services.objectDetectionService.detector import YoloDetector
from app.services.objectDetectionService.stage import extract_objects
from app.services.preprocessingService.prepare import prepare
from app.services.summarizationService.context import extract_structure
from app.services.summarizationService.summary import extract_summary
from app.services.summarizationService.video_structure import extract_video_structure
from app.services.visyalInspectorService.faces import extract_faces
from app.services.visyalInspectorService.landmarks import extract_landmarks
from app.services.visyalInspectorService.ocr import extract_ocr
from app.services.visyalInspectorService.road_geometry import extract_road_geometry
from app.services.visyalInspectorService.scene_objects import extract_scene_objects
from app.services.visyalInspectorService.scenes import extract_scenes
from app.services.visyalInspectorService.visual_profile import extract_visual_profile
from app.storage import StorageService

STAGES = (
    "prepare",
    "metadata",
    "scenes",
    "speech",
    "audio_structure",
    "ocr",
    "structure",
    "scene_objects",
    "faces",
    "visual_profile",
    "road_geometry",
    "location_evidence",
    "summary",
    "video_structure",
    "landmarks",
    "ai_prompt",
)


def run_stage(
    stage: str,
    folder: Path,
    run_id: str,
    options: dict,
    stages: dict,
    progress: Callable[[float, str], None],
) -> dict:
    storage = StorageService(folder=folder, run_id=run_id)
    storage.ensure_dirs()

    if stage == "prepare":
        return prepare(storage, progress)

    prepared = stages["prepare"]["result"]
    video = storage.resolve(prepared["preview"])

    handlers = {
        "metadata": lambda: extract_metadata(
            storage,
        ),

        "scenes": lambda: extract_scenes(
            video,
            prepared["duration"],
            progress,
        ),
       

        "speech": lambda: extract_speech(
            storage,
            video,
            prepared,
            options,
            progress,
        ),

        "ocr": lambda: extract_ocr(
            storage,
            video,
            prepared["duration"],
            stages,
            options,
            progress,
        ),

        "scene_objects": lambda: extract_scene_objects(
            storage,
            video,
            prepared["duration"],
            stages,
            options,
            progress,
        ),
        "object_detection": lambda: 
        extract_objects(storage, 
                        stages, 
                        progress)
        ,

        "faces": lambda: extract_faces(
            storage,
            stages,
            progress,
        ),

        "visual_profile": lambda: extract_visual_profile(
            storage,
            video,
            prepared["duration"],
            stages,
            options,
            progress,
        ),

        "location_evidence": lambda: extract_location_evidence(
            storage,
            stages,
            progress,
        ),

        "road_geometry": lambda: extract_road_geometry(
            storage,
            stages,
            progress,
            video,
            prepared["duration"],
            options,
        ),

        "audio_structure": lambda: extract_audio_structure(
            storage,
            video,
            prepared,
            progress,
        ),

        "structure": lambda: extract_structure(
            storage,
            stages,
            progress,
        ),

        "summary": lambda: extract_summary(
            storage,
            stages,
            progress,
        ),

        "video_structure": lambda: extract_video_structure(
            storage,
            stages,
            progress,
        ),

        "landmarks": lambda: extract_landmarks(
            storage,
            stages,
            progress,
        ),

        "ai_prompt": lambda: build_location_prompt(
            storage,
            stages,
            progress,
        ),
    }

    if stage not in handlers:
        raise ValueError(f"Неизвестный этап: {stage}")

    return handlers[stage]()