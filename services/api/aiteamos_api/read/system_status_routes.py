"""System Status read routes."""

from __future__ import annotations

import os

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .memory_service import GraphitiBackendStatus, graphiti_backend_status
from .ticket_service import TicketBackendStatus, ticket_backend_settings, ticket_backend_status

router = APIRouter(prefix="/api/v1/system-status", tags=["system-status"])


class SystemStatusSecretItem(BaseModel):
    id: str
    scope: str
    purpose: str
    env_vars: list[str] = Field(default_factory=list)
    required_for: str
    configured: bool
    how_to_configure: str


class SystemStatusBlocker(BaseModel):
    id: str
    scope: str
    status: str
    detail: str
    setup_required: list[str] = Field(default_factory=list)


class SystemStatusResponse(BaseModel):
    secrets: list[SystemStatusSecretItem]
    ticket_backend: TicketBackendStatus | None = None
    memory_backend: GraphitiBackendStatus | None = None
    blockers: list[SystemStatusBlocker] = Field(default_factory=list)


def _configured(env_vars: list[str]) -> bool:
    return any(bool(os.environ.get(name)) for name in env_vars)


def _secret_item(
    *,
    item_id: str,
    scope: str,
    purpose: str,
    env_vars: list[str],
    required_for: str,
) -> SystemStatusSecretItem:
    return SystemStatusSecretItem(
        id=item_id,
        scope=scope,
        purpose=purpose,
        env_vars=env_vars,
        required_for=required_for,
        configured=_configured(env_vars),
        how_to_configure=f"Set {' or '.join(env_vars)} in the server environment before starting AITeamOS.",
    )


@router.get("", response_model=SystemStatusResponse)
async def get_system_status() -> SystemStatusResponse:
    ticket_settings = ticket_backend_settings()
    ticket_status = ticket_backend_status()
    memory_status = graphiti_backend_status()
    plane_api_key_env = ticket_settings.plane_api_key_env.strip() or "PLANE_API_KEY"
    blockers: list[SystemStatusBlocker] = []
    if ticket_status.status != "ready":
        blockers.append(
            SystemStatusBlocker(
                id="ticket_backend",
                scope="Ticket Backend",
                status=ticket_status.status,
                detail=ticket_status.detail,
                setup_required=ticket_status.setup_required,
            )
        )
    if memory_status.status != "ready":
        blockers.append(
            SystemStatusBlocker(
                id="memory_asset_graph_backend",
                scope="Memory / Asset Graph Backend",
                status=memory_status.status,
                detail=memory_status.detail,
                setup_required=[
                    name
                    for name, configured in (
                        ("Graphiti URI/user", memory_status.graph_configured),
                        ("AITEAMOS_GRAPHITI_PASSWORD or NEO4J_PASSWORD", memory_status.password_configured),
                        (memory_status.llm_api_key_env or "selected Graphiti LLM API key", memory_status.llm_api_key_configured),
                    )
                    if not configured
                ],
            )
        )
    return SystemStatusResponse(
        ticket_backend=ticket_status,
        memory_backend=memory_status,
        blockers=blockers,
        secrets=[
            _secret_item(
                item_id="deepseek_api_key",
                scope="AI Engines",
                purpose="DeepSeek LLM API key.",
                env_vars=["DEEPSEEK_API_KEY"],
                required_for="DeepSeek AI Engine execution.",
            ),
            _secret_item(
                item_id="openai_api_key",
                scope="AI Engines / Memory / Asset Graph Backend",
                purpose="OpenAI API key for the OpenAI AI Engine; Graphiti uses this env when that AI Engine is selected.",
                env_vars=["OPENAI_API_KEY"],
                required_for="OpenAI AI Engine execution and Graphiti ingestion when OpenAI is selected.",
            ),
            _secret_item(
                item_id="graphiti_neo4j_password",
                scope="Memory / Asset Graph Backend",
                purpose="Neo4j password for Graphiti Memory / Asset Graph Backend.",
                env_vars=["AITEAMOS_GRAPHITI_PASSWORD", "NEO4J_PASSWORD"],
                required_for="Graphiti graph database connection.",
            ),
            _secret_item(
                item_id="plane_api_key",
                scope="Ticket Backend",
                purpose="Plane API key when Plane is selected as the Ticket Backend.",
                env_vars=[plane_api_key_env],
                required_for="Plane-backed ticket sync.",
            ),
            _secret_item(
                item_id="jira_api_token",
                scope="Ticket Backend",
                purpose="Jira API token when Jira is selected as a Ticket Backend.",
                env_vars=["AITEAMOS_JIRA_API_TOKEN"],
                required_for="Jira-backed ticket sync.",
            ),
            _secret_item(
                item_id="github_token",
                scope="Tool Connectors / Code Repositories",
                purpose="GitHub token for repository, issue, and pull request connectors.",
                env_vars=["AITEAMOS_GITHUB_TOKEN", "GITHUB_TOKEN"],
                required_for="GitHub connector calls.",
            ),
            _secret_item(
                item_id="ci_harness_token",
                scope="Tool Connectors",
                purpose="Token for external CI or harness connector calls.",
                env_vars=["AITEAMOS_CI_HARNESS_TOKEN"],
                required_for="CI or harness connector execution.",
            ),
        ]
    )
