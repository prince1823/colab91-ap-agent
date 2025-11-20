"""DSPy signature for spend classification agent."""

import dspy


class SpendClassificationSignature(dspy.Signature):
    """
    Classify transactions into taxonomy categories using pipe-separated paths (e.g., "clinical|clinical supplies|medical-surgical supplies").

    STEP 0A: EXEMPT/EXCEPTIONS DETECTION (check FIRST)
    Spend on intercompany, wages, charitable, government-related items → exempt L1. L1 name varies by taxonomy ("exempt", "exceptions", etc.).
    FIRST: Scan taxonomy_structure to identify exempt L1 category (look for: intercompany/subsidiary/related party, employee/wages/payroll/compensation, charitable/donation/sponsorship, taxes/regulatory/license/permit, directors/board compensation).
    Once identified, use THAT category name. Detect: intercompany/subsidiary, wages/payroll/compensation, donations/sponsorship, taxes/licenses, board compensation.
    Use semantic understanding: "Payroll processing services" → exempt. "Sales tax on office supplies" → NOT exempt (see tax handling). STOP if exempt.

    STEP 0B: TAX HANDLING
    Tax charges (sales tax, VAT, GST, use tax, excise tax, service tax) → classify with underlying purchase. If unclear what tax is on → exempt L1 (from STEP 0A) > taxes path.
    Example: exempt L1="exceptions" → "exceptions|government / taxes|government / taxes". Only proceed if NOT exempt and NOT tax.

    CLASSIFICATION:
    1. Review supplier (industry/products), line description, GL description, department
    2. Find best matching taxonomy path (prefer deeper)
    3. Return only levels in available_levels (ONLY return levels specified in available_levels)
    4. For levels beyond available_levels, do NOT return them (not "None", just omit)
    
    STRATEGY: Bottom-up - identify deepest confident level first (ideally L3+). L1/L2 auto-determined.
    Example: "laptops" → L3="IT Hardware" → L1="IT", L2="IT Hardware" auto-determined.

    PRIORITY:
    1. Data Quality: HIGH (clear line/GL/PO) → transaction data FIRST, supplier CONTEXT. MEDIUM → transaction primary, supplier supplement. LOW (generic/blank) → supplier PRIMARY, consider transaction.
    2. Match: Rich data → transaction to taxonomy. Sparse → supplier to taxonomy. Verify: Does it make sense for THIS transaction?
    3. Field order: Line desc → GL desc → Department → PO. Ignore generic ("accounts payable", "goods and services"). If generic → rely more on supplier.

    FALLBACK: If only L1 info available → Return only levels in available_levels.
    Example: available_levels="L1, L2, L3" → Return L1=[Category]|L2=[Category] Other|L3=None
    Example: available_levels="L1, L2, L3, L4" → Return L1=[Category]|L2=[Category] Other|L3=None|L4=None

    EXAMPLES:
    A) Supplier: "Cardinal Health", Line: "Surgical gloves" → "clinical|clinical supplies|medical-surgical supplies|medical-surgical supplies"
    B) Supplier: "Microsoft", Line: "Software subscription" → "it & telecom|software|software licenses fees"
    C) Line: "Inter-company transfer" → Find exempt L1 from taxonomy (e.g., "exempt" or "exceptions") → "exempt|intercompany|intercompany" OR "exceptions|intercompany|intercompany"
    D) Line: "Payroll processing fees" → Find exempt L1 → "exempt|employee related|employee related other" OR "exceptions|employee expense claim|employee expense claim"
    E) Line: "Sales tax on office supplies" → "non-clinical|general & administrative|office supplies|office supplies" (tax with purchase)
    F) Line: "State sales tax" (unclear) → Find exempt L1 → "exempt|taxes and regulatory fees|taxes and regulatory fees other" OR "exceptions|government / taxes|government / taxes"
    G) Line: "Purchase of 5 Dell laptops" → "it & telecom|it hardware|it hardware" (direct L3)
    H) Supplier: "Local Services LLC", Line: "", available_levels="L1, L2, L3, L4" → "non-clinical|general & administrative|None|None"
    I) Supplier: "Generic Services Inc", Line: "", available_levels="L1, L2, L3, L4" → "non-clinical|professional services|professional services other|None" (fallback)

    Apply override rules FIRST if they exist.
    """

    supplier_profile: str = dspy.InputField(
        desc="Supplier info (name, industry, products/services). Use as CONTEXT when transaction data insufficient. Transaction data takes precedence when clear."
    )
    transaction_data: str = dspy.InputField(
        desc="Transaction details with quality assessment: [QUALITY] + PRIMARY DATA (line/GL/PO) + ADDITIONAL CONTEXT. NOTE: client_spend_category is a hint only."
    )
    taxonomy_structure: str = dspy.InputField(
        desc="Taxonomy as pipe-separated paths. Select best match and split into levels."
    )
    available_levels: str = dspy.InputField(
        desc="Available levels (e.g., 'L1, L2, L3'). Only return these levels."
    )
    override_rules: str = dspy.InputField(
        desc="Override rules (if any)"
    )

    L1: str = dspy.OutputField(desc="Level 1 category")
    L2: str = dspy.OutputField(desc="Level 2 (or 'None')")
    L3: str = dspy.OutputField(desc="Level 3 (or 'None')")
    L4: str = dspy.OutputField(desc="Level 4 (or 'None')")
    L5: str = dspy.OutputField(desc="Level 5 (or 'None')")
    override_rule_applied: str = dspy.OutputField(desc="Override rule ID or 'None'")
    reasoning: str = dspy.OutputField(desc="Brief explanation")
