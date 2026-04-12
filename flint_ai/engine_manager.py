"""Global engine management — start once, enqueue from anywhere.

This is the Hangfire pattern: configure at app startup, enqueue from
anywhere in your code without passing the engine around.

Usage::

    # ── App startup (e.g. main.py, app.py, FastAPI lifespan) ────
    from flint_ai import configure_engine, shutdown_engine
    from flint_ai.adapters.openai import FlintOpenAIAgent

    agent = FlintOpenAIAgent(name="summarizer", model="gpt-4o-mini")

    configure_engine(agents=[agent], port=5160, workers=4)

    # ── From ANYWHERE in your code ──────────────────────────────
    from flint_ai import Workflow, Node

    results = (
        Workflow("my-pipeline")
        .add(Node("summarize", agent=agent, prompt="..."))
        .run()  # ← Auto-discovers the global engine. No engine= needed.
    )

    # ── App shutdown ────────────────────────────────────────────
    shutdown_engine()
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger("flint.engine")

_lock = threading.Lock()
_engine: Any = None  # The FlintEngine instance
_started = False


def configure_engine(
    *,
    agents: list[Any] | None = None,
    port: int = 5160,
    workers: int = 4,
    poll_interval: float = 1.0,
    adapter_concurrency: int = 5,
    **kwargs: Any,
) -> Any:
    """Start the Flint engine as a global singleton.

    Call this once at app startup (e.g. in main.py or a FastAPI lifespan).
    After calling, any ``workflow.run()`` without ``server_url=`` or
    ``engine=`` will automatically reuse this engine.

    Args:
        agents: List of FlintAdapter instances to register.
        port: HTTP port for the embedded server (default 5160).
        workers: Number of background worker coroutines (default 4).
        poll_interval: Queue poll interval in seconds (default 1.0).
        adapter_concurrency: Default per-agent concurrency limit (default 5).
        **kwargs: Additional ServerConfig parameters.

    Returns:
        The FlintEngine instance.

    Raises:
        RuntimeError: If called more than once.
    """
    global _engine, _started

    with _lock:
        if _started:
            raise RuntimeError("configure_engine() was already called. Call it once at app startup.")

        from flint_ai.server import FlintEngine, ServerConfig
        from flint_ai.server.config import ConcurrencyConfig, WorkerConfig

        config = ServerConfig(
            port=port,
            worker=WorkerConfig(count=workers, poll_interval_ms=int(poll_interval * 1000)),
            concurrency=ConcurrencyConfig(default_limit=adapter_concurrency),
            **kwargs,
        )

        _engine = FlintEngine(config)

        # Register agents
        if agents:
            for agent in agents:
                _engine.register_adapter(agent)

        _engine.start()
        _started = True

        host = "localhost" if config.host == "0.0.0.0" else config.host
        logger.info(
            "Global Flint engine started at http://%s:%d (workers=%d, concurrency=%d)",
            host,
            port,
            workers,
            adapter_concurrency,
        )

        return _engine


def get_engine() -> Any | None:
    """Return the global FlintEngine if configured, else None."""
    with _lock:
        return _engine if _started else None


def shutdown_engine(timeout: float = 10.0) -> None:
    """Stop the global Flint engine.

    Call this at app shutdown (e.g. in FastAPI lifespan teardown).

    Args:
        timeout: Seconds to wait for graceful shutdown.
    """
    global _engine, _started

    with _lock:
        if not _started or _engine is None:
            return

        logger.info("Stopping global Flint engine...")
        _engine.stop()
        _engine = None
        _started = False
        logger.info("Global Flint engine stopped")


def wait_for_ready(timeout: float = 10.0) -> bool:
    """Wait until the global engine is ready.

    Useful in startup scripts to ensure the engine is listening before
    submitting workflows.

    Args:
        timeout: Maximum seconds to wait.

    Returns:
        True if the engine is ready, False if timed out.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with _lock:
            if _started and _engine is not None and _engine.is_running:
                return True
        time.sleep(0.1)
    return False
