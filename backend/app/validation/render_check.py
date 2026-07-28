"""The render/auto-fix check's execution half (docs/PLAN.md §5.2 step 3):
load the generated scene in a real, sandboxed browser and determine whether it
renders — catching JS execution errors, console errors, and hangs — before it
ever reaches a learner. Does not call Claude; ``app/validation/pipeline.py``
wires this together with auto-fix and critique.
"""

from dataclasses import dataclass
from typing import Any

from app.validation import browser as browser_module
from app.validation.runtime import ERROR, READY, build_harness_html, build_scene_srcdoc


@dataclass
class RenderCheckResult:
    ok: bool
    error: str | None = None
    screenshot: bytes | None = None
    # Second screenshot after simulating a manipulable change, if any (§5.2
    # step 4), plus which param/value produced it — so the vision critique
    # (app/validation/critique.py, Phase 7) can judge whether the interaction
    # visibly and correctly changed the rendering, not just that the initial
    # frame looks right.
    interaction_screenshot: bytes | None = None
    interaction_param: str | None = None
    interaction_value: object | None = None


def _first_manipulable_alternate_value(manipulables: list[Any]) -> tuple[str, object] | None:
    """Pick a param + a value distinct from its default, to exercise onParamChange."""
    if not manipulables:
        return None
    m = manipulables[0]
    if m.type.value in ("slider", "stepper"):
        lo, hi = m.min, m.max
        mid = lo + (hi - lo) / 2
        alt = mid if mid != m.default else hi
        return m.param, alt
    if m.type.value == "toggle":
        return m.param, not m.default
    if m.type.value == "select" and m.options:
        alt = next((o for o in m.options if o != m.default), m.options[0])
        return m.param, alt
    return None


def render_check(
    *,
    engine: str,
    code: str,
    params: dict[str, object],
    manipulables: list[Any] | None = None,
    timeout_ms: int = 5000,
    max_concurrent: int = 3,
    palette: dict[str, str] | None = None,
) -> RenderCheckResult:
    """Load ``code`` in a sandboxed browser and report whether it renders.

    A scene passes if it calls ``ctx.ready()`` (or its controller's
    ``render``/first ``draw`` does) within ``timeout_ms``, without throwing or
    logging a console error first. Anything else — an explicit ``ctx`` error
    report, an uncaught exception, or a hang — is a failure with a message
    suitable for feeding back to the auto-fix model.
    """
    srcdoc = build_scene_srcdoc(engine=engine, code=code, params=params, palette=palette)
    harness = build_harness_html(srcdoc)

    with browser_module.get_page(max_concurrent=max_concurrent) as page:
        page_errors: list[str] = []
        console_errors: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
        )

        page.set_content(harness)

        try:
            page.wait_for_function("window.__ideascope_status__ !== null", timeout=timeout_ms)
        except Exception:  # noqa: BLE001 — Playwright's TimeoutError; treat any wait failure as a hang
            if page_errors:
                return RenderCheckResult(ok=False, error=page_errors[0])
            return RenderCheckResult(
                ok=False,
                error=f"scene did not call ctx.ready() or report an error within {timeout_ms}ms",
            )

        status = page.evaluate("window.__ideascope_status__")
        if page_errors:
            return RenderCheckResult(ok=False, error=page_errors[0])
        if status.get("type") == ERROR:
            return RenderCheckResult(ok=False, error=status.get("message", "unknown scene error"))
        if status.get("type") != READY:
            return RenderCheckResult(ok=False, error=f"unexpected status: {status!r}")

        screenshot = page.locator("#scene").screenshot()

        interaction_screenshot = None
        interaction_param = interaction_value = None
        alt = _first_manipulable_alternate_value(manipulables or [])
        if alt is not None:
            param, value = alt
            page.evaluate("([p, v]) => window.__ideascope_update_param__(p, v)", [param, value])
            page.wait_for_timeout(300)
            if page_errors:
                return RenderCheckResult(ok=False, error=page_errors[0])
            post_status = page.evaluate("window.__ideascope_status__")
            if post_status and post_status.get("type") == ERROR:
                return RenderCheckResult(
                    ok=False, error=post_status.get("message", "error during interaction")
                )
            interaction_screenshot = page.locator("#scene").screenshot()
            interaction_param, interaction_value = param, value

        return RenderCheckResult(
            ok=True,
            screenshot=screenshot,
            interaction_screenshot=interaction_screenshot,
            interaction_param=interaction_param,
            interaction_value=interaction_value,
        )
