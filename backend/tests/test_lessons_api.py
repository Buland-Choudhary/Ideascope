"""API-level tests for the JIT/SSE lesson surface (docs/PLAN.md §5.1, Phase 6).

Mock mode's background generation task completes synchronously within the
TestClient's request/response cycle (Starlette runs ``BackgroundTasks`` before
the ASGI call returns), so by the time a test opens the stream endpoint every
event — including ``lesson_complete`` — is already buffered. That lets these
tests assert on the full event sequence with a single, non-hanging request
rather than needing real concurrency; genuine incremental delivery against a
live server is exercised separately (see the Phase 6 close-out notes in
docs/PLAN.md §11).
"""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    # Settings are cached; clear so per-test env changes take effect.
    get_settings.cache_clear()


def _parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    """Parse ``event: ...\\ndata: ...\\n\\n`` blocks into (event, data) pairs."""
    events: list[tuple[str, dict[str, Any]]] = []
    for block in body.split("\n\n"):
        if not block.strip() or block.startswith(":"):
            continue
        event_name = None
        data_lines = []
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data_lines.append(line.removeprefix("data: "))
        if event_name is not None:
            events.append((event_name, json.loads("\n".join(data_lines))))
    return events


def test_mock_mode_streams_a_complete_playable_lesson(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IDEASCOPE_MOCK_GENERATION", "true")
    get_settings.cache_clear()

    create = client.post("/api/lessons", json={"topic": "how a sine wave works"})
    assert create.status_code == 202
    lesson_id = create.json()["lessonId"]

    stream = client.get(f"/api/lessons/{lesson_id}/stream")
    assert stream.status_code == 200
    events = _parse_sse(stream.text)

    assert events[0][0] == "outline_ready"
    assert events[-1] == ("lesson_complete", {"lessonId": lesson_id})

    beat_events = [e for e in events if e[0] == "beat_ready"]
    assert beat_events, "mock lesson should stream at least one beat"
    for _, data in beat_events:
        beat = data["beat"]
        assert beat["scene"]["code"]
        assert beat["status"] == "ready"

    state = client.get(f"/api/lessons/{lesson_id}").json()
    assert state["status"] == "complete"
    assert len(state["lesson"]["beats"]) == len(beat_events)


def test_get_single_beat_after_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IDEASCOPE_MOCK_GENERATION", "true")
    get_settings.cache_clear()

    lesson_id = client.post("/api/lessons", json={"topic": "the water cycle"}).json()["lessonId"]
    client.get(f"/api/lessons/{lesson_id}/stream")  # drain — completes generation

    beat = client.get(f"/api/lessons/{lesson_id}/beats/0")
    assert beat.status_code == 200
    assert beat.json()["index"] == 0

    missing = client.get(f"/api/lessons/{lesson_id}/beats/999")
    assert missing.status_code == 404


def test_unknown_lesson_id_returns_404() -> None:
    assert client.get("/api/lessons/lesson-does-not-exist").status_code == 404
    assert client.get("/api/lessons/lesson-does-not-exist/stream").status_code == 404
    assert client.get("/api/lessons/lesson-does-not-exist/beats/0").status_code == 404


def test_topic_length_capped() -> None:
    resp = client.post("/api/lessons", json={"topic": "x" * 301})
    assert resp.status_code == 422


def test_empty_topic_rejected() -> None:
    resp = client.post("/api/lessons", json={"topic": ""})
    assert resp.status_code == 422


def test_whitespace_only_topic_rejected() -> None:
    # A regression check: `min_length=1` alone passes on pure whitespace
    # (it's checked before stripping), which used to sail through and start
    # generating a lesson for an empty topic.
    for junk_topic in [" ", "\t\t\t", "   \n  "]:
        resp = client.post("/api/lessons", json={"topic": junk_topic})
        assert resp.status_code == 422, f"{junk_topic!r} should have been rejected"


def test_topic_is_trimmed_before_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IDEASCOPE_MOCK_GENERATION", "true")
    get_settings.cache_clear()

    resp = client.post("/api/lessons", json={"topic": "  the water cycle  "})
    assert resp.status_code == 202


def test_gibberish_topic_still_produces_a_schema_valid_lesson(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Junk input should never crash the pipeline — structured outputs make the
    # response schema-valid regardless of what the model does with a
    # nonsensical topic (docs/PLAN.md §7 prompt-injection resistance).
    monkeypatch.setenv("IDEASCOPE_MOCK_GENERATION", "true")
    get_settings.cache_clear()

    lesson_id = client.post(
        "/api/lessons", json={"topic": "asdkj qwoeiu !!! ??? 12345 xzcv"}
    ).json()["lessonId"]
    stream = client.get(f"/api/lessons/{lesson_id}/stream")
    assert stream.status_code == 200
    assert "lesson_complete" in stream.text


def test_rate_limit_returns_429_after_exceeding_the_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.rate_limit import limiter

    monkeypatch.setenv("IDEASCOPE_MOCK_GENERATION", "true")
    monkeypatch.setenv("IDEASCOPE_LESSONS_RATE_LIMIT", "2/hour")
    get_settings.cache_clear()
    limiter.reset()
    try:
        for _ in range(2):
            resp = client.post("/api/lessons", json={"topic": "how a sine wave works"})
            assert resp.status_code == 202
        blocked = client.post("/api/lessons", json={"topic": "how a sine wave works"})
        assert blocked.status_code == 429
    finally:
        limiter.reset()


def test_real_mode_without_key_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    # setenv to "", not delenv — see the comment in test_service.py's
    # equivalent test: delenv alone doesn't stop a real key in backend/.env
    # from leaking through as a lower-priority Settings source.
    monkeypatch.setenv("IDEASCOPE_ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("IDEASCOPE_MOCK_GENERATION", "false")
    get_settings.cache_clear()

    resp = client.post("/api/lessons", json={"topic": "entropy"})
    assert resp.status_code == 503
    assert "API key" in resp.json()["detail"]
