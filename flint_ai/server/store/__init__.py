"""Abstract store interface for task and workflow persistence."""

from __future__ import annotations

import abc
from typing import Any, Dict, List, Optional

from flint_ai.server.engine import (
    TaskRecord,
    TaskState,
    WorkflowDefinition,
    WorkflowRun,
)


class BaseTaskStore(abc.ABC):
    """Abstract interface for task persistence."""

    @abc.abstractmethod
    async def create(self, record: TaskRecord) -> TaskRecord:
        """Persist a new task record."""

    @abc.abstractmethod
    async def get(self, task_id: str) -> Optional[TaskRecord]:
        """Retrieve a task by ID."""

    @abc.abstractmethod
    async def update(self, record: TaskRecord) -> TaskRecord:
        """Update an existing task record."""

    @abc.abstractmethod
    async def update_state(self, task_id: str, state: TaskState, **kwargs: Any) -> None:
        """Atomically update task state and optional fields."""

    @abc.abstractmethod
    async def list_tasks(
        self,
        state: Optional[TaskState] = None,
        workflow_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[TaskRecord]:
        """List tasks with optional filters."""

    @abc.abstractmethod
    async def count_by_state(self) -> Dict[TaskState, int]:
        """Count tasks grouped by state."""

    async def connect(self) -> None:
        """Initialize connections."""

    async def disconnect(self) -> None:
        """Clean up connections."""


class BaseWorkflowStore(abc.ABC):
    """Abstract interface for workflow definition and run persistence."""

    # --- Workflow definitions ---

    @abc.abstractmethod
    async def save_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        """Save or update a workflow definition."""

    @abc.abstractmethod
    async def get_definition(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        """Retrieve a workflow definition by ID."""

    @abc.abstractmethod
    async def list_definitions(self, limit: int = 100) -> List[WorkflowDefinition]:
        """List all workflow definitions."""

    @abc.abstractmethod
    async def delete_definition(self, workflow_id: str) -> bool:
        """Delete a workflow definition. Returns True if deleted."""

    # --- Workflow runs ---

    @abc.abstractmethod
    async def create_run(self, run: WorkflowRun) -> WorkflowRun:
        """Create a new workflow run."""

    @abc.abstractmethod
    async def get_run(self, run_id: str) -> Optional[WorkflowRun]:
        """Retrieve a workflow run by ID."""

    @abc.abstractmethod
    async def update_run(self, run: WorkflowRun) -> WorkflowRun:
        """Update a workflow run."""

    @abc.abstractmethod
    async def list_runs(
        self,
        workflow_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[WorkflowRun]:
        """List workflow runs, optionally filtered by workflow ID."""

    async def connect(self) -> None:
        """Initialize connections."""

    async def disconnect(self) -> None:
        """Clean up connections."""
