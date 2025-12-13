"""Shared validation functions for request models."""

from typing import List


def validate_classification_path_format(path: str) -> str:
    """
    Validate and normalize classification path format.
    
    Args:
        path: Classification path string (e.g., "L1|L2|L3")
        
    Returns:
        Normalized path string
        
    Raises:
        ValueError: If path format is invalid
    """
    if not path or not path.strip():
        raise ValueError("Classification path cannot be empty")
    
    parts = path.split("|")
    if len(parts) < 1 or len(parts) > 5:
        raise ValueError("Classification path must have 1-5 levels separated by |")
    
    # Check for empty levels
    if any(not part.strip() for part in parts):
        raise ValueError("Classification path levels cannot be empty")
    
    # Normalize: trim whitespace from each level
    normalized = "|".join(part.strip() for part in parts)
    if len(normalized) > 500:
        raise ValueError("Classification path too long (max 500 characters)")
    
    return normalized


def validate_supplier_name(name: str) -> str:
    """
    Validate and normalize supplier name.
    
    Args:
        name: Supplier name string
        
    Returns:
        Normalized supplier name
        
    Raises:
        ValueError: If name is invalid
    """
    if not name or not name.strip():
        raise ValueError("Supplier name cannot be empty")
    
    # Remove control characters and normalize whitespace
    normalized = " ".join(name.strip().split())
    if len(normalized) > 255:
        raise ValueError("Supplier name too long (max 255 characters)")
    
    return normalized


def validate_taxonomy_paths_list(paths: List[str]) -> List[str]:
    """
    Validate and normalize list of taxonomy paths.
    
    Args:
        paths: List of taxonomy path strings
        
    Returns:
        Normalized list of unique paths
        
    Raises:
        ValueError: If paths are invalid
    """
    if not paths:
        raise ValueError("At least one taxonomy path is required")
    
    if len(paths) > 100:  # Reasonable limit
        raise ValueError("Too many taxonomy paths (max 100)")
    
    normalized_paths = []
    for path in paths:
        if not path or not isinstance(path, str) or not path.strip():
            raise ValueError("All taxonomy paths must be non-empty strings")
        
        parts = path.split("|")
        if len(parts) < 1 or len(parts) > 5:
            raise ValueError(f"Taxonomy path '{path}' must have 1-5 levels separated by |")
        
        # Check for empty levels
        if any(not part.strip() for part in parts):
            raise ValueError(f"Taxonomy path '{path}' has empty levels")
        
        # Normalize: trim whitespace from each level
        normalized = "|".join(part.strip() for part in parts)
        if len(normalized) > 500:
            raise ValueError(f"Taxonomy path '{path}' too long (max 500 characters)")
        
        normalized_paths.append(normalized)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_paths = []
    for path in normalized_paths:
        if path not in seen:
            seen.add(path)
            unique_paths.append(path)
    
    return unique_paths

