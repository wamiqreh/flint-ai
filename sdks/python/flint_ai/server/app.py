"""FastAPI application factory — assembles all components."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional

from flint_ai.server.config import QueueBackend, ServerConfig, StoreBackend

logger = logging.getLogger("flint.server.app")


def create_app(config: Optional[ServerConfig] = None) -> Any:
    """Create and configure the FastAPI application.

    This is the main entry point for the Flint Python server.
    It wires up all components: queue, store, engines, workers, metrics.
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
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
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
        app.state.agent_registry = agent_registry

        # Concurrency Manager
        from flint_ai.server.engine.concurrency import ConcurrencyManager
        concurrency = ConcurrencyManager(config.concurrency)
        app.state.concurrency = concurrency

        # Metrics
        from flint_ai.server.metrics import FlintMetrics
        metrics = FlintMetrics()
        app.state.metrics = metrics

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
        )
        app.state.task_engine = task_engine

        # DAG Engine
        from flint_ai.server.dag.engine import DAGEngine
        dag_engine = DAGEngine(
            workflow_store=workflow_store,
            task_store=task_store,
        )
        app.state.dag_engine = dag_engine

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

        # Scheduler
        from flint_ai.server.dag.scheduler import WorkflowScheduler

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

        scheduler = WorkflowScheduler(trigger_callback=trigger_workflow)
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
            "Flint server ready: queue=%s store=%s workers=%d",
            config.queue_backend.value,
            config.store_backend.value,
            config.worker.count,
        )

        yield

        # --- Shutdown ---
        logger.info("Flint server shutting down...")
        await scheduler.stop()
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

    # CORS
    if config.enable_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Register API routes
    from flint_ai.server.api import create_task_routes
    from flint_ai.server.api.workflows import create_workflow_routes
    from flint_ai.server.api.dashboard import create_dashboard_routes
    from flint_ai.server.api.agents import create_agent_routes

    create_task_routes(app)
    create_workflow_routes(app)
    create_dashboard_routes(app)
    create_agent_routes(app)

    # Serve React UI static files
    import pathlib
    static_dir = pathlib.Path(__file__).parent / "static"
    if static_dir.exists():
        from starlette.staticfiles import StaticFiles
        from starlette.responses import FileResponse

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

    # Health check
    @app.get("/health")
    async def health() -> dict:
        return {"status": "healthy", "version": "2.0.0"}

    return app
