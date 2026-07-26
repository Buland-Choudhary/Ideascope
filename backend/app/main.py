"""FastAPI application entrypoint.

Phase 0 wired up CORS and the health router; the generation pipeline, SSE
streaming, and lesson endpoints (docs/PLAN.md §5) arrived in Phase 3+; Phase 9
adds the IP-based rate limiter (§5.4) at the application level so it applies
wherever ``app/rate_limit.py``'s ``limiter.limit(...)`` is used.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app import __version__
from app.api import health, lessons
from app.config import get_settings
from app.rate_limit import limiter


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Ideascope", version=__version__)

    app.state.limiter = limiter
    # slowapi's handler is typed for RateLimitExceeded specifically, narrower
    # than add_exception_handler's generic Exception signature.
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_middleware(SlowAPIMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(lessons.router)
    return app


app = create_app()
