"""Datasets API router."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from api.models.responses import DatasetInfo
from api.services.dataset_service import DatasetService
from api.dependencies import get_dataset_service

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
