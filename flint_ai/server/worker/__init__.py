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
                record = await self._task_engine.process_next()
                if not record:
                    await asyncio.sleep(self._poll_interval)
                else:
                    # After processing, advance workflow DAG if this is a workflow task
                    if record.workflow_id and record.node_id:
                        await self._advance_dag(record)

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

    async def _advance_dag(self, record) -> None:
        """Advance DAG after a workflow task completes or fails."""
        from flint_ai.server.engine import TaskState

        run_id = record.metadata.get("workflow_run_id")
        if not run_id:
            return

        try:
            run = await self._wf_store.get_run(run_id)
            if not run:
                logger.warning("Workflow run %s not found for task %s", run_id, record.id)
                return

            defn = await self._wf_store.get_definition(run.workflow_id)
            if not defn:
                logger.warning("Workflow %s not found for run %s", run.workflow_id, run_id)
                return

            # Update node state based on task outcome
            node_id = record.node_id
            if record.state == TaskState.SUCCEEDED:
                run.node_states[node_id] = TaskState.SUCCEEDED
            elif record.state == TaskState.FAILED:
                run.node_states[node_id] = TaskState.FAILED
            elif record.state == TaskState.DEAD_LETTER:
                run.node_states[node_id] = TaskState.DEAD_LETTER
            else:
                run.node_states[node_id] = record.state

            # Find downstream nodes that are now ready
            if record.state == TaskState.SUCCEEDED:
                downstream = self._dag_engine.get_ready_nodes(defn, run)
                for node in downstream:
                    if run.node_states.get(node.id) in (None, TaskState.PENDING, "pending"):
                        state = TaskState.PENDING if node.human_approval else TaskState.QUEUED
                        new_record = await self._task_engine.submit_task(
                            agent_type=node.agent_type,
                            prompt=node.prompt_template,
                            workflow_id=run.workflow_id,
                            node_id=node.id,
                            max_retries=node.retry_policy.max_retries,
                            human_approval=node.human_approval,
                            metadata={"workflow_run_id": run.id, **node.metadata},
                        )
                        run.node_states[node.id] = new_record.state
                        run.node_task_ids.setdefault(node.id, []).append(new_record.id)
                        logger.info(
                            "DAG advanced: workflow=%s node=%s → queued task=%s",
                            run.workflow_id, node.id, new_record.id,
                        )

            # Check if all nodes are terminal → mark run complete
            all_terminal = all(
                self._is_terminal_state(s)
                for s in run.node_states.values()
            )
            if all_terminal and run.node_states:
                any_failed = any(
                    self._is_failed_state(s)
                    for s in run.node_states.values()
                )
                from flint_ai.server.engine import WorkflowRunState
                from datetime import datetime, timezone
                run.state = WorkflowRunState.FAILED if any_failed else WorkflowRunState.SUCCEEDED
                run.completed_at = datetime.now(timezone.utc)
                logger.info("Workflow run %s completed: %s", run.id, run.state.value)

            await self._wf_store.update_run(run)

        except Exception:
            logger.exception("Error advancing DAG for task %s", record.id)

    @staticmethod
    def _is_terminal_state(state) -> bool:
        terminal_values = {"succeeded", "failed", "dead_letter", "cancelled"}
        val = state.value if hasattr(state, 'value') else str(state)
        return val in terminal_values

    @staticmethod
    def _is_failed_state(state) -> bool:
        failed_values = {"failed", "dead_letter"}
        val = state.value if hasattr(state, 'value') else str(state)
        return val in failed_values
