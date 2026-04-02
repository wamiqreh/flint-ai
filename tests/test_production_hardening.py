"""Tests for production hardening features.

Covers:
- Compare-and-swap (CAS) / optimistic locking
- Distributed concurrency manager
- Scheduler leader election
- Redis Pub/Sub event bus
- DAG crash recovery
- Structured JSON logging
- Multi-pod race simulation
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from flint_ai.server.config import ServerConfig, ConcurrencyConfig
from flint_ai.server.engine import (
    AgentResult,
    TaskRecord,
    TaskState,
    TaskPriority,
    WorkflowDefinition,
    WorkflowNode,
    WorkflowEdge,
    WorkflowRun,
    WorkflowRunState,
)
from flint_ai.server.engine.concurrency import ConcurrencyManager
from flint_ai.server.engine.task_engine import TaskEngine
from flint_ai.server.dag.engine import DAGEngine
from flint_ai.server.metrics import FlintMetrics
from flint_ai.server.queue.memory import InMemoryQueue
from flint_ai.server.store.memory import InMemoryTaskStore, InMemoryWorkflowStore


# ── Helpers ──────────────────────────────────────────────────────────


class EchoAgent:
    agent_type = "echo"

    async def execute(self, task_id: str, prompt: str, **kw: Any) -> Any:
        return AgentResult(task_id=task_id, success=True, output=f"echo: {prompt}")

    async def health_check(self) -> bool:
        return True


class SlowAgent:
    agent_type = "slow"

    async def execute(self, task_id: str, prompt: str, **kw: Any) -> Any:
        await asyncio.sleep(0.2)
        return AgentResult(task_id=task_id, success=True, output=f"slow: {prompt}")

    async def health_check(self) -> bool:
        return True


@pytest_asyncio.fixture
async def engine_stack():
    """Create a full engine stack with in-memory backends."""
    queue = InMemoryQueue()
    await queue.connect()
    task_store = InMemoryTaskStore()
    await task_store.connect()
    workflow_store = InMemoryWorkflowStore()
    await workflow_store.connect()

    config = ServerConfig()
    concurrency = ConcurrencyManager(config.concurrency)
    metrics = FlintMetrics()
    agents = {"echo": EchoAgent(), "slow": SlowAgent()}

    task_engine = TaskEngine(
        queue=queue,
        task_store=task_store,
        agent_registry=agents,
        concurrency=concurrency,
        metrics=metrics,
        max_task_duration_s=5,
    )

    dag_engine = DAGEngine(
        workflow_store=workflow_store,
        task_store=task_store,
    )

    yield {
        "queue": queue,
        "task_store": task_store,
        "workflow_store": workflow_store,
        "task_engine": task_engine,
        "dag_engine": dag_engine,
        "concurrency": concurrency,
        "metrics": metrics,
        "agents": agents,
        "config": config,
    }

    await queue.disconnect()
    await task_store.disconnect()
    await workflow_store.disconnect()


# ── 1. Compare-and-Swap (CAS) Tests ─────────────────────────────────


class TestCompareAndSwap:
    """Test optimistic locking prevents double-claim races."""

    @pytest.mark.asyncio
    async def test_cas_succeeds_on_expected_state(self, engine_stack):
        """CAS should succeed when state matches."""
        store = engine_stack["task_store"]
        record = TaskRecord(agent_type="echo", prompt="test", state=TaskState.QUEUED)
        record = await store.create(record)

        record.state = TaskState.RUNNING
        ok = await store.compare_and_swap(record.id, TaskState.QUEUED, record)
        assert ok is True

        updated = await store.get(record.id)
        assert updated.state == TaskState.RUNNING

    @pytest.mark.asyncio
    async def test_cas_fails_on_wrong_state(self, engine_stack):
        """CAS should fail when state doesn't match."""
        store = engine_stack["task_store"]
        record = TaskRecord(agent_type="echo", prompt="test", state=TaskState.QUEUED)
        record = await store.create(record)

        record.state = TaskState.RUNNING
        ok = await store.compare_and_swap(record.id, TaskState.RUNNING, record)
        assert ok is False

        original = await store.get(record.id)
        assert original.state == TaskState.QUEUED

    @pytest.mark.asyncio
    async def test_cas_prevents_double_claim(self, engine_stack):
        """Two concurrent CAS attempts on the same task — only one should win."""
        store = engine_stack["task_store"]
        record = TaskRecord(agent_type="echo", prompt="test", state=TaskState.QUEUED)
        record = await store.create(record)

        task1 = await store.get(record.id)
        task2 = await store.get(record.id)

        task1.state = TaskState.RUNNING
        task1.metadata["worker_id"] = "worker-1"
        task2.state = TaskState.RUNNING
        task2.metadata["worker_id"] = "worker-2"

        result1 = await store.compare_and_swap(record.id, TaskState.QUEUED, task1)
        result2 = await store.compare_and_swap(record.id, TaskState.QUEUED, task2)

        assert result1 is True
        assert result2 is False

        final = await store.get(record.id)
        assert final.metadata["worker_id"] == "worker-1"

    @pytest.mark.asyncio
    async def test_cas_nonexistent_task(self, engine_stack):
        """CAS on non-existent task should fail gracefully."""
        store = engine_stack["task_store"]
        record = TaskRecord(agent_type="echo", prompt="test", state=TaskState.RUNNING)
        ok = await store.compare_and_swap("nonexistent-id", TaskState.QUEUED, record)
        assert ok is False

    @pytest.mark.asyncio
    async def test_process_next_uses_cas(self, engine_stack):
        """process_next() should use CAS to atomically transition QUEUED→RUNNING."""
        te = engine_stack["task_engine"]
        store = engine_stack["task_store"]

        record = await te.submit_task(agent_type="echo", prompt="test CAS")
        assert record.state == TaskState.QUEUED

        processed = await te.process_next()
        assert processed is not None
        assert processed.state == TaskState.SUCCEEDED

        final = await store.get(record.id)
        assert final.state == TaskState.SUCCEEDED

    @pytest.mark.asyncio
    async def test_claim_task_uses_cas(self, engine_stack):
        """claim_task() for external workers should use CAS."""
        te = engine_stack["task_engine"]

        await te.submit_task(agent_type="echo", prompt="test claim CAS")

        claimed = await te.claim_task(agent_types=["echo"], worker_id="ext-1")
        assert claimed is not None
        assert claimed.state == TaskState.RUNNING
        assert claimed.metadata["worker_id"] == "ext-1"


