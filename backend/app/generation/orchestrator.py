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

Beats generate several at a time (``settings.beat_generation_concurrency``),
not strictly one after another — each beat is an independent ~15-25s Anthropic
call with no data dependency on its siblings, so serializing them was pure
wasted wall-clock time. The Anthropic SDK's client is safe to share across
threads (it's a thin wrapper over ``httpx.Client``, which pools connections
for concurrent use). Because beats can now finish out of order, ``LessonState``
and ``GET .../beats/{index}`` key beats by their own ``index`` field rather
than assuming list position matches it (see ``app/state/store.py``).
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

from anthropic import Anthropic

from app.config import Settings
from app.generation.plan import PlanGenerationError, generate_plan
from app.generation.schema import BeatPlan
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
        plan = generate_plan(
            client, settings, topic=topic, params=params, on_usage=state.record_usage
        )
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

    # Only parallelize when the (Playwright-based) validation pipeline is
    # skipped: Playwright's sync API requires every call to originate from
    # the single thread that started it (browser.py's shared instance isn't
    # safe to drive from several worker threads at once — confirmed via a
    # real greenlet thread-affinity crash when this was tried). With
    # skip_validation, a beat is just one Anthropic call with no such
    # constraint, so this is exactly the case that most needs the speedup.
    #
    # When concurrency is 1 (validation active), beats run directly on this
    # calling thread via a plain loop — NOT inside a ThreadPoolExecutor, even
    # a 1-worker one. Each `ThreadPoolExecutor()` spins up a brand-new worker
    # thread, so two separate lessons generated back-to-back (e.g. across
    # requests, or across tests in one suite run) would each hand Playwright
    # a *different* thread, which breaks its single-thread affinity just as
    # surely as real concurrency does — confirmed via a second, more subtle
    # greenlet crash after the first fix above.
    concurrency = (
        max(1, min(settings.beat_generation_concurrency, len(plan.beats)))
        if settings.skip_validation
        else 1
    )
    if concurrency == 1:
        for i, beat_plan in enumerate(plan.beats):
            state.add_beat(_build_beat(client, settings, beat_plan, lesson.id, i, state))
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {
                pool.submit(_build_beat, client, settings, beat_plan, lesson.id, i, state): i
                for i, beat_plan in enumerate(plan.beats)
            }
            for future in as_completed(futures):
                state.add_beat(future.result())

    state.complete()


def _build_beat(
    client: Anthropic,
    settings: Settings,
    beat_plan: BeatPlan,
    lesson_id: str,
    index: int,
    state: LessonState,
) -> Beat:
    """Generate+validate one beat and return it, degrading to a fallback on
    any unexpected failure. Runs on a worker thread — one per concurrently
    in-flight beat (see ``run_lesson_generation``) — so this must not touch
    anything besides its own arguments and ``state`` (already thread-safe).
    """
    try:
        scene, status, validation = generate_and_validate_beat(
            client,
            settings,
            beat_plan=beat_plan,
            lesson_id=lesson_id,
            beat_index=index,
            on_usage=state.record_usage,
        )
        return Beat(
            id=f"beat-{index}",
            index=index,
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
        state.fail_beat(index, str(exc))
        return Beat(
            id=f"beat-{index}",
            index=index,
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
