"""CSV operations using DuckDB for HITL."""

import json
from pathlib import Path
from typing import Dict, List, Optional

import duckdb
import pandas as pd


def _get_column_mapping(csv_path: str) -> Dict[str, str]:
    """
    Get the canonical to actual column mapping from the CSV.

    Args:
        csv_path: Path to the output CSV file

    Returns:
        Dictionary mapping canonical column names to actual column names
    """
    con = duckdb.connect()
    try:
        # Get columns_used from first row
        result = con.execute(
            "SELECT columns_used FROM read_csv_auto(?) LIMIT 1",
            [csv_path]
        ).fetchone()

        if result and result[0]:
            return json.loads(result[0])
        return {}
    except Exception:
        # Fallback to empty mapping if columns_used doesn't exist
        return {}
    finally:
        con.close()


def query_classified_transactions(
    csv_path: str,
    filters: Optional[Dict] = None,
    page: int = 1,
    limit: int = 50
) -> Dict:
    """
    Query classified transactions from CSV using DuckDB.

    Args:
        csv_path: Path to the output CSV file
        filters: Optional filters (l1, confidence, supplier_name)
        page: Page number (1-indexed)
        limit: Number of rows per page

    Returns:
        Dictionary with rows, total count, and page info
    """
    filters = filters or {}

    # Get column mapping to use actual column names
    column_mapping = _get_column_mapping(csv_path)

    # Build WHERE clause
    where_clauses = []
    params = []

    if filters.get('l1'):
        where_clauses.append("L1 = ?")
        params.append(filters['l1'])

    if filters.get('confidence'):
        where_clauses.append("confidence = ?")
        params.append(filters['confidence'])

    if filters.get('supplier_name'):
        # Use canonicalized column mapping to get the actual column name
        actual_col = column_mapping.get('supplier_name', 'Supplier')
        where_clauses.append(f'LOWER("{actual_col}") = LOWER(?)')
        params.append(filters['supplier_name'])

    where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    # Calculate offset
    offset = (page - 1) * limit

    # Query with DuckDB
    con = duckdb.connect()

    # Get total count
    count_query = f"SELECT COUNT(*) as total FROM read_csv_auto(?) {where_clause}"
    total = con.execute(count_query, [csv_path] + params).fetchone()[0]

    # Get paginated rows
    data_query = f"""
        SELECT * FROM read_csv_auto(?)
        {where_clause}
        LIMIT ? OFFSET ?
    """
    result_df = con.execute(data_query, [csv_path] + params + [limit, offset]).fetchdf()

    con.close()

    return {
        'rows': result_df.to_dict('records'),
        'total': total,
        'page': page,
        'pages': (total + limit - 1) // limit,  # Ceiling division
        'limit': limit
    }


def get_transaction_by_row_index(csv_path: str, row_index: int) -> Optional[Dict]:
    """
    Get a single transaction row by index from CSV.

    Args:
        csv_path: Path to the output CSV file
        row_index: Row index (0-based)

    Returns:
        Row as dictionary, or None if not found
    """
    con = duckdb.connect()

    query = "SELECT * FROM read_csv_auto(?) LIMIT 1 OFFSET ?"
    result_df = con.execute(query, [csv_path, row_index]).fetchdf()

    con.close()

    if result_df.empty:
        return None

    return result_df.iloc[0].to_dict()


def list_available_datasets() -> List[Dict]:
    """
    List available datasets by scanning benchmarks directory.

    DEPRECATED: Use DatasetService.list_datasets() instead.

    Returns:
        List of dataset info dicts with csv_path, dataset_name, foldername, row_count
    """
    benchmarks_dir = Path("benchmarks")

    if not benchmarks_dir.exists():
        return []

    datasets = []

    # Scan for */*/output.csv pattern
    for output_csv in benchmarks_dir.glob("*/*/output.csv"):
        folder_path = output_csv.parent
        dataset_name = folder_path.name
        foldername = folder_path.parent.name

        # Get row count using DuckDB
        con = duckdb.connect()
        try:
            count_query = "SELECT COUNT(*) as count FROM read_csv_auto(?)"
            row_count = con.execute(count_query, [str(output_csv)]).fetchone()[0]
        except Exception:
            row_count = 0
        finally:
            con.close()

        datasets.append({
            'csv_path': str(output_csv),
            'dataset_name': dataset_name,
            'foldername': foldername,
            'row_count': row_count
        })

    return datasets


def find_rows_by_supplier(csv_path: str, supplier_name: str) -> List[Dict]:
    """
    Find all rows for a specific supplier.

    Args:
        csv_path: Path to the output CSV file (can be local path or S3 URI)
        supplier_name: Supplier name to search for

    Returns:
        List of row dictionaries and their indices
    """
    con = duckdb.connect()

    # Get column mapping to use actual column name
    column_mapping = _get_column_mapping(csv_path)
    actual_col = column_mapping.get('supplier_name', 'Supplier')

    query = f"""
        SELECT *, row_number() OVER () - 1 as row_idx
        FROM read_csv_auto(?)
        WHERE LOWER("{actual_col}") = LOWER(?)
    """
    result_df = con.execute(query, [csv_path, supplier_name]).fetchdf()

    con.close()

    return result_df.to_dict('records')


def find_rows_by_condition(csv_path: str, condition_field: str, condition_value: str) -> List[Dict]:
    """
    Find all rows matching a transaction rule condition.

    Args:
        csv_path: Path to the output CSV file
        condition_field: Field name to match (e.g., "gl_code")
        condition_value: Value to match

    Returns:
        List of row dictionaries and their indices
    """
    con = duckdb.connect()

    # Dynamically build query - be careful with SQL injection
    # We trust condition_field comes from validated rule creation
    query = f"""
        SELECT *, row_number() OVER () - 1 as row_idx
        FROM read_csv_auto(?)
        WHERE "{condition_field}" = ?
    """
    result_df = con.execute(query, [csv_path, condition_value]).fetchdf()

    con.close()

    return result_df.to_dict('records')


def update_csv_rows(csv_path: str, row_indices: List[int], updates: Dict) -> int:
    """
    Update specific rows in the CSV file.

    NOTE: This function works with local file paths. For S3 URIs, use DatasetService.update_transactions() instead.

    Args:
        csv_path: Path to the output CSV file (local path only, not S3 URI)
        row_indices: List of row indices to update (0-based)
        updates: Dictionary of column: value pairs to update

    Returns:
        Number of rows updated

    Raises:
        ValueError: If csv_path is an S3 URI (use DatasetService instead)
    """
    # Check if this is an S3 URI
    if csv_path.startswith("s3://"):
        raise ValueError(
            "update_csv_rows does not support S3 URIs. "
            "Use DatasetService.update_transactions() with dataset_id and foldername instead."
        )

    # Read CSV with pandas
    df = pd.read_csv(csv_path)

    # Update specified rows
    for idx in row_indices:
        if idx < len(df):
            for col, value in updates.items():
                df.at[idx, col] = value

    # Write back to CSV
    df.to_csv(csv_path, index=False)

    return len([idx for idx in row_indices if idx < len(df)])
