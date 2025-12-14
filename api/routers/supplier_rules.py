"""Supplier Rules API router for direct mappings and taxonomy constraints."""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
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
from api.routers.supplier_rules_helpers import (
    build_direct_mapping_query,
    build_taxonomy_constraint_query,
    calculate_pagination_metadata,
    to_direct_mapping_response,
    to_taxonomy_constraint_response,
)
from core.database.models import SupplierDirectMapping, SupplierTaxonomyConstraint

logger = logging.getLogger(__name__)

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
    try:
        # Normalize supplier name (already done in validator, but ensure consistency)
        supplier_name = request.supplier_name.strip()
        
        # Check for conflicting taxonomy constraint
        existing_constraint = (
            session.query(SupplierTaxonomyConstraint)
            .filter(
                SupplierTaxonomyConstraint.supplier_name == supplier_name,
                SupplierTaxonomyConstraint.dataset_name == request.dataset_name,
                SupplierTaxonomyConstraint.active == True,
            )
            .first()
        )
        if existing_constraint:
            raise HTTPException(
                status_code=400,
                detail=f"Supplier '{supplier_name}' already has an active taxonomy constraint. Cannot create direct mapping."
            )
        
        # Check if mapping already exists (for better error message)
        existing = (
            session.query(SupplierDirectMapping)
            .filter(
                SupplierDirectMapping.supplier_name == supplier_name,
                SupplierDirectMapping.dataset_name == request.dataset_name,
                SupplierDirectMapping.active == True,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Direct mapping already exists for supplier '{supplier_name}'"
            )
        
        mapping = SupplierDirectMapping(
            supplier_name=supplier_name,
            classification_path=request.classification_path,
            dataset_name=request.dataset_name,
            priority=request.priority,
            notes=request.notes,
            created_by=request.created_by,
        )
        session.add(mapping)
        session.commit()
        session.refresh(mapping)
        
        logger.info(f"Created direct mapping for supplier: {supplier_name} -> {request.classification_path} (id={mapping.id})")
        
        return to_direct_mapping_response(mapping)
    except HTTPException:
        raise
    except IntegrityError as e:
        session.rollback()
        logger.warning(f"Integrity error creating direct mapping: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Direct mapping already exists for supplier '{request.supplier_name}'"
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Error creating direct mapping: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create direct mapping: {str(e)}"
        )


@router.get("/direct-mappings", response_model=List[DirectMappingResponse])
def list_direct_mappings(
    supplier_name: Optional[str] = Query(None, description="Filter by supplier name"),
    dataset_name: Optional[str] = Query(None, description="Filter by dataset name"),
    active_only: bool = Query(True, description="Only return active mappings"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(50, ge=1, le=200, description="Items per page"),
    session: Session = Depends(get_db_session),
):
    """List direct mapping rules with pagination."""
    query = build_direct_mapping_query(session, supplier_name, dataset_name, active_only)
    
    # Get total count before pagination
    total = query.count()
    
    # Apply pagination
    offset = (page - 1) * limit
    mappings = query.offset(offset).limit(limit).all()
    
    return [to_direct_mapping_response(m) for m in mappings]


@router.get("/direct-mappings/{mapping_id}", response_model=DirectMappingResponse)
def get_direct_mapping(
    mapping_id: int,
    session: Session = Depends(get_db_session),
):
    """Get a specific direct mapping rule."""
    mapping = session.query(SupplierDirectMapping).filter(SupplierDirectMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail=f"Direct mapping {mapping_id} not found")
    
    return to_direct_mapping_response(mapping)


@router.put("/direct-mappings/{mapping_id}", response_model=DirectMappingResponse)
def update_direct_mapping(
    mapping_id: int,
    request: UpdateDirectMappingRequest,
    session: Session = Depends(get_db_session),
):
    """Update a direct mapping rule. Cannot change supplier_name or dataset_name."""
    try:
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
        
        logger.info(f"Updated direct mapping {mapping_id} for supplier: {mapping.supplier_name}")
        
        return to_direct_mapping_response(mapping)
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating direct mapping {mapping_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update direct mapping: {str(e)}"
        )


@router.delete("/direct-mappings/{mapping_id}")
def delete_direct_mapping(
    mapping_id: int,
    hard_delete: bool = Query(False, description="Hard delete (vs soft delete by setting active=False)"),
    session: Session = Depends(get_db_session),
):
    """Delete a direct mapping rule."""
    try:
        mapping = session.query(SupplierDirectMapping).filter(SupplierDirectMapping.id == mapping_id).first()
        if not mapping:
            raise HTTPException(status_code=404, detail=f"Direct mapping {mapping_id} not found")
        
        supplier_name = mapping.supplier_name
        
        if hard_delete:
            logger.warning(f"Hard deleting direct mapping {mapping_id} for supplier: {supplier_name}")
            session.delete(mapping)
        else:
            logger.info(f"Soft deleting direct mapping {mapping_id} for supplier: {supplier_name}")
            # Check if there's already an inactive row to avoid unique constraint violation
            # If so, just hard delete this one
            existing_inactive = (
                session.query(SupplierDirectMapping)
                .filter(
                    SupplierDirectMapping.supplier_name == mapping.supplier_name,
                    SupplierDirectMapping.dataset_name == mapping.dataset_name,
                    SupplierDirectMapping.active == False,
                    SupplierDirectMapping.id != mapping_id
                )
                .first()
            )
            if existing_inactive:
                # Already have an inactive row, so hard delete this one
                logger.info(f"Found existing inactive mapping, hard deleting {mapping_id}")
                session.delete(mapping)
            else:
                mapping.active = False
        
        session.commit()
        return {"message": "Direct mapping deleted successfully"}
    except HTTPException:
        raise
    except IntegrityError as e:
        session.rollback()
        # If soft delete fails due to unique constraint, try hard delete instead
        logger.warning(f"Soft delete failed due to constraint, trying hard delete: {e}")
        try:
            mapping = session.query(SupplierDirectMapping).filter(SupplierDirectMapping.id == mapping_id).first()
            if mapping:
                session.delete(mapping)
                session.commit()
                return {"message": "Direct mapping deleted successfully"}
        except:
            pass
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete direct mapping: {str(e)}"
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting direct mapping {mapping_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete direct mapping: {str(e)}"
        )


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
    try:
        # Normalize supplier name (already done in validator, but ensure consistency)
        supplier_name = request.supplier_name.strip()
        
        # Check for conflicting direct mapping
        existing_mapping = (
            session.query(SupplierDirectMapping)
            .filter(
                SupplierDirectMapping.supplier_name == supplier_name,
                SupplierDirectMapping.dataset_name == request.dataset_name,
                SupplierDirectMapping.active == True,
            )
            .first()
        )
        if existing_mapping:
            raise HTTPException(
                status_code=400,
                detail=f"Supplier '{supplier_name}' already has an active direct mapping. Cannot create taxonomy constraint."
            )
        
        # Check if constraint already exists (for better error message)
        existing = (
            session.query(SupplierTaxonomyConstraint)
            .filter(
                SupplierTaxonomyConstraint.supplier_name == supplier_name,
                SupplierTaxonomyConstraint.dataset_name == request.dataset_name,
                SupplierTaxonomyConstraint.active == True,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Taxonomy constraint already exists for supplier '{supplier_name}'"
            )
        
        constraint = SupplierTaxonomyConstraint(
            supplier_name=supplier_name,
            allowed_taxonomy_paths=request.allowed_taxonomy_paths,
            dataset_name=request.dataset_name,
            priority=request.priority,
            notes=request.notes,
            created_by=request.created_by,
        )
        session.add(constraint)
        session.commit()
        session.refresh(constraint)
        
        logger.info(f"Created taxonomy constraint for supplier: {supplier_name} with {len(request.allowed_taxonomy_paths)} paths (id={constraint.id})")
        
        return to_taxonomy_constraint_response(constraint)
    except HTTPException:
        raise
    except IntegrityError as e:
        session.rollback()
        logger.warning(f"Integrity error creating taxonomy constraint: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Taxonomy constraint already exists for supplier '{request.supplier_name}'"
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Error creating taxonomy constraint: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create taxonomy constraint: {str(e)}"
        )


@router.get("/taxonomy-constraints", response_model=List[TaxonomyConstraintResponse])
def list_taxonomy_constraints(
    supplier_name: Optional[str] = Query(None, description="Filter by supplier name"),
    dataset_name: Optional[str] = Query(None, description="Filter by dataset name"),
    active_only: bool = Query(True, description="Only return active constraints"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(50, ge=1, le=200, description="Items per page"),
    session: Session = Depends(get_db_session),
):
    """List taxonomy constraint rules with pagination."""
    query = build_taxonomy_constraint_query(session, supplier_name, dataset_name, active_only)
    
    # Get total count before pagination
    total = query.count()
    
    # Apply pagination
    offset = (page - 1) * limit
    constraints = query.offset(offset).limit(limit).all()
    
    return [to_taxonomy_constraint_response(c) for c in constraints]


@router.get("/taxonomy-constraints/{constraint_id}", response_model=TaxonomyConstraintResponse)
def get_taxonomy_constraint(
    constraint_id: int,
    session: Session = Depends(get_db_session),
):
    """Get a specific taxonomy constraint rule."""
    constraint = session.query(SupplierTaxonomyConstraint).filter(SupplierTaxonomyConstraint.id == constraint_id).first()
    if not constraint:
        raise HTTPException(status_code=404, detail=f"Taxonomy constraint {constraint_id} not found")
    
    return to_taxonomy_constraint_response(constraint)


@router.put("/taxonomy-constraints/{constraint_id}", response_model=TaxonomyConstraintResponse)
def update_taxonomy_constraint(
    constraint_id: int,
    request: UpdateTaxonomyConstraintRequest,
    session: Session = Depends(get_db_session),
):
    """Update a taxonomy constraint rule. Cannot change supplier_name or dataset_name."""
    try:
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
        
        logger.info(f"Updated taxonomy constraint {constraint_id} for supplier: {constraint.supplier_name}")
        
        return to_taxonomy_constraint_response(constraint)
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating taxonomy constraint {constraint_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update taxonomy constraint: {str(e)}"
        )


@router.delete("/taxonomy-constraints/{constraint_id}")
def delete_taxonomy_constraint(
    constraint_id: int,
    hard_delete: bool = Query(False, description="Hard delete (vs soft delete by setting active=False)"),
    session: Session = Depends(get_db_session),
):
    """Delete a taxonomy constraint rule."""
    try:
        constraint = session.query(SupplierTaxonomyConstraint).filter(SupplierTaxonomyConstraint.id == constraint_id).first()
        if not constraint:
            raise HTTPException(status_code=404, detail=f"Taxonomy constraint {constraint_id} not found")
        
        supplier_name = constraint.supplier_name
        
        if hard_delete:
            logger.warning(f"Hard deleting taxonomy constraint {constraint_id} for supplier: {supplier_name}")
            session.delete(constraint)
        else:
            logger.info(f"Soft deleting taxonomy constraint {constraint_id} for supplier: {supplier_name}")
            # Check if there's already an inactive row to avoid unique constraint violation
            # If so, just hard delete this one
            existing_inactive = (
                session.query(SupplierTaxonomyConstraint)
                .filter(
                    SupplierTaxonomyConstraint.supplier_name == constraint.supplier_name,
                    SupplierTaxonomyConstraint.dataset_name == constraint.dataset_name,
                    SupplierTaxonomyConstraint.active == False,
                    SupplierTaxonomyConstraint.id != constraint_id
                )
                .first()
            )
            if existing_inactive:
                # Already have an inactive row, so hard delete this one
                logger.info(f"Found existing inactive constraint, hard deleting {constraint_id}")
                session.delete(constraint)
            else:
                constraint.active = False
        
        session.commit()
        return {"message": "Taxonomy constraint deleted successfully"}
    except HTTPException:
        raise
    except IntegrityError as e:
        session.rollback()
        # If soft delete fails due to unique constraint, try hard delete instead
        logger.warning(f"Soft delete failed due to constraint, trying hard delete: {e}")
        try:
            constraint = session.query(SupplierTaxonomyConstraint).filter(SupplierTaxonomyConstraint.id == constraint_id).first()
            if constraint:
                session.delete(constraint)
                session.commit()
                return {"message": "Taxonomy constraint deleted successfully"}
        except:
            pass
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete taxonomy constraint: {str(e)}"
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting taxonomy constraint {constraint_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete taxonomy constraint: {str(e)}"
        )

