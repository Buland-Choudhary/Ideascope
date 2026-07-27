"""Lightweight text-based code review — a cheap stand-in for the heavy
Playwright-based validation pipeline when ``skip_validation`` is on (docs/
PLAN.md's Phase 10 cost-lever note). Rather than rendering the scene in a
real browser, this asks a small/cheap model to read the generated source
directly and judge whether it plausibly satisfies the beat's intent and
avoids common structural bugs — catching an obviously wrong or broken beat
without needing Chromium at all.

Deliberately cheap and approximate: it cannot see the rendering, so it will
miss purely visual defects (bad layout, colors, spacing) that
``critique.py``'s screenshot-based judgement would catch. It's a floor, not
a replacement for full validation — see the module docstring in
``app/generation/service.py`` for how the two relate.
"""

import time
from typing import Any

from app.config import Settings
from app.generation.retry import is_retryable
from app.generation.schema import BeatPlan
from app.observability import UsageRecorder, log_generation_event, record_usage
from app.validation.schema import Critique

_MAX_API_ATTEMPTS = 2

_SYSTEM_PROMPT = """\
You are reviewing the SOURCE CODE of one beat of an animated micro-lesson — \
you cannot see it render, only read it. Judge whether the code plausibly \
achieves the stated intent, and flag concrete structural problems a reviewer \
could catch just by reading:

- Does it call `ctx.ready()` somewhere (a scene that never signals ready \
never displays anything to the learner)?
- Does it actually build the elements the intent describes — the right \
number of stages/axes/labeled parts/comparison items — rather than something \
generic or unrelated to the stated intent?
- Any obvious JS bugs: a variable used before it's defined, mismatched \
brackets/parens, a syntax error, an early return that skips required setup?
- Does it size itself from `ctx.width`/`ctx.height` rather than hardcoding \
pixel dimensions (hardcoding usually breaks on other screen sizes)?
- If manipulables are listed below, does the code actually read their \
current values from `ctx` (an ignored manipulable is a broken control)?

This is a coarse, code-only pass, not a full render check — only fail code \
for a real, specific problem you can point to. Do not fail a scene merely \
because you would have written it differently, and do not penalize visual \
polish you can't actually judge from source alone."""


def _build_user_message(*, beat_plan: BeatPlan, code: str) -> str:
    manipulable_note = (
        f"Manipulables this beat declares: {', '.join(m.param for m in beat_plan.manipulables)}."
        if beat_plan.manipulables
        else "This beat declares no manipulables."
    )
    return (
        f"Intent: {beat_plan.intent}\n\n"
        f"Narration shown alongside it: {beat_plan.narration}\n\n"
        f"{manipulable_note}\n\n"
        f"Scene code:\n```js\n{code}\n```\n\n"
        "Does this code plausibly achieve the intent, and is it free of the "
        "structural problems described above?"
    )


def review_beat_code(
    client: Any,
    settings: Settings,
    *,
    beat_plan: BeatPlan,
    code: str,
    lesson_id: str,
    beat_index: int,
    on_usage: UsageRecorder | None = None,
) -> Critique | None:
    """Return a text-only ``Critique`` verdict on ``code``, or ``None`` if the
    review call itself failed (infra, not a quality signal — callers should
    treat that as "unreviewed", not "failed", and ship the code as-is).

    Runs on ``settings.auto_fix_model`` — like ``auto_fix.py``, this is
    constrained, well-specified judgement work against a known rubric, not
    creative generation, so it doesn't need the big model.
    """
    log_ctx = {"lesson_id": lesson_id, "beat_index": beat_index}
    user_message = _build_user_message(beat_plan=beat_plan, code=code)

    for attempt in range(1, _MAX_API_ATTEMPTS + 1):
        started = time.monotonic()
        try:
            response = client.messages.parse(
                model=settings.auto_fix_model,
                max_tokens=1024,
                system=[{"type": "text", "text": _SYSTEM_PROMPT}],
                messages=[{"role": "user", "content": user_message}],
                output_format=Critique,
            )
        except Exception as exc:  # noqa: BLE001 — classify below, then log + convert/retry
            retryable = is_retryable(exc)
            log_generation_event(
                "code_review",
                "error",
                attempt=attempt,
                error=str(exc),
                retryable=retryable,
                **log_ctx,
            )
            if retryable and attempt < _MAX_API_ATTEMPTS:
                time.sleep(min(2**attempt, 10))
                continue
            return None

        record_usage(
            on_usage, stage="code_review", model=settings.auto_fix_model, response=response
        )
        latency_ms = int((time.monotonic() - started) * 1000)
        parsed = getattr(response, "parsed_output", None)
        usage = getattr(response, "usage", None)
        if not isinstance(parsed, Critique):
            log_generation_event(
                "code_review",
                "error",
                attempt=attempt,
                latency_ms=latency_ms,
                error="no parsed critique returned",
                **log_ctx,
            )
            return None

        log_generation_event(
            "code_review",
            "ok" if parsed.passed else "critique_fail",
            attempt=attempt,
            latency_ms=latency_ms,
            passed=parsed.passed,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            **log_ctx,
        )
        return parsed

    return None
