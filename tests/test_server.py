"""Tests for the Flint Python server core components."""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
from flint_ai.server.engine import (
    EdgeCondition,
    RetryPolicy,
    TaskPriority,
    TaskRecord,
    TaskState,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
    WorkflowRun,
    WorkflowRunState,
)


class TestTaskState:
    def test_terminal_states(self):
        assert TaskState.SUCCEEDED.is_terminal
        assert TaskState.FAILED.is_terminal
        assert TaskState.DEAD_LETTER.is_terminal
        assert TaskState.CANCELLED.is_terminal
        assert not TaskState.QUEUED.is_terminal
        assert not TaskState.RUNNING.is_terminal
        assert not TaskState.PENDING.is_terminal

    def test_task_record_defaults(self):
        rec = TaskRecord(agent_type="openai", prompt="hello")
        assert rec.state == TaskState.QUEUED
        assert rec.priority == TaskPriority.NORMAL
        assert rec.attempt == 0
        assert rec.max_retries == 3
        assert rec.id  # auto-generated

    def test_task_priority_ordering(self):
        assert TaskPriority.LOW < TaskPriority.NORMAL < TaskPriority.HIGH < TaskPriority.CRITICAL


class TestRetryPolicy:
    def test_delay_calculation(self):
        policy = RetryPolicy(backoff_base_s=1.0, backoff_multiplier=2.0, backoff_max_s=60.0)
        d0 = policy.delay_for_attempt(0)
        d1 = policy.delay_for_attempt(1)
        d2 = policy.delay_for_attempt(2)
        # Base delays: 1, 2, 4 — with ±25% jitter
        assert 0.75 <= d0 <= 1.25
        assert 1.5 <= d1 <= 2.5
        assert 3.0 <= d2 <= 5.0

    def test_delay_capped(self):
        policy = RetryPolicy(backoff_base_s=1.0, backoff_multiplier=10.0, backoff_max_s=5.0)
        d10 = policy.delay_for_attempt(10)
        assert d10 <= 6.25  # 5.0 + 25% jitter


class TestEdgeCondition:
    def test_empty_condition(self):
        cond = EdgeCondition()
        assert cond.is_empty()

    def test_status_condition(self):
        cond = EdgeCondition(on_status=[TaskState.SUCCEEDED])
        assert not cond.is_empty()

    def test_expression_condition(self):
        cond = EdgeCondition(expression='status == "succeeded"')
        assert not cond.is_empty()


# ---------------------------------------------------------------------------
# Queue (In-Memory)
# ---------------------------------------------------------------------------
from flint_ai.server.queue.memory import InMemoryQueue  # noqa: E402


class TestInMemoryQueue:
    @pytest.fixture
    def queue(self):
        return InMemoryQueue()

    @pytest.mark.asyncio
    async def test_enqueue_dequeue(self, queue):
        msg_id = await queue.enqueue("t1", {"agent_type": "dummy"})
        assert msg_id

        messages = await queue.dequeue(count=1, block_ms=100)
        assert len(messages) == 1
        assert messages[0].task_id == "t1"

    @pytest.mark.asyncio
    async def test_ack_removes(self, queue):
        await queue.enqueue("t1", {"agent_type": "dummy"})
        msgs = await queue.dequeue(count=1, block_ms=100)
        await queue.ack(msgs[0].message_id)
        assert await queue.get_queue_length() == 0

    @pytest.mark.asyncio
    async def test_nack_requeues(self, queue):
        await queue.enqueue("t1", {"agent_type": "dummy"})
        msgs = await queue.dequeue(count=1, block_ms=100)
        await queue.nack(msgs[0].message_id)
        assert await queue.get_queue_length() == 1

    @pytest.mark.asyncio
    async def test_dlq_operations(self, queue):
        await queue.enqueue("t1", {"agent_type": "dummy"})
        msgs = await queue.dequeue(count=1, block_ms=100)
        await queue.move_to_dlq(msgs[0].message_id, reason="test failure")

        assert await queue.get_dlq_length() == 1
        dlq_msgs = await queue.get_dlq_messages()
        assert dlq_msgs[0].task_id == "t1"
        assert dlq_msgs[0].data["dlq_reason"] == "test failure"

    @pytest.mark.asyncio
    async def test_retry_dlq(self, queue):
        await queue.enqueue("t1", {"agent_type": "dummy"})
        msgs = await queue.dequeue(count=1, block_ms=100)
        await queue.move_to_dlq(msgs[0].message_id)

        new_id = await queue.retry_dlq_message(msgs[0].message_id)
        assert new_id
        assert await queue.get_dlq_length() == 0
        assert await queue.get_queue_length() == 1

    @pytest.mark.asyncio
    async def test_purge_dlq(self, queue):
        await queue.enqueue("t1", {"agent_type": "dummy"})
        msgs = await queue.dequeue(count=1, block_ms=100)
        await queue.move_to_dlq(msgs[0].message_id)

        count = await queue.purge_dlq()
        assert count == 1
        assert await queue.get_dlq_length() == 0

    @pytest.mark.asyncio
    async def test_empty_dequeue_returns_empty(self, queue):
        msgs = await queue.dequeue(count=1, block_ms=50)
        assert msgs == []


