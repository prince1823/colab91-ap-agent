"""DSPy signature for context prioritization agent."""

import dspy


class ContextPrioritizationSignature(dspy.Signature):
    """
    Assess transaction data quality and supplier context strength to make two decisions:
    1. Research Decision: Should we research the supplier? (when supplier_profile is not available)
    2. Prioritization Decision: How to weight supplier context vs transaction data? (when both are available)
    
    CONTEXTUAL ASSESSMENT APPROACH:
    Evaluate all available signals contextually - assess their relevance and reliability for THIS specific
    transaction, rather than following hardcoded rules. Let the context guide your assessment.
    
    1. TRANSACTION DATA QUALITY ASSESSMENT:
       - Review all available transaction fields (Department, GL Code, Cost Center, PO Number, Amount,
         Invoice Date, Line Description, GL Description, etc.)
       - Assess contextually: Are descriptions specific and useful, or generic/accounting jargon?
       - Identify patterns you observe (tax/VAT, payment processing, accounting references, etc.)
       - Consider: Does the transaction data clearly indicate what was purchased, or is it vague?
       - Classify as: "rich" (helpful, specific data), "sparse" (missing/empty), "generic" (vague),
         or "accounting_reference" (describes processing/entity rather than purchase)
    
    2. SUPPLIER CONTEXT STRENGTH ASSESSMENT (if supplier_profile available):
       - Review supplier profile: Industry, products/services, service_type, NAICS/SIC codes
       - Assess: How specific and relevant is this supplier information for classification?
       - Consider: Does supplier profile clearly indicate what they provide?
       - Classify as: "strong" (specific, relevant), "medium" (some context), "weak" (generic), 
         or "none" (no profile)
    
    3. PERSON DETECTION (for research decision):
       - If supplier_name appears to be an individual person → should_research="no"
       - Person indicators: Personal names (first + last name), titles (Dr., Mr., etc.), 
         no business suffixes (Inc., LLC, Corp, etc.)
       - Examples: "John Smith", "Dr. Jane Doe" → person; "Smith & Co", "John Smith LLC" → business
    
    4. RESEARCH DECISION (when supplier_profile is None):
       - If supplier is a person → should_research="no" (research won't help)
       - Assess: Would supplier research add useful context for classification?
       - Consider: Transaction data quality, supplier name specificity, domain context
       - Make contextual decision based on whether research would meaningfully help
    
    5. PRIORITIZATION DECISION (when supplier_profile is available):
       - Evaluate contextually: For THIS transaction, which signals are most reliable?
       - Consider: Supplier profile relevance vs transaction data specificity
       - Consider: Are transaction descriptions specific, or generic/accounting references?
       - Consider: Patterns you've identified (tax/VAT, payment processing, etc.) - do they indicate
         special categories that might override supplier profile?
       - Decide based on context:
         * "supplier_primary": Supplier profile is most reliable for this transaction
         * "transaction_primary": Transaction data is most reliable for this transaction
         * "balanced": Both provide useful, complementary information
         * "supplier_only": Transaction data is not useful (e.g., accounting references only)
    
    CONTEXTUAL REASONING:
    - Don't follow hardcoded rules - evaluate each transaction on its own merits
    - Consider all available signals and their contextual relevance
    - Identify patterns (tax/VAT, accounting references, etc.) contextually
    - Make decisions that make sense for THIS specific transaction
    """
    
    transaction_data: str = dspy.InputField(
        desc="Transaction details organized by field type (Transaction Context, Descriptions, References, Additional Information). Evaluate all fields contextually - assess what's useful for THIS transaction rather than applying hardcoded priorities."
    )
    supplier_name: str = dspy.InputField(
        desc="Supplier name (if available, 'None' if not available)"
    )
    supplier_profile: str = dspy.InputField(
        desc="Supplier profile JSON (industry, products_services, service_type, etc.) or 'None' if not available"
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

