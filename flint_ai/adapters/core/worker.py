"""Inline adapter worker — runs adapters in-process via a lightweight HTTP server.

When adapters run in inline mode, this worker handles /execute requests
from the Flint orchestrator without an extra network hop. The worker runs
inside the same process as your Python application.
"""

from __future__ import annotations

import asyncio
import json
import logging

from .registry import get_inline_adapter, list_inline_adapters

logger = logging.getLogger("flint.adapters.worker")

_worker_instance: InlineWorker | None = None


class InlineWorker:
    """Lightweight HTTP worker that serves inline adapters.

    Runs a small HTTP server (using only stdlib or starlette if available)
    that receives task payloads from Flint and routes them to the correct
    inline adapter.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 5157):
        self.host = host
        self.port = port
        self._server = None
        self._app = None

    async def handle_execute(self, agent_name: str, body: dict) -> dict:
        """Route an execution request to the correct inline adapter."""
        adapter = get_inline_adapter(agent_name)
        if not adapter:
            return {"error": f"adapter_not_found: {agent_name}", "output": ""}

        prompt = body.get("prompt", body.get("Prompt", ""))
        input_data = {
            "prompt": prompt,
            "task_id": body.get("task_id", body.get("TaskId", "")),
            "workflow_id": body.get("workflow_id", body.get("WorkflowId", "")),
            "metadata": body.get("metadata", {}),
        }

        result = await adapter.safe_run(input_data)
        return result.to_dict()

    async def handle_list(self) -> dict:
        """List all inline adapters."""
        adapters = list_inline_adapters()
        return {"agents": [{"name": name, "type": a.__class__.__name__} for name, a in adapters.items()]}

    def _build_app(self):
        """Build the ASGI/WSGI app. Uses starlette if available, falls back to stdlib."""
        try:
            from starlette.applications import Starlette
            from starlette.requests import Request
            from starlette.responses import JSONResponse
            from starlette.routing import Route

            async def execute_handler(request: Request) -> JSONResponse:
                agent_name = request.path_params["agent_name"]
                body = await request.json()
                result = await self.handle_execute(agent_name, body)
                status = 200 if result.get("success", True) and "error" not in result else 500
                return JSONResponse(result, status_code=status)

            async def list_handler(request: Request) -> JSONResponse:
                return JSONResponse(await self.handle_list())

            async def health_handler(request: Request) -> JSONResponse:
                return JSONResponse({"status": "ok", "inline_agents": len(list_inline_adapters())})

            self._app = Starlette(
                routes=[
                    Route("/adapters/{agent_name}/execute", execute_handler, methods=["POST"]),
                    Route("/adapters", list_handler, methods=["GET"]),
                    Route("/health", health_handler, methods=["GET"]),
                ],
            )
            return self._app
        except ImportError:
            logger.info("starlette not installed — using stdlib HTTP server for inline worker")
            return None

    async def start(self) -> None:
        """Start the inline worker server."""
        app = self._build_app()

        if app is not None:
            # Use uvicorn if available
            try:
                import uvicorn

                config = uvicorn.Config(
                    app,
                    host=self.host,
                    port=self.port,
                    log_level="warning",
                    access_log=False,
                )
                self._server = uvicorn.Server(config)
                logger.info("Inline worker starting on %s:%d (uvicorn)", self.host, self.port)
                # Run in background task so it doesn't block
                self._serve_task = asyncio.create_task(self._server.serve())
                return
            except ImportError:
                pass

        # Fallback: stdlib asyncio server
        await self._start_stdlib_server()

    async def _start_stdlib_server(self) -> None:
        """Minimal asyncio HTTP server using only stdlib."""

        worker = self

        async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            try:
                request_line = await asyncio.wait_for(reader.readline(), timeout=30)
                if not request_line:
                    writer.close()
                    return

                method, path, _ = request_line.decode().strip().split(" ", 2)

                # Read headers
                headers = {}
                while True:
                    line = await reader.readline()
                    if line in (b"\r\n", b"\n", b""):
                        break
                    key, val = line.decode().strip().split(": ", 1)
                    headers[key.lower()] = val

                # Read body
                content_length = int(headers.get("content-length", 0))
                body = b""
                if content_length > 0:
                    body = await reader.read(content_length)

                # Route
                response_body: dict
                status = 200
                if path.startswith("/adapters/") and path.endswith("/execute") and method == "POST":
                    agent_name = path.split("/")[2]
                    payload = json.loads(body) if body else {}
                    response_body = await worker.handle_execute(agent_name, payload)
                    if "error" in response_body:
                        status = 500
                elif path == "/adapters" and method == "GET":
                    response_body = await worker.handle_list()
                elif path == "/health" and method == "GET":
                    response_body = {"status": "ok", "inline_agents": len(list_inline_adapters())}
                else:
                    response_body = {"error": "not_found"}
                    status = 404

                resp_bytes = json.dumps(response_body).encode()
                writer.write(
                    f"HTTP/1.1 {status} OK\r\n"
                    f"Content-Type: application/json\r\n"
                    f"Content-Length: {len(resp_bytes)}\r\n"
                    f"\r\n".encode()
                )
                writer.write(resp_bytes)
                await writer.drain()
            except Exception as exc:
                logger.debug("Inline worker connection error: %s", exc)
            finally:
                writer.close()

        server = await asyncio.start_server(handle_client, self.host, self.port)
        logger.info("Inline worker starting on %s:%d (stdlib)", self.host, self.port)
        self._server = server

    async def stop(self) -> None:
        """Stop the inline worker server."""
        if self._server is not None:
            if hasattr(self._server, "should_exit"):
                self._server.should_exit = True
            elif hasattr(self._server, "close"):
                self._server.close()
                await self._server.wait_closed()
            self._server = None
            logger.info("Inline worker stopped")


async def start_worker(host: str = "0.0.0.0", port: int = 5157) -> InlineWorker:
    """Start the global inline worker."""
    global _worker_instance
    if _worker_instance is not None:
        return _worker_instance
    _worker_instance = InlineWorker(host=host, port=port)
    await _worker_instance.start()
    return _worker_instance


async def stop_worker() -> None:
    """Stop the global inline worker."""
    global _worker_instance
    if _worker_instance is not None:
        await _worker_instance.stop()
        _worker_instance = None
