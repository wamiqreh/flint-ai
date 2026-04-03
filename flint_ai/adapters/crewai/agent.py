"""Flint CrewAI Adapter — run CrewAI crews as Flint agents.

Wraps a CrewAI Crew so it can run as a Flint task inside
the queue/DAG/retry/approval infrastructure.

Usage:
    from flint_ai.adapters.crewai import FlintCrewAIAdapter

    adapter = FlintCrewAIAdapter(
        name="research_crew",
        agents=[researcher, writer],
        tasks=[research_task, write_task],
        process=Process.sequential,
    )

    wf = (Workflow("research")
        .add(Node("run", agent=adapter, prompt="Research AI trends"))
        .build())
"""

from __future__ import annotations

import logging
from typing import Any

from ..core.base import FlintAdapter
from ..core.types import AdapterConfig, AgentRunResult, ErrorMapping

logger = logging.getLogger("flint.adapters.crewai")


class FlintCrewAIAdapter(FlintAdapter):
    """Wrap a CrewAI Crew as a Flint agent.

    Args:
        name: Agent name for Flint registration.
        agents: List of CrewAI Agent objects.
        tasks: List of CrewAI Task objects.
        process: CrewAI Process type (sequential or hierarchical).
        verbose: Enable verbose output from CrewAI.
        memory: Enable CrewAI memory.
        config: Flint adapter config override.
    """

    def __init__(
        self,
        *,
        name: str,
        agents: list | None = None,
        tasks: list | None = None,
        process: Any = None,
        verbose: bool = False,
        memory: bool = False,
        config: AdapterConfig | None = None,
    ):
        error_mapping = ErrorMapping(
            retry_on=[TimeoutError, ConnectionError],
            fail_on=[ValueError],
        )
        super().__init__(name=name, config=config, error_mapping=error_mapping)
        self._agents = agents or []
        self._tasks = tasks or []
        self._process = process
        self._verbose = verbose
        self._memory = memory

    async def run(self, input_data: dict[str, Any]) -> AgentRunResult:
        """Execute the CrewAI crew."""
        prompt = input_data.get("prompt", "")

        try:
            from crewai import Crew, Process
        except ImportError:
            return AgentRunResult(
                output="",
                success=False,
                error="crewai package not installed. Run: pip install flint-ai[crewai]",
            )

        if not self._agents or not self._tasks:
            return AgentRunResult(
                output="",
                success=False,
                error="CrewAI adapter requires at least one agent and one task.",
            )

        process = self._process or Process.sequential

        # Inject the Flint prompt into the first task's description
        tasks_copy = list(self._tasks)
        if tasks_copy and prompt:
            first_task = tasks_copy[0]
            if hasattr(first_task, 'description'):
                original_desc = first_task.description or ""
                first_task.description = f"{original_desc}\n\nContext: {prompt}"

        crew = Crew(
            agents=self._agents,
            tasks=tasks_copy,
            process=process,
            verbose=self._verbose,
            memory=self._memory,
        )

        result = crew.kickoff()

        # CrewAI returns a CrewOutput object or string
        output = str(result)
        if hasattr(result, 'raw'):
            output = result.raw

        return AgentRunResult(
            output=output,
            metadata={
                "adapter": "FlintCrewAIAdapter",
                "agent_count": len(self._agents),
                "task_count": len(self._tasks),
                "process": str(process),
            },
        )

    def to_registered_agent(self):
        from ..core.types import RegisteredAgent
        return RegisteredAgent(
            name=self._name,
            inline=self._config.inline,
            adapter_type="FlintCrewAIAdapter",
        )