# ---------------------------------------------------------------------------
# Store (In-Memory)
# ---------------------------------------------------------------------------
from flint_ai.server.store.memory import InMemoryTaskStore, InMemoryWorkflowStore  # noqa: E402


class TestInMemoryTaskStore:
    @pytest.fixture
    def store(self):
        return InMemoryTaskStore()

    @pytest.mark.asyncio
    async def test_create_and_get(self, store):
        rec = TaskRecord(agent_type="dummy", prompt="test")
        await store.create(rec)
        got = await store.get(rec.id)
        assert got is not None
        assert got.agent_type == "dummy"

    @pytest.mark.asyncio
    async def test_update_state(self, store):
        rec = TaskRecord(agent_type="dummy", prompt="test")
        await store.create(rec)
        await store.update_state(rec.id, TaskState.RUNNING)
        got = await store.get(rec.id)
        assert got.state == TaskState.RUNNING

    @pytest.mark.asyncio
    async def test_list_filter_by_state(self, store):
        await store.create(TaskRecord(agent_type="a", prompt="1", state=TaskState.QUEUED))
        await store.create(TaskRecord(agent_type="b", prompt="2", state=TaskState.SUCCEEDED))
        await store.create(TaskRecord(agent_type="c", prompt="3", state=TaskState.QUEUED))

        queued = await store.list_tasks(state=TaskState.QUEUED)
        assert len(queued) == 2

    @pytest.mark.asyncio
    async def test_count_by_state(self, store):
        await store.create(TaskRecord(agent_type="a", prompt="1", state=TaskState.QUEUED))
        await store.create(TaskRecord(agent_type="b", prompt="2", state=TaskState.SUCCEEDED))
        counts = await store.count_by_state()
        assert counts[TaskState.QUEUED] == 1
        assert counts[TaskState.SUCCEEDED] == 1


class TestInMemoryWorkflowStore:
    @pytest.fixture
    def store(self):
        return InMemoryWorkflowStore()

    @pytest.mark.asyncio
    async def test_save_and_get_definition(self, store):
        defn = WorkflowDefinition(
            id="wf1",
            name="Test",
            nodes=[WorkflowNode(id="n1", agent_type="dummy", prompt_template="hello")],
        )
        await store.save_definition(defn)
        got = await store.get_definition("wf1")
        assert got is not None
        assert got.name == "Test"

    @pytest.mark.asyncio
    async def test_create_and_get_run(self, store):
        run = WorkflowRun(workflow_id="wf1")
        await store.create_run(run)
        got = await store.get_run(run.id)
        assert got is not None
        assert got.workflow_id == "wf1"


# ---------------------------------------------------------------------------
# Concurrency Manager
# ---------------------------------------------------------------------------
from flint_ai.server.config import ConcurrencyConfig  # noqa: E402
from flint_ai.server.engine.concurrency import ConcurrencyManager  # noqa: E402


