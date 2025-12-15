"""Datasets API router."""

import io
from typing import List, Optional

import pandas as pd
import yaml
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from api.dependencies import get_dataset_service
from api.exceptions import DatasetNotFoundError, InvalidDatasetIdError
from api.models.requests import (
    CreateDatasetRequest,
    UpdateDatasetCSVRequest,
    UpdateDatasetTaxonomyRequest,
)
from api.models.responses import (
    CreateDatasetResponse,
    DatasetDetailResponse,
    DatasetInfo,
    DatasetTaxonomyResponse,
    UpdateDatasetResponse,
)
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


@router.post("/datasets/upload", response_model=CreateDatasetResponse, status_code=201)
async def create_dataset_upload(
    dataset_id: str = Form(..., description="Dataset identifier"),
    foldername: str = Form("default", description="Folder name (use empty string for direct dataset access)"),
    input_csv: UploadFile = File(..., description="Input CSV file"),
    taxonomy_yaml: UploadFile = File(..., description="Taxonomy YAML file"),
    dataset_service: DatasetService = Depends(get_dataset_service),
):
    """
    Create a new dataset by uploading CSV and YAML files.
    
    This endpoint accepts file uploads via multipart/form-data.

    Args:
        dataset_id: Dataset identifier
        foldername: Folder name (default: "default", use "" for direct dataset access)
        input_csv: Uploaded CSV file with transaction data
        taxonomy_yaml: Uploaded YAML file with taxonomy structure
        dataset_service: Dataset service dependency

    Returns:
        Created dataset information

    Raises:
        HTTPException: If dataset already exists or data is invalid
    """
    try:
        # Validate dataset_id format
        import re
        if not re.match(r"^[a-zA-Z0-9_.-]+$", dataset_id):
            raise HTTPException(
                status_code=400,
                detail="dataset_id can only contain alphanumeric characters, underscore, hyphen, and dot"
            )
        
        # Validate foldername format
        if foldername != "" and not re.match(r"^[a-zA-Z0-9_.-]+$", foldername):
            raise HTTPException(
                status_code=400,
                detail="foldername can only contain alphanumeric characters, underscore, hyphen, and dot"
            )
        
        # Validate file types
        if not input_csv.filename or not input_csv.filename.lower().endswith('.csv'):
            raise HTTPException(status_code=400, detail="input_csv must be a CSV file")
        
        if not taxonomy_yaml.filename or not taxonomy_yaml.filename.lower().endswith(('.yaml', '.yml')):
            raise HTTPException(status_code=400, detail="taxonomy_yaml must be a YAML file")
        
        # Read CSV file
        csv_content = await input_csv.read()
        try:
            transactions_df = pd.read_csv(io.BytesIO(csv_content))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid CSV file: {str(e)}")
        
        # Read YAML file
        yaml_content = await taxonomy_yaml.read()
        try:
            taxonomy_data = yaml.safe_load(io.BytesIO(yaml_content))
            if not isinstance(taxonomy_data, dict):
                raise ValueError("Taxonomy YAML must be a dictionary")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid YAML file: {str(e)}")
        
        # Create dataset
        result = dataset_service.create_dataset(
            dataset_id=dataset_id,
            transactions_df=transactions_df,
            taxonomy_data=taxonomy_data,
            foldername=foldername,
            csv_filename="input.csv",  # Use standard filename
        )

        return CreateDatasetResponse(
            dataset_id=result["dataset_id"],
            foldername=result["foldername"],
            row_count=result["row_count"],
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create dataset: {str(e)}")


@router.post("/datasets", response_model=CreateDatasetResponse, status_code=201)
def create_dataset(
    request: CreateDatasetRequest,
    dataset_service: DatasetService = Depends(get_dataset_service),
):
    """
    Create a new dataset with transactions and taxonomy provided as JSON.
    
    This endpoint accepts JSON data (for backward compatibility and programmatic access).

    Args:
        request: Dataset creation request with transactions and taxonomy as JSON
        dataset_service: Dataset service dependency

    Returns:
        Created dataset information

    Raises:
        HTTPException: If dataset already exists or data is invalid
    """
    try:
        # Convert transactions list to DataFrame
        transactions_df = pd.DataFrame(request.transactions)

        # Create dataset
        result = dataset_service.create_dataset(
            dataset_id=request.dataset_id,
            transactions_df=transactions_df,
            taxonomy_data=request.taxonomy,
            foldername=request.foldername,
            csv_filename=request.csv_filename,
        )

        return CreateDatasetResponse(
            dataset_id=result["dataset_id"],
            foldername=result["foldername"],
            row_count=result["row_count"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create dataset: {str(e)}")


@router.put("/datasets/{dataset_id}/csv", response_model=UpdateDatasetResponse)
def update_dataset_csv(
    dataset_id: str,
    request: UpdateDatasetCSVRequest,
    foldername: str = Query("default", description="Folder name"),
    dataset_service: DatasetService = Depends(get_dataset_service),
):
    """
    Update the transactions CSV for a dataset.

    Args:
        dataset_id: Dataset identifier
        request: Update request with transactions
        foldername: Folder name
        dataset_service: Dataset service dependency

    Returns:
        Updated dataset information

    Raises:
        HTTPException: If dataset not found
    """
    try:
        # Convert transactions list to DataFrame
        transactions_df = pd.DataFrame(request.transactions)

        result = dataset_service.update_dataset_csv(
            dataset_id=dataset_id,
            transactions_df=transactions_df,
            foldername=foldername,
        )

        return UpdateDatasetResponse(
            dataset_id=result["dataset_id"],
            foldername=result["foldername"],
            row_count=result["row_count"],
        )
    except DatasetNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update dataset CSV: {str(e)}")


@router.put("/datasets/{dataset_id}/taxonomy", response_model=UpdateDatasetResponse)
def update_dataset_taxonomy(
    dataset_id: str,
    request: UpdateDatasetTaxonomyRequest,
    foldername: str = Query("default", description="Folder name"),
    dataset_service: DatasetService = Depends(get_dataset_service),
):
    """
    Update the taxonomy YAML for a dataset.

    Args:
        dataset_id: Dataset identifier
        request: Update request with taxonomy
        foldername: Folder name
        dataset_service: Dataset service dependency

    Returns:
        Updated dataset information

    Raises:
        HTTPException: If dataset not found
    """
    try:
        result = dataset_service.update_dataset_taxonomy(
            dataset_id=dataset_id,
            taxonomy_data=request.taxonomy,
            foldername=foldername,
        )

        return UpdateDatasetResponse(
            dataset_id=result["dataset_id"],
            foldername=result["foldername"],
        )
    except DatasetNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update dataset taxonomy: {str(e)}")


@router.get("/datasets/{dataset_id}/taxonomy", response_model=DatasetTaxonomyResponse)
def get_dataset_taxonomy(
    dataset_id: str,
    foldername: str = Query("default", description="Folder name"),
    dataset_service: DatasetService = Depends(get_dataset_service),
):
    """
    Get taxonomy YAML for a dataset.

    Args:
        dataset_id: Dataset identifier
        foldername: Folder name
        dataset_service: Dataset service dependency

    Returns:
        Dataset taxonomy structure

    Raises:
        HTTPException: If dataset or taxonomy not found
    """
    try:
        taxonomy = dataset_service.get_dataset_taxonomy(dataset_id, foldername)

        return DatasetTaxonomyResponse(
            dataset_id=dataset_id,
            foldername=foldername,
            taxonomy=taxonomy,
        )
    except DatasetNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get dataset taxonomy: {str(e)}")


@router.delete("/datasets/{dataset_id}", status_code=204)
def delete_dataset(
    dataset_id: str,
    foldername: str = Query("default", description="Folder name"),
    dataset_service: DatasetService = Depends(get_dataset_service),
):
    """
    Delete a dataset (both CSV and YAML files).

    Args:
        dataset_id: Dataset identifier
        foldername: Folder name
        dataset_service: Dataset service dependency

    Raises:
        HTTPException: If dataset not found
    """
    try:
        dataset_service.delete_dataset(dataset_id, foldername)
    except DatasetNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete dataset: {str(e)}")
