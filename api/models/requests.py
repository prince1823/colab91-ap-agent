"""Pydantic request models for HITL API."""

import re
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class SubmitFeedbackRequest(BaseModel):
    """Request model for submitting user feedback."""

    dataset_id: str = Field(..., description="Dataset identifier (e.g., 'innova', 'fox')")
    foldername: str = Field(default="default", description="Folder name (e.g., 'default', 'test_bench')")
    row_index: int = Field(..., ge=0, description="Row index in CSV (0-based)")
    corrected_path: str = Field(..., description="Corrected classification path (L1|L2|L3|L4)")
    feedback_text: str = Field(..., min_length=1, description="Natural language feedback explaining why classification was wrong")

    @field_validator("dataset_id")
    @classmethod
    def validate_dataset_id(cls, v: str) -> str:
        """Validate dataset ID format."""
        if not re.match(r"^[a-zA-Z0-9_.-]+$", v):
            raise ValueError("dataset_id can only contain alphanumeric characters, underscore, hyphen, and dot")
        return v

    @field_validator("foldername")
    @classmethod
    def validate_foldername(cls, v: str) -> str:
        """Validate foldername format."""
        if not re.match(r"^[a-zA-Z0-9_.-]+$", v):
            raise ValueError("foldername can only contain alphanumeric characters, underscore, hyphen, and dot")
        return v

    @field_validator("corrected_path")
    @classmethod
    def validate_corrected_path(cls, v: str) -> str:
        """Validate corrected path format."""
        parts = v.split("|")
        if len(parts) < 1 or len(parts) > 4:
            raise ValueError("corrected_path must have 1-4 levels separated by |")
        return v


class ApproveFeedbackRequest(BaseModel):
    """Request model for approving feedback."""

    edited_text: Optional[str] = Field(None, description="User's edited proposal text (optional)")


class ApplyBulkRequest(BaseModel):
    """Request model for applying bulk corrections."""

    row_indices: List[int] = Field(..., description="List of row indices to update")
