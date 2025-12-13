"""Custom exceptions for classification workflow."""


class WorkflowError(Exception):
    """Base exception for workflow errors."""
    pass


class CanonicalizationError(WorkflowError):
    """Error during canonicalization stage."""
    pass


class VerificationError(WorkflowError):
    """Error during verification stage."""
    pass


class ClassificationError(WorkflowError):
    """Error during classification stage."""
    pass


class InvalidStateTransitionError(WorkflowError):
    """Invalid workflow state transition attempted."""
    pass


class InvalidColumnError(WorkflowError):
    """Invalid column name or modification."""
    pass


class CSVIntegrityError(WorkflowError):
    """CSV file integrity validation failed."""
    pass

