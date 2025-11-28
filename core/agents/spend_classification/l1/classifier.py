"""L1 Preliminary Classification Engine using DSPy

Classifies transactions to L1 category only using transaction data (no supplier research).
"""

import json
import logging
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Optional, Union

import dspy
import pandas as pd

from core.config import get_config
from core.llms.llm import get_llm_for_agent
from core.utils.mlflow import setup_mlflow_tracing
from core.utils.taxonomy_filter import extract_l1_categories
from core.agents.spend_classification.l1.signature import L1ClassificationSignature
from core.agents.context_prioritization.model import PrioritizationDecision
from core.utils.transaction_utils import format_transaction_data, is_valid_value

logger = logging.getLogger(__name__)


class L1Classifier:
    """L1 Preliminary Classification Engine using DSPy"""

    def __init__(
        self,
        taxonomy_path: Optional[str] = None,
        lm: Optional[dspy.LM] = None,
        enable_tracing: bool = True,
    ):
        """
        Initialize L1 classifier

        Args:
            taxonomy_path: Optional path to taxonomy YAML file used as default
            lm: DSPy language model (if None, uses default configured LM)
            enable_tracing: Whether to enable MLflow tracing (default: True)
        """
        # Setup MLflow tracing if enabled
        if enable_tracing:
            setup_mlflow_tracing(experiment_name="l1_classification")

        if lm is None:
            lm = get_llm_for_agent("spend_classification")

        dspy.configure(lm=lm)

        self.taxonomy_path: Optional[str] = str(taxonomy_path) if taxonomy_path else None

        # Create DSPy predictor
        self.classifier = dspy.ChainOfThought(L1ClassificationSignature)
        
        # Cache for taxonomy data to avoid reloading
        # Use OrderedDict for LRU eviction (max 10 taxonomies)
        self._taxonomy_cache: OrderedDict[str, Dict] = OrderedDict()
        self._l1_cache: Dict[str, list] = {}
        self._max_cache_size = 10
        # Lock for thread-safe cache access
        self._cache_lock = threading.Lock()

    def load_taxonomy(self, taxonomy_path: Union[str, Path]) -> Dict:
        """Load taxonomy from YAML file"""
        import yaml
        path_str = str(taxonomy_path)
        with open(path_str, 'r') as f:
            return yaml.safe_load(f)

    def _format_transaction_data(self, transaction_data: Dict) -> str:
        """Format transaction data to emphasize relevant fields"""
        # Priority fields for L1 classification
        # Note: Department is excluded - it's an internal organizational code that doesn't indicate
        # what was purchased, only where it was charged. It's not useful for spend categorization.
        priority_fields = {
            'line_description': 'Line Description',
            'gl_description': 'GL Description',
        }
        
        # Format without section headers for L1 (simpler format)
        formatted_parts = []
        for key, label in priority_fields.items():
            value = transaction_data.get(key)
            if is_valid_value(value):
                value_str = str(value).strip().lower()
                # Skip placeholder values like "[blank]", "[no data]", etc.
                is_placeholder = value_str in ['[blank]', '[no data]', 'blank', 'n/a', 'na', 'none', '']
                if not is_placeholder:
                    formatted_parts.append(f"{label}: {value}")
        
        # Check if we have meaningful line_description (the PRIMARY indicator)
        # Line description is the most important field for classification
        # Note: The LLM will determine if line descriptions are accounting references vs. purchase descriptions
        # based on semantic understanding, not hardcoded patterns
        line_desc = transaction_data.get('line_description')
        has_meaningful_line_desc = False
        if line_desc and is_valid_value(line_desc):
            line_desc_str = str(line_desc).strip().lower()
            # Check if it's meaningful (not just a date, not too short, not generic, not placeholder)
            # Filter out placeholder values like "[blank]", "[no data]", etc.
            is_placeholder = line_desc_str in ['[blank]', '[no data]', 'blank', 'n/a', 'na', 'none', '']
            if not is_placeholder and len(line_desc_str) > 3 and not self._is_likely_date(line_desc_str):
                # Also check if it's generic - if generic, treat as not meaningful so supplier name hint is included
                if not self._is_generic_description(line_desc_str):
                    has_meaningful_line_desc = True
        
        # If line_description is missing or not meaningful, include supplier name as a hint
        # (L1 classifier can use this when transaction data is insufficient)
        if not has_meaningful_line_desc:
            supplier_name = transaction_data.get('supplier_name')
            if supplier_name and is_valid_value(supplier_name):
                formatted_parts.append(f"Supplier Name (hint only): {supplier_name}")
        
        return "\n".join(formatted_parts) if formatted_parts else "No transaction details available"
    
    def _is_likely_date(self, value_str: str) -> bool:
        """Check if value looks like a date (common patterns)"""
        import re
        date_patterns = [
            r'^\d{4}-\d{2}-\d{2}$',  # 2022-02-17
            r'^\d{2}/\d{2}/\d{4}$',  # 02/17/2022
            r'^\d{2}-\d{2}-\d{4}$',  # 02-17-2022
            r'^\d{4}/\d{2}/\d{2}$',  # 2022/02/17
        ]
        return any(re.match(pattern, value_str.strip()) for pattern in date_patterns)
    
    def _is_generic_description(self, value_str: str) -> bool:
        """Check if description is too generic to be useful for classification"""
        generic_patterns = [
            'goods and services',
            'other professional services',
            'professional services',
            'services',
            'miscellaneous',
            'other',
            'general',
            'various',
            'general services',
            'other services',
            'misc',
            'miscellaneous services',
        ]
        value_lower = value_str.lower().strip()
        # Check if the description is just a generic term or contains generic patterns
        return any(pattern in value_lower for pattern in generic_patterns) and len(value_lower.split()) <= 4
    

    def classify_l1(
        self,
        transaction_data: Union[Dict, str],
        taxonomy_yaml: Optional[Union[str, Path]] = None,
        supplier_profile: Optional[Dict] = None,
        prioritization_decision: Optional[PrioritizationDecision] = None,
    ) -> Dict[str, str]:
        """
        Classify transaction to L1 category only

        Args:
            transaction_data: Transaction details dict or formatted string
            taxonomy_yaml: Path to taxonomy YAML file (overrides default if provided)
            supplier_profile: Optional supplier profile dict (industry, products_services, service_type, etc.)
                             Use this when transaction data is sparse to improve classification

        Returns:
            Dictionary with 'L1', 'confidence', and 'reasoning'
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
                    evicted_key = next(iter(self._taxonomy_cache))
                    self._taxonomy_cache.pop(evicted_key)
                    self._l1_cache.pop(evicted_key, None)  # Remove corresponding L1 cache
                taxonomy_data = self.load_taxonomy(taxonomy_source)
                self._taxonomy_cache[taxonomy_source_str] = taxonomy_data
            else:
                # Move to end (most recently used)
                taxonomy_data = self._taxonomy_cache.pop(taxonomy_source_str)
                self._taxonomy_cache[taxonomy_source_str] = taxonomy_data
            
            # Cache L1 categories
            if taxonomy_source_str not in self._l1_cache:
                self._l1_cache[taxonomy_source_str] = extract_l1_categories(taxonomy_data)
            l1_categories = self._l1_cache[taxonomy_source_str]

        # Prepare inputs
        if isinstance(transaction_data, str):
            transaction_json = transaction_data
        else:
            transaction_json = self._format_transaction_data(transaction_data)

        # Format supplier profile if provided
        supplier_profile_json = ""
        if supplier_profile:
            # Extract key fields that help with L1 classification
            profile_fields = {
                'industry': supplier_profile.get('industry', ''),
                'products_services': supplier_profile.get('products_services', ''),
                'service_type': supplier_profile.get('service_type', ''),
                'description': supplier_profile.get('description', ''),
            }
            # Only include non-empty fields
            profile_fields = {k: v for k, v in profile_fields.items() if v and str(v).strip() and str(v).lower() not in ['unknown', 'n/a', 'none']}
            if profile_fields:
                supplier_profile_json = json.dumps(profile_fields, indent=2)

        # Format L1 categories as JSON list
        l1_categories_json = json.dumps(l1_categories, indent=2)
        
        # Format prioritization decision fields
        if prioritization_decision:
            prioritization_strategy = prioritization_decision.prioritization_strategy
            supplier_context_strength = prioritization_decision.supplier_context_strength
            transaction_data_quality = prioritization_decision.transaction_data_quality
        else:
            prioritization_strategy = "n/a"
            supplier_context_strength = "none"
            transaction_data_quality = "unknown"

        # Call LLM with error handling and retry logic
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                result = self.classifier(
                    transaction_data=transaction_json,
                    l1_categories=l1_categories_json,
                    supplier_profile=supplier_profile_json if supplier_profile_json else "No supplier profile available",
                    prioritization_strategy=prioritization_strategy,
                    supplier_context_strength=supplier_context_strength,
                    transaction_data_quality=transaction_data_quality,
                )
                
                # Validate result
                if not result or not hasattr(result, 'L1') or not result.L1 or str(result.L1).strip().lower() in ['nan', 'none', 'null', '']:
                    if attempt < max_retries:
                        logger.warning(f"L1 classifier returned invalid result (attempt {attempt + 1}/{max_retries + 1}): {result}. Retrying...")
                        continue
                    else:
                        logger.warning(f"L1 classifier returned invalid result after {max_retries + 1} attempts: {result}")
                        # Return default low-confidence classification
                        return {
                            'L1': l1_categories[0] if l1_categories else 'non-clinical',
                            'confidence': 'low',
                            'reasoning': 'L1 classifier returned invalid result after retries, using fallback',
                        }
                
                # Validate L1 is in the available categories
                l1_value = str(result.L1).strip()
                if l1_categories and l1_value.lower() not in [cat.lower() for cat in l1_categories]:
                    if attempt < max_retries:
                        logger.warning(f"L1 classifier returned category not in taxonomy (attempt {attempt + 1}/{max_retries + 1}): {l1_value}. Retrying...")
                        continue
                    else:
                        logger.warning(f"L1 classifier returned invalid category after {max_retries + 1} attempts: {l1_value}. Using fallback.")
                        return {
                            'L1': l1_categories[0] if l1_categories else 'non-clinical',
                            'confidence': 'low',
                            'reasoning': f'L1 category "{l1_value}" not in taxonomy, using fallback',
                        }
                
                return {
                    'L1': l1_value,
                    'confidence': result.confidence if hasattr(result, 'confidence') else 'low',
                    'reasoning': result.reasoning if hasattr(result, 'reasoning') else "",
                }
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"Error in L1 classification (attempt {attempt + 1}/{max_retries + 1}): {e}. Retrying...")
                    continue
                else:
                    logger.error(f"Error in L1 classification after {max_retries + 1} attempts: {e}", exc_info=True)
                    # Return default low-confidence classification on error
                    return {
                        'L1': l1_categories[0] if l1_categories else 'non-clinical',
                        'confidence': 'low',
                        'reasoning': f'L1 classification failed after retries: {str(e)}',
                    }

