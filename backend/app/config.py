"""Runtime configuration, loaded from environment variables.

Keeps all env access in one place so the rest of the app depends on a typed
settings object rather than scattered ``os.environ`` reads. See docs/PLAN.md §5.
"""

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    beat_model: str = "claude-opus-4-8"
    auto_fix_model: str = "claude-haiku-4-5"
    critique_model: str = "claude-opus-4-8"

    # Validation pipeline (docs/PLAN.md §5.2, §5.4).
    render_timeout_ms: int = 5000
    max_concurrent_renders: int = 3

    # When true, the generation pipeline serves fixture lessons instead of
    # calling Anthropic (docs/PLAN.md §1 "Mock generation mode"). Wired up in
    # Phase 3; declared here so the surface is stable.
    mock_generation: bool = False

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
