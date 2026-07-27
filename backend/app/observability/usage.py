"""Per-call token usage capture, feeding the user-facing token/cost report
(``app/observability/pricing.py``, ``LessonState.usage_summary``). Every
generation function that calls the Anthropic API takes an optional
``on_usage`` callback and invokes it once per real response it gets —
including an attempt that goes on to fail a downstream check and retry,
since that attempt still cost real tokens. Threaded through as a callback
rather than folded into a return value so recording usage never changes what
a caller gets back.
"""

from typing import Protocol


class UsageRecorder(Protocol):
    def __call__(
        self, *, stage: str, model: str, input_tokens: int, output_tokens: int
    ) -> None: ...


def record_usage(
    on_usage: UsageRecorder | None, *, stage: str, model: str, response: object
) -> None:
    """Extract token counts off an SDK response and forward them to
    ``on_usage``.

    Safe to call unconditionally: a missing callback, or a response with no
    (or non-integer) ``usage`` attribute — as fake test clients often omit —
    both no-op silently rather than raising.
    """
    if on_usage is None:
        return
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
        return
    on_usage(stage=stage, model=model, input_tokens=input_tokens, output_tokens=output_tokens)
