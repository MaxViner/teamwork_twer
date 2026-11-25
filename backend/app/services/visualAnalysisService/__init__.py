"""Консолидированный визуальный анализ.

Пакет объединяет метрики кадра, семантическую разметку, YOLO-детекцию
и лица в одну стадию visual_analysis. Внутренние модули самодостаточны
и не импортируют старые стадии visyalInspectorService.
"""

from app.services.visualAnalysisService.stage import extract_visual_analysis


__all__ = ["extract_visual_analysis"]
