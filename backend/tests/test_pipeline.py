"""Orchestration tests for the validation pipeline (app.validation.pipeline),
using monkeypatched render/auto-fix/critique/regenerate calls so each branch —
happy path, auto-fix recovery, critique-triggered regeneration, the infra-
failure carve-out, and full degradation — is exercised deterministically
without a browser or network call. render_check.py itself is covered
end-to-end (real browser) in test_render_check.py.
"""

import pytest

from app.config import Settings
from app.generation.schema import BeatPlan
from app.models import BeatStatus, Engine, Primitive
from app.validation import pipeline as pipeline_module
from app.validation.render_check import RenderCheckResult
from app.validation.schema import Critique

SETTINGS = Settings(critique_model="claude-opus-4-8", auto_fix_model="claude-haiku-4-5")


def _beat_plan() -> BeatPlan:
    return BeatPlan(
        intent="Show something.",
        narration="Some narration.",
        primitive=Primitive.PLOT,
        engine=Engine.CANVAS,
    )


def _ok_render(screenshot: bytes = b"png-bytes") -> RenderCheckResult:
    return RenderCheckResult(ok=True, screenshot=screenshot)


def _fail_render(error: str = "boom") -> RenderCheckResult:
    return RenderCheckResult(ok=False, error=error)


def _validate(**overrides: object) -> pipeline_module.ValidatedBeat:
    kwargs: dict[str, object] = {
        "client": object(),
        "settings": SETTINGS,
        "beat_plan": _beat_plan(),
        "code": "orig",
        "lesson_id": "l1",
        "beat_index": 0,
    }
    kwargs.update(overrides)
    return pipeline_module.validate_beat(**kwargs)  # type: ignore[arg-type]


def test_interaction_screenshot_and_metadata_pass_through_to_critique(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pipeline_module,
        "render_check",
        lambda **kw: RenderCheckResult(
            ok=True,
            screenshot=b"before",
            interaction_screenshot=b"after",
            interaction_param="amplitude",
            interaction_value=90,
        ),
    )
    captured: dict[str, object] = {}

    def fake_critique(*a: object, **kw: object) -> Critique:
        captured.update(kw)
        return Critique(passed=True, feedback="ok")

    monkeypatch.setattr(pipeline_module, "critique_screenshot", fake_critique)

    result = _validate()

    assert result.status == BeatStatus.READY
    assert captured["interaction_screenshot"] == b"after"
    assert captured["interaction_param"] == "amplitude"
    assert captured["interaction_value"] == 90


def test_happy_path_renders_and_passes_critique(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline_module, "render_check", lambda **kw: _ok_render())
    monkeypatch.setattr(
        pipeline_module,
        "critique_screenshot",
        lambda *a, **kw: Critique(passed=True, feedback="looks right"),
    )

    result = _validate()

    assert result.status == BeatStatus.READY
    assert result.render_ok is True
    assert result.auto_fix_attempts == 0
    assert result.critique_pass is True
    assert result.code == "orig"


def test_render_fails_then_auto_fix_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    render_calls = {"n": 0}

    def fake_render(**kw: object) -> RenderCheckResult:
        render_calls["n"] += 1
        return _fail_render("syntax error") if render_calls["n"] == 1 else _ok_render()

    monkeypatch.setattr(pipeline_module, "render_check", fake_render)
    monkeypatch.setattr(pipeline_module, "auto_fix_scene", lambda *a, **kw: "fixed code")
    monkeypatch.setattr(
        pipeline_module,
        "critique_screenshot",
        lambda *a, **kw: Critique(passed=True, feedback="ok"),
    )

    result = _validate()

    assert result.status == BeatStatus.READY
    assert result.auto_fix_attempts == 1
    assert render_calls["n"] == 2


def test_critique_fails_then_regeneration_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline_module, "render_check", lambda **kw: _ok_render())
    critique_calls = {"n": 0}

    def fake_critique(*a: object, **kw: object) -> Critique:
        critique_calls["n"] += 1
        if critique_calls["n"] == 1:
            return Critique(passed=False, feedback="missing axis labels")
        return Critique(passed=True, feedback="good now")

    monkeypatch.setattr(pipeline_module, "critique_screenshot", fake_critique)
    monkeypatch.setattr(pipeline_module, "generate_beat_scene", lambda *a, **kw: "regenerated code")

    result = _validate()

    assert result.status == BeatStatus.READY
    assert result.critique_pass is True
    assert result.code == "regenerated code"
    assert critique_calls["n"] == 2


def test_ships_as_ready_when_critique_call_itself_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline_module, "render_check", lambda **kw: _ok_render())
    monkeypatch.setattr(pipeline_module, "critique_screenshot", lambda *a, **kw: None)

    result = _validate()

    assert result.status == BeatStatus.READY
    assert result.render_ok is True
    assert result.critique_pass is None
    assert result.critique_feedback is None


def test_degrades_after_exhausting_critique_rounds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline_module, "render_check", lambda **kw: _ok_render())
    monkeypatch.setattr(
        pipeline_module,
        "critique_screenshot",
        lambda *a, **kw: Critique(passed=False, feedback="still wrong"),
    )
    monkeypatch.setattr(pipeline_module, "generate_beat_scene", lambda *a, **kw: "regenerated code")
    monkeypatch.setattr(pipeline_module, "build_fallback_scene", lambda text: "FALLBACK:" + text)

    result = _validate()

    assert result.status == BeatStatus.DEGRADED
    assert result.code == "FALLBACK:Some narration."
    assert result.critique_pass is False
    assert result.critique_feedback == "still wrong"


def test_degrades_after_render_never_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline_module, "render_check", lambda **kw: _fail_render("always broken"))
    monkeypatch.setattr(pipeline_module, "auto_fix_scene", lambda *a, **kw: None)
    monkeypatch.setattr(pipeline_module, "generate_beat_scene", lambda *a, **kw: "regenerated code")
    monkeypatch.setattr(pipeline_module, "build_fallback_scene", lambda text: "FALLBACK:" + text)

    result = _validate()

    assert result.status == BeatStatus.DEGRADED
    assert result.render_ok is False
    assert result.critique_pass is None
    assert result.critique_feedback == "always broken"
    assert result.code == "FALLBACK:Some narration."
