from concurrent.futures import ThreadPoolExecutor
from threading import RLock
from uuid import uuid4

from fastapi import HTTPException

from app.errors import SkipStage
from app.jobs import (
    DATA,
    LOCK,
    job_folder,
    load_job,
    mutate_job,
    save_job,
    set_progress,
    set_stage_progress,
    stage_enabled,
)
from app.pipeline import STAGES, run_stage


POOL = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="video-analysis",
)


def execute(job_id: str, selected: list[str]) -> None:
    try:
        mutate_job(job_id, lambda job: job.update(status="running"))

        for stage in selected:
            _run_selected_stage(job_id, stage)

        _finish_job(job_id)

    except Exception as error:
        try:
            mutate_job(
                job_id,
                lambda job: job.update(
                    status="failed",
                    progress=f"Ошибка задания: {str(error)[:1000]}",
                ),
            )
        except Exception:
            pass


def _run_selected_stage(job_id: str, stage: str) -> None:
    snapshot = load_job(job_id)

    if not stage_enabled(stage, snapshot["options"]):
        _mark_stage(job_id, stage, {
            "status": "skipped",
            "error": None,
            "note": "Отключено в настройках задания.",
        })
        return

    if (
        stage != "prepare"
        and snapshot["stages"]["prepare"]["status"] != "completed"
    ):
        _mark_stage(job_id, stage, {
            "status": "skipped",
            "note": "Не завершена подготовка видео.",
        })
        return

    run_id = uuid4().hex
    _begin_stage(job_id, stage, run_id)

    try:
        snapshot = load_job(job_id)

        result = run_stage(
            stage=stage,
            folder=job_folder(job_id),
            run_id=run_id,
            options=snapshot["options"],
            stages=snapshot["stages"],
            progress=lambda percent, message: set_stage_progress(
                job_id,
                stage,
                percent,
                message,
)        )

        observations = result.pop("observations", [])
        _complete_stage(job_id, stage, result, observations, run_id)

    except SkipStage as error:
        _mark_stage(job_id, stage, {
            "status": "skipped",
            "note": str(error),
            "error": None,
        })

    except Exception as error:
        _mark_stage(job_id, stage, {
            "status": "failed",
            "error": str(error)[:4000],
        })


def _mark_stage(job_id: str, stage: str, patch: dict) -> None:
    def update(job):
        job["stages"][stage].update(patch)

    mutate_job(job_id, update)


def _begin_stage(job_id: str, stage: str, run_id: str) -> None:
    def begin(job):
        state = job["stages"][stage]

        if state["run_id"] is not None:
            state["history"].append({
                "run_id": state["run_id"],
                "result_run_id": state["result_run_id"],
                "result": state["result"],
                "observations": state["observations"],
            })

        state.update(
            status="running",
            run_id=run_id,
            error=None,
            note=None,
        )
        job["progress"] = f"Этап: {stage}"

    mutate_job(job_id, begin)


def _complete_stage(
    job_id: str,
    stage: str,
    result: dict,
    observations: list,
    run_id: str,
) -> None:
    def complete(job):
        job["stages"][stage].update(
            status="completed",
            result_run_id=run_id,
            result=result,
            observations=observations,
            note=result.get("note"),
            error=None,
        )

        job.setdefault("stage_progress", {})
        job["stage_progress"][stage] = 100.0

    mutate_job(job_id, complete)

def _finish_job(job_id: str) -> None:
    def finish(job):
        states = job["stages"]

        if states["prepare"]["status"] != "completed":
            status = "failed"
        elif any(
            item["status"] == "failed" for item in states.values()
        ):
            status = "partial"
        else:
            status = "completed"

        job.update(
            status=status,
            progress="Обработка завершена",
        )

    mutate_job(job_id, finish)


def schedule(job_id: str, selected: list[str]) -> None:
    with LOCK:
        job = load_job(job_id)

        if job["status"] in ("queued", "running"):
            raise HTTPException(409, "Задание уже выполняется.")

        job.update(
            status="queued",
            progress="В очереди",
        )

        for stage in selected:
            job["stages"][stage].update(
                status="pending",
                error=None,
                note=None,
            )

        save_job(job)

        try:
            POOL.submit(execute, job_id, selected)
        except Exception:
            job["status"] = "failed"
            job["progress"] = "Не удалось запустить обработку"
            save_job(job)
            raise
