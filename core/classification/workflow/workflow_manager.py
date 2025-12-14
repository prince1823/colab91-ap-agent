"""Workflow manager for orchestrating classification stages."""

import logging
from pathlib import Path
from typing import Dict, Optional

from sqlalchemy.orm import Session

from core.classification.services.canonicalization_service import CanonicalizationService
from core.classification.services.verification_service import VerificationService
from core.classification.services.classification_service import ClassificationService
from core.database.models import DatasetProcessingState
from api.services.dataset_service import DatasetService
from core.classification.exceptions import WorkflowError
from core.classification.constants import (
    WorkflowStatus,
    DEFAULT_MAX_WORKERS
)

logger = logging.getLogger(__name__)


class WorkflowManager:
    """Manages the overall classification workflow."""

    def __init__(
        self,
        session: Session,
        dataset_service: DatasetService,
        taxonomy_path: Optional[str] = None
    ):
        """
        Initialize workflow manager.

        Args:
            session: SQLAlchemy database session
            dataset_service: Dataset service
            taxonomy_path: Optional path to taxonomy YAML file (resolved per-dataset when needed)
        """
        self.session = session
        self.dataset_service = dataset_service
        self.taxonomy_path = taxonomy_path

        self.canonicalization_service = CanonicalizationService(session, dataset_service)
        self.verification_service = VerificationService(session)
        # Classification service will be created with dataset-specific taxonomy path when needed
        # For now, pass None - it will be resolved in the classification endpoint
        self.classification_service = None

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
            "status": WorkflowStatus.CANONICALIZED,
            "mapping_result": {
                "mappings": mapping_result.mappings,
                "unmapped_columns": mapping_result.unmapped_client_columns,
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
                "status": WorkflowStatus.PENDING,
                "message": "No processing state found. Start with canonicalization."
            }

        result = {
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
        
        # Add progress tracking if available (for async classification)
        if hasattr(state, 'progress_invoices_total') and state.progress_invoices_total is not None:
            result["progress_invoices_total"] = state.progress_invoices_total
            result["progress_invoices_processed"] = state.progress_invoices_processed or 0
            result["progress_percentage"] = state.progress_percentage or 0
        
        return result

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
        current_status = state["status"]

        if current_status == WorkflowStatus.PENDING:
            # Start canonicalization
            return self.start_canonicalization(dataset_id, foldername)
        elif current_status in (WorkflowStatus.CANONICALIZED, WorkflowStatus.AWAITING_VERIFICATION):
            # Auto-approve for automated workflows (benchmarks)
            self.verification_service.approve_canonicalization(
                dataset_id, foldername, auto_approve=True
            )
            # Continue to classification
            return self._start_classification(dataset_id, foldername)
        elif current_status == WorkflowStatus.VERIFIED:
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
        taxonomy_path = self._get_taxonomy_path(dataset_id, foldername)
        
        # Create classification service with dataset-specific taxonomy
        classification_service = ClassificationService(
            self.session, self.dataset_service, taxonomy_path
        )
        
        result_df = classification_service.classify_dataset(
            dataset_id, foldername, max_workers=DEFAULT_MAX_WORKERS
        )

        return {
            "dataset_id": dataset_id,
            "foldername": foldername,
            "status": WorkflowStatus.COMPLETED,
            "row_count": len(result_df),
        }

    def _get_taxonomy_path(self, dataset_id: str, foldername: str) -> str:
        """
        Get taxonomy path from dataset directory (same level as input.csv).

        Args:
            dataset_id: Dataset identifier
            foldername: Folder name

        Returns:
            Path to taxonomy YAML file

        Raises:
            WorkflowError: If taxonomy file not found
        """
        try:
            # Get the actual taxonomy file path from storage
            if hasattr(self.dataset_service.storage, '_get_yaml_path'):
                taxonomy_path = str(self.dataset_service.storage._get_yaml_path(dataset_id, foldername))
            else:
                # Fallback: construct path manually
                from pathlib import Path
                from core.config import get_config
                config = get_config()
                datasets_dir = config.datasets_dir
                if foldername == "":
                    taxonomy_path = str(datasets_dir / dataset_id / "taxonomy.yaml")
                else:
                    taxonomy_path = str(datasets_dir / foldername / dataset_id / "taxonomy.yaml")
            
            # Verify the file exists
            taxonomy_file = Path(taxonomy_path)
            if not taxonomy_file.exists():
                raise FileNotFoundError(f"Taxonomy file not found: {taxonomy_path}")
            
            return taxonomy_path
        except Exception as e:
            raise WorkflowError(
                f"Could not load taxonomy from dataset {dataset_id}: {e}. "
                f"Expected taxonomy.yaml in the same directory as input.csv."
            ) from e

