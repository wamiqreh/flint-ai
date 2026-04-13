"""PostgreSQL store using asyncpg for task and workflow persistence."""

from __future__ import annotations

import json
import logging
from typing import Any

from flint_ai.server.config import PostgresConfig
from flint_ai.server.engine import (
    TaskPriority,
    TaskRecord,
    TaskState,
    ToolExecution,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowRunState,
)
from flint_ai.server.store import BaseTaskStore, BaseToolExecutionStore, BaseWorkflowStore

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
    # V5: Model pricing table (seeded with OpenAI defaults)
    """
    CREATE TABLE IF NOT EXISTS flint_model_pricing (
        id TEXT PRIMARY KEY,
        model TEXT NOT NULL,
        provider TEXT NOT NULL DEFAULT 'openai',
        prompt_cost_per_million NUMERIC(10, 6) NOT NULL DEFAULT 0,
        completion_cost_per_million NUMERIC(10, 6) NOT NULL DEFAULT 0,
        currency TEXT NOT NULL DEFAULT 'USD',
        effective_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        effective_to TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_pricing_model ON flint_model_pricing(model);
    CREATE INDEX IF NOT EXISTS idx_pricing_active ON flint_model_pricing(model, effective_from) WHERE effective_to IS NULL;
    INSERT INTO flint_model_pricing (id, model, provider, prompt_cost_per_million, completion_cost_per_million)
    VALUES
        ('gpt-4o', 'gpt-4o', 'openai', 2.50, 10.00),
        ('gpt-4o-mini', 'gpt-4o-mini', 'openai', 0.150, 0.600),
        ('gpt-4-turbo', 'gpt-4-turbo', 'openai', 10.00, 30.00),
        ('gpt-4', 'gpt-4', 'openai', 30.00, 60.00),
        ('gpt-3.5-turbo', 'gpt-3.5-turbo', 'openai', 0.50, 1.50),
        ('o1', 'o1', 'openai', 15.00, 60.00),
        ('o1-mini', 'o1-mini', 'openai', 3.00, 12.00),
        ('o3-mini', 'o3-mini', 'openai', 1.10, 4.40)
    ON CONFLICT (id) DO NOTHING;
    """,
    # V6: Tool executions table
    """
    CREATE TABLE IF NOT EXISTS flint_tool_executions (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        workflow_run_id TEXT,
        node_id TEXT,
        tool_name TEXT NOT NULL,
        input_json JSONB,
        output_json JSONB,
        duration_ms NUMERIC(10, 2),
        error TEXT,
        stack_trace TEXT,
        sanitized_input JSONB,
        cost_usd NUMERIC(10, 6) DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'succeeded',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_tool_exec_task ON flint_tool_executions(task_id);
    CREATE INDEX IF NOT EXISTS idx_tool_exec_workflow ON flint_tool_executions(workflow_run_id);
    CREATE INDEX IF NOT EXISTS idx_tool_exec_tool_name ON flint_tool_executions(tool_name);
    CREATE INDEX IF NOT EXISTS idx_tool_exec_status ON flint_tool_executions(status);
    """,
    # V7: Fix model pricing to support time-bound entries (multiple prices per model)
    """
    ALTER TABLE flint_model_pricing DROP CONSTRAINT IF EXISTS flint_model_pricing_pkey;
    ALTER TABLE flint_model_pricing ADD COLUMN IF NOT EXISTS id TEXT;
    UPDATE flint_model_pricing SET id = model WHERE id IS NULL;
    ALTER TABLE flint_model_pricing ALTER COLUMN id SET NOT NULL;
    ALTER TABLE flint_model_pricing ADD PRIMARY KEY (id);
    CREATE INDEX IF NOT EXISTS idx_pricing_model ON flint_model_pricing(model);
    CREATE INDEX IF NOT EXISTS idx_pricing_active ON flint_model_pricing(model, effective_from) WHERE effective_to IS NULL;
    """,
    # V8: AI events table for unified usage tracking
    """
    CREATE TABLE IF NOT EXISTS flint_ai_events (
        id TEXT PRIMARY KEY,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        type TEXT NOT NULL,
        input_tokens INTEGER,
        output_tokens INTEGER,
        estimated BOOLEAN NOT NULL DEFAULT FALSE,
        cost_usd NUMERIC(10, 6),
        metadata JSONB NOT NULL DEFAULT '{}',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_events_task ON flint_ai_events((metadata->>'task_id'));
    CREATE INDEX IF NOT EXISTS idx_events_workflow ON flint_ai_events((metadata->>'workflow_run_id'));
    CREATE INDEX IF NOT EXISTS idx_events_model ON flint_ai_events(model);
    CREATE INDEX IF NOT EXISTS idx_events_type ON flint_ai_events(type);
    CREATE INDEX IF NOT EXISTS idx_events_created ON flint_ai_events(created_at);
    """,
    # V9: Seed Anthropic models in flint_model_pricing
    """
    INSERT INTO flint_model_pricing (id, model, provider, prompt_cost_per_million, completion_cost_per_million, effective_from)
    VALUES
        ('claude-3-5-sonnet-20241022', 'claude-3-5-sonnet-20241022', 'anthropic', 3.00, 15.00, NOW()),
        ('claude-3-opus-20250219', 'claude-3-opus-20250219', 'anthropic', 5.00, 25.00, NOW()),
        ('claude-3-sonnet-20240229', 'claude-3-sonnet-20240229', 'anthropic', 3.00, 15.00, NOW()),
        ('claude-3-haiku-20240307', 'claude-3-haiku-20240307', 'anthropic', 0.80, 4.00, NOW()),
        ('claude-2', 'claude-2', 'anthropic', 8.00, 24.00, NOW()),
        ('claude-2.1', 'claude-2.1', 'anthropic', 8.00, 24.00, NOW())
    ON CONFLICT (id) DO NOTHING;
    """,
    # V10: agents_config table + last_heartbeat for stale task recovery
    """
    -- Persistent agent registration so server restarts can auto-reconstruct
    CREATE TABLE IF NOT EXISTS flint_agents_config (
        agent_type TEXT PRIMARY KEY,
        provider TEXT NOT NULL DEFAULT 'sdk',
        model TEXT,
        config_json JSONB NOT NULL DEFAULT '{}',
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_agents_enabled ON flint_agents_config(agent_type) WHERE enabled = TRUE;

    ALTER TABLE flint_tasks ADD COLUMN IF NOT EXISTS last_heartbeat TIMESTAMPTZ;

    -- Composite index for efficient task claiming (FOR UPDATE SKIP LOCKED)
    CREATE INDEX IF NOT EXISTS idx_flint_tasks_claim
        ON flint_tasks(state, agent_type, priority DESC, created_at ASC)
        WHERE state = 'queued';
    """,
    # V11: version column for workflow run CAS
    """
    ALTER TABLE flint_workflow_runs ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 0;
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
        except ImportError as e:
            raise ImportError(
                "asyncpg required for Postgres store. Install with: pip install flint-ai[server-postgres]"
            ) from e

        self._pool = await asyncpg.create_pool(
            self._config.url,
            min_size=self._config.min_pool_size,
            max_size=self._config.max_pool_size,
        )
        logger.info(
            "PostgreSQL task store connected (pool=%d-%d)", self._config.min_pool_size, self._config.max_pool_size
        )

        if self._config.run_migrations:
            await self._run_migrations()

    async def _run_migrations(self) -> None:
        async with self._pool.acquire() as conn:
            # Ensure schema_version table (V4)
            await conn.execute(MIGRATIONS[3])
            for i, sql in enumerate(MIGRATIONS[:4], start=1):
                exists = await conn.fetchval("SELECT 1 FROM flint_schema_version WHERE version = $1", i)
                if not exists:
                    await conn.execute(sql)
                    await conn.execute("INSERT INTO flint_schema_version (version) VALUES ($1)", i)
                    logger.info("Applied migration V%d", i)
            # V5-V11 (cost tracking + pricing + AI events + Anthropic seed + agents_config + heartbeat + version)
            for i in (4, 5, 6, 7, 8, 9, 10):
                exists = await conn.fetchval("SELECT 1 FROM flint_schema_version WHERE version = $1", i + 1)
                if not exists:
                    await conn.execute(MIGRATIONS[i])
                    await conn.execute("INSERT INTO flint_schema_version (version) VALUES ($1)", i + 1)
                    logger.info("Applied migration V%d", i + 1)

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()

    async def create(self, record: TaskRecord) -> TaskRecord:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO flint_tasks
                   (id, agent_type, prompt, workflow_id, node_id, state, priority,
                    result_json, error, attempt, max_retries, metadata, created_at, last_heartbeat)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)""",
                record.id,
                record.agent_type,
                record.prompt,
                record.workflow_id,
                record.node_id,
                record.state.value,
                record.priority.value,
                record.result_json,
                record.error,
                record.attempt,
                record.max_retries,
                json.dumps(record.metadata),
                record.created_at,
                record.metadata.get("last_heartbeat"),
            )
        return record

    async def get(self, task_id: str) -> TaskRecord | None:
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
                record.id,
                record.state.value,
                record.priority.value,
                record.result_json,
                record.error,
                record.attempt,
                json.dumps(record.metadata),
                record.started_at,
                record.completed_at,
            )
        return record

    async def compare_and_swap(
        self,
        task_id: str,
        expected_state: TaskState,
        record: TaskRecord,
    ) -> bool:
        """Atomically update only if current state matches expected_state."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """UPDATE flint_tasks SET
                   state=$2, priority=$3, result_json=$4, error=$5,
                   attempt=$6, metadata=$7, started_at=$8, completed_at=$9
                   WHERE id=$1 AND state=$10""",
                record.id,
                record.state.value,
                record.priority.value,
                record.result_json,
                record.error,
                record.attempt,
                json.dumps(record.metadata),
                record.started_at,
                record.completed_at,
                expected_state.value,
            )
            return result == "UPDATE 1"

    # Whitelist of columns allowed in dynamic updates (prevents SQL injection)
    _ALLOWED_COLUMNS = frozenset(
        {
            "state",
            "result_json",
            "error",
            "attempt",
            "max_retries",
            "metadata",
            "started_at",
            "completed_at",
            "priority",
        }
    )

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
        state: TaskState | None = None,
        workflow_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TaskRecord]:
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
        sql = f"SELECT * FROM flint_tasks {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}"
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
            return [self._row_to_record(r) for r in rows]

    async def count_by_state(self) -> dict[TaskState, int]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT state, COUNT(*) as cnt FROM flint_tasks GROUP BY state")
            return {TaskState(r["state"]): r["cnt"] for r in rows}

    @staticmethod
    def _row_to_record(row: Any) -> TaskRecord:
        meta = row["metadata"]
        if isinstance(meta, str):
            meta = json.loads(meta)
        # Sync last_heartbeat column into metadata for backwards compat
        if row.get("last_heartbeat") and "last_heartbeat" not in meta:
            meta["last_heartbeat"] = row["last_heartbeat"]
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

    async def update_heartbeat(self, task_id: str) -> None:
        """Update the last_heartbeat timestamp for a task."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE flint_tasks SET last_heartbeat = NOW() WHERE id = $1",
                task_id,
            )

    async def find_stale_running_tasks(self, stale_threshold_seconds: int = 120) -> list[TaskRecord]:
        """Find tasks stuck in RUNNING state (no heartbeat for too long)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT * FROM flint_tasks
                   WHERE state = 'running'
                     AND (last_heartbeat < NOW() - ($1 * interval '1 second')
                          OR (last_heartbeat IS NULL AND started_at < NOW() - ($1 * interval '1 second')))
                   ORDER BY started_at""",
                stale_threshold_seconds,
            )
            return [self._row_to_record(row) for row in rows]

    async def reset_to_queued(self, task_id: str) -> None:
        """Reset a stuck RUNNING task back to QUEUED state for retry."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE flint_tasks SET
                   state = 'queued', error = 'Worker died without heartbeat. Auto-reset by stale recovery.',
                   last_heartbeat = NULL
                   WHERE id = $1 AND state = 'running'""",
                task_id,
            )

    async def claim_for_agent(
        self,
        agent_types: list[str],
        worker_id: str,
    ) -> TaskRecord | None:
        """Atomically claim the next QUEUED task matching one of the worker's agent types.

        Uses FOR UPDATE SKIP LOCKED — each concurrent worker gets its own row
        without contention. This is the standard PostgreSQL queue pattern.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """UPDATE flint_tasks SET
                   state = 'running',
                   attempt = attempt + 1,
                   started_at = NOW(),
                   metadata = jsonb_set(
                       COALESCE(metadata, '{}')::jsonb,
                       '{worker_id}',
                       $2::jsonb
                   ),
                   last_heartbeat = NOW()
                   WHERE id = (
                       SELECT id FROM flint_tasks
                       WHERE state = 'queued'
                         AND agent_type = ANY($3::text[])
                       ORDER BY priority DESC, created_at ASC
                       LIMIT 1
                       FOR UPDATE SKIP LOCKED
                   )
                   RETURNING *""",
                worker_id,
                f'"{worker_id}"',
                agent_types,
            )
            if row is None:
                return None
            return self._row_to_record(row)


class PostgresWorkflowStore(BaseWorkflowStore):
    def __init__(self, config: PostgresConfig) -> None:
        self._config = config
        self._pool: Any = None

    async def connect(self) -> None:
        try:
            import asyncpg
        except ImportError as e:
            raise ImportError("asyncpg required for Postgres store.") from e
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
                definition.id,
                definition.name,
                definition.description,
                definition.model_dump_json(),
                definition.enabled,
                definition.created_at,
            )
        return definition

    async def get_definition(self, workflow_id: str) -> WorkflowDefinition | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT definition FROM flint_workflow_definitions WHERE id = $1", workflow_id)
            if row:
                return WorkflowDefinition.model_validate_json(row["definition"])
            return None

    async def list_definitions(self, limit: int = 100) -> list[WorkflowDefinition]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT definition FROM flint_workflow_definitions ORDER BY created_at DESC LIMIT $1",
                limit,
            )
            return [WorkflowDefinition.model_validate_json(r["definition"]) for r in rows]

    async def delete_definition(self, workflow_id: str) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute("DELETE FROM flint_workflow_definitions WHERE id = $1", workflow_id)
            return result == "DELETE 1"

    async def create_run(self, run: WorkflowRun) -> WorkflowRun:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO flint_workflow_runs
                   (id, workflow_id, state, node_states, node_task_ids, context, created_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7)""",
                run.id,
                run.workflow_id,
                run.state.value,
                json.dumps({k: v.value for k, v in run.node_states.items()}),
                json.dumps(run.node_task_ids),
                json.dumps(run.context),
                run.created_at,
            )
        return run

    async def get_run(self, run_id: str) -> WorkflowRun | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM flint_workflow_runs WHERE id = $1", run_id)
            return self._row_to_run(row) if row else None

    async def update_run(self, run: WorkflowRun) -> WorkflowRun:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE flint_workflow_runs SET
                   state=$2, node_states=$3, node_task_ids=$4,
                   context=$5, version=version+1, completed_at=$6
                   WHERE id=$1""",
                run.id,
                run.state.value,
                json.dumps({k: v.value if hasattr(v, "value") else v for k, v in run.node_states.items()}),
                json.dumps(run.node_task_ids),
                json.dumps(run.context),
                run.completed_at,
            )
            run.version += 1
        return run

    async def compare_and_swap_run(
        self,
        run_id: str,
        expected_version: int,
        run: WorkflowRun,
    ) -> bool:
        """Atomically update run only if version matches."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """UPDATE flint_workflow_runs SET
                   state=$2, node_states=$3, node_task_ids=$4,
                   context=$5, version=version+1, completed_at=$6
                   WHERE id=$1 AND version=$7""",
                run_id,
                run.state.value,
                json.dumps({k: v.value if hasattr(v, "value") else v for k, v in run.node_states.items()}),
                json.dumps(run.node_task_ids),
                json.dumps(run.context),
                run.completed_at,
                expected_version,
            )
            if result == "UPDATE 1":
                run.version = expected_version + 1
                return True
            return False

    async def list_runs(self, workflow_id: str | None = None, limit: int = 50) -> list[WorkflowRun]:
        async with self._pool.acquire() as conn:
            if workflow_id:
                rows = await conn.fetch(
                    "SELECT * FROM flint_workflow_runs WHERE workflow_id=$1 ORDER BY created_at DESC LIMIT $2",
                    workflow_id,
                    limit,
                )
            else:
                rows = await conn.fetch("SELECT * FROM flint_workflow_runs ORDER BY created_at DESC LIMIT $1", limit)
            return [self._row_to_run(r) for r in rows]

    async def list_running_runs(self) -> list[WorkflowRun]:
        """Direct DB query for RUNNING runs (more efficient than base default)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM flint_workflow_runs WHERE state='RUNNING' ORDER BY created_at ASC")
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


