"""Validation utilities for classification workflow."""

import re
from typing import List, Dict, Any, Set

from core.agents.column_canonicalization.canonical_columns import CANONICAL_COLUMNS
from core.classification.exceptions import InvalidColumnError, CSVIntegrityError, InvalidStateTransitionError
import pandas as pd


# Required canonical columns that cannot be removed
REQUIRED_CANONICAL_COLUMNS: Set[str] = {
    'supplier_name',  # Critical for classification
    'amount',  # Critical for spend analysis
}

# Valid canonical column names (from schema)
VALID_CANONICAL_COLUMNS: Set[str] = {col.canonical_name for col in CANONICAL_COLUMNS}

# Valid state transitions
VALID_STATE_TRANSITIONS = {
    'pending': {'canonicalizing'},
    'canonicalizing': {'canonicalized', 'failed'},
    'canonicalized': {'awaiting_verification', 'pending'},  # Can reset to pending on rejection
    'awaiting_verification': {'verified', 'pending'},  # Can reset to pending on rejection
    'verified': {'classifying', 'pending'},  # Can reset if needed
    'classifying': {'completed', 'failed'},
    'completed': set(),  # Terminal state
    'failed': {'pending'},  # Can retry from pending
}


def validate_column_name(column_name: str) -> None:
    """
    Validate that a column name is safe and valid.
    
    Args:
        column_name: Column name to validate
        
    Raises:
        InvalidColumnError: If column name is invalid
    """
    if not column_name or not isinstance(column_name, str):
        raise InvalidColumnError(f"Column name must be a non-empty string, got: {type(column_name)}")
    
    # Check for path traversal
    if '..' in column_name or '/' in column_name or '\\' in column_name:
        raise InvalidColumnError(f"Column name contains invalid characters: {column_name}")
    
    # Check for control characters
    if any(ord(c) < 32 and c not in '\t\n\r' for c in column_name):
        raise InvalidColumnError(f"Column name contains control characters: {column_name}")
    
    # Check length
    if len(column_name) > 255:
        raise InvalidColumnError(f"Column name too long (max 255): {len(column_name)}")
    
    # Check for valid characters (alphanumeric, underscore, hyphen, space)
    if not re.match(r'^[a-zA-Z0-9_\-\s]+$', column_name):
        raise InvalidColumnError(f"Column name contains invalid characters: {column_name}")


def validate_canonical_column_name(canonical_name: str) -> None:
    """
    Validate that a canonical column name is in the allowed schema.
    
    Args:
        canonical_name: Canonical column name to validate
        
    Raises:
        InvalidColumnError: If canonical name is not valid
    """
    validate_column_name(canonical_name)
    
    if canonical_name not in VALID_CANONICAL_COLUMNS:
        raise InvalidColumnError(
            f"Invalid canonical column name: {canonical_name}. "
            f"Must be one of: {sorted(VALID_CANONICAL_COLUMNS)}"
        )


def validate_column_modifications(
    columns_to_add: List[Dict[str, Any]],
    columns_to_remove: List[str],
    existing_columns: Set[str]
) -> None:
    """
    Validate column modifications (add/remove).
    
    Args:
        columns_to_add: List of columns to add
        columns_to_remove: List of columns to remove
        existing_columns: Set of existing canonical column names
        
    Raises:
        InvalidColumnError: If modifications are invalid
    """
    # Validate columns to add
    if columns_to_add:
        for col_spec in columns_to_add:
            canonical_name = col_spec.get('canonical_name')
            if not canonical_name:
                raise InvalidColumnError("Each column to add must have 'canonical_name'")
            
            validate_canonical_column_name(canonical_name)
            
            # Check if already exists
            if canonical_name in existing_columns:
                raise InvalidColumnError(
                    f"Cannot add column '{canonical_name}': already exists"
                )
    
    # Validate columns to remove
    if columns_to_remove:
        for col_name in columns_to_remove:
            validate_canonical_column_name(col_name)
            
            # Check if exists
            if col_name not in existing_columns:
                raise InvalidColumnError(
                    f"Cannot remove column '{col_name}': does not exist"
                )
            
            # Check if required
            if col_name in REQUIRED_CANONICAL_COLUMNS:
                raise InvalidColumnError(
                    f"Cannot remove required column '{col_name}'. "
                    f"Required columns: {REQUIRED_CANONICAL_COLUMNS}"
                )


def validate_state_transition(current_status: str, new_status: str) -> None:
    """
    Validate that a state transition is allowed.
    
    Args:
        current_status: Current workflow status
        new_status: Desired new status
        
    Raises:
        InvalidStateTransitionError: If transition is not allowed
    """
    allowed_transitions = VALID_STATE_TRANSITIONS.get(current_status, set())
    
    if new_status not in allowed_transitions:
        raise InvalidStateTransitionError(
            f"Cannot transition from '{current_status}' to '{new_status}'. "
            f"Allowed transitions: {allowed_transitions}"
        )


def validate_canonicalized_csv(df: pd.DataFrame) -> None:
    """
    Validate canonicalized CSV integrity.
    
    Args:
        df: DataFrame to validate
        
    Raises:
        CSVIntegrityError: If CSV is invalid
    """
    if df is None or df.empty:
        raise CSVIntegrityError("Canonicalized CSV is empty or None")
    
    # Check required columns
    missing_required = REQUIRED_CANONICAL_COLUMNS - set(df.columns)
    if missing_required:
        raise CSVIntegrityError(
            f"Missing required columns: {missing_required}. "
            f"Required columns: {REQUIRED_CANONICAL_COLUMNS}"
        )
    
    # Check for null supplier_name (critical column)
    if 'supplier_name' in df.columns:
        null_supplier_count = df['supplier_name'].isna().sum()
        if null_supplier_count > 0:
            # Warning, not error - some rows might legitimately have null suppliers
            # But log it
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Found {null_supplier_count} rows with null supplier_name. "
                f"This may cause classification issues."
            )
    
    # Check for null amount (critical column)
    if 'amount' in df.columns:
        null_amount_count = df['amount'].isna().sum()
        if null_amount_count == len(df):
            raise CSVIntegrityError(
                "All rows have null amount. Cannot proceed with classification."
            )
    
    # Validate data types (basic checks)
    if 'amount' in df.columns:
        # Try to convert to numeric, catch errors
        try:
            pd.to_numeric(df['amount'], errors='coerce')
        except Exception as e:
            raise CSVIntegrityError(f"Invalid amount column: {e}")
    
    # Check for duplicate column names
    if len(df.columns) != len(set(df.columns)):
        duplicates = [col for col in df.columns if df.columns.tolist().count(col) > 1]
        raise CSVIntegrityError(f"Duplicate column names found: {set(duplicates)}")

