"""Classification workflow API router."""

import logging
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from api.dependencies import get_db_session, get_dataset_service
from api.exceptions import DatasetNotFoundError, InvalidDatasetIdError
from api.models.requests import VerifyCanonicalizationRequest
from api.models.responses import (
    CanonicalizationReviewResponse,
    ClassificationStatusResponse,
    WorkflowStatusResponse,
)
from api.services.dataset_service import DatasetService
from core.classification.services.verification_service import VerificationService
from core.classification.services.classification_service import ClassificationService
from core.classification.workflow.workflow_manager import WorkflowManager
from core.classification.exceptions import (
    WorkflowError,
    CanonicalizationError,
    VerificationError,
    ClassificationError,
    InvalidStateTransitionError,
    InvalidColumnError,
    CSVIntegrityError
)
from core.config import get_config

router = APIRouter(prefix="/api/v1", tags=["classification"])


def get_workflow_manager(
    session: Session = Depends(get_db_session),
    dataset_service: DatasetService = Depends(get_dataset_service),
) -> WorkflowManager:
    """Get workflow manager instance."""
    # Note: Taxonomy path will be determined per-dataset when needed
    # For workflow manager, we use None as placeholder - actual taxonomy is loaded from dataset directory
    # The actual taxonomy path is resolved per-dataset in each service (canonicalization, classification)
    return WorkflowManager(session, dataset_service, taxonomy_path=None)


@router.post("/datasets/{dataset_id}/canonicalize", response_model=Dict)
def start_canonicalization(
    dataset_id: str,
    foldername: str = Query("default", description="Folder name"),
    workflow_manager: WorkflowManager = Depends(get_workflow_manager),
):
    """
    Start canonicalization stage for a dataset.

    Args:
        dataset_id: Dataset identifier
        foldername: Folder name
        workflow_manager: Workflow manager dependency

    Returns:
        Canonicalization result

    Raises:
        HTTPException: If dataset not found or canonicalization fails
    """
    try:
        result = workflow_manager.start_canonicalization(dataset_id, foldername)
        return result
    except (DatasetNotFoundError, InvalidDatasetIdError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (CanonicalizationError, InvalidStateTransitionError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Canonicalization failed: {str(e)}")


@router.get("/datasets/{dataset_id}/canonicalization", response_model=CanonicalizationReviewResponse)
def get_canonicalization_review(
    dataset_id: str,
    foldername: str = Query("default", description="Folder name"),
    session: Session = Depends(get_db_session),
):
    """
    Get canonicalization result for human review.

    Args:
        dataset_id: Dataset identifier
        foldername: Folder name
        session: Database session

    Returns:
        Canonicalization review data

    Raises:
        HTTPException: If dataset not found or not canonicalized
    """
    try:
        verification_service = VerificationService(session)
        review_data = verification_service.get_canonicalization_for_review(dataset_id, foldername)
        return CanonicalizationReviewResponse(**review_data)
    except VerificationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get canonicalization review: {str(e)}")


@router.post("/datasets/{dataset_id}/verify", response_model=Dict)
def approve_canonicalization(
    dataset_id: str,
    request: VerifyCanonicalizationRequest,
    foldername: str = Query("default", description="Folder name"),
    session: Session = Depends(get_db_session),
):
    """
    Approve/update canonicalization mappings with column modifications.

    Human-in-the-loop verification allows:
    - Updating column mappings (correcting LLM mistakes)
    - Adding missing columns important for classification (with default values)
    - Removing unwanted columns that shouldn't be processed

    Args:
        dataset_id: Dataset identifier
        request: Verification request with:
            - approved_mappings: Optional updated column mappings
            - columns_to_add: Optional list of columns to add (each with canonical_name, default_value, description)
            - columns_to_remove: Optional list of canonical column names to remove
            - notes: Optional verification notes
            - auto_approve: Auto-approve flag (for benchmarks)
        foldername: Folder name
        session: Database session

    Returns:
        Success response with modification summary

    Raises:
        HTTPException: If dataset not found or not in correct state
    """
    try:
        verification_service = VerificationService(session)
        verification_service.approve_canonicalization(
            dataset_id,
            foldername,
            approved_mappings=request.approved_mappings,
            columns_to_add=request.columns_to_add,
            columns_to_remove=request.columns_to_remove,
            notes=request.notes,
            auto_approve=request.auto_approve
        )
        return {"status": "verified", "message": "Canonicalization approved"}
    except (VerificationError, InvalidColumnError, InvalidStateTransitionError, CSVIntegrityError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")


@router.post("/datasets/{dataset_id}/classify", response_model=Dict)
def start_classification(
    dataset_id: str,
    foldername: str = Query("default", description="Folder name"),
    max_workers: int = Query(4, ge=1, le=16, description="Number of parallel workers"),
    session: Session = Depends(get_db_session),
    dataset_service: DatasetService = Depends(get_dataset_service),
):
    """
    Start classification stage (after verification).

    Args:
        dataset_id: Dataset identifier
        foldername: Folder name
        max_workers: Number of parallel workers
        session: Database session
        dataset_service: Dataset service

    Returns:
        Classification result summary

    Raises:
        HTTPException: If dataset not found or not verified
    """
    try:
        # Get taxonomy path directly from dataset directory (same level as input.csv)
        try:
            # Get the actual taxonomy file path from storage
            if hasattr(dataset_service.storage, '_get_yaml_path'):
                taxonomy_path = str(dataset_service.storage._get_yaml_path(dataset_id, foldername))
            else:
                # Fallback: construct path manually
                from pathlib import Path
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
        except Exception as e:
            # No fallback - taxonomy must exist in dataset directory
            logger.error(f"Could not load taxonomy from dataset {dataset_id}: {e}")
            raise HTTPException(
                status_code=404,
                detail=f"Taxonomy file not found for dataset '{dataset_id}' in folder '{foldername}'. "
                       f"Expected taxonomy.yaml in the same directory as input.csv."
            )
        
        classification_service = ClassificationService(
            session, dataset_service, taxonomy_path
        )
        result_df = classification_service.classify_dataset(
            dataset_id, foldername, max_workers=max_workers
        )
        
        return {
            "status": "completed",
            "dataset_id": dataset_id,
            "foldername": foldername,
            "row_count": len(result_df),
            "message": "Classification completed successfully"
        }
    except (ClassificationError, InvalidStateTransitionError, CSVIntegrityError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Classification failed: {str(e)}")


@router.get("/datasets/{dataset_id}/status", response_model=WorkflowStatusResponse)
def get_workflow_status(
    dataset_id: str,
    foldername: str = Query("default", description="Folder name"),
    workflow_manager: WorkflowManager = Depends(get_workflow_manager),
):
    """
    Get current workflow status for a dataset.

    Args:
        dataset_id: Dataset identifier
        foldername: Folder name
        workflow_manager: Workflow manager dependency

    Returns:
        Workflow status information
    """
    status = workflow_manager.get_workflow_status(dataset_id, foldername)
    return WorkflowStatusResponse(**status)

