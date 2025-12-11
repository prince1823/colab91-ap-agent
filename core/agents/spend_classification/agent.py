"""Spend Classification Engine using DSPy

Classifies spend transactions using supplier intelligence, transaction data, and taxonomy.
"""

import json
import threading
from pathlib import Path
from typing import Dict, List, Optional, Union

import dspy
import pandas as pd
import yaml

from core.config import get_config
from core.llms.llm import get_llm_for_agent
from core.utils.mlflow import setup_mlflow_tracing
from core.agents.spend_classification.signature import SpendClassificationSignature
from core.agents.spend_classification.model import ClassificationResult
from core.agents.spend_classification.validation import ClassificationValidator


class SpendClassifier:
    """Spend Classification Engine using DSPy"""

    def __init__(
        self,
        taxonomy_path: Optional[str] = None,
        lm: Optional[dspy.LM] = None,
        enable_tracing: bool = True,
    ):
        """
        Initialize classifier

        Args:
            taxonomy_path: Optional path to taxonomy YAML file used as default
            lm: DSPy language model (if None, uses default configured LM)
            enable_tracing: Whether to enable MLflow tracing (default: True)
        """
        # Setup MLflow tracing if enabled
        if enable_tracing:
            setup_mlflow_tracing(experiment_name="spend_classification")

        if lm is None:
            lm = get_llm_for_agent("spend_classification")

        dspy.configure(lm=lm)

        self.taxonomy_path: Optional[str] = str(taxonomy_path) if taxonomy_path else None

        # Initialize validator for post-processing
        self.validator = (
            ClassificationValidator(self.taxonomy_path) if self.taxonomy_path else None
        )

        # Create DSPy predictor
        self.classifier = dspy.ChainOfThought(SpendClassificationSignature)
        
        # Cache for taxonomy data to avoid reloading for each transaction
        self._taxonomy_cache: Dict[str, Dict] = {}
        # Lock for thread-safe cache access
        self._cache_lock = threading.Lock()
        
        # Feedback examples for iterative improvement
        self._feedback_examples: List[Dict] = []
    
    def add_feedback_examples(self, examples: List[Dict]):
        """
        Add feedback examples for few-shot learning.
        
        Args:
            examples: List of feedback examples with transaction data and corrected classifications
        """
        self._feedback_examples.extend(examples)
    
    def clear_feedback_examples(self):
        """Clear all feedback examples."""
        self._feedback_examples = []

    def load_taxonomy(self, taxonomy_path: Union[str, Path]) -> Dict:
        """Load taxonomy from YAML file"""
        path_str = str(taxonomy_path)
        with open(path_str, 'r') as f:
            return yaml.safe_load(f)

    def _format_transaction_data(self, transaction_data: Dict) -> str:
        """Format transaction data to emphasize relevant fields"""
        def _is_valid_value(value) -> bool:
            """Check if value is valid and not empty"""
            if value is None:
                return False
            try:
                if pd.isna(value):
                    return False
            except (TypeError, ValueError):
                # Not a pandas type, check if it's a valid string
                pass
            return bool(str(value).strip())
        
        # Priority fields for classification
        priority_fields = {
            'line_description': 'Line Description',
            'gl_description': 'GL Description', 
            'department': 'Department',
            'po_number': 'PO Number',
            'invoice_number': 'Invoice Number',
        }
        
        # Secondary fields
        secondary_fields = {
            'cost_center': 'Cost Center',
            'amount': 'Amount',
            'currency': 'Currency',
        }
        
        formatted_parts = []
        
        # Add priority fields first
        formatted_parts.append("PRIMARY TRANSACTION DATA:")
        for key, label in priority_fields.items():
            value = transaction_data.get(key)
            if _is_valid_value(value):
                formatted_parts.append(f"  {label}: {value}")
        
        # Add secondary fields if available
        has_secondary = any(
            _is_valid_value(transaction_data.get(k))
            for k in secondary_fields.keys()
        )
        if has_secondary:
            formatted_parts.append("\nADDITIONAL CONTEXT:")
            for key, label in secondary_fields.items():
                value = transaction_data.get(key)
                if _is_valid_value(value):
                    formatted_parts.append(f"  {label}: {value}")
        
        return "\n".join(formatted_parts) if formatted_parts else "No transaction details available"

    def _assess_transaction_data_quality(self, transaction_data: Dict) -> str:
        """Assess quality of transaction data"""
        def _has_valid_field(field_name: str) -> bool:
            """Check if field exists and has valid content"""
            value = transaction_data.get(field_name)
            if value is None:
                return False
            try:
                if pd.isna(value):
                    return False
            except (TypeError, ValueError):
                pass
            return bool(str(value).strip())
        
        has_line_desc = _has_valid_field('line_description')
        has_gl_desc = _has_valid_field('gl_description')
        has_po = _has_valid_field('po_number')
        
        if has_line_desc or has_gl_desc or has_po:
            return "HIGH - Rich transaction data available. Prioritize transaction details over supplier industry."
        elif has_line_desc or has_gl_desc:
            return "MEDIUM - Some transaction data available. Use transaction details primarily, supplement with supplier context."
        else:
            return "LOW - Limited transaction data. Rely more on supplier industry/products, but still consider transaction context."

    def classify_transaction(
        self,
        supplier_profile: Dict,
        transaction_data: Union[Dict, str],
        taxonomy_yaml: Optional[Union[str, Path]] = None,
    ) -> ClassificationResult:
        """
        Classify a spend transaction

        Args:
            supplier_profile: Supplier information dict
            transaction_data: Transaction details dict or formatted string
            taxonomy_yaml: Path to taxonomy YAML file (overrides default if provided)

        Returns:
            ClassificationResult with L1-L5 classification
        """
        taxonomy_source = taxonomy_yaml or self.taxonomy_path
        if taxonomy_source is None:
            raise ValueError(
                "A taxonomy YAML path must be provided to classify a transaction."
            )

        # Use cached taxonomy if available, otherwise load and cache it (thread-safe)
        taxonomy_source_str = str(taxonomy_source)
        with self._cache_lock:
            if taxonomy_source_str not in self._taxonomy_cache:
                self._taxonomy_cache[taxonomy_source_str] = self.load_taxonomy(taxonomy_source)
            taxonomy_data = self._taxonomy_cache[taxonomy_source_str]

        # Prepare inputs
        supplier_json = json.dumps(supplier_profile, indent=2)

        # Handle string transaction format
        if isinstance(transaction_data, str):
            transaction_json = transaction_data  # Use as-is
            data_quality = "UNKNOWN - Transaction data provided as string"
        else:
            # Format transaction data with quality assessment
            data_quality = self._assess_transaction_data_quality(transaction_data)
            formatted_transaction = self._format_transaction_data(transaction_data)
            transaction_json = f"{data_quality}\n\n{formatted_transaction}"

        # Format taxonomy as list of pipe-separated strings for LLM
        taxonomy_list = taxonomy_data['taxonomy']
        taxonomy_json = json.dumps(taxonomy_list, indent=2)

        # Extract available levels from taxonomy
        available_levels = taxonomy_data.get('available_levels', ['L1', 'L2', 'L3', 'L4', 'L5'])
        available_levels_str = ', '.join(available_levels)

        override_rules = (
            "\n".join(taxonomy_data.get('override_rules', []))
            if taxonomy_data.get('override_rules')
            else "None"
        )

        # Prepare examples from feedback if available
        # DSPy can use examples through the predictor's configuration
        # We'll add examples to the prompt context by including them in the transaction_data
        feedback_context = ""
        if self._feedback_examples:
            feedback_context = "\n\nFEEDBACK EXAMPLES FROM PREVIOUS ITERATIONS:\n"
            for i, example in enumerate(self._feedback_examples[:3], 1):  # Limit to 3 examples
                if 'corrected' in example:
                    corrected = example['corrected']
                    example_path = '|'.join([
                        v for v in [
                            corrected.get('L1', ''),
                            corrected.get('L2', ''),
                            corrected.get('L3', ''),
                            corrected.get('L4', ''),
                            corrected.get('L5', ''),
                        ] if v
                    ])
                    feedback_context += f"\nExample {i}:\n"
                    feedback_context += f"Transaction: {json.dumps(example.get('transaction_data', {}), indent=2)}\n"
                    feedback_context += f"Correct Classification: {example_path}\n"
            feedback_context += "\nUse these examples to guide your classification.\n"

        # Add feedback context to transaction data
        enhanced_transaction_json = transaction_json + feedback_context

        # Call LLM
        result = self.classifier(
            supplier_profile=supplier_json,
            transaction_data=enhanced_transaction_json,
            taxonomy_structure=taxonomy_json,
            available_levels=available_levels_str,
            override_rules=override_rules,
        )

        # Parse levels
        l1 = result.L1
        l2 = result.L2 if result.L2.lower() != 'none' else None
        l3 = result.L3 if result.L3.lower() != 'none' else None
        l4 = result.L4 if result.L4.lower() != 'none' else None
        l5 = result.L5 if result.L5.lower() != 'none' else None

        reasoning = result.reasoning if hasattr(result, 'reasoning') else ""

        # Create result
        classification = ClassificationResult(
            L1=l1,
            L2=l2,
            L3=l3,
            L4=l4,
            L5=l5,
            override_rule_applied=(
                result.override_rule_applied
                if hasattr(result, 'override_rule_applied')
                and result.override_rule_applied.lower() != 'none'
                else None
            ),
            reasoning=reasoning,
        )

        return classification
