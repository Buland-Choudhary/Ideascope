"""End-to-end orchestration test for real-mode generate_lesson.

Uses a fake Anthropic client (dispatching on `output_format`) so the whole
plan → per-beat pipeline is exercised without a network call.
"""

from types import SimpleNamespace

import pytest

from app.config import Settings
from app.generation.schema import BeatCode, BeatPlan, LessonPlan
from app.generation.service import GenerationUnavailableError, generate_lesson
from app.models import BeatStatus, Duration, Engine, LessonParams, Palette, Primitive
from app.validation.schema import Critique

_PALETTE = Palette(
    background="#f8fafc", primary="#4f46e5", secondary="#f59e0b", text="#334155", muted="#cbd5e1"
)


def _plan(n_beats: int) -> LessonPlan:
    return LessonPlan(
        title="Test Lesson",
        summary="A test lesson.",
        palette=_PALETTE,
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
    """Dispatches on `output_format`: LessonPlan for the plan call, BeatCode per
    beat, and (when skip_validation triggers the lightweight code review)
    Critique per review call. ``review_passed`` controls every review verdict;
    a beat that regenerates gets ``regenerated_code`` on its second BeatCode
    call, so tests can distinguish "shipped as generated" from "shipped after
    a review-triggered rewrite".
    """

    def __init__(
        self,
        plan: LessonPlan,
        beat_code: str,
        *,
        review_passed: bool = True,
        regenerated_code: str | None = None,
    ) -> None:
        self._plan = plan
        self._beat_code = beat_code
        self._review_passed = review_passed
        self._regenerated_code = regenerated_code
        self.plan_calls = 0
        self.beat_calls = 0
        self.review_calls = 0

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
            code = self._beat_code
            if self.beat_calls == 2 and self._regenerated_code is not None:
                code = self._regenerated_code
            return SimpleNamespace(
                parsed_output=BeatCode(code=code),
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            )
        if fmt is Critique:
            self.review_calls += 1
            # Only the very first review call fails, when regenerated_code is
            # set — every other call (including the retry after a rewrite)
            # passes, so exactly one beat regenerates.
            passed = self._review_passed or self.review_calls > 1
            return SimpleNamespace(
                parsed_output=Critique(
                    passed=passed, feedback="ok" if passed else "missing ctx.ready()"
                ),
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            )
        raise AssertionError(f"unexpected output_format: {fmt!r}")


class FakeClient:
    def __init__(
        self,
        plan: LessonPlan,
        beat_code: str,
        *,
        review_passed: bool = True,
        regenerated_code: str | None = None,
    ) -> None:
        self.messages = FakeMessages(
            plan, beat_code, review_passed=review_passed, regenerated_code=regenerated_code
        )


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


def test_generate_lesson_skip_validation_ships_code_after_passing_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With skip_validation, a beat skips the Playwright render-check/auto-fix/
    vision-critique pipeline (no render call ever happens — the fake client
    has no render/screenshot surface at all), but still gets the lightweight
    text-only code review (app/validation/code_review.py) before shipping."""
    code = "export default (ctx) => { ctx.ready(); return {}; }"
    # duration=short bands to 3-5 beats; the fake plan below has 3.
    fake_client = FakeClient(_plan(3), code, review_passed=True)
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
        assert beat.validation.critique_pass is True
        assert beat.validation.critique_feedback == "ok"

    assert fake_client.messages.plan_calls == 1
    assert fake_client.messages.beat_calls == 3
    assert fake_client.messages.review_calls == 3


def test_generate_lesson_skip_validation_regenerates_after_failed_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A beat that fails the code review gets one feedback-guided regeneration
    retry, then ships whatever the retry's own review verdict says — mirroring
    the full pipeline's critique-and-retry shape, just without ever rendering
    anything."""
    code = "export default (ctx) => { ctx.ready(); return {}; }"
    regenerated_code = "export default (ctx) => { ctx.ready(); return { fixed: true }; }"
    # review_passed=False makes only the *first* review call fail (see
    # FakeMessages) — exactly one beat (the first) regenerates and passes on
    # its retry; the other two pass their only review outright.
    fake_client = FakeClient(_plan(3), code, review_passed=False, regenerated_code=regenerated_code)
    monkeypatch.setattr("app.generation.service.Anthropic", lambda api_key: fake_client)

    settings = Settings(anthropic_api_key="sk-test", mock_generation=False, skip_validation=True)
    lesson = generate_lesson(
        settings,
        topic="how something works",
        params=LessonParams(duration=Duration.SHORT),
    )

    assert lesson.beats[0].scene.code == regenerated_code
    assert lesson.beats[0].validation is not None
    assert lesson.beats[0].validation.critique_pass is True
    assert lesson.beats[1].scene.code == code
    assert lesson.beats[2].scene.code == code

    assert fake_client.messages.beat_calls == 4  # 3 beats + 1 regeneration
    assert fake_client.messages.review_calls == 4  # 3 beats + 1 re-review


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
