"""Local filesystem storage backend."""

import re
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
import yaml

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

    def _get_dataset_path(self, dataset_id: str, foldername: str) -> Path:
        """
        Get validated dataset directory path.

        Args:
            dataset_id: Dataset identifier
            foldername: Folder name

        Returns:
            Path to dataset directory

        Raises:
            ValueError: If dataset_id or foldername is invalid
        """
        self._validate_dataset_id(dataset_id)
        self._validate_foldername(foldername)

        dataset_path = self.base_dir / foldername / dataset_id

        # Resolve to absolute path and validate it's within base_dir
        dataset_path = dataset_path.resolve()
        base_resolved = self.base_dir.resolve()

        # Check that resolved path is within base directory
        try:
            dataset_path.relative_to(base_resolved)
        except ValueError:
            raise ValueError(f"Invalid dataset path: {dataset_id}/{foldername}")

        return dataset_path

    def _find_csv_file(self, dataset_path: Path) -> Optional[Path]:
        """
        Find any CSV file in the dataset directory.

        Args:
            dataset_path: Path to dataset directory

        Returns:
            Path to CSV file if found, None otherwise
        """
        if not dataset_path.exists():
            return None

        # Look for any .csv file in the directory
        csv_files = list(dataset_path.glob("*.csv"))
        if csv_files:
            # Return the first CSV file found
            return csv_files[0]
        return None

    def _get_csv_path(self, dataset_id: str, foldername: str, csv_filename: Optional[str] = None) -> Path:
        """
        Get validated CSV path.

        Args:
            dataset_id: Dataset identifier
            foldername: Folder name
            csv_filename: Optional specific CSV filename

        Returns:
            Path to CSV file

        Raises:
            ValueError: If dataset_id or foldername is invalid
            FileNotFoundError: If CSV file not found
        """
        dataset_path = self._get_dataset_path(dataset_id, foldername)

        if csv_filename:
            # Use specified filename
            csv_path = dataset_path / csv_filename
            if not csv_path.exists():
                raise FileNotFoundError(f"CSV file '{csv_filename}' not found for dataset '{dataset_id}'")
            return csv_path

        # Auto-detect CSV file
        csv_path = self._find_csv_file(dataset_path)
        if csv_path:
            return csv_path

        # Fallback to common names
        for name in ["transactions.csv", "output.csv", "data.csv"]:
            csv_path = dataset_path / name
            if csv_path.exists():
                return csv_path

        raise FileNotFoundError(f"No CSV file found for dataset '{dataset_id}' in folder '{foldername}'")

    def _get_yaml_path(self, dataset_id: str, foldername: str) -> Path:
        """
        Get validated YAML taxonomy path.

        Args:
            dataset_id: Dataset identifier
            foldername: Folder name

        Returns:
            Path to YAML file

        Raises:
            ValueError: If dataset_id or foldername is invalid
        """
        dataset_path = self._get_dataset_path(dataset_id, foldername)
        return dataset_path / "taxonomy.yaml"

    def read_csv(self, dataset_id: str, foldername: str = "default") -> pd.DataFrame:
        """Read CSV file for a dataset (auto-detects CSV filename)."""
        csv_path = self._get_csv_path(dataset_id, foldername)
        return pd.read_csv(csv_path)

    def write_csv(self, dataset_id: str, df: pd.DataFrame, foldername: str = "default", csv_filename: Optional[str] = None) -> None:
        """Write CSV file for a dataset."""
        dataset_path = self._get_dataset_path(dataset_id, foldername)
        dataset_path.mkdir(parents=True, exist_ok=True)

        if csv_filename:
            # Use specified filename
            csv_path = dataset_path / csv_filename
        else:
            # For existing datasets, update the existing CSV file
            existing_csv = self._find_csv_file(dataset_path)
            if existing_csv:
                csv_path = existing_csv
            else:
                # New dataset - use default transactions.csv
                csv_path = dataset_path / "transactions.csv"

        df.to_csv(csv_path, index=False)

    def exists(self, dataset_id: str, foldername: str = "default") -> bool:
        """Check if dataset CSV exists."""
        try:
            dataset_path = self._get_dataset_path(dataset_id, foldername)
            return self._find_csv_file(dataset_path) is not None
        except (ValueError, FileNotFoundError):
            return False

    def get_csv_path_or_uri(self, dataset_id: str, foldername: str = "default") -> str:
        """Get file path for CSV (auto-detects CSV filename)."""
        csv_path = self._get_csv_path(dataset_id, foldername)
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
                        # Find any CSV file in the directory
                        csv_path = self._find_csv_file(dataset_dir)
                        if csv_path:
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
                                # Find any CSV file in the directory
                                csv_path = self._find_csv_file(dataset_dir)
                                if csv_path:
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

    def read_yaml(self, dataset_id: str, foldername: str = "default") -> Dict[str, Any]:
        """Read YAML taxonomy file for a dataset."""
        yaml_path = self._get_yaml_path(dataset_id, foldername)

        if not yaml_path.exists():
            raise FileNotFoundError(f"Taxonomy YAML for dataset '{dataset_id}' not found in folder '{foldername}'")

        with open(yaml_path, 'r') as f:
            return yaml.safe_load(f) or {}

    def write_yaml(self, dataset_id: str, data: Dict[str, Any], foldername: str = "default") -> None:
        """Write YAML taxonomy file for a dataset."""
        yaml_path = self._get_yaml_path(dataset_id, foldername)
        yaml_path.parent.mkdir(parents=True, exist_ok=True)

        with open(yaml_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    def delete_dataset(self, dataset_id: str, foldername: str = "default") -> None:
        """Delete a dataset (both CSV and YAML files)."""
        dataset_path = self._get_dataset_path(dataset_id, foldername)

        if not dataset_path.exists():
            raise FileNotFoundError(f"Dataset '{dataset_id}' not found in folder '{foldername}'")

        # Remove entire dataset directory
        shutil.rmtree(dataset_path)