class TestConcurrencyManager:
    @pytest.mark.asyncio
    async def test_acquire_release(self):
        config = ConcurrencyConfig(default_limit=2)
        mgr = ConcurrencyManager(config)

        await mgr.acquire("openai")
        stats = await mgr.get_stats()
        assert stats["openai"]["used"] == 1

        mgr.release("openai")
        stats = await mgr.get_stats()
        assert stats["openai"]["used"] == 0

    @pytest.mark.asyncio
    async def test_per_agent_limits(self):
        config = ConcurrencyConfig(default_limit=2, agent_limits={"openai": 1})
        mgr = ConcurrencyManager(config)
        await mgr.get_stats()  # no stats yet

        await mgr.acquire("openai")
        stats = await mgr.get_stats()
        assert stats["openai"]["limit"] == 1


# ---------------------------------------------------------------------------
# DAG Conditions
# ---------------------------------------------------------------------------
from flint_ai.server.dag.conditions import evaluate_condition  # noqa: E402


class TestConditionEvaluator:
    def test_empty_condition_succeeds_on_success(self):
        cond = EdgeCondition()
        assert evaluate_condition(cond, TaskState.SUCCEEDED) is True

    def test_empty_condition_fails_on_failure(self):
        cond = EdgeCondition()
        assert evaluate_condition(cond, TaskState.FAILED) is False

    def test_status_filter(self):
        cond = EdgeCondition(on_status=[TaskState.FAILED])
        assert evaluate_condition(cond, TaskState.FAILED) is True
        assert evaluate_condition(cond, TaskState.SUCCEEDED) is False

    def test_expression_simple(self):
        cond = EdgeCondition(expression='status == "succeeded"')
        assert evaluate_condition(cond, TaskState.SUCCEEDED) is True
        assert evaluate_condition(cond, TaskState.FAILED) is False

    def test_expression_with_result(self):
        cond = EdgeCondition(expression='"error" not in result')
        assert evaluate_condition(cond, TaskState.SUCCEEDED, upstream_result="all good") is True
        assert evaluate_condition(cond, TaskState.SUCCEEDED, upstream_result="error found") is False

    def test_expression_with_context(self):
        cond = EdgeCondition(expression='context.get("score", 0) > 5')
        assert evaluate_condition(cond, TaskState.SUCCEEDED, context={"score": 10}) is True
        assert evaluate_condition(cond, TaskState.SUCCEEDED, context={"score": 2}) is False

    def test_invalid_expression_returns_false(self):
        cond = EdgeCondition(expression="undefined_var + 1")
        assert evaluate_condition(cond, TaskState.SUCCEEDED) is False


# ---------------------------------------------------------------------------
# DAG Context (XCom)
# ---------------------------------------------------------------------------
from flint_ai.server.dag.context import WorkflowContext  # noqa: E402


class TestWorkflowContext:
    def test_push_pull(self):
        ctx = WorkflowContext()
        ctx.push("n1", "key1", "value1")
        assert ctx.pull("n1", "key1") == "value1"
        assert ctx.pull("n1", "missing", "default") == "default"

    def test_push_pull_result(self):
        ctx = WorkflowContext()
        ctx.push_result("n1", "Hello world", {"tokens": 10})
        assert ctx.pull_result("n1") == "Hello world"
        assert ctx.pull("n1", "__metadata__") == {"tokens": 10}

    def test_upstream_results(self):
        ctx = WorkflowContext()
        ctx.push_result("n1", "Result 1")
        ctx.push_result("n2", "Result 2")
        results = ctx.get_upstream_results(["n1", "n2"])
        assert results == {"n1": "Result 1", "n2": "Result 2"}

    def test_enriched_prompt_auto_prepend(self):
        ctx = WorkflowContext()
        ctx.push_result("n1", "Analysis complete")
        prompt = ctx.build_enriched_prompt("Write a summary", ["n1"])
        assert "[Output from n1]" in prompt
        assert "Analysis complete" in prompt
        assert "Write a summary" in prompt

    def test_enriched_prompt_template_vars(self):
        ctx = WorkflowContext()
        ctx.push_result("step1", "Code reviewed")
        ctx.push("step1", "score", "95")
        prompt = ctx.build_enriched_prompt("Based on {step1}, score={step1.score}", ["step1"])
        assert "Code reviewed" in prompt
        assert "95" in prompt

    def test_serialization(self):
        ctx = WorkflowContext()
        ctx.push("n1", "key", "val")
        data = ctx.to_dict()
        ctx2 = WorkflowContext.from_dict(data)
        assert ctx2.pull("n1", "key") == "val"


