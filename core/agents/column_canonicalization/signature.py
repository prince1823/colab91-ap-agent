"""DSPy signature for column canonicalization agent."""

import dspy


class ColumnCanonicalizationSignature(dspy.Signature):
    """
    Map client data columns to canonical columns for spend classification.
    
    CRITICAL: Map ALL available fields matching canonical columns. Missing fields break downstream classification.
    
    MAPPING STRATEGY:
    1. Map ALL Critical/High fields if available
    2. Map Medium/Low fields if available  
    3. Skip ONLY system/metadata fields (mapping rules, flags, audit fields, derived indicators)
    
    RELEVANCE LEVELS:
    - Critical: supplier, GL/line descriptions - MUST MAP
    - High: GL codes, departments - SHOULD MAP
    - Medium: cost centers, dates, PO numbers, supplier address - MAP if available
    - Low: amounts, currency, transaction IDs - MAP if available
    
    ADDRESS FIELD MAPPING:
    - Map ONE primary address field to supplier_address (prefer complete addresses over components)
    - If a complete "Supplier Address" or "Vendor Address" field exists, map it to supplier_address
    - If only address components exist (Address 1, City, State, etc.), map the most complete field (prefer Address 1/Address over City/State alone)
    - DO NOT map multiple fields to the same canonical column - map only ONE field per canonical column
    
    MAPPING RULES:
    ✓ Map: ALL matching fields (especially Critical/High/Medium)
    ✗ Skip: "Mapping Rule", "Flag", system IDs, audit fields, derived indicators
    
    IMPORTANT: If a client column matches canonical (by name/alias), MAP IT. Better to over-map than under-map.
    
    EXAMPLES:
    A) ["Vendor Name", "GL Description", "Line Item", "PO Number"] → Map all
    B) ["Vendor Name", "Mapping Rule", "Flag"] → Map supplier_name, skip system fields
    C) ["Vendor Name", "GL Description", "Line Item"] → Map all (under-mapping breaks classification)
    D) ["Vendor Name", "Vendor Address", "Line Item"] → Map all including supplier_address
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
        desc="JSON array of client columns not mapped. Split into two categories: 1) Important columns (preserve) - columns that contain useful information for classification even if no canonical match (e.g., project codes, cost centers, transaction categories, department codes, region/territory info, custom classification fields). 2) Unimportant columns (skip) - system/metadata fields, mapping rules, flags, audit fields, derived indicators."
    )
    important_unmapped_columns: str = dspy.OutputField(
        desc="JSON array of important client columns that should be preserved even though they don't map to canonical columns. These are columns with potentially useful information for classification (e.g., project codes, cost centers, transaction categories, department codes, region/territory info, custom classification fields, business unit codes). Exclude system/metadata fields."
    )
    unmapped_canonical_columns: str = dspy.OutputField(
        desc="JSON array of canonical columns not found in client data"
    )
    reasoning: str = dspy.OutputField(
        desc="Explain your mapping decisions and why certain columns were included/excluded"
    )
