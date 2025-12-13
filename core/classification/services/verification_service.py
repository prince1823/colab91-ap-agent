"""Verification service for human review of canonicalization."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Set

import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from core.database.models import DatasetProcessingState
from core.config import get_config
from core.classification.exceptions import (
    VerificationError,
    InvalidStateTransitionError,
    InvalidColumnError,
    CSVIntegrityError
)
from core.classification.validators import (
    validate_state_transition,
    validate_column_modifications,
    validate_canonicalized_csv
)
from core.classification.constants import WorkflowStatus

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
        state = self._get_state(dataset_id, foldername, lock=True)

        if state.status != WorkflowStatus.CANONICALIZED:
            raise VerificationError(
                f"Dataset must be canonicalized first. Current status: {state.status}"
            )

        # Update status to awaiting verification
        try:
            validate_state_transition(state.status, WorkflowStatus.AWAITING_VERIFICATION)
            state.status = WorkflowStatus.AWAITING_VERIFICATION
            self.session.commit()
        except SQLAlchemyError as e:
            self.session.rollback()
            raise VerificationError(f"Failed to update state: {e}") from e

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
        state = self._get_state(dataset_id, foldername, lock=True)

        valid_states = [WorkflowStatus.CANONICALIZED, WorkflowStatus.AWAITING_VERIFICATION]
        if state.status not in valid_states:
            raise VerificationError(
                f"Cannot verify. Current status: {state.status}. "
                f"Expected one of: {valid_states}"
            )

        # Validate state transition
        try:
            validate_state_transition(state.status, WorkflowStatus.VERIFIED)
        except InvalidStateTransitionError as e:
            raise VerificationError(str(e)) from e

        if not state.canonicalized_csv_path:
            raise VerificationError("Canonicalized CSV path not found in state")

        # Validate CSV path security
        csv_path = Path(state.canonicalized_csv_path)
        if not csv_path.exists():
            raise VerificationError(f"Canonicalized CSV not found: {csv_path}")

        # Load canonicalized CSV
        try:
            canonical_df = pd.read_csv(state.canonicalized_csv_path)
        except Exception as e:
            raise CSVIntegrityError(f"Failed to read canonicalized CSV: {e}") from e
        
        # Validate CSV integrity
        validate_canonicalized_csv(canonical_df)
        
        existing_columns: Set[str] = set(canonical_df.columns)

        # Validate column modifications before applying
        if columns_to_add or columns_to_remove:
            try:
                validate_column_modifications(
                    columns_to_add or [],
                    columns_to_remove or [],
                    existing_columns
                )
            except InvalidColumnError as e:
                raise VerificationError(f"Invalid column modification: {e}") from e

        # Apply column modifications
        modifications_made = self._apply_column_modifications(
            canonical_df, existing_columns, columns_to_add, columns_to_remove
        )

        # Update mappings if provided
        if approved_mappings and state.canonicalization_result:
            state.canonicalization_result['mappings'] = approved_mappings
            modifications_made.append("Updated column mappings")

        # Save modified canonicalized CSV if changes were made
        if modifications_made:
            self._save_modified_csv_and_update_state(
                canonical_df, state, columns_to_add, columns_to_remove, modifications_made
            )

        # Update state
        try:
            state.status = WorkflowStatus.VERIFIED
            verification_note = notes or ("Auto-approved" if auto_approve else None)
            if modifications_made:
                modification_summary = "; ".join(modifications_made)
                state.verification_notes = (
                    f"{verification_note or 'Approved'}. Modifications: {modification_summary}"
                )
            else:
                state.verification_notes = verification_note
            
            self.session.commit()
        except SQLAlchemyError as e:
            self.session.rollback()
            raise VerificationError(f"Failed to update verification state: {e}") from e

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
        state = self._get_state(dataset_id, foldername, lock=True)

        if state.status not in [WorkflowStatus.CANONICALIZED, WorkflowStatus.AWAITING_VERIFICATION]:
            raise VerificationError(
                f"Cannot reject. Current status: {state.status}"
            )

        try:
            validate_state_transition(state.status, WorkflowStatus.PENDING)
            state.status = WorkflowStatus.PENDING
            state.error_message = f"Rejected: {reason}"
            state.canonicalization_result = None
            state.canonicalized_csv_path = None
            self.session.commit()
        except SQLAlchemyError as e:
            self.session.rollback()
            raise VerificationError(f"Failed to update rejection state: {e}") from e

        logger.info(f"Canonicalization rejected for {dataset_id}/{foldername}: {reason}")

    def _get_state(self, dataset_id: str, foldername: str, lock: bool = False) -> DatasetProcessingState:
        """
        Get processing state with optional locking.
        
        Args:
            dataset_id: Dataset identifier
            foldername: Folder name
            lock: If True, lock the row to prevent concurrent modifications
            
        Returns:
            DatasetProcessingState
        """
        query = self.session.query(DatasetProcessingState).filter(
            DatasetProcessingState.dataset_id == dataset_id,
            DatasetProcessingState.foldername == foldername
        )
        
        if lock:
            query = query.with_for_update(nowait=True)
        
        state = query.first()

        if not state:
            raise VerificationError(
                f"No processing state found for {dataset_id}/{foldername}"
            )

        return state

    def _apply_column_modifications(
        self,
        canonical_df: pd.DataFrame,
        existing_columns: Set[str],
        columns_to_add: Optional[List[Dict[str, Any]]],
        columns_to_remove: Optional[List[str]]
    ) -> List[str]:
        """
        Apply column modifications (add/remove) to canonicalized DataFrame.
        
        Args:
            canonical_df: DataFrame to modify
            existing_columns: Set of existing column names (updated in-place)
            columns_to_add: Columns to add
            columns_to_remove: Columns to remove
            
        Returns:
            List of modification descriptions
        """
        modifications_made = []
        
        # 1. Remove unwanted columns
        if columns_to_remove:
            for col_name in columns_to_remove:
                if col_name in canonical_df.columns:
                    canonical_df.drop(columns=[col_name], inplace=True)
                    existing_columns.discard(col_name)
                    modifications_made.append(f"Removed column: {col_name}")
                    logger.info(f"Removed column '{col_name}' from canonicalized dataset")
                else:
                    logger.warning(f"Column '{col_name}' not found in canonicalized CSV, skipping removal")

        # 2. Add missing columns
        if columns_to_add:
            for col_spec in columns_to_add:
                canonical_name = col_spec.get('canonical_name')
                if not canonical_name:
                    raise VerificationError("Each column to add must have 'canonical_name'")
                
                default_value = col_spec.get('default_value', '')
                
                if canonical_name not in canonical_df.columns:
                    canonical_df[canonical_name] = default_value
                    existing_columns.add(canonical_name)
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
        
        # Re-validate CSV after modifications
        if modifications_made:
            validate_canonicalized_csv(canonical_df)
        
        return modifications_made

    def _save_modified_csv_and_update_state(
        self,
        canonical_df: pd.DataFrame,
        state: DatasetProcessingState,
        columns_to_add: Optional[List[Dict[str, Any]]],
        columns_to_remove: Optional[List[str]],
        modifications_made: List[str]
    ) -> None:
        """
        Save modified CSV and update state with modification tracking.
        
        Args:
            canonical_df: Modified DataFrame
            state: Processing state to update
            columns_to_add: Columns that were added
            columns_to_remove: Columns that were removed
            modifications_made: List of modification descriptions
        """
        canonical_df.to_csv(state.canonicalized_csv_path, index=False)
        logger.info(
            f"Updated canonicalized CSV with modifications: {', '.join(modifications_made)}"
        )
        
        # Update canonicalization result to reflect removed columns
        if columns_to_remove and state.canonicalization_result:
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

