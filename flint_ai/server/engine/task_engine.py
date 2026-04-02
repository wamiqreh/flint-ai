"""Task lifecycle engine — the heart of task processing.

Manages the full lifecycle: submit → enqueue → dequeue → execute → succeed/fail/retry/DLQ.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from flint_ai.server.agents import AgentRegistry
from flint_ai.server.engine import AgentResult, TaskRecord, TaskState, TaskPriority
from flint_ai.server.engine.concurrency import ConcurrencyManager
from flint_ai.server.metrics import FlintMetrics
from flint_ai.server.queue import BaseQueue
from flint_ai.server.store import BaseTaskStore

logger = logging.getLogger("flint.server.engine.task")


class TaskEngine:
    """Manages the complete task lifecycle.

    This engine coordinates between the queue, store, agent registry,
    and concurrency manager to process tasks reliably.
    """

    def __init__(
        self,
        queue: BaseQueue,
        task_store: BaseTaskStore,
        agent_registry: AgentRegistry,
        concurrency: ConcurrencyManager,
        metrics: FlintMetrics,
        max_task_duration_s: int = 300,
        completion_webhook_url: Optional[str] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._queue = queue
        self._store = task_store
        self._agents = agent_registry
        self._concurrency = concurrency
        self._metrics = metrics
        self._max_duration = max_task_duration_s
        self._webhook_url = completion_webhook_url
        self._event_bus = event_bus  # RedisPubSubBus for cross-pod SSE
        self._subscribers: Dict[str, list] = {}

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    async def submit_task(
        self,
        agent_type: str,
        prompt: str,
        workflow_id: Optional[str] = None,
        node_id: Optional[str] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        max_retries: int = 3,
        metadata: Optional[Dict[str, Any]] = None,
        human_approval: bool = False,
    ) -> TaskRecord:
        """Submit a new task for processing."""
        state = TaskState.PENDING if human_approval else TaskState.QUEUED

        record = TaskRecord(
            agent_type=agent_type,
            prompt=prompt,
            workflow_id=workflow_id,
            node_id=node_id,
            state=state,
            priority=priority,
            max_retries=max_retries,
            metadata=metadata or {},
        )

        record = await self._store.create(record)
        self._metrics.record_submit(agent_type)

        if not human_approval:
            await self._enqueue(record)

        logger.info(
            "Submitted task=%s agent=%s state=%s",
            record.id, agent_type, state,
        )
        return record

    async def _enqueue(self, record: TaskRecord) -> None:
        """Put a task on the queue."""
        data = {
            "task_id": record.id,
            "agent_type": record.agent_type,
            "prompt": record.prompt,
            "attempt": record.attempt,
            "workflow_id": record.workflow_id,
            "node_id": record.node_id,
        }
        await self._queue.enqueue(record.id, data, priority=record.priority.value)

    # ------------------------------------------------------------------
    # Process (called by worker)
    # ------------------------------------------------------------------

    async def process_next(self) -> Optional[TaskRecord]:
        """Dequeue and process one task. Returns the processed TaskRecord or None."""
        messages = await self._queue.dequeue(count=1, block_ms=5000)
        if not messages:
            return None

        msg = messages[0]
        task_id = msg.task_id
        agent_type = msg.data.get("agent_type", "")

        record = await self._store.get(task_id)
        if not record:
            logger.warning("Task %s not found in store, acking", task_id)
            await self._queue.ack(msg.message_id)
            return None

        # Skip tasks already claimed by external workers
        if record.state == TaskState.RUNNING:
            logger.debug("Task %s already running (external worker?), acking", task_id)
            await self._queue.ack(msg.message_id)
            return None

        # Skip tasks already in terminal state (e.g. cancelled while queued)
        if record.state.is_terminal:
            logger.debug("Task %s already terminal (%s), acking", task_id, record.state.value)
            await self._queue.ack(msg.message_id)
            return None

        # Check if agent exists
        agent = self._agents.get(agent_type)
        if not agent:
            logger.error("No agent registered for type=%s, moving to DLQ", agent_type)
            await self._handle_dead_letter(record, msg, f"Unknown agent type: {agent_type}")
            return record

        # Acquire concurrency semaphore
        await self._concurrency.acquire(agent_type)
        start_time = time.monotonic()

        try:
            # Mark as running (with optimistic lock)
            expected_state = record.state
            record.state = TaskState.RUNNING
            record.started_at = datetime.now(timezone.utc)
            record.attempt = msg.attempt + 1
            record.metadata["message_id"] = msg.message_id
            # Generate a unique execution_id for idempotency
            execution_id = str(uuid.uuid4())
            record.metadata["execution_id"] = execution_id
            if not await self._store.compare_and_swap(record.id, expected_state, record):
                # Another worker already claimed this task
                logger.debug("Task %s already claimed by another worker, acking", task_id)
                await self._queue.ack(msg.message_id)
                self._concurrency.release(agent_type)
                return None

            # Idempotency guard: re-read from store and verify our execution_id
            # is still current — prevents duplicate execution after crash/restart
            fresh = await self._store.get(record.id)
            if fresh and fresh.metadata.get("execution_id") != execution_id:
                logger.info(
                    "Task %s execution_id mismatch (ours=%s, store=%s), "
                    "another worker took over — skipping",
                    task_id, execution_id[:8],
                    fresh.metadata.get("execution_id", "?")[:8],
                )
                await self._queue.ack(msg.message_id)
                self._concurrency.release(agent_type)
                return None

            await self._notify_subscribers(task_id, "running", record)

            # Execute with timeout
            result = await asyncio.wait_for(
                agent.execute(
                    task_id=task_id,
                    prompt=record.prompt,
                    workflow_id=record.workflow_id,
                    node_id=record.node_id,
                    metadata=record.metadata,
                ),
                timeout=self._max_duration,
            )

            duration = time.monotonic() - start_time

            if result.success:
                await self._handle_success(record, msg, result, duration)
            else:
                error_action = result.metadata.get("error_action", "retry")
                error_msg = result.error or "Agent reported failure"

                if error_action == "fail":
                    await self._handle_failure(record, msg, result, duration)
                elif error_action == "dlq" or record.attempt >= record.max_retries:
                    await self._handle_dead_letter(record, msg, error_msg)
                else:
                    # Default: retry (covers "retry" action and any unknown)
                    await self._handle_retry(record, msg, error_msg)

        except asyncio.TimeoutError:
            duration = time.monotonic() - start_time
            await self._handle_retry_or_fail(
                record, msg, f"Task timed out after {self._max_duration}s"
            )
        except Exception as e:
            duration = time.monotonic() - start_time
            logger.exception("Unexpected error processing task=%s", task_id)
            await self._handle_retry_or_fail(record, msg, str(e))
        finally:
            self._concurrency.release(agent_type)

        return record

    # ------------------------------------------------------------------
    # Outcome handlers
    # ------------------------------------------------------------------

    async def _handle_success(
        self, record: TaskRecord, msg: Any, result: AgentResult, duration: float
    ) -> None:
        record.state = TaskState.SUCCEEDED
        record.result_json = result.output
        record.completed_at = datetime.now(timezone.utc)
        record.metadata.update(result.metadata)
        await self._store.update(record)
        await self._queue.ack(msg.message_id)
        self._metrics.record_success(record.agent_type, duration)
        await self._notify_subscribers(record.id, "succeeded", record)
        await self._fire_completion_webhook(record)
        logger.info(
            "Task %s succeeded (%.2fs, attempt %d)", record.id, duration, record.attempt
        )

    async def _handle_failure(
        self, record: TaskRecord, msg: Any, result: AgentResult, duration: float
    ) -> None:
        record.state = TaskState.FAILED
        record.error = result.error or "Task failed"
        record.completed_at = datetime.now(timezone.utc)
        record.metadata.update(result.metadata)
        await self._store.update(record)
        await self._queue.move_to_dlq(msg.message_id, record.error)
        self._metrics.record_failure(record.agent_type)
        await self._notify_subscribers(record.id, "failed", record)
        logger.warning("Task %s failed: %s", record.id, record.error)

    async def _handle_retry(self, record: TaskRecord, msg: Any, reason: str) -> None:
        delay = record.metadata.get("retry_after", 0)
        record.state = TaskState.QUEUED
        record.error = reason
        await self._store.update(record)
        await self._queue.ack(msg.message_id)
        self._metrics.record_retry(record.agent_type)

        if delay > 0:
            await asyncio.sleep(delay)

        # Re-enqueue with incremented attempt
        data = {
            "task_id": record.id,
            "agent_type": record.agent_type,
            "prompt": record.prompt,
            "attempt": record.attempt,
            "workflow_id": record.workflow_id,
            "node_id": record.node_id,
        }
        await self._queue.enqueue(record.id, data, priority=record.priority.value)
        logger.info(
            "Task %s retrying (attempt %d/%d): %s",
            record.id, record.attempt + 1, record.max_retries, reason,
        )

    async def _handle_retry_or_fail(self, record: TaskRecord, msg: Any, reason: str) -> None:
        """Retry if attempts remain, otherwise fail/DLQ."""
        if record.attempt < record.max_retries:
            await self._handle_retry(record, msg, reason)
        else:
            await self._handle_dead_letter(record, msg, reason)

    async def _handle_dead_letter(self, record: TaskRecord, msg: Any, reason: str) -> None:
        record.state = TaskState.DEAD_LETTER
        record.error = reason
        record.completed_at = datetime.now(timezone.utc)
        await self._store.update(record)
        await self._queue.move_to_dlq(msg.message_id, reason)
        self._metrics.record_dead_letter(record.agent_type)
        await self._notify_subscribers(record.id, "dead_letter", record)
        logger.warning("Task %s moved to DLQ: %s", record.id, reason)

    # ------------------------------------------------------------------
    # External worker support (claim/result pattern)
    # ------------------------------------------------------------------

    async def claim_task(
        self,
        agent_types: list[str],
        worker_id: str,
    ) -> Optional[TaskRecord]:
        """Claim the next available QUEUED task for an external worker.

        Uses compare-and-swap to prevent two workers from claiming the same task.
        """
        tasks = await self._store.list_tasks(state=TaskState.QUEUED, limit=50, offset=0)
        for task in tasks:
            if task.agent_type in agent_types:
                expected = task.state
                task.state = TaskState.RUNNING
                task.started_at = datetime.now(timezone.utc)
                task.attempt += 1
                task.metadata["worker_id"] = worker_id
                # Atomic: only succeeds if state is still QUEUED
                if await self._store.compare_and_swap(task.id, expected, task):
                    self._metrics.record_submit(task.agent_type)
                    await self._notify_subscribers(task.id, "running", task)
                    logger.info(
                        "Task %s claimed by worker %s (agent=%s, attempt %d)",
                        task.id, worker_id, task.agent_type, task.attempt,
                    )
                    return task
                # CAS failed — another worker claimed it, try next
                continue
        return None

    async def report_result(
        self,
        task_id: str,
        worker_id: str,
        success: bool,
        output: Optional[str] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[TaskRecord]:
        """Process execution result reported by an external worker.

        Applies the same retry/DLQ/success logic as internal workers:
        - Success → SUCCEEDED, store result, fire webhook
        - Failure + retries remaining → QUEUED (for re-claim)
        - Failure + exhausted → DEAD_LETTER
        - error_action=fail → FAILED immediately
        """
        record = await self._store.get(task_id)
        if not record:
            return None

        merged_meta = metadata or {}

        if success:
            record.state = TaskState.SUCCEEDED
            record.result_json = output
            record.completed_at = datetime.now(timezone.utc)
            record.metadata.update(merged_meta)
            await self._store.update(record)
            self._metrics.record_success(record.agent_type, 0)
            await self._notify_subscribers(record.id, "succeeded", record)
            await self._fire_completion_webhook(record)
            logger.info("Task %s succeeded (external worker %s)", record.id, worker_id)
        else:
            error_action = merged_meta.get("error_action", "retry")
            error_msg = error or "Agent reported failure"

            if error_action == "fail":
                record.state = TaskState.FAILED
                record.error = error_msg
                record.completed_at = datetime.now(timezone.utc)
                record.metadata.update(merged_meta)
                await self._store.update(record)
                self._metrics.record_failure(record.agent_type)
                await self._notify_subscribers(record.id, "failed", record)
                logger.warning("Task %s failed (external): %s", record.id, error_msg)

            elif error_action == "dlq" or record.attempt >= record.max_retries:
                record.state = TaskState.DEAD_LETTER
                record.error = error_msg
                record.completed_at = datetime.now(timezone.utc)
                record.metadata.update(merged_meta)
                await self._store.update(record)
                self._metrics.record_dead_letter(record.agent_type)
                await self._notify_subscribers(record.id, "dead_letter", record)
                logger.warning("Task %s → DLQ (external): %s", record.id, error_msg)

            else:
                # Retry — set back to QUEUED for re-claim
                record.state = TaskState.QUEUED
                record.error = error_msg
                record.metadata.update(merged_meta)
                await self._store.update(record)
                self._metrics.record_retry(record.agent_type)
                logger.info(
                    "Task %s retrying (attempt %d/%d, external): %s",
                    record.id, record.attempt + 1, record.max_retries, error_msg,
                )

        # Release concurrency slot
        try:
            self._concurrency.release(record.agent_type)
        except Exception:
            pass  # may not have been acquired

        return record

    # ------------------------------------------------------------------
    # Task operations
    # ------------------------------------------------------------------

    async def get_task(self, task_id: str) -> Optional[TaskRecord]:
        return await self._store.get(task_id)

    async def cancel_task(self, task_id: str) -> Optional[TaskRecord]:
        record = await self._store.get(task_id)
        if not record or record.state.is_terminal:
            return record
        record.state = TaskState.CANCELLED
        record.completed_at = datetime.now(timezone.utc)
        await self._store.update(record)
        await self._notify_subscribers(task_id, "cancelled", record)
        return record

    async def restart_task(self, task_id: str) -> Optional[TaskRecord]:
        """Restart a failed/DLQ task as a new task."""
        old = await self._store.get(task_id)
        if not old:
            return None
        return await self.submit_task(
            agent_type=old.agent_type,
            prompt=old.prompt,
            workflow_id=old.workflow_id,
            node_id=old.node_id,
            priority=old.priority,
            max_retries=old.max_retries,
            metadata={**old.metadata, "restarted_from": task_id},
        )

    async def approve_task(self, task_id: str) -> Optional[TaskRecord]:
        """Approve a pending (human-approval) task → enqueue it."""
        record = await self._store.get(task_id)
        if not record or record.state != TaskState.PENDING:
            return record
        record.state = TaskState.QUEUED
        await self._store.update(record)
        await self._enqueue(record)
        logger.info("Approved task=%s → queued", task_id)
        return record

    async def reject_task(self, task_id: str) -> Optional[TaskRecord]:
        """Reject a pending task → dead letter."""
        record = await self._store.get(task_id)
        if not record or record.state != TaskState.PENDING:
            return record
        record.state = TaskState.DEAD_LETTER
        record.error = "Rejected by human"
        record.completed_at = datetime.now(timezone.utc)
        await self._store.update(record)
        logger.info("Rejected task=%s → DLQ", task_id)
        return record

    # ------------------------------------------------------------------
    # SSE / Subscriptions
    # ------------------------------------------------------------------

    def subscribe(self, task_id: str, callback: Any) -> None:
        """Subscribe to task state changes (for SSE/WebSocket).

        When an event bus is available, subscriptions are routed through
        Redis Pub/Sub so events from any pod reach this client.
        """
        if self._event_bus:
            self._event_bus.subscribe(task_id, callback)
        else:
            if task_id not in self._subscribers:
                self._subscribers[task_id] = []
            self._subscribers[task_id].append(callback)

    def unsubscribe(self, task_id: str, callback: Any) -> None:
        if self._event_bus:
            self._event_bus.unsubscribe(task_id, callback)
        else:
            if task_id in self._subscribers:
                self._subscribers[task_id] = [
                    cb for cb in self._subscribers[task_id] if cb is not callback
                ]

    async def _notify_subscribers(
        self, task_id: str, event: str, record: TaskRecord
    ) -> None:
        # Publish via event bus (cross-pod) if available
        if self._event_bus:
            data = {
                "state": record.state.value,
                "result": record.result_json,
                "error": record.error,
                "attempt": record.attempt,
            }
            await self._event_bus.publish(task_id, event, data)
        # Also notify local subscribers (in-memory fallback)
        callbacks = self._subscribers.get(task_id, [])
        for cb in callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(event, record)
                else:
                    cb(event, record)
            except Exception:
                logger.exception("Subscriber error for task=%s", task_id)

    # ------------------------------------------------------------------
    # Completion webhook
    # ------------------------------------------------------------------

    async def _fire_completion_webhook(self, record: TaskRecord) -> None:
        if not self._webhook_url:
            return
        try:
            import httpx

            payload = {
                "task_id": record.id,
                "state": record.state.value,
                "result": record.result_json,
                "agent_type": record.agent_type,
            }
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(self._webhook_url, json=payload)
        except Exception:
            logger.warning("Completion webhook failed for task=%s", record.id)
