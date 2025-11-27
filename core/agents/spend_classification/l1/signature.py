"""DSPy signature for L1 preliminary classification agent."""

import dspy


class L1ClassificationSignature(dspy.Signature):
    """
    Classify transactions into L1 (top-level) category ONLY using transaction data.
    
    This is a preliminary classifier that runs before supplier research. It uses only
    transaction data (line descriptions, GL descriptions) to determine the top-level category.
    Note: Department codes are internal organizational identifiers and are not useful for spend categorization.
    
    STEP 0A: EXEMPT/EXCEPTIONS DETECTION (check FIRST)
    
    Spend on intercompany transfers, sponsorship, wages, government-related items, etc. should be 
    bucketed under an Exempt category (L1). The L1 category name varies by taxonomy - it could be 
    "exempt", "exceptions", or another name.
    
    FIRST: Scan the l1_categories list to identify what L1 category serves as the exempt/exceptions 
    bucket. Look for L1 categories that contain:
    - "exempt", "exceptions", "non-sourceable"
    
    Detect exempt-type transactions:
    - Intercompany: "intercompany", "inter-company", "subsidiary", "related party", "internal transfer"
    - Employee: "wages", "salary", "payroll", "employee", "compensation", "benefits", "payroll processing"
    - Charitable: "donation", "charitable", "sponsorship", "grant", "contribution", "philanthropy"
    - Government: "tax", "regulatory", "license", "permit", "government fee", "compliance fee"
    - Directors: "director", "board member", "board compensation"
    
    Use semantic understanding: "Payroll processing services" → exempt/exceptions (employee). 
    "Sales tax on office supplies" → NOT exempt/exceptions (see tax handling). STOP if exempt/exceptions detected.
    
    STEP 0B: TAX HANDLING
    Taxes on purchases → classify with underlying purchase category.
    Identify tax charges: sales tax, VAT, GST, use tax, excise tax, service tax.
    If tax charge: find what it's ON → classify to same category as purchase.
    If unclear what tax is on → classify to the exempt/exceptions L1 category (from STEP 0A) > taxes path.
    Only proceed if NOT exempt/exceptions and NOT tax charge.
    
    CLASSIFICATION PROCEDURE:
    1. Review: line description, GL description
    2. If transaction data is sparse and supplier name is provided as hint:
       - Use semantic understanding of the supplier name to infer what type of service/product they provide
       - Supplier names often directly indicate their business domain (company names reflect their industry)
       - Map the inferred service/product type to the most appropriate L1 category
    3. Match to best L1 category from the provided list
    4. Consider transaction context (what is being purchased, not who is selling)
    
    
    SPARSE DATA HANDLING:
    If transaction data is sparse (only dates, generic GL like "accounts payable", or empty):
    - DO NOT default to "non-sourceable" unless transaction is clearly exempt (intercompany, payroll, etc.)
    - Supplier name hints are a STRONG SIGNAL when transaction data is sparse
    - Use semantic understanding to infer the spend category from the supplier name:
      * Analyze what the supplier name suggests about their business domain
      * Map that business domain to the most appropriate L1 category
      * Return confidence="low" to trigger supplier research for refinement
    - If no supplier context available → "non-clinical" with confidence="low" (most general category)
    - Only use "non-sourceable" for truly exempt transactions (intercompany, payroll, taxes, etc.)
    
    PRIORITY:
    1. Rich transaction data (PO/Invoice/GL) - PRIMARY when available
    2. Line description → GL description (ignore generic like "accounts payable")
    3. If data is sparse, use supplier name hint to infer category, return low confidence to allow supplier research to help
    
    EXAMPLES:
    A) Line: "Surgical gloves" → "clinical"
    B) Line: "Software subscription" → "it & telecom"
    C) Line: "Inter-company transfer" → Find exempt L1 (e.g., "exempt" or "exceptions") → "exempt" OR "exceptions"
    D) Line: "Payroll processing fees" → Find exempt L1 → "exempt" OR "exceptions"
    E) Line: "Sales tax on office supplies" → "non-clinical" (tax with purchase)
    F) Line: "State sales tax" (unclear) → Find exempt L1 → "exempt" OR "exceptions"
    G) Line: "Purchase of 5 Dell laptops" → "it & telecom"
    H) Line: "", GL: "rent - misc expense" → "non-clinical"
    """
    
    transaction_data: str = dspy.InputField(
        desc="Transaction details (GL description, line description). If supplier name is provided as a hint (marked 'hint only'), use semantic understanding of the supplier name to infer the spend category when transaction data is sparse. Supplier names often directly indicate their business domain and should be prioritized when transaction descriptions are missing or generic."
    )
    l1_categories: str = dspy.InputField(
        desc="List of available L1 categories (e.g., ['clinical', 'non-clinical', 'it & telecom', 'exempt']). Select the best matching category."
    )
    
    L1: str = dspy.OutputField(
        desc="Level 1 category (top level) - must be one of the provided l1_categories"
    )
    confidence: str = dspy.OutputField(
        desc="Confidence level: 'high' (clear match), 'medium' (reasonable match), or 'low' (uncertain, may need supplier research)"
    )
    reasoning: str = dspy.OutputField(
        desc="Brief explanation of why this L1 category was chosen"
    )