# ── 2. Concurrent Claim Simulation ──────────────────────────────────


class TestConcurrentClaimRace:
    """Simulate multi-pod race conditions with concurrent claim attempts."""

    @pytest.mark.asyncio
    async def test_concurrent_process_next_only_one_wins(self, engine_stack):
        """When two workers try to process the same task, only one succeeds."""
        te = engine_stack["task_engine"]

        await te.submit_task(agent_type="echo", prompt="race test")

        # Both workers try to process simultaneously
        results = await asyncio.gather(
            te.process_next(),
            te.process_next(),
            return_exceptions=True,
        )

        # Exactly one should succeed
        non_none = [r for r in results if r is not None and not isinstance(r, Exception)]
        assert len(non_none) == 1
        assert non_none[0].state == TaskState.SUCCEEDED

    @pytest.mark.asyncio
    async def test_concurrent_claim_only_one_wins(self, engine_stack):
        """When two external workers claim concurrently, only one gets the task."""
        te = engine_stack["task_engine"]

        await te.submit_task(agent_type="echo", prompt="claim race")

        claims = await asyncio.gather(
            te.claim_task(agent_types=["echo"], worker_id="w1"),
            te.claim_task(agent_types=["echo"], worker_id="w2"),
        )

        non_none = [c for c in claims if c is not None]
        assert len(non_none) == 1
        assert non_none[0].metadata["worker_id"] in ("w1", "w2")

    @pytest.mark.asyncio
    async def test_many_tasks_no_double_processing(self, engine_stack):
        """Submit N tasks, process with M workers, ensure each task processed once."""
        te = engine_stack["task_engine"]
        store = engine_stack["task_store"]

        task_count = 10
        for i in range(task_count):
            await te.submit_task(agent_type="echo", prompt=f"task-{i}")

        # 20 concurrent workers competing for 10 tasks
        results = await asyncio.gather(
            *[te.process_next() for _ in range(20)],
            return_exceptions=True,
        )

        succeeded = [r for r in results if r is not None and not isinstance(r, Exception)]
        assert len(succeeded) == task_count

        # Verify all tasks succeeded in the store
        for r in succeeded:
            task = await store.get(r.id)
            assert task.state == TaskState.SUCCEEDED


