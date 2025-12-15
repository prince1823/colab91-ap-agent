"""Database manager for classification results.

Simplified for Expert Classifier - only exact match cache.
"""

import hashlib
import json
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from core.agents.spend_classification.model import ClassificationResult
from core.database.models import (
    SupplierClassification,
    SupplierDirectMapping,
    SupplierTaxonomyConstraint,
)
from core.database.schema import get_session_factory, init_database

logger = logging.getLogger(__name__)


class ClassificationDBManager:
    """Manages database operations for classification caching.
    
    Simplified for Expert Classifier - only exact match cache on
    (supplier_name + transaction_hash).
    """

    def __init__(self, db_path: Path, echo: bool = False):
        """
        Initialize database manager.

        Args:
            db_path: Path to SQLite database file
            echo: Whether to echo SQL queries (for debugging)
        """
        self.db_path = db_path
        self.engine = init_database(db_path, echo=echo)
        self.Session = get_session_factory(self.engine)
    
    @contextmanager
    def _get_session(self, commit: bool = True):
        """
        Context manager for database sessions.
        
        Args:
            commit: Whether to commit on successful exit (default: True)
        """
        session = self.Session()
        try:
            yield session
            if commit:
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_transaction_hash(self, transaction_data: Dict) -> str:
        """
        Create normalized hash from transaction data.

        Args:
            transaction_data: Dictionary with transaction fields

        Returns:
            SHA256 hash as hex string
        """
        # Normalize key fields
        fields = [
            str(transaction_data.get("gl_description", "")).lower().strip(),
            str(transaction_data.get("line_description", "")).lower().strip(),
            str(transaction_data.get("department", "")).lower().strip(),
        ]
        normalized = "|".join(fields)
        return hashlib.sha256(normalized.encode()).hexdigest()

    def normalize_supplier_name(self, supplier_name: str) -> str:
        """
        Normalize supplier name for consistent lookup.

        Args:
            supplier_name: Raw supplier name

        Returns:
            Normalized supplier name
        """
        return str(supplier_name).lower().strip()

    def get_by_supplier_and_hash(
        self, supplier_name: str, transaction_hash: str, run_id: Optional[str] = None
    ) -> Optional[ClassificationResult]:
        """
        Get classification by exact match (supplier + transaction hash).

        Args:
            supplier_name: Supplier name
            transaction_hash: Transaction hash
            run_id: Optional run_id to filter by (if None, searches across all runs)

        Returns:
            ClassificationResult if found, None otherwise
        """
        normalized_name = self.normalize_supplier_name(supplier_name)
        with self._get_session() as session:
            query = (
                session.query(SupplierClassification)
                .filter(
                    SupplierClassification.supplier_name == normalized_name,
                    SupplierClassification.transaction_hash == transaction_hash,
                )
            )
            # Filter by run_id if provided (scoped to current run)
            if run_id:
                query = query.filter(SupplierClassification.run_id == run_id)
            
            result = query.first()
            if result:
                # Increment usage count (will be committed by context manager)
                result.usage_count += 1
                return self._to_classification_result(result)
            return None

    def batch_get_by_supplier_and_hash(
        self, supplier_name: str, transaction_hashes: List[str], run_id: Optional[str] = None
    ) -> Dict[str, ClassificationResult]:
        """
        Batch get classifications by supplier and multiple transaction hashes.
        
        More efficient than calling get_by_supplier_and_hash multiple times.
        
        Args:
            supplier_name: Supplier name
            transaction_hashes: List of transaction hashes to look up
            run_id: Optional run_id to filter by (if None, searches across all runs)
            
        Returns:
            Dictionary mapping transaction_hash -> ClassificationResult for found entries
        """
        if not transaction_hashes:
            return {}
            
        normalized_name = self.normalize_supplier_name(supplier_name)
        with self._get_session() as session:
            query = (
                session.query(SupplierClassification)
                .filter(
                    SupplierClassification.supplier_name == normalized_name,
                    SupplierClassification.transaction_hash.in_(transaction_hashes),
                )
            )
            # Filter by run_id if provided (scoped to current run)
            if run_id:
                query = query.filter(SupplierClassification.run_id == run_id)
            
            results = query.all()
            result_dict = {}
            for result in results:
                # Increment usage count
                result.usage_count += 1
                result_dict[result.transaction_hash] = self._to_classification_result(result)
            
            return result_dict

    def get_supplier_profile(
        self, supplier_name: str, max_age_days: Optional[int] = None
    ) -> Optional[Dict]:
        """
        Get the most recent supplier profile for a supplier from previous classifications.
        
        This allows reusing supplier profiles across different runs to avoid re-researching.
        If max_age_days is specified, only return profiles updated within that time window.
        This allows invalidating stale profiles when research agent logic changes.

        Args:
            supplier_name: Supplier name
            max_age_days: Optional maximum age in days for cached profile. If None, uses any cached profile.

        Returns:
            Supplier profile dict if found and not expired, None otherwise
        """
        from datetime import datetime, timedelta
        
        normalized_name = self.normalize_supplier_name(supplier_name)
        with self._get_session() as session:
            query = (
                session.query(SupplierClassification)
                .filter(
                    SupplierClassification.supplier_name == normalized_name,
                    SupplierClassification.supplier_profile_snapshot.isnot(None)
                )
            )
            
            # If max_age_days is specified, filter by date
            if max_age_days is not None:
                cutoff_date = datetime.utcnow() - timedelta(days=max_age_days)
                query = query.filter(SupplierClassification.updated_at >= cutoff_date)
            
            # Get the most recent classification with a supplier profile snapshot
            result = query.order_by(SupplierClassification.updated_at.desc()).first()
            
            if result and result.supplier_profile_snapshot:
                return result.supplier_profile_snapshot
            return None

    def get_supplier_history(
        self, supplier_name: str, run_id: Optional[str] = None
    ) -> List[ClassificationResult]:
        """
        Get classification history for a supplier.

        Args:
            supplier_name: Supplier name
            run_id: Optional run_id to filter by (if None, searches across all runs)

        Returns:
            List of ClassificationResult objects, ordered by usage count
        """
        normalized_name = self.normalize_supplier_name(supplier_name)
        with self._get_session() as session:
            query = (
                session.query(SupplierClassification)
                .filter(SupplierClassification.supplier_name == normalized_name)
            )
            # Filter by run_id if provided
            if run_id:
                query = query.filter(SupplierClassification.run_id == run_id)
            
            results = query.order_by(SupplierClassification.usage_count.desc()).limit(10).all()
            return [self._to_classification_result(r) for r in results]

    def store_classification(
        self,
        supplier_name: str,
        transaction_hash: Optional[str],
        classification_result: ClassificationResult,
        run_id: str,
        dataset_name: Optional[str] = None,
        supplier_profile: Optional[Dict] = None,
        transaction_data: Optional[Dict] = None,
    ):
        """
        Store classification result in database.

        Simple exact match storage (supplier + transaction_hash).

        Args:
            supplier_name: Supplier name
            transaction_hash: Transaction hash (can be None)
            classification_result: ClassificationResult object
            run_id: Run ID (UUID) to identify this run
            dataset_name: Optional dataset name (e.g., "fox", "innova")
            supplier_profile: Optional supplier profile snapshot
            transaction_data: Optional transaction data snapshot
        """
        normalized_name = self.normalize_supplier_name(supplier_name)
        classification_path = self._build_classification_path(classification_result)
        
        # Extract confidence from reasoning if present
        confidence = None
        if classification_result.reasoning:
            if 'Confidence: high' in classification_result.reasoning:
                confidence = 'high'
            elif 'Confidence: medium' in classification_result.reasoning:
                confidence = 'medium'
            elif 'Confidence: low' in classification_result.reasoning:
                confidence = 'low'

        with self._get_session() as session:
            # Check if exact match entry already exists (within same run)
            existing = None
            if transaction_hash:
                existing = (
                    session.query(SupplierClassification)
                    .filter(
                        SupplierClassification.run_id == run_id,
                        SupplierClassification.supplier_name == normalized_name,
                        SupplierClassification.transaction_hash == transaction_hash,
                    )
                    .first()
                )

            if existing:
                # Update existing entry
                existing.classification_path = classification_path
                existing.l1 = classification_result.L1
                existing.l2 = classification_result.L2
                existing.l3 = classification_result.L3
                existing.l4 = classification_result.L4
                existing.l5 = classification_result.L5
                existing.override_rule_applied = classification_result.override_rule_applied
                existing.reasoning = classification_result.reasoning
                existing.confidence = confidence
                existing.supplier_profile_snapshot = supplier_profile
                existing.transaction_data_snapshot = transaction_data
                existing.usage_count += 1
            else:
                # Create new entry
                new_entry = SupplierClassification(
                    run_id=run_id,
                    dataset_name=dataset_name,
                    supplier_name=normalized_name,
                    transaction_hash=transaction_hash,
                    classification_path=classification_path,
                    l1=classification_result.L1,
                    l2=classification_result.L2,
                    l3=classification_result.L3,
                    l4=classification_result.L4,
                    l5=classification_result.L5,
                    override_rule_applied=classification_result.override_rule_applied,
                    reasoning=classification_result.reasoning,
                    confidence=confidence,
                    supplier_profile_snapshot=supplier_profile,
                    transaction_data_snapshot=transaction_data,
                    usage_count=1,
                )
                session.add(new_entry)

    def batch_store_classifications(
        self,
        supplier_name: str,
        classifications: List[Tuple[str, ClassificationResult, Optional[Dict], Optional[Dict]]],
        run_id: str,
        dataset_name: Optional[str] = None,
        supplier_profile: Optional[Dict] = None,
    ):
        """
        Batch store multiple classification results in a single transaction.
        
        More efficient than calling store_classification multiple times.
        
        Args:
            supplier_name: Supplier name
            classifications: List of tuples (transaction_hash, classification_result, transaction_data, supplier_profile)
            run_id: Run ID (UUID) to identify this run
            dataset_name: Optional dataset name (e.g., "fox", "innova")
            supplier_profile: Optional supplier profile snapshot (used if not provided per classification)
        """
        if not classifications:
            return
            
        normalized_name = self.normalize_supplier_name(supplier_name)
        
        with self._get_session() as session:
            # Build lookup map for existing entries
            transaction_hashes = [txn_hash for txn_hash, _, _, _ in classifications if txn_hash]
            existing_map = {}
            if transaction_hashes:
                existing_entries = (
                    session.query(SupplierClassification)
                    .filter(
                        SupplierClassification.run_id == run_id,
                        SupplierClassification.supplier_name == normalized_name,
                        SupplierClassification.transaction_hash.in_(transaction_hashes),
                    )
                    .all()
                )
                existing_map = {entry.transaction_hash: entry for entry in existing_entries}
            
            # Process each classification
            for transaction_hash, classification_result, transaction_data, txn_supplier_profile in classifications:
                classification_path = self._build_classification_path(classification_result)
                
                # Extract confidence from reasoning if present
                confidence = None
                if classification_result.reasoning:
                    if 'Confidence: high' in classification_result.reasoning:
                        confidence = 'high'
                    elif 'Confidence: medium' in classification_result.reasoning:
                        confidence = 'medium'
                    elif 'Confidence: low' in classification_result.reasoning:
                        confidence = 'low'
                
                # Use per-transaction supplier profile if provided, otherwise use invoice-level one
                profile_to_use = txn_supplier_profile if txn_supplier_profile is not None else supplier_profile
                
                if transaction_hash and transaction_hash in existing_map:
                    # Update existing entry
                    existing = existing_map[transaction_hash]
                    existing.classification_path = classification_path
                    existing.l1 = classification_result.L1
                    existing.l2 = classification_result.L2
                    existing.l3 = classification_result.L3
                    existing.l4 = classification_result.L4
                    existing.l5 = classification_result.L5
                    existing.override_rule_applied = classification_result.override_rule_applied
                    existing.reasoning = classification_result.reasoning
                    existing.confidence = confidence
                    existing.supplier_profile_snapshot = profile_to_use
                    existing.transaction_data_snapshot = transaction_data
                    existing.usage_count += 1
                else:
                    # Create new entry
                    new_entry = SupplierClassification(
                        run_id=run_id,
                        dataset_name=dataset_name,
                        supplier_name=normalized_name,
                        transaction_hash=transaction_hash,
                        classification_path=classification_path,
                        l1=classification_result.L1,
                        l2=classification_result.L2,
                        l3=classification_result.L3,
                        l4=classification_result.L4,
                        l5=classification_result.L5,
                        override_rule_applied=classification_result.override_rule_applied,
                        reasoning=classification_result.reasoning,
                        confidence=confidence,
                        supplier_profile_snapshot=profile_to_use,
                        transaction_data_snapshot=transaction_data,
                        usage_count=1,
                    )
                    session.add(new_entry)

    def _to_classification_result(self, db_entry: SupplierClassification) -> ClassificationResult:
        """Convert database entry to ClassificationResult."""
        return ClassificationResult(
            L1=db_entry.l1,
            L2=db_entry.l2,
            L3=db_entry.l3,
            L4=db_entry.l4,
            L5=db_entry.l5,
            override_rule_applied=db_entry.override_rule_applied,
            reasoning=db_entry.reasoning or "",
        )

    def _build_classification_path(self, result: ClassificationResult) -> str:
        """Build pipe-separated classification path."""
        parts = [result.L1]
        for level in [result.L2, result.L3, result.L4, result.L5]:
            if level:
                parts.append(level)
        return "|".join(parts)
    
    def clear_cache(self) -> int:
        """
        Clear all classification cache entries from the database.
        
        Returns:
            Number of records deleted
        """
        with self._get_session() as session:
            count = session.query(SupplierClassification).count()
            session.query(SupplierClassification).delete()
            logger.info(f"Cleared {count} classification cache entries from database")
            return count

    def get_supplier_direct_mapping(
        self, supplier_name: str, dataset_name: Optional[str] = None
    ) -> Optional[SupplierDirectMapping]:
        """
        Get direct mapping rule for a supplier (100% confidence, skip LLM).
        
        Checks dataset-specific rules first, then global rules (dataset_name=None).
        Returns highest priority active rule.
        
        Args:
            supplier_name: Supplier name to look up
            dataset_name: Optional dataset name (checks dataset-specific rules first)
            
        Returns:
            SupplierDirectMapping if found, None otherwise
        """
        with self._get_session(commit=False) as session:
            # Normalize supplier name
            supplier_name = str(supplier_name).strip()
            
            # First check dataset-specific rule
            if dataset_name:
                rule = (
                    session.query(SupplierDirectMapping)
                    .filter(
                        SupplierDirectMapping.supplier_name == supplier_name,
                        SupplierDirectMapping.dataset_name == dataset_name,
                        SupplierDirectMapping.active == True,
                    )
                    .order_by(
                        SupplierDirectMapping.priority.desc(),
                        SupplierDirectMapping.id.desc()  # Tie-breaker for same priority
                    )
                    .first()
                )
                if rule:
                    return rule
            
            # Then check global rule (dataset_name=None)
            rule = (
                session.query(SupplierDirectMapping)
                .filter(
                    SupplierDirectMapping.supplier_name == supplier_name,
                    SupplierDirectMapping.dataset_name.is_(None),
                    SupplierDirectMapping.active == True,
                )
                .order_by(
                    SupplierDirectMapping.priority.desc(),
                    SupplierDirectMapping.id.desc()  # Tie-breaker for same priority
                )
                .first()
            )
            return rule

    def get_supplier_taxonomy_constraint(
        self, supplier_name: str, dataset_name: Optional[str] = None
    ) -> Optional[SupplierTaxonomyConstraint]:
        """
        Get taxonomy constraint for a supplier (replace RAG with stored list).
        
        Checks dataset-specific constraints first, then global constraints (dataset_name=None).
        Returns highest priority active constraint.
        
        Args:
            supplier_name: Supplier name to look up
            dataset_name: Optional dataset name (checks dataset-specific constraints first)
            
        Returns:
            SupplierTaxonomyConstraint if found, None otherwise
        """
        with self._get_session(commit=False) as session:
            # Normalize supplier name
            supplier_name = str(supplier_name).strip()
            
            # First check dataset-specific constraint
            if dataset_name:
                constraint = (
                    session.query(SupplierTaxonomyConstraint)
                    .filter(
                        SupplierTaxonomyConstraint.supplier_name == supplier_name,
                        SupplierTaxonomyConstraint.dataset_name == dataset_name,
                        SupplierTaxonomyConstraint.active == True,
                    )
                    .order_by(
                        SupplierTaxonomyConstraint.priority.desc(),
                        SupplierTaxonomyConstraint.id.desc()  # Tie-breaker for same priority
                    )
                    .first()
                )
                if constraint:
                    return constraint
            
            # Then check global constraint (dataset_name=None)
            constraint = (
                session.query(SupplierTaxonomyConstraint)
                .filter(
                    SupplierTaxonomyConstraint.supplier_name == supplier_name,
                    SupplierTaxonomyConstraint.dataset_name.is_(None),
                    SupplierTaxonomyConstraint.active == True,
                )
                .order_by(
                    SupplierTaxonomyConstraint.priority.desc(),
                    SupplierTaxonomyConstraint.id.desc()  # Tie-breaker for same priority
                )
                .first()
            )
            return constraint

    def _batch_get_supplier_rules(
        self,
        model_class,
        supplier_names: List[str],
        dataset_name: Optional[str] = None
    ) -> Dict[str, Optional[Any]]:
        """
        Generic batch lookup for supplier rules (direct mappings or taxonomy constraints).
        
        Args:
            model_class: SQLAlchemy model class (SupplierDirectMapping or SupplierTaxonomyConstraint)
            supplier_names: List of supplier names to look up
            dataset_name: Optional dataset name
            
        Returns:
            Dict mapping supplier_name -> rule (or None if not found)
        """
        if not supplier_names:
            return {}
        
        with self._get_session(commit=False) as session:
            # Normalize supplier names
            normalized_names = [str(name).strip() for name in supplier_names]
            
            # Build base query
            query = session.query(model_class).filter(
                model_class.supplier_name.in_(normalized_names),
                model_class.active == True,
            )
            
            if dataset_name:
                # Get dataset-specific first
                dataset_rules = query.filter(
                    model_class.dataset_name == dataset_name
                ).order_by(
                    model_class.priority.desc(),
                    model_class.id.desc()
                ).all()
                
                # Get global rules for suppliers not found in dataset-specific
                found_suppliers = {rule.supplier_name for rule in dataset_rules}
                missing_suppliers = [name for name in normalized_names if name not in found_suppliers]
                
                global_rules = []
                if missing_suppliers:
                    global_rules = query.filter(
                        model_class.dataset_name.is_(None)
                    ).filter(
                        model_class.supplier_name.in_(missing_suppliers)
                    ).order_by(
                        model_class.priority.desc(),
                        model_class.id.desc()
                    ).all()
                
                # Combine results (dataset-specific takes precedence)
                result = {}
                for rule in dataset_rules + global_rules:
                    if rule.supplier_name not in result:  # First match wins
                        result[rule.supplier_name] = rule
            else:
                # Only global rules
                rules = query.filter(
                    model_class.dataset_name.is_(None)
                ).order_by(
                    model_class.priority.desc(),
                    model_class.id.desc()
                ).all()
                
                result = {}
                for rule in rules:
                    if rule.supplier_name not in result:  # First match wins
                        result[rule.supplier_name] = rule
            
            # Add None for suppliers not found
            for name in normalized_names:
                if name not in result:
                    result[name] = None
            
            return result

    def batch_get_supplier_direct_mappings(
        self, supplier_names: List[str], dataset_name: Optional[str] = None
    ) -> Dict[str, Optional[SupplierDirectMapping]]:
        """
        Batch lookup direct mappings for multiple suppliers.
        
        Args:
            supplier_names: List of supplier names to look up
            dataset_name: Optional dataset name
            
        Returns:
            Dict mapping supplier_name -> SupplierDirectMapping (or None if not found)
        """
        return self._batch_get_supplier_rules(SupplierDirectMapping, supplier_names, dataset_name)

    def batch_get_supplier_taxonomy_constraints(
        self, supplier_names: List[str], dataset_name: Optional[str] = None
    ) -> Dict[str, Optional[SupplierTaxonomyConstraint]]:
        """
        Batch lookup taxonomy constraints for multiple suppliers.
        
        Args:
            supplier_names: List of supplier names to look up
            dataset_name: Optional dataset name
            
        Returns:
            Dict mapping supplier_name -> SupplierTaxonomyConstraint (or None if not found)
        """
        return self._batch_get_supplier_rules(SupplierTaxonomyConstraint, supplier_names, dataset_name)

