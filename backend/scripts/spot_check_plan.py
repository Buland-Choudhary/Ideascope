"""Manual spot-check for the live plan stage (docs/PLAN.md Phase 3 exit criterion).

Runs the real Claude plan call across a varied topic set and reports beat
counts, bands, and primitive/engine tagging so a human can eyeball quality.
Requires a real IDEASCOPE_ANTHROPIC_API_KEY / ANTHROPIC_API_KEY.

Run:  cd backend && uv run python scripts/spot_check_plan.py
"""

import time

from anthropic import Anthropic

from app.config import get_settings
from app.generation.plan import PlanGenerationError, generate_plan
from app.models import BEAT_BANDS, Difficulty, Duration, LessonParams, Tone

TOPICS: list[tuple[str, LessonParams]] = [
    ("how a sine wave works", LessonParams(duration=Duration.SHORT)),
    ("the water cycle", LessonParams(duration=Duration.SHORT)),
    ("how binary search works", LessonParams(duration=Duration.MEDIUM)),
    ("what compound interest is", LessonParams(duration=Duration.MEDIUM)),
    ("photosynthesis", LessonParams(duration=Duration.MEDIUM)),
    ("supply and demand", LessonParams(duration=Duration.MEDIUM, tone=Tone.PLAYFUL)),
    (
        "how neural networks learn (backpropagation)",
        LessonParams(duration=Duration.LONG, difficulty=Difficulty.ADVANCED),
    ),
    ("what entropy means", LessonParams(duration=Duration.MEDIUM)),
    ("how a bill becomes a law", LessonParams(duration=Duration.SHORT)),
    ("the trolley problem", LessonParams(duration=Duration.SHORT, tone=Tone.NEUTRAL)),
]


def main() -> None:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise SystemExit("No Anthropic API key configured — set IDEASCOPE_ANTHROPIC_API_KEY.")

    client = Anthropic(api_key=settings.anthropic_api_key)
    results = []

    for topic, params in TOPICS:
        lo, hi = BEAT_BANDS[params.duration]
        start = time.monotonic()
        try:
            plan = generate_plan(client, settings, topic=topic, params=params)
            elapsed = time.monotonic() - start
            in_band = lo <= len(plan.beats) <= hi
            print(
                f"{'OK ' if in_band else 'BAND'} [{elapsed:5.1f}s] "
                f"({params.duration.value:6s} {lo}-{hi}, got {len(plan.beats)}) {topic!r}"
            )
            print(f"       title: {plan.title}")
            primitives = [b.primitive.value for b in plan.beats]
            engines = [b.engine.value for b in plan.beats]
            print(f"       primitives: {primitives}")
            print(f"       engines:    {engines}")
            results.append((topic, True, in_band, len(plan.beats)))
        except PlanGenerationError as exc:
            elapsed = time.monotonic() - start
            print(f"FAIL [{elapsed:5.1f}s] {topic!r}: {exc}")
            results.append((topic, False, False, 0))

    ok_count = sum(1 for _, ok, _, _ in results if ok)
    band_count = sum(1 for _, _, in_band, _ in results if in_band)
    print(
        f"\n{ok_count}/{len(results)} succeeded, {band_count}/{len(results)} in-band on first pass "
        "(retries happen inside generate_plan and aren't visible here)"
    )


if __name__ == "__main__":
    main()
