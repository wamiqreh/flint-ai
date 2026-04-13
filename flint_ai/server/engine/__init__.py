"""Core server models — task lifecycle, workflow DAG, and state machines."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Task lifecycle
# ---------------------------------------------------------------------------


class TaskState(str, Enum):
    """Task state machine: Pending → Queued → Running → Succeeded/Failed/DeadLetter/Cancelled."""

    PENDING = "pending"  # Awaiting human approval
    QUEUED = "queued"  # In queue, waiting for worker
    RUNNING = "running"  # Being executed by worker
    SUCCEEDED = "succeeded"  # Completed successfully
    FAILED = "failed"  # Failed (retries exhausted)
    DEAD_LETTER = "dead_letter"  # Moved to DLQ
    CANCELLED = "cancelled"  # Cancelled by user

    @property
    def is_terminal(self) -> bool:
        return self in (
            TaskState.SUCCEEDED,
            TaskState.FAILED,
            TaskState.DEAD_LETTER,
            TaskState.CANCELLED,
        )


class TaskPriority(int, Enum):
    """Task priority levels."""

    LOW = 0
    NORMAL = 5
    HIGH = 10
    CRITICAL = 20


class TaskRecord(BaseModel):
    """Persistent task record."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_type: str
    prompt: str
    workflow_id: str | None = None
    node_id: str | None = None
    state: TaskState = TaskState.QUEUED
    priority: TaskPriority = TaskPriority.NORMAL
    result_json: str | None = None
    error: str | None = None
    attempt: int = 0
    max_retries: int = 3
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskSubmitRequest(BaseModel):
    """API request to submit a task."""

    agent_type: str = Field(..., alias="AgentType")
    prompt: str = Field(..., alias="Prompt")
    workflow_id: str | None = Field(None, alias="WorkflowId")
    priority: TaskPriority = Field(TaskPriority.NORMAL, alias="Priority")
    metadata: dict[str, Any] = Field(default_factory=dict, alias="Metadata")

    model_config = {"populate_by_name": True}


class TaskSubmitResponse(BaseModel):
    """API response after submitting a task."""

    id: str


class TaskResponse(BaseModel):
    """API response for task details."""

    id: str
    agent_type: str
    prompt: str
    state: TaskState
    priority: TaskPriority = TaskPriority.NORMAL
    workflow_id: str | None = None
    node_id: str | None = None
    result_json: str | None = None
    error: str | None = None
    attempt: int = 0
    max_retries: int = 3
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_record(cls, rec: TaskRecord) -> TaskResponse:
        return cls(
            id=rec.id,
            agent_type=rec.agent_type,
            prompt=rec.prompt,
            state=rec.state,
            priority=rec.priority,
            workflow_id=rec.workflow_id,
            node_id=rec.node_id,
            result_json=rec.result_json,
            error=rec.error,
            attempt=rec.attempt,
            max_retries=rec.max_retries,
            created_at=rec.created_at,
            started_at=rec.started_at,
            completed_at=rec.completed_at,
            metadata=rec.metadata,
        )


# ---------------------------------------------------------------------------
# Workflow / DAG models
# ---------------------------------------------------------------------------


class RetryPolicy(BaseModel):
    """Per-node retry configuration."""

    max_retries: int = Field(default=3, ge=0)
    backoff_base_s: float = Field(default=1.0, description="Base backoff in seconds")
    backoff_max_s: float = Field(default=60.0, description="Max backoff cap")
    backoff_multiplier: float = Field(default=2.0, description="Exponential multiplier")
    retry_on_timeout: bool = Field(default=True)

    def delay_for_attempt(self, attempt: int) -> float:
        """Calculate delay with exponential backoff + jitter cap."""
        import random

        delay = self.backoff_base_s * (self.backoff_multiplier**attempt)
        delay = min(delay, self.backoff_max_s)
        # Add ±25% jitter
        jitter = delay * 0.25 * (2 * random.random() - 1)
        return max(0, delay + jitter)


class EdgeCondition(BaseModel):
    """Condition for a workflow edge. Edge fires only when condition evaluates to True."""

    expression: str | None = Field(
        None,
        description="Python expression evaluated against upstream outputs. "
        "Available vars: result (str), metadata (dict), status (str). "
        'Example: \'status == "succeeded" and "error" not in result\'',
    )
    on_status: list[TaskState] | None = Field(
        None, description="Fire only if upstream task ended in one of these states"
    )

    def is_empty(self) -> bool:
        return self.expression is None and self.on_status is None


class WorkflowNode(BaseModel):
    """Enhanced workflow node with retry policies and sub-DAG support."""

    id: str
    agent_type: str
    prompt_template: str
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    dead_letter_on_failure: bool = Field(default=True)
    human_approval: bool = Field(default=False)
    timeout_s: float | None = Field(None, description="Per-node timeout in seconds")
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Sub-DAG: if set, this node expands to a child workflow
    sub_workflow_id: str | None = Field(None, description="Expand this node into a child workflow")
    # Task mapping: fan-out a single node into N parallel instances
    map_variable: str | None = Field(
        None,
        description="Context key containing a list; node fans out to one task per item",
    )


class WorkflowEdge(BaseModel):
    """Edge connecting two nodes, optionally conditional."""

    from_node_id: str
    to_node_id: str
    condition: EdgeCondition = Field(default_factory=EdgeCondition)


class WorkflowDefinition(BaseModel):
    """Complete DAG workflow definition."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str | None = None
    description: str | None = None
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Scheduling
    schedule_cron: str | None = Field(None, description="Cron expression, e.g. '0 * * * *'")
    schedule_interval_s: int | None = Field(None, description="Run every N seconds")
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkflowRunState(str, Enum):
    """State of a workflow run (instance)."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowRun(BaseModel):
    """An instance/execution of a workflow definition."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    state: WorkflowRunState = WorkflowRunState.PENDING
    node_states: dict[str, TaskState] = Field(default_factory=dict)
    node_task_ids: dict[str, list[str]] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    version: int = 0  # Incremented on each update for CAS
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None


# ---------------------------------------------------------------------------
# Agent models
# ---------------------------------------------------------------------------


class AgentDefinition(BaseModel):
    """Registered agent type."""

    agent_type: str
    display_name: str | None = None
    description: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    """Result returned by an agent execution."""

    task_id: str
    success: bool
    output: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tool execution models
# ---------------------------------------------------------------------------


class ToolExecution(BaseModel):
    """Records a single tool call execution."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    workflow_run_id: str | None = None
    node_id: str | None = None
    tool_name: str
    input_json: dict[str, Any] | None = None
    output_json: str | dict[str, Any] | None = None
    duration_ms: float | None = None
    error: str | None = None
    stack_trace: str | None = None
    sanitized_input: dict[str, Any] | None = None
    cost_usd: float = 0.0
    status: str = "succeeded"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
