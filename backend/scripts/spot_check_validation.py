"""Manual spot-check for the live Phase-5 validation pipeline (docs/PLAN.md
§11 exit criterion: beats are render-checked, auto-fixed, and vision-critiqued
— or gracefully degraded — before being returned).

Runs full real-mode `generate_lesson` (plan + beats + validation) for a small,
cost-bounded topic set and reports each beat's final status (ready/degraded),
whether auto-fix or critique-triggered regeneration fired, and — via a
`ideascope.trace` log collector, same technique as spot_check_beats.py — the
real token usage and estimated cost across every stage (plan, beat, auto_fix,
critique).

Requires a real IDEASCOPE_ANTHROPIC_API_KEY / ANTHROPIC_API_KEY.

Run:  cd backend && uv run python scripts/spot_check_validation.py
"""

import json
import logging
import time
from typing import Any

from app.config import get_settings
from app.generation.service import generate_lesson
from app.models import Duration, LessonParams

# Short duration bounds cost/time (3-5 beats). Kept to a couple of topics —
# this run pays for real vision-critique calls on top of plan+beat.
TOPICS = [
    "how a rainbow forms",
    "the water cycle",
]

PRICING_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-opus-4-8": {"input": 5.0, "output": 25.0},
    "claude-sonnet-5": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
}


class _TraceCollector(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.records: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append(json.loads(record.getMessage()))
        except (TypeError, ValueError):
            pass


def _summarize_cost(records: list[dict[str, Any]], settings: Any) -> None:
    model_by_stage = {
        "plan": settings.plan_model,
        "beat": settings.beat_model,
        "auto_fix": settings.auto_fix_model,
        "critique": settings.critique_model,
    }
    total_in = total_out = 0
    total_cost = 0.0
    per_stage: dict[str, dict[str, int]] = {}

    for r in records:
        stage = r.get("stage")
        in_tok = r.get("input_tokens") or 0
        out_tok = r.get("output_tokens") or 0
        if in_tok == 0 and out_tok == 0:
            continue
        total_in += in_tok
        total_out += out_tok
        model = model_by_stage.get(stage, "claude-opus-4-8")
        rates = PRICING_PER_MTOK.get(model, PRICING_PER_MTOK["claude-opus-4-8"])
        total_cost += (in_tok / 1_000_000) * rates["input"] + (out_tok / 1_000_000) * rates[
            "output"
        ]
        bucket = per_stage.setdefault(stage, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
        bucket["calls"] += 1
        bucket["input_tokens"] += in_tok
        bucket["output_tokens"] += out_tok

    print("\n--- token usage / cost (this run) ---")
    for stage, b in per_stage.items():
        calls, in_tok, out_tok = b["calls"], b["input_tokens"], b["output_tokens"]
        print(f"  {stage:9s}: {calls:3d} calls, {in_tok:6d} in / {out_tok:6d} out")
    print(f"  TOTAL    : {total_in} input tokens, {total_out} output tokens")
    print(f"  Estimated cost: ${total_cost:.4f}")


def main() -> None:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise SystemExit("No Anthropic API key configured — set IDEASCOPE_ANTHROPIC_API_KEY.")

    collector = _TraceCollector()
    trace_logger = logging.getLogger("ideascope.trace")
    trace_logger.setLevel(logging.INFO)
    trace_logger.addHandler(collector)

    for topic in TOPICS:
        params = LessonParams(duration=Duration.SHORT)
        start = time.monotonic()
        lesson = generate_lesson(settings, topic=topic, params=params)
        elapsed = time.monotonic() - start

        print(f"\n=== {topic!r} ({elapsed:.1f}s, {len(lesson.beats)} beats) ===")
        print(f"    title: {lesson.outline.title}")
        for beat in lesson.beats:
            v = beat.validation
            extra = ""
            if v is not None:
                extra = f" auto_fix={v.auto_fix_attempts} critique_pass={v.critique_pass}" + (
                    f" feedback={v.critique_feedback!r}" if v.critique_feedback else ""
                )
            print(
                f"    beat {beat.index} [{beat.primitive.value}/{beat.engine.value}]: "
                f"{beat.status.value}{extra}"
            )

    _summarize_cost(collector.records, settings)


if __name__ == "__main__":
    main()
