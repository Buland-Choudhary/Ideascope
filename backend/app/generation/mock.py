"""Mock generation mode (docs/PLAN.md §1).

Serves the hand-authored fixture lessons through the real request surface so the
frontend, E2E tests, and demos of the player itself cost $0 and run offline. The
returned lessons are complete and playable (unlike the Phase-3 real path, which
only plans — scene generation is Phase 4).
"""

from app.fixtures import load_all_fixtures
from app.models import Lesson


def mock_lesson(topic: str) -> Lesson:
    """Pick a fixture for the topic — keyword match, else deterministic fallback."""
    fixtures = load_all_fixtures()
    lowered = topic.lower()

    for fixture in fixtures.values():
        if any(word in lowered for word in _keywords(fixture)):
            return fixture

    # Deterministic fallback so the same topic always maps to the same fixture.
    ordered = list(fixtures.values())
    return ordered[hash(topic) % len(ordered)]


def _keywords(lesson: Lesson) -> list[str]:
    return [w for w in lesson.topic.lower().split() if len(w) > 3]
