from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from typing import Annotated

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = ""
    admin_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)
    database_path: Path = ROOT_DIR / "bot.db"
    data_path: Path = ROOT_DIR / "legal_bot.json"
    cache_dir: Path = ROOT_DIR / "cache"
    search_high_threshold: float = Field(default=0.78, ge=0, le=1)
    search_low_threshold: float = Field(default=0.35, ge=0, le=1)
    search_top_k: int = Field(default=5, ge=1, le=20)
    throttle_messages_per_minute: int = Field(default=12, ge=1)
    log_retention_days: int = Field(default=90, ge=1)
    use_llm: bool = False
    llm_provider: str = "none"
    openai_api_key: str = ""
    openai_embed_model: str = "text-embedding-3-small"
    openai_chat_model: str = "gpt-4o-mini"
    openai_daily_token_limit: int = Field(default=100_000, ge=0)
    openai_daily_cost_limit_usd: float = Field(default=5, ge=0)
    openai_cost_per_1k_tokens_usd: float = Field(default=0.001, ge=0)
    webhook_url: str = ""
    webhook_path: str = "/telegram/webhook"
    webhook_secret: str = ""
    host: str = "0.0.0.0"
    port: int = Field(default=8080, ge=1, le=65535)
    voice_enabled: bool = False

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, value: str) -> str:
        if value not in {"openai", "none"}:
            raise ValueError("LLM_PROVIDER must be 'openai' or 'none'")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
