"""Render-check tests against the real, sandboxed headless-Chromium harness —
no Anthropic call, so these are free to run repeatedly. Exercises the render/
auto-fix check's execution half (docs/PLAN.md §5.2 step 3): a scene that
renders cleanly, the two contract violations that should fail loudly (missing
export, thrown error), a hang, and the manipulable-interaction smoke path.
"""

from collections.abc import Iterator

import pytest

from app.models import Manipulable, ManipulableType
from app.validation import browser as browser_module
from app.validation.render_check import render_check

GOOD_CANVAS = """
export default function createScene(ctx) {
  ctx.p5.background(255);
  ctx.p5.circle(ctx.width / 2, ctx.height / 2, 40);
  ctx.ready();
  return {};
}
"""

GOOD_SVG_WITH_MANIPULABLE = """
export default function createScene(ctx) {
  const NS = "http://www.w3.org/2000/svg";
  const circle = document.createElementNS(NS, "circle");
  circle.setAttribute("cx", "50");
  circle.setAttribute("cy", "50");
  circle.setAttribute("r", String(ctx.params.radius));
  ctx.svg.appendChild(circle);
  ctx.ready();
  return {
    onParamChange(param, value) {
      if (param === "radius") circle.setAttribute("r", String(value));
    },
  };
}
"""

MISSING_EXPORT = """
function createScene(ctx) { ctx.ready(); return {}; }
"""

THROWS = """
export default function createScene(ctx) {
  throw new Error("kaboom");
}
"""

NEVER_READY = """
export default function createScene(ctx) {
  return {};
}
"""

GSAP_CANVAS = """
export default function createScene(ctx) {
  if (!ctx.gsap || typeof ctx.gsap.to !== "function") {
    throw new Error("ctx.gsap not available");
  }
  const state = { r: 10 };
  ctx.gsap.to(state, { r: 40, duration: 0.05, ease: "power2.out" });
  let firstFrame = true;
  return {
    draw(p) {
      p.background(255);
      p.circle(ctx.width / 2, ctx.height / 2, state.r);
      if (firstFrame) { firstFrame = false; ctx.ready(); }
    },
  };
}
"""

GSAP_SVG = """
export default function createScene(ctx) {
  if (!ctx.gsap || typeof ctx.gsap.to !== "function") {
    throw new Error("ctx.gsap not available");
  }
  const NS = "http://www.w3.org/2000/svg";
  const circle = document.createElementNS(NS, "circle");
  circle.setAttribute("cx", "50");
  circle.setAttribute("cy", "50");
  circle.setAttribute("r", "10");
  ctx.svg.appendChild(circle);
  ctx.gsap.to({}, { duration: 0.01 }); // exercises a real tween end-to-end
  ctx.ready();
  return {};
}
"""


@pytest.fixture(autouse=True, scope="module")
def _cleanup_browser() -> Iterator[None]:
    yield
    browser_module.shutdown()


def test_good_canvas_scene_renders() -> None:
    result = render_check(engine="canvas", code=GOOD_CANVAS, params={})
    assert result.ok is True
    assert result.error is None
    assert result.screenshot is not None


def test_missing_default_export_fails() -> None:
    result = render_check(engine="canvas", code=MISSING_EXPORT, params={})
    assert result.ok is False
    assert "default" in (result.error or "")


def test_thrown_error_is_captured() -> None:
    result = render_check(engine="canvas", code=THROWS, params={})
    assert result.ok is False
    assert "kaboom" in (result.error or "")


def test_hanging_scene_times_out_as_failure() -> None:
    result = render_check(engine="canvas", code=NEVER_READY, params={}, timeout_ms=500)
    assert result.ok is False
    assert result.error is not None


def test_gsap_is_available_in_canvas_scenes() -> None:
    result = render_check(engine="canvas", code=GSAP_CANVAS, params={})
    assert result.ok is True
    assert result.error is None
    assert result.screenshot is not None


def test_gsap_is_available_in_svg_scenes() -> None:
    result = render_check(engine="svg", code=GSAP_SVG, params={})
    assert result.ok is True
    assert result.error is None
    assert result.screenshot is not None


def test_svg_scene_with_manipulable_interaction() -> None:
    manipulable = Manipulable(
        id="radius",
        label="Radius",
        type=ManipulableType.SLIDER,
        param="radius",
        default=10,
        min=1,
        max=100,
    )
    result = render_check(
        engine="svg",
        code=GOOD_SVG_WITH_MANIPULABLE,
        params={"radius": 10},
        manipulables=[manipulable],
    )
    assert result.ok is True
    assert result.screenshot is not None
    assert result.interaction_screenshot is not None
    # Interacting should actually change the rendered pixels.
    assert result.interaction_screenshot != result.screenshot
    assert result.interaction_param == "radius"
    assert result.interaction_value != 10  # moved away from the default
