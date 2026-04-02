"""End-to-end tests for the Flint server.

Tests the full request lifecycle: API → TaskEngine → Queue → Worker → Store
using in-memory backends (no external dependencies).
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from flint_ai.adapters.core.types import AgentRunResult, ErrorMapping
from flint_ai.adapters.core.base import FlintAdapter
from flint_ai.server.config import ServerConfig
from flint_ai.server.engine import TaskState, WorkflowRunState
from flint_ai.server.engine.concurrency import ConcurrencyManager
from flint_ai.server.engine.task_engine import TaskEngine
from flint_ai.server.dag.engine import DAGEngine
from flint_ai.server.metrics import FlintMetrics
from flint_ai.server.queue.memory import InMemoryQueue
from flint_ai.server.store.memory import InMemoryTaskStore, InMemoryWorkflowStore
from flint_ai.server.worker import Worker
from flint_ai.server.worker.pool import WorkerPool


# ── Test helpers ──────────────────────────────────────────────────────


class EchoAgent:
    """Test agent that echoes the prompt."""

    agent_type = "echo"

    async def execute(self, task_id: str, prompt: str, **kw: Any) -> Any:
        from flint_ai.server.engine import AgentResult
        return AgentResult(task_id=task_id, success=True, output=f"echo: {prompt}")

    async def health_check(self) -> bool:
        return True


class FailingAgent:
    """Test agent that always fails."""

    agent_type = "fail"

    def __init__(self, error: str = "boom"):
        self._error = error

    async def execute(self, task_id: str, prompt: str, **kw: Any) -> Any:
        from flint_ai.server.engine import AgentResult
        return AgentResult(task_id=task_id, success=False, error=self._error,
                           metadata={"error_action": "retry"})

    async def health_check(self) -> bool:
        return True


class SlowAgent:
    """Test agent that takes a configurable time to complete."""

    agent_type = "slow"

    def __init__(self, delay: float = 0.5):
        self._delay = delay

    async def execute(self, task_id: str, prompt: str, **kw: Any) -> Any:
        from flint_ai.server.engine import AgentResult
        await asyncio.sleep(self._delay)
        return AgentResult(task_id=task_id, success=True, output=f"slow: {prompt}")

    async def health_check(self) -> bool:
        return True


class CountingAgent:
    """Agent that succeeds on Nth attempt."""

    agent_type = "counting"

    def __init__(self, succeed_on_attempt: int = 2):
        self._target = succeed_on_attempt
        self.call_count = 0

    async def execute(self, task_id: str, prompt: str, **kw: Any) -> Any:
        from flint_ai.server.engine import AgentResult
        self.call_count += 1
        if self.call_count < self._target:
            return AgentResult(task_id=task_id, success=False,
                               error=f"attempt {self.call_count} failed",
                               metadata={"error_action": "retry"})
        return AgentResult(task_id=task_id, success=True,
                           output=f"succeeded on attempt {self.call_count}")

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

    agents = {"echo": EchoAgent(), "fail": FailingAgent(), "slow": SlowAgent()}

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


# ── Task lifecycle E2E ────────────────────────────────────────────────


class TestTaskLifecycleE2E:
    """Test the full task lifecycle: submit → process → succeed/fail/DLQ."""

    @pytest.mark.asyncio
    async def test_submit_process_succeed(self, engine_stack):
        """Submit a task, process it, verify it succeeds."""
        te = engine_stack["task_engine"]

        record = await te.submit_task(agent_type="echo", prompt="hello world")
        assert record.state == TaskState.QUEUED
        assert record.id is not None

        # Process the task
        processed = await te.process_next()
        assert processed is not None
        assert processed.state == TaskState.SUCCEEDED
        assert processed.result_json == "echo: hello world"

    @pytest.mark.asyncio
    async def test_submit_process_fail_goes_to_retry(self, engine_stack):
        """Failed task with retry action should re-queue."""
        te = engine_stack["task_engine"]

        record = await te.submit_task(agent_type="fail", prompt="test", max_retries=3)
        processed = await te.process_next()

        # Should be re-queued for retry (attempt 1 < max_retries 3)
        assert processed.state == TaskState.QUEUED
        assert processed.error == "boom"

    @pytest.mark.asyncio
    async def test_task_exhausts_retries_goes_to_dlq(self, engine_stack):
        """Task that exhausts retries should go to DLQ."""
        te = engine_stack["task_engine"]

        record = await te.submit_task(agent_type="fail", prompt="test", max_retries=1)
        # First attempt: attempt=1 (from dequeue), max_retries=1 → DLQ
        processed = await te.process_next()
        assert processed.state in (TaskState.DEAD_LETTER, TaskState.FAILED)

    @pytest.mark.asyncio
    async def test_unknown_agent_goes_to_dlq(self, engine_stack):
        """Task with unknown agent type should go to DLQ immediately."""
        te = engine_stack["task_engine"]

        record = await te.submit_task(agent_type="nonexistent", prompt="test")
        processed = await te.process_next()
        assert processed.state == TaskState.DEAD_LETTER
        assert "Unknown agent" in processed.error

    @pytest.mark.asyncio
    async def test_task_cancel(self, engine_stack):
        """Cancelling a queued task should set CANCELLED state."""
        te = engine_stack["task_engine"]

        record = await te.submit_task(agent_type="echo", prompt="test")
        cancelled = await te.cancel_task(record.id)
        assert cancelled.state == TaskState.CANCELLED

    @pytest.mark.asyncio
    async def test_task_restart(self, engine_stack):
        """Restarting a failed task should create a new task."""
        te = engine_stack["task_engine"]

        record = await te.submit_task(agent_type="fail", prompt="test", max_retries=0)
        # Process to failure (max_retries=0, but first attempt counts)
        processed = await te.process_next()
        # The task either fails or goes to DLQ

        restarted = await te.restart_task(record.id)
        assert restarted is not None
        assert restarted.state == TaskState.QUEUED
        assert restarted.id != record.id

    @pytest.mark.asyncio
    async def test_human_approval_flow(self, engine_stack):
        """Task with human_approval should wait in PENDING until approved."""
        te = engine_stack["task_engine"]

        record = await te.submit_task(
            agent_type="echo", prompt="needs approval",
            human_approval=True,
        )
        assert record.state == TaskState.PENDING

        # Approve the task
        approved = await te.approve_task(record.id)
        assert approved.state == TaskState.QUEUED

        # Now process it
        processed = await te.process_next()
        assert processed.state == TaskState.SUCCEEDED

    @pytest.mark.asyncio
    async def test_reject_task(self, engine_stack):
        """Rejecting a pending task should move it to DLQ."""
        te = engine_stack["task_engine"]

        record = await te.submit_task(
            agent_type="echo", prompt="reject me",
            human_approval=True,
        )
        assert record.state == TaskState.PENDING
        rejected = await te.reject_task(record.id)
        assert rejected.state == TaskState.DEAD_LETTER

    @pytest.mark.asyncio
    async def test_batch_submit(self, engine_stack):
        """Submit multiple tasks and process them all."""
        te = engine_stack["task_engine"]

        records = []
        for i in range(5):
            r = await te.submit_task(agent_type="echo", prompt=f"task {i}")
            records.append(r)

        assert len(records) == 5
        q_len = await engine_stack["queue"].get_queue_length()
        assert q_len == 5

        # Process all
        for _ in range(5):
            p = await te.process_next()
            assert p.state == TaskState.SUCCEEDED

    @pytest.mark.asyncio
    async def test_queue_dlq_operations(self, engine_stack):
        """Verify DLQ inspection, retry, and purge."""
        te = engine_stack["task_engine"]
        queue = engine_stack["queue"]

        # Submit and fail a task to DLQ
        record = await te.submit_task(agent_type="fail", prompt="dlq test", max_retries=0)
        await te.process_next()

        # Check DLQ
        dlq_len = await queue.get_dlq_length()
        assert dlq_len >= 1

        dlq_msgs = await queue.get_dlq_messages()
        assert len(dlq_msgs) >= 1


# ── Workflow / DAG E2E ────────────────────────────────────────────────


class TestWorkflowE2E:
    """Test DAG workflow execution end-to-end."""

    @pytest.mark.asyncio
    async def test_simple_linear_dag(self, engine_stack):
        """Test A → B → C linear workflow."""
        from flint_ai.server.engine import (
            WorkflowDefinition, WorkflowNode, WorkflowEdge, RetryPolicy,
        )

        dag = engine_stack["dag_engine"]
        wf_store = engine_stack["workflow_store"]

        defn = WorkflowDefinition(
            id="linear-test",
            name="Linear Test",
            nodes=[
                WorkflowNode(id="a", agent_type="echo", prompt_template="step A"),
                WorkflowNode(id="b", agent_type="echo", prompt_template="step B"),
                WorkflowNode(id="c", agent_type="echo", prompt_template="step C"),
            ],
            edges=[
                WorkflowEdge(from_node_id="a", to_node_id="b"),
                WorkflowEdge(from_node_id="b", to_node_id="c"),
            ],
        )

        # Validate
        errors = dag.validate(defn)
        assert errors == []

        # Save
        await wf_store.save_definition(defn)

        # Topological sort
        order = dag.topological_sort(defn)
        assert order == ["a", "b", "c"]

        # Get root nodes
        roots = dag.get_root_nodes(defn)
        assert len(roots) == 1
        assert roots[0].id == "a"

    @pytest.mark.asyncio
    async def test_parallel_fan_out_dag(self, engine_stack):
        """Test A → [B, C] → D fan-out/fan-in workflow."""
        from flint_ai.server.engine import (
            WorkflowDefinition, WorkflowNode, WorkflowEdge,
        )

        dag = engine_stack["dag_engine"]

        defn = WorkflowDefinition(
            id="fanout-test",
            name="Fan Out Test",
            nodes=[
                WorkflowNode(id="start", agent_type="echo", prompt_template="begin"),
                WorkflowNode(id="branch_a", agent_type="echo", prompt_template="branch A"),
                WorkflowNode(id="branch_b", agent_type="echo", prompt_template="branch B"),
                WorkflowNode(id="merge", agent_type="echo", prompt_template="merge"),
            ],
            edges=[
                WorkflowEdge(from_node_id="start", to_node_id="branch_a"),
                WorkflowEdge(from_node_id="start", to_node_id="branch_b"),
                WorkflowEdge(from_node_id="branch_a", to_node_id="merge"),
                WorkflowEdge(from_node_id="branch_b", to_node_id="merge"),
            ],
        )

        errors = dag.validate(defn)
        assert errors == []

        roots = dag.get_root_nodes(defn)
        assert len(roots) == 1
        assert roots[0].id == "start"

        order = dag.topological_sort(defn)
        assert order.index("start") < order.index("branch_a")
        assert order.index("start") < order.index("branch_b")
        assert order.index("branch_a") < order.index("merge")

    @pytest.mark.asyncio
    async def test_cycle_detection(self, engine_stack):
        """Cyclic DAG should fail validation."""
        from flint_ai.server.engine import (
            WorkflowDefinition, WorkflowNode, WorkflowEdge,
        )

        dag = engine_stack["dag_engine"]

        defn = WorkflowDefinition(
            id="cycle-test",
            name="Cycle Test",
            nodes=[
                WorkflowNode(id="a", agent_type="echo", prompt_template="A"),
                WorkflowNode(id="b", agent_type="echo", prompt_template="B"),
                WorkflowNode(id="c", agent_type="echo", prompt_template="C"),
            ],
            edges=[
                WorkflowEdge(from_node_id="a", to_node_id="b"),
                WorkflowEdge(from_node_id="b", to_node_id="c"),
                WorkflowEdge(from_node_id="c", to_node_id="a"),  # cycle!
            ],
        )

        errors = dag.validate(defn)
        assert len(errors) > 0
        assert any("cycle" in e.lower() for e in errors)

    @pytest.mark.asyncio
    async def test_workflow_run_start(self, engine_stack):
        """Starting a workflow should create a run with initial node states."""
        from flint_ai.server.engine import (
            WorkflowDefinition, WorkflowNode, WorkflowEdge,
        )

        dag = engine_stack["dag_engine"]
        wf_store = engine_stack["workflow_store"]

        defn = WorkflowDefinition(
            id="run-test",
            name="Run Test",
            nodes=[
                WorkflowNode(id="a", agent_type="echo", prompt_template="A"),
                WorkflowNode(id="b", agent_type="echo", prompt_template="B"),
            ],
            edges=[WorkflowEdge(from_node_id="a", to_node_id="b")],
        )
        await wf_store.save_definition(defn)

        run = await dag.start_workflow("run-test")
        assert run.state == WorkflowRunState.RUNNING
        assert "a" in run.node_states
        assert "b" in run.node_states


# ── Middleware tests ──────────────────────────────────────────────────


class TestCircuitBreaker:
    """Test the circuit breaker implementation."""

    def test_initial_state_closed(self):
        from flint_ai.server.middleware.circuit_breaker import CircuitBreaker, CircuitState
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=1.0)
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request()

    def test_trips_after_threshold(self):
        from flint_ai.server.middleware.circuit_breaker import CircuitBreaker, CircuitState
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=60.0)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert not cb.allow_request()

    def test_success_resets(self):
        from flint_ai.server.middleware.circuit_breaker import CircuitBreaker, CircuitState
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=60.0)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Simulate recovery timeout with reset
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request()

    def test_half_open_after_recovery_timeout(self):
        from flint_ai.server.middleware.circuit_breaker import CircuitBreaker, CircuitState
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0.1)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.allow_request()  # Allow probe

    def test_success_after_half_open_closes(self):
        from flint_ai.server.middleware.circuit_breaker import CircuitBreaker, CircuitState
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0.1)

        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitState.CLOSED


class TestInputValidation:
    """Test input validation helpers."""

    def test_valid_agent_type(self):
        from flint_ai.server.middleware.validation import validate_agent_type
        validate_agent_type("my_agent_123")
        validate_agent_type("openai")
        validate_agent_type("crew-ai-writer")

    def test_invalid_agent_type(self):
        from flint_ai.server.middleware.validation import validate_agent_type, ValidationError
        with pytest.raises(ValidationError):
            validate_agent_type("bad agent!")
        with pytest.raises(ValidationError):
            validate_agent_type("")
        with pytest.raises(ValidationError):
            validate_agent_type("a" * 200)

    def test_prompt_length_ok(self):
        from flint_ai.server.middleware.validation import validate_prompt_length
        validate_prompt_length("short prompt")
        validate_prompt_length("x" * 1000)

    def test_prompt_too_long(self):
        from flint_ai.server.middleware.validation import validate_prompt_length, ValidationError
        with pytest.raises(ValidationError):
            validate_prompt_length("x" * 2_000_000)

    def test_metadata_size_ok(self):
        from flint_ai.server.middleware.validation import validate_metadata
        validate_metadata({"key": "value"})
        validate_metadata(None)

    def test_metadata_too_large(self):
        from flint_ai.server.middleware.validation import validate_metadata, ValidationError
        big = {"key": "x" * 100_000}
        with pytest.raises(ValidationError):
            validate_metadata(big)

    def test_dag_size_ok(self):
        from flint_ai.server.middleware.validation import validate_dag_size
        validate_dag_size(list(range(100)))

    def test_dag_too_large(self):
        from flint_ai.server.middleware.validation import validate_dag_size, ValidationError
        with pytest.raises(ValidationError):
            validate_dag_size(list(range(600)))


class TestCorrelationID:
    """Test correlation ID middleware."""

    def test_get_request_id_default(self):
        from flint_ai.server.middleware.correlation import get_request_id
        # Should return empty string when no request context
        rid = get_request_id()
        assert isinstance(rid, str)


class TestErrorActionRouting:
    """Test that error_action metadata properly routes through task engine."""

    @pytest.mark.asyncio
    async def test_retry_action_retries(self, engine_stack):
        """error_action=retry should re-queue the task."""
        te = engine_stack["task_engine"]

        record = await te.submit_task(agent_type="fail", prompt="test", max_retries=3)
        processed = await te.process_next()

        # FailingAgent returns error_action="retry", so should re-queue
        assert processed.state == TaskState.QUEUED
        assert processed.error == "boom"

    @pytest.mark.asyncio
    async def test_fail_action_fails_immediately(self, engine_stack):
        """error_action=fail should fail without retry."""
        from flint_ai.server.engine import AgentResult

        class FailImmediately:
            agent_type = "fail_now"

            async def execute(self, task_id, prompt, **kw):
                return AgentResult(
                    task_id=task_id, success=False, error="bad request",
                    metadata={"error_action": "fail"},
                )

            async def health_check(self):
                return True

        engine_stack["agents"]["fail_now"] = FailImmediately()
        te = engine_stack["task_engine"]

        record = await te.submit_task(agent_type="fail_now", prompt="test", max_retries=5)
        processed = await te.process_next()
        assert processed.state == TaskState.FAILED

    @pytest.mark.asyncio
    async def test_dlq_action_goes_straight_to_dlq(self, engine_stack):
        """error_action=dlq should go to DLQ without retry."""
        from flint_ai.server.engine import AgentResult

        class DLQAgent:
            agent_type = "dlq_now"

            async def execute(self, task_id, prompt, **kw):
                return AgentResult(
                    task_id=task_id, success=False, error="invalid data",
                    metadata={"error_action": "dlq"},
                )

            async def health_check(self):
                return True

        engine_stack["agents"]["dlq_now"] = DLQAgent()
        te = engine_stack["task_engine"]

        record = await te.submit_task(agent_type="dlq_now", prompt="test", max_retries=5)
        processed = await te.process_next()
        assert processed.state == TaskState.DEAD_LETTER


# ── Config tests ─────────────────────────────────────────────────────


class TestConfigExtended:
    """Test new config options."""

    def test_sqs_backend_enum(self):
        from flint_ai.server.config import QueueBackend
        assert QueueBackend.SQS.value == "sqs"

    def test_api_key_from_env(self):
        import os
        os.environ["FLINT_API_KEY"] = "test-key-123"
        try:
            config = ServerConfig.from_env()
            assert config.api_key == "test-key-123"
        finally:
            del os.environ["FLINT_API_KEY"]

    def test_cors_origins_from_env(self):
        import os
        os.environ["FLINT_CORS_ORIGINS"] = "http://localhost:3000,https://app.example.com"
        try:
            config = ServerConfig.from_env()
            assert "http://localhost:3000" in config.cors_origins
            assert "https://app.example.com" in config.cors_origins
        finally:
            del os.environ["FLINT_CORS_ORIGINS"]

    def test_sqs_config_from_env(self):
        import os
        os.environ["SQS_QUEUE_URL"] = "https://sqs.us-east-1.amazonaws.com/123/test"
        try:
            from flint_ai.server.config import QueueBackend
            config = ServerConfig.from_env()
            assert config.queue_backend == QueueBackend.SQS
            assert config.sqs.queue_url == "https://sqs.us-east-1.amazonaws.com/123/test"
        finally:
            del os.environ["SQS_QUEUE_URL"]


# ── Fluent API E2E ────────────────────────────────────────────────────


class TestWorkflowBuilderE2E:
    """Test the Workflow.build() fluent API end-to-end."""

    def test_build_simple_workflow(self):
        from flint_ai import Workflow, Node

        wf = (
            Workflow("test")
            .add(Node("a", agent="echo", prompt="hello"))
            .add(Node("b", agent="echo", prompt="world").depends_on("a"))
        )

        defn = wf.build()
        assert defn.id == "test"
        assert len(defn.nodes) == 2
        assert len(defn.edges) == 1

    def test_build_with_approval_and_retries(self):
        from flint_ai import Workflow, Node

        wf = (
            Workflow("approval-test")
            .add(Node("step1", agent="echo", prompt="go")
                 .with_retries(5)
                 .dead_letter_on_failure())
            .add(Node("step2", agent="echo", prompt="approve me")
                 .requires_approval()
                 .depends_on("step1"))
        )

        # Use server dict format (Python server format)
        d = wf._to_server_dict()
        nodes_by_id = {n["id"]: n for n in d["nodes"]}

        assert nodes_by_id["step1"]["retry_policy"]["max_retries"] == 5
        assert nodes_by_id["step2"]["human_approval"] is True

    def test_cycle_detection(self):
        from flint_ai import Workflow, Node

        with pytest.raises(ValueError, match="[Cc]ycle"):
            (
                Workflow("cycle")
                .add(Node("a", agent="x", prompt="").depends_on("b"))
                .add(Node("b", agent="x", prompt="").depends_on("a"))
                .build()
            )

    def test_duplicate_node_detection(self):
        from flint_ai import Workflow, Node

        with pytest.raises(ValueError, match="[Dd]uplicate"):
            (
                Workflow("dup")
                .add(Node("a", agent="x", prompt=""))
                .add(Node("a", agent="y", prompt=""))
                .build()
            )
