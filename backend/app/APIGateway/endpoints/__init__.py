"""Роутеры FastAPI."""


from app.APIGateway.endpoints.ai import router as ai_router
from app.APIGateway.endpoints.artifacts import router as artifact_router
from app.APIGateway.endpoints.health import router as health_router
from app.APIGateway.endpoints.jobs import router as job_router
from app.APIGateway.endpoints.observations import router as observation_router
from app.APIGateway.endpoints.reports import router as report_router


__all__ = [
    "ai_router",
    "artifact_router",
    "health_router",
    "job_router",
    "observation_router",
    "report_router",
]