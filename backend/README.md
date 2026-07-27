# Ideascope backend

FastAPI service for the Claude-powered lesson generation pipeline. See
[`../docs/PLAN.md`](../docs/PLAN.md) §5 for the full design.

## Development

Uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
cd backend
uv sync                                # create .venv and install deps + dev deps
uv run playwright install chromium     # one-time: browser used by the validation pipeline
uv run uvicorn app.main:app --reload   # http://localhost:8000/api/health
```

The Playwright install step is required even in mock mode's absence of real
generation, since the validation pipeline's own tests launch a real browser
(no Anthropic cost — see `IDEASCOPE_MOCK_GENERATION` below for skipping real
API calls specifically). If Chromium fails to launch with a missing shared
library error, install its system dependencies too:
`uv run playwright install --with-deps chromium` (uses `sudo apt-get` under
the hood on Debian/Ubuntu).

## Checks

```bash
uv run ruff check .           # lint
uv run ruff format --check .  # format
uv run mypy app tests         # type-check
uv run pytest                 # tests (real Chromium, no Anthropic calls — $0)
```

## Generating lessons

The just-in-time API (docs/PLAN.md §5.1): `POST /api/lessons` kicks off
generation and returns `{"lessonId": "..."}` immediately; subscribe to
`GET /api/lessons/{id}/stream` (Server-Sent Events) for `outline_ready`,
`beat_ready`, `beat_failed`, and `lesson_complete`/`lesson_failed` events as
the lesson is planned, generated, and validated. `GET /api/lessons/{id}` and
`GET /api/lessons/{id}/beats/{index}` cover reconnects and debugging.

- **Mock mode** (`IDEASCOPE_MOCK_GENERATION=true`) replays a complete,
  playable fixture lesson through that same event sequence — no API key, no
  network, no cost. Use this for frontend/UI work and most backend dev.
- **Real mode** runs the full pipeline against Claude: plan → per-beat scene
  generation → render-check/auto-fix → vision critique → graceful
  degradation (docs/PLAN.md §5.2). Needs an Anthropic API key (below); every
  beat costs real tokens.

### Setting the Anthropic API key

1. Get a key from the [Anthropic Console](https://console.anthropic.com/) →
   **Settings → API keys → Create Key**. It looks like `sk-ant-...`.
2. Put it in `backend/.env` (this file is git-ignored):
   ```
   IDEASCOPE_ANTHROPIC_API_KEY=sk-ant-your-key-here
   ```
   The plain `ANTHROPIC_API_KEY` name also works. Never commit the key.
3. Run in real mode (mock off) and try it:
   ```bash
   uv run uvicorn app.main:app --reload   # IDEASCOPE_MOCK_GENERATION defaults to false
   curl -s localhost:8000/api/lessons -X POST -H 'content-type: application/json' \
     -d '{"topic":"how binary search works","duration":"short"}'
   # => {"lessonId":"lesson-..."}  — then:
   curl -N localhost:8000/api/lessons/<lessonId>/stream
   ```

## Configuration

Environment variables (prefix `IDEASCOPE_`, or a `.env` file):

| Variable | Default | Purpose |
|---|---|---|
| `IDEASCOPE_ANTHROPIC_API_KEY` | _(unset)_ | Anthropic API key — server-side only. Also read from `ANTHROPIC_API_KEY`. |
| `IDEASCOPE_MOCK_GENERATION` | `false` | Serve fixture lessons instead of calling Anthropic (§1). |
| `IDEASCOPE_SKIP_VALIDATION` | `false` | Skip the render-check/auto-fix/vision-critique pipeline in real mode — ships each beat's generated code as-is, no Chromium needed. Deliberate cost/ops trade-off; see `docs/PLAN.md`'s Phase 10 note. |
| `IDEASCOPE_PLAN_MODEL` | `claude-opus-4-8` | Model for the plan stage. |
| `IDEASCOPE_BEAT_MODEL` | `claude-opus-4-8` | Model for per-beat scene generation. |
| `IDEASCOPE_AUTO_FIX_MODEL` | `claude-haiku-4-5` | Model for repairing a beat that fails to render. |
| `IDEASCOPE_CRITIQUE_MODEL` | `claude-opus-4-8` | Model for the vision self-critique step. |
| `IDEASCOPE_RENDER_TIMEOUT_MS` | `5000` | Per-beat render-check timeout (validation pipeline). |
| `IDEASCOPE_MAX_CONCURRENT_RENDERS` | `3` | Cap on concurrent Playwright render checks. |
| `IDEASCOPE_LESSONS_RATE_LIMIT` | `20/hour` | IP-based cap on `POST /api/lessons` (`slowapi` rate string). |
| `IDEASCOPE_CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed frontend origins. |
