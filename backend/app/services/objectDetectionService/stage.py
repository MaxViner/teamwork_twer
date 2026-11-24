# backend/app/services/objectDetectionService/stage.py
from app.storage import StorageService
from app.utils.observations import observation
from .detector import YoloDetector

def extract_objects(storage: StorageService, stages: dict, progress) -> dict:
    # Собираем все кадры из уже завершённых визуальных этапов
    frames = []
    for stage_name in ("visual_profile", "ocr", "scene_objects"):
        result = (stages.get(stage_name) or {}).get("result") or {}
        frames.extend(result.get("frames") or [])
    # Убираем дубликаты по artifact
    seen = set()
    unique_frames = []
    for f in frames:
        art = f.get("artifact")
        if art and art not in seen:
            seen.add(art)
            unique_frames.append(f)

    if not unique_frames:
        raise SkipStage("Нет кадров для детекции объектов.")

    detector = YoloDetector()
    all_detections = []
    for i, frame in enumerate(unique_frames):
        progress(i / len(unique_frames) * 100, f"Детекция объектов: {i+1}/{len(unique_frames)}")
        path = storage.resolve(frame["artifact"])
        if not path.is_file():
            continue
        dets = detector.detect(path)
        all_detections.append({
            "timestamp": frame["timestamp"],
            "artifact": frame["artifact"],
            "detections": dets,
        })

    storage.save_json("object_detections.json", all_detections)

    return {
        "frames": all_detections,
        "total_frames": len(all_detections),
        "observations": [observation(
            source="object_detection",
            text=f"Детекция объектов выполнена на {len(all_detections)} кадрах.",
            extractor="YOLOv8n ONNX",
        )],
    }