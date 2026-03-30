"""Unit tests for the Flint LangGraph adapter."""

from __future__ import annotations

import asyncio
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from flint_ai.adapters.core.types import (
    AdapterConfig,
    AgentRunResult,
    ErrorAction,
    ErrorMapping,
    RegisteredAgent,
)
from flint_ai.adapters.langgraph.agent import FlintLangGraphAdapter


# ── Helpers ─────────────────────────────────────────────────────────────────

def _make_mock_graph(messages=None):
    """Create a mock compiled LangGraph graph."""
    if messages is None:
        msg = MagicMock()
        msg.content = "Hello from LangGraph"
        messages = [msg]

    graph = MagicMock()
    graph.ainvoke = AsyncMock(return_value={"messages": messages})
    return graph


# ── Creation ────────────────────────────────────────────────────────────────

class TestLangGraphAdapterCreation:
    def test_creation_with_graph(self):
        graph = _make_mock_graph()
        adapter = FlintLangGraphAdapter(name="test-agent", graph=graph)
        assert adapter.name == "test-agent"
        assert adapter._graph is graph
        assert adapter._graph_builder is None

    def test_creation_with_graph_builder(self):
        builder = MagicMock(return_value=_make_mock_graph())
        adapter = FlintLangGraphAdapter(name="test-agent", graph_builder=builder)
        assert adapter._graph is None
        assert adapter._graph_builder is builder

    def test_creation_requires_graph_or_builder(self):
        with pytest.raises(ValueError, match="Either 'graph' or 'graph_builder'"):
            FlintLangGraphAdapter(name="test-agent")

    def test_creation_with_config(self):
        graph = _make_mock_graph()
        config = AdapterConfig(max_retries=5, human_approval=True)
        adapter = FlintLangGraphAdapter(name="test", graph=graph, config=config)
        assert adapter.config.max_retries == 5
        assert adapter.config.human_approval is True

    def test_creation_with_recursion_limit(self):
        graph = _make_mock_graph()
        adapter = FlintLangGraphAdapter(name="test", graph=graph, recursion_limit=50)
        assert adapter._recursion_limit == 50

    def test_default_recursion_limit(self):
        graph = _make_mock_graph()
        adapter = FlintLangGraphAdapter(name="test", graph=graph)
        assert adapter._recursion_limit == 25


# ── get_agent_name ──────────────────────────────────────────────────────────

class TestGetAgentName:
    def test_returns_correct_name(self):
        graph = _make_mock_graph()
        adapter = FlintLangGraphAdapter(name="my-langgraph-agent", graph=graph)
        assert adapter.get_agent_name() == "my-langgraph-agent"


# ── to_registered_agent ────────────────────────────────────────────────────

class TestToRegisteredAgent:
    def test_returns_correct_payload(self):
        graph = _make_mock_graph()
        adapter = FlintLangGraphAdapter(name="my-agent", graph=graph)
        reg = adapter.to_registered_agent()
        assert reg.name == "my-agent"
        assert reg.adapter_type == "FlintLangGraphAdapter"
        assert reg.inline is True

    def test_registration_payload(self):
        graph = _make_mock_graph()
        adapter = FlintLangGraphAdapter(name="my-agent", graph=graph)
        reg = adapter.to_registered_agent()
        payload = reg.to_registration_payload()
        assert payload == {"name": "my-agent"}


# ── run() ───────────────────────────────────────────────────────────────────

