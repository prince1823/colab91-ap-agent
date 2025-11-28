"""Spend Classification Pipeline

Orchestrates column canonicalization, supplier research, and spend classification agents.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import uuid

import pandas as pd

logger = logging.getLogger(__name__)

from core.agents.column_canonicalization import ColumnCanonicalizationAgent, MappingResult
from core.agents.research import ResearchAgent
from core.agents.context_prioritization import ContextPrioritizationAgent, PrioritizationDecision
from core.agents.spend_classification import SpendClassifier, ClassificationResult, L1Classifier
from core.database import ClassificationDBManager
from core.config import get_config
from core.utils.mlflow import setup_mlflow_tracing


class SpendClassificationPipeline:
    """Pipeline that orchestrates all three agents for end-to-end spend classification"""

    def __init__(self, taxonomy_path: str, enable_tracing: bool = True):
        """
        Initialize pipeline with all three agents

        Args:
            taxonomy_path: Path to taxonomy YAML file
            enable_tracing: Whether to enable MLflow tracing (default: True)
        """
        if enable_tracing:
            setup_mlflow_tracing(experiment_name="spend_classification_pipeline")

        self.taxonomy_path = taxonomy_path
        self.canonicalization_agent = ColumnCanonicalizationAgent(enable_tracing=enable_tracing)
        self.research_agent = ResearchAgent(enable_tracing=enable_tracing)
        self.context_prioritization_agent = ContextPrioritizationAgent(enable_tracing=enable_tracing)
        self.l1_classifier = L1Classifier(
            taxonomy_path=taxonomy_path, enable_tracing=enable_tracing
        )
        self.classification_agent = SpendClassifier(
            taxonomy_path=taxonomy_path, enable_tracing=enable_tracing
        )

        # Cache for supplier profiles to avoid duplicate research calls
        self._supplier_cache: Dict[str, Dict] = {}
        
        # Initialize database manager if caching is enabled
        config = get_config()
        self.db_manager: Optional[ClassificationDBManager] = None
        if config.enable_classification_cache:
            self.db_manager = ClassificationDBManager(config.database_path)

    def _classify_single_row(
        self, pos: int, df_idx: int, row_dict: Dict, supplier_name: str, taxonomy: str, run_id: str, dataset_name: Optional[str] = None
    ) -> Tuple[int, Optional[ClassificationResult], Optional[Dict]]:
        """
        Helper method to classify a single row with multi-level caching (used for parallel processing)
        
        Args:
            pos: Position in DataFrame (for result list indexing)
            df_idx: Original DataFrame index (for error reporting)
            row_dict: Row data as dictionary
            supplier_name: Supplier name
            taxonomy: Taxonomy path
            run_id: Run ID (UUID) to identify this run
            dataset_name: Optional dataset name (e.g., "fox", "innova")
            
        Returns:
            Tuple of (position, classification_result, error_dict)
        """
        try:
            # Step 1: Check exact match cache (supplier_name + transaction_hash) - current run only
            if self.db_manager:
                transaction_hash = self.db_manager.create_transaction_hash(row_dict)
                cached_result = self.db_manager.get_by_supplier_and_hash(supplier_name, transaction_hash, run_id=run_id)
                if cached_result:
                    return pos, cached_result, None
            
            # Step 2: Assess context and make prioritization decision (before L1 classification)
            prioritization_decision = self.context_prioritization_agent.assess_context(
                transaction_data=row_dict,
                supplier_name=supplier_name,
                supplier_profile=None,  # No profile yet for L1
                l1_result=None,  # No L1 result yet
            )
            
            # Step 3: Do early research if needed for L1 classification
            supplier_profile_for_l1 = None
            if prioritization_decision.should_research:
                # Do early research when context assessment indicates it's needed
                cache_key = str(supplier_name).lower().strip()
                if cache_key in self._supplier_cache:
                    supplier_profile_for_l1 = self._supplier_cache[cache_key]
                    logger.debug(f"Using cached research data for early L1 classification: {supplier_name}")
                else:
                    # Research supplier early
                    supplier_address = row_dict.get('supplier_address')
                    supplier_profile_obj = self.research_agent.research_supplier(
                        str(supplier_name),
                        supplier_address=supplier_address if supplier_address and pd.notna(supplier_address) else None
                    )
                    supplier_profile_for_l1 = supplier_profile_obj.to_dict()
                    # Cache the research result for reuse
                    self._supplier_cache[cache_key] = supplier_profile_for_l1
                    logger.debug(f"Early research completed for L1 classification: {supplier_name}")
            
            # Step 4: Run L1 classifier (with supplier profile if available, and prioritization decision)
            l1_result = self.l1_classifier.classify_l1(
                transaction_data=row_dict,
                taxonomy_yaml=taxonomy,
                supplier_profile=supplier_profile_for_l1,
                prioritization_decision=prioritization_decision,
            )
            l1_category = l1_result.get('L1') if l1_result else None
            
            # Validate L1 result
            if not l1_category or pd.isna(l1_category) or str(l1_category).strip() == '':
                error_msg = f"L1 classifier returned empty result for supplier: {supplier_name}"
                logger.warning(error_msg)
                return pos, None, {
                    'row_index': df_idx,
                    'supplier_name': supplier_name,
                    'error': error_msg,
                    'l1_result': l1_result,
                }
            
            # Step 5: Check Supplier + L1 cache - current run only
            if self.db_manager:
                cached_result = self.db_manager.get_by_supplier_and_l1(supplier_name, l1_category, run_id=run_id)
                if cached_result:
                    return pos, cached_result, None
            
            # Step 6: Re-assess context with L1 result and get prioritization decision for full classifier
            prioritization_decision_full = self.context_prioritization_agent.assess_context(
                transaction_data=row_dict,
                supplier_name=supplier_name,
                supplier_profile=supplier_profile_for_l1,  # Use profile if we have it
                l1_result=l1_result,
            )
            
            # Step 7: Do additional research if needed (if not already done)
            supplier_profile = supplier_profile_for_l1  # Reuse if we already did early research
            if not supplier_profile and prioritization_decision_full.should_research:
                # Check if we already have research data for this supplier (cache)
                cache_key = str(supplier_name).lower().strip()
                if cache_key in self._supplier_cache:
                    supplier_profile = self._supplier_cache[cache_key]
                    logger.debug(f"Using cached research data for supplier: {supplier_name}")
                else:
                    # Research supplier
                    supplier_address = row_dict.get('supplier_address')
                    supplier_profile_obj = self.research_agent.research_supplier(
                        str(supplier_name),
                        supplier_address=supplier_address if supplier_address and pd.notna(supplier_address) else None
                    )
                    supplier_profile = supplier_profile_obj.to_dict()
                    # Cache the research result for reuse
                    self._supplier_cache[cache_key] = supplier_profile
                    logger.debug(f"Cached research data for supplier: {supplier_name}")
            elif not supplier_profile:
                # Use minimal supplier profile (no research needed)
                supplier_profile = {
                    'supplier_name': supplier_name,
                    'official_business_name': supplier_name,
                    'description': '',
                    'industry': 'Unknown',
                    'products_services': 'Unknown',
                    'confidence': 'low',
                    'is_person': False,
                    'is_large_company': False,
                }
            
            # Step 8: Run full classifier (L1 + transaction + supplier + filtered taxonomy + prioritization decision)
            try:
                result = self.classification_agent.classify_transaction(
                    l1_category=l1_category,
                    supplier_profile=supplier_profile,
                    transaction_data=row_dict,
                    taxonomy_yaml=taxonomy,
                    prioritization_decision=prioritization_decision_full,
                )
                
                # Validate result
                if not result or not hasattr(result, 'L1') or not result.L1:
                    error_msg = f"Full classifier returned None or invalid result for supplier: {supplier_name}"
                    logger.warning(error_msg)
                    return pos, None, {
                        'row_index': df_idx,
                        'supplier_name': supplier_name,
                        'error': error_msg,
                        'l1_category': l1_category,
                    }
            except Exception as e:
                error_msg = f"Error in full classification for supplier {supplier_name}: {e}"
                logger.error(error_msg, exc_info=True)
                return pos, None, {
                    'row_index': df_idx,
                    'supplier_name': supplier_name,
                    'error': error_msg,
                    'l1_category': l1_category,
                }
            
            # Step 7: Store result in database at all cache levels
            if self.db_manager:
                transaction_hash = self.db_manager.create_transaction_hash(row_dict)
                self.db_manager.store_classification(
                    supplier_name=supplier_name,
                    transaction_hash=transaction_hash,
                    l1_category=l1_category,
                    classification_result=result,
                    run_id=run_id,
                    dataset_name=dataset_name,
                    supplier_profile=supplier_profile,
                    transaction_data=row_dict,
                )
            
            return pos, result, None
        except Exception as e:
            return pos, None, {'row': df_idx, 'supplier': supplier_name, 'error': str(e)}

    def process_transactions(
        self, df: pd.DataFrame, taxonomy_path: Optional[str] = None, return_intermediate: bool = False, max_workers: int = 5, run_id: Optional[str] = None, dataset_name: Optional[str] = None
    ) -> Union[pd.DataFrame, Tuple[pd.DataFrame, Dict]]:
        """
        Process transactions through the full pipeline

        Args:
            df: DataFrame with raw transaction data (client-specific column names)
            taxonomy_path: Optional override for taxonomy path
            return_intermediate: If True, returns tuple with intermediate results
            max_workers: Maximum number of parallel workers for classification (default: 5)
            run_id: Optional run ID (UUID). If not provided, a new UUID will be generated
            dataset_name: Optional dataset name (e.g., "fox", "innova"). Used for tracking

        Returns:
            DataFrame with original + canonical + classification columns
            If return_intermediate=True, returns (result_df, intermediate_dict) where intermediate_dict contains:
            - mapping_result: Column canonicalization mapping result
            - supplier_profiles: Dict mapping supplier_name to profile dict
            - run_id: The run_id used for this processing run
        """
        taxonomy = taxonomy_path or self.taxonomy_path
        
        # Generate run_id if not provided
        if run_id is None:
            run_id = str(uuid.uuid4())

        # Step 1: Canonicalization
        client_schema = self.canonicalization_agent.extract_schema_from_dataframe(df, sample_rows=3)
        mapping_result = self.canonicalization_agent.map_columns(client_schema)

        if not mapping_result.validation_passed:
            raise ValueError(
                f"Cannot proceed with invalid column mappings: {mapping_result.validation_errors}"
            )

        canonical_df = self.canonicalization_agent.apply_mapping(df, mapping_result)

        # Step 2: Classify transactions (parallel processing with multi-level caching)
        # Initialize results list with None for all rows
        classification_results = [None] * len(canonical_df)
        errors = []

        # Prepare tasks for parallel processing
        # Use enumerate to track position in DataFrame (for list indexing)
        tasks = []
        for pos, row_tuple in enumerate(canonical_df.itertuples(index=True)):
            df_idx = row_tuple.Index  # Original DataFrame index
            # Convert named tuple to dict, excluding Index
            row_dict = {col: getattr(row_tuple, col) for col in canonical_df.columns}
            
            supplier_name = row_dict.get('supplier_name')
            if not supplier_name or pd.isna(supplier_name):
                errors.append({'row': df_idx, 'error': 'Missing supplier_name'})
                continue

            # Add task for parallel processing (pos is position in DataFrame, df_idx is original index)
            tasks.append((pos, df_idx, row_dict, str(supplier_name), taxonomy, run_id, dataset_name))

        # Process tasks in parallel
        if tasks:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all tasks
                future_to_pos = {
                    executor.submit(self._classify_single_row, pos, df_idx, row_dict, supplier_name, taxonomy, run_id, dataset_name): pos
                    for pos, df_idx, row_dict, supplier_name, taxonomy, run_id, dataset_name in tasks
                }
                
                # Collect results as they complete
                error_by_pos = {}  # Map position to error
                for future in as_completed(future_to_pos):
                    pos = future_to_pos[future]
                    result_pos, result, error = future.result()
                    classification_results[result_pos] = result
                    if error:
                        errors.append(error)
                        # Map error to position for easier lookup
                        error_by_pos[result_pos] = error.get('error', str(error))

        # Step 4: Add classification columns to DataFrame
        result_df = canonical_df.copy()

        # Add classification columns (handle None results gracefully)
        result_df['L1'] = [r.L1 if r and hasattr(r, 'L1') and r.L1 else None for r in classification_results]
        result_df['L2'] = [r.L2 if r and hasattr(r, 'L2') and r.L2 else None for r in classification_results]
        result_df['L3'] = [r.L3 if r and hasattr(r, 'L3') and r.L3 else None for r in classification_results]
        result_df['L4'] = [r.L4 if r and hasattr(r, 'L4') and r.L4 else None for r in classification_results]
        result_df['L5'] = [r.L5 if r and hasattr(r, 'L5') and r.L5 else None for r in classification_results]

        # Add other metadata
        result_df['override_rule_applied'] = [
            r.override_rule_applied if r and hasattr(r, 'override_rule_applied') and r.override_rule_applied else None for r in classification_results
        ]
        result_df['reasoning'] = [r.reasoning if r and hasattr(r, 'reasoning') and r.reasoning else None for r in classification_results]

        # Add error column - match errors to their corresponding positions
        result_df['error'] = [
            error_by_pos.get(pos, None) if pos in error_by_pos else None
            for pos in range(len(result_df))
        ]

        # Store errors as attribute for inspection
        result_df.attrs['classification_errors'] = errors

        if return_intermediate:
            intermediate = {
                'mapping_result': mapping_result,
                'supplier_profiles': self._supplier_cache.copy(),
                'run_id': run_id,
            }
            return result_df, intermediate
        
        return result_df
    
    def _is_transaction_data_sparse(self, row_dict: Dict) -> bool:
        """
        Check if transaction data is sparse (generic GL + accounting references).
        
        Args:
            row_dict: Transaction data dictionary
            
        Returns:
            True if transaction data is sparse, False otherwise
        """
        from core.utils.transaction_utils import is_valid_value
        
        line_desc = row_dict.get('line_description')
        gl_desc = row_dict.get('gl_description')
        
        # Check if line description is missing or is an accounting reference
        has_meaningful_line_desc = False
        if line_desc and is_valid_value(line_desc):
            line_desc_str = str(line_desc).strip().lower()
            # Check if it's likely an accounting reference (starts with common patterns)
            accounting_patterns = ['operational journal:', 'supplier invoice:', 'journal entry', 'journal:']
            if not any(line_desc_str.startswith(pattern) for pattern in accounting_patterns):
                # Not an accounting reference, might be meaningful
                if len(line_desc_str) > 3:
                    has_meaningful_line_desc = True
        
        # Check if GL is generic payment term
        has_meaningful_gl = False
        if gl_desc and is_valid_value(gl_desc):
            gl_desc_str = str(gl_desc).strip().lower()
            generic_gl_terms = [
                'accounts payable', 'accounts receivable', 'ap', 'ar',
                'accrued invoices', 'accrued', 'payable', 't&e payable',
                'general ledger', 'gl', 'journal entry', 'adjustment'
            ]
            if not any(term in gl_desc_str for term in generic_gl_terms):
                has_meaningful_gl = True
        
        # Data is sparse if both line description and GL are not meaningful
        return not (has_meaningful_line_desc or has_meaningful_gl)
