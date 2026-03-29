"""Google Gemini agent adapter for Flint.

Implements the IAgent interface pattern. Install the plugin with:
    flint plugins install agent-gemini

Requires:
    pip install google-generativeai
    export GOOGLE_API_KEY=your-api-key
"""

from __future__ import annotations

import asyncio
import os
from functools import partial
from typing import Any


class AgentExecutionError(Exception):
    """Raised when the agent fails to produce a result."""


class Agent:
    """Google Gemini agent adapter.

    Implements the AQO IAgent interface:
        - agent_type (property) -> str
        - execute(prompt, **kwargs) -> str
        - aexecute(prompt, **kwargs) -> str  (optional async variant)
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self.api_key: str = cfg.get(
            "GOOGLE_API_KEY", os.environ.get("GOOGLE_API_KEY", "")
        )
        self.model_name: str = cfg.get("GEMINI_MODEL", "gemini-pro")

        if not self.api_key:
            raise AgentExecutionError(
                "GOOGLE_API_KEY is required. Set it as an environment variable "
                "or pass it in the config dict."
            )

    @property
    def agent_type(self) -> str:
        """Unique identifier for this agent."""
        return "gemini"

    def execute(self, prompt: str, **kwargs: Any) -> str:
        """Execute a prompt synchronously and return the result.

        Args:
            prompt: The user prompt / task description.
            **kwargs: Optional context (task_id, workflow_id, metadata).

        Returns:
            The model's response as a string.

        Raises:
            AgentExecutionError: If the API call fails.
        """
        try:
            import google.generativeai as genai  # type: ignore[import-untyped]
        except ImportError as exc:
            raise AgentExecutionError(
                "google-generativeai package is required. "
                "Install with: pip install google-generativeai"
            ) from exc

        try:
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model_name)
            response = model.generate_content(prompt)
            return response.text
        except Exception as exc:
            raise AgentExecutionError(
                f"Gemini API call failed: {exc}"
            ) from exc

    async def aexecute(self, prompt: str, **kwargs: Any) -> str:
        """Execute a prompt asynchronously.

        Runs the synchronous execute() in a thread pool to avoid
        blocking the event loop.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, partial(self.execute, prompt, **kwargs)
        )
