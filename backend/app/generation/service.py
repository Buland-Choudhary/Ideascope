"""Generation orchestration — the entry point the API calls.

Phase 3: chooses mock vs. real mode, and in real mode runs the plan stage and
assembles a ``Lesson`` whose beats are *planned but not yet generated* (empty
scene code, ``status=pending``). Per-beat scene generation (Phase 4), validation
(Phase 5), and JIT/SSE delivery (Phase 6) build on this.
"""

import uuid

from app.config import Settings
from app.generation.plan import PlanGenerationError, generate_plan
from app.generation.schema import LessonPlan
from app.models import (
    Beat,
    BeatStatus,
    Lesson,
    LessonParams,
    Narration,
    Outline,
    Scene,
)


class GenerationUnavailableError(RuntimeError):
    """Raised when real generation is requested but no API key is configured."""


def _lesson_from_plan(topic: str, params: LessonParams, plan: LessonPlan) -> Lesson:
    beats = [
        Beat(
            id=f"beat-{i}",
            index=i,
            intent=bp.intent,
            primitive=bp.primitive,
            engine=bp.engine,
            narration=Narration(text=bp.narration),
            # Scene code is generated in Phase 4; planned beats start empty/pending.
            scene=Scene(code=""),
            manipulables=bp.manipulables,
            status=BeatStatus.PENDING,
        )
        for i, bp in enumerate(plan.beats)
    ]
    return Lesson(
        id=f"lesson-{uuid.uuid4().hex[:12]}",
        topic=topic,
        params=params,
        outline=Outline(title=plan.title, summary=plan.summary, target_beat_count=len(beats)),
        beats=beats,
    )


def generate_lesson(settings: Settings, *, topic: str, params: LessonParams) -> Lesson:
    """Generate a lesson for the given topic.

    In mock mode returns a complete, playable fixture. In real mode runs the plan
    stage and returns a lesson with planned (not-yet-generated) beats.
    """
    if settings.mock_generation:
        # Imported lazily so mock mode has no dependency on the plan path.
        from app.generation.mock import mock_lesson

        return mock_lesson(topic)

    if not settings.anthropic_api_key:
        raise GenerationUnavailableError(
            "No Anthropic API key configured. Set IDEASCOPE_ANTHROPIC_API_KEY "
            "(or ANTHROPIC_API_KEY), or run with IDEASCOPE_MOCK_GENERATION=true."
        )

    from anthropic import Anthropic

    client = Anthropic(api_key=settings.anthropic_api_key)
    try:
        plan = generate_plan(client, settings, topic=topic, params=params)
    except PlanGenerationError as exc:
        raise exc
    return _lesson_from_plan(topic, params, plan)
