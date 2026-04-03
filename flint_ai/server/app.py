"""FastAPI application factory — assembles all components."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from flint_ai.server.config import QueueBackend, ServerConfig, StoreBackend

logger = logging.getLogger("flint.server.app")


def create_app(config: ServerConfig | None = None) -> Any:
    """Create and configure the FastAPI application.

    This is the main entry point for the Flint Python server.
    It wires up all components: queue, store, engines, workers, metrics,
    and production middleware (auth, CORS, correlation IDs, validation).
    """
    try:
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError:
        raise ImportError(
            "FastAPI required for Flint server. "
            "Install with: pip install flint-ai[server]"
        )

    if config is None:
        config = ServerConfig.from_env()

    # Configure logging
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)
    if config.log_format == "json":
        import json as _json

        class JsonFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                log_entry = {
                    "timestamp": self.formatTime(record),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                }
                if record.exc_info and record.exc_info[0]:
                    log_entry["exception"] = self.formatException(record.exc_info)
                return _json.dumps(log_entry)

        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logging.root.handlers.clear()
        logging.root.addHandler(handler)
        logging.root.setLevel(log_level)
    else:
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        """Manage application lifecycle — startup and shutdown."""
        logger.info("Flint Python Server starting...")

        # --- Create components ---
        # Queue
        if config.queue_backend == QueueBackend.REDIS:
            from flint_ai.server.queue.redis_streams import RedisStreamsQueue
            queue = RedisStreamsQueue(config.redis)
        elif config.queue_backend == QueueBackend.SQS:
            from flint_ai.server.queue.sqs import SQSQueue
            queue = SQSQueue(config.sqs)
        else:
            from flint_ai.server.queue.memory import InMemoryQueue
            queue = InMemoryQueue()
        await queue.connect()
        app.state.queue = queue

        # Task Store
        if config.store_backend == StoreBackend.POSTGRES:
            from flint_ai.server.store.postgres import PostgresTaskStore
            task_store = PostgresTaskStore(config.postgres)
        else:
            from flint_ai.server.store.memory import InMemoryTaskStore
            task_store = InMemoryTaskStore()
        await task_store.connect()
        app.state.task_store = task_store

        # Workflow Store
        if config.store_backend == StoreBackend.POSTGRES:
            from flint_ai.server.store.postgres import PostgresWorkflowStore
            workflow_store = PostgresWorkflowStore(config.postgres)
        else:
            from flint_ai.server.store.memory import InMemoryWorkflowStore
            workflow_store = InMemoryWorkflowStore()
        await workflow_store.connect()
        app.state.workflow_store = workflow_store

        # Agent Registry
        from flint_ai.server.agents import AgentRegistry
        from flint_ai.server.agents.dummy import DummyAgent
        agent_registry = AgentRegistry()
        agent_registry.register(DummyAgent())
        # No server-side adapter auto-registration — agents execute on client side
        # via the FlintWorker claim/result pattern.

        app.state.agent_registry = agent_registry

        # Concurrency Manager (distributed if Redis is available)
        from flint_ai.server.engine.concurrency import ConcurrencyManager
        if config.queue_backend == QueueBackend.REDIS:
            from flint_ai.server.engine.distributed_concurrency import DistributedConcurrencyManager
            concurrency = DistributedConcurrencyManager(config.concurrency, queue._redis)
            logger.info("Using distributed (Redis) concurrency manager")
        else:
            concurrency = ConcurrencyManager(config.concurrency)
        app.state.concurrency = concurrency

        # Metrics
        from flint_ai.server.metrics import FlintMetrics
        metrics = FlintMetrics()
        app.state.metrics = metrics

        # Event Bus (Redis Pub/Sub for cross-pod SSE)
        event_bus = None
        if config.queue_backend == QueueBackend.REDIS:
            from flint_ai.server.events import RedisPubSubBus
            event_bus = RedisPubSubBus(queue._redis)
            await event_bus.start()
            app.state.event_bus = event_bus
            logger.info("Redis Pub/Sub event bus enabled")

        # Task Engine
        from flint_ai.server.engine.task_engine import TaskEngine
        task_engine = TaskEngine(
            queue=queue,
            task_store=task_store,
            agent_registry=agent_registry,
            concurrency=concurrency,
            metrics=metrics,
            max_task_duration_s=config.worker.max_task_duration_s,
            completion_webhook_url=config.task_completion_webhook_url,
            event_bus=event_bus,
        )
        app.state.task_engine = task_engine

        # DAG Engine
        from flint_ai.server.dag.engine import DAGEngine
        dag_engine = DAGEngine(
            workflow_store=workflow_store,
            task_store=task_store,
        )
        app.state.dag_engine = dag_engine

        # Circuit breakers for backends
        from flint_ai.server.middleware.circuit_breaker import CircuitBreaker
        app.state.circuit_breaker_queue = CircuitBreaker("queue", failure_threshold=5, recovery_timeout=30.0)
        app.state.circuit_breaker_store = CircuitBreaker("store", failure_threshold=5, recovery_timeout=30.0)

        # Worker Pool
        from flint_ai.server.worker.pool import WorkerPool
        worker_pool = WorkerPool(
            config=config.worker,
            task_engine=task_engine,
            dag_engine=dag_engine,
            queue=queue,
            workflow_store=workflow_store,
            metrics=metrics,
        )
        app.state.worker_pool = worker_pool
        await worker_pool.start()

        # DAG Recovery — resume any stale RUNNING workflow runs from a previous crash
        try:
            stale_runs = await workflow_store.list_running_runs()
            if stale_runs:
                logger.info("Recovering %d stale workflow runs", len(stale_runs))
                for run in stale_runs:
                    await dag_engine.recover_run(run, task_store, queue, task_engine)
        except Exception:
            logger.exception("DAG recovery failed (non-fatal, will retry on next startup)")

        # Scheduler
        from flint_ai.server.dag.scheduler import WorkflowScheduler

        # Leader lock for scheduler (prevents duplicate cron triggers across pods)
        leader_lock = None
        if config.queue_backend == QueueBackend.REDIS:
            from flint_ai.server.dag.leader import SchedulerLeaderLock
            leader_lock = SchedulerLeaderLock(queue._redis)
            await leader_lock.start()
            app.state.leader_lock = leader_lock

        async def trigger_workflow(wf_id: str) -> None:
            defn = await workflow_store.get_definition(wf_id)
            if defn:
                run = await dag_engine.start_workflow(wf_id)
                root_nodes = dag_engine.get_root_nodes(defn)
                for node in root_nodes:
                    await task_engine.submit_task(
                        agent_type=node.agent_type,
                        prompt=node.prompt_template,
                        workflow_id=wf_id,
                        node_id=node.id,
                        max_retries=node.retry_policy.max_retries,
                        metadata={"workflow_run_id": run.id},
                    )

        scheduler = WorkflowScheduler(
            trigger_callback=trigger_workflow,
            leader_lock=leader_lock,
        )
        app.state.scheduler = scheduler

        # Load scheduled workflows from store
        all_defs = await workflow_store.list_definitions()
        for defn in all_defs:
            if defn.schedule_cron:
                scheduler.add(defn.id, cron=defn.schedule_cron)
            elif defn.schedule_interval_s:
                scheduler.add(defn.id, interval_s=defn.schedule_interval_s)
        await scheduler.start()

        logger.info(
            "Flint server ready: queue=%s store=%s workers=%d auth=%s",
            config.queue_backend.value,
            config.store_backend.value,
            config.worker.count,
            "enabled" if config.api_key else "disabled",
        )

        yield

        # --- Graceful shutdown ---
        logger.info("Flint server shutting down...")
        await scheduler.stop()
        if leader_lock:
            await leader_lock.stop()
        if event_bus:
            await event_bus.stop()
        await worker_pool.stop()
        await queue.disconnect()
        await task_store.disconnect()
        await workflow_store.disconnect()
        logger.info("Flint server stopped")

    app = FastAPI(
        title="Flint — AI Agent Queue Orchestrator",
        description=(
            "Production-grade task queue and DAG workflow engine for AI agents. "
            "Submit tasks, build workflows, monitor execution."
        ),
        version="2.0.0",
        lifespan=lifespan,
    )

    # --- Middleware stack (order matters: last added = first executed) ---

    # CORS — configured per environment
    if config.enable_cors:
        # If wildcard origins, disable credentials (browser security requirement)
        has_wildcard = "*" in config.cors_origins
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.cors_origins if not has_wildcard else ["*"],
            allow_credentials=not has_wildcard,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # API key auth (no-op if FLINT_API_KEY not set)
    from flint_ai.server.middleware.auth import APIKeyAuthMiddleware
    app.add_middleware(APIKeyAuthMiddleware, api_key=config.api_key)

    # Correlation IDs for distributed tracing
    from flint_ai.server.middleware.correlation import CorrelationIDMiddleware
    app.add_middleware(CorrelationIDMiddleware)

    # Register API routes
    from flint_ai.server.api import create_task_routes
    from flint_ai.server.api.agents import create_agent_routes
    from flint_ai.server.api.dashboard import create_dashboard_routes
    from flint_ai.server.api.workers import create_worker_routes
    from flint_ai.server.api.workflows import create_workflow_routes

    create_task_routes(app)
    create_workflow_routes(app)
    create_dashboard_routes(app)
    create_agent_routes(app)
    create_worker_routes(app)

    # Serve React UI static files
    import pathlib
    static_dir = pathlib.Path(__file__).parent / "static"
    if static_dir.exists():
        from starlette.responses import FileResponse
        from starlette.staticfiles import StaticFiles

        @app.get("/ui/{rest_of_path:path}")
        async def serve_ui(rest_of_path: str) -> FileResponse:
            """Serve the React SPA — fall back to index.html for client routes."""
            file = static_dir / rest_of_path
            if file.is_file():
                return FileResponse(file)
            return FileResponse(static_dir / "index.html")

        # Mount assets directory for JS/CSS chunks
        assets_dir = static_dir / "assets"
        if assets_dir.exists():
            app.mount(
                "/ui/assets",
                StaticFiles(directory=str(assets_dir)),
                name="ui-assets",
            )

        @app.get("/ui")
        async def redirect_ui() -> FileResponse:
            return FileResponse(static_dir / "index.html")

    return app