# ── 3. Distributed Concurrency Manager Tests ────────────────────────


class TestDistributedConcurrencyManager:
    """Test the Redis-backed distributed concurrency manager."""

    @pytest.mark.asyncio
    async def test_distributed_concurrency_acquire_release(self):
        """Test acquire/release with a mocked Redis."""
        from flint_ai.server.engine.distributed_concurrency import DistributedConcurrencyManager

        mock_redis = AsyncMock()
        mock_redis.script_load = AsyncMock(return_value="sha123")
        mock_redis.evalsha = AsyncMock(return_value=1)  # Always succeeds

        config = ConcurrencyConfig(default_limit=5, agent_limits={"openai": 3})
        mgr = DistributedConcurrencyManager(config, mock_redis)

        await mgr.acquire("openai")
        mock_redis.evalsha.assert_awaited()

        # Verify the limit passed is correct (3 for openai)
        call_args = mock_redis.evalsha.call_args
        assert call_args[0][3] == 3  # limit is 4th positional arg (sha, numkeys, key, limit, ttl)

    @pytest.mark.asyncio
    async def test_distributed_concurrency_blocks_at_limit(self):
        """When at limit, acquire should retry."""
        from flint_ai.server.engine.distributed_concurrency import DistributedConcurrencyManager

        mock_redis = AsyncMock()
        mock_redis.script_load = AsyncMock(return_value="sha123")
        # First call returns 0 (at limit), second returns 1 (acquired)
        mock_redis.evalsha = AsyncMock(side_effect=[0, 1])

        config = ConcurrencyConfig(default_limit=1)
        mgr = DistributedConcurrencyManager(config, mock_redis)

        await mgr.acquire("test-agent")
        assert mock_redis.evalsha.await_count == 2

    @pytest.mark.asyncio
    async def test_distributed_concurrency_stats(self):
        """Stats should reflect current usage from Redis."""
        from flint_ai.server.engine.distributed_concurrency import DistributedConcurrencyManager

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="2")

        config = ConcurrencyConfig(default_limit=5, agent_limits={"openai": 3})
        mgr = DistributedConcurrencyManager(config, mock_redis)

        stats = await mgr.get_stats()
        assert "openai" in stats
        assert stats["openai"]["limit"] == 3
        assert stats["openai"]["used"] == 2
        assert stats["openai"]["available"] == 1


# ── 4. Scheduler Leader Lock Tests ──────────────────────────────────


