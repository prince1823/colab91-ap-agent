"""Main HITL feedback service orchestrating the workflow."""

from datetime import datetime
from typing import Dict, List, Optional

import dspy
from sqlalchemy.orm import Session

from core.agents.feedback_action import FeedbackAction
from core.database.models import UserFeedback
from core.hitl.csv_service import (
    find_rows_by_condition,
    find_rows_by_supplier,
    get_transaction_by_row_index,
    update_csv_rows
)
from core.hitl.supplier_rule import create_supplier_rule
from core.hitl.taxonomy_updates import (
    execute_company_context_change,
    execute_taxonomy_description_change
)
from core.hitl.transaction_rule import create_transaction_rule
from core.hitl.yaml_service import read_taxonomy_yaml


def submit_feedback(
    session: Session,
    csv_path: str,
    row_index: int,
    corrected_path: str,
    feedback_text: str,
    dataset_name: str,
    lm: dspy.LM
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
        lm: DSPy language model

    Returns:
        Dictionary with feedback_id, action_type, proposal_text
    """
    # 1. Read transaction from CSV
    transaction = get_transaction_by_row_index(csv_path, row_index)
    if not transaction:
        raise ValueError(f"Transaction not found at row index {row_index}")

    # Get original classification
    original_path = f"{transaction.get('L1', '')}|{transaction.get('L2', '')}|{transaction.get('L3', '')}|{transaction.get('L4', '')}"

    # 2. Load taxonomy YAML
    taxonomy = read_taxonomy_yaml(dataset_name)
    taxonomy_structure = taxonomy.get('taxonomy', [])
    taxonomy_descriptions = taxonomy.get('taxonomy_descriptions', {})
    company_context = taxonomy.get('company_context', {})

    # 3. Call FeedbackAction agent
    with dspy.context(lm=lm):
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

    # 5. Extract foldername from csv_path if possible, otherwise default to "default"
    # csv_path format: "benchmarks/{foldername}/{dataset_name}/output.csv" or S3 URI
    foldername = "default"
    if "/" in csv_path:
        parts = csv_path.split("/")
        # Try to extract foldername: look for pattern benchmarks/{foldername}/{dataset_name}/output.csv
        if "benchmarks" in parts:
            idx = parts.index("benchmarks")
            if idx + 1 < len(parts):
                foldername = parts[idx + 1]
        # For S3 URIs: s3://bucket/benchmarks/{foldername}/{dataset_name}/output.csv
        elif csv_path.startswith("s3://"):
            # Extract from S3 URI
            uri_parts = csv_path.replace("s3://", "").split("/")
            if "benchmarks" in uri_parts:
                idx = uri_parts.index("benchmarks")
                if idx + 1 < len(uri_parts):
                    foldername = uri_parts[idx + 1]

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


def format_action_proposal(action_type: str, action_details: Dict, dataset_name: str) -> str:
    """
    Format action proposal text for user review.

    Args:
        action_type: Type of action
        action_details: Action-specific details
        dataset_name: Dataset name

    Returns:
        Formatted proposal text
    """
    if action_type == "company_context":
        field_name = action_details.get('field_name', 'unknown')
        current_value = action_details.get('current_value', '')
        proposed_value = action_details.get('proposed_value', '')

        return f"""Company Context Update
Field: {field_name}

Current:
{current_value}

Proposed:
{proposed_value}

You can edit the proposed text above before approving."""

    elif action_type == "taxonomy_description":
        taxonomy_path = action_details.get('taxonomy_path', '')
        current_description = action_details.get('current_description', '')
        proposed_description = action_details.get('proposed_description', '')

        return f"""Taxonomy Description Update
Path: {taxonomy_path}

Current Description:
{current_description}

Proposed Description:
{proposed_description}

You can edit the proposed description above before approving."""

    elif action_type == "supplier_rule":
        supplier_name = action_details.get('supplier_name', '')
        rule_category = action_details.get('rule_category', 'A')
        classification_paths = action_details.get('classification_paths', [])

        category_desc = "one-to-one mapping" if rule_category == "A" else "multiple possible classifications"
        paths_str = "\n".join(f"  - {path}" for path in classification_paths)

        return f"""Supplier Rule
Supplier: {supplier_name}
Rule Type: Category {rule_category} ({category_desc})
Classification:
{paths_str}

This rule will apply to all future transactions from this supplier."""

    elif action_type == "transaction_rule":
        condition_field = action_details.get('condition_field', '')
        condition_value = action_details.get('condition_value', '')
        classification_path = action_details.get('classification_path', '')
        rule_name = action_details.get('rule_name', '')

        return f"""Transaction Rule
Rule: if {condition_field} = {condition_value}, always classify as {classification_path}

Rule Name: {rule_name}

You can edit the rule above before approving."""

    else:
        return f"Unknown action type: {action_type}"


def approve_feedback(
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


def execute_action(session: Session, feedback_id: int) -> Dict:
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

    # Execute based on action type
    if action_type == "company_context":
        execute_company_context_change(dataset_name, action_details)

    elif action_type == "taxonomy_description":
        execute_taxonomy_description_change(dataset_name, action_details)

    elif action_type == "supplier_rule":
        create_supplier_rule(session, dataset_name, action_details)

    elif action_type == "transaction_rule":
        create_transaction_rule(session, dataset_name, action_details)

    else:
        raise ValueError(f"Unknown action type: {action_type}")

    # Update feedback status
    feedback.status = "applied"
    feedback.applied_at = datetime.utcnow()
    session.commit()

    return {'action_applied': True}


def preview_affected_rows(session: Session, feedback_id: int) -> Dict:
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

    affected_rows = []

    if action_type == "supplier_rule":
        supplier_name = action_details.get('supplier_name', '')
        affected_rows = find_rows_by_supplier(csv_path, supplier_name)

    elif action_type == "transaction_rule":
        condition_field = action_details.get('condition_field', '')
        condition_value = action_details.get('condition_value', '')
        affected_rows = find_rows_by_condition(csv_path, condition_field, condition_value)

    # Extract row indices
    row_indices = [row.get('row_idx') for row in affected_rows if 'row_idx' in row]

    return {
        'rows': affected_rows,
        'count': len(affected_rows),
        'row_indices': row_indices
    }


def apply_bulk_corrections(
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
    parts = corrected_path.split('|')
    updates = {
        'L1': parts[0] if len(parts) > 0 else '',
        'L2': parts[1] if len(parts) > 1 else '',
        'L3': parts[2] if len(parts) > 2 else '',
        'L4': parts[3] if len(parts) > 3 else '',
        'override_rule_applied': f'feedback_{feedback_id}'
    }

    # Use storage abstraction if available and csv_path is S3 URI
    if dataset_service and csv_path.startswith("s3://"):
        # Use DatasetService for S3
        update_list = [{"row_index": idx, "fields": updates} for idx in row_indices]
        updated_count = dataset_service.update_transactions(dataset_id, update_list, foldername)
    else:
        # Use direct file update for local paths
        updated_count = update_csv_rows(csv_path, row_indices, updates)

    return {'updated_count': updated_count}
