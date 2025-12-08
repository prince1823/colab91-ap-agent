"""Data models for research agent."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SupplierProfile:
    """Structured supplier information from research"""
    
    supplier_name: str
    official_business_name: str
    description: str
    website_url: Optional[str]
    industry: str
    products_services: str
    parent_company: Optional[str]
    confidence: str  # high, medium, low
    supplier_address: Optional[str] = None  # Optional supplier address/location
    is_large_company: bool = False  # Whether company is very large (may confuse LLM)
    company_size: Optional[str] = None  # small, medium, large, enterprise
    
    # Enhanced fields for better classification
    service_type: Optional[str] = None  # e.g., "Travel - Airlines", "IT - Hardware", "Professional Services - Consulting"
    naics_code: Optional[str] = None  # NAICS industry code (e.g., "481111" for Scheduled Passenger Air Transportation)
    naics_description: Optional[str] = None  # NAICS code description
    sic_code: Optional[str] = None  # SIC industry code
    primary_business_model: Optional[str] = None  # "B2B Services", "B2C Retail", "B2B Products", "Mixed"
    primary_revenue_streams: Optional[str] = None  # Comma-separated list of main revenue sources
    service_categories: Optional[str] = None  # Specific service categories (comma-separated)
    target_market: Optional[str] = None  # "Enterprise", "SMB", "Consumer", "Healthcare", "Government", "Mixed"
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "supplier_name": self.supplier_name,
            "official_business_name": self.official_business_name,
            "description": self.description,
            "website_url": self.website_url,
            "industry": self.industry,
            "products_services": self.products_services,
            "parent_company": self.parent_company,
            "confidence": self.confidence,
            "supplier_address": self.supplier_address,
            "is_large_company": self.is_large_company,
            "company_size": self.company_size,
            "service_type": self.service_type,
            "naics_code": self.naics_code,
            "naics_description": self.naics_description,
            "sic_code": self.sic_code,
            "primary_business_model": self.primary_business_model,
            "primary_revenue_streams": self.primary_revenue_streams,
            "service_categories": self.service_categories,
            "target_market": self.target_market,
        }

