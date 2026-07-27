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

from app.models import Beat, Lesson, LessonUsage, UsageBreakdownEntry
from app.observability import estimate_cost_usd

_DEFAULT_TTL_SECONDS = 2 * 60 * 60  # 2 hours (docs/PLAN.md §5.3)

GenerationStatus = Literal["generating", "complete", "failed"]


@dataclass
class LessonEvent:
    seq: int
    event: str
    data: dict[str, Any]


@dataclass
class _UsageRecord:
    stage: str
    model: str
    input_tokens: int
    output_tokens: int


class LessonState:
    def __init__(self, lesson_id: str) -> None:
        self.lesson_id = lesson_id
        self.status: GenerationStatus = "generating"
        self.error: str | None = None
        self.lesson: Lesson | None = None
        self.created_at = time.monotonic()
        self._lock = threading.Lock()
        self._events: list[LessonEvent] = []
        self._usage: list[_UsageRecord] = []

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
            # Kept sorted by index rather than plain arrival order: concurrent
            # generation (docs/PLAN.md §5.2) can finish beats out of order, and
            # a complete lesson's ``beats`` list needs index-order for
            # ``Lesson.check_beat_indices`` (app/models/lesson.py) to accept
            # it once every beat has arrived.
            beats = sorted([*self.lesson.beats, beat], key=lambda b: b.index)
            self.lesson = self.lesson.model_copy(update={"beats": beats})
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
        self._append("lesson_failed", self._add_usage_if_any({"error": error}))

    def complete(self) -> None:
        with self._lock:
            if self.status == "generating":
                self.status = "complete"
        self._append("lesson_complete", self._add_usage_if_any({"lessonId": self.lesson_id}))

    def events_since(self, seq: int) -> list[LessonEvent]:
        with self._lock:
            return list(self._events[seq:])

    def record_usage(
        self, *, stage: str, model: str, input_tokens: int, output_tokens: int
    ) -> None:
        """Record one real Anthropic call's token usage (docs cost-transparency
        note). Called from worker threads — one per concurrently in-flight beat
        when generation is parallelized (see ``app/generation/orchestrator.py``)
        — so this, like every other mutation here, is lock-guarded.
        """
        with self._lock:
            self._usage.append(_UsageRecord(stage, model, input_tokens, output_tokens))

    def usage_summary(self) -> LessonUsage:
        """Aggregate every recorded call into per-(stage, model) totals plus a
        grand total and estimated cost, for the after-generation cost report.
        """
        with self._lock:
            records = list(self._usage)

        buckets: dict[tuple[str, str], dict[str, int]] = {}
        for r in records:
            bucket = buckets.setdefault(
                (r.stage, r.model), {"calls": 0, "input_tokens": 0, "output_tokens": 0}
            )
            bucket["calls"] += 1
            bucket["input_tokens"] += r.input_tokens
            bucket["output_tokens"] += r.output_tokens

        breakdown = [
            UsageBreakdownEntry(
                stage=stage,
                model=model,
                calls=b["calls"],
                input_tokens=b["input_tokens"],
                output_tokens=b["output_tokens"],
                cost_usd=round(estimate_cost_usd(model, b["input_tokens"], b["output_tokens"]), 6),
            )
            for (stage, model), b in buckets.items()
        ]
        total_input = sum(b.input_tokens for b in breakdown)
        total_output = sum(b.output_tokens for b in breakdown)
        total_cost = sum(b.cost_usd for b in breakdown)
        return LessonUsage(
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=round(total_cost, 6),
            breakdown=breakdown,
        )

    def _add_usage_if_any(self, payload: dict[str, Any]) -> dict[str, Any]:
        usage = self.usage_summary()
        if usage.input_tokens or usage.output_tokens:
            payload["usage"] = usage.model_dump(mode="json", by_alias=True)
        return payload


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
