"""Error models for classification processing."""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ClassificationError:
    """Standardized error model for classification processing."""

    row_index: Any
    supplier_name: Optional[str]
    error: str
    error_type: str
    invoice_key: Optional[str] = None
    raw_response: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for backward compatibility."""
        result = {
            'row_index': self.row_index,
            'supplier_name': self.supplier_name,
            'error': self.error,
        }
        if self.invoice_key:
            result['invoice_key'] = self.invoice_key
        if self.raw_response:
            result['raw_response'] = self.raw_response
        return result

    @classmethod
    def from_dict(cls, data: dict) -> 'ClassificationError':
        """Create from dictionary (backward compatibility)."""
        return cls(
            row_index=data.get('row_index') or data.get('row'),
            supplier_name=data.get('supplier_name'),
            error=data.get('error', str(data)),
            error_type=data.get('error_type', 'UNKNOWN'),
            invoice_key=data.get('invoice_key'),
            raw_response=data.get('raw_response')
        )

