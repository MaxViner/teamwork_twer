"""Топологическая BEV-проекция.

Пакет строит карту сверху по относительной траектории и детекциям и
рендерит её в PNG. Метрика условная: цель v1 — показать порядок
движения и объекты рядом с маршрутом.
"""

from app.services.bevService.projection import build_bev
from app.services.bevService.render import render_bev_png


__all__ = ["build_bev", "render_bev_png"]
