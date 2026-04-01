"""Dummy echo agent for testing."""

from __future__ import annotations

import asyncio
import random
from typing import Any

from flint_ai.server.agents import BaseAgent
from flint_ai.server.engine import AgentResult


class DummyAgent(BaseAgent):
    """Echo agent that returns the prompt after a random delay.

    Useful for testing the queue/workflow pipeline without external API calls.
    """

    def __init__(self, min_delay_ms: int = 50, max_delay_ms: int = 300) -> None:
        self._min_delay = min_delay_ms
        self._max_delay = max_delay_ms

    @property
    def agent_type(self) -> str:
        return "dummy"

    async def execute(self, task_id: str, prompt: str, **kwargs: Any) -> AgentResult:
        delay = random.randint(self._min_delay, self._max_delay) / 1000.0
        await asyncio.sleep(delay)
        return AgentResult(
            task_id=task_id,
            success=True,
            output=f"[Dummy] Processed: {prompt}",
            metadata={"delay_ms": int(delay * 1000)},
        )
