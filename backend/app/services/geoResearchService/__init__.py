"""Исследовательская гео-задача: регион, слои карт, тени, триангуляция."""

from app.services.geoResearchService.research import (
    CROSS_CHECKS,
    LAYERS,
    build_research,
    solar_position,
    triangulate,
)

__all__ = [
    "CROSS_CHECKS",
    "LAYERS",
    "build_research",
    "solar_position",
    "triangulate",
]
