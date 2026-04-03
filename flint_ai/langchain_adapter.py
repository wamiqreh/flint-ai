from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .client import AsyncOrchestratorClient
from .models import TaskResponse


@dataclass
class LangChainOrchestratorRunnable:
    """
    Minimal LangChain-compatible runnable adapter.

    It accepts string input and dispatches it to the orchestrator as a task.
    """

    client: AsyncOrchestratorClient
    agent_type: str = "openai"
    workflow_id: str | None = None

    async def ainvoke(self, input: Any, config: dict[str, Any] | None = None) -> TaskResponse:
        prompt = input if isinstance(input, str) else str(input)
        task_id = await self.client.submit_task(self.agent_type, prompt, workflow_id=self.workflow_id)
        return await self.client.wait_for_task(task_id)
