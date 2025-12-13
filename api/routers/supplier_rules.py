"""Supplier Rules API router for direct mappings and taxonomy constraints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.dependencies import get_db_session
from api.models.requests import (
    CreateDirectMappingRequest,
    CreateTaxonomyConstraintRequest,
    UpdateDirectMappingRequest,
    UpdateTaxonomyConstraintRequest,
)
from api.models.responses import (
    DirectMappingResponse,
    TaxonomyConstraintResponse,
)
from core.database.models import SupplierDirectMapping, SupplierTaxonomyConstraint

router = APIRouter(prefix="/api/v1/supplier-rules", tags=["supplier-rules"])


# ==================== Direct Mappings (100% Confidence) ====================

@router.post("/direct-mappings", response_model=DirectMappingResponse)
def create_direct_mapping(
    request: CreateDirectMappingRequest,
    session: Session = Depends(get_db_session),
):
    """
    Create a direct mapping rule for a supplier (100% confidence, skip LLM).
    
    When this supplier is encountered, all transactions will be directly
    mapped to the specified classification path without LLM classification.
    """
    # Check if mapping already exists
    existing = (
        session.query(SupplierDirectMapping)
        .filter(
            SupplierDirectMapping.supplier_name == request.supplier_name,
            SupplierDirectMapping.dataset_name == request.dataset_name,
            SupplierDirectMapping.active == True,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Direct mapping already exists for supplier '{request.supplier_name}'"
        )
    
    mapping = SupplierDirectMapping(
        supplier_name=request.supplier_name,
        classification_path=request.classification_path,
        dataset_name=request.dataset_name,
        priority=request.priority,
        notes=request.notes,
        created_by=request.created_by,
    )
    session.add(mapping)
    session.commit()
    session.refresh(mapping)
    
    return DirectMappingResponse(
        id=mapping.id,
        supplier_name=mapping.supplier_name,
        classification_path=mapping.classification_path,
        dataset_name=mapping.dataset_name,
        priority=mapping.priority,
        active=mapping.active,
        created_at=mapping.created_at,
        updated_at=mapping.updated_at,
        created_by=mapping.created_by,
        notes=mapping.notes,
    )


@router.get("/direct-mappings", response_model=List[DirectMappingResponse])
def list_direct_mappings(
    supplier_name: Optional[str] = Query(None, description="Filter by supplier name"),
    dataset_name: Optional[str] = Query(None, description="Filter by dataset name"),
    active_only: bool = Query(True, description="Only return active mappings"),
    session: Session = Depends(get_db_session),
):
    """List direct mapping rules."""
    query = session.query(SupplierDirectMapping)
    
    if supplier_name:
        query = query.filter(SupplierDirectMapping.supplier_name == supplier_name)
    if dataset_name:
        query = query.filter(SupplierDirectMapping.dataset_name == dataset_name)
    if active_only:
        query = query.filter(SupplierDirectMapping.active == True)
    
    mappings = query.order_by(SupplierDirectMapping.priority.desc(), SupplierDirectMapping.created_at.desc()).all()
    
    return [
        DirectMappingResponse(
            id=m.id,
            supplier_name=m.supplier_name,
            classification_path=m.classification_path,
            dataset_name=m.dataset_name,
            priority=m.priority,
            active=m.active,
            created_at=m.created_at,
            updated_at=m.updated_at,
            created_by=m.created_by,
            notes=m.notes,
        )
        for m in mappings
    ]


@router.get("/direct-mappings/{mapping_id}", response_model=DirectMappingResponse)
def get_direct_mapping(
    mapping_id: int,
    session: Session = Depends(get_db_session),
):
    """Get a specific direct mapping rule."""
    mapping = session.query(SupplierDirectMapping).filter(SupplierDirectMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail=f"Direct mapping {mapping_id} not found")
    
    return DirectMappingResponse(
        id=mapping.id,
        supplier_name=mapping.supplier_name,
        classification_path=mapping.classification_path,
        dataset_name=mapping.dataset_name,
        priority=mapping.priority,
        active=mapping.active,
        created_at=mapping.created_at,
        updated_at=mapping.updated_at,
        created_by=mapping.created_by,
        notes=mapping.notes,
    )


@router.put("/direct-mappings/{mapping_id}", response_model=DirectMappingResponse)
def update_direct_mapping(
    mapping_id: int,
    request: UpdateDirectMappingRequest,
    session: Session = Depends(get_db_session),
):
    """Update a direct mapping rule."""
    mapping = session.query(SupplierDirectMapping).filter(SupplierDirectMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail=f"Direct mapping {mapping_id} not found")
    
    if request.classification_path is not None:
        mapping.classification_path = request.classification_path
    if request.priority is not None:
        mapping.priority = request.priority
    if request.active is not None:
        mapping.active = request.active
    if request.notes is not None:
        mapping.notes = request.notes
    
    session.commit()
    session.refresh(mapping)
    
    return DirectMappingResponse(
        id=mapping.id,
        supplier_name=mapping.supplier_name,
        classification_path=mapping.classification_path,
        dataset_name=mapping.dataset_name,
        priority=mapping.priority,
        active=mapping.active,
        created_at=mapping.created_at,
        updated_at=mapping.updated_at,
        created_by=mapping.created_by,
        notes=mapping.notes,
    )


@router.delete("/direct-mappings/{mapping_id}")
def delete_direct_mapping(
    mapping_id: int,
    hard_delete: bool = Query(False, description="Hard delete (vs soft delete by setting active=False)"),
    session: Session = Depends(get_db_session),
):
    """Delete a direct mapping rule."""
    mapping = session.query(SupplierDirectMapping).filter(SupplierDirectMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail=f"Direct mapping {mapping_id} not found")
    
    if hard_delete:
        session.delete(mapping)
    else:
        mapping.active = False
    
    session.commit()
    return {"message": "Direct mapping deleted successfully"}


# ==================== Taxonomy Constraints ====================

@router.post("/taxonomy-constraints", response_model=TaxonomyConstraintResponse)
def create_taxonomy_constraint(
    request: CreateTaxonomyConstraintRequest,
    session: Session = Depends(get_db_session),
):
    """
    Create a taxonomy constraint for a supplier.
    
    When this supplier is encountered, instead of using RAG to retrieve
    taxonomy paths, use the stored list of allowed paths for LLM classification.
    """
    # Check if constraint already exists
    existing = (
        session.query(SupplierTaxonomyConstraint)
        .filter(
            SupplierTaxonomyConstraint.supplier_name == request.supplier_name,
            SupplierTaxonomyConstraint.dataset_name == request.dataset_name,
            SupplierTaxonomyConstraint.active == True,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Taxonomy constraint already exists for supplier '{request.supplier_name}'"
        )
    
    constraint = SupplierTaxonomyConstraint(
        supplier_name=request.supplier_name,
        allowed_taxonomy_paths=request.allowed_taxonomy_paths,
        dataset_name=request.dataset_name,
        priority=request.priority,
        notes=request.notes,
        created_by=request.created_by,
    )
    session.add(constraint)
    session.commit()
    session.refresh(constraint)
    
    return TaxonomyConstraintResponse(
        id=constraint.id,
        supplier_name=constraint.supplier_name,
        allowed_taxonomy_paths=constraint.allowed_taxonomy_paths,
        dataset_name=constraint.dataset_name,
        priority=constraint.priority,
        active=constraint.active,
        created_at=constraint.created_at,
        updated_at=constraint.updated_at,
        created_by=constraint.created_by,
        notes=constraint.notes,
    )


@router.get("/taxonomy-constraints", response_model=List[TaxonomyConstraintResponse])
def list_taxonomy_constraints(
    supplier_name: Optional[str] = Query(None, description="Filter by supplier name"),
    dataset_name: Optional[str] = Query(None, description="Filter by dataset name"),
    active_only: bool = Query(True, description="Only return active constraints"),
    session: Session = Depends(get_db_session),
):
    """List taxonomy constraint rules."""
    query = session.query(SupplierTaxonomyConstraint)
    
    if supplier_name:
        query = query.filter(SupplierTaxonomyConstraint.supplier_name == supplier_name)
    if dataset_name:
        query = query.filter(SupplierTaxonomyConstraint.dataset_name == dataset_name)
    if active_only:
        query = query.filter(SupplierTaxonomyConstraint.active == True)
    
    constraints = query.order_by(SupplierTaxonomyConstraint.priority.desc(), SupplierTaxonomyConstraint.created_at.desc()).all()
    
    return [
        TaxonomyConstraintResponse(
            id=c.id,
            supplier_name=c.supplier_name,
            allowed_taxonomy_paths=c.allowed_taxonomy_paths,
            dataset_name=c.dataset_name,
            priority=c.priority,
            active=c.active,
            created_at=c.created_at,
            updated_at=c.updated_at,
            created_by=c.created_by,
            notes=c.notes,
        )
        for c in constraints
    ]


@router.get("/taxonomy-constraints/{constraint_id}", response_model=TaxonomyConstraintResponse)
def get_taxonomy_constraint(
    constraint_id: int,
    session: Session = Depends(get_db_session),
):
    """Get a specific taxonomy constraint rule."""
    constraint = session.query(SupplierTaxonomyConstraint).filter(SupplierTaxonomyConstraint.id == constraint_id).first()
    if not constraint:
        raise HTTPException(status_code=404, detail=f"Taxonomy constraint {constraint_id} not found")
    
    return TaxonomyConstraintResponse(
        id=constraint.id,
        supplier_name=constraint.supplier_name,
        allowed_taxonomy_paths=constraint.allowed_taxonomy_paths,
        dataset_name=constraint.dataset_name,
        priority=constraint.priority,
        active=constraint.active,
        created_at=constraint.created_at,
        updated_at=constraint.updated_at,
        created_by=constraint.created_by,
        notes=constraint.notes,
    )


@router.put("/taxonomy-constraints/{constraint_id}", response_model=TaxonomyConstraintResponse)
def update_taxonomy_constraint(
    constraint_id: int,
    request: UpdateTaxonomyConstraintRequest,
    session: Session = Depends(get_db_session),
):
    """Update a taxonomy constraint rule."""
    constraint = session.query(SupplierTaxonomyConstraint).filter(SupplierTaxonomyConstraint.id == constraint_id).first()
    if not constraint:
        raise HTTPException(status_code=404, detail=f"Taxonomy constraint {constraint_id} not found")
    
    if request.allowed_taxonomy_paths is not None:
        constraint.allowed_taxonomy_paths = request.allowed_taxonomy_paths
    if request.priority is not None:
        constraint.priority = request.priority
    if request.active is not None:
        constraint.active = request.active
    if request.notes is not None:
        constraint.notes = request.notes
    
    session.commit()
    session.refresh(constraint)
    
    return TaxonomyConstraintResponse(
        id=constraint.id,
        supplier_name=constraint.supplier_name,
        allowed_taxonomy_paths=constraint.allowed_taxonomy_paths,
        dataset_name=constraint.dataset_name,
        priority=constraint.priority,
        active=constraint.active,
        created_at=constraint.created_at,
        updated_at=constraint.updated_at,
        created_by=constraint.created_by,
        notes=constraint.notes,
    )


@router.delete("/taxonomy-constraints/{constraint_id}")
def delete_taxonomy_constraint(
    constraint_id: int,
    hard_delete: bool = Query(False, description="Hard delete (vs soft delete by setting active=False)"),
    session: Session = Depends(get_db_session),
):
    """Delete a taxonomy constraint rule."""
    constraint = session.query(SupplierTaxonomyConstraint).filter(SupplierTaxonomyConstraint.id == constraint_id).first()
    if not constraint:
        raise HTTPException(status_code=404, detail=f"Taxonomy constraint {constraint_id} not found")
    
    if hard_delete:
        session.delete(constraint)
    else:
        constraint.active = False
    
    session.commit()
    return {"message": "Taxonomy constraint deleted successfully"}

