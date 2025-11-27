"""Database manager for classification results."""

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
    """Manages database operations for classification caching."""

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

    def get_by_supplier_and_l1(
        self, supplier_name: str, l1_category: str, run_id: Optional[str] = None
    ) -> Optional[ClassificationResult]:
        """
        Get classification by supplier + L1 category.

        Args:
            supplier_name: Supplier name
            l1_category: L1 category from preliminary classifier
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
                    SupplierClassification.l1_category == l1_category,
                )
            )
            # Filter by run_id if provided (scoped to current run)
            if run_id:
                query = query.filter(SupplierClassification.run_id == run_id)
            
            result = query.order_by(SupplierClassification.usage_count.desc()).first()
            if result:
                # Increment usage count (will be committed by context manager)
                result.usage_count += 1
                return self._to_classification_result(result)
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
        l1_category: str,
        classification_result: ClassificationResult,
        run_id: str,
        dataset_name: Optional[str] = None,
        supplier_profile: Optional[Dict] = None,
        transaction_data: Optional[Dict] = None,
    ):
        """
        Store classification result in database.

        Stores at multiple cache levels:
        1. Exact match entry (supplier + transaction_hash)
        2. Supplier + L1 entry (for future Supplier + L1 lookups)
        3. Updates supplier history

        Args:
            supplier_name: Supplier name
            transaction_hash: Transaction hash (can be None)
            l1_category: L1 category
            classification_result: ClassificationResult object
            run_id: Run ID (UUID) to identify this run
            dataset_name: Optional dataset name (e.g., "fox", "innova")
            supplier_profile: Optional supplier profile snapshot
            transaction_data: Optional transaction data snapshot
        """
        normalized_name = self.normalize_supplier_name(supplier_name)
        classification_path = self._build_classification_path(classification_result)

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
                existing.l1_category = l1_category
                existing.classification_path = classification_path
                existing.l1 = classification_result.L1
                existing.l2 = classification_result.L2
                existing.l3 = classification_result.L3
                existing.l4 = classification_result.L4
                existing.l5 = classification_result.L5
                existing.override_rule_applied = classification_result.override_rule_applied
                existing.reasoning = classification_result.reasoning
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
                    l1_category=l1_category,
                    classification_path=classification_path,
                    l1=classification_result.L1,
                    l2=classification_result.L2,
                    l3=classification_result.L3,
                    l4=classification_result.L4,
                    l5=classification_result.L5,
                    override_rule_applied=classification_result.override_rule_applied,
                    reasoning=classification_result.reasoning,
                    supplier_profile_snapshot=supplier_profile,
                    transaction_data_snapshot=transaction_data,
                    usage_count=1,
                )
                session.add(new_entry)

            # Also ensure Supplier + L1 entry exists (for future lookups within same run)
            supplier_l1_entry = (
                session.query(SupplierClassification)
                .filter(
                    SupplierClassification.run_id == run_id,
                    SupplierClassification.supplier_name == normalized_name,
                    SupplierClassification.l1_category == l1_category,
                    SupplierClassification.transaction_hash.is_(None),  # Supplier+L1 entry has no hash
                )
                .first()
            )

            if not supplier_l1_entry:
                # Create Supplier + L1 entry (without transaction_hash)
                supplier_l1_entry = SupplierClassification(
                    run_id=run_id,
                    dataset_name=dataset_name,
                    supplier_name=normalized_name,
                    transaction_hash=None,
                    l1_category=l1_category,
                    classification_path=classification_path,
                    l1=classification_result.L1,
                    l2=classification_result.L2,
                    l3=classification_result.L3,
                    l4=classification_result.L4,
                    l5=classification_result.L5,
                    override_rule_applied=classification_result.override_rule_applied,
                    reasoning=classification_result.reasoning,
                    supplier_profile_snapshot=supplier_profile,
                    transaction_data_snapshot=transaction_data,
                    usage_count=1,
                )
                session.add(supplier_l1_entry)
            else:
                # Update existing Supplier + L1 entry
                supplier_l1_entry.classification_path = classification_path
                supplier_l1_entry.l1 = classification_result.L1
                supplier_l1_entry.l2 = classification_result.L2
                supplier_l1_entry.l3 = classification_result.L3
                supplier_l1_entry.l4 = classification_result.L4
                supplier_l1_entry.l5 = classification_result.L5
                supplier_l1_entry.override_rule_applied = classification_result.override_rule_applied
                supplier_l1_entry.reasoning = classification_result.reasoning
                supplier_l1_entry.usage_count += 1

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

