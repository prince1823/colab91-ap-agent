"""Taxonomy service for YAML file operations."""

from pathlib import Path
from typing import Any, Dict

import yaml


class TaxonomyService:
    """Service for taxonomy YAML file operations."""

    def __init__(self, taxonomy_base_path: Path = None):
        """
        Initialize taxonomy service.

        Args:
            taxonomy_base_path: Base path for taxonomy files (defaults to "taxonomies/")
        """
        self.taxonomy_base_path = taxonomy_base_path or Path("taxonomies")

    def read_taxonomy(self, dataset_name: str) -> Dict:
        """
        Read taxonomy YAML file for a dataset.

        Args:
            dataset_name: Dataset name (e.g., "innova", "fox")

        Returns:
            Taxonomy dictionary

        Raises:
            FileNotFoundError: If taxonomy file doesn't exist
        """
        taxonomy_path = self.taxonomy_base_path / f"{dataset_name}.yaml"

        if not taxonomy_path.exists():
            raise FileNotFoundError(f"Taxonomy file not found: {taxonomy_path}")

        with open(taxonomy_path, 'r') as f:
            taxonomy = yaml.safe_load(f)

        return taxonomy

    def update_company_context(
        self,
        dataset_name: str,
        updates: Dict[str, str]
    ) -> None:
        """
        Update company context in taxonomy YAML.

        Args:
            dataset_name: Dataset name
            updates: Dictionary of field_name -> new_value mappings

        Raises:
            FileNotFoundError: If taxonomy file doesn't exist
        """
        taxonomy_path = self.taxonomy_base_path / f"{dataset_name}.yaml"

        if not taxonomy_path.exists():
            raise FileNotFoundError(f"Taxonomy file not found: {taxonomy_path}")

        # Read existing taxonomy
        with open(taxonomy_path, 'r') as f:
            taxonomy = yaml.safe_load(f)

        # Update company_context section
        if 'company_context' not in taxonomy:
            taxonomy['company_context'] = {}

        for field_name, new_value in updates.items():
            taxonomy['company_context'][field_name] = new_value

        # Write back to file
        with open(taxonomy_path, 'w') as f:
            yaml.dump(taxonomy, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    def update_taxonomy_description(
        self,
        dataset_name: str,
        updates: Dict[str, str]
    ) -> None:
        """
        Update taxonomy descriptions in taxonomy YAML.

        Args:
            dataset_name: Dataset name
            updates: Dictionary of taxonomy_path -> new_description mappings

        Raises:
            FileNotFoundError: If taxonomy file doesn't exist
        """
        taxonomy_path = self.taxonomy_base_path / f"{dataset_name}.yaml"

        if not taxonomy_path.exists():
            raise FileNotFoundError(f"Taxonomy file not found: {taxonomy_path}")

        # Read existing taxonomy
        with open(taxonomy_path, 'r') as f:
            taxonomy = yaml.safe_load(f)

        # Update taxonomy_descriptions section
        if 'taxonomy_descriptions' not in taxonomy:
            taxonomy['taxonomy_descriptions'] = {}

        for taxonomy_path_key, new_description in updates.items():
            taxonomy['taxonomy_descriptions'][taxonomy_path_key] = new_description

        # Write back to file
        with open(taxonomy_path, 'w') as f:
            yaml.dump(taxonomy, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

