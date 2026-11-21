"""Хранение заданий.

Каждое задание лежит в backend/data/<id>/job.json. Здесь собраны
чтение и атомарная запись JSON, общая блокировка, обновление
прогресса и проверка, включён ли этап в настройках задания.
"""

import json
import os
import time


from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import UUID


from fastapi import HTTPException


from app.config import STAGE_WEIGHTS
from app.errors import JobError



DATA = Path(__file__).resolve().parent.parent / "data"
DATA.mkdir(exist_ok=True)


LOCK = RLock()


PROGRESS_UPDATE_INTERVAL = 0.5


LAST_PROGRESS_UPDATE = {}



def now() -> str:
    return datetime.now(timezone.utc).isoformat()



def job_folder(job_id: str) -> Path:
    try:
        normalized = UUID(job_id).hex

    except ValueError:
        raise HTTPException(
            404,
            "Задание не найдено.",
        ) from None


    return DATA / normalized



def load_job(job_id: str) -> dict:
    with LOCK:
        path = job_folder(job_id) / "job.json"


        if not path.is_file():
            raise HTTPException(
                404,
                "Задание не найдено.",
            )


        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)



def save_job(job: dict) -> None:
    folder = job_folder(job["id"])

    folder.mkdir(parents=True, exist_ok=True)

    target = folder / "job.json"

    temporary = folder / (
        f"job.{os.getpid()}.{time.monotonic_ns()}.tmp"
    )

    payload = json.dumps(
        job,
        ensure_ascii=False,
        indent=2,
    )

    last_error = None


    for attempt in range(6):
        try:
            with temporary.open(
                "w",
                encoding="utf-8",
            ) as file:
                file.write(payload)
                file.flush()

                os.fsync(file.fileno())


            os.replace(temporary, target)

            return

        except PermissionError as error:
            last_error = error

            time.sleep(0.25 * (attempt + 1))

        except OSError as error:
            last_error = error

            time.sleep(0.25 * (attempt + 1))


    try:
        temporary.unlink(missing_ok=True)

    except OSError:
        pass


    raise JobError(
        "Не удалось сохранить состояние задания. "
        "Файл job.json может быть занят другим процессом. "
        f"Подробности: {last_error}"
    )



def mutate_job(job_id: str, callback) -> dict:
    with LOCK:
        job = load_job(job_id)

        callback(job)

        job["updated_at"] = now()

        save_job(job)

        return job



def set_progress(
    job_id: str,
    message: str,
) -> None:
    mutate_job(
        job_id,
        lambda job: job.update(
            progress=message,
        ),
    )



def set_stage_progress(
    job_id: str,
    stage: str,
    stage_percent: float,
    message: str | None = None,
) -> None:
    stage_percent = max(
        0.0,
        min(100.0, float(stage_percent)),
    )


    current_time = time.monotonic()

    progress_key = (job_id, stage)

    last_time = LAST_PROGRESS_UPDATE.get(
        progress_key,
        0.0,
    )


    is_final = stage_percent >= 100.0
    early_phase = stage_percent <= 10.0


    if (
        not is_final
        and not early_phase
        and current_time - last_time
        < PROGRESS_UPDATE_INTERVAL
    ):
        return


    LAST_PROGRESS_UPDATE[progress_key] = current_time


    def update(job):
        job.setdefault("stage_progress", {})


        for name in STAGE_WEIGHTS:
            job["stage_progress"].setdefault(
                name,
                0.0,
            )


        job["stage_progress"][stage] = stage_percent

        state = job.get("stages", {}).get(stage)

        if state is not None:
            state["progress"] = stage_percent

            if message:
                state["progress_message"] = message


        total = sum(
            STAGE_WEIGHTS[name] * percent / 100
            for name, percent
            in job["stage_progress"].items()
        )


        job["progress_percent"] = round(
            total,
            1,
        )


        if message:
            job["progress"] = message

        else:
            job["progress"] = (
                f"{stage}: {stage_percent:.0f}%"
            )


    mutate_job(job_id, update)



def stage_enabled(
    stage: str,
    options: dict,
) -> bool:
    option_map = {
        "metadata": "metadata",
        "speech": "speech",
        "ocr": "ocr",
        "scene_objects": "scene_objects",
        "visual_profile": "visual_profile",
        "location_evidence": "location_evidence",
        "road_geometry": "road_geometry",
        "audio_structure": "audio_structure",
        "structure": "structure",
        "summary": "summary",
        "video_structure": "video_structure",
        "comprehension": "comprehension",
        "landmarks": "landmarks",
        "visual": "visual",
        "audio_events": "audio_events",
    }


    if stage not in option_map:
        return True


    option_name = option_map[stage]


    default = option_name in (
        "metadata",
        "speech",
        "ocr",
        "scene_objects",
        "visual_profile",
        "location_evidence",
        "road_geometry",
        "audio_structure",
        "structure",
        "summary",
        "video_structure",
        "comprehension",
        "landmarks",
    )


    return bool(
        options.get(
            option_name,
            default,
        )
    )