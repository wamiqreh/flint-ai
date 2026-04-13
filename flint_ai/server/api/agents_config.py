"""Agent configuration API routes — register, list, enable/disable agents persistently."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


def create_agent_config_routes() -> APIRouter:
    router = APIRouter(tags=["Agent Config"])

    class AgentConfigRequest(BaseModel):
        agent_type: str
        provider: str = "sdk"
        model: str | None = None
        config_json: dict[str, Any] = {}
        enabled: bool = True

    class AgentConfigResponse(BaseModel):
        agent_type: str
        provider: str
        model: str | None
        config_json: dict[str, Any]
        enabled: bool

    @router.post("/agents/config", response_model=AgentConfigResponse)
    async def register_agent_config(req: AgentConfigRequest, request: Any = None):  # type: ignore
        """Register an agent configuration persistently (survives restarts).

        The agent will be auto-registered on every server startup.
        """
        from flint_ai.server.agents_config import AgentConfigRecord

        store = request.app.state.agents_config_store  # type: ignore
        if store is None:
            raise HTTPException(status_code=503, detail="Agent config store not available")

        record = AgentConfigRecord(
            agent_type=req.agent_type,
            provider=req.provider,
            model=req.model,
            config_json=req.config_json,
            enabled=req.enabled,
        )
        await store.save(record)
        return AgentConfigResponse(**record.__dict__)  # type: ignore

    @router.get("/agents/config", response_model=list[AgentConfigResponse])
    async def list_agent_configs(request: Any = None) -> list[AgentConfigResponse]:  # type: ignore
        """List all registered agent configurations."""
        store = request.app.state.agents_config_store  # type: ignore
        if store is None:
            raise HTTPException(status_code=503, detail="Agent config store not available")

        agents = await store.list_enabled()
        return [AgentConfigResponse(**a.__dict__) for a in agents]  # type: ignore

    @router.delete("/agents/config/{agent_type}")
    async def delete_agent_config(agent_type: str, request: Any = None) -> dict[str, str]:  # type: ignore
        """Remove an agent configuration."""
        store = request.app.state.agents_config_store  # type: ignore
        if store is None:
            raise HTTPException(status_code=503, detail="Agent config store not available")

        await store.delete(agent_type)
        return {"status": "deleted", "agent_type": agent_type}

    return router
