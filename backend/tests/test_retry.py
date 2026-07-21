"""Tests for the transient-error retry classification (app.generation.retry).

Also exercises the "retry once on a transient error" path in generate_plan and
generate_beat_scene, using real Anthropic SDK exception types (constructed
directly, no network) rather than plain Exceptions — this is what a 529
overloaded / 429 rate-limit / connection blip actually looks like.
"""

import httpx
import pytest
from anthropic import APIConnectionError, APIStatusError, RateLimitError

from app.config import Settings
from app.generation.beat import generate_beat_scene
from app.generation.plan import generate_plan
from app.generation.retry import is_retryable
from app.generation.schema import BeatPlan, LessonPlan
from app.models import Engine, LessonParams, Primitive

from .test_beat import FakeClient as FakeBeatClient
from .test_plan import FakeClient as FakePlanClient


def _status_error(status_code: int) -> APIStatusError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status_code, request=request)
    return APIStatusError("boom", response=response, body=None)


def _connection_error() -> APIConnectionError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return APIConnectionError(request=request)


def test_overloaded_and_serverside_errors_are_retryable() -> None:
    assert is_retryable(_status_error(529)) is True
    assert is_retryable(_status_error(500)) is True
    assert is_retryable(_connection_error()) is True


def test_client_errors_are_not_retryable() -> None:
    assert is_retryable(_status_error(400)) is False
    assert is_retryable(_status_error(404)) is False
    assert is_retryable(ValueError("not an anthropic error")) is False


def test_rate_limit_error_is_retryable() -> None:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(429, request=request)
    assert is_retryable(RateLimitError("slow down", response=response, body=None)) is True


def _flaky_then_ok_plan_client(plan: LessonPlan) -> FakePlanClient:
    """A fake plan client whose first .parse() raises a transient error."""
    client = FakePlanClient([plan])
    real_parse = client.messages.parse
    calls = {"n": 0}

    def flaky_parse(**kwargs: object) -> object:
        calls["n"] += 1
        if calls["n"] == 1:
            raise _status_error(529)
        return real_parse(**kwargs)

    client.messages.parse = flaky_parse  # type: ignore[method-assign]
    return client


def test_plan_retries_once_on_transient_error_then_succeeds() -> None:
    from .test_plan import _plan

    client = _flaky_then_ok_plan_client(_plan(7))  # medium band 6-9
    plan = generate_plan(
        client, Settings(plan_model="claude-opus-4-8"), topic="t", params=LessonParams()
    )
    assert len(plan.beats) == 7


def test_beat_retries_once_on_transient_error_then_succeeds() -> None:
    good_code = "export default (ctx) => { ctx.ready(); return {}; }"
    client = FakeBeatClient([good_code])
    real_parse = client.messages.parse
    calls = {"n": 0}

    def flaky_parse(**kwargs: object) -> object:
        calls["n"] += 1
        if calls["n"] == 1:
            raise _connection_error()
        return real_parse(**kwargs)

    client.messages.parse = flaky_parse  # type: ignore[method-assign]

    beat = BeatPlan(intent="x", narration="n", primitive=Primitive.PLOT, engine=Engine.CANVAS)
    code = generate_beat_scene(
        client,
        Settings(beat_model="claude-opus-4-8"),
        beat=beat,
        lesson_id="l",
        beat_index=0,
    )
    assert code == good_code


def test_non_retryable_error_fails_immediately_without_consuming_full_budget() -> None:
    """A genuine bad-request error should not be retried at all."""

    class BoomOnceClient:
        def __init__(self) -> None:
            self.calls = 0
            self.messages = self

        def parse(self, **kwargs: object) -> object:
            self.calls += 1
            raise _status_error(400)

    client = BoomOnceClient()
    with pytest.raises(Exception, match="beat call failed"):
        generate_beat_scene(
            client,
            Settings(beat_model="claude-opus-4-8"),
            beat=BeatPlan(
                intent="x", narration="n", primitive=Primitive.PLOT, engine=Engine.CANVAS
            ),
            lesson_id="l",
            beat_index=0,
        )
    assert client.calls == 1
