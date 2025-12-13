"""Helper functions for CSV operations using DuckDB."""

import json
from contextlib import contextmanager
from typing import Dict, List, Optional

import duckdb


@contextmanager
def duckdb_connection():
    """
    Context manager for DuckDB connections.
    
    Ensures connections are properly closed even if exceptions occur.
    """
    con = duckdb.connect()
    try:
        yield con
    finally:
        con.close()


def get_column_mapping(csv_path: str) -> Dict[str, str]:
    """
    Get the canonical to actual column mapping from the CSV.
    
    Args:
        csv_path: Path to the output CSV file
        
    Returns:
        Dictionary mapping canonical column names to actual column names
    """
    with duckdb_connection() as con:
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


def build_where_clause(filters: Dict, column_mapping: Optional[Dict[str, str]] = None) -> tuple:
    """
    Build WHERE clause and parameters for DuckDB query.
    
    Args:
        filters: Dictionary of filter conditions (l1, confidence, supplier_name)
        column_mapping: Optional mapping from canonical to actual column names
        
    Returns:
        Tuple of (where_clause_string, params_list)
    """
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
        actual_col = (column_mapping or {}).get('supplier_name', 'Supplier')
        where_clauses.append(f'LOWER("{actual_col}") = LOWER(?)')
        params.append(filters['supplier_name'])
    
    where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    return where_clause, params

