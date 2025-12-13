"""Pydantic response models for HITL API."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DatasetInfo(BaseModel):
    """Dataset information."""

    dataset_id: str
    foldername: str
    row_count: int


class DatasetDetailResponse(BaseModel):
    """Response model for detailed dataset information."""

    dataset_id: str
    foldername: str
    row_count: int
    csv_path_or_uri: str


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


class FeedbackDetailResponse(BaseModel):
    """Response model for detailed feedback information."""

    id: int
    dataset_id: str
    foldername: Optional[str]
    row_index: int
    original_classification: str
    corrected_classification: str
    feedback_text: Optional[str]
    action_type: str
    action_details: Dict[str, Any]
    action_reasoning: Optional[str]
    status: str
    proposal_text: Optional[str]
    user_edited_text: Optional[str]
    created_at: Any
    approved_at: Optional[Any]
    applied_at: Optional[Any]


class FeedbackListResponse(BaseModel):
    """Response model for feedback list item."""

    id: int
    dataset_id: str
    row_index: int
    original_classification: str
    corrected_classification: str
    action_type: str
    status: str
    created_at: Any


class FeedbackListPaginatedResponse(BaseModel):
    """Response model for paginated feedback list."""

    items: List[FeedbackListResponse]
    total: int
    page: int
    pages: int
    limit: int


# ==================== Supplier Rules Responses ====================

class DirectMappingResponse(BaseModel):
    """Response model for direct mapping rule."""

    id: int
    supplier_name: str
    classification_path: str
    dataset_name: Optional[str]
    priority: int
    active: bool
    created_at: Any
    updated_at: Any
    created_by: Optional[str]
    notes: Optional[str]


class TaxonomyConstraintResponse(BaseModel):
    """Response model for taxonomy constraint rule."""

    id: int
    supplier_name: str
    allowed_taxonomy_paths: List[str]
    dataset_name: Optional[str]
    priority: int
    active: bool
    created_at: Any
    updated_at: Any
    created_by: Optional[str]
    notes: Optional[str]


class TransactionDetailResponse(BaseModel):
    """Response model for single transaction."""

    row_index: int
    data: Dict[str, Any]
