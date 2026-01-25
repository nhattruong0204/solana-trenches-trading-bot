"""
Configuration management using Pydantic for validation.

Supports loading from environment variables and .env files
with full validation and type coercion.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.constants import (
    DEFAULT_BUY_AMOUNT_SOL,
    DEFAULT_MAX_POSITIONS,
    DEFAULT_MIN_MULTIPLIER,
    DEFAULT_SELL_PERCENTAGE,
    DEFAULT_STATE_FILE,
    DEFAULT_LOG_FILE,
    GMGN_BOT_USERNAME,
    TRENCHES_CHANNEL_USERNAME,
)


class TelegramSettings(BaseModel):
    """Telegram API configuration."""
    
    api_id: int = Field(..., description="Telegram API ID from my.telegram.org")
    api_hash: str = Field(..., description="Telegram API hash from my.telegram.org")
    phone: Optional[str] = Field(None, description="Phone number for authentication")
    session_name: str = Field(
        "wallet_tracker_session",
        description="Name of the session file (without extension)"
    )
    
    @field_validator("api_id")
    @classmethod
    def validate_api_id(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("API ID must be a positive integer")
        return v
    
    @field_validator("api_hash")
    @classmethod
    def validate_api_hash(cls, v: str) -> str:
        if not v or len(v) < 10:
            raise ValueError("API hash appears to be invalid")
        return v


class TradingSettings(BaseModel):
    """Trading strategy configuration."""

    enabled: bool = Field(True, description="Master switch for trading")
    dry_run: bool = Field(True, description="If True, simulate trades without execution")
    buy_amount_sol: float = Field(
        DEFAULT_BUY_AMOUNT_SOL,
        ge=0.001,
        le=100.0,
        description="Amount of SOL to buy per signal"
    )
    sell_percentage: int = Field(
        DEFAULT_SELL_PERCENTAGE,
        ge=1,
        le=100,
        description="Percentage to sell when target is hit"
    )
    min_multiplier_to_sell: float = Field(
        DEFAULT_MIN_MULTIPLIER,
        ge=1.1,
        le=100.0,
        description="Minimum multiplier to trigger sell"
    )
    max_open_positions: int = Field(
        DEFAULT_MAX_POSITIONS,
        ge=1,
        le=100,
        description="Maximum number of concurrent positions"
    )

    @field_validator("buy_amount_sol")
    @classmethod
    def validate_buy_amount(cls, v: float) -> float:
        if v < 0.001:
            raise ValueError("Buy amount must be at least 0.001 SOL")
        return round(v, 4)


class PublicChannelSettings(BaseModel):
    """Public marketing channel configuration."""

    # Public channel for marketing (free, delayed signals)
    public_channel_id: Optional[str] = Field(
        None, description="Public Telegram channel ID for marketing broadcasts"
    )
    public_channel_username: Optional[str] = Field(
        None, description="Public channel @username"
    )

    # Premium channel (instant signals, full details)
    premium_channel_id: Optional[str] = Field(
        None, description="Premium Telegram channel ID"
    )

    # Broadcast settings
    min_multiplier_to_broadcast: float = Field(
        2.0, ge=1.5, le=10.0,
        description="Minimum multiplier to broadcast to public channel"
    )
    broadcast_delay_seconds: int = Field(
        300, ge=60, le=3600,
        description="Delay before broadcasting to public channel (free users)"
    )
    show_token_address_public: bool = Field(
        False, description="Show token address in public channel (usually False)"
    )
    include_cta: bool = Field(
        True, description="Include call-to-action for premium in broadcasts"
    )

    # Branding
    bot_name: str = Field("Trenches Trading Bot", description="Bot name for branding")
    bot_username: str = Field("TrenchesBot", description="Bot @username for CTAs")


class SubscriptionSettings(BaseModel):
    """Subscription and payment configuration."""

    # Enable subscriptions
    subscriptions_enabled: bool = Field(
        False, description="Enable premium subscription system"
    )

    # Payment wallets
    payment_sol_address: Optional[str] = Field(
        None, description="SOL wallet address for payments"
    )
    payment_usdt_bep20_address: Optional[str] = Field(
        None, description="USDT BEP20 (BNB Chain) address"
    )
    payment_usdc_sol_address: Optional[str] = Field(
        None, description="USDC (Solana) address"
    )

    # Pricing (USD)
    price_monthly: float = Field(79.0, ge=1.0, description="Monthly plan price USD")
    price_quarterly: float = Field(199.0, ge=1.0, description="Quarterly plan price USD")
    price_yearly: float = Field(599.0, ge=1.0, description="Yearly plan price USD")
    price_lifetime: float = Field(999.0, ge=1.0, description="Lifetime plan price USD")

    # State file
    subscriptions_file: str = Field(
        "subscriptions.json", description="Path to subscriptions state file"
    )


class RiskSettings(BaseModel):
    """Risk management configuration."""

    # Stop Loss
    stop_loss_enabled: bool = Field(True, description="Enable stop loss protection")
    stop_loss_type: str = Field(
        "fixed_percentage",
        description="Stop loss type: fixed_percentage, trailing, time_based, atr_based"
    )
    stop_loss_percentage: float = Field(
        0.25,
        ge=0.05,
        le=0.90,
        description="Fixed stop loss percentage (e.g., 0.25 = 25% loss)"
    )
    trailing_stop_percentage: float = Field(
        0.20,
        ge=0.05,
        le=0.50,
        description="Trailing stop percentage from peak"
    )
    trailing_stop_activation: float = Field(
        1.5,
        ge=1.1,
        le=10.0,
        description="Multiplier to activate trailing stop"
    )
    time_stop_hours: int = Field(
        24,
        ge=1,
        le=168,
        description="Hours before time-based stop triggers if underwater"
    )

    # Position Sizing
    dynamic_sizing_enabled: bool = Field(True, description="Enable dynamic position sizing")
    risk_per_trade: float = Field(
        0.02,
        ge=0.005,
        le=0.10,
        description="Risk per trade as fraction of capital (e.g., 0.02 = 2%)"
    )
    min_position_size_sol: float = Field(0.01, ge=0.001, description="Minimum position size")
    max_position_size_sol: float = Field(1.0, le=10.0, description="Maximum position size")

    # Portfolio Risk
    max_portfolio_heat: float = Field(
        0.10,
        ge=0.05,
        le=0.50,
        description="Maximum portfolio risk as fraction of capital"
    )
    max_hold_time_hours: int = Field(
        72,
        ge=1,
        le=720,
        description="Maximum hours to hold a position"
    )

    # Circuit Breaker
    circuit_breaker_enabled: bool = Field(True, description="Enable circuit breaker")
    daily_loss_limit_pct: float = Field(
        0.05,
        ge=0.01,
        le=0.25,
        description="Daily loss limit as fraction of capital"
    )
    consecutive_loss_limit: int = Field(
        5,
        ge=2,
        le=20,
        description="Number of consecutive losses to trigger circuit breaker"
    )
    circuit_breaker_cooldown_minutes: int = Field(
        60,
        ge=5,
        le=1440,
        description="Cooldown period after circuit breaker triggers"
    )

    # Capital tracking
    trading_capital_sol: float = Field(
        10.0,
        ge=0.1,
        le=10000.0,
        description="Total trading capital in SOL for risk calculations"
    )


class ChannelSettings(BaseModel):
    """Telegram channel configuration."""
    
    signal_channel: str = Field(
        TRENCHES_CHANNEL_USERNAME,
        description="Channel username to monitor for signals"
    )
    gmgn_bot: str = Field(
        GMGN_BOT_USERNAME,
        description="GMGN bot username for trade execution"
    )


class PathSettings(BaseModel):
    """File path configuration."""
    
    state_file: Path = Field(
        Path(DEFAULT_STATE_FILE),
        description="Path to state persistence file"
    )
    log_file: Path = Field(
        Path(DEFAULT_LOG_FILE),
        description="Path to log file"
    )
    session_path: Optional[Path] = Field(
        None,
        description="Custom path to Telegram session file"
    )


class Settings(BaseSettings):
    """
    Main application settings.
    
    Configuration is loaded from environment variables with the following prefixes:
    - TELEGRAM_* for Telegram settings
    - TRADING_* for trading settings
    
    You can also use a .env file in the working directory.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # Telegram configuration (required)
    telegram_api_id: int = Field(..., alias="TELEGRAM_API_ID")
    telegram_api_hash: str = Field(..., alias="TELEGRAM_API_HASH")
    telegram_phone: Optional[str] = Field(None, alias="TELEGRAM_PHONE")
    telegram_session_name: str = Field(
        "wallet_tracker_session",
        alias="TELEGRAM_SESSION_NAME"
    )
    
    # Trading configuration
    trading_enabled: bool = Field(True, alias="TRADING_ENABLED")
    trading_dry_run: bool = Field(True, alias="TRADING_DRY_RUN")
    trading_buy_amount_sol: float = Field(
        DEFAULT_BUY_AMOUNT_SOL,
        alias="TRADING_BUY_AMOUNT_SOL"
    )
    trading_sell_percentage: int = Field(
        DEFAULT_SELL_PERCENTAGE,
        alias="TRADING_SELL_PERCENTAGE"
    )
    trading_min_multiplier: float = Field(
        DEFAULT_MIN_MULTIPLIER,
        alias="TRADING_MIN_MULTIPLIER"
    )
    trading_max_positions: int = Field(
        DEFAULT_MAX_POSITIONS,
        alias="TRADING_MAX_POSITIONS"
    )
    
    # Channel configuration
    signal_channel: str = Field(
        TRENCHES_CHANNEL_USERNAME,
        alias="SIGNAL_CHANNEL"
    )
    gmgn_bot: str = Field(
        GMGN_BOT_USERNAME,
        alias="GMGN_BOT"
    )
    
    # Controller configuration (for Telegram remote control)
    controller_enabled: bool = Field(True, alias="CONTROLLER_ENABLED")
    admin_user_id: Optional[int] = Field(None, alias="ADMIN_USER_ID")
    
    # Bot configuration (for notifications via BotFather bot)
    bot_token: Optional[str] = Field(None, alias="BOT_TOKEN")
    notification_channel: Optional[str] = Field(None, alias="NOTIFICATION_CHANNEL")
    
    # GMGN Wallet configuration
    gmgn_wallet: Optional[str] = Field(None, alias="GMGN_WALLET")
    
    # Path configuration
    state_file: str = Field(DEFAULT_STATE_FILE, alias="STATE_FILE")
    log_file: str = Field(DEFAULT_LOG_FILE, alias="LOG_FILE")

    # Public channel configuration
    public_channel_id: Optional[str] = Field(None, alias="PUBLIC_CHANNEL_ID")
    public_channel_username: Optional[str] = Field(None, alias="PUBLIC_CHANNEL_USERNAME")
    premium_channel_id: Optional[str] = Field(None, alias="PREMIUM_CHANNEL_ID")
    broadcast_min_multiplier: float = Field(2.0, alias="BROADCAST_MIN_MULTIPLIER")
    broadcast_delay_seconds: int = Field(300, alias="BROADCAST_DELAY_SECONDS")
    show_token_address_public: bool = Field(False, alias="SHOW_TOKEN_ADDRESS_PUBLIC")
    bot_name: str = Field("Trenches Trading Bot", alias="BOT_NAME")
    bot_public_username: str = Field("TrenchesBot", alias="BOT_PUBLIC_USERNAME")

    # Subscription configuration
    subscriptions_enabled: bool = Field(False, alias="SUBSCRIPTIONS_ENABLED")
    payment_sol_address: Optional[str] = Field(None, alias="PAYMENT_SOL_ADDRESS")
    payment_usdt_bep20_address: Optional[str] = Field(None, alias="PAYMENT_USDT_BEP20_ADDRESS")
    payment_usdc_sol_address: Optional[str] = Field(None, alias="PAYMENT_USDC_SOL_ADDRESS")
    price_monthly: float = Field(79.0, alias="PRICE_MONTHLY")
    price_quarterly: float = Field(199.0, alias="PRICE_QUARTERLY")
    price_yearly: float = Field(599.0, alias="PRICE_YEARLY")
    price_lifetime: float = Field(999.0, alias="PRICE_LIFETIME")
    subscriptions_file: str = Field("subscriptions.json", alias="SUBSCRIPTIONS_FILE")

    # Risk management configuration
    risk_stop_loss_enabled: bool = Field(True, alias="STOP_LOSS_ENABLED")
    risk_stop_loss_type: str = Field("fixed_percentage", alias="STOP_LOSS_TYPE")
    risk_stop_loss_percentage: float = Field(0.25, alias="STOP_LOSS_PERCENTAGE")
    risk_trailing_stop_percentage: float = Field(0.20, alias="TRAILING_STOP_PERCENTAGE")
    risk_trailing_stop_activation: float = Field(1.5, alias="TRAILING_STOP_ACTIVATION")
    risk_time_stop_hours: int = Field(24, alias="TIME_STOP_HOURS")
    risk_dynamic_sizing_enabled: bool = Field(True, alias="DYNAMIC_SIZING_ENABLED")
    risk_per_trade: float = Field(0.02, alias="RISK_PER_TRADE")
    risk_min_position_size_sol: float = Field(0.01, alias="MIN_POSITION_SIZE_SOL")
    risk_max_position_size_sol: float = Field(1.0, alias="MAX_POSITION_SIZE_SOL")
    risk_max_portfolio_heat: float = Field(0.10, alias="MAX_PORTFOLIO_HEAT")
    risk_max_hold_time_hours: int = Field(72, alias="MAX_HOLD_TIME_HOURS")
    risk_circuit_breaker_enabled: bool = Field(True, alias="CIRCUIT_BREAKER_ENABLED")
    risk_daily_loss_limit_pct: float = Field(0.05, alias="DAILY_LOSS_LIMIT_PCT")
    risk_consecutive_loss_limit: int = Field(5, alias="CONSECUTIVE_LOSS_LIMIT")
    risk_circuit_breaker_cooldown_minutes: int = Field(60, alias="CIRCUIT_BREAKER_COOLDOWN_MINUTES")
    risk_trading_capital_sol: float = Field(10.0, alias="TRADING_CAPITAL_SOL")
    
    @property
    def telegram(self) -> TelegramSettings:
        """Get Telegram settings as a structured object."""
        return TelegramSettings(
            api_id=self.telegram_api_id,
            api_hash=self.telegram_api_hash,
            phone=self.telegram_phone,
            session_name=self.telegram_session_name,
        )
    
    @property
    def trading(self) -> TradingSettings:
        """Get trading settings as a structured object."""
        return TradingSettings(
            enabled=self.trading_enabled,
            dry_run=self.trading_dry_run,
            buy_amount_sol=self.trading_buy_amount_sol,
            sell_percentage=self.trading_sell_percentage,
            min_multiplier_to_sell=self.trading_min_multiplier,
            max_open_positions=self.trading_max_positions,
        )
    
    @property
    def channel(self) -> ChannelSettings:
        """Get channel settings as a structured object."""
        return ChannelSettings(
            signal_channel=self.signal_channel,
            gmgn_bot=self.gmgn_bot,
        )
    
    @property
    def paths(self) -> PathSettings:
        """Get path settings as a structured object."""
        return PathSettings(
            state_file=Path(self.state_file),
            log_file=Path(self.log_file),
        )

    @property
    def risk(self) -> RiskSettings:
        """Get risk management settings as a structured object."""
        return RiskSettings(
            stop_loss_enabled=self.risk_stop_loss_enabled,
            stop_loss_type=self.risk_stop_loss_type,
            stop_loss_percentage=self.risk_stop_loss_percentage,
            trailing_stop_percentage=self.risk_trailing_stop_percentage,
            trailing_stop_activation=self.risk_trailing_stop_activation,
            time_stop_hours=self.risk_time_stop_hours,
            dynamic_sizing_enabled=self.risk_dynamic_sizing_enabled,
            risk_per_trade=self.risk_per_trade,
            min_position_size_sol=self.risk_min_position_size_sol,
            max_position_size_sol=self.risk_max_position_size_sol,
            max_portfolio_heat=self.risk_max_portfolio_heat,
            max_hold_time_hours=self.risk_max_hold_time_hours,
            circuit_breaker_enabled=self.risk_circuit_breaker_enabled,
            daily_loss_limit_pct=self.risk_daily_loss_limit_pct,
            consecutive_loss_limit=self.risk_consecutive_loss_limit,
            circuit_breaker_cooldown_minutes=self.risk_circuit_breaker_cooldown_minutes,
            trading_capital_sol=self.risk_trading_capital_sol,
        )

    @property
    def public_channel(self) -> PublicChannelSettings:
        """Get public channel settings as a structured object."""
        return PublicChannelSettings(
            public_channel_id=self.public_channel_id,
            public_channel_username=self.public_channel_username,
            premium_channel_id=self.premium_channel_id,
            min_multiplier_to_broadcast=self.broadcast_min_multiplier,
            broadcast_delay_seconds=self.broadcast_delay_seconds,
            show_token_address_public=self.show_token_address_public,
            bot_name=self.bot_name,
            bot_username=self.bot_public_username,
        )

    @property
    def subscription(self) -> SubscriptionSettings:
        """Get subscription settings as a structured object."""
        return SubscriptionSettings(
            subscriptions_enabled=self.subscriptions_enabled,
            payment_sol_address=self.payment_sol_address,
            payment_usdt_bep20_address=self.payment_usdt_bep20_address,
            payment_usdc_sol_address=self.payment_usdc_sol_address,
            price_monthly=self.price_monthly,
            price_quarterly=self.price_quarterly,
            price_yearly=self.price_yearly,
            price_lifetime=self.price_lifetime,
            subscriptions_file=self.subscriptions_file,
        )


@lru_cache
def get_settings() -> Settings:
    """
    Get cached application settings.
    
    Settings are loaded once and cached for performance.
    Use clear_settings_cache() to reload.
    
    Returns:
        Settings: Application settings instance
        
    Raises:
        ValidationError: If required settings are missing or invalid
    """
    return Settings()


def clear_settings_cache() -> None:
    """Clear the settings cache to force reload."""
    get_settings.cache_clear()


def validate_environment() -> tuple[bool, list[str]]:
    """
    Validate that all required environment variables are set.

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    # Load .env file first if it exists
    from dotenv import load_dotenv
    load_dotenv()

    errors: list[str] = []

    required_vars = [
        ("TELEGRAM_API_ID", "Telegram API ID"),
        ("TELEGRAM_API_HASH", "Telegram API Hash"),
    ]

    for var_name, description in required_vars:
        if not os.environ.get(var_name):
            errors.append(f"Missing required environment variable: {var_name} ({description})")

    # Validate API ID is numeric if present
    api_id = os.environ.get("TELEGRAM_API_ID", "")
    if api_id and not api_id.isdigit():
        errors.append("TELEGRAM_API_ID must be a numeric value")

    return len(errors) == 0, errors
