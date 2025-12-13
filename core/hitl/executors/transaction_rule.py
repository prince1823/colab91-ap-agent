"""Executor for transaction rule actions."""

from datetime import datetime
from typing import Dict, List

from sqlalchemy.orm import Session

from core.database.models import TransactionRule
from core.hitl.executors.base import BaseActionExecutor
from core.hitl.services.csv_service import CSVService


class TransactionRuleExecutor(BaseActionExecutor):
    """Executor for transaction rule creation actions."""

    def __init__(self, csv_service: CSVService = None):
        """
        Initialize transaction rule executor.

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

    def preview_affected_rows(
        self,
        csv_path: str,
        action_details: Dict
    ) -> List[Dict]:
        """
        Find all rows matching a transaction rule condition.

        Args:
            csv_path: Path to the CSV file
            action_details: Dictionary with condition_field, condition_value

        Returns:
            List of row dictionaries with their indices
        """
        condition_field = action_details.get('condition_field', '')
        condition_value = action_details.get('condition_value', '')
        return self.csv_service.find_rows_by_condition(csv_path, condition_field, condition_value)

