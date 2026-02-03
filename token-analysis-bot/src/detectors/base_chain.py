"""Base chain event detector - listens for PairCreated events on DEX factories."""

import asyncio
import logging
from datetime import datetime
from typing import AsyncIterator, Callable, Optional

from web3 import AsyncWeb3
from web3.contract import AsyncContract
from web3.types import LogReceipt

from src.config import Settings
from src.constants import (
    AERODROME_FACTORY,
    PAIR_CREATED_ABI,
    QUOTE_TOKENS,
    STABLECOINS,
    SUSHISWAP_FACTORY,
    UNISWAP_V2_FACTORY,
    UNISWAP_V3_FACTORY,
)
from src.models import EventSource, TokenEvent

logger = logging.getLogger(__name__)


class BaseChainDetector:
    """Detects new token pairs on Base chain DEX factories."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._w3: Optional[AsyncWeb3] = None
        self._running = False
        self._callbacks: list[Callable[[TokenEvent], asyncio.Future]] = []

        # DEX factories to monitor
        self.factories = {
            "uniswap_v2": UNISWAP_V2_FACTORY,
            "uniswap_v3": UNISWAP_V3_FACTORY,
            "aerodrome": AERODROME_FACTORY,
            "sushiswap": SUSHISWAP_FACTORY,
        }

        # Track seen pairs to avoid duplicates
        self._seen_pairs: set[str] = set()

    async def connect(self) -> None:
        """Connect to Base chain RPC."""
        logger.info(f"Connecting to Base chain: {self.settings.chain.rpc_url}")
        self._w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self.settings.chain.rpc_url))

        if await self._w3.is_connected():
            chain_id = await self._w3.eth.chain_id
            logger.info(f"Connected to chain ID: {chain_id}")
        else:
            raise ConnectionError("Failed to connect to Base chain RPC")

    async def disconnect(self) -> None:
        """Disconnect from RPC."""
        self._running = False
        logger.info("Disconnected from Base chain")

    def register_callback(self, callback: Callable[[TokenEvent], asyncio.Future]) -> None:
        """Register callback for new token events."""
        self._callbacks.append(callback)

    async def _notify_callbacks(self, event: TokenEvent) -> None:
        """Notify all registered callbacks."""
        for callback in self._callbacks:
            try:
                await callback(event)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def _is_new_token_pair(self, token0: str, token1: str) -> tuple[bool, Optional[str]]:
        """
        Check if this is a new token paired with a quote token.
        Returns (is_new, new_token_address).
        """
        token0_lower = token0.lower()
        token1_lower = token1.lower()

        # Check if one is a quote token (WETH/USDC)
        quote_tokens_lower = {t.lower() for t in QUOTE_TOKENS}

        if token0_lower in quote_tokens_lower:
            new_token = token1
        elif token1_lower in quote_tokens_lower:
            new_token = token0
        else:
            # Neither is a standard quote token - might be exotic pair
            return False, None

        # Skip stablecoins
        stables_lower = {t.lower() for t in STABLECOINS}
        if new_token.lower() in stables_lower:
            return False, None

        return True, new_token

    async def _process_pair_created_log(
        self, log: LogReceipt, factory_name: str
    ) -> Optional[TokenEvent]:
        """Process a PairCreated event log."""
        try:
            # Decode event data
            token0 = self._w3.to_checksum_address("0x" + log["topics"][1].hex()[-40:])
            token1 = self._w3.to_checksum_address("0x" + log["topics"][2].hex()[-40:])
            pair_address = self._w3.to_checksum_address("0x" + log["data"].hex()[26:66])

            # Check if already seen
            pair_key = pair_address.lower()
            if pair_key in self._seen_pairs:
                return None
            self._seen_pairs.add(pair_key)

            # Check if this is a new token
            is_new, new_token = self._is_new_token_pair(token0, token1)
            if not is_new or not new_token:
                return None

            # Get block timestamp
            block = await self._w3.eth.get_block(log["blockNumber"])
            timestamp = datetime.fromtimestamp(block["timestamp"])

            logger.info(
                f"New token detected on {factory_name}: {new_token} "
                f"(pair: {pair_address})"
            )

            return TokenEvent(
                token_address=new_token,
                pair_address=pair_address,
                source=EventSource.CHAIN,
                detected_at=timestamp,
                chain_id=self.settings.chain.chain_id,
                source_metadata={
                    "factory": factory_name,
                    "token0": token0,
                    "token1": token1,
                    "block_number": log["blockNumber"],
                    "tx_hash": log["transactionHash"].hex(),
                },
            )
        except Exception as e:
            logger.error(f"Error processing PairCreated log: {e}")
            return None

    async def _poll_factory(
        self, factory_address: str, factory_name: str, from_block: int
    ) -> tuple[list[TokenEvent], int]:
        """Poll a single factory for new pairs."""
        events: list[TokenEvent] = []

        try:
            # Get latest block
            latest_block = await self._w3.eth.block_number
            to_block = min(from_block + 1000, latest_block)  # Max 1000 blocks per query

            if from_block >= to_block:
                return events, from_block

            # PairCreated event signature
            event_signature = self._w3.keccak(
                text="PairCreated(address,address,address,uint256)"
            )

            # Get logs
            logs = await self._w3.eth.get_logs({
                "address": factory_address,
                "topics": [event_signature],
                "fromBlock": from_block,
                "toBlock": to_block,
            })

            for log in logs:
                event = await self._process_pair_created_log(log, factory_name)
                if event:
                    events.append(event)

            return events, to_block

        except Exception as e:
            logger.error(f"Error polling {factory_name}: {e}")
            return events, from_block

    async def scan_historical(
        self, from_block: int, to_block: Optional[int] = None
    ) -> AsyncIterator[TokenEvent]:
        """Scan historical blocks for new token events."""
        if not self._w3:
            await self.connect()

        if to_block is None:
            to_block = await self._w3.eth.block_number

        current_block = from_block

        while current_block < to_block:
            for factory_name, factory_address in self.factories.items():
                events, new_block = await self._poll_factory(
                    factory_address, factory_name, current_block
                )
                for event in events:
                    yield event

            current_block = min(current_block + 1000, to_block)
            await asyncio.sleep(0.1)  # Rate limiting

    async def start_listening(self) -> None:
        """Start real-time listening for new pairs."""
        if not self._w3:
            await self.connect()

        self._running = True
        logger.info("Starting Base chain listener...")

        # Track last polled block per factory
        latest_block = await self._w3.eth.block_number
        last_blocks = {name: latest_block for name in self.factories}

        while self._running:
            try:
                for factory_name, factory_address in self.factories.items():
                    events, new_block = await self._poll_factory(
                        factory_address, factory_name, last_blocks[factory_name]
                    )

                    last_blocks[factory_name] = new_block

                    for event in events:
                        await self._notify_callbacks(event)

                # Poll every 3 seconds (target < 5s latency)
                await asyncio.sleep(3)

            except Exception as e:
                logger.error(f"Error in listener loop: {e}")
                await asyncio.sleep(5)

    async def stop_listening(self) -> None:
        """Stop the listener."""
        self._running = False
        logger.info("Stopped Base chain listener")

    async def get_deployer(self, token_address: str) -> Optional[str]:
        """Get the deployer address of a token contract."""
        if not self._w3:
            await self.connect()

        try:
            # Get contract creation transaction
            # Note: This requires archive node or basescan API
            # Simplified: get the first transaction to the contract
            code = await self._w3.eth.get_code(token_address)
            if code == b"" or code == "0x":
                return None

            # For now, return None - would need basescan API for accurate deployer
            # In production, use: basescan.io/api?module=contract&action=getcontractcreation
            logger.warning(
                f"Deployer lookup requires Basescan API for {token_address}"
            )
            return None

        except Exception as e:
            logger.error(f"Error getting deployer for {token_address}: {e}")
            return None
