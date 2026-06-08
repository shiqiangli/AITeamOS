"""Remote AI Engine HTTP clients used by Employee Chat."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import HTTPException


AsyncClientFactory = Callable[..., Any]


async def call_openai_responses(
    *,
    async_client_factory: AsyncClientFactory,
    base_url: str,
    api_key: str,
    request_body: dict[str, Any],
) -> dict[str, Any]:
    return await _post_json(
        async_client_factory=async_client_factory,
        url=f"{base_url.rstrip('/')}/responses",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        request_body=request_body,
        provider_label="OpenAI AI Engine",
    )


async def call_deepseek_chat_completion(
    *,
    async_client_factory: AsyncClientFactory,
    base_url: str,
    api_key: str,
    request_body: dict[str, Any],
) -> dict[str, Any]:
    return await _post_json(
        async_client_factory=async_client_factory,
        url=f"{base_url.rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        request_body=request_body,
        provider_label="DeepSeek AI Engine",
    )


async def _post_json(
    *,
    async_client_factory: AsyncClientFactory,
    url: str,
    headers: dict[str, str],
    request_body: dict[str, Any],
    provider_label: str,
) -> dict[str, Any]:
    async with async_client_factory(timeout=60) as client:
        response = await client.post(url, headers=headers, json=request_body)
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"{provider_label} failed: {response.status_code} {response.text[:500]}",
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail=f"{provider_label} returned invalid JSON payload")
    return payload


def extract_openai_text(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    chunks: list[str] = []
    for output in payload.get("output", []):
        if not isinstance(output, dict):
            continue
        for content in output.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks).strip()
