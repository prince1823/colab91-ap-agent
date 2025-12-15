"""DSPy Signature for spend classification."""

import dspy


class SpendClassificationSignature(dspy.Signature):
    """Classify business transactions into taxonomy categories using contextual reasoning.
    
    APPROACH: Use contextual pattern recognition - evaluate all available signals and decide
    what matters most for THIS specific transaction based on the context.
    
    CONTEXTUAL PATTERN RECOGNITION:
    - Supplier Profile: Understand what the supplier typically provides (industry, products/services).
      This is often reliable, but consider: does the transaction match what the supplier sells?
    - Department/Business Unit: Organizational context - often aligns with spend categories.
    - GL Code: Give VERY LOW priority - accounting constructs rarely indicate spend category. Only use if there's nothing else.
    - Descriptions: Can be highly specific and useful OR generic/accounting jargon - evaluate each case.
      Accounting references ("accounts payable", "accrued invoices") are usually less useful than
      specific product/service descriptions.
    
    PROCESS (Contextual Bottom-Up):
    1. Review all available signals contextually - assess field completeness and data quality
       - Note which fields are available (structured fields, descriptions, references)
       - Evaluate the specificity and relevance of each field for THIS transaction
       - Identify patterns you observe in the data (without hardcoded rules)
    
    2. Examine taxonomy paths starting from deepest/most specific levels (L5/L4) and work backward to L1
       - Similarity scores (if shown) indicate RAG retrieval confidence - use as one signal
       - Focus on matching the END of taxonomy paths (leaf nodes) first
       - Consider the full hierarchy when multiple paths seem similar
       - Understand category boundaries by examining the taxonomy structure itself
    
    3. Match transaction context to taxonomy paths - use ALL signals that seem relevant
       - For each transaction, reason about which signals are most trustworthy for THIS specific case
       - Consider: Does supplier profile match the transaction? Are descriptions specific or generic?
       - Consider: Do patterns suggest special categories (tax, payment processing) that might override other signals?
    
    4. Contextual signal reliability assessment:
       - Specific, detailed information > Generic, vague information (regardless of field type)
       - Transaction-specific signals > Generic organizational context (when transaction is clear)
       - Clear, unambiguous patterns > Ambiguous, conflicting signals
       - Evaluate signal relevance dynamically - what matters most for THIS transaction?
    
    USE TRANSACTION AMOUNT FOR PATTERNS:
    - Large one-time amounts (>$50k) → Capital equipment, major services, construction, infrastructure
    - Small recurring amounts (same amount monthly/quarterly) → Subscriptions, utilities, recurring services, software licenses
    - Medium recurring amounts → Professional services contracts, maintenance agreements
    - Variable amounts → Usage-based services, one-time purchases
    - Very large amounts (>$100k) → Major projects, enterprise contracts, capital investments
    
    USE PO NUMBER:
    - Same PO across multiple transactions → Related purchases, same project/category
    - PO indicates contract → May have pre-categorized spend patterns
    
    USE COST CENTER:
    - Organizational alignment with departments → Spend category context
    - Cost center codes often indicate business function → Category hints
    
    CONTEXTUAL REASONING EXAMPLES:
    - Specific descriptions: "AWS Cloud Services" is more reliable than "services" - use the specific one.
    - Accounting codes: "accounts payable" or "accrued invoices" are accounting processes, not categories.
      However, descriptions WITHIN those codes might be useful.
    - Supplier vs Transaction: If supplier sells "payroll services" but transaction description indicates something else,
      prioritize the transaction context.
    
    EDGE CASE HANDLING (Contextual):
    - Zero or very small amounts: Evaluate if this is an adjustment, refund, or actual purchase based on context
    - Missing/blank descriptions: Rely on supplier profile and department first; use GL code only as last resort
    - Generic accounting references: May indicate processing entries rather than spend categories - evaluate contextually
    - Supplier profile mismatch: If supplier typically provides X but transaction suggests Y, prioritize transaction context
    
    INVOICE-LEVEL CLASSIFICATION:
    - For invoices with multiple line items, you will be shown all line items together
    - Return ONE classification per line item in the order provided
    - Most line items in an invoice often share the same classification
    - Response format options:
      * If ALL rows get the SAME classification → Return single path: "Technology|Software|Cloud Services"
      * If rows need DIFFERENT classifications → Return JSON list: ["path1", "path2", "path3"]
    - For single-row transactions, use the standard single output format

    TAX CLASSIFICATION RULES:
    - Only classify as taxes if the payment recipient is a government entity (taxes are NEVER paid to vendors)
    - Tax-related software or services from vendors (e.g., Vertex, Avalara) should be classified by their service type, NOT as taxes
    - If taxes are incidental to a purchase, do NOT classify as taxes - classify by the underlying purchase
    - Example: Invoice with 5 lines for 'AWS Cloud Services' and 1 line for 'Sales Tax on AWS' → Classify ALL 6 lines as the underlying purchase category
    - The goal is to capture the business spend category, not the accounting treatment of tax

    GENERAL RULES:
    - NEVER return just L1 - must have L1|L2|L3 minimum
    - Prefer specific categories over "Other" when confident
    - Distinguish consumption expenses (meals, services consumed) from operational purchases
    - Consider context: What matters most for THIS transaction given all available signals?
    - Patterns in descriptions (tax, payment processing) are contextual clues - evaluate their relevance
    - Field completeness matters - use available fields contextually based on their quality and specificity
    """
    
    supplier_info: str = dspy.InputField(
        desc="JSON with supplier name, industry, products/services, service_type. Understand what the supplier typically provides - this context helps inform classification, but evaluate if it matches the transaction."
    )
    transaction_info: str = dspy.InputField(
        desc="Transaction details with all available signals and contextual patterns. Includes: Department, GL Code, Amount, PO Number, Cost Center, Invoice Date, and descriptions. Contextual patterns (tax/VAT, payment processing) are highlighted if detected. Evaluate all signals contextually - decide what matters most for THIS transaction."
    )
    taxonomy_sample: str = dspy.InputField(
        desc="Taxonomy paths sorted by depth (deepest first). Start matching from the END (most specific categories) and work backward to L1. Consider all transaction signals when matching to taxonomy paths."
    )
    prioritization: str = dspy.InputField(
        desc="Suggested prioritization hint: 'supplier_primary', 'transaction_primary', 'balanced', or 'supplier_only'. Use as guidance, but make your own contextual assessment of what matters most for this transaction."
    )
    domain_context: str = dspy.InputField(
        desc="Company context (industry, sector, business_focus) from taxonomy file. Use this context to inform your understanding of the business domain - it may help narrow L1 selection when other signals are ambiguous."
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
