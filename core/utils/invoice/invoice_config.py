"""Configuration constants for invoice-level processing."""

from dataclasses import dataclass


@dataclass
class InvoiceProcessingConfig:
    """Configuration for invoice-level processing."""

    # Batch processing
    max_rows_per_batch: int = 50

    # Aggregation limits
    max_line_descriptions: int = 5
    max_gl_descriptions: int = 3

    # Similarity thresholds for context prioritization
    low_similarity_threshold: float = 0.3
    high_similarity_threshold: float = 0.7

    # Supplier cache
    supplier_cache_max_size: int = 1000

    # Invoice grouping columns (can be overridden)
    default_grouping_columns: list = None

    def __post_init__(self):
        """Initialize default grouping columns if not provided."""
        if self.default_grouping_columns is None:
            self.default_grouping_columns = [
                'invoice_date',
                'company',
                'supplier_name',
                'creation_date'
            ]


# Global default configuration
DEFAULT_CONFIG = InvoiceProcessingConfig()

