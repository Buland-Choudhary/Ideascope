"""End-to-end orchestration test for real-mode generate_lesson.

Uses a fake Anthropic client (dispatching on `output_format`) so the whole
plan → per-beat pipeline is exercised without a network call.
"""

from types import SimpleNamespace

import pytest

from app.config import Settings
from app.generation.schema import BeatCode, BeatPlan, LessonPlan
from app.generation.service import GenerationUnavailableError, generate_lesson
from app.models import BeatStatus, Duration, Engine, LessonParams, Primitive


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
    """Dispatches on `output_format`: LessonPlan for the plan call, BeatCode per beat."""

    def __init__(self, plan: LessonPlan, beat_code: str) -> None:
        self._plan = plan
        self._beat_code = beat_code
        self.plan_calls = 0
        self.beat_calls = 0

    def parse(self, **kwargs: object) -> object:
        fmt = kwargs.get("output_format")
        if fmt is LessonPlan:
            self.plan_calls += 1
            return SimpleNamespace(
                parsed_output=self._plan,
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            )
        if fmt is BeatCode:
            self.beat_calls += 1
            return SimpleNamespace(
                parsed_output=BeatCode(code=self._beat_code),
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            )
        raise AssertionError(f"unexpected output_format: {fmt!r}")


class FakeClient:
    def __init__(self, plan: LessonPlan, beat_code: str) -> None:
        self.messages = FakeMessages(plan, beat_code)


def test_generate_lesson_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    good_code = "export default (ctx) => { ctx.ready(); return {}; }"
    # duration=short bands to 3-5 beats; the fake plan below has 3.
    fake_client = FakeClient(_plan(3), good_code)
    monkeypatch.setattr("app.generation.service.Anthropic", lambda api_key: fake_client)

    settings = Settings(anthropic_api_key="sk-test", mock_generation=False)
    lesson = generate_lesson(
        settings,
        topic="how something works",
        params=LessonParams(duration=Duration.SHORT),
    )

    assert lesson.outline.title == "Test Lesson"
    assert len(lesson.beats) == 3
    for i, beat in enumerate(lesson.beats):
        assert beat.index == i
        assert beat.scene.code == good_code
        assert beat.status == BeatStatus.READY

    assert fake_client.messages.plan_calls == 1
    assert fake_client.messages.beat_calls == 3


def test_generate_lesson_skip_validation_ships_code_unchecked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With skip_validation, a beat ships straight from generation — no
    render-check/auto-fix/critique call, so a fake client that only ever
    answers the plan/beat-code formats (and would raise on a Critique
    request) proves validate_beat was never invoked."""
    code = "export default (ctx) => { ctx.ready(); return {}; }"
    # duration=short bands to 3-5 beats; the fake plan below has 3.
    fake_client = FakeClient(_plan(3), code)
    monkeypatch.setattr("app.generation.service.Anthropic", lambda api_key: fake_client)

    settings = Settings(anthropic_api_key="sk-test", mock_generation=False, skip_validation=True)
    lesson = generate_lesson(
        settings,
        topic="how something works",
        params=LessonParams(duration=Duration.SHORT),
    )

    assert len(lesson.beats) == 3
    for beat in lesson.beats:
        assert beat.status == BeatStatus.READY
        assert beat.scene.code == code
        assert beat.validation is not None
        assert beat.validation.render_ok is True
        assert beat.validation.auto_fix_attempts == 0
        assert beat.validation.critique_pass is None

    assert fake_client.messages.plan_calls == 1
    assert fake_client.messages.beat_calls == 3


def test_generate_lesson_without_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # setenv to "", not delenv: Settings reads backend/.env directly (a lower-
    # priority source than a real env var, but higher than the field default),
    # so merely deleting the env var still lets a real key in .env leak
    # through — an empty env var actually wins that source-priority fight.
    monkeypatch.setenv("IDEASCOPE_ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    settings = Settings(mock_generation=False)
    with pytest.raises(GenerationUnavailableError):
        generate_lesson(settings, topic="t", params=LessonParams())
