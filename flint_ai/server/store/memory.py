"""In-memory store for development and testing."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from flint_ai.server.engine import (
    TaskRecord,
    TaskState,
    WorkflowDefinition,
    WorkflowRun,
)
from flint_ai.server.store import BaseTaskStore, BaseWorkflowStore

logger = logging.getLogger("flint.server.store.memory")


class InMemoryTaskStore(BaseTaskStore):
    """Dict-backed task store. Fast, volatile, single-process only.

    Stores deep copies to prevent mutation through shared references
    (same safety guarantees as a real database).
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, TaskRecord] = {}

    async def create(self, record: TaskRecord) -> TaskRecord:
        self._tasks[record.id] = record.model_copy(deep=True)
        logger.debug("Created task=%s state=%s", record.id, record.state)
        return record

    async def get(self, task_id: str) -> Optional[TaskRecord]:
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
        state: Optional[TaskState] = None,
        workflow_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[TaskRecord]:
        result = [t.model_copy(deep=True) for t in self._tasks.values()]
        if state:
            result = [t for t in result if t.state == state]
        if workflow_id:
            result = [t for t in result if t.workflow_id == workflow_id]
        result.sort(key=lambda t: t.created_at, reverse=True)
        return result[offset : offset + limit]

    async def count_by_state(self) -> Dict[TaskState, int]:
        counts: Dict[TaskState, int] = defaultdict(int)
        for task in self._tasks.values():
            counts[task.state] += 1
        return dict(counts)


class InMemoryWorkflowStore(BaseWorkflowStore):
    """Dict-backed workflow store."""

    def __init__(self) -> None:
        self._definitions: Dict[str, WorkflowDefinition] = {}
        self._runs: Dict[str, WorkflowRun] = {}

    async def save_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        self._definitions[definition.id] = definition
        logger.debug("Saved workflow definition=%s", definition.id)
        return definition

    async def get_definition(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        return self._definitions.get(workflow_id)

    async def list_definitions(self, limit: int = 100) -> List[WorkflowDefinition]:
        defs = list(self._definitions.values())
        defs.sort(key=lambda d: d.created_at, reverse=True)
        return defs[:limit]

    async def delete_definition(self, workflow_id: str) -> bool:
        return self._definitions.pop(workflow_id, None) is not None

    async def create_run(self, run: WorkflowRun) -> WorkflowRun:
        self._runs[run.id] = run
        logger.debug("Created workflow run=%s for workflow=%s", run.id, run.workflow_id)
        return run

    async def get_run(self, run_id: str) -> Optional[WorkflowRun]:
        return self._runs.get(run_id)

    async def update_run(self, run: WorkflowRun) -> WorkflowRun:
        self._runs[run.id] = run
        return run

    async def list_runs(
        self,
        workflow_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[WorkflowRun]:
        runs = list(self._runs.values())
        if workflow_id:
            runs = [r for r in runs if r.workflow_id == workflow_id]
        runs.sort(key=lambda r: r.created_at, reverse=True)
        return runs[:limit]
