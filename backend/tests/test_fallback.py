"""Graceful-degradation fallback tests — real browser, no Anthropic call.

Confirms the deterministic text fallback (docs/PLAN.md §5.2 step 5) always
satisfies the scene contract, including against adversarial narration text
that a degraded beat's own generation attempt might have contained.
"""

from app.validation.fallback import build_fallback_scene
from app.validation.render_check import render_check


def test_fallback_scene_renders() -> None:
    code = build_fallback_scene("A short explanation of how tides work.")
    result = render_check(engine="svg", code=code, params={})
    assert result.ok is True
    assert result.screenshot is not None


def test_fallback_scene_wraps_long_text_into_multiple_lines() -> None:
    long_text = " ".join(["word"] * 40)
    code = build_fallback_scene(long_text)
    assert code.count("tspan") > 2  # opening+closing tags for >1 line
    result = render_check(engine="svg", code=code, params={})
    assert result.ok is True


def test_fallback_scene_is_safe_against_script_injection() -> None:
    code = build_fallback_scene("<script>window.__pwned__ = true;</script>")
    assert "innerHTML" not in code  # assigned via .textContent, never parsed as markup
    result = render_check(engine="svg", code=code, params={})
    assert result.ok is True
