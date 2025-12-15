"""Helper functions for supplier rules API router."""

from typing import List, Optional

from sqlalchemy.orm import Query, Session

from api.models.responses import DirectMappingResponse, TaxonomyConstraintResponse
from core.database.models import SupplierDirectMapping, SupplierTaxonomyConstraint


# Constants
SUPPLIER_RULES_CACHE_SIZE = 500
MAX_TAXONOMY_PATHS = 100
MAX_SUPPLIER_NAME_LENGTH = 255
MAX_CLASSIFICATION_PATH_LENGTH = 500


def to_direct_mapping_response(mapping: SupplierDirectMapping) -> DirectMappingResponse:
    """Convert database model to response model."""
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


def to_taxonomy_constraint_response(constraint: SupplierTaxonomyConstraint) -> TaxonomyConstraintResponse:
    """Convert database model to response model."""
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


def build_direct_mapping_query(
    session: Session,
    supplier_name: Optional[str] = None,
    dataset_name: Optional[str] = None,
    active_only: bool = True,
) -> Query:
    """Build query for direct mappings with filters."""
    query = session.query(SupplierDirectMapping)
    
    filters = []
    if supplier_name:
        filters.append(SupplierDirectMapping.supplier_name == supplier_name.strip())
    if dataset_name:
        filters.append(SupplierDirectMapping.dataset_name == dataset_name)
    if active_only:
        filters.append(SupplierDirectMapping.active == True)
    
    if filters:
        query = query.filter(*filters)
    
    return query.order_by(
        SupplierDirectMapping.priority.desc(),
        SupplierDirectMapping.created_at.desc()
    )


def build_taxonomy_constraint_query(
    session: Session,
    supplier_name: Optional[str] = None,
    dataset_name: Optional[str] = None,
    active_only: bool = True,
) -> Query:
    """Build query for taxonomy constraints with filters."""
    query = session.query(SupplierTaxonomyConstraint)
    
    filters = []
    if supplier_name:
        filters.append(SupplierTaxonomyConstraint.supplier_name == supplier_name.strip())
    if dataset_name:
        filters.append(SupplierTaxonomyConstraint.dataset_name == dataset_name)
    if active_only:
        filters.append(SupplierTaxonomyConstraint.active == True)
    
    if filters:
        query = query.filter(*filters)
    
    return query.order_by(
        SupplierTaxonomyConstraint.priority.desc(),
        SupplierTaxonomyConstraint.created_at.desc()
    )


def calculate_pagination_metadata(total: int, page: int, limit: int) -> dict:
    """Calculate pagination metadata."""
    pages = (total + limit - 1) // limit if total > 0 else 0
    return {
        "total": total,
        "page": page,
        "pages": pages,
        "limit": limit,
    }

