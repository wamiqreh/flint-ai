"""Dashboard and monitoring API routes."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from pydantic import BaseModel

from flint_ai.server.engine import TaskResponse, TaskState

logger = logging.getLogger("flint.server.api.dashboard")


class DashboardSummary(BaseModel):
    task_counts: Dict[str, int]
    queue_length: int
    dlq_length: int
    worker_count: int
    concurrency: Dict[str, Dict[str, int]]


class DLQEntry(BaseModel):
    message_id: str
    task_id: str
    reason: str
    data: Dict[str, Any]


def create_dashboard_routes(app: Any) -> None:
    """Register dashboard/monitoring API routes."""
    from fastapi import Response

    task_engine = app.state.task_engine
    queue = app.state.queue
    metrics = app.state.metrics
    concurrency = app.state.concurrency
    worker_pool = app.state.worker_pool

    @app.get("/dashboard/summary", response_model=DashboardSummary, tags=["Dashboard"])
    async def dashboard_summary() -> DashboardSummary:
        """Get dashboard summary with task counts, queue depth, concurrency."""
        counts = await task_engine._store.count_by_state()
        q_len = await queue.get_queue_length()
        dlq_len = await queue.get_dlq_length()

        return DashboardSummary(
            task_counts={k.value: v for k, v in counts.items()},
            queue_length=q_len,
            dlq_length=dlq_len,
            worker_count=worker_pool.worker_count if worker_pool else 0,
            concurrency=concurrency.get_stats(),
        )

    @app.get("/dashboard/agents/concurrency", tags=["Dashboard"])
    async def agent_concurrency() -> Dict[str, Dict[str, int]]:
        """Get per-agent concurrency usage."""
        return concurrency.get_stats()

    @app.get("/dashboard/dlq", tags=["Dashboard"])
    async def list_dlq(count: int = 50) -> List[DLQEntry]:
        """List messages in the dead-letter queue."""
        messages = await queue.get_dlq_messages(count=count)
        return [
            DLQEntry(
                message_id=m.message_id,
                task_id=m.task_id,
                reason=m.data.get("dlq_reason", ""),
                data=m.data,
            )
            for m in messages
        ]

    @app.post("/dashboard/dlq/{message_id}/retry", tags=["Dashboard"])
    async def retry_dlq(message_id: str) -> Dict[str, str]:
        """Retry a dead-lettered message."""
        try:
            new_id = await queue.retry_dlq_message(message_id)
            return {"status": "retried", "new_message_id": new_id}
        except KeyError:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="DLQ message not found")

    @app.post("/dashboard/dlq/purge", tags=["Dashboard"])
    async def purge_dlq() -> Dict[str, int]:
        """Purge all DLQ messages."""
        count = await queue.purge_dlq()
        return {"purged": count}

    @app.get("/dashboard/approvals", tags=["Dashboard"])
    async def list_approvals() -> List[TaskResponse]:
        """List tasks awaiting human approval."""
        records = await task_engine._store.list_tasks(state=TaskState.PENDING, limit=100)
        return [TaskResponse.from_record(r) for r in records]

    @app.get("/metrics", tags=["Monitoring"])
    async def prometheus_metrics() -> Response:
        """Prometheus metrics endpoint."""
        # Update queue metrics before serving
        q_len = await queue.get_queue_length()
        dlq_len = await queue.get_dlq_length()
        metrics.update_queue_lengths(q_len, dlq_len)

        # Update concurrency metrics
        for agent_type, stats in concurrency.get_stats().items():
            metrics.update_concurrency(agent_type, stats["limit"], stats["used"])

        body = metrics.generate_latest()
        return Response(content=body, media_type="text/plain; charset=utf-8")

    @app.get("/health", tags=["Monitoring"])
    async def health() -> Dict[str, str]:
        return {"status": "healthy"}

    @app.get("/ready", tags=["Monitoring"])
    async def ready() -> Dict[str, str]:
        return {"status": "ready"}

    @app.get("/live", tags=["Monitoring"])
    async def live() -> Dict[str, str]:
        return {"status": "live"}
