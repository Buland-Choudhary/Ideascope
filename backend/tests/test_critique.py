"""Vision self-critique tests using a fake Anthropic client — no network call.

Exercises the pass/fail parse paths and the transient-error retry, plus the
"call itself failed" path that the pipeline treats as an infra hiccup rather
than a quality failure.
"""

import base64
from types import SimpleNamespace

import httpx
from anthropic import APIConnectionError

from app.config import Settings
from app.validation.critique import critique_screenshot
from app.validation.schema import Critique

SETTINGS = Settings(critique_model="claude-opus-4-8")


class FakeMessages:
    def __init__(self, results: list[object]) -> None:
        self._results = results
        self.calls = 0
        self.last_kwargs: dict[str, object] = {}

    def parse(self, **kwargs: object) -> object:
        self.last_kwargs = kwargs
        result = self._results[self.calls]
        self.calls += 1
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(
            parsed_output=result,
            usage=SimpleNamespace(input_tokens=5, output_tokens=15),
        )


class FakeClient:
    def __init__(self, results: list[object]) -> None:
        self.messages = FakeMessages(results)


def test_returns_passed_critique() -> None:
    client = FakeClient([Critique(passed=True, feedback="Shows the wave clearly.")])
    critique = critique_screenshot(
        client,
        SETTINGS,
        screenshot=b"png-bytes",
        intent="Show a wave",
        narration="n",
        lesson_id="l1",
        beat_index=0,
    )
    assert critique is not None
    assert critique.passed is True


def test_returns_failed_critique_with_feedback() -> None:
    client = FakeClient([Critique(passed=False, feedback="Missing axis labels.")])
    critique = critique_screenshot(
        client,
        SETTINGS,
        screenshot=b"png-bytes",
        intent="Show a wave",
        narration="n",
        lesson_id="l1",
        beat_index=0,
    )
    assert critique is not None
    assert critique.passed is False
    assert critique.feedback == "Missing axis labels."


def test_retries_on_transient_error_then_succeeds() -> None:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    client = FakeClient([APIConnectionError(request=request), Critique(passed=True, feedback="ok")])
    critique = critique_screenshot(
        client,
        SETTINGS,
        screenshot=b"png-bytes",
        intent="x",
        narration="n",
        lesson_id="l1",
        beat_index=0,
    )
    assert critique is not None
    assert critique.passed is True
    assert client.messages.calls == 2


def test_interaction_screenshot_is_sent_alongside_the_base_one() -> None:
    client = FakeClient([Critique(passed=True, feedback="Amplitude control works.")])
    critique = critique_screenshot(
        client,
        SETTINGS,
        screenshot=b"before-bytes",
        intent="Show that amplitude controls wave height",
        narration="n",
        lesson_id="l1",
        beat_index=0,
        interaction_screenshot=b"after-bytes",
        interaction_param="amplitude",
        interaction_value=90,
    )
    assert critique is not None
    assert critique.passed is True

    content = client.messages.last_kwargs["messages"][0]["content"]  # type: ignore[index]
    image_blocks = [c for c in content if c["type"] == "image"]
    text_blocks = [c for c in content if c["type"] == "text"]
    assert len(image_blocks) == 2
    assert image_blocks[0]["source"]["data"] == base64.standard_b64encode(b"before-bytes").decode()
    assert image_blocks[1]["source"]["data"] == base64.standard_b64encode(b"after-bytes").decode()
    assert "amplitude" in text_blocks[0]["text"]
    assert "90" in text_blocks[0]["text"]


def test_without_interaction_screenshot_sends_only_one_image() -> None:
    client = FakeClient([Critique(passed=True, feedback="ok")])
    critique_screenshot(
        client,
        SETTINGS,
        screenshot=b"before-bytes",
        intent="x",
        narration="n",
        lesson_id="l1",
        beat_index=0,
    )
    content = client.messages.last_kwargs["messages"][0]["content"]  # type: ignore[index]
    assert len([c for c in content if c["type"] == "image"]) == 1


def test_returns_none_when_call_fails_non_retryably() -> None:
    client = FakeClient([RuntimeError("boom")])
    critique = critique_screenshot(
        client,
        SETTINGS,
        screenshot=b"png-bytes",
        intent="x",
        narration="n",
        lesson_id="l1",
        beat_index=0,
    )
    assert critique is None
