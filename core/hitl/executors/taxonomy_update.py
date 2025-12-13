"""Executor for taxonomy and company context update actions."""

from typing import Dict, List

from sqlalchemy.orm import Session

from core.hitl.executors.base import BaseActionExecutor
from core.hitl.services.taxonomy_service import TaxonomyService


class TaxonomyUpdateExecutor(BaseActionExecutor):
    """Executor for taxonomy description and company context update actions."""

    def __init__(self, taxonomy_service: TaxonomyService = None):
        """
        Initialize taxonomy update executor.

        Args:
            taxonomy_service: TaxonomyService instance (creates new if None)
        """
        self.taxonomy_service = taxonomy_service or TaxonomyService()

    def execute(
        self,
        session: Session,
        dataset_name: str,
        action_details: Dict
    ) -> None:
        """
        Execute a taxonomy or company context update.

        Args:
            session: SQLAlchemy session (not used for taxonomy updates, but required by interface)
            dataset_name: Dataset name
            action_details: Dictionary with action-specific details

        Raises:
            ValueError: If action type is not recognized
        """
        # Determine action type from action_details structure
        if 'field_name' in action_details:
            # Company context update
            field_name = action_details['field_name']
            proposed_value = action_details['proposed_value']
            self.taxonomy_service.update_company_context(
                dataset_name,
                {field_name: proposed_value}
            )
        elif 'taxonomy_path' in action_details:
            # Taxonomy description update
            taxonomy_path = action_details['taxonomy_path']
            proposed_description = action_details['proposed_description']
            self.taxonomy_service.update_taxonomy_description(
                dataset_name,
                {taxonomy_path: proposed_description}
            )
        else:
            raise ValueError(f"Invalid action_details for taxonomy update: {action_details}")

    def preview_affected_rows(
        self,
        csv_path: str,
        action_details: Dict
    ) -> List[Dict]:
        """
        Preview rows affected by taxonomy updates.

        Note: Taxonomy updates don't directly affect specific rows in the CSV.
        They affect future classifications. This method returns an empty list.

        Args:
            csv_path: Path to the CSV file (not used)
            action_details: Dictionary with action-specific details (not used)

        Returns:
            Empty list (taxonomy updates don't affect existing rows)
        """
        # Taxonomy updates don't affect existing rows, only future classifications
        return []

