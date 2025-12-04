"""Context prioritization agent - determines research needs and prioritization strategy."""

import json
import logging
import threading
from pathlib import Path
from typing import Dict, Optional, Any, Union

import dspy
import yaml

from core.config import get_config
from core.llms.llm import get_llm_for_agent
from core.utils.mlflow import setup_mlflow_tracing
from core.agents.context_prioritization.signature import ContextPrioritizationSignature
from core.agents.context_prioritization.model import PrioritizationDecision
from core.utils.transaction_utils import is_valid_value
from core.agents.taxonomy_rag import TaxonomyRetriever

logger = logging.getLogger(__name__)


class ContextPrioritizationAgent:
    """Agent that assesses context and makes research/prioritization decisions."""
    
    def __init__(
        self,
        taxonomy_path: Optional[str] = None,
        lm: Optional[dspy.LM] = None,
        enable_tracing: bool = True,
    ):
        """
        Initialize Context Prioritization Agent.
        
        Args:
            taxonomy_path: Optional path to taxonomy YAML file (for similarity-based decisions)
            lm: DSPy language model (if None, uses config for this agent)
            enable_tracing: Whether to enable MLflow tracing (default: True)
        """
        if enable_tracing:
            setup_mlflow_tracing(experiment_name="context_prioritization")
        
        if lm is None:
            lm = get_llm_for_agent("context_prioritization")
        
        dspy.configure(lm=lm)
        
        # Create DSPy predictor
        self.decision_agent = dspy.ChainOfThought(ContextPrioritizationSignature)
        
        # Taxonomy RAG for similarity-based decisions
        self.taxonomy_path = str(taxonomy_path) if taxonomy_path else None
        self._taxonomy_cache: Dict[str, Dict] = {}
        self._cache_lock = threading.Lock()
        self._taxonomy_retriever = TaxonomyRetriever()
    
    def _format_transaction_data(self, transaction_data: Dict[str, Any]) -> str:
        """Format transaction data for assessment - present all data neutrally.
        
        No hardcoded priorities - let LLM assess context and decide what matters.
        Format matches Spend Classification Agent for consistency.
        """
        parts = []
        
        # Organize fields by type (same structure as Spend Classification Agent)
        structured_fields = []
        description_fields = []
        reference_fields = []
        other_fields = []
        
        # Structured/contextual fields
        if is_valid_value(transaction_data.get('department')):
            structured_fields.append(('Department', transaction_data['department']))
        
        if is_valid_value(transaction_data.get('gl_code')):
            structured_fields.append(('GL Code', transaction_data['gl_code']))
        
        if is_valid_value(transaction_data.get('cost_center')):
            structured_fields.append(('Cost Center', transaction_data['cost_center']))
        
        if is_valid_value(transaction_data.get('amount')):
            try:
                amount_val = float(str(transaction_data['amount']).replace(',', ''))
                amount_str = f"${amount_val:,.2f}" if amount_val >= 1 else f"${amount_val:.2f}"
                structured_fields.append(('Amount', amount_str))
            except (ValueError, TypeError):
                structured_fields.append(('Amount', transaction_data['amount']))
        
        # Reference/identifier fields
        if is_valid_value(transaction_data.get('po_number')):
            reference_fields.append(('PO Number', transaction_data['po_number']))
        
        if is_valid_value(transaction_data.get('invoice_number')):
            reference_fields.append(('Invoice Number', transaction_data['invoice_number']))
        
        if is_valid_value(transaction_data.get('invoice_date')):
            reference_fields.append(('Invoice Date', transaction_data['invoice_date']))
        
        # Description fields (present raw - LLM identifies patterns)
        if is_valid_value(transaction_data.get('line_description')):
            description_fields.append(('Line Description', transaction_data['line_description']))
        
        if is_valid_value(transaction_data.get('gl_description')):
            description_fields.append(('GL Description', transaction_data['gl_description']))
        
        # Other fields
        excluded_fields = {'supplier_name', 'L1', 'L2', 'L3', 'L4', 'L5', 'classification_path', 
                          'pipeline_output', 'expected_output', 'error', 'reasoning',
                          'line_description', 'gl_description', 'department', 'gl_code', 
                          'invoice_number', 'po_number', 'invoice_date', 'amount', 'cost_center',
                          'currency', 'supplier_address'}
        for key, value in sorted(transaction_data.items()):
            if key not in excluded_fields and is_valid_value(value):
                other_fields.append((key.replace('_', ' ').title(), value))
        
        # Format sections
        if structured_fields:
            parts.append("Transaction Context:")
            for label, value in structured_fields:
                parts.append(f"  {label}: {value}")
        
        if description_fields:
            if parts:
                parts.append("")
            parts.append("Descriptions:")
            for label, value in description_fields:
                display_value = str(value)
                if len(display_value) > 200:
                    display_value = display_value[:197] + "..."
                parts.append(f"  {label}: {display_value}")
        
        if reference_fields:
            if parts:
                parts.append("")
            parts.append("References:")
            for label, value in reference_fields:
                parts.append(f"  {label}: {value}")
        
        if other_fields:
            if parts:
                parts.append("")
            parts.append("Additional Information:")
            for label, value in other_fields:
                display_value = str(value)
                if len(display_value) > 150:
                    display_value = display_value[:147] + "..."
                parts.append(f"  {label}: {display_value}")
        
        return "\n".join(parts) if parts else "No transaction details available"
    
    def _format_supplier_profile(self, supplier_profile: Optional[Dict[str, Any]]) -> str:
        """Format supplier profile for assessment."""
        if not supplier_profile:
            return "None"
        
        # Extract key fields that indicate context strength
        profile_fields = {
            'industry': supplier_profile.get('industry', ''),
            'products_services': supplier_profile.get('products_services', ''),
            'service_type': supplier_profile.get('service_type', ''),
            'description': supplier_profile.get('description', ''),
            'naics_code': supplier_profile.get('naics_code', ''),
            'naics_description': supplier_profile.get('naics_description', ''),
            'sic_code': supplier_profile.get('sic_code', ''),
        }
        
        # Only include non-empty, meaningful fields
        profile_fields = {
            k: v for k, v in profile_fields.items() 
            if v and str(v).strip() and str(v).lower() not in ['unknown', 'n/a', 'none', '']
        }
        
        if profile_fields:
            return json.dumps(profile_fields, indent=2)
        return "None"
    
    def _detect_accounting_reference(self, transaction_data: Dict[str, Any]) -> bool:
        """
        Detect if transaction data contains accounting references.
        
        Accounting references describe WHO (entity) or HOW (processing), not WHAT (purchase).
        """
        line_desc = transaction_data.get('line_description')
        if not line_desc or not is_valid_value(line_desc):
            return False
        
        line_desc_str = str(line_desc).strip().lower()
        
        # Patterns that indicate accounting references
        accounting_patterns = [
            'operational journal:',
            'journal entry:',
            'journal:',
            'supplier invoice:',
            'invoice:',
            'journal entry',
        ]
        
        # Check if line description starts with accounting pattern
        if any(line_desc_str.startswith(pattern) for pattern in accounting_patterns):
            return True
        
        # Check for entity names followed by dates (common in journal entries)
        # Pattern: Entity name followed by date pattern (MM/DD/YYYY, YYYY-MM-DD, etc.)
        import re
        date_patterns = [
            r'\d{2}/\d{2}/\d{4}',  # MM/DD/YYYY
            r'\d{4}-\d{2}-\d{2}',   # YYYY-MM-DD
            r'\d{2}-\d{2}-\d{4}',   # MM-DD-YYYY
        ]
        
        # If line contains entity-like text (capitalized words) followed by date, likely accounting reference
        if any(re.search(pattern, line_desc_str) for pattern in date_patterns):
            # Check if there are capitalized words before the date (entity name)
            words_before_date = line_desc_str.split()
            if len(words_before_date) > 2:  # Likely has entity name
                return True
        
        return False
    
    def load_taxonomy(self, taxonomy_path: Union[str, Path]) -> Dict:
        """Load taxonomy from YAML with caching."""
        path_str = str(taxonomy_path)
        with self._cache_lock:
            if path_str not in self._taxonomy_cache:
                with open(path_str, 'r') as f:
                    self._taxonomy_cache[path_str] = yaml.safe_load(f)
            return self._taxonomy_cache[path_str]
    
    def _get_taxonomy_similarity_score(
        self,
        transaction_data: Dict[str, Any],
        supplier_profile: Optional[Dict[str, Any]] = None
    ) -> Optional[float]:
        """
        Get taxonomy similarity confidence score using RAG.
        
        Returns:
            Float 0-1 (higher = better match) or None if taxonomy not available
        """
        taxonomy_path = self.taxonomy_path
        if not taxonomy_path:
            return None
        
        try:
            taxonomy_data = self.load_taxonomy(taxonomy_path)
            taxonomy_list = taxonomy_data.get('taxonomy', [])
            descriptions = taxonomy_data.get('taxonomy_descriptions', {})  # Extract descriptions
            
            if not taxonomy_list:
                return None
            
            # Get confidence score from RAG
            confidence = self._taxonomy_retriever.get_confidence_score(
                transaction_data=transaction_data,
                supplier_profile=supplier_profile,
                taxonomy_list=taxonomy_list,
                top_n=3,
                descriptions=descriptions
            )
            
            return confidence
        
        except Exception as e:
            logger.warning(f"Failed to get taxonomy similarity score: {e}")
            return None
    
    def assess_context(
        self,
        transaction_data: Dict[str, Any],
        supplier_name: Optional[str] = None,
        supplier_profile: Optional[Dict[str, Any]] = None,
    ) -> PrioritizationDecision:
        """
        Assess transaction data quality and supplier context strength, make research and prioritization decisions.
        
        Args:
            transaction_data: Transaction data dictionary
            supplier_name: Optional supplier name
            supplier_profile: Optional supplier profile dict
            
        Returns:
            PrioritizationDecision with assessments and decisions
        """
        # Get taxonomy similarity score if taxonomy is available
        similarity_score = self._get_taxonomy_similarity_score(transaction_data, supplier_profile)
        
        # Fast path: Quick rule-based checks for obvious cases
        line_desc = transaction_data.get('line_description')
        gl_desc = transaction_data.get('gl_description')
        
        has_line_desc = line_desc and is_valid_value(line_desc)
        has_gl_desc = gl_desc and is_valid_value(gl_desc)
        
        # Use similarity score to inform research decision
        # Low similarity (< 0.3) suggests transaction doesn't match taxonomy well -> research needed
        # High similarity (> 0.7) suggests clear match -> research may not be needed
        similarity_should_research = None
        similarity_reasoning = ""
        
        if similarity_score is not None:
            if similarity_score < 0.3:
                similarity_should_research = True
                similarity_reasoning = f"Low taxonomy similarity ({similarity_score:.2f}) - transaction doesn't match taxonomy well"
            elif similarity_score > 0.7:
                similarity_should_research = False
                similarity_reasoning = f"High taxonomy similarity ({similarity_score:.2f}) - clear taxonomy match"
            # For medium scores (0.3-0.7), let other signals decide
        
        # Fast path: Always research if both are missing and no supplier profile
        if not supplier_profile and not has_line_desc and not has_gl_desc:
            reasoning = "Transaction data is completely missing, research needed"
            if similarity_reasoning:
                reasoning += f". {similarity_reasoning}"
            return PrioritizationDecision(
                should_research=True,
                prioritization_strategy="n/a",
                supplier_context_strength="none",
                transaction_data_quality="sparse",
                reasoning=reasoning
            )
        
        # For other cases, use LLM to make semantic decision
        formatted_transaction = self._format_transaction_data(transaction_data)
        supplier_name_str = supplier_name or 'None'
        supplier_profile_str = self._format_supplier_profile(supplier_profile)
        
        # Add similarity score info to transaction data if available
        if similarity_score is not None:
            formatted_transaction += f"\n\nTaxonomy Similarity Score: {similarity_score:.2f} (0-1 scale, higher = better match)"
        
        try:
            result = self.decision_agent(
                transaction_data=formatted_transaction,
                supplier_name=supplier_name_str,
                supplier_profile=supplier_profile_str,
            )
            
            should_research = result.should_research.lower().strip() == 'yes' if result.should_research.lower().strip() != 'n/a' else False
            
            # Override with similarity-based decision if similarity score strongly suggests it
            if similarity_should_research is not None:
                # Use similarity score as a strong signal, but combine with LLM decision
                if similarity_score < 0.3:
                    # Low similarity: strongly suggest research
                    should_research = True
                elif similarity_score > 0.7 and not supplier_profile:
                    # High similarity without supplier profile: research less critical
                    should_research = False
            
            reasoning = result.reasoning.strip()
            if similarity_reasoning:
                reasoning += f" {similarity_reasoning}"
            
            return PrioritizationDecision(
                should_research=should_research,
                prioritization_strategy=result.prioritization_strategy.strip(),
                supplier_context_strength=result.supplier_context_strength.strip(),
                transaction_data_quality=result.transaction_data_quality.strip(),
                reasoning=reasoning
            )
        except Exception as e:
            logger.warning(f"Context prioritization LLM call failed: {e}")
            # Fallback: Simple defaults without hardcoded pattern detection
            # Let LLM handle pattern detection - just use basic heuristics for fallback
            transaction_quality = "sparse" if not (has_line_desc or has_gl_desc) else "rich"
            
            # Simple fallback prioritization (no hardcoded patterns)
            if supplier_profile:
                priority_strategy = "balanced"  # Default to balanced when both available
            else:
                priority_strategy = "transaction_primary"  # Use transaction if no supplier profile
            
            # Use similarity score for fallback decision if available
            should_research_fallback = not (has_line_desc or has_gl_desc) if not supplier_profile else False
            if similarity_should_research is not None:
                # Similarity score is a strong signal for fallback
                should_research_fallback = similarity_should_research
            
            reasoning_fallback = f"Fallback decision after LLM error: {str(e)}"
            if similarity_reasoning:
                reasoning_fallback += f". {similarity_reasoning}"
            
            return PrioritizationDecision(
                should_research=should_research_fallback,
                prioritization_strategy=priority_strategy,
                supplier_context_strength="strong" if supplier_profile else "none",
                transaction_data_quality=transaction_quality,
                reasoning=reasoning_fallback
            )

