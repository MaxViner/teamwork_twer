"""Профиль места: дорога, геометрия, одометрия и BEV.

Пакет объединяет бывшие road_geometry и landmarks и добавляет
визуальную одометрию с топологической BEV-проекцией.
"""

from app.services.placeProfileService.stage import extract_place_profile


__all__ = ["extract_place_profile"]