class TestRun:
    def test_run_with_content_attribute(self):
        """Test run() with a message object that has .content."""
        msg = MagicMock()
        msg.content = "Generated response"
        graph = _make_mock_graph(messages=[msg])

        adapter = FlintLangGraphAdapter(name="test", graph=graph)

        # Mock langgraph being installed
        mock_langgraph = MagicMock()
        with patch.dict(sys.modules, {"langgraph": mock_langgraph}):
            result = asyncio.run(adapter.run({"prompt": "Hello"}))

        assert result.success is True
        assert result.output == "Generated response"
        assert result.metadata["adapter"] == "FlintLangGraphAdapter"
        assert result.metadata["recursion_limit"] == 25
        assert result.metadata["message_count"] == 1

    def test_run_with_dict_message(self):
        """Test run() with a dict message containing 'content' key."""
        graph = _make_mock_graph(messages=[{"content": "Dict response", "role": "assistant"}])

        adapter = FlintLangGraphAdapter(name="test", graph=graph)

        mock_langgraph = MagicMock()
        with patch.dict(sys.modules, {"langgraph": mock_langgraph}):
            result = asyncio.run(adapter.run({"prompt": "Hello"}))

        assert result.success is True
        assert result.output == "Dict response"

    def test_run_with_multiple_messages(self):
        """Test that run() extracts the last message."""
        msg1 = MagicMock()
        msg1.content = "First message"
        msg2 = MagicMock()
        msg2.content = "Final answer"
        graph = _make_mock_graph(messages=[msg1, msg2])

        adapter = FlintLangGraphAdapter(name="test", graph=graph)

        mock_langgraph = MagicMock()
        with patch.dict(sys.modules, {"langgraph": mock_langgraph}):
            result = asyncio.run(adapter.run({"prompt": "Hello"}))

        assert result.output == "Final answer"
        assert result.metadata["message_count"] == 2

    def test_run_passes_correct_input(self):
        """Test that run() calls ainvoke with the right message format."""
        graph = _make_mock_graph()
        adapter = FlintLangGraphAdapter(name="test", graph=graph)

        mock_langgraph = MagicMock()
        with patch.dict(sys.modules, {"langgraph": mock_langgraph}):
            asyncio.run(adapter.run({"prompt": "Do something"}))

        graph.ainvoke.assert_called_once()
        call_args = graph.ainvoke.call_args
        assert call_args[0][0] == {"messages": [("user", "Do something")]}

    def test_run_passes_recursion_limit(self):
        """Test that recursion_limit is passed in config."""
        graph = _make_mock_graph()
        adapter = FlintLangGraphAdapter(name="test", graph=graph, recursion_limit=50)

        mock_langgraph = MagicMock()
        with patch.dict(sys.modules, {"langgraph": mock_langgraph}):
            asyncio.run(adapter.run({"prompt": "Hello"}))

        call_args = graph.ainvoke.call_args
        assert call_args[1]["config"]["recursion_limit"] == 50


# ── run() when langgraph not installed ──────────────────────────────────────

class TestRunWithoutLangGraph:
    def test_returns_error_when_not_installed(self):
        graph = _make_mock_graph()
        adapter = FlintLangGraphAdapter(name="test", graph=graph)

        # Simulate langgraph not being installed
        with patch.dict(sys.modules, {"langgraph": None}):
            result = asyncio.run(adapter.run({"prompt": "Hello"}))

        assert result.success is False
        assert "langgraph not installed" in result.error


# ── run() with graph_builder ────────────────────────────────────────────────

class TestRunWithGraphBuilder:
    def test_sync_graph_builder(self):
        """Test run() with a sync graph_builder callable."""
        msg = MagicMock()
        msg.content = "Built result"
        graph = _make_mock_graph(messages=[msg])
        builder = MagicMock(return_value=graph)

        adapter = FlintLangGraphAdapter(name="test", graph_builder=builder)

        mock_langgraph = MagicMock()
        with patch.dict(sys.modules, {"langgraph": mock_langgraph}):
            result = asyncio.run(adapter.run({"prompt": "Hello"}))

        builder.assert_called_once()
        assert result.success is True
        assert result.output == "Built result"

    def test_async_graph_builder(self):
        """Test run() with an async graph_builder callable."""
        msg = MagicMock()
        msg.content = "Async built result"
        graph = _make_mock_graph(messages=[msg])

        async def async_builder():
            return graph

        adapter = FlintLangGraphAdapter(name="test", graph_builder=async_builder)

        mock_langgraph = MagicMock()
        with patch.dict(sys.modules, {"langgraph": mock_langgraph}):
            result = asyncio.run(adapter.run({"prompt": "Hello"}))

        assert result.success is True
        assert result.output == "Async built result"

    def test_graph_builder_caches_result(self):
        """Test that graph_builder is only called once."""
        graph = _make_mock_graph()
        builder = MagicMock(return_value=graph)

        adapter = FlintLangGraphAdapter(name="test", graph_builder=builder)

        mock_langgraph = MagicMock()
        with patch.dict(sys.modules, {"langgraph": mock_langgraph}):
            asyncio.run(adapter.run({"prompt": "First"}))
            asyncio.run(adapter.run({"prompt": "Second"}))

        builder.assert_called_once()


