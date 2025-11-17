"""Research agent for supplier profiles."""

import json
from typing import Any, Dict, Optional

import dspy
from openai import OpenAI

from core.config import get_config
from core.llms.llm import get_llm_for_agent
from core.utils.mlflow import setup_mlflow_tracing
from core.agents.research.signature import ResearchSignature
from core.agents.research.model import SupplierProfile


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
    except json.JSONDecodeError:
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
            except Exception:
                self.exa_client = None
                self.use_exa = False
    
    def _exa_search(self, supplier_name: str) -> Optional[Dict[str, Any]]:
        """Exa search that returns structured JSON."""
        if not self.exa_client:
            return None
        
        fields = "supplier_name, official_business_name, description, website_url, industry, products_services, parent_company"
        prompt = f"Get the following information about {supplier_name} company in json format - {fields}"
        
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
        except Exception:
            return None
    
    def research_supplier(self, supplier_name: str, search_results: str = None) -> SupplierProfile:
        """
        Research supplier and extract structured information
        
        Args:
            supplier_name: Name of supplier to research
            search_results: Optional pre-fetched search results (only used if not using Exa)
            
        Returns:
            SupplierProfile with extracted information
        """
        # If using Exa, get structured data directly from Exa
        if self.use_exa:
            exa_data = self._exa_search(supplier_name)
            
            if exa_data:
                # Exa returns structured JSON, use it directly
                return SupplierProfile(
                    supplier_name=exa_data.get("supplier_name", supplier_name),
                    official_business_name=exa_data.get("official_business_name", "Unknown"),
                    description=exa_data.get("description", "Unknown"),
                    website_url=exa_data.get("website_url") if exa_data.get("website_url") and exa_data.get("website_url").lower() not in ["unknown", "none", ""] else None,
                    industry=exa_data.get("industry", "Unknown"),
                    products_services=exa_data.get("products_services", "Unknown"),
                    parent_company=exa_data.get("parent_company") if exa_data.get("parent_company") and exa_data.get("parent_company").lower() not in ["unknown", "none", ""] else None,
                    confidence="high",  # Exa provides structured data, so confidence is high
                )
            else:
                # Exa failed, return minimal profile
                return SupplierProfile(
                    supplier_name=supplier_name,
                    official_business_name="Unknown",
                    description="No information found",
                    website_url=None,
                    industry="Unknown",
                    products_services="Unknown",
                    parent_company=None,
                    confidence="low",
                )
        
        # If not using Exa, use LLM to extract from search results
        if search_results is None:
            search_results = "No search results found."
        
        # Extract structured information using LLM
        result = self.researcher(
            supplier_name=supplier_name,
            search_results=search_results
        )
        
        # Create supplier profile from LLM result
        return SupplierProfile(
            supplier_name=supplier_name,
            official_business_name=result.official_business_name,
            description=result.description,
            website_url=result.website_url if result.website_url.lower() != "unknown" else None,
            industry=result.industry,
            products_services=result.products_services,
            parent_company=result.parent_company if result.parent_company.lower() not in ["none", "unknown"] else None,
            confidence=result.confidence.lower().strip(),
        )
    
    def __call__(self, supplier_name: str, search_results: str = None) -> SupplierProfile:
        """Research supplier and return structured profile."""
        return self.research_supplier(supplier_name, search_results)
