"""Datasets API router."""

from typing import List

from fastapi import APIRouter

from api.models.responses import DatasetInfo
from core.hitl.csv_service import list_available_datasets

router = APIRouter(prefix="/api/v1", tags=["datasets"])


@router.get("/datasets", response_model=List[DatasetInfo])
def get_datasets():
    """
    List available datasets.

    Scans benchmarks directory for */*/output.csv files.

    Returns:
        List of dataset information
    """
    datasets = list_available_datasets()
    return datasets
