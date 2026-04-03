"""Integration tests — mock OpenAI + full adapter -> workflow -> deploy flow."""

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from flint_ai.adapters.core.types import AdapterConfig, AgentRunResult
from flint_ai.adapters.core.registry import register_inline, get_inline_adapter, list_inline_adapters, _inline_registry
from flint_ai.adapters.openai.agent import FlintOpenAIAgent
from flint_ai.adapters.openai.tools import tool, get_tool_schemas, execute_tool_call
from flint_ai.workflow_builder import Workflow, Node


# -- Fixtures --


@tool
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return f"Sunny, 22C in {city}"


@tool
def calculate(expression: str) -> str:
    """Evaluate a math expression."""
    return str(eval(expression))


class FakeChoice:
    def __init__(self, content=None, tool_calls=None, finish_reason="stop"):
        self.message = MagicMock()
        self.message.content = content
        self.message.tool_calls = tool_calls
        self.finish_reason = finish_reason


class FakeCompletion:
    def __init__(self, choices):
        self.choices = choices
        self.usage = None


# -- OpenAI Agent with Mocked API --


class TestOpenAIAgentMocked:
    """Test FlintOpenAIAgent with mocked openai.AsyncOpenAI."""

    @pytest.fixture(autouse=True)
    def clear_registry(self):
        _inline_registry.clear()
        yield
        _inline_registry.clear()

    @pytest.mark.asyncio
    async def test_simple_completion(self):
        """Agent gets a simple text response (no tools)."""
        agent = FlintOpenAIAgent(
            name="test-agent",
            model="gpt-4o",
            instructions="You are helpful.",
            api_key="sk-fake-key",
        )

        fake_resp = FakeCompletion([FakeChoice(content="The weather is sunny!")])
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_resp)
        mock_openai = MagicMock()
        mock_openai.AsyncOpenAI = MagicMock(return_value=mock_client)

        with patch.dict(sys.modules, {"openai": mock_openai}):
            result = await agent.run({"prompt": "What is the weather?"})

        assert result.success is True
        assert "sunny" in result.output.lower()

    @pytest.mark.asyncio
    async def test_tool_calling_flow(self):
        """Agent uses a tool, gets tool result, then responds."""
        agent = FlintOpenAIAgent(
            name="tool-agent",
            model="gpt-4o",
            instructions="Use tools when asked.",
            tools=[get_weather],
            api_key="sk-fake-key",
        )

        tc = MagicMock()
        tc.id = "call_123"
        tc.type = "function"
        tc.function.name = "get_weather"
        tc.function.arguments = json.dumps({"city": "London"})

        first_resp = FakeCompletion([FakeChoice(tool_calls=[tc], finish_reason="tool_calls")])
        second_resp = FakeCompletion([FakeChoice(content="It is sunny, 22C in London.")])

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=[first_resp, second_resp])
        mock_openai = MagicMock()
        mock_openai.AsyncOpenAI = MagicMock(return_value=mock_client)

        with patch.dict(sys.modules, {"openai": mock_openai}):
            result = await agent.run({"prompt": "Weather in London?"})

        assert result.success is True
        assert "London" in result.output

    @pytest.mark.asyncio
    async def test_multiple_tool_rounds(self):
        """Agent calls tools multiple times before final answer."""
        agent = FlintOpenAIAgent(
            name="multi-tool",
            model="gpt-4o",
            instructions="Use tools.",
            tools=[get_weather, calculate],
            api_key="sk-fake-key",
            max_tool_rounds=5,
        )

        tc1 = MagicMock()
        tc1.id = "c1"
        tc1.type = "function"
        tc1.function.name = "get_weather"
        tc1.function.arguments = json.dumps({"city": "Paris"})

        tc2 = MagicMock()
        tc2.id = "c2"
        tc2.type = "function"
        tc2.function.name = "calculate"
        tc2.function.arguments = json.dumps({"expression": "22 * 9/5 + 32"})

        resp1 = FakeCompletion([FakeChoice(tool_calls=[tc1], finish_reason="tool_calls")])
        resp2 = FakeCompletion([FakeChoice(tool_calls=[tc2], finish_reason="tool_calls")])
        resp3 = FakeCompletion([FakeChoice(content="Paris: 22C (71.6F)")])

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=[resp1, resp2, resp3])
        mock_openai = MagicMock()
        mock_openai.AsyncOpenAI = MagicMock(return_value=mock_client)

        with patch.dict(sys.modules, {"openai": mock_openai}):
            result = await agent.run({"prompt": "Paris temp in F?"})

        assert result.success is True
        assert "71.6" in result.output

    @pytest.mark.asyncio
    async def test_api_error_classified(self):
        """OpenAI API errors should be caught and reported."""
        agent = FlintOpenAIAgent(
            name="err-agent",
            model="gpt-4o",
            instructions="test",
            api_key="sk-fake-key",
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("Connection timeout"))
        mock_openai = MagicMock()
        mock_openai.AsyncOpenAI = MagicMock(return_value=mock_client)

        with patch.dict(sys.modules, {"openai": mock_openai}):
            result = await agent.safe_run({"prompt": "test"})

        assert result.success is False
        assert "Connection timeout" in result.error


# -- Full Workflow Integration --


