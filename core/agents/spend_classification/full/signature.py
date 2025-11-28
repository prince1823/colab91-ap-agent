"""DSPy signature for full spend classification agent (L2-L5)."""

import dspy


class FullClassificationSignature(dspy.Signature):
    """
    Classify transactions into taxonomy categories (L2-L5) using L1 category, transaction data, supplier profile, and filtered taxonomy.
    
    This classifier runs AFTER L1 preliminary classification. It takes the L1 category from Stage 1
    and fills in L2-L5 categories using supplier information and transaction details.
    
    IMPORTANT: The L1 category is already determined. You must use the provided L1 category and
    find the best matching path that starts with that L1 category.
    
    STEP 0: ASSESS L1 VALIDITY
    The provided l1_category is from preliminary classification. Before using it, assess:
    
    L1 OVERRIDE RULE: If l1_category is "non-sourceable" (or similar catch-all) AND supplier profile
    strongly suggests a specific category (e.g., supplier="medical supplies company" → "clinical"),
    you may override L1 to use the supplier profile category instead.
    
    PRINCIPLE: Supplier profile is STRONG signal when transaction data is sparse. If L1 is a catch-all
    category but supplier profile clearly indicates a specific spend category, prioritize supplier profile.
    
    If L1 override is needed:
    - Use supplier profile to determine correct L1 category
    - Find taxonomy paths starting with the corrected L1 category
    - Return the corrected L1 in your response
    
    If L1 is valid:
    - Only consider paths that start with the provided L1 category
    
    CLASSIFICATION PROCEDURE:
    1. Assess if L1 needs override (catch-all category + strong supplier profile signal)
    2. Review: supplier profile (PRIMARY when transaction data is sparse), line description, GL description
    3. Find best matching taxonomy path (prefer deeper paths)
    4. Split path into levels based on available_levels (ONLY return levels specified in available_levels)
    5. For levels beyond available_levels, do NOT return them (not "None", just omit)
    
    STRATEGY - Bottom-Up: Identify deepest confident level first (ideally L3+). L2 auto-determined from path.
    Example: "laptops" → L3="IT Hardware" → L2="IT Hardware" auto-determined from path.
    
    PRIORITY (CRITICAL - READ CAREFULLY):
    
    When transaction data is SPARSE (generic GL like "accounts payable" + accounting references):
    1. Supplier profile is PRIMARY signal - use it exclusively
    2. Ignore sparse transaction data (generic GL, accounting references)
    3. Map supplier profile (industry, products_services, service_type) to taxonomy
    
    When transaction data is RICH (specific line descriptions, descriptive GL):
    1. Transaction data (line description, GL description) - PRIMARY when available
    2. Supplier profile - SECONDARY (supplemental context)
    3. Line description → GL description (ignore generic like "accounts payable")
    
    GL MISLEADING DETECTION (CRITICAL):
    ⚠️ IMPORTANT: GL codes are accounting categories used for financial reporting, NOT spend categories.
    They may not accurately reflect what was purchased.
    
    PRINCIPLE: If GL description conflicts with supplier profile, GL may be misleading.
    
    RULE: When GL conflicts with supplier profile:
    1. GL may be misleading - accounting codes don't always match spend categories
    2. Prioritize supplier profile over conflicting GL
    3. Use GL only if it aligns with supplier profile
    
    Examples:
    - GL="advertising", Supplier Profile="clinical services, healthcare IT" →
      Analysis: GL suggests marketing, but supplier profile suggests clinical services
      ❌ WRONG: "non-clinical|marketing" (following misleading GL)
      ✅ CORRECT: GL is misleading, use supplier profile → "clinical|clinical services"
    
    - GL="professional fees", Supplier Profile="consulting services, financial advisory" →
      Analysis: GL aligns with supplier profile
      ✅ CORRECT: Use both GL and supplier profile → "non-clinical|professional services|consulting"
    
    - GL="accounts payable" (generic), Supplier Profile="medical supplies, pharmaceuticals" →
      Analysis: GL is generic, supplier profile is specific
      ✅ CORRECT: Use supplier profile → "clinical|clinical supplies|medical-surgical supplies"
    
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
        desc="Client's taxonomy paths. If l1_category is a catch-all category (non-sourceable, exempt, exceptions), this contains ALL taxonomy paths. Otherwise, it contains only paths starting with l1_category (e.g., ['L1|L2|L3', 'L1|L2|L3|L4']). Select the best matching path and return it as classification_path."
    )
    available_levels: str = dspy.InputField(
        desc="Available taxonomy levels (e.g., 'L1, L2, L3'). Only return levels specified here."
    )
    override_rules: str = dspy.InputField(
        desc="Override rules that take precedence (if any)"
    )
    
    classification_path: str = dspy.OutputField(
        desc="Complete classification path in pipe-separated format: 'L1|L2|L3|L4|L5'. Use 'None' for missing levels. IMPORTANT: For L1, return the provided l1_category in most cases. ONLY override L1 if l1_category is a catch-all category (like 'non-sourceable', 'exempt', 'exceptions') AND supplier profile strongly suggests a specific category (e.g., supplier='medical supplies company' → 'clinical'). Examples: 'clinical|clinical supplies|medical-surgical supplies|medical-surgical supplies', 'it & telecom|software|software licenses fees', 'non-clinical|general & administrative|None|None'"
    )
    override_rule_applied: str = dspy.OutputField(
        desc="ID/description of override rule if applied, otherwise 'None'"
    )
    reasoning: str = dspy.OutputField(
        desc="Brief explanation of why this categorization was chosen"
    )

