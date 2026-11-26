"""Очередь выполнения заданий.

Все этапы выполняются в одном фоновом потоке. Для каждого этапа
executor запускает анализатор, сохраняет результат и наблюдения,
ведёт историю прошлых попыток и выставляет итоговый статус задания.
"""

from concurrent.futures import ThreadPoolExecutor
from threading import RLock
from uuid import uuid4
import psutil
from fastapi import HTTPException

from app.utils.errors import PauseRequested, SkipStage
from app.APIGateway.jobs import (
    DATA,
    LAST_PROGRESS_UPDATE,
    LOCK,
    job_folder,
    load_job,
    mutate_job,
    save_job,
    set_progress,
    set_stage_progress,
    stage_enabled,
)
from app.APIGateway.pipeline import STAGES, run_stage


POOL = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="video-analysis",
)

# Задания, для которых пользователь запросил паузу. Множество
# проверяется в progress-callback, чтобы длинный этап остановился
# на ближайшем обновлении прогресса.
PAUSED_JOBS: set[str] = set()


def is_paused(job_id: str) -> bool:
    return job_id in PAUSED_JOBS

def log_memory(stage: str):
    process = psutil.Process()
    print(
        f"[MEMORY] {stage}: "
        f"rss={process.memory_info().rss / 1024 / 1024:.1f} MB, "
        f"threads={process.num_threads()}"
    )
    
def execute(job_id: str, selected: list[str]) -> None:
    try:
        if is_paused(job_id):
            _mark_paused(job_id)
            return

        mutate_job(job_id, lambda job: job.update(status="running"))

        for stage in selected:
            if is_paused(job_id):
                _mark_paused(job_id)
                return

            _run_selected_stage(job_id, stage)

            if is_paused(job_id):
                _mark_paused(job_id)
                return

        _finish_job(job_id)

    except PauseRequested:
        _mark_paused(job_id)

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
            progress=lambda percent, message: _report_progress(
                job_id,
                stage,
                percent,
                message,
            ),
        )

        observations = result.pop("observations", [])
        _complete_stage(job_id, stage, result, observations, run_id)

    except PauseRequested:
        _mark_stage(job_id, stage, {
            "status": "paused",
            "note": "Пауза по запросу пользователя.",
            "error": None,
            "progress_message": "Пауза",
        })
        raise

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


def _ensure_stage(job: dict, stage: str) -> dict:
    """Создать состояние этапа в старом job.json при повторе."""
    return job["stages"].setdefault(stage, {
        "status": "pending",
        "run_id": None,
        "result_run_id": None,
        "result": {},
        "observations": [],
        "history": [],
        "error": None,
        "note": None,
    })


def _mark_stage(job_id: str, stage: str, patch: dict) -> None:
    def update(job):
        _ensure_stage(job, stage).update(patch)

    mutate_job(job_id, update)


def _begin_stage(job_id: str, stage: str, run_id: str) -> None:
    def begin(job):
        state = _ensure_stage(job, stage)

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
            progress=0.0,
            progress_message=None,
        )

        job.setdefault("stage_progress", {})[stage] = 0.0
        LAST_PROGRESS_UPDATE.pop((job_id, stage), None)

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
        _ensure_stage(job, stage).update(
            status="completed",
            result_run_id=run_id,
            result=result,
            observations=observations,
            note=result.get("note"),
            error=None,
            progress=100.0,
            progress_message=None,
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
            
        job["progress_percent"] = 100.0
        job.update(
            status=status,
            progress="Обработка завершена",
        )
   
    
    mutate_job(job_id, finish)


def _report_progress(
    job_id: str,
    stage: str,
    percent: float,
    message: str | None,
) -> None:
    """Обновить прогресс или прервать этап по запросу паузы."""

    if is_paused(job_id):
        raise PauseRequested()

    set_stage_progress(
        job_id,
        stage,
        percent,
        message,
    )


def _mark_paused(job_id: str) -> None:
    """Зафиксировать паузу в job.json."""

    def update(job):
        job["status"] = "paused"
        job["progress"] = "Пауза"
        job["pause_requested"] = True

        for state in (job.get("stages") or {}).values():
            if state.get("status") == "running":
                state["status"] = "paused"
                state["progress_message"] = "Пауза"

    mutate_job(job_id, update)


def request_pause(job_id: str) -> dict:
    """Поставить задание на паузу.

    Для queued/created пауза применяется сразу. Для running —
    выставляется флаг, и этап останавливается на ближайшем
    обновлении прогресса.
    """

    with LOCK:
        job = load_job(job_id)
        status = job.get("status")

        if status in ("completed", "partial", "failed"):
            raise HTTPException(
                409,
                "Задание уже завершено.",
            )

        PAUSED_JOBS.add(job_id)

        def update(current):
            current["pause_requested"] = True

            if current.get("status") in ("queued", "created"):
                current["status"] = "paused"
                current["progress"] = "Пауза"

                for state in (current.get("stages") or {}).values():
                    if state.get("status") == "pending":
                        state["note"] = "Пауза"

            else:
                current["progress"] = (
                    "Пауза запрошена: завершаю текущий шаг"
                )

        mutate_job(job_id, update)

        return load_job(job_id)


def request_resume(job_id: str) -> dict:
    """Продолжить задание с первого незавершённого этапа."""

    with LOCK:
        job = load_job(job_id)

        if job.get("status") != "paused":
            raise HTTPException(
                409,
                "Задание не стоит на паузе.",
            )

        PAUSED_JOBS.discard(job_id)

        mutate_job(
            job_id,
            lambda current: current.update(
                pause_requested=False,
                progress="Возобновление",
            ),
        )

        remaining = _remaining_stages(job)

        if not remaining:
            _finish_job(job_id)
            return load_job(job_id)

        schedule(job_id, remaining)

        return load_job(job_id)


def _remaining_stages(job: dict) -> list[str]:
    """Этапы, начиная с первого незавершённого."""

    states = job.get("stages") or {}

    for index, stage in enumerate(STAGES):
        state = states.get(stage) or {}

        if state.get("status") not in ("completed", "skipped"):
            return list(STAGES[index:])

    return []


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
            _ensure_stage(job, stage).update(
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
