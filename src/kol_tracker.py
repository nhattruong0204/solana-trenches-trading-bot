"""
KOL (Key Opinion Leader) and Whale Tracker.

This module tracks transactions from known influential wallets including:
- Crypto influencers/KOLs
- Whale wallets
- Smart money addresses
- Successful traders

Provides alerts when these wallets make significant moves, enabling
copy-trading opportunities for premium subscribers.

Inspired by AstroX's "KOLs/Whales Onchain Tracking" feature.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Callable, Awaitable

import httpx

logger = logging.getLogger(__name__)


class WalletType(str, Enum):
    """Types of tracked wallets."""
    KOL = "kol"  # Key Opinion Leader / Influencer
    WHALE = "whale"  # Large holder
    SMART_MONEY = "smart_money"  # High win rate traders
    DEV = "dev"  # Token developers
    FUND = "fund"  # Crypto funds
    INSIDER = "insider"  # Known insiders


class TransactionType(str, Enum):
    """Types of transactions to track."""
    BUY = "buy"
    SELL = "sell"
    TRANSFER = "transfer"


@dataclass
class TrackedWallet:
    """A wallet being tracked."""

    address: str
    name: str
    wallet_type: WalletType

    # Optional metadata
    twitter_handle: Optional[str] = None
    telegram_handle: Optional[str] = None
    notes: Optional[str] = None

    # Tracking settings
    enabled: bool = True
    min_trade_usd: float = 1000.0  # Minimum trade size to alert

    # Stats
    total_trades: int = 0
    profitable_trades: int = 0
    last_seen: Optional[datetime] = None

    @property
    def win_rate(self) -> float:
        """Calculate win rate."""
        if self.total_trades == 0:
            return 0.0
        return (self.profitable_trades / self.total_trades) * 100

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "address": self.address,
            "name": self.name,
            "wallet_type": self.wallet_type.value,
            "twitter_handle": self.twitter_handle,
            "telegram_handle": self.telegram_handle,
            "notes": self.notes,
            "enabled": self.enabled,
            "min_trade_usd": self.min_trade_usd,
            "total_trades": self.total_trades,
            "profitable_trades": self.profitable_trades,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TrackedWallet":
        """Create from dictionary."""
        return cls(
            address=data["address"],
            name=data["name"],
            wallet_type=WalletType(data.get("wallet_type", "smart_money")),
            twitter_handle=data.get("twitter_handle"),
            telegram_handle=data.get("telegram_handle"),
            notes=data.get("notes"),
            enabled=data.get("enabled", True),
            min_trade_usd=data.get("min_trade_usd", 1000.0),
            total_trades=data.get("total_trades", 0),
            profitable_trades=data.get("profitable_trades", 0),
            last_seen=datetime.fromisoformat(data["last_seen"]) if data.get("last_seen") else None,
        )


@dataclass
class WalletTransaction:
    """A transaction from a tracked wallet."""

    wallet: TrackedWallet
    tx_type: TransactionType
    token_address: str
    token_symbol: str

    # Transaction details
    amount_tokens: float
    amount_usd: float
    price_usd: float

    # Metadata
    tx_hash: str
    timestamp: datetime

    # Market context
    token_mcap: Optional[float] = None
    token_liquidity: Optional[float] = None

    @property
    def is_significant(self) -> bool:
        """Check if transaction is significant based on wallet settings."""
        return self.amount_usd >= self.wallet.min_trade_usd

    @property
    def emoji(self) -> str:
        """Get emoji for transaction type."""
        if self.tx_type == TransactionType.BUY:
            return "🟢"
        elif self.tx_type == TransactionType.SELL:
            return "🔴"
        return "🔄"


@dataclass
class KOLTrackerConfig:
    """Configuration for KOL tracker."""

    # Polling settings
    poll_interval_seconds: int = 30
    max_tx_age_hours: int = 1  # Only alert on recent transactions

    # Alert settings
    min_trade_usd_default: float = 500.0
    alert_on_buys: bool = True
    alert_on_sells: bool = True

    # API settings
    helius_api_key: Optional[str] = None
    birdeye_api_key: Optional[str] = None


class KOLTracker:
    """
    Tracks KOL and whale wallets for trading signals.

    Features:
    - Monitor multiple wallets
    - Real-time transaction alerts
    - Copy-trading support
    - Win rate tracking

    Usage:
        tracker = KOLTracker(config)
        await tracker.load()
        tracker.add_wallet(address, name, wallet_type)
        await tracker.start_monitoring(callback)
    """

    # Some known KOL/Whale wallets (examples - should be configured by user)
    DEFAULT_WALLETS = [
        # These are example addresses - replace with real KOL wallets
        TrackedWallet(
            address="",  # Will be set by user
            name="Example KOL",
            wallet_type=WalletType.KOL,
            enabled=False,
        ),
    ]

    def __init__(
        self,
        config: Optional[KOLTrackerConfig] = None,
        state_file: str = "kol_tracker_state.json",
    ) -> None:
        """
        Initialize KOL tracker.

        Args:
            config: Tracker configuration
            state_file: Path to state file
        """
        self._config = config or KOLTrackerConfig()
        self._state_file = Path(state_file)
        self._wallets: dict[str, TrackedWallet] = {}
        self._recent_txs: list[WalletTransaction] = []
        self._monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._http_client: Optional[httpx.AsyncClient] = None
        self._alert_callback: Optional[Callable[[WalletTransaction], Awaitable[None]]] = None

    @property
    def config(self) -> KOLTrackerConfig:
        """Get configuration."""
        return self._config

    @property
    def wallets(self) -> list[TrackedWallet]:
        """Get all tracked wallets."""
        return list(self._wallets.values())

    @property
    def enabled_wallets(self) -> list[TrackedWallet]:
        """Get enabled wallets only."""
        return [w for w in self._wallets.values() if w.enabled]

    async def load(self) -> None:
        """Load state from file."""
        if self._state_file.exists():
            try:
                with open(self._state_file, 'r') as f:
                    data = json.load(f)

                for wallet_data in data.get("wallets", []):
                    wallet = TrackedWallet.from_dict(wallet_data)
                    self._wallets[wallet.address] = wallet

            except Exception as e:
                logger.error(f"Failed to load KOL tracker state: {e}")

        logger.info(f"Loaded {len(self._wallets)} tracked wallets")

    async def save(self) -> None:
        """Save state to file."""
        try:
            data = {
                "wallets": [w.to_dict() for w in self._wallets.values()],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            with open(self._state_file, 'w') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save KOL tracker state: {e}")

    def add_wallet(
        self,
        address: str,
        name: str,
        wallet_type: WalletType = WalletType.SMART_MONEY,
        **kwargs,
    ) -> TrackedWallet:
        """
        Add a wallet to track.

        Args:
            address: Wallet address
            name: Display name
            wallet_type: Type of wallet
            **kwargs: Additional wallet settings

        Returns:
            New TrackedWallet
        """
        wallet = TrackedWallet(
            address=address,
            name=name,
            wallet_type=wallet_type,
            min_trade_usd=kwargs.get("min_trade_usd", self._config.min_trade_usd_default),
            twitter_handle=kwargs.get("twitter_handle"),
            telegram_handle=kwargs.get("telegram_handle"),
            notes=kwargs.get("notes"),
        )

        self._wallets[address] = wallet

        # Save asynchronously
        asyncio.create_task(self.save())

        logger.info(f"Added wallet to track: {name} ({address[:8]}...)")
        return wallet

    def remove_wallet(self, address: str) -> bool:
        """Remove a wallet from tracking."""
        if address in self._wallets:
            del self._wallets[address]
            asyncio.create_task(self.save())
            return True
        return False

    def enable_wallet(self, address: str) -> bool:
        """Enable tracking for a wallet."""
        if address in self._wallets:
            self._wallets[address].enabled = True
            asyncio.create_task(self.save())
            return True
        return False

    def disable_wallet(self, address: str) -> bool:
        """Disable tracking for a wallet."""
        if address in self._wallets:
            self._wallets[address].enabled = False
            asyncio.create_task(self.save())
            return True
        return False

    def get_wallet(self, address: str) -> Optional[TrackedWallet]:
        """Get wallet by address."""
        return self._wallets.get(address)

    async def start_monitoring(
        self,
        callback: Callable[[WalletTransaction], Awaitable[None]],
    ) -> None:
        """
        Start monitoring wallets for transactions.

        Args:
            callback: Async function to call when transaction detected
        """
        if self._monitoring:
            logger.warning("KOL tracker already monitoring")
            return

        self._alert_callback = callback
        self._monitoring = True
        self._http_client = httpx.AsyncClient(timeout=30.0)

        self._monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info("KOL tracker started monitoring")

    async def stop_monitoring(self) -> None:
        """Stop monitoring."""
        self._monitoring = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        if self._http_client:
            await self._http_client.aclose()

        logger.info("KOL tracker stopped")

    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        last_check_time = datetime.now(timezone.utc)

        while self._monitoring:
            try:
                for wallet in self.enabled_wallets:
                    transactions = await self._fetch_recent_transactions(
                        wallet, since=last_check_time
                    )

                    for tx in transactions:
                        if tx.is_significant and self._alert_callback:
                            await self._alert_callback(tx)

                last_check_time = datetime.now(timezone.utc)

            except Exception as e:
                logger.error(f"Error in KOL monitoring loop: {e}")

            await asyncio.sleep(self._config.poll_interval_seconds)

    async def _fetch_recent_transactions(
        self,
        wallet: TrackedWallet,
        since: Optional[datetime] = None,
    ) -> list[WalletTransaction]:
        """
        Fetch recent transactions for a wallet.

        Uses Helius or Birdeye API for transaction data.
        """
        if not self._http_client:
            return []

        # Try Helius first
        if self._config.helius_api_key:
            return await self._fetch_from_helius(wallet, since)

        # Fallback to Birdeye
        if self._config.birdeye_api_key:
            return await self._fetch_from_birdeye(wallet, since)

        # No API configured - return empty
        logger.debug("No API key configured for KOL tracking")
        return []

    async def _fetch_from_helius(
        self,
        wallet: TrackedWallet,
        since: Optional[datetime] = None,
    ) -> list[WalletTransaction]:
        """Fetch transactions from Helius API."""
        try:
            url = f"https://api.helius.xyz/v0/addresses/{wallet.address}/transactions"
            params = {
                "api-key": self._config.helius_api_key,
                "limit": 20,
            }

            response = await self._http_client.get(url, params=params)

            if response.status_code != 200:
                return []

            data = response.json()
            transactions = []

            for tx_data in data:
                tx = self._parse_helius_transaction(wallet, tx_data)
                if tx and (since is None or tx.timestamp > since):
                    transactions.append(tx)

            return transactions

        except Exception as e:
            logger.error(f"Helius API error: {e}")
            return []

    async def _fetch_from_birdeye(
        self,
        wallet: TrackedWallet,
        since: Optional[datetime] = None,
    ) -> list[WalletTransaction]:
        """Fetch transactions from Birdeye API."""
        try:
            url = f"https://public-api.birdeye.so/defi/txs/token/{wallet.address}"
            headers = {"X-API-KEY": self._config.birdeye_api_key}

            response = await self._http_client.get(url, headers=headers)

            if response.status_code != 200:
                return []

            data = response.json()
            transactions = []

            for tx_data in data.get("data", {}).get("items", []):
                tx = self._parse_birdeye_transaction(wallet, tx_data)
                if tx and (since is None or tx.timestamp > since):
                    transactions.append(tx)

            return transactions

        except Exception as e:
            logger.error(f"Birdeye API error: {e}")
            return []

    def _parse_helius_transaction(
        self,
        wallet: TrackedWallet,
        data: dict,
    ) -> Optional[WalletTransaction]:
        """Parse Helius transaction data."""
        try:
            # Check if this is a token swap
            if data.get("type") not in ["SWAP", "TOKEN_TRANSFER"]:
                return None

            # Extract token info
            token_transfers = data.get("tokenTransfers", [])
            if not token_transfers:
                return None

            # Determine if buy or sell
            first_transfer = token_transfers[0]
            is_buy = first_transfer.get("toUserAccount") == wallet.address

            return WalletTransaction(
                wallet=wallet,
                tx_type=TransactionType.BUY if is_buy else TransactionType.SELL,
                token_address=first_transfer.get("mint", ""),
                token_symbol=first_transfer.get("tokenSymbol", "UNKNOWN"),
                amount_tokens=float(first_transfer.get("tokenAmount", 0)),
                amount_usd=0.0,  # Would need price lookup
                price_usd=0.0,
                tx_hash=data.get("signature", ""),
                timestamp=datetime.fromtimestamp(
                    data.get("timestamp", 0), tz=timezone.utc
                ),
            )

        except Exception as e:
            logger.debug(f"Error parsing Helius tx: {e}")
            return None

    def _parse_birdeye_transaction(
        self,
        wallet: TrackedWallet,
        data: dict,
    ) -> Optional[WalletTransaction]:
        """Parse Birdeye transaction data."""
        try:
            return WalletTransaction(
                wallet=wallet,
                tx_type=TransactionType.BUY if data.get("side") == "buy" else TransactionType.SELL,
                token_address=data.get("address", ""),
                token_symbol=data.get("symbol", "UNKNOWN"),
                amount_tokens=float(data.get("volume", 0)),
                amount_usd=float(data.get("volumeUSD", 0)),
                price_usd=float(data.get("price", 0)),
                tx_hash=data.get("txHash", ""),
                timestamp=datetime.fromtimestamp(
                    data.get("blockUnixTime", 0), tz=timezone.utc
                ),
            )

        except Exception as e:
            logger.debug(f"Error parsing Birdeye tx: {e}")
            return None

    async def check_wallet_now(self, address: str) -> list[WalletTransaction]:
        """
        Manually check a wallet for recent transactions.

        Args:
            address: Wallet address to check

        Returns:
            List of recent transactions
        """
        wallet = self._wallets.get(address)
        if not wallet:
            return []

        # Create temporary client if needed
        client_created = False
        if not self._http_client:
            self._http_client = httpx.AsyncClient(timeout=30.0)
            client_created = True

        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=self._config.max_tx_age_hours)
            return await self._fetch_recent_transactions(wallet, since=cutoff)
        finally:
            if client_created and self._http_client:
                await self._http_client.aclose()
                self._http_client = None

    def format_transaction_alert(self, tx: WalletTransaction) -> str:
        """Format a transaction for Telegram alert."""
        wallet_emoji = {
            WalletType.KOL: "👑",
            WalletType.WHALE: "🐋",
            WalletType.SMART_MONEY: "🧠",
            WalletType.DEV: "👨‍💻",
            WalletType.FUND: "🏦",
            WalletType.INSIDER: "🔮",
        }

        w_emoji = wallet_emoji.get(tx.wallet.wallet_type, "👤")
        tx_emoji = tx.emoji

        lines = [
            f"{w_emoji} **{tx.wallet.wallet_type.value.upper()} ALERT** {tx_emoji}",
            "",
            f"**{tx.wallet.name}** just {tx.tx_type.value.upper()}!",
            "",
            f"Token: **${tx.token_symbol}**",
            f"Address: `{tx.token_address}`",
            "",
            f"Amount: **${tx.amount_usd:,.0f}**",
        ]

        if tx.token_mcap:
            lines.append(f"MCap: ${tx.token_mcap / 1_000_000:.1f}M")

        lines.extend([
            "",
            f"📈 [DexScreener](https://dexscreener.com/solana/{tx.token_address})",
            f"🔗 [Transaction](https://solscan.io/tx/{tx.tx_hash})",
        ])

        if tx.wallet.twitter_handle:
            lines.append(f"🐦 [@{tx.wallet.twitter_handle}](https://twitter.com/{tx.wallet.twitter_handle})")

        lines.extend([
            "",
            f"_Win Rate: {tx.wallet.win_rate:.0f}%_",
        ])

        return "\n".join(lines)

    def format_wallets_list(self) -> str:
        """Format list of tracked wallets."""
        if not self._wallets:
            return "No wallets being tracked.\n\nUse `/addwallet <address> <name>` to add one."

        lines = [
            "👥 **TRACKED WALLETS**",
            "",
        ]

        wallet_emoji = {
            WalletType.KOL: "👑",
            WalletType.WHALE: "🐋",
            WalletType.SMART_MONEY: "🧠",
            WalletType.DEV: "👨‍💻",
            WalletType.FUND: "🏦",
            WalletType.INSIDER: "🔮",
        }

        for wallet in self._wallets.values():
            emoji = wallet_emoji.get(wallet.wallet_type, "👤")
            status = "✅" if wallet.enabled else "❌"

            lines.append(
                f"{status} {emoji} **{wallet.name}**"
            )
            lines.append(f"    `{wallet.address[:16]}...`")

            if wallet.win_rate > 0:
                lines.append(f"    Win Rate: {wallet.win_rate:.0f}%")

            lines.append("")

        lines.append(f"_Total: {len(self._wallets)} wallets_")

        return "\n".join(lines)

    def get_top_performers(self, limit: int = 10) -> list[TrackedWallet]:
        """Get wallets sorted by win rate."""
        return sorted(
            self._wallets.values(),
            key=lambda w: w.win_rate,
            reverse=True,
        )[:limit]
