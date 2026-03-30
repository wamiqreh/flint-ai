from __future__ import annotations

import asyncio
import json
import random
from typing import Any, AsyncIterator, Optional, Sequence

import httpx

from .exceptions import (
    AuthenticationError,
    ConnectionError,
    OrchestratorError,
    RateLimitError,
    TaskNotFoundError,
    WorkflowValidationError,
)
from .models import (
    SubmitTaskRequest,
    SubmitTaskResponse,
    TaskResponse,
    TaskSubmission,
    WorkflowDefinition,
)

# Defaults ------------------------------------------------------------------
_DEFAULT_CONNECT_TIMEOUT = 5.0  # seconds
_DEFAULT_READ_TIMEOUT = 30.0  # seconds
_DEFAULT_WRITE_TIMEOUT = 30.0  # seconds
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_BACKOFF_BASE = 0.5  # seconds
_DEFAULT_BACKOFF_MAX = 30.0  # seconds


def _build_timeout(
    timeout: Optional[httpx.Timeout] = None,
    *,
    connect: Optional[float] = None,
    read: Optional[float] = None,
    write: Optional[float] = None,
) -> httpx.Timeout:
    """Build an ``httpx.Timeout`` from explicit values or a supplied instance."""
    if timeout is not None:
        return timeout
    return httpx.Timeout(
        connect=connect if connect is not None else _DEFAULT_CONNECT_TIMEOUT,
        read=read if read is not None else _DEFAULT_READ_TIMEOUT,
        write=write if write is not None else _DEFAULT_WRITE_TIMEOUT,
        pool=None,
    )


def _map_status_to_error(response: httpx.Response) -> OrchestratorError:
    """Translate an HTTP error response into a typed SDK exception."""
    status = response.status_code
    try:
        detail = response.text
    except Exception:
        detail = None

    if status == 404:
        return TaskNotFoundError(
            f"Resource not found: {response.url}",
            status_code=status,
            detail=detail,
        )
    if status == 422:
        return WorkflowValidationError(
            "Workflow validation failed",
            status_code=status,
            detail=detail,
        )
    if status == 429:
        retry_after = _parse_retry_after(response)
        return RateLimitError(
            "Rate limit exceeded",
            status_code=status,
            detail=detail,
            retry_after=retry_after,
        )
    if status in {401, 403}:
        return AuthenticationError(
            "Authentication failed" if status == 401 else "Forbidden",
            status_code=status,
            detail=detail,
        )
    return OrchestratorError(
        f"HTTP {status}",
        status_code=status,
        detail=detail,
    )


def _parse_retry_after(response: httpx.Response) -> Optional[float]:
    """Extract a ``Retry-After`` value (in seconds) from a response."""
    header = response.headers.get("retry-after")
    if header is None:
        return None
    try:
        return float(header)
    except ValueError:
        return None


def _jittered_backoff(attempt: int, base: float, maximum: float) -> float:
    """Calculate exponential backoff with full jitter."""
    delay = min(base * (2 ** attempt), maximum)
    return random.uniform(0, delay)  # noqa: S311


# ---------------------------------------------------------------------------
# Async client
# ---------------------------------------------------------------------------

