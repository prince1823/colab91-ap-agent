"""Utilities for filtering and augmenting taxonomy data."""

from typing import Dict, List, Set


def extract_l1_categories(taxonomy_data: Dict) -> List[str]:
    """
    Extract unique L1 categories from taxonomy paths.

    Args:
        taxonomy_data: Dictionary with 'taxonomy' key containing list of pipe-separated paths

    Returns:
        List of unique L1 categories
    """
    taxonomy_paths = taxonomy_data.get("taxonomy", [])
    l1_categories: Set[str] = set()

    for path in taxonomy_paths:
        if isinstance(path, str):
            parts = path.split("|")
            if parts:
                l1_categories.add(parts[0].strip())

    return sorted(list(l1_categories))


def filter_taxonomy_by_l1(taxonomy_data: Dict, l1_category: str) -> Dict:
    """
    Filter taxonomy paths to only those starting with the given L1 category.

    Args:
        taxonomy_data: Dictionary with taxonomy structure
        l1_category: L1 category to filter by

    Returns:
        Dictionary with filtered taxonomy paths
    """
    taxonomy_paths = taxonomy_data.get("taxonomy", [])
    filtered_paths = []

    for path in taxonomy_paths:
        if isinstance(path, str):
            parts = path.split("|")
            if parts and parts[0].strip().lower() == l1_category.lower():
                filtered_paths.append(path)

    # Create new taxonomy dict with filtered paths
    filtered_taxonomy = taxonomy_data.copy()
    filtered_taxonomy["taxonomy"] = filtered_paths

    return filtered_taxonomy


def augment_taxonomy_with_other(taxonomy_data: Dict) -> Dict:
    """
    Augment taxonomy with "Other" categories at each level.

    Runtime logic:
    - For each L1 category → add "L1|Other" if not exists
    - For each L2 category → add "L1|L2|Other" if not exists
    - For each L3 category → add "L1|L2|L3|Other" if not exists
    - Continue for L4, L5

    Args:
        taxonomy_data: Dictionary with taxonomy structure

    Returns:
        Dictionary with augmented taxonomy paths
    """
    taxonomy_paths = taxonomy_data.get("taxonomy", [])
    existing_paths = set(taxonomy_paths)
    augmented_paths = list(taxonomy_paths)

    # Track what we've seen at each level
    l1_seen: Set[str] = set()
    l2_seen: Set[tuple] = set()
    l3_seen: Set[tuple] = set()
    l4_seen: Set[tuple] = set()

    # First pass: identify existing paths and levels
    for path in taxonomy_paths:
        if isinstance(path, str):
            parts = [p.strip() for p in path.split("|")]
            if len(parts) >= 1:
                l1_seen.add(parts[0])
            if len(parts) >= 2:
                l2_seen.add((parts[0], parts[1]))
            if len(parts) >= 3:
                l3_seen.add((parts[0], parts[1], parts[2]))
            if len(parts) >= 4:
                l4_seen.add((parts[0], parts[1], parts[2], parts[3]))

    # Add "Other" categories
    # L1 level: "L1|Other"
    for l1 in l1_seen:
        other_path = f"{l1}|Other"
        if other_path not in existing_paths:
            augmented_paths.append(other_path)
            existing_paths.add(other_path)

    # L2 level: "L1|L2|Other"
    for l1, l2 in l2_seen:
        other_path = f"{l1}|{l2}|Other"
        if other_path not in existing_paths:
            augmented_paths.append(other_path)
            existing_paths.add(other_path)

    # L3 level: "L1|L2|L3|Other"
    for l1, l2, l3 in l3_seen:
        other_path = f"{l1}|{l2}|{l3}|Other"
        if other_path not in existing_paths:
            augmented_paths.append(other_path)
            existing_paths.add(other_path)

    # L4 level: "L1|L2|L3|L4|Other"
    for l1, l2, l3, l4 in l4_seen:
        other_path = f"{l1}|{l2}|{l3}|{l4}|Other"
        if other_path not in existing_paths:
            augmented_paths.append(other_path)
            existing_paths.add(other_path)

    # Create augmented taxonomy dict
    augmented_taxonomy = taxonomy_data.copy()
    augmented_taxonomy["taxonomy"] = augmented_paths

    return augmented_taxonomy

