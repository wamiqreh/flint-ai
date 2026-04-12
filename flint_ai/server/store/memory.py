"""In-memory store for development and testing."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from flint_ai.server.engine import (
    TaskRecord,
    TaskState,
    ToolExecution,
    WorkflowDefinition,
    WorkflowRun,
)
from flint_ai.server.store import BaseTaskStore, BaseToolExecutionStore, BaseWorkflowStore

logger = logging.getLogger("flint.server.store.memory")


class InMemoryTaskStore(BaseTaskStore):
    """Dict-backed task store. Fast, volatile, single-process only.

    Stores deep copies to prevent mutation through shared references
    (same safety guarantees as a real database).
    """

    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def create(self, record: TaskRecord) -> TaskRecord:
        self._tasks[record.id] = record.model_copy(deep=True)
        logger.debug("Created task=%s state=%s", record.id, record.state)
        return record

    async def get(self, task_id: str) -> TaskRecord | None:
        rec = self._tasks.get(task_id)
        return rec.model_copy(deep=True) if rec else None

    async def update(self, record: TaskRecord) -> TaskRecord:
        self._tasks[record.id] = record.model_copy(deep=True)
        return record

    async def compare_and_swap(
        self,
        task_id: str,
        expected_state: TaskState,
        record: TaskRecord,
    ) -> bool:
        existing = self._tasks.get(task_id)
        if not existing or existing.state != expected_state:
            return False
        self._tasks[task_id] = record.model_copy(deep=True)
        return True

    async def update_state(self, task_id: str, state: TaskState, **kwargs: Any) -> None:
        rec = self._tasks.get(task_id)
        if rec:
            rec.state = state
            for k, v in kwargs.items():
                if hasattr(rec, k):
                    setattr(rec, k, v)
            logger.debug("Updated task=%s → state=%s", task_id, state)

    async def list_tasks(
        self,
        state: TaskState | None = None,
        workflow_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TaskRecord]:
        result = [t.model_copy(deep=True) for t in self._tasks.values()]
        if state:
            result = [t for t in result if t.state == state]
        if workflow_id:
            result = [t for t in result if t.workflow_id == workflow_id]
        result.sort(key=lambda t: t.created_at, reverse=True)
        return result[offset : offset + limit]

    async def count_by_state(self) -> dict[TaskState, int]:
        counts: dict[TaskState, int] = defaultdict(int)
        for task in self._tasks.values():
            counts[task.state] += 1
        return dict(counts)

    async def update_heartbeat(self, task_id: str) -> None:
        if task_id in self._tasks:
            self._tasks[task_id].metadata["last_heartbeat"] = datetime.now(timezone.utc)

    async def find_stale_running_tasks(self, stale_threshold_seconds: int = 120) -> list[TaskRecord]:
        now = datetime.now(timezone.utc)
        stale: list[TaskRecord] = []
        for task in self._tasks.values():
            if task.state != TaskState.RUNNING:
                continue
            hb = task.metadata.get("last_heartbeat") or task.started_at
            if hb and (now - hb).total_seconds() > stale_threshold_seconds:
                stale.append(task)
        stale.sort(key=lambda t: t.started_at or t.created_at)
        return stale

    async def reset_to_queued(self, task_id: str) -> None:
        if task_id in self._tasks and self._tasks[task_id].state == TaskState.RUNNING:
            self._tasks[task_id].state = TaskState.QUEUED
            self._tasks[task_id].error = "Worker dies without heartbeat. Auto-reset by stale recovery."
            self._tasks[task_id].metadata.pop("last_heartbeat", None)


class InMemoryWorkflowStore(BaseWorkflowStore):
    """Dict-backed workflow store."""

    def __init__(self) -> None:
        self._definitions: dict[str, WorkflowDefinition] = {}
        self._runs: dict[str, WorkflowRun] = {}

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def save_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        self._definitions[definition.id] = definition
        logger.debug("Saved workflow definition=%s", definition.id)
        return definition

    async def get_definition(self, workflow_id: str) -> WorkflowDefinition | None:
        return self._definitions.get(workflow_id)

    async def list_definitions(self, limit: int = 100) -> list[WorkflowDefinition]:
        defs = list(self._definitions.values())
        defs.sort(key=lambda d: d.created_at, reverse=True)
        return defs[:limit]

    async def delete_definition(self, workflow_id: str) -> bool:
        return self._definitions.pop(workflow_id, None) is not None

    async def create_run(self, run: WorkflowRun) -> WorkflowRun:
        self._runs[run.id] = run
        logger.debug("Created workflow run=%s for workflow=%s", run.id, run.workflow_id)
        return run

    async def get_run(self, run_id: str) -> WorkflowRun | None:
        return self._runs.get(run_id)

    async def update_run(self, run: WorkflowRun) -> WorkflowRun:
        self._runs[run.id] = run
        return run

    async def list_runs(
        self,
        workflow_id: str | None = None,
        limit: int = 50,
    ) -> list[WorkflowRun]:
        runs = list(self._runs.values())
        if workflow_id:
            runs = [r for r in runs if r.workflow_id == workflow_id]
        runs.sort(key=lambda r: r.created_at, reverse=True)
        return runs[:limit]


class InMemoryToolExecutionStore(BaseToolExecutionStore):
    """Dict-backed tool execution store for dev/testing."""

    def __init__(self) -> None:
        self._executions: dict[str, ToolExecution] = {}

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def create(self, execution: ToolExecution) -> ToolExecution:
        self._executions[execution.id] = execution.model_copy(deep=True)
        return execution

    async def get(self, execution_id: str) -> ToolExecution | None:
        return self._executions.get(execution_id)

    async def list_by_task(self, task_id: str, limit: int = 100) -> list[ToolExecution]:
        result = [e for e in self._executions.values() if e.task_id == task_id]
        result.sort(key=lambda e: e.created_at, reverse=True)
        return result[:limit]

    async def list_by_workflow_run(self, workflow_run_id: str, limit: int = 200) -> list[ToolExecution]:
        result = [e for e in self._executions.values() if e.workflow_run_id == workflow_run_id]
        result.sort(key=lambda e: e.created_at, reverse=True)
        return result[:limit]

    async def list_by_tool_name(self, tool_name: str, limit: int = 100) -> list[ToolExecution]:
        result = [e for e in self._executions.values() if e.tool_name == tool_name]
        result.sort(key=lambda e: e.created_at, reverse=True)
        return result[:limit]

    async def list_errors(self, workflow_run_id: str | None = None, limit: int = 50) -> list[ToolExecution]:
        result = [e for e in self._executions.values() if e.status == "failed"]
        if workflow_run_id:
            result = [e for e in result if e.workflow_run_id == workflow_run_id]
        result.sort(key=lambda e: e.created_at, reverse=True)
        return result[:limit]

    async def list_recent(self, limit: int = 100, offset: int = 0) -> list[ToolExecution]:
        result = sorted(self._executions.values(), key=lambda e: e.created_at, reverse=True)
        return result[offset : offset + limit]
