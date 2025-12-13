"""Datasets API router."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_dataset_service
from api.exceptions import DatasetNotFoundError, InvalidDatasetIdError
from api.models.responses import DatasetDetailResponse, DatasetInfo
from api.services.dataset_service import DatasetService

router = APIRouter(prefix="/api/v1", tags=["datasets"])


@router.get("/datasets", response_model=List[DatasetInfo])
def get_datasets(
    foldername: Optional[str] = Query(None, description="Optional folder name to filter by"),
    dataset_service: DatasetService = Depends(get_dataset_service),
):
    """
    List available datasets.

    Args:
        foldername: Optional folder name to filter by
        dataset_service: Dataset service dependency

    Returns:
        List of dataset information
    """
    datasets = dataset_service.list_datasets(foldername)
    return [
        DatasetInfo(
            dataset_id=d["dataset_id"],
            foldername=d["foldername"],
            row_count=d["row_count"],
        )
            for d in datasets
    ]


@router.get("/datasets/{dataset_id}", response_model=DatasetDetailResponse)
def get_dataset(
    dataset_id: str,
    foldername: str = Query("default", description="Folder name (e.g., 'default', 'test_bench')"),
    dataset_service: DatasetService = Depends(get_dataset_service),
):
    """
    Get detailed information about a specific dataset.
    
    Args:
        dataset_id: Dataset identifier
        foldername: Folder name
        dataset_service: Dataset service dependency
        
    Returns:
        Detailed dataset information
        
    Raises:
        HTTPException: If dataset not found
    """
    try:
        csv_path_or_uri = dataset_service.get_output_csv_path(dataset_id, foldername)
        
        # Get dataset info from list
        datasets = dataset_service.list_datasets(foldername)
        dataset_info = next((d for d in datasets if d["dataset_id"] == dataset_id), None)
        
        if not dataset_info:
            raise DatasetNotFoundError(f"Dataset '{dataset_id}' not found in folder '{foldername}'")
        
        return DatasetDetailResponse(
            dataset_id=dataset_id,
            foldername=foldername,
            row_count=dataset_info["row_count"],
            csv_path_or_uri=csv_path_or_uri,
        )
    except (DatasetNotFoundError, InvalidDatasetIdError) as e:
        raise HTTPException(status_code=404, detail=str(e))