# ---------------------------------------------------------------------------
# DAG Engine
# ---------------------------------------------------------------------------
from flint_ai.server.dag.engine import DAGEngine  # noqa: E402


class TestDAGEngine:
    @pytest.fixture
    def stores(self):
        return InMemoryWorkflowStore(), InMemoryTaskStore()

    @pytest.fixture
    def engine(self, stores):
        return DAGEngine(workflow_store=stores[0], task_store=stores[1])

    def _make_linear_workflow(self) -> WorkflowDefinition:
        return WorkflowDefinition(
            id="wf-linear",
            name="Linear",
            nodes=[
                WorkflowNode(id="n1", agent_type="dummy", prompt_template="Step 1"),
                WorkflowNode(id="n2", agent_type="dummy", prompt_template="Step 2"),
                WorkflowNode(id="n3", agent_type="dummy", prompt_template="Step 3"),
            ],
            edges=[
                WorkflowEdge(from_node_id="n1", to_node_id="n2"),
                WorkflowEdge(from_node_id="n2", to_node_id="n3"),
            ],
        )

    def _make_fanout_workflow(self) -> WorkflowDefinition:
        return WorkflowDefinition(
            id="wf-fanout",
            nodes=[
                WorkflowNode(id="start", agent_type="dummy", prompt_template="Start"),
                WorkflowNode(id="branch_a", agent_type="dummy", prompt_template="A"),
                WorkflowNode(id="branch_b", agent_type="dummy", prompt_template="B"),
                WorkflowNode(id="join", agent_type="dummy", prompt_template="Join"),
            ],
            edges=[
                WorkflowEdge(from_node_id="start", to_node_id="branch_a"),
                WorkflowEdge(from_node_id="start", to_node_id="branch_b"),
                WorkflowEdge(from_node_id="branch_a", to_node_id="join"),
                WorkflowEdge(from_node_id="branch_b", to_node_id="join"),
            ],
        )

    def test_validate_valid(self, engine):
        wf = self._make_linear_workflow()
        errors = engine.validate(wf)
        assert errors == []

    def test_validate_cycle(self, engine):
        wf = WorkflowDefinition(
            id="wf-cycle",
            nodes=[
                WorkflowNode(id="a", agent_type="d", prompt_template="A"),
                WorkflowNode(id="b", agent_type="d", prompt_template="B"),
            ],
            edges=[
                WorkflowEdge(from_node_id="a", to_node_id="b"),
                WorkflowEdge(from_node_id="b", to_node_id="a"),
            ],
        )
        errors = engine.validate(wf)
        assert any("cycle" in e.lower() for e in errors)

    def test_validate_duplicate_ids(self, engine):
        wf = WorkflowDefinition(
            id="wf-dup",
            nodes=[
                WorkflowNode(id="n1", agent_type="d", prompt_template="A"),
                WorkflowNode(id="n1", agent_type="d", prompt_template="B"),
            ],
        )
        errors = engine.validate(wf)
        assert any("Duplicate" in e for e in errors)

    def test_validate_dangling_edge(self, engine):
        wf = WorkflowDefinition(
            id="wf-dangle",
            nodes=[WorkflowNode(id="n1", agent_type="d", prompt_template="A")],
            edges=[WorkflowEdge(from_node_id="n1", to_node_id="n999")],
        )
        errors = engine.validate(wf)
        assert any("unknown" in e.lower() for e in errors)

    def test_topological_sort(self, engine):
        wf = self._make_linear_workflow()
        order = engine.topological_sort(wf)
        assert order.index("n1") < order.index("n2") < order.index("n3")

    def test_root_nodes(self, engine):
        wf = self._make_fanout_workflow()
        roots = engine.get_root_nodes(wf)
        assert len(roots) == 1
        assert roots[0].id == "start"

    def test_upstream_nodes(self, engine):
        wf = self._make_fanout_workflow()
        upstream = engine.get_upstream_nodes("join", wf)
        assert set(upstream) == {"branch_a", "branch_b"}

    @pytest.mark.asyncio
    async def test_start_workflow(self, engine, stores):
        wf_store, _task_store = stores
        wf = self._make_linear_workflow()
        await wf_store.save_definition(wf)

        run = await engine.start_workflow("wf-linear")
        assert run.state == WorkflowRunState.RUNNING
        assert len(run.node_states) == 3

    @pytest.mark.asyncio
    async def test_conditional_edge(self, engine, stores):
        wf_store, _task_store = stores
        wf = WorkflowDefinition(
            id="wf-cond",
            nodes=[
                WorkflowNode(id="check", agent_type="dummy", prompt_template="Check"),
                WorkflowNode(id="pass", agent_type="dummy", prompt_template="Pass"),
                WorkflowNode(id="fail_handler", agent_type="dummy", prompt_template="Handle fail"),
            ],
            edges=[
                WorkflowEdge(
                    from_node_id="check",
                    to_node_id="pass",
                    condition=EdgeCondition(expression='"success" in result'),
                ),
                WorkflowEdge(
                    from_node_id="check",
                    to_node_id="fail_handler",
                    condition=EdgeCondition(on_status=[TaskState.FAILED]),
                ),
            ],
        )
        await wf_store.save_definition(wf)
        run = await engine.start_workflow("wf-cond")

        # Simulate success with "success" in result
        task = TaskRecord(
            id="t1",
            agent_type="dummy",
            prompt="Check",
            state=TaskState.SUCCEEDED,
            result_json="all success here",
            workflow_id="wf-cond",
            node_id="check",
        )
        run.node_states["check"] = TaskState.SUCCEEDED

        ready = await engine.on_task_completed(run, "check", task, wf)
        assert len(ready) == 1
        assert ready[0][0].id == "pass"


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------
from flint_ai.server.agents import AgentRegistry  # noqa: E402
from flint_ai.server.agents.dummy import DummyAgent  # noqa: E402