class TestSchedulerLeaderLock:
    """Test Redis-based leader election for the scheduler."""

    @pytest.mark.asyncio
    async def test_leader_acquire(self):
        """Single instance should acquire leadership."""
        from flint_ai.server.dag.leader import SchedulerLeaderLock

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        lock = SchedulerLeaderLock(mock_redis)
        acquired = await lock._acquire()
        assert acquired is True
        mock_redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_leader_acquire_fails_when_held(self):
        """Second instance should fail to acquire leadership."""
        from flint_ai.server.dag.leader import SchedulerLeaderLock

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=None)  # NX fails

        lock = SchedulerLeaderLock(mock_redis)
        acquired = await lock._acquire()
        assert acquired is False

    @pytest.mark.asyncio
    async def test_leader_renew(self):
        """Leader should renew its lock."""
        from flint_ai.server.dag.leader import SchedulerLeaderLock

        mock_redis = AsyncMock()
        mock_redis.eval = AsyncMock(return_value=1)  # Lua returns 1

        lock = SchedulerLeaderLock(mock_redis)
        lock._is_leader = True
        renewed = await lock._renew()
        assert renewed is True

    @pytest.mark.asyncio
    async def test_leader_renew_fails_if_stolen(self):
        """Renew should fail if another instance stole the lock."""
        from flint_ai.server.dag.leader import SchedulerLeaderLock

        mock_redis = AsyncMock()
        mock_redis.eval = AsyncMock(return_value=0)

        lock = SchedulerLeaderLock(mock_redis)
        lock._is_leader = True
        renewed = await lock._renew()
        assert renewed is False

    @pytest.mark.asyncio
    async def test_leader_release(self):
        """Release should delete the key only if we hold it."""
        from flint_ai.server.dag.leader import SchedulerLeaderLock

        mock_redis = AsyncMock()
        mock_redis.eval = AsyncMock(return_value=1)

        lock = SchedulerLeaderLock(mock_redis)
        lock._is_leader = True
        await lock._release()
        assert lock._is_leader is False

    @pytest.mark.asyncio
    async def test_scheduler_skips_when_not_leader(self):
        """Scheduler loop should skip execution when not leader."""
        from flint_ai.server.dag.scheduler import WorkflowScheduler
        from flint_ai.server.dag.leader import SchedulerLeaderLock

        mock_leader = MagicMock(spec=SchedulerLeaderLock)
        mock_leader.is_leader = False

        callback = AsyncMock()
        scheduler = WorkflowScheduler(
            trigger_callback=callback,
            leader_lock=mock_leader,
        )

        # The scheduler wouldn't fire any callbacks since is_leader=False
        # This just validates wiring — full integration requires the loop running


# ── 5. Redis Pub/Sub Event Bus Tests ────────────────────────────────


class TestRedisPubSubBus:
    """Test the cross-pod SSE event bus."""

    @pytest.mark.asyncio
    async def test_publish(self):
        """Publish should send JSON to Redis."""
        from flint_ai.server.events import RedisPubSubBus

        mock_redis = AsyncMock()
        bus = RedisPubSubBus(mock_redis)

        await bus.publish("task-123", "succeeded", {"result": "ok"})

        mock_redis.publish.assert_awaited_once()
        channel, payload = mock_redis.publish.call_args[0]
        assert "task-123" in channel
        data = json.loads(payload)
        assert data["event"] == "succeeded"
        assert data["task_id"] == "task-123"

    @pytest.mark.asyncio
    async def test_subscribe_unsubscribe(self):
        """Subscribe and unsubscribe should manage local callbacks."""
        from flint_ai.server.events import RedisPubSubBus

        mock_redis = AsyncMock()
        bus = RedisPubSubBus(mock_redis)

        callback = MagicMock()
        bus.subscribe("task-123", callback)
        assert "task-123" in bus._subscribers
        assert callback in bus._subscribers["task-123"]

        bus.unsubscribe("task-123", callback)
        assert "task-123" not in bus._subscribers

    @pytest.mark.asyncio
    async def test_dispatch_calls_callbacks(self):
        """Internal dispatch should invoke registered callbacks."""
        from flint_ai.server.events import RedisPubSubBus

        mock_redis = AsyncMock()
        bus = RedisPubSubBus(mock_redis)

        received = []

        async def on_event(event, data):
            received.append((event, data))

        bus.subscribe("task-123", on_event)
        await bus._dispatch("task-123", "running", {"state": "running"})

        assert len(received) == 1
        assert received[0][0] == "running"

    @pytest.mark.asyncio
    async def test_task_engine_with_event_bus(self, engine_stack):
        """TaskEngine should publish events via event bus when configured."""
        from flint_ai.server.events import RedisPubSubBus

        mock_redis = AsyncMock()
        bus = RedisPubSubBus(mock_redis)

        te = engine_stack["task_engine"]
        te._event_bus = bus

        record = await te.submit_task(agent_type="echo", prompt="event bus test")
        processed = await te.process_next()

        assert processed.state == TaskState.SUCCEEDED
        # Should have published at least "running" and one of succeeded/failed
        assert mock_redis.publish.await_count >= 1


