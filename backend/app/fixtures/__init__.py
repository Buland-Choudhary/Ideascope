"""Hand-authored fixture lessons.

The ``*.json`` files here are the runtime artifact (built by
``scripts/build_fixtures.py``). They back mock generation mode (docs/PLAN.md §1)
and the Phase-2 static player. Loading re-validates against the lesson spec, so a
hand-edited or stale fixture fails loudly.
"""

import json
from pathlib import Path

from app.models import Lesson

_FIXTURES_DIR = Path(__file__).resolve().parent


def load_fixture(name: str) -> Lesson:
    """Load and validate a single fixture by file stem (e.g. ``"sine_wave"``)."""
    path = _FIXTURES_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"No fixture named {name!r} in {_FIXTURES_DIR}")
    return Lesson.model_validate(json.loads(path.read_text()))


def load_all_fixtures() -> dict[str, Lesson]:
    """Load and validate every fixture, keyed by file stem."""
    return {path.stem: load_fixture(path.stem) for path in sorted(_FIXTURES_DIR.glob("*.json"))}
