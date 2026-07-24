"""Orchestrates the full validation pipeline for one beat (docs/PLAN.md §5.2
steps 3-5): render/auto-fix → vision self-critique → bounded regeneration →
graceful degradation. This is what turns "a beat has generated code" into "a
beat is safe to ship to a learner."
"""

from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.generation.beat import generate_beat_scene
from app.generation.schema import BeatPlan
from app.models import BeatStatus
from app.observability import log_generation_event
from app.validation.auto_fix import auto_fix_scene
from app.validation.critique import critique_screenshot
from app.validation.fallback import build_fallback_scene
from app.validation.render_check import RenderCheckResult, render_check

_MAX_AUTO_FIX_ATTEMPTS = 2  # per render round (docs/PLAN.md §5.2 step 3)
_MAX_CRITIQUE_ROUNDS = 2  # initial + 1 critique-triggered retry (§5.2 step 4)


@dataclass
class ValidatedBeat:
    code: str
    status: BeatStatus
    render_ok: bool
    auto_fix_attempts: int
    critique_pass: bool | None
    critique_feedback: str | None


def _default_params(manipulables: list[Any]) -> dict[str, object]:
    return {m.param: m.default for m in manipulables}


def _render_with_auto_fix(
    client: Any,
    settings: Settings,
    *,
    engine: str,
    code: str,
    manipulables: list[Any],
    lesson_id: str,
    beat_index: int,
) -> tuple[RenderCheckResult, str, int]:
    """Render-check ``code``, repairing via auto-fix up to the attempt budget.

    Returns the final render result, the code that produced it (which may
    differ from the input if a fix was applied), and how many fix calls ran.
    """
    current_code = code
    fix_attempts = 0
    params = _default_params(manipulables)

    for round_ in range(_MAX_AUTO_FIX_ATTEMPTS + 1):
        result = render_check(
            engine=engine,
            code=current_code,
            params=params,
            manipulables=manipulables,
            timeout_ms=settings.render_timeout_ms,
            max_concurrent=settings.max_concurrent_renders,
        )
        if result.ok or round_ >= _MAX_AUTO_FIX_ATTEMPTS:
            return result, current_code, fix_attempts

        fixed = auto_fix_scene(
            client,
            settings,
            engine=engine,
            code=current_code,
            error=result.error or "unknown render error",
            lesson_id=lesson_id,
            beat_index=beat_index,
        )
        fix_attempts += 1
        if fixed is None:
            return result, current_code, fix_attempts
        current_code = fixed

    return result, current_code, fix_attempts  # pragma: no cover — loop always returns above


def validate_beat(
    client: Any,
    settings: Settings,
    *,
    beat_plan: BeatPlan,
    code: str,
    lesson_id: str,
    beat_index: int,
) -> ValidatedBeat:
    """Run the full validation pipeline and return a beat that's safe to ship.

    Always returns a usable result — either a validated/ready beat or a
    gracefully degraded one (docs/PLAN.md §5.2 step 5). Never raises for a
    generation-quality problem; only a bug in this function itself would.
    """
    engine = beat_plan.engine.value
    current_code = code
    total_auto_fix_attempts = 0
    critique_feedback: str | None = None
    last_render_error: str | None = None

    for critique_round in range(_MAX_CRITIQUE_ROUNDS):
        render_result, current_code, fix_attempts = _render_with_auto_fix(
            client,
            settings,
            engine=engine,
            code=current_code,
            manipulables=beat_plan.manipulables,
            lesson_id=lesson_id,
            beat_index=beat_index,
        )
        total_auto_fix_attempts += fix_attempts

        if not render_result.ok:
            last_render_error = render_result.error
            if critique_round < _MAX_CRITIQUE_ROUNDS - 1:
                current_code = (
                    generate_beat_scene(
                        client,
                        settings,
                        beat=beat_plan,
                        lesson_id=lesson_id,
                        beat_index=beat_index,
                        extra_feedback=(
                            f"A previous attempt at this beat failed to render: "
                            f"{render_result.error}. Avoid that mistake."
                        ),
                    )
                    or current_code
                )
                continue
            break  # exhausted — degrade below

        assert render_result.screenshot is not None
        critique = critique_screenshot(
            client,
            settings,
            screenshot=render_result.screenshot,
            intent=beat_plan.intent,
            narration=beat_plan.narration,
            lesson_id=lesson_id,
            beat_index=beat_index,
        )
        if critique is None:
            # The critique call itself failed (infra, not quality) — the scene
            # did render correctly, so ship it rather than degrade over an
            # unrelated API hiccup. Recorded as critique_pass=None (unknown).
            return ValidatedBeat(
                code=current_code,
                status=BeatStatus.READY,
                render_ok=True,
                auto_fix_attempts=total_auto_fix_attempts,
                critique_pass=None,
                critique_feedback=None,
            )

        if critique.passed:
            return ValidatedBeat(
                code=current_code,
                status=BeatStatus.READY,
                render_ok=True,
                auto_fix_attempts=total_auto_fix_attempts,
                critique_pass=True,
                critique_feedback=critique.feedback,
            )

        critique_feedback = critique.feedback
        last_render_error = None
        if critique_round < _MAX_CRITIQUE_ROUNDS - 1:
            current_code = (
                generate_beat_scene(
                    client,
                    settings,
                    beat=beat_plan,
                    lesson_id=lesson_id,
                    beat_index=beat_index,
                    extra_feedback=(
                        f"A previous attempt at this beat did not pass visual review: "
                        f"{critique.feedback}. Address this."
                    ),
                )
                or current_code
            )
            continue

    log_generation_event(
        "beat",
        "degraded",
        lesson_id=lesson_id,
        beat_index=beat_index,
        auto_fix_attempts=total_auto_fix_attempts,
        render_error=last_render_error,
        critique_feedback=critique_feedback,
    )
    return ValidatedBeat(
        code=build_fallback_scene(beat_plan.narration),
        status=BeatStatus.DEGRADED,
        render_ok=last_render_error is None,
        auto_fix_attempts=total_auto_fix_attempts,
        critique_pass=False if critique_feedback else None,
        critique_feedback=critique_feedback or last_render_error,
    )
