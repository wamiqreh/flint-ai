"""AutoGen integration adapter for Flint.

Provides ``OrchestratorAgent`` – a class compatible with AutoGen
multi-agent conversations that delegates generation to the orchestrator.

Usage::

    from flint_ai.autogen_adapter import OrchestratorAgent

    agent = OrchestratorAgent(
        name="orchestrator",
        base_url="http://localhost:5156",
        agent_type="claude",
    )
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Union

from .client import AsyncOrchestratorClient, OrchestratorClient

try:
    from autogen import ConversableAgent  # pyautogen

    _AUTOGEN_AVAILABLE = True
except ImportError:  # pragma: no cover
    _AUTOGEN_AVAILABLE = False
    ConversableAgent = None  # type: ignore[assignment,misc]


def _extract_last_message(messages: Union[str, List[Dict[str, Any]], Dict[str, Any]]) -> str:
    """Extract the text content from the last message in AutoGen format."""
    if isinstance(messages, str):
        return messages
    if isinstance(messages, dict):
        return str(messages.get("content", ""))
    if isinstance(messages, list) and messages:
        last = messages[-1]
        if isinstance(last, dict):
            return str(last.get("content", ""))
        return str(last)
    return ""


class OrchestratorAgent:
    """An AutoGen-compatible agent backed by Flint.

    This agent can participate in AutoGen group chats and two-agent
    conversations.  When asked to generate a reply it submits the last
    incoming message to the orchestrator queue and returns the result.

    Parameters
    ----------
    name:
        Agent name used in AutoGen conversations.
    base_url:
        Root URL of the orchestrator API.
    agent_type:
        Agent backend to use (e.g. ``"openai"``, ``"claude"``).
    system_message:
        System prompt prepended to every task submission.
    timeout:
        Maximum seconds to wait for a task result. ``None`` waits
        indefinitely.
    poll_interval:
        Seconds between status polls while waiting.
    workflow_id:
        Optional workflow to associate with submitted tasks.
    """

    def __init__(
        self,
        name: str = "orchestrator",
        *,
        base_url: str = "http://localhost:5156",
        agent_type: str = "openai",
        system_message: str = "",
        timeout: Optional[float] = 300.0,
        poll_interval: float = 1.0,
        workflow_id: Optional[str] = None,
    ) -> None:
        if not _AUTOGEN_AVAILABLE:
            raise ImportError(
                "pyautogen is required for OrchestratorAgent. "
                "Install it with: pip install 'flint-ai[autogen]'"
            )

        self.name = name
        self.base_url = base_url
        self.agent_type = agent_type
        self.system_message = system_message
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.workflow_id = workflow_id

        # Create a ConversableAgent and register our reply function.
        self._agent = ConversableAgent(
            name=name,
            system_message=system_message,
            llm_config=False,  # We do not use a local LLM
            human_input_mode="NEVER",
        )
        self._agent.register_reply(
            trigger=[ConversableAgent, None],
            reply_func=self._generate_reply_func,
        )

    # -- AutoGen reply function ----------------------------------------------

    def _generate_reply_func(
        self,
        recipient: Any,
        messages: Optional[List[Dict[str, Any]]] = None,
        sender: Any = None,
        config: Any = None,
    ) -> tuple[bool, str]:
        """AutoGen reply function: submit to orchestrator and return result."""
        prompt = _extract_last_message(messages or [])
        if self.system_message:
            prompt = f"{self.system_message}\n\n{prompt}"

        reply = self._submit_sync(prompt)
        return True, reply

    # -- public helpers ------------------------------------------------------

    def generate_reply(
        self,
        messages: Union[str, List[Dict[str, Any]], Dict[str, Any]],
    ) -> str:
        """Submit the last message to the orchestrator and return the result.

        This is a convenience method for use outside of AutoGen's built-in
        conversation loop.
        """
        prompt = _extract_last_message(messages)
        if self.system_message:
            prompt = f"{self.system_message}\n\n{prompt}"
        return self._submit_sync(prompt)

    async def a_generate_reply(
        self,
        messages: Union[str, List[Dict[str, Any]], Dict[str, Any]],
    ) -> str:
        """Async variant of :meth:`generate_reply`."""
        prompt = _extract_last_message(messages)
        if self.system_message:
            prompt = f"{self.system_message}\n\n{prompt}"
        return await self._submit_async(prompt)

    # -- underlying AutoGen agent access -------------------------------------

    @property
    def agent(self) -> Any:
        """Return the wrapped ``ConversableAgent`` for use in AutoGen chats."""
        return self._agent

    # -- internal ------------------------------------------------------------

    def _submit_sync(self, prompt: str) -> str:
        client = OrchestratorClient(base_url=self.base_url)
        with client:
            task_id = client.submit_task(
                self.agent_type, prompt, workflow_id=self.workflow_id,
            )
            result = client.wait_for_task(task_id, poll_interval_seconds=self.poll_interval)

        if result.state == "Succeeded":
            return result.result or ""
        return f"[Task {result.state}] {result.result or 'No output'}"

    async def _submit_async(self, prompt: str) -> str:
        async with AsyncOrchestratorClient(base_url=self.base_url) as client:
            task_id = await client.submit_task(
                self.agent_type, prompt, workflow_id=self.workflow_id,
            )

            if self.timeout is not None:
                result = await asyncio.wait_for(
                    client.wait_for_task(task_id, poll_interval_seconds=self.poll_interval),
                    timeout=self.timeout,
                )
            else:
                result = await client.wait_for_task(
                    task_id, poll_interval_seconds=self.poll_interval,
                )

        if result.state == "Succeeded":
            return result.result or ""
        return f"[Task {result.state}] {result.result or 'No output'}"
