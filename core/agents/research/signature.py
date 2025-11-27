"""DSPy signature for research agent."""

import dspy


class ResearchSignature(dspy.Signature):
    """
    Extract structured supplier information from web search results for spend classification.
    
    STRATEGY: Use supplier address if available. Prioritize first result (official website). 
    Check "Services"/"About Us" for L1. Extract address if found. Select most relevant result if multiple.
    
    Extract: industry/sector, products/services, official name, parent company, address/location.
    Be concise. Use "Unknown" if not found.
    """
    
    supplier_name: str = dspy.InputField(
        desc="Supplier name to research"
    )
    search_results: str = dspy.InputField(
        desc="Web search results about the supplier"
    )
    
    official_business_name: str = dspy.OutputField(
        desc="Official registered business name of the company"
    )
    description: str = dspy.OutputField(
        desc="Brief 2-3 sentence description of what the company does"
    )
    website_url: str = dspy.OutputField(
        desc="Official company website URL (just the domain, e.g., 'https://example.com')"
    )
    industry: str = dspy.OutputField(
        desc="Primary industry or sector (e.g., 'Technology', 'Healthcare', 'Manufacturing')"
    )
    products_services: str = dspy.OutputField(
        desc="Main products or services offered (brief, comma-separated)"
    )
    parent_company: str = dspy.OutputField(
        desc="Parent company name if this is a subsidiary, otherwise 'None'"
    )
    confidence: str = dspy.OutputField(
        desc="Research confidence: 'high' (found official info), 'medium' (partial info), or 'low' (limited/no info)"
    )
    supplier_address: str = dspy.OutputField(
        desc="Supplier address/location if found in search results, otherwise 'Unknown'"
    )
    sources: list = dspy.OutputField(
        desc="List of source URLs used for the research"
    )
