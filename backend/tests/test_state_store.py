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


def test_usage_summary_is_empty_before_any_recorded_call() -> None:
    store = LessonStore()
    state = store.create()
    usage = state.usage_summary()
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    assert usage.cost_usd == 0
    assert usage.breakdown == []


def test_record_usage_aggregates_by_stage_and_model() -> None:
    store = LessonStore()
    state = store.create()

    state.record_usage(stage="plan", model="claude-opus-4-8", input_tokens=1000, output_tokens=500)
    state.record_usage(stage="beat", model="claude-sonnet-5", input_tokens=2000, output_tokens=1000)
    # A second beat call on the same model — should fold into the same bucket.
    state.record_usage(stage="beat", model="claude-sonnet-5", input_tokens=500, output_tokens=250)

    usage = state.usage_summary()
    assert usage.input_tokens == 3500
    assert usage.output_tokens == 1750

    by_stage = {(b.stage, b.model): b for b in usage.breakdown}
    plan_bucket = by_stage[("plan", "claude-opus-4-8")]
    assert plan_bucket.calls == 1
    assert plan_bucket.input_tokens == 1000
    assert plan_bucket.output_tokens == 500
    # opus: $5/$25 per MTok -> 1000/1e6*5 + 500/1e6*25 = 0.005 + 0.0125 = 0.0175
    assert plan_bucket.cost_usd == 0.0175

    beat_bucket = by_stage[("beat", "claude-sonnet-5")]
    assert beat_bucket.calls == 2
    assert beat_bucket.input_tokens == 2500
    assert beat_bucket.output_tokens == 1250

    assert usage.cost_usd == round(plan_bucket.cost_usd + beat_bucket.cost_usd, 6)


def test_record_usage_is_thread_safe_under_concurrent_writers() -> None:
    import threading

    store = LessonStore()
    state = store.create()

    def _record_many() -> None:
        for _ in range(200):
            state.record_usage(
                stage="beat", model="claude-sonnet-5", input_tokens=1, output_tokens=1
            )

    threads = [threading.Thread(target=_record_many) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    usage = state.usage_summary()
    assert usage.input_tokens == 1000
    assert usage.output_tokens == 1000


def test_complete_includes_usage_in_lesson_complete_event_when_present() -> None:
    store = LessonStore()
    state = store.create()
    state.set_lesson(_outline_lesson(state.lesson_id))
    state.record_usage(stage="plan", model="claude-opus-4-8", input_tokens=10, output_tokens=10)
    state.complete()

    complete_event = next(e for e in state.events_since(0) if e.event == "lesson_complete")
    assert "usage" in complete_event.data
    assert complete_event.data["usage"]["inputTokens"] == 10


def test_complete_omits_usage_when_nothing_was_recorded() -> None:
    # Exact-equality regression check (test_lessons_api.py's mock-mode test
    # relies on this shape too): no real API calls happened (e.g. mock mode),
    # so the payload stays exactly {"lessonId": ...} with no extra key.
    store = LessonStore()
    state = store.create()
    state.complete()

    complete_event = next(e for e in state.events_since(0) if e.event == "lesson_complete")
    assert complete_event.data == {"lessonId": state.lesson_id}
