"""Workflow API routes."""

import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from flint_ai.server.engine import (
    TaskState,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowRunState,
)

logger = logging.getLogger("flint.server.api.workflows")


class StartWorkflowRequest(BaseModel):
    context: Dict[str, Any] = Field(default_factory=dict)


class WorkflowRunResponse(BaseModel):
    id: str
    workflow_id: str
    state: WorkflowRunState
    node_states: Dict[str, str]
    task_ids: Dict[str, str] = {}
    started_at: str
    created_at: str
    completed_at: Optional[str] = None

    @classmethod
    def from_run(cls, run: WorkflowRun) -> "WorkflowRunResponse":
        ts = run.created_at.isoformat()
        # task_ids: first task per node (for UI display)
        task_ids = {k: v[0] if v else "" for k, v in run.node_task_ids.items()}
        return cls(
            id=run.id,
            workflow_id=run.workflow_id,
            state=run.state,
            node_states={k: v.value if hasattr(v, 'value') else v for k, v in run.node_states.items()},
            task_ids=task_ids,
            started_at=ts,
            created_at=ts,
            completed_at=run.completed_at.isoformat() if run.completed_at else None,
        )


def create_workflow_routes(app: Any) -> None:
    """Register workflow-related API routes."""
    from fastapi import HTTPException, Request

    @app.post("/workflows", tags=["Workflows"])
    async def create_workflow(definition: WorkflowDefinition, request: Request) -> WorkflowDefinition:
        """Create or update a workflow definition."""
        dag_engine = request.app.state.dag_engine
        errors = dag_engine.validate(definition)
        if errors:
            raise HTTPException(status_code=422, detail={"errors": errors})
        return await request.app.state.workflow_store.save_definition(definition)

    @app.put("/workflows/{workflow_id}", tags=["Workflows"])
    async def update_workflow(workflow_id: str, definition: WorkflowDefinition, request: Request) -> WorkflowDefinition:
        """Update an existing workflow definition."""
        dag_engine = request.app.state.dag_engine
        definition.id = workflow_id
        errors = dag_engine.validate(definition)
        if errors:
            raise HTTPException(status_code=422, detail={"errors": errors})
        return await request.app.state.workflow_store.save_definition(definition)

    @app.get("/workflows", tags=["Workflows"])
    async def list_workflows(request: Request, limit: int = 100) -> List[WorkflowDefinition]:
        """List all workflow definitions."""
        return await request.app.state.workflow_store.list_definitions(limit=limit)

    @app.get("/workflows/{workflow_id}", tags=["Workflows"])
    async def get_workflow(workflow_id: str, request: Request) -> WorkflowDefinition:
        """Get a workflow definition."""
        defn = await request.app.state.workflow_store.get_definition(workflow_id)
        if not defn:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return defn

    @app.delete("/workflows/{workflow_id}", tags=["Workflows"])
    async def delete_workflow(workflow_id: str, request: Request) -> Dict[str, bool]:
        """Delete a workflow definition."""
        deleted = await request.app.state.workflow_store.delete_definition(workflow_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return {"deleted": True}

    @app.post("/workflows/{workflow_id}/start", tags=["Workflows"])
    async def start_workflow(
        workflow_id: str, request: Request, req: StartWorkflowRequest = StartWorkflowRequest()
    ) -> WorkflowRunResponse:
        """Start a new workflow run."""
        wf_store = request.app.state.workflow_store
        dag_engine = request.app.state.dag_engine
        task_engine = request.app.state.task_engine
        defn = await wf_store.get_definition(workflow_id)
        if not defn:
            raise HTTPException(status_code=404, detail="Workflow not found")

        run = await dag_engine.start_workflow(workflow_id, initial_context=req.context)

        # Enqueue root nodes
        root_nodes = dag_engine.get_root_nodes(defn)
        for node in root_nodes:
            state = TaskState.PENDING if node.human_approval else TaskState.QUEUED
            record = await task_engine.submit_task(
                agent_type=node.agent_type,
                prompt=node.prompt_template,
                workflow_id=workflow_id,
                node_id=node.id,
                max_retries=node.retry_policy.max_retries,
                human_approval=node.human_approval,
                metadata={"workflow_run_id": run.id, **node.metadata},
            )
            run.node_states[node.id] = record.state
            run.node_task_ids[node.id] = [record.id]

        await wf_store.update_run(run)
        return WorkflowRunResponse.from_run(run)

    @app.get("/workflows/{workflow_id}/runs", tags=["Workflows"])
    async def list_runs(workflow_id: str, request: Request, limit: int = 50) -> List[WorkflowRunResponse]:
        """List runs for a workflow."""
        runs = await request.app.state.workflow_store.list_runs(workflow_id=workflow_id, limit=limit)
        return [WorkflowRunResponse.from_run(r) for r in runs]

    @app.get("/workflows/runs/{run_id}", tags=["Workflows"])
    async def get_run(run_id: str, request: Request) -> WorkflowRunResponse:
        """Get a specific workflow run."""
        run = await request.app.state.workflow_store.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        return WorkflowRunResponse.from_run(run)

    @app.post("/workflows/runs/{run_id}/nodes/{node_id}/approve", tags=["Workflows"])
    async def approve_node(run_id: str, node_id: str, request: Request) -> Dict[str, str]:
        """Approve a human-approval node in a workflow run."""
        wf_store = request.app.state.workflow_store
        dag_engine = request.app.state.dag_engine
        task_engine = request.app.state.task_engine
        run = await wf_store.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        defn = await wf_store.get_definition(run.workflow_id)
        if not defn:
            raise HTTPException(status_code=404, detail="Workflow not found")

        result = await dag_engine.approve_node(run, node_id, defn)
        if result:
            node, prompt = result
            record = await task_engine.submit_task(
                agent_type=node.agent_type,
                prompt=prompt,
                workflow_id=run.workflow_id,
                node_id=node.id,
                max_retries=node.retry_policy.max_retries,
                metadata={"workflow_run_id": run.id},
            )
            run.node_task_ids.setdefault(node.id, []).append(record.id)
            await wf_store.update_run(run)
            return {"status": "approved", "task_id": record.id}

        raise HTTPException(status_code=400, detail="Node not in pending state")

    @app.post("/workflows/runs/{run_id}/nodes/{node_id}/reject", tags=["Workflows"])
    async def reject_node(run_id: str, node_id: str, request: Request) -> Dict[str, str]:
        """Reject a human-approval node."""
        wf_store = request.app.state.workflow_store
        dag_engine = request.app.state.dag_engine
        run = await wf_store.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        defn = await wf_store.get_definition(run.workflow_id)
        if not defn:
            raise HTTPException(status_code=404, detail="Workflow not found")

        await dag_engine.reject_node(run, node_id, defn)
        return {"status": "rejected"}
