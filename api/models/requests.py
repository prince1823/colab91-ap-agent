"""Pydantic request models for HITL API."""

from typing import List, Optional

from pydantic import BaseModel, Field


class SubmitFeedbackRequest(BaseModel):
    """Request model for submitting user feedback."""

    csv_path: str = Field(..., description="Path to the output CSV file")
    row_index: int = Field(..., ge=0, description="Row index in CSV (0-based)")
    corrected_path: str = Field(..., description="Corrected classification path (L1|L2|L3|L4)")
    feedback_text: str = Field(..., description="Natural language feedback explaining why classification was wrong")
    dataset_name: str = Field(..., description="Dataset name (e.g., 'innova', 'fox')")


class ApproveFeedbackRequest(BaseModel):
    """Request model for approving feedback."""

    edited_text: Optional[str] = Field(None, description="User's edited proposal text (optional)")


class ApplyBulkRequest(BaseModel):
    """Request model for applying bulk corrections."""

    row_indices: List[int] = Field(..., description="List of row indices to update")
