"""FastAPI application entrypoint.

Phase 0: wires up CORS and the health router only. The generation pipeline,
SSE streaming, and lesson endpoints (docs/PLAN.md §5) arrive in Phase 3+.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import health
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Ideascope", version=__version__)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    return app


app = create_app()
