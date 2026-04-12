"""PostgreSQL-backed agent config store."""

from __future__ import annotations

import json
import logging
from typing import Any

from flint_ai.server.agents_config import AgentConfigRecord, BaseAgentConfigStore
from flint_ai.server.config import PostgresConfig

logger = logging.getLogger("flint.server.agents_config.postgres")


class PostgresAgentConfigStore(BaseAgentConfigStore):
    """PostgreSQL implementation of agent config storage."""

    def __init__(self, config: PostgresConfig) -> None:
        self._config = config
        self._pool: Any = None

    async def connect(self) -> None:
        try:
            import asyncpg
        except ImportError as e:
            raise ImportError(
                "asyncpg required for Postgres agent config. Install with: pip install flint-ai[server-postgres]"
            ) from e

        self._pool = await asyncpg.create_pool(
            self._config.url,
            min_size=1,
            max_size=2,
        )

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()

    async def save(self, record: AgentConfigRecord) -> None:
        async with self._pool.acquire() as conn:
            config_json = json.dumps(record.config_json)

            # Check if exists
            exists = await conn.fetchval(
                "SELECT 1 FROM flint_agents_config WHERE agent_type = $1",
                record.agent_type,
            )

            if exists:
                await conn.execute(
                    """UPDATE flint_agents_config
                       SET provider = $1, model = $2, config_json = $3::jsonb,
                           enabled = $4, updated_at = NOW()
                       WHERE agent_type = $5""",
                    record.provider,
                    record.model,
                    config_json,
                    record.enabled,
                    record.agent_type,
                )
            else:
                await conn.execute(
                    """INSERT INTO flint_agents_config
                       (agent_type, provider, model, config_json, enabled)
                       VALUES ($1, $2, $3, $4::jsonb, $5)""",
                    record.agent_type,
                    record.provider,
                    record.model,
                    config_json,
                    record.enabled,
                )
            logger.info("Saved agent config: %s", record.agent_type)

    async def get(self, agent_type: str) -> AgentConfigRecord | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT agent_type, provider, model, config_json, enabled, "
                "created_at, updated_at FROM flint_agents_config WHERE agent_type = $1",
                agent_type,
            )
            if row is None:
                return None
            return AgentConfigRecord(
                agent_type=row["agent_type"],
                provider=row["provider"],
                model=row["model"],
                config_json=json.loads(row["config_json"]),
                enabled=row["enabled"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    async def list_enabled(self) -> list[AgentConfigRecord]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT agent_type, provider, model, config_json, enabled, "
                "created_at, updated_at FROM flint_agents_config WHERE enabled = TRUE "
                "ORDER BY agent_type",
            )
            return [
                AgentConfigRecord(
                    agent_type=row["agent_type"],
                    provider=row["provider"],
                    model=row["model"],
                    config_json=json.loads(row["config_json"]),
                    enabled=row["enabled"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
                for row in rows
            ]

    async def disable(self, agent_type: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE flint_agents_config SET enabled = FALSE, updated_at = NOW() WHERE agent_type = $1",
                agent_type,
            )

    async def delete(self, agent_type: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM flint_agents_config WHERE agent_type = $1",
                agent_type,
            )
