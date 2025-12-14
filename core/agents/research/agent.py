"""Research agent for supplier profiles."""

import json
import logging
from typing import Any, Dict, Optional, Tuple

import dspy
from openai import OpenAI

from core.config import get_config
from core.llms.llm import get_llm_for_agent
from core.utils.infrastructure.mlflow import setup_mlflow_tracing
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
        
        # Store LM for thread-safe context usage instead of configure
        self.lm = lm
        
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
        """
        Exa search that returns structured JSON.
        
        Raises:
            RuntimeError: If Exa client is not available or API call fails
        """
        if not self.exa_client:
            raise RuntimeError(
                "Exa client is not initialized. Please configure EXA_API_KEY."
            )
        
        # Build search query with address if available
        search_query = supplier_name
        if supplier_address:
            search_query = f"{supplier_name} {supplier_address}"
        
        fields = "supplier_name, official_business_name, description, website_url, industry, products_services, parent_company, supplier_address, service_type, naics_code, naics_description, sic_code, primary_business_model, primary_revenue_streams, service_categories, target_market"
        prompt = f"""You MUST return ONLY valid JSON, no explanatory text. Extract the following information about "{search_query}" company.

Required fields: {fields}

INSTRUCTIONS:
- Return ONLY a valid JSON object with the requested fields
- Use "Unknown" for any fields you cannot determine
- For service_type, use specific categories like 'Travel - Airlines', 'IT - Hardware', 'Professional Services - Consulting'
- Extract NAICS/SIC codes if available
- If supplier address is provided, use it for more accurate results
- If this is a government agency or public sector organization, set industry to "Government/Public Sector" and provide available information
- ALWAYS return valid JSON, even if information is limited

JSON format: {{"supplier_name": "...", "official_business_name": "...", "description": "...", ...}}"""
        
        try:
            completion = self.exa_client.chat.completions.create(
                model=self.exa_model,
                messages=[{"role": "user", "content": prompt}],
                stream=False,
            )
            
            if not completion.choices:
                raise RuntimeError(
                    f"Exa API returned no results for supplier '{supplier_name}'. "
                    f"This may indicate an API issue or insufficient credits."
                )
            
            raw_content = completion.choices[0].message.content or ""
            
            if not raw_content:
                raise RuntimeError(
                    f"Exa API returned empty content for supplier '{supplier_name}'. "
                    f"This may indicate an API issue."
                )
            
            # First try to extract JSON (handles code fences and plain JSON)
            parsed = _extract_json_object(raw_content)
            
            # If extraction succeeded, return the parsed JSON
            if parsed is not None:
                return parsed
            
            # Try direct JSON parsing as fallback
            try:
                return json.loads(raw_content)
            except json.JSONDecodeError:
                pass
            
            # Only if both JSON extraction methods failed, check for error messages
            raw_lower = raw_content.lower()
            if any(phrase in raw_lower for phrase in [
                "unable to provide", "cannot provide", "do not have the functionality",
                "i am sorry", "i cannot", "unable to provide the information",
                "i don't have", "i do not have"
            ]):
                # Exa returned a text explanation instead of JSON
                # Return minimal structured data instead of failing
                logger.warning(
                    f"Exa API returned non-JSON response for supplier '{supplier_name}'. "
                    f"Using minimal supplier profile. Response: {raw_content[:150]}..."
                )
                return {
                    "supplier_name": supplier_name,
                    "official_business_name": supplier_name,
                    "description": "Information not available",
                    "industry": "Unknown",
                    "products_services": "Unknown",
                    "confidence": "low"
                }
            
            # If we get here, JSON parsing failed but no error message detected
            raise RuntimeError(
                f"Exa API returned invalid JSON for supplier '{supplier_name}'. "
                f"Raw content: {raw_content[:200]}..."
            )
        except RuntimeError:
            # Re-raise RuntimeErrors as-is
            raise
        except Exception as e:
            # Wrap other exceptions with context
            error_msg = str(e)
            if "402" in error_msg or "credit" in error_msg.lower() or "insufficient" in error_msg.lower():
                raise RuntimeError(
                    f"Exa API credit limit reached or insufficient credits for supplier '{supplier_name}'. "
                    f"Please check your Exa API account and add credits. Original error: {error_msg}"
                ) from e
            elif "401" in error_msg or "403" in error_msg or "unauthorized" in error_msg.lower():
                raise RuntimeError(
                    f"Exa API authentication failed for supplier '{supplier_name}'. "
                    f"Please check your EXA_API_KEY. Original error: {error_msg}"
                ) from e
            else:
                raise RuntimeError(
                    f"Exa search failed for supplier '{supplier_name}': {error_msg}. "
                    f"Please check your Exa API configuration and account status."
                ) from e
    
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
        Research supplier and extract structured information using Exa.
        
        Args:
            supplier_name: Name of supplier to research
            supplier_address: Optional supplier address/location for more accurate search
            search_results: Deprecated - no longer used (Exa is required)
            
        Returns:
            SupplierProfile with extracted information
            
        Raises:
            RuntimeError: If Exa is not available or search fails
        """
        logger.info(f"Starting supplier research for: {supplier_name}")

        # Exa is required - raise error if not available
        if not self.use_exa or not self.exa_client:
            raise RuntimeError(
                "Exa API is required for supplier research but is not available. "
                "Please configure EXA_API_KEY in your environment or config file."
            )
        
        # Get structured data from Exa (will raise error if it fails)
        exa_data = self._exa_search(supplier_name, supplier_address)
        
        # Handle case where Exa returns a list instead of dict
        if isinstance(exa_data, list) and len(exa_data) > 0:
            exa_data = exa_data[0]  # Use first element
        
        if not isinstance(exa_data, dict):
            # Exa search returned invalid format
            raise RuntimeError(
                f"Exa search returned invalid data format for supplier '{supplier_name}'. "
                f"Expected dict or list, got {type(exa_data)}. "
                f"Please check your Exa API configuration."
            )
        
        # Exa returns structured JSON, use it directly
        # Extract supplier_address from search results if found, otherwise use provided address
        found_address = exa_data.get("supplier_address")
        if found_address and found_address is not None and str(found_address).strip().lower() not in ["unknown", "none", ""]:
            final_address = found_address
        else:
            final_address = supplier_address
        
        # Detect large company - handle None values properly
        description = exa_data.get("description") or "Unknown"
        industry = exa_data.get("industry") or "Unknown"
        # Ensure they're strings (in case Exa returns other types)
        description = str(description) if description else "Unknown"
        industry = str(industry) if industry else "Unknown"
        is_large_company, company_size = self._detect_large_company(description, industry)
        
        # Helper function to normalize optional fields from Exa data
        def get_exa_field(key: str, default: Optional[str] = None) -> Optional[str]:
            value = exa_data.get(key)
            if value and str(value).strip().lower() not in ["unknown", "none", ""]:
                return str(value).strip()
            return default
        
        # Handle supplier_name - ensure it's never None
        supplier_name_from_exa = exa_data.get("supplier_name")
        final_supplier_name = str(supplier_name_from_exa) if supplier_name_from_exa else str(supplier_name)
        
        # Handle other required fields with None safety
        official_name = exa_data.get("official_business_name") or "Unknown"
        products_services = exa_data.get("products_services") or "Unknown"
        
        return SupplierProfile(
            supplier_name=final_supplier_name,
            official_business_name=str(official_name),
            description=description,
            website_url=get_exa_field("website_url"),
            industry=industry,
            products_services=str(products_services),
            parent_company=get_exa_field("parent_company"),
            confidence="high",  # Exa provides structured data, so confidence is high
            supplier_address=final_address,
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
    
    def __call__(self, supplier_name: str, supplier_address: Optional[str] = None, search_results: str = None) -> SupplierProfile:
        """Research supplier and return structured profile."""
        return self.research_supplier(supplier_name, supplier_address, search_results)