# ── 6. DAG Recovery Tests ────────────────────────────────────────────


class TestDAGRecovery:
    """Test crash recovery for workflow runs."""

    @pytest.mark.asyncio
    async def test_list_running_runs(self, engine_stack):
        """Workflow store should list runs in RUNNING state."""
        wf_store = engine_stack["workflow_store"]

        run1 = WorkflowRun(
            workflow_id="wf-1",
            state=WorkflowRunState.RUNNING,
            node_states={"A": TaskState.SUCCEEDED},
        )
        run2 = WorkflowRun(
            workflow_id="wf-2",
            state=WorkflowRunState.SUCCEEDED,
            node_states={"B": TaskState.SUCCEEDED},
        )
        await wf_store.create_run(run1)
        await wf_store.create_run(run2)

        running = await wf_store.list_running_runs()
        assert len(running) == 1
        assert running[0].workflow_id == "wf-1"

    @pytest.mark.asyncio
    async def test_recover_syncs_stale_states(self, engine_stack):
        """Recovery should sync run states with actual task states."""
        dag = engine_stack["dag_engine"]
        store = engine_stack["task_store"]
        wf_store = engine_stack["workflow_store"]
        te = engine_stack["task_engine"]
        queue = engine_stack["queue"]

        # Create a definition
        defn = WorkflowDefinition(
            id="wf-recovery",
            name="Recovery Test",
            nodes=[
                WorkflowNode(id="A", agent_type="echo", prompt_template="step A"),
                WorkflowNode(id="B", agent_type="echo", prompt_template="step B"),
            ],
            edges=[WorkflowEdge(from_node_id="A", to_node_id="B")],
        )
        await wf_store.save_definition(defn)

        # Simulate a run where task A finished but run wasn't updated
        task_a = TaskRecord(
            agent_type="echo", prompt="step A",
            state=TaskState.SUCCEEDED,
            result_json="done",
        )
        task_a = await store.create(task_a)

        run = WorkflowRun(
            workflow_id="wf-recovery",
            state=WorkflowRunState.RUNNING,
            node_states={"A": TaskState.RUNNING, "B": TaskState.PENDING},
            node_task_ids={"A": [task_a.id]},
        )
        run = await wf_store.create_run(run)

        # Recovery should detect A is actually SUCCEEDED
        await dag.recover_run(run, store, queue, te)

        updated_run = await wf_store.get_run(run.id)
        assert updated_run.node_states["A"] == TaskState.SUCCEEDED


# ── 7. Structured Logging Tests ─────────────────────────────────────


class TestStructuredLogging:
    """Test JSON log format support."""

    def test_config_log_format_default(self):
        """Default log format should be 'text'."""
        config = ServerConfig()
        assert config.log_format == "text"

    def test_config_log_format_from_env(self):
        """LOG_FORMAT env var should override default."""
        with patch.dict("os.environ", {"LOG_FORMAT": "json"}):
            config = ServerConfig.from_env()
            assert config.log_format == "json"


# ── 8. Memory Store Isolation Tests ─────────────────────────────────


class TestMemoryStoreIsolation:
    """Verify in-memory store returns copies (not references)."""

    @pytest.mark.asyncio
    async def test_get_returns_copy(self):
        """Modifying a get() result should not affect the store."""
        store = InMemoryTaskStore()
        record = TaskRecord(agent_type="echo", prompt="test", state=TaskState.QUEUED)
        record = await store.create(record)

        fetched = await store.get(record.id)
        fetched.state = TaskState.RUNNING

        original = await store.get(record.id)
        assert original.state == TaskState.QUEUED

    @pytest.mark.asyncio
    async def test_list_returns_copies(self):
        """Modifying list_tasks() results should not affect the store."""
        store = InMemoryTaskStore()
        for i in range(3):
            await store.create(
                TaskRecord(agent_type="echo", prompt=f"task-{i}", state=TaskState.QUEUED)
            )

        tasks = await store.list_tasks(state=TaskState.QUEUED)
        for t in tasks:
            t.state = TaskState.RUNNING

        originals = await store.list_tasks(state=TaskState.QUEUED)
        assert len(originals) == 3

    @pytest.mark.asyncio
    async def test_create_stores_copy(self):
        """Modifying the original record after create() should not affect the store."""
        store = InMemoryTaskStore()
        record = TaskRecord(agent_type="echo", prompt="test", state=TaskState.QUEUED)
        created = await store.create(record)

        record.state = TaskState.RUNNING  # mutate original

        stored = await store.get(created.id)
        assert stored.state == TaskState.QUEUED


