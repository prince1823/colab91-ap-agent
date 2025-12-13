"""Transactions API router."""

from typing import Optional

from fastapi import APIRouter, Query

from api.models.responses import TransactionsResponse
from core.hitl.csv_service import query_classified_transactions

router = APIRouter(prefix="/api/v1", tags=["transactions"])


@router.get("/transactions", response_model=TransactionsResponse)
def get_transactions(
    csv_path: str = Query(..., description="Path to the output CSV file"),
    l1: Optional[str] = Query(None, description="Filter by L1 category"),
    confidence: Optional[str] = Query(None, description="Filter by confidence level"),
    supplier_name: Optional[str] = Query(None, description="Filter by supplier name"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(50, ge=1, le=200, description="Number of rows per page")
):
    """
    Query classified transactions from CSV.

    Args:
        csv_path: Path to the output CSV file
        l1: Optional L1 category filter
        confidence: Optional confidence filter
        supplier_name: Optional supplier name filter
        page: Page number
        limit: Rows per page

    Returns:
        Paginated transaction data
    """
    filters = {}
    if l1:
        filters['l1'] = l1
    if confidence:
        filters['confidence'] = confidence
    if supplier_name:
        filters['supplier_name'] = supplier_name

    result = query_classified_transactions(csv_path, filters, page, limit)
    return result
