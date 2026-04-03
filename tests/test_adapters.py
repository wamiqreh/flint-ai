"""Unit tests for the Flint adapter layer."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

# ── Core Types ──────────────────────────────────────────────────────────────
from flint_ai.adapters.core.types import (
    AdapterConfig,
    AgentRunResult,
    ErrorAction,
    ErrorMapping,
    RegisteredAgent,
)


class TestErrorMapping:
    def test_classify_retry(self):
        mapping = ErrorMapping(retry_on=[TimeoutError])
        assert mapping.classify(TimeoutError("timeout")) == ErrorAction.RETRY

    def test_classify_fail(self):
        mapping = ErrorMapping(fail_on=[ValueError])
        assert mapping.classify(ValueError("bad")) == ErrorAction.FAIL

    def test_classify_unknown_goes_to_dlq(self):
        mapping = ErrorMapping()
        assert mapping.classify(RuntimeError("wat")) == ErrorAction.DLQ

    def test_classify_subclass_match(self):
        mapping = ErrorMapping(retry_on=[OSError])
        assert mapping.classify(ConnectionError("conn")) == ErrorAction.RETRY


class TestAgentRunResult:
    def test_to_dict_success(self):
        result = AgentRunResult(output="hello")
        d = result.to_dict()
        assert d == {"output": "hello", "success": True}

    def test_to_dict_failure(self):
        result = AgentRunResult(output="", success=False, error="boom")
        d = result.to_dict()
        assert d["success"] is False
        assert d["error"] == "boom"

    def test_to_dict_with_metadata(self):
        result = AgentRunResult(output="ok", metadata={"model": "gpt-4o"})
        d = result.to_dict()
        assert d["metadata"]["model"] == "gpt-4o"


class TestRegisteredAgent:
    def test_to_registration_payload(self):
        agent = RegisteredAgent(name="test", url="http://localhost:8000/execute")
        payload = agent.to_registration_payload()
        assert payload == {"name": "test", "url": "http://localhost:8000/execute"}

    def test_payload_without_url(self):
        agent = RegisteredAgent(name="inline-agent", inline=True)
        payload = agent.to_registration_payload()
        assert payload == {"name": "inline-agent"}


class TestAdapterConfig:
    def test_defaults(self):
        config = AdapterConfig()
        assert config.flint_url == "http://localhost:5156"
        assert config.inline is True
        assert config.auto_register is True
        assert config.timeout_seconds == 300.0
        assert config.max_retries == 3


# ── Base Adapter ────────────────────────────────────────────────────────────

from flint_ai.adapters.core.base import FlintAdapter  # noqa: E402


class DummyAdapter(FlintAdapter):
    """A test adapter that returns a fixed response."""

    def __init__(self, name: str = "dummy", response: str = "ok", should_fail: bool = False):
        super().__init__(name=name)
        self._response = response
        self._should_fail = should_fail

    async def run(self, input_data):
        if self._should_fail:
            raise RuntimeError("agent crashed")
        return AgentRunResult(output=self._response)


class TestFlintAdapter:
    def test_get_agent_name(self):
        adapter = DummyAdapter(name="my-agent")
        assert adapter.get_agent_name() == "my-agent"

    def test_to_registered_agent(self):
        adapter = DummyAdapter(name="my-agent")
        reg = adapter.to_registered_agent()
        assert reg.name == "my-agent"
        assert reg.inline is True

    def test_run_success(self):
        adapter = DummyAdapter(response="hello world")
        result = asyncio.run(adapter.run({"prompt": "test"}))
        assert result.output == "hello world"
        assert result.success is True

    def test_safe_run_catches_errors(self):
        adapter = DummyAdapter(should_fail=True)
        adapter._error_mapping = ErrorMapping(retry_on=[RuntimeError])
        result = asyncio.run(adapter.safe_run({"prompt": "test"}))
        assert result.success is False
        assert "agent crashed" in result.error
        assert result.metadata["error_action"] == "retry"

    def test_safe_run_unknown_error_dlq(self):
        adapter = DummyAdapter(should_fail=True)
        result = asyncio.run(adapter.safe_run({"prompt": "test"}))
        assert result.metadata["error_action"] == "dlq"


# ── Registry ────────────────────────────────────────────────────────────────

from flint_ai.adapters.core.registry import (  # noqa: E402
    _inline_registry,
    get_inline_adapter,
    list_inline_adapters,
    register_inline,
)


class TestRegistry:
    def setup_method(self):
        _inline_registry.clear()

    def test_register_and_get(self):
        adapter = DummyAdapter(name="test-agent")
        register_inline(adapter)
        assert get_inline_adapter("test-agent") is adapter

    def test_get_missing_returns_none(self):
        assert get_inline_adapter("nonexistent") is None

    def test_list_adapters(self):
        register_inline(DummyAdapter(name="a"))
        register_inline(DummyAdapter(name="b"))
        adapters = list_inline_adapters()
        assert set(adapters.keys()) == {"a", "b"}


# ── Tool Decorator ──────────────────────────────────────────────────────────

from flint_ai.adapters.openai.tools import execute_tool_call, get_tool_schemas, tool  # noqa: E402


class TestToolDecorator:
    def test_basic_tool(self):
        @tool
        def greet(name: str) -> str:
            """Say hello."""
            return f"Hello {name}"

        assert hasattr(greet, "_flint_tool")
        assert greet._flint_tool_name == "greet"

    def test_custom_name_and_description(self):
        @tool(name="my_tool", description="Does a thing")
        def some_func(x: int) -> str:
            return str(x)

        assert some_func._flint_tool_name == "my_tool"
        schema = some_func._flint_tool_schema
        assert schema["function"]["name"] == "my_tool"
        assert schema["function"]["description"] == "Does a thing"

    def test_schema_generation(self):
        @tool
        def search(query: str, limit: int = 10) -> str:
            """Search for stuff."""
            return "results"

        schemas = get_tool_schemas([search])
        assert len(schemas) == 1
        fn = schemas[0]["function"]
        assert fn["name"] == "search"
        assert "query" in fn["parameters"]["properties"]
        assert "limit" in fn["parameters"]["properties"]
        assert "query" in fn["parameters"]["required"]
        assert "limit" not in fn["parameters"]["required"]

    def test_execute_tool_call(self):
        @tool
        def add(a: int, b: int) -> str:
            return str(a + b)

        result = asyncio.run(execute_tool_call([add], "add", {"a": 3, "b": 4}))
        assert result == "7"

    def test_execute_tool_not_found(self):
        result = asyncio.run(execute_tool_call([], "missing", {}))
        assert "tool_not_found" in result

    def test_execute_async_tool(self):
        @tool
        async def async_greet(name: str) -> str:
            return f"Hi {name}"

        result = asyncio.run(execute_tool_call([async_greet], "async_greet", {"name": "World"}))
        assert result == "Hi World"


# ── FlintOpenAIAgent ────────────────────────────────────────────────────────

from flint_ai.adapters.openai.agent import FlintOpenAIAgent  # noqa: E402


class TestFlintOpenAIAgent:
    def test_creation(self):
        agent = FlintOpenAIAgent(
            name="reviewer",
            model="gpt-4o",
            instructions="Review code",
        )
        assert agent.name == "reviewer"
        assert agent.model == "gpt-4o"

    def test_missing_api_key(self):
        agent = FlintOpenAIAgent(name="test", api_key="")
        with patch.dict("os.environ", {}, clear=True):
            agent.api_key = ""
            result = asyncio.run(agent.run({"prompt": "hello"}))
            assert result.success is False
            assert "OPENAI_API_KEY" in result.error

    def test_to_registered_agent(self):
        agent = FlintOpenAIAgent(name="reviewer")
        reg = agent.to_registered_agent()
        assert reg.name == "reviewer"
        assert reg.adapter_type == "FlintOpenAIAgent"


# ── Workflow Builder with Adapters ──────────────────────────────────────────

from flint_ai import Node, Workflow  # noqa: E402


class TestWorkflowWithAdapters:
    def test_node_with_string_agent(self):
        node = Node("n1", agent="dummy", prompt="test")
        assert node._agent == "dummy"
        assert node._adapter is None

    def test_node_with_adapter(self):
        agent = FlintOpenAIAgent(name="my-agent")
        node = Node("n1", agent=agent, prompt="test")
        assert node._agent == "my-agent"
        assert node._adapter is agent

    def test_workflow_get_adapters(self):
        a1 = FlintOpenAIAgent(name="a1")
        a2 = FlintOpenAIAgent(name="a2")
        wf = (
            Workflow("test")
            .add(Node("n1", agent=a1, prompt="p1"))
            .add(Node("n2", agent="dummy", prompt="p2").depends_on("n1"))
            .add(Node("n3", agent=a2, prompt="p3").depends_on("n2"))
        )
        adapters = wf.get_adapters()
        assert len(adapters) == 2
        assert adapters[0].name == "a1"
        assert adapters[1].name == "a2"

    def test_workflow_builds_correctly_with_adapters(self):
        agent = FlintOpenAIAgent(name="reviewer")
        wf = (
            Workflow("test")
            .add(Node("review", agent=agent, prompt="Review this"))
            .add(Node("report", agent="dummy", prompt="Report").depends_on("review"))
        )
        wf_def = wf.build()
        assert len(wf_def.nodes) == 2
        assert wf_def.nodes[0].agent_type == "reviewer"
        assert wf_def.nodes[1].agent_type == "dummy"
        assert len(wf_def.edges) == 1

    def test_adapter_config_inherited(self):
        config = AdapterConfig(human_approval=True, max_retries=5)
        agent = FlintOpenAIAgent(name="strict", config=config)
        node = Node("n1", agent=agent, prompt="test")
        assert node._human_approval is True
        assert node._max_retries == 5


# ── Failure Path / DLQ Tests ───────────────────────────────────────────────


class TestFailurePaths:
    def test_error_mapping_classifies_timeout_as_retry(self):
        mapping = ErrorMapping(retry_on=[TimeoutError, ConnectionError])
        assert mapping.classify(TimeoutError()) == ErrorAction.RETRY
        assert mapping.classify(ConnectionError()) == ErrorAction.RETRY

    def test_error_mapping_classifies_value_error_as_fail(self):
        mapping = ErrorMapping(fail_on=[ValueError, TypeError])
        assert mapping.classify(ValueError("bad input")) == ErrorAction.FAIL

    def test_unknown_error_goes_to_dlq(self):
        mapping = ErrorMapping(retry_on=[TimeoutError], fail_on=[ValueError])
        assert mapping.classify(KeyError("missing")) == ErrorAction.DLQ

    def test_safe_run_returns_error_action_in_metadata(self):
        adapter = DummyAdapter(should_fail=True)
        adapter._error_mapping = ErrorMapping(fail_on=[RuntimeError])
        result = asyncio.run(adapter.safe_run({"prompt": "test"}))
        assert result.success is False
        assert result.metadata["error_action"] == "fail"
        assert result.metadata["error_type"] == "RuntimeError"

    def test_safe_run_success_has_no_error(self):
        adapter = DummyAdapter(response="all good")
        result = asyncio.run(adapter.safe_run({"prompt": "test"}))
        assert result.success is True
        assert result.error is None


# ── Inline Worker ───────────────────────────────────────────────────────────

from flint_ai.adapters.core.worker import InlineWorker  # noqa: E402


class TestInlineWorker:
    def setup_method(self):
        _inline_registry.clear()

    def test_handle_execute_missing_adapter(self):
        worker = InlineWorker()
        result = asyncio.run(worker.handle_execute("nonexistent", {"prompt": "hi"}))
        assert "adapter_not_found" in result.get("error", "")

    def test_handle_execute_success(self):
        register_inline(DummyAdapter(name="test", response="done"))
        worker = InlineWorker()
        result = asyncio.run(worker.handle_execute("test", {"prompt": "go"}))
        assert result["output"] == "done"
        assert result["success"] is True

    def test_handle_list(self):
        register_inline(DummyAdapter(name="a"))
        register_inline(DummyAdapter(name="b"))
        worker = InlineWorker()
        result = asyncio.run(worker.handle_list())
        names = {a["name"] for a in result["agents"]}
        assert names == {"a", "b"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
