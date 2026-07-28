"""Per-model $/MTok pricing for the generation cost report (surfaced to the
learner after each lesson generates — see ``LessonState.usage_summary`` in
``app/state/store.py``). Hand-maintained, approximate figures; good enough
for a "here's roughly what that lesson cost" estimate, not a substitute for
the real Anthropic invoice.
"""

PRICING_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-fable-5": {"input": 10.0, "output": 50.0},
    "claude-opus-5": {"input": 5.0, "output": 25.0},
    "claude-opus-4-8": {"input": 5.0, "output": 25.0},
    "claude-sonnet-5": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
}

# Fallback for a model that isn't in the table (e.g. one only added upstream
# after this list was last updated) — assume the most expensive tier rather
# than silently under-reporting cost.
_FALLBACK_MODEL = "claude-opus-4-8"


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = PRICING_PER_MTOK.get(model, PRICING_PER_MTOK[_FALLBACK_MODEL])
    return (input_tokens / 1_000_000) * rates["input"] + (output_tokens / 1_000_000) * rates[
        "output"
    ]
