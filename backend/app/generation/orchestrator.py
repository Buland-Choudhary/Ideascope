"""Just-in-time lesson generation (docs/PLAN.md §5.1-5.3, Phase 6): runs the
plan + per-beat pipeline in the background, publishing events to a
``LessonState`` as each stage completes, so the SSE endpoint can hand beat 1
to the learner the moment it's ready instead of making them wait for the
whole lesson.

``run_lesson_generation`` is a plain synchronous function — dispatched to a
worker thread by FastAPI's ``BackgroundTasks`` (which runs sync background
tasks via a thread pool). That's the right fit here: the pipeline underneath
(Anthropic SDK, Playwright's sync API) is itself fully synchronous, exactly
like the render-check browser singleton in ``app/validation/browser.py``.
"""

from anthropic import Anthropic

from app.config import Settings
from app.generation.plan import PlanGenerationError, generate_plan
from app.generation.service import generate_and_validate_beat
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
from app.state import LessonState
from app.validation.fallback import build_fallback_scene


def run_lesson_generation(
    settings: Settings, state: LessonState, *, topic: str, params: LessonParams
) -> None:
    """Populate ``state`` incrementally, ending in ``complete`` or ``failed``.

    Never raises: every failure mode is recorded on ``state`` instead, since
    this runs detached from any request that could observe an exception.
    """
    if settings.mock_generation:
        _run_mock(state, topic=topic)
        return

    if not settings.anthropic_api_key:
        state.fail(
            "No Anthropic API key configured. Set IDEASCOPE_ANTHROPIC_API_KEY "
            "(or ANTHROPIC_API_KEY), or run with IDEASCOPE_MOCK_GENERATION=true."
        )
        return

    client = Anthropic(api_key=settings.anthropic_api_key)
    try:
        plan = generate_plan(client, settings, topic=topic, params=params)
    except PlanGenerationError as exc:
        state.fail(str(exc))
        return

    lesson = Lesson(
        id=state.lesson_id,
        topic=topic,
        params=params,
        outline=Outline(title=plan.title, summary=plan.summary, target_beat_count=len(plan.beats)),
        beats=[],
    )
    state.set_lesson(lesson)

    for i, beat_plan in enumerate(plan.beats):
        try:
            scene, status, validation = generate_and_validate_beat(
                client, settings, beat_plan=beat_plan, lesson_id=lesson.id, beat_index=i
            )
            beat = Beat(
                id=f"beat-{i}",
                index=i,
                intent=beat_plan.intent,
                primitive=beat_plan.primitive,
                engine=beat_plan.engine,
                narration=Narration(text=beat_plan.narration),
                scene=scene,
                manipulables=beat_plan.manipulables,
                status=status,
                validation=validation,
            )
        except Exception as exc:  # noqa: BLE001 — a beat-level bug must never blank a beat
            # Keeps beat indices contiguous (every index 0..N-1 gets exactly one
            # beat) even when something unexpected — not just a generation-
            # quality failure — goes wrong; beat_failed is an observability
            # signal alongside the substitute beat_ready, not a real gap.
            state.fail_beat(i, str(exc))
            beat = Beat(
                id=f"beat-{i}",
                index=i,
                intent=beat_plan.intent,
                primitive=beat_plan.primitive,
                engine=beat_plan.engine,
                narration=Narration(text=beat_plan.narration),
                scene=Scene(code=build_fallback_scene(beat_plan.narration)),
                manipulables=[],
                status=BeatStatus.DEGRADED,
                validation=BeatValidation(
                    render_ok=False,
                    auto_fix_attempts=0,
                    critique_pass=None,
                    critique_feedback=str(exc),
                ),
            )
        state.add_beat(beat)

    state.complete()


def _run_mock(state: LessonState, *, topic: str) -> None:
    """Replay a complete fixture through the same event sequence a real
    generation would produce, so mock mode exercises the real JIT/SSE surface
    (docs/PLAN.md §1) instead of just returning a finished lesson.
    """
    from app.generation.mock import mock_lesson

    fixture = mock_lesson(topic)
    state.set_lesson(fixture.model_copy(update={"id": state.lesson_id, "beats": []}))
    for beat in fixture.beats:
        state.add_beat(beat)
    state.complete()
