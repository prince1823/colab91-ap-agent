"""Data models for column canonicalization agent."""

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class MappingResult:
    """Result of column mapping operation"""
    
    mappings: Dict[str, str]  # canonical_name -> client_column_name
    confidence: str  # high, medium, low
    unmapped_client_columns: List[str]  # All unmapped columns
    important_unmapped_columns: List[str]  # Important unmapped columns to preserve
    unmapped_canonical_columns: List[str]
    validation_passed: bool
    validation_errors: List[str]
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "mappings": self.mappings,
            "confidence": self.confidence,
            "unmapped_client_columns": self.unmapped_client_columns,
            "important_unmapped_columns": self.important_unmapped_columns,
            "unmapped_canonical_columns": self.unmapped_canonical_columns,
            "validation_passed": self.validation_passed,
            "validation_errors": self.validation_errors,
        }

