"""Retry utilities for LLM calls and other operations."""

import logging
import time
from functools import wraps
from typing import Callable, TypeVar, Optional

logger = logging.getLogger(__name__)

T = TypeVar('T')


def is_rate_limit_error(exception: Exception) -> bool:
    """
    Check if an exception is a rate limit/quota error that should not be retried.
    
    Args:
        exception: Exception to check
        
    Returns:
        True if this is a rate limit error that should not be retried
    """
    error_str = str(exception).lower()
    error_type = type(exception).__name__.lower()
    
    # Check for rate limit indicators
    rate_limit_indicators = [
        'ratelimiterror',
        'rate limit',
        'quota',
        'exceeded your current quota',
        'billing',
        'insufficient credits',
        '402',  # Payment required
        '429',  # Too many requests
    ]
    
    return any(indicator in error_str or indicator in error_type for indicator in rate_limit_indicators)


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,),
    log_errors: bool = True,
    skip_rate_limit_errors: bool = True
):
    """
    Decorator for retrying functions with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry
        backoff_factor: Multiplier for delay between retries
        exceptions: Tuple of exceptions to catch and retry on
        log_errors: Whether to log retry attempts
        skip_rate_limit_errors: If True, don't retry rate limit/quota errors (default: True)

    Returns:
        Decorated function
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            delay = initial_delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    # Don't retry rate limit/quota errors - they're not transient
                    if skip_rate_limit_errors and is_rate_limit_error(e):
                        if log_errors:
                            logger.error(
                                f"{func.__name__} hit rate limit/quota error (not retrying): {e}"
                            )
                        raise e  # Re-raise immediately without retrying
                    
                    if attempt < max_retries:
                        if log_errors:
                            logger.warning(
                                f"{func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                                f"Retrying in {delay:.2f}s..."
                            )
                        time.sleep(delay)
                        delay *= backoff_factor
                    else:
                        if log_errors:
                            logger.error(
                                f"{func.__name__} failed after {max_retries + 1} attempts: {e}"
                            )

            # If we get here, all retries failed
            raise last_exception

        return wrapper
    return decorator

