"""Execute transaction rule creation."""

from datetime import datetime
from typing import Dict

from sqlalchemy.orm import Session

from core.database.models import TransactionRule


def create_transaction_rule(
    session: Session,
    dataset_name: str,
    action_details: Dict
) -> None:
    """
    Create a transaction-based classification rule.

    Args:
        session: SQLAlchemy session
        dataset_name: Dataset name
        action_details: Dictionary with condition_field, condition_value, classification_path, rule_name
    """
    rule_name = action_details['rule_name']
    condition_field = action_details['condition_field']
    condition_value = action_details['condition_value']
    classification_path = action_details['classification_path']

    # Create new transaction rule
    new_rule = TransactionRule(
        dataset_name=dataset_name,
        rule_name=rule_name,
        rule_condition={condition_field: condition_value},
        classification_path=classification_path,
        priority=10,  # Default priority
        created_at=datetime.utcnow(),
        active=True
    )

    session.add(new_rule)
    session.commit()
