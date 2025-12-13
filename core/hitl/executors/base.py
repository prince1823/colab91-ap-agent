"""Base class for action executors."""

from abc import ABC, abstractmethod
from typing import Dict, List

from sqlalchemy.orm import Session


class BaseActionExecutor(ABC):
    """Base class for action executors in the HITL feedback system."""

    @abstractmethod
    def execute(
        self,
        session: Session,
        dataset_name: str,
        action_details: Dict
    ) -> None:
        """
        Execute the action.

        Args:
            session: SQLAlchemy database session
            dataset_name: Dataset name
            action_details: Dictionary with action-specific details

        Raises:
            ValueError: If action_details are invalid
        """
        pass

    @abstractmethod
    def preview_affected_rows(
        self,
        csv_path: str,
        action_details: Dict
    ) -> List[Dict]:
        """
        Preview rows that will be affected by this action.

        Args:
            csv_path: Path to the CSV file
            action_details: Dictionary with action-specific details

        Returns:
            List of row dictionaries with their indices
        """
        pass

