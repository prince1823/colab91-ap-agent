"""Execute supplier rule creation."""

from datetime import datetime
from typing import Dict

from sqlalchemy.orm import Session

from core.database.models import SupplierClassification


def create_supplier_rule(
    session: Session,
    dataset_name: str,
    action_details: Dict
) -> None:
    """
    Create a supplier rule by updating supplier_classifications table.

    Args:
        session: SQLAlchemy session
        dataset_name: Dataset name
        action_details: Dictionary with supplier_name, rule_category, classification_paths

    Note:
        Supplier rules are global per dataset (not scoped to run_id).
        We update/create a representative entry in supplier_classifications.
    """
    supplier_name = action_details['supplier_name'].lower()  # Normalize
    rule_category = action_details['rule_category']  # "A" or "B"
    classification_paths = action_details['classification_paths']

    # Find or create a supplier classification entry for this supplier+dataset
    # We use the first entry we find, or create a new one
    supplier_entry = session.query(SupplierClassification).filter(
        SupplierClassification.supplier_name == supplier_name,
        SupplierClassification.dataset_name == dataset_name
    ).first()

    if supplier_entry:
        # Update existing entry
        supplier_entry.supplier_rule_type = f"category_{rule_category.lower()}"
        supplier_entry.supplier_rule_paths = classification_paths
        supplier_entry.supplier_rule_created_at = datetime.utcnow()
        supplier_entry.supplier_rule_active = True
    else:
        # Create new entry (this is a rule-only entry, not tied to a specific transaction)
        # We'll use dummy values for required fields
        new_entry = SupplierClassification(
            run_id="rule_only",
            dataset_name=dataset_name,
            supplier_name=supplier_name,
            classification_path=classification_paths[0] if classification_paths else "",
            l1=classification_paths[0].split('|')[0] if classification_paths else "",
            supplier_rule_type=f"category_{rule_category.lower()}",
            supplier_rule_paths=classification_paths,
            supplier_rule_created_at=datetime.utcnow(),
            supplier_rule_active=True
        )
        session.add(new_entry)

    session.commit()
