"""Worker API routes — claim tasks, report results, heartbeat.

These endpoints enable the client-worker pattern where external workers
(running in the dev's code) pull tasks from the Flint server, execute
them locally, and report results back.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("flint.server.api.workers")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ClaimRequest(BaseModel):
    """Request to claim a task for execution."""
    worker_id: str
    agent_types: list[str]


class ClaimResponse(BaseModel):
    """Task data returned to an external worker after claiming."""
    id: str
    agent_type: str
    prompt: str
    attempt: int
    max_retries: int
    workflow_id: str | None = None
    node_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResultRequest(BaseModel):
    """Result reported by an external worker after executing a task."""
    worker_id: str
    success: bool
    output: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class HeartbeatRequest(BaseModel):
    """Heartbeat from an external worker to keep a task lease alive."""
    worker_id: str


# ---------------------------------------------------------------------------
# Route factory
# ---------------------------------------------------------------------------

def create_worker_routes(app: Any) -> None:
    """Register worker-related API routes (claim/result/heartbeat)."""
    from fastapi import HTTPException, Request
    from fastapi.responses import JSONResponse

    @app.post("/tasks/claim", tags=["Workers"])
    async def claim_task(req: ClaimRequest, request: Request):
        """Claim the next available task matching the worker's agent types.

        Returns 200 with task data if a task is available, or 204 if no
        tasks are available for the requested agent types.
        """
        task_engine = request.app.state.task_engine
        record = await task_engine.claim_task(
            agent_types=req.agent_types,
            worker_id=req.worker_id,
        )
        if not record:
            return JSONResponse(status_code=204, content=None)

        return ClaimResponse(
            id=record.id,
            agent_type=record.agent_type,
            prompt=record.prompt,
            attempt=record.attempt,
            max_retries=record.max_retries,
            workflow_id=record.workflow_id,
            node_id=record.node_id,
            metadata=record.metadata,
        )

    @app.post("/tasks/{task_id}/result", tags=["Workers"])
    async def report_result(task_id: str, req: ResultRequest, request: Request):
        """Report execution result from an external worker.

        Triggers retry/DLQ/DAG advancement logic on the server side,
        exactly as if an internal worker had processed the task.
        """
        task_engine = request.app.state.task_engine
        dag_engine = request.app.state.dag_engine
        workflow_store = request.app.state.workflow_store
        metrics = request.app.state.metrics

        record = await task_engine.report_result(
            task_id=task_id,
            worker_id=req.worker_id,
            success=req.success,
            output=req.output,
            error=req.error,
            metadata=req.metadata,
        )
        if not record:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        # Advance DAG if this is a workflow task (same logic as internal worker)
        if record.workflow_id and record.node_id:
            await _advance_dag(
                record=record,
                task_engine=task_engine,
                dag_engine=dag_engine,
                workflow_store=workflow_store,
                metrics=metrics,
            )

        from flint_ai.server.engine import TaskResponse
        return TaskResponse.from_record(record)

    @app.post("/tasks/{task_id}/heartbeat", tags=["Workers"])
    async def heartbeat(task_id: str, req: HeartbeatRequest, request: Request):
        """Keep a claimed task alive. Resets Redis idle time to prevent reclaim."""
        task_engine = request.app.state.task_engine
        record = await task_engine.get_task(task_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        # Update heartbeat timestamp in metadata
        from datetime import datetime, timezone
        record.metadata["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
        record.metadata["worker_id"] = req.worker_id
        await task_engine._store.update(record)

        # Reset Redis idle time so XAUTOCLAIM won't steal this task
        queue = request.app.state.queue
        if hasattr(queue, "reset_idle"):
            msg_id = record.metadata.get("message_id")
            if msg_id:
                await queue.reset_idle(msg_id)

        return {"status": "ok"}


async def _advance_dag(
    record: Any,
    task_engine: Any,
    dag_engine: Any,
    workflow_store: Any,
    metrics: Any,
) -> None:
    """Advance DAG after an external worker reports a task result.

    Mirrors the Worker._advance_dag() logic for internal workers.
    """

    run_id = record.metadata.get("workflow_run_id")
    if not run_id:
        return

    try:
        run = await workflow_store.get_run(run_id)
        if not run:
            logger.warning("Workflow run %s not found for task %s", run_id, record.id)
            return

        defn = await workflow_store.get_definition(run.workflow_id)
        if not defn:
            logger.warning("Workflow %s not found for run %s", run.workflow_id, run_id)
            return

        node_id = record.node_id

        failed_values = {"failed", "dead_letter"}
        terminal_values = {"succeeded", "failed", "dead_letter", "cancelled"}
        state_val = record.state.value if hasattr(record.state, "value") else str(record.state)

        if state_val in failed_values:
            result = await dag_engine.on_task_failed(run, node_id, record, defn)
            if result:
                node, enriched_prompt = result
                new_record = await task_engine.submit_task(
                    agent_type=node.agent_type,
                    prompt=enriched_prompt,
                    workflow_id=run.workflow_id,
                    node_id=node.id,
                    max_retries=node.retry_policy.max_retries,
                    human_approval=node.human_approval,
                    metadata={"workflow_run_id": run.id, **node.metadata},
                )
                run.node_states[node.id] = new_record.state
                run.node_task_ids.setdefault(node.id, []).append(new_record.id)
                logger.info(
                    "DAG retry/fallback: workflow=%s node=%s task=%s",
                    run.workflow_id, node.id, new_record.id,
                )
            await workflow_store.update_run(run)

        elif state_val in terminal_values:
            ready_nodes = await dag_engine.on_task_completed(run, node_id, record, defn)
            for node, enriched_prompt in ready_nodes:
                new_record = await task_engine.submit_task(
                    agent_type=node.agent_type,
                    prompt=enriched_prompt,
                    workflow_id=run.workflow_id,
                    node_id=node.id,
                    max_retries=node.retry_policy.max_retries,
                    human_approval=node.human_approval,
                    metadata={"workflow_run_id": run.id, **node.metadata},
                )
                run.node_states[node.id] = new_record.state
                run.node_task_ids.setdefault(node.id, []).append(new_record.id)
                logger.info(
                    "DAG advanced: workflow=%s node=%s → %s task=%s",
                    run.workflow_id, node.id, new_record.state.value, new_record.id,
                )
            await workflow_store.update_run(run)

    except Exception:
        logger.exception("Error advancing DAG for task %s", record.id)
