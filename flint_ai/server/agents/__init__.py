"""Server-side agent interface and registry."""

from __future__ import annotations

import abc
import logging
from collections.abc import Callable
from typing import Any

from flint_ai.server.engine import AgentResult

logger = logging.getLogger("flint.server.agents")


class BaseAgent(abc.ABC):
    """Abstract interface for server-side agents.

    Server-side agents handle task execution. They receive a prompt
    and return a result. For AI-framework agents (OpenAI, LangChain, etc.),
    use the SDK adapter system instead.
    """

    @property
    @abc.abstractmethod
    def agent_type(self) -> str:
        """Unique identifier for this agent type."""

    @abc.abstractmethod
    async def execute(self, task_id: str, prompt: str, **kwargs: Any) -> AgentResult:
        """Execute the agent with the given prompt.

        Args:
            task_id: Unique task identifier.
            prompt: The input prompt/instruction.
            **kwargs: Additional context (workflow_id, node_id, metadata, etc.)

        Returns:
            AgentResult with success/failure and output.
        """

    async def health_check(self) -> bool:
        """Check if the agent is healthy and ready to accept tasks."""
        return True


class AgentRegistry:
    """Global registry for server-side agents."""

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}
        self._factories: dict[str, Callable[[], BaseAgent]] = {}

    def register(self, agent: BaseAgent) -> None:
        """Register an agent instance."""
        self._agents[agent.agent_type] = agent
        logger.info("Registered agent: %s", agent.agent_type)

    def register_factory(self, agent_type: str, factory: Callable[[], BaseAgent]) -> None:
        """Register a factory function for lazy agent creation."""
        self._factories[agent_type] = factory
        logger.info("Registered agent factory: %s", agent_type)

    def get(self, agent_type: str) -> BaseAgent | None:
        """Get an agent by type, creating from factory if needed."""
        if agent_type in self._agents:
            return self._agents[agent_type]
        if agent_type in self._factories:
            agent = self._factories[agent_type]()
            self._agents[agent_type] = agent
            return agent
        return None

    def list_types(self) -> list[str]:
        """List all registered agent types."""
        types = set(self._agents.keys()) | set(self._factories.keys())
        return sorted(types)

    def has(self, agent_type: str) -> bool:
        return agent_type in self._agents or agent_type in self._factories
