import pytest
from fastapi.testclient import TestClient

from app import __version__
from app.main import app

client = TestClient(app)


def test_health_ok() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "ideascope-backend"
    assert body["version"] == __version__
    assert body["generation"] == "real"


def test_health_reports_mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IDEASCOPE_MOCK_GENERATION", "true")
    assert client.get("/api/health").json()["generation"] == "mock"
