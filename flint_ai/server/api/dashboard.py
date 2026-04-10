"""Dashboard and monitoring API routes."""

import logging
from typing import Any

from pydantic import BaseModel

from flint_ai.server.engine import TaskResponse, TaskState

logger = logging.getLogger("flint.server.api.dashboard")


class DashboardSummary(BaseModel):
    total: int = 0
    by_state: dict[str, int] = {}
    task_counts: dict[str, int] = {}
    queue_length: int = 0
    dlq_length: int = 0
    worker_count: int = 0
    concurrency: dict[str, dict[str, int]] = {}


class DLQEntry(BaseModel):
    message_id: str
    task_id: str
    reason: str
    data: dict[str, Any]


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
            concurrency=await concurrency.get_stats(),
        )

    @app.get("/dashboard/concurrency", tags=["Dashboard"])
    async def agent_concurrency(request: Request) -> dict[str, dict[str, int]]:
        """Get per-agent concurrency usage."""
        return await request.app.state.concurrency.get_stats()

    @app.get("/dashboard/dlq", tags=["Dashboard"])
    async def list_dlq(request: Request, count: int = 50) -> list[DLQEntry]:
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
    async def retry_dlq(message_id: str, request: Request) -> dict[str, str]:
        """Retry a dead-lettered message."""
        try:
            new_id = await request.app.state.queue.retry_dlq_message(message_id)
            return {"status": "retried", "new_message_id": new_id}
        except KeyError as e:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="DLQ message not found") from e

    @app.post("/dashboard/dlq/purge", tags=["Dashboard"])
    async def purge_dlq(request: Request) -> dict[str, int]:
        """Purge all DLQ messages."""
        count = await request.app.state.queue.purge_dlq()
        return {"purged": count}

    @app.get("/dashboard/approvals", tags=["Dashboard"])
    async def list_approvals(request: Request) -> list[TaskResponse]:
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
        for agent_type, stats in (await concurrency.get_stats()).items():
            metrics.update_concurrency(agent_type, stats["limit"], stats["used"])

        body = metrics.generate_latest()
        return Response(content=body, media_type="text/plain; charset=utf-8")

    @app.get("/health", tags=["Monitoring"])
    async def health(request: Request) -> Any:
        """Health check — tests queue and store connectivity."""
        checks: dict[str, Any] = {}
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
    async def ready(request: Request) -> Any:
        """Readiness probe — returns 503 if any dependency is down."""
        try:
            await request.app.state.queue.get_queue_length()
            await request.app.state.task_engine._store.count_by_state()
            return {"status": "ready"}
        except Exception as e:
            from starlette.responses import JSONResponse

            return JSONResponse({"status": "not_ready", "error": str(e)}, status_code=503)

    @app.get("/live", tags=["Monitoring"])
    async def live() -> dict[str, str]:
        """Liveness probe — always returns 200 if the process is alive."""
        return {"status": "live"}

    # ------------------------------------------------------------------
    # Cost tracking endpoints
    # ------------------------------------------------------------------

    @app.get("/dashboard/cost/summary", tags=["Cost"])
    async def cost_summary(request: Request) -> dict[str, Any]:
        """Aggregate cost summary across all tasks."""
        records = await request.app.state.task_engine._store.list_tasks(limit=1000)
        total_cost = 0.0
        total_tokens = 0
        by_model: dict[str, dict[str, Any]] = {}
        by_agent: dict[str, dict[str, Any]] = {}

        for r in records:
            cb = r.metadata.get("cost_breakdown")
            if not cb:
                continue
            cost = cb.get("total_cost_usd", 0.0) or 0.0
            tokens = cb.get("total_tokens", 0) or 0
            model = cb.get("model", "unknown")
            total_cost += cost
            total_tokens += tokens

            if model not in by_model:
                by_model[model] = {"cost_usd": 0.0, "tokens": 0, "count": 0}
            by_model[model]["cost_usd"] += cost
            by_model[model]["tokens"] += tokens
            by_model[model]["count"] += 1

            if r.agent_type not in by_agent:
                by_agent[r.agent_type] = {"cost_usd": 0.0, "tokens": 0, "count": 0}
            by_agent[r.agent_type]["cost_usd"] += cost
            by_agent[r.agent_type]["tokens"] += tokens
            by_agent[r.agent_type]["count"] += 1

        for m in by_model.values():
            m["cost_usd"] = round(m["cost_usd"], 6)
        for a in by_agent.values():
            a["cost_usd"] = round(a["cost_usd"], 6)

        return {
            "total_cost_usd": round(total_cost, 6),
            "total_tokens": total_tokens,
            "task_count": len([r for r in records if r.metadata.get("cost_breakdown")]),
            "by_model": by_model,
            "by_agent": by_agent,
        }

    @app.get("/dashboard/cost/task/{task_id}", tags=["Cost"])
    async def cost_task(task_id: str, request: Request) -> dict[str, Any]:
        """Cost breakdown for a single task."""
        record = await request.app.state.task_engine._store.get(task_id)
        if not record:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Task not found")

        cost_breakdown = record.metadata.get("cost_breakdown")
        return {
            "task_id": task_id,
            "agent_type": record.agent_type,
            "state": record.state.value,
            "cost_breakdown": cost_breakdown,
            "attempt": record.attempt,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }

    @app.get("/dashboard/cost/workflow/{run_id}", tags=["Cost"])
    async def cost_workflow(run_id: str, request: Request) -> dict[str, Any]:
        """Cost breakdown for a workflow run (aggregated across all nodes)."""
        records = await request.app.state.task_engine._store.list_tasks(limit=1000)
        workflow_tasks = [r for r in records if r.metadata.get("workflow_run_id") == run_id]

        total_cost = 0.0
        total_tokens = 0
        node_costs: dict[str, dict[str, Any]] = {}

        for r in workflow_tasks:
            cb = r.metadata.get("cost_breakdown")
            if not cb:
                continue
            cost = cb.get("total_cost_usd", 0.0) or 0.0
            tokens = cb.get("total_tokens", 0) or 0
            node_id = r.node_id or "unknown"
            total_cost += cost
            total_tokens += tokens

            if node_id not in node_costs:
                node_costs[node_id] = {
                    "cost_usd": 0.0,
                    "tokens": 0,
                    "task_count": 0,
                    "agent_type": r.agent_type,
                }
            node_costs[node_id]["cost_usd"] += cost
            node_costs[node_id]["tokens"] += tokens
            node_costs[node_id]["task_count"] += 1

        for nc in node_costs.values():
            nc["cost_usd"] = round(nc["cost_usd"], 6)

        return {
            "workflow_run_id": run_id,
            "total_cost_usd": round(total_cost, 6),
            "total_tokens": total_tokens,
            "node_count": len(node_costs),
            "node_costs": node_costs,
        }

    @app.get("/dashboard/cost/timeline", tags=["Cost"])
    async def cost_timeline(request: Request, hours: int = 24) -> list[dict[str, Any]]:
        """Cost over time for charting (hourly buckets)."""
        from datetime import datetime, timedelta, timezone

        records = await request.app.state.task_engine._store.list_tasks(limit=1000)
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=hours)

        buckets: dict[str, dict[str, Any]] = {}
        for r in records:
            if not r.completed_at or r.completed_at < cutoff:
                continue
            cb = r.metadata.get("cost_breakdown")
            if not cb:
                continue
            hour_key = r.completed_at.strftime("%Y-%m-%dT%H:00:00Z")
            cost = cb.get("total_cost_usd", 0.0) or 0.0
            tokens = cb.get("total_tokens", 0) or 0

            if hour_key not in buckets:
                buckets[hour_key] = {"timestamp": hour_key, "cost_usd": 0.0, "tokens": 0, "task_count": 0}
            buckets[hour_key]["cost_usd"] += cost
            buckets[hour_key]["tokens"] += tokens
            buckets[hour_key]["task_count"] += 1

        for b in buckets.values():
            b["cost_usd"] = round(b["cost_usd"], 6)

        return sorted(buckets.values(), key=lambda x: x["timestamp"])

    # ------------------------------------------------------------------
    # AI Usage & Event Tracking endpoints
    # ------------------------------------------------------------------

    @app.get("/dashboard/usage/events", tags=["Usage"])
    async def usage_events(
        request: Request,
        provider: str | None = None,
        model: str | None = None,
        event_type: str | None = None,
        task_id: str | None = None,
        workflow_run_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List recent AI usage events with optional filters."""
        records = await request.app.state.task_engine._store.list_tasks(limit=2000)
        events: list[dict[str, Any]] = []

        for r in records:
            cb = r.metadata.get("cost_breakdown")
            if not cb:
                continue

            event = {
                "task_id": r.id,
                "agent_type": r.agent_type,
                "model": cb.get("model", "unknown"),
                "provider": "openai",
                "input_tokens": cb.get("prompt_tokens", 0),
                "output_tokens": cb.get("completion_tokens", 0),
                "total_tokens": cb.get("total_tokens", 0),
                "cost_usd": cb.get("total_cost_usd", 0.0),
                "tool_costs": cb.get("tool_call_costs", []),
                "workflow_run_id": r.metadata.get("workflow_run_id"),
                "node_id": r.node_id,
                "attempt": r.attempt,
                "state": r.state.value,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }

            if provider and event["provider"] != provider:
                continue
            if model and event["model"] != model:
                continue
            if event_type:
                pass  # event_type not available in cost_breakdown metadata yet
            if task_id and event["task_id"] != task_id:
                continue
            if workflow_run_id and event.get("workflow_run_id") != workflow_run_id:
                continue

            events.append(event)
            if len(events) >= limit:
                break

        return events

    @app.get("/dashboard/usage/summary", tags=["Usage"])
    async def usage_summary(request: Request) -> dict[str, Any]:
        """Aggregated usage summary across all tasks."""
        records = await request.app.state.task_engine._store.list_tasks(limit=2000)
        total_cost = 0.0
        total_input = 0
        total_output = 0
        total_events = 0
        by_model: dict[str, dict[str, Any]] = {}
        by_provider: dict[str, dict[str, Any]] = {}

        for r in records:
            cb = r.metadata.get("cost_breakdown")
            if not cb:
                continue
            cost = cb.get("total_cost_usd", 0.0) or 0.0
            input_t = cb.get("prompt_tokens", 0) or 0
            output_t = cb.get("completion_tokens", 0) or 0
            model = cb.get("model", "unknown")
            total_cost += cost
            total_input += input_t
            total_output += output_t
            total_events += 1

            if model not in by_model:
                by_model[model] = {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0, "call_count": 0}
            by_model[model]["cost_usd"] += cost
            by_model[model]["input_tokens"] += input_t
            by_model[model]["output_tokens"] += output_t
            by_model[model]["call_count"] += 1

            prov = "openai"
            if prov not in by_provider:
                by_provider[prov] = {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0, "call_count": 0}
            by_provider[prov]["cost_usd"] += cost
            by_provider[prov]["input_tokens"] += input_t
            by_provider[prov]["output_tokens"] += output_t
            by_provider[prov]["call_count"] += 1

        for m in by_model.values():
            m["cost_usd"] = round(m["cost_usd"], 6)
        for p in by_provider.values():
            p["cost_usd"] = round(p["cost_usd"], 6)

        return {
            "total_cost_usd": round(total_cost, 6),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "event_count": total_events,
            "by_model": by_model,
            "by_provider": by_provider,
        }

    @app.get("/dashboard/usage/retry/{task_id}", tags=["Usage"])
    async def usage_retry(task_id: str, request: Request) -> dict[str, Any]:
        """Retry-aware cost breakdown for a task."""
        records = await request.app.state.task_engine._store.list_tasks(limit=2000)
        task_records = [r for r in records if r.id == task_id]

        if not task_records:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Task not found")

        first_cost = 0.0
        retry_cost = 0.0
        first_tokens = 0
        retry_tokens = 0

        for i, r in enumerate(task_records):
            cb = r.metadata.get("cost_breakdown")
            if not cb:
                continue
            cost = cb.get("total_cost_usd", 0.0) or 0.0
            tokens = cb.get("total_tokens", 0) or 0
            if i == 0:
                first_cost += cost
                first_tokens += tokens
            else:
                retry_cost += cost
                retry_tokens += tokens

        return {
            "task_id": task_id,
            "attempts": len(task_records),
            "first_attempt_cost_usd": round(first_cost, 6),
            "retry_cost_usd": round(retry_cost, 6),
            "total_cost_usd": round(first_cost + retry_cost, 6),
            "first_attempt_tokens": first_tokens,
            "retry_tokens": retry_tokens,
            "total_tokens": first_tokens + retry_tokens,
        }

    # ------------------------------------------------------------------
    # Tool execution endpoints
    # ------------------------------------------------------------------

    @app.get("/dashboard/tools/executions", tags=["Tools"])
    async def tool_executions(
        request: Request,
        task_id: str | None = None,
        workflow_run_id: str | None = None,
        tool_name: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List tool executions with optional filters."""
        tool_store = getattr(request.app.state, "tool_exec_store", None)
        if not tool_store:
            return []

        if task_id:
            executions = await tool_store.list_by_task(task_id, limit=limit)
        elif workflow_run_id:
            executions = await tool_store.list_by_workflow_run(workflow_run_id, limit=limit)
        elif tool_name:
            executions = await tool_store.list_by_tool_name(tool_name, limit=limit)
        else:
            executions = await tool_store.list_recent(limit=limit, offset=offset)

        if status:
            executions = [e for e in executions if e.status == status]

        return [
            {
                "id": e.id,
                "task_id": e.task_id,
                "workflow_run_id": e.workflow_run_id,
                "node_id": e.node_id,
                "tool_name": e.tool_name,
                "input_json": e.input_json,
                "output_json": e.output_json,
                "duration_ms": e.duration_ms,
                "error": e.error,
                "stack_trace": e.stack_trace,
                "sanitized_input": e.sanitized_input,
                "cost_usd": e.cost_usd,
                "status": e.status,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in executions
        ]

    @app.get("/dashboard/tools/errors", tags=["Tools"])
    async def tool_errors(
        request: Request,
        workflow_run_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List failed tool executions."""
        tool_store = getattr(request.app.state, "tool_exec_store", None)
        if not tool_store:
            return []

        executions = await tool_store.list_errors(workflow_run_id=workflow_run_id, limit=limit)
        return [
            {
                "id": e.id,
                "task_id": e.task_id,
                "workflow_run_id": e.workflow_run_id,
                "node_id": e.node_id,
                "tool_name": e.tool_name,
                "error": e.error,
                "stack_trace": e.stack_trace,
                "sanitized_input": e.sanitized_input,
                "duration_ms": e.duration_ms,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in executions
        ]

    @app.get("/dashboard/tools/stats", tags=["Tools"])
    async def tool_stats(request: Request) -> dict[str, Any]:
        """Aggregate tool execution statistics."""
        tool_store = getattr(request.app.state, "tool_exec_store", None)
        if not tool_store:
            return {"total_executions": 0, "by_tool": {}, "error_rate": 0.0}

        executions = await tool_store.list_recent(limit=1000)
        total = len(executions)
        errors = len([e for e in executions if e.status == "failed"])
        by_tool: dict[str, dict[str, Any]] = {}

        for e in executions:
            if e.tool_name not in by_tool:
                by_tool[e.tool_name] = {"count": 0, "errors": 0, "avg_duration_ms": 0.0, "total_duration_ms": 0.0}
            by_tool[e.tool_name]["count"] += 1
            if e.status == "failed":
                by_tool[e.tool_name]["errors"] += 1
            if e.duration_ms is not None:
                by_tool[e.tool_name]["total_duration_ms"] += e.duration_ms

        for t in by_tool.values():
            if t["count"] > 0:
                t["avg_duration_ms"] = round(t["total_duration_ms"] / t["count"], 2)
            del t["total_duration_ms"]

        return {
            "total_executions": total,
            "error_count": errors,
            "error_rate": round(errors / total, 4) if total > 0 else 0.0,
            "by_tool": by_tool,
        }
