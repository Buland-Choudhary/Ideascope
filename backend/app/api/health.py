"""Health and version endpoints.

The only routes that exist at Phase 0 — enough to prove the service boots and
is reachable from the frontend and the deploy platform's health check.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="ideascope-backend", version=__version__)
