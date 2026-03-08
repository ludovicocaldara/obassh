class ObasshError(Exception):
    """Base project exception."""


class ValidationError(ObasshError):
    """Raised when user input or configuration is invalid."""


class OciApiError(ObasshError):
    """Raised when OCI API operations fail."""


class SessionTimeoutError(ObasshError):
    """Raised when waiting for session activation times out."""


class SshExecutionError(ObasshError):
    """Raised when SSH process execution fails."""
