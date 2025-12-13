"""Transactions API router."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_dataset_service
from api.exceptions import DatasetNotFoundError, InvalidDatasetIdError, TransactionNotFoundError
from api.models.requests import UpdateTransactionRequest
from api.models.responses import TransactionDetailResponse, TransactionsResponse
from api.services.dataset_service import DatasetService
from core.hitl.csv_service import get_transaction_by_row_index, query_classified_transactions

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


@router.get("/transactions/{row_index}", response_model=TransactionDetailResponse)
def get_transaction(
    row_index: int,
    dataset_id: str = Query(..., description="Dataset identifier (e.g., 'innova', 'fox')"),
    foldername: str = Query("default", description="Folder name (e.g., 'default', 'test_bench')"),
    dataset_service: DatasetService = Depends(get_dataset_service),
):
    """
    Get a single transaction by row index.
    
    Args:
        row_index: Row index (0-based)
        dataset_id: Dataset identifier
        foldername: Folder name
        dataset_service: Dataset service dependency
        
    Returns:
        Transaction data
        
    Raises:
        HTTPException: If dataset or transaction not found
    """
    try:
        csv_path_or_uri = dataset_service.get_output_csv_path(dataset_id, foldername)
        transaction = get_transaction_by_row_index(csv_path_or_uri, row_index)
        
        if not transaction:
            raise TransactionNotFoundError(f"Transaction at row {row_index} not found")
        
        return TransactionDetailResponse(
            row_index=row_index,
            data=transaction,
        )
    except (DatasetNotFoundError, InvalidDatasetIdError, TransactionNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/transactions/{row_index}", response_model=TransactionDetailResponse)
def update_transaction(
    row_index: int,
    request: UpdateTransactionRequest,
    dataset_id: str = Query(..., description="Dataset identifier (e.g., 'innova', 'fox')"),
    foldername: str = Query("default", description="Folder name (e.g., 'default', 'test_bench')"),
    dataset_service: DatasetService = Depends(get_dataset_service),
):
    """
    Update a transaction's classification.
    
    Args:
        row_index: Row index (0-based)
        request: Update request with new classification path
        dataset_id: Dataset identifier
        foldername: Folder name
        dataset_service: Dataset service dependency
        
    Returns:
        Updated transaction data
        
    Raises:
        HTTPException: If dataset or transaction not found
    """
    try:
        # Parse classification path
        parts = request.classification_path.split('|')
        updates = {
            'L1': parts[0] if len(parts) > 0 else '',
            'L2': parts[1] if len(parts) > 1 else '',
            'L3': parts[2] if len(parts) > 2 else '',
            'L4': parts[3] if len(parts) > 3 else '',
            'L5': parts[4] if len(parts) > 4 else '',
        }
        if request.override_rule_applied:
            updates['override_rule_applied'] = request.override_rule_applied
        
        # Update transaction
        update_list = [{"row_index": row_index, "fields": updates}]
        updated_count = dataset_service.update_transactions(dataset_id, update_list, foldername)
        
        if updated_count == 0:
            raise TransactionNotFoundError(f"Transaction at row {row_index} not found")
        
        # Get updated transaction
        csv_path_or_uri = dataset_service.get_output_csv_path(dataset_id, foldername)
        transaction = get_transaction_by_row_index(csv_path_or_uri, row_index)
        
        return TransactionDetailResponse(
            row_index=row_index,
            data=transaction,
        )
    except (DatasetNotFoundError, InvalidDatasetIdError, TransactionNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
