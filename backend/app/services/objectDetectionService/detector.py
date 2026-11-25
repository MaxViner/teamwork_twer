"""YOLOv8n на ONNX Runtime.

Модель обучена на COCO и отдаёт 80 классов. Инференс идёт через
onnxruntime.InferenceSession(providers=["CPUExecutionProvider"]):
OpenCV 5.0 несовместим с этим ONNX-графом, поэтому cv2.dnn не
используется даже для NMS (NMS остаётся из cv2 — это отдельная
функция, не чтение модели).

Вход модели — тензор [1, 3, 640, 640] в RGB и диапазоне 0..1.
Выход — [1, 84, 8400]: 4 координаты рамки (cx, cy, w, h) и 80
оценок классов. Рамки возвращаются в пикселях исходного кадра,
а не в нормализованных долях.

Экспортированный yolov8n.onnx имеет фиксированный batch=1, поэтому
detect_batch обрабатывает кадры небольшими группами по одному
вызову сессии. Это сохраняет контракт и не ломается на модели
с фиксированной размерностью.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.config import MODELS_DIR


try:
    import onnxruntime as ort
except ImportError:  # pragma: no cover - зависит от окружения
    ort = None


INPUT_SIZE = 640

# Классы COCO в том порядке, в котором их отдаёт YOLOv8.
COCO_CLASSES = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus",
    "train", "truck", "boat", "traffic light", "fire hydrant",
    "stop sign", "parking meter", "bench", "bird", "cat", "dog",
    "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe",
    "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat",
    "baseball glove", "skateboard", "surfboard", "tennis racket",
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl",
    "banana", "apple", "sandwich", "orange", "broccoli", "carrot",
    "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop",
    "mouse", "remote", "keyboard", "cell phone", "microwave", "oven",
    "toaster", "sink", "refrigerator", "book", "clock", "vase",
    "scissors", "teddy bear", "hair drier", "toothbrush",
)

# Классы, которые движутся сами и мешают визуальной одометрии.
DYNAMIC_CLASSES: set[str] = {
    "person",
    "bicycle",
    "car",
    "motorcycle",
    "bus",
    "truck",
    "boat",
}


class YoloDetector:
    """Детектор YOLOv8n поверх ONNX Runtime.

    Один экземпляр держит открытую сессию: создание сессии читает
    файл модели (~12 МБ), поэтому детектор имеет смысл переиспользовать.
    """

    def __init__(
        self,
        model_path: Path | None = None,
        conf_thres: float = 0.25,
        iou_thres: float = 0.45,
    ) -> None:
        """Открыть ONNX-модель и запомнить пороги детекции.

        Если путь не передан, берётся app/models/yolov8n.onnx.
        """

        if ort is None:
            raise RuntimeError(
                "onnxruntime не установлен. "
                "Установите его: pip install onnxruntime"
            )

        path = Path(model_path) if model_path else (
            MODELS_DIR / "yolov8n.onnx"
        )

        if not path.is_file():
            raise FileNotFoundError(
                f"Модель YOLO не найдена: {path}"
            )

        self.conf_thres = float(conf_thres)
        self.iou_thres = float(iou_thres)

        self.session = ort.InferenceSession(
            str(path),
            providers=["CPUExecutionProvider"],
        )

        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name

    def detect(self, image_path: Path) -> list[dict]:
        """Найти объекты на одном изображении.

        Возвращает список словарей с полями label, cls_id, confidence,
        bbox (пиксели исходного кадра) и is_dynamic.
        """

        image = _read_image(image_path)
        return self._detect_array(image)

    def detect_batch(
        self,
        image_paths: list[Path],
        chunk_size: int = 4,
    ) -> list[list[dict]]:
        """Найти объекты на нескольких изображениях.

        Модель имеет фиксированный batch=1, поэтому кадры идут
        группами, но сессия вызывается по одному изображению.
        """

        paths = list(image_paths)
        step = max(1, int(chunk_size))
        results: list[list[dict]] = []

        for start in range(0, len(paths), step):
            for path in paths[start:start + step]:
                results.append(self.detect(path))

        return results

    def dynamic_mask(
        self,
        image_shape: tuple[int, int],
        detections: list[dict],
    ) -> np.ndarray:
        """Маска для ORB: 255 — рабочие пиксели, 0 — динамика.

        Рамки динамических объектов (люди, машины, лодки) вырезаются,
        чтобы одометрия не цеплялась за движущиеся предметы.
        """

        height = int(image_shape[0])
        width = int(image_shape[1])
        mask = np.full((height, width), 255, dtype=np.uint8)

        for detection in detections:
            if not detection.get("is_dynamic"):
                continue

            try:
                x1, y1, x2, y2 = (
                    int(round(float(value)))
                    for value in detection["bbox"]
                )
            except (KeyError, TypeError, ValueError):
                continue

            x1 = max(0, min(width, x1))
            y1 = max(0, min(height, y1))
            x2 = max(0, min(width, x2))
            y2 = max(0, min(height, y2))

            if x2 > x1 and y2 > y1:
                mask[y1:y2, x1:x2] = 0

        return mask

    def _detect_array(self, image: np.ndarray) -> list[dict]:
        """Инференс по массиву BGR и разбор выхода YOLOv8."""

        height, width = image.shape[:2]

        canvas, scale, pad_x, pad_y = _letterbox(
            image,
            INPUT_SIZE,
        )

        blob = (
            canvas[:, :, ::-1]
            .transpose(2, 0, 1)[None]
            .astype(np.float32)
            / 255.0
        )

        outputs = self.session.run(
            [self.output_name],
            {self.input_name: blob},
        )[0]

        predictions = np.asarray(outputs)

        if predictions.ndim == 3:
            predictions = predictions[0]

        # (84, 8400) → (8400, 84)
        if predictions.shape[0] < predictions.shape[1]:
            predictions = predictions.T

        if predictions.size == 0:
            return []

        class_scores = predictions[:, 4:]
        class_ids = class_scores.argmax(axis=1)
        scores = class_scores[
            np.arange(len(class_ids)),
            class_ids,
        ]

        keep = scores >= self.conf_thres

        if not np.any(keep):
            return []

        boxes = predictions[keep, :4]
        scores = scores[keep]
        class_ids = class_ids[keep]

        # cx, cy, w, h → x, y, w, h для NMS.
        boxes_xywh = np.empty_like(boxes)
        boxes_xywh[:, 0] = boxes[:, 0] - boxes[:, 2] / 2
        boxes_xywh[:, 1] = boxes[:, 1] - boxes[:, 3] / 2
        boxes_xywh[:, 2] = boxes[:, 2]
        boxes_xywh[:, 3] = boxes[:, 3]

        raw_indices = cv2.dnn.NMSBoxes(
            boxes_xywh.tolist(),
            scores.tolist(),
            self.conf_thres,
            self.iou_thres,
        )

        indices = np.asarray(raw_indices).reshape(-1)

        detections: list[dict] = []

        for index in indices:
            x, y, w, h = boxes_xywh[int(index)]

            x1 = (x - pad_x) / scale
            y1 = (y - pad_y) / scale
            x2 = (x + w - pad_x) / scale
            y2 = (y + h - pad_y) / scale

            x1 = max(0, min(width, int(round(x1))))
            y1 = max(0, min(height, int(round(y1))))
            x2 = max(0, min(width, int(round(x2))))
            y2 = max(0, min(height, int(round(y2))))

            if x2 - x1 < 2 or y2 - y1 < 2:
                continue

            cls_id = int(class_ids[int(index)])
            label = (
                COCO_CLASSES[cls_id]
                if 0 <= cls_id < len(COCO_CLASSES)
                else str(cls_id)
            )

            detections.append({
                "label": label,
                "cls_id": cls_id,
                "confidence": round(float(scores[int(index)]), 4),
                "bbox": [x1, y1, x2, y2],
                "is_dynamic": label in DYNAMIC_CLASSES,
            })

        detections.sort(key=lambda item: -item["confidence"])
        return detections


def _read_image(image_path: Path) -> np.ndarray:
    """Прочитать изображение с поддержкой кириллицы в пути."""

    data = np.fromfile(str(image_path), dtype=np.uint8)

    if not data.size:
        raise ValueError(f"Пустой файл изображения: {image_path}")

    image = cv2.imdecode(data, cv2.IMREAD_COLOR)

    if image is None:
        raise ValueError(
            f"Не удалось прочитать изображение: {image_path}"
        )

    return image


def _letterbox(
    image: np.ndarray,
    size: int,
) -> tuple[np.ndarray, float, int, int]:
    """Вписать кадр в квадрат size×size без искажения пропорций.

    Возвращает холст, масштаб и отступы слева и сверху: по ним
    координаты из выхода модели переводятся обратно в пиксели кадра.
    """

    height, width = image.shape[:2]

    scale = min(size / width, size / height)
    new_width = max(1, int(round(width * scale)))
    new_height = max(1, int(round(height * scale)))

    resized = cv2.resize(
        image,
        (new_width, new_height),
        interpolation=cv2.INTER_LINEAR,
    )

    canvas = np.full(
        (size, size, 3),
        114,
        dtype=np.uint8,
    )

    pad_x = (size - new_width) // 2
    pad_y = (size - new_height) // 2

    canvas[
        pad_y:pad_y + new_height,
        pad_x:pad_x + new_width,
    ] = resized

    return canvas, scale, pad_x, pad_y
