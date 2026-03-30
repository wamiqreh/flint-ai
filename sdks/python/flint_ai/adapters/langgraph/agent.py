"""Flint LangGraph Adapter — run LangGraph graphs as Flint agents.

Wraps a compiled LangGraph graph so it can run as a Flint task inside
the queue/DAG/retry/approval infrastructure.

Usage:
    from langgraph.graph import StateGraph, MessagesState, START, END
    from flint_ai.adapters.langgraph import FlintLangGraphAdapter

    # Build your LangGraph graph
    graph_builder = StateGraph(MessagesState)
    graph_builder.add_node("agent", call_model)
    graph_builder.add_edge(START, "agent")
    graph_builder.add_edge("agent", END)
    graph = graph_builder.compile()

    # Wrap it as a Flint adapter
    adapter = FlintLangGraphAdapter(name="my-agent", graph=graph)

    # Or defer graph construction with a builder function
    async def build_graph():
        graph_builder = StateGraph(MessagesState)
        graph_builder.add_node("agent", call_model)
        graph_builder.add_edge(START, "agent")
        graph_builder.add_edge("agent", END)
        return graph_builder.compile()

    adapter = FlintLangGraphAdapter(name="my-agent", graph_builder=build_graph)
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Callable, Optional

from ..core.base import FlintAdapter
from ..core.types import AdapterConfig, AgentRunResult, ErrorMapping

logger = logging.getLogger("flint.adapters.langgraph")


class FlintLangGraphAdapter(FlintAdapter):
    """Wrap a compiled LangGraph graph as a Flint agent.

    Args:
        name: Agent name for Flint registration.
        graph: A compiled LangGraph graph object. Either ``graph`` or
            ``graph_builder`` must be provided.
        graph_builder: A callable (sync or async) that returns a compiled
            graph. Useful for deferring graph construction until first run.
        config: Flint adapter config override.
        checkpointer: Optional LangGraph checkpointer for persistence.
        recursion_limit: Maximum recursion depth for the graph invocation.
    """

    def __init__(
        self,
        *,
        name: str,
        graph: Any = None,
        graph_builder: Optional[Callable[..., Any]] = None,
        config: Optional[AdapterConfig] = None,
        checkpointer: Any = None,
        recursion_limit: int = 25,
    ):
        if graph is None and graph_builder is None:
            raise ValueError("Either 'graph' or 'graph_builder' must be provided.")

        error_mapping = ErrorMapping(
            retry_on=[TimeoutError, ConnectionError],
            fail_on=[ValueError],
        )
        super().__init__(name=name, config=config, error_mapping=error_mapping)
        self._graph = graph
        self._graph_builder = graph_builder
        self._checkpointer = checkpointer
        self._recursion_limit = recursion_limit

    async def _resolve_graph(self) -> Any:
        """Resolve the graph, calling graph_builder if needed."""
        if self._graph is not None:
            return self._graph

        if self._graph_builder is not None:
            if inspect.iscoroutinefunction(self._graph_builder):
                self._graph = await self._graph_builder()
            else:
                self._graph = self._graph_builder()
            return self._graph

        raise ValueError("No graph or graph_builder available.")

    async def run(self, input_data: dict[str, Any]) -> AgentRunResult:
        """Execute the LangGraph graph."""
        prompt = input_data.get("prompt", "")

        # Lazy-import to avoid hard dependency
        try:
            import langgraph  # noqa: F401
        except ImportError:
            return AgentRunResult(
                output="",
                success=False,
                error="langgraph not installed. Run: pip install flint-ai[langgraph]",
            )

        graph = await self._resolve_graph()

        invoke_config: dict[str, Any] = {}
        if self._recursion_limit:
            invoke_config["recursion_limit"] = self._recursion_limit
        if self._checkpointer:
            invoke_config["configurable"] = {"thread_id": input_data.get("task_id", "default")}

        result = await graph.ainvoke(
            {"messages": [("user", prompt)]},
            config=invoke_config,
        )

        # Extract output from result
        output = ""
        message_count = 0
        if isinstance(result, dict) and "messages" in result:
            messages = result["messages"]
            message_count = len(messages)
            if messages:
                last_msg = messages[-1]
                if isinstance(last_msg, dict):
                    output = last_msg.get("content", str(last_msg))
                elif hasattr(last_msg, "content"):
                    output = last_msg.content
                else:
                    output = str(last_msg)
        else:
            output = str(result)

        return AgentRunResult(
            output=output,
            metadata={
                "adapter": "FlintLangGraphAdapter",
                "recursion_limit": self._recursion_limit,
                "message_count": message_count,
            },
        )

    def to_registered_agent(self):
        from ..core.types import RegisteredAgent
        return RegisteredAgent(
            name=self._name,
            inline=self._config.inline,
            adapter_type="FlintLangGraphAdapter",
        )
