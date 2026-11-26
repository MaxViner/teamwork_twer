"""Endpoints исследовательской гео-задачи.

Это отдельная задача, не этап обработки видео: пользователь вводит
видимые признаки, а сервис предлагает регион, порядок слоёв карт,
положение солнца, триангуляцию и чек-лист проверки.
"""

from __future__ import annotations

from fastapi import APIRouter

from pydantic import BaseModel, Field

from app.services.geoResearchService import (
    CROSS_CHECKS,
    LAYERS,
    build_research,
)


router = APIRouter(
    prefix="/api/geo",
    tags=["geo-research"],
)


class TriangulationPoint(BaseModel):
    name: str | None = None
    lat: float
    lon: float
    azimuth: float


class GeoResearchRequest(BaseModel):
    species: list[str] = Field(default_factory=list)
    landmarks: list[str] = Field(default_factory=list)
    traces: list[str] = Field(default_factory=list)
    sounds: list[str] = Field(default_factory=list)
    region: str | None = None
    district: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    date: str | None = None
    time: str | None = None
    utc_offset: float = 3
    triangulation_points: list[TriangulationPoint] = Field(
        default_factory=list,
    )


@router.get("/meta")
def geo_research_meta() -> dict:
    """Справочник слоёв и проверок для формы."""

    return {
        "layers": list(LAYERS),
        "cross_checks": list(CROSS_CHECKS),
    }


@router.post("/research")
def geo_research(payload: GeoResearchRequest) -> dict:
    """Собрать гипотезу региона и план проверки по картам."""

    return build_research(payload.model_dump())
