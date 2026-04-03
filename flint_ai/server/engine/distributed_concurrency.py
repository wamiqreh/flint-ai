"""Distributed concurrency control using Redis for cross-pod limits."""

from __future__ import annotations

import logging
from typing import Any

from flint_ai.server.config import ConcurrencyConfig

logger = logging.getLogger("flint.server.concurrency.distributed")

# Lua script for atomic acquire: returns 1 if acquired, 0 if at limit
_ACQUIRE_LUA = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local current = tonumber(redis.call('GET', key) or '0')
if current < limit then
    redis.call('INCR', key)
    redis.call('EXPIRE', key, ttl)
    return 1
end
return 0
"""

# Lua script for atomic release: decrements but never below 0
_RELEASE_LUA = """
local key = KEYS[1]
local current = tonumber(redis.call('GET', key) or '0')
if current > 0 then
    redis.call('DECR', key)
    return 1
end
return 0
"""


class DistributedConcurrencyManager:
    """Cross-pod concurrency limits backed by Redis.

    Uses atomic Lua scripts to increment/decrement per-agent counters.
    All pods share the same Redis keys, so limits are enforced globally.
    """

    KEY_PREFIX = "flint:concurrency:"
    TTL_SECONDS = 600  # auto-expire keys if server dies without cleanup

    def __init__(self, config: ConcurrencyConfig, redis_client: Any) -> None:
        self._config = config
        self._redis = redis_client
        self._acquire_sha: str | None = None
        self._release_sha: str | None = None

    async def _ensure_scripts(self) -> None:
        if self._acquire_sha is None:
            self._acquire_sha = await self._redis.script_load(_ACQUIRE_LUA)
            self._release_sha = await self._redis.script_load(_RELEASE_LUA)

    def _key(self, agent_type: str) -> str:
        return f"{self.KEY_PREFIX}{agent_type}"

    async def acquire(self, agent_type: str) -> None:
        """Block until a concurrency slot is available for this agent type."""
        await self._ensure_scripts()
        limit = self._config.get_limit(agent_type)
        key = self._key(agent_type)

        import asyncio

        while True:
            result = await self._redis.evalsha(self._acquire_sha, 1, key, limit, self.TTL_SECONDS)
            if result == 1:
                logger.debug("Acquired slot for agent=%s", agent_type)
                return
            # Back off before retrying
            await asyncio.sleep(0.5)

    def release(self, agent_type: str) -> None:
        """Release a concurrency slot. Fire-and-forget via background task."""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(self._release_async(agent_type))
            task.add_done_callback(lambda _: None)
        except RuntimeError:
            pass  # no event loop — skip (tests, shutdown)

    async def _release_async(self, agent_type: str) -> None:
        await self._ensure_scripts()
        key = self._key(agent_type)
        await self._redis.evalsha(self._release_sha, 1, key)
        logger.debug("Released slot for agent=%s", agent_type)

    async def get_stats(self) -> dict[str, dict[str, int]]:
        """Return concurrency stats per agent type (reads from Redis)."""
        stats: dict[str, dict[str, int]] = {}
        for agent_type in [*list(self._config.agent_limits.keys()), "_default"]:
            if agent_type == "_default":
                continue
            limit = self._config.get_limit(agent_type)
            key = self._key(agent_type)
            used = int(await self._redis.get(key) or 0)
            stats[agent_type] = {"limit": limit, "used": used, "available": limit - used}
        return stats
