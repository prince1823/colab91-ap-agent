"""Feedback API router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import dspy
from api.models.requests import ApplyBulkRequest, ApproveFeedbackRequest, SubmitFeedbackRequest
from api.models.responses import (
    ApplyBulkResponse,
    ApproveFeedbackResponse,
    ExecuteActionResponse,
    PreviewAffectedRowsResponse,
    SubmitFeedbackResponse
)
from core.hitl.feedback_service import (
    apply_bulk_corrections,
    approve_feedback,
    execute_action,
    preview_affected_rows,
    submit_feedback
)

router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])


# Dependency to get database session
def get_db_session():
    """Get database session. This should be implemented based on your DB setup."""
    from core.database.schema import get_session_factory, init_database
    from core.config import get_config

    config = get_config()
    engine = init_database(config.database_path)
    Session = get_session_factory(engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


# Dependency to get DSPy language model
def get_lm():
    """Get configured DSPy language model."""
    from core.config import get_config

    config = get_config()

    # Configure DSPy LM based on settings
    if config.spend_classification_llm == "anthropic":
        lm = dspy.Claude(model="claude-sonnet-4-20250514", api_key=config.anthropic.api_key)
    else:
        lm = dspy.OpenAI(model="gpt-4", api_key=config.openai.api_key)

    return lm


@router.post("", response_model=SubmitFeedbackResponse)
def create_feedback(
    request: SubmitFeedbackRequest,
    session: Session = Depends(get_db_session),
    lm: dspy.LM = Depends(get_lm)
):
    """
    Submit user feedback and get LLM-generated action proposal.

    Args:
        request: Feedback submission request
        session: Database session
        lm: DSPy language model

    Returns:
        Feedback submission response with proposal
    """
    try:
        result = submit_feedback(
            session=session,
            csv_path=request.csv_path,
            row_index=request.row_index,
            corrected_path=request.corrected_path,
            feedback_text=request.feedback_text,
            dataset_name=request.dataset_name,
            lm=lm
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{feedback_id}/approve", response_model=ApproveFeedbackResponse)
def approve_user_feedback(
    feedback_id: int,
    request: ApproveFeedbackRequest,
    session: Session = Depends(get_db_session)
):
    """
    Approve feedback with optional user edits.

    Args:
        feedback_id: Feedback ID
        request: Approval request with optional edited text
        session: Database session

    Returns:
        Approval response
    """
    try:
        result = approve_feedback(
            session=session,
            feedback_id=feedback_id,
            user_edited_text=request.edited_text
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{feedback_id}/preview", response_model=PreviewAffectedRowsResponse)
def get_preview_affected_rows(
    feedback_id: int,
    session: Session = Depends(get_db_session)
):
    """
    Preview rows that will be affected by this action.

    Args:
        feedback_id: Feedback ID
        session: Database session

    Returns:
        Preview of affected rows
    """
    try:
        result = preview_affected_rows(session=session, feedback_id=feedback_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{feedback_id}/apply", response_model=ApplyBulkResponse)
def apply_feedback(
    feedback_id: int,
    request: ApplyBulkRequest,
    session: Session = Depends(get_db_session)
):
    """
    Execute action and apply bulk corrections.

    Args:
        feedback_id: Feedback ID
        request: Request with row indices to update
        session: Database session

    Returns:
        Bulk apply response
    """
    try:
        # First execute the action (update taxonomy/create rules)
        execute_action(session=session, feedback_id=feedback_id)

        # Then apply bulk corrections to CSV
        result = apply_bulk_corrections(
            session=session,
            feedback_id=feedback_id,
            row_indices=request.row_indices
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
