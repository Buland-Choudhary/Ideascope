"""Lesson generation endpoint (docs/PLAN.md §5.1).

Phase 3 is synchronous: ``POST /api/lessons`` returns a lesson directly. The
just-in-time / SSE-streaming version (return ``{lessonId}``, then stream
``beat_ready`` events) arrives in Phase 6.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings
from app.generation.beat import BeatGenerationError
from app.generation.plan import PlanGenerationError
from app.generation.service import GenerationUnavailableError, generate_lesson
from app.models import Difficulty, Duration, Lesson, LessonParams, Tone

router = APIRouter()


class GenerateLessonRequest(BaseModel):
    # Topic length cap (docs/PLAN.md §5.4); empty topics rejected.
    topic: str = Field(min_length=1, max_length=300)
    duration: Duration = Duration.MEDIUM
    difficulty: Difficulty | None = None
    prior_knowledge: str | None = Field(default=None, max_length=500)
    tone: Tone | None = None


@router.post("/api/lessons", response_model=Lesson)
def create_lesson(request: GenerateLessonRequest) -> Lesson:
    settings = get_settings()
    params = LessonParams(
        duration=request.duration,
        difficulty=request.difficulty,
        prior_knowledge=request.prior_knowledge,
        tone=request.tone,
    )
    try:
        return generate_lesson(settings, topic=request.topic.strip(), params=params)
    except GenerationUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (PlanGenerationError, BeatGenerationError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
