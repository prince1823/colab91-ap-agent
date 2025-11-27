"""DSPy signature for research agent."""

import dspy


class ResearchSignature(dspy.Signature):
    """
    Extract structured supplier information from web search results for spend classification.
    
    STRATEGY: Use supplier address if available. Prioritize first result (official website). 
    Check "Services"/"About Us" for L1. Extract address if found. Select most relevant result if multiple.
    
    Extract: industry/sector, products/services, official name, parent company, address/location.
    Also extract enhanced classification fields: service type, NAICS/SIC codes, business model, revenue streams.
    Be concise. Use "Unknown" if not found.
    
    SERVICE TYPE CLASSIFICATION:
    Classify into specific service types that map to taxonomy categories:
    - Travel: "Travel - Airlines", "Travel - Hotels", "Travel - Restaurants", "Travel - Car Rental"
    - IT: "IT - Hardware", "IT - Software", "IT - Cloud Services", "IT - Consulting", "IT - Telecom"
    - Professional Services: "Professional Services - Consulting", "Professional Services - Staffing", 
      "Professional Services - Legal", "Professional Services - Accounting"
    - Marketing: "Marketing - Agency", "Marketing - Advertising", "Marketing - Print"
    - Healthcare: "Healthcare - Clinical Supplies", "Healthcare - Pharmaceuticals", "Healthcare - Services"
    - Facilities: "Facilities - Maintenance", "Facilities - Cleaning", "Facilities - Utilities"
    - General: "General - Office Supplies", "General - Equipment", "General - Services"
    
    NAICS/SIC CODES:
    Extract standardized industry codes if available. These help with precise classification.
    Examples: NAICS "481111" (Scheduled Passenger Air Transportation), "541611" (Administrative Management Consulting)
    
    BUSINESS MODEL:
    Identify primary business model: "B2B Services", "B2C Retail", "B2B Products", "Mixed"
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
    
    # Enhanced fields for better classification
    service_type: str = dspy.OutputField(
        desc="Specific service type classification (e.g., 'Travel - Airlines', 'IT - Hardware', 'Professional Services - Consulting'). Use 'Unknown' if cannot determine."
    )
    naics_code: str = dspy.OutputField(
        desc="NAICS industry code if available (e.g., '481111', '541611'), otherwise 'Unknown'"
    )
    naics_description: str = dspy.OutputField(
        desc="NAICS code description if available, otherwise 'Unknown'"
    )
    sic_code: str = dspy.OutputField(
        desc="SIC industry code if available, otherwise 'Unknown'"
    )
    primary_business_model: str = dspy.OutputField(
        desc="Primary business model: 'B2B Services', 'B2C Retail', 'B2B Products', 'Mixed', or 'Unknown'"
    )
    primary_revenue_streams: str = dspy.OutputField(
        desc="Main revenue streams (comma-separated, e.g., 'Passenger Airfare, Cargo Services'), otherwise 'Unknown'"
    )
    service_categories: str = dspy.OutputField(
        desc="Specific service categories that map to taxonomy (comma-separated, e.g., 'Security Guard Services, Access Control'), otherwise 'Unknown'"
    )
    target_market: str = dspy.OutputField(
        desc="Target market: 'Enterprise', 'SMB', 'Consumer', 'Healthcare', 'Government', 'Mixed', or 'Unknown'"
    )
