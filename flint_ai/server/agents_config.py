"""Persistent agent configuration store.

Allows agents to be registered in the database so they survive
server restarts. On startup, the server auto-reconstructs agents
from this table.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("flint.server.agents_config")


@dataclass
class AgentConfigRecord:
    """A single agent configuration entry."""

    agent_type: str
    provider: str = "sdk"  # sdk, openai, anthropic, webhook
    model: str | None = None
    config_json: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


class BaseAgentConfigStore(ABC):
    """Abstract base for agent config storage."""

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def save(self, record: AgentConfigRecord) -> None:
        """Save or update an agent config entry."""

    @abstractmethod
    async def get(self, agent_type: str) -> AgentConfigRecord | None:
        """Get a single agent config by type."""

    @abstractmethod
    async def list_enabled(self) -> list[AgentConfigRecord]:
        """List all enabled agent configs."""

    @abstractmethod
    async def disable(self, agent_type: str) -> None:
        """Disable an agent config (soft delete)."""

    @abstractmethod
    async def delete(self, agent_type: str) -> None:
        """Hard delete an agent config."""


class InMemoryAgentConfigStore(BaseAgentConfigStore):
    """In-memory agent config store for testing."""

    def __init__(self) -> None:
        self._configs: dict[str, AgentConfigRecord] = {}

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def save(self, record: AgentConfigRecord) -> None:
        now = datetime.now(timezone.utc)
        if record.agent_type in self._configs:
            record.created_at = self._configs[record.agent_type].created_at
            record.updated_at = now
        else:
            record.created_at = now
            record.updated_at = now
        self._configs[record.agent_type] = record

    async def get(self, agent_type: str) -> AgentConfigRecord | None:
        return self._configs.get(agent_type)

    async def list_enabled(self) -> list[AgentConfigRecord]:
        return [r for r in self._configs.values() if r.enabled]

    async def disable(self, agent_type: str) -> None:
        if agent_type in self._configs:
            self._configs[agent_type].enabled = False
            self._configs[agent_type].updated_at = datetime.now(timezone.utc)

    async def delete(self, agent_type: str) -> None:
        self._configs.pop(agent_type, None)
