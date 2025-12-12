"""DSPy signature for feedback action planning."""

import dspy


class FeedbackActionSignature(dspy.Signature):
    """
    Analyze user feedback on a misclassified transaction and determine the appropriate action.

    The agent determines which of 4 action types applies:
    - Action 1: company_context - User indicates company context changed (e.g., "we pivoted to streaming")
    - Action 2: taxonomy_description - User says taxonomy description is wrong (e.g., "this category includes X")
    - Action 3: supplier_rule - User says this supplier always does Y (create supplier rule)
    - Action 4: transaction_rule - User says this GL code/attribute always means Z (create transaction rule)

    The agent must generate COMPLETE proposal details with all specifics needed to execute the action.
    """

    # Inputs
    original_classification: str = dspy.InputField(
        desc="The incorrect L1|L2|L3|L4 classification path"
    )
    corrected_classification: str = dspy.InputField(
        desc="The user's corrected L1|L2|L3|L4 classification path"
    )
    natural_language_feedback: str = dspy.InputField(
        desc="User's explanation of WHY the classification was wrong (e.g., 'company focus changed to streaming', 'this supplier always provides cloud services')"
    )
    transaction_data: str = dspy.InputField(
        desc="JSON string of full transaction details (supplier, GL description, amount, department, etc.)"
    )
    taxonomy_structure: str = dspy.InputField(
        desc="Available taxonomy paths as list"
    )
    taxonomy_descriptions: str = dspy.InputField(
        desc="Current taxonomy_descriptions from YAML as JSON string"
    )
    company_context: str = dspy.InputField(
        desc="Current company_context from YAML as JSON string (all fields: industry, sector, business_focus, etc.)"
    )

    # Outputs
    action_type: str = dspy.OutputField(
        desc="One of: 'company_context', 'taxonomy_description', 'supplier_rule', 'transaction_rule'"
    )
    action_reasoning: str = dspy.OutputField(
        desc="Brief explanation of why this action type was chosen based on the natural language feedback"
    )
    action_details: str = dspy.OutputField(
        desc="""JSON string with complete action-specific details:

For company_context:
{
  "field_name": "business_focus",
  "current_value": "Broadcast Television",
  "proposed_value": "Streaming and Digital Media"
}

For taxonomy_description:
{
  "taxonomy_path": "it & telecom|cloud services|iaas",
  "current_description": "Infrastructure as a service...",
  "proposed_description": "Cloud infrastructure including compute, storage, and networking..."
}

For supplier_rule:
{
  "supplier_name": "AWS",
  "rule_category": "A",
  "classification_paths": ["it & telecom|cloud services|iaas"]
}

For transaction_rule:
{
  "condition_field": "gl_code",
  "condition_value": "1234",
  "classification_path": "facilities|utilities|electricity",
  "rule_name": "GL 1234 -> Utilities"
}
"""
    )
