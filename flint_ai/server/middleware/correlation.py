"""Request correlation ID middleware.

Adds a unique X-Request-ID to every request/response for tracing.
"""

from __future__ import annotations

import contextvars
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Context variable accessible anywhere in the async call chain
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID to every request.

    - Reads from incoming X-Request-ID header (for distributed tracing)
    - Generates a new UUID4 if absent
    - Sets the ID in a contextvar for use in logs/task metadata
    - Returns it in the response X-Request-ID header
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = request.headers.get("x-request-id") or str(uuid.uuid4())
        request_id_var.set(rid)
        request.state.request_id = rid

        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


def get_request_id() -> str:
    """Get the current request's correlation ID (safe to call from anywhere)."""
    return request_id_var.get()
