"""Pydantic response models for HITL API."""

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class DatasetInfo(BaseModel):
    """Dataset information."""

    csv_path: str
    dataset_name: str
    foldername: str
    row_count: int


class TransactionsResponse(BaseModel):
    """Response model for transaction queries."""

    rows: List[Dict[str, Any]]
    total: int
    page: int
    pages: int
    limit: int


class SubmitFeedbackResponse(BaseModel):
    """Response model for feedback submission."""

    feedback_id: int
    action_type: str
    proposal_text: str
    action_details: Dict[str, Any]


class ApproveFeedbackResponse(BaseModel):
    """Response model for feedback approval."""

    status: str
    issues: List[str]


class ExecuteActionResponse(BaseModel):
    """Response model for action execution."""

    action_applied: bool


class PreviewAffectedRowsResponse(BaseModel):
    """Response model for previewing affected rows."""

    rows: List[Dict[str, Any]]
    count: int
    row_indices: List[int]


class ApplyBulkResponse(BaseModel):
    """Response model for bulk corrections."""

    updated_count: int
