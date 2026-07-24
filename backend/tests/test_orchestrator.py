"""Tests for the JIT generation orchestrator (docs/PLAN.md §5.1-5.3, Phase 6):
mock mode replays a fixture through the same event sequence real generation
would produce; real mode is exercised with a fake Anthropic client so plan
failures, per-beat failures, and the happy path are all covered without a
network call.
"""

from types import SimpleNamespace

import pytest

from app.config import Settings
from app.generation import orchestrator as orchestrator_module
from app.generation.plan import PlanGenerationError
from app.generation.schema import BeatCode, BeatPlan, LessonPlan
from app.models import BeatStatus, Duration, Engine, LessonParams, Primitive
from app.state.store import LessonStore


def _plan(n_beats: int) -> LessonPlan:
    return LessonPlan(
        title="Test Lesson",
        summary="A test lesson.",
        beats=[
            BeatPlan(
                intent=f"intent {i}",
                narration=f"narration {i}",
                primitive=Primitive.PLOT,
                engine=Engine.CANVAS,
            )
            for i in range(n_beats)
        ],
    )


class FakeMessages:
    """Dispatches on `output_format`, same technique as test_service.py."""

    def __init__(self, plan: LessonPlan, beat_code: str) -> None:
        self._plan = plan
        self._beat_code = beat_code

    def parse(self, **kwargs: object) -> object:
        fmt = kwargs.get("output_format")
        if fmt is LessonPlan:
            return SimpleNamespace(
                parsed_output=self._plan, usage=SimpleNamespace(input_tokens=1, output_tokens=1)
            )
        if fmt is BeatCode:
            return SimpleNamespace(
                parsed_output=BeatCode(code=self._beat_code),
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            )
        raise AssertionError(f"unexpected output_format: {fmt!r}")


class FakeClient:
    def __init__(self, plan: LessonPlan, beat_code: str) -> None:
        self.messages = FakeMessages(plan, beat_code)


GOOD_CODE = "export default (ctx) => { ctx.ready(); return {}; };"


def test_mock_mode_streams_a_complete_fixture() -> None:
    state = LessonStore().create()
    settings = Settings(mock_generation=True)

    orchestrator_module.run_lesson_generation(
        settings, state, topic="how a sine wave works", params=LessonParams()
    )

    assert state.status == "complete"
    assert state.lesson is not None
    assert state.lesson.id == state.lesson_id  # rewritten to the pre-allocated id
    assert state.lesson.beats
    events = [e.event for e in state.events_since(0)]
    assert events[0] == "outline_ready"
    assert events[-1] == "lesson_complete"
    assert events.count("beat_ready") == len(state.lesson.beats)


def test_fails_immediately_without_an_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IDEASCOPE_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    state = LessonStore().create()
    settings = Settings(mock_generation=False)

    orchestrator_module.run_lesson_generation(
        settings, state, topic="entropy", params=LessonParams()
    )

    assert state.status == "failed"
    assert state.error is not None and "API key" in state.error
    assert state.lesson is None


def test_real_mode_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = FakeClient(_plan(3), GOOD_CODE)
    monkeypatch.setattr(orchestrator_module, "Anthropic", lambda api_key: fake_client)

    state = LessonStore().create()
    settings = Settings(anthropic_api_key="sk-test", mock_generation=False)

    orchestrator_module.run_lesson_generation(
        settings, state, topic="how something works", params=LessonParams(duration=Duration.SHORT)
    )

    assert state.status == "complete"
    assert state.lesson is not None
    assert state.lesson.id == state.lesson_id
    assert state.lesson.outline.title == "Test Lesson"
    assert len(state.lesson.beats) == 3
    for i, beat in enumerate(state.lesson.beats):
        assert beat.index == i
        assert beat.status == BeatStatus.READY


def test_plan_failure_fails_the_whole_lesson(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator_module, "Anthropic", lambda api_key: object())
    monkeypatch.setattr(
        orchestrator_module,
        "generate_plan",
        lambda *a, **kw: (_ for _ in ()).throw(PlanGenerationError("no plan for you")),
    )

    state = LessonStore().create()
    settings = Settings(anthropic_api_key="sk-test", mock_generation=False)

    orchestrator_module.run_lesson_generation(settings, state, topic="t", params=LessonParams())

    assert state.status == "failed"
    assert state.error == "no plan for you"
    assert state.lesson is None
    assert [e.event for e in state.events_since(0)] == ["lesson_failed"]


def test_unexpected_beat_exception_is_skipped_not_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = FakeClient(_plan(3), GOOD_CODE)
    monkeypatch.setattr(orchestrator_module, "Anthropic", lambda api_key: fake_client)

    def flaky_generate_and_validate(client: object, settings: object, **kwargs: object) -> object:
        if kwargs["beat_index"] == 1:
            raise RuntimeError("unexpected bug")
        from app.models import BeatValidation, Scene

        return (
            Scene(code=GOOD_CODE),
            BeatStatus.READY,
            BeatValidation(render_ok=True, auto_fix_attempts=0, critique_pass=True),
        )

    monkeypatch.setattr(
        orchestrator_module, "generate_and_validate_beat", flaky_generate_and_validate
    )

    state = LessonStore().create()
    settings = Settings(anthropic_api_key="sk-test", mock_generation=False)

    orchestrator_module.run_lesson_generation(
        settings, state, topic="t", params=LessonParams(duration=Duration.SHORT)
    )

    assert state.status == "complete"  # a single beat's bug doesn't fail the lesson
    assert state.lesson is not None
    # Beat indices stay contiguous — the failing beat is degraded, not skipped.
    assert [b.index for b in state.lesson.beats] == [0, 1, 2]
    assert state.lesson.beats[1].status == BeatStatus.DEGRADED
    assert state.lesson.beats[0].status == BeatStatus.READY
    assert state.lesson.beats[2].status == BeatStatus.READY
    events = [e.event for e in state.events_since(0)]
    assert events == [
        "outline_ready",
        "beat_ready",
        "beat_failed",
        "beat_ready",
        "beat_ready",
        "lesson_complete",
    ]