class PostgresToolExecutionStore(BaseToolExecutionStore):
    """PostgreSQL-backed tool execution store."""

    def __init__(self, config: PostgresConfig) -> None:
        self._config = config
        self._pool: Any = None

    async def connect(self) -> None:
        try:
            import asyncpg
        except ImportError as e:
            raise ImportError("asyncpg required for Postgres store.") from e

        if self._pool is not None and self._pool.is_closed():
            self._pool = None

        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self._config.url,
                min_size=self._config.min_pool_size,
                max_size=self._config.max_pool_size,
            )
        logger.info("PostgreSQL tool execution store connected")

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()

    async def create(self, execution: ToolExecution) -> ToolExecution:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO flint_tool_executions
                   (id, task_id, workflow_run_id, node_id, tool_name, input_json, output_json,
                    duration_ms, error, stack_trace, sanitized_input, cost_usd, status, created_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)""",
                execution.id,
                execution.task_id,
                execution.workflow_run_id,
                execution.node_id,
                execution.tool_name,
                json.dumps(execution.input_json) if execution.input_json is not None else None,
                json.dumps(execution.output_json) if execution.output_json is not None else None,
                execution.duration_ms,
                execution.error,
                execution.stack_trace,
                json.dumps(execution.sanitized_input) if execution.sanitized_input is not None else None,
                execution.cost_usd,
                execution.status,
                execution.created_at,
            )
        return execution

    async def get(self, execution_id: str) -> ToolExecution | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM flint_tool_executions WHERE id = $1", execution_id)
            return self._row_to_execution(row) if row else None

    async def list_by_task(self, task_id: str, limit: int = 100) -> list[ToolExecution]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM flint_tool_executions WHERE task_id = $1 ORDER BY created_at DESC LIMIT $2",
                task_id,
                limit,
            )
            return [self._row_to_execution(r) for r in rows]

    async def list_by_workflow_run(self, workflow_run_id: str, limit: int = 200) -> list[ToolExecution]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM flint_tool_executions WHERE workflow_run_id = $1 ORDER BY created_at DESC LIMIT $2",
                workflow_run_id,
                limit,
            )
            return [self._row_to_execution(r) for r in rows]

    async def list_by_tool_name(self, tool_name: str, limit: int = 100) -> list[ToolExecution]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM flint_tool_executions WHERE tool_name = $1 ORDER BY created_at DESC LIMIT $2",
                tool_name,
                limit,
            )
            return [self._row_to_execution(r) for r in rows]

    async def list_errors(self, workflow_run_id: str | None = None, limit: int = 50) -> list[ToolExecution]:
        async with self._pool.acquire() as conn:
            if workflow_run_id:
                rows = await conn.fetch(
                    "SELECT * FROM flint_tool_executions WHERE status = 'failed' AND workflow_run_id = $1 ORDER BY created_at DESC LIMIT $2",
                    workflow_run_id,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM flint_tool_executions WHERE status = 'failed' ORDER BY created_at DESC LIMIT $1",
                    limit,
                )
            return [self._row_to_execution(r) for r in rows]

    async def list_recent(self, limit: int = 100, offset: int = 0) -> list[ToolExecution]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM flint_tool_executions ORDER BY created_at DESC LIMIT $1 OFFSET $2",
                limit,
                offset,
            )
            return [self._row_to_execution(r) for r in rows]

    @staticmethod
    def _row_to_execution(row: Any) -> ToolExecution:
        def _maybe_json(val):
            if val is None:
                return None
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    return val
            return val

        return ToolExecution(
            id=row["id"],
            task_id=row["task_id"],
            workflow_run_id=row["workflow_run_id"],
            node_id=row["node_id"],
            tool_name=row["tool_name"],
            input_json=_maybe_json(row["input_json"]),
            output_json=_maybe_json(row["output_json"]),
            duration_ms=float(row["duration_ms"]) if row["duration_ms"] is not None else None,
            error=row["error"],
            stack_trace=row["stack_trace"],
            sanitized_input=_maybe_json(row["sanitized_input"]),
            cost_usd=float(row["cost_usd"]) if row["cost_usd"] is not None else 0.0,
            status=row["status"],
            created_at=row["created_at"],
        )
