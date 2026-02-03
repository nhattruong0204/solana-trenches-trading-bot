"""Tests for utility helpers."""

from datetime import datetime

import pytest

from src.utils.helpers import (
    chunk_list,
    format_number,
    generate_job_id,
    validate_eth_address,
    RateLimiter,
    Timer,
)


class TestGenerateJobId:
    """Tests for job ID generation."""

    def test_generate_unique_ids(self):
        """Test that job IDs are unique."""
        id1 = generate_job_id("0x123", datetime(2024, 1, 1, 12, 0, 0))
        id2 = generate_job_id("0x123", datetime(2024, 1, 1, 12, 0, 1))

        assert id1 != id2

    def test_same_input_same_id(self):
        """Test that same inputs produce same ID."""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        id1 = generate_job_id("0x123", timestamp)
        id2 = generate_job_id("0x123", timestamp)

        assert id1 == id2

    def test_id_length(self):
        """Test job ID length."""
        job_id = generate_job_id("0x123")

        assert len(job_id) == 16


class TestFormatNumber:
    """Tests for number formatting."""

    def test_format_billions(self):
        """Test formatting billions."""
        assert format_number(1_500_000_000) == "1.50B"
        assert format_number(10_000_000_000, decimals=1) == "10.0B"

    def test_format_millions(self):
        """Test formatting millions."""
        assert format_number(1_500_000) == "1.50M"
        assert format_number(500_000) == "0.50M"

    def test_format_thousands(self):
        """Test formatting thousands."""
        assert format_number(50_000) == "50.00K"
        assert format_number(1_500) == "1.50K"

    def test_format_small(self):
        """Test formatting small numbers."""
        assert format_number(500) == "500.00"
        assert format_number(99.5, decimals=1) == "99.5"


class TestValidateEthAddress:
    """Tests for Ethereum address validation."""

    def test_valid_address(self):
        """Test valid Ethereum address."""
        assert validate_eth_address("0x1234567890abcdef1234567890abcdef12345678")
        assert validate_eth_address("0xABCDEF1234567890ABCDEF1234567890ABCDEF12")

    def test_invalid_no_prefix(self):
        """Test invalid address without 0x prefix."""
        assert not validate_eth_address("1234567890abcdef1234567890abcdef12345678")

    def test_invalid_wrong_length(self):
        """Test invalid address with wrong length."""
        assert not validate_eth_address("0x123")
        assert not validate_eth_address("0x1234567890abcdef1234567890abcdef1234567890")

    def test_invalid_characters(self):
        """Test invalid address with non-hex characters."""
        assert not validate_eth_address("0xGGGG567890abcdef1234567890abcdef12345678")

    def test_empty_address(self):
        """Test empty address."""
        assert not validate_eth_address("")
        assert not validate_eth_address(None)


class TestChunkList:
    """Tests for list chunking."""

    def test_chunk_even(self):
        """Test chunking list with even division."""
        lst = [1, 2, 3, 4, 5, 6]
        chunks = chunk_list(lst, 2)

        assert len(chunks) == 3
        assert chunks[0] == [1, 2]
        assert chunks[1] == [3, 4]
        assert chunks[2] == [5, 6]

    def test_chunk_uneven(self):
        """Test chunking list with uneven division."""
        lst = [1, 2, 3, 4, 5]
        chunks = chunk_list(lst, 2)

        assert len(chunks) == 3
        assert chunks[2] == [5]

    def test_chunk_empty(self):
        """Test chunking empty list."""
        chunks = chunk_list([], 2)

        assert chunks == []

    def test_chunk_larger_than_list(self):
        """Test chunk size larger than list."""
        lst = [1, 2, 3]
        chunks = chunk_list(lst, 10)

        assert len(chunks) == 1
        assert chunks[0] == [1, 2, 3]


class TestRateLimiter:
    """Tests for rate limiter."""

    @pytest.mark.asyncio
    async def test_rate_limiter_allows_within_limit(self):
        """Test that rate limiter allows calls within limit."""
        limiter = RateLimiter(max_calls=5, period_seconds=1.0)

        for _ in range(5):
            await limiter.acquire()

        # Should complete without delay

    @pytest.mark.asyncio
    async def test_rate_limiter_context_manager(self):
        """Test rate limiter as context manager."""
        limiter = RateLimiter(max_calls=2, period_seconds=1.0)

        async with limiter:
            pass

        async with limiter:
            pass


class TestTimer:
    """Tests for Timer context manager."""

    def test_timer_sync(self):
        """Test timer in sync context."""
        import time

        with Timer("test") as timer:
            time.sleep(0.1)

        assert timer.elapsed >= 0.1
        assert timer.elapsed < 0.2

    @pytest.mark.asyncio
    async def test_timer_async(self):
        """Test timer in async context."""
        import asyncio

        async with Timer("test") as timer:
            await asyncio.sleep(0.1)

        assert timer.elapsed >= 0.1
        assert timer.elapsed < 0.2
