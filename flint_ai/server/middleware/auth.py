"""API key authentication middleware.

Protects all API endpoints with a Bearer token or X-API-Key header.
Disable in development by not setting FLINT_API_KEY.
"""

from __future__ import annotations

import logging
import secrets
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("flint.server.middleware.auth")

# Paths that never require auth
_PUBLIC_PATHS = frozenset({"/health", "/ready", "/live", "/metrics", "/docs", "/openapi.json"})


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Validate API key on every request (unless path is public).

    Supports two header formats:
      - Authorization: Bearer <key>
      - X-API-Key: <key>

    Args:
        app: The ASGI application.
        api_key: Required API key. If None, middleware is a no-op (dev mode).
    """

    def __init__(self, app, api_key: Optional[str] = None):  # noqa: ANN001
        super().__init__(app)
        self._api_key = api_key

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # No key configured → dev mode, skip auth
        if not self._api_key:
            return await call_next(request)

        path = request.url.path

        # Allow public paths and UI assets
        if path in _PUBLIC_PATHS or path.startswith("/ui/"):
            return await call_next(request)

        # Allow OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Extract key from headers
        key = _extract_key(request)
        if not key:
            return JSONResponse(
                {"error": "Missing API key. Use Authorization: Bearer <key> or X-API-Key header."},
                status_code=401,
            )

        # Constant-time comparison to prevent timing attacks
        if not secrets.compare_digest(key, self._api_key):
            logger.warning("Invalid API key from %s", request.client.host if request.client else "unknown")
            return JSONResponse({"error": "Invalid API key."}, status_code=403)

        return await call_next(request)


def _extract_key(request: Request) -> Optional[str]:
    """Extract API key from Authorization or X-API-Key header."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()

    return request.headers.get("x-api-key")
