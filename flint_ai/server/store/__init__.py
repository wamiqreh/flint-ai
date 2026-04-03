"""Abstract store interface for task and workflow persistence."""

from __future__ import annotations

import abc
from typing import Any

from flint_ai.server.engine import (
    TaskRecord,
    TaskState,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowRunState,
)


class BaseTaskStore(abc.ABC):
    """Abstract interface for task persistence."""

    @abc.abstractmethod
    async def create(self, record: TaskRecord) -> TaskRecord:
        """Persist a new task record."""

    @abc.abstractmethod
    async def get(self, task_id: str) -> TaskRecord | None:
        """Retrieve a task by ID."""

    @abc.abstractmethod
    async def update(self, record: TaskRecord) -> TaskRecord:
        """Update an existing task record."""

    async def compare_and_swap(
        self,
        task_id: str,
        expected_state: TaskState,
        record: TaskRecord,
    ) -> bool:
        """Atomically update a task only if its current state matches expected_state.

        Returns True if the update was applied, False if the state had changed
        (i.e., another worker already claimed or modified this task).
        """
        # Default implementation falls back to non-atomic update.
        # Postgres overrides this with a proper WHERE clause.
        existing = await self.get(task_id)
        if not existing or existing.state != expected_state:
            return False
        await self.update(record)
        return True

    @abc.abstractmethod
    async def update_state(self, task_id: str, state: TaskState, **kwargs: Any) -> None:
        """Atomically update task state and optional fields."""

    @abc.abstractmethod
    async def list_tasks(
        self,
        state: TaskState | None = None,
        workflow_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TaskRecord]:
        """List tasks with optional filters."""

    @abc.abstractmethod
    async def count_by_state(self) -> dict[TaskState, int]:
        """Count tasks grouped by state."""

    @abc.abstractmethod
    async def connect(self) -> None:
        """Initialize connections."""

    @abc.abstractmethod
    async def disconnect(self) -> None:
        """Clean up connections."""


class BaseWorkflowStore(abc.ABC):
    """Abstract interface for workflow definition and run persistence."""

    # --- Workflow definitions ---

    @abc.abstractmethod
    async def save_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        """Save or update a workflow definition."""

    @abc.abstractmethod
    async def get_definition(self, workflow_id: str) -> WorkflowDefinition | None:
        """Retrieve a workflow definition by ID."""

    @abc.abstractmethod
    async def list_definitions(self, limit: int = 100) -> list[WorkflowDefinition]:
        """List all workflow definitions."""

    @abc.abstractmethod
    async def delete_definition(self, workflow_id: str) -> bool:
        """Delete a workflow definition. Returns True if deleted."""

    # --- Workflow runs ---

    @abc.abstractmethod
    async def create_run(self, run: WorkflowRun) -> WorkflowRun:
        """Create a new workflow run."""

    @abc.abstractmethod
    async def get_run(self, run_id: str) -> WorkflowRun | None:
        """Retrieve a workflow run by ID."""

    @abc.abstractmethod
    async def update_run(self, run: WorkflowRun) -> WorkflowRun:
        """Update a workflow run."""

    @abc.abstractmethod
    async def list_runs(
        self,
        workflow_id: str | None = None,
        limit: int = 50,
    ) -> list[WorkflowRun]:
        """List workflow runs, optionally filtered by workflow ID."""

    async def list_running_runs(self) -> list[WorkflowRun]:
        """List all workflow runs in RUNNING state (for crash recovery)."""
        runs = await self.list_runs(limit=500)
        return [r for r in runs if r.state == WorkflowRunState.RUNNING]

    @abc.abstractmethod
    async def connect(self) -> None:
        """Initialize connections."""

    @abc.abstractmethod
    async def disconnect(self) -> None:
        """Clean up connections."""
