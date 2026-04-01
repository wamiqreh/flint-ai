"""Flint Python Server — Production-grade queue orchestration engine.

Two deployment modes:
    1. Standalone: `flint server start` or `python -m flint_ai.server`
    2. Embedded:   `FlintEngine(config).start()` within your application

Example (Embedded)::

    from flint_ai.server import FlintEngine, ServerConfig

    engine = FlintEngine(ServerConfig(redis_url="redis://localhost:6379"))
    engine.register_adapter(my_openai_adapter)
    engine.start()  # starts API + workers in background

Example (Standalone)::

    $ flint server start --host 0.0.0.0 --port 5156 --redis redis://localhost
"""

from flint_ai.server.config import ServerConfig
from flint_ai.server.embedded import FlintEngine

__all__ = ["ServerConfig", "FlintEngine"]