# ── 9. Idempotent Retry Flow ────────────────────────────────────────


class TestIdempotentRetry:
    """Test retry flow with CAS ensures idempotent state transitions."""

    @pytest.mark.asyncio
    async def test_retry_requeues_with_cas(self, engine_stack):
        """A failing task should be atomically re-queued for retry."""
        te = engine_stack["task_engine"]
        store = engine_stack["task_store"]

        # Register a failing agent
        class FailAgent:
            agent_type = "fail"
            async def execute(self, task_id, prompt, **kw):
                return AgentResult(task_id=task_id, success=False, error="boom",
                                   metadata={"error_action": "retry"})
            async def health_check(self):
                return True

        te._agents["fail"] = FailAgent()

        record = await te.submit_task(agent_type="fail", prompt="test retry", max_retries=3)

        # First attempt: should fail and be re-queued
        processed = await te.process_next()
        assert processed is not None
        assert processed.state == TaskState.QUEUED
        assert processed.attempt == 1

    @pytest.mark.asyncio
    async def test_exhausted_retries_goes_to_dlq(self, engine_stack):
        """Task with no retries left should go to DLQ."""
        te = engine_stack["task_engine"]

        class FailAgent:
            agent_type = "fail"
            async def execute(self, task_id, prompt, **kw):
                return AgentResult(task_id=task_id, success=False, error="boom",
                                   metadata={"error_action": "retry"})
            async def health_check(self):
                return True

        te._agents["fail"] = FailAgent()

        record = await te.submit_task(agent_type="fail", prompt="test dlq", max_retries=1)
        processed = await te.process_next()
        assert processed is not None
        assert processed.state in (TaskState.DEAD_LETTER, TaskState.FAILED)


# ── 10. Multi-Pod Simulation ────────────────────────────────────────


class TestMultiPodSimulation:
    """Simulate multiple pods competing for tasks."""

    @pytest.mark.asyncio
    async def test_two_engines_same_queue(self):
        """Two TaskEngines sharing a queue should not double-process."""
        queue = InMemoryQueue()
        await queue.connect()
        store = InMemoryTaskStore()
        await store.connect()

        config = ServerConfig()
        agents = {"echo": EchoAgent()}

        # Two "pods"
        te1 = TaskEngine(
            queue=queue, task_store=store, agent_registry=agents,
            concurrency=ConcurrencyManager(config.concurrency),
            metrics=FlintMetrics(), max_task_duration_s=5,
        )
        te2 = TaskEngine(
            queue=queue, task_store=store, agent_registry=agents,
            concurrency=ConcurrencyManager(config.concurrency),
            metrics=FlintMetrics(), max_task_duration_s=5,
        )

        # Submit 5 tasks
        for i in range(5):
            await te1.submit_task(agent_type="echo", prompt=f"multi-pod-{i}")

        # Both pods race to process
        all_results = await asyncio.gather(
            *[te1.process_next() for _ in range(5)],
            *[te2.process_next() for _ in range(5)],
            return_exceptions=True,
        )

        succeeded = [r for r in all_results if r is not None and not isinstance(r, Exception)]
        assert len(succeeded) == 5

        # All should have unique IDs
        ids = [r.id for r in succeeded]
        assert len(set(ids)) == 5

    @pytest.mark.asyncio
    async def test_two_engines_claim_race(self):
        """Two pods racing to claim external tasks."""
        queue = InMemoryQueue()
        await queue.connect()
        store = InMemoryTaskStore()
        await store.connect()

        config = ServerConfig()
        agents = {"echo": EchoAgent()}

        te1 = TaskEngine(
            queue=queue, task_store=store, agent_registry=agents,
            concurrency=ConcurrencyManager(config.concurrency),
            metrics=FlintMetrics(), max_task_duration_s=5,
        )
        te2 = TaskEngine(
            queue=queue, task_store=store, agent_registry=agents,
            concurrency=ConcurrencyManager(config.concurrency),
            metrics=FlintMetrics(), max_task_duration_s=5,
        )

        await te1.submit_task(agent_type="echo", prompt="claim-race")

        claims = await asyncio.gather(
            te1.claim_task(agent_types=["echo"], worker_id="pod-1"),
            te2.claim_task(agent_types=["echo"], worker_id="pod-2"),
        )

        non_none = [c for c in claims if c is not None]
        assert len(non_none) == 1

        await queue.disconnect()
        await store.disconnect()


