"""Beat-generation tests using a fake Anthropic client.

Exercises structured-output handling, the contract-compliance retry (missing
`export default`), and the denylist retry (§7) — without a network call.
"""

from types import SimpleNamespace

import pytest

from app.config import Settings
from app.generation.beat import BeatGenerationError, generate_beat_scene
from app.generation.schema import BeatCode, BeatPlan
from app.models import Engine, Primitive

GOOD_CODE = "export default function createScene(ctx) { ctx.ready(); return {}; }"
NO_EXPORT_CODE = "function createScene(ctx) { ctx.ready(); return {}; }"
DENYLISTED_CODE = (
    "export default (ctx) => { fetch('https://evil.example'); ctx.ready(); return {}; }"
)

SETTINGS = Settings(beat_model="claude-opus-4-8")  # type: ignore[call-arg]


def _beat_plan() -> BeatPlan:
    return BeatPlan(
        intent="Show something.",
        narration="Some narration.",
        primitive=Primitive.PLOT,
        engine=Engine.CANVAS,
    )


class FakeMessages:
    def __init__(self, codes: list[str]) -> None:
        self._codes = codes
        self.calls = 0

    def parse(self, **kwargs: object) -> object:
        code = self._codes[self.calls]
        self.calls += 1
        return SimpleNamespace(
            parsed_output=BeatCode(code=code),
            usage=SimpleNamespace(input_tokens=10, output_tokens=20),
        )


class FakeClient:
    def __init__(self, codes: list[str]) -> None:
        self.messages = FakeMessages(codes)


def test_accepts_good_code_on_first_attempt() -> None:
    client = FakeClient([GOOD_CODE])
    code = generate_beat_scene(client, SETTINGS, beat=_beat_plan(), lesson_id="l1", beat_index=0)
    assert code == GOOD_CODE
    assert client.messages.calls == 1


def test_retries_when_missing_default_export() -> None:
    client = FakeClient([NO_EXPORT_CODE, GOOD_CODE])
    code = generate_beat_scene(client, SETTINGS, beat=_beat_plan(), lesson_id="l1", beat_index=0)
    assert code == GOOD_CODE
    assert client.messages.calls == 2


def test_retries_when_denylisted_pattern_present() -> None:
    client = FakeClient([DENYLISTED_CODE, GOOD_CODE])
    code = generate_beat_scene(client, SETTINGS, beat=_beat_plan(), lesson_id="l1", beat_index=0)
    assert code == GOOD_CODE
    assert client.messages.calls == 2


def test_gives_up_after_max_attempts() -> None:
    client = FakeClient([NO_EXPORT_CODE, NO_EXPORT_CODE])
    with pytest.raises(BeatGenerationError):
        generate_beat_scene(client, SETTINGS, beat=_beat_plan(), lesson_id="l1", beat_index=0)
    assert client.messages.calls == 2


def test_wraps_client_errors() -> None:
    class BoomMessages:
        def parse(self, **kwargs: object) -> object:
            raise RuntimeError("boom")

    client = SimpleNamespace(messages=BoomMessages())
    with pytest.raises(BeatGenerationError, match="beat call failed"):
        generate_beat_scene(
            client,  # type: ignore[arg-type]
            SETTINGS,
            beat=_beat_plan(),
            lesson_id="l1",
            beat_index=0,
        )
