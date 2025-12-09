"""Invoice grouping utilities for transaction processing."""

import logging
from typing import Dict, List, Tuple
import pandas as pd

logger = logging.getLogger(__name__)


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
    grouping_columns: List[str] = None
) -> Dict[str, List[Tuple[int, int, Dict]]]:
    """
    Group transactions into invoices.

    Args:
        canonical_df: DataFrame with canonical columns
        grouping_columns: Columns to group by
            Default: ['invoice_date', 'company', 'supplier_name', 'creation_date']
            TODO: Make this configurable via config file

    Returns:
        Dictionary mapping invoice_key to list of (position, df_index, row_dict) tuples
    """
    if grouping_columns is None:
        # TODO: Make this configurable via config file
        grouping_columns = ['invoice_date', 'company', 'supplier_name', 'creation_date']

    invoices = {}

    for pos, (df_idx, row) in enumerate(canonical_df.iterrows()):
        row_dict = row.to_dict()

        # Create invoice key
        invoice_key = create_invoice_key(row_dict, grouping_columns)

        # Add to invoice group
        if invoice_key not in invoices:
            invoices[invoice_key] = []

        invoices[invoice_key].append((pos, df_idx, row_dict))

    logger.info(f"Grouped {len(canonical_df)} rows into {len(invoices)} invoices (avg {len(canonical_df)/len(invoices):.1f} rows/invoice)")

    return invoices
