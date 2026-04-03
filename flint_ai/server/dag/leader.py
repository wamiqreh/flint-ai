"""Distributed leader election for the workflow scheduler.

Uses Redis SET NX with TTL so only one pod runs scheduled workflows.
The leader periodically refreshes its lock; if it crashes, the lock
expires and another pod takes over.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
import uuid
from typing import Any

logger = logging.getLogger("flint.server.dag.leader")


class SchedulerLeaderLock:
    """Redis-based leader election for the scheduler.

    Only the pod that holds the lock runs scheduled workflows.
    Other pods stand by and attempt to acquire the lock when it expires.
    """

    LOCK_KEY = "flint:scheduler:leader"
    LOCK_TTL_S = 30  # lock expires after 30s if not renewed
    RENEW_INTERVAL_S = 10  # renew every 10s (well before TTL)

    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client
        self._identity = f"{socket.gethostname()}-{uuid.uuid4().hex[:6]}"
        self._is_leader = False
        self._renew_task: asyncio.Task | None = None
        self._running = False

    @property
    def is_leader(self) -> bool:
        return self._is_leader

    async def start(self) -> None:
        """Start the leader election loop."""
        self._running = True
        self._renew_task = asyncio.create_task(self._election_loop())
        logger.info("Leader election started (identity=%s)", self._identity)

    async def stop(self) -> None:
        """Stop and release leadership."""
        self._running = False
        if self._renew_task:
            self._renew_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._renew_task
        # Release lock if we hold it
        if self._is_leader:
            await self._release()
        logger.info("Leader election stopped")

    async def _election_loop(self) -> None:
        """Continuously try to acquire/renew the leader lock."""
        while self._running:
            try:
                if self._is_leader:
                    renewed = await self._renew()
                    if not renewed:
                        logger.warning("Lost leadership (lock expired or stolen)")
                        self._is_leader = False
                else:
                    acquired = await self._acquire()
                    if acquired:
                        logger.info("Acquired leadership")
                        self._is_leader = True

                await asyncio.sleep(self.RENEW_INTERVAL_S)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Leader election error")
                self._is_leader = False
                await asyncio.sleep(self.RENEW_INTERVAL_S)

    async def _acquire(self) -> bool:
        """Try to acquire the lock (SET NX EX)."""
        result = await self._redis.set(
            self.LOCK_KEY,
            self._identity,
            nx=True,
            ex=self.LOCK_TTL_S,
        )
        return result is True

    async def _renew(self) -> bool:
        """Renew the lock if we still hold it."""
        # Lua script: only renew if we're the current holder
        lua = """
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            redis.call('EXPIRE', KEYS[1], ARGV[2])
            return 1
        end
        return 0
        """
        result = await self._redis.eval(lua, 1, self.LOCK_KEY, self._identity, self.LOCK_TTL_S)
        return result == 1

    async def _release(self) -> None:
        """Release the lock if we hold it."""
        lua = """
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            redis.call('DEL', KEYS[1])
            return 1
        end
        return 0
        """
        await self._redis.eval(lua, 1, self.LOCK_KEY, self._identity)
        self._is_leader = False
        logger.info("Released leadership")
