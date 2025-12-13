"""Feedback API router."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import dspy
from api.dependencies import get_db_session, get_dataset_service, get_lm
from core.database.models import UserFeedback
from api.exceptions import (
    DatasetNotFoundError,
    FeedbackNotFoundError,
    InvalidDatasetIdError,
    InvalidFeedbackStateError,
    TransactionNotFoundError,
)
from api.models.requests import ApplyBulkRequest, ApproveFeedbackRequest, SubmitFeedbackRequest
from api.models.responses import (
    ApplyBulkResponse,
    ApproveFeedbackResponse,
    ExecuteActionResponse,
    FeedbackDetailResponse,
    FeedbackListPaginatedResponse,
    FeedbackListResponse,
    PreviewAffectedRowsResponse,
    SubmitFeedbackResponse,
)
from api.services.dataset_service import DatasetService
from core.hitl.service import FeedbackService

router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])

# Initialize feedback service instance for read-only operations
# Note: This instance doesn't have DatasetService, which is fine for:
# - list_feedback_items (database queries only)
# - get_feedback_item (database queries only)
# - approve_feedback (database updates only)
# - preview_affected_rows (reads CSV via CSVService, doesn't need DatasetService)
# - delete_feedback_item (database deletion only)
# For operations that need DatasetService (submit_feedback, apply_feedback), 
# we create new FeedbackService instances with DatasetService dependency injection.
_feedback_service = FeedbackService()


@router.get("", response_model=FeedbackListPaginatedResponse)
def list_feedback(
    status: Optional[str] = Query(None, description="Filter by status (pending, approved, applied)"),
    dataset_id: Optional[str] = Query(None, description="Filter by dataset ID"),
    action_type: Optional[str] = Query(None, description="Filter by action type"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(50, ge=1, le=200, description="Number of items per page"),
    session: Session = Depends(get_db_session),
):
    """
    List all feedback items with optional filters and pagination.
    
    Args:
        status: Filter by status (pending, approved, applied)
        dataset_id: Filter by dataset ID
        action_type: Filter by action type
        page: Page number
        limit: Items per page
        session: Database session
        
    Returns:
        Paginated list of feedback items
    """
    result = _feedback_service.list_feedback_items(
        session=session,
        status=status,
        dataset_id=dataset_id,
        action_type=action_type,
        page=page,
        limit=limit,
    )
    
    items = [
        FeedbackListResponse(
            id=item.id,
            dataset_id=item.dataset_name,
            row_index=item.row_index,
            original_classification=item.original_classification,
            corrected_classification=item.corrected_classification,
            action_type=item.action_type,
            status=item.status,
            created_at=item.created_at,
        )
        for item in result['items']
    ]
    
    return FeedbackListPaginatedResponse(
        items=items,
        total=result['total'],
        page=result['page'],
        pages=result['pages'],
        limit=result['limit'],
    )


@router.get("/{feedback_id}", response_model=FeedbackDetailResponse)
def get_feedback(
    feedback_id: int,
    session: Session = Depends(get_db_session),
):
    """
    Get detailed information about a specific feedback item.
    
    Args:
        feedback_id: Feedback ID
        session: Database session
        
    Returns:
        Detailed feedback information
        
    Raises:
        HTTPException: If feedback not found
    """
    feedback = _feedback_service.get_feedback_item(session, feedback_id)
    if not feedback:
        raise HTTPException(status_code=404, detail=f"Feedback {feedback_id} not found")
    
    return FeedbackDetailResponse(
        id=feedback.id,
        dataset_id=feedback.dataset_name,
        foldername=feedback.foldername,
        row_index=feedback.row_index,
        original_classification=feedback.original_classification,
        corrected_classification=feedback.corrected_classification,
        feedback_text=feedback.feedback_text,
        action_type=feedback.action_type,
        action_details=feedback.action_details,
        action_reasoning=feedback.action_reasoning,
        status=feedback.status,
        proposal_text=feedback.proposal_text,
        user_edited_text=feedback.user_edited_text,
        created_at=feedback.created_at,
        approved_at=feedback.approved_at,
        applied_at=feedback.applied_at,
    )


@router.post("", response_model=SubmitFeedbackResponse)
def create_feedback(
    request: SubmitFeedbackRequest,
    session: Session = Depends(get_db_session),
    lm: dspy.LM = Depends(get_lm),
    dataset_service: DatasetService = Depends(get_dataset_service),
):
    """
    Submit user feedback and get LLM-generated action proposal.

    Args:
        request: Feedback submission request
        session: Database session
        lm: DSPy language model
        dataset_service: Dataset service dependency

    Returns:
        Feedback submission response with proposal

    Raises:
        HTTPException: If dataset not found or invalid
    """
    try:
        csv_path = dataset_service.get_output_csv_path(request.dataset_id, request.foldername)

        # Create a FeedbackService instance with the provided LM and DatasetService
        feedback_service = FeedbackService(lm=lm, dataset_service=dataset_service)
        result = feedback_service.submit_feedback(
            session=session,
            csv_path=csv_path,
            row_index=request.row_index,
            corrected_path=request.corrected_path,
            feedback_text=request.feedback_text,
            dataset_name=request.dataset_id,
        )
        return result
    except (DatasetNotFoundError, InvalidDatasetIdError, TransactionNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{feedback_id}/approve", response_model=ApproveFeedbackResponse)
def approve_user_feedback(
    feedback_id: int,
    request: ApproveFeedbackRequest,
    session: Session = Depends(get_db_session),
):
    """
    Approve feedback with optional user edits.

    Args:
        feedback_id: Feedback ID
        request: Approval request with optional edited text
        session: Database session

    Returns:
        Approval response

    Raises:
        HTTPException: If feedback not found
    """
    try:
        result = _feedback_service.approve_feedback(
            session=session,
            feedback_id=feedback_id,
            user_edited_text=request.edited_text,
        )
        return result
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{feedback_id}/preview", response_model=PreviewAffectedRowsResponse)
def get_preview_affected_rows(
    feedback_id: int,
    session: Session = Depends(get_db_session),
):
    """
    Preview rows that will be affected by this action.

    Args:
        feedback_id: Feedback ID
        session: Database session

    Returns:
        Preview of affected rows

    Raises:
        HTTPException: If feedback not found
    """
    try:
        result = _feedback_service.preview_affected_rows(session=session, feedback_id=feedback_id)
        return result
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{feedback_id}/apply", response_model=ApplyBulkResponse)
def apply_feedback(
    feedback_id: int,
    request: ApplyBulkRequest,
    session: Session = Depends(get_db_session),
    dataset_service: DatasetService = Depends(get_dataset_service),
):
    """
    Execute action and apply bulk corrections.

    Args:
        feedback_id: Feedback ID
        request: Request with row indices to update
        session: Database session
        dataset_service: Dataset service dependency

    Returns:
        Bulk apply response

    Raises:
        HTTPException: If feedback not found or in invalid state
    """
    try:
        # Create FeedbackService with DatasetService for taxonomy updates
        feedback_service = FeedbackService(dataset_service=dataset_service)
        
        # First execute the action (update taxonomy/create rules)
        feedback_service.execute_action(session=session, feedback_id=feedback_id)

        # Then apply bulk corrections to CSV
        result = feedback_service.apply_bulk_corrections(
            session=session,
            feedback_id=feedback_id,
            row_indices=request.row_indices,
            dataset_service=dataset_service,
        )
        return result
    except ValueError as e:
        error_str = str(e).lower()
        if "not found" in error_str:
            raise HTTPException(status_code=404, detail=str(e))
        if "must be approved" in error_str or "status" in error_str:
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{feedback_id}")
def delete_feedback(
    feedback_id: int,
    session: Session = Depends(get_db_session),
):
    """
    Delete/reject a feedback item.
    
    Args:
        feedback_id: Feedback ID
        session: Database session
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If feedback not found
    """
    try:
        _feedback_service.delete_feedback_item(session=session, feedback_id=feedback_id)
        return {"message": f"Feedback {feedback_id} deleted successfully"}
    except ValueError as e:
        error_str = str(e).lower()
        if "not found" in error_str:
            raise HTTPException(status_code=404, detail=str(e))
        if "cannot delete" in error_str or "status" in error_str:
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
