"""Feedback analysis agent for determining downstream actions."""

import json
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any

import dspy

from core.config import get_config
from core.llms.llm import get_llm_for_agent
from core.agents.feedback_analysis.signature import FeedbackAnalysisSignature
from core.agents.feedback_analysis.model import FeedbackAction, ActionType


class FeedbackAnalyzer:
    """Analyzes user feedback and determines appropriate downstream actions."""
    
    def __init__(self, lm: Optional[dspy.LM] = None):
        """
        Initialize feedback analyzer.
        
        Args:
            lm: DSPy language model (if None, uses default configured LM)
        """
        if lm is None:
            lm = get_llm_for_agent("spend_classification")  # Reuse classification LLM
        
        dspy.configure(lm=lm)
        self.analyzer = dspy.ChainOfThought(FeedbackAnalysisSignature)
    
    def analyze_feedback(
        self,
        feedback_item: Dict[str, Any],
        transaction_data: Dict[str, Any],
        supplier_context: Dict[str, Any],
        taxonomy_path: Optional[Path] = None,
        taxonomy_data: Optional[Dict] = None,
    ) -> FeedbackAction:
        """
        Analyze feedback and determine downstream action.
        
        Args:
            feedback_item: User feedback with corrected classifications
            transaction_data: Original transaction data
            supplier_context: Supplier profile/context
            taxonomy_path: Path to taxonomy YAML file
            taxonomy_data: Pre-loaded taxonomy data (optional)
        
        Returns:
            FeedbackAction with recommended action
        """
        # Load taxonomy if needed
        if taxonomy_data is None and taxonomy_path:
            with open(taxonomy_path, 'r') as f:
                taxonomy_data = yaml.safe_load(f)
        
        # Format feedback item
        feedback_str = self._format_feedback_item(feedback_item)
        
        # Format transaction data
        transaction_str = json.dumps(transaction_data, indent=2)
        
        # Format supplier context
        supplier_str = json.dumps(supplier_context, indent=2)
        
        # Format taxonomy context
        taxonomy_str = self._format_taxonomy_context(taxonomy_data)
        
        # Get existing rules
        existing_rules = self._format_existing_rules(taxonomy_data)
        
        # Run analysis
        result = self.analyzer(
            feedback_item=feedback_str,
            transaction_data=transaction_str,
            supplier_context=supplier_str,
            taxonomy_context=taxonomy_str,
            existing_rules=existing_rules,
        )
        
        # Parse action metadata
        try:
            metadata = json.loads(result.action_metadata)
        except (json.JSONDecodeError, AttributeError):
            metadata = {}
        
        # Create feedback action
        action_type = ActionType(result.action_type.lower())
        
        # Generate appropriate proposed change text based on action type
        proposed_change = self._generate_proposed_change_text(
            action_type, result, metadata, feedback_item, transaction_data
        )
        
        return FeedbackAction(
            action_type=action_type,
            description=result.reasoning,
            proposed_change=proposed_change,
            metadata=metadata,
        )
    
    def _format_feedback_item(self, feedback_item: Dict[str, Any]) -> str:
        """Format feedback item for analysis."""
        parts = ["FEEDBACK ITEM:"]
        
        original = feedback_item.get("original_classification", {})
        corrected = {
            "L1": feedback_item.get("corrected_l1"),
            "L2": feedback_item.get("corrected_l2"),
            "L3": feedback_item.get("corrected_l3"),
            "L4": feedback_item.get("corrected_l4"),
            "L5": feedback_item.get("corrected_l5"),
        }
        corrected = {k: v for k, v in corrected.items() if v}
        
        if original:
            parts.append(f"Original Classification: {json.dumps(original, indent=2)}")
        parts.append(f"Corrected Classification: {json.dumps(corrected, indent=2)}")
        
        comment = feedback_item.get("comment")
        if comment:
            parts.append(f"User Comment: {comment}")
        
        return "\n".join(parts)
    
    def _format_taxonomy_context(self, taxonomy_data: Optional[Dict]) -> str:
        """Format relevant taxonomy context."""
        if not taxonomy_data:
            return "No taxonomy data available"
        
        parts = ["TAXONOMY CONTEXT:"]
        
        # Get corrected path from feedback if available
        # For now, show taxonomy structure
        taxonomy_paths = taxonomy_data.get("taxonomy", [])
        if taxonomy_paths:
            parts.append("Available taxonomy paths (first 20):")
            for path in taxonomy_paths[:20]:
                parts.append(f"  - {path}")
        
        return "\n".join(parts)
    
    def _format_existing_rules(self, taxonomy_data: Optional[Dict]) -> str:
        """Format existing override rules."""
        if not taxonomy_data:
            return "No existing rules"
        
        rules = taxonomy_data.get("override_rules", [])
        if not rules:
            return "No existing override rules"
        
        parts = ["EXISTING OVERRIDE RULES:"]
        for i, rule in enumerate(rules, 1):
            parts.append(f"{i}. {rule}")
        
        return "\n".join(parts)
    
    def _generate_proposed_change_text(
        self,
        action_type: ActionType,
        result: Any,
        metadata: Dict[str, Any],
        feedback_item: Dict[str, Any],
        transaction_data: Dict[str, Any],
    ) -> str:
        """Generate appropriate proposed change text based on action type."""
        
        corrected_path = "|".join([
            v for v in [
                feedback_item.get("corrected_l1"),
                feedback_item.get("corrected_l2"),
                feedback_item.get("corrected_l3"),
                feedback_item.get("corrected_l4"),
                feedback_item.get("corrected_l5"),
            ] if v
        ])
        
        if action_type == ActionType.TAXONOMY_UPDATE:
            # Action 1: Show taxonomy excerpt
            category_path = metadata.get("category_path", corrected_path)
            description = metadata.get("proposed_description", result.proposed_change_description)
            return f"Update taxonomy category: {category_path}\n\nProposed description update:\n{description}"
        
        elif action_type == ActionType.USER_CONTEXT_UPDATE:
            # Action 2: Show user context excerpt
            supplier_name = metadata.get("supplier_name", transaction_data.get("supplier_name", "Unknown"))
            context_update = metadata.get("context_update", result.proposed_change_description)
            return f"Update supplier context for: {supplier_name}\n\nProposed context update:\n{context_update}"
        
        elif action_type == ActionType.SUPPLIER_DB_UPDATE:
            # Action 3: Show supplier name and category mapping
            supplier_name = metadata.get("supplier_name", transaction_data.get("supplier_name", "Unknown"))
            category_type = metadata.get("category_type", "A")  # A = one-one, B = one-many
            
            if category_type == "A":
                return f"Add supplier mapping (Category A - One-to-One):\n\nSupplier: {supplier_name}\nAlways classify as: {corrected_path}"
            else:
                # Category B - show list
                alternatives = metadata.get("alternative_classifications", [])
                alt_text = "\n".join([f"  - {alt}" for alt in alternatives])
                return f"Add supplier mapping (Category B - One-to-Many):\n\nSupplier: {supplier_name}\nPotential classifications:\n  - {corrected_path}\n{alt_text}"
        
        elif action_type == ActionType.RULE_CREATION:
            # Action 4: Show rule in SQL-like format
            rule_condition = metadata.get("rule_condition", "N/A")
            gl_code = transaction_data.get("gl_code") or metadata.get("gl_code")
            
            if gl_code:
                return f"Just added new rule: if row has GL Account Code {gl_code}, always classify as {corrected_path}"
            else:
                condition_desc = metadata.get("condition_description", rule_condition)
                return f"New classification rule:\n\nIf: {condition_desc}\nThen: Always classify as {corrected_path}"
        
        # Fallback
        return result.proposed_change_text
