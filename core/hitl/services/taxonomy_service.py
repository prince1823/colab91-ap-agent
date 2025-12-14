"""Taxonomy service for YAML file operations using DatasetService."""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from api.exceptions import DatasetNotFoundError
from api.services.dataset_service import DatasetService

logger = logging.getLogger(__name__)


class TaxonomyService:
    """Service for taxonomy YAML file operations using DatasetService storage abstraction."""

    def __init__(self, dataset_service: Optional[DatasetService] = None):
        """
        Initialize taxonomy service.

        Args:
            dataset_service: DatasetService instance (creates new if None)
        """
        self.dataset_service = dataset_service
        # Fallback to old path-based approach if dataset_service not provided
        self.taxonomy_base_path = Path("taxonomies")

    def _update_taxonomy_section(
        self,
        dataset_name: str,
        foldername: str,
        section_name: str,
        updates: Dict[str, str]
    ) -> None:
        """
        Internal helper to update a taxonomy section (company_context or taxonomy_descriptions).

        Args:
            dataset_name: Dataset name
            foldername: Folder name
            section_name: Section name ('company_context' or 'taxonomy_descriptions')
            updates: Dictionary of key -> value mappings

        Raises:
            FileNotFoundError: If taxonomy file doesn't exist
        """
        if self.dataset_service:
            try:
                # Read existing taxonomy from dataset storage
                taxonomy = self.dataset_service.get_dataset_taxonomy(dataset_name, foldername)

                # Update section
                if section_name not in taxonomy:
                    taxonomy[section_name] = {}

                for key, value in updates.items():
                    taxonomy[section_name][key] = value

                # Write back using DatasetService
                self.dataset_service.update_dataset_taxonomy(dataset_name, taxonomy, foldername)
                logger.info(
                    f"Updated {section_name} for dataset '{dataset_name}' in folder '{foldername}': {list(updates.keys())}"
                )
                return
            except DatasetNotFoundError:
                # Fallback to old path if dataset not found in new system
                logger.warning(
                    f"Dataset '{dataset_name}' not found in storage, falling back to legacy path 'taxonomies/{dataset_name}.yaml'"
                )
            except Exception as e:
                # Log unexpected errors but still try fallback
                logger.error(
                    f"Error updating {section_name} via DatasetService for '{dataset_name}': {e}. "
                    f"Falling back to legacy path.",
                    exc_info=True
                )

        # Fallback to old path-based approach
        taxonomy_path = self.taxonomy_base_path / f"{dataset_name}.yaml"

        if not taxonomy_path.exists():
            raise FileNotFoundError(
                f"Taxonomy file not found: {taxonomy_path}. "
                f"Tried DatasetService first, then legacy path."
            )

        # Read existing taxonomy
        with open(taxonomy_path, 'r') as f:
            taxonomy = yaml.safe_load(f)

        # Update section
        if section_name not in taxonomy:
            taxonomy[section_name] = {}

        for key, value in updates.items():
            taxonomy[section_name][key] = value

        # Write back to file
        with open(taxonomy_path, 'w') as f:
            yaml.dump(taxonomy, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        
        logger.info(
            f"Updated {section_name} for dataset '{dataset_name}' via legacy path: {list(updates.keys())}"
        )

    def read_taxonomy(self, dataset_name: str, foldername: str = "default") -> Dict:
        """
        Read taxonomy YAML file for a dataset.

        Uses DatasetService if available, otherwise falls back to old path-based approach.

        Args:
            dataset_name: Dataset name (e.g., "innova", "fox")
            foldername: Folder name (default: "default")

        Returns:
            Taxonomy dictionary

        Raises:
            FileNotFoundError: If taxonomy file doesn't exist
        """
        if self.dataset_service:
            try:
                taxonomy = self.dataset_service.get_dataset_taxonomy(dataset_name, foldername)
                logger.info(f"Successfully loaded taxonomy for '{dataset_name}' in folder '{foldername}' from DatasetService")
                return taxonomy
            except DatasetNotFoundError as e:
                # No fallback - taxonomy must be in dataset directory
                raise FileNotFoundError(
                    f"Taxonomy file not found for dataset '{dataset_name}' in folder '{foldername}'. "
                    f"Expected taxonomy.yaml in the same directory as input.csv (datasets/{dataset_name}/taxonomy.yaml). "
                    f"Error: {e}"
                ) from e
            except Exception as e:
                # Log and re-raise unexpected errors
                logger.error(
                    f"Error reading taxonomy from DatasetService for '{dataset_name}' in folder '{foldername}': {type(e).__name__}: {e}.",
                    exc_info=True
                )
                raise FileNotFoundError(
                    f"Failed to load taxonomy for dataset '{dataset_name}' in folder '{foldername}': {e}"
                ) from e

        # If no DatasetService, raise error (we require DatasetService)
        raise ValueError(
            f"TaxonomyService requires DatasetService to load taxonomy. "
            f"Taxonomy files are stored in dataset directories (datasets/{dataset_name}/taxonomy.yaml), not in taxonomies/ folder."
        )

    def update_company_context(
        self,
        dataset_name: str,
        updates: Dict[str, str],
        foldername: str = "default"
    ) -> None:
        """
        Update company context in taxonomy YAML.

        Uses DatasetService if available, otherwise falls back to old path-based approach.

        Args:
            dataset_name: Dataset name
            updates: Dictionary of field_name -> new_value mappings
            foldername: Folder name (default: "default")

        Raises:
            ValueError: If updates dict is empty
            FileNotFoundError: If taxonomy file doesn't exist
            DatasetNotFoundError: If dataset doesn't exist (when using DatasetService)
        """
        # Validate input
        if not updates:
            raise ValueError("updates dictionary cannot be empty")

        self._update_taxonomy_section(
            dataset_name=dataset_name,
            foldername=foldername,
            section_name="company_context",
            updates=updates
        )

    def update_taxonomy_description(
        self,
        dataset_name: str,
        updates: Dict[str, str],
        foldername: str = "default"
    ) -> None:
        """
        Update taxonomy descriptions in taxonomy YAML.

        Uses DatasetService if available, otherwise falls back to old path-based approach.

        Args:
            dataset_name: Dataset name
            updates: Dictionary of taxonomy_path -> new_description mappings
            foldername: Folder name (default: "default")

        Raises:
            ValueError: If updates dict is empty
            FileNotFoundError: If taxonomy file doesn't exist
            DatasetNotFoundError: If dataset doesn't exist (when using DatasetService)
        """
        # Validate input
        if not updates:
            raise ValueError("updates dictionary cannot be empty")

        self._update_taxonomy_section(
            dataset_name=dataset_name,
            foldername=foldername,
            section_name="taxonomy_descriptions",
            updates=updates
        )

