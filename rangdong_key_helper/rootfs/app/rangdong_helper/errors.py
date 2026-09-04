"""Safe errors returned by the helper API."""

from __future__ import annotations


class HelperError(Exception):
    """An expected helper failure with a public error code."""

    def __init__(self, code: str, message: str, *, status: int = 400) -> None:
        """Initialize a safe error."""

        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
