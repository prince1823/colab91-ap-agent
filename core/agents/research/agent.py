"""Research agent for supplier profiles."""

import json
import logging
from typing import Any, Dict, Optional, Tuple

import dspy
from openai import OpenAI

from core.config import get_config
from core.llms.llm import get_llm_for_agent
from core.utils.mlflow import setup_mlflow_tracing
from core.agents.research.signature import ResearchSignature
from core.agents.research.model import SupplierProfile

logger = logging.getLogger(__name__)


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Parse JSON from raw model output, handling code fences."""
    if not text:
        return None
    
    cleaned = text.strip()
    
    # Remove code fences if present (Exa wraps JSON in ```json ... ```)
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines:
            # Remove first line (```json or ```)
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            # Remove last line (```)
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.debug(f"Failed to parse JSON from text: {e}")
        return None


class ResearchAgent:
    """Agent that researches suppliers using Exa or other search tools."""
    
    def __init__(
        self,
        lm: Optional[dspy.LM] = None,
        *,
        use_exa: Optional[bool] = None,
        enable_tracing: bool = True,
    ):
        """
        Initialize Research Agent
        
        Args:
            lm: DSPy language model (if None, uses config for this agent)
            use_exa: Force enabling/disabling Exa integration (defaults to True when EXA_API_KEY is set)
            enable_tracing: Whether to enable MLflow tracing (default: True)
        """
        # Setup MLflow tracing if enabled
        if enable_tracing:
            setup_mlflow_tracing(experiment_name="research")
        
        config = get_config()
        
        if lm is None:
            lm = get_llm_for_agent("research")
        
        dspy.configure(lm=lm)
        
        # Create DSPy predictor
        self.researcher = dspy.ChainOfThought(ResearchSignature)
        
        # Initialize Exa client if available
        exa_key = config.exa_api_key
        self.exa_model = config.exa_model
        self.exa_client: Optional[OpenAI] = None
        
        enable_exa = use_exa if use_exa is not None else bool(exa_key)
        self.use_exa = enable_exa and bool(exa_key)
        
        if self.use_exa:
            try:
                self.exa_client = OpenAI(
                    base_url=config.exa_base_url,
                    api_key=exa_key,
                )
            except Exception as e:
                logger.warning(f"Failed to initialize Exa client: {e}")
                self.exa_client = None
                self.use_exa = False
    
    def _exa_search(self, supplier_name: str, supplier_address: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Exa search that returns structured JSON."""
        if not self.exa_client:
            return None
        
        # Build search query with address if available
        search_query = supplier_name
        if supplier_address:
            search_query = f"{supplier_name} {supplier_address}"
        
        fields = "supplier_name, official_business_name, description, website_url, industry, products_services, parent_company, supplier_address, service_type, naics_code, naics_description, sic_code, primary_business_model, primary_revenue_streams, service_categories, target_market"
        prompt = f"Get the following information about {search_query} company in json format - {fields}. Use supplier address if available for more accurate search results. For service_type, classify into specific categories like 'Travel - Airlines', 'IT - Hardware', 'Professional Services - Consulting', etc. Extract NAICS/SIC codes if available."
        
        try:
            completion = self.exa_client.chat.completions.create(
                model=self.exa_model,
                messages=[{"role": "user", "content": prompt}],
                stream=False,
            )
            
            if not completion.choices:
                return None
            
            raw_content = completion.choices[0].message.content or ""
            
            # Try direct JSON parsing first (most common case)
            try:
                return json.loads(raw_content)
            except json.JSONDecodeError:
                # If direct parsing fails, use extraction function for code fences or extra text
                return _extract_json_object(raw_content)
        except Exception as e:
            logger.warning(f"Exa search failed for {supplier_name}: {e}")
            return None
    
    def _detect_large_company(self, description: str, industry: str) -> Tuple[bool, Optional[str]]:
        """
        Detect if company is very large based on description and industry.
        
        Args:
            description: Company description
            industry: Industry sector
            
        Returns:
            Tuple of (is_large_company, company_size)
        """
        description_lower = description.lower()
        industry_lower = industry.lower()
        
        # Keywords that suggest large companies
        large_company_keywords = [
            'fortune 500', 'fortune 1000', 'multinational', 'global', 'enterprise',
            'conglomerate', 'publicly traded', 'public company', 'nyse', 'nasdaq',
            'revenue', 'employees', 'headquarters', 'subsidiaries'
        ]
        
        # Check description for large company indicators
        is_large = any(keyword in description_lower for keyword in large_company_keywords)
        
        # Check for specific large company patterns
        if any(term in description_lower for term in ['thousands of employees', 'millions in revenue', 'billion']):
            return True, 'enterprise'
        
        if is_large:
            return True, 'large'
        
        return False, None
    
    def research_supplier(self, supplier_name: str, supplier_address: Optional[str] = None, search_results: str = None) -> SupplierProfile:
        """
        Research supplier and extract structured information
        
        Args:
            supplier_name: Name of supplier to research
            supplier_address: Optional supplier address/location for more accurate search
            search_results: Optional pre-fetched search results (only used if not using Exa)
            
        Returns:
            SupplierProfile with extracted information
        """
        # If using Exa, get structured data directly from Exa
        if self.use_exa:
            exa_data = self._exa_search(supplier_name, supplier_address)
            
            # Handle case where Exa returns a list instead of dict
            if isinstance(exa_data, list) and len(exa_data) > 0:
                exa_data = exa_data[0]  # Use first element
            elif not isinstance(exa_data, dict):
                exa_data = None  # Invalid format, fall back to LLM
            
            if exa_data and isinstance(exa_data, dict):
                # Exa returns structured JSON, use it directly
                # Extract supplier_address from search results if found, otherwise use provided address
                found_address = exa_data.get("supplier_address")
                if found_address and found_address.lower() not in ["unknown", "none", ""]:
                    final_address = found_address
                else:
                    final_address = supplier_address
                
                # Detect large company
                description = exa_data.get("description", "Unknown")
                industry = exa_data.get("industry", "Unknown")
                is_person = False  # Person detection removed
                is_large_company, company_size = self._detect_large_company(description, industry)
                
                # Helper function to normalize optional fields from Exa data
                def get_exa_field(key: str, default: Optional[str] = None) -> Optional[str]:
                    value = exa_data.get(key)
                    if value and str(value).strip().lower() not in ["unknown", "none", ""]:
                        return str(value).strip()
                    return default
                
                return SupplierProfile(
                    supplier_name=exa_data.get("supplier_name", supplier_name),
                    official_business_name=exa_data.get("official_business_name", "Unknown"),
                    description=description,
                    website_url=get_exa_field("website_url"),
                    industry=industry,
                    products_services=exa_data.get("products_services", "Unknown"),
                    parent_company=get_exa_field("parent_company"),
                    confidence="high",  # Exa provides structured data, so confidence is high
                    supplier_address=final_address,
                    is_person=is_person,
                    is_large_company=is_large_company,
                    company_size=company_size,
                    # Enhanced fields
                    service_type=get_exa_field("service_type"),
                    naics_code=get_exa_field("naics_code"),
                    naics_description=get_exa_field("naics_description"),
                    sic_code=get_exa_field("sic_code"),
                    primary_business_model=get_exa_field("primary_business_model"),
                    primary_revenue_streams=get_exa_field("primary_revenue_streams"),
                    service_categories=get_exa_field("service_categories"),
                    target_market=get_exa_field("target_market"),
                )
            
        
        # If not using Exa, use LLM to extract from search results
        if search_results is None:
            search_results = "No search results found."
        
        # Extract structured information using LLM
        result = self.researcher(
            supplier_name=supplier_name,
            search_results=search_results
        )
        
        # Extract supplier_address from LLM result if available
        supplier_addr = None
        if hasattr(result, 'supplier_address'):
            addr_value = getattr(result, 'supplier_address', None)
            if addr_value and str(addr_value).strip().lower() not in ["unknown", "none", ""]:
                supplier_addr = str(addr_value).strip()
        # Fallback to provided address if LLM didn't find one
        if not supplier_addr:
            supplier_addr = supplier_address
        
        # Detect large company
        description = result.description
        industry = result.industry
        is_person = False  # Person detection removed
        is_large_company, company_size = self._detect_large_company(description, industry)
        
        # Helper function to normalize optional fields from LLM result
        def get_llm_field(field_name: str, default: Optional[str] = None) -> Optional[str]:
            if not hasattr(result, field_name):
                return default
            value = getattr(result, field_name, None)
            if value and str(value).strip().lower() not in ["unknown", "none", ""]:
                return str(value).strip()
            return default
        
        # Create supplier profile from LLM result
        return SupplierProfile(
            supplier_name=supplier_name,
            official_business_name=result.official_business_name,
            description=description,
            website_url=get_llm_field("website_url"),
            industry=industry,
            products_services=result.products_services,
            parent_company=get_llm_field("parent_company"),
            confidence=result.confidence.lower().strip(),
            supplier_address=supplier_addr,
            is_person=is_person,
            is_large_company=is_large_company,
            company_size=company_size,
            # Enhanced fields
            service_type=get_llm_field("service_type"),
            naics_code=get_llm_field("naics_code"),
            naics_description=get_llm_field("naics_description"),
            sic_code=get_llm_field("sic_code"),
            primary_business_model=get_llm_field("primary_business_model"),
            primary_revenue_streams=get_llm_field("primary_revenue_streams"),
            service_categories=get_llm_field("service_categories"),
            target_market=get_llm_field("target_market"),
        )
    
    def __call__(self, supplier_name: str, supplier_address: Optional[str] = None, search_results: str = None) -> SupplierProfile:
        """Research supplier and return structured profile."""
        return self.research_supplier(supplier_name, supplier_address, search_results)
