"""Manual spot-check for the live per-beat generation pipeline (Phase 4 exit
criterion — docs/PLAN.md §11: "generated beats render (even if not yet
validated)").

Runs full real-mode generation (plan + all beats) for a varied topic set, then
verifies every generated scene module is syntactically valid JavaScript via
`node --check`. This is the same technique used to verify the Phase-1 hand-
authored fixtures, now applied to LLM-generated code. Requires a real
IDEASCOPE_ANTHROPIC_API_KEY / ANTHROPIC_API_KEY and Node on PATH.

Also attaches a handler to the "ideascope.trace" logger (docs/PLAN.md §5.5) to
tally real token usage and an estimated cost, using the $/MTok figures from
§14 — so a run of this script reports exactly what it spent.

Run:  cd backend && uv run python scripts/spot_check_beats.py
"""

import json
import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from anthropic import Anthropic

from app.config import get_settings
from app.generation.beat import BeatGenerationError, generate_beat_scene
from app.generation.plan import PlanGenerationError, generate_plan
from app.generation.service import _lesson_from_plan
from app.models import Duration, LessonParams

# Deliberately distinct from the Phase-1 fixture topics (sine wave, water
# cycle) and the Phase-3 plan spot-check topics, so this exercises fresh
# generations. All "short" to bound cost/time (3-5 beats each).
TOPICS = [
    "the phases of the moon",
    "how a rainbow forms",
    "the pythagorean theorem",
    "how vaccines train the immune system",
    "newton's second law of motion",
]

# $ per million tokens (docs/PLAN.md §14). Only the models this script can
# select (plan_model/beat_model) need entries.
PRICING_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-opus-4-8": {"input": 5.0, "output": 25.0},
    "claude-sonnet-5": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
}


class _TraceCollector(logging.Handler):
    """Collects every generation-trace record emitted during this run."""

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.records: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append(json.loads(record.getMessage()))
        except (TypeError, ValueError):
            pass


def _node_check(code: str) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as tmp:
        tmp.write(code)
        path = Path(tmp.name)
    try:
        result = subprocess.run(
            ["node", "--check", str(path)], capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0, result.stderr
    finally:
        path.unlink(missing_ok=True)


def _summarize_cost(records: list[dict[str, Any]], settings: Any) -> None:
    model_by_stage = {"plan": settings.plan_model, "beat": settings.beat_model}
    total_in = total_out = 0
    total_cost = 0.0
    per_stage: dict[str, dict[str, int]] = {}

    for r in records:
        stage = r.get("stage")
        in_tok = r.get("input_tokens") or 0
        out_tok = r.get("output_tokens") or 0
        if in_tok == 0 and out_tok == 0:
            continue  # failed-before-response attempts carry no usage
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
        print(f"  {stage:6s}: {calls:3d} calls, {in_tok:6d} in / {out_tok:6d} out")
    print(f"  TOTAL : {total_in} input tokens, {total_out} output tokens")
    print(f"  Estimated cost: ${total_cost:.4f}")


def main() -> None:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise SystemExit("No Anthropic API key configured — set IDEASCOPE_ANTHROPIC_API_KEY.")

    collector = _TraceCollector()
    trace_logger = logging.getLogger("ideascope.trace")
    trace_logger.setLevel(logging.INFO)
    trace_logger.addHandler(collector)

    client = Anthropic(api_key=settings.anthropic_api_key)
    total_beats = 0
    total_valid = 0
    total_topics_ok = 0

    for topic in TOPICS:
        params = LessonParams(duration=Duration.SHORT)
        start = time.monotonic()
        try:
            plan = generate_plan(client, settings, topic=topic, params=params)
            lesson = _lesson_from_plan(topic, params, plan)
            for i, (beat_plan, beat) in enumerate(zip(plan.beats, lesson.beats, strict=True)):
                code = generate_beat_scene(
                    client, settings, beat=beat_plan, lesson_id=lesson.id, beat_index=i
                )
                beat.scene.code = code
        except (PlanGenerationError, BeatGenerationError) as exc:
            print(f"FAIL {topic!r}: {exc}")
            continue

        elapsed = time.monotonic() - start
        print(f"\n=== {topic!r} ({elapsed:.1f}s, {len(lesson.beats)} beats) ===")
        print(f"    title: {lesson.outline.title}")

        topic_all_valid = True
        for beat in lesson.beats:
            ok, stderr = _node_check(beat.scene.code)
            total_beats += 1
            total_valid += 1 if ok else 0
            topic_all_valid = topic_all_valid and ok
            status = "valid JS" if ok else "SYNTAX ERROR"
            print(f"    beat {beat.index} [{beat.primitive.value}/{beat.engine.value}]: {status}")
            if not ok:
                print(f"      {stderr.strip()}")
        total_topics_ok += 1 if topic_all_valid else 0

    print(
        f"\n{total_topics_ok}/{len(TOPICS)} topics fully valid, "
        f"{total_valid}/{total_beats} individual beats valid JS"
    )
    _summarize_cost(collector.records, settings)


if __name__ == "__main__":
    main()
