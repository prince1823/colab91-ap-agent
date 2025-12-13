"""Helper functions for path parsing and extraction."""

from typing import Optional


def extract_foldername_from_path(csv_path: str) -> str:
    """
    Extract foldername from CSV path.
    
    Supports both local paths and S3 URIs:
    - Local: "benchmarks/{foldername}/{dataset_name}/output.csv"
    - S3: "s3://bucket/benchmarks/{foldername}/{dataset_name}/output.csv"
    
    Args:
        csv_path: CSV file path (local or S3 URI)
        
    Returns:
        Foldername (defaults to "default" if not found)
    """
    if not csv_path or "/" not in csv_path:
        return "default"
    
    # Handle S3 URIs
    if csv_path.startswith("s3://"):
        uri_parts = csv_path.replace("s3://", "").split("/")
        if "benchmarks" in uri_parts:
            idx = uri_parts.index("benchmarks")
            if idx + 1 < len(uri_parts):
                return uri_parts[idx + 1]
        return "default"
    
    # Handle local paths
    parts = csv_path.split("/")
    if "benchmarks" in parts:
        idx = parts.index("benchmarks")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    
    return "default"

