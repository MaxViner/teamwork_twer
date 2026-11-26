"""Роутеры FastAPI."""


from app.APIGateway.endpoints.ai import router as ai_router
from app.APIGateway.endpoints.artifacts import router as artifact_router
from app.APIGateway.endpoints.geo_research import router as geo_research_router
from app.APIGateway.endpoints.health import router as health_router
from app.APIGateway.endpoints.jobs import router as job_router
from app.APIGateway.endpoints.observations import router as observation_router
from app.APIGateway.endpoints.reports import router as report_router
from app.APIGateway.endpoints.dev.odometry_lab import (
    router as odometry_lab_router,
)
from app.APIGateway.endpoints.dev.services import (
    router as dev_services_router,
)
from app.APIGateway.endpoints.dev.video_lab import router as video_lab_router

__all__ = [
    "ai_router",
    "artifact_router",
    "geo_research_router",
    "health_router",
    "job_router",
    "observation_router",
    "report_router",
    "dev_services_router",
    "odometry_lab_router",
    "video_lab_router",
]