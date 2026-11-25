"""Обёртка стадии location_prompt.

Тонкий слой между pipeline и location_prompt.build_location_prompt:
проверяет, что улики собраны, и передаёт управление сборщику
промпта. Логика SYSTEM/PROMPT остаётся в location_prompt.py.
"""

from __future__ import annotations

from app.services.aiService.location_prompt import build_location_prompt
from app.storage import StorageService


def extract_location_prompt(
    storage: StorageService,
    stages: dict,
    progress,
) -> dict:
    """Сформировать поисковый промпт по накопленным уликам."""

    return build_location_prompt(
        storage,
        stages,
        progress,
    )
