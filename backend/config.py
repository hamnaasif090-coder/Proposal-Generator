"""
config.py — Centralised settings loader.

All environment variables are validated at startup via Pydantic Settings.
Import `settings` anywhere in the codebase; never read os.environ directly.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide configuration loaded from .env (or real env vars)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Anthropic ──────────────────────────────────────────────────────────────
    anthropic_api_key: str = Field(..., description="Anthropic secret key")
    anthropic_model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Claude model identifier",
    )
    anthropic_max_tokens: int = Field(default=4096, ge=256, le=8192)

    # ── Application ────────────────────────────────────────────────────────────
    app_name: str = Field(default="AI Proposal Generator")
    app_version: str = Field(default="1.0.0")
    environment: Literal["development", "staging", "production"] = Field(
        default="development"
    )
    debug: bool = Field(default=False)

    # ── Backend server ─────────────────────────────────────────────────────────
    backend_host: str = Field(default="0.0.0.0")
    backend_port: int = Field(default=8000, ge=1024, le=65535)
    allowed_origins: list[str] = Field(
        default=["http://localhost:8501", "http://127.0.0.1:8501"]
    )

    # ── Database ───────────────────────────────────────────────────────────────
    database_url: str = Field(default="sqlite:///./proposal_generator.db")

    # ── File paths ─────────────────────────────────────────────────────────────
    prompts_dir: Path = Field(default=Path("prompts"))
    generated_dir: Path = Field(default=Path("generated"))
    logs_dir: Path = Field(default=Path("logs"))

    # ── Logging ────────────────────────────────────────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO"
    )
    log_format: Literal["json", "text"] = Field(default="json")

    # ── Proposal generation ────────────────────────────────────────────────────
    default_tone: Literal["professional", "friendly", "technical", "executive"] = Field(
        default="professional"
    )
    generation_timeout_seconds: int = Field(default=120, ge=10, le=600)
    max_concurrent_generations: int = Field(default=5, ge=1, le=20)

    # ── Computed properties ────────────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @field_validator("prompts_dir", "generated_dir", "logs_dir", mode="before")
    @classmethod
    def coerce_path(cls, v: object) -> Path:
        return Path(v)  # type: ignore[arg-type]

    def ensure_directories(self) -> None:
        """Create required runtime directories if they don't exist."""
        for directory in (self.generated_dir, self.logs_dir):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings singleton.

    Using lru_cache means .env is parsed exactly once per process.
    Call ``get_settings.cache_clear()`` in tests to reload.
    """
    s = Settings()  # type: ignore[call-arg]
    s.ensure_directories()
    return s


# Module-level convenience alias
settings: Settings = get_settings()
