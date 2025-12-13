"""Transactions API router."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_dataset_service
from api.exceptions import DatasetNotFoundError, InvalidDatasetIdError
from api.models.responses import TransactionsResponse
from api.services.dataset_service import DatasetService
from core.hitl.csv_service import query_classified_transactions

router = APIRouter(prefix="/api/v1", tags=["transactions"])


@router.get("/transactions", response_model=TransactionsResponse)
def get_transactions(
    dataset_id: str = Query(..., description="Dataset identifier (e.g., 'innova', 'fox')"),
    foldername: str = Query("default", description="Folder name (e.g., 'default', 'test_bench')"),
    l1: Optional[str] = Query(None, description="Filter by L1 category"),
    confidence: Optional[str] = Query(None, description="Filter by confidence level"),
    supplier_name: Optional[str] = Query(None, description="Filter by supplier name"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(50, ge=1, le=200, description="Number of rows per page"),
    dataset_service: DatasetService = Depends(get_dataset_service),
):
    """
    Query classified transactions from dataset.

    Args:
        dataset_id: Dataset identifier
        foldername: Folder name
        l1: Optional L1 category filter
        confidence: Optional confidence filter
        supplier_name: Optional supplier name filter
        page: Page number
        limit: Rows per page
        dataset_service: Dataset service dependency

    Returns:
        Paginated transaction data

    Raises:
        HTTPException: If dataset not found or invalid
    """
    try:
        csv_path_or_uri = dataset_service.get_output_csv_path(dataset_id, foldername)

        filters = {}
        if l1:
            filters["l1"] = l1
        if confidence:
            filters["confidence"] = confidence
        if supplier_name:
            filters["supplier_name"] = supplier_name

        result = query_classified_transactions(csv_path_or_uri, filters, page, limit)
        return result
    except (DatasetNotFoundError, InvalidDatasetIdError) as e:
        raise HTTPException(status_code=404, detail=str(e))
