"""Task API routes."""

import asyncio
import json
import logging
from typing import Any

from flint_ai.server.engine import (
    TaskPriority as TaskPriority,
)
from flint_ai.server.engine import (
    TaskRecord,
    TaskResponse,
    TaskState,
    TaskSubmitRequest,
    TaskSubmitResponse,
)

logger = logging.getLogger("flint.server.api.tasks")


def create_task_routes(app: Any) -> None:
    """Register task-related API routes on the FastAPI app."""
    from fastapi import HTTPException, Query, Request
    from fastapi.responses import StreamingResponse

    from flint_ai.server.middleware.validation import (
        ValidationError,
        validate_agent_type,
        validate_metadata,
        validate_prompt_length,
    )

    @app.post("/tasks", response_model=TaskSubmitResponse, tags=["Tasks"])
    async def submit_task(req: TaskSubmitRequest, request: Request) -> TaskSubmitResponse:
        """Submit a new task for processing."""
        try:
            validate_agent_type(req.agent_type)
            validate_prompt_length(req.prompt)
            validate_metadata(req.metadata)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e

        task_engine = request.app.state.task_engine
        record = await task_engine.submit_task(
            agent_type=req.agent_type,
            prompt=req.prompt,
            workflow_id=req.workflow_id,
            priority=req.priority,
            metadata=req.metadata,
        )
        return TaskSubmitResponse(id=record.id)

    @app.post("/tasks/batch", tags=["Tasks"])
    async def submit_batch(tasks: list[TaskSubmitRequest], request: Request) -> list[TaskSubmitResponse]:
        """Submit multiple tasks at once."""
        if len(tasks) > 100:
            raise HTTPException(status_code=422, detail="Batch size exceeds maximum of 100")

        task_engine = request.app.state.task_engine
        results = []
        for t in tasks:
            try:
                validate_agent_type(t.agent_type)
                validate_prompt_length(t.prompt)
            except ValidationError as e:
                raise HTTPException(status_code=422, detail=str(e)) from e
            record = await task_engine.submit_task(
                agent_type=t.agent_type,
                prompt=t.prompt,
                workflow_id=t.workflow_id,
                priority=t.priority,
                metadata=t.metadata,
            )
            results.append(TaskSubmitResponse(id=record.id))
        return results

    @app.get("/tasks", response_model=list[TaskResponse], tags=["Tasks"])
    async def list_tasks(
        request: Request,
        state: TaskState | None = None,
        workflow_id: str | None = None,
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
    ) -> list[TaskResponse]:
        """List tasks with optional filters."""
        records = await request.app.state.task_engine._store.list_tasks(
            state=state, workflow_id=workflow_id, limit=limit, offset=offset
        )
        return [TaskResponse.from_record(r) for r in records]

    @app.get("/tasks/{task_id}", response_model=TaskResponse, tags=["Tasks"])
    async def get_task(task_id: str, request: Request) -> TaskResponse:
        """Get a task by ID."""
        record = await request.app.state.task_engine.get_task(task_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        return TaskResponse.from_record(record)

    @app.post("/tasks/{task_id}/cancel", response_model=TaskResponse, tags=["Tasks"])
    async def cancel_task(task_id: str, request: Request) -> TaskResponse:
        """Cancel a queued or running task."""
        record = await request.app.state.task_engine.cancel_task(task_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        return TaskResponse.from_record(record)

    @app.post("/tasks/{task_id}/restart", response_model=TaskSubmitResponse, tags=["Tasks"])
    async def restart_task(task_id: str, request: Request) -> TaskSubmitResponse:
        """Restart a failed or dead-lettered task as a new task."""
        record = await request.app.state.task_engine.restart_task(task_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        return TaskSubmitResponse(id=record.id)

    @app.post("/tasks/{task_id}/approve", response_model=TaskResponse, tags=["Tasks"])
    async def approve_task(task_id: str, request: Request) -> TaskResponse:
        """Approve a pending (human-approval) task."""
        record = await request.app.state.task_engine.approve_task(task_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        return TaskResponse.from_record(record)

    @app.post("/tasks/{task_id}/reject", response_model=TaskResponse, tags=["Tasks"])
    async def reject_task(task_id: str, request: Request) -> TaskResponse:
        """Reject a pending task → dead letter."""
        record = await request.app.state.task_engine.reject_task(task_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        return TaskResponse.from_record(record)

    @app.get("/tasks/{task_id}/stream", tags=["Tasks"], response_class=StreamingResponse)
    async def stream_task(task_id: str, request: Request):
        """SSE stream of task state changes."""
        task_engine = request.app.state.task_engine
        record = await task_engine.get_task(task_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        async def event_generator():
            queue: asyncio.Queue = asyncio.Queue()

            async def on_change(event: str, rec: TaskRecord):
                await queue.put((event, rec))

            task_engine.subscribe(task_id, on_change)
            try:
                # Send current state
                yield f"data: {json.dumps({'event': 'state', 'state': record.state.value, 'task_id': task_id})}\n\n"

                if record.state.is_terminal:
                    yield f"data: {json.dumps({'event': 'complete', 'state': record.state.value, 'result': record.result_json})}\n\n"
                    return

                while True:
                    try:
                        event, rec = await asyncio.wait_for(queue.get(), timeout=30)
                        data = {
                            "event": event,
                            "state": rec.state.value,
                            "task_id": task_id,
                        }
                        if rec.result_json:
                            data["result"] = rec.result_json
                        if rec.error:
                            data["error"] = rec.error
                        yield f"data: {json.dumps(data)}\n\n"

                        if rec.state.is_terminal:
                            return
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
            finally:
                task_engine.unsubscribe(task_id, on_change)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Versioned aliases
    @app.post("/api/v1/tasks", response_model=TaskSubmitResponse, tags=["Tasks v1"], include_in_schema=False)
    async def submit_task_v1(req: TaskSubmitRequest, request: Request) -> TaskSubmitResponse:
        return await submit_task(req, request)

    @app.get("/api/v1/tasks/{task_id}", response_model=TaskResponse, tags=["Tasks v1"], include_in_schema=False)
    async def get_task_v1(task_id: str, request: Request) -> TaskResponse:
        return await get_task(task_id, request)
