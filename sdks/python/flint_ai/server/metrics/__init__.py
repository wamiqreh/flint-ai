"""Prometheus metrics for the Flint server."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("flint.server.metrics")

# Lazy-import prometheus_client so the server works without it
_prometheus: Any = None


def _get_prometheus() -> Any:
    global _prometheus
    if _prometheus is None:
        try:
            import prometheus_client

            _prometheus = prometheus_client
        except ImportError:
            logger.warning(
                "prometheus_client not installed — metrics disabled. "
                "Install with: pip install prometheus-client"
            )
            _prometheus = False
    return _prometheus if _prometheus else None


class FlintMetrics:
    """Prometheus metrics registry for the Flint server."""

    def __init__(self) -> None:
        prom = _get_prometheus()
        if not prom:
            self._enabled = False
            return
        self._enabled = True

        self.tasks_submitted = prom.Counter(
            "flint_tasks_submitted_total",
            "Total tasks submitted",
            ["agent_type"],
        )
        self.tasks_succeeded = prom.Counter(
            "flint_tasks_succeeded_total",
            "Total tasks that succeeded",
            ["agent_type"],
        )
        self.tasks_failed = prom.Counter(
            "flint_tasks_failed_total",
            "Total tasks that failed",
            ["agent_type"],
        )
        self.tasks_retried = prom.Counter(
            "flint_tasks_retried_total",
            "Total task retry attempts",
            ["agent_type"],
        )
        self.tasks_dead_lettered = prom.Counter(
            "flint_tasks_dead_lettered_total",
            "Total tasks moved to DLQ",
            ["agent_type"],
        )
        self.queue_length = prom.Gauge(
            "flint_queue_length",
            "Current queue depth",
        )
        self.dlq_length = prom.Gauge(
            "flint_dlq_length",
            "Current dead-letter queue depth",
        )
        self.agent_concurrency_limit = prom.Gauge(
            "flint_agent_concurrency_limit",
            "Concurrency limit per agent type",
            ["agent_type"],
        )
        self.agent_concurrency_used = prom.Gauge(
            "flint_agent_concurrency_used",
            "Current concurrency usage per agent type",
            ["agent_type"],
        )
        self.task_duration_seconds = prom.Histogram(
            "flint_task_duration_seconds",
            "Task execution duration",
            ["agent_type"],
            buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
        )
        self.workflow_runs_started = prom.Counter(
            "flint_workflow_runs_started_total",
            "Total workflow runs started",
        )
        self.workflow_runs_completed = prom.Counter(
            "flint_workflow_runs_completed_total",
            "Total workflow runs completed",
            ["status"],
        )
        self.reclaimed_entries = prom.Counter(
            "flint_reclaimed_entries_total",
            "Total stale messages reclaimed from pending",
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def record_submit(self, agent_type: str) -> None:
        if self._enabled:
            self.tasks_submitted.labels(agent_type=agent_type).inc()

    def record_success(self, agent_type: str, duration: float) -> None:
        if self._enabled:
            self.tasks_succeeded.labels(agent_type=agent_type).inc()
            self.task_duration_seconds.labels(agent_type=agent_type).observe(duration)

    def record_failure(self, agent_type: str) -> None:
        if self._enabled:
            self.tasks_failed.labels(agent_type=agent_type).inc()

    def record_retry(self, agent_type: str) -> None:
        if self._enabled:
            self.tasks_retried.labels(agent_type=agent_type).inc()

    def record_dead_letter(self, agent_type: str) -> None:
        if self._enabled:
            self.tasks_dead_lettered.labels(agent_type=agent_type).inc()

    def update_queue_lengths(self, queue_len: int, dlq_len: int) -> None:
        if self._enabled:
            self.queue_length.set(queue_len)
            self.dlq_length.set(dlq_len)

    def update_concurrency(self, agent_type: str, limit: int, used: int) -> None:
        if self._enabled:
            self.agent_concurrency_limit.labels(agent_type=agent_type).set(limit)
            self.agent_concurrency_used.labels(agent_type=agent_type).set(used)

    def record_reclaimed(self, count: int) -> None:
        if self._enabled:
            self.reclaimed_entries.inc(count)

    def generate_latest(self) -> bytes:
        """Generate Prometheus text format output."""
        prom = _get_prometheus()
        if prom:
            return prom.generate_latest()
        return b""
