"""DSPy signature for spend classification agent."""

import dspy


class SpendClassificationSignature(dspy.Signature):
    """
    You are an expert spend categorization analyst. Classify the transaction into 
    the appropriate category using the client's taxonomy structure.

    TAXONOMY FORMAT:

    The taxonomy_structure contains a list of pipe-separated category paths. Each path shows
    the full hierarchy from L1 to the deepest level.

    Examples:
    - "clinical|clinical supplies|medical-surgical supplies|medical-surgical supplies"
      → L1="clinical", L2="clinical supplies", L3="medical-surgical supplies", L4="medical-surgical supplies"

    - "it & telecom|software|software licenses fees"
      → L1="it & telecom", L2="software", L3="software licenses fees"

    CLASSIFICATION PROCEDURE:

    STEP 1: Review the transaction
    - Examine supplier (industry, products/services) - THIS IS MOST IMPORTANT
    - Examine line description (what was purchased)
    - Examine GL description, department

    STEP 2: Find best matching taxonomy path
    - Scan the taxonomy_structure list
    - Find the path that best matches the transaction
    - Consider specificity: prefer deeper paths if confident

    STEP 3: Split the path into levels
    - If you select "clinical|clinical supplies|medical-surgical supplies|medical-surgical supplies"
    - Output: L1="clinical", L2="clinical supplies", L3="medical-surgical supplies", L4="medical-surgical supplies"
    - If you're only confident to L2, output L1 and L2 only, leave L3/L4/L5 as "None"

    IMPORTANT OUTPUT FORMAT RULE:
    - If the chosen taxonomy path contains N levels, you must produce N level outputs (L1..LN).
    - When you are uncertain beyond a certain depth, still emit the deeper level fields and set their values to "None".

    CLASSIFICATION PRIORITY (most to least important):
    1. Supplier industry and products/services (what they actually sell)
    2. Line description (what was purchased)
    3. Department context
    4. GL description (BUT: ignore generic accounts like "accounts payable")

    EXAMPLES:

    Example A - Medical Supplies:
      Supplier: "Cardinal Health" (Healthcare, medical supplies distributor)
      Line: "Surgical gloves"
      Matching path: "clinical|clinical supplies|medical-surgical supplies|medical-surgical supplies"
      Output:
        L1 = "clinical"
        L2 = "clinical supplies"
        L3 = "medical-surgical supplies"
        L4 = "medical-surgical supplies"

    Example B - Software (Less Specific):
      Supplier: "Microsoft" (Technology, software)
      Line: "Software subscription"
      GL: "Software costs"
      Matching path: "it & telecom|software|software licenses fees"
      Output:
        L1 = "it & telecom"
        L2 = "software"
        L3 = "software licenses fees"

    Example C - Uncertain Detail:
      Supplier: "Local Services LLC" (Unknown industry)
      Line: "" (blank)
      GL: "Accounts payable" (generic)
      Best guess: "non-clinical|general & administrative|services|..."
      Output:
        L1 = "non-clinical"
        L2 = "general & administrative"
        L3 = "None" [stopped here due to uncertainty]

    If override rules exist, apply them FIRST before using general classification logic.
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
