"""Server configuration with Pydantic Settings."""

from __future__ import annotations

import os
from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, Field


class QueueBackend(str, Enum):
    MEMORY = "memory"
    REDIS = "redis"


class StoreBackend(str, Enum):
    MEMORY = "memory"
    POSTGRES = "postgres"


class RedisConfig(BaseModel):
    """Redis connection and Streams configuration."""

    url: str = Field(default="redis://localhost:6379", description="Redis connection URL")
    consumer_group: str = Field(default="flint-group", description="Consumer group name")
    consumer_prefix: str = Field(default="flint-worker", description="Consumer name prefix")
    reclaim_idle_ms: int = Field(default=60000, description="XAUTOCLAIM min idle time (ms)")
    block_ms: int = Field(default=5000, description="XREADGROUP block timeout (ms)")
    stream_key: str = Field(default="flint:tasks", description="Main task stream key")
    dlq_prefix: str = Field(default="flint:dlq", description="Dead-letter stream prefix")
    max_stream_length: int = Field(default=100000, description="Max stream length (MAXLEN ~)")


class PostgresConfig(BaseModel):
    """PostgreSQL connection configuration."""

    url: str = Field(
        default="postgresql://flint:flint@localhost:5432/flint",
        description="PostgreSQL connection URL",
    )
    min_pool_size: int = Field(default=2, description="Minimum connection pool size")
    max_pool_size: int = Field(default=10, description="Maximum connection pool size")
    run_migrations: bool = Field(default=True, description="Auto-run migrations on startup")


class WorkerConfig(BaseModel):
    """Worker pool configuration."""

    count: int = Field(default=4, description="Number of worker coroutines")
    poll_interval_ms: int = Field(default=1000, description="Queue poll interval (ms)")
    shutdown_timeout_s: int = Field(default=30, description="Graceful shutdown timeout (s)")
    max_task_duration_s: int = Field(default=300, description="Max task execution time (s)")


class ConcurrencyConfig(BaseModel):
    """Per-agent concurrency limits."""

    default_limit: int = Field(default=5, description="Default per-agent concurrency")
    agent_limits: Dict[str, int] = Field(
        default_factory=dict,
        description="Per-agent overrides, e.g. {'openai': 10, 'claude': 3}",
    )

    def get_limit(self, agent_type: str) -> int:
        return self.agent_limits.get(agent_type, self.default_limit)


class ServerConfig(BaseModel):
    """Root server configuration."""

    host: str = Field(default="0.0.0.0", description="API bind host")
    port: int = Field(default=5156, description="API bind port")

    queue_backend: QueueBackend = Field(default=QueueBackend.MEMORY)
    store_backend: StoreBackend = Field(default=StoreBackend.MEMORY)

    redis: RedisConfig = Field(default_factory=RedisConfig)
    postgres: PostgresConfig = Field(default_factory=PostgresConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)
    concurrency: ConcurrencyConfig = Field(default_factory=ConcurrencyConfig)

    enable_metrics: bool = Field(default=True, description="Expose /metrics endpoint")
    enable_cors: bool = Field(default=True, description="Enable CORS for all origins")
    log_level: str = Field(default="INFO", description="Logging level")

    task_completion_webhook_url: Optional[str] = Field(
        default=None, description="POST webhook on task completion"
    )

    @classmethod
    def from_env(cls) -> "ServerConfig":
        """Build config from environment variables."""
        config = cls()

        if url := os.environ.get("REDIS_URL"):
            config.redis.url = url
            config.queue_backend = QueueBackend.REDIS
        if group := os.environ.get("REDIS_CONSUMER_GROUP"):
            config.redis.consumer_group = group
        if idle := os.environ.get("REDIS_RECLAIM_MIN_IDLE_MS"):
            config.redis.reclaim_idle_ms = int(idle)

        if url := os.environ.get("POSTGRES_URL", os.environ.get("DATABASE_URL")):
            config.postgres.url = url
            config.store_backend = StoreBackend.POSTGRES

        if count := os.environ.get("WORKER_COUNT"):
            config.worker.count = int(count)

        if host := os.environ.get("HOST"):
            config.host = host
        if port := os.environ.get("PORT"):
            config.port = int(port)

        if level := os.environ.get("LOG_LEVEL"):
            config.log_level = level

        if webhook := os.environ.get("TASK_COMPLETION_WEBHOOK_URL"):
            config.task_completion_webhook_url = webhook

        # Per-agent concurrency from CONCURRENCY_<AGENT>=N
        for key, val in os.environ.items():
            if key.startswith("CONCURRENCY_"):
                agent = key[len("CONCURRENCY_"):].lower()
                config.concurrency.agent_limits[agent] = int(val)

        return config
