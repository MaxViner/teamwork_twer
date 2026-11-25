"""Порядок этапов анализа.

Здесь перечислены все этапы и описано, какой анализатор вызывать
для каждого из них. executor передаёт сюда задание, а pipeline
запускает нужную функцию с подготовленными аргументами.

Визуальные этапы консолидированы: visual_analysis объединяет
метрики, семантику, YOLO и лица, place_profile — дорогу, геометрию,
ориентиры, одометрию и BEV. location_prompt завершает цепочку.

Все файловые операции этапов идут через StorageService — единую
точку, которая знает раскладку папок задания. Этапы, которым файлы
не нужны (например, scenes — он работает с video как с Path),
получают только Path-аргументы.
"""

from pathlib import Path
from typing import Callable

from app.services.aiService.stage import extract_location_prompt
from app.services.audioService.audio_structure import extract_audio_structure
from app.services.audioService.speech import extract_speech
from app.services.geoInspectService.location import extract_location_evidence
from app.services.mediaService.metadata import extract_metadata
from app.services.placeProfileService.stage import extract_place_profile
from app.services.preprocessingService.prepare import prepare
from app.services.summarizationService.context import extract_structure
from app.services.summarizationService.summary import extract_summary
from app.services.summarizationService.video_structure import extract_video_structure
from app.services.visyalInspectorService.ocr import extract_ocr
from app.services.visyalInspectorService.scenes import extract_scenes
from app.services.visualAnalysisService.stage import extract_visual_analysis
from app.storage import StorageService

STAGES = (
    "prepare",
    "metadata",
    "scenes",
    "speech",
    "audio_structure",
    "ocr",
    "structure",
    "visual_analysis",
    "place_profile",
    "location_evidence",
    "summary",
    "video_structure",
    "location_prompt",
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

        "audio_structure": lambda: extract_audio_structure(
            storage,
            video,
            prepared,
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

        "structure": lambda: extract_structure(
            storage,
            stages,
            progress,
        ),

        "visual_analysis": lambda: extract_visual_analysis(
            storage,
            video,
            prepared["duration"],
            stages,
            options,
            progress,
        ),

        "place_profile": lambda: extract_place_profile(
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

        "location_prompt": lambda: extract_location_prompt(
            storage,
            stages,
            progress,
        ),
    }

    if stage not in handlers:
        raise ValueError(f"Неизвестный этап: {stage}")

    return handlers[stage]()
