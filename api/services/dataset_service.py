"""Dataset service for managing datasets with storage abstraction."""

from typing import Any, Dict, List, Optional

import pandas as pd

from api.exceptions import DatasetNotFoundError, InvalidDatasetIdError, TransactionNotFoundError
from api.storage.base import StorageBackend
from api.storage.factory import get_storage_backend


class DatasetService:
    """Manages datasets with configurable storage backend."""

    def __init__(self, storage: Optional[StorageBackend] = None):
        """
        Initialize dataset service.

        Args:
            storage: Optional storage backend. If None, uses configured backend.
        """
        self.storage = storage or get_storage_backend()

    def get_output_csv_path(self, dataset_id: str, foldername: str = "default") -> str:
        """
        Get CSV path/URI for dataset.

        Args:
            dataset_id: Dataset identifier
            foldername: Folder name

        Returns:
            CSV path or URI string

        Raises:
            HTTPException: If dataset not found
        """
        try:
            if not self.storage.exists(dataset_id, foldername):
                raise DatasetNotFoundError(f"Dataset '{dataset_id}' not found in folder '{foldername}'")

            return self.storage.get_csv_path_or_uri(dataset_id, foldername)
        except ValueError as e:
            raise InvalidDatasetIdError(str(e)) from e
        except FileNotFoundError as e:
            raise DatasetNotFoundError(str(e)) from e

    def read_transaction(self, dataset_id: str, row_index: int, foldername: str = "default") -> Dict:
        """
        Read a single transaction from dataset.

        Args:
            dataset_id: Dataset identifier
            row_index: Row index (0-based)
            foldername: Folder name

        Returns:
            Transaction data as dictionary

        Raises:
            HTTPException: If dataset or transaction not found
        """
        try:
            df = self.storage.read_csv(dataset_id, foldername)

            if row_index >= len(df):
                raise TransactionNotFoundError(f"Transaction at row {row_index} not found")

            return df.iloc[row_index].to_dict()
        except FileNotFoundError as e:
            raise DatasetNotFoundError(str(e)) from e
        except ValueError as e:
            raise InvalidDatasetIdError(str(e)) from e

    def update_transactions(
        self, dataset_id: str, updates: List[Dict], foldername: str = "default"
    ) -> int:
        """
        Update multiple transactions in dataset.

        Args:
            dataset_id: Dataset identifier
            updates: List of update dicts with 'row_index' and 'fields'
            foldername: Folder name

        Returns:
            Number of transactions updated

        Raises:
            HTTPException: If dataset not found
        """
        try:
            df = self.storage.read_csv(dataset_id, foldername)

            updated_count = 0
            for update in updates:
                row_index = update.get("row_index")
                if row_index is None:
                    continue

                if row_index < len(df):
                    fields = update.get("fields", {})
                    for col, value in fields.items():
                        df.at[row_index, col] = value
                    updated_count += 1

            if updated_count > 0:
                self.storage.write_csv(dataset_id, df, foldername)

            return updated_count
        except FileNotFoundError as e:
            raise DatasetNotFoundError(str(e)) from e
        except ValueError as e:
            raise InvalidDatasetIdError(str(e)) from e

    def list_datasets(self, foldername: Optional[str] = None) -> List[Dict]:
        """
        List available datasets.

        Args:
            foldername: Optional folder name to filter by

        Returns:
            List of dataset info dicts
        """
        return self.storage.list_datasets(foldername)

    def create_dataset(
        self,
        dataset_id: str,
        transactions_df: pd.DataFrame,
        taxonomy_data: Dict[str, Any],
        foldername: str = "default",
        csv_filename: Optional[str] = None
    ) -> Dict:
        """
        Create a new dataset with transactions CSV and taxonomy YAML.

        Args:
            dataset_id: Dataset identifier
            transactions_df: DataFrame with transaction data
            taxonomy_data: Dictionary with taxonomy structure
            foldername: Folder name

        Returns:
            Dictionary with dataset info

        Raises:
            ValueError: If dataset already exists or data is invalid
        """
        if self.storage.exists(dataset_id, foldername):
            raise ValueError(f"Dataset '{dataset_id}' already exists in folder '{foldername}'")

        # Write CSV with optional custom filename
        self.storage.write_csv(dataset_id, transactions_df, foldername, csv_filename=csv_filename)

        # Write YAML
        self.storage.write_yaml(dataset_id, taxonomy_data, foldername)

        return {
            "dataset_id": dataset_id,
            "foldername": foldername,
            "row_count": len(transactions_df),
        }

    def update_dataset_csv(
        self,
        dataset_id: str,
        transactions_df: pd.DataFrame,
        foldername: str = "default"
    ) -> Dict:
        """
        Update the transactions CSV for a dataset.

        Args:
            dataset_id: Dataset identifier
            transactions_df: DataFrame with updated transaction data
            foldername: Folder name

        Returns:
            Dictionary with updated dataset info

        Raises:
            DatasetNotFoundError: If dataset does not exist
        """
        if not self.storage.exists(dataset_id, foldername):
            raise DatasetNotFoundError(f"Dataset '{dataset_id}' not found in folder '{foldername}'")

        self.storage.write_csv(dataset_id, transactions_df, foldername)

        return {
            "dataset_id": dataset_id,
            "foldername": foldername,
            "row_count": len(transactions_df),
        }

    def update_dataset_taxonomy(
        self,
        dataset_id: str,
        taxonomy_data: Dict[str, Any],
        foldername: str = "default"
    ) -> Dict:
        """
        Update the taxonomy YAML for a dataset.

        Args:
            dataset_id: Dataset identifier
            taxonomy_data: Dictionary with updated taxonomy structure
            foldername: Folder name

        Returns:
            Dictionary with dataset info

        Raises:
            DatasetNotFoundError: If dataset does not exist
        """
        if not self.storage.exists(dataset_id, foldername):
            raise DatasetNotFoundError(f"Dataset '{dataset_id}' not found in folder '{foldername}'")

        self.storage.write_yaml(dataset_id, taxonomy_data, foldername)

        return {
            "dataset_id": dataset_id,
            "foldername": foldername,
        }

    def get_dataset_taxonomy(
        self,
        dataset_id: str,
        foldername: str = "default"
    ) -> Dict[str, Any]:
        """
        Get taxonomy YAML for a dataset.

        Args:
            dataset_id: Dataset identifier
            foldername: Folder name

        Returns:
            Dictionary with taxonomy structure

        Raises:
            DatasetNotFoundError: If dataset or taxonomy does not exist
        """
        try:
            return self.storage.read_yaml(dataset_id, foldername)
        except FileNotFoundError as e:
            raise DatasetNotFoundError(str(e))

    def delete_dataset(self, dataset_id: str, foldername: str = "default") -> None:
        """
        Delete a dataset (both CSV and YAML files).

        Args:
            dataset_id: Dataset identifier
            foldername: Folder name

        Raises:
            DatasetNotFoundError: If dataset does not exist
        """
        if not self.storage.exists(dataset_id, foldername):
            raise DatasetNotFoundError(f"Dataset '{dataset_id}' not found in folder '{foldername}'")

        self.storage.delete_dataset(dataset_id, foldername)

