"""Research decision agent - determines when supplier research is needed."""

import logging
from typing import Dict, Optional, Any

import dspy

from core.config import get_config
from core.llms.llm import get_llm_for_agent
from core.utils.mlflow import setup_mlflow_tracing
from core.agents.research_decision.signature import ResearchDecisionSignature
from core.utils.transaction_utils import is_valid_value

logger = logging.getLogger(__name__)


class ResearchDecisionAgent:
    """Agent that decides when supplier research is needed using hybrid approach."""
    
    def __init__(
        self,
        lm: Optional[dspy.LM] = None,
        enable_tracing: bool = True,
    ):
        """
        Initialize Research Decision Agent.
        
        Args:
            lm: DSPy language model (if None, uses config for this agent)
            enable_tracing: Whether to enable MLflow tracing (default: True)
        """
        if enable_tracing:
            setup_mlflow_tracing(experiment_name="research_decision")
        
        if lm is None:
            lm = get_llm_for_agent("research_decision")
        
        dspy.configure(lm=lm)
        
        # Create DSPy predictor
        self.decision_agent = dspy.ChainOfThought(ResearchDecisionSignature)
    
    def _format_transaction_for_decision(self, transaction_data: Dict[str, Any]) -> str:
        """Format transaction data for research decision."""
        parts = []
        
        line_desc = transaction_data.get('line_description')
        gl_desc = transaction_data.get('gl_description')
        department = transaction_data.get('department')
        
        if is_valid_value(line_desc):
            parts.append(f"Line Description: {line_desc}")
        if is_valid_value(gl_desc):
            parts.append(f"GL Description: {gl_desc}")
        if is_valid_value(department):
            parts.append(f"Department: {department}")
        
        return "\n".join(parts) if parts else "No transaction details available"
    
    def should_research(
        self, 
        transaction_data: Dict[str, Any], 
        l1_result: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Determine if supplier research is needed using hybrid approach:
        1. Quick rule-based checks for obvious cases (fast path)
        2. LLM decision for ambiguous cases (semantic understanding)
        
        Args:
            transaction_data: Transaction data dictionary
            l1_result: Optional L1 classification result with 'confidence' and 'L1' keys
            
        Returns:
            True if research is needed, False otherwise
        """
        # Fast path: Obvious cases that always need research
        line_desc = transaction_data.get('line_description')
        gl_desc = transaction_data.get('gl_description')
        supplier_name = transaction_data.get('supplier_name', '')
        
        has_line_desc = line_desc and is_valid_value(line_desc)
        has_gl_desc = gl_desc and is_valid_value(gl_desc)
        
        # Always research if both are missing
        if not has_line_desc and not has_gl_desc:
            return True
        
        # Fast path: L1 confidence is low
        if l1_result and l1_result.get('confidence', '').lower() == 'low':
            return True
        
        # Fast path: L1 is "non-sourceable" with low confidence
        if l1_result:
            l1_category = l1_result.get('L1', '').lower()
            if l1_category in ['non-sourceable', 'non_sourceable', 'exempt', 'exceptions']:
                if l1_result.get('confidence', '').lower() != 'high':
                    return True
        
        # For ambiguous cases, use LLM to make semantic decision
        formatted_transaction = self._format_transaction_for_decision(transaction_data)
        l1_category = l1_result.get('L1', 'unknown') if l1_result else 'unknown'
        l1_confidence = l1_result.get('confidence', 'unknown') if l1_result else 'unknown'
        
        try:
            result = self.decision_agent(
                supplier_name=supplier_name or 'Unknown',
                transaction_data=formatted_transaction,
                l1_category=l1_category,
                l1_confidence=l1_confidence
            )
            should_research = result.should_research.lower().strip() == 'yes'
            logger.debug(f"Research decision for '{supplier_name}': {should_research} - {result.reasoning}")
            return should_research
        except Exception as e:
            logger.warning(f"Research decision LLM call failed for '{supplier_name}': {e}")
            # Fallback to conservative: research if transaction data is sparse
            return not (has_line_desc and has_gl_desc)

