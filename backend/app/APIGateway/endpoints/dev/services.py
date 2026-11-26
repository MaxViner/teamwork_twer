"""Диагностика единой оболочки сервисов.

`GET /api/dev/services` показывает, какие ключевые этапы доступны,
какие модели загружены и какие стадии обслуживает каждый сервис.
Endpoint лёгкий: тяжёлые модели не загружает.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.services.serviceHub import HUB


router = APIRouter(
    prefix="/api/dev",
    tags=["dev-services"],
)


@router.get("/services")
def services_status() -> dict:
    """Паспорт визуального, аудио- и локационного сервисов."""

    return HUB.describe()
