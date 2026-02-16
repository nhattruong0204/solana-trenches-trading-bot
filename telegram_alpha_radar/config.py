"""Configuration module - loads settings from environment variables."""

import os
import logging
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelegramConfig:
    """Telegram MTProto client settings."""

    api_id: int = int(os.getenv("TELEGRAM_API_ID", "0"))
    api_hash: str = os.getenv("TELEGRAM_API_HASH", "")
    session_name: str = os.getenv("TELEGRAM_SESSION_NAME", "alpha_radar")
    phone: str = os.getenv("TELEGRAM_PHONE", "")


@dataclass(frozen=True)
class DatabaseConfig:
    """PostgreSQL connection settings."""

    host: str = os.getenv("DB_HOST", "localhost")
    port: int = int(os.getenv("DB_PORT", "5432"))
    user: str = os.getenv("DB_USER", "postgres")
    password: str = os.getenv("DB_PASSWORD", "")
    database: str = os.getenv("DB_NAME", "alpha_radar")
    min_pool_size: int = int(os.getenv("DB_MIN_POOL", "2"))
    max_pool_size: int = int(os.getenv("DB_MAX_POOL", "10"))

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )


@dataclass(frozen=True)
class TrendingConfig:
    """Trending detection thresholds."""

    window_minutes: int = int(os.getenv("WINDOW_MINUTES", "5"))
    min_mentions: int = int(os.getenv("MIN_MENTIONS", "3"))
    min_unique_chats: int = int(os.getenv("MIN_UNIQUE_CHATS", "2"))
    alert_cooldown_minutes: int = int(os.getenv("ALERT_COOLDOWN_MINUTES", "15"))
    check_interval_seconds: int = int(os.getenv("TRENDING_CHECK_INTERVAL", "30"))


@dataclass(frozen=True)
class FilterConfig:
    """Anti-spam and false-positive filter settings."""

    min_message_length: int = int(os.getenv("MIN_MESSAGE_LENGTH", "0"))
    ignore_forwarded: bool = os.getenv("IGNORE_FORWARDED", "false").lower() == "true"


@dataclass(frozen=True)
class DexscreenerConfig:
    """Dexscreener liquidity validation settings."""

    enabled: bool = os.getenv("DEXSCREENER_ENABLED", "false").lower() == "true"
    min_liquidity_usd: float = float(os.getenv("MIN_LIQUIDITY_USD", "20000"))
    api_base_url: str = "https://api.dexscreener.com/latest/dex/tokens"


@dataclass(frozen=True)
class MetricsConfig:
    """Prometheus metrics settings."""

    enabled: bool = os.getenv("METRICS_ENABLED", "false").lower() == "true"
    port: int = int(os.getenv("METRICS_PORT", "9090"))


@dataclass
class AppConfig:
    """Root application configuration."""

    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    trending: TrendingConfig = field(default_factory=TrendingConfig)
    filters: FilterConfig = field(default_factory=FilterConfig)
    dexscreener: DexscreenerConfig = field(default_factory=DexscreenerConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    def validate(self) -> None:
        """Validate that critical configuration values are present."""
        errors: list[str] = []
        if not self.telegram.api_id:
            errors.append("TELEGRAM_API_ID is required")
        if not self.telegram.api_hash:
            errors.append("TELEGRAM_API_HASH is required")
        if not self.telegram.phone:
            errors.append("TELEGRAM_PHONE is required")
        if not self.database.password:
            errors.append("DB_PASSWORD is required")
        if errors:
            for err in errors:
                logger.error("Config error: %s", err)
            raise SystemExit(
                f"Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors)
            )
        logger.info("Configuration validated successfully")
