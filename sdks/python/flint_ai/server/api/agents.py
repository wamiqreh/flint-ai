"""Agent management API routes."""

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("flint.server.api.agents")


class RegisterAgentRequest(BaseModel):
    agent_type: str
    url: str
    auth_token: Optional[str] = None
    timeout_s: float = Field(default=60.0)
    headers: Dict[str, str] = Field(default_factory=dict)


class AgentInfo(BaseModel):
    agent_type: str
    kind: str  # "built-in", "webhook", "sdk-adapter"


def create_agent_routes(app: Any) -> None:
    """Register agent management API routes."""
    from fastapi import HTTPException, Request

    @app.get("/agents", response_model=List[AgentInfo], tags=["Agents"])
    async def list_agents(request: Request) -> List[AgentInfo]:
        """List all registered agent types."""
        agent_registry = request.app.state.agent_registry
        infos = []
        for agent_type in agent_registry.list_types():
            agent = agent_registry.get(agent_type)
            kind = "built-in"
            if agent and hasattr(agent, '_url'):
                kind = "webhook"
            infos.append(AgentInfo(agent_type=agent_type, kind=kind))
        return infos

    @app.post("/agents/register", response_model=AgentInfo, tags=["Agents"])
    async def register_webhook_agent(req: RegisterAgentRequest, request: Request) -> AgentInfo:
        """Register a new webhook agent at runtime."""
        from flint_ai.server.agents.webhook import WebhookAgent

        agent = WebhookAgent(
            name=req.agent_type,
            url=req.url,
            auth_token=req.auth_token,
            timeout_s=req.timeout_s,
            headers=req.headers,
        )
        request.app.state.agent_registry.register(agent)
        return AgentInfo(agent_type=req.agent_type, kind="webhook")
