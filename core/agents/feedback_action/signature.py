"""DSPy signature for feedback action planning."""

import dspy


class FeedbackActionSignature(dspy.Signature):
    """
    Analyze user feedback on a misclassified transaction and determine the appropriate action.

    DECISION CRITERIA FOR CHOOSING ACTION TYPE:

    1. Company Context (Action 1) - Choose when feedback indicates the COMPANY'S business has changed:
       - Trigger phrases: "we pivoted", "our business now", "company focus changed", "we are now", "our company"
       - Scope: Affects ALL future classifications for this company
       - Examples: "We pivoted to streaming", "Our company now focuses on cloud services"
       - Key indicator: First-person plural ("we", "our") referring to the company itself

    2. Taxonomy Description (Action 2) - Choose when feedback indicates a CATEGORY DEFINITION is unclear/wrong:
       - Trigger phrases: "this category includes", "should be defined as", "definition is wrong", "category should cover"
       - Scope: Affects how this category is understood across all transactions
       - Examples: "IaaS should include compute AND storage", "This category covers subscription software"
       - Key indicator: Third-person reference to a taxonomy category definition

    3. Supplier Rule (Action 3) - Choose when feedback indicates a SPECIFIC SUPPLIER always provides same service:
       - Trigger phrases: "this supplier always", "[supplier name] only provides", "all [supplier] transactions are"
       - Scope: Affects only transactions from this specific supplier
       - Examples: "AWS always provides cloud infrastructure", "This vendor only sells hardware"
       - Key indicator: References a specific supplier name with "always" or "only"

    4. Transaction Rule (Action 4) - Choose when feedback indicates a TRANSACTION ATTRIBUTE always maps to category:
       - Trigger phrases: "GL code X is always", "department Y always means", "this code always indicates"
       - Scope: Affects transactions matching the specific attribute value
       - Examples: "GL 1234 is always utilities", "IT dept is always IT services"
       - Key indicator: References a transaction field (GL code, department) with deterministic mapping

    DISAMBIGUATION RULES FOR AMBIGUOUS FEEDBACK:
    - "We focus on cloud services" → company_context (company's business focus)
    - "Cloud services category should include X" → taxonomy_description (category definition)
    - "This supplier provides cloud services" → supplier_rule (supplier-specific behavior)
    - "Cloud service purchases use GL code X" → transaction_rule (attribute-based rule)

    The agent must determine which action type applies (company_context, taxonomy_description,
    supplier_rule, or transaction_rule) and generate COMPLETE proposal details with all specifics
    needed to execute the action.
    """

    # Inputs
    original_classification: str = dspy.InputField(
        desc="The incorrect L1|L2|L3|L4 classification path"
    )
    corrected_classification: str = dspy.InputField(
        desc="The user's corrected L1|L2|L3|L4 classification path"
    )
    natural_language_feedback: str = dspy.InputField(
        desc="""User's explanation of WHY the classification was wrong. Examples by action type:
- Company context: 'we pivoted to streaming', 'our business now focuses on cloud services', 'company changed to SaaS model'
- Taxonomy description: 'this category should include cloud services', 'IaaS definition is too narrow', 'category covers subscription software'
- Supplier rule: 'this supplier always provides cloud infrastructure', 'AWS is exclusively IaaS', 'vendor only sells hardware'
- Transaction rule: 'GL code 1234 is always utilities', 'IT department expenses are IT services', 'this cost center is facilities'
"""
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
        desc="""Explain why this action type was chosen over the other 3 alternatives.
Must reference specific trigger words/phrases from the natural language feedback that led to this decision.
Address why the other action types (company_context, taxonomy_description, supplier_rule, transaction_rule) do NOT apply to this feedback."""
    )
    action_details: str = dspy.OutputField(
        desc="""JSON string with complete action-specific details:

For company_context:
{
  "field_name": "<choose from: industry|sector|business_focus|description>",
  "current_value": "<current value from company_context YAML>",
  "proposed_value": "<proposed new value based on feedback>"
}

Choose the most appropriate existing field:
- "industry": Broad industry classification (e.g., "Healthcare" → "Digital Health")
- "sector": Specific sector within industry (e.g., "Hospitals" → "Telehealth Services")
- "business_focus": Business focus areas/activities (e.g., "Broadcast TV" → "Streaming Media")
- "description": Company description narrative

Examples:
{"field_name": "industry", "current_value": "Healthcare", "proposed_value": "Digital Health Technology"}
{"field_name": "business_focus", "current_value": "Broadcast Television", "proposed_value": "Streaming and Digital Media"}

For taxonomy_description:
{
  "taxonomy_path": "it & telecom|cloud services|iaas",
  "current_description": "Infrastructure as a service...",
  "proposed_description": "Cloud infrastructure including compute, storage, and networking..."
}

For supplier_rule (Category A - single classification, supplier ALWAYS provides ONE specific service):
{
  "supplier_name": "AWS",
  "rule_category": "A",
  "classification_paths": ["it & telecom|cloud services|iaas"]
}

For supplier_rule (Category B - multiple possible classifications, supplier provides MULTIPLE types of services):
{
  "supplier_name": "Microsoft",
  "rule_category": "B",
  "classification_paths": ["it & telecom|cloud services|saas", "it & telecom|cloud services|iaas"]
}

IMPORTANT: Choose Category A when the supplier ALWAYS provides the same single type of service (one-to-one mapping).
Choose Category B when the supplier provides MULTIPLE types of services that require different classifications (one-to-many mapping).

For transaction_rule:
{
  "condition_field": "gl_code",
  "condition_value": "1234",
  "classification_path": "facilities|utilities|electricity",
  "rule_name": "GL 1234 -> Utilities"
}
"""
    )
