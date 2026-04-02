"""PostgreSQL store using asyncpg for task and workflow persistence."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from flint_ai.server.config import PostgresConfig
from flint_ai.server.engine import (
    TaskRecord,
    TaskState,
    TaskPriority,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowRunState,
)
from flint_ai.server.store import BaseTaskStore, BaseWorkflowStore

logger = logging.getLogger("flint.server.store.postgres")

MIGRATIONS = [
    # V1: Tasks table
    """
    CREATE TABLE IF NOT EXISTS flint_tasks (
        id TEXT PRIMARY KEY,
        agent_type TEXT NOT NULL,
        prompt TEXT NOT NULL,
        workflow_id TEXT,
        node_id TEXT,
        state TEXT NOT NULL DEFAULT 'queued',
        priority INTEGER NOT NULL DEFAULT 5,
        result_json TEXT,
        error TEXT,
        attempt INTEGER NOT NULL DEFAULT 0,
        max_retries INTEGER NOT NULL DEFAULT 3,
        metadata JSONB NOT NULL DEFAULT '{}',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        started_at TIMESTAMPTZ,
        completed_at TIMESTAMPTZ
    );
    CREATE INDEX IF NOT EXISTS idx_flint_tasks_state ON flint_tasks(state);
    CREATE INDEX IF NOT EXISTS idx_flint_tasks_workflow ON flint_tasks(workflow_id) WHERE workflow_id IS NOT NULL;
    """,
    # V2: Workflow definitions
    """
    CREATE TABLE IF NOT EXISTS flint_workflow_definitions (
        id TEXT PRIMARY KEY,
        name TEXT,
        description TEXT,
        definition JSONB NOT NULL,
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    # V3: Workflow runs
    """
    CREATE TABLE IF NOT EXISTS flint_workflow_runs (
        id TEXT PRIMARY KEY,
        workflow_id TEXT NOT NULL REFERENCES flint_workflow_definitions(id),
        state TEXT NOT NULL DEFAULT 'pending',
        node_states JSONB NOT NULL DEFAULT '{}',
        node_task_ids JSONB NOT NULL DEFAULT '{}',
        context JSONB NOT NULL DEFAULT '{}',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        completed_at TIMESTAMPTZ
    );
    CREATE INDEX IF NOT EXISTS idx_flint_runs_workflow ON flint_workflow_runs(workflow_id);
    """,
    # V4: Schema version tracking
    """
    CREATE TABLE IF NOT EXISTS flint_schema_version (
        version INTEGER PRIMARY KEY,
        applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
]


class PostgresTaskStore(BaseTaskStore):
    """PostgreSQL-backed task store using asyncpg."""

    def __init__(self, config: PostgresConfig) -> None:
        self._config = config
        self._pool: Any = None

    async def connect(self) -> None:
        try:
            import asyncpg
        except ImportError:
            raise ImportError(
                "asyncpg required for Postgres store. "
                "Install with: pip install flint-ai[server-postgres]"
            )

        self._pool = await asyncpg.create_pool(
            self._config.url,
            min_size=self._config.min_pool_size,
            max_size=self._config.max_pool_size,
        )
        logger.info("PostgreSQL task store connected (pool=%d-%d)",
                     self._config.min_pool_size, self._config.max_pool_size)

        if self._config.run_migrations:
            await self._run_migrations()

    async def _run_migrations(self) -> None:
        async with self._pool.acquire() as conn:
            # Ensure schema_version table
            await conn.execute(MIGRATIONS[3])
            for i, sql in enumerate(MIGRATIONS[:3], start=1):
                exists = await conn.fetchval(
                    "SELECT 1 FROM flint_schema_version WHERE version = $1", i
                )
                if not exists:
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO flint_schema_version (version) VALUES ($1)", i
                    )
                    logger.info("Applied migration V%d", i)

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()

    async def create(self, record: TaskRecord) -> TaskRecord:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO flint_tasks
                   (id, agent_type, prompt, workflow_id, node_id, state, priority,
                    result_json, error, attempt, max_retries, metadata, created_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)""",
                record.id, record.agent_type, record.prompt,
                record.workflow_id, record.node_id, record.state.value,
                record.priority.value, record.result_json, record.error,
                record.attempt, record.max_retries,
                json.dumps(record.metadata), record.created_at,
            )
        return record

    async def get(self, task_id: str) -> Optional[TaskRecord]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM flint_tasks WHERE id = $1", task_id)
            return self._row_to_record(row) if row else None

    async def update(self, record: TaskRecord) -> TaskRecord:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE flint_tasks SET
                   state=$2, priority=$3, result_json=$4, error=$5,
                   attempt=$6, metadata=$7, started_at=$8, completed_at=$9
                   WHERE id=$1""",
                record.id, record.state.value, record.priority.value,
                record.result_json, record.error, record.attempt,
                json.dumps(record.metadata), record.started_at, record.completed_at,
            )
        return record

    # Whitelist of columns allowed in dynamic updates (prevents SQL injection)
    _ALLOWED_COLUMNS = frozenset({
        "state", "result_json", "error", "attempt", "max_retries",
        "metadata", "started_at", "completed_at", "priority",
    })

    async def update_state(self, task_id: str, state: TaskState, **kwargs: Any) -> None:
        sets = ["state = $2"]
        params: list = [task_id, state.value]
        idx = 3
        for k, v in kwargs.items():
            if k not in self._ALLOWED_COLUMNS:
                raise ValueError(f"Column '{k}' not allowed in update")
            if k == "metadata":
                v = json.dumps(v)
            sets.append(f"{k} = ${idx}")
            params.append(v)
            idx += 1
        sql = f"UPDATE flint_tasks SET {', '.join(sets)} WHERE id = $1"
        async with self._pool.acquire() as conn:
            await conn.execute(sql, *params)

    async def list_tasks(
        self,
        state: Optional[TaskState] = None,
        workflow_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[TaskRecord]:
        conditions = []
        params: list = []
        idx = 1
        if state:
            conditions.append(f"state = ${idx}")
            params.append(state.value)
            idx += 1
        if workflow_id:
            conditions.append(f"workflow_id = ${idx}")
            params.append(workflow_id)
            idx += 1
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend([limit, offset])
        sql = f"SELECT * FROM flint_tasks {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx+1}"
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
            return [self._row_to_record(r) for r in rows]

    async def count_by_state(self) -> Dict[TaskState, int]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT state, COUNT(*) as cnt FROM flint_tasks GROUP BY state"
            )
            return {TaskState(r["state"]): r["cnt"] for r in rows}

    @staticmethod
    def _row_to_record(row: Any) -> TaskRecord:
        meta = row["metadata"]
        if isinstance(meta, str):
            meta = json.loads(meta)
        return TaskRecord(
            id=row["id"],
            agent_type=row["agent_type"],
            prompt=row["prompt"],
            workflow_id=row["workflow_id"],
            node_id=row["node_id"],
            state=TaskState(row["state"]),
            priority=TaskPriority(row["priority"]),
            result_json=row["result_json"],
            error=row["error"],
            attempt=row["attempt"],
            max_retries=row["max_retries"],
            metadata=meta,
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )


class PostgresWorkflowStore(BaseWorkflowStore):
    """PostgreSQL-backed workflow store."""

    def __init__(self, config: PostgresConfig) -> None:
        self._config = config
        self._pool: Any = None

    async def connect(self) -> None:
        try:
            import asyncpg
        except ImportError:
            raise ImportError("asyncpg required for Postgres store.")
        self._pool = await asyncpg.create_pool(
            self._config.url,
            min_size=self._config.min_pool_size,
            max_size=self._config.max_pool_size,
        )

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()

    async def save_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO flint_workflow_definitions (id, name, description, definition, enabled, created_at)
                   VALUES ($1, $2, $3, $4, $5, $6)
                   ON CONFLICT (id) DO UPDATE SET
                   name=EXCLUDED.name, description=EXCLUDED.description,
                   definition=EXCLUDED.definition, enabled=EXCLUDED.enabled""",
                definition.id, definition.name, definition.description,
                definition.model_dump_json(), definition.enabled, definition.created_at,
            )
        return definition

    async def get_definition(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT definition FROM flint_workflow_definitions WHERE id = $1", workflow_id
            )
            if row:
                return WorkflowDefinition.model_validate_json(row["definition"])
            return None

    async def list_definitions(self, limit: int = 100) -> List[WorkflowDefinition]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT definition FROM flint_workflow_definitions ORDER BY created_at DESC LIMIT $1",
                limit,
            )
            return [WorkflowDefinition.model_validate_json(r["definition"]) for r in rows]

    async def delete_definition(self, workflow_id: str) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM flint_workflow_definitions WHERE id = $1", workflow_id
            )
            return result == "DELETE 1"

    async def create_run(self, run: WorkflowRun) -> WorkflowRun:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO flint_workflow_runs
                   (id, workflow_id, state, node_states, node_task_ids, context, created_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7)""",
                run.id, run.workflow_id, run.state.value,
                json.dumps({k: v.value for k, v in run.node_states.items()}),
                json.dumps(run.node_task_ids),
                json.dumps(run.context),
                run.created_at,
            )
        return run

    async def get_run(self, run_id: str) -> Optional[WorkflowRun]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM flint_workflow_runs WHERE id = $1", run_id
            )
            return self._row_to_run(row) if row else None

    async def update_run(self, run: WorkflowRun) -> WorkflowRun:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE flint_workflow_runs SET
                   state=$2, node_states=$3, node_task_ids=$4,
                   context=$5, completed_at=$6
                   WHERE id=$1""",
                run.id, run.state.value,
                json.dumps({k: v.value if hasattr(v, 'value') else v for k, v in run.node_states.items()}),
                json.dumps(run.node_task_ids),
                json.dumps(run.context),
                run.completed_at,
            )
        return run

    async def list_runs(
        self, workflow_id: Optional[str] = None, limit: int = 50
    ) -> List[WorkflowRun]:
        async with self._pool.acquire() as conn:
            if workflow_id:
                rows = await conn.fetch(
                    "SELECT * FROM flint_workflow_runs WHERE workflow_id=$1 ORDER BY created_at DESC LIMIT $2",
                    workflow_id, limit,
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM flint_workflow_runs ORDER BY created_at DESC LIMIT $1", limit
                )
            return [self._row_to_run(r) for r in rows]

    @staticmethod
    def _row_to_run(row: Any) -> WorkflowRun:
        ns = row["node_states"]
        if isinstance(ns, str):
            ns = json.loads(ns)
        nti = row["node_task_ids"]
        if isinstance(nti, str):
            nti = json.loads(nti)
        ctx = row["context"]
        if isinstance(ctx, str):
            ctx = json.loads(ctx)

        return WorkflowRun(
            id=row["id"],
            workflow_id=row["workflow_id"],
            state=WorkflowRunState(row["state"]),
            node_states={k: TaskState(v) for k, v in ns.items()},
            node_task_ids=nti,
            context=ctx,
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )
