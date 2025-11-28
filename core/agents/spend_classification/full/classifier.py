"""Spend Classification Engine using DSPy

Classifies spend transactions using supplier intelligence, transaction data, and taxonomy.
"""

import json
import logging
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Optional, Union

import dspy
import pandas as pd
import yaml

from core.config import get_config
from core.llms.llm import get_llm_for_agent
from core.utils.mlflow import setup_mlflow_tracing
from core.agents.spend_classification.full.signature import FullClassificationSignature
from core.agents.spend_classification.model import ClassificationResult
from core.agents.spend_classification.full.validation import ClassificationValidator
from core.agents.context_prioritization.model import PrioritizationDecision
from core.utils.taxonomy_filter import filter_taxonomy_by_l1, augment_taxonomy_with_other, is_catch_all_l1, parse_taxonomy_path
from core.utils.transaction_utils import format_transaction_data, is_valid_value

logger = logging.getLogger(__name__)


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
        self.classifier = dspy.ChainOfThought(FullClassificationSignature)
        
        # Cache for taxonomy data to avoid reloading for each transaction
        # Use OrderedDict for LRU eviction (max 10 taxonomies)
        self._taxonomy_cache: OrderedDict[str, Dict] = OrderedDict()
        self._max_cache_size = 10
        # Lock for thread-safe cache access
        self._cache_lock = threading.Lock()

    def load_taxonomy(self, taxonomy_path: Union[str, Path]) -> Dict:
        """Load taxonomy from YAML file"""
        path_str = str(taxonomy_path)
        with open(path_str, 'r') as f:
            return yaml.safe_load(f)

    def _format_transaction_data(self, transaction_data: Dict) -> str:
        """Format transaction data to emphasize relevant fields"""
        # Priority fields for classification
        # Note: The following fields are excluded as they don't help with categorization:
        # - department: Internal organizational code (indicates WHERE charged, not WHAT purchased)
        # - cost_center: Internal organizational code (similar to department)
        # - po_number: Transaction ID, not descriptive of what was purchased
        # - invoice_number: Transaction ID, not descriptive of what was purchased
        # - amount: Financial value doesn't indicate spend category
        # - currency: Currency code doesn't indicate spend category
        priority_fields = {
            'line_description': 'Line Description',
            'gl_description': 'GL Description',
        }
        
        # No secondary fields - only include fields that help identify what was purchased
        secondary_fields = {}
        
        return format_transaction_data(transaction_data, priority_fields, secondary_fields)

    def _assess_transaction_data_quality(self, transaction_data: Dict) -> str:
        """Assess quality of transaction data"""
        has_line_desc = is_valid_value(transaction_data.get('line_description'))
        has_gl_desc = is_valid_value(transaction_data.get('gl_description'))
        has_po = is_valid_value(transaction_data.get('po_number'))
        
        if has_line_desc or has_gl_desc or has_po:
            return "HIGH - Rich transaction data available. Prioritize transaction details over supplier industry."
        elif has_line_desc or has_gl_desc:
            return "MEDIUM - Some transaction data available. Use transaction details primarily, supplement with supplier context."
        else:
            return "LOW - Limited transaction data. Rely more on supplier industry/products, but still consider transaction context."

    def classify_transaction(
        self,
        l1_category: str,
        supplier_profile: Dict,
        transaction_data: Union[Dict, str],
        taxonomy_yaml: Optional[Union[str, Path]] = None,
        prioritization_decision: Optional[PrioritizationDecision] = None,
    ) -> ClassificationResult:
        """
        Classify a spend transaction (L2-L5) given L1 category from preliminary classifier

        Args:
            l1_category: L1 category from preliminary L1 classifier
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
                # Evict oldest entry if cache is full
                if len(self._taxonomy_cache) >= self._max_cache_size:
                    self._taxonomy_cache.popitem(last=False)
                taxonomy_data = self.load_taxonomy(taxonomy_source)
                self._taxonomy_cache[taxonomy_source_str] = taxonomy_data
            else:
                # Move to end (most recently used)
                taxonomy_data = self._taxonomy_cache.pop(taxonomy_source_str)
                self._taxonomy_cache[taxonomy_source_str] = taxonomy_data

        # Check if L1 is a catch-all category - if so, use full taxonomy for override capability
        l1_is_catch_all = is_catch_all_l1(l1_category)
        
        if l1_is_catch_all:
            # Use full taxonomy when catch-all L1 is detected (allows LLM to override to specific category)
            logger.debug(f"L1 '{l1_category}' is catch-all, using full taxonomy for override capability")
            taxonomy_to_augment = taxonomy_data
        else:
            # Filter taxonomy by L1 category for non-catch-all cases
            taxonomy_to_augment = filter_taxonomy_by_l1(taxonomy_data, l1_category)
        
        # Augment taxonomy with "Other" categories
        augmented_taxonomy = augment_taxonomy_with_other(taxonomy_to_augment)

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
        taxonomy_list = augmented_taxonomy['taxonomy']
        taxonomy_json = json.dumps(taxonomy_list, indent=2)

        # Extract available levels from taxonomy
        available_levels = augmented_taxonomy.get('available_levels', ['L1', 'L2', 'L3', 'L4', 'L5'])
        available_levels_str = ', '.join(available_levels)

        override_rules = (
            "\n".join(augmented_taxonomy.get('override_rules', []))
            if augmented_taxonomy.get('override_rules')
            else "None"
        )
        
        # Format prioritization decision fields
        if prioritization_decision:
            prioritization_strategy = prioritization_decision.prioritization_strategy
            supplier_context_strength = prioritization_decision.supplier_context_strength
            transaction_data_quality = prioritization_decision.transaction_data_quality
        else:
            prioritization_strategy = "n/a"
            supplier_context_strength = "none"
            transaction_data_quality = "unknown"

        # Call LLM with retry logic
        max_retries = 2
        result = None
        for attempt in range(max_retries + 1):
            try:
                result = self.classifier(
                    l1_category=l1_category,
                    supplier_profile=supplier_json,
                    transaction_data=transaction_json,
                    taxonomy_structure=taxonomy_json,
                    available_levels=available_levels_str,
                    override_rules=override_rules,
                    prioritization_strategy=prioritization_strategy,
                    supplier_context_strength=supplier_context_strength,
                    transaction_data_quality=transaction_data_quality,
                )
                
                # Validate result
                if not result or not hasattr(result, 'classification_path') or not result.classification_path:
                    if attempt < max_retries:
                        logger.warning(f"Full classifier returned invalid classification_path (attempt {attempt + 1}/{max_retries + 1}): {result.classification_path if hasattr(result, 'classification_path') else 'None'}. Retrying...")
                        continue
                    else:
                        logger.warning(f"Full classifier returned invalid classification_path after {max_retries + 1} attempts. Using L1 category as fallback.")
                        # Return result with L1 from input, other levels as None
                        return ClassificationResult(
                            L1=l1_category,
                            L2=None,
                            L3=None,
                            L4=None,
                            L5=None,
                            reasoning=f'Full classifier returned invalid result after retries, using L1 category: {l1_category}',
                        )
                
                break  # Success, exit retry loop
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"Error in full classification (attempt {attempt + 1}/{max_retries + 1}): {e}. Retrying...")
                    continue
                else:
                    logger.error(f"Error in full classification after {max_retries + 1} attempts: {e}", exc_info=True)
                    # Return fallback result
                    return ClassificationResult(
                        L1=l1_category,
                        L2=None,
                        L3=None,
                        L4=None,
                        L5=None,
                        reasoning=f'Full classification failed after retries: {str(e)}',
                    )
        
        # If we get here, result should be valid
        if not result:
            logger.error("Full classifier returned None after all retries")
            return ClassificationResult(
                L1=l1_category,
                L2=None,
                L3=None,
                L4=None,
                L5=None,
                reasoning='Full classifier returned None after retries',
            )

        # Parse classification_path from single output field
        classification_path = result.classification_path if hasattr(result, 'classification_path') else None
        if not classification_path or str(classification_path).strip().lower() in ['nan', 'none', 'null', '']:
            logger.warning(f"Full classifier returned invalid classification_path, using L1 category as fallback: {l1_category}")
            parsed_levels = {'L1': l1_category, 'L2': None, 'L3': None, 'L4': None, 'L5': None}
        else:
            # Parse the pipe-separated path into individual levels
            parsed_levels = parse_taxonomy_path(str(classification_path).strip())
        
        # Handle L1 override logic
        result_l1 = parsed_levels.get('L1')
        l1_is_catch_all = is_catch_all_l1(l1_category)
        
        if result_l1 and l1_is_catch_all:
            # L1 is a catch-all AND LLM suggests a specific category - allow override
            if result_l1.strip().lower() != l1_category.strip().lower():
                l1 = result_l1  # Use LLM's override
                logger.info(f"Full classifier overrode catch-all L1 '{l1_category}' → '{result_l1}' based on supplier profile")
            else:
                l1 = l1_category  # LLM agrees with catch-all, use it
        elif result_l1 and not l1_is_catch_all:
            # L1 is NOT a catch-all - always use the provided l1_category (respect L1 classifier's decision)
            if result_l1.strip().lower() != l1_category.strip().lower():
                logger.warning(f"Full classifier suggested different L1 '{result_l1}' but L1 '{l1_category}' is not catch-all. Using provided L1.")
            l1 = l1_category  # Always use L1 classifier's output for non-catch-all categories
            # Update parsed_levels to use provided L1
            parsed_levels['L1'] = l1_category
        else:
            # LLM didn't return L1 or returned invalid - use provided l1_category
            l1 = l1_category
            parsed_levels['L1'] = l1_category
            if not result_l1:
                logger.warning(f"Full classifier returned invalid L1 in path, using provided l1_category: '{l1_category}'")
        
        # Extract other levels from parsed path
        l2 = parsed_levels.get('L2')
        l3 = parsed_levels.get('L3')
        l4 = parsed_levels.get('L4')
        l5 = parsed_levels.get('L5')

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
                and result.override_rule_applied
                and str(result.override_rule_applied).strip().lower() not in ['nan', 'none', 'null', '']
                else None
            ),
            reasoning=reasoning,
        )

        return classification

