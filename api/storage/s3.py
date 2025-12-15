"""AWS S3 storage backend."""

import re
from io import StringIO
from typing import Any, Dict, Optional

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = Exception

import pandas as pd
import yaml

from api.storage.base import StorageBackend


class S3StorageBackend(StorageBackend):
    """AWS S3 storage backend."""

    def __init__(self, bucket_name: str, prefix: str = "benchmarks/"):
        """
        Initialize S3 storage backend.

        Args:
            bucket_name: S3 bucket name
            prefix: S3 key prefix (e.g., "benchmarks/")

        Raises:
            ImportError: If boto3 is not installed
        """
        if boto3 is None:
            raise ImportError(
                "boto3 is required for S3 storage. Install it with: pip install boto3"
            )
        self.s3_client = boto3.client("s3")
        self.bucket_name = bucket_name
        self.prefix = prefix.rstrip("/") + "/"

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

    def _get_s3_key(self, dataset_id: str, foldername: str, filename: str = "output.csv") -> str:
        """
        Construct S3 key (path in bucket).

        Args:
            dataset_id: Dataset identifier
            foldername: Folder name
            filename: Filename (default: "output.csv")

        Returns:
            S3 key string
        """
        self._validate_dataset_id(dataset_id)
        self._validate_foldername(foldername)

        return f"{self.prefix}{foldername}/{dataset_id}/{filename}"

    def read_csv(self, dataset_id: str, foldername: str = "default") -> pd.DataFrame:
        """Read CSV file from S3 (auto-detects CSV filename)."""
        # Try to find any CSV file in the dataset directory
        dataset_prefix = f"{self.prefix}{foldername}/{dataset_id}/"
        
        try:
            # List objects to find CSV file
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=dataset_prefix,
                MaxKeys=10
            )
            
            csv_key = None
            if "Contents" in response:
                for obj in response["Contents"]:
                    if obj["Key"].endswith(".csv"):
                        csv_key = obj["Key"]
                        break
            
            if not csv_key:
                # Fallback to common names
                for filename in ["transactions.csv", "output.csv", "data.csv"]:
                    try:
                        test_key = self._get_s3_key(dataset_id, foldername, filename)
                        self.s3_client.head_object(Bucket=self.bucket_name, Key=test_key)
                        csv_key = test_key
                        break
                    except Exception:
                        continue
            
            if not csv_key:
                raise FileNotFoundError(f"Dataset '{dataset_id}' not found in folder '{foldername}'")
            
            # Download from S3
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=csv_key)
            csv_content = response["Body"].read().decode("utf-8")

            # Read into pandas
            return pd.read_csv(StringIO(csv_content))
        except FileNotFoundError:
            raise
        except Exception as e:
            if hasattr(e, "response") and e.response.get("Error", {}).get("Code") == "NoSuchKey":
                raise FileNotFoundError(f"Dataset '{dataset_id}' not found in folder '{foldername}'")
            raise

    def write_csv(self, dataset_id: str, df: pd.DataFrame, foldername: str = "default", csv_filename: Optional[str] = None) -> None:
        """Write CSV file to S3."""
        if csv_filename:
            # Use specified filename
            s3_key = self._get_s3_key(dataset_id, foldername, csv_filename)
        else:
            # For existing datasets, try to find existing CSV file
            # Check common filenames
            for filename in ["transactions.csv", "output.csv", "data.csv"]:
                try:
                    test_key = self._get_s3_key(dataset_id, foldername, filename)
                    self.s3_client.head_object(Bucket=self.bucket_name, Key=test_key)
                    s3_key = test_key
                    break
                except Exception:
                    continue
            else:
                # New dataset - use default transactions.csv
                s3_key = self._get_s3_key(dataset_id, foldername, "transactions.csv")

        # Convert DataFrame to CSV string
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_content = csv_buffer.getvalue()

        # Upload to S3
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=s3_key,
            Body=csv_content.encode("utf-8"),
            ContentType="text/csv",
        )

    def exists(self, dataset_id: str, foldername: str = "default") -> bool:
        """Check if dataset CSV exists in S3."""
        # Check for any CSV file with common names
        for filename in ["transactions.csv", "output.csv", "data.csv"]:
            try:
                s3_key = self._get_s3_key(dataset_id, foldername, filename)
                self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
                return True
            except Exception:
                continue
        
        # Also try to list objects in the dataset directory to find any CSV
        try:
            dataset_prefix = f"{self.prefix}{foldername}/{dataset_id}/"
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=dataset_prefix,
                MaxKeys=10
            )
            if "Contents" in response:
                for obj in response["Contents"]:
                    if obj["Key"].endswith(".csv"):
                        return True
        except Exception:
            pass
        
        return False

    def get_csv_path_or_uri(self, dataset_id: str, foldername: str = "default") -> str:
        """Return S3 URI for DuckDB compatibility (auto-detects CSV filename)."""
        if not self.exists(dataset_id, foldername):
            raise FileNotFoundError(f"Dataset '{dataset_id}' not found in folder '{foldername}'")

        # Find the actual CSV file
        dataset_prefix = f"{self.prefix}{foldername}/{dataset_id}/"
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=dataset_prefix,
                MaxKeys=10
            )
            
            if "Contents" in response:
                for obj in response["Contents"]:
                    if obj["Key"].endswith(".csv"):
                        return f"s3://{self.bucket_name}/{obj['Key']}"
        except Exception:
            pass

        # Fallback to common names
        for filename in ["transactions.csv", "output.csv", "data.csv"]:
            try:
                s3_key = self._get_s3_key(dataset_id, foldername, filename)
                self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
                return f"s3://{self.bucket_name}/{s3_key}"
            except Exception:
                continue

        raise FileNotFoundError(f"Dataset '{dataset_id}' not found in folder '{foldername}'")

    def list_datasets(self, foldername: Optional[str] = None) -> list[dict]:
        """List available datasets in S3."""
        datasets = []

        try:
            if foldername:
                # List datasets in specific folder
                self._validate_foldername(foldername)
                prefix = f"{self.prefix}{foldername}/"
            else:
                # List datasets in all folders
                prefix = self.prefix

            # List objects with the prefix
            paginator = self.s3_client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=self.bucket_name, Prefix=prefix, Delimiter="/")

            for page in pages:
                # Process common prefixes (folders)
                for common_prefix in page.get("CommonPrefixes", []):
                    folder_key = common_prefix["Prefix"]
                    # Extract foldername from key
                    folder_rel_path = folder_key[len(self.prefix):].rstrip("/")
                    if "/" in folder_rel_path:
                        continue  # Skip nested folders for now

                    # List datasets in this folder
                    dataset_prefix = f"{folder_key}"
                    dataset_pages = paginator.paginate(Bucket=self.bucket_name, Prefix=dataset_prefix, Delimiter="/")

                    for dataset_page in dataset_pages:
                        for dataset_prefix_obj in dataset_page.get("CommonPrefixes", []):
                            dataset_key = dataset_prefix_obj["Prefix"]
                            dataset_id = dataset_key.rstrip("/").split("/")[-1]

                            try:
                                self._validate_dataset_id(dataset_id)
                                # Check if output.csv exists
                                csv_key = f"{dataset_key}output.csv"
                                if self.exists(dataset_id, folder_rel_path):
                                    # Get row count by reading first few bytes or using metadata
                                    # For efficiency, we'll just mark it exists
                                    # Full row count would require reading the file
                                    datasets.append({
                                        "dataset_id": dataset_id,
                                        "foldername": folder_rel_path,
                                        "row_count": 0,  # Would need to read file to get count
                                    })
                            except ValueError:
                                continue

                # Also check for any CSV files (not just output.csv)
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if key.endswith(".csv"):
                        # Extract dataset_id and foldername from key
                        rel_path = key[len(self.prefix):]
                        parts = rel_path.split("/")
                        if len(parts) == 3 and parts[2].endswith(".csv"):
                            folder_name = parts[0]
                            dataset_id = parts[1]

                            try:
                                self._validate_foldername(folder_name)
                                self._validate_dataset_id(dataset_id)
                                datasets.append({
                                    "dataset_id": dataset_id,
                                    "foldername": folder_name,
                                    "row_count": 0,  # Would need to read file to get count
                                })
                            except ValueError:
                                continue

        except Exception:
            # Return empty list on error
            pass

        return datasets

    def read_yaml(self, dataset_id: str, foldername: str = "default") -> Dict[str, Any]:
        """Read YAML taxonomy file from S3."""
        s3_key = self._get_s3_key(dataset_id, foldername, "taxonomy.yaml")

        try:
            # Download from S3
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            yaml_content = response["Body"].read().decode("utf-8")

            # Parse YAML
            return yaml.safe_load(yaml_content) or {}
        except Exception as e:
            if hasattr(e, "response") and e.response.get("Error", {}).get("Code") == "NoSuchKey":
                raise FileNotFoundError(f"Taxonomy YAML for dataset '{dataset_id}' not found in folder '{foldername}'")
            raise

    def write_yaml(self, dataset_id: str, data: Dict[str, Any], foldername: str = "default") -> None:
        """Write YAML taxonomy file to S3."""
        s3_key = self._get_s3_key(dataset_id, foldername, "taxonomy.yaml")

        # Convert dictionary to YAML string
        yaml_content = yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)

        # Upload to S3
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=s3_key,
            Body=yaml_content.encode("utf-8"),
            ContentType="application/x-yaml",
        )

    def delete_dataset(self, dataset_id: str, foldername: str = "default") -> None:
        """Delete a dataset (both CSV and YAML files) from S3."""
        # Delete CSV file
        csv_key = self._get_s3_key(dataset_id, foldername, "transactions.csv")
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=csv_key)
        except Exception:
            # Try legacy output.csv
            csv_key = self._get_s3_key(dataset_id, foldername, "output.csv")
            try:
                self.s3_client.delete_object(Bucket=self.bucket_name, Key=csv_key)
            except Exception:
                pass

        # Delete YAML file
        yaml_key = self._get_s3_key(dataset_id, foldername, "taxonomy.yaml")
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=yaml_key)
        except Exception:
            pass

        # Check if dataset still exists
        if self.exists(dataset_id, foldername):
            raise FileNotFoundError(f"Dataset '{dataset_id}' still exists in folder '{foldername}' after deletion attempt")

