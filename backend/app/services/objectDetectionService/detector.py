# backend/app/services/objectDetectionService/detector.py
import cv2
import numpy as np
from pathlib import Path

MODEL_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "models"
    / "yolov8n.onnx"
)
INPUT_SIZE = (640, 640)
print(MODEL_PATH)
# Классы COCO, которые можно считать динамическими (для будущей фильтрации)
DYNAMIC_CLASSES = {"person", "bicycle", "car", "motorcycle", "bus", "truck"}

class YoloDetector:
    def __init__(self):
        self.net = cv2.dnn.readNetFromONNX(str(MODEL_PATH))
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        self.class_names = self._load_coco_names()

    def _load_coco_names(self) -> list[str]:
        # Стандартные 80 классов COCO
        return [
            "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
            "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
            "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
            "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball",
            "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
            "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
            "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
            "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
            "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
            "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier",
            "toothbrush"
        ]

    def detect(self, image_path: Path, conf_thres: float = 0.25, iou_thres: float = 0.45) -> list[dict]:
        image = cv2.imread(str(image_path))
        if image is None:
            return []

        h, w = image.shape[:2]
        # Предобработка: создание квадратного изображения с сохранением пропорций
        length = max((h, w))
        padded = np.zeros((length, length, 3), np.uint8)
        padded[0:h, 0:w] = image
        scale = length / INPUT_SIZE[0]

        blob = cv2.dnn.blobFromImage(padded, 1/255.0, INPUT_SIZE, swapRB=True)
        self.net.setInput(blob)
        outputs = self.net.forward()  # форма (1, 84, 8400) для YOLOv8

        # Постобработка
        outputs = np.array([cv2.transpose(outputs[0])])
        rows = outputs.shape[1]
        boxes, scores, class_ids = [], [], []

        for i in range(rows):
            classes_scores = outputs[0][i][4:]
            _, max_score, _, (_, max_class_id) = cv2.minMaxLoc(classes_scores)
            if max_score >= conf_thres:
                # Координаты в формате [x_center, y_center, width, height]
                cx, cy, bw, bh = outputs[0][i][0:4]
                x1 = (cx - 0.5 * bw) * scale
                y1 = (cy - 0.5 * bh) * scale
                box_w = bw * scale
                box_h = bh * scale
                boxes.append([int(x1), int(y1), int(box_w), int(box_h)])
                scores.append(float(max_score))
                class_ids.append(int(max_class_id))

        indices = cv2.dnn.NMSBoxes(boxes, scores, conf_thres, iou_thres)

        results = []
        if len(indices) > 0:
            for i in indices.flatten():
                x, y, bw, bh = boxes[i]
                label = self.class_names[class_ids[i]] if class_ids[i] < len(self.class_names) else f"class_{class_ids[i]}"
                results.append({
                    "label": label,
                    "confidence": round(scores[i], 3),
                    "bbox": [x, y, x + bw, y + bh],  # [x1, y1, x2, y2]
                    "is_dynamic": label in DYNAMIC_CLASSES,
                })
        return results