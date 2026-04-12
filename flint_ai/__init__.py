# Adapter re-exports (lightweight — no heavy deps pulled)
from .adapters import AdapterConfig, AgentRunResult, CostBreakdown, FlintAdapter, FlintCostTracker

# Tool decorator (always available)
from .adapters.openai.tools import tool
from .client import AsyncOrchestratorClient, OrchestratorClient

# Centralized cost config
from .config import CostConfigManager, get_pricing, set_pricing

# Global engine management (Hangfire-style: start once, enqueue anywhere)
from .engine_manager import configure_engine, get_engine, shutdown_engine, wait_for_ready
from .exceptions import (
    AuthenticationError,
    ConnectionError,
    OrchestratorError,
    RateLimitError,
    TaskNotFoundError,
    WorkflowValidationError,
)
from .langchain_adapter import LangChainOrchestratorRunnable
from .models import (
    SubmitTaskRequest,
    SubmitTaskResponse,
    TaskResponse,
    TaskSubmission,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
)
from .worker import FlintWorker
from .workflow_builder import Node, Workflow, WorkflowBuilder

# NOTE: Framework-specific adapters are NOT imported here to avoid pulling in
# heavy optional dependencies.  Import them explicitly from their modules:
#
#   from flint_ai.adapters.openai import FlintOpenAIAgent
#   from flint_ai.crewai_adapter import OrchestratorTool
#   from flint_ai.fastapi_middleware import OrchestratorMiddleware, orchestrator_task

__all__ = [
    "AdapterConfig",
    "AgentRunResult",
    "AsyncOrchestratorClient",
    "AuthenticationError",
    "ConnectionError",
    "CostBreakdown",
    "CostConfigManager",
    "FlintAdapter",
    "FlintCostTracker",
    "FlintWorker",
    "LangChainOrchestratorRunnable",
    "Node",
    "OrchestratorClient",
    "OrchestratorError",
    "RateLimitError",
    "SubmitTaskRequest",
    "SubmitTaskResponse",
    "TaskNotFoundError",
    "TaskResponse",
    "TaskSubmission",
    "Workflow",
    "WorkflowBuilder",
    "WorkflowDefinition",
    "WorkflowEdge",
    "WorkflowNode",
    "WorkflowValidationError",
    "configure_engine",
    "get_engine",
    "get_pricing",
    "set_pricing",
    "shutdown_engine",
    "tool",
    "wait_for_ready",
]
