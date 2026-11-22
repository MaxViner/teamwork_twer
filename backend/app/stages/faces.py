"""Лица и анонимные метки людей.

Находит лица на уже извлечённых ключевых кадрах и объединяет
одинаковые лица внутри одного видео в метки «Человек 1»,
«Человек 2». Личность не устанавливается: метки нужны только
чтобы отличать людей друг от друга и находить их появление.
"""

from pathlib import Path

from app.errors import SkipStage
from app.keyframes import collect_frames
from app.media.faces import (
    cluster_faces,
    detect_faces,
    model_available,
)
from app.observations import observation


MAX_FACE_FRAMES = 600


def extract_faces(
    folder: Path,
    run_folder: Path,
    stages: dict,
    progress,
) -> dict:
    if not model_available():
        raise SkipStage(
            "Детектор лиц недоступен: нет локальной модели YuNet."
        )

    frames = collect_frames(stages)

    if not frames:
        raise SkipStage(
            "Нет кадров для поиска лиц: визуальные этапы "
            "не завершены."
        )

    frames = frames[:MAX_FACE_FRAMES]
    analyzed = []
    face_total = 0

    for index, frame in enumerate(frames):
        progress(
            index / max(len(frames), 1) * 99,
            f"Поиск лиц: кадр {index + 1} из {len(frames)}",
        )

        artifact = frame.get("artifact")

        if not artifact:
            continue

        path = folder / artifact

        if not path.is_file():
            continue

        faces = detect_faces(path)

        if not faces:
            continue

        face_total += len(faces)

        analyzed.append({
            "timestamp": round(float(frame["timestamp"]), 3),
            "artifact": artifact,
            "faces": faces,
        })

    people = cluster_faces(analyzed)

    progress(100, "Поиск лиц завершён")

    text = _summary_text(people, face_total, len(frames))

    observations = []

    if analyzed:
        observations.append(
            observation(
                source="faces",
                start=analyzed[0]["timestamp"],
                end=analyzed[-1]["timestamp"],
                text=text,
                extractor="opencv-yunet-faces",
                data={
                    "kind": "faces_summary",
                    "people": people,
                    "frame_count": len(analyzed),
                    "face_count": face_total,
                    "anonymous": True,
                },
            )
        )

    return {
        "people": people,
        "frames": analyzed,
        "person_count": len(people),
        "face_count": face_total,
        "sampled_frames": len(frames),
        "frames_with_faces": len(analyzed),
        "observations": observations,
        "method": "YuNet + HOG-описание внешности",
        "note": (
            "Метки «Человек N» анонимны: это разные лица внутри "
            "видео, а не установленная личность. Совпадение лиц "
            "между кадрами приблизительное."
        ),
    }


def _summary_text(people, face_count, sampled):
    if not people:
        return (
            "Лица не обнаружены "
            f"(проверено кадров: {sampled}). "
            "Это не значит, что людей в видео нет."
        )

    parts = [
        f"Обнаружено лиц: {face_count}; "
        f"разных людей по внешности: {len(people)}."
    ]

    for item in people[:6]:
        parts.append(
            f"{item['label']}: {item['frame_count']} кадр., "
            f"с {item['first_start']:.1f} с."
        )

    return " ".join(parts)
