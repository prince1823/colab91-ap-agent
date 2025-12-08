"""SQLAlchemy models for classification database."""

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class SupplierClassification(Base):
    """Model for storing supplier classification results.
    
    Simplified schema for Expert Classifier (no L1-only cache).
    Uses exact match cache on (supplier_name + transaction_hash).
    """

    __tablename__ = "supplier_classifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(36), nullable=True, index=True)  # UUID format
    dataset_name = Column(String(255), nullable=True, index=True)  # e.g., "fox", "innova"
    supplier_name = Column(String(255), nullable=False, index=True)
    transaction_hash = Column(String(64), nullable=True, index=True)
    classification_path = Column(String(500), nullable=False)  # Full L1|L2|L3|L4|L5 path
    l1 = Column(String(100), nullable=False)
    l2 = Column(Text, nullable=True)
    l3 = Column(Text, nullable=True)
    l4 = Column(Text, nullable=True)
    l5 = Column(Text, nullable=True)
    override_rule_applied = Column(Text, nullable=True)
    reasoning = Column(Text, nullable=True)  # Full reasoning trace
    alternative_paths = Column(JSON, nullable=True)  # Alternative paths considered
    confidence = Column(String(20), nullable=True)  # high/medium/low
    supplier_profile_snapshot = Column(JSON, nullable=True)
    transaction_data_snapshot = Column(JSON, nullable=True)
    usage_count = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Composite indexes for exact match cache
    __table_args__ = (
        Index("idx_run_supplier_hash", "run_id", "supplier_name", "transaction_hash"),
        Index("idx_supplier_hash", "supplier_name", "transaction_hash"),
    )

    def __repr__(self):
        return f"<SupplierClassification(supplier={self.supplier_name}, path={self.classification_path})>"

