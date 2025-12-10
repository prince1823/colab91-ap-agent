"""Spend Classification Pipeline

Orchestrates column canonicalization, supplier research, and spend classification agents.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import pandas as pd

from core.agents.column_canonicalization import ColumnCanonicalizationAgent, MappingResult
from core.agents.research import ResearchAgent
from core.agents.spend_classification import SpendClassifier, ClassificationResult
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
        self.classification_agent = SpendClassifier(
            taxonomy_path=taxonomy_path, enable_tracing=enable_tracing
        )

        # Cache for supplier profiles to avoid duplicate research calls
        self._supplier_cache: Dict[str, Dict] = {}

    def _classify_single_row(
        self, idx: int, row_dict: Dict, supplier_profile: Dict, taxonomy: str
    ) -> Tuple[int, Optional[ClassificationResult], Optional[Dict]]:
        """
        Helper method to classify a single row (used for parallel processing)
        
        Args:
            idx: Row index
            row_dict: Row data as dictionary
            supplier_profile: Supplier profile dictionary
            taxonomy: Taxonomy path
            
        Returns:
            Tuple of (row_index, classification_result, error_dict)
        """
        supplier_name = row_dict.get('supplier_name')
        if not supplier_name or pd.isna(supplier_name):
            return idx, None, {'row': idx, 'error': 'Missing supplier_name'}
        
        if not supplier_profile or 'error' in supplier_profile:
            return idx, None, {
                'row': idx,
                'supplier': supplier_name,
                'error': supplier_profile.get('error', 'Supplier profile not found') if supplier_profile else 'Supplier not researched'
            }
        
        try:
            result = self.classification_agent.classify_transaction(
                supplier_profile=supplier_profile,
                transaction_data=row_dict,
                taxonomy_yaml=taxonomy,
            )
            return idx, result, None
        except Exception as e:
            return idx, None, {'row': idx, 'supplier': supplier_name, 'error': str(e)}

    def process_transactions(
        self,
        df: pd.DataFrame,
        taxonomy_path: Optional[str] = None,
        return_intermediate: bool = False,
        max_workers: int = 5,
        normalized_column_overrides: Optional[Dict[str, str]] = None,
    ) -> Union[pd.DataFrame, Tuple[pd.DataFrame, Dict]]:
        """
        Process transactions through the full pipeline

        Args:
            df: DataFrame with raw transaction data (client-specific column names)
            taxonomy_path: Optional override for taxonomy path
            return_intermediate: If True, returns tuple with intermediate results
            max_workers: Maximum number of parallel workers for classification (default: 5)

        Returns:
            DataFrame with original + canonical + classification columns
            If return_intermediate=True, returns (result_df, intermediate_dict) where intermediate_dict contains:
            - mapping_result: Column canonicalization mapping result
            - supplier_profiles: Dict mapping supplier_name to profile dict
        """
        taxonomy = taxonomy_path or self.taxonomy_path

        # Step 1: Canonicalization
        client_schema = self.canonicalization_agent.extract_schema_from_dataframe(df, sample_rows=3)
        mapping_result = self.canonicalization_agent.map_columns(client_schema)

        if not mapping_result.validation_passed:
            raise ValueError(
                f"Cannot proceed with invalid column mappings: {mapping_result.validation_errors}"
            )

        canonical_df = self.canonicalization_agent.apply_mapping(df, mapping_result)

        # Step 2: Research suppliers (cache results)
        unique_suppliers = canonical_df['supplier_name'].dropna().unique()
        for supplier_name in unique_suppliers:
            if supplier_name not in self._supplier_cache:
                try:
                    # Get supplier address if available (optional field)
                    supplier_address = None
                    if 'supplier_address' in canonical_df.columns:
                        # Get address from first row with this supplier (addresses should be consistent per supplier)
                        supplier_rows = canonical_df[canonical_df['supplier_name'] == supplier_name]
                        if not supplier_rows.empty:
                            address_value = supplier_rows['supplier_address'].dropna().iloc[0] if 'supplier_address' in supplier_rows.columns else None
                            if address_value and pd.notna(address_value) and str(address_value).strip():
                                supplier_address = str(address_value).strip()
                    
                    profile = self.research_agent.research_supplier(
                        str(supplier_name), 
                        supplier_address=supplier_address
                    )
                    self._supplier_cache[supplier_name] = profile.to_dict()
                except Exception as e:
                    # Store error info for debugging
                    self._supplier_cache[supplier_name] = {
                        'supplier_name': str(supplier_name),
                        'error': str(e),
                    }

        # Step 3: Classify transactions (parallel processing)
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

            supplier_profile = self._supplier_cache.get(supplier_name)
            if not supplier_profile or 'error' in supplier_profile:
                errors.append({
                    'row': df_idx,
                    'supplier': supplier_name,
                    'error': supplier_profile.get('error', 'Supplier profile not found') if supplier_profile else 'Supplier not researched'
                })
                continue

            # Add task for parallel processing (pos is position in DataFrame, df_idx is original index)
            tasks.append((pos, df_idx, row_dict, supplier_profile, taxonomy))

        # Process tasks in parallel
        if tasks:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all tasks
                future_to_pos = {
                    executor.submit(self._classify_single_row, df_idx, row_dict, supplier_profile, taxonomy): pos
                    for pos, df_idx, row_dict, supplier_profile, taxonomy in tasks
                }
                
                # Collect results as they complete
                for future in as_completed(future_to_pos):
                    pos = future_to_pos[future]
                    df_idx, result, error = future.result()
                    classification_results[pos] = result
                    if error:
                        errors.append(error)

        # Step 4: Add classification columns to DataFrame
        result_df = canonical_df.copy()

        # Add classification columns
        result_df['L1'] = [r.L1 if r else None for r in classification_results]
        result_df['L2'] = [r.L2 if r else None for r in classification_results]
        result_df['L3'] = [r.L3 if r else None for r in classification_results]
        result_df['L4'] = [r.L4 if r else None for r in classification_results]
        result_df['L5'] = [r.L5 if r else None for r in classification_results]

        # Add other metadata
        result_df['override_rule_applied'] = [
            r.override_rule_applied if r else None for r in classification_results
        ]
        result_df['reasoning'] = [r.reasoning if r else None for r in classification_results]

        # Store errors as attribute for inspection
        result_df.attrs['classification_errors'] = errors

        # Apply optional normalized column overrides for output display
        if normalized_column_overrides:
            safe_overrides = {
                col: new_name.strip()
                for col, new_name in normalized_column_overrides.items()
                if col in result_df.columns and isinstance(new_name, str) and new_name.strip()
            }
            if safe_overrides:
                # Avoid accidental duplicate target names by preserving originals on conflict
                target_names = set()
                rename_map: Dict[str, str] = {}
                for canonical_col, new_name in safe_overrides.items():
                    if new_name in target_names:
                        continue
                    target_names.add(new_name)
                    rename_map[canonical_col] = new_name
                if rename_map:
                    result_df = result_df.rename(columns=rename_map)
                    # Preserve attached metadata after rename
                    result_df.attrs['classification_errors'] = errors

        if return_intermediate:
            intermediate = {
                'mapping_result': mapping_result,
                'supplier_profiles': self._supplier_cache.copy(),
            }
            return result_df, intermediate
        
        return result_df

    def process_single_transaction(
        self, row: Dict, supplier_profile: Dict, taxonomy_path: Optional[str] = None
    ) -> ClassificationResult:
        """
        Helper for single transaction classification

        Args:
            row: Transaction data as dict
            supplier_profile: Supplier profile dict
            taxonomy_path: Optional override for taxonomy path

        Returns:
            ClassificationResult
        """
        taxonomy = taxonomy_path or self.taxonomy_path
        return self.classification_agent.classify_transaction(
            supplier_profile=supplier_profile,
            transaction_data=row,
            taxonomy_yaml=taxonomy,
        )
