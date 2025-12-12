"""SQLAlchemy models for classification database."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, JSON, Column, DateTime, Index, Integer, String, Text
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

    # HITL: Supplier rule columns
    supplier_rule_type = Column(String(20), nullable=True)  # "category_a" or "category_b"
    supplier_rule_paths = Column(JSON, nullable=True)  # Category A: single path, Category B: array
    supplier_rule_created_at = Column(DateTime, nullable=True)
    supplier_rule_active = Column(Boolean, default=True, nullable=True)

    # Composite indexes for exact match cache
    __table_args__ = (
        Index("idx_run_supplier_hash", "run_id", "supplier_name", "transaction_hash"),
        Index("idx_supplier_hash", "supplier_name", "transaction_hash"),
    )

    def __repr__(self):
        return f"<SupplierClassification(supplier={self.supplier_name}, path={self.classification_path})>"


class UserFeedback(Base):
    """Model for storing HITL user feedback and workflow state."""

    __tablename__ = "user_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Transaction reference
    csv_file_path = Column(String(500), nullable=False)  # e.g., "benchmarks/default/innova/output.csv"
    row_index = Column(Integer, nullable=False)
    dataset_name = Column(String(255), nullable=False)

    # User input
    original_classification = Column(String(500), nullable=False)
    corrected_classification = Column(String(500), nullable=False)
    feedback_text = Column(Text, nullable=True)

    # LLM output
    action_type = Column(String(50), nullable=False)  # "company_context", "taxonomy_description", "supplier_rule", "transaction_rule"
    action_details = Column(JSON, nullable=False)
    action_reasoning = Column(Text, nullable=True)

    # Workflow state
    status = Column(String(20), nullable=False, default="pending")  # "pending", "approved", "applied"
    proposal_text = Column(Text, nullable=True)
    user_edited_text = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    approved_at = Column(DateTime, nullable=True)
    applied_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_feedback_status", "status"),
        Index("idx_feedback_csv", "csv_file_path"),
    )

    def __repr__(self):
        return f"<UserFeedback(id={self.id}, status={self.status}, action_type={self.action_type})>"


class TransactionRule(Base):
    """Model for storing transaction-based classification rules (e.g., GL code rules)."""

    __tablename__ = "transaction_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_name = Column(String(255), nullable=False)
    rule_name = Column(String(255), nullable=False)
    rule_condition = Column(JSON, nullable=False)  # e.g., {"gl_code": "1234"}
    classification_path = Column(String(500), nullable=False)
    priority = Column(Integer, default=10, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    active = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index("idx_rules_dataset", "dataset_name", "active"),
    )

    def __repr__(self):
        return f"<TransactionRule(id={self.id}, rule_name={self.rule_name}, dataset={self.dataset_name})>"

