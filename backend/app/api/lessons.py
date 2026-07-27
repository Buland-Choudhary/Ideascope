"""Lesson generation endpoints (docs/PLAN.md §5.1) — the just-in-time /
SSE-streaming surface. ``POST /api/lessons`` kicks off generation in the
background and returns ``{lessonId}`` immediately; the beats themselves
arrive over ``GET /api/lessons/{id}/stream`` as they're generated and
validated, so the learner sees beat 1 without waiting for the whole lesson.
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.config import ALLOWED_GENERATION_MODELS, get_settings
from app.generation.orchestrator import run_lesson_generation
from app.models import (
    Beat,
    CamelModel,
    Difficulty,
    Duration,
    Lesson,
    LessonParams,
    LessonUsage,
    Tone,
)
from app.observability.pricing import PRICING_PER_MTOK
from app.rate_limit import limiter
from app.state import LessonState, get_lesson_store

router = APIRouter()

# SSE keepalive so proxies/hosts don't kill an idle-looking long-lived
# connection while a beat is still generating (docs/PLAN.md §9).
_KEEPALIVE_SECONDS = 15.0
_POLL_INTERVAL_SECONDS = 0.25

_TERMINAL_EVENTS = {"lesson_complete", "lesson_failed"}


class GenerateLessonRequest(BaseModel):
    # Topic length cap (docs/PLAN.md §5.4); empty (or whitespace-only) topics
    # rejected. Stripped *before* the length check — otherwise a string of
    # pure whitespace passes `min_length=1` and only becomes empty later.
    topic: str = Field(min_length=1, max_length=300)
    duration: Duration = Duration.MEDIUM
    difficulty: Difficulty | None = None
    prior_knowledge: str | None = Field(default=None, max_length=500)
    tone: Tone | None = None
    # Optional per-lesson model override for plan+beat generation (docs/PLAN.md
    # §14 cost-experimentation note) — lets a learner trade quality for cost
    # (or vice versa) one lesson at a time instead of via a server env var.
    # None keeps the server's configured defaults (Settings.plan_model /
    # .beat_model).
    model: str | None = None

    @field_validator("topic")
    @classmethod
    def _strip_topic(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("topic must not be empty or whitespace-only")
        return stripped

    @field_validator("model")
    @classmethod
    def _validate_model(cls, value: str | None) -> str | None:
        if value is not None and value not in ALLOWED_GENERATION_MODELS:
            raise ValueError(
                f"unsupported model {value!r}; choose one of {ALLOWED_GENERATION_MODELS}"
            )
        return value


class CreateLessonResponse(CamelModel):
    lesson_id: str


class ModelOption(CamelModel):
    id: str
    input_price_per_mtok: float
    output_price_per_mtok: float


class LessonStateResponse(CamelModel):
    lesson_id: str
    status: str
    error: str | None = None
    lesson: Lesson | None = None
    usage: LessonUsage | None = None


def _require_generation_available() -> None:
    settings = get_settings()
    if not settings.mock_generation and not settings.anthropic_api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "No Anthropic API key configured. Set IDEASCOPE_ANTHROPIC_API_KEY "
                "(or ANTHROPIC_API_KEY), or run with IDEASCOPE_MOCK_GENERATION=true."
            ),
        )


def _get_state_or_404(lesson_id: str) -> LessonState:
    state = get_lesson_store().get(lesson_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Unknown lesson id: {lesson_id!r}")
    return state


@router.post("/api/lessons", response_model=CreateLessonResponse, status_code=202)
@limiter.limit(lambda: get_settings().lessons_rate_limit)
def create_lesson(
    request: Request, body: GenerateLessonRequest, background_tasks: BackgroundTasks
) -> CreateLessonResponse:
    _require_generation_available()
    settings = get_settings()
    if body.model:
        # Per-lesson override, not a mutation of the cached global Settings —
        # model_copy returns a new instance, so concurrent lessons with
        # different (or no) override never see each other's choice.
        settings = settings.model_copy(update={"plan_model": body.model, "beat_model": body.model})
    params = LessonParams(
        duration=body.duration,
        difficulty=body.difficulty,
        prior_knowledge=body.prior_knowledge,
        tone=body.tone,
    )
    state = get_lesson_store().create()
    background_tasks.add_task(
        run_lesson_generation, settings, state, topic=body.topic, params=params
    )
    return CreateLessonResponse(lesson_id=state.lesson_id)


@router.get("/api/models", response_model=list[ModelOption])
def list_models() -> list[ModelOption]:
    """The models a learner can pick for a lesson (docs/PLAN.md §14 cost-
    experimentation note), with the $/MTok pricing used to estimate cost —
    so the picker can show the trade-off, not just a bare id.
    """
    return [
        ModelOption(
            id=model_id,
            input_price_per_mtok=PRICING_PER_MTOK[model_id]["input"],
            output_price_per_mtok=PRICING_PER_MTOK[model_id]["output"],
        )
        for model_id in ALLOWED_GENERATION_MODELS
    ]


@router.get("/api/lessons/{lesson_id}", response_model=LessonStateResponse)
def get_lesson_state(lesson_id: str) -> LessonStateResponse:
    """Full current known state — for SSE-reconnect and debugging."""
    state = _get_state_or_404(lesson_id)
    usage = state.usage_summary()
    return LessonStateResponse(
        lesson_id=state.lesson_id,
        status=state.status,
        error=state.error,
        lesson=state.lesson,
        usage=usage if (usage.input_tokens or usage.output_tokens) else None,
    )


@router.get("/api/lessons/{lesson_id}/beats/{index}", response_model=Beat)
def get_lesson_beat(lesson_id: str, index: int) -> Beat:
    """Single beat detail — a fallback if a client missed an SSE event.

    Looked up by the beat's own ``index`` field, not its position in
    ``state.lesson.beats`` — beats can complete out of order now that
    generation runs several at a time (docs/PLAN.md §5.2), so list position
    no longer matches logical index while a lesson is still generating.
    """
    state = _get_state_or_404(lesson_id)
    beat = next((b for b in (state.lesson.beats if state.lesson else []) if b.index == index), None)
    if beat is None:
        raise HTTPException(status_code=404, detail=f"No beat {index} for lesson {lesson_id!r}")
    return beat


def _json_lines(data: object) -> list[str]:
    # SSE "data:" fields can't contain a bare newline; json.dumps without
    # indentation never produces one, but split defensively in case that ever
    # changes (e.g. someone adds indent= while debugging).
    return json.dumps(data).split("\n")


async def _event_stream(state: LessonState) -> AsyncIterator[bytes]:
    last_seq = 0
    last_sent = time.monotonic()
    while True:
        events = state.events_since(last_seq)
        for evt in events:
            last_seq = evt.seq + 1
            yield f"event: {evt.event}\n".encode()
            for line in _json_lines(evt.data):
                yield f"data: {line}\n".encode()
            yield b"\n"
            last_sent = time.monotonic()
        if events and events[-1].event in _TERMINAL_EVENTS:
            return
        if not events:
            if time.monotonic() - last_sent >= _KEEPALIVE_SECONDS:
                yield b": keepalive\n\n"
                last_sent = time.monotonic()
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)


@router.get("/api/lessons/{lesson_id}/stream")
async def stream_lesson(lesson_id: str) -> StreamingResponse:
    state = _get_state_or_404(lesson_id)
    return StreamingResponse(
        _event_stream(state),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
