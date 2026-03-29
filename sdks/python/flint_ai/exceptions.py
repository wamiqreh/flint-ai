"""Typed exception hierarchy for the Flint SDK."""

from __future__ import annotations

from typing import Optional


class OrchestratorError(Exception):
    """Base exception for all orchestrator SDK errors.

    Attributes:
        status_code: HTTP status code that triggered the error, if any.
        detail: Additional detail from the server response body.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        detail: Optional[str] = None,
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(message)


class TaskNotFoundError(OrchestratorError):
    """Raised when a requested task does not exist (HTTP 404)."""


class WorkflowValidationError(OrchestratorError):
    """Raised when a workflow definition fails server-side validation (HTTP 422)."""


class RateLimitError(OrchestratorError):
    """Raised when the server returns HTTP 429 (Too Many Requests).

    Attributes:
        retry_after: Seconds to wait before retrying, parsed from the
            ``Retry-After`` header when available.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        detail: Optional[str] = None,
        retry_after: Optional[float] = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(message, status_code=status_code, detail=detail)


class AuthenticationError(OrchestratorError):
    """Raised on HTTP 401 (Unauthorized) or 403 (Forbidden)."""


class ConnectionError(OrchestratorError):  # noqa: A001 – intentional shadow of builtin
    """Raised when the SDK cannot reach the orchestrator server."""
