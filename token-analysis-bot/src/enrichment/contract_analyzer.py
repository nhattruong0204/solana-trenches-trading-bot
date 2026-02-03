"""Contract analysis agent - security checks and deployer analysis."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

import httpx
from web3 import AsyncWeb3
from web3.exceptions import ContractLogicError

from src.config import Settings
from src.constants import HONEYPOT_INDICATORS, ERC20_ABI, ConfidenceLevel
from src.models import ContractAnalysis, TokenEvent

logger = logging.getLogger(__name__)


class ContractAnalyzer:
    """Analyzes token contracts for security and metadata."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._w3: Optional[AsyncWeb3] = None
        self._http_client: Optional[httpx.AsyncClient] = None

        # Basescan API (optional, for deployer lookup)
        self.basescan_api_key = ""  # Set via env or config
        self.basescan_url = "https://api.basescan.org/api"

    async def initialize(self) -> None:
        """Initialize connections."""
        self._w3 = AsyncWeb3(
            AsyncWeb3.AsyncHTTPProvider(self.settings.chain.rpc_url)
        )
        self._http_client = httpx.AsyncClient(timeout=30.0)
        logger.info("Contract analyzer initialized")

    async def close(self) -> None:
        """Close connections."""
        if self._http_client:
            await self._http_client.aclose()

    async def analyze(self, event: TokenEvent) -> ContractAnalysis:
        """Perform full contract analysis."""
        logger.info(f"Analyzing contract: {event.token_address}")
        start_time = datetime.utcnow()

        analysis = ContractAnalysis(
            token_address=event.token_address,
            deployer_address="",
            analyzed_at=start_time,
        )

        try:
            # Run analyses in parallel
            token_info_task = self._get_token_info(event.token_address)
            deployer_task = self._get_deployer_address(event.token_address)
            honeypot_task = self._check_honeypot(event.token_address)
            security_task = self._analyze_security(event.token_address)

            results = await asyncio.gather(
                token_info_task,
                deployer_task,
                honeypot_task,
                security_task,
                return_exceptions=True,
            )

            # Process token info
            if not isinstance(results[0], Exception):
                token_info = results[0]
                analysis.name = token_info.get("name", "")
                analysis.symbol = token_info.get("symbol", "")
                analysis.decimals = token_info.get("decimals", 18)
                analysis.total_supply = token_info.get("total_supply", 0)
                analysis.owner_address = token_info.get("owner")

            # Process deployer info
            if not isinstance(results[1], Exception):
                deployer_info = results[1]
                analysis.deployer_address = deployer_info.get("address", "")
                analysis.deployer_eth_balance = deployer_info.get("balance", 0)
                analysis.deployer_tx_count = deployer_info.get("tx_count", 0)
                analysis.deployer_age_days = deployer_info.get("age_days", 0)
                analysis.deployer_prior_tokens = deployer_info.get("prior_tokens", [])

                # Calculate deployer balance percentage
                if analysis.total_supply > 0 and analysis.deployer_address:
                    deployer_balance = await self._get_token_balance(
                        event.token_address, analysis.deployer_address
                    )
                    analysis.deployer_balance_pct = (
                        deployer_balance / analysis.total_supply * 100
                    )

            # Process honeypot check
            if not isinstance(results[2], Exception):
                honeypot_result = results[2]
                analysis.is_honeypot = honeypot_result.get("is_honeypot", False)
                analysis.honeypot_reason = honeypot_result.get("reason")

            # Process security analysis
            if not isinstance(results[3], Exception):
                security = results[3]
                analysis.has_proxy = security.get("has_proxy", False)
                analysis.has_mint_function = security.get("has_mint", False)
                analysis.has_blacklist = security.get("has_blacklist", False)
                analysis.is_renounced = security.get("is_renounced", False)

            # Set confidence based on data completeness
            if analysis.deployer_address and analysis.symbol:
                analysis.confidence = ConfidenceLevel.HIGH
            elif analysis.symbol:
                analysis.confidence = ConfidenceLevel.MEDIUM
            else:
                analysis.confidence = ConfidenceLevel.LOW

            logger.info(
                f"Contract analysis complete for {analysis.symbol}: "
                f"honeypot={analysis.is_honeypot}, "
                f"deployer_pct={analysis.deployer_balance_pct:.1f}%"
            )

        except Exception as e:
            logger.error(f"Error analyzing contract {event.token_address}: {e}")
            analysis.confidence = ConfidenceLevel.UNVERIFIED

        return analysis

    async def _get_token_info(self, token_address: str) -> dict[str, Any]:
        """Get basic token information from contract."""
        info = {}

        try:
            contract = self._w3.eth.contract(
                address=self._w3.to_checksum_address(token_address),
                abi=ERC20_ABI,
            )

            # Fetch basic info
            try:
                info["name"] = await contract.functions.name().call()
            except (ContractLogicError, Exception):
                info["name"] = ""

            try:
                info["symbol"] = await contract.functions.symbol().call()
            except (ContractLogicError, Exception):
                info["symbol"] = ""

            try:
                info["decimals"] = await contract.functions.decimals().call()
            except (ContractLogicError, Exception):
                info["decimals"] = 18

            try:
                info["total_supply"] = await contract.functions.totalSupply().call()
            except (ContractLogicError, Exception):
                info["total_supply"] = 0

            try:
                info["owner"] = await contract.functions.owner().call()
            except (ContractLogicError, Exception):
                info["owner"] = None

        except Exception as e:
            logger.error(f"Error getting token info: {e}")

        return info

    async def _get_deployer_address(self, token_address: str) -> dict[str, Any]:
        """Get deployer address and info using Basescan API."""
        result = {"address": "", "balance": 0, "tx_count": 0, "age_days": 0, "prior_tokens": []}

        if not self.basescan_api_key:
            logger.debug("Basescan API key not configured, skipping deployer lookup")
            return result

        try:
            # Get contract creation info
            response = await self._http_client.get(
                self.basescan_url,
                params={
                    "module": "contract",
                    "action": "getcontractcreation",
                    "contractaddresses": token_address,
                    "apikey": self.basescan_api_key,
                },
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "1" and data.get("result"):
                creator_info = data["result"][0]
                deployer = creator_info.get("contractCreator", "")
                result["address"] = deployer

                if deployer:
                    # Get deployer balance
                    balance = await self._w3.eth.get_balance(
                        self._w3.to_checksum_address(deployer)
                    )
                    result["balance"] = self._w3.from_wei(balance, "ether")

                    # Get transaction count
                    result["tx_count"] = await self._w3.eth.get_transaction_count(
                        self._w3.to_checksum_address(deployer)
                    )

                    # Get prior token deployments
                    result["prior_tokens"] = await self._get_prior_deployments(deployer)

        except Exception as e:
            logger.error(f"Error getting deployer info: {e}")

        return result

    async def _get_prior_deployments(self, deployer_address: str) -> list[str]:
        """Get list of prior token deployments by this address."""
        prior_tokens = []

        if not self.basescan_api_key:
            return prior_tokens

        try:
            response = await self._http_client.get(
                self.basescan_url,
                params={
                    "module": "account",
                    "action": "txlist",
                    "address": deployer_address,
                    "startblock": 0,
                    "endblock": 99999999,
                    "sort": "desc",
                    "apikey": self.basescan_api_key,
                },
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "1" and data.get("result"):
                for tx in data["result"][:100]:  # Check last 100 txs
                    # Contract creation tx has empty "to" field
                    if not tx.get("to") and tx.get("contractAddress"):
                        prior_tokens.append(tx["contractAddress"])

        except Exception as e:
            logger.error(f"Error getting prior deployments: {e}")

        return prior_tokens[:10]  # Limit to 10

    async def _check_honeypot(self, token_address: str) -> dict[str, Any]:
        """Check if token is a honeypot using simulation."""
        result = {"is_honeypot": False, "reason": None}

        # Use external honeypot checker API
        try:
            response = await self._http_client.get(
                f"https://api.honeypot.is/v2/IsHoneypot",
                params={
                    "address": token_address,
                    "chainId": self.settings.chain.chain_id,
                },
            )

            if response.status_code == 200:
                data = response.json()
                result["is_honeypot"] = data.get("honeypotResult", {}).get(
                    "isHoneypot", False
                )

                if result["is_honeypot"]:
                    reason = data.get("honeypotResult", {}).get("honeypotReason", "")
                    result["reason"] = reason or "Failed sell simulation"

                # Check for high taxes
                sell_tax = data.get("simulationResult", {}).get("sellTax", 0)
                if sell_tax > 10:  # >10% sell tax
                    result["is_honeypot"] = True
                    result["reason"] = f"High sell tax: {sell_tax}%"

        except Exception as e:
            logger.debug(f"Honeypot check failed (will try alternative): {e}")

            # Alternative: Try GoPlus API
            try:
                response = await self._http_client.get(
                    f"https://api.gopluslabs.io/api/v1/token_security/{self.settings.chain.chain_id}",
                    params={"contract_addresses": token_address},
                )

                if response.status_code == 200:
                    data = response.json()
                    token_data = data.get("result", {}).get(token_address.lower(), {})

                    if token_data.get("is_honeypot") == "1":
                        result["is_honeypot"] = True
                        result["reason"] = "Flagged by GoPlus"

                    if token_data.get("cannot_sell_all") == "1":
                        result["is_honeypot"] = True
                        result["reason"] = "Cannot sell all tokens"

            except Exception as e2:
                logger.error(f"Alternative honeypot check also failed: {e2}")

        return result

    async def _analyze_security(self, token_address: str) -> dict[str, Any]:
        """Analyze contract security features."""
        result = {
            "has_proxy": False,
            "has_mint": False,
            "has_blacklist": False,
            "is_renounced": False,
        }

        try:
            # Check for proxy pattern
            code = await self._w3.eth.get_code(
                self._w3.to_checksum_address(token_address)
            )
            code_hex = code.hex()

            # Common proxy patterns
            proxy_patterns = [
                "363d3d373d3d3d363d73",  # EIP-1167 minimal proxy
                "5c60da1b",  # implementation() selector
                "f851a440",  # admin() selector
            ]
            result["has_proxy"] = any(p in code_hex for p in proxy_patterns)

            # Check for mint/blacklist via GoPlus
            response = await self._http_client.get(
                f"https://api.gopluslabs.io/api/v1/token_security/{self.settings.chain.chain_id}",
                params={"contract_addresses": token_address},
            )

            if response.status_code == 200:
                data = response.json()
                token_data = data.get("result", {}).get(token_address.lower(), {})

                result["has_mint"] = token_data.get("is_mintable") == "1"
                result["has_blacklist"] = token_data.get("is_blacklisted") == "1"

                # Check if owner is null/renounced
                owner = token_data.get("owner_address", "")
                result["is_renounced"] = owner.lower() in [
                    "0x0000000000000000000000000000000000000000",
                    "0x000000000000000000000000000000000000dead",
                    "",
                ]

        except Exception as e:
            logger.error(f"Error analyzing security: {e}")

        return result

    async def _get_token_balance(self, token_address: str, holder_address: str) -> int:
        """Get token balance for a specific holder."""
        try:
            contract = self._w3.eth.contract(
                address=self._w3.to_checksum_address(token_address),
                abi=ERC20_ABI,
            )
            balance = await contract.functions.balanceOf(
                self._w3.to_checksum_address(holder_address)
            ).call()
            return balance
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return 0
