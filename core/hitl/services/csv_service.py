"""CSV service for operations using DuckDB."""

from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from core.utils.data.csv_helpers import (
    build_where_clause,
    duckdb_connection,
    get_column_mapping,
)


class CSVService:
    """Service for CSV operations using DuckDB."""

    def query_transactions(
        self,
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
        column_mapping = get_column_mapping(csv_path)

        # Build WHERE clause
        where_clause, params = build_where_clause(filters, column_mapping)

        # Calculate offset
        offset = (page - 1) * limit

        # Query with DuckDB
        with duckdb_connection() as con:
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

        return {
            'rows': result_df.to_dict('records'),
            'total': total,
            'page': page,
            'pages': (total + limit - 1) // limit,  # Ceiling division
            'limit': limit
        }

    def get_transaction_by_index(self, csv_path: str, row_index: int) -> Optional[Dict]:
        """
        Get a single transaction row by index from CSV.

        Args:
            csv_path: Path to the output CSV file
            row_index: Row index (0-based)

        Returns:
            Row as dictionary, or None if not found
        """
        with duckdb_connection() as con:
            query = "SELECT * FROM read_csv_auto(?) LIMIT 1 OFFSET ?"
            result_df = con.execute(query, [csv_path, row_index]).fetchdf()

        if result_df.empty:
            return None

        return result_df.iloc[0].to_dict()

    def list_available_datasets(self) -> List[Dict]:
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
            try:
                with duckdb_connection() as con:
                    count_query = "SELECT COUNT(*) as count FROM read_csv_auto(?)"
                    row_count = con.execute(count_query, [str(output_csv)]).fetchone()[0]
            except Exception:
                row_count = 0

            datasets.append({
                'csv_path': str(output_csv),
                'dataset_name': dataset_name,
                'foldername': foldername,
                'row_count': row_count
            })

        return datasets

    def find_rows_by_supplier(self, csv_path: str, supplier_name: str) -> List[Dict]:
        """
        Find all rows for a specific supplier.

        Args:
            csv_path: Path to the output CSV file (can be local path or S3 URI)
            supplier_name: Supplier name to search for

        Returns:
            List of row dictionaries and their indices
        """
        # Get column mapping to use actual column name
        column_mapping = get_column_mapping(csv_path)
        actual_col = column_mapping.get('supplier_name', 'Supplier')

        with duckdb_connection() as con:
            query = f"""
                SELECT *, row_number() OVER () - 1 as row_idx
                FROM read_csv_auto(?)
                WHERE LOWER("{actual_col}") = LOWER(?)
            """
            result_df = con.execute(query, [csv_path, supplier_name]).fetchdf()

        return result_df.to_dict('records')

    def find_rows_by_condition(
        self,
        csv_path: str,
        condition_field: str,
        condition_value: str
    ) -> List[Dict]:
        """
        Find all rows matching a transaction rule condition.

        Args:
            csv_path: Path to the output CSV file
            condition_field: Field name to match (e.g., "gl_code")
            condition_value: Value to match

        Returns:
            List of row dictionaries and their indices
        """
        # Dynamically build query - be careful with SQL injection
        # We trust condition_field comes from validated rule creation
        with duckdb_connection() as con:
            query = f"""
                SELECT *, row_number() OVER () - 1 as row_idx
                FROM read_csv_auto(?)
                WHERE "{condition_field}" = ?
            """
            result_df = con.execute(query, [csv_path, condition_value]).fetchdf()

        return result_df.to_dict('records')

    def update_rows(
        self,
        csv_path: str,
        row_indices: List[int],
        updates: Dict
    ) -> int:
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
                "update_rows does not support S3 URIs. "
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

