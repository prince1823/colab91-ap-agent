"""Custom exceptions for API."""


class DatasetNotFoundError(Exception):
    """Raised when a dataset is not found."""

    pass


class InvalidDatasetIdError(Exception):
    """Raised when dataset ID is invalid."""

    pass


class TransactionNotFoundError(Exception):
    """Raised when a transaction is not found."""

    pass


class FeedbackNotFoundError(Exception):
    """Raised when feedback is not found."""

    pass


class InvalidFeedbackStateError(Exception):
    """Raised when feedback is in invalid state for operation."""

    pass

