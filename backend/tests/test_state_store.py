"""Unit tests for the in-memory LessonState/LessonStore (docs/PLAN.md §5.3):
event log ordering/replay, the lesson-shell mutation helpers, and TTL eviction.
"""

import time

from app.models import (
    Beat,
    BeatStatus,
    Engine,
    Lesson,
    LessonParams,
    Narration,
    Outline,
    Primitive,
    Scene,
)
from app.state.store import LessonStore


def _outline_lesson(lesson_id: str) -> Lesson:
    return Lesson(
        id=lesson_id,
        topic="t",
        params=LessonParams(),
        outline=Outline(title="Title", summary="Summary", target_beat_count=1),
        beats=[],
    )


def _beat(index: int) -> Beat:
    return Beat(
        id=f"beat-{index}",
        index=index,
        intent="intent",
        primitive=Primitive.PLOT,
        engine=Engine.CANVAS,
        narration=Narration(text="n"),
        scene=Scene(code="export default (ctx) => { ctx.ready(); return {}; };"),
        status=BeatStatus.READY,
    )


def test_create_assigns_a_lesson_id_and_starts_generating() -> None:
    store = LessonStore()
    state = store.create()
    assert state.lesson_id.startswith("lesson-")
    assert state.status == "generating"
    assert state.lesson is None
    assert store.get(state.lesson_id) is state


def test_set_lesson_then_add_beat_builds_up_the_lesson_and_events() -> None:
    store = LessonStore()
    state = store.create()

    state.set_lesson(_outline_lesson(state.lesson_id))
    state.add_beat(_beat(0))
    state.complete()

    assert state.status == "complete"
    assert state.lesson is not None
    assert len(state.lesson.beats) == 1

    events = state.events_since(0)
    assert [e.event for e in events] == ["outline_ready", "beat_ready", "lesson_complete"]
    assert [e.seq for e in events] == [0, 1, 2]


def test_events_since_only_returns_new_events() -> None:
    store = LessonStore()
    state = store.create()
    state.set_lesson(_outline_lesson(state.lesson_id))

    first_batch = state.events_since(0)
    assert len(first_batch) == 1

    state.add_beat(_beat(0))
    second_batch = state.events_since(len(first_batch))
    assert [e.event for e in second_batch] == ["beat_ready"]

    # Replaying from 0 again (a reconnecting client) sees everything so far.
    assert [e.event for e in state.events_since(0)] == ["outline_ready", "beat_ready"]


def test_fail_marks_lesson_failed_with_error() -> None:
    store = LessonStore()
    state = store.create()
    state.fail("boom")
    assert state.status == "failed"
    assert state.error == "boom"
    assert [e.event for e in state.events_since(0)] == ["lesson_failed"]


def test_fail_beat_does_not_change_lesson_status() -> None:
    store = LessonStore()
    state = store.create()
    state.set_lesson(_outline_lesson(state.lesson_id))
    state.fail_beat(0, "unexpected crash")
    state.complete()

    assert state.status == "complete"
    assert [e.event for e in state.events_since(0)] == [
        "outline_ready",
        "beat_failed",
        "lesson_complete",
    ]


def test_ttl_eviction() -> None:
    store = LessonStore(ttl_seconds=0.01)
    state = store.create()
    lesson_id = state.lesson_id
    time.sleep(0.05)

    assert store.get(lesson_id) is None  # sweep runs on get()


def test_unexpired_lesson_is_not_evicted() -> None:
    store = LessonStore(ttl_seconds=60)
    state = store.create()
    assert store.get(state.lesson_id) is not None
