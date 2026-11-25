"""Детекция объектов на ONNX Runtime.

Пакет добавляет YOLOv8n как отдельный сервис. Модель запускается
только через onnxruntime (CPUExecutionProvider): OpenCV 5.0 не умеет
читать этот ONNX-граф, поэтому cv2.dnn здесь не используется.
"""

from app.services.objectDetectionService.detector import (
    DYNAMIC_CLASSES,
    YoloDetector,
)


__all__ = ["DYNAMIC_CLASSES", "YoloDetector"]
