"""Health and version endpoints.

The only routes that exist at Phase 0 — enough to prove the service boots and
is reachable from the frontend and the deploy platform's health check.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.config import get_settings

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    # "mock" or "real" — lets a deploy be checked for Anthropic spend exposure
    # without making a paid call.
    generation: str


@router.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    generation = "mock" if get_settings().mock_generation else "real"
    return HealthResponse(
        status="ok", service="ideascope-backend", version=__version__, generation=generation
    )
