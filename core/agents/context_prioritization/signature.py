"""DSPy signature for context prioritization agent."""

import dspy


class ContextPrioritizationSignature(dspy.Signature):
    """
    Assess transaction data quality and supplier context strength to make two decisions:
    1. Research Decision: Should we research the supplier? (when supplier_profile is not available)
    2. Prioritization Decision: How to weight supplier context vs transaction data? (when both are available)
    
    ASSESSMENT FRAMEWORK:
    
    1. TRANSACTION DATA QUALITY ASSESSMENT:
       - Detect accounting references: journal entries, invoice numbers, entity names followed by dates
       - Detect generic GL terms: "accounts payable", "t&e payable", "accrued invoices"
       - Assess specificity: Are descriptions specific (e.g., "Surgical gloves") or generic (e.g., "services")?
       - Classify as: "rich" (specific, descriptive), "sparse" (missing/empty), "generic" (vague terms), or "accounting_reference" (journal entries, invoice numbers)
    
    2. SUPPLIER CONTEXT STRENGTH ASSESSMENT (if supplier_profile available):
       - Analyze supplier name: Domain-specific names (e.g., "medical supplies", "telecom") are strong signals
       - Analyze supplier profile: Industry, products_services, service_type, NAICS/SIC codes
       - Classify as: "strong" (specific industry/products), "medium" (some context), "weak" (generic), or "none" (no profile)
    
    3. RESEARCH DECISION (when supplier_profile is None):
       - If transaction_data_quality is "sparse"/"generic"/"accounting_reference" → should_research="yes"
       - If transaction_data_quality is "rich" AND supplier_name is generic → should_research="no"
       - If transaction_data_quality is "rich" AND supplier_name is domain-specific → assess if research would help
       - Use semantic understanding for ambiguous cases
    
    4. PRIORITIZATION DECISION (when supplier_profile is available):
       - If supplier_context_strength is "strong" AND transaction_data_quality is "sparse"/"generic"/"accounting_reference" → "supplier_primary"
       - If supplier_context_strength is "strong" AND transaction_data conflicts with supplier → "supplier_primary" (supplier more reliable)
       - If transaction_data_quality is "rich" AND supplier_context_strength is "weak" → "transaction_primary"
       - If both are strong and align → "balanced"
       - If transaction_data is "accounting_reference" → "supplier_only" (ignore transaction data)
       - Use semantic understanding for nuanced decisions
    
    PRINCIPLES:
    - Accounting references describe WHO (entity) or HOW (processing), not WHAT (purchase) - treat as low quality
    - Generic GL terms are accounting codes, not spend categories - treat as low quality
    - Supplier names/profile are strong signals when transaction data is sparse
    - Transaction data is strong signal when it's specific and descriptive
    - Conflicts between supplier and transaction data: supplier usually more reliable for domain-specific suppliers
    """
    
    transaction_data: str = dspy.InputField(
        desc="Transaction details (line description, GL description)"
    )
    supplier_name: str = dspy.InputField(
        desc="Supplier name (if available, 'None' if not available)"
    )
    supplier_profile: str = dspy.InputField(
        desc="Supplier profile JSON (industry, products_services, service_type, etc.) or 'None' if not available"
    )
    l1_category: str = dspy.InputField(
        desc="L1 category from preliminary classification (if available, 'unknown' if not available)"
    )
    l1_confidence: str = dspy.InputField(
        desc="L1 classification confidence: 'high', 'medium', 'low', or 'unknown'"
    )
    
    should_research: str = dspy.OutputField(
        desc="'yes' if research is needed (only relevant when supplier_profile is 'None'), 'no' if not needed, 'n/a' if supplier_profile is available"
    )
    prioritization_strategy: str = dspy.OutputField(
        desc="How to weight supplier context vs transaction data: 'supplier_primary' (prioritize supplier), 'transaction_primary' (prioritize transaction), 'balanced' (use both equally), 'supplier_only' (ignore transaction data), or 'n/a' if supplier_profile is not available"
    )
    supplier_context_strength: str = dspy.OutputField(
        desc="Strength of supplier context signal: 'strong' (specific industry/products), 'medium' (some context), 'weak' (generic), or 'none' (no profile/name)"
    )
    transaction_data_quality: str = dspy.OutputField(
        desc="Quality of transaction data: 'rich' (specific, descriptive), 'sparse' (missing/empty), 'generic' (vague terms), or 'accounting_reference' (journal entries, invoice numbers)"
    )
    reasoning: str = dspy.OutputField(
        desc="Brief explanation of the assessments and decisions made"
    )

