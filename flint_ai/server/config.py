"""Server configuration with Pydantic Settings."""

from __future__ import annotations

import os
from enum import Enum

from pydantic import BaseModel, Field


class QueueBackend(str, Enum):
    MEMORY = "memory"
    REDIS = "redis"
    SQS = "sqs"


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


class SQSConfig(BaseModel):
    """AWS SQS configuration."""

    queue_url: str = Field(default="", description="SQS queue URL")
    dlq_url: str = Field(default="", description="SQS DLQ URL")
    region: str = Field(default="us-east-1", description="AWS region")
    visibility_timeout: int = Field(default=300, description="Visibility timeout (s)")
    max_receive_count: int = Field(default=3, description="Max receives before DLQ")
    wait_time_seconds: int = Field(default=5, description="Long-poll wait time (s)")


class WorkerConfig(BaseModel):
    """Worker pool configuration."""

    count: int = Field(default=4, description="Number of worker coroutines")
    poll_interval_ms: int = Field(default=1000, description="Queue poll interval (ms)")
    shutdown_timeout_s: int = Field(default=30, description="Graceful shutdown timeout (s)")
    max_task_duration_s: int = Field(default=300, description="Max task execution time (s)")


class ConcurrencyConfig(BaseModel):
    """Per-agent concurrency limits."""

    default_limit: int = Field(default=5, description="Default per-agent concurrency")
    agent_limits: dict[str, int] = Field(
        default_factory=dict,
        description="Per-agent overrides, e.g. {'openai': 10, 'claude': 3}",
    )

    def get_limit(self, agent_type: str) -> int:
        return self.agent_limits.get(agent_type, self.default_limit)


class ServerConfig(BaseModel):
    """Root server configuration.

    Defaults to PostgreSQL + Redis for production-grade persistence.
    Development and production use the same backends.
    """

    host: str = Field(default="0.0.0.0", description="API bind host")
    port: int = Field(default=5156, description="API bind port")

    queue_backend: QueueBackend = Field(default=QueueBackend.REDIS)
    store_backend: StoreBackend = Field(default=StoreBackend.POSTGRES)

    redis: RedisConfig = Field(default_factory=RedisConfig)
    postgres: PostgresConfig = Field(default_factory=PostgresConfig)
    sqs: SQSConfig = Field(default_factory=SQSConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)
    concurrency: ConcurrencyConfig = Field(default_factory=ConcurrencyConfig)

    # Security
    api_key: str | None = Field(default=None, description="API key for auth (None = no auth)")
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:*", "http://127.0.0.1:*"],
        description="Allowed CORS origins (supports wildcards)",
    )

    enable_metrics: bool = Field(default=True, description="Expose /metrics endpoint")
    enable_cors: bool = Field(default=True, description="Enable CORS")
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="text", description="Log format: 'text' or 'json'")

    task_completion_webhook_url: str | None = Field(default=None, description="POST webhook on task completion")

    @classmethod
    def from_env(cls) -> ServerConfig:
        """Build config from environment variables."""
        config = cls()

        # Queue backend
        if url := os.environ.get("REDIS_URL"):
            config.redis.url = url
            config.queue_backend = QueueBackend.REDIS
        if group := os.environ.get("REDIS_CONSUMER_GROUP"):
            config.redis.consumer_group = group
        if idle := os.environ.get("REDIS_RECLAIM_MIN_IDLE_MS"):
            config.redis.reclaim_idle_ms = int(idle)

        if os.environ.get("SQS_QUEUE_URL"):
            config.sqs.queue_url = os.environ["SQS_QUEUE_URL"]
            config.queue_backend = QueueBackend.SQS
            if dlq := os.environ.get("SQS_DLQ_URL"):
                config.sqs.dlq_url = dlq
            if region := os.environ.get("AWS_REGION"):
                config.sqs.region = region

        # Store backend — always POSTGRES by default, override if env set
        if url := os.environ.get("POSTGRES_URL", os.environ.get("DATABASE_URL")):
            config.postgres.url = url

        # Workers
        if count := os.environ.get("WORKER_COUNT"):
            config.worker.count = int(count)

        # Server
        if host := os.environ.get("HOST"):
            config.host = host
        if port := os.environ.get("PORT"):
            config.port = int(port)

        if level := os.environ.get("LOG_LEVEL"):
            config.log_level = level
        if fmt := os.environ.get("LOG_FORMAT"):
            config.log_format = fmt

        if webhook := os.environ.get("TASK_COMPLETION_WEBHOOK_URL"):
            config.task_completion_webhook_url = webhook

        # Security
        if api_key := os.environ.get("FLINT_API_KEY"):
            config.api_key = api_key
        if origins := os.environ.get("FLINT_CORS_ORIGINS"):
            config.cors_origins = [o.strip() for o in origins.split(",")]

        # Per-agent concurrency from CONCURRENCY_<AGENT>=N
        for key, val in os.environ.items():
            if key.startswith("CONCURRENCY_"):
                agent = key[len("CONCURRENCY_") :].lower()
                config.concurrency.agent_limits[agent] = int(val)

        return config
