"""DSPy signature for research decision agent."""

import dspy


class ResearchDecisionSignature(dspy.Signature):
    """
    Determine if supplier research is needed to improve classification accuracy.
    
    Research helps when:
    - Transaction data is sparse or unhelpful (dates, generic terms, accounting codes)
    - L1 classification confidence is low or medium
    - Transaction data doesn't provide enough context for accurate classification
    - Supplier name might provide valuable context that transaction data lacks
    
    Research is NOT needed when:
    - Transaction data is rich and specific (clear line descriptions, detailed GL codes)
    - L1 classification confidence is high and transaction data supports it
    - Transaction clearly indicates what was purchased without needing supplier context
    
    Use semantic understanding to assess data quality and classification confidence.
    """
    
    supplier_name: str = dspy.InputField(
        desc="Supplier name (may provide context if transaction data is sparse)"
    )
    transaction_data: str = dspy.InputField(
        desc="Transaction details (line description, GL description, department)"
    )
    l1_category: str = dspy.InputField(
        desc="L1 category from preliminary classification"
    )
    l1_confidence: str = dspy.InputField(
        desc="L1 classification confidence: 'high', 'medium', or 'low'"
    )
    
    should_research: str = dspy.OutputField(
        desc="'yes' if research is needed, 'no' if not needed"
    )
    reasoning: str = dspy.OutputField(
        desc="Brief explanation of why research is or isn't needed"
    )