class TestWorkflowIntegration:
    """Test building and deploying a workflow with adapters."""

    @pytest.fixture(autouse=True)
    def clear_registry(self):
        _inline_registry.clear()
        yield
        _inline_registry.clear()

    def test_multi_agent_workflow_build(self):
        """Build a workflow with multiple adapter agents and verify output."""
        researcher = FlintOpenAIAgent(
            name="researcher",
            model="gpt-4o",
            instructions="You research topics.",
            api_key="sk-fake",
        )
        writer = FlintOpenAIAgent(
            name="writer",
            model="gpt-4o",
            instructions="You write articles.",
            api_key="sk-fake",
        )

        wf = (
            Workflow("research-pipeline")
            .add(Node("research", agent=researcher, prompt="Research topic"))
            .add(Node("write", agent=writer, prompt="Write article").depends_on("research"))
        )

        defn = wf.build()
        payload = defn.model_dump(by_alias=True)

        assert payload["Id"] == "research-pipeline"
        assert len(payload["Nodes"]) == 2
        assert payload["Nodes"][0]["AgentType"] == "researcher"
        assert payload["Nodes"][1]["AgentType"] == "writer"
        assert len(payload["Edges"]) == 1

    def test_get_adapters_returns_all(self):
        """get_adapters() returns adapter objects for adapter-based nodes."""
        a1 = FlintOpenAIAgent(name="a1", model="gpt-4o", instructions="t", api_key="k")
        a2 = FlintOpenAIAgent(name="a2", model="gpt-4o", instructions="t", api_key="k")

        wf = (
            Workflow("test-wf")
            .add(Node("n1", agent=a1, prompt="p1"))
            .add(Node("n2", agent="dummy", prompt="p2"))
            .add(Node("n3", agent=a2, prompt="p3"))
        )

        adapters = wf.get_adapters()
        assert len(adapters) == 2
        names = {a.get_agent_name() for a in adapters}
        assert names == {"a1", "a2"}

    def test_mixed_agents_workflow(self):
        """Workflow with both adapter and string agents builds correctly."""
        agent = FlintOpenAIAgent(name="smart", model="gpt-4o", instructions="t", api_key="k")

        wf = (
            Workflow("mixed")
            .add(Node("step1", agent="dummy", prompt="init"))
            .add(Node("step2", agent=agent, prompt="process").depends_on("step1"))
            .add(Node("step3", agent="dummy", prompt="finish").depends_on("step2"))
        )

        defn = wf.build()
        payload = defn.model_dump(by_alias=True)
        agents = [n["AgentType"] for n in payload["Nodes"]]
        assert agents == ["dummy", "smart", "dummy"]

    def test_workflow_with_human_approval(self):
        """Nodes with human_approval flag are included in build."""
        agent = FlintOpenAIAgent(name="reviewer", model="gpt-4o", instructions="t", api_key="k")

        wf = (
            Workflow("approval-flow")
            .add(Node("auto", agent="dummy", prompt="auto task"))
            .add(Node("review", agent=agent, prompt="review this").requires_approval().depends_on("auto"))
        )

        defn = wf.build()
        payload = defn.model_dump(by_alias=True)
        review_node = [n for n in payload["Nodes"] if n["Id"] == "review"][0]
        assert review_node.get("HumanApproval") is True


# -- Tool Schema Integration --


class TestToolSchemaIntegration:
    """Test that tool schemas integrate correctly with agent creation."""

    def test_schemas_match_openai_format(self):
        schemas = get_tool_schemas([get_weather, calculate])

        assert len(schemas) == 2
        weather_schema = schemas[0]
        assert weather_schema["type"] == "function"
        assert weather_schema["function"]["name"] == "get_weather"
        assert "city" in weather_schema["function"]["parameters"]["properties"]
        assert "city" in weather_schema["function"]["parameters"]["required"]

        calc_schema = schemas[1]
        assert calc_schema["function"]["name"] == "calculate"
        assert "expression" in calc_schema["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_tool_execution_in_context(self):
        result = await execute_tool_call([get_weather], "get_weather", {"city": "Tokyo"})
        assert "Tokyo" in result

        result = await execute_tool_call([calculate], "calculate", {"expression": "2 + 3"})
        assert result == "5"

    @pytest.mark.asyncio
    async def test_tool_not_found_returns_error(self):
        result = await execute_tool_call([get_weather], "nonexistent", {})
        assert "tool_not_found" in result


# -- Registry + Worker Integration --


class TestRegistryWorkerIntegration:
    """Test adapter registration and inline worker routing."""

    @pytest.fixture(autouse=True)
    def clear_registry(self):
        _inline_registry.clear()
        yield
        _inline_registry.clear()

    def test_register_openai_agent(self):
        agent = FlintOpenAIAgent(name="my-agent", model="gpt-4o", instructions="t", api_key="k")
        register_inline(agent)

        retrieved = get_inline_adapter("my-agent")
        assert retrieved is agent
        assert "my-agent" in list_inline_adapters()

    def test_multiple_agents_registered(self):
        a1 = FlintOpenAIAgent(name="agent-1", model="gpt-4o", instructions="t", api_key="k")
        a2 = FlintOpenAIAgent(name="agent-2", model="gpt-4o-mini", instructions="t2", api_key="k")
        register_inline(a1)
        register_inline(a2)

        assert get_inline_adapter("agent-1") is a1
        assert get_inline_adapter("agent-2") is a2
        assert set(list_inline_adapters()) == {"agent-1", "agent-2"}

    @pytest.mark.asyncio
    async def test_inline_worker_routes_to_adapter(self):
        from flint_ai.adapters.core.worker import InlineWorker

        agent = FlintOpenAIAgent(name="routed-agent", model="gpt-4o", instructions="t", api_key="k")
        register_inline(agent)

        worker = InlineWorker()
        agent.run = AsyncMock(return_value=AgentRunResult(success=True, output="routed!"))

        result = await worker.handle_execute("routed-agent", {"prompt": "test"})
        assert result["success"] is True
        assert result["output"] == "routed!"
