"""Per-beat scene-code generation (docs/PLAN.md §5.2, Phase 4).

Generates ``scene.code`` for one planned beat via Claude structured outputs, so
the response is schema-valid by construction. Two lightweight, static checks
run before the code is accepted — contract compliance (a default export) and
the §7 denylist scan — each with one feedback-guided retry. This is NOT the
Phase 5 validation pipeline: it never executes or renders the code (that's
Playwright's job); it only rejects code that's obviously wrong before it ever
reaches a browser.

The denylist patterns intentionally mirror
``frontend/src/engines/denylist.ts`` — two independent checks (server-side at
generation time, client-side before mounting), matching docs/PLAN.md §7's
"both at validation time and defensively again client-side."
"""

import re
import time
from typing import Any

from app.config import Settings
from app.generation.beat_prompts import BEAT_SYSTEM_PROMPT, build_beat_user_message
from app.generation.retry import is_retryable
from app.generation.schema import BeatCode, BeatPlan
from app.observability import UsageRecorder, log_generation_event, record_usage

_MAX_ATTEMPTS = 2

_FORBIDDEN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bfetch\s*\("), "network access (fetch)"),
    (re.compile(r"\bXMLHttpRequest\b"), "network access (XMLHttpRequest)"),
    (re.compile(r"\bWebSocket\b"), "network access (WebSocket)"),
    (re.compile(r"\bimport\s*\("), "dynamic import"),
    (re.compile(r"\beval\s*\("), "eval"),
    (re.compile(r"\bnew\s+Function\b"), "Function constructor"),
    (re.compile(r"document\s*\.\s*cookie"), "cookie access"),
    (re.compile(r"\blocalStorage\b"), "localStorage access"),
    (re.compile(r"\bsessionStorage\b"), "sessionStorage access"),
    (re.compile(r"window\s*\.\s*parent"), "parent-frame access"),
    (re.compile(r"window\s*\.\s*top"), "top-frame access"),
    (re.compile(r"\bpostMessage\s*\("), "direct postMessage (runtime owns the bridge)"),
]


class BeatGenerationError(RuntimeError):
    """Raised when a beat's scene code cannot be generated within the retry budget."""


def _denylist_reason(code: str) -> str | None:
    for pattern, reason in _FORBIDDEN_PATTERNS:
        if pattern.search(code):
            return reason
    return None


def generate_beat_scene(
    client: Any,
    settings: Settings,
    *,
    beat: BeatPlan,
    lesson_id: str,
    beat_index: int,
    extra_feedback: str | None = None,
    on_usage: UsageRecorder | None = None,
) -> str:
    """Generate and return this beat's scene code (module source).

    ``extra_feedback``, when given, is appended to the base prompt — used by
    the validation pipeline (docs/PLAN.md §5.2 step 4) to regenerate a beat
    that failed the vision critique, steering the new attempt away from the
    same mistake. Independent of the contract/denylist retry loop below,
    which always starts from the (possibly feedback-augmented) base message.
    """
    system = [
        {"type": "text", "text": BEAT_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
    ]
    user_message = build_beat_user_message(beat)
    if extra_feedback:
        user_message = f"{user_message}\n\n{extra_feedback}"
    log_ctx = {
        "lesson_id": lesson_id,
        "beat_index": beat_index,
        "primitive": beat.primitive.value,
        "engine": beat.engine.value,
    }

    last_error: str | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        content = user_message
        if last_error:
            content = f"{user_message}\n\nFix the previous attempt: {last_error}"

        started = time.monotonic()
        try:
            response = client.messages.parse(
                model=settings.beat_model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": content}],
                output_format=BeatCode,
            )
        except Exception as exc:  # noqa: BLE001 — classify below, then log + convert/retry
            retryable = is_retryable(exc)
            log_generation_event(
                "beat", "error", attempt=attempt, error=str(exc), retryable=retryable, **log_ctx
            )
            if retryable and attempt < _MAX_ATTEMPTS:
                time.sleep(min(2**attempt, 10))
                continue
            raise BeatGenerationError(f"beat call failed: {exc}") from exc

        record_usage(on_usage, stage="beat", model=settings.beat_model, response=response)
        latency_ms = int((time.monotonic() - started) * 1000)
        parsed = getattr(response, "parsed_output", None)
        usage = getattr(response, "usage", None)
        code = parsed.code if isinstance(parsed, BeatCode) else ""

        if "export default" not in code:
            last_error = (
                "your response must contain a single `export default` factory "
                "function, per the contract — nothing else."
            )
            log_generation_event(
                "beat",
                "render_fail",
                attempt=attempt,
                latency_ms=latency_ms,
                error="missing export default",
                input_tokens=getattr(usage, "input_tokens", None),
                output_tokens=getattr(usage, "output_tokens", None),
                **log_ctx,
            )
            continue

        reason = _denylist_reason(code)
        if reason:
            last_error = f"the code used a forbidden pattern ({reason}); rely only on ctx."
            log_generation_event(
                "beat",
                "render_fail",
                attempt=attempt,
                latency_ms=latency_ms,
                error=reason,
                input_tokens=getattr(usage, "input_tokens", None),
                output_tokens=getattr(usage, "output_tokens", None),
                **log_ctx,
            )
            continue

        log_generation_event(
            "beat",
            "ok",
            attempt=attempt,
            latency_ms=latency_ms,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            **log_ctx,
        )
        return code

    raise BeatGenerationError(
        f"beat {beat_index} failed after {_MAX_ATTEMPTS} attempts: {last_error}"
    )
