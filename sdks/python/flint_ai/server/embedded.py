"""Embedded engine — run the full Flint server within your application.

Usage::

    from flint_ai.server import FlintEngine, ServerConfig
    from flint_ai.adapters.openai import FlintOpenAIAgent

    engine = FlintEngine(ServerConfig(port=5156))
    engine.register_adapter(FlintOpenAIAgent(name="reviewer", model="gpt-4o-mini", ...))
    engine.start()  # Non-blocking: starts API + workers in background

    # Your application code continues...
    # Submit tasks via the SDK client pointing at localhost:5156

    engine.stop()  # Graceful shutdown
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, List, Optional

from flint_ai.server.config import ServerConfig

logger = logging.getLogger("flint.server.embedded")


class FlintEngine:
    """Embedded Flint server that runs within your Python process.

    Two operation modes:
    1. Background thread (default): Starts event loop in a daemon thread.
       Non-blocking — your main thread continues.
    2. Foreground: Blocks the calling thread (use for standalone server).

    The engine starts:
    - FastAPI HTTP server (for API endpoints)
    - Worker pool (for task processing)
    - Scheduler (for recurring workflows)
    """

    def __init__(self, config: Optional[ServerConfig] = None) -> None:
        self._config = config or ServerConfig()
        self._adapters: List[Any] = []
        self._webhook_agents: List[dict] = []
        self._app: Any = None
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._server: Any = None
        self._running = False

    def register_adapter(self, adapter: Any) -> "FlintEngine":
        """Register a FlintAdapter (OpenAI, LangChain, CrewAI, etc.) as a server-side agent.

        The adapter will be wrapped and registered in the agent registry
        so the server can execute tasks using it.
        """
        self._adapters.append(adapter)
        return self

    def register_webhook(
        self,
        agent_type: str,
        url: str,
        auth_token: Optional[str] = None,
        timeout_s: float = 60.0,
    ) -> "FlintEngine":
        """Register a webhook agent."""
        self._webhook_agents.append({
            "agent_type": agent_type,
            "url": url,
            "auth_token": auth_token,
            "timeout_s": timeout_s,
        })
        return self

    def start(self, blocking: bool = False) -> "FlintEngine":
        """Start the embedded server.

        Args:
            blocking: If True, blocks the calling thread (foreground mode).
                      If False (default), starts in a background daemon thread.
        """
        if self._running:
            logger.warning("Engine already running")
            return self

        if blocking:
            self._run_blocking()
        else:
            self._thread = threading.Thread(target=self._run_blocking, daemon=True)
            self._thread.start()
            # Wait for server to be ready
            import time
            for _ in range(50):
                if self._running:
                    break
                time.sleep(0.1)
            if self._running:
                logger.info(
                    "Flint engine started (background) at http://%s:%d",
                    self._config.host, self._config.port,
                )
            else:
                logger.error("Engine failed to start within 5 seconds")

        return self

    def stop(self) -> None:
        """Stop the embedded server."""
        if not self._running:
            return

        self._running = False
        if self._server:
            self._server.should_exit = True

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)

        logger.info("Flint engine stopped")

    def _run_blocking(self) -> None:
        """Run the server (blocking)."""
        try:
            import uvicorn
        except ImportError:
            raise ImportError(
                "uvicorn required for embedded server. "
                "Install with: pip install flint-ai[server]"
            )

        from flint_ai.server.app import create_app

        self._app = create_app(self._config)
        self._register_adapters_on_startup()

        config = uvicorn.Config(
            self._app,
            host=self._config.host,
            port=self._config.port,
            log_level=self._config.log_level.lower(),
        )
        self._server = uvicorn.Server(config)
        self._running = True

        # Run the server
        self._server.run()

    def _register_adapters_on_startup(self) -> None:
        """Hook to register adapters after the app's lifespan creates the registry."""
        original_lifespan = self._app.router.lifespan_context

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def wrapped_lifespan(app: Any):
            async with original_lifespan(app):
                # Register SDK adapters as server agents
                for adapter in self._adapters:
                    wrapped = _AdapterAgent(adapter)
                    app.state.agent_registry.register(wrapped)
                    logger.info("Registered SDK adapter: %s", wrapped.agent_type)

                # Register webhook agents
                for wh in self._webhook_agents:
                    from flint_ai.server.agents.webhook import WebhookAgent
                    agent = WebhookAgent(
                        name=wh["agent_type"],
                        url=wh["url"],
                        auth_token=wh.get("auth_token"),
                        timeout_s=wh.get("timeout_s", 60.0),
                    )
                    app.state.agent_registry.register(agent)

                yield

        self._app.router.lifespan_context = wrapped_lifespan

    @property
    def url(self) -> str:
        return f"http://{self._config.host}:{self._config.port}"

    @property
    def is_running(self) -> bool:
        return self._running


class _AdapterAgent:
    """Wraps a FlintAdapter (from the SDK) as a server-side BaseAgent."""

    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter

    @property
    def agent_type(self) -> str:
        if hasattr(self._adapter, 'get_agent_name'):
            return self._adapter.get_agent_name()
        if hasattr(self._adapter, 'name'):
            return self._adapter.name
        return str(type(self._adapter).__name__).lower()

    async def execute(self, task_id: str, prompt: str, **kwargs: Any) -> Any:
        from flint_ai.server.engine import AgentResult

        try:
            if hasattr(self._adapter, 'safe_run'):
                result = await self._adapter.safe_run({"prompt": prompt, **kwargs})
            elif hasattr(self._adapter, 'run'):
                result = await self._adapter.run({"prompt": prompt, **kwargs})
            else:
                return AgentResult(
                    task_id=task_id,
                    success=False,
                    error=f"Adapter {self.agent_type} has no run method",
                )

            return AgentResult(
                task_id=task_id,
                success=result.success if hasattr(result, 'success') else True,
                output=result.output if hasattr(result, 'output') else str(result),
                metadata=result.metadata if hasattr(result, 'metadata') else {},
            )
        except Exception as e:
            return AgentResult(
                task_id=task_id,
                success=False,
                error=str(e),
            )

    async def health_check(self) -> bool:
        return True
