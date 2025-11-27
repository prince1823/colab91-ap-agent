"""DSPy signature for full spend classification agent (L2-L5)."""

import dspy


class FullClassificationSignature(dspy.Signature):
    """
    Classify transactions into taxonomy categories (L2-L5) using L1 category, transaction data, supplier profile, and filtered taxonomy.
    
    This classifier runs AFTER L1 preliminary classification. It takes the L1 category from Stage 1
    and fills in L2-L5 categories using supplier information and transaction details.
    
    IMPORTANT: The L1 category is already determined. You must use the provided L1 category and
    find the best matching path that starts with that L1 category.
    
    STEP 0: VERIFY L1 MATCH
    The provided l1_category must match the first level of the taxonomy paths. Only consider
    paths that start with the provided L1 category.
    
    CLASSIFICATION PROCEDURE:
    1. Review: supplier (industry/products), line description, GL description
    2. Find best matching taxonomy path that starts with the provided L1 category (prefer deeper paths)
    3. Split path into levels based on available_levels (ONLY return levels specified in available_levels)
    4. For levels beyond available_levels, do NOT return them (not "None", just omit)
    
    STRATEGY - Bottom-Up: Identify deepest confident level first (ideally L3+). L2 auto-determined from path.
    Example: "laptops" → L3="IT Hardware" → L2="IT Hardware" auto-determined from path.
    
    PRIORITY:
    1. Rich transaction data (line description, GL description) - PRIMARY when available. Use FIRST if clear (e.g., "laptops", "cloud hosting").
    2. Supplier industry/products - PRIMARY when transaction data insufficient
    3. Line description → GL description (ignore generic like "accounts payable")
    
    NOTE: Transaction IDs (PO numbers, invoice numbers), organizational codes (department, cost center),
    and financial values (amount, currency) are NOT useful for classification and are excluded.
    
    LARGE COMPANY HANDLING:
    If is_large_company=True, the supplier description may be too broad and confusing. 
    Prioritize transaction line items over supplier description. Focus on what is being purchased,
    not the general nature of the supplier's business.
    
    FALLBACK: If only L1 info available → Return only levels in available_levels.
    Example: If available_levels is "L1, L2, L3" → Return L1=[Category]|L2=[Category] Other|L3=None
    Example: If available_levels is "L1, L2, L3, L4" → Return L1=[Category]|L2=[Category] Other|L3=None|L4=None
    
    EXAMPLES:
    A) L1="clinical", Supplier: "Cardinal Health", Line: "Surgical gloves" → "clinical|clinical supplies|medical-surgical supplies|medical-surgical supplies"
    B) L1="it & telecom", Supplier: "Microsoft", Line: "Software subscription" → "it & telecom|software|software licenses fees"
    C) L1="non-clinical", Supplier: "Local Services LLC", Line: "", available_levels="L1, L2, L3, L4" → "non-clinical|general & administrative|None|None"
    D) L1="non-clinical", Supplier: "Generic Services Inc", Line: "", available_levels="L1, L2, L3, L4" → "non-clinical|professional services|professional services other|None"
    
    Apply override rules FIRST if they exist.
    """
    
    l1_category: str = dspy.InputField(
        desc="L1 category from preliminary classifier (must match first level of taxonomy paths)"
    )
    supplier_profile: str = dspy.InputField(
        desc="Supplier information including: name, industry, products/services, description, is_large_company, service_type (e.g., 'Travel - Airlines', 'IT - Hardware'), NAICS/SIC codes, business_model, revenue_streams, service_categories, target_market. For large companies, prioritize transaction data over supplier description. Use service_type and service_categories to map directly to taxonomy categories."
    )
    transaction_data: str = dspy.InputField(
        desc="Transaction details (GL description, line description). NOTE: client_spend_category is a hint, NOT a taxonomy level. Department codes are internal organizational identifiers and are not useful for classification."
    )
    taxonomy_structure: str = dspy.InputField(
        desc="Client's taxonomy filtered to paths starting with l1_category (e.g., ['L1|L2|L3', 'L1|L2|L3|L4']). Select the best matching path and split it into individual levels."
    )
    available_levels: str = dspy.InputField(
        desc="Available taxonomy levels (e.g., 'L1, L2, L3'). Only return levels specified here."
    )
    override_rules: str = dspy.InputField(
        desc="Override rules that take precedence (if any)"
    )
    
    L1: str = dspy.OutputField(
        desc="Level 1 category (must match the provided l1_category)"
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

