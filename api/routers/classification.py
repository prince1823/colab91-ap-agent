"""Classification workflow API router."""

from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

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
from core.config import get_config

router = APIRouter(prefix="/api/v1", tags=["classification"])


def get_workflow_manager(
    session: Session = Depends(get_db_session),
    dataset_service: DatasetService = Depends(get_dataset_service),
) -> WorkflowManager:
    """Get workflow manager instance."""
    # Get taxonomy path - in production, this should come from dataset metadata
    config = get_config()
    # For now, use a default - this should be improved to get from dataset
    taxonomy_path = "taxonomies/default.yaml"
    return WorkflowManager(session, dataset_service, taxonomy_path)


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
    except ValueError as e:
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
    except ValueError as e:
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
    except ValueError as e:
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
        config = get_config()
        # Get taxonomy path from dataset - for now use default
        # TODO: Get taxonomy path from dataset metadata
        taxonomy_path = "taxonomies/default.yaml"
        
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
    except ValueError as e:
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

