from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import json
import os
import urllib.error
import urllib.request

from aiteamos_schema import ModelProfile

from .artifacts import record_artifact_manifest
from .io import read_text_if_exists, read_yaml, write_text, write_yaml
from .loader import WorkspaceIndex, load_workspace
from .model_policy import evaluate_model_policy, estimate_tokens, model_policy_event
from .mutations import propose_memory, update_run, update_task
from .run_events import append_run_event_record


@dataclass
class ModelExecutionResult:
    text: str
    provider: str
    model: str
    response_id: str | None = None
    status: str | None = None
    usage: dict[str, Any] | None = None


def execute_run_with_model(workspace_path: str | Path, run_id: str) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")

    run = index.runs[run_id]
    if run.spec.mode != "managed_llm":
        _append_event(
            index.workspace_root,
            run_id,
            {
                "type": "model.execution.blocked",
                "reason": "run-mode",
                "mode": run.spec.mode,
                "member": run.spec.member,
                "memberKind": run.spec.memberKind,
            },
        )
        raise ValueError(f"run {run_id} mode {run.spec.mode} is not managed_llm; use assisted/manual ingest or automation service flow")
    if not run.spec.modelProfile:
        raise ValueError(f"run {run_id} has no modelProfile")

    context = index.run_context_capsules.get(run_id)
    if not context:
        raise ValueError(f"run {run_id} has no context capsule")
    decision = evaluate_model_policy(index, run_id, estimated_input_tokens=estimate_tokens(context))
    if not decision["ready"]:
        _append_event(index.workspace_root, run_id, {"type": "model.policy.blocked", **model_policy_event(decision)})
        raise ValueError(decision["summary"])
    profile = index.model_profiles[decision["profile"]]

    update_run(workspace_path, run_id, {"status": "RUNNING"})
    _append_event(
        index.workspace_root,
        run_id,
        {
            "type": "model.call.started",
            "provider": profile.spec.provider,
            "model": profile.spec.model,
            "policy": decision.get("policy"),
            "estimatedInputTokens": decision["estimates"]["inputTokens"],
        },
    )

    try:
        result = call_model_with_prompt(profile, _managed_run_prompt(context))
    except Exception as exc:
        _append_event(index.workspace_root, run_id, {"type": "model.call.failed", "error": str(exc)})
        update_run(workspace_path, run_id, {"status": "FAILED"})
        update_task(workspace_path, run.spec.task, {"status": "FAILED"})
        raise

    model_output_path = _append_model_output(index.workspace_root, run_id, result)
    model_output_manifest = record_artifact_manifest(
        index.workspace_root,
        run_id,
        "model_output",
        model_output_path,
        source_id="model-output",
        extra={"provider": result.provider, "model": result.model, "responseId": result.response_id},
    )
    _append_event(
        index.workspace_root,
        run_id,
        {
            "type": "model.call.completed",
            "provider": result.provider,
            "model": result.model,
            "responseId": result.response_id,
            "status": result.status,
            "usage": result.usage or {},
        },
    )
    _maybe_propose_memory(workspace_path, run_id, result.text)
    updates: dict[str, Any] = {
        "status": "REVIEW",
        "outputs": _with_model_output(run.spec.outputs, model_output_path, result, model_output_manifest),
    }
    if not run.spec.reviewTarget:
        updates["reviewTarget"] = {
            "type": "external_review",
            "ref": model_output_path,
            "description": "Managed model output captured for dashboard review.",
        }
    update_run(workspace_path, run_id, updates)
    update_task(workspace_path, run.spec.task, {"status": "REVIEW"})
    return load_workspace(workspace_path).runs[run_id].model_dump(mode="json")


def _resolve_model_profile(index: WorkspaceIndex, profile_id: str) -> ModelProfile:
    if profile_id in index.model_profiles:
        return index.model_profiles[profile_id]
    builtin = _builtin_model_profile(profile_id)
    if builtin:
        return builtin
    raise ValueError(f"unknown model profile {profile_id}")


