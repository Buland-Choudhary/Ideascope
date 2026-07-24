"""``LessonState``/``LessonStore`` (docs/PLAN.md §5.3): an in-memory,
single-process store mapping ``lessonId -> LessonState``, TTL-evicted. This is
an explicit MVP scaling limitation — no horizontal scaling, state lost on
restart/deploy — documented and accepted (a Redis-backed store is the
drop-in fix if multi-instance deployment is ever needed).

A ``LessonState`` is written by the background generation worker (a plain
thread, since the whole Anthropic/Playwright pipeline is synchronous — see
``app/generation/orchestrator.py``) and read by the async SSE endpoint. It
keeps an append-only, replayable event log rather than pushing over a
cross-thread queue: the event loop just polls ``events_since`` on an interval,
which is simpler than wiring real cross-thread async notification and makes
"a client reconnects mid-generation" trivial (replay from event 0). A
``threading.Lock`` guards every read/write of the mutable fields.
"""

import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from app.models import Beat, Lesson

_DEFAULT_TTL_SECONDS = 2 * 60 * 60  # 2 hours (docs/PLAN.md §5.3)

GenerationStatus = Literal["generating", "complete", "failed"]


@dataclass
class LessonEvent:
    seq: int
    event: str
    data: dict[str, Any]


class LessonState:
    def __init__(self, lesson_id: str) -> None:
        self.lesson_id = lesson_id
        self.status: GenerationStatus = "generating"
        self.error: str | None = None
        self.lesson: Lesson | None = None
        self.created_at = time.monotonic()
        self._lock = threading.Lock()
        self._events: list[LessonEvent] = []

    def _append(self, event: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._events.append(LessonEvent(seq=len(self._events), event=event, data=data))

    def set_lesson(self, lesson: Lesson) -> None:
        """Record the freshly-planned lesson shell (outline + no beats yet)."""
        with self._lock:
            self.lesson = lesson
        self._append(
            "outline_ready",
            {
                "lessonId": lesson.id,
                "outline": lesson.outline.model_dump(mode="json", by_alias=True),
            },
        )

    def add_beat(self, beat: Beat) -> None:
        with self._lock:
            assert self.lesson is not None, "set_lesson must be called before add_beat"
            self.lesson = self.lesson.model_copy(update={"beats": [*self.lesson.beats, beat]})
        self._append(
            "beat_ready",
            {"index": beat.index, "beat": beat.model_dump(mode="json", by_alias=True)},
        )

    def fail_beat(self, index: int, error: str) -> None:
        """A single beat crashed in a way even graceful degradation couldn't
        absorb (unexpected bug, not a generation-quality failure) — logged and
        skipped so the rest of the lesson still streams.
        """
        self._append("beat_failed", {"index": index, "error": error})

    def fail(self, error: str) -> None:
        """The lesson itself never got an outline (e.g. the plan call failed) —
        nothing to gracefully degrade, so the whole lesson fails.
        """
        with self._lock:
            self.status = "failed"
            self.error = error
        self._append("lesson_failed", {"error": error})

    def complete(self) -> None:
        with self._lock:
            if self.status == "generating":
                self.status = "complete"
        self._append("lesson_complete", {"lessonId": self.lesson_id})

    def events_since(self, seq: int) -> list[LessonEvent]:
        with self._lock:
            return list(self._events[seq:])


class LessonStore:
    def __init__(self, ttl_seconds: float = _DEFAULT_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._states: dict[str, LessonState] = {}

    def create(self, lesson_id: str | None = None) -> LessonState:
        self._sweep()
        lesson_id = lesson_id or f"lesson-{uuid.uuid4().hex[:12]}"
        state = LessonState(lesson_id)
        with self._lock:
            self._states[lesson_id] = state
        return state

    def get(self, lesson_id: str) -> LessonState | None:
        self._sweep()
        with self._lock:
            return self._states.get(lesson_id)

    def _sweep(self) -> None:
        now = time.monotonic()
        with self._lock:
            expired = [lid for lid, s in self._states.items() if now - s.created_at > self._ttl]
            for lid in expired:
                del self._states[lid]


_store = LessonStore()


def get_lesson_store() -> LessonStore:
    return _store
