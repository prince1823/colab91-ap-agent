"""Database manager for classification results.

Simplified for Expert Classifier - only exact match cache.
"""

import hashlib
import json
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from core.agents.spend_classification.model import ClassificationResult
from core.database.models import SupplierClassification
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
    
    def get_successful_examples(
        self, 
        taxonomy_path: Optional[str] = None,
        dataset_name: Optional[str] = None,
        min_confidence: str = 'high',
        min_usage_count: int = 2,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get successful classification examples from database.
        
        Successful examples are those with high confidence and validated by multiple uses.
        
        Args:
            taxonomy_path: Optional taxonomy path to filter by (if available in future)
            dataset_name: Optional dataset name to filter by
            min_confidence: Minimum confidence level ('high', 'medium', 'low')
            min_usage_count: Minimum usage count (validated by multiple uses)
            limit: Maximum number of examples to return
            
        Returns:
            List of dictionaries with example data:
            {
                'transaction_data': {...},
                'supplier_profile': {...},
                'classification_path': 'L1|L2|L3',
                'confidence': 'high',
                'reasoning': '...'
            }
        """
        with self._get_session() as session:
            query = session.query(SupplierClassification).filter(
                SupplierClassification.confidence == min_confidence,
                SupplierClassification.usage_count >= min_usage_count
            )
            
            # Optional filters
            if dataset_name:
                query = query.filter(SupplierClassification.dataset_name == dataset_name)
            
            # Order by usage_count descending (most validated first)
            query = query.order_by(SupplierClassification.usage_count.desc())
            
            results = query.limit(limit).all()
            
            examples = []
            for entry in results:
                if entry.transaction_data_snapshot and entry.classification_path:
                    examples.append({
                        'transaction_data': entry.transaction_data_snapshot,
                        'supplier_profile': entry.supplier_profile_snapshot or {},
                        'classification_path': entry.classification_path,
                        'confidence': entry.confidence or 'high',
                        'reasoning': entry.reasoning or '',
                        'l1': entry.l1,
                        'l2': entry.l2,
                        'l3': entry.l3,
                        'l4': entry.l4,
                        'l5': entry.l5,
                    })
            
            return examples
    
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

