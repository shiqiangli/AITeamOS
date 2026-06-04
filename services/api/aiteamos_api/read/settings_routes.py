"""Settings-side health routes."""

from __future__ import annotations

import os

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


class SecretHealthItem(BaseModel):
    id: str
    scope: str
    purpose: str
    env_vars: list[str] = Field(default_factory=list)
    required_for: str
    configured: bool
    how_to_configure: str


class SecretsHealthResponse(BaseModel):
    items: list[SecretHealthItem]


def _configured(env_vars: list[str]) -> bool:
    return any(bool(os.environ.get(name)) for name in env_vars)


def _secret_item(
    *,
    item_id: str,
    scope: str,
    purpose: str,
    env_vars: list[str],
    required_for: str,
) -> SecretHealthItem:
    return SecretHealthItem(
        id=item_id,
        scope=scope,
        purpose=purpose,
        env_vars=env_vars,
        required_for=required_for,
        configured=_configured(env_vars),
        how_to_configure=f"Set {' or '.join(env_vars)} in the server environment before starting AITeamOS.",
    )


@router.get("/secrets-health", response_model=SecretsHealthResponse)
async def get_secrets_health() -> SecretsHealthResponse:
    return SecretsHealthResponse(
        items=[
            _secret_item(
                item_id="deepseek_api_key",
                scope="AI Engines",
                purpose="DeepSeek LLM API key.",
                env_vars=["DEEPSEEK_API_KEY"],
                required_for="DeepSeek AI Engine execution.",
            ),
            _secret_item(
                item_id="openai_api_key",
                scope="AI Engines / Memory Backend",
                purpose="OpenAI API key for OpenAI AI Engine and optional Graphiti LLM ingestion.",
                env_vars=["OPENAI_API_KEY"],
                required_for="OpenAI AI Engine execution or Graphiti fallback LLM key.",
            ),
            _secret_item(
                item_id="graphiti_neo4j_password",
                scope="Memory Backend",
                purpose="Neo4j password for Graphiti memory backend.",
                env_vars=["AITEAMOS_GRAPHITI_PASSWORD", "NEO4J_PASSWORD"],
                required_for="Graphiti graph database connection.",
            ),
            _secret_item(
                item_id="graphiti_openai_api_key",
                scope="Memory Backend",
                purpose="Dedicated OpenAI API key for Graphiti ingestion and graph search.",
                env_vars=["AITEAMOS_GRAPHITI_OPENAI_API_KEY", "OPENAI_API_KEY"],
                required_for="Graphiti LLM calls.",
            ),
            _secret_item(
                item_id="plane_api_token",
                scope="Ticket Backend",
                purpose="Plane API token when Plane is selected as a Ticket Backend.",
                env_vars=["AITEAMOS_PLANE_API_TOKEN"],
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
