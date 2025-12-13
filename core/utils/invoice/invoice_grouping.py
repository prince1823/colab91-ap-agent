"""Invoice grouping utilities for transaction processing."""

import logging
from typing import Dict, List, Optional, Tuple
import pandas as pd

from core.utils.invoice.invoice_config import DEFAULT_CONFIG

logger = logging.getLogger(__name__)


def validate_grouping_columns(canonical_df: pd.DataFrame, grouping_columns: List[str]) -> None:
    """
    Validate that all required grouping columns exist in the DataFrame.

    Args:
        canonical_df: DataFrame to validate
        grouping_columns: List of required column names

    Raises:
        ValueError: If any required columns are missing
    """
    missing_cols = [col for col in grouping_columns if col not in canonical_df.columns]
    if missing_cols:
        raise ValueError(
            f"Missing required grouping columns: {missing_cols}. "
            f"Available columns: {list(canonical_df.columns)}"
        )


def create_invoice_key(row_dict: Dict, grouping_columns: List[str]) -> str:
    """
    Create a normalized invoice key from grouping columns.

    Args:
        row_dict: Transaction data dictionary
        grouping_columns: List of column names to group by

    Returns:
        Normalized invoice key (pipe-separated values)
    """
    key_parts = []
    for col in grouping_columns:
        value = row_dict.get(col)
        # Normalize: handle None, NaN, empty strings
        if value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == '':
            normalized = '<NULL>'
        else:
            # Normalize to lowercase string, strip whitespace
            normalized = str(value).lower().strip()
        key_parts.append(normalized)

    return '|'.join(key_parts)


def group_transactions_by_invoice(
    canonical_df: pd.DataFrame,
    grouping_columns: Optional[List[str]] = None
) -> Dict[str, List[Tuple[int, int, Dict]]]:
    """
    Group transactions into invoices.

    Args:
        canonical_df: DataFrame with canonical columns
        grouping_columns: Columns to group by
            If None, uses default from InvoiceProcessingConfig
            Default: ['invoice_date', 'company', 'supplier_name', 'creation_date']

    Returns:
        Dictionary mapping invoice_key to list of (position, df_index, row_dict) tuples
    """
    if grouping_columns is None:
        # Use default from configuration
        grouping_columns = DEFAULT_CONFIG.default_grouping_columns

    # Validate that all required columns exist
    validate_grouping_columns(canonical_df, grouping_columns)

    invoices = {}

    for pos, (df_idx, row) in enumerate(canonical_df.iterrows()):
        row_dict = row.to_dict()

        # Create invoice key
        invoice_key = create_invoice_key(row_dict, grouping_columns)

        # Add to invoice group
        if invoice_key not in invoices:
            invoices[invoice_key] = []

        invoices[invoice_key].append((pos, df_idx, row_dict))

    # Filter out empty invoice groups (shouldn't happen, but safety check)
    invoices = {k: v for k, v in invoices.items() if v}

    logger.info(f"Grouped {len(canonical_df)} rows into {len(invoices)} invoices (avg {len(canonical_df)/len(invoices):.1f} rows/invoice)")

    return invoices
