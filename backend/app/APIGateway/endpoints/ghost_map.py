"""Эндпоинты карты «привидений».

Префикс ``/api/ghost-map``. Генерация запускается только локальным
пользователем (или при явном ``GHOST_MAP_ALLOW_REMOTE=1``), чтение
артефактов свободное. Основной пайплайн видео эти эндпоинты не
затрагивают.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.services.ghostMapService import (
    GenerationBusy,
    GhostMapError,
    UYEZDS,
    add_marks,
    delete_mark,
    read_ghosts,
    read_marks,
    read_meta,
    read_places,
    roads,
    start_generation,
    status,
)


router = APIRouter(
    prefix="/api/ghost-map",
    tags=["ghost-map"],
)


class GenerateRequest(BaseModel):
    """Параметры фоновой генерации."""

    uyezd: str | None = None
    use_nominatim: bool = False


class MarkInput(BaseModel):
    """Ручная отметка «призрака» с карты."""

    name: str = Field(min_length=1, max_length=200)
    lat: float
    lon: float
    note: str | None = Field(default=None, max_length=1000)


def _require_local(request: Request) -> None:
    """Разрешить генерацию только локальному пользователю."""

    if os.getenv("GHOST_MAP_ALLOW_REMOTE") == "1":
        return

    host = request.client.host if request.client else ""

    if host in ("127.0.0.1", "::1", "localhost", "testclient"):
        return

    raise HTTPException(
        403,
        "Генерация доступна только локальному пользователю. "
        "Для удалённого доступа задайте GHOST_MAP_ALLOW_REMOTE=1.",
    )


@router.get("/places")
def get_places() -> dict:
    """Все совпавшие НП 1859 г. (GeoJSON) и счётчики из meta.json."""

    try:
        payload = read_places()

    except FileNotFoundError as error:
        raise HTTPException(404, str(error)) from None

    payload["meta"] = read_meta()

    return payload


@router.get("/ghosts")
def get_ghosts() -> dict:
    """Только «привидения» (GeoJSON)."""

    try:
        payload = read_ghosts()

    except FileNotFoundError as error:
        raise HTTPException(404, str(error)) from None

    payload["meta"] = read_meta()

    return payload


@router.get("/status")
def get_status() -> dict:
    """Состояние генерации, прогресс и метаданные."""

    return status()


@router.post("/generate")
def generate(
    payload: GenerateRequest,
    request: Request,
) -> dict:
    """Запустить генерацию в фоне."""

    _require_local(request)

    if payload.uyezd:
        requested = payload.uyezd.strip().lower()
        matches = [
            name
            for name in UYEZDS
            if requested in name
        ]

        if not matches:
            raise HTTPException(
                400,
                f"Неизвестный уезд: {payload.uyezd}. "
                f"Доступны: {', '.join(UYEZDS)}.",
            )

        uyezd = matches[0]

    else:
        uyezd = None

    try:
        return start_generation({
            "uyezd": uyezd,
            "use_nominatim": payload.use_nominatim,
        })

    except GenerationBusy as error:
        raise HTTPException(409, str(error)) from None


@router.get("/roads")
def get_roads(
    bbox: str = Query(
        ...,
        description="west,south,east,north",
    ),
) -> dict:
    """Прокси Overpass: дороги и деревни по видимому экрану."""

    try:
        return roads(bbox)

    except ValueError as error:
        raise HTTPException(400, str(error)) from None

    except GhostMapError as error:
        raise HTTPException(502, str(error)) from None


@router.get("/marks")
def get_marks() -> dict:
    """Список ручных отметок."""

    marks = read_marks()

    return {"marks": marks, "count": len(marks)}


@router.post("/marks")
def create_marks(
    payload: MarkInput | list[MarkInput],
) -> dict:
    """Добавить одну или несколько ручных отметок."""

    items = payload if isinstance(payload, list) else [payload]

    try:
        marks = add_marks([
            item.model_dump()
            for item in items
        ])

    except ValueError as error:
        raise HTTPException(400, str(error)) from None

    return {"marks": marks, "count": len(marks)}


@router.delete("/marks/{mark_id}")
def remove_mark(mark_id: str) -> dict:
    """Удалить ручную отметку по id."""

    marks = delete_mark(mark_id)

    return {"marks": marks, "count": len(marks)}
