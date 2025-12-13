"""Canonicalization service for column mapping."""

import logging
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
from sqlalchemy.orm import Session

from core.agents.column_canonicalization import ColumnCanonicalizationAgent, MappingResult
from core.database.models import DatasetProcessingState
from api.services.dataset_service import DatasetService
from core.config import get_config

logger = logging.getLogger(__name__)


class CanonicalizationService:
    """Handles column canonicalization stage."""

    def __init__(self, session: Session, dataset_service: DatasetService):
        """
        Initialize canonicalization service.

        Args:
            session: SQLAlchemy database session
            dataset_service: Dataset service for reading/writing datasets
        """
        self.session = session
        self.dataset_service = dataset_service
        self.canonicalization_agent = ColumnCanonicalizationAgent(enable_tracing=True)

    def canonicalize_dataset(
        self,
        dataset_id: str,
        foldername: str = "default"
    ) -> MappingResult:
        """
        Run canonicalization on dataset.

        Args:
            dataset_id: Dataset identifier
            foldername: Folder name

        Returns:
            MappingResult with column mappings

        Raises:
            ValueError: If canonicalization validation fails
        """
        # 1. Get or create processing state
        state = self._get_or_create_state(dataset_id, foldername)
        state.status = "canonicalizing"
        self.session.commit()

        try:
            # 2. Read raw CSV
            raw_df = self.dataset_service.storage.read_csv(dataset_id, foldername)

            # 3. Extract schema and map columns
            client_schema = self.canonicalization_agent.extract_schema_from_dataframe(
                raw_df, sample_rows=3
            )
            mapping_result = self.canonicalization_agent.map_columns(client_schema)

            if not mapping_result.validation_passed:
                raise ValueError(
                    f"Canonicalization validation failed: {mapping_result.validation_errors}"
                )

            # 4. Apply mapping to create canonicalized CSV
            canonical_df = self.canonicalization_agent.apply_mapping(raw_df, mapping_result)

            # 5. Save canonicalized CSV to intermediate location
            canonical_path = self._save_canonicalized_csv(
                dataset_id, foldername, canonical_df
            )

            # 6. Update state
            state.status = "canonicalized"
            state.canonicalization_result = {
                'mappings': mapping_result.mappings,
                'unmapped_columns': mapping_result.unmapped_columns,
                'validation_passed': mapping_result.validation_passed,
                'validation_errors': mapping_result.validation_errors,
            }
            state.canonicalized_csv_path = canonical_path
            self.session.commit()

            logger.info(f"Canonicalization completed for {dataset_id}/{foldername}")
            return mapping_result

        except Exception as e:
            state.status = "failed"
            state.error_message = str(e)
            self.session.commit()
            logger.error(f"Canonicalization failed for {dataset_id}/{foldername}: {e}", exc_info=True)
            raise

    def _get_or_create_state(
        self, dataset_id: str, foldername: str
    ) -> DatasetProcessingState:
        """Get or create processing state."""
        state = self.session.query(DatasetProcessingState).filter(
            DatasetProcessingState.dataset_id == dataset_id,
            DatasetProcessingState.foldername == foldername
        ).first()

        if not state:
            state = DatasetProcessingState(
                dataset_id=dataset_id,
                foldername=foldername,
                status="pending"
            )
            self.session.add(state)
            self.session.commit()

        return state

    def _save_canonicalized_csv(
        self, dataset_id: str, foldername: str, df: pd.DataFrame
    ) -> str:
        """Save canonicalized CSV to intermediate location."""
        config = get_config()
        datasets_dir = config.datasets_dir
        dataset_path = datasets_dir / foldername / dataset_id
        dataset_path.mkdir(parents=True, exist_ok=True)

        canonical_path = dataset_path / "canonicalized.csv"
        df.to_csv(canonical_path, index=False)

        return str(canonical_path)

