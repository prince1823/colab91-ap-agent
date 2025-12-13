"""Workflow manager for orchestrating classification stages."""

import logging
from typing import Dict, Optional

from sqlalchemy.orm import Session

from core.classification.services.canonicalization_service import CanonicalizationService
from core.classification.services.verification_service import VerificationService
from core.classification.services.classification_service import ClassificationService
from core.database.models import DatasetProcessingState
from api.services.dataset_service import DatasetService

logger = logging.getLogger(__name__)


class WorkflowManager:
    """Manages the overall classification workflow."""

    def __init__(
        self,
        session: Session,
        dataset_service: DatasetService,
        taxonomy_path: str
    ):
        """
        Initialize workflow manager.

        Args:
            session: SQLAlchemy database session
            dataset_service: Dataset service
            taxonomy_path: Path to taxonomy YAML file
        """
        self.session = session
        self.dataset_service = dataset_service
        self.taxonomy_path = taxonomy_path

        self.canonicalization_service = CanonicalizationService(session, dataset_service)
        self.verification_service = VerificationService(session)
        self.classification_service = ClassificationService(
            session, dataset_service, taxonomy_path
        )

    def start_canonicalization(
        self, dataset_id: str, foldername: str = "default"
    ) -> Dict:
        """
        Start canonicalization stage.

        Args:
            dataset_id: Dataset identifier
            foldername: Folder name

        Returns:
            Dictionary with canonicalization result
        """
        mapping_result = self.canonicalization_service.canonicalize_dataset(
            dataset_id, foldername
        )

        return {
            "dataset_id": dataset_id,
            "foldername": foldername,
            "status": "canonicalized",
            "mapping_result": {
                "mappings": mapping_result.mappings,
                "unmapped_columns": mapping_result.unmapped_columns,
                "validation_passed": mapping_result.validation_passed,
            }
        }

    def get_workflow_status(
        self, dataset_id: str, foldername: str = "default"
    ) -> Dict:
        """
        Get current workflow status.

        Args:
            dataset_id: Dataset identifier
            foldername: Folder name

        Returns:
            Dictionary with workflow status
        """
        state = self.session.query(DatasetProcessingState).filter(
            DatasetProcessingState.dataset_id == dataset_id,
            DatasetProcessingState.foldername == foldername
        ).first()

        if not state:
            return {
                "dataset_id": dataset_id,
                "foldername": foldername,
                "status": "pending",
                "message": "No processing state found. Start with canonicalization."
            }

        return {
            "dataset_id": dataset_id,
            "foldername": foldername,
            "status": state.status,
            "canonicalized_csv_path": state.canonicalized_csv_path,
            "classification_result_path": state.classification_result_path,
            "run_id": state.run_id,
            "error_message": state.error_message,
            "created_at": state.created_at.isoformat() if state.created_at else None,
            "updated_at": state.updated_at.isoformat() if state.updated_at else None,
        }

    def continue_workflow(
        self, dataset_id: str, foldername: str = "default"
    ) -> Dict:
        """
        Continue workflow from current state.

        Args:
            dataset_id: Dataset identifier
            foldername: Folder name

        Returns:
            Dictionary with workflow status
        """
        state = self.get_workflow_status(dataset_id, foldername)

        if state["status"] == "pending":
            # Start canonicalization
            return self.start_canonicalization(dataset_id, foldername)
        elif state["status"] == "canonicalized" or state["status"] == "awaiting_verification":
            # Auto-approve for automated workflows (benchmarks)
            self.verification_service.approve_canonicalization(
                dataset_id, foldername, auto_approve=True
            )
            # Continue to classification
            return self._start_classification(dataset_id, foldername)
        elif state["status"] == "verified":
            # Start classification
            return self._start_classification(dataset_id, foldername)
        else:
            return {
                "dataset_id": dataset_id,
                "foldername": foldername,
                "status": state["status"],
                "message": f"Cannot continue from status: {state['status']}"
            }

    def _start_classification(
        self, dataset_id: str, foldername: str = "default"
    ) -> Dict:
        """Start classification stage."""
        result_df = self.classification_service.classify_dataset(
            dataset_id, foldername, max_workers=4
        )

        return {
            "dataset_id": dataset_id,
            "foldername": foldername,
            "status": "completed",
            "row_count": len(result_df),
        }

