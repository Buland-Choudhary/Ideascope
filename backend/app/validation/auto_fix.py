"""Auto-fix: repair a scene that failed the render check (docs/PLAN.md §5.2
step 3). Runs on ``claude-haiku-4-5`` by design — this is constrained,
well-specified repair work against a known error, not creative generation, so
it doesn't need the big model (docs/PLAN.md §1).
"""

import time
from typing import Any

from app.config import Settings
from app.generation.retry import is_retryable
from app.generation.schema import BeatCode
from app.observability import log_generation_event

_MAX_API_ATTEMPTS = 2  # transient-error retries for a single fix call, not fix rounds

_SYSTEM_PROMPT = """\
You repair broken scene modules for Ideascope. You will be given a scene's \
source code and the error it produced. Return a corrected version of the \
ENTIRE module that fixes the error while preserving the original visual intent \
as closely as possible. Follow the same contract the original code was written \
against: a single `export default` factory `(ctx) => controller`, no imports, \
no network/eval/storage access, call `ctx.ready()` once at a representative \
frame. Do not rewrite parts of the scene that aren't related to the error."""


def build_auto_fix_user_message(*, engine: str, code: str, error: str) -> str:
    return (
        f"Engine: {engine}\n\nBroken code:\n```js\n{code}\n```\n\n"
        f"Error when rendered:\n{error}\n\nReturn the fixed module."
    )


def auto_fix_scene(
    client: Any,
    settings: Settings,
    *,
    engine: str,
    code: str,
    error: str,
    lesson_id: str,
    beat_index: int,
) -> str | None:
    """Return repaired code, or ``None`` if the fix call itself failed."""
    user_message = build_auto_fix_user_message(engine=engine, code=code, error=error)
    log_ctx = {"lesson_id": lesson_id, "beat_index": beat_index, "engine": engine}

    for attempt in range(1, _MAX_API_ATTEMPTS + 1):
        started = time.monotonic()
        try:
            response = client.messages.parse(
                model=settings.auto_fix_model,
                max_tokens=4096,
                system=[{"type": "text", "text": _SYSTEM_PROMPT}],
                messages=[{"role": "user", "content": user_message}],
                output_format=BeatCode,
            )
        except Exception as exc:  # noqa: BLE001 — classify below, then log + convert/retry
            retryable = is_retryable(exc)
            log_generation_event(
                "auto_fix",
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

        latency_ms = int((time.monotonic() - started) * 1000)
        parsed = getattr(response, "parsed_output", None)
        usage = getattr(response, "usage", None)
        if not isinstance(parsed, BeatCode) or "export default" not in parsed.code:
            log_generation_event(
                "auto_fix",
                "error",
                attempt=attempt,
                latency_ms=latency_ms,
                error="no usable fix returned",
                **log_ctx,
            )
            return None

        log_generation_event(
            "auto_fix",
            "ok",
            attempt=attempt,
            latency_ms=latency_ms,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            **log_ctx,
        )
        return parsed.code

    return None
