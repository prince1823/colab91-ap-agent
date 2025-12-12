"""DSPy signature for feedback analysis agent."""

import dspy


class FeedbackAnalysisSignature(dspy.Signature):
    """
    Analyze user feedback on classification corrections and determine appropriate downstream actions.
    
    Based on the feedback, decide which of these 4 actions is most appropriate:
    
    ACTION 1 (taxonomy_update): If the correction indicates the taxonomy description or category 
    structure needs updating. This would apply when the user's correction reveals that the taxonomy 
    category itself is poorly defined or missing important context.
    
    ACTION 2 (user_context_update): If the correction suggests the supplier/user context information 
    needs updating. This applies when supplier profile, industry, or business description needs refinement.
    
    ACTION 3 (supplier_db_update): If the feedback indicates a supplier-to-category mapping should 
    be added/updated in the supplier database. This is for one-to-one (Category A) or one-to-many 
    (Category B) supplier mappings.
    - Category A: Single supplier should always map to one specific classification
    - Category B: Supplier can map to multiple potential classifications (show list to user)
    
    ACTION 4 (rule_creation): If the feedback suggests a new rule should be created (e.g., 
    "if GL Account Code XXXX, always classify as L1|L2|L3|L4"). These are rule-based classifications 
    that apply to transactions matching specific criteria.
    
    Consider the user's comment/natural language feedback to understand intent.
    Multiple actions may be appropriate - select the PRIMARY action that would have the most impact.
    """
    
    feedback_item: str = dspy.InputField(
        desc="User feedback including original classification, corrected classification, and optional comment"
    )
    transaction_data: str = dspy.InputField(
        desc="Transaction data including supplier, GL code, descriptions, etc."
    )
    supplier_context: str = dspy.InputField(
        desc="Current supplier profile and context information"
    )
    taxonomy_context: str = dspy.InputField(
        desc="Relevant taxonomy structure and descriptions"
    )
    existing_rules: str = dspy.InputField(
        desc="Existing override rules to avoid duplication"
    )
    
    action_type: str = dspy.OutputField(
        desc="One of: taxonomy_update, user_context_update, supplier_db_update, rule_creation"
    )
    reasoning: str = dspy.OutputField(
        desc="Explanation of why this action was chosen"
    )
    proposed_change_description: str = dspy.OutputField(
        desc="Human-readable description of the proposed change"
    )
    proposed_change_text: str = dspy.OutputField(
        desc="Editable text for the proposed change (for user to review/edit)"
    )
    action_metadata: str = dspy.OutputField(
        desc="JSON string with additional metadata needed for action execution (supplier name, category path, rule conditions, etc.)"
    )
