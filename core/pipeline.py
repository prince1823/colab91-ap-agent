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
from core.utils.lru_cache import LRUCache
from core.utils.invoice_config import InvoiceProcessingConfig, DEFAULT_CONFIG
from core.utils.error_models import ClassificationError
from core.utils.path_parsing import parse_classification_path
from core.utils.sanitize import sanitize_invoice_key


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

        # Cache for supplier profiles with LRU eviction to prevent memory growth
        app_config = get_config()
        invoice_config = DEFAULT_CONFIG
        self._supplier_cache = LRUCache(max_size=invoice_config.supplier_cache_max_size)
        
        # Cache for supplier rules (direct mappings and taxonomy constraints)
        # Smaller cache size since rules are less frequently accessed
        self._supplier_rules_cache = LRUCache(max_size=500)
        
        # Initialize database manager if caching is enabled
        self.db_manager: Optional[ClassificationDBManager] = None
        self.supplier_cache_max_age_days: Optional[int] = None
        if app_config.enable_classification_cache:
            self.db_manager = ClassificationDBManager(db_path=app_config.database_path)
            # Cache the config value to avoid repeated get_config() calls in hot path
            self.supplier_cache_max_age_days = app_config.supplier_cache_max_age_days if hasattr(app_config, 'supplier_cache_max_age_days') else None
            # Pass db_manager to expert classifier for classification caching
            self.expert_classifier.db_manager = self.db_manager
        
        # Invoice processing configuration
        self.invoice_config = invoice_config


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
                
                # Step 1.5: Check for direct mapping rule (100% confidence, skip LLM)
                # Use cache to avoid repeated database queries
                cache_key = f"direct_mapping:{supplier_name}:{dataset_name or 'global'}"
                cached_mapping = self._supplier_rules_cache.get(cache_key)
                if cached_mapping is None and self.db_manager:
                    direct_mapping = self.db_manager.get_supplier_direct_mapping(supplier_name, dataset_name)
                    if direct_mapping:
                        self._supplier_rules_cache.set(cache_key, direct_mapping)
                    else:
                        # Cache False to avoid repeated lookups for non-existent rules
                        self._supplier_rules_cache.set(cache_key, False)
                        direct_mapping = None
                else:
                    direct_mapping = cached_mapping if cached_mapping is not False else None
                
                if direct_mapping:
                    # Parse classification path
                    path_dict = parse_classification_path(direct_mapping.classification_path)
                    result = ClassificationResult(
                        L1=path_dict['L1'] or "Unknown",
                        L2=path_dict['L2'],
                        L3=path_dict['L3'],
                        L4=path_dict['L4'],
                        L5=path_dict['L5'],
                        override_rule_applied=f"direct_mapping_{direct_mapping.id}",
                        reasoning=f"[Direct Mapping Rule] Supplier '{supplier_name}' mapped to {direct_mapping.classification_path}",
                    )
                    logger.info(f"Using direct mapping for supplier: {supplier_name} -> {direct_mapping.classification_path}")
                    
                    # Store result in cache
                    if self.db_manager:
                        transaction_hash = self.db_manager.create_transaction_hash(row_dict)
                        self.db_manager.store_classification(
                            supplier_name=supplier_name,
                            transaction_hash=transaction_hash,
                            classification_result=result,
                            supplier_profile=None,
                            transaction_data=row_dict,
                            run_id=run_id,
                            dataset_name=dataset_name,
                        )
                    
                    return pos, result, None
            
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
                supplier_profile = self._supplier_cache.get(cache_key)
                if supplier_profile:
                    logger.debug(f"Using in-memory cached research data for: {supplier_name}")
                # Check database for persistent cache (across runs)
                elif self.db_manager:
                    # Use cached config value instead of calling get_config() for every row
                    cached_profile = self.db_manager.get_supplier_profile(supplier_name, max_age_days=self.supplier_cache_max_age_days)
                    if cached_profile:
                        supplier_profile = cached_profile
                        self._supplier_cache.set(cache_key, supplier_profile)  # Also cache in memory
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
                    self._supplier_cache.set(cache_key, supplier_profile)
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
            
            # Step 2.5: Check for taxonomy constraint (replace RAG with stored list)
            # Use cache to avoid repeated database queries
            taxonomy_constraint = None
            cache_key = f"taxonomy_constraint:{supplier_name}:{dataset_name or 'global'}"
            cached_constraint = self._supplier_rules_cache.get(cache_key)
            if cached_constraint is not None:
                taxonomy_constraint = cached_constraint if cached_constraint is not False else None
            elif self.db_manager:
                taxonomy_constraint = self.db_manager.get_supplier_taxonomy_constraint(supplier_name, dataset_name)
                if taxonomy_constraint:
                    self._supplier_rules_cache.set(cache_key, taxonomy_constraint)
                    logger.info(f"Using taxonomy constraint for supplier: {supplier_name} ({len(taxonomy_constraint.allowed_taxonomy_paths)} paths)")
                else:
                    # Cache None to avoid repeated lookups for non-existent rules
                    self._supplier_rules_cache.set(cache_key, False)
            
            # Step 3: Expert Classification - single-shot L1-L5 with tool-augmented validation
            try:
                result = self.expert_classifier.classify_with_tools(
                    supplier_profile=supplier_profile,
                    transaction_data=row_dict,
                    taxonomy_yaml=taxonomy,
                    prioritization_decision=prioritization_decision,
                    dataset_name=dataset_name,
                    taxonomy_constraint_paths=taxonomy_constraint.allowed_taxonomy_paths if taxonomy_constraint else None,
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
    ) -> Tuple[Dict[int, ClassificationResult], List[Dict], Optional[PrioritizationDecision]]:
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
            Tuple of (position_to_result_dict, errors_list, prioritization_decision)
        """
        results = {}
        errors = []
        prioritization_decision = None

        # Extract supplier name from any row (check all rows, not just first)
        supplier_name = None
        for _, _, row_dict in invoice_rows:
            candidate = row_dict.get('supplier_name')
            if candidate and pd.notna(candidate) and str(candidate).strip():
                supplier_name = str(candidate).strip()
                break
        
        if not supplier_name:
            for pos, df_idx, row_dict in invoice_rows:
                error = ClassificationError(
                    row_index=df_idx,
                    supplier_name=None,
                    error='Missing supplier_name in all invoice rows',
                    error_type='MISSING_SUPPLIER_NAME',
                    invoice_key=sanitize_invoice_key(invoice_key)
                )
                errors.append(error.to_dict())
            return results, errors

        # Step 1: Check for direct mapping rule (100% confidence, skip LLM for all rows)
        # Use cache to avoid repeated database queries
        cache_key = f"direct_mapping:{supplier_name}:{dataset_name or 'global'}"
        cached_mapping = self._supplier_rules_cache.get(cache_key)
        if cached_mapping is None and self.db_manager:
            direct_mapping = self.db_manager.get_supplier_direct_mapping(supplier_name, dataset_name)
            if direct_mapping:
                self._supplier_rules_cache.set(cache_key, direct_mapping)
            else:
                # Cache False to avoid repeated lookups for non-existent rules
                self._supplier_rules_cache.set(cache_key, False)
                direct_mapping = None
        else:
            direct_mapping = cached_mapping if cached_mapping is not False else None
        
        if direct_mapping:
                # Parse classification path
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
                logger.info(f"Using direct mapping for invoice supplier: {supplier_name} -> {direct_mapping.classification_path}")
                
                # Apply to all uncached rows
                batch_results = []
                for pos, df_idx, row_dict in invoice_rows:
                    result = base_result  # Same result for all rows
                    results[pos] = result
                    batch_results.append({
                        'pos': pos,
                        'df_idx': df_idx,
                        'row_dict': row_dict,
                        'result': result,
                    })
                
                # Batch store all results
                if self.db_manager:
                    self.db_manager.batch_store_classifications(
                        supplier_name=supplier_name,
                        batch_results=batch_results,
                        run_id=run_id,
                        dataset_name=dataset_name,
                    )
                
                return results, errors, None

        # Step 1.5: Batch check cache for all rows in invoice
        uncached_rows = []
        if self.db_manager:
            # Batch create hashes and look up all at once
            hash_to_row = {}
            for pos, df_idx, row_dict in invoice_rows:
                transaction_hash = self.db_manager.create_transaction_hash(row_dict)
                hash_to_row[transaction_hash] = (pos, df_idx, row_dict)
            
            # Single batch query instead of N individual queries
            transaction_hashes = list(hash_to_row.keys())
            cached_results = self.db_manager.batch_get_by_supplier_and_hash(
                supplier_name, transaction_hashes, run_id=run_id
            )
            
            # Map cached results back to positions
            for transaction_hash, cached_result in cached_results.items():
                pos, df_idx, row_dict = hash_to_row[transaction_hash]
                results[pos] = cached_result
                logger.debug(f"Cache hit for invoice row at position {pos}")
            
            # Collect uncached rows
            uncached_hashes = set(transaction_hashes) - set(cached_results.keys())
            uncached_rows = [hash_to_row[txn_hash] for txn_hash in uncached_hashes]
        else:
            # No db_manager, all rows are uncached
            uncached_rows = list(invoice_rows)

        # If all rows cached, we're done (no prioritization decision needed)
        if not uncached_rows:
            logger.debug(f"Invoice {invoice_key}: All {len(invoice_rows)} rows cached")
            return results, errors, None

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
                error = ClassificationError(
                    row_index=df_idx,
                    supplier_name=supplier_name,
                    error=error_msg,
                    error_type='CONTEXT_PRIORITIZATION_FAILED',
                    invoice_key=sanitize_invoice_key(invoice_key)
                )
                errors.append(error.to_dict())
            return results, errors, None

        # Step 3: Supplier Research (if needed)
        supplier_profile = None
        if prioritization_decision.should_research:
            cache_key = supplier_name.lower().strip()

            # Check in-memory cache
            supplier_profile = self._supplier_cache.get(cache_key)
            if supplier_profile:
                logger.debug(f"Using in-memory cached research for: {supplier_name}")
            # Check database
            elif self.db_manager:
                cached_profile = self.db_manager.get_supplier_profile(supplier_name, max_age_days=self.supplier_cache_max_age_days)
                if cached_profile:
                    supplier_profile = cached_profile
                    self._supplier_cache.set(cache_key, supplier_profile)
                    logger.debug(f"Using database-cached research for: {supplier_name}")

            # Research if not found
            if not supplier_profile:
                # Use supplier address from first row
                supplier_address = uncached_transactions[0].get('supplier_address')
                supplier_address = supplier_address if (supplier_address and pd.notna(supplier_address) and str(supplier_address).strip()) else None
                try:
                    supplier_profile_obj = self.research_agent.research_supplier(
                        supplier_name,
                        supplier_address=supplier_address
                    )
                    supplier_profile = supplier_profile_obj.to_dict()
                    self._supplier_cache.set(cache_key, supplier_profile)
                    logger.debug(f"Researched and cached: {supplier_name}")
                except Exception as e:
                    error_msg = f"Supplier research failed for {supplier_name}: {e}"
                    logger.warning(error_msg)
                    # Mark all rows in this invoice with the research error and skip classification
                    for pos, df_idx, row_dict in uncached_rows:
                        error = ClassificationError(
                            row_index=df_idx,
                            supplier_name=supplier_name,
                            error=error_msg,
                            error_type='SUPPLIER_RESEARCH_FAILED',
                            invoice_key=sanitize_invoice_key(invoice_key)
                        )
                        errors.append(error.to_dict())
                    return results, errors, prioritization_decision
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
            # Check for taxonomy constraint (replace RAG with stored list)
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

            # Validate results - handle partial results gracefully
            if len(classification_results) != len(uncached_rows):
                error_msg = f"Classification returned {len(classification_results)} results for {len(uncached_rows)} rows"
                logger.error(error_msg)
                # Map what we have, mark missing as errors
                for i, (pos, df_idx, row_dict) in enumerate(uncached_rows):
                    if i < len(classification_results):
                        # Store valid result
                        results[pos] = classification_results[i]
                    else:
                        # Missing result - add error
                        error = ClassificationError(
                            row_index=df_idx,
                            supplier_name=supplier_name,
                            error=f"Missing classification result: {error_msg}",
                            error_type='MISSING_CLASSIFICATION_RESULT',
                            invoice_key=sanitize_invoice_key(invoice_key)
                        )
                        errors.append(error.to_dict())
                # Continue processing - don't return early, we've handled partial results

        except Exception as e:
            error_msg = f"Invoice classification failed for supplier {supplier_name}: {e}"
            logger.error(error_msg, exc_info=True)
            for pos, df_idx, row_dict in uncached_rows:
                error = ClassificationError(
                    row_index=df_idx,
                    supplier_name=supplier_name,
                    error=error_msg,
                    error_type='INVOICE_CLASSIFICATION_FAILED',
                    invoice_key=sanitize_invoice_key(invoice_key)
                )
                errors.append(error.to_dict())
            return results, errors, prioritization_decision

        # Step 5: Validate results and prepare for batch storage
        valid_classifications = []
        for (pos, df_idx, row_dict), result in zip(uncached_rows, classification_results):
            # Validate result before storing
            if not result or not hasattr(result, 'L1') or not result.L1:
                error_msg = f"Invalid classification result for row {df_idx}"
                logger.warning(error_msg)
                error = ClassificationError(
                    row_index=df_idx,
                    supplier_name=supplier_name,
                    error=error_msg,
                    error_type='INVALID_CLASSIFICATION_RESULT',
                    invoice_key=sanitize_invoice_key(invoice_key)
                )
                errors.append(error.to_dict())
                continue
            
            # Additional validation: ensure result matches taxonomy structure
            if not self._validate_classification_result(result, taxonomy):
                error_msg = f"Classification result does not match taxonomy structure for row {df_idx}"
                logger.warning(error_msg)
                error = ClassificationError(
                    row_index=df_idx,
                    supplier_name=supplier_name,
                    error=error_msg,
                    error_type='INVALID_TAXONOMY_PATH',
                    invoice_key=sanitize_invoice_key(invoice_key)
                )
                errors.append(error.to_dict())
                continue

            # Prepare for batch storage
            transaction_hash = self.db_manager.create_transaction_hash(row_dict) if self.db_manager else None
            valid_classifications.append((pos, df_idx, row_dict, result, transaction_hash))
            results[pos] = result

        # Batch store all valid classifications in a single transaction
        if self.db_manager and valid_classifications:
            try:
                batch_data = [
                    (
                        txn_hash,
                        result,
                        row_dict,
                        supplier_profile,  # Use invoice-level supplier profile
                    )
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
                # Log error but don't fail the entire invoice - results are still valid
                logger.warning(f"Failed to batch store classification results for invoice {invoice_key}: {e}")

        return results, errors, prioritization_decision
    
    def _validate_classification_result(self, result: ClassificationResult, taxonomy: str) -> bool:
        """
        Validate that classification result matches taxonomy structure.

        Args:
            result: Classification result to validate
            taxonomy: Taxonomy path (for loading taxonomy if needed)

        Returns:
            True if valid, False otherwise
        """
        if not result or not hasattr(result, 'L1') or not result.L1:
            return False
        
        # Basic validation: check that L1 exists and is not empty
        if result.L1 == "Unknown":
            return True  # Unknown is always valid
        
        # Could add more sophisticated validation here (e.g., check against taxonomy list)
        # For now, basic validation is sufficient
        return True

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

        # Step 2: Group transactions into invoices (using configurable grouping columns)
        invoices = group_transactions_by_invoice(
            canonical_df,
            grouping_columns=self.invoice_config.default_grouping_columns
        )

        # Step 3: Process each invoice (with multi-level caching and parallel processing)
        classification_results = [None] * len(canonical_df)
        errors = []
        # Track prioritization decisions per invoice (invoice_key -> PrioritizationDecision)
        prioritization_decisions = {}
        # Build invoice_key to position mapping for prioritization decisions
        invoice_key_to_positions = {}
        for invoice_key, invoice_rows in invoices.items():
            positions = [pos for pos, _, _ in invoice_rows]
            invoice_key_to_positions[invoice_key] = positions

        print(f"Processing {len(invoices)} invoices with {len(canonical_df)} total rows (max_workers={max_workers})")
        
        # Process invoices in parallel if max_workers > 1
        if max_workers > 1 and len(invoices) > 1:
            # Parallel processing
            invoice_items = list(invoices.items())
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all invoice processing tasks
                future_to_invoice = {
                    executor.submit(
                        self._classify_invoice,
                        invoice_key=invoice_key,
                        invoice_rows=invoice_rows,
                        taxonomy=taxonomy,
                        run_id=run_id,
                        dataset_name=dataset_name,
                    ): (idx, invoice_key, invoice_rows)
                    for idx, (invoice_key, invoice_rows) in enumerate(invoice_items, 1)
                }
                
                # Collect results as they complete
                completed = 0
                for future in as_completed(future_to_invoice):
                    idx, invoice_key, invoice_rows = future_to_invoice[future]
                    completed += 1
                    try:
                        invoice_results, invoice_errors, invoice_prioritization = future.result()
                        
                        if invoice_errors:
                            logger.warning(f"Invoice {invoice_key} had {len(invoice_errors)} errors")
                        
                        # Store prioritization decision for this invoice
                        if invoice_prioritization:
                            prioritization_decisions[invoice_key] = invoice_prioritization
                        
                        # Merge results into master results list
                        for pos, result in invoice_results.items():
                            classification_results[pos] = result
                        
                        # Collect errors
                        errors.extend(invoice_errors)
                        
                        if completed % 10 == 0 or completed == len(invoices):
                            print(f"Progress: {completed}/{len(invoices)} invoices completed")
                    except Exception as e:
                        error_msg = f"Invoice {invoice_key} processing failed: {e}"
                        logger.error(error_msg, exc_info=True)
                        # Mark all rows in this invoice as errors
                        for pos, df_idx, row_dict in invoice_rows:
                            error = ClassificationError(
                                row_index=df_idx,
                                supplier_name=row_dict.get('supplier_name'),
                                error=error_msg,
                                error_type='INVOICE_PROCESSING_FAILED',
                                invoice_key=sanitize_invoice_key(invoice_key)
                            )
                            errors.append(error.to_dict())
        else:
            # Sequential processing (for max_workers=1 or single invoice)
            for idx, (invoice_key, invoice_rows) in enumerate(invoices.items(), 1):
                print(f"Processing invoice {idx}/{len(invoices)}: {invoice_key} ({len(invoice_rows)} rows)")
                invoice_results, invoice_errors, invoice_prioritization = self._classify_invoice(
                    invoice_key=invoice_key,
                    invoice_rows=invoice_rows,
                    taxonomy=taxonomy,
                    run_id=run_id,
                    dataset_name=dataset_name,
                )
                if invoice_errors:
                    print(f"WARNING: Invoice {invoice_key} had {len(invoice_errors)} errors")
                print(f"Completed invoice {idx}/{len(invoices)}: {invoice_key}")

                # Store prioritization decision for this invoice
                if invoice_prioritization:
                    prioritization_decisions[invoice_key] = invoice_prioritization

                # Merge results into master results list
                for pos, result in invoice_results.items():
                    classification_results[pos] = result

                # Collect errors
                errors.extend(invoice_errors)

        # Build position map once for efficient lookup
        position_map = {idx: pos for pos, idx in enumerate(canonical_df.index)}
        
        # Build error_by_pos mapping for compatibility with downstream code
        error_by_pos = {}
        for error_dict in errors:
            # Convert to ClassificationError for consistent handling
            error = ClassificationError.from_dict(error_dict)
            
            # Try to map row_index to position
            row_idx = error.row_index
            if row_idx is not None:
                pos = position_map.get(row_idx)
                if pos is not None:
                    error_by_pos[pos] = error.error
                else:
                    logger.warning(f"Could not map error row_index {row_idx} to position")

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
        
        # Add prioritization decision fields
        # Map each position to its invoice_key, then to its prioritization decision
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

        # Add error column - match errors to their corresponding positions
        result_df['error'] = [
            error_by_pos.get(pos, None) if pos in error_by_pos else None
            for pos in range(len(result_df))
        ]

        # Store errors as attribute for inspection
        result_df.attrs['classification_errors'] = errors

        if return_intermediate:
            # Convert LRU cache to dict for return (snapshot)
            supplier_profiles_snapshot = {}
            # Note: LRUCache doesn't have a copy method, so we iterate
            # This is a snapshot at this point in time
            intermediate = {
                'mapping_result': mapping_result,
                'supplier_profiles': supplier_profiles_snapshot,  # Empty for now - cache is internal
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
