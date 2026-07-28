"""Plan-stage tests using a fake Anthropic client.

Exercises structured-output handling and the semantic beat-band retry (§5.2)
without a network call or an API key.
"""

from types import SimpleNamespace

import pytest

from app.config import Settings
from app.generation.plan import PlanGenerationError, generate_plan
from app.generation.schema import BeatPlan, LessonPlan
from app.models import Engine, LessonParams, Palette, Primitive

_PALETTE = Palette(
    background="#f8fafc", primary="#4f46e5", secondary="#f59e0b", text="#334155", muted="#cbd5e1"
)


def _plan(n_beats: int) -> LessonPlan:
    return LessonPlan(
        title="T",
        summary="S",
        palette=_PALETTE,
        beats=[
            BeatPlan(
                intent=f"intent {i}",
                narration="n",
                primitive=Primitive.PLOT,
                engine=Engine.CANVAS,
            )
            for i in range(n_beats)
        ],
    )


class FakeMessages:
    def __init__(self, plans: list[LessonPlan]) -> None:
        self._plans = plans
        self.calls = 0

    def parse(self, **kwargs: object) -> object:
        plan = self._plans[self.calls]
        self.calls += 1
        return SimpleNamespace(
            parsed_output=plan, usage=SimpleNamespace(input_tokens=10, output_tokens=20)
        )


class FakeClient:
    def __init__(self, plans: list[LessonPlan]) -> None:
        self.messages = FakeMessages(plans)


SETTINGS = Settings(plan_model="claude-opus-4-8")


def test_plan_returns_when_beat_count_in_band() -> None:
    # medium band is 6–9; a 7-beat plan passes on the first attempt.
    client = FakeClient([_plan(7)])
    plan = generate_plan(client, SETTINGS, topic="t", params=LessonParams())
    assert len(plan.beats) == 7
    assert client.messages.calls == 1


def test_plan_retries_when_out_of_band_then_succeeds() -> None:
    # First plan (3 beats) is out of the medium band; second (6) is in-band.
    client = FakeClient([_plan(3), _plan(6)])
    plan = generate_plan(client, SETTINGS, topic="t", params=LessonParams())
    assert len(plan.beats) == 6
    assert client.messages.calls == 2


def test_plan_gives_up_after_max_attempts() -> None:
    client = FakeClient([_plan(2), _plan(2)])
    with pytest.raises(PlanGenerationError):
        generate_plan(client, SETTINGS, topic="t", params=LessonParams())
    assert client.messages.calls == 2


def test_plan_wraps_client_errors() -> None:
    class BoomMessages:
        def parse(self, **kwargs: object) -> object:
            raise RuntimeError("boom")

    client = SimpleNamespace(messages=BoomMessages())
    with pytest.raises(PlanGenerationError, match="plan call failed"):
        generate_plan(client, SETTINGS, topic="t", params=LessonParams())
