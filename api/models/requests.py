"""Pydantic request models for HITL API."""

import re
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from api.models.validation_helpers import (
    validate_classification_path_format,
    validate_supplier_name,
    validate_taxonomy_paths_list,
)


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


# ==================== Supplier Rules Requests ====================

class CreateDirectMappingRequest(BaseModel):
    """Request model for creating a direct mapping rule."""

    supplier_name: str = Field(..., description="Supplier name", min_length=1, max_length=255)
    classification_path: str = Field(..., description="Classification path (L1|L2|L3|L4|L5)", max_length=500)
    dataset_name: Optional[str] = Field(None, description="Dataset name (None = applies to all datasets)", max_length=255)
    priority: int = Field(10, ge=1, le=100, description="Priority (higher = checked first)")
    notes: Optional[str] = Field(None, description="Optional notes")
    created_by: Optional[str] = Field(None, description="User who created this rule", max_length=255)

    @field_validator("supplier_name")
    @classmethod
    def validate_supplier_name(cls, v: str) -> str:
        """Normalize and validate supplier name."""
        return validate_supplier_name(v)

    @field_validator("classification_path")
    @classmethod
    def validate_classification_path(cls, v: str) -> str:
        """Validate classification path format."""
        return validate_classification_path_format(v)


class UpdateDirectMappingRequest(BaseModel):
    """Request model for updating a direct mapping rule."""

    classification_path: Optional[str] = Field(None, description="Classification path (L1|L2|L3|L4|L5)", max_length=500)
    priority: Optional[int] = Field(None, ge=1, le=100, description="Priority (higher = checked first)")
    active: Optional[bool] = Field(None, description="Whether the rule is active")
    notes: Optional[str] = Field(None, description="Optional notes")

    @field_validator("classification_path")
    @classmethod
    def validate_classification_path(cls, v: Optional[str]) -> Optional[str]:
        """Validate classification path format if provided."""
        if v is None:
            return v
        return validate_classification_path_format(v)


class CreateTaxonomyConstraintRequest(BaseModel):
    """Request model for creating a taxonomy constraint rule."""

    supplier_name: str = Field(..., description="Supplier name", min_length=1, max_length=255)
    allowed_taxonomy_paths: List[str] = Field(..., min_length=1, description="List of allowed taxonomy paths")
    dataset_name: Optional[str] = Field(None, description="Dataset name (None = applies to all datasets)", max_length=255)
    priority: int = Field(10, ge=1, le=100, description="Priority (higher = checked first)")
    notes: Optional[str] = Field(None, description="Optional notes")
    created_by: Optional[str] = Field(None, description="User who created this rule", max_length=255)

    @field_validator("supplier_name")
    @classmethod
    def validate_supplier_name(cls, v: str) -> str:
        """Normalize and validate supplier name."""
        return validate_supplier_name(v)

    @field_validator("allowed_taxonomy_paths")
    @classmethod
    def validate_taxonomy_paths(cls, v: List[str]) -> List[str]:
        """Validate taxonomy paths format."""
        return validate_taxonomy_paths_list(v)


class UpdateTaxonomyConstraintRequest(BaseModel):
    """Request model for updating a taxonomy constraint rule."""

    allowed_taxonomy_paths: Optional[List[str]] = Field(None, min_length=1, description="List of allowed taxonomy paths")
    priority: Optional[int] = Field(None, ge=1, le=100, description="Priority (higher = checked first)")
    active: Optional[bool] = Field(None, description="Whether the constraint is active")
    notes: Optional[str] = Field(None, description="Optional notes")

    @field_validator("allowed_taxonomy_paths")
    @classmethod
    def validate_taxonomy_paths(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validate taxonomy paths format if provided."""
        if v is None:
            return v
        return validate_taxonomy_paths_list(v)


class UpdateTransactionRequest(BaseModel):
    """Request model for updating a transaction classification."""

    classification_path: str = Field(..., description="Updated classification path (L1|L2|L3|L4|L5)")
    override_rule_applied: Optional[str] = Field(None, description="Optional rule identifier that was applied")
