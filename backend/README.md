# Ideascope backend

FastAPI service for the Claude-powered lesson generation pipeline. See
[`../docs/PLAN.md`](../docs/PLAN.md) §5 for the full design. At Phase 0 this is
a health-check-only skeleton.

## Development

Uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
cd backend
uv sync                       # create .venv and install deps + dev deps
uv run uvicorn app.main:app --reload   # http://localhost:8000/api/health
```

## Checks

```bash
uv run ruff check .           # lint
uv run ruff format --check .  # format
uv run mypy app               # type-check
uv run pytest                 # tests
```

## Configuration

Environment variables (prefix `IDEASCOPE_`, or a `.env` file):

| Variable | Default | Purpose |
|---|---|---|
| `IDEASCOPE_ANTHROPIC_API_KEY` | _(unset)_ | Anthropic API key — server-side only. Unused until Phase 3. |
| `IDEASCOPE_MOCK_GENERATION` | `false` | Serve fixture lessons instead of calling Anthropic (§1). |
| `IDEASCOPE_CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed frontend origins. |
