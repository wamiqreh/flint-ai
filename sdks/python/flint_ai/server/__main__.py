"""Entry point for running the Flint server standalone.

Usage:
    python -m flint_ai.server
    python -m flint_ai.server --host 0.0.0.0 --port 5156 --redis redis://localhost
"""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Flint Python Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=5156, help="Bind port")
    parser.add_argument("--redis", default=None, help="Redis URL (enables Redis queue)")
    parser.add_argument("--postgres", default=None, help="PostgreSQL URL (enables Postgres store)")
    parser.add_argument("--workers", type=int, default=4, help="Number of worker coroutines")
    parser.add_argument("--log-level", default="INFO", help="Log level")
    args = parser.parse_args()

    from flint_ai.server.config import QueueBackend, ServerConfig, StoreBackend

    config = ServerConfig(
        host=args.host,
        port=args.port,
        worker={"count": args.workers},
        log_level=args.log_level,
    )

    if args.redis:
        config.queue_backend = QueueBackend.REDIS
        config.redis.url = args.redis

    if args.postgres:
        config.store_backend = StoreBackend.POSTGRES
        config.postgres.url = args.postgres

    from flint_ai.server.embedded import FlintEngine

    engine = FlintEngine(config)
    print(f"Starting Flint server at http://{args.host}:{args.port}")
    print(f"  Queue: {config.queue_backend.value}")
    print(f"  Store: {config.store_backend.value}")
    print(f"  Workers: {args.workers}")
    engine.start(blocking=True)


if __name__ == "__main__":
    main()
