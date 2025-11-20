"""Spend Classification Engine using DSPy

Classifies spend transactions using supplier intelligence, transaction data, and taxonomy.
"""

import json
from pathlib import Path
from typing import Dict, Optional, Union

import dspy
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

    def load_taxonomy(self, taxonomy_path: Union[str, Path]) -> Dict:
        """Load taxonomy from YAML file"""
        path_str = str(taxonomy_path)
        with open(path_str, 'r') as f:
            return yaml.safe_load(f)

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

        # Use cached taxonomy if available, otherwise load and cache it
        taxonomy_source_str = str(taxonomy_source)
        if taxonomy_source_str not in self._taxonomy_cache:
            self._taxonomy_cache[taxonomy_source_str] = self.load_taxonomy(taxonomy_source)
        taxonomy_data = self._taxonomy_cache[taxonomy_source_str]

        # Prepare inputs
        supplier_json = json.dumps(supplier_profile, indent=2)

        # Handle string transaction format
        if isinstance(transaction_data, str):
            transaction_json = transaction_data  # Use as-is
        else:
            transaction_json = json.dumps(transaction_data, indent=2)

        # Format taxonomy as list of pipe-separated strings for LLM
        taxonomy_list = taxonomy_data['taxonomy']
        taxonomy_json = json.dumps(taxonomy_list, indent=2)

        override_rules = (
            "\n".join(taxonomy_data.get('override_rules', []))
            if taxonomy_data.get('override_rules')
            else "None"
        )

        # Call LLM
        result = self.classifier(
            supplier_profile=supplier_json,
            transaction_data=transaction_json,
            taxonomy_structure=taxonomy_json,
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
