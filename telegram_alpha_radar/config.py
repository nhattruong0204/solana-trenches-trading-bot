"""Environment-based configuration with validation."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root or cwd
_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)
else:
    load_dotenv()


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _env_int(key: str, default: int = 0) -> int:
    return int(os.getenv(key, str(default)))


def _env_float(key: str, default: float = 0.0) -> float:
    return float(os.getenv(key, str(default)))


def _env_bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Sub-configs
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TelegramConfig:
    """Telegram MTProto credentials (Telethon user session)."""

    api_id: int = field(default_factory=lambda: _env_int("TELEGRAM_API_ID"))
    api_hash: str = field(default_factory=lambda: _env("TELEGRAM_API_HASH"))
    phone: str = field(default_factory=lambda: _env("TELEGRAM_PHONE"))
    session_name: str = field(
        default_factory=lambda: _env("TELEGRAM_SESSION_NAME", "alpha_radar")
    )


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    """PostgreSQL connection settings."""

    host: str = field(default_factory=lambda: _env("DB_HOST", "localhost"))
    port: int = field(default_factory=lambda: _env_int("DB_PORT", 5432))
    user: str = field(default_factory=lambda: _env("DB_USER", "radar"))
    password: str = field(default_factory=lambda: _env("DB_PASSWORD"))
    database: str = field(
        default_factory=lambda: _env("DB_NAME", "alpha_radar")
    )
    pool_min: int = field(default_factory=lambda: _env_int("DB_POOL_MIN", 2))
    pool_max: int = field(default_factory=lambda: _env_int("DB_POOL_MAX", 10))

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )


@dataclass(frozen=True, slots=True)
class TrendingConfig:
    """Trending detection thresholds."""

    window_minutes: int = field(
        default_factory=lambda: _env_int("TRENDING_WINDOW_MINUTES", 5)
    )
    min_mentions: int = field(
        default_factory=lambda: _env_int("TRENDING_MIN_MENTIONS", 3)
    )
    min_unique_chats: int = field(
        default_factory=lambda: _env_int("TRENDING_MIN_UNIQUE_CHATS", 2)
    )
    cooldown_minutes: int = field(
        default_factory=lambda: _env_int("TRENDING_COOLDOWN_MINUTES", 15)
    )
    check_interval_seconds: int = field(
        default_factory=lambda: _env_int("TRENDING_CHECK_INTERVAL", 30)
    )


@dataclass(frozen=True, slots=True)
class FilterConfig:
    """Message filtering rules."""

    min_message_length: int = field(
        default_factory=lambda: _env_int("FILTER_MIN_MSG_LENGTH", 5)
    )
    ignore_forwarded: bool = field(
        default_factory=lambda: _env_bool("FILTER_IGNORE_FORWARDED", False)
    )


@dataclass(frozen=True, slots=True)
class DexscreenerConfig:
    """Optional Dexscreener liquidity validation."""

    enabled: bool = field(
        default_factory=lambda: _env_bool("DEXSCREENER_ENABLED", False)
    )
    min_liquidity_usd: float = field(
        default_factory=lambda: _env_float("DEXSCREENER_MIN_LIQUIDITY", 1000.0)
    )
    api_url: str = field(
        default_factory=lambda: _env(
            "DEXSCREENER_API_URL",
            "https://api.dexscreener.com/latest/dex/tokens",
        )
    )


@dataclass(frozen=True, slots=True)
class MetricsConfig:
    """Prometheus metrics settings."""

    enabled: bool = field(
        default_factory=lambda: _env_bool("METRICS_ENABLED", False)
    )
    port: int = field(
        default_factory=lambda: _env_int("METRICS_PORT", 9090)
    )


@dataclass(frozen=True, slots=True)
class HealthConfig:
    """Health check endpoint settings."""

    enabled: bool = field(
        default_factory=lambda: _env_bool("HEALTH_ENABLED", True)
    )
    port: int = field(
        default_factory=lambda: _env_int("HEALTH_PORT", 8080)
    )


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Root application configuration aggregating all sub-configs."""

    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    trending: TrendingConfig = field(default_factory=TrendingConfig)
    filters: FilterConfig = field(default_factory=FilterConfig)
    dexscreener: DexscreenerConfig = field(default_factory=DexscreenerConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    health: HealthConfig = field(default_factory=HealthConfig)
    log_level: str = field(
        default_factory=lambda: _env("LOG_LEVEL", "INFO")
    )
    log_json: bool = field(
        default_factory=lambda: _env_bool("LOG_JSON", False)
    )

    def validate(self) -> None:
        """Validate required fields; exits on failure."""
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
            for e in errors:
                print(f"[CONFIG ERROR] {e}", file=sys.stderr)
            raise SystemExit(1)
