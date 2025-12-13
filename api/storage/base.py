"""Abstract storage backend interface."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import pandas as pd


class StorageBackend(ABC):
    """Abstract storage backend for dataset files."""

    @abstractmethod
    def read_csv(self, dataset_id: str, foldername: str = "default") -> pd.DataFrame:
        """
        Read CSV file for a dataset.

        Args:
            dataset_id: Dataset identifier (e.g., 'innova', 'fox')
            foldername: Folder name (e.g., 'default', 'test_bench')

        Returns:
            DataFrame with CSV data

        Raises:
            FileNotFoundError: If dataset CSV does not exist
            ValueError: If dataset_id is invalid
        """
        pass

    @abstractmethod
    def write_csv(self, dataset_id: str, df: pd.DataFrame, foldername: str = "default", csv_filename: Optional[str] = None) -> None:
        """
        Write CSV file for a dataset.

        Args:
            dataset_id: Dataset identifier
            foldername: Folder name
            df: DataFrame to write
            csv_filename: Optional CSV filename (if None, auto-detects or uses default)

        Raises:
            ValueError: If dataset_id is invalid
        """
        pass

    @abstractmethod
    def exists(self, dataset_id: str, foldername: str = "default") -> bool:
        """
        Check if dataset CSV exists.

        Args:
            dataset_id: Dataset identifier
            foldername: Folder name

        Returns:
            True if dataset exists, False otherwise
        """
        pass

    @abstractmethod
    def get_csv_path_or_uri(self, dataset_id: str, foldername: str = "default") -> str:
        """
        Get path/URI for CSV file.

        For local: returns file path
        For S3: returns s3://bucket/key

        Args:
            dataset_id: Dataset identifier
            foldername: Folder name

        Returns:
            Path or URI string

        Raises:
            FileNotFoundError: If dataset does not exist
            ValueError: If dataset_id is invalid
        """
        pass

    @abstractmethod
    def list_datasets(self, foldername: Optional[str] = None) -> list[dict]:
        """
        List available datasets.

        Args:
            foldername: Optional folder name to filter by

        Returns:
            List of dataset info dicts with keys:
            - dataset_id: Dataset identifier
            - foldername: Folder name
            - row_count: Number of rows in CSV
        """
        pass

    @abstractmethod
    def read_yaml(self, dataset_id: str, foldername: str = "default") -> Dict[str, Any]:
        """
        Read YAML taxonomy file for a dataset.

        Args:
            dataset_id: Dataset identifier
            foldername: Folder name

        Returns:
            Dictionary with YAML content

        Raises:
            FileNotFoundError: If YAML file does not exist
            ValueError: If dataset_id is invalid
        """
        pass

    @abstractmethod
    def write_yaml(self, dataset_id: str, data: Dict[str, Any], foldername: str = "default") -> None:
        """
        Write YAML taxonomy file for a dataset.

        Args:
            dataset_id: Dataset identifier
            data: Dictionary to write as YAML
            foldername: Folder name

        Raises:
            ValueError: If dataset_id is invalid
        """
        pass

    @abstractmethod
    def delete_dataset(self, dataset_id: str, foldername: str = "default") -> None:
        """
        Delete a dataset (both CSV and YAML files).

        Args:
            dataset_id: Dataset identifier
            foldername: Folder name

        Raises:
            FileNotFoundError: If dataset does not exist
            ValueError: If dataset_id is invalid
        """
        pass

