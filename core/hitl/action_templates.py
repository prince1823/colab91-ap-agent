"""Templates for formatting action proposals in HITL feedback."""


def format_company_context_proposal(action_details: dict) -> str:
    """Format company context update proposal."""
    field_name = action_details.get('field_name', 'unknown')
    current_value = action_details.get('current_value', '')
    proposed_value = action_details.get('proposed_value', '')
    
    return f"""Company Context Update
Field: {field_name}

Current:
{current_value}

Proposed:
{proposed_value}

You can edit the proposed text above before approving."""


def format_taxonomy_description_proposal(action_details: dict) -> str:
    """Format taxonomy description update proposal."""
    taxonomy_path = action_details.get('taxonomy_path', '')
    current_description = action_details.get('current_description', '')
    proposed_description = action_details.get('proposed_description', '')
    
    return f"""Taxonomy Description Update
Path: {taxonomy_path}

Current Description:
{current_description}

Proposed Description:
{proposed_description}

You can edit the proposed description above before approving."""


def format_supplier_rule_proposal(action_details: dict) -> str:
    """Format supplier rule proposal."""
    supplier_name = action_details.get('supplier_name', '')
    rule_category = action_details.get('rule_category', 'A')
    classification_paths = action_details.get('classification_paths', [])
    
    category_desc = "one-to-one mapping" if rule_category == "A" else "multiple possible classifications"
    paths_str = "\n".join(f"  - {path}" for path in classification_paths)
    
    return f"""Supplier Rule
Supplier: {supplier_name}
Rule Type: Category {rule_category} ({category_desc})
Classification:
{paths_str}

This rule will apply to all future transactions from this supplier."""


def format_transaction_rule_proposal(action_details: dict) -> str:
    """Format transaction rule proposal."""
    condition_field = action_details.get('condition_field', '')
    condition_value = action_details.get('condition_value', '')
    classification_path = action_details.get('classification_path', '')
    rule_name = action_details.get('rule_name', '')
    
    return f"""Transaction Rule
Rule: if {condition_field} = {condition_value}, always classify as {classification_path}

Rule Name: {rule_name}

You can edit the rule above before approving."""


ACTION_FORMATTERS = {
    "company_context": format_company_context_proposal,
    "taxonomy_description": format_taxonomy_description_proposal,
    "supplier_rule": format_supplier_rule_proposal,
    "transaction_rule": format_transaction_rule_proposal,
}


def format_action_proposal(action_type: str, action_details: dict, dataset_name: str) -> str:
    """
    Format action proposal text for user review.
    
    Args:
        action_type: Type of action
        action_details: Action-specific details
        dataset_name: Dataset name (unused but kept for compatibility)
        
    Returns:
        Formatted proposal text
    """
    formatter = ACTION_FORMATTERS.get(action_type)
    if formatter:
        return formatter(action_details)
    return f"Unknown action type: {action_type}"

