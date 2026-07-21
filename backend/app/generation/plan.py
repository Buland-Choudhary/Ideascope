"""The plan stage: topic + params → whole-lesson outline via Claude.

Uses the Anthropic API's native structured outputs (``client.messages.parse``
against the ``LessonPlan`` model), so the response is schema-valid by
construction — no JSON parsing or shape-retry code. The one retry is reserved
for *semantic* problems the schema can't express, e.g. a beat count outside the
duration band (docs/PLAN.md §5.2).
"""

import time
from typing import Any

from app.config import Settings
from app.generation.prompts import PLAN_SYSTEM_PROMPT, build_plan_user_message
from app.generation.schema import LessonPlan
from app.models import BEAT_BANDS, LessonParams
from app.observability import log_generation_event

_MAX_ATTEMPTS = 2


class PlanGenerationError(RuntimeError):
    """Raised when the plan stage cannot produce a usable outline."""


def _within_band(plan: LessonPlan, params: LessonParams) -> bool:
    lo, hi = BEAT_BANDS[params.duration]
    return bool(lo <= len(plan.beats) <= hi)


def generate_plan(
    client: Any,
    settings: Settings,
    *,
    topic: str,
    params: LessonParams,
) -> LessonPlan:
    """Generate and return a validated ``LessonPlan``.

    ``client`` is an ``anthropic.Anthropic`` (typed ``Any`` to avoid coupling to
    the SDK's parse signature); tests inject a fake with the same ``messages.parse``
    surface.
    """
    system = [
        {"type": "text", "text": PLAN_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
    ]
    user_message = build_plan_user_message(topic, params)
    lo, hi = BEAT_BANDS[params.duration]

    last_error: str | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        content = user_message
        if last_error:
            content = f"{user_message}\n\nRevise your previous plan: {last_error}"

        started = time.monotonic()
        try:
            response = client.messages.parse(
                model=settings.plan_model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": content}],
                output_format=LessonPlan,
            )
        except Exception as exc:  # noqa: BLE001 — log and convert to a domain error
            log_generation_event("plan", "error", topic=topic, attempt=attempt, error=str(exc))
            raise PlanGenerationError(f"plan call failed: {exc}") from exc

        latency_ms = int((time.monotonic() - started) * 1000)
        plan = _extract_plan(response)
        usage = getattr(response, "usage", None)

        if plan is None:
            last_error = "the response did not contain a parsed plan; return the required fields."
            log_generation_event(
                "plan",
                "error",
                topic=topic,
                attempt=attempt,
                latency_ms=latency_ms,
                error="no parsed_output",
            )
            continue

        if not _within_band(plan, params):
            last_error = (
                f"you returned {len(plan.beats)} beats; this duration needs {lo}–{hi}. "
                "Re-plan with a beat count in that range."
            )
            log_generation_event(
                "plan",
                "critique_fail",
                topic=topic,
                attempt=attempt,
                latency_ms=latency_ms,
                beat_count=len(plan.beats),
                input_tokens=getattr(usage, "input_tokens", None),
                output_tokens=getattr(usage, "output_tokens", None),
            )
            continue

        log_generation_event(
            "plan",
            "ok",
            topic=topic,
            attempt=attempt,
            latency_ms=latency_ms,
            beat_count=len(plan.beats),
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
        )
        return plan

    raise PlanGenerationError(f"plan stage failed after {_MAX_ATTEMPTS} attempts: {last_error}")


def _extract_plan(response: object) -> LessonPlan | None:
    parsed = getattr(response, "parsed_output", None)
    return parsed if isinstance(parsed, LessonPlan) else None
