"""Гео-улики: Grounding DINO tiny + SAM2.1 hiera tiny.

Публичные функции модуля:
- analyze_frame / analyze_frames — JSON с geo_clues и frame_summary;
- unique_geo_clues — сводка по кадрам;
- status / reset — состояние и сброс моделей.
"""

from app.services.geoCluesService.service import (
    analyze_frame,
    analyze_frames,
    detector_available,
    detector_error,
    format_time,
    reset,
    status,
    unique_geo_clues,
)

__all__ = [
    "analyze_frame",
    "analyze_frames",
    "detector_available",
    "detector_error",
    "format_time",
    "reset",
    "status",
    "unique_geo_clues",
]
