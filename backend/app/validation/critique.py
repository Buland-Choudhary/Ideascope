"""Vision self-critique (docs/PLAN.md §5.2 step 4): screenshot a passing scene
and ask Claude whether it actually achieves the beat's pedagogical intent —
the core correctness gate (D7). Runs on ``claude-opus-4-8`` per docs/PLAN.md §1.
"""

import base64
import time
from typing import Any

from app.config import Settings
from app.generation.retry import is_retryable
from app.observability import log_generation_event
from app.validation.schema import Critique

_MAX_API_ATTEMPTS = 2

_SYSTEM_PROMPT = """\
You are grading one beat of an animated micro-lesson against its intended \
pedagogical goal, using only a screenshot of how it currently renders.

Judge visually: does the image plausibly show what the intent describes? Be \
concrete — check for the specific elements the intent implies (labeled axes, \
the right number of stages, a comparison actually being shown side by side, \
etc.), not just "does something appear to be rendered." A scene that renders \
without errors but shows the wrong thing, mislabels something, or omits a key \
element described in the intent should NOT pass.

Do not penalize minor visual polish issues (colors, exact spacing) — focus on \
whether the concept is correctly and recognizably depicted."""


def _build_user_content(*, intent: str, narration: str) -> str:
    return (
        f"Intent: {intent}\n\nNarration the learner sees alongside this: {narration}\n\n"
        "Does the attached screenshot achieve this intent?"
    )


def critique_screenshot(
    client: Any,
    settings: Settings,
    *,
    screenshot: bytes,
    intent: str,
    narration: str,
    lesson_id: str,
    beat_index: int,
) -> Critique | None:
    """Return a ``Critique``, or ``None`` if the critique call itself failed."""
    image_b64 = base64.standard_b64encode(screenshot).decode("ascii")
    log_ctx = {"lesson_id": lesson_id, "beat_index": beat_index}

    for attempt in range(1, _MAX_API_ATTEMPTS + 1):
        started = time.monotonic()
        try:
            response = client.messages.parse(
                model=settings.critique_model,
                max_tokens=1024,
                system=[{"type": "text", "text": _SYSTEM_PROMPT}],
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_b64,
                                },
                            },
                            {
                                "type": "text",
                                "text": _build_user_content(intent=intent, narration=narration),
                            },
                        ],
                    }
                ],
                output_format=Critique,
            )
        except Exception as exc:  # noqa: BLE001 — classify below, then log + convert/retry
            retryable = is_retryable(exc)
            log_generation_event(
                "critique",
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
        if not isinstance(parsed, Critique):
            log_generation_event(
                "critique",
                "error",
                attempt=attempt,
                latency_ms=latency_ms,
                error="no parsed critique returned",
                **log_ctx,
            )
            return None

        log_generation_event(
            "critique",
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
