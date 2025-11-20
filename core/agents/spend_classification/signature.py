"""DSPy signature for spend classification agent."""

import dspy


class SpendClassificationSignature(dspy.Signature):
    """
    Classify transactions into taxonomy categories using pipe-separated paths (e.g., "clinical|clinical supplies|medical-surgical supplies").

    STEP 0A: EXEMPT/EXCEPTIONS DETECTION (check FIRST)
    
    Spend on intercompany transfers, sponsorship, wages, government-related items, etc. should be 
    bucketed under an Exempt category (L1). The L1 category name varies by taxonomy - it could be 
    "exempt", "exceptions", or another name.
    
    FIRST: Scan the taxonomy_structure to identify what L1 category serves as the exempt/exceptions 
    bucket. Look for L1 categories that contain paths like:
    - "intercompany", "inter-company", "subsidiary", "related party", "internal transfer"
    - "employee", "wages", "salary", "payroll", "compensation", "benefits"
    - "charitable", "donation", "sponsorship", "grant", "contribution"
    - "taxes", "regulatory", "license", "permit", "government fee"
    - "directors", "board member", "board compensation"
    
    Once you identify the exempt/exceptions L1 category name from the taxonomy, use THAT category name.
    
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
    Example: If exempt L1 is "exceptions", use "exceptions|government / taxes|government / taxes"
    Example: If exempt L1 is "exempt", use "exempt|taxes and regulatory fees|taxes and regulatory fees other"
    Only proceed if NOT exempt/exceptions and NOT tax charge.

    CLASSIFICATION PROCEDURE:
    1. Review: supplier (industry/products), line description, GL description, department
    2. Find best matching taxonomy path (prefer deeper paths)
    3. Split path into levels based on available_levels (ONLY return levels specified in available_levels)
    4. For levels beyond available_levels, do NOT return them (not "None", just omit)

    STRATEGY - Bottom-Up: Identify deepest confident level first (ideally L3+). L1/L2 auto-determined.
    Example: "laptops" → L3="IT Hardware" → L1="IT", L2="IT Hardware" auto-determined.

    PRIORITY:
    1. Rich transaction data (PO/Invoice/GL) - PRIMARY when available. Use FIRST if clear (e.g., "laptops", "cloud hosting").
    2. Supplier industry/products - PRIMARY when transaction data insufficient
    3. Line description → Department → GL description (ignore generic like "accounts payable")

    FALLBACK: If only L1 info available → Return only levels in available_levels.
    Example: If available_levels is "L1, L2, L3" → Return L1=[Category]|L2=[Category] Other|L3=None
    Example: If available_levels is "L1, L2, L3, L4" → Return L1=[Category]|L2=[Category] Other|L3=None|L4=None

    EXAMPLES:
    A) Supplier: "Cardinal Health", Line: "Surgical gloves" → "clinical|clinical supplies|medical-surgical supplies|medical-surgical supplies"
    B) Supplier: "Microsoft", Line: "Software subscription" → "it & telecom|software|software licenses fees"
    C) Line: "Inter-company transfer" → Find exempt L1 from taxonomy (e.g., "exempt" or "exceptions") → "exempt|intercompany|intercompany" OR "exceptions|intercompany|intercompany"
    D) Line: "Payroll processing fees" → Find exempt L1 from taxonomy → "exempt|employee related|employee related other" OR "exceptions|employee expense claim|employee expense claim"
    E) Line: "Sales tax on office supplies" → "non-clinical|general & administrative|office supplies|office supplies" (tax with purchase)
    F) Line: "State sales tax" (unclear) → Find exempt L1 from taxonomy → "exempt|taxes and regulatory fees|taxes and regulatory fees other" OR "exceptions|government / taxes|government / taxes"
    G) Line: "Purchase of 5 Dell laptops" → "it & telecom|it hardware|it hardware" (direct L3)
    H) Supplier: "Local Services LLC", Line: "", available_levels="L1, L2, L3, L4" → "non-clinical|general & administrative|None|None"
    I) Supplier: "Generic Services Inc", Line: "", available_levels="L1, L2, L3, L4" → "non-clinical|professional services|professional services other|None" (fallback - return only available levels)

    Apply override rules FIRST if they exist.
    """

    supplier_profile: str = dspy.InputField(
        desc="Supplier information (name, industry, products/services, description) - PRIMARY classification source"
    )
    transaction_data: str = dspy.InputField(
        desc="Transaction details (GL description, line description, client_spend_category [HINT ONLY], department). NOTE: client_spend_category is a hint, NOT a taxonomy level"
    )
    taxonomy_structure: str = dspy.InputField(
        desc="Client's taxonomy as a list of pipe-separated paths (e.g., ['L1|L2|L3', 'L1|L2|L3|L4']). Select the best matching path and split it into individual levels."
    )
    available_levels: str = dspy.InputField(
        desc="Available taxonomy levels (e.g., 'L1, L2, L3'). Only return levels specified here."
    )
    override_rules: str = dspy.InputField(
        desc="Override rules that take precedence (if any)"
    )

    L1: str = dspy.OutputField(
        desc="Level 1 category (top level)"
    )
    L2: str = dspy.OutputField(
        desc="Level 2 category (if applicable, otherwise 'None')"
    )
    L3: str = dspy.OutputField(
        desc="Level 3 category (if applicable, otherwise 'None')"
    )
    L4: str = dspy.OutputField(
        desc="Level 4 category (if applicable, otherwise 'None')"
    )
    L5: str = dspy.OutputField(
        desc="Level 5 category (if applicable, otherwise 'None')"
    )
    override_rule_applied: str = dspy.OutputField(
        desc="ID/description of override rule if applied, otherwise 'None'"
    )
    reasoning: str = dspy.OutputField(
        desc="Brief explanation of why this categorization was chosen"
    )
