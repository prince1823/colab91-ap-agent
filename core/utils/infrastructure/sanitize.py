"""Utilities for sanitizing sensitive data in logs."""

from typing import Optional


def sanitize_invoice_key(key: str, max_length: int = 100) -> str:
    """
    Sanitize invoice key for logging.

    Args:
        key: Invoice key to sanitize
        max_length: Maximum length to return

    Returns:
        Sanitized invoice key
    """
    if not key:
        return ""
    
    # Truncate long keys
    if len(key) > max_length:
        return key[:max_length] + "..."
    
    return key


def sanitize_for_logging(value: Optional[str], max_length: int = 200) -> str:
    """
    Sanitize any string value for logging.

    Args:
        value: Value to sanitize
        max_length: Maximum length to return

    Returns:
        Sanitized string
    """
    if value is None:
        return ""
    
    value_str = str(value)
    if len(value_str) > max_length:
        return value_str[:max_length] + "..."
    
    return value_str

