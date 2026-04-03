"""Webhook agent — forwards tasks to an external HTTP endpoint."""

from __future__ import annotations

import logging
from typing import Any

from flint_ai.server.agents import BaseAgent
from flint_ai.server.engine import AgentResult

logger = logging.getLogger("flint.server.agents.webhook")


class WebhookAgent(BaseAgent):
    """Generic HTTP webhook agent.

    Sends a POST request to a configured URL with the task prompt.
    Supports Bearer token auth and configurable timeouts.
    """

    def __init__(
        self,
        name: str,
        url: str,
        auth_token: str | None = None,
        timeout_s: float = 60.0,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._name = name
        self._url = url
        self._auth_token = auth_token
        self._timeout = timeout_s
        self._extra_headers = headers or {}

    @property
    def agent_type(self) -> str:
        return self._name

    async def execute(self, task_id: str, prompt: str, **kwargs: Any) -> AgentResult:
        try:
            import httpx
        except ImportError:
            return AgentResult(
                task_id=task_id,
                success=False,
                error="httpx not installed",
            )

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            **self._extra_headers,
        }
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        payload = {
            "task_id": task_id,
            "prompt": prompt,
            **{k: v for k, v in kwargs.items() if isinstance(v, (str, int, float, bool))},
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(self._url, json=payload, headers=headers)

                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After", "5")
                    return AgentResult(
                        task_id=task_id,
                        success=False,
                        error=f"Rate limited, retry after {retry_after}s",
                        metadata={"retry_after": float(retry_after), "should_retry": True},
                    )

                resp.raise_for_status()
                body = resp.text
                return AgentResult(
                    task_id=task_id,
                    success=True,
                    output=body,
                    metadata={"status_code": resp.status_code},
                )

        except httpx.TimeoutException as e:
            return AgentResult(
                task_id=task_id,
                success=False,
                error=f"Webhook timeout after {self._timeout}s: {e}",
                metadata={"should_retry": True},
            )
        except httpx.HTTPStatusError as e:
            return AgentResult(
                task_id=task_id,
                success=False,
                error=f"Webhook HTTP error {e.response.status_code}: {e}",
            )
        except Exception as e:
            return AgentResult(
                task_id=task_id,
                success=False,
                error=f"Webhook error: {e}",
            )
