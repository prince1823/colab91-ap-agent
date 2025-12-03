"""DSPy Signature for spend classification."""

import dspy


class SpendClassificationSignature(dspy.Signature):
    """Classify business transactions into taxonomy categories.
    
    PROCESS:
    1. Check for tax/VAT patterns first: "vertex", "vat", "indirect tax", "sales tax", "reverse charge" → exceptions|government / taxes
       (Exception: "tax ON something" → classify underlying purchase)
    2. Assess transaction data (line_description, GL description): SPECIFIC/GENERIC/MISSING/MISLEADING
    3. Select L1: Use transaction data if SPECIFIC; use supplier profile if GENERIC/MISSING. L1 wrong = all wrong.
    4. Select path: Choose deepest path (min L1|L2|L3) from pre-searched paths matching transaction data
    
    WHAT vs WHO (Transaction Data vs Supplier):
    - WHAT (transaction data) is PRIMARY when SPECIFIC. Use when: clear product/service names, category descriptions, abbreviated GL with category signals (IT, pharmacy, travel codes)
    - WHO (supplier profile) is SECONDARY. Use when: WHAT is GENERIC ("services", "goods"), MISSING, MISLEADING (accounting codes), or ACCOUNTING_REFERENCE (invoice numbers only)
    - Parse abbreviations: Extract category keywords from GL (department codes, equipment types). Abbreviated GL with category signals = SPECIFIC
    - Supplier PRIMARY SERVICE (what they sell) vs INDUSTRY (what they operate in): Use PRIMARY SERVICE when WHAT is missing
    - When WHAT conflicts with WHO: Trust SPECIFIC transaction data; use WHO if WHAT is VAGUE/MISLEADING
    
    RULES:
    - Ignore payment codes: "accounts payable", "accrued invoices", "t&e payable" are not categories
    - NEVER return just L1 - must have L1|L2|L3 minimum
    - Prefer specific categories over "Other"
    - Distinguish consumption expenses (meals, services consumed) from operational purchases (supplies, equipment, infrastructure). Services/platforms that deliver meals = meal expenses, not operational supplies.
    - Airlines → travel & entertainment|airfare (not aviation fuel)
    - Medical suppliers → clinical|clinical supplies (not clinical services) when buying supplies
    """
    
    supplier_info: str = dspy.InputField(
        desc="JSON with supplier name, industry, products/services, service_type. Use as SECONDARY signal when transaction data is sparse/generic."
    )
    transaction_info: str = dspy.InputField(
        desc="Transaction details with PRIMARY signal marked: line_description (what was purchased - PRIMARY), gl_description (accounting code - SECONDARY, may be misleading)"
    )
    taxonomy_sample: str = dspy.InputField(
        desc="Sample taxonomy paths showing structure and L1 categories available"
    )
    prioritization: str = dspy.InputField(
        desc="Which signal to prioritize: 'supplier_primary', 'transaction_primary', 'balanced', or 'supplier_only'"
    )
    domain_context: str = dspy.InputField(
        desc="Company name/industry context to inform L1 selection (healthcare→clinical, media→marketing, etc.)"
    )
    
    classification_path: str = dspy.OutputField(
        desc="Pipe-separated path like 'Technology|Software|Cloud Services'. MUST have at least 3 levels and exist in taxonomy - use validate_path to verify."
    )
    confidence: str = dspy.OutputField(
        desc="'high' (clear match), 'medium' (reasonable match), 'low' (uncertain)"
    )
    reasoning: str = dspy.OutputField(
        desc="Brief explanation: what key signals led to this classification"
    )
