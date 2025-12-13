"""Storage backend factory."""

from pathlib import Path

from api.storage.base import StorageBackend
from api.storage.local import LocalStorageBackend
from api.storage.s3 import S3StorageBackend
from core.config import get_config


def get_storage_backend() -> StorageBackend:
    """
    Get storage backend based on configuration.

    Configuration via environment variables:
    - STORAGE_TYPE: "local" or "s3" (default: "local")
    - For S3:
      - S3_BUCKET: S3 bucket name
      - S3_PREFIX: S3 key prefix (default: "benchmarks/")
    - For local:
      - LOCAL_BASE_DIR: Base directory path (default: "benchmarks")

    Returns:
        Storage backend instance

    Raises:
        ValueError: If storage type is invalid or required config is missing
    """
    config = get_config()

    storage_type = getattr(config, "storage_type", "local")

    if storage_type == "s3":
        bucket = getattr(config, "s3_bucket", None)
        prefix = getattr(config, "s3_prefix", "benchmarks/")
        if not bucket:
            raise ValueError("s3_bucket must be configured for S3 storage. Set S3_BUCKET environment variable.")
        return S3StorageBackend(bucket_name=bucket, prefix=prefix)

    elif storage_type == "local":
        # Use datasets_dir for new datasets, but support benchmarks for backward compatibility
        datasets_dir = getattr(config, "datasets_dir", None)
        if datasets_dir:
            base_dir = Path(datasets_dir)
        else:
            base_dir_str = getattr(config, "local_base_dir", "benchmarks")
            base_dir = Path(base_dir_str)
        return LocalStorageBackend(base_dir=base_dir)

    else:
        raise ValueError(f"Unknown storage type: {storage_type}. Must be 'local' or 's3'")

