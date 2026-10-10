"""Errors raised by services for rule violations."""


class RosterError(Exception):
    """A roster rule was violated. Routes translate this to an HTTP error."""

    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
