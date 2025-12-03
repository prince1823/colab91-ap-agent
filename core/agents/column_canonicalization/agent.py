"""Column canonicalization agent."""

import json
import logging
from typing import Dict, List, Optional

import dspy
import pandas as pd

logger = logging.getLogger(__name__)

from core.config import get_config
from core.llms.llm import get_llm_for_agent
from core.utils.mlflow import setup_mlflow_tracing
from core.agents.column_canonicalization.signature import ColumnCanonicalizationSignature
from core.agents.column_canonicalization.canonical_columns import (
    get_canonical_columns_for_prompt,
    CANONICAL_COLUMNS
)
from core.agents.column_canonicalization.model import MappingResult


class ColumnCanonicalizationAgent:
    """Column Mapper using DSPy ReAct for intelligent column mapping"""
    
    def __init__(self, lm: Optional[dspy.LM] = None, enable_tracing: bool = True):
        """
        Initialize the Column Canonicalization Agent
        
        Args:
            lm: DSPy language model (if None, uses config for this agent)
            enable_tracing: Whether to enable MLflow tracing (default: True)
        """
        # Setup MLflow tracing if enabled
        if enable_tracing:
            setup_mlflow_tracing(experiment_name="column_canonicalization")
        
        if lm is None:
            lm = get_llm_for_agent("column_canonicalization")
        
        dspy.configure(lm=lm)
        
        # Use ChainOfThought for reasoning about column mappings
        # No tools needed - LLM can reason about column mappings directly
        self.predictor = dspy.ChainOfThought(ColumnCanonicalizationSignature)
    
    def extract_schema_from_dataframe(
        self, 
        df: pd.DataFrame, 
        sample_rows: int = 3
    ) -> List[dict]:
        """
        Extract client schema from dataframe
        
        Args:
            df: Input dataframe
            sample_rows: Number of sample rows to include
            
        Returns:
            List of dictionaries with column info
        """
        schema = []
        for col in df.columns:
            # Get non-null sample values
            sample_values = df[col].dropna().head(sample_rows).tolist()
            schema.append({
                "column_name": col,
                "sample_values": [str(v) for v in sample_values],
            })
        return schema
    
    def map_columns(
        self, 
        client_schema: List[dict],
        sample_rows: int = 3
    ) -> MappingResult:
        """
        Map client columns to canonical columns using ReAct agent
        
        Args:
            client_schema: List of dictionaries with column info (from extract_schema_from_dataframe or manual)
            sample_rows: Number of sample rows (used if client_schema needs to be enriched)
            
        Returns:
            MappingResult with mapping details and validation
        """
        # Get canonical columns
        canonical_columns = get_canonical_columns_for_prompt()
        
        # Prepare inputs for DSPy ReAct agent
        canonical_json = json.dumps(canonical_columns, indent=2)
        client_json = json.dumps(client_schema, indent=2)
        
        # Call predictor
        result = self.predictor(
            client_schema=client_json,
            canonical_columns=canonical_json,
        )
        
        # Parse JSON outputs
        mappings = json.loads(result.mappings.strip()) if result.mappings.strip() else {}
        unmapped_client = json.loads(result.unmapped_client_columns.strip()) if result.unmapped_client_columns.strip() else []
        unmapped_canonical = json.loads(result.unmapped_canonical_columns.strip()) if result.unmapped_canonical_columns.strip() else []
        important_unmapped = json.loads(result.important_unmapped_columns.strip()) if result.important_unmapped_columns.strip() else []
        
        # Compute unmapped if not provided by LLM
        client_columns = {col.get("column_name") for col in client_schema}
        canonical_names = {col["name"] for col in canonical_columns}
        mapped_client_columns = set(mappings.values())
        mapped_canonical_columns = set(mappings.keys())
        
        unmapped_client = unmapped_client or list(client_columns - mapped_client_columns)
        unmapped_canonical = unmapped_canonical or list(canonical_names - mapped_canonical_columns)
        
        # Validate mappings
        validation_errors = []
        validation_warnings = []
        
        # Check that mapped client columns exist
        for canonical_name, client_col in list(mappings.items()):  # Use list() to avoid modification during iteration
            if client_col not in client_columns:
                # Make currency optional - don't fail if missing (currency is not used in classification)
                if canonical_name == 'currency':
                    validation_warnings.append(f"Optional column 'currency' mapped but not found: '{client_col}'")
                    # Remove from mappings to avoid error
                    mappings.pop(canonical_name, None)
                else:
                    validation_errors.append(f"Mapped client column '{client_col}' does not exist")
            if canonical_name not in canonical_names:
                validation_errors.append(f"Canonical column '{canonical_name}' not found")
        
        # Check for critical and high relevance columns
        mapped_canonical = set(mappings.keys())
        critical_fields = ['supplier_name', 'gl_description', 'line_description']
        high_fields = ['gl_code', 'department']
        
        # Check which critical fields are missing
        missing_critical = [f for f in critical_fields if f not in mapped_canonical]
        missing_high = [f for f in high_fields if f not in mapped_canonical]
        
        # Warn if critical fields are missing (they might not exist in client data)
        if missing_critical:
            validation_warnings.append(
                f"Missing critical fields (if available in client data, should be mapped): {', '.join(missing_critical)}"
            )
        
        # Warn if high relevance fields are missing
        if missing_high:
            validation_warnings.append(
                f"Missing high relevance fields (if available in client data, should be mapped): {', '.join(missing_high)}"
            )
        
        # Ensure at least one critical field is mapped
        if not any(f in mapped_canonical for f in critical_fields):
            validation_warnings.append(
                "CRITICAL: At least one critical field (supplier_name, gl_description, or line_description) must be mapped for classification to work"
            )
        
        validation_passed = len(validation_errors) == 0
        
        return MappingResult(
            mappings=mappings,
            confidence=result.confidence.lower().strip() if result.confidence else "medium",
            unmapped_client_columns=unmapped_client,
            important_unmapped_columns=important_unmapped,
            unmapped_canonical_columns=unmapped_canonical,
            validation_passed=validation_passed,
            validation_errors=validation_errors + validation_warnings,
        )
    
    def apply_mapping(
        self, 
        df: pd.DataFrame, 
        mapping_result: MappingResult
    ) -> pd.DataFrame:
        """
        Apply the mapping to transform client data to canonical schema
        
        Args:
            df: Input dataframe with client data
            mapping_result: Result from map_columns()
            
        Returns:
            Transformed dataframe with canonical column names
        """
        if not mapping_result.validation_passed:
            raise ValueError(
                f"Cannot apply mapping with validation errors: {mapping_result.validation_errors}"
            )
        
        # Handle mappings where multiple canonical columns map to the same client column
        # We want to duplicate the client column for each canonical column that maps to it
        # This preserves all important fields (e.g., both gl_description and line_description)
        
        # Track which client columns are mapped to multiple canonical columns
        client_to_canonical = {}
        for canonical_col, client_col in mapping_result.mappings.items():
            if client_col not in client_to_canonical:
                client_to_canonical[client_col] = []
            client_to_canonical[client_col].append(canonical_col)
        
        # Build the canonical dataframe by copying client columns for each canonical column
        df_canonical = pd.DataFrame(index=df.index)
        
        for canonical_col, client_col in mapping_result.mappings.items():
            if client_col in df.columns:
                # Copy the client column data to the canonical column
                df_canonical[canonical_col] = df[client_col]
                
                # Log if this client column maps to multiple canonical columns
                if len(client_to_canonical[client_col]) > 1:
                    logger.debug(
                        f"Client column '{client_col}' mapped to multiple canonical columns: {client_to_canonical[client_col]}. "
                        f"Duplicating data for all mappings."
                    )
            else:
                logger.warning(f"Client column '{client_col}' not found in input data, skipping canonical column '{canonical_col}'")
        
        # Preserve important unmapped columns identified by the canonicalization agent
        # These are columns that don't map to canonical columns but contain useful information for classification
        for col in mapping_result.important_unmapped_columns:
            if col in df.columns and col not in df_canonical.columns:
                # Preserve this important unmapped column
                df_canonical[col] = df[col]
                logger.debug(f"Preserving important unmapped column: {col}")
        
        # Ensure canonical columns exist (even if empty) for consistency
        canonical_columns = list(mapping_result.mappings.keys())
        for canonical_col in canonical_columns:
            if canonical_col not in df_canonical.columns:
                # Canonical column doesn't exist - create empty column
                df_canonical[canonical_col] = None
        
        return df_canonical
