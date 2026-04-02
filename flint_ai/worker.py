"""FlintWorker — client-side worker that pulls tasks and executes them locally.

Your agents, your API keys, your code. Flint only handles orchestration.

Usage::

    from flint_ai import FlintWorker
    from flint_ai.adapters.openai import FlintOpenAIAgent

    researcher = FlintOpenAIAgent(
        name="researcher", model="gpt-4o-mini",
        instructions="Research the topic.",
    )

    worker = (
        FlintWorker("http://localhost:5156")
        .register("researcher", researcher)
    )
    worker.start()   # blocks, polling for tasks
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger("flint.worker")


class FlintWorker:
    """Client-side worker that pulls tasks from a Flint server and executes locally.

    The worker connects to a running Flint server, claims tasks matching
    its registered adapters, executes them in-process, and reports results
    back to the server. The server handles retry, DLQ, and DAG advancement.

    This is the core of the client-worker architecture: agents always run
    on the client side — the server never touches your code, API keys, or tools.
    """

    def __init__(self, server_url: str, *, worker_id: Optional[str] = None) -> None:
        self.server_url = server_url.rstrip("/")
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self._adapters: Dict[str, Any] = {}
        self._running = False
        self._tasks: list[asyncio.Task] = []

    def register(self, agent_type: str, adapter: Any) -> "FlintWorker":
        """Register an adapter to handle tasks of the given agent type.

        Args:
            agent_type: The agent type name (must match what workflows use).
            adapter: A FlintAdapter instance (e.g. FlintOpenAIAgent).

        Returns:
            self (for chaining).
        """
        self._adapters[agent_type] = adapter
        return self

    @property
    def agent_types(self) -> list[str]:
        """List of agent types this worker can handle."""
        return list(self._adapters.keys())

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(
        self,
        *,
        poll_interval: float = 1.0,
        concurrency: int = 1,
        block: bool = True,
    ) -> None:
        """Start polling for tasks.

        Args:
            poll_interval: Seconds between polls when no tasks available.
            concurrency: Number of concurrent task execution slots.
            block: If True (default), blocks until stop() is called.
                   If False, starts in a background thread (useful in notebooks).
        """
        if not self._adapters:
            raise RuntimeError("No adapters registered. Call .register() first.")

        logger.info(
            "FlintWorker %s starting — server=%s agents=%s concurrency=%d",
            self.worker_id, self.server_url, list(self._adapters.keys()), concurrency,
        )

        if block:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    pool.submit(asyncio.run, self._run(poll_interval, concurrency)).result()
            else:
                asyncio.run(self._run(poll_interval, concurrency))
        else:
            import threading
            t = threading.Thread(
                target=asyncio.run,
                args=(self._run(poll_interval, concurrency),),
                daemon=True,
            )
            t.start()

    async def start_async(
        self,
        *,
        poll_interval: float = 1.0,
        concurrency: int = 1,
    ) -> None:
        """Start polling (async version, for use inside an event loop)."""
        if not self._adapters:
            raise RuntimeError("No adapters registered. Call .register() first.")
        await self._run(poll_interval, concurrency)

    def stop(self) -> None:
        """Signal the worker to stop polling gracefully."""
        self._running = False
        for t in self._tasks:
            t.cancel()
        logger.info("FlintWorker %s stopping", self.worker_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run(self, poll_interval: float, concurrency: int) -> None:
        self._running = True
        logger.info(
            "🔧 FlintWorker %s connected to %s (agents: %s)",
            self.worker_id, self.server_url, ", ".join(self._adapters.keys()),
        )
        self._tasks = [
            asyncio.create_task(self._poll_loop(poll_interval, i))
            for i in range(concurrency)
        ]
        try:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            logger.info("FlintWorker %s stopped", self.worker_id)

    async def _poll_loop(self, interval: float, slot: int) -> None:
        """Single poll loop — claims and executes tasks."""
        try:
            import httpx
        except ImportError:
            raise ImportError("httpx required for FlintWorker. Install with: pip install httpx")

        async with httpx.AsyncClient(base_url=self.server_url, timeout=30) as client:
            while self._running:
                try:
                    record = await self._claim(client)
                    if record:
                        await self._execute_and_report(client, record)
                    else:
                        await asyncio.sleep(interval)
                except asyncio.CancelledError:
                    break
                except Exception:
                    logger.exception("FlintWorker slot-%d poll error", slot)
                    await asyncio.sleep(interval)

    async def _claim(self, client: Any) -> Optional[Dict[str, Any]]:
        """Claim the next available task from the server."""
        resp = await client.post("/tasks/claim", json={
            "worker_id": self.worker_id,
            "agent_types": list(self._adapters.keys()),
        })
        if resp.status_code == 204:
            return None
        resp.raise_for_status()
        return resp.json()

    async def _execute_and_report(self, client: Any, task_data: Dict[str, Any]) -> None:
        """Execute a task locally and report the result to the server."""
        task_id = task_data["id"]
        agent_type = task_data["agent_type"]
        adapter = self._adapters.get(agent_type)

        if not adapter:
            await self._report(client, task_id, success=False,
                               error=f"No adapter registered for '{agent_type}'",
                               metadata={"error_action": "dlq"})
            return

        # Start heartbeat to keep the task lease alive
        heartbeat = asyncio.create_task(self._heartbeat_loop(client, task_id))

        try:
            input_data = {
                "prompt": task_data["prompt"],
                "task_id": task_id,
                "workflow_id": task_data.get("workflow_id"),
                "node_id": task_data.get("node_id"),
                "metadata": task_data.get("metadata", {}),
            }

            # Use safe_run for error classification + tracing
            if hasattr(adapter, "safe_run"):
                result = await adapter.safe_run(input_data)
            else:
                result = await adapter.run(input_data)

            await self._report(
                client, task_id,
                success=result.success if hasattr(result, "success") else True,
                output=result.output if hasattr(result, "output") else str(result),
                error=result.error if hasattr(result, "error") else None,
                metadata=result.metadata if hasattr(result, "metadata") else {},
            )

            status = "✅" if (result.success if hasattr(result, "success") else True) else "❌"
            logger.info("%s Task %s (%s) — %s", status, task_id[:8], agent_type,
                        "succeeded" if status == "✅" else result.error if hasattr(result, "error") else "failed")

        except Exception as e:
            logger.exception("Task %s execution error", task_id)
            await self._report(
                client, task_id,
                success=False,
                error=str(e),
                metadata={"error_action": "retry", "error_type": type(e).__name__},
            )
        finally:
            heartbeat.cancel()

    async def _report(
        self,
        client: Any,
        task_id: str,
        *,
        success: bool,
        output: Optional[str] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Report task execution result to the server."""
        await client.post(f"/tasks/{task_id}/result", json={
            "worker_id": self.worker_id,
            "success": success,
            "output": output,
            "error": error,
            "metadata": metadata or {},
        })

    async def _heartbeat_loop(self, client: Any, task_id: str, interval: float = 15.0) -> None:
        """Send periodic heartbeats to keep the task lease alive."""
        try:
            while True:
                await asyncio.sleep(interval)
                try:
                    await client.post(f"/tasks/{task_id}/heartbeat", json={
                        "worker_id": self.worker_id,
                    })
                except Exception:
                    logger.debug("Heartbeat failed for task %s", task_id)
        except asyncio.CancelledError:
            pass
