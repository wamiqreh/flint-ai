"""Worker pool management — starts and stops multiple worker coroutines."""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from flint_ai.server.config import WorkerConfig
from flint_ai.server.dag.engine import DAGEngine
from flint_ai.server.engine.task_engine import TaskEngine
from flint_ai.server.metrics import FlintMetrics
from flint_ai.server.queue import BaseQueue
from flint_ai.server.store import BaseWorkflowStore
from flint_ai.server.worker import Worker

logger = logging.getLogger("flint.server.worker.pool")


class WorkerPool:
    """Manages a pool of worker coroutines."""

    def __init__(
        self,
        config: WorkerConfig,
        task_engine: TaskEngine,
        dag_engine: DAGEngine,
        queue: BaseQueue,
        workflow_store: BaseWorkflowStore,
        metrics: FlintMetrics,
    ) -> None:
        self._config = config
        self._task_engine = task_engine
        self._dag_engine = dag_engine
        self._queue = queue
        self._wf_store = workflow_store
        self._metrics = metrics
        self._workers: List[Worker] = []

    async def start(self) -> None:
        """Start all workers."""
        for i in range(self._config.count):
            worker = Worker(
                worker_id=i,
                task_engine=self._task_engine,
                dag_engine=self._dag_engine,
                queue=self._queue,
                workflow_store=self._wf_store,
                metrics=self._metrics,
                poll_interval_ms=self._config.poll_interval_ms,
            )
            self._workers.append(worker)
            await worker.start()

        logger.info("Worker pool started: %d workers", len(self._workers))

    async def stop(self) -> None:
        """Gracefully stop all workers."""
        logger.info("Stopping worker pool (%d workers)...", len(self._workers))
        await asyncio.gather(
            *(w.stop() for w in self._workers),
            return_exceptions=True,
        )
        self._workers.clear()
        logger.info("Worker pool stopped")

    @property
    def worker_count(self) -> int:
        return len(self._workers)
