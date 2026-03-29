"""CrewAI integration adapter for Flint.

Provides ``OrchestratorTool`` – a CrewAI-compatible tool that submits
prompts to the orchestrator queue and returns the result.

Usage::

    from flint_ai.crewai_adapter import OrchestratorTool

    tool = OrchestratorTool(
        base_url="http://localhost:5156",
        agent_type="openai",
        name="code_generator",
        description="Generates code using the orchestrator queue",
    )
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional, Type

from pydantic import BaseModel, Field

from .client import AsyncOrchestratorClient, OrchestratorClient

try:
    from crewai.tools import BaseTool as CrewAIBaseTool

    _CREWAI_AVAILABLE = True
except ImportError:  # pragma: no cover
    _CREWAI_AVAILABLE = False

    # Provide a lightweight stand-in so the class definition always works.
    class CrewAIBaseTool(BaseModel):  # type: ignore[no-redef]
        """Placeholder when crewai is not installed."""

        name: str = ""
        description: str = ""


class _OrchestratorToolInput(BaseModel):
    """Input schema for OrchestratorTool."""

    prompt: str = Field(description="The prompt to send to the orchestrator.")


class OrchestratorTool(CrewAIBaseTool):  # type: ignore[misc]
    """CrewAI tool that delegates work to Flint.

    Parameters
    ----------
    base_url:
        Root URL of the orchestrator API.
    agent_type:
        Agent backend to use (e.g. ``"openai"``, ``"claude"``).
    name:
        Tool name exposed to CrewAI agents.
    description:
        Human-readable description of what the tool does.
    timeout:
        Maximum seconds to wait for a task to complete. ``None`` means wait
        indefinitely.
    poll_interval:
        Seconds between status polls while waiting.
    workflow_id:
        Optional workflow to associate with submitted tasks.
    """

    name: str = "orchestrator"
    description: str = "Submit a task to Flint and return the result."
    args_schema: Type[BaseModel] = _OrchestratorToolInput

    # Orchestrator-specific configuration
    base_url: str = "http://localhost:5156"
    agent_type: str = "openai"
    timeout: Optional[float] = 300.0
    poll_interval: float = 1.0
    workflow_id: Optional[str] = None

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, **kwargs: Any) -> None:
        if not _CREWAI_AVAILABLE:
            raise ImportError(
                "crewai is required for OrchestratorTool. "
                "Install it with: pip install 'flint-ai[crewai]'"
            )
        super().__init__(**kwargs)

    # -- sync entry point (CrewAI calls this) --------------------------------

    def _run(self, prompt: str) -> str:
        """Submit *prompt* to the orchestrator and block until a result is available."""
        client = OrchestratorClient(base_url=self.base_url)
        with client:
            task_id = client.submit_task(
                self.agent_type, prompt, workflow_id=self.workflow_id,
            )
            result = client.wait_for_task(task_id, poll_interval_seconds=self.poll_interval)

        if result.state == "Succeeded":
            return result.result or ""
        return f"[Task {result.state}] {result.result or 'No output'}"

    # -- async entry point ---------------------------------------------------

    async def _arun(self, prompt: str) -> str:
        """Async variant used when CrewAI runs in an async context."""
        async with AsyncOrchestratorClient(base_url=self.base_url) as client:
            task_id = await client.submit_task(
                self.agent_type, prompt, workflow_id=self.workflow_id,
            )

            if self.timeout is not None:
                result = await asyncio.wait_for(
                    client.wait_for_task(task_id, poll_interval_seconds=self.poll_interval),
                    timeout=self.timeout,
                )
            else:
                result = await client.wait_for_task(
                    task_id, poll_interval_seconds=self.poll_interval,
                )

        if result.state == "Succeeded":
            return result.result or ""
        return f"[Task {result.state}] {result.result or 'No output'}"