class TestAgents:
    @pytest.mark.asyncio
    async def test_dummy_agent(self):
        agent = DummyAgent(min_delay_ms=10, max_delay_ms=20)
        result = await agent.execute("t1", "hello world")
        assert result.success
        assert "hello world" in result.output

    def test_agent_registry(self):
        reg = AgentRegistry()
        reg.register(DummyAgent())
        assert reg.has("dummy")
        assert reg.get("dummy") is not None
        assert "dummy" in reg.list_types()
        assert not reg.has("nonexistent")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
from flint_ai.server.config import QueueBackend, ServerConfig, StoreBackend  # noqa: E402


class TestConfig:
    def test_defaults(self):
        config = ServerConfig()
        assert config.port == 5156
        assert config.queue_backend == QueueBackend.MEMORY
        assert config.store_backend == StoreBackend.MEMORY

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://test:6379")
        monkeypatch.setenv("POSTGRES_URL", "postgresql://test:5432/db")
        monkeypatch.setenv("WORKER_COUNT", "8")
        monkeypatch.setenv("CONCURRENCY_openai", "10")

        config = ServerConfig.from_env()
        assert config.queue_backend == QueueBackend.REDIS
        assert config.redis.url == "redis://test:6379"
        assert config.store_backend == StoreBackend.POSTGRES
        assert config.worker.count == 8
        assert config.concurrency.agent_limits["openai"] == 10


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
from flint_ai.server.metrics import FlintMetrics  # noqa: E402


class TestMetrics:
    def test_metrics_without_prometheus(self):
        """Metrics should work (no-op) even without prometheus_client."""
        metrics = FlintMetrics()
        # Should not raise
        metrics.record_submit("dummy")
        metrics.record_success("dummy", 1.0)
        metrics.record_failure("dummy")
        metrics.record_dead_letter("dummy")
        metrics.update_queue_lengths(10, 2)
