"""Adapter registry — manages registration of adapters with Flint."""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from .base import FlintAdapter
from .types import RegisteredAgent

logger = logging.getLogger("flint.adapters.registry")

# Global in-process registry for inline adapters
_inline_registry: dict[str, FlintAdapter] = {}


def get_inline_adapter(name: str) -> Optional[FlintAdapter]:
    """Get an inline adapter by name."""
    return _inline_registry.get(name)


def list_inline_adapters() -> dict[str, FlintAdapter]:
    """List all registered inline adapters."""
    return dict(_inline_registry)


def register_inline(adapter: FlintAdapter) -> None:
    """Register an adapter for inline (in-process) execution."""
    _inline_registry[adapter.get_agent_name()] = adapter
    logger.info("Registered inline adapter: %s", adapter.get_agent_name())


async def register_with_flint(
    adapter: FlintAdapter,
    flint_url: Optional[str] = None,
    worker_url: Optional[str] = None,
) -> bool:
    """Register an adapter with the Flint API server.

    For inline adapters, also registers them in the local registry.
    For webhook adapters, tells Flint where to POST task payloads.

    Args:
        adapter: The adapter to register.
        flint_url: Override Flint API URL (default from adapter config).
        worker_url: URL where Flint should send tasks (webhook mode).
                    If None and adapter is inline, uses the inline worker URL.

    Returns:
        True if registration succeeded.
    """
    url = flint_url or adapter.config.flint_url
    agent = adapter.to_registered_agent()

    # Always register inline for in-process execution
    if adapter.config.inline:
        register_inline(adapter)

    # Register with Flint API so it knows this agent type exists
    payload = agent.to_registration_payload()
    if worker_url:
        payload["url"] = worker_url
    elif adapter.config.inline:
        # Inline worker URL — set by the worker when it starts
        payload["url"] = f"http://localhost:5157/adapters/{adapter.get_agent_name()}/execute"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{url}/agents/register", json=payload)
            if resp.status_code in (200, 201):
                logger.info("Registered %s with Flint at %s", agent.name, url)
                return True
            else:
                logger.warning(
                    "Failed to register %s with Flint: %s %s",
                    agent.name,
                    resp.status_code,
                    resp.text,
                )
                return False
    except httpx.ConnectError:
        logger.warning(
            "Could not connect to Flint at %s — adapter %s registered locally only",
            url,
            agent.name,
        )
        return False


async def auto_register(adapter: FlintAdapter) -> None:
    """Auto-register an adapter (inline + remote if possible).

    Called automatically when an adapter is used for the first time.
    """
    if adapter._registered:
        return

    if adapter.config.inline:
        register_inline(adapter)

    if adapter.config.auto_register:
        await register_with_flint(adapter)

    adapter._registered = True
