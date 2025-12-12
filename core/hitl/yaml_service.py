"""YAML taxonomy file operations for HITL."""

from pathlib import Path
from typing import Any, Dict

import yaml


def read_taxonomy_yaml(dataset_name: str) -> Dict:
    """
    Read taxonomy YAML file for a dataset.

    Args:
        dataset_name: Dataset name (e.g., "innova", "fox")

    Returns:
        Taxonomy dictionary

    Raises:
        FileNotFoundError: If taxonomy file doesn't exist
    """
    taxonomy_path = Path(f"taxonomies/{dataset_name}.yaml")

    if not taxonomy_path.exists():
        raise FileNotFoundError(f"Taxonomy file not found: {taxonomy_path}")

    with open(taxonomy_path, 'r') as f:
        taxonomy = yaml.safe_load(f)

    return taxonomy


def update_taxonomy(dataset_name: str, change_type: str, updates: Dict[str, Any]) -> None:
    """
    Update taxonomy YAML file.

    Handles both company_context and taxonomy_descriptions updates.

    Args:
        dataset_name: Dataset name
        change_type: "company_context" or "taxonomy_description"
        updates: Dictionary of updates to apply

    Raises:
        FileNotFoundError: If taxonomy file doesn't exist
        ValueError: If change_type is invalid
    """
    taxonomy_path = Path(f"taxonomies/{dataset_name}.yaml")

    if not taxonomy_path.exists():
        raise FileNotFoundError(f"Taxonomy file not found: {taxonomy_path}")

    # Read existing taxonomy
    with open(taxonomy_path, 'r') as f:
        taxonomy = yaml.safe_load(f)

    # Apply updates based on change type
    if change_type == "company_context":
        # Update company_context section
        if 'company_context' not in taxonomy:
            taxonomy['company_context'] = {}

        for field_name, new_value in updates.items():
            taxonomy['company_context'][field_name] = new_value

    elif change_type == "taxonomy_description":
        # Update taxonomy_descriptions section
        if 'taxonomy_descriptions' not in taxonomy:
            taxonomy['taxonomy_descriptions'] = {}

        for taxonomy_path_key, new_description in updates.items():
            taxonomy['taxonomy_descriptions'][taxonomy_path_key] = new_description

    else:
        raise ValueError(f"Invalid change_type: {change_type}. Must be 'company_context' or 'taxonomy_description'")

    # Write back to file (preserving structure as much as possible)
    with open(taxonomy_path, 'w') as f:
        yaml.dump(taxonomy, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
