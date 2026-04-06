from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SubmitTaskRequest(BaseModel):
    agent_type: str = Field(alias="AgentType")
    prompt: str = Field(alias="Prompt")
    workflow_id: str | None = Field(default=None, alias="WorkflowId")

    model_config = {"populate_by_name": True}


class SubmitTaskResponse(BaseModel):
    id: str


class TaskResponse(BaseModel):
    id: str
    state: str
    result: str | None = None
    workflow_id: str | None = Field(default=None, alias="workflowId")

    model_config = {"populate_by_name": True}


class WorkflowNode(BaseModel):
    id: str = Field(alias="Id")
    agent_type: str = Field(alias="AgentType")
    prompt_template: str = Field(alias="PromptTemplate")
    max_retries: int = Field(default=3, alias="MaxRetries")
    dead_letter_on_failure: bool = Field(default=True, alias="DeadLetterOnFailure")
    human_approval: bool = Field(default=False, alias="HumanApproval")

    model_config = {"populate_by_name": True}


class WorkflowEdge(BaseModel):
    from_node_id: str = Field(alias="FromNodeId")
    to_node_id: str = Field(alias="ToNodeId")
    condition: str | dict[str, Any] = Field(default="", alias="Condition")

    model_config = {"populate_by_name": True}


class WorkflowDefinition(BaseModel):
    id: str = Field(alias="Id")
    nodes: list[WorkflowNode] = Field(default_factory=list, alias="Nodes")
    edges: list[WorkflowEdge] = Field(default_factory=list, alias="Edges")

    model_config = {"populate_by_name": True}


class WorkflowStartResponse(BaseModel):
    accepted: bool = True
    location: str | None = None


class TaskSubmission(BaseModel):
    """Describes a single task for use with :pymeth:`submit_tasks` batch API."""

    agent_type: str = Field(alias="AgentType")
    prompt: str = Field(alias="Prompt")
    workflow_id: str | None = Field(default=None, alias="WorkflowId")

    model_config = {"populate_by_name": True}


JsonDict = dict[str, Any]
