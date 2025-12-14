"""Helper functions for path parsing and extraction."""

from typing import Optional


def extract_foldername_from_path(csv_path: str) -> str:
    """
    Extract foldername from CSV path.
    
    Supports both local paths and S3 URIs:
    - Local: "datasets/{foldername}/{dataset_name}/classified.csv" or "datasets/{dataset_name}/classified.csv"
    - Local (legacy): "benchmarks/{foldername}/{dataset_name}/output.csv"
    - S3: "s3://bucket/datasets/{foldername}/{dataset_name}/classified.csv"
    
    Args:
        csv_path: CSV file path (local or S3 URI)
        
    Returns:
        Foldername (empty string "" for direct dataset access, "default" if not found)
    """
    if not csv_path or "/" not in csv_path:
        return "default"
    
    # Handle S3 URIs
    if csv_path.startswith("s3://"):
        uri_parts = csv_path.replace("s3://", "").split("/")
        if "datasets" in uri_parts:
            idx = uri_parts.index("datasets")
            if idx + 1 < len(uri_parts):
                # Check if next part is a dataset_id (if there's a classified.csv or similar file after it)
                # If the path is datasets/{dataset_id}/classified.csv, foldername is ""
                if idx + 2 < len(uri_parts) and uri_parts[idx + 2] in ["classified.csv", "canonicalized.csv", "input.csv"]:
                    return ""  # Direct dataset access
                return uri_parts[idx + 1]  # Foldername
        elif "benchmarks" in uri_parts:
            idx = uri_parts.index("benchmarks")
            if idx + 1 < len(uri_parts):
                return uri_parts[idx + 1]
        return "default"
    
    # Handle local paths
    parts = csv_path.split("/")
    if "datasets" in parts:
        idx = parts.index("datasets")
        if idx + 1 < len(parts):
            # Check if next part is a dataset_id (if there's a classified.csv or similar file after it)
            # If the path is datasets/{dataset_id}/classified.csv, foldername is ""
            if idx + 2 < len(parts) and parts[idx + 2] in ["classified.csv", "canonicalized.csv", "input.csv"]:
                return ""  # Direct dataset access
            return parts[idx + 1]  # Foldername
    elif "benchmarks" in parts:
        idx = parts.index("benchmarks")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    
    return "default"

