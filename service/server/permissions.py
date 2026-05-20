"""Agent authorization helpers."""

from __future__ import annotations

import os
from typing import Iterable

from fastapi import HTTPException

from services import _get_agent_by_token
from utils import _extract_token


EXPERIMENT_ADMIN_CAPABILITY = "experiment_admin"
RESEARCH_EXPORTS_CAPABILITY = "research_exports"
TEAM_MISSION_ADMIN_CAPABILITY = "team_mission_admin"

ALL_CAPABILITIES = (
    EXPERIMENT_ADMIN_CAPABILITY,
    RESEARCH_EXPORTS_CAPABILITY,
    TEAM_MISSION_ADMIN_CAPABILITY,
)

ROLE_CAPABILITIES = {
    "admin": set(ALL_CAPABILITIES),
    "experiment_admin": {EXPERIMENT_ADMIN_CAPABILITY},
    "researcher": {RESEARCH_EXPORTS_CAPABILITY},
    "research": {RESEARCH_EXPORTS_CAPABILITY},
    "team_mission_admin": {TEAM_MISSION_ADMIN_CAPABILITY},
    "team_admin": {TEAM_MISSION_ADMIN_CAPABILITY},
}

CAPABILITY_ENV_VARS = {
    EXPERIMENT_ADMIN_CAPABILITY: "AI_TRADER_EXPERIMENT_ADMIN_AGENTS",
    RESEARCH_EXPORTS_CAPABILITY: "AI_TRADER_RESEARCH_AGENTS",
    TEAM_MISSION_ADMIN_CAPABILITY: "AI_TRADER_TEAM_MISSION_ADMIN_AGENTS",
}


def _split_values(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def _agent_matches_env(agent: dict, env_var: str) -> bool:
    values = _split_values(os.getenv(env_var))
    if not values:
        return False
    agent_id = str(agent.get("id", "")).strip().lower()
    agent_name = str(agent.get("name", "")).strip().lower()
    return agent_id in values or agent_name in values


def agent_role(agent: dict | None) -> str:
    if not agent:
        return "agent"
    if _agent_matches_env(agent, "AI_TRADER_ADMIN_AGENTS"):
        return "admin"
    return str(agent.get("role") or "agent").strip().lower() or "agent"


def agent_capability_set(agent: dict | None) -> set[str]:
    if not agent:
        return set()

    capabilities: set[str] = set()
    role_tokens = _split_values(agent.get("role"))
    if not role_tokens:
        role_tokens = {"agent"}
    for role in role_tokens:
        capabilities.update(ROLE_CAPABILITIES.get(role, set()))

    if _agent_matches_env(agent, "AI_TRADER_ADMIN_AGENTS"):
        capabilities.update(ALL_CAPABILITIES)
    for capability, env_var in CAPABILITY_ENV_VARS.items():
        if _agent_matches_env(agent, env_var):
            capabilities.add(capability)

    return capabilities


def agent_permissions(agent: dict | None) -> dict[str, bool]:
    capabilities = agent_capability_set(agent)
    return {capability: capability in capabilities for capability in ALL_CAPABILITIES}


def require_agent(authorization: str | None) -> dict:
    token = _extract_token(authorization)
    agent = _get_agent_by_token(token)
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid token")
    return agent


def require_capability(authorization: str | None, capability: str) -> dict:
    agent = require_agent(authorization)
    if capability not in agent_capability_set(agent):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return agent


def require_any_capability(authorization: str | None, capabilities: Iterable[str]) -> dict:
    agent = require_agent(authorization)
    agent_capabilities = agent_capability_set(agent)
    if not any(capability in agent_capabilities for capability in capabilities):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return agent
