"""Feedback action planning agent."""

import json
from typing import Dict

import dspy

from core.agents.feedback_action.signature import FeedbackActionSignature


class FeedbackAction(dspy.Module):
    """
    Agent that analyzes user feedback and determines the appropriate action to take.

    Uses DSPy ChainOfThought to determine one of 4 action types and generate
    complete proposal details for user review.
    """

    def __init__(self):
        super().__init__()
        self.plan_action = dspy.ChainOfThought(FeedbackActionSignature)

    def forward(
        self,
        original_classification: str,
        corrected_classification: str,
        natural_language_feedback: str,
        transaction_data: Dict,
        taxonomy_structure: list,
        taxonomy_descriptions: Dict,
        company_context: Dict
    ) -> Dict:
        """
        Analyze feedback and determine action.

        Args:
            original_classification: Wrong L1|L2|L3|L4 path
            corrected_classification: User's correction
            natural_language_feedback: User's explanation
            transaction_data: Full transaction details
            taxonomy_structure: Available taxonomy paths
            taxonomy_descriptions: Current descriptions
            company_context: Current company context

        Returns:
            Dictionary with action_type, action_reasoning, and action_details
        """
        # Convert inputs to string format for DSPy
        transaction_data_str = json.dumps(transaction_data, indent=2)
        taxonomy_structure_str = json.dumps(taxonomy_structure, indent=2)
        taxonomy_descriptions_str = json.dumps(taxonomy_descriptions, indent=2)
        company_context_str = json.dumps(company_context, indent=2)

        # Call DSPy chain of thought
        result = self.plan_action(
            original_classification=original_classification,
            corrected_classification=corrected_classification,
            natural_language_feedback=natural_language_feedback,
            transaction_data=transaction_data_str,
            taxonomy_structure=taxonomy_structure_str,
            taxonomy_descriptions=taxonomy_descriptions_str,
            company_context=company_context_str
        )

        # Parse action_details JSON
        try:
            action_details = json.loads(result.action_details)
        except json.JSONDecodeError:
            # If LLM didn't return valid JSON, wrap the response
            action_details = {"raw_response": result.action_details}

        return {
            'action_type': result.action_type,
            'action_reasoning': result.action_reasoning,
            'action_details': action_details
        }
