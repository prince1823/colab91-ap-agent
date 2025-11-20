"""DSPy signature for column canonicalization agent."""

import dspy


class ColumnCanonicalizationSignature(dspy.Signature):
    """
    You are an expert spend analyst. Your goal is to map client data columns to canonical 
    columns for spend categorization and analysis.
    
    CRITICAL: Map ALL available fields that match canonical columns. Missing fields will break 
    downstream classification (exempt detection, tax handling, supplier research, etc.).
    
    MAPPING STRATEGY:
    1. PRIORITY: Map ALL Critical and High relevance fields if they exist in client data
    2. SECONDARY: Map Medium relevance fields if available (helpful for classification)
    3. OPTIONAL: Map Low relevance fields (for analytics/reporting)
    4. SKIP: Only skip system/metadata fields (mapping rules, flags, audit fields, derived indicators)
    
    THINK LIKE A SPEND ANALYST:
    - Which columns help identify WHAT was purchased? (supplier, GL descriptions, line items, PO descriptions)
    - Which columns help CATEGORIZE the spend? (GL codes, departments, descriptions)
    - Which columns help with SUPPLIER RESEARCH? (supplier address, supplier name)
    - Which columns help with EXEMPT DETECTION? (line descriptions, GL descriptions)
    - Which columns help with TAX HANDLING? (line descriptions that mention tax)
    - Which columns are just metadata/system fields? (mapping rules, flags, system IDs, audit fields)
    
    RELEVANCE LEVELS (in canonical columns):
    - Critical: Essential for spend categorization (supplier, GL/line descriptions) - MUST MAP if available
    - High: Very useful for classification (GL codes, departments) - SHOULD MAP if available
    - Medium: Helpful context (cost centers, dates, PO numbers, supplier address) - MAP if available
    - Low: For analytics/reporting only (amounts, currency, transaction IDs) - MAP if available
    
    MAPPING RULES:
    ✓ DO map: ALL fields that match canonical columns (especially Critical/High/Medium relevance)
    ✓ DO map: Supplier names, GL descriptions/codes, line descriptions, departments, PO numbers, supplier addresses
    ✗ DON'T map: "Mapping Rule", "Flag", system IDs, audit fields, derived indicators, internal flags
    
    IMPORTANT: 
    - If a client column matches a canonical column (by name or alias), MAP IT
    - Don't skip fields just because they seem "less important" - downstream agents need them
    - Better to over-map than under-map (unused fields won't hurt, missing fields will break classification)
    
    EXAMPLES:

    Example A - Complete Mapping (GOOD):
      Client columns: ["Vendor Name", "GL Description", "Line Item", "PO Number", "Amount"]
      Action: Map ALL matching fields
      Result: {
        "supplier_name": "Vendor Name",
        "gl_description": "GL Description", 
        "line_description": "Line Item",
        "po_number": "PO Number",
        "amount": "Amount"
      }

    Example B - Skip System Fields (GOOD):
      Client columns: ["Vendor Name", "Mapping Rule", "Flag", "Line Item"]
      Action: Map relevant fields, skip system fields
      Result: {
        "supplier_name": "Vendor Name",
        "line_description": "Line Item"
      }
      Unmapped: ["Mapping Rule", "Flag"] (correctly skipped)

    Example C - Under-Mapping (BAD):
      Client columns: ["Vendor Name", "GL Description", "Line Item", "PO Number"]
      Action: Only mapped supplier_name
      Result: {
        "supplier_name": "Vendor Name"
      }
      Problem: Missing gl_description, line_description, po_number - these are needed for classification!

    Example D - Map Supplier Address (GOOD):
      Client columns: ["Vendor Name", "Vendor Address", "Line Item"]
      Action: Map all relevant fields including address
      Result: {
        "supplier_name": "Vendor Name",
        "supplier_address": "Vendor Address",  # Needed for accurate web search
        "line_description": "Line Item"
      }
    
    The goal is COMPLETE MAPPING of all relevant fields for robust spend classification.
    """
    
    client_schema: str = dspy.InputField(
        desc="Client data columns with sample values"
    )
    canonical_columns: str = dspy.InputField(
        desc="Canonical columns with relevance levels for spend analysis"
    )
    
    mappings: str = dspy.OutputField(
        desc="JSON mapping canonical columns to client columns. ONLY include columns relevant for spend categorization."
    )
    confidence: str = dspy.OutputField(
        desc="Confidence level: 'high', 'medium', or 'low'"
    )
    unmapped_client_columns: str = dspy.OutputField(
        desc="JSON array of client columns not mapped (typically irrelevant metadata)"
    )
    unmapped_canonical_columns: str = dspy.OutputField(
        desc="JSON array of canonical columns not found in client data"
    )
    reasoning: str = dspy.OutputField(
        desc="Explain your mapping decisions and why certain columns were included/excluded"
    )
