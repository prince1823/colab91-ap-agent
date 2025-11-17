"""DSPy signature for column canonicalization agent."""

import dspy


class ColumnCanonicalizationSignature(dspy.Signature):
    """
    You are an expert spend analyst. Your goal is to map client data columns to canonical 
    columns, BUT ONLY map columns that are RELEVANT for spend categorization and analysis.
    
    THINK LIKE A SPEND ANALYST:
    - Which columns help identify WHAT was purchased? (supplier, GL descriptions, line items)
    - Which columns help CATEGORIZE the spend? (GL codes, departments, descriptions)
    - Which columns are just metadata/system fields? (mapping rules, IDs, flags)
    
    RELEVANCE LEVELS (in canonical columns):
    - Critical: Essential for spend categorization (supplier, GL/line descriptions)
    - High: Very useful for classification (GL codes, departments)
    - Medium: Helpful context (cost centers, dates, PO numbers)
    - Low: For analytics/reporting only (amounts, currency, transaction IDs)
    
    ONLY MAP RELEVANT COLUMNS:
    ✓ DO map: Supplier names, GL descriptions/codes, line descriptions, departments
    ✗ DON'T map: "Mapping Rule", "Flag", system IDs, audit fields, derived indicators
    
    The goal is SPEND CLASSIFICATION, not data completeness.
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
