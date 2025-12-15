"""Classification workflow API router."""

import logging
import threading
from typing import Dict, Optional

from pathlib import Path
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


def _run_classification_in_background(
    dataset_id: str,
    foldername: str,
    taxonomy_path: str,
    max_workers: int,
    db_path: str
):
    """
    Run classification in a background thread.
    
    This function runs in a separate thread and creates its own database session.
    """
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import create_engine
    from pathlib import Path
    from api.services.dataset_service import DatasetService
    from core.classification.services.classification_service import ClassificationService
    from core.database.models import DatasetProcessingState
    
    # Create a new database session for this thread
    engine = create_engine(f"sqlite:///{db_path}")
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    try:
        # Verify taxonomy path exists
        if not Path(taxonomy_path).exists():
            raise FileNotFoundError(f"Taxonomy file not found: {taxonomy_path}")
        
        dataset_service = DatasetService()
        classification_service = ClassificationService(
            session, dataset_service, taxonomy_path
        )
        
        logger.info(f"Starting background classification for {dataset_id}/{foldername}")
        result_df = classification_service.classify_dataset(
            dataset_id, foldername, max_workers=max_workers
        )
        logger.info(f"Background classification completed for {dataset_id}/{foldername}: {len(result_df)} rows")
    except Exception as e:
        logger.error(f"Background classification failed for {dataset_id}/{foldername}: {e}", exc_info=True)
        # Update error state
        try:
            state = session.query(DatasetProcessingState).filter(
                DatasetProcessingState.dataset_id == dataset_id,
                DatasetProcessingState.foldername == foldername
            ).first()
            if state:
                state.status = "failed"
                state.error_message = str(e)
                session.commit()
        except Exception as db_error:
            session.rollback()
            logger.error(f"Failed to update error state: {db_error}", exc_info=True)
    finally:
        session.close()


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
    
    This endpoint starts classification asynchronously and returns immediately.
    Use the GET /datasets/{dataset_id}/status endpoint to poll for progress.

    Args:
        dataset_id: Dataset identifier
        foldername: Folder name
        max_workers: Number of parallel workers
        session: Database session
        dataset_service: Dataset service

    Returns:
        Response indicating classification has started

    Raises:
        HTTPException: If dataset not found or not verified
    """
    try:
        # Verify dataset is in correct state
        from core.database.models import DatasetProcessingState
        from core.classification.constants import WorkflowStatus
        from core.classification.validators import validate_state_transition
        
        state = session.query(DatasetProcessingState).filter(
            DatasetProcessingState.dataset_id == dataset_id,
            DatasetProcessingState.foldername == foldername
        ).first()
        
        if not state:
            raise HTTPException(
                status_code=404,
                detail=f"Dataset '{dataset_id}' not found in folder '{foldername}'. Please run canonicalization first."
            )
        
        if state.status not in [WorkflowStatus.VERIFIED, WorkflowStatus.COMPLETED]:
            raise HTTPException(
                status_code=400,
                detail=f"Dataset must be verified before classification. Current status: {state.status}"
            )
        
        # Check if classification is already running
        if state.status == WorkflowStatus.CLASSIFYING:
            return {
                "status": "already_running",
                "dataset_id": dataset_id,
                "foldername": foldername,
                "message": "Classification is already in progress. Poll /status endpoint for progress."
            }
        
        # Get taxonomy path directly from dataset directory (same level as input.csv)
        from pathlib import Path
        try:
            # Get the actual taxonomy file path from storage
            if hasattr(dataset_service.storage, '_get_yaml_path'):
                taxonomy_path_obj = dataset_service.storage._get_yaml_path(dataset_id, foldername)
                # Convert Path object to absolute string path
                if isinstance(taxonomy_path_obj, Path):
                    taxonomy_path = str(taxonomy_path_obj.resolve())
                else:
                    taxonomy_path = str(taxonomy_path_obj)
            else:
                # Fallback: construct path manually
                config = get_config()
                datasets_dir = Path(config.datasets_dir)
                if foldername == "":
                    taxonomy_path = str((datasets_dir / dataset_id / "taxonomy.yaml").resolve())
                else:
                    taxonomy_path = str((datasets_dir / foldername / dataset_id / "taxonomy.yaml").resolve())
            
            # Verify the file exists
            taxonomy_file = Path(taxonomy_path)
            if not taxonomy_file.exists():
                raise FileNotFoundError(f"Taxonomy file not found: {taxonomy_path}")
            
            logger.info(f"Using taxonomy path: {taxonomy_path}")
        except Exception as e:
            # No fallback - taxonomy must exist in dataset directory
            logger.error(f"Could not load taxonomy from dataset {dataset_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=404,
                detail=f"Taxonomy file not found for dataset '{dataset_id}' in folder '{foldername}'. "
                       f"Expected taxonomy.yaml in the same directory as input.csv. Error: {str(e)}"
            )
        
        # Update state to "classifying" before starting background thread
        try:
            validate_state_transition(state.status, WorkflowStatus.CLASSIFYING)
            state.status = WorkflowStatus.CLASSIFYING
            state.progress_invoices_total = None
            state.progress_invoices_processed = 0
            state.progress_percentage = 0
            session.commit()
        except Exception as e:
            session.rollback()
            raise HTTPException(status_code=400, detail=f"Failed to update state: {str(e)}")
        
        # Get database path for background thread
        config = get_config()
        db_path = str(config.database_path)
        
        # Start classification in background thread
        thread = threading.Thread(
            target=_run_classification_in_background,
            args=(dataset_id, foldername, taxonomy_path, max_workers, db_path),
            daemon=True
        )
        thread.start()
        
        return {
            "status": "started",
            "dataset_id": dataset_id,
            "foldername": foldername,
            "message": "Classification started. Poll GET /datasets/{dataset_id}/status endpoint for progress."
        }
    except HTTPException:
        raise
    except (ClassificationError, InvalidStateTransitionError, CSVIntegrityError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to start classification: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start classification: {str(e)}")


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

