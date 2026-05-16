"""
Exchange client factory with retry logic.
==========================================

Bot contributed:
- retry_on_error decorator with exponential backoff
- Transient vs critical error classification
- ExchangeClientFactory with get_exchange_client()
- BinanceTestnetClient wrapper

Adapted:
- Factory returns ExchangeAdapter instances instead of raw clients
- Removed BinanceTestnetClient (use ExchangeAdapter pattern instead)
"""

import functools
import logging
import time
from typing import Any, Callable, Optional, Type

logger = logging.getLogger(__name__)

TRANSIENT_ERROR_PATTERNS = (
    "rate limit",
    "rate_limit",
    "429",
    "timeout",
    "timed out",
    "connection",
    "ConnectionError",
    "ConnectionResetError",
    "ConnectionAbortedError",
    "BrokenPipeError",
    "Too Many Requests",
    "HTTP 5",
    "Internal Server Error",
    "Bad Gateway",
    "Service Unavailable",
    "Gateway Timeout",
    "temporary",
    "retry",
    "overload",
)


def is_transient_error(exc: Exception) -> bool:
    exc_str = str(exc).lower()
    exc_type = type(exc).__name__.lower()
    for pattern in TRANSIENT_ERROR_PATTERNS:
        if pattern.lower() in exc_str or pattern.lower() in exc_type:
            return True
    return False


def retry_on_error(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    transient_only: bool = True,
    on_retry: Optional[Callable[[Exception, int], None]] = None,
) -> Callable:
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Optional[Exception] = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if transient_only and not is_transient_error(exc):
                        logger.error(
                            "Non-transient error in %s (attempt %d/%d): %s",
                            func.__name__,
                            attempt + 1,
                            max_retries + 1,
                            exc,
                        )
                        raise

                    if attempt < max_retries:
                        delay = min(base_delay * (backoff_factor**attempt), max_delay)
                        logger.warning(
                            "Retry %d/%d for %s in %.1fs: %s",
                            attempt + 1,
                            max_retries,
                            func.__name__,
                            delay,
                            exc,
                        )
                        if on_retry:
                            on_retry(exc, attempt + 1)
                        time.sleep(delay)
                    else:
                        logger.error(
                            "All %d retries exhausted for %s: %s",
                            max_retries,
                            func.__name__,
                            exc,
                        )

            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator


class ExchangeClientFactory:
    """Factory for creating ExchangeAdapter instances with retry-wrapped methods."""

    _adapter_cache: Optional[Any] = None

    @classmethod
    def get_exchange_adapter(cls) -> Any:
        if cls._adapter_cache is not None:
            return cls._adapter_cache

        from .exchange_adapter import create_exchange_adapter

        adapter = create_exchange_adapter()
        cls._wrap_with_retry(adapter)
        cls._adapter_cache = adapter
        return adapter

    @classmethod
    def _wrap_with_retry(cls, adapter: Any) -> None:
        for method_name in (
            "get_balance",
            "place_order",
            "cancel_order",
            "get_order",
            "get_ticker",
            "borrow",
            "repay",
            "get_margin_info",
        ):
            original = getattr(adapter, method_name, None)
            if original is not None:
                wrapped = retry_on_error(
                    max_retries=3,
                    base_delay=1.0,
                    transient_only=True,
                )(original)
                setattr(adapter, method_name, wrapped)

    @classmethod
    def reset_cache(cls) -> None:
        cls._adapter_cache = None


def get_exchange_adapter() -> Any:
    return ExchangeClientFactory.get_exchange_adapter()
