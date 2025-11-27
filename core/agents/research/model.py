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
        }

