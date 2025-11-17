"""Spend Classification Pipeline

Orchestrates column canonicalization, supplier research, and spend classification agents.
"""

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

    def process_transactions(
        self, df: pd.DataFrame, taxonomy_path: Optional[str] = None, return_intermediate: bool = False
    ) -> Union[pd.DataFrame, Tuple[pd.DataFrame, Dict]]:
        """
        Process transactions through the full pipeline

        Args:
            df: DataFrame with raw transaction data (client-specific column names)
            taxonomy_path: Optional override for taxonomy path
            return_intermediate: If True, returns tuple with intermediate results

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
                    profile = self.research_agent.research_supplier(str(supplier_name))
                    self._supplier_cache[supplier_name] = profile.to_dict()
                except Exception as e:
                    # Store error info for debugging
                    self._supplier_cache[supplier_name] = {
                        'supplier_name': str(supplier_name),
                        'error': str(e),
                    }

        # Step 3: Classify transactions
        classification_results = []
        errors = []

        for idx, row in canonical_df.iterrows():
            supplier_name = row.get('supplier_name')
            if not supplier_name or pd.isna(supplier_name):
                errors.append({'row': idx, 'error': 'Missing supplier_name'})
                classification_results.append(None)
                continue

            supplier_profile = self._supplier_cache.get(supplier_name)
            if not supplier_profile or 'error' in supplier_profile:
                errors.append({
                    'row': idx,
                    'supplier': supplier_name,
                    'error': supplier_profile.get('error', 'Supplier profile not found') if supplier_profile else 'Supplier not researched'
                })
                classification_results.append(None)
                continue

            # Prepare transaction data dict
            transaction_data = row.to_dict()

            try:
                result = self.classification_agent.classify_transaction(
                    supplier_profile=supplier_profile,
                    transaction_data=transaction_data,
                    taxonomy_yaml=taxonomy,
                )
                classification_results.append(result)
            except Exception as e:
                errors.append({'row': idx, 'supplier': supplier_name, 'error': str(e)})
                classification_results.append(None)

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

        if return_intermediate:
            intermediate = {
                'mapping_result': mapping_result,
                'supplier_profiles': self._supplier_cache.copy(),
            }
            return result_df, intermediate
        
        return result_df

    def process_batch_transactions(
        self,
        transactions: Union[str, Path, List[Dict], pd.DataFrame],
        taxonomy_path: Optional[str] = None,
        batch_size: int = 10,
    ) -> List[ClassificationResult]:
        """
        Process batch of transactions

        Args:
            transactions: CSV file path, list of dicts, or DataFrame
            taxonomy_path: Optional override for taxonomy path
            batch_size: Number of transactions to process per batch

        Returns:
            List of ClassificationResult objects
        """
        taxonomy = taxonomy_path or self.taxonomy_path

        # Load data if CSV path provided
        if isinstance(transactions, (str, Path)):
            df = pd.read_csv(transactions)
        elif isinstance(transactions, list):
            df = pd.DataFrame(transactions)
        else:
            df = transactions

        # Check if already canonicalized (has supplier_name column)
        if 'supplier_name' not in df.columns:
            # Run canonicalization
            client_schema = self.canonicalization_agent.extract_schema_from_dataframe(df, sample_rows=3)
            mapping_result = self.canonicalization_agent.map_columns(client_schema)
            if mapping_result.validation_passed:
                df = self.canonicalization_agent.apply_mapping(df, mapping_result)
            else:
                raise ValueError(
                    f"Cannot proceed with invalid column mappings: {mapping_result.validation_errors}"
                )

        # Group by supplier to batch research
        unique_suppliers = df['supplier_name'].dropna().unique()

        # Research all unique suppliers
        for supplier_name in unique_suppliers:
            if supplier_name not in self._supplier_cache:
                try:
                    profile = self.research_agent.research_supplier(str(supplier_name))
                    self._supplier_cache[supplier_name] = profile.to_dict()
                except Exception as e:
                    self._supplier_cache[supplier_name] = {
                        'supplier_name': str(supplier_name),
                        'error': str(e),
                    }

        # Process transactions in batches
        results = []
        total_rows = len(df)

        for start_idx in range(0, total_rows, batch_size):
            end_idx = min(start_idx + batch_size, total_rows)
            batch_df = df.iloc[start_idx:end_idx]

            for idx, row in batch_df.iterrows():
                supplier_name = row.get('supplier_name')
                if not supplier_name or pd.isna(supplier_name):
                    results.append(None)
                    continue

                supplier_profile = self._supplier_cache.get(supplier_name)
                if not supplier_profile or 'error' in supplier_profile:
                    results.append(None)
                    continue

                transaction_data = row.to_dict()

                try:
                    result = self.classification_agent.classify_transaction(
                        supplier_profile=supplier_profile,
                        transaction_data=transaction_data,
                        taxonomy_yaml=taxonomy,
                    )
                    results.append(result)
                except Exception as e:
                    results.append(None)

        return results

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
