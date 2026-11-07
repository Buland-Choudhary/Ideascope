"""Keep tests hermetic: a developer's backend/.env or shell IDEASCOPE_* vars
must not change Settings defaults the tests rely on (e.g. a local
IDEASCOPE_SKIP_VALIDATION=true flips the orchestrator's sequential path)."""

import os
from collections.abc import Iterator

import pytest

from app.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _isolate_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for name in list(os.environ):
        if name.startswith("IDEASCOPE_") or name == "ANTHROPIC_API_KEY":
            monkeypatch.delenv(name)
    # get_settings() is lru_cached and first runs at import (app.main's
    # create_app), before this fixture — drop that environment-read copy.
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
