"""Verification service for human review of canonicalization."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

import pandas as pd
from sqlalchemy.orm import Session

from core.database.models import DatasetProcessingState
from core.config import get_config

logger = logging.getLogger(__name__)


class VerificationService:
    """Handles human verification of column mappings."""

    def __init__(self, session: Session):
        """
        Initialize verification service.

        Args:
            session: SQLAlchemy database session
        """
        self.session = session

    def get_canonicalization_for_review(
        self, dataset_id: str, foldername: str = "default"
    ) -> Dict:
        """
        Get canonicalization result for human review.

        Args:
            dataset_id: Dataset identifier
            foldername: Folder name

        Returns:
            Dictionary with canonicalization result and paths

        Raises:
            ValueError: If dataset is not in canonicalized state
        """
        state = self._get_state(dataset_id, foldername)

        if state.status != "canonicalized":
            raise ValueError(
                f"Dataset must be canonicalized first. Current status: {state.status}"
            )

        # Update status to awaiting verification
        if state.status == "canonicalized":
            state.status = "awaiting_verification"
            self.session.commit()

        return {
            "dataset_id": dataset_id,
            "foldername": foldername,
            "canonicalization_result": state.canonicalization_result,
            "canonicalized_csv_path": state.canonicalized_csv_path,
        }

    def approve_canonicalization(
        self,
        dataset_id: str,
        foldername: str,
        approved_mappings: Optional[Dict] = None,
        columns_to_add: Optional[List[Dict[str, Any]]] = None,
        columns_to_remove: Optional[List[str]] = None,
        notes: Optional[str] = None,
        auto_approve: bool = False
    ) -> None:
        """
        Approve canonicalization mappings with optional column modifications.

        Args:
            dataset_id: Dataset identifier
            foldername: Folder name
            approved_mappings: Optional updated mappings (if user made changes)
            columns_to_add: Optional list of columns to add. Each dict should have:
                {'canonical_name': str, 'default_value': Any, 'description': Optional[str]}
            columns_to_remove: Optional list of canonical column names to remove
            notes: Optional verification notes
            auto_approve: If True, auto-approve without human review (for benchmarks)

        Raises:
            ValueError: If dataset is not in correct state or modifications are invalid
        """
        state = self._get_state(dataset_id, foldername)

        valid_states = ["canonicalized", "awaiting_verification"]
        if state.status not in valid_states:
            raise ValueError(
                f"Cannot verify. Current status: {state.status}. "
                f"Expected one of: {valid_states}"
            )

        if not state.canonicalized_csv_path:
            raise ValueError("Canonicalized CSV path not found in state")

        # Load canonicalized CSV
        canonical_df = pd.read_csv(state.canonicalized_csv_path)

        # Apply column modifications
        modifications_made = []
        
        # 1. Remove unwanted columns
        if columns_to_remove:
            for col_name in columns_to_remove:
                if col_name in canonical_df.columns:
                    canonical_df = canonical_df.drop(columns=[col_name])
                    modifications_made.append(f"Removed column: {col_name}")
                    logger.info(f"Removed column '{col_name}' from canonicalized dataset")
                else:
                    logger.warning(f"Column '{col_name}' not found in canonicalized CSV, skipping removal")

        # 2. Add missing columns
        if columns_to_add:
            for col_spec in columns_to_add:
                canonical_name = col_spec.get('canonical_name')
                if not canonical_name:
                    raise ValueError("Each column to add must have 'canonical_name'")
                
                default_value = col_spec.get('default_value', '')
                description = col_spec.get('description', '')
                
                if canonical_name not in canonical_df.columns:
                    # Add column with default value for all rows
                    canonical_df[canonical_name] = default_value
                    modifications_made.append(
                        f"Added column: {canonical_name} (default: {default_value})"
                    )
                    logger.info(
                        f"Added column '{canonical_name}' with default value '{default_value}'"
                    )
                else:
                    logger.warning(
                        f"Column '{canonical_name}' already exists, skipping addition"
                    )

        # 3. Update mappings if provided
        if approved_mappings and state.canonicalization_result:
            state.canonicalization_result['mappings'] = approved_mappings
            modifications_made.append("Updated column mappings")

        # Save modified canonicalized CSV if changes were made
        if modifications_made:
            canonical_df.to_csv(state.canonicalized_csv_path, index=False)
            logger.info(
                f"Updated canonicalized CSV with modifications: {', '.join(modifications_made)}"
            )
            
            # Update canonicalization result to reflect removed columns
            if columns_to_remove and state.canonicalization_result:
                # Track removed columns in the result
                removed_cols = state.canonicalization_result.get('removed_columns', [])
                removed_cols.extend(columns_to_remove)
                state.canonicalization_result['removed_columns'] = list(set(removed_cols))
            
            # Track added columns in the result
            if columns_to_add and state.canonicalization_result:
                added_cols = state.canonicalization_result.get('added_columns', [])
                added_cols.extend([
                    {
                        'canonical_name': col['canonical_name'],
                        'default_value': col.get('default_value', ''),
                        'description': col.get('description', '')
                    }
                    for col in columns_to_add
                ])
                state.canonicalization_result['added_columns'] = added_cols

        # Update state
        state.status = "verified"
        verification_note = notes or ("Auto-approved" if auto_approve else None)
        if modifications_made:
            modification_summary = "; ".join(modifications_made)
            state.verification_notes = (
                f"{verification_note or 'Approved'}. Modifications: {modification_summary}"
            )
        else:
            state.verification_notes = verification_note
        
        self.session.commit()

        logger.info(f"Canonicalization verified for {dataset_id}/{foldername}")

    def reject_canonicalization(
        self,
        dataset_id: str,
        foldername: str,
        reason: str
    ) -> None:
        """
        Reject canonicalization and reset to pending.

        Args:
            dataset_id: Dataset identifier
            foldername: Folder name
            reason: Reason for rejection

        Raises:
            ValueError: If dataset is not in correct state
        """
        state = self._get_state(dataset_id, foldername)

        if state.status not in ["canonicalized", "awaiting_verification"]:
            raise ValueError(
                f"Cannot reject. Current status: {state.status}"
            )

        state.status = "pending"
        state.error_message = f"Rejected: {reason}"
        state.canonicalization_result = None
        state.canonicalized_csv_path = None
        self.session.commit()

        logger.info(f"Canonicalization rejected for {dataset_id}/{foldername}: {reason}")

    def _get_state(self, dataset_id: str, foldername: str) -> DatasetProcessingState:
        """Get processing state."""
        state = self.session.query(DatasetProcessingState).filter(
            DatasetProcessingState.dataset_id == dataset_id,
            DatasetProcessingState.foldername == foldername
        ).first()

        if not state:
            raise ValueError(
                f"No processing state found for {dataset_id}/{foldername}"
            )

        return state