def _builtin_model_profile(profile_id: str) -> ModelProfile | None:
    builtin_specs: dict[str, dict[str, Any]] = {
        "builtin/openai-gpt-5.5-xhigh": {
            "displayName": "OpenAI GPT-5.5 Extra High",
            "provider": "openai",
            "model": "gpt-5.5",
            "gateway": "openai-responses",
            "secretEnv": "OPENAI_API_KEY",
            "invocation": {"reasoningEffort": "xhigh", "reasoningSummary": "auto"},
            "capabilities": ["managed_llm", "assisted", "reasoning", "coding", "review"],
        },
        "builtin/openai-gpt-5.4": {
            "displayName": "OpenAI GPT-5.4",
            "provider": "openai",
            "model": "gpt-5.4",
            "gateway": "openai-responses",
            "secretEnv": "OPENAI_API_KEY",
            "invocation": {"reasoningEffort": "high", "reasoningSummary": "auto"},
            "capabilities": ["managed_llm", "assisted", "reasoning", "coding", "review"],
        },
    }
    spec = builtin_specs.get(profile_id)
    if spec is None:
        return None
    return ModelProfile.model_validate(
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "ModelProfile",
            "metadata": {"name": profile_id},
            "spec": spec,
        }
    )


def call_model_with_prompt(profile: ModelProfile, prompt: str) -> ModelExecutionResult:
    provider = profile.spec.provider.lower()
    gateway = (profile.spec.gateway or "").lower()
    if provider == "local" and profile.spec.model == "manual":
        fixture_response = profile.spec.invocation.get("fixtureResponse")
        if isinstance(fixture_response, str) and fixture_response.strip():
            return ModelExecutionResult(
                text=fixture_response,
                provider=profile.spec.provider,
                model=profile.spec.model,
                response_id="local-manual-fixture",
                status="completed",
                usage={},
            )
        return ModelExecutionResult(
            text="Local/manual model profile selected. No provider call was made.",
            provider=profile.spec.provider,
            model=profile.spec.model,
            status="completed",
            usage={},
        )
    if gateway == "litellm":
        return _call_litellm(profile, prompt)
    if provider == "openai":
        return _call_openai_responses(profile, prompt)
    raise ValueError(f"provider {profile.spec.provider!r} is not executable yet")


def _call_litellm(profile: ModelProfile, prompt: str) -> ModelExecutionResult:
    try:
        from litellm import completion
    except Exception as exc:
        raise ValueError("LiteLLM is not installed. Install package dependency `litellm` first.") from exc

    invocation = profile.spec.invocation or {}
    kwargs: dict[str, Any] = {
        "model": profile.spec.model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if invocation.get("maxOutputTokens"):
        kwargs["max_tokens"] = int(invocation["maxOutputTokens"])
    if invocation.get("timeoutSeconds"):
        kwargs["timeout"] = int(invocation["timeoutSeconds"])
    if invocation.get("temperature") is not None:
        kwargs["temperature"] = invocation["temperature"]
    if invocation.get("reasoningEffort"):
        kwargs["reasoning_effort"] = invocation["reasoningEffort"]

    response = completion(**kwargs)
    text = response.choices[0].message.content or ""
    usage_obj = getattr(response, "usage", None)
    usage = usage_obj.model_dump(mode="json") if hasattr(usage_obj, "model_dump") else dict(usage_obj or {})
    return ModelExecutionResult(
        text=text,
        provider=profile.spec.provider,
        model=profile.spec.model,
        response_id=getattr(response, "id", None),
        status="completed",
        usage=usage,
    )


def _call_openai_responses(profile: ModelProfile, prompt: str) -> ModelExecutionResult:
    secret_env = profile.spec.secretEnv or "OPENAI_API_KEY"
    api_key = os.environ.get(secret_env)
    if not api_key:
        raise ValueError(f"missing API key environment variable {secret_env}")

    invocation = profile.spec.invocation or {}
    reasoning_effort = invocation.get("reasoningEffort") or invocation.get("reasoning_effort")
    reasoning_summary = invocation.get("reasoningSummary") or invocation.get("reasoning_summary")
    max_output_tokens = invocation.get("maxOutputTokens") or invocation.get("max_output_tokens")

    payload: dict[str, Any] = {
        "model": profile.spec.model,
        "input": prompt,
        "store": False,
    }
    if reasoning_effort:
        payload["reasoning"] = {"effort": reasoning_effort}
        if reasoning_summary:
            payload["reasoning"]["summary"] = reasoning_summary
    if max_output_tokens:
        payload["max_output_tokens"] = int(max_output_tokens)

    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=int(invocation.get("timeoutSeconds", 240))) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"OpenAI request failed with HTTP {exc.code}: {_compact_error_body(body)}") from exc

    data = json.loads(body)
    return ModelExecutionResult(
        text=_extract_output_text(data),
        provider=profile.spec.provider,
        model=profile.spec.model,
        response_id=data.get("id"),
        status=data.get("status"),
        usage=data.get("usage"),
    )


