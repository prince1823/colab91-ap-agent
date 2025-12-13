"""Local filesystem storage backend."""

import re
from pathlib import Path
from typing import Optional

import pandas as pd

from api.storage.base import StorageBackend


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage backend."""

    def __init__(self, base_dir: Path):
        """
        Initialize local storage backend.

        Args:
            base_dir: Base directory for datasets (e.g., Path("benchmarks"))
        """
        self.base_dir = base_dir.resolve()

    def _validate_dataset_id(self, dataset_id: str) -> None:
        """
        Validate dataset ID to prevent path traversal.

        Args:
            dataset_id: Dataset identifier

        Raises:
            ValueError: If dataset_id contains invalid characters
        """
        # Only allow alphanumeric, underscore, hyphen, and dot
        if not re.match(r"^[a-zA-Z0-9_.-]+$", dataset_id):
            raise ValueError(f"Invalid dataset_id: {dataset_id}. Only alphanumeric, underscore, hyphen, and dot are allowed.")

    def _validate_foldername(self, foldername: str) -> None:
        """
        Validate foldername to prevent path traversal.

        Args:
            foldername: Folder name

        Raises:
            ValueError: If foldername contains invalid characters
        """
        # Only allow alphanumeric, underscore, hyphen, and dot
        if not re.match(r"^[a-zA-Z0-9_.-]+$", foldername):
            raise ValueError(f"Invalid foldername: {foldername}. Only alphanumeric, underscore, hyphen, and dot are allowed.")

    def _get_csv_path(self, dataset_id: str, foldername: str) -> Path:
        """
        Get validated CSV path.

        Args:
            dataset_id: Dataset identifier
            foldername: Folder name

        Returns:
            Path to CSV file

        Raises:
            ValueError: If dataset_id or foldername is invalid
        """
        self._validate_dataset_id(dataset_id)
        self._validate_foldername(foldername)

        dataset_path = self.base_dir / foldername / dataset_id
        csv_path = dataset_path / "output.csv"

        # Resolve to absolute path and validate it's within base_dir
        csv_path = csv_path.resolve()
        base_resolved = self.base_dir.resolve()

        # Check that resolved path is within base directory
        try:
            csv_path.relative_to(base_resolved)
        except ValueError:
            raise ValueError(f"Invalid dataset path: {dataset_id}/{foldername}")

        return csv_path

    def read_csv(self, dataset_id: str, foldername: str = "default") -> pd.DataFrame:
        """Read CSV file for a dataset."""
        csv_path = self._get_csv_path(dataset_id, foldername)

        if not csv_path.exists():
            raise FileNotFoundError(f"Dataset '{dataset_id}' not found in folder '{foldername}'")

        return pd.read_csv(csv_path)

    def write_csv(self, dataset_id: str, df: pd.DataFrame, foldername: str = "default") -> None:
        """Write CSV file for a dataset."""
        csv_path = self._get_csv_path(dataset_id, foldername)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(csv_path, index=False)

    def exists(self, dataset_id: str, foldername: str = "default") -> bool:
        """Check if dataset CSV exists."""
        csv_path = self._get_csv_path(dataset_id, foldername)
        return csv_path.exists()

    def get_csv_path_or_uri(self, dataset_id: str, foldername: str = "default") -> str:
        """Get file path for CSV."""
        csv_path = self._get_csv_path(dataset_id, foldername)

        if not csv_path.exists():
            raise FileNotFoundError(f"Dataset '{dataset_id}' not found in folder '{foldername}'")

        return str(csv_path)

    def list_datasets(self, foldername: Optional[str] = None) -> list[dict]:
        """List available datasets."""
        if not self.base_dir.exists():
            return []

        datasets = []

        if foldername:
            # List datasets in specific folder
            self._validate_foldername(foldername)
            folder_path = self.base_dir / foldername
            if folder_path.exists():
                for dataset_dir in folder_path.iterdir():
                    if dataset_dir.is_dir():
                        csv_path = dataset_dir / "output.csv"
                        if csv_path.exists():
                            dataset_id = dataset_dir.name
                            try:
                                self._validate_dataset_id(dataset_id)
                                # Get row count
                                df = pd.read_csv(csv_path)
                                row_count = len(df)
                            except Exception:
                                row_count = 0

                            datasets.append({
                                "dataset_id": dataset_id,
                                "foldername": foldername,
                                "row_count": row_count,
                            })
        else:
            # List datasets in all folders
            for folder_path in self.base_dir.iterdir():
                if folder_path.is_dir():
                    folder_name = folder_path.name
                    try:
                        self._validate_foldername(folder_name)
                        for dataset_dir in folder_path.iterdir():
                            if dataset_dir.is_dir():
                                csv_path = dataset_dir / "output.csv"
                                if csv_path.exists():
                                    dataset_id = dataset_dir.name
                                    try:
                                        self._validate_dataset_id(dataset_id)
                                        # Get row count
                                        df = pd.read_csv(csv_path)
                                        row_count = len(df)
                                    except Exception:
                                        row_count = 0

                                    datasets.append({
                                        "dataset_id": dataset_id,
                                        "foldername": folder_name,
                                        "row_count": row_count,
                                    })
                    except ValueError:
                        # Skip invalid folder names
                        continue

        return datasets

