"""Constants for classification workflow."""

# Workflow status values
class WorkflowStatus:
    """Workflow status constants."""
    PENDING = "pending"
    CANONICALIZING = "canonicalizing"
    CANONICALIZED = "canonicalized"
    AWAITING_VERIFICATION = "awaiting_verification"
    VERIFIED = "verified"
    CLASSIFYING = "classifying"
    COMPLETED = "completed"
    FAILED = "failed"


# Default configuration values
DEFAULT_MAX_WORKERS = 4
DEFAULT_SUPPLIER_RULES_CACHE_SIZE = 500

# CSV filenames
CANONICALIZED_CSV_FILENAME = "canonicalized.csv"
CLASSIFIED_CSV_FILENAME = "classified.csv"

