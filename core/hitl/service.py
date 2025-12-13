"""Main HITL feedback service orchestrating the workflow."""

from datetime import datetime
from typing import Dict, List, Optional

import dspy
from sqlalchemy.orm import Session

from core.agents.feedback_action import FeedbackAction
from core.database.models import UserFeedback
from core.hitl.action_templates import format_action_proposal
from core.hitl.executors import (
    SupplierRuleExecutor,
    TaxonomyUpdateExecutor,
    TransactionRuleExecutor,
)
from core.hitl.services.csv_service import CSVService
from core.hitl.services.taxonomy_service import TaxonomyService
from core.llms.llm import get_llm_for_agent
from core.utils.data.path_helpers import extract_foldername_from_path
from core.utils.data.path_parsing import parse_path_to_updates
from core.utils.infrastructure.mlflow import setup_mlflow_tracing


class FeedbackService:
    """Main HITL feedback service orchestrating the workflow."""

    def __init__(
        self,
        lm: Optional[dspy.LM] = None,
        csv_service: Optional[CSVService] = None,
        taxonomy_service: Optional[TaxonomyService] = None,
        enable_tracing: bool = True,
    ):
        """
        Initialize feedback service with dependencies.

        Args:
            lm: DSPy language model (if None, uses config for feedback_action agent)
            csv_service: CSVService instance (creates new if None)
            taxonomy_service: TaxonomyService instance (creates new if None)
            enable_tracing: Whether to enable MLflow tracing (default: True)
        """
        # Setup MLflow tracing if enabled
        if enable_tracing:
            setup_mlflow_tracing(experiment_name="hitl_feedback")

        self.lm = lm or get_llm_for_agent("feedback_action")
        self.csv_service = csv_service or CSVService()
        self.taxonomy_service = taxonomy_service or TaxonomyService()

        # Initialize action executors
        self.action_executors = {
            "supplier_rule": SupplierRuleExecutor(csv_service=self.csv_service),
            "transaction_rule": TransactionRuleExecutor(csv_service=self.csv_service),
            "company_context": TaxonomyUpdateExecutor(taxonomy_service=self.taxonomy_service),
            "taxonomy_description": TaxonomyUpdateExecutor(taxonomy_service=self.taxonomy_service),
        }

    def submit_feedback(
        self,
        session: Session,
        csv_path: str,
        row_index: int,
        corrected_path: str,
        feedback_text: str,
        dataset_name: str,
    ) -> Dict:
        """
        Submit user feedback and get LLM-generated action proposal.

        Args:
            session: SQLAlchemy session
            csv_path: Path to output CSV
            row_index: Row index in CSV (0-based)
            corrected_path: User's corrected classification (L1|L2|L3|L4)
            feedback_text: Natural language feedback
            dataset_name: Dataset name

        Returns:
            Dictionary with feedback_id, action_type, proposal_text
        """
        # 1. Read transaction from CSV
        transaction = self.csv_service.get_transaction_by_index(csv_path, row_index)
        if not transaction:
            raise ValueError(f"Transaction not found at row index {row_index}")

        # Get original classification
        original_path = f"{transaction.get('L1', '')}|{transaction.get('L2', '')}|{transaction.get('L3', '')}|{transaction.get('L4', '')}"

        # 2. Load taxonomy YAML
        taxonomy = self.taxonomy_service.read_taxonomy(dataset_name)
        taxonomy_structure = taxonomy.get('taxonomy', [])
        taxonomy_descriptions = taxonomy.get('taxonomy_descriptions', {})
        company_context = taxonomy.get('company_context', {})

        # 3. Call FeedbackAction agent
        with dspy.context(lm=self.lm):
            agent = FeedbackAction()
            result = agent.forward(
                original_classification=original_path,
                corrected_classification=corrected_path,
                natural_language_feedback=feedback_text,
                transaction_data=transaction,
                taxonomy_structure=taxonomy_structure,
                taxonomy_descriptions=taxonomy_descriptions,
                company_context=company_context
            )

        action_type = result['action_type']
        action_reasoning = result['action_reasoning']
        action_details = result['action_details']

        # 4. Format proposal text
        proposal_text = format_action_proposal(action_type, action_details, dataset_name)

        # 5. Extract foldername from csv_path
        foldername = extract_foldername_from_path(csv_path)

        # 6. Insert into user_feedback table
        feedback = UserFeedback(
            csv_file_path=csv_path,
            row_index=row_index,
            dataset_name=dataset_name,
            foldername=foldername,
            original_classification=original_path,
            corrected_classification=corrected_path,
            feedback_text=feedback_text,
            action_type=action_type,
            action_details=action_details,
            action_reasoning=action_reasoning,
            status="pending",
            proposal_text=proposal_text,
            created_at=datetime.utcnow()
        )

        session.add(feedback)
        session.commit()

        return {
            'feedback_id': feedback.id,
            'action_type': action_type,
            'proposal_text': proposal_text,
            'action_details': action_details
        }

    def approve_feedback(
        self,
        session: Session,
        feedback_id: int,
        user_edited_text: Optional[str] = None
    ) -> Dict:
        """
        Approve feedback with optional user edits.

        Args:
            session: SQLAlchemy session
            feedback_id: Feedback ID
            user_edited_text: User's edited proposal text (optional)

        Returns:
            Dictionary with status and issues (if any)
        """
        feedback = session.query(UserFeedback).filter(UserFeedback.id == feedback_id).first()
        if not feedback:
            raise ValueError(f"Feedback not found: {feedback_id}")

        # If user edited the text, we could parse it and update action_details
        # For MVP, we'll just store the edited text and use original action_details
        if user_edited_text:
            feedback.user_edited_text = user_edited_text
            # TODO: Parse edited text and validate format

        feedback.status = "approved"
        feedback.approved_at = datetime.utcnow()
        session.commit()

        return {
            'status': 'approved',
            'issues': []
        }

    def execute_action(self, session: Session, feedback_id: int) -> Dict:
        """
        Execute the approved action.

        Args:
            session: SQLAlchemy session
            feedback_id: Feedback ID

        Returns:
            Dictionary with action_applied status
        """
        feedback = session.query(UserFeedback).filter(UserFeedback.id == feedback_id).first()
        if not feedback:
            raise ValueError(f"Feedback not found: {feedback_id}")

        if feedback.status != "approved":
            raise ValueError(f"Feedback must be approved before execution. Current status: {feedback.status}")

        action_type = feedback.action_type
        action_details = feedback.action_details
        dataset_name = feedback.dataset_name

        # Get the appropriate executor
        executor = self.action_executors.get(action_type)
        if not executor:
            raise ValueError(f"Unknown action type: {action_type}")

        # Execute the action
        executor.execute(session, dataset_name, action_details)

        # Update feedback status
        feedback.status = "applied"
        feedback.applied_at = datetime.utcnow()
        session.commit()

        return {'action_applied': True}

    def preview_affected_rows(self, session: Session, feedback_id: int) -> Dict:
        """
        Preview rows that will be affected by this action.

        Args:
            session: SQLAlchemy session
            feedback_id: Feedback ID

        Returns:
            Dictionary with rows, count, and row_indices
        """
        feedback = session.query(UserFeedback).filter(UserFeedback.id == feedback_id).first()
        if not feedback:
            raise ValueError(f"Feedback not found: {feedback_id}")

        action_type = feedback.action_type
        action_details = feedback.action_details
        csv_path = feedback.csv_file_path

        # Get the appropriate executor
        executor = self.action_executors.get(action_type)
        if not executor:
            raise ValueError(f"Unknown action type: {action_type}")

        # Get affected rows
        affected_rows = executor.preview_affected_rows(csv_path, action_details)

        # Extract row indices
        row_indices = [row.get('row_idx') for row in affected_rows if 'row_idx' in row]

        return {
            'rows': affected_rows,
            'count': len(affected_rows),
            'row_indices': row_indices
        }

    def apply_bulk_corrections(
        self,
        session: Session,
        feedback_id: int,
        row_indices: List[int],
        dataset_service=None
    ) -> Dict:
        """
        Apply bulk corrections to CSV rows.

        Args:
            session: SQLAlchemy session
            feedback_id: Feedback ID
            row_indices: List of row indices to update
            dataset_service: Optional DatasetService for storage abstraction (if None, uses csv_path directly)

        Returns:
            Dictionary with updated_count
        """
        feedback = session.query(UserFeedback).filter(UserFeedback.id == feedback_id).first()
        if not feedback:
            raise ValueError(f"Feedback not found: {feedback_id}")

        csv_path = feedback.csv_file_path
        corrected_path = feedback.corrected_classification
        dataset_id = feedback.dataset_name
        foldername = feedback.foldername or "default"

        # Parse corrected classification into components
        updates = parse_path_to_updates(corrected_path, override_rule=f'feedback_{feedback_id}')

        # Use storage abstraction if available and csv_path is S3 URI
        if dataset_service and csv_path.startswith("s3://"):
            # Use DatasetService for S3
            update_list = [{"row_index": idx, "fields": updates} for idx in row_indices]
            updated_count = dataset_service.update_transactions(dataset_id, update_list, foldername)
        else:
            # Use direct file update for local paths
            updated_count = self.csv_service.update_rows(csv_path, row_indices, updates)

        return {'updated_count': updated_count}

    def list_feedback_items(
        self,
        session: Session,
        status: Optional[str] = None,
        dataset_id: Optional[str] = None,
        action_type: Optional[str] = None,
        page: int = 1,
        limit: int = 50
    ) -> Dict:
        """
        List feedback items with pagination and filters.

        Args:
            session: SQLAlchemy session
            status: Optional status filter (pending, approved, applied)
            dataset_id: Optional dataset name filter
            action_type: Optional action type filter
            page: Page number (1-indexed)
            limit: Number of items per page

        Returns:
            Dictionary with items, total count, and page info
        """
        query = session.query(UserFeedback)

        # Apply filters
        if status:
            query = query.filter(UserFeedback.status == status)
        if dataset_id:
            query = query.filter(UserFeedback.dataset_name == dataset_id)
        if action_type:
            query = query.filter(UserFeedback.action_type == action_type)

        # Get total count
        total = query.count()

        # Apply pagination
        offset = (page - 1) * limit
        items = query.order_by(UserFeedback.created_at.desc()).offset(offset).limit(limit).all()

        return {
            'items': items,
            'total': total,
            'page': page,
            'pages': (total + limit - 1) // limit,
            'limit': limit
        }

    def get_feedback_item(self, session: Session, feedback_id: int) -> Optional[UserFeedback]:
        """
        Get a single feedback item by ID.

        Args:
            session: SQLAlchemy session
            feedback_id: Feedback ID

        Returns:
            UserFeedback object or None if not found
        """
        return session.query(UserFeedback).filter(UserFeedback.id == feedback_id).first()

    def delete_feedback_item(self, session: Session, feedback_id: int) -> None:
        """
        Delete a feedback item (only if status is pending).

        Args:
            session: SQLAlchemy session
            feedback_id: Feedback ID

        Raises:
            ValueError: If feedback not found or status is not pending
        """
        feedback = session.query(UserFeedback).filter(UserFeedback.id == feedback_id).first()
        if not feedback:
            raise ValueError(f"Feedback not found: {feedback_id}")

        if feedback.status != "pending":
            raise ValueError(f"Cannot delete feedback with status: {feedback.status}. Only pending feedback can be deleted.")

        session.delete(feedback)
        session.commit()

