# Ideascope backend image.
#
# Deployment stage A (current): a lightweight image for mock-mode-only
# deployment. All real dependencies are installed via uv (including the
# `playwright` Python package itself, which app/validation/browser.py imports
# unconditionally), but the Chromium *browser binary* is not installed here —
# that's the expensive part (~1.5 GB). Mock mode never launches a browser
# (docs/PLAN.md §1's "Mock generation mode" serves fixtures directly), so this
# image runs the full app correctly as long as IDEASCOPE_MOCK_GENERATION=true.
# Real-mode generation would fail at the render-check step on this image.
#
# Deployment stage B (when ready for real generation): switch the FROM line to
# the official Playwright Python base image (mcr.microsoft.com/playwright/python,
# matching the pinned playwright version in pyproject.toml), keep everything
# else in this file the same, and size the hosting instance at >=1 GB RAM
# (docs/PLAN.md §13) since headless Chromium is the dominant memory consumer.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install dependencies first (better layer caching), then the app itself.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 8000

# Fly.io / Render inject $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
