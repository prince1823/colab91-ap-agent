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


def format_transaction_data(
    transaction_data: Dict,
    priority_fields: Dict[str, str],
    secondary_fields: Dict[str, str] = None,
) -> str:
    """
    Format transaction data to emphasize relevant fields.
    
    Args:
        transaction_data: Transaction data dictionary
        priority_fields: Dictionary mapping field keys to display labels for priority fields
        secondary_fields: Optional dictionary mapping field keys to display labels for secondary fields
        
    Returns:
        Formatted string representation of transaction data
    """
    if secondary_fields is None:
        secondary_fields = {}
    
    formatted_parts = []
    
    # Add priority fields first
    formatted_parts.append("PRIMARY TRANSACTION DATA:")
    for key, label in priority_fields.items():
        value = transaction_data.get(key)
        if is_valid_value(value):
            formatted_parts.append(f"  {label}: {value}")
    
    # Add secondary fields if available
    has_secondary = any(
        is_valid_value(transaction_data.get(k))
        for k in secondary_fields.keys()
    )
    if has_secondary:
        formatted_parts.append("\nADDITIONAL CONTEXT:")
        for key, label in secondary_fields.items():
            value = transaction_data.get(key)
            if is_valid_value(value):
                formatted_parts.append(f"  {label}: {value}")
    
    return "\n".join(formatted_parts) if formatted_parts else "No transaction details available"

