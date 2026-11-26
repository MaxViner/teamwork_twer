"""Единая оболочка сервисов анализа.

Визуальный анализ, аудио и локационные привязки раньше жили в
разных пакетах с разными сигнатурами. Здесь они получают общий
фасад: каждый сервис умеет представиться (`describe`), сообщить
состояние моделей (`status`) и выполнить свой ключевой этап.

Оболочка намеренно аддитивная: она не двигает файлы и не меняет
контракты существующих функций. Это слой интерфейсов, который
используют тестовые endpoint'ы и который позже сможет вызывать
pipeline. Тяжёлые зависимости импортируются лениво, чтобы импорт
`serviceHub` не тянул модели.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

ProgressFn = Callable[[float, str], None]


def _noop_progress(percent: float, message: str = "") -> None:
    """Прогресс по умолчанию: ничего не делает."""

    return None


class StageService:
    """Базовый сервис одного ключевого этапа."""

    name = "stage"
    title = "Этап"
    stages: tuple[str, ...] = ()

    def describe(self) -> dict:
        """Паспорт сервиса для UI и диагностики."""

        return {
            "name": self.name,
            "title": self.title,
            "stages": list(self.stages),
            "status": self.status(),
        }

    def status(self) -> dict:
        """Состояние моделей и зависимостей."""

        return {"available": True}


class VisualService(StageService):
    """Визуальный анализ: метрики, гео-улики, сегменты, лица, BEV."""

    name = "visual"
    title = "Визуальный анализ"
    stages = ("visual_analysis", "place_profile")

    def status(self) -> dict:
        try:
            from app.services.geoCluesService import status

            clues = status()

        except Exception as error:
            clues = {"error": str(error)[:500]}

        return {
            "available": True,
            "geo_clue_models": clues,
        }

    # ── кадр ──────────────────────────────────────────────

    def metrics(self, path: Path) -> dict:
        """Метрики и словесные дескрипторы одного кадра."""

        from app.services.visualAnalysisService.metrics import (
            analyze_frame,
            describe_metrics,
        )

        metrics = analyze_frame(Path(path))

        return {
            "metrics": metrics,
            "descriptors": describe_metrics(metrics),
        }

    def geo_clues(self, path: Path) -> dict:
        """Гео-улики одного кадра (Grounding DINO + SAM2)."""

        from app.services.geoCluesService import analyze_frame

        return analyze_frame(Path(path))

    def segments(self, path: Path) -> dict:
        """Семантическая разметка кадра."""

        from app.services.visualAnalysisService.segmentation import (
            run_segformer,
        )

        return run_segformer(Path(path))

    def faces(self, path: Path) -> dict:
        """Лица на кадре."""

        from app.services.visualAnalysisService.faces import detect_faces

        return detect_faces(Path(path))

    # ── последовательность ────────────────────────────────

    def odometry(
        self,
        frames: list[dict],
        visual_result: dict | None = None,
        stages: dict | None = None,
        road_summary: dict | None = None,
        progress: ProgressFn | None = None,
    ) -> dict:
        """Относительная траектория камеры по кадрам."""

        from app.services.placeProfileService.odometry import (
            extract_odometry,
        )

        return extract_odometry(
            frames,
            visual_result or {},
            stages or {},
            road_summary,
            progress or _noop_progress,
        )

    def bev(
        self,
        trajectory: dict,
        detections_per_frame: list[dict] | None = None,
        road_segments: list[dict] | None = None,
        camera_height_m: float = 1.2,
    ) -> dict | None:
        """Топологическая карта «маршрут + ключевые якоря»."""

        from app.services.bevService.projection import build_bev

        return build_bev(
            trajectory,
            detections_per_frame or [],
            road_segments or [],
            camera_height_m=camera_height_m,
        )

    def render_bev(self, bev: dict, output: Path) -> Path:
        """Отрисовать BEV в PNG."""

        from app.services.bevService.render import render_bev_png

        return render_bev_png(bev, Path(output))


class AudioService(StageService):
    """Аудио: структура дорожки и речь."""

    name = "audio"
    title = "Аудиальный анализ"
    stages = ("audio_structure", "speech")

    def status(self) -> dict:
        try:
            import importlib.util

            return {
                "available": True,
                "faster_whisper": (
                    importlib.util.find_spec("faster_whisper")
                    is not None
                ),
                "librosa": (
                    importlib.util.find_spec("librosa") is not None
                ),
            }

        except Exception as error:
            return {"available": True, "error": str(error)[:500]}

    def structure(
        self,
        storage,
        video: Path,
        prepared: dict,
        progress: ProgressFn | None = None,
    ) -> dict:
        """Громкость, паузы и звуковые события."""

        from app.services.audioService.audio_structure import (
            extract_audio_structure,
        )

        return extract_audio_structure(
            storage,
            Path(video),
            prepared,
            progress or _noop_progress,
        )

    def speech(
        self,
        storage,
        video: Path,
        prepared: dict,
        options: dict | None = None,
        progress: ProgressFn | None = None,
    ) -> dict:
        """Распознавание речи."""

        from app.services.audioService.speech import extract_speech

        return extract_speech(
            storage,
            Path(video),
            prepared,
            options or {},
            progress or _noop_progress,
        )


class LocationService(StageService):
    """Локационные привязки: улики места и карт-исследование."""

    name = "location"
    title = "Локационные привязки"
    stages = ("location_evidence", "location_prompt", "geo_research")

    def evidence(
        self,
        storage,
        stages: dict,
        progress: ProgressFn | None = None,
    ) -> dict:
        """Сводка локационных улик по результатам других этапов."""

        from app.services.geoInspectService.location import (
            extract_location_evidence,
        )

        return extract_location_evidence(
            storage,
            stages,
            progress or _noop_progress,
        )

    def prompt(
        self,
        storage,
        stages: dict,
        progress: ProgressFn | None = None,
    ) -> dict:
        """Промпт для AI-поиска места."""

        from app.services.aiService.stage import extract_location_prompt

        return extract_location_prompt(
            storage,
            stages,
            progress or _noop_progress,
        )

    def research(self, payload: dict) -> dict:
        """Отдельная карт-задача: регион, слои, тени, триангуляция."""

        from app.services.geoResearchService import build_research

        return build_research(payload)


class ServiceHub:
    """Точка сборки трёх сервисов с общим интерфейсом."""

    def __init__(self) -> None:
        self.visual = VisualService()
        self.audio = AudioService()
        self.location = LocationService()

    def services(self) -> list[StageService]:
        return [self.visual, self.audio, self.location]

    def get(self, name: str) -> StageService:
        for service in self.services():
            if service.name == name:
                return service

        raise KeyError(f"Неизвестный сервис: {name}")

    def describe(self) -> dict:
        """Единое описание всех сервисов и их состояний."""

        return {
            "schema_version": 1,
            "services": [
                service.describe()
                for service in self.services()
            ],
        }


HUB = ServiceHub()


__all__ = [
    "HUB",
    "AudioService",
    "LocationService",
    "ServiceHub",
    "StageService",
    "VisualService",
]
