"""Shared database exception types across storage adapters."""


class DatabaseUnavailableError(RuntimeError):
    """Raised when the configured application database is unavailable."""
