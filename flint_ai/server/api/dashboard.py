"""Dashboard and monitoring API routes."""

import logging
from typing import Any, Dict, List

from pydantic import BaseModel

from flint_ai.server.engine import TaskResponse, TaskState

logger = logging.getLogger("flint.server.api.dashboard")


class DashboardSummary(BaseModel):
    total: int = 0
    by_state: Dict[str, int] = {}
    task_counts: Dict[str, int] = {}
    queue_length: int = 0
    dlq_length: int = 0
    worker_count: int = 0
    concurrency: Dict[str, Dict[str, int]] = {}


class DLQEntry(BaseModel):
    message_id: str
    task_id: str
    reason: str
    data: Dict[str, Any]


def create_dashboard_routes(app: Any) -> None:
    """Register dashboard/monitoring API routes."""
    from fastapi import Request, Response

    @app.get("/dashboard/summary", response_model=DashboardSummary, tags=["Dashboard"])
    async def dashboard_summary(request: Request) -> DashboardSummary:
        """Get dashboard summary with task counts, queue depth, concurrency."""
        task_engine = request.app.state.task_engine
        queue = request.app.state.queue
        concurrency = request.app.state.concurrency
        worker_pool = request.app.state.worker_pool
        counts = await task_engine._store.count_by_state()
        q_len = await queue.get_queue_length()
        dlq_len = await queue.get_dlq_length()

        counts_dict = {k.value: v for k, v in counts.items()}
        total = sum(counts_dict.values())

        return DashboardSummary(
            total=total,
            by_state=counts_dict,
            task_counts=counts_dict,
            queue_length=q_len,
            dlq_length=dlq_len,
            worker_count=worker_pool.worker_count if worker_pool else 0,
            concurrency=concurrency.get_stats(),
        )

    @app.get("/dashboard/concurrency", tags=["Dashboard"])
    async def agent_concurrency(request: Request) -> Dict[str, Dict[str, int]]:
        """Get per-agent concurrency usage."""
        return request.app.state.concurrency.get_stats()

    @app.get("/dashboard/dlq", tags=["Dashboard"])
    async def list_dlq(request: Request, count: int = 50) -> List[DLQEntry]:
        """List messages in the dead-letter queue."""
        messages = await request.app.state.queue.get_dlq_messages(count=count)
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
    async def retry_dlq(message_id: str, request: Request) -> Dict[str, str]:
        """Retry a dead-lettered message."""
        try:
            new_id = await request.app.state.queue.retry_dlq_message(message_id)
            return {"status": "retried", "new_message_id": new_id}
        except KeyError:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="DLQ message not found")

    @app.post("/dashboard/dlq/purge", tags=["Dashboard"])
    async def purge_dlq(request: Request) -> Dict[str, int]:
        """Purge all DLQ messages."""
        count = await request.app.state.queue.purge_dlq()
        return {"purged": count}

    @app.get("/dashboard/approvals", tags=["Dashboard"])
    async def list_approvals(request: Request) -> List[TaskResponse]:
        """List tasks awaiting human approval."""
        records = await request.app.state.task_engine._store.list_tasks(state=TaskState.PENDING, limit=100)
        return [TaskResponse.from_record(r) for r in records]

    @app.get("/metrics", tags=["Monitoring"])
    async def prometheus_metrics(request: Request) -> Response:
        """Prometheus metrics endpoint."""
        queue = request.app.state.queue
        metrics = request.app.state.metrics
        concurrency = request.app.state.concurrency
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
    async def health(request: Request) -> Dict[str, Any]:
        """Health check — tests queue and store connectivity."""
        checks: Dict[str, Any] = {}
        healthy = True

        # Check queue
        try:
            await request.app.state.queue.get_queue_length()
            checks["queue"] = "ok"
        except Exception as e:
            checks["queue"] = f"error: {e}"
            healthy = False

        # Check store
        try:
            await request.app.state.task_engine._store.count_by_state()
            checks["store"] = "ok"
        except Exception as e:
            checks["store"] = f"error: {e}"
            healthy = False

        status = "healthy" if healthy else "degraded"
        status_code = 200 if healthy else 503
        from starlette.responses import JSONResponse
        return JSONResponse({"status": status, "checks": checks}, status_code=status_code)

    @app.get("/ready", tags=["Monitoring"])
    async def ready(request: Request) -> Dict[str, Any]:
        """Readiness probe — returns 503 if any dependency is down."""
        try:
            await request.app.state.queue.get_queue_length()
            await request.app.state.task_engine._store.count_by_state()
            return {"status": "ready"}
        except Exception as e:
            from starlette.responses import JSONResponse
            return JSONResponse({"status": "not_ready", "error": str(e)}, status_code=503)

    @app.get("/live", tags=["Monitoring"])
    async def live() -> Dict[str, str]:
        """Liveness probe — always returns 200 if the process is alive."""
        return {"status": "live"}
