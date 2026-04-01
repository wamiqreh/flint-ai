"""Per-agent concurrency control using asyncio semaphores."""

from __future__ import annotations

import asyncio
import logging
from typing import Dict

from flint_ai.server.config import ConcurrencyConfig

logger = logging.getLogger("flint.server.concurrency")


class ConcurrencyManager:
    """Manages per-agent concurrency limits using asyncio.Semaphore.

    Each agent type gets its own semaphore. When a worker picks up a task,
    it acquires the semaphore for that agent type. This prevents overwhelming
    external APIs (e.g., OpenAI rate limits).
    """

    def __init__(self, config: ConcurrencyConfig) -> None:
        self._config = config
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        self._usage: Dict[str, int] = {}

    def _get_semaphore(self, agent_type: str) -> asyncio.Semaphore:
        if agent_type not in self._semaphores:
            limit = self._config.get_limit(agent_type)
            self._semaphores[agent_type] = asyncio.Semaphore(limit)
            self._usage[agent_type] = 0
            logger.info("Created semaphore for agent=%s limit=%d", agent_type, limit)
        return self._semaphores[agent_type]

    async def acquire(self, agent_type: str) -> None:
        sem = self._get_semaphore(agent_type)
        await sem.acquire()
        self._usage[agent_type] = self._usage.get(agent_type, 0) + 1

    def release(self, agent_type: str) -> None:
        if agent_type in self._semaphores:
            self._semaphores[agent_type].release()
            self._usage[agent_type] = max(0, self._usage.get(agent_type, 1) - 1)

    def get_stats(self) -> Dict[str, Dict[str, int]]:
        """Return concurrency stats per agent type."""
        stats: Dict[str, Dict[str, int]] = {}
        for agent_type in self._semaphores:
            limit = self._config.get_limit(agent_type)
            used = self._usage.get(agent_type, 0)
            stats[agent_type] = {"limit": limit, "used": used, "available": limit - used}
        return stats
