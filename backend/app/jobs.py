import json
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import UUID

from fastapi import HTTPException

from app.config import STAGE_WEIGHTS


DATA = Path(__file__).resolve().parent.parent / "data"
DATA.mkdir(exist_ok=True)

LOCK = RLock()

LAST_PROGRESS_UPDATE = 0.0
PROGRESS_UPDATE_INTERVAL = 0.5


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def job_folder(job_id: str) -> Path:
    try:
        normalized = UUID(job_id).hex
    except ValueError:
        raise HTTPException(404, "Задание не найдено.") from None

    return DATA / normalized


def load_job(job_id: str) -> dict:
    with LOCK:
        path = job_folder(job_id) / "job.json"

        if not path.is_file():
            raise HTTPException(404, "Задание не найдено.")

        return json.loads(path.read_text(encoding="utf-8"))


def save_job(job: dict) -> None:
    with LOCK:
        folder = job_folder(job["id"])
        folder.mkdir(exist_ok=True)

        temporary = folder / "job.json.tmp"
        temporary.write_text(
            json.dumps(job, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(folder / "job.json")


def mutate_job(job_id: str, callback) -> dict:
    with LOCK:
        job = load_job(job_id)
        callback(job)
        job["updated_at"] = now()
        save_job(job)
        return job


def set_progress(job_id: str, message: str) -> None:
    mutate_job(job_id, lambda job: job.update(progress=message))


def set_stage_progress(
    job_id: str,
    stage: str,
    stage_percent: float,
    message: str | None = None,
) -> None:
    global LAST_PROGRESS_UPDATE

    current_time = time.monotonic()

    if current_time - LAST_PROGRESS_UPDATE < PROGRESS_UPDATE_INTERVAL:
        return

    LAST_PROGRESS_UPDATE = current_time

    stage_percent = max(0.0, min(100.0, float(stage_percent)))

    def update(job):
        job.setdefault("stage_progress", {})

        for name in STAGE_WEIGHTS:
            job["stage_progress"].setdefault(name, 0.0)

        job["stage_progress"][stage] = stage_percent

        total = sum(
            STAGE_WEIGHTS[name] * percent / 100
            for name, percent in job["stage_progress"].items()
        )

        job["progress_percent"] = round(total, 1)

        if message:
            job["progress"] = message
        else:
            job["progress"] = f"{stage}: {stage_percent:.0f}%"

    mutate_job(job_id, update)


def stage_enabled(stage: str, options: dict) -> bool:
    if stage == "metadata":
        # В текущей задаче GPS и метаданные не анализируем.
        return False

    defaults = {
        "speech": True,
        "ocr": True,
        "visual": False,
        "audio_events": False,
        "structure": True,
    }

    if stage in defaults:
        return bool(
            options.get(stage, defaults[stage])
        )

    return True

 