"""Feedback API router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import dspy
from api.dependencies import get_db_session, get_dataset_service, get_lm
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
    PreviewAffectedRowsResponse,
    SubmitFeedbackResponse,
)
from api.services.dataset_service import DatasetService
from core.hitl.feedback_service import (
    apply_bulk_corrections,
    approve_feedback,
    execute_action,
    preview_affected_rows,
    submit_feedback,
)

router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])


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

        result = submit_feedback(
            session=session,
            csv_path=csv_path,
            row_index=request.row_index,
            corrected_path=request.corrected_path,
            feedback_text=request.feedback_text,
            dataset_name=request.dataset_id,
            lm=lm,
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
        result = approve_feedback(
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
        result = preview_affected_rows(session=session, feedback_id=feedback_id)
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
):
    """
    Execute action and apply bulk corrections.

    Args:
        feedback_id: Feedback ID
        request: Request with row indices to update
        session: Database session

    Returns:
        Bulk apply response

    Raises:
        HTTPException: If feedback not found or in invalid state
    """
    try:
        # First execute the action (update taxonomy/create rules)
        execute_action(session=session, feedback_id=feedback_id)

        # Then apply bulk corrections to CSV
        dataset_service = get_dataset_service()
        result = apply_bulk_corrections(
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
