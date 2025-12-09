"""Spend Classification Pipeline

Orchestrates column canonicalization, supplier research, and spend classification agents.

Simplified 5-step pipeline:
1. Canonicalization
2. Context Prioritization (decide if research is needed)
3. Supplier Research (if needed)
4. Expert Classification (single-shot L1-L5)
5. Store results
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
from core.agents.spend_classification import ExpertClassifier, ClassificationResult
from core.database import ClassificationDBManager
from core.config import get_config
from core.utils.mlflow import setup_mlflow_tracing
from core.utils.invoice_grouping import group_transactions_by_invoice


class SpendClassificationPipeline:
    """Pipeline that orchestrates all agents for end-to-end spend classification.
    
    Simplified 5-step pipeline:
    1. Canonicalization - Map client columns to canonical schema
    2. Context Prioritization - Decide if research is needed
    3. Supplier Research - Get supplier profile if needed
    4. Expert Classification - Single-shot L1-L5 with validation
    5. Store Results - Cache and return
    """

    def __init__(self, taxonomy_path: str, enable_tracing: bool = True):
        """
        Initialize pipeline with all agents.

        Args:
            taxonomy_path: Path to taxonomy YAML file
            enable_tracing: Whether to enable MLflow tracing (default: True)
        """
        if enable_tracing:
            setup_mlflow_tracing(experiment_name="spend_classification_pipeline")

        self.taxonomy_path = taxonomy_path
        self.canonicalization_agent = ColumnCanonicalizationAgent(enable_tracing=enable_tracing)
        self.research_agent = ResearchAgent(enable_tracing=enable_tracing)
        self.context_prioritization_agent = ContextPrioritizationAgent(
            taxonomy_path=taxonomy_path, enable_tracing=enable_tracing
        )
        self.expert_classifier = ExpertClassifier(
            taxonomy_path=taxonomy_path, enable_tracing=enable_tracing
        )

        # Cache for supplier profiles to avoid duplicate research calls
        self._supplier_cache: Dict[str, Dict] = {}
        
        # Initialize database manager if caching is enabled
        config = get_config()
        self.db_manager: Optional[ClassificationDBManager] = None
        self.supplier_cache_max_age_days: Optional[int] = None
        if config.enable_classification_cache:
            self.db_manager = ClassificationDBManager(db_path=config.database_path)
            # Cache the config value to avoid repeated get_config() calls in hot path
            self.supplier_cache_max_age_days = config.supplier_cache_max_age_days if hasattr(config, 'supplier_cache_max_age_days') else None
            # Pass db_manager to expert classifier for classification caching
            self.expert_classifier.db_manager = self.db_manager


    def _classify_single_row(
        self, pos: int, df_idx: int, row_dict: Dict, supplier_name: str, taxonomy: str, run_id: str, dataset_name: Optional[str] = None, prioritization_decision: Optional[PrioritizationDecision] = None
    ) -> Tuple[int, Optional[ClassificationResult], Optional[Dict]]:
        """
        Classify a single row using the simplified pipeline.
        
        Steps:
        1. Check exact match cache
        2. Supplier Research - get profile if needed (based on pre-computed prioritization decision)
        3. Expert Classification - single-shot L1-L5
        4. Store result
        
        Args:
            pos: Position in DataFrame (for result list indexing)
            df_idx: Original DataFrame index (for error reporting)
            row_dict: Row data as dictionary
            supplier_name: Supplier name
            taxonomy: Taxonomy path
            run_id: Run ID (UUID) to identify this run
            dataset_name: Optional dataset name (e.g., "fox", "innova")
            prioritization_decision: Pre-computed prioritization decision (from context prioritization step)
            
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
            
            # Use pre-computed prioritization decision (context prioritization done before parallel processing)
            if not prioritization_decision:
                return pos, None, {
                    'row_index': df_idx,
                    'supplier_name': supplier_name,
                    'error': 'Missing prioritization decision'
                }
            
            # Step 2: Supplier Research - get profile if needed (based on prioritization decision)
            supplier_profile = None
            if prioritization_decision.should_research:
                # Ensure supplier_name is not None before processing
                if supplier_name is None:
                    supplier_name = ""
                cache_key = str(supplier_name).lower().strip()
                
                # Check in-memory cache first
                if cache_key in self._supplier_cache:
                    supplier_profile = self._supplier_cache[cache_key]
                    logger.debug(f"Using in-memory cached research data for: {supplier_name}")
                # Check database for persistent cache (across runs)
                elif self.db_manager:
                    # Use cached config value instead of calling get_config() for every row
                    cached_profile = self.db_manager.get_supplier_profile(supplier_name, max_age_days=self.supplier_cache_max_age_days)
                    if cached_profile:
                        supplier_profile = cached_profile
                        self._supplier_cache[cache_key] = supplier_profile  # Also cache in memory
                        logger.debug(f"Using database-cached research data for: {supplier_name}")
                
                # Research supplier if not found in cache
                if not supplier_profile:
                    # Address is already combined by canonicalization agent into supplier_address field
                    supplier_address = row_dict.get('supplier_address')
                    supplier_address = supplier_address if (supplier_address and pd.notna(supplier_address) and str(supplier_address).strip()) else None
                    supplier_profile_obj = self.research_agent.research_supplier(
                        str(supplier_name),
                        supplier_address=supplier_address
                    )
                    supplier_profile = supplier_profile_obj.to_dict()
                    self._supplier_cache[cache_key] = supplier_profile
                    logger.debug(f"Researched and cached: {supplier_name}")
            else:
                # Use minimal supplier profile (no research needed)
                supplier_profile = {
                    'supplier_name': supplier_name,
                    'official_business_name': supplier_name,
                    'description': '',
                    'industry': 'Unknown',
                    'products_services': 'Unknown',
                    'confidence': 'low',
                    'is_large_company': False,
                }
            
            # Step 3: Expert Classification - single-shot L1-L5 with tool-augmented validation
            try:
                result = self.expert_classifier.classify_with_tools(
                    supplier_profile=supplier_profile,
                    transaction_data=row_dict,
                    taxonomy_yaml=taxonomy,
                    prioritization_decision=prioritization_decision,
                    dataset_name=dataset_name,
                )
                
                # Validate result
                if not result or not hasattr(result, 'L1') or not result.L1:
                    error_msg = f"Expert classifier returned invalid result for supplier: {supplier_name}"
                    logger.warning(error_msg)
                    return pos, None, {
                        'row_index': df_idx,
                        'supplier_name': supplier_name,
                        'error': error_msg,
                    }
            except Exception as e:
                error_msg = f"Error in classification for supplier {supplier_name}: {e}"
                logger.error(error_msg, exc_info=True)
                return pos, None, {
                    'row_index': df_idx,
                    'supplier_name': supplier_name,
                    'error': error_msg,
                }
            
            # Step 4: Store result in database
            if self.db_manager:
                transaction_hash = self.db_manager.create_transaction_hash(row_dict)
                self.db_manager.store_classification(
                    supplier_name=supplier_name,
                    transaction_hash=transaction_hash,
                    classification_result=result,
                    run_id=run_id,
                    dataset_name=dataset_name,
                    supplier_profile=supplier_profile,
                    transaction_data=row_dict,
                )
            
            return pos, result, None
        except Exception as e:
            return pos, None, {'row': df_idx, 'supplier': supplier_name, 'error': str(e)}

    def _classify_invoice(
        self,
        invoice_key: str,
        invoice_rows: List[Tuple[int, int, Dict]],
        taxonomy: str,
        run_id: str,
        dataset_name: Optional[str] = None,
    ) -> Tuple[Dict[int, ClassificationResult], List[Dict]]:
        """
        Classify all rows in an invoice together.

        Steps:
        1. Check cache for each row (may skip processing if all cached)
        2. Context Prioritization at invoice level
        3. Supplier Research (if needed)
        4. Invoice-level Classification (one result per row)
        5. Store results

        Args:
            invoice_key: Invoice identifier (for logging)
            invoice_rows: List of (position, df_index, row_dict) tuples
            taxonomy: Taxonomy path
            run_id: Run ID (UUID)
            dataset_name: Optional dataset name

        Returns:
            Tuple of (position_to_result_dict, errors_list)
        """
        results = {}
        errors = []

        # Extract supplier name from first row (should be same for all rows in invoice)
        supplier_name = invoice_rows[0][2].get('supplier_name')
        if not supplier_name or pd.isna(supplier_name):
            for pos, df_idx, row_dict in invoice_rows:
                errors.append({'row_index': df_idx, 'supplier_name': None, 'error': 'Missing supplier_name'})
            return results, errors

        supplier_name = str(supplier_name)

        # Step 1: Check cache for each row
        uncached_rows = []
        for pos, df_idx, row_dict in invoice_rows:
            if self.db_manager:
                transaction_hash = self.db_manager.create_transaction_hash(row_dict)
                cached_result = self.db_manager.get_by_supplier_and_hash(supplier_name, transaction_hash, run_id=run_id)
                if cached_result:
                    results[pos] = cached_result
                    logger.debug(f"Cache hit for invoice row at position {pos}")
                    continue
            uncached_rows.append((pos, df_idx, row_dict))

        # If all rows cached, we're done
        if not uncached_rows:
            logger.debug(f"Invoice {invoice_key}: All {len(invoice_rows)} rows cached")
            return results, errors

        logger.debug(f"Invoice {invoice_key}: {len(uncached_rows)} uncached rows (out of {len(invoice_rows)})")

        # Extract transaction data for uncached rows
        uncached_transactions = [row_dict for _, _, row_dict in uncached_rows]

        # Step 2: Invoice-level Context Prioritization
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
                errors.append({'row_index': df_idx, 'supplier_name': supplier_name, 'error': error_msg})
            return results, errors

        # Step 3: Supplier Research (if needed)
        supplier_profile = None
        if prioritization_decision.should_research:
            cache_key = supplier_name.lower().strip()

            # Check in-memory cache
            if cache_key in self._supplier_cache:
                supplier_profile = self._supplier_cache[cache_key]
                logger.debug(f"Using in-memory cached research for: {supplier_name}")
            # Check database
            elif self.db_manager:
                cached_profile = self.db_manager.get_supplier_profile(supplier_name, max_age_days=self.supplier_cache_max_age_days)
                if cached_profile:
                    supplier_profile = cached_profile
                    self._supplier_cache[cache_key] = supplier_profile
                    logger.debug(f"Using database-cached research for: {supplier_name}")

            # Research if not found
            if not supplier_profile:
                # Use supplier address from first row
                supplier_address = uncached_transactions[0].get('supplier_address')
                supplier_address = supplier_address if (supplier_address and pd.notna(supplier_address) and str(supplier_address).strip()) else None
                supplier_profile_obj = self.research_agent.research_supplier(
                    supplier_name,
                    supplier_address=supplier_address
                )
                supplier_profile = supplier_profile_obj.to_dict()
                self._supplier_cache[cache_key] = supplier_profile
                logger.debug(f"Researched and cached: {supplier_name}")
        else:
            # Minimal supplier profile
            supplier_profile = {
                'supplier_name': supplier_name,
                'official_business_name': supplier_name,
                'description': '',
                'industry': 'Unknown',
                'products_services': 'Unknown',
                'confidence': 'low',
                'is_large_company': False,
            }

        # Step 4: Invoice-level Classification
        try:
            classification_results = self.expert_classifier.classify_invoice(
                supplier_profile=supplier_profile,
                invoice_transactions=uncached_transactions,
                taxonomy_yaml=taxonomy,
                prioritization_decision=prioritization_decision,
                dataset_name=dataset_name,
            )

            # Validate results
            if len(classification_results) != len(uncached_rows):
                error_msg = f"Classification returned {len(classification_results)} results for {len(uncached_rows)} rows"
                logger.error(error_msg)
                for pos, df_idx, row_dict in uncached_rows:
                    errors.append({'row_index': df_idx, 'supplier_name': supplier_name, 'error': error_msg})
                return results, errors

        except Exception as e:
            error_msg = f"Invoice classification failed for supplier {supplier_name}: {e}"
            logger.error(error_msg, exc_info=True)
            for pos, df_idx, row_dict in uncached_rows:
                errors.append({'row_index': df_idx, 'supplier_name': supplier_name, 'error': error_msg})
            return results, errors

        # Step 5: Store results in database and build result dict
        for (pos, df_idx, row_dict), result in zip(uncached_rows, classification_results):
            # Validate result
            if not result or not hasattr(result, 'L1') or not result.L1:
                error_msg = f"Invalid classification result for row {df_idx}"
                logger.warning(error_msg)
                errors.append({'row_index': df_idx, 'supplier_name': supplier_name, 'error': error_msg})
                continue

            # Store in database
            if self.db_manager:
                transaction_hash = self.db_manager.create_transaction_hash(row_dict)
                self.db_manager.store_classification(
                    supplier_name=supplier_name,
                    transaction_hash=transaction_hash,
                    classification_result=result,
                    run_id=run_id,
                    dataset_name=dataset_name,
                    supplier_profile=supplier_profile,
                    transaction_data=row_dict,
                )

            results[pos] = result

        return results, errors

    def process_transactions(
        self, df: pd.DataFrame, taxonomy_path: Optional[str] = None, return_intermediate: bool = False, max_workers: int = 1, run_id: Optional[str] = None, dataset_name: Optional[str] = None
    ) -> Union[pd.DataFrame, Tuple[pd.DataFrame, Dict]]:
        """
        Process transactions through the full pipeline

        Args:
            df: DataFrame with raw transaction data (client-specific column names)
            taxonomy_path: Optional override for taxonomy path
            return_intermediate: If True, returns tuple with intermediate results
            max_workers: Maximum number of parallel workers for classification (default: 1, context prioritization done before parallel processing)
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

        # Step 2: Group transactions into invoices
        invoices = group_transactions_by_invoice(canonical_df)

        # Step 3: Process each invoice (with multi-level caching)
        classification_results = [None] * len(canonical_df)
        errors = []

        for invoice_key, invoice_rows in invoices.items():
            invoice_results, invoice_errors = self._classify_invoice(
                invoice_key=invoice_key,
                invoice_rows=invoice_rows,
                taxonomy=taxonomy,
                run_id=run_id,
                dataset_name=dataset_name,
            )

            # Merge results into master results list
            for pos, result in invoice_results.items():
                classification_results[pos] = result

            # Collect errors
            errors.extend(invoice_errors)

        # Build error_by_pos mapping for compatibility with downstream code
        error_by_pos = {}
        for error in errors:
            if 'row_index' in error:
                # Convert DataFrame index to position
                pos = canonical_df.index.get_loc(error['row_index'])
                error_by_pos[pos] = error.get('error', str(error))
            elif 'row' in error:
                # Legacy format compatibility
                try:
                    pos = canonical_df.index.get_loc(error['row'])
                    error_by_pos[pos] = error.get('error', str(error))
                except KeyError:
                    pass

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
