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
    
    L1 OVERRIDE RULE (AGENTIC DECISION):
    If l1_category is a catch-all category (e.g., "non-sourceable", "exempt", "exceptions") AND supplier profile
    strongly suggests a specific category, you may override L1 to use the supplier profile category instead.
    
    Decision Criteria:
    1. **Assess Supplier Profile Strength**: Use provided supplier_context_strength:
       - If "strong": Supplier profile is specific and reliable (specific industry, products/services)
       - If "medium" or "weak": Supplier profile is less reliable, be cautious about override
       - If "none": Cannot override (no supplier context)
    
    2. **Assess Business Context**: Consider the full business context:
       - Industry: What industry does the supplier operate in?
       - Business Model: What is the supplier's primary business model?
       - Target Market: Who does the supplier serve?
       - Products/Services: What does the supplier actually provide?
       - NOT just product/service name - consider the full business domain
    
    3. **Consider Taxonomy Structure**: What L1 categories are available in taxonomy_structure?
       - Map the supplier's business context to the most appropriate L1 category
       - Use semantic understanding to match business domain to taxonomy
    
    PRINCIPLE: When overriding catch-all, consider the full business context - industry, business model, target market - 
    not just product/service name. Use semantic understanding to map supplier profile to the most appropriate L1 category 
    from available taxonomy.
    
    If L1 override is needed:
    - Use supplier profile (considering full business context) to determine correct L1 category
    - Find taxonomy paths starting with the corrected L1 category
    - Return the corrected L1 in your response
    
    If L1 is valid (not catch-all or supplier profile doesn't strongly suggest override):
    - Only consider paths that start with the provided l1_category
    
    CLASSIFICATION PROCEDURE:
    1. Assess if L1 needs override (catch-all category + strong supplier profile signal)
    2. Review: supplier profile (PRIMARY when transaction data is sparse), line description, GL description
    3. Find best matching taxonomy path (prefer deeper paths)
    4. Split path into levels based on available_levels (ONLY return levels specified in available_levels)
    5. For levels beyond available_levels, do NOT return them (not "None", just omit)
    
    STRATEGY - Bottom-Up: Identify deepest confident level first (ideally L3+). L2 auto-determined from path.
    Example: "laptops" → L3="IT Hardware" → L2="IT Hardware" auto-determined from path.
    
    TAXONOMY DEPTH PREFERENCE (CRITICAL):
    - Always select the deepest matching path available in the taxonomy
    - Prefer specific categories over generic 'Other' categories when both are available
    - If multiple paths match at different depths, choose the deepest one you're confident about
    - Examples:
      * If both "L1|L2|L3" and "L1|L2|L3|L4" match, prefer "L1|L2|L3|L4" (deeper path)
      * If both "L1|L2|Other" and "L1|L2|L3|Specific Category" match, prefer "L1|L2|L3|Specific Category" (more specific)
    - Bottom-Up approach: Identify deepest confident level first (ideally L3+), then work backwards to fill L2
    
    PRIORITIZATION STRATEGY (CRITICAL - FOLLOW STRICTLY):
    
    Use the provided prioritization_strategy to determine how to weight supplier profile vs transaction data:
    
    - If prioritization_strategy is 'supplier_primary': Prioritize supplier profile over transaction data. Use supplier profile as PRIMARY signal, transaction data as secondary.
    - If prioritization_strategy is 'transaction_primary': Prioritize transaction data over supplier profile. Use transaction data as PRIMARY signal, supplier profile as secondary.
    - If prioritization_strategy is 'balanced': Use both supplier profile and transaction data equally. Consider both signals when making classification decision.
    - If prioritization_strategy is 'supplier_only': Ignore transaction data completely (likely accounting reference). Use ONLY supplier profile for classification.
    - If prioritization_strategy is 'n/a': Use default priority (transaction data first, then supplier profile if transaction data is sparse).
    
    The prioritization_strategy was determined by analyzing supplier_context_strength and transaction_data_quality. Follow it strictly.
    
    DEFAULT PRIORITY (when prioritization_strategy is 'n/a'):
    
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
    prioritization_strategy: str = dspy.InputField(
        desc="How to weight supplier profile vs transaction data: 'supplier_primary' (prioritize supplier), 'transaction_primary' (prioritize transaction), 'balanced' (use both equally), 'supplier_only' (ignore transaction data), or 'n/a' (not available). Use this strategy to determine which signals to prioritize."
    )
    supplier_context_strength: str = dspy.InputField(
        desc="Strength of supplier context signal: 'strong' (specific industry/products), 'medium' (some context), 'weak' (generic), or 'none' (no profile/name)."
    )
    transaction_data_quality: str = dspy.InputField(
        desc="Quality of transaction data: 'rich' (specific, descriptive), 'sparse' (missing/empty), 'generic' (vague terms), or 'accounting_reference' (journal entries, invoice numbers)."
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

