# Ideascope backend image.
#
# Phase 0 uses a plain slim-Python base. When the validation pipeline lands
# (docs/PLAN.md §5.2), switch the base to the official Playwright Python image
# (mcr.microsoft.com/playwright/python) so headless Chromium is available —
# expect a ~1.5 GB image and size the instance at >=1 GB RAM (§13).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    "fastapi>=0.115" "uvicorn[standard]>=0.32" "pydantic>=2.9" "pydantic-settings>=2.5"

COPY app ./app

EXPOSE 8000

# Fly.io / Render inject $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
