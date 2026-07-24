"""Auto-fix repair tests using a fake Anthropic client — no network call.

Exercises success, the transient-error retry (shared with plan/beat via
app.generation.retry), and the two ways a fix call can come back unusable.
"""

from types import SimpleNamespace

import httpx
from anthropic import APIConnectionError

from app.config import Settings
from app.generation.schema import BeatCode
from app.validation.auto_fix import auto_fix_scene

GOOD_FIX = "export default function createScene(ctx) { ctx.ready(); return {}; }"

SETTINGS = Settings(auto_fix_model="claude-haiku-4-5")


class FakeMessages:
    def __init__(self, results: list[object]) -> None:
        self._results = results
        self.calls = 0

    def parse(self, **kwargs: object) -> object:
        result = self._results[self.calls]
        self.calls += 1
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(
            parsed_output=BeatCode(code=str(result)),
            usage=SimpleNamespace(input_tokens=5, output_tokens=15),
        )


class FakeClient:
    def __init__(self, results: list[object]) -> None:
        self.messages = FakeMessages(results)


def test_returns_fixed_code_on_success() -> None:
    client = FakeClient([GOOD_FIX])
    fixed = auto_fix_scene(
        client,
        SETTINGS,
        engine="canvas",
        code="broken",
        error="ReferenceError: x is not defined",
        lesson_id="l1",
        beat_index=0,
    )
    assert fixed == GOOD_FIX
    assert client.messages.calls == 1


def test_retries_on_transient_error_then_succeeds() -> None:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    client = FakeClient([APIConnectionError(request=request), GOOD_FIX])
    fixed = auto_fix_scene(
        client,
        SETTINGS,
        engine="canvas",
        code="broken",
        error="boom",
        lesson_id="l1",
        beat_index=0,
    )
    assert fixed == GOOD_FIX
    assert client.messages.calls == 2


def test_returns_none_when_fix_lacks_export_default() -> None:
    client = FakeClient(["function createScene(ctx) { ctx.ready(); }"])
    fixed = auto_fix_scene(
        client,
        SETTINGS,
        engine="canvas",
        code="broken",
        error="boom",
        lesson_id="l1",
        beat_index=0,
    )
    assert fixed is None


def test_returns_none_when_call_fails_non_retryably() -> None:
    client = FakeClient([RuntimeError("boom")])
    fixed = auto_fix_scene(
        client,
        SETTINGS,
        engine="canvas",
        code="broken",
        error="boom",
        lesson_id="l1",
        beat_index=0,
    )
    assert fixed is None
