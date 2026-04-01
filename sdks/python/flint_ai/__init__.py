from .client import AsyncOrchestratorClient, OrchestratorClient
from .exceptions import (
    AuthenticationError,
    ConnectionError,
    OrchestratorError,
    RateLimitError,
    TaskNotFoundError,
    WorkflowValidationError,
)
from .models import (
    SubmitTaskRequest,
    SubmitTaskResponse,
    TaskResponse,
    TaskSubmission,
    WorkflowDefinition,
    WorkflowNode,
    WorkflowEdge,
)
from .langchain_adapter import LangChainOrchestratorRunnable
from .workflow_builder import Node, Workflow, WorkflowBuilder

# Adapter re-exports (lightweight — no heavy deps pulled)
from .adapters import FlintAdapter, AdapterConfig, AgentRunResult

# Tool decorator (always available)
from .adapters.openai.tools import tool

# NOTE: Framework-specific adapters are NOT imported here to avoid pulling in
# heavy optional dependencies.  Import them explicitly from their modules:
#
#   from flint_ai.adapters.openai import FlintOpenAIAgent
#   from flint_ai.crewai_adapter import OrchestratorTool
#   from flint_ai.fastapi_middleware import OrchestratorMiddleware, orchestrator_task

__all__ = [
    # Clients
    "AsyncOrchestratorClient",
    "OrchestratorClient",
    # Exceptions
    "OrchestratorError",
    "TaskNotFoundError",
    "WorkflowValidationError",
    "RateLimitError",
    "AuthenticationError",
    "ConnectionError",
    # Models
    "SubmitTaskRequest",
    "SubmitTaskResponse",
    "TaskResponse",
    "TaskSubmission",
    "WorkflowDefinition",
    "WorkflowNode",
    "WorkflowEdge",
    # Integrations (LangChain is lightweight enough to keep here)
    "LangChainOrchestratorRunnable",
    # Workflow Builder DSL
    "Node",
    "Workflow",
    "WorkflowBuilder",
    # Adapter base
    "FlintAdapter",
    "AdapterConfig",
    "AgentRunResult",
    "tool",
]
