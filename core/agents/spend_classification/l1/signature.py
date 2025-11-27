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
    - Government/Taxes: "tax", "vat", "gst", "indirect tax", "input tax", "output tax", "reverse charge", 
      "regulatory", "license", "permit", "government fee", "compliance fee", "vertex" (tax software)
    - Directors: "director", "board member", "board compensation"
    
    TAX/VAT DETECTION:
    IMPORTANT: Distinguish between standalone tax transactions vs. tax on purchases.
    
    Standalone tax transactions (classify as exceptions/government/taxes):
    - Line descriptions that are ONLY about tax: "vertex fr vat - country fr input", "ariba us tax", "vat payment"
    - GL descriptions that are ONLY about tax: "a/r indirect tax", "accrued indirect tax"
    - These are tax processing transactions, not purchases
    
    Tax on purchases (classify with underlying purchase category):
    - Line descriptions mentioning tax as part of a purchase: "utility bill - input tax recoverable", "services with VAT"
    - GL descriptions with tax terms but purchase context: "utilities - input tax"
    - These are purchases with tax included - classify as the purchase category (e.g., utilities, not tax)
    
    RULE: If tax terms appear in a purchase description (utility bill, service invoice, etc.), 
    classify with the underlying purchase category, NOT as tax exceptions.
    
    Use semantic understanding: "Payroll processing services" → exempt/exceptions (employee). 
    "Sales tax on office supplies" → NOT exempt/exceptions (see tax handling). 
    "vertex fr vat - country fr input" → exceptions/government/taxes (standalone tax transaction).
    STOP if exempt/exceptions detected.
    
    STEP 0B: TAX HANDLING
    Taxes on purchases → classify with underlying purchase category.
    Identify tax charges: sales tax, VAT, GST, use tax, excise tax, service tax.
    If tax charge: find what it's ON → classify to same category as purchase.
    If unclear what tax is on → classify to the exempt/exceptions L1 category (from STEP 0A) > taxes path.
    Only proceed if NOT exempt/exceptions and NOT tax charge.
    
    CLASSIFICATION PROCEDURE:
    
    STEP 1: IDENTIFY AND HANDLE GENERIC PAYMENT GL DESCRIPTIONS (DO THIS FIRST):
    ⚠️ CRITICAL: Many GL descriptions are generic payment/accounting terms that DO NOT indicate the actual spend category.
    These are accounting codes for HOW money moves, NOT WHAT was purchased.
    
    Generic payment GL patterns (IGNORE these for classification):
    - "t&e payable", "accounts payable", "accrued invoices", "accrued", "payable", "a/r" (accounts receivable)
    - "t&e" in GL does NOT mean travel - it's just an accounting code for payment processing
    
    RULE: When you see a generic payment GL term:
    1. IMMEDIATELY IGNORE the GL description - it's not useful for classification
    2. Look at the LINE DESCRIPTION instead - this tells you what was actually purchased
    3. If line description is also sparse, use supplier name context
    4. Only use GL description if it's specific and descriptive (e.g., "rent - misc expense", "telecommunications", "professional fees")
    
    Examples of CORRECT handling:
    - GL="t&e payable", Line="payment to card vendor", Supplier="citibank" → 
      ❌ WRONG: "travel & entertainment" (following "t&e" in GL)
      ✅ CORRECT: IGNORE "t&e payable", use Line="payment to card vendor" → "general & administrative|financial services"
    - GL="accrued invoices", Line="vertex ariba us tax" → 
      ✅ CORRECT: IGNORE "accrued invoices", use Line="vertex ariba us tax" → "exceptions|government / taxes"
    - GL="rent - misc expense", Line="" → 
      ✅ CORRECT: USE GL (specific and descriptive) → appropriate category
    
    STEP 2: DISTINGUISH ACCOUNTING REFERENCES FROM PURCHASE DESCRIPTIONS (CRITICAL):
    ⚠️ IMPORTANT: Line descriptions can be either:
    A) Descriptions of WHAT was purchased (e.g., "Surgical gloves", "Software subscription", "Consulting services")
    B) Accounting references that describe WHO the transaction is with or HOW it was processed (e.g., "Operational Journal: [entity]", "Supplier Invoice: [number]")
    
    KEY PRINCIPLE: Use semantic understanding to distinguish between:
    - Purchase descriptions: Describe products, services, or items purchased → USE for classification
    - Accounting references: Describe accounting entities, journal entries, invoice numbers, or transaction processing → DEPRIORITIZE for classification
    
    STEP 2B: DETECT MISLEADING GL DESCRIPTIONS (CRITICAL):
    ⚠️ IMPORTANT: GL codes are accounting categories used for financial reporting, NOT spend categories.
    They may not accurately reflect what was purchased.
    
    PRINCIPLE: If GL description conflicts with supplier context (name or profile), GL may be misleading.
    
    RULE: When GL conflicts with supplier context:
    1. GL may be misleading - accounting codes don't always match spend categories
    2. Prioritize supplier context (name/profile) over conflicting GL
    3. Use GL only if it aligns with supplier context or if no supplier context is available
    
    Examples:
    - GL="advertising", Supplier="clinical services company" or Supplier Profile="clinical services" →
      Analysis: GL suggests marketing, but supplier context suggests clinical services
      ❌ WRONG: "non-clinical|marketing" (following misleading GL)
      ✅ CORRECT: GL is misleading, use supplier context → "clinical|clinical services"
    
    - GL="professional fees", Supplier="consulting company" or Supplier Profile="consulting services" →
      Analysis: GL aligns with supplier context
      ✅ CORRECT: Use both GL and supplier context → "non-clinical|professional services"
    
    - GL="accounts payable" (generic), Supplier="medical supplies company" →
      Analysis: GL is generic, supplier context is specific
      ✅ CORRECT: Use supplier context → "clinical|clinical supplies"
    
    RULE: When line description appears to be an accounting reference:
    1. DO NOT infer spend category from company names or entity names mentioned in accounting references
    2. Accounting references describe WHO (the accounting entity) or HOW (processing method), not WHAT (the purchase)
    3. If line description is primarily an accounting reference, treat transaction data as sparse and rely on:
       - GL description (if specific and descriptive, not generic payment terms)
       - Supplier name context (what does the supplier actually provide?)
       - Other meaningful transaction fields
    
    Examples of CORRECT semantic understanding:
    - Line="Operational Journal: LE0033 West Colonial Physician Group, LLC - 05/20/2022", GL="telecommunications", Supplier="charter communications" →
      Analysis: Line is accounting reference (mentions accounting entity), not purchase description
      ❌ WRONG: "clinical" (inferring from "physician group" in accounting reference)
      ✅ CORRECT: Use GL="telecommunications" → "non clinical|it & telecom"
    
    - Line="Operational Journal: LE0053 Trinity Medical Physicians Services, LLC - 02/09/2022", GL="accounts payable", Supplier="mckesson medical surgical" →
      Analysis: Line is accounting reference, GL is generic payment term
      ❌ WRONG: "clinical" (inferring from "physician services" in accounting reference)
      ✅ CORRECT: Use supplier context "mckesson medical surgical" (medical supplies supplier) → "clinical|clinical supplies"
    
    - Line="Surgical gloves and medical supplies", GL="clinical supplies", Supplier="mckesson" →
      Analysis: Line is purchase description (describes what was purchased)
      ✅ CORRECT: Use line description → "clinical|clinical supplies"
    
    STEP 3: Review line description and (non-generic) GL description
    - If line description is a purchase description → use it for classification
    - If line description is an accounting reference → deprioritize it, use other fields
    
    STEP 4: If transaction data is sparse and supplier name is provided as hint:
       - Use semantic understanding of the supplier name to infer what type of service/product they provide
       - Supplier names often directly indicate their business domain (company names reflect their industry)
       - Map the inferred service/product type to the most appropriate L1 category
    
    4. Match to best L1 category from the provided list
    5. Consider transaction context (what is being purchased, not who is selling)
    
    
    SPARSE DATA HANDLING (CRITICAL):
    When transaction data is sparse (generic GL like "accounts payable", accounting references, or empty):
    
    PRINCIPLE: Supplier context (name or profile) is PRIMARY signal when transaction data is sparse.
    
    RULE: If transaction data is sparse:
    1. DO NOT default to "non-sourceable" unless transaction is clearly exempt (intercompany, payroll, etc.)
    2. Supplier name/profile is STRONG SIGNAL - use it to infer spend category
    3. Use semantic understanding to infer business domain from supplier:
       * Analyze what the supplier name/profile suggests about their business domain
       * Map that business domain to the most appropriate L1 category
       * Supplier names often directly indicate their industry (e.g., "mckesson medical" → medical supplies → clinical)
    4. Return confidence="low" to trigger supplier research for refinement (if not already done)
    5. Only use "non-sourceable" for truly exempt transactions (intercompany, payroll, taxes, etc.)
    
    Examples:
    - GL="accounts payable" (generic), Line="Operational Journal: ..." (accounting reference), Supplier="medical supplies company" →
      ✅ CORRECT: Use supplier context → "clinical" (not "non-sourceable")
    - GL="accounts payable" (generic), Line="Operational Journal: ..." (accounting reference), Supplier="pest control company" →
      ✅ CORRECT: Use supplier context → "non-clinical|facilities" (not "non-sourceable")
    - GL="accounts payable" (generic), Line="", Supplier="" →
      ✅ CORRECT: "non-clinical" with confidence="low" (most general category, not "non-sourceable")
    
    PRIORITY (IMPORTANT - READ CAREFULLY):
    1. Line description - PRIMARY source (tells you WHAT was purchased)
       ⚠️ EXCEPTION: Use semantic understanding to determine if line description is:
       - A purchase description (describes products/services purchased) → USE for classification
       - An accounting reference (describes accounting entity/processing) → DEPRIORITIZE, treat as sparse data
    2. Supplier context (name/profile) - STRONG signal, especially when GL conflicts
       ⚠️ CRITICAL: If GL conflicts with supplier context → GL may be misleading, prioritize supplier context
    3. GL description - ONLY if it's specific and descriptive AND aligns with supplier context
       ⚠️ If GL conflicts with supplier context → GL is misleading, ignore GL
    4. Generic payment GL terms (like "t&e payable", "accounts payable") - IGNORE these completely
    
    REMEMBER: 
    - "t&e payable" does NOT mean travel expenses - it's just an accounting code
    - GL codes are accounting categories, not spend categories - they may be misleading
    - If GL conflicts with supplier context, GL is likely misleading - use supplier context instead
    - Accounting references (journal entries, invoice numbers, entity names) describe WHO/HOW, not WHAT
    - Company names in accounting references do NOT indicate the spend category
    - Use semantic understanding to distinguish purchase descriptions from accounting references
    - When in doubt, prioritize fields that describe WHAT was purchased over fields that describe accounting processing
    
    EXAMPLES:
    A) Line: "Surgical gloves" → "clinical"
    B) Line: "Software subscription" → "it & telecom"
    C) Line: "Inter-company transfer" → Find exempt L1 (e.g., "exempt" or "exceptions") → "exempt" OR "exceptions"
    D) Line: "Payroll processing fees" → Find exempt L1 → "exempt" OR "exceptions"
    E) Line: "Sales tax on office supplies" → "non-clinical" (tax with purchase)
    F) Line: "State sales tax" (unclear) → Find exempt L1 → "exempt" OR "exceptions"
    G) Line: "Purchase of 5 Dell laptops" → "it & telecom"
    H) Line: "", GL: "rent - misc expense" → "non-clinical"
    I) Line: "vertex fr vat - country fr input", GL: "a/r indirect tax" → Find exceptions L1 → "exceptions" (standalone tax transaction)
    J) Line: "vertex ariba us tax", GL: "accrued invoices" → Find exceptions L1 → "exceptions" (tax transaction, ignore generic "accrued invoices")
    K) Line: "payment to card vendor", GL: "t&e payable", Supplier: "citibank" → "general & administrative" (GL is generic payment term, prioritize line description + supplier context)
    """
    
    transaction_data: str = dspy.InputField(
        desc="Transaction details (GL description, line description). If transaction data is sparse (generic GL, accounting references, or empty), use supplier name/profile context as PRIMARY signal to infer spend category. Supplier names and profiles directly indicate business domain and should be prioritized when transaction descriptions are missing or generic."
    )
    supplier_profile: str = dspy.InputField(
        desc="Optional supplier profile information (industry, products/services, service_type). Use this when transaction data is sparse to infer the spend category. If provided, this is a STRONG signal for classification when transaction data is generic or missing."
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