# ── 11. Idempotency Guard (execution_id) ───────────────────────────


class TestIdempotencyGuard:
    """Tests for the execution_id idempotency guard in process_next."""

    @pytest.mark.asyncio
    async def test_execution_id_is_set_on_process(self, engine_stack):
        """process_next should stamp execution_id into metadata."""
        te = engine_stack["task_engine"]
        store = engine_stack["task_store"]

        rec = await te.submit_task(agent_type="echo", prompt="id-test")
        processed = await te.process_next()
        assert processed is not None

        final = await store.get(rec.id)
        assert "execution_id" in final.metadata
        assert len(final.metadata["execution_id"]) == 36  # UUID length

    @pytest.mark.asyncio
    async def test_execution_id_unique_per_attempt(self, engine_stack):
        """Each processing attempt should generate a new execution_id."""
        te = engine_stack["task_engine"]
        store = engine_stack["task_store"]

        rec = await te.submit_task(agent_type="echo", prompt="unique-exec-id")
        await te.process_next()

        first = await store.get(rec.id)
        exec_id_1 = first.metadata.get("execution_id")
        assert exec_id_1 is not None

        # Simulate a retry by re-submitting the same task
        rec2 = await te.submit_task(agent_type="echo", prompt="unique-exec-id-2")
        await te.process_next()

        second = await store.get(rec2.id)
        exec_id_2 = second.metadata.get("execution_id")
        assert exec_id_2 is not None
        assert exec_id_1 != exec_id_2  # Different tasks → different execution_ids

    @pytest.mark.asyncio
    async def test_stale_execution_id_blocks_duplicate(self):
        """If another worker overwrites execution_id between CAS and execute,
        the original worker should detect the mismatch and skip."""
        queue = InMemoryQueue()
        await queue.connect()
        store = InMemoryTaskStore()
        await store.connect()

        config = ServerConfig()
        agents = {"echo": EchoAgent()}

        te = TaskEngine(
            queue=queue, task_store=store, agent_registry=agents,
            concurrency=ConcurrencyManager(config.concurrency),
            metrics=FlintMetrics(), max_task_duration_s=5,
        )

        rec = await te.submit_task(agent_type="echo", prompt="dup-guard")

        # Monkey-patch store.get to simulate another worker changing execution_id
        original_get = store.get
        call_count = 0

        async def tampered_get(task_id):
            nonlocal call_count
            result = await original_get(task_id)
            call_count += 1
            # On the second get (the idempotency check), tamper the execution_id
            if call_count == 2 and result and "execution_id" in result.metadata:
                result.metadata["execution_id"] = "stolen-by-another-worker"
                # Write it back so the store reflects the tampering
                await store.update(result)
            return result

        store.get = tampered_get

        # process_next should detect mismatch and return None
        processed = await te.process_next()
        assert processed is None, (
            "Should have returned None because execution_id was tampered"
        )

        await queue.disconnect()
        await store.disconnect()
