"""Shared safety wrapper for optional external runtime adapters."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shlex
import tempfile
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx

from ..execution_contract import ExecutionEvent, ExecutionRequest, ExecutionResult
from ..execution_session_store import load_execution_sessions, save_execution_session
from ..runtime_executor_config_service import runtime_executor_config_for
from .base import blocked_result, utc_now


_REPO_MUTATION_ACTION_RE = re.compile(
    r"repo[_:-]?write|repository[_:-]?write|code[_:-]?(change|edit|mutation)|apply[_:-]?patch|implement|modify|delete",
    re.IGNORECASE,
)
_RESULT_STATUSES = {"completed", "failed", "blocked", "needs_approval", "partial", "cancelled"}
_RESULT_STATUS_ALIASES = {
    "ok": "completed",
    "success": "completed",
    "succeeded": "completed",
    "done": "completed",
    "error": "failed",
    "errored": "failed",
    "failure": "failed",
    "approval_required": "needs_approval",
    "approval-requested": "needs_approval",
    "approval_requested": "needs_approval",
    "setup_blocked": "blocked",
    "setup-blocked": "blocked",
}


class ExternalRuntimeExecutor:
    id = "external_runtime"
    display_name = "External Runtime Executor"
    capabilities: set[str] = {"agent_loop", "repo:read"}
    required_env: tuple[str, ...] = ()
    binary_env: tuple[str, ...] = ()
    command_template_env: str = ""
    model_env: str = ""
    api_base_url_env: str = ""
    api_key_env_env: str = ""
    http_endpoint_path_env: str = ""
    working_dir_env: str = ""
    mode_env: str = ""
    timeout_env: str = ""
    default_command_template = "{binary}"
    default_api_key_env = ""
    default_http_endpoint_path = ""
    default_mode = "non_destructive_inspect_and_report"
    setup_url = ""
    supported_actions: set[str] = {"answer_only", "inspect_code_repository", "append_report"}
    safety_policy = {
        "default_mode": "non_destructive_inspect_and_report",
        "repo_mutation_guard": [
            "ticket_bound",
            "approval_bound",
            "evidence_bound",
            "repo_write_capability_required",
        ],
        "completion_policy": "external_runtime_completion_must_not_be_faked",
    }
    expected_output_schema = {
        "status": "completed | failed | blocked | needs_approval | partial | cancelled",
        "report": "string",
        "evidence": "list[dict]",
        "artifacts": "list[dict]",
        "approval_requests": "list[dict]",
        "errors": "list[dict]",
        "memory_candidates": "list[dict]",
        "tool_events": "list[dict]",
        "learning_delta": "dict",
        "usage": "dict",
    }

    async def health(self) -> dict:
        config = self._runtime_config()
        missing = self._missing_env(config)
        status = "setup_blocked" if missing else "ready"
        payload = {
            "executor_id": self.id,
            "status": status,
            "detail": (
                f"{self.display_name} is not configured."
                if missing
                else f"{self.display_name} is configured for non-destructive inspect-and-report execution."
            ),
            "capabilities": sorted(self.capabilities),
            "supported_actions": sorted(self.supported_actions),
            "safety_policy": self.safety_policy,
            "delivery": self._health_delivery(config),
            "config": self._health_config(config),
            "config_env": self._health_config_env(),
            "expected_output_schema": self.expected_output_schema,
            "configured": {
                "binary": bool(config.get("binary_path")),
                "command_template": bool(config.get("command_template")),
                "model": bool(config.get("model")),
                "api_base_url": bool(config.get("api_base_url")),
                "api_key_env": bool(config.get("api_key_env")),
                "http_endpoint_path": bool(config.get("http_endpoint_path")),
                "working_dir": bool(config.get("working_dir")),
            },
        }
        if missing:
            payload["missing_env"] = missing
            payload["setup_url"] = self.setup_url
        return payload

    def _health_delivery(self, config: dict[str, Any]) -> dict[str, Any]:
        delivery_modes = []
        if self.binary_env:
            delivery_modes.append("local_cli")
        if self.http_endpoint_path_env:
            delivery_modes.append("http")
        configured_mode = "handoff"
        if config.get("binary_path"):
            configured_mode = "local_cli"
        elif config.get("api_base_url") and config.get("http_endpoint_path"):
            configured_mode = "http"
        return {
            "configured_mode": configured_mode,
            "supported_modes": delivery_modes or ["handoff"],
            "prompt_delivery": "stdin_and_prompt_file" if configured_mode == "local_cli" else ("http_json" if configured_mode == "http" else "artifact_handoff"),
            "default_mode": self.default_mode,
            "non_destructive_default": True,
        }

    def _health_config(self, config: dict[str, Any]) -> dict[str, Any]:
        return {
            "mode": config.get("mode") or self.default_mode,
            "binary_path": config.get("binary_path") or "",
            "command_template_configured": bool(config.get("command_template")),
            "working_dir": config.get("working_dir") or "",
            "model": config.get("model") or "",
            "api_base_url_configured": bool(config.get("api_base_url")),
            "api_key_env": config.get("api_key_env") or "",
            "http_endpoint_path": config.get("http_endpoint_path") or "",
            "timeout_seconds": config.get("timeout_seconds"),
        }

    def _health_config_env(self) -> dict[str, str]:
        return {
            key: value
            for key, value in {
                "binary_path": self.binary_env[0] if self.binary_env else "",
                "command_template": self.command_template_env,
                "model": self.model_env,
                "api_base_url": self.api_base_url_env,
                "api_key_env": self.api_key_env_env,
                "http_endpoint_path": self.http_endpoint_path_env,
                "working_dir": self.working_dir_env,
                "mode": self.mode_env,
                "timeout_seconds": self.timeout_env,
            }.items()
            if value
        }

    def _runtime_config(self, request: ExecutionRequest | None = None) -> dict[str, Any]:
        saved_config = runtime_executor_config_for(self.id)
        request_config: dict[str, Any] = {}
        if request is not None:
            raw_config = request.permission_policy.get("runtime_config") or request.permission_policy.get("executor_config")
            if isinstance(raw_config, dict):
                nested = raw_config.get(self.id)
                request_config = nested if isinstance(nested, dict) else raw_config

        def _value(key: str, env_name: str, default: str = "") -> str:
            return str(
                request_config.get(key)
                or saved_config.get(key)
                or (os.environ.get(env_name) if env_name else "")
                or default
            ).strip()

        timeout_raw = _value("timeout_seconds", self.timeout_env, "120")
        try:
            timeout_seconds = max(1, min(int(float(timeout_raw)), 1800))
        except ValueError:
            timeout_seconds = 120
        return {
            "binary_path": _value("binary_path", self.binary_env[0] if self.binary_env else ""),
            "command_template": _value("command_template", self.command_template_env, self.default_command_template),
            "model": _value("model", self.model_env),
            "api_base_url": _value("api_base_url", self.api_base_url_env),
            "api_key_env": _value("api_key_env", self.api_key_env_env, self.default_api_key_env),
            "http_endpoint_path": _value("http_endpoint_path", self.http_endpoint_path_env, self.default_http_endpoint_path),
            "working_dir": _value("working_dir", self.working_dir_env),
            "mode": _value("mode", self.mode_env, self.default_mode),
            "timeout_seconds": timeout_seconds,
        }

    def _missing_env(self, config: dict[str, Any] | None = None) -> list[str]:
        config = config or self._runtime_config()
        required_config_keys = {
            self.api_base_url_env: "api_base_url",
            self.api_key_env_env: "api_key_env",
            self.command_template_env: "command_template",
            self.http_endpoint_path_env: "http_endpoint_path",
            self.model_env: "model",
            self.mode_env: "mode",
            self.timeout_env: "timeout_seconds",
            self.working_dir_env: "working_dir",
        }
        if self.binary_env:
            for env_name in self.binary_env:
                required_config_keys[env_name] = "binary_path"
        missing = [
            name
            for name in self.required_env
            if not os.environ.get(name)
            and not (
                name == self.default_api_key_env
                and config.get("api_key_env")
            )
            and not config.get(required_config_keys.get(name, ""))
        ]
        if self.binary_env and not config.get("binary_path"):
            missing.append(self.binary_env[0])
        api_key_env = str(config.get("api_key_env") or "").strip()
        if api_key_env and not os.environ.get(api_key_env):
            missing.append(api_key_env)
        return list(dict.fromkeys(missing))

    def _validate_binary(self, request: ExecutionRequest, config: dict[str, Any]) -> ExecutionResult | None:
        binary_path = str(config.get("binary_path") or "").strip()
        if not binary_path:
            return None
        path = Path(binary_path).expanduser()
        if not path.exists():
            return blocked_result(
                request,
                executor_id=self.id,
                reason="executor_binary_not_found",
                detail=f"{self.display_name} binary was not found: {binary_path}",
            )
        if path.is_dir() or not os.access(path, os.X_OK):
            return blocked_result(
                request,
                executor_id=self.id,
                reason="executor_binary_not_executable",
                detail=f"{self.display_name} binary is not executable: {binary_path}",
            )
        return None

    async def stream(self, request: ExecutionRequest) -> AsyncIterator[ExecutionEvent]:
        yield ExecutionEvent(event="started", request_id=request.request_id, data={"executor_id": self.id})
        result = await self.run(request)
        if result.status == "needs_approval":
            yield ExecutionEvent(
                event="approval_requested",
                request_id=request.request_id,
                data={"approval_requests": result.approval_requests, "report": result.report},
            )
        elif result.status == "blocked":
            yield ExecutionEvent(event="blocked", request_id=request.request_id, data={"errors": result.errors, "report": result.report})
        else:
            yield ExecutionEvent(event="completed", request_id=request.request_id, data=result.model_dump(mode="json"))

    async def run(self, request: ExecutionRequest) -> ExecutionResult:
        repo_mutation = self._is_repo_mutation(request)
        mutation_blocker = self._repo_mutation_blocker(request)
        if mutation_blocker is not None:
            return mutation_blocker

        config = self._runtime_config(request)
        missing = self._missing_env(config)
        if missing:
            return blocked_result(
                request,
                executor_id=self.id,
                reason="executor_setup_blocker",
                detail=(
                    f"{self.display_name} is not configured. Missing: {', '.join(missing)}. "
                    "Configure a compatible local runtime/API adapter before dispatching work."
                ),
            )
        binary_blocker = self._validate_binary(request, config)
        if isinstance(binary_blocker, ExecutionResult):
            return binary_blocker

        if repo_mutation:
            if config.get("binary_path"):
                return self._validate_repo_mutation_result(
                    request,
                    await self._run_local_cli_inspect(request, config),
                )
            if config.get("api_base_url") and config.get("http_endpoint_path"):
                return self._validate_repo_mutation_result(
                    request,
                    await self._run_http_inspect(request, config),
                )
            return blocked_result(
                request,
                executor_id=self.id,
                reason="executor_adapter_not_implemented",
                detail=(
                    f"{self.display_name} is configured, but no local CLI or HTTP endpoint is available for approved repo mutation. "
                    "AITeamOS will not fake external runtime completion."
                ),
            )

        if self._is_non_destructive_inspect_request(request):
            if config.get("binary_path"):
                return await self._run_local_cli_inspect(request, config)
            if config.get("api_base_url") and config.get("http_endpoint_path"):
                return await self._run_http_inspect(request, config)
            return self._inspect_handoff_result(request)

        return blocked_result(
            request,
            executor_id=self.id,
            reason="executor_adapter_not_implemented",
            detail=(
                f"{self.display_name} configuration is present, but concrete execution is not implemented yet. "
                "AITeamOS will not fake external runtime completion."
            ),
        )

    def _repo_mutation_blocker(self, request: ExecutionRequest) -> ExecutionResult | None:
        if not self._is_repo_mutation(request):
            return None
        ticket_id = str(request.ticket_id or request.ticket_binding.ticket_id or "").strip()
        if request.ticket_binding.mode != "existing" or not ticket_id:
            return blocked_result(
                request,
                executor_id=self.id,
                reason="repo_mutation_ticket_binding_required",
                detail="External repo mutation must be bound to an existing AITeamOS Ticket.",
            )
        if "repo:write" not in set(request.capability_grants):
            return blocked_result(
                request,
                executor_id=self.id,
                reason="repo_mutation_capability_required",
                detail="External repo mutation requires the repo:write governance capability grant.",
            )
        if not self._has_repo_write_approval(request):
            timestamp = utc_now()
            executor_session_ref = f"{self.id}-{request.request_id}"
            checkpoint_ref = f"{self.id}:{request.request_id}"
            source_state_ref = f"state://{self.id}/{request.request_id}/repo_mutation_approval"
            approval = {
                "kind": "repo_mutation",
                "ticket_id": ticket_id,
                "executor_id": self.id,
                "reason": "External runtime repo mutation requires approval before execution.",
                "required_capability": "repo:write",
                "risk_level": "high",
                "proposed_action": {
                    "action": request.action_plan.action,
                    "ticket_id": ticket_id,
                    "executor_id": self.id,
                    "capability": "repo:write",
                    "summary": str(request.action_plan.arguments.get("message") or request.trace_context.get("source_message") or ""),
                },
                "checkpoint_ref": checkpoint_ref,
                "executor_session_ref": executor_session_ref,
                "source_state_ref": source_state_ref,
                "current_graph_node": "repo_mutation_approval_gate",
            }
            return ExecutionResult(
                request_id=request.request_id,
                executor_id=self.id,
                status="needs_approval",
                report="External repo mutation needs approval before execution.",
                output_ticket_id=ticket_id,
                trace_ref=str(request.trace_context.get("trace_ref") or ""),
                executor_session_ref=executor_session_ref,
                checkpoint_ref=checkpoint_ref,
                approval_requests=[approval],
                errors=[{"reason": "repo_mutation_approval_required", "detail": approval["reason"]}],
                learning_delta={
                    "approval_interrupt": {
                        "source": "external_runtime_guard",
                        "checkpoint_ref": checkpoint_ref,
                        "executor_session_ref": executor_session_ref,
                        "source_state_ref": source_state_ref,
                        "current_graph_node": "repo_mutation_approval_gate",
                    }
                },
                started_at=timestamp,
                finished_at=timestamp,
            )
        if not (request.expected_outputs.get("evidence") or "ticket:evidence:write" in set(request.capability_grants)):
            return blocked_result(
                request,
                executor_id=self.id,
                reason="repo_mutation_evidence_required",
                detail="External repo mutation requires evidence output so AITeamOS can write Ticket provenance.",
            )
        return None

    def _is_repo_mutation(self, request: ExecutionRequest) -> bool:
        action = request.action_plan.action
        message = str(request.action_plan.arguments.get("message") or request.trace_context.get("source_message") or "")
        return "repo:write" in set(request.capability_grants) or bool(_REPO_MUTATION_ACTION_RE.search(f"{action} {message}"))

    def _has_repo_write_approval(self, request: ExecutionRequest) -> bool:
        approvals = request.approval_policy.get("approved_capabilities")
        if isinstance(approvals, list) and "repo:write" in {str(item) for item in approvals}:
            return True
        approval_refs = request.approval_policy.get("approval_refs")
        return isinstance(approval_refs, list) and bool(approval_refs)

    def _is_non_destructive_inspect_request(self, request: ExecutionRequest) -> bool:
        if request.action_plan.action not in self.supported_actions:
            return False
        if self._is_repo_mutation(request):
            return False
        grants = set(request.capability_grants)
        return request.action_plan.action == "answer_only" or "repo:read" in grants or request.action_plan.action == "inspect_code_repository"

    def _operation(self, request: ExecutionRequest) -> str:
        return "repo_mutation" if self._is_repo_mutation(request) else "inspect"

    def _validate_repo_mutation_result(self, request: ExecutionRequest, result: ExecutionResult) -> ExecutionResult:
        if result.status != "completed":
            return result
        if not self._has_patch_or_changed_files(result):
            return result.model_copy(
                update={
                    "status": "blocked",
                    "report": (
                        f"{result.report}\n\nAITeamOS governance blocker: approved repo mutation must return "
                        "a patch, diff, or changed_files artifact."
                    ),
                    "errors": [
                        *result.errors,
                        {
                            "reason": "repo_mutation_patch_required",
                            "detail": "Approved repo mutation must return patch/diff/changed_files provenance.",
                        },
                    ],
                }
            )
        if not self._has_runtime_test_or_validation_evidence(result):
            return result.model_copy(
                update={
                    "status": "blocked",
                    "report": (
                        f"{result.report}\n\nAITeamOS governance blocker: approved repo mutation must return "
                        "runtime test evidence or validation evidence."
                    ),
                    "errors": [
                        *result.errors,
                        {
                            "reason": "repo_mutation_test_evidence_required",
                            "detail": "Approved repo mutation must return test evidence or validation evidence before ingestion.",
                        },
                    ],
                }
            )
        return result

    def _has_patch_or_changed_files(self, result: ExecutionResult) -> bool:
        for artifact in result.artifacts:
            if not isinstance(artifact, dict):
                continue
            if artifact.get("kind") in {"repo_patch", "code_patch", "patch", "changed_files"}:
                return True
            if artifact.get("patch") or artifact.get("diff") or artifact.get("diff_ref"):
                return True
            changed_files = artifact.get("changed_files")
            if isinstance(changed_files, list) and changed_files:
                return True
        return False

    def _has_runtime_test_or_validation_evidence(self, result: ExecutionResult) -> bool:
        for evidence in result.evidence:
            if not isinstance(evidence, dict):
                continue
            kind = str(evidence.get("kind") or "").lower()
            ref = str(evidence.get("ref") or evidence.get("evidence_ref") or "").lower()
            summary = str(evidence.get("summary") or "").lower()
            evidence_text = f"{kind} {ref} {summary}"
            if "test" in evidence_text or "validation" in evidence_text:
                return True
        return False

    async def _run_http_inspect(self, request: ExecutionRequest, config: dict[str, Any]) -> ExecutionResult:
        started = time.monotonic()
        timestamp = utc_now()
        ticket_id = str(request.ticket_id or request.ticket_binding.ticket_id or "").strip()
        operation = self._operation(request)
        endpoint_path = str(config.get("http_endpoint_path") or "").strip()
        url = f"{str(config.get('api_base_url') or '').rstrip('/')}/{endpoint_path.lstrip('/')}"
        headers = {
            "Content-Type": "application/json",
            "X-AITeamOS-Executor": self.id,
            "X-AITeamOS-Request-ID": request.request_id,
        }
        api_key_env = str(config.get("api_key_env") or "").strip()
        api_key = os.environ.get(api_key_env) if api_key_env else ""
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = self._prompt_payload(request, config)
        payload["delivery"] = {"kind": "http", "executor_id": self.id, "endpoint_path": endpoint_path}
        try:
            async with httpx.AsyncClient(timeout=float(config.get("timeout_seconds") or 120)) as client:
                self._record_active_http_session(request, operation=operation, endpoint_path=endpoint_path)
                request_task = asyncio.create_task(
                    client.post(url, headers=headers, json=payload),
                    name=f"{self.id}:{request.request_id}:http-request",
                )
                control_task = asyncio.create_task(
                    self._watch_http_control(request, request_task),
                    name=f"{self.id}:{request.request_id}:http-control-watch",
                )
                done, _ = await asyncio.wait(
                    {request_task, control_task},
                    timeout=float(config.get("timeout_seconds") or 120),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    await self._cancel_task(request_task)
                    await self._cancel_task(control_task)
                    return blocked_result(
                        request,
                        executor_id=self.id,
                        reason="executor_timeout",
                        detail=f"{self.display_name} timed out after {config.get('timeout_seconds')} seconds.",
                    )
                if control_task in done:
                    control_event = control_task.result()
                    if control_event:
                        await self._cancel_task(request_task)
                        elapsed_ms = int((time.monotonic() - started) * 1000)
                        return self._http_controlled_result(
                            request,
                            operation=operation,
                            endpoint_path=endpoint_path,
                            started_at=timestamp,
                            elapsed_ms=elapsed_ms,
                            control_event=control_event,
                        )
                await self._cancel_task(control_task)
                response = request_task.result()
        except httpx.TimeoutException:
            return blocked_result(
                request,
                executor_id=self.id,
                reason="executor_timeout",
                detail=f"{self.display_name} timed out after {config.get('timeout_seconds')} seconds.",
            )
        except httpx.RequestError as exc:
            return blocked_result(
                request,
                executor_id=self.id,
                reason="executor_http_request_failed",
                detail=f"{self.display_name} HTTP inspect request failed: {exc}",
            )

        elapsed_ms = int((time.monotonic() - started) * 1000)
        finished_at = utc_now()
        response_text = response.text.strip()
        if response.status_code >= 400:
            return ExecutionResult(
                request_id=request.request_id,
                executor_id=self.id,
                status="failed",
                report=response_text or f"{self.display_name} failed with HTTP {response.status_code}.",
                output_ticket_id=ticket_id,
                trace_ref=str(request.trace_context.get("trace_ref") or ""),
                executor_session_ref=f"{self.id}-{request.request_id}",
                checkpoint_ref=f"{self.id}:http:{request.request_id}",
                tool_events=[self._http_event("runtime.external.http.failed", request, endpoint_path, response.status_code, elapsed_ms)],
                errors=[
                    {
                        "reason": "executor_http_failed",
                        "detail": response_text or f"HTTP {response.status_code}",
                        "status_code": response.status_code,
                    }
                ],
                usage={"runtime_steps": 1, "http_status_code": response.status_code, "latency_ms": elapsed_ms},
                started_at=timestamp,
                finished_at=finished_at,
            )

        try:
            response_payload = response.json()
        except ValueError:
            response_payload = response_text
        normalized = self._normalize_runtime_payload(response_payload, fallback_report=response_text)
        artifact = {
            "kind": "external_runtime_http_execution",
            "executor_id": self.id,
            "display_name": self.display_name,
            "ticket_id": ticket_id,
            "operation": operation,
            "repo_mutation": operation == "repo_mutation",
            "mode": config.get("mode") or self.default_mode,
            "model": config.get("model") or "",
            "api_base_url_configured": bool(config.get("api_base_url")),
            "api_key_env": api_key_env,
            "http_endpoint_path": endpoint_path,
            "http_status_code": response.status_code,
            "response_bytes": len(response.content),
            "approval_refs": request.approval_policy.get("approval_refs", []),
            "approved_capabilities": request.approval_policy.get("approved_capabilities", []),
            "trace_ref": str(request.trace_context.get("trace_ref") or ""),
        }
        evidence = {
            "kind": "external_runtime_http_evidence",
            "ref": f"external-runtime:{self.id}:http:{request.request_id}",
            "ticket_id": ticket_id,
            "summary": f"{self.display_name} completed {operation.replace('_', ' ')} via HTTP adapter.",
        }
        return ExecutionResult(
            request_id=request.request_id,
            executor_id=self.id,
            status=str(normalized.get("status") or "completed"),
            report=str(normalized.get("report") or response_text or f"{self.display_name} completed inspect-and-report."),
            output_ticket_id=ticket_id,
            artifacts=[artifact, *self._dict_list(normalized.get("artifacts"))],
            evidence=[evidence, *self._dict_list(normalized.get("evidence"))],
            trace_ref=str(request.trace_context.get("trace_ref") or ""),
            executor_session_ref=f"{self.id}-{request.request_id}",
            checkpoint_ref=f"{self.id}:http:{request.request_id}",
            tool_events=[
                self._http_event("runtime.external.http.completed", request, endpoint_path, response.status_code, elapsed_ms),
                *self._dict_list(normalized.get("tool_events")),
            ],
            memory_candidates=self._dict_list(normalized.get("memory_candidates")),
            approval_requests=self._dict_list(normalized.get("approval_requests")),
            errors=self._dict_list(normalized.get("errors")),
            learning_delta={
                "action": request.action_plan.action,
                "executor": self.id,
                "source": "external_runtime_http",
                "runtime_result_contract": normalized.get("contract"),
                **(normalized.get("learning_delta") if isinstance(normalized.get("learning_delta"), dict) else {}),
            },
            usage={
                "runtime_steps": 1,
                "http_status_code": response.status_code,
                "latency_ms": elapsed_ms,
                "response_bytes": len(response.content),
                **(normalized.get("usage") if isinstance(normalized.get("usage"), dict) else {}),
            },
            started_at=timestamp,
            finished_at=finished_at,
        )

    async def _run_local_cli_inspect(self, request: ExecutionRequest, config: dict[str, Any]) -> ExecutionResult:
        started = time.monotonic()
        timestamp = utc_now()
        ticket_id = str(request.ticket_id or request.ticket_binding.ticket_id or "").strip()
        operation = self._operation(request)
        with tempfile.TemporaryDirectory(prefix=f"aiteamos-{self.id}-") as tmp:
            prompt_path = Path(tmp) / "execution_request.json"
            output_schema_path = Path(tmp) / "execution_result_schema.json"
            output_last_message_path = Path(tmp) / "execution_result.json"
            prompt_payload = self._prompt_payload(request, config)
            prompt_text = json.dumps(prompt_payload, ensure_ascii=False, indent=2)
            prompt_path.write_text(prompt_text, encoding="utf-8")
            output_schema_path.write_text(json.dumps(self._output_schema(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
            command = self._command_args(
                config=config,
                prompt_path=prompt_path,
                request=request,
                output_schema_path=output_schema_path,
                output_last_message_path=output_last_message_path,
            )
            env = self._runtime_env(request=request, config=config, prompt_path=prompt_path)
            cwd = str(config.get("working_dir") or request.workspace_id or os.getcwd())
            if not Path(cwd).exists():
                return blocked_result(
                    request,
                    executor_id=self.id,
                    reason="executor_working_dir_not_found",
                    detail=f"{self.display_name} working_dir was not found: {cwd}",
                )
            process: asyncio.subprocess.Process | None = None
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=cwd,
                    env=env,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                self._record_active_cli_session(request, operation=operation)
                communicate_task = asyncio.create_task(
                    process.communicate(prompt_text.encode("utf-8")),
                    name=f"{self.id}:{request.request_id}:communicate",
                )
                control_task = asyncio.create_task(
                    self._watch_cli_control(request, process),
                    name=f"{self.id}:{request.request_id}:control-watch",
                )
                done, _ = await asyncio.wait(
                    {communicate_task, control_task},
                    timeout=float(config.get("timeout_seconds") or 120),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    await self._terminate_process(process)
                    await self._cancel_task(communicate_task)
                    await self._cancel_task(control_task)
                    return blocked_result(
                        request,
                        executor_id=self.id,
                        reason="executor_timeout",
                        detail=f"{self.display_name} timed out after {config.get('timeout_seconds')} seconds.",
                    )
                if control_task in done:
                    control_event = control_task.result()
                    if control_event:
                        await self._terminate_process(process)
                        await self._cancel_task(communicate_task)
                        return self._cli_controlled_result(request, operation=operation, command=command, started_at=timestamp, control_event=control_event)
                await self._cancel_task(control_task)
                stdout, stderr = await communicate_task
                output_last_message_text = ""
                with contextlib.suppress(OSError):
                    output_last_message_text = output_last_message_path.read_text(encoding="utf-8").strip()
            except TimeoutError:
                if process is not None:
                    await self._terminate_process(process)
                return blocked_result(
                    request,
                    executor_id=self.id,
                    reason="executor_timeout",
                    detail=f"{self.display_name} timed out after {config.get('timeout_seconds')} seconds.",
                )
            except OSError as exc:
                return blocked_result(
                    request,
                    executor_id=self.id,
                    reason="executor_launch_failed",
                    detail=f"{self.display_name} failed to launch: {exc}",
                )

        finished_at = utc_now()
        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if process.returncode != 0:
            return ExecutionResult(
                request_id=request.request_id,
                executor_id=self.id,
                status="failed",
                report=stderr_text or stdout_text or f"{self.display_name} failed with exit code {process.returncode}.",
                output_ticket_id=ticket_id,
                trace_ref=str(request.trace_context.get("trace_ref") or ""),
                executor_session_ref=f"{self.id}-{request.request_id}",
                checkpoint_ref=f"{self.id}:cli:{request.request_id}",
                tool_events=[
                    self._cli_event("runtime.external.cli.failed", request, command, process.returncode, elapsed_ms, stderr_text),
                ],
                errors=[
                    {
                        "reason": "executor_cli_failed",
                        "detail": stderr_text or f"Exit code {process.returncode}",
                        "exit_code": process.returncode,
                    }
                ],
                usage={"runtime_steps": 1, "exit_code": process.returncode, "latency_ms": elapsed_ms},
                started_at=timestamp,
                finished_at=finished_at,
            )

        parse_source = output_last_message_text or stdout_text
        normalized = self._normalize_runtime_payload(self._parse_cli_output(parse_source), fallback_report=parse_source)
        artifact = {
            "kind": "external_runtime_cli_execution",
            "executor_id": self.id,
            "display_name": self.display_name,
            "ticket_id": ticket_id,
            "operation": operation,
            "repo_mutation": operation == "repo_mutation",
            "mode": config.get("mode") or self.default_mode,
            "model": config.get("model") or "",
            "api_base_url_configured": bool(config.get("api_base_url")),
            "api_key_env": config.get("api_key_env") or "",
            "command_template_configured": bool(config.get("command_template")),
            "prompt_delivery": "stdin_and_prompt_file",
            "exit_code": process.returncode,
            "stderr_summary": stderr_text[:1000],
            "stdout_bytes": len(stdout),
            "output_last_message_bytes": len(output_last_message_text.encode("utf-8")),
            "approval_refs": request.approval_policy.get("approval_refs", []),
            "approved_capabilities": request.approval_policy.get("approved_capabilities", []),
            "trace_ref": str(request.trace_context.get("trace_ref") or ""),
        }
        evidence = {
            "kind": "external_runtime_cli_evidence",
            "ref": f"external-runtime:{self.id}:cli:{request.request_id}",
            "ticket_id": ticket_id,
            "summary": f"{self.display_name} completed {operation.replace('_', ' ')} via local CLI.",
        }
        return ExecutionResult(
            request_id=request.request_id,
            executor_id=self.id,
            status=str(normalized.get("status") or "completed"),
            report=str(normalized.get("report") or stdout_text or f"{self.display_name} completed inspect-and-report."),
            output_ticket_id=ticket_id,
            artifacts=[artifact, *self._dict_list(normalized.get("artifacts"))],
            evidence=[evidence, *self._dict_list(normalized.get("evidence"))],
            trace_ref=str(request.trace_context.get("trace_ref") or ""),
            executor_session_ref=f"{self.id}-{request.request_id}",
            checkpoint_ref=f"{self.id}:cli:{request.request_id}",
            tool_events=[
                self._cli_event("runtime.external.cli.completed", request, command, process.returncode, elapsed_ms, stderr_text),
                *self._dict_list(normalized.get("tool_events")),
            ],
            memory_candidates=self._dict_list(normalized.get("memory_candidates")),
            approval_requests=self._dict_list(normalized.get("approval_requests")),
            errors=self._dict_list(normalized.get("errors")),
            learning_delta={
                "action": request.action_plan.action,
                "executor": self.id,
                "source": "external_runtime_cli",
                "runtime_result_contract": normalized.get("contract"),
                **(normalized.get("learning_delta") if isinstance(normalized.get("learning_delta"), dict) else {}),
            },
            usage={
                "runtime_steps": 1,
                "exit_code": process.returncode,
                "latency_ms": elapsed_ms,
                "stdout_bytes": len(stdout),
                "stderr_bytes": len(stderr),
                "output_last_message_bytes": len(output_last_message_text.encode("utf-8")),
                **(normalized.get("usage") if isinstance(normalized.get("usage"), dict) else {}),
            },
            started_at=timestamp,
            finished_at=finished_at,
        )

    def _prompt_payload(self, request: ExecutionRequest, config: dict[str, Any]) -> dict[str, Any]:
        return {
            "execution_request": request.model_dump(mode="json"),
            "runtime_mode": config.get("mode") or self.default_mode,
            "instructions": [
                "Run non-destructive inspect-and-report unless AITeamOS explicitly approved repo mutation.",
                "For approved repo mutation, return patch/diff or changed_files plus runtime test evidence or validation evidence.",
                "Return JSON with report, evidence, artifacts, memory_candidates, learning_delta, and usage when possible.",
                "When an output schema is supplied, include empty arrays/objects for fields with no values.",
                "Do not replace AITeamOS Ticket ledger, Employee ledger, Review Queue, or durable memory.",
            ],
            "expected_output_schema": {
                **self.expected_output_schema,
            },
        }

    def _command_args(
        self,
        *,
        config: dict[str, Any],
        prompt_path: Path,
        request: ExecutionRequest,
        output_schema_path: Path | None = None,
        output_last_message_path: Path | None = None,
    ) -> list[str]:
        binary = str(config.get("binary_path") or "").strip()
        values = {
            "binary": shlex.quote(binary),
            "prompt_path": shlex.quote(str(prompt_path)),
            "output_schema_path": shlex.quote(str(output_schema_path or "")),
            "output_last_message_path": shlex.quote(str(output_last_message_path or "")),
            "model": shlex.quote(str(config.get("model") or "")),
            "api_base_url": shlex.quote(str(config.get("api_base_url") or "")),
            "working_dir": shlex.quote(str(config.get("working_dir") or request.workspace_id or "")),
            "request_id": shlex.quote(request.request_id),
            "ticket_id": shlex.quote(str(request.ticket_id or request.ticket_binding.ticket_id or "")),
        }
        template = str(config.get("command_template") or self.default_command_template or "{binary}")
        rendered = template.format(**values)
        return shlex.split(rendered)

    def _output_schema(self) -> dict[str, Any]:
        simple_ref = {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "ref", "summary", "detail"],
            "properties": {
                "kind": {"type": "string"},
                "ref": {"type": "string"},
                "summary": {"type": "string"},
                "detail": {"type": "string"},
            },
        }
        artifact = {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "ref", "summary", "path", "diff", "changed_files"],
            "properties": {
                "kind": {"type": "string"},
                "ref": {"type": "string"},
                "summary": {"type": "string"},
                "path": {"type": "string"},
                "diff": {"type": "string"},
                "changed_files": {"type": "array", "items": {"type": "string"}},
            },
        }
        memory_candidate = {
            "type": "object",
            "additionalProperties": False,
            "required": ["content", "memory_type", "source_kind", "source_ref", "scope_kind", "scope_ref", "confidence"],
            "properties": {
                "content": {"type": "string"},
                "memory_type": {"type": "string"},
                "source_kind": {"type": "string"},
                "source_ref": {"type": "string"},
                "scope_kind": {"type": "string"},
                "scope_ref": {"type": "string"},
                "confidence": {"type": "number"},
            },
        }
        summary_object = {
            "type": "object",
            "additionalProperties": False,
            "required": ["summary", "source", "action", "status", "executor_id", "ticket_id"],
            "properties": {
                "summary": {"type": "string"},
                "source": {"type": "string"},
                "action": {"type": "string"},
                "status": {"type": "string"},
                "executor_id": {"type": "string"},
                "ticket_id": {"type": "string"},
            },
        }
        return {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "status",
                "report",
                "evidence",
                "artifacts",
                "approval_requests",
                "errors",
                "memory_candidates",
                "tool_events",
                "learning_delta",
                "usage",
            ],
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["completed", "failed", "blocked", "needs_approval", "partial", "cancelled"],
                },
                "report": {"type": "string"},
                "evidence": {"type": "array", "items": simple_ref},
                "artifacts": {"type": "array", "items": artifact},
                "approval_requests": {"type": "array", "items": simple_ref},
                "errors": {"type": "array", "items": simple_ref},
                "memory_candidates": {"type": "array", "items": memory_candidate},
                "tool_events": {"type": "array", "items": simple_ref},
                "learning_delta": summary_object,
                "usage": summary_object,
            },
        }

    def _runtime_env(self, *, request: ExecutionRequest, config: dict[str, Any], prompt_path: Path) -> dict[str, str]:
        env = os.environ.copy()
        env.update(
            {
                "AITEAMOS_EXECUTOR_ID": self.id,
                "AITEAMOS_EXECUTION_REQUEST_ID": request.request_id,
                "AITEAMOS_TICKET_ID": str(request.ticket_id or request.ticket_binding.ticket_id or ""),
                "AITEAMOS_EMPLOYEE_ID": request.employee_id,
                "AITEAMOS_RUNTIME_MODE": str(config.get("mode") or self.default_mode),
                "AITEAMOS_PROMPT_PATH": str(prompt_path),
            }
        )
        if config.get("model"):
            env["AITEAMOS_LLM_MODEL"] = str(config["model"])
        if config.get("api_base_url"):
            env["AITEAMOS_LLM_BASE_URL"] = str(config["api_base_url"])
        if config.get("api_key_env"):
            env["AITEAMOS_LLM_API_KEY_ENV"] = str(config["api_key_env"])
        return env

    def _record_active_cli_session(self, request: ExecutionRequest, *, operation: str) -> None:
        workspace = _workspace_dir()
        thread_id = str(request.trace_context.get("thread_id") or request.request_id)
        ticket_id = str(request.ticket_id or request.ticket_binding.ticket_id or "")
        save_execution_session(
            workspace,
            employee_id=request.employee_id,
            thread_id=thread_id,
            ticket_id=ticket_id,
            executor_id=self.id,
            executor_session_ref=f"{self.id}-{request.request_id}",
            checkpoint_ref=f"{self.id}:cli:{request.request_id}",
            last_request_id=request.request_id,
            status="running",
            trace_ref=str(request.trace_context.get("trace_ref") or ""),
            current_graph_node="external_runtime_cli",
            tool_events=[
                {
                    "event": "runtime.external.cli.started",
                    "detail": f"{self.display_name} started {operation.replace('_', ' ')} via local CLI.",
                    "data": {"request_id": request.request_id, "executor_id": self.id, "operation": operation},
                }
            ],
            updated_at=utc_now(),
        )

    def _record_active_http_session(self, request: ExecutionRequest, *, operation: str, endpoint_path: str) -> None:
        workspace = _workspace_dir()
        thread_id = str(request.trace_context.get("thread_id") or request.request_id)
        ticket_id = str(request.ticket_id or request.ticket_binding.ticket_id or "")
        save_execution_session(
            workspace,
            employee_id=request.employee_id,
            thread_id=thread_id,
            ticket_id=ticket_id,
            executor_id=self.id,
            executor_session_ref=f"{self.id}-{request.request_id}",
            checkpoint_ref=f"{self.id}:http:{request.request_id}",
            last_request_id=request.request_id,
            status="running",
            trace_ref=str(request.trace_context.get("trace_ref") or ""),
            current_graph_node="external_runtime_http",
            tool_events=[
                {
                    "event": "runtime.external.http.started",
                    "detail": f"{self.display_name} started {operation.replace('_', ' ')} through HTTP adapter.",
                    "data": {
                        "request_id": request.request_id,
                        "executor_id": self.id,
                        "operation": operation,
                        "endpoint_path": endpoint_path,
                    },
                }
            ],
            updated_at=utc_now(),
        )

    async def _watch_cli_control(self, request: ExecutionRequest, process: asyncio.subprocess.Process) -> dict[str, Any] | None:
        while process.returncode is None:
            control = self._active_control_for_request(request)
            if control is not None:
                return control
            await asyncio.sleep(0.05)
        return None

    async def _watch_http_control(self, request: ExecutionRequest, request_task: asyncio.Task[Any]) -> dict[str, Any] | None:
        while not request_task.done():
            control = self._active_control_for_request(request)
            if control is not None:
                return control
            await asyncio.sleep(0.05)
        return None

    def _active_control_for_request(self, request: ExecutionRequest) -> dict[str, Any] | None:
        ticket_id = str(request.ticket_id or request.ticket_binding.ticket_id or "").strip()
        executor_session_ref = f"{self.id}-{request.request_id}"
        for session in load_execution_sessions(_workspace_dir()).values():
            if str(session.get("last_request_id") or "") != request.request_id and str(session.get("executor_session_ref") or "") != executor_session_ref:
                continue
            if ticket_id and str(session.get("ticket_id") or "") != ticket_id:
                continue
            control = session.get("control_state") if isinstance(session.get("control_state"), dict) else {}
            action = str(control.get("action") or "").strip().lower()
            if action in {"stop", "pause", "cancel"}:
                return control
        return None

    async def _terminate_process(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=2)
        except TimeoutError:
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass
        except ProcessLookupError:
            pass

    async def _cancel_task(self, task: asyncio.Task[Any]) -> None:
        if task.done():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    def _cli_controlled_result(
        self,
        request: ExecutionRequest,
        *,
        operation: str,
        command: list[str],
        started_at: str,
        control_event: dict[str, Any],
    ) -> ExecutionResult:
        finished_at = utc_now()
        action = str(control_event.get("action") or "cancel").strip().lower()
        reason = str(control_event.get("reason") or f"Ticket loop control requested {action}.")
        return ExecutionResult(
            request_id=request.request_id,
            executor_id=self.id,
            status="cancelled",
            report=f"{self.display_name} was interrupted in-flight by Ticket control: {action}. {reason}",
            output_ticket_id=str(request.ticket_id or request.ticket_binding.ticket_id or ""),
            trace_ref=str(request.trace_context.get("trace_ref") or ""),
            executor_session_ref=f"{self.id}-{request.request_id}",
            checkpoint_ref=f"{self.id}:cli:{request.request_id}",
            tool_events=[
                self._cli_event("runtime.external.cli.interrupted", request, command, -1, 0, reason),
            ],
            errors=[{"reason": "external_runtime_interrupted", "detail": reason, "action": action}],
            learning_delta={
                "action": request.action_plan.action,
                "executor": self.id,
                "source": "external_runtime_cli",
                "interrupt": {"action": action, "reason": reason, "in_flight": True},
            },
            usage={"runtime_steps": 1, "interrupted": True, "control_action": action},
            started_at=started_at,
            finished_at=finished_at,
        )

    def _http_controlled_result(
        self,
        request: ExecutionRequest,
        *,
        operation: str,
        endpoint_path: str,
        started_at: str,
        elapsed_ms: int,
        control_event: dict[str, Any],
    ) -> ExecutionResult:
        finished_at = utc_now()
        action = str(control_event.get("action") or "cancel").strip().lower()
        reason = str(control_event.get("reason") or f"Ticket loop control requested {action}.")
        return ExecutionResult(
            request_id=request.request_id,
            executor_id=self.id,
            status="cancelled",
            report=f"{self.display_name} HTTP request was cancelled in-flight by Ticket control: {action}. {reason}",
            output_ticket_id=str(request.ticket_id or request.ticket_binding.ticket_id or ""),
            trace_ref=str(request.trace_context.get("trace_ref") or ""),
            executor_session_ref=f"{self.id}-{request.request_id}",
            checkpoint_ref=f"{self.id}:http:{request.request_id}",
            tool_events=[
                self._http_event("runtime.external.http.interrupted", request, endpoint_path, None, elapsed_ms),
            ],
            errors=[{"reason": "external_runtime_interrupted", "detail": reason, "action": action}],
            learning_delta={
                "action": request.action_plan.action,
                "executor": self.id,
                "source": "external_runtime_http",
                "interrupt": {
                    "action": action,
                    "reason": reason,
                    "in_flight": True,
                    "request_cancelled": True,
                    "operation": operation,
                },
            },
            usage={"runtime_steps": 1, "interrupted": True, "control_action": action, "http_request_cancelled": True},
            started_at=started_at,
            finished_at=finished_at,
        )

    def _parse_cli_output(self, stdout_text: str) -> Any:
        if not stdout_text:
            return {"report": ""}
        try:
            payload = json.loads(stdout_text)
        except json.JSONDecodeError:
            return {"report": stdout_text}
        return payload if isinstance(payload, dict) else {"report": stdout_text}

    def _normalize_runtime_payload(self, payload: Any, *, fallback_report: str = "") -> dict[str, Any]:
        normalized = dict(payload) if isinstance(payload, dict) else {"report": str(fallback_report or payload or "")}
        errors = self._dict_list(normalized.get("errors"))
        explicit_status = normalized.get("status") is not None
        raw_status = str(normalized.get("status") or "completed").strip().lower()
        status = _RESULT_STATUS_ALIASES.get(raw_status, raw_status.replace("-", "_"))
        contract = {"status": "valid", "warnings": []}
        if status not in _RESULT_STATUSES:
            contract["status"] = "invalid"
            contract["warnings"].append(f"unknown_status:{raw_status}")
            errors.append(
                {
                    "reason": "runtime_result_contract_invalid_status",
                    "detail": f"External runtime returned unsupported status: {raw_status}",
                }
            )
            status = "failed"
        report = str(
            normalized.get("report")
            or normalized.get("summary")
            or normalized.get("message")
            or normalized.get("text")
            or ""
        ).strip()
        if isinstance(payload, dict) and not report:
            contract["status"] = "invalid"
            contract["warnings"].append("missing_report")
            errors.append(
                {
                    "reason": "runtime_result_contract_missing_report",
                    "detail": "External runtime result must include report/summary/message/text.",
                }
            )
            if status == "completed" or not explicit_status:
                status = "blocked"
            report = f"{self.display_name} returned an invalid ExecutionResult payload: missing report."
        normalized["status"] = status
        normalized["report"] = report or str(fallback_report or f"{self.display_name} completed inspect-and-report.")
        normalized["errors"] = errors
        normalized["contract"] = contract
        return normalized

    def _dict_list(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def _cli_event(
        self,
        event: str,
        request: ExecutionRequest,
        command: list[str],
        exit_code: int | None,
        elapsed_ms: int,
        stderr_text: str,
    ) -> dict[str, Any]:
        return {
            "event": event,
            "detail": f"{self.display_name} local CLI execution event.",
            "data": {
                "command": {"id": f"runtime.external:{self.id}:cli", "capability": self.id, "operation": "inspect"},
                "executor_id": self.id,
                "ticket_id": str(request.ticket_id or request.ticket_binding.ticket_id or ""),
                "argv0": command[0] if command else "",
                "exit_code": exit_code,
                "latency_ms": elapsed_ms,
                "stderr_summary": stderr_text[:1000],
            },
        }

    def _http_event(
        self,
        event: str,
        request: ExecutionRequest,
        endpoint_path: str,
        status_code: int | None,
        elapsed_ms: int,
    ) -> dict[str, Any]:
        return {
            "event": event,
            "detail": f"{self.display_name} HTTP execution event.",
            "data": {
                "command": {"id": f"runtime.external:{self.id}:http", "capability": self.id, "operation": "inspect"},
                "executor_id": self.id,
                "ticket_id": str(request.ticket_id or request.ticket_binding.ticket_id or ""),
                "endpoint_path": endpoint_path,
                "status_code": status_code,
                "latency_ms": elapsed_ms,
            },
        }

    def _inspect_handoff_result(self, request: ExecutionRequest) -> ExecutionResult:
        timestamp = utc_now()
        ticket_id = str(request.ticket_id or request.ticket_binding.ticket_id or "").strip()
        task_summary = str(
            request.action_plan.arguments.get("message")
            or request.action_plan.arguments.get("query")
            or request.task_context.get("task_summary")
            or ""
        ).strip()
        repository_scope = request.task_context.get("repository_scope")
        artifact = {
            "kind": "external_runtime_inspect_handoff",
            "executor_id": self.id,
            "display_name": self.display_name,
            "ticket_id": ticket_id,
            "task_summary": task_summary,
            "repository_scope": repository_scope if isinstance(repository_scope, dict) else {},
            "capability_grants": list(request.capability_grants),
            "approval_policy": {
                "requires_approval_for": request.approval_policy.get("require_approval_for", []),
                "approved_capabilities": request.approval_policy.get("approved_capabilities", []),
            },
            "external_execution_status": "not_started",
        }
        evidence = {
            "kind": "external_runtime_handoff_evidence",
            "ref": f"external-runtime:{self.id}:{request.request_id}",
            "ticket_id": ticket_id,
            "summary": f"Prepared non-destructive inspect-and-report handoff for {self.display_name}.",
        }
        report = (
            f"Prepared non-destructive inspect-and-report handoff for {self.display_name}. "
            "No repo mutation was executed, and no external runtime completion is being faked."
        )
        if task_summary:
            report += f"\n\nTask: {task_summary}"
        return ExecutionResult(
            request_id=request.request_id,
            executor_id=self.id,
            status="partial",
            report=report,
            output_ticket_id=ticket_id,
            artifacts=[artifact],
            evidence=[evidence],
            trace_ref=str(request.trace_context.get("trace_ref") or ""),
            executor_session_ref=f"{self.id}-{request.request_id}",
            checkpoint_ref=f"{self.id}:handoff:{request.request_id}",
            tool_events=[
                {
                    "event": "runtime.external.inspect_handoff.prepared",
                    "detail": f"{self.display_name} inspect-and-report handoff package was prepared.",
                    "data": {
                        "executor_id": self.id,
                        "ticket_id": ticket_id,
                        "artifact": artifact,
                        "evidence": evidence,
                    },
                }
            ],
            learning_delta={
                "action": request.action_plan.action,
                "executor": self.id,
                "source": "external_runtime_inspect_handoff",
            },
            usage={"runtime_steps": 1, "external_execution": "not_started"},
            started_at=timestamp,
            finished_at=timestamp,
        )


def _workspace_root() -> Path:
    configured = os.environ.get("AITEAMOS_WORKSPACE_DIR")
    return Path(configured).resolve() if configured else Path.cwd().resolve()


def _workspace_dir() -> Path:
    root = _workspace_root()
    return root if root.name == ".aiteamos" else root / ".aiteamos"
