class ReconciliationError(Exception):
    """Base error for reconciliation-as-code."""


class SpecError(ReconciliationError):
    """Raised when a reconciliation specification is invalid."""


class DataError(ReconciliationError):
    """Raised when input data cannot be loaded or interpreted."""
