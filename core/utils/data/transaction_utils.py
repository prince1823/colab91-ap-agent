"""Utility functions for transaction data processing."""

from typing import Any, Dict

import pandas as pd


def is_valid_value(value: Any) -> bool:
    """
    Check if value is valid and not empty.
    
    Args:
        value: Value to check
        
    Returns:
        True if value is valid and non-empty, False otherwise
    """
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        # Not a pandas type, check if it's a valid string
        pass
    return bool(str(value).strip())