def _managed_run_prompt(context: str) -> str:
    return f"""You are executing an AITEAMOS managed LLM run.

Use the context capsule below as the source of truth. Produce a concise work result that can be reviewed in the AITEAMOS dashboard.

Your output must include:
- Summary
- Proposed implementation or review result
- Files or modules likely affected
- Risks and required human review
- Memory proposal candidates, if any

Do not claim that you changed files, created branches, ran tests, opened a PR, or executed shell commands unless the context explicitly proves it.

{context}
"""


def worker_patch_prompt(context: str) -> str:
    return f"""You are executing an AITEAMOS managed worker run.

Use the context capsule below as the source of truth. If code changes are needed, return a unified diff in one fenced ```diff block. Keep the patch minimal and within the current assignment's declared write scope. If more context is required or the task is unsafe, do not invent a patch; explain what is blocked.

Your output must include:
- Summary
- Unified diff, if safe and sufficient
- Test commands to run, if obvious
- Risks and required human review
- Memory proposal candidates, if any

Do not claim that you ran commands or opened a PR.

{context}
"""


def _extract_output_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    chunks: list[str] = []
    for item in data.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks).strip() or json.dumps({"status": data.get("status"), "id": data.get("id")}, ensure_ascii=True)


def _append_model_output(workspace_root: Path, run_id: str, result: ModelExecutionResult) -> str:
    run_dir = workspace_root / "runs" / run_id
    output_path = run_dir / "model_output.md"
    journal_path = run_dir / "journal.md"
    previous = read_text_if_exists(journal_path) or f"# {run_id} Journal\n"
    now = datetime.now().astimezone().isoformat(timespec="milliseconds")
    section = f"""# Managed Model Result

Generated: `{now}`
Provider: `{result.provider}`
Model: `{result.model}`
Response ID: `{result.response_id or "n/a"}`
Status: `{result.status or "unknown"}`

{result.text}
"""
    write_text(output_path, section)
    journal_section = f"""

## Managed Model Result ({now})

Provider: `{result.provider}`
Model: `{result.model}`
Response ID: `{result.response_id or "n/a"}`
Status: `{result.status or "unknown"}`

{result.text}
"""
    write_text(journal_path, previous.rstrip() + journal_section)
    return f"runs/{run_id}/model_output.md"


def _with_model_output(outputs: list[Any], path: str, result: ModelExecutionResult, artifact_manifest: str) -> list[Any]:
    next_outputs = list(outputs)
    next_outputs = [
        output
        for output in next_outputs
        if not (isinstance(output, dict) and output.get("type") == "model_output" and output.get("path") == path)
    ]
    next_outputs.append(
        {
            "type": "model_output",
            "path": path,
            "provider": result.provider,
            "model": result.model,
            "responseId": result.response_id,
            "status": result.status,
            "artifactManifest": artifact_manifest,
        }
    )
    return next_outputs


def _append_event(workspace_root: Path, run_id: str, event: dict[str, Any]) -> None:
    append_run_event_record(workspace_root, run_id, event)


def _compact_error_body(body: str) -> str:
    try:
        data = json.loads(body)
        message = data.get("error", {}).get("message")
        if message:
            return str(message)
    except json.JSONDecodeError:
        pass
    return body[:500]


def _maybe_propose_memory(workspace_path: str | Path, run_id: str, text: str) -> None:
    candidate = _extract_memory_candidate(text)
    if not candidate:
        return
    index = load_workspace(workspace_path)
    run = index.runs[run_id]
    title = f"Lessons from {run_id}"
    propose_memory(
        workspace_path,
        project=run.spec.project,
        member=run.spec.member,
        assignment=run.spec.assignment,
        source_run=run_id,
        source_task=run.spec.task,
        title=title,
        content=candidate,
        kind="procedural",
        evidence=[f"runs/{run_id}/journal.md"],
        review_guidance="Auto-extracted from managed model output; human review required before approval.",
    )


def _extract_memory_candidate(text: str) -> str | None:
    marker = "memory proposal"
    lower = text.lower()
    start = lower.find(marker)
    if start < 0:
        return None
    candidate = text[start:].strip()
    for delimiter in ["\n## ", "\n# "]:
        next_section = candidate.find(delimiter, len(marker))
        if next_section > 0:
            candidate = candidate[:next_section].strip()
            break
    if len(candidate) < 32:
        return None
    if any(word in candidate.lower() for word in ["none", "no memory", "not applicable", "n/a"]):
        return None
    return candidate[:4000]