class AsyncOrchestratorClient:
    """Async HTTP client for Flint.

    Supports ``async with`` context-manager usage, automatic retries with
    exponential backoff + jitter, configurable timeouts, and typed exceptions.

    Args:
        base_url: Root URL of the orchestrator API.
        timeout: An ``httpx.Timeout`` to use as-is.  If *None*, individual
            ``connect_timeout`` / ``read_timeout`` / ``write_timeout`` values
            are used instead.
        connect_timeout: TCP connect timeout in seconds (default 5).
        read_timeout: Read timeout in seconds (default 30).
        write_timeout: Write timeout in seconds (default 30).
        max_retries: Maximum number of retry attempts for transient errors
            (HTTP 429, 502, 503, 504 and connection failures).
        backoff_base: Base delay for exponential backoff in seconds.
        backoff_max: Maximum delay between retries in seconds.
    """

    _RETRYABLE_STATUS_CODES = frozenset({429, 502, 503, 504})

    def __init__(
        self,
        base_url: str = "http://localhost:5156",
        *,
        timeout: Optional[httpx.Timeout] = None,
        connect_timeout: Optional[float] = None,
        read_timeout: Optional[float] = None,
        write_timeout: Optional[float] = None,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        backoff_base: float = _DEFAULT_BACKOFF_BASE,
        backoff_max: float = _DEFAULT_BACKOFF_MAX,
    ) -> None:
        self._timeout = _build_timeout(
            timeout, connect=connect_timeout, read=read_timeout, write=write_timeout,
        )
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=self._timeout,
        )

    # -- context manager -----------------------------------------------------

    async def __aenter__(self) -> AsyncOrchestratorClient:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP transport."""
        await self._client.aclose()

    # -- internal request helper ---------------------------------------------

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json: Any = None,
        params: Any = None,
    ) -> httpx.Response:
        """Issue an HTTP request with retry logic and error mapping."""
        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.request(
                    method, url, json=json, params=params,
                )
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    await asyncio.sleep(
                        _jittered_backoff(attempt, self._backoff_base, self._backoff_max)
                    )
                    continue
                raise ConnectionError(
                    f"Failed to connect to {self._client.base_url}: {exc}"
                ) from exc

            if response.status_code < 400:
                return response

            if response.status_code in self._RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                retry_after = _parse_retry_after(response)
                if retry_after is not None:
                    delay = retry_after
                else:
                    delay = _jittered_backoff(attempt, self._backoff_base, self._backoff_max)
                await asyncio.sleep(delay)
                continue

            raise _map_status_to_error(response)

        # Should not reach here, but satisfy type checkers.
        if last_exc is not None:
            raise ConnectionError(
                f"Failed after {self._max_retries + 1} attempts"
            ) from last_exc
        raise OrchestratorError("Unexpected retry exhaustion")  # pragma: no cover

    # -- public API ----------------------------------------------------------

    async def submit_task(
        self,
        agent_type: str,
        prompt: str,
        workflow_id: Optional[str] = None,
    ) -> str:
        """Submit a single task and return its ID."""
        payload = SubmitTaskRequest(
            AgentType=agent_type, Prompt=prompt, WorkflowId=workflow_id,
        )
        response = await self._request(
            "POST", "/tasks",
            json=payload.model_dump(by_alias=True, exclude_none=True),
        )
        body = SubmitTaskResponse.model_validate(response.json())
        return body.id

    async def submit_tasks(
        self,
        tasks: Sequence[TaskSubmission],
    ) -> list[str]:
        """Submit multiple tasks concurrently.

        Each task is submitted as a separate HTTP request in parallel.

        Returns:
            A list of task IDs in the same order as the input *tasks*.
        """
        coros = [
            self._request(
                "POST",
                "/tasks",
                json=SubmitTaskRequest(
                    AgentType=t.agent_type, Prompt=t.prompt, WorkflowId=t.workflow_id,
                ).model_dump(by_alias=True, exclude_none=True),
            )
            for t in tasks
        ]
        responses = await asyncio.gather(*coros)
        return [
            SubmitTaskResponse.model_validate(r.json()).id for r in responses
        ]

    async def get_task(self, task_id: str) -> TaskResponse:
        """Retrieve the current state of a task."""
        response = await self._request("GET", f"/tasks/{task_id}")
        return TaskResponse.model_validate(response.json())

    async def wait_for_task(
        self,
        task_id: str,
        poll_interval_seconds: float = 1.0,
    ) -> TaskResponse:
        """Poll a task until it reaches a terminal state."""
        while True:
            task = await self.get_task(task_id)
            if task.state in {"Succeeded", "Failed", "DeadLetter"}:
                return task
            await asyncio.sleep(poll_interval_seconds)

    async def create_workflow(
        self,
        workflow: WorkflowDefinition,
    ) -> WorkflowDefinition:
        """Create a new workflow definition on the server.

        If the workflow was built with adapter objects, auto-registers them.
        """
        response = await self._request(
            "POST", "/workflows",
            json=workflow.model_dump(by_alias=True),
        )
        return WorkflowDefinition.model_validate(response.json())

    async def register_adapter(self, adapter: Any) -> bool:
        """Register a FlintAdapter with the Flint server.

        Args:
            adapter: A FlintAdapter instance (e.g., FlintOpenAIAgent).

        Returns:
            True if registration succeeded.
        """
        from .adapters.core.registry import auto_register
        await auto_register(adapter)
        return True

    async def deploy_workflow(self, workflow_builder: Any) -> str:
        """Build, register adapters, create, and start a workflow in one call.

        Args:
            workflow_builder: A Workflow builder instance (not yet built).

        Returns:
            The workflow ID.
        """
        # Register any adapters used by nodes
        adapters = workflow_builder.get_adapters()
        for adapter in adapters:
            await self.register_adapter(adapter)

        # Build and create the workflow
        wf_def = workflow_builder.build()
        await self.create_workflow(wf_def)
        await self.start_workflow(wf_def.id)
        return wf_def.id

    async def start_workflow(self, workflow_id: str) -> None:
        """Trigger execution of an existing workflow."""
        await self._request("POST", f"/workflows/{workflow_id}/start")

    async def list_workflows(self) -> list[WorkflowDefinition]:
        """List all workflow definitions."""
        response = await self._request("GET", "/workflows")
        return [WorkflowDefinition.model_validate(item) for item in response.json()]

    async def get_workflow_nodes(self, workflow_id: str) -> list[Any]:
        """Return the raw node list for a workflow."""
        response = await self._request("GET", f"/workflows/{workflow_id}/nodes")
        return response.json()  # type: ignore[no-any-return]

    async def stream_metrics(
        self,
        interval_seconds: float = 2.0,
    ) -> AsyncIterator[str]:
        """Yield metrics snapshots at the given interval."""
        while True:
            response = await self._request("GET", "/metrics")
            yield response.text
            await asyncio.sleep(interval_seconds)

    async def stream_task(self, task_id: str) -> AsyncIterator[TaskResponse]:
        """Stream SSE updates for a task."""
        async with self._client.stream("GET", f"/tasks/{task_id}/stream") as response:
            if response.status_code >= 400:
                # Read body so error detail is available
                await response.aread()
                raise _map_status_to_error(response)
            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                payload = line[len("data: "):].strip()
                if not payload:
                    continue
                yield TaskResponse.model_validate(json.loads(payload))


# ---------------------------------------------------------------------------
# Synchronous wrapper
# ---------------------------------------------------------------------------

class OrchestratorClient:
    """Synchronous convenience wrapper around :class:`AsyncOrchestratorClient`.

    Supports ``with`` context-manager usage.  Every public method creates a
    short-lived event loop so callers never have to deal with ``async/await``.

    Accepts all the same configuration parameters as
    :class:`AsyncOrchestratorClient`.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:5156",
        *,
        timeout: Optional[httpx.Timeout] = None,
        connect_timeout: Optional[float] = None,
        read_timeout: Optional[float] = None,
        write_timeout: Optional[float] = None,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        backoff_base: float = _DEFAULT_BACKOFF_BASE,
        backoff_max: float = _DEFAULT_BACKOFF_MAX,
    ) -> None:
        self._kwargs = dict(
            base_url=base_url,
            timeout=timeout,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            write_timeout=write_timeout,
            max_retries=max_retries,
            backoff_base=backoff_base,
            backoff_max=backoff_max,
        )

    # -- context manager -----------------------------------------------------

    def __enter__(self) -> OrchestratorClient:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass  # each call creates+closes its own async client

    # -- helpers -------------------------------------------------------------

    def _run(self, coro_factory: Any) -> Any:
        """Run an async operation with a fresh client in a new event loop."""
        async def _inner() -> Any:
            async with AsyncOrchestratorClient(**self._kwargs) as client:
                return await coro_factory(client)
        return asyncio.run(_inner())

    # -- public API ----------------------------------------------------------

    def submit_task(
        self,
        agent_type: str,
        prompt: str,
        workflow_id: Optional[str] = None,
    ) -> str:
        """Submit a single task and return its ID."""
        return self._run(lambda c: c.submit_task(agent_type, prompt, workflow_id))

    def submit_tasks(self, tasks: Sequence[TaskSubmission]) -> list[str]:
        """Submit multiple tasks concurrently and return their IDs."""
        return self._run(lambda c: c.submit_tasks(tasks))

    def get_task(self, task_id: str) -> TaskResponse:
        """Retrieve the current state of a task."""
        return self._run(lambda c: c.get_task(task_id))

    def wait_for_task(
        self,
        task_id: str,
        poll_interval_seconds: float = 1.0,
    ) -> TaskResponse:
        """Poll a task until it reaches a terminal state."""
        return self._run(lambda c: c.wait_for_task(task_id, poll_interval_seconds))

    def create_workflow(
        self,
        workflow: WorkflowDefinition,
    ) -> WorkflowDefinition:
        """Create a new workflow definition on the server."""
        return self._run(lambda c: c.create_workflow(workflow))

    def register_adapter(self, adapter: Any) -> bool:
        """Register a FlintAdapter with the Flint server."""
        return self._run(lambda c: c.register_adapter(adapter))

    def deploy_workflow(self, workflow_builder: Any) -> str:
        """Build, register adapters, create, and start a workflow in one call."""
        return self._run(lambda c: c.deploy_workflow(workflow_builder))

    def start_workflow(self, workflow_id: str) -> None:
        """Trigger execution of an existing workflow."""
        return self._run(lambda c: c.start_workflow(workflow_id))

    def list_workflows(self) -> list[WorkflowDefinition]:
        """List all workflow definitions."""
        return self._run(lambda c: c.list_workflows())

    def get_workflow_nodes(self, workflow_id: str) -> list[Any]:
        """Return the raw node list for a workflow."""
        return self._run(lambda c: c.get_workflow_nodes(workflow_id))
