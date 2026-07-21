"""Runtime configuration, loaded from environment variables.

Keeps all env access in one place so the rest of the app depends on a typed
settings object rather than scattered ``os.environ`` reads. See docs/PLAN.md §5.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IDEASCOPE_", env_file=".env")

    # Anthropic API key is server-side only and never shipped to the client
    # (docs/PLAN.md §7). Optional at this phase — no generation calls exist yet.
    anthropic_api_key: str | None = None

    # When true, the generation pipeline serves fixture lessons instead of
    # calling Anthropic (docs/PLAN.md §1 "Mock generation mode"). Wired up in
    # Phase 3; declared here so the surface is stable.
    mock_generation: bool = False

    # CORS allowlist for the frontend origin(s) (docs/PLAN.md §13).
    # Comma-separated in the env var; defaults to local Vite dev.
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
