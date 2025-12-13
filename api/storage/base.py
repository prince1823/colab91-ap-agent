"""Abstract storage backend interface."""

from abc import ABC, abstractmethod
from typing import Optional

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
    def write_csv(self, dataset_id: str, df: pd.DataFrame, foldername: str = "default") -> None:
        """
        Write CSV file for a dataset.

        Args:
            dataset_id: Dataset identifier
            foldername: Folder name
            df: DataFrame to write

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

