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

## Generating lessons

`POST /api/lessons` with `{"topic": "...", "duration": "short|medium|long"}`.

- **Mock mode** (`IDEASCOPE_MOCK_GENERATION=true`) returns a complete, playable
  fixture lesson — no API key, no network. Use this for frontend/UI work.
- **Real mode** runs the Claude plan stage and needs an Anthropic API key (see
  below). At this phase it returns the planned outline (beats with intent,
  narration, engine, manipulables); per-beat scene code is generated in Phase 4.

### Setting the Anthropic API key

1. Get a key from the [Anthropic Console](https://console.anthropic.com/) →
   **Settings → API keys → Create Key**. It looks like `sk-ant-...`.
2. Put it in `backend/.env` (this file is git-ignored):
   ```
   IDEASCOPE_ANTHROPIC_API_KEY=sk-ant-your-key-here
   ```
   The plain `ANTHROPIC_API_KEY` name also works. Never commit the key.
3. Run in real mode (mock off):
   ```bash
   uv run uvicorn app.main:app --reload   # IDEASCOPE_MOCK_GENERATION defaults to false
   curl -s localhost:8000/api/lessons -X POST -H 'content-type: application/json' \
     -d '{"topic":"how binary search works","duration":"short"}' | python -m json.tool
   ```

## Configuration

Environment variables (prefix `IDEASCOPE_`, or a `.env` file):

| Variable | Default | Purpose |
|---|---|---|
| `IDEASCOPE_ANTHROPIC_API_KEY` | _(unset)_ | Anthropic API key — server-side only. Also read from `ANTHROPIC_API_KEY`. |
| `IDEASCOPE_MOCK_GENERATION` | `false` | Serve fixture lessons instead of calling Anthropic (§1). |
| `IDEASCOPE_PLAN_MODEL` | `claude-opus-4-8` | Model for the plan stage. |
| `IDEASCOPE_CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed frontend origins. |
