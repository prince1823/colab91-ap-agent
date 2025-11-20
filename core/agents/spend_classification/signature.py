"""DSPy signature for spend classification agent."""

import dspy


class SpendClassificationSignature(dspy.Signature):
    """
    Classify transactions into taxonomy categories using pipe-separated paths (e.g., "clinical|clinical supplies|medical-surgical supplies").

    STEP 0A: EXEMPT DETECTION (check FIRST)
    Detect and classify to exempt path if found:
    - Intercompany: "intercompany", "inter-company", "subsidiary", "related party", "internal transfer"
    - Employee: "wages", "salary", "payroll", "employee", "compensation", "benefits", "payroll processing"
    - Charitable: "donation", "charitable", "sponsorship", "grant", "contribution", "philanthropy"
    - Government: "tax", "regulatory", "license", "permit", "government fee", "compliance fee"
    - Directors: "director", "board member", "board compensation"
    
    Use semantic understanding: "Payroll processing services" → exempt (employee). 
    "Sales tax on office supplies" → NOT exempt (see tax handling). STOP if exempt detected.

    STEP 0B: TAX HANDLING
    Taxes on purchases → classify with underlying purchase category.
    Identify tax charges: sales tax, VAT, GST, use tax, excise tax, service tax.
    If tax charge: find what it's ON → classify to same category as purchase.
    If unclear what tax is on → classify to "exempt|taxes and regulatory fees|taxes and regulatory fees other".
    Only proceed if NOT exempt and NOT tax charge.

    CLASSIFICATION PROCEDURE:
    1. Review: supplier (industry/products), line description, GL description, department
    2. Find best matching taxonomy path (prefer deeper paths)
    3. Split path into L1-L5 levels (set to "None" if uncertain)

    STRATEGY - Bottom-Up: Identify deepest confident level first (ideally L3+). L1/L2 auto-determined.
    Example: "laptops" → L3="IT Hardware" → L1="IT", L2="IT Hardware" auto-determined.

    PRIORITY:
    1. Rich transaction data (PO/Invoice/GL) - PRIMARY when available. Use FIRST if clear (e.g., "laptops", "cloud hosting").
    2. Supplier industry/products - PRIMARY when transaction data insufficient
    3. Line description → Department → GL description (ignore generic like "accounts payable")

    FALLBACK: If only L1 info available → L1=[Category] > L2=[Category] Other (e.g., "Professional Services > Professional Services Other")

    EXAMPLES:
    A) Supplier: "Cardinal Health", Line: "Surgical gloves" → "clinical|clinical supplies|medical-surgical supplies|medical-surgical supplies"
    B) Supplier: "Microsoft", Line: "Software subscription" → "it & telecom|software|software licenses fees"
    C) Line: "Inter-company transfer" → "exempt|intercompany|intercompany"
    D) Line: "Payroll processing fees" → "exempt|employee related|employee related other"
    E) Line: "Sales tax on office supplies" → "non-clinical|general & administrative|office supplies|office supplies" (tax with purchase)
    F) Line: "State sales tax" (unclear) → "exempt|taxes and regulatory fees|taxes and regulatory fees other"
    G) Line: "Purchase of 5 Dell laptops" → "it & telecom|it hardware|it hardware" (direct L3)
    H) Supplier: "Local Services LLC", Line: "" → "non-clinical|general & administrative|None"
    I) Supplier: "Generic Services Inc", Line: "" → "non-clinical|professional services|professional services other" (fallback)

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
