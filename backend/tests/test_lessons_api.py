import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    # Settings are cached; clear so per-test env changes take effect.
    get_settings.cache_clear()


def test_mock_mode_returns_playable_lesson(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IDEASCOPE_MOCK_GENERATION", "true")
    get_settings.cache_clear()

    resp = client.post("/api/lessons", json={"topic": "how a sine wave works"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["beats"], "mock lesson should have beats"
    # Mock fixtures are complete and playable: every beat has scene code + ready.
    for beat in body["beats"]:
        assert beat["scene"]["code"]
        assert beat["status"] == "ready"


def test_topic_length_capped() -> None:
    resp = client.post("/api/lessons", json={"topic": "x" * 301})
    assert resp.status_code == 422


def test_empty_topic_rejected() -> None:
    resp = client.post("/api/lessons", json={"topic": ""})
    assert resp.status_code == 422


def test_real_mode_without_key_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IDEASCOPE_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("IDEASCOPE_MOCK_GENERATION", "false")
    get_settings.cache_clear()

    resp = client.post("/api/lessons", json={"topic": "entropy"})
    assert resp.status_code == 503
    assert "API key" in resp.json()["detail"]
