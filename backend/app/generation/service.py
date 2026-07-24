"""Generation orchestration — the entry point the API calls.

Phase 3 added the plan stage; Phase 4 added per-beat scene generation; Phase 5
added the validation pipeline, so real mode returns a lesson whose beats have
each been render-checked, auto-fixed, and vision-critiqued — or gracefully
degraded to a reliable text fallback rather than shipping something broken
(docs/PLAN.md §5.2 steps 3-5). ``generate_lesson`` here generates the whole
lesson in one blocking call; ``app/generation/orchestrator.py`` (Phase 6)
shares ``generate_and_validate_beat`` below to do the same work incrementally,
streaming each beat to the client as it's ready instead of making the learner
wait for all of them.
"""

import uuid
from typing import Any

from anthropic import Anthropic

from app.config import Settings
from app.generation.beat import BeatGenerationError, generate_beat_scene
from app.generation.plan import generate_plan
from app.generation.schema import BeatPlan, LessonPlan
from app.models import (
    Beat,
    BeatStatus,
    BeatValidation,
    Lesson,
    LessonParams,
    Narration,
    Outline,
    Scene,
)
from app.observability import log_generation_event
from app.validation.fallback import build_fallback_scene
from app.validation.pipeline import validate_beat


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
            # Scene code fills in below, per beat, once generated.
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


def generate_and_validate_beat(
    client: Any, settings: Settings, *, beat_plan: BeatPlan, lesson_id: str, beat_index: int
) -> tuple[Scene, BeatStatus, BeatValidation]:
    """Generate one beat's scene code and run it through the validation
    pipeline, returning the fields a ``Beat`` needs.

    If scene-code generation itself fails outright (``BeatGenerationError`` —
    exhausted the contract/denylist retry budget, or a non-retryable API
    error), degrade straight to the deterministic text fallback rather than
    propagating the error: a beat with no content at all would violate the
    "never blank" rule (README principle 4) just as much as one that fails
    validation, so the same graceful-degradation path (docs/PLAN.md §5.2 step
    5) applies here too.
    """
    try:
        code = generate_beat_scene(
            client, settings, beat=beat_plan, lesson_id=lesson_id, beat_index=beat_index
        )
    except BeatGenerationError as exc:
        log_generation_event(
            "beat", "degraded", lesson_id=lesson_id, beat_index=beat_index, render_error=str(exc)
        )
        return (
            Scene(code=build_fallback_scene(beat_plan.narration)),
            BeatStatus.DEGRADED,
            BeatValidation(
                render_ok=False, auto_fix_attempts=0, critique_pass=None, critique_feedback=str(exc)
            ),
        )

    validated = validate_beat(
        client,
        settings,
        beat_plan=beat_plan,
        code=code,
        lesson_id=lesson_id,
        beat_index=beat_index,
    )
    return (
        Scene(code=validated.code),
        validated.status,
        BeatValidation(
            render_ok=validated.render_ok,
            auto_fix_attempts=validated.auto_fix_attempts,
            critique_pass=validated.critique_pass,
            critique_feedback=validated.critique_feedback,
        ),
    )


def generate_lesson(settings: Settings, *, topic: str, params: LessonParams) -> Lesson:
    """Generate a lesson for the given topic.

    In mock mode returns a complete, playable fixture. In real mode runs the
    plan stage, generates each beat's scene code, then validates it — render
    check + auto-fix + vision critique, or graceful degradation — so every
    returned beat is safe to show a learner (docs/PLAN.md §5.2).
    """
    if settings.mock_generation:
        # Imported lazily so mock mode has no dependency on the generation path.
        from app.generation.mock import mock_lesson

        return mock_lesson(topic)

    if not settings.anthropic_api_key:
        raise GenerationUnavailableError(
            "No Anthropic API key configured. Set IDEASCOPE_ANTHROPIC_API_KEY "
            "(or ANTHROPIC_API_KEY), or run with IDEASCOPE_MOCK_GENERATION=true."
        )

    client = Anthropic(api_key=settings.anthropic_api_key)
    plan = generate_plan(client, settings, topic=topic, params=params)
    lesson = _lesson_from_plan(topic, params, plan)

    for i, (beat_plan, beat) in enumerate(zip(plan.beats, lesson.beats, strict=True)):
        scene, status, validation = generate_and_validate_beat(
            client, settings, beat_plan=beat_plan, lesson_id=lesson.id, beat_index=i
        )
        beat.scene = scene
        beat.status = status
        beat.validation = validation

    return lesson
