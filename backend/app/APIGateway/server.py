"""Точка входа FastAPI.

Здесь только создание приложения, lifespan и подключение роутеров.
Бизнес-логика и endpoints разнесены по отдельным модулям.
"""


import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI


from app.APIGateway.executor import PAUSED_JOBS, POOL
from app.APIGateway.jobs import (
    DATA,
    load_job,
    save_job,
)
from app.APIGateway.endpoints import (
    ai_router,
    artifact_router,
    geo_research_router,
    health_router,
    job_router,
    observation_router,
    report_router,
)
from app.APIGateway.test_endpoints import (
    geo_clue_router,
    test_router,
)


logger = logging.getLogger(__name__)



@asynccontextmanager
async def lifespan(appServer):
    logger.warning("BACKEND STARTED")

    _recover_interrupted_jobs()

    yield

    logger.warning(
        "BACKEND SHUTDOWN REQUESTED: "
        "waiting for active pipeline task"
    )

    POOL.shutdown(
        wait=True,
        cancel_futures=True,
    )

    logger.warning("BACKEND SHUTDOWN COMPLETE")



def _recover_interrupted_jobs() -> None:
    """Пометить незавершённые задания после перезапуска backend."""


    for path in DATA.glob("*/job.json"):
        job = load_job(path.parent.name)

        # Пауза переживает перезапуск backend: не превращаем её
        # в «прерванный запуск» и не требуем повторного этапа.
        if (
            job.get("status") == "paused"
            or job.get("pause_requested")
        ):
            PAUSED_JOBS.add(path.parent.name)
            job["status"] = "paused"
            job["progress"] = "Пауза"

            for stage in job.get("stages", {}).values():
                if stage.get("status") == "running":
                    stage["status"] = "paused"
                    stage["progress_message"] = "Пауза"

            save_job(job)
            continue

        if job.get("status") not in (
            "queued",
            "running",
        ):
            continue

        job["status"] = "partial"
        job["progress"] = (
            "Прошлый запуск был прерван. "
            "Повторите нужный этап."
        )

        for stage in job.get("stages", {}).values():
            if stage.get("status") in (
                "pending",
                "running",
            ):
                stage["status"] = "failed"
                stage["error"] = "Запуск прерван."

        save_job(job)



appServer = FastAPI(
    title="Local Video Evidence",
    lifespan=lifespan,
)


appServer.include_router(health_router)
appServer.include_router(job_router)
appServer.include_router(artifact_router)
appServer.include_router(observation_router)
appServer.include_router(report_router)
appServer.include_router(ai_router)
appServer.include_router(geo_research_router)

# Тестовые роутеры подключены всегда, но сами отдают 404, пока
# ENABLE_TEST_ENDPOINTS не равен 1. Так контракт скрыт, а тесты
# могут проверить поведение.
appServer.include_router(test_router)
appServer.include_router(geo_clue_router)