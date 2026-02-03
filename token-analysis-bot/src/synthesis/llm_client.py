"""LLM client for synthesis operations."""

import json
import logging
from typing import Any, Literal, Optional

import httpx

from src.config import Settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Client for LLM API calls (Anthropic Claude or OpenAI)."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._anthropic_client: Optional[httpx.AsyncClient] = None
        self._openai_client: Optional[httpx.AsyncClient] = None

    async def initialize(self) -> None:
        """Initialize HTTP clients."""
        if self.settings.llm.provider == "anthropic":
            self._anthropic_client = httpx.AsyncClient(
                base_url="https://api.anthropic.com/v1",
                timeout=60.0,
                headers={
                    "x-api-key": self.settings.llm.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
            )
            logger.info("Anthropic client initialized")

        elif self.settings.llm.provider == "openai":
            self._openai_client = httpx.AsyncClient(
                base_url="https://api.openai.com/v1",
                timeout=60.0,
                headers={
                    "Authorization": f"Bearer {self.settings.llm.openai_api_key}",
                    "Content-Type": "application/json",
                },
            )
            logger.info("OpenAI client initialized")

    async def close(self) -> None:
        """Close HTTP clients."""
        if self._anthropic_client:
            await self._anthropic_client.aclose()
        if self._openai_client:
            await self._openai_client.aclose()

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """Generate text from LLM."""
        max_tokens = max_tokens or self.settings.llm.max_tokens
        temperature = temperature or self.settings.llm.temperature

        if self.settings.llm.provider == "anthropic":
            return await self._generate_anthropic(
                prompt, system_prompt, max_tokens, temperature
            )
        elif self.settings.llm.provider == "openai":
            return await self._generate_openai(
                prompt, system_prompt, max_tokens, temperature
            )
        else:
            raise ValueError(f"Unknown LLM provider: {self.settings.llm.provider}")

    async def _generate_anthropic(
        self,
        prompt: str,
        system_prompt: Optional[str],
        max_tokens: int,
        temperature: float,
    ) -> str:
        """Generate using Anthropic Claude API."""
        if not self._anthropic_client:
            raise RuntimeError("Anthropic client not initialized")

        request_body = {
            "model": self.settings.llm.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }

        if system_prompt:
            request_body["system"] = system_prompt

        try:
            response = await self._anthropic_client.post(
                "/messages", json=request_body
            )
            response.raise_for_status()
            data = response.json()

            # Extract text from response
            content = data.get("content", [])
            if content and content[0].get("type") == "text":
                return content[0].get("text", "")

            logger.warning(f"Unexpected Anthropic response format: {data}")
            return ""

        except httpx.HTTPStatusError as e:
            logger.error(f"Anthropic API error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Anthropic generation error: {e}")
            raise

    async def _generate_openai(
        self,
        prompt: str,
        system_prompt: Optional[str],
        max_tokens: int,
        temperature: float,
    ) -> str:
        """Generate using OpenAI API."""
        if not self._openai_client:
            raise RuntimeError("OpenAI client not initialized")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        request_body = {
            "model": self.settings.llm.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }

        try:
            response = await self._openai_client.post(
                "/chat/completions", json=request_body
            )
            response.raise_for_status()
            data = response.json()

            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")

            logger.warning(f"Unexpected OpenAI response format: {data}")
            return ""

        except httpx.HTTPStatusError as e:
            logger.error(f"OpenAI API error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"OpenAI generation error: {e}")
            raise

    async def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> dict[str, Any]:
        """Generate and parse JSON from LLM."""
        response = await self.generate(
            prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature or 0.1,  # Lower temp for JSON
        )

        # Extract JSON from response
        try:
            # Try to find JSON in the response
            response = response.strip()

            # Remove markdown code blocks if present
            if response.startswith("```json"):
                response = response[7:]
            elif response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]

            response = response.strip()

            return json.loads(response)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from LLM response: {e}")
            logger.debug(f"Raw response: {response[:500]}")

            # Return empty dict on failure
            return {}

    async def verify_claim(
        self,
        claim: str,
        evidence: str,
    ) -> dict[str, Any]:
        """Verify a specific claim against evidence."""
        prompt = f"""Verify the following claim against the provided evidence.

CLAIM: {claim}

EVIDENCE:
{evidence}

Return JSON:
{{
    "is_supported": true/false,
    "confidence": 0.0-1.0,
    "explanation": "brief explanation"
}}
"""
        return await self.generate_json(prompt, temperature=0.1)
