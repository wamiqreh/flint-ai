"""FastAPI middleware and decorator for Flint.

Provides :class:`OrchestratorMiddleware` and :func:`orchestrator_task` –
together they allow FastAPI routes to transparently offload work to the
orchestrator queue.

Usage::

    from fastapi import FastAPI
    from flint_ai.fastapi_middleware import (
        OrchestratorMiddleware,
        orchestrator_task,
    )

    app = FastAPI()
    app.add_middleware(OrchestratorMiddleware, base_url="http://localhost:5156")

    @app.post("/generate")
    @orchestrator_task(agent_type="openai")
    async def generate(prompt: str):
        return {"prompt": prompt}
"""

from __future__ import annotations

import asyncio
import functools
import json
from typing import Any, Callable, Optional

from .client import AsyncOrchestratorClient

try:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response
    from starlette.types import ASGIApp

    _FASTAPI_AVAILABLE = True
except ImportError:  # pragma: no cover
    _FASTAPI_AVAILABLE = False
    BaseHTTPMiddleware = object  # type: ignore[assignment,misc]

# Key used to store the orchestrator client on app.state
_STATE_KEY = "orchestrator_client"
# Attribute set by the @orchestrator_task decorator on route functions
_TASK_ATTR = "_orchestrator_task_opts"


class OrchestratorMiddleware(BaseHTTPMiddleware):  # type: ignore[misc]
    """FastAPI/Starlette middleware that intercepts decorated routes.

    Routes decorated with :func:`orchestrator_task` will have their request
    body forwarded to the orchestrator as a task.  The middleware waits for
    the task to complete and returns the result as a JSON response.

    Non-decorated routes pass through unmodified.

    Parameters
    ----------
    app:
        The ASGI application.
    base_url:
        Root URL of the orchestrator API.
    poll_interval:
        Seconds between status polls while waiting for results.
    timeout:
        Maximum seconds to wait for a result.  ``None`` means wait
        indefinitely.
    """

    def __init__(
        self,
        app: Any,
        *,
        base_url: str = "http://localhost:5156",
        poll_interval: float = 1.0,
        timeout: Optional[float] = 300.0,
    ) -> None:
        if not _FASTAPI_AVAILABLE:
            raise ImportError(
                "fastapi (and starlette) are required for OrchestratorMiddleware. "
                "Install with: pip install 'flint-ai[fastapi]'"
            )
        super().__init__(app)
        self.base_url = base_url
        self.poll_interval = poll_interval
        self.timeout = timeout
        self._client: Optional[AsyncOrchestratorClient] = None

    async def _get_client(self) -> AsyncOrchestratorClient:
        if self._client is None:
            self._client = AsyncOrchestratorClient(base_url=self.base_url)
        return self._client

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        # Find the route function and check for our decorator marker.
        route_func = self._resolve_route_func(request)
        opts = getattr(route_func, _TASK_ATTR, None) if route_func else None

        if opts is None:
            # Not an orchestrator-decorated route – pass through.
            return await call_next(request)

        agent_type: str = opts.get("agent_type", "openai")
        workflow_id: Optional[str] = opts.get("workflow_id")
        timeout: Optional[float] = opts.get("timeout", self.timeout)
        poll_interval: float = opts.get("poll_interval", self.poll_interval)

        # Build prompt from the request body.
        try:
            body = await request.json()
        except Exception:
            body = (await request.body()).decode(errors="replace")

        if isinstance(body, dict):
            prompt = body.get("prompt", json.dumps(body))
        else:
            prompt = str(body)

        client = await self._get_client()
        try:
            task_id = await client.submit_task(
                agent_type, prompt, workflow_id=workflow_id,
            )

            if timeout is not None:
                result = await asyncio.wait_for(
                    client.wait_for_task(task_id, poll_interval_seconds=poll_interval),
                    timeout=timeout,
                )
            else:
                result = await client.wait_for_task(
                    task_id, poll_interval_seconds=poll_interval,
                )
        except asyncio.TimeoutError:
            return JSONResponse(
                {"error": "Task timed out", "task_id": task_id},
                status_code=504,
            )
        except Exception as exc:
            return JSONResponse(
                {"error": str(exc)},
                status_code=502,
            )

        status_code = 200 if result.state == "Succeeded" else 500
        return JSONResponse(
            {
                "task_id": result.id,
                "state": result.state,
                "result": result.result,
            },
            status_code=status_code,
        )

    # -- route resolution helper ---------------------------------------------

    @staticmethod
    def _resolve_route_func(request: Request) -> Optional[Callable[..., Any]]:
        """Attempt to locate the endpoint function for a request."""
        app: Any = request.app
        router = getattr(app, "router", None)
        if router is None:
            return None
        for route in getattr(router, "routes", []):
            match, _ = route.matches(request.scope)
            # starlette Match enum: FULL = 2
            if getattr(match, "value", match) == 2:
                endpoint = getattr(route, "endpoint", None)
                return endpoint
        return None


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------


def orchestrator_task(
    *,
    agent_type: str = "openai",
    workflow_id: Optional[str] = None,
    timeout: Optional[float] = None,
    poll_interval: Optional[float] = None,
) -> Callable[..., Any]:
    """Mark a FastAPI route to be handled by the orchestrator.

    When :class:`OrchestratorMiddleware` is active, decorated routes will
    have their request body forwarded to the orchestrator instead of being
    executed locally.

    Parameters
    ----------
    agent_type:
        Agent backend for the task (e.g. ``"openai"``).
    workflow_id:
        Optional workflow ID.
    timeout:
        Per-route timeout override (seconds).
    poll_interval:
        Per-route poll interval override (seconds).
    """
    opts: dict[str, Any] = {"agent_type": agent_type}
    if workflow_id is not None:
        opts["workflow_id"] = workflow_id
    if timeout is not None:
        opts["timeout"] = timeout
    if poll_interval is not None:
        opts["poll_interval"] = poll_interval

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        setattr(func, _TASK_ATTR, opts)

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await func(*args, **kwargs)

        # Preserve marker on the wrapper as well
        setattr(wrapper, _TASK_ATTR, opts)
        return wrapper

    return decorator
