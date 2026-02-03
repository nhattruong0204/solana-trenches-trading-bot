"""Configuration management using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database configuration."""

    model_config = SettingsConfigDict(env_prefix="")

    url: str = Field(
        default="postgresql://postgres:password@localhost:5432/token_analysis",
        alias="DATABASE_URL",
    )
    pool_size: int = Field(default=10, alias="DATABASE_POOL_SIZE")
    max_overflow: int = Field(default=20, alias="DATABASE_MAX_OVERFLOW")


class TelegramSettings(BaseSettings):
    """Telegram bot and client configuration."""

    model_config = SettingsConfigDict(env_prefix="TELEGRAM_")

    # Bot API (for posting)
    bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    target_channel: str = Field(default="", alias="TELEGRAM_TARGET_CHANNEL")
    admin_users: list[int] = Field(default_factory=list, alias="TELEGRAM_ADMIN_USERS")

    # Client API (for monitoring)
    api_id: int = Field(default=0, alias="TELEGRAM_API_ID")
    api_hash: str = Field(default="", alias="TELEGRAM_API_HASH")
    session_name: str = Field(default="token_analyzer", alias="TELEGRAM_SESSION_NAME")

    @field_validator("admin_users", mode="before")
    @classmethod
    def parse_admin_users(cls, v: str | list) -> list[int]:
        if isinstance(v, list):
            return v
        if isinstance(v, str) and v:
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return []


class LLMSettings(BaseSettings):
    """LLM provider configuration."""

    model_config = SettingsConfigDict(env_prefix="")

    provider: Literal["anthropic", "openai"] = Field(
        default="anthropic", alias="LLM_PROVIDER"
    )
    model: str = Field(default="claude-sonnet-4-20250514", alias="LLM_MODEL")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    max_tokens: int = Field(default=2048, alias="LLM_MAX_TOKENS")
    temperature: float = Field(default=0.3, alias="LLM_TEMPERATURE")


class ChainSettings(BaseSettings):
    """Blockchain configuration."""

    model_config = SettingsConfigDict(env_prefix="BASE_")

    rpc_url: str = Field(default="https://mainnet.base.org", alias="BASE_RPC_URL")
    wss_url: str = Field(default="wss://mainnet.base.org", alias="BASE_WSS_URL")
    chain_id: int = Field(default=8453, alias="BASE_CHAIN_ID")


class TwitterSettings(BaseSettings):
    """Twitter/X API configuration."""

    model_config = SettingsConfigDict(env_prefix="TWITTER_")

    bearer_token: str = Field(default="", alias="TWITTER_BEARER_TOKEN")
    api_key: str = Field(default="", alias="TWITTER_API_KEY")
    api_secret: str = Field(default="", alias="TWITTER_API_SECRET")
    access_token: str = Field(default="", alias="TWITTER_ACCESS_TOKEN")
    access_secret: str = Field(default="", alias="TWITTER_ACCESS_SECRET")


class MoltbookSettings(BaseSettings):
    """Moltbook API configuration."""

    model_config = SettingsConfigDict(env_prefix="MOLTBOOK_")

    api_url: str = Field(default="https://moltbook.com/api", alias="MOLTBOOK_API_URL")
    poll_interval_seconds: int = Field(default=30, alias="MOLTBOOK_POLL_INTERVAL_SECONDS")


class AnalysisSettings(BaseSettings):
    """Analysis thresholds and configuration."""

    model_config = SettingsConfigDict(env_prefix="")

    min_liquidity_usd: float = Field(default=5000.0, alias="MIN_LIQUIDITY_USD")
    min_holder_count: int = Field(default=50, alias="MIN_HOLDER_COUNT")
    max_top_holder_percentage: float = Field(default=30.0, alias="MAX_TOP_HOLDER_PERCENTAGE")
    confidence_threshold: float = Field(default=0.7, alias="CONFIDENCE_THRESHOLD")

    # Human approval
    enable_human_approval: bool = Field(default=False, alias="ENABLE_HUMAN_APPROVAL")
    approval_timeout_seconds: int = Field(default=300, alias="APPROVAL_TIMEOUT_SECONDS")

    # Rate limiting
    max_analyses_per_hour: int = Field(default=60, alias="MAX_ANALYSES_PER_HOUR")
    cooldown_between_posts_seconds: int = Field(default=60, alias="COOLDOWN_BETWEEN_POSTS_SECONDS")


class PathSettings(BaseSettings):
    """File path configuration."""

    model_config = SettingsConfigDict(env_prefix="")

    data_dir: Path = Field(default=Path("data"), alias="DATA_DIR")
    log_file: Path = Field(default=Path("data/logs/token_analysis.log"), alias="LOG_FILE")
    state_file: Path = Field(default=Path("data/analysis_state.json"), alias="STATE_FILE")
    blacklist_file: Path = Field(default=Path("data/blacklist.json"), alias="BLACKLIST_FILE")


class Settings(BaseSettings):
    """Main settings container."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Nested settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    chain: ChainSettings = Field(default_factory=ChainSettings)
    twitter: TwitterSettings = Field(default_factory=TwitterSettings)
    moltbook: MoltbookSettings = Field(default_factory=MoltbookSettings)
    analysis: AnalysisSettings = Field(default_factory=AnalysisSettings)
    paths: PathSettings = Field(default_factory=PathSettings)

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    debug: bool = Field(default=False, alias="DEBUG")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
