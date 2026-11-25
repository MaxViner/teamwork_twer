"""Визуальная одометрия и масштаб.

Пакет оценивает движение камеры между двумя кадрами по ORB и
essential-матрице, накапливает относительную траекторию и подбирает
грубый масштаб. Метрика здесь приблизительная: точные расстояния
появятся только после интеграции в place_profile.
"""

from app.services.odometryService.scale import estimate_scale
from app.services.odometryService.trajectory import TrajectoryAccumulator
from app.services.odometryService.visual_odometry import VisualOdometry


__all__ = [
    "TrajectoryAccumulator",
    "VisualOdometry",
    "estimate_scale",
]