# ── safe_run() error classification ────────────────────────────────────────

class TestSafeRunErrorClassification:
    def test_timeout_classified_as_retry(self):
        graph = MagicMock()
        graph.ainvoke = AsyncMock(side_effect=TimeoutError("timed out"))

        adapter = FlintLangGraphAdapter(name="test", graph=graph)

        mock_langgraph = MagicMock()
        with patch.dict(sys.modules, {"langgraph": mock_langgraph}):
            result = asyncio.run(adapter.safe_run({"prompt": "Hello"}))

        assert result.success is False
        assert result.metadata["error_action"] == "retry"
        assert result.metadata["error_type"] == "TimeoutError"

    def test_connection_error_classified_as_retry(self):
        graph = MagicMock()
        graph.ainvoke = AsyncMock(side_effect=ConnectionError("connection failed"))

        adapter = FlintLangGraphAdapter(name="test", graph=graph)

        mock_langgraph = MagicMock()
        with patch.dict(sys.modules, {"langgraph": mock_langgraph}):
            result = asyncio.run(adapter.safe_run({"prompt": "Hello"}))

        assert result.success is False
        assert result.metadata["error_action"] == "retry"

    def test_value_error_classified_as_fail(self):
        graph = MagicMock()
        graph.ainvoke = AsyncMock(side_effect=ValueError("bad input"))

        adapter = FlintLangGraphAdapter(name="test", graph=graph)

        mock_langgraph = MagicMock()
        with patch.dict(sys.modules, {"langgraph": mock_langgraph}):
            result = asyncio.run(adapter.safe_run({"prompt": "Hello"}))

        assert result.success is False
        assert result.metadata["error_action"] == "fail"

    def test_unknown_error_classified_as_dlq(self):
        graph = MagicMock()
        graph.ainvoke = AsyncMock(side_effect=RuntimeError("unexpected"))

        adapter = FlintLangGraphAdapter(name="test", graph=graph)

        mock_langgraph = MagicMock()
        with patch.dict(sys.modules, {"langgraph": mock_langgraph}):
            result = asyncio.run(adapter.safe_run({"prompt": "Hello"}))

        assert result.success is False
        assert result.metadata["error_action"] == "dlq"


# ── Workflow/Node integration ───────────────────────────────────────────────

from flint_ai import Workflow, Node


class TestWorkflowIntegration:
    def test_node_with_langgraph_adapter(self):
        graph = _make_mock_graph()
        adapter = FlintLangGraphAdapter(name="lg-agent", graph=graph)
        node = Node("process", agent=adapter, prompt="Analyze this")
        assert node._agent == "lg-agent"
        assert node._adapter is adapter

    def test_workflow_builds_with_langgraph_adapter(self):
        graph = _make_mock_graph()
        adapter = FlintLangGraphAdapter(name="lg-agent", graph=graph)
        wf = (Workflow("test-pipeline")
            .add(Node("process", agent=adapter, prompt="Analyze this"))
            .add(Node("report", agent="dummy", prompt="Report").depends_on("process"))
        )
        wf_def = wf.build()
        assert len(wf_def.nodes) == 2
        assert wf_def.nodes[0].agent_type == "lg-agent"
        assert wf_def.nodes[1].agent_type == "dummy"
        assert len(wf_def.edges) == 1

    def test_workflow_get_adapters_includes_langgraph(self):
        graph = _make_mock_graph()
        adapter = FlintLangGraphAdapter(name="lg-agent", graph=graph)
        wf = (Workflow("test")
            .add(Node("n1", agent=adapter, prompt="p1"))
            .add(Node("n2", agent="dummy", prompt="p2").depends_on("n1"))
        )
        adapters = wf.get_adapters()
        assert len(adapters) == 1
        assert isinstance(adapters[0], FlintLangGraphAdapter)
        assert adapters[0].name == "lg-agent"

    def test_adapter_config_flows_to_node(self):
        graph = _make_mock_graph()
        config = AdapterConfig(human_approval=True, max_retries=7)
        adapter = FlintLangGraphAdapter(name="lg-agent", graph=graph, config=config)
        node = Node("n1", agent=adapter, prompt="test")
        assert node._human_approval is True
        assert node._max_retries == 7


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
