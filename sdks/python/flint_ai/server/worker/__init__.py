"""Background worker that polls the queue and processes tasks."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from flint_ai.server.dag.engine import DAGEngine
from flint_ai.server.engine import TaskState, WorkflowRunState
from flint_ai.server.engine.task_engine import TaskEngine
from flint_ai.server.metrics import FlintMetrics
from flint_ai.server.queue import BaseQueue
from flint_ai.server.store import BaseWorkflowStore

logger = logging.getLogger("flint.server.worker")


class Worker:
    """Single worker coroutine that polls queue and processes tasks.

    The worker:
    1. Dequeues a task from the queue
    2. Delegates to TaskEngine for execution
    3. If task belongs to a workflow, notifies DAGEngine
    4. Handles retries, failures, and DLQ routing
    """

    def __init__(
        self,
        worker_id: int,
        task_engine: TaskEngine,
        dag_engine: DAGEngine,
        queue: BaseQueue,
        workflow_store: BaseWorkflowStore,
        metrics: FlintMetrics,
        poll_interval_ms: int = 1000,
    ) -> None:
        self._id = worker_id
        self._task_engine = task_engine
        self._dag_engine = dag_engine
        self._queue = queue
        self._wf_store = workflow_store
        self._metrics = metrics
        self._poll_interval = poll_interval_ms / 1000.0
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Worker-%d started", self._id)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Worker-%d stopped", self._id)

    async def _loop(self) -> None:
        while self._running:
            try:
                processed = await self._task_engine.process_next()
                if not processed:
                    await asyncio.sleep(self._poll_interval)
                else:
                    # After processing, check if it's a workflow task
                    # The task engine already handled the execution;
                    # we just need to trigger DAG progression
                    pass

                # Periodically reclaim stale messages
                reclaimed = await self._queue.reclaim_stale()
                if reclaimed:
                    self._metrics.record_reclaimed(reclaimed)

                # Update queue metrics
                q_len = await self._queue.get_queue_length()
                dlq_len = await self._queue.get_dlq_length()
                self._metrics.update_queue_lengths(q_len, dlq_len)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Worker-%d error", self._id)
                await asyncio.sleep(self._poll_interval)
