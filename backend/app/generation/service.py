"""Generation orchestration — the entry point the API calls.

Phase 3 added the plan stage; Phase 4 added per-beat scene generation; Phase 5
adds the validation pipeline, so real mode now returns a lesson whose beats
have each been render-checked, auto-fixed, and vision-critiqued — or gracefully
degraded to a reliable text fallback rather than shipping something broken
(docs/PLAN.md §5.2 steps 3-5). Beats generate and validate sequentially within
the request for now; JIT/SSE delivery so the learner sees beat 1 immediately is
Phase 6.
"""

import uuid

from anthropic import Anthropic

from app.config import Settings
from app.generation.beat import generate_beat_scene
from app.generation.plan import generate_plan
from app.generation.schema import LessonPlan
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
        code = generate_beat_scene(
            client, settings, beat=beat_plan, lesson_id=lesson.id, beat_index=i
        )
        validated = validate_beat(
            client, settings, beat_plan=beat_plan, code=code, lesson_id=lesson.id, beat_index=i
        )
        beat.scene = Scene(code=validated.code)
        beat.status = validated.status
        beat.validation = BeatValidation(
            render_ok=validated.render_ok,
            auto_fix_attempts=validated.auto_fix_attempts,
            critique_pass=validated.critique_pass,
            critique_feedback=validated.critique_feedback,
        )

    return lesson
