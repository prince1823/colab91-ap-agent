"""Executor for supplier rule actions."""

from datetime import datetime
from typing import Dict, List

from sqlalchemy.orm import Session

from core.database.models import SupplierDirectMapping, SupplierTaxonomyConstraint
from core.hitl.executors.base import BaseActionExecutor
from core.hitl.services.csv_service import CSVService


class SupplierRuleExecutor(BaseActionExecutor):
    """Executor for supplier rule creation actions."""

    def __init__(self, csv_service: CSVService = None):
        """
        Initialize supplier rule executor.

        Args:
            csv_service: CSVService instance (creates new if None)
        """
        self.csv_service = csv_service or CSVService()

    def execute(
        self,
        session: Session,
        dataset_name: str,
        action_details: Dict
    ) -> None:
        """
        Create a supplier rule in the appropriate table.

        Category A (DirectMapping): Writes to SupplierDirectMapping table.
        Category B (TaxonomyConstraint): Writes to SupplierTaxonomyConstraint table.

        Args:
            session: SQLAlchemy session
            dataset_name: Dataset name
            action_details: Dictionary with supplier_name, rule_category, classification_paths

        Raises:
            ValueError: If rule_category is invalid or classification_paths is invalid
        """
        supplier_name = action_details['supplier_name'].lower().strip()  # Normalize
        rule_category = action_details['rule_category'].upper()  # "A" or "B"
        classification_paths = action_details['classification_paths']
        feedback_id = action_details.get('_feedback_id')  # Optional feedback ID for tracking

        if not classification_paths:
            raise ValueError("classification_paths cannot be empty")

        # Deactivate any existing rules for this supplier+dataset (both types)
        self._deactivate_existing_rules(session, supplier_name, dataset_name)

        if rule_category == "A":
            # Category A: DirectMapping (100% confidence, single path)
            if len(classification_paths) != 1:
                raise ValueError(f"Category A requires exactly one classification path, got {len(classification_paths)}")

            # Check if active mapping already exists (shouldn't happen after deactivation, but safety check)
            existing = (
                session.query(SupplierDirectMapping)
                .filter(
                    SupplierDirectMapping.supplier_name == supplier_name,
                    SupplierDirectMapping.dataset_name == dataset_name,
                    SupplierDirectMapping.active == True
                )
                .first()
            )

            if existing:
                # Update existing mapping
                existing.classification_path = classification_paths[0]
                existing.priority = 10
                existing.active = True
                existing.updated_at = datetime.utcnow()
                existing.notes = f"Updated via HITL feedback (ID: {feedback_id})" if feedback_id else "Updated via HITL feedback"
            else:
                # Create new mapping
                notes = f"Created via HITL feedback (ID: {feedback_id})" if feedback_id else "Created via HITL feedback"
                mapping = SupplierDirectMapping(
                    supplier_name=supplier_name,
                    classification_path=classification_paths[0],
                    dataset_name=dataset_name,
                    priority=10,
                    created_by="hitl_feedback",
                    notes=notes,
                    active=True
                )
                session.add(mapping)

        elif rule_category == "B":
            # Category B: TaxonomyConstraint (multiple allowed paths)
            if len(classification_paths) < 1:
                raise ValueError(f"Category B requires at least one classification path, got {len(classification_paths)}")

            # Check if active constraint already exists
            existing = (
                session.query(SupplierTaxonomyConstraint)
                .filter(
                    SupplierTaxonomyConstraint.supplier_name == supplier_name,
                    SupplierTaxonomyConstraint.dataset_name == dataset_name,
                    SupplierTaxonomyConstraint.active == True
                )
                .first()
            )

            if existing:
                # Update existing constraint
                existing.allowed_taxonomy_paths = classification_paths
                existing.priority = 10
                existing.active = True
                existing.updated_at = datetime.utcnow()
                existing.notes = f"Updated via HITL feedback (ID: {feedback_id})" if feedback_id else "Updated via HITL feedback"
            else:
                # Create new constraint
                notes = f"Created via HITL feedback (ID: {feedback_id})" if feedback_id else "Created via HITL feedback"
                constraint = SupplierTaxonomyConstraint(
                    supplier_name=supplier_name,
                    allowed_taxonomy_paths=classification_paths,
                    dataset_name=dataset_name,
                    priority=10,
                    created_by="hitl_feedback",
                    notes=notes,
                    active=True
                )
                session.add(constraint)

        else:
            raise ValueError(f"Invalid rule_category: {rule_category}. Must be 'A' or 'B'")

        session.commit()

    def _deactivate_existing_rules(
        self,
        session: Session,
        supplier_name: str,
        dataset_name: str
    ) -> None:
        """
        Deactivate any existing active rules for this supplier+dataset.

        This ensures only one rule type (A or B) is active at a time.

        Args:
            session: SQLAlchemy session
            supplier_name: Supplier name
            dataset_name: Dataset name
        """
        # Deactivate existing direct mappings
        existing_mappings = (
            session.query(SupplierDirectMapping)
            .filter(
                SupplierDirectMapping.supplier_name == supplier_name,
                SupplierDirectMapping.dataset_name == dataset_name,
                SupplierDirectMapping.active == True
            )
            .all()
        )
        for mapping in existing_mappings:
            mapping.active = False
            mapping.updated_at = datetime.utcnow()

        # Deactivate existing taxonomy constraints
        existing_constraints = (
            session.query(SupplierTaxonomyConstraint)
            .filter(
                SupplierTaxonomyConstraint.supplier_name == supplier_name,
                SupplierTaxonomyConstraint.dataset_name == dataset_name,
                SupplierTaxonomyConstraint.active == True
            )
            .all()
        )
        for constraint in existing_constraints:
            constraint.active = False
            constraint.updated_at = datetime.utcnow()

    def preview_affected_rows(
        self,
        csv_path: str,
        action_details: Dict
    ) -> List[Dict]:
        """
        Find all rows for a specific supplier.

        Args:
            csv_path: Path to the CSV file
            action_details: Dictionary with supplier_name

        Returns:
            List of row dictionaries with their indices
        """
        supplier_name = action_details.get('supplier_name', '')
        return self.csv_service.find_rows_by_supplier(csv_path, supplier_name)

