"""Helper utilities."""

import asyncio
import hashlib
import logging
import time
from datetime import datetime
from functools import wraps
from typing import Any, Callable, TypeVar

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


def generate_job_id(token_address: str, timestamp: datetime = None) -> str:
    """Generate a unique job ID."""
    timestamp = timestamp or datetime.utcnow()
    data = f"{token_address.lower()}:{timestamp.isoformat()}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def format_number(value: float, decimals: int = 2) -> str:
    """Format number with K/M/B suffix."""
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.{decimals}f}B"
    elif value >= 1_000_000:
        return f"{value / 1_000_000:.{decimals}f}M"
    elif value >= 1_000:
        return f"{value / 1_000:.{decimals}f}K"
    else:
        return f"{value:.{decimals}f}"


def retry_async(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exceptions: tuple = (Exception,),
):
    """Decorator for retrying async functions with exponential backoff."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            delay = base_delay

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}/{max_attempts}): {e}"
                        )
                        await asyncio.sleep(delay)
                        delay = min(delay * 2, max_delay)
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts: {e}"
                        )

            raise last_exception

        return wrapper
    return decorator


class RateLimiter:
    """Simple rate limiter."""

    def __init__(self, max_calls: int, period_seconds: float):
        self.max_calls = max_calls
        self.period = period_seconds
        self._calls: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait if rate limit is exceeded."""
        async with self._lock:
            now = time.time()

            # Remove old calls
            self._calls = [t for t in self._calls if now - t < self.period]

            if len(self._calls) >= self.max_calls:
                # Wait until oldest call expires
                sleep_time = self.period - (now - self._calls[0])
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    self._calls = self._calls[1:]

            self._calls.append(time.time())

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, *args):
        pass


class Timer:
    """Context manager for timing operations."""

    def __init__(self, name: str = "Operation"):
        self.name = name
        self.start_time: Optional[float] = None
        self.elapsed: float = 0

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, *args):
        self.elapsed = time.time() - self.start_time
        logger.debug(f"{self.name} took {self.elapsed:.3f}s")

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, *args):
        return self.__exit__(*args)


def chunk_list(lst: list, chunk_size: int) -> list[list]:
    """Split a list into chunks."""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def validate_eth_address(address: str) -> bool:
    """Validate Ethereum address format."""
    if not address:
        return False
    if not address.startswith("0x"):
        return False
    if len(address) != 42:
        return False
    try:
        int(address, 16)
        return True
    except ValueError:
        return False
