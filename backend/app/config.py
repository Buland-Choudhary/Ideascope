"""Runtime configuration, loaded from environment variables.

Keeps all env access in one place so the rest of the app depends on a typed
settings object rather than scattered ``os.environ`` reads. See docs/PLAN.md §5.
"""

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Models a learner can pick for a lesson's plan+beat generation (docs/PLAN.md
# §14 cost-experimentation note) — deliberately an allowlist the app also
# prices elsewhere (app/observability/pricing.py), not an arbitrary passthrough
# string, so a request can't name an unpriced or unvetted model. Limited to
# models confirmed to support structured outputs (client.messages.parse, which
# every generation call in this app uses) per the claude-api skill's
# documentation — Opus 4.7/4.6 and Sonnet 4.6 are deliberately excluded even
# though they're current Anthropic models, since they're not on that confirmed
# list and every stage here (plan/beat/code-review/critique) depends on it.
ALLOWED_GENERATION_MODELS: list[str] = [
    "claude-fable-5",
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-sonnet-5",
    "claude-haiku-4-5",
]


class Settings(BaseSettings):
    # populate_by_name lets tests construct Settings(anthropic_api_key=...) by
    # field name even though the field also declares an env-var alias below.
    model_config = SettingsConfigDict(
        env_prefix="IDEASCOPE_", env_file=".env", populate_by_name=True
    )

    # Anthropic API key is server-side only and never shipped to the client
    # (docs/PLAN.md §7). Accepts either IDEASCOPE_ANTHROPIC_API_KEY or the
    # SDK-standard ANTHROPIC_API_KEY, so setting either works.
    anthropic_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("IDEASCOPE_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"),
    )

    # Model roles (docs/PLAN.md §1). Overridable via env for experiments.
    plan_model: str = "claude-opus-4-8"
    # Beat calls dominate per-lesson spend (long code-generation output, N per
    # lesson vs. one plan call) — claude-sonnet-5 cuts that ~40% (output-token
    # price is the bulk of the cost) vs. opus, still a strong coding model, so
    # this is the default cost lever with skip_validation on (docs/PLAN.md
    # Phase 10 note) and no auto-fix/critique net to catch a bad generation.
    # Set IDEASCOPE_BEAT_MODEL=claude-opus-4-8 to trade cost back for quality.
    beat_model: str = "claude-sonnet-5"
    auto_fix_model: str = "claude-haiku-4-5"
    critique_model: str = "claude-opus-4-8"

    # Validation pipeline (docs/PLAN.md §5.2, §5.4).
    render_timeout_ms: int = 5000
    max_concurrent_renders: int = 3

    # How many beats generate concurrently (app/generation/orchestrator.py).
    # Beats used to generate strictly one-at-a-time — each a ~15-25s Anthropic
    # call — so a lesson's Nth beat didn't even *start* until the (N-1)th
    # finished. Running several at once cuts wall-clock lesson time by
    # roughly this factor with zero cost change (same calls, same tokens) —
    # purely a latency win. Bounded to avoid hammering Anthropic's per-account
    # rate limits; the SDK's own retry/backoff (app/generation/retry.py)
    # absorbs transient 429s regardless.
    beat_generation_concurrency: int = 3

    # When true, the generation pipeline serves fixture lessons instead of
    # calling Anthropic (docs/PLAN.md §1 "Mock generation mode"). Wired up in
    # Phase 3; declared here so the surface is stable.
    mock_generation: bool = False

    # When true, real-mode generation skips the validation pipeline (render
    # check/auto-fix + vision critique, docs/PLAN.md §5.2 steps 3-5) and ships
    # each beat's generated code as-is. A deliberate, temporary cost/ops
    # trade-off (no Chromium needed, no vision-critique spend) — see
    # docs/PLAN.md's Phase 10 note for the rationale and what it gives up.
    # The pipeline code itself is untouched; this only skips calling it.
    skip_validation: bool = False

    # CORS allowlist for the frontend origin(s) (docs/PLAN.md §13).
    # Comma-separated in the env var; defaults to local Vite dev.
    cors_origins: str = "http://localhost:5173"

    # IP-based cap on lesson generation (docs/PLAN.md §5.4) — bounds worst-case
    # Anthropic spend from a single abusive client. A `slowapi`/`limits` rate
    # string, e.g. "20/hour".
    lessons_rate_limit: str = "20/hour"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
