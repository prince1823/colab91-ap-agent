"""Data models for context prioritization agent."""

from dataclasses import dataclass


@dataclass
class PrioritizationDecision:
    """Decision from context prioritization agent."""
    
    should_research: bool
    prioritization_strategy: str  # "supplier_primary", "transaction_primary", "balanced", "supplier_only"
    supplier_context_strength: str  # "strong", "medium", "weak", "none"
    transaction_data_quality: str  # "rich", "sparse", "generic", "accounting_reference"
    reasoning: str

