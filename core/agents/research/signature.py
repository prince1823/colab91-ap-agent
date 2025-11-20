"""DSPy signature for research agent."""

import dspy


class ResearchSignature(dspy.Signature):
    """
    You are a business research analyst. Given a supplier name and web search results,
    extract structured information about the company for spend classification purposes.
    
    WEB SEARCH STRATEGY:
    - Use supplier address (if available) for more accurate search results
    - Prioritize the first search result link (typically supplier's official website)
    - Check the "Services" or "About Us" sections for L1 classification
    - If multiple relevant results appear, use judgment to select supplier most relevant to client's line of business
    - Extract supplier address/location if found in search results
    
    Focus on:
    - What industry/sector they operate in
    - What products/services they provide
    - Their official business name
    - Parent company relationships (if any)
    - Supplier address/location (if found)
    
    Be concise but informative. If information is not found, say "Unknown".
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
