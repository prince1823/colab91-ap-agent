"""Classification service for running full classification on verified datasets."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import uuid

import pandas as pd
from sqlalchemy.orm import Session

from core.agents.research import ResearchAgent
from core.agents.context_prioritization import ContextPrioritizationAgent, PrioritizationDecision
from core.agents.spend_classification import ExpertClassifier, ClassificationResult
from core.database import ClassificationDBManager
from core.database.models import DatasetProcessingState
from core.config import get_config
from core.utils.infrastructure.mlflow import setup_mlflow_tracing
from core.utils.invoice.invoice_grouping import group_transactions_by_invoice
from core.utils.cache.lru_cache import LRUCache
from core.utils.invoice.invoice_config import DEFAULT_CONFIG
from core.utils.error.error_models import ClassificationError as TransactionClassificationError
from core.utils.data.path_parsing import parse_classification_path
from core.utils.infrastructure.sanitize import sanitize_invoice_key
from api.services.dataset_service import DatasetService
from core.classification.exceptions import (
    ClassificationError,
    InvalidStateTransitionError,
    CSVIntegrityError
)
from core.classification.constants import (
    WorkflowStatus,
    DEFAULT_MAX_WORKERS,
    DEFAULT_SUPPLIER_RULES_CACHE_SIZE,
    CLASSIFIED_CSV_FILENAME
)
from core.classification.validators import validate_state_transition, validate_canonicalized_csv
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class ClassificationService:
    """Handles full classification after verification."""

    def __init__(
        self,
        session: Session,
        dataset_service: DatasetService,
        taxonomy_path: str,
        enable_tracing: bool = True
    ):
        """
        Initialize classification service.

        Args:
            session: SQLAlchemy database session
            dataset_service: Dataset service for reading/writing
            taxonomy_path: Path to taxonomy YAML file
            enable_tracing: Whether to enable MLflow tracing
        """
        if enable_tracing:
            setup_mlflow_tracing(experiment_name="classification_service")

        self.session = session
        self.dataset_service = dataset_service
        self.taxonomy_path = taxonomy_path
        self.research_agent = ResearchAgent(enable_tracing=enable_tracing)
        self.context_prioritization_agent = ContextPrioritizationAgent(
            taxonomy_path=taxonomy_path, enable_tracing=enable_tracing
        )
        self.expert_classifier = ExpertClassifier(
            taxonomy_path=taxonomy_path, enable_tracing=enable_tracing
        )

        # Cache for supplier profiles
        app_config = get_config()
        invoice_config = DEFAULT_CONFIG
        self._supplier_cache = LRUCache(max_size=invoice_config.supplier_cache_max_size)
        self._supplier_rules_cache = LRUCache(max_size=DEFAULT_SUPPLIER_RULES_CACHE_SIZE)

        # Initialize database manager if caching is enabled
        self.db_manager: Optional[ClassificationDBManager] = None
        self.supplier_cache_max_age_days: Optional[int] = None
        if app_config.enable_classification_cache:
            self.db_manager = ClassificationDBManager(db_path=app_config.database_path)
            self.supplier_cache_max_age_days = app_config.supplier_cache_max_age_days if hasattr(app_config, 'supplier_cache_max_age_days') else None
            self.expert_classifier.db_manager = self.db_manager

        self.invoice_config = invoice_config

    def classify_dataset(
        self,
        dataset_id: str,
        foldername: str = "default",
        max_workers: int = DEFAULT_MAX_WORKERS,
        taxonomy_path: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Run full classification on verified canonicalized dataset.

        Args:
            dataset_id: Dataset identifier
            foldername: Folder name
            max_workers: Maximum number of parallel workers
            taxonomy_path: Optional override for taxonomy path

        Returns:
            DataFrame with classification results

        Raises:
            ValueError: If dataset is not verified
        """
        state = self._get_state(dataset_id, foldername, lock=True)

        if state.status != WorkflowStatus.VERIFIED:
            raise ClassificationError(
                f"Dataset must be verified first. Current status: {state.status}"
            )

        # Validate state transition
        try:
            validate_state_transition(state.status, WorkflowStatus.CLASSIFYING)
        except InvalidStateTransitionError as e:
            raise ClassificationError(str(e)) from e

        try:
            state.status = WorkflowStatus.CLASSIFYING
            run_id = str(uuid.uuid4())
            state.run_id = run_id
            self.session.commit()
        except SQLAlchemyError as e:
            self.session.rollback()
            raise ClassificationError(f"Failed to update classification state: {e}") from e

        try:
            taxonomy = taxonomy_path or self.taxonomy_path

            # 1. Load canonicalized CSV
            if not state.canonicalized_csv_path:
                raise ClassificationError("Canonicalized CSV path not found in state")

            csv_path = Path(state.canonicalized_csv_path)
            if not csv_path.exists():
                raise ClassificationError(f"Canonicalized CSV not found: {csv_path}")

            try:
                canonical_df = pd.read_csv(state.canonicalized_csv_path)
            except Exception as e:
                raise CSVIntegrityError(f"Failed to read canonicalized CSV: {e}") from e
            
            # Validate CSV integrity before processing
            validate_canonicalized_csv(canonical_df)

            # 2. Group transactions into invoices
            invoices = group_transactions_by_invoice(
                canonical_df,
                grouping_columns=self.invoice_config.default_grouping_columns
            )

            # 3. Process each invoice
            classification_results = [None] * len(canonical_df)
            errors = []
            prioritization_decisions = {}
            invoice_key_to_positions = {}
            for invoice_key, invoice_rows in invoices.items():
                positions = [pos for pos, _, _ in invoice_rows]
                invoice_key_to_positions[invoice_key] = positions

            logger.info(f"Processing {len(invoices)} invoices with {len(canonical_df)} total rows (max_workers={max_workers})")

            # Process invoices in parallel if max_workers > 1
            if max_workers > 1 and len(invoices) > 1:
                invoice_items = list(invoices.items())
                from concurrent.futures import ThreadPoolExecutor, as_completed

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_invoice = {
                        executor.submit(
                            self._classify_invoice,
                            invoice_key=invoice_key,
                            invoice_rows=invoice_rows,
                            taxonomy=taxonomy,
                            run_id=run_id,
                            dataset_name=dataset_id,
                        ): (idx, invoice_key, invoice_rows)
                        for idx, (invoice_key, invoice_rows) in enumerate(invoice_items, 1)
                    }

                    completed = 0
                    for future in as_completed(future_to_invoice):
                        idx, invoice_key, invoice_rows = future_to_invoice[future]
                        completed += 1
                        try:
                            invoice_results, invoice_errors, invoice_prioritization = future.result()

                            if invoice_errors:
                                logger.warning(f"Invoice {invoice_key} had {len(invoice_errors)} errors")

                            if invoice_prioritization:
                                prioritization_decisions[invoice_key] = invoice_prioritization

                            for pos, result in invoice_results.items():
                                classification_results[pos] = result

                            errors.extend(invoice_errors)

                            if completed % 10 == 0 or completed == len(invoices):
                                logger.info(f"Progress: {completed}/{len(invoices)} invoices completed")
                        except Exception as e:
                            error_msg = f"Invoice {invoice_key} processing failed: {e}"
                            logger.error(error_msg, exc_info=True)
                            for pos, df_idx, row_dict in invoice_rows:
                                error = TransactionClassificationError(
                                    row_index=df_idx,
                                    supplier_name=row_dict.get('supplier_name'),
                                    error=error_msg,
                                    error_type='INVOICE_PROCESSING_FAILED',
                                    invoice_key=sanitize_invoice_key(invoice_key)
                                )
                                errors.append(error.to_dict())
            else:
                # Sequential processing
                for idx, (invoice_key, invoice_rows) in enumerate(invoices.items(), 1):
                    logger.info(f"Processing invoice {idx}/{len(invoices)}: {invoice_key} ({len(invoice_rows)} rows)")
                    invoice_results, invoice_errors, invoice_prioritization = self._classify_invoice(
                        invoice_key=invoice_key,
                        invoice_rows=invoice_rows,
                        taxonomy=taxonomy,
                        run_id=run_id,
                        dataset_name=dataset_id,
                    )

                    if invoice_prioritization:
                        prioritization_decisions[invoice_key] = invoice_prioritization

                    for pos, result in invoice_results.items():
                        classification_results[pos] = result

                    errors.extend(invoice_errors)

            # 4. Build result DataFrame
            result_df = canonical_df.copy()

            # Add classification columns
            result_df['L1'] = [r.L1 if r and hasattr(r, 'L1') and r.L1 else None for r in classification_results]
            result_df['L2'] = [r.L2 if r and hasattr(r, 'L2') and r.L2 else None for r in classification_results]
            result_df['L3'] = [r.L3 if r and hasattr(r, 'L3') and r.L3 else None for r in classification_results]
            result_df['L4'] = [r.L4 if r and hasattr(r, 'L4') and r.L4 else None for r in classification_results]
            result_df['L5'] = [r.L5 if r and hasattr(r, 'L5') and r.L5 else None for r in classification_results]

            result_df['override_rule_applied'] = [
                r.override_rule_applied if r and hasattr(r, 'override_rule_applied') and r.override_rule_applied else None
                for r in classification_results
            ]
            result_df['reasoning'] = [
                r.reasoning if r and hasattr(r, 'reasoning') and r.reasoning else None
                for r in classification_results
            ]

            # Add prioritization decision fields
            position_to_invoice_key = {}
            for invoice_key, positions in invoice_key_to_positions.items():
                for pos in positions:
                    position_to_invoice_key[pos] = invoice_key

            result_df['should_research'] = [
                prioritization_decisions.get(position_to_invoice_key.get(pos, None), None).should_research
                if position_to_invoice_key.get(pos, None) in prioritization_decisions and prioritization_decisions.get(position_to_invoice_key.get(pos, None), None) is not None
                else None
                for pos in range(len(result_df))
            ]
            result_df['prioritization_strategy'] = [
                prioritization_decisions.get(position_to_invoice_key.get(pos, None), None).prioritization_strategy
                if position_to_invoice_key.get(pos, None) in prioritization_decisions and prioritization_decisions.get(position_to_invoice_key.get(pos, None), None) is not None
                else None
                for pos in range(len(result_df))
            ]
            result_df['supplier_context_strength'] = [
                prioritization_decisions.get(position_to_invoice_key.get(pos, None), None).supplier_context_strength
                if position_to_invoice_key.get(pos, None) in prioritization_decisions and prioritization_decisions.get(position_to_invoice_key.get(pos, None), None) is not None
                else None
                for pos in range(len(result_df))
            ]
            result_df['transaction_data_quality'] = [
                prioritization_decisions.get(position_to_invoice_key.get(pos, None), None).transaction_data_quality
                if position_to_invoice_key.get(pos, None) in prioritization_decisions and prioritization_decisions.get(position_to_invoice_key.get(pos, None), None) is not None
                else None
                for pos in range(len(result_df))
            ]
            result_df['prioritization_reasoning'] = [
                prioritization_decisions.get(position_to_invoice_key.get(pos, None), None).reasoning
                if position_to_invoice_key.get(pos, None) in prioritization_decisions and prioritization_decisions.get(position_to_invoice_key.get(pos, None), None) is not None
                else None
                for pos in range(len(result_df))
            ]

            # Add error column
            position_map = {idx: pos for pos, idx in enumerate(canonical_df.index)}
            error_by_pos = {}
            for error_dict in errors:
                error = TransactionClassificationError.from_dict(error_dict)
                row_idx = error.row_index
                if row_idx is not None:
                    pos = position_map.get(row_idx)
                    if pos is not None:
                        error_by_pos[pos] = error.error

            result_df['error'] = [
                error_by_pos.get(pos, None) if pos in error_by_pos else None
                for pos in range(len(result_df))
            ]

            result_df.attrs['classification_errors'] = errors

            # 5. Save result
            result_path = self._save_classified_csv(dataset_id, foldername, result_df)

            # 6. Update state
            try:
                validate_state_transition(state.status, WorkflowStatus.COMPLETED)
                state.status = WorkflowStatus.COMPLETED
                state.classification_result_path = result_path
                self.session.commit()
            except SQLAlchemyError as e:
                self.session.rollback()
                raise ClassificationError(f"Failed to save classification state: {e}") from e

            logger.info(f"Classification completed for {dataset_id}/{foldername}")
            return result_df

        except Exception as e:
            try:
                state.status = "failed"
                state.error_message = str(e)
                self.session.commit()
            except SQLAlchemyError as db_error:
                self.session.rollback()
                logger.error(f"Failed to update error state: {db_error}", exc_info=True)
            logger.error(f"Classification failed for {dataset_id}/{foldername}: {e}", exc_info=True)
            raise ClassificationError(f"Classification failed: {e}") from e

    def _classify_invoice(
        self,
        invoice_key: str,
        invoice_rows: List[Tuple[int, int, Dict]],
        taxonomy: str,
        run_id: str,
        dataset_name: Optional[str] = None,
    ) -> Tuple[Dict[int, ClassificationResult], List[Dict], Optional[PrioritizationDecision]]:
        """
        Classify all rows in an invoice together.

        This is the same logic from pipeline.py but without canonicalization.
        """
        results = {}
        errors = []
        prioritization_decision = None

        # Extract supplier name
        supplier_name = None
        for _, _, row_dict in invoice_rows:
            candidate = row_dict.get('supplier_name')
            if candidate and pd.notna(candidate) and str(candidate).strip():
                supplier_name = str(candidate).strip()
                break

        if not supplier_name:
            for pos, df_idx, row_dict in invoice_rows:
                error = TransactionClassificationError(
                    row_index=df_idx,
                    supplier_name=None,
                    error='Missing supplier_name in all invoice rows',
                    error_type='MISSING_SUPPLIER_NAME',
                    invoice_key=sanitize_invoice_key(invoice_key)
                )
                errors.append(error.to_dict())
            return results, errors, None

        # Check for direct mapping rule
        cache_key = f"direct_mapping:{supplier_name}:{dataset_name or 'global'}"
        cached_mapping = self._supplier_rules_cache.get(cache_key)
        if cached_mapping is None and self.db_manager:
            direct_mapping = self.db_manager.get_supplier_direct_mapping(supplier_name, dataset_name)
            if direct_mapping:
                self._supplier_rules_cache.set(cache_key, direct_mapping)
            else:
                self._supplier_rules_cache.set(cache_key, False)
                direct_mapping = None
        else:
            direct_mapping = cached_mapping if cached_mapping is not False else None

        if direct_mapping:
            path_dict = parse_classification_path(direct_mapping.classification_path)
            base_result = ClassificationResult(
                L1=path_dict['L1'] or "Unknown",
                L2=path_dict['L2'],
                L3=path_dict['L3'],
                L4=path_dict['L4'],
                L5=path_dict['L5'],
                override_rule_applied=f"direct_mapping_{direct_mapping.id}",
                reasoning=f"[Direct Mapping Rule] Supplier '{supplier_name}' mapped to {direct_mapping.classification_path}",
            )

            batch_results = []
            for pos, df_idx, row_dict in invoice_rows:
                results[pos] = base_result
                batch_results.append({
                    'pos': pos,
                    'df_idx': df_idx,
                    'row_dict': row_dict,
                    'result': base_result,
                })

            if self.db_manager:
                self.db_manager.batch_store_classifications(
                    supplier_name=supplier_name,
                    batch_results=batch_results,
                    run_id=run_id,
                    dataset_name=dataset_name,
                )

            return results, errors, None

        # Batch check cache
        uncached_rows = []
        if self.db_manager:
            hash_to_row = {}
            for pos, df_idx, row_dict in invoice_rows:
                transaction_hash = self.db_manager.create_transaction_hash(row_dict)
                hash_to_row[transaction_hash] = (pos, df_idx, row_dict)

            transaction_hashes = list(hash_to_row.keys())
            cached_results = self.db_manager.batch_get_by_supplier_and_hash(
                supplier_name, transaction_hashes, run_id=run_id
            )

            for transaction_hash, cached_result in cached_results.items():
                pos, df_idx, row_dict = hash_to_row[transaction_hash]
                results[pos] = cached_result

            uncached_hashes = set(transaction_hashes) - set(cached_results.keys())
            uncached_rows = [hash_to_row[txn_hash] for txn_hash in uncached_hashes]
        else:
            uncached_rows = list(invoice_rows)

        if not uncached_rows:
            return results, errors, None

        # Context Prioritization
        uncached_transactions = [row_dict for _, _, row_dict in uncached_rows]
        try:
            prioritization_decision = self.context_prioritization_agent.assess_invoice_context(
                invoice_transactions=uncached_transactions,
                supplier_name=supplier_name,
                supplier_profile=None,
            )
        except Exception as e:
            error_msg = f"Context prioritization failed for invoice: {e}"
            logger.error(error_msg, exc_info=True)
            for pos, df_idx, row_dict in uncached_rows:
                error = TransactionClassificationError(
                    row_index=df_idx,
                    supplier_name=supplier_name,
                    error=error_msg,
                    error_type='CONTEXT_PRIORITIZATION_FAILED',
                    invoice_key=sanitize_invoice_key(invoice_key)
                )
                errors.append(error.to_dict())
            return results, errors, None

        # Supplier Research
        supplier_profile = None
        if prioritization_decision.should_research:
            cache_key = supplier_name.lower().strip()
            supplier_profile = self._supplier_cache.get(cache_key)
            if supplier_profile:
                logger.debug(f"Using in-memory cached research for: {supplier_name}")
            elif self.db_manager:
                cached_profile = self.db_manager.get_supplier_profile(supplier_name, max_age_days=self.supplier_cache_max_age_days)
                if cached_profile:
                    supplier_profile = cached_profile
                    self._supplier_cache.set(cache_key, supplier_profile)

            if not supplier_profile:
                supplier_address = uncached_transactions[0].get('supplier_address')
                supplier_address = supplier_address if (supplier_address and pd.notna(supplier_address) and str(supplier_address).strip()) else None
                try:
                    supplier_profile_obj = self.research_agent.research_supplier(
                        supplier_name,
                        supplier_address=supplier_address
                    )
                    supplier_profile = supplier_profile_obj.to_dict()
                    self._supplier_cache.set(cache_key, supplier_profile)
                except Exception as e:
                    error_msg = f"Supplier research failed for {supplier_name}: {e}"
                    logger.warning(error_msg)
                    for pos, df_idx, row_dict in uncached_rows:
                        error = TransactionClassificationError(
                            row_index=df_idx,
                            supplier_name=supplier_name,
                            error=error_msg,
                            error_type='SUPPLIER_RESEARCH_FAILED',
                            invoice_key=sanitize_invoice_key(invoice_key)
                        )
                        errors.append(error.to_dict())
                    return results, errors, prioritization_decision
        else:
            supplier_profile = {
                'supplier_name': supplier_name,
                'official_business_name': supplier_name,
                'description': '',
                'industry': 'Unknown',
                'products_services': 'Unknown',
                'confidence': 'low',
                'is_large_company': False,
            }

        # Classification
        try:
            taxonomy_constraint = None
            if self.db_manager:
                taxonomy_constraint = self.db_manager.get_supplier_taxonomy_constraint(supplier_name, dataset_name)
                if taxonomy_constraint:
                    logger.info(f"Using taxonomy constraint for invoice supplier: {supplier_name} ({len(taxonomy_constraint.allowed_taxonomy_paths)} paths)")

            classification_results = self.expert_classifier.classify_invoice(
                supplier_profile=supplier_profile,
                invoice_transactions=uncached_transactions,
                taxonomy_yaml=taxonomy,
                prioritization_decision=prioritization_decision,
                dataset_name=dataset_name,
                taxonomy_constraint_paths=taxonomy_constraint.allowed_taxonomy_paths if taxonomy_constraint else None,
            )

            if len(classification_results) != len(uncached_rows):
                error_msg = f"Classification returned {len(classification_results)} results for {len(uncached_rows)} rows"
                logger.error(error_msg)
                for i, (pos, df_idx, row_dict) in enumerate(uncached_rows):
                    if i < len(classification_results):
                        results[pos] = classification_results[i]
                    else:
                        error = TransactionClassificationError(
                            row_index=df_idx,
                            supplier_name=supplier_name,
                            error=f"Missing classification result: {error_msg}",
                            error_type='MISSING_CLASSIFICATION_RESULT',
                            invoice_key=sanitize_invoice_key(invoice_key)
                        )
                        errors.append(error.to_dict())

        except Exception as e:
            error_msg = f"Invoice classification failed for supplier {supplier_name}: {e}"
            logger.error(error_msg, exc_info=True)
            for pos, df_idx, row_dict in uncached_rows:
                error = TransactionClassificationError(
                    row_index=df_idx,
                    supplier_name=supplier_name,
                    error=error_msg,
                    error_type='INVOICE_CLASSIFICATION_FAILED',
                    invoice_key=sanitize_invoice_key(invoice_key)
                )
                errors.append(error.to_dict())
            return results, errors, prioritization_decision

        # Validate and store results
        valid_classifications = []
        for (pos, df_idx, row_dict), result in zip(uncached_rows, classification_results):
            if not result or not hasattr(result, 'L1') or not result.L1:
                error_msg = f"Invalid classification result for row {df_idx}"
                logger.warning(error_msg)
                error = TransactionClassificationError(
                    row_index=df_idx,
                    supplier_name=supplier_name,
                    error=error_msg,
                    error_type='INVALID_CLASSIFICATION_RESULT',
                    invoice_key=sanitize_invoice_key(invoice_key)
                )
                errors.append(error.to_dict())
                continue

            transaction_hash = self.db_manager.create_transaction_hash(row_dict) if self.db_manager else None
            valid_classifications.append((pos, df_idx, row_dict, result, transaction_hash))
            results[pos] = result

        # Batch store
        if self.db_manager and valid_classifications:
            try:
                batch_data = [
                    (txn_hash, result, row_dict, supplier_profile)
                    for _, _, row_dict, result, txn_hash in valid_classifications
                ]
                self.db_manager.batch_store_classifications(
                    supplier_name=supplier_name,
                    classifications=batch_data,
                    run_id=run_id,
                    dataset_name=dataset_name,
                    supplier_profile=supplier_profile,
                )
            except Exception as e:
                logger.warning(f"Failed to batch store classification results for invoice {invoice_key}: {e}")

        return results, errors, prioritization_decision

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
            raise ClassificationError(
                f"No processing state found for {dataset_id}/{foldername}"
            )

        return state

    def _save_classified_csv(
        self, dataset_id: str, foldername: str, df: pd.DataFrame
    ) -> str:
        """Save classified CSV to final location."""
        config = get_config()
        datasets_dir = config.datasets_dir
        # Handle empty foldername for direct dataset access
        if foldername == "":
            dataset_path = datasets_dir / dataset_id
        else:
            dataset_path = datasets_dir / foldername / dataset_id
        dataset_path.mkdir(parents=True, exist_ok=True)

        # Save as classified.csv
        classified_path = dataset_path / CLASSIFIED_CSV_FILENAME
        df.to_csv(classified_path, index=False)

        return str(classified_path)

