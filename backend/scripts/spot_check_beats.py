"""Manual spot-check for the live per-beat generation pipeline (Phase 4 exit
criterion — docs/PLAN.md §11: "generated beats render (even if not yet
validated)").

Runs full real-mode generation (plan + all beats) for a varied topic set, then
verifies every generated scene module is syntactically valid JavaScript via
`node --check`. This is the same technique used to verify the Phase-1 hand-
authored fixtures, now applied to LLM-generated code. Requires a real
IDEASCOPE_ANTHROPIC_API_KEY / ANTHROPIC_API_KEY and Node on PATH.

Run:  cd backend && uv run python scripts/spot_check_beats.py
"""

import subprocess
import tempfile
import time
from pathlib import Path

from anthropic import Anthropic

from app.config import get_settings
from app.generation.beat import BeatGenerationError
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


def main() -> None:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise SystemExit("No Anthropic API key configured — set IDEASCOPE_ANTHROPIC_API_KEY.")

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
            from app.generation.beat import generate_beat_scene

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


if __name__ == "__main__":
    main()
