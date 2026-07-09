"""Deterministic AITeamOS governance actions behind the runtime boundary."""

from __future__ import annotations

import re
import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from ..chat_engine_thread_store import delete_engine_thread_states
from ..chat_terminal_utils import (
    extract_terminal_command_line,
    run_terminal_command_collect,
    terminal_argv_from_command,
    terminal_cwd_from_raw,
    terminal_evidence_ref,
    terminal_reply,
    terminal_report_content,
    validate_terminal_workspace_args,
)
from ..chat_kernel_permission_utils import build_permissions_reply, command_access_rows
from ..execution_contract import ExecutionEvent, ExecutionRequest, ExecutionResult
from ..kernel_command_service import expand_employee_permissions
from ..knowledge_service import search_knowledge_sync
from ..memory_service import MemoryRecallUsefulnessReviewRequest, review_memory_recall_usage
from ..repository_service import CodeRepository, get_code_repository, inspect_code_repository, list_code_repositories
from ..ticket_service import (
    TicketCreateRequest,
    TicketReportRequest,
    add_ticket_report,
    create_ticket,
    get_ticket,
    self_bootstrap_learning_summary,
    ticket_asset_records,
    ticket_backend_status,
)
from ..validation_skill_catalog import VALIDATION_SKILL_DEFINITIONS
from .base import blocked_result, utc_now


class LocalToolExecutor:
    id = "local_tool"
    display_name = "Local Governance Tool Executor"
    capabilities = {
        "list_employees",
        "create_employee",
        "edit_employee_profile",
        "delete_employee",
        "list_skills",
        "create_skill",
        "assign_skill_to_employee",
        "delete_skill",
        "inspect_permissions",
        "search_knowledge",
        "self_bootstrap_close",
        "self_bootstrap_start",
        "self_bootstrap_summary",
        "list_code_repositories",
        "inspect_code_repository",
        "terminal_run",
        "stream",
    }

    async def health(self) -> dict:
        return {
            "executor_id": self.id,
            "status": "ready",
            "detail": "Deterministic governance actions are available.",
            "capabilities": sorted(self.capabilities),
        }

    async def stream(self, request: ExecutionRequest) -> AsyncIterator[ExecutionEvent]:
        yield ExecutionEvent(event="started", request_id=request.request_id, data={"executor_id": self.id})
        result = await self.run(request)
        if result.status == "blocked":
            yield ExecutionEvent(event="blocked", request_id=request.request_id, data={"errors": result.errors, "report": result.report})
            yield ExecutionEvent(event="completed", request_id=request.request_id, data=result.model_dump(mode="json"))
        else:
            for event in result.tool_events:
                yield ExecutionEvent(event="tool_event", request_id=request.request_id, data=event)
            yield ExecutionEvent(event="delta", request_id=request.request_id, data={"text": result.report})
            yield ExecutionEvent(event="completed", request_id=request.request_id, data=result.model_dump(mode="json"))

    async def run(self, request: ExecutionRequest) -> ExecutionResult:
        action = request.action_plan.action
        if action not in self.capabilities:
            return blocked_result(
                request,
                executor_id=self.id,
                reason="unsupported_action",
                detail=f"LocalToolExecutor does not support action '{action}'.",
            )
        started_at = utc_now()
        if action == "inspect_permissions":
            report, payload, command_id = self._inspect_permissions(request)
        elif action == "list_employees":
            report, payload, command_id = self._list_employees(request)
        elif action == "create_employee":
            return self._create_employee_result(request, started_at=started_at)
        elif action == "edit_employee_profile":
            return self._edit_employee_result(request, started_at=started_at)
        elif action == "delete_employee":
            return self._delete_employee_result(request, started_at=started_at)
        elif action == "list_skills":
            report, payload, command_id = self._list_skills(request)
        elif action == "create_skill":
            return self._create_skill_result(request, started_at=started_at)
        elif action == "assign_skill_to_employee":
            return self._assign_skill_result(request, started_at=started_at)
        elif action == "delete_skill":
            return self._delete_skill_result(request, started_at=started_at)
        elif action == "search_knowledge":
            report, payload, command_id = self._search_knowledge(request)
        elif action == "list_code_repositories":
            report, payload, command_id = self._list_code_repositories()
        elif action == "inspect_code_repository":
            return self._inspect_code_repository_result(request, started_at=started_at)
        elif action == "self_bootstrap_start":
            return self._self_bootstrap_start_result(request, started_at=started_at)
        elif action == "self_bootstrap_close":
            return self._self_bootstrap_close_result(request, started_at=started_at)
        elif action == "terminal_run":
            return await self._terminal_run_result(request, started_at=started_at)
        else:
            report, payload, command_id = self._self_bootstrap_summary()
        finished_at = utc_now()
        return ExecutionResult(
            request_id=request.request_id,
            executor_id=self.id,
            status="completed",
            report=report,
            output_ticket_id=request.ticket_id,
            trace_ref=str(request.trace_context.get("trace_ref") or ""),
            executor_session_ref=f"local-{request.request_id}",
            checkpoint_ref=f"local:{request.request_id}",
            tool_events=[
                self._command_event("command.called", command_id, {"status": "called"}),
                self._command_event("command.completed", command_id, payload),
            ],
            learning_delta={"action": action, "executor": self.id, "source": "local_tool_executor"},
            usage={"runtime_steps": 1},
            started_at=started_at,
            finished_at=finished_at,
        )

    def _employee_profiles(self, request: ExecutionRequest) -> list[dict[str, Any]]:
        profiles = request.task_context.get("employee_profiles")
        if not isinstance(profiles, list):
            profiles = []
        return [profile for profile in profiles if isinstance(profile, dict)]

    def _employee_summary(self, profile: dict[str, Any]) -> dict[str, str]:
        return {
            "id": str(profile.get("id") or "").strip(),
            "display_name": str(profile.get("display_name") or profile.get("name") or profile.get("id") or "").strip(),
            "role": str(profile.get("role") or "").strip(),
        }

    def _target_profile(self, request: ExecutionRequest) -> dict[str, Any]:
        profiles = self._employee_profiles(request)
        employee = request.task_context.get("employee") if isinstance(request.task_context.get("employee"), dict) else {}
        target = str(request.action_plan.arguments.get("target_employee_hint") or "").strip().lower()
        message = str(request.action_plan.arguments.get("message") or request.trace_context.get("source_message") or "").lower()
        if target:
            for profile in profiles:
                summary = self._employee_summary(profile)
                if target in {summary["id"].lower(), summary["display_name"].lower()}:
                    return profile
        for profile in profiles:
            summary = self._employee_summary(profile)
            if summary["id"].lower() and re.search(rf"\b{re.escape(summary['id'].lower())}\b", message):
                return profile
            if summary["display_name"].lower() and summary["display_name"].lower() in message:
                return profile
        for profile in profiles:
            if str(profile.get("id") or "").strip() == str(employee.get("id") or "").strip():
                return profile
        return employee

    def _inspect_permissions(self, request: ExecutionRequest) -> tuple[str, dict[str, Any], str]:
        profile = self._target_profile(request)
        summary = self._employee_summary(profile)
        raw_permissions = [str(permission) for permission in profile.get("permissions", []) if str(permission).strip()]
        expanded_permissions = sorted(expand_employee_permissions(raw_permissions))
        command_rows = command_access_rows(raw_permissions)
        prefers_chinese = any("\u4e00" <= char <= "\u9fff" for char in str(request.trace_context.get("source_message") or ""))
        payload = {
            "status": "completed",
            "detail": f"Inspected Kernel permissions for employee: {summary['id']}",
            "employee": summary,
            "raw_permissions": raw_permissions,
            "expanded_permissions": expanded_permissions,
            "commands": command_rows,
        }
        report = build_permissions_reply(
            employee_display_name=summary["display_name"] or summary["id"],
            employee_id=summary["id"],
            employee_role=summary["role"],
            raw_permissions=raw_permissions,
            expanded_permissions=expanded_permissions,
            commands=command_rows,
            prefers_chinese=prefers_chinese,
        )
        return report, payload, "kernel.permissions:inspect"

    def _list_employees(self, request: ExecutionRequest) -> tuple[str, dict[str, Any], str]:
        profiles = self._employee_profiles(request)
        employees = [self._employee_summary(profile) for profile in profiles]
        employees = [employee for employee in employees if employee["id"]]
        employees.sort(key=lambda employee: employee["id"])
        lines = [f"我找到了 {len(employees)} 个成员。", ""]
        if not employees:
            lines.append("- none")
        for employee in employees:
            lines.append(f"- {employee['display_name']} ({employee['id']})；role={employee['role'] or '-'}")
        lines.extend(["", "入口：", "- Employees: #/employees"])
        payload = {
            "status": "completed",
            "detail": "Listed Employee workforce records.",
            "employees": employees,
        }
        return "\n".join(lines), payload, "employees.manage:list"

    def _workspace_root(self, request: ExecutionRequest) -> Path:
        explicit = os.environ.get("AITEAMOS_WORKSPACE_DIR")
        if explicit:
            return Path(explicit).expanduser().resolve()
        value = str(request.workspace_id or "").strip()
        if value and value != "local":
            return Path(value).expanduser().resolve()
        return Path.cwd().resolve()

    def _workspace_dir(self, request: ExecutionRequest) -> Path:
        return self._workspace_root(request) / ".aiteamos"

    def _employees_dir(self, request: ExecutionRequest) -> Path:
        return self._workspace_dir(request) / "employees"

    def _skills_dir(self, request: ExecutionRequest) -> Path:
        return self._workspace_dir(request) / "skills"

    def _read_yaml(self, path: Path) -> dict[str, Any]:
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, yaml.YAMLError):
            payload = {}
        return payload if isinstance(payload, dict) else {}

    def _write_yaml(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")

    def _slugify_id(self, value: str, *, prefix: str) -> str:
        slug = re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-_")
        slug = re.sub(r"-{2,}", "-", slug)
        return (slug or f"{prefix}-{uuid4().hex[:8]}")[:80]

    def _find_employee_file(self, request: ExecutionRequest, lookup: str) -> tuple[Path, dict[str, Any]] | None:
        normalized = lookup.strip().lower()
        if not normalized:
            return None
        employees_dir = self._employees_dir(request)
        if not employees_dir.exists():
            return None
        for path in sorted(employees_dir.glob("*.yaml")):
            profile = self._read_yaml(path)
            profile_id = str(profile.get("id") or path.stem)
            display_name = str(profile.get("display_name") or profile_id)
            if normalized in {profile_id.lower(), display_name.lower()}:
                profile.setdefault("id", profile_id)
                return path, profile
        return None

    def _employee_payload(self, profile: dict[str, Any]) -> dict[str, Any]:
        employee_id = str(profile.get("id") or "").strip()
        return {
            "id": employee_id,
            "display_name": str(profile.get("display_name") or employee_id).strip(),
            "kind": str(profile.get("kind") or "ai").strip(),
            "role": str(profile.get("role") or "").strip(),
            "summary": str(profile.get("summary") or "").strip(),
            "skills": [str(item) for item in profile.get("skills", []) if str(item).strip()],
        }

    def _action_message(self, request: ExecutionRequest) -> str:
        return str(request.action_plan.arguments.get("message") or request.trace_context.get("source_message") or "")

    def _arg_str(self, request: ExecutionRequest, *names: str) -> str:
        for name in names:
            value = request.action_plan.arguments.get(name)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _arg_list(self, request: ExecutionRequest, *names: str) -> list[str]:
        for name in names:
            value = request.action_plan.arguments.get(name)
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()]
            if isinstance(value, str) and value.strip():
                return [item.strip(" ,，") for item in re.split(r"[,，、]\s*|\s+and\s+", value) if item.strip(" ,，")]
        return []

    def _extract_first(self, patterns: list[str], message: str) -> str:
        for pattern in patterns:
            match = re.search(pattern, message, flags=re.IGNORECASE)
            if not match:
                continue
            value = re.sub(r"\s+", " ", match.group(1)).strip(" :：,，。;；")
            if value:
                return value
        return ""

    def _display_name_from_message(self, message: str) -> str:
        return self._extract_first(
            [
                r"(?:名字叫|名为|叫做|叫)\s*([A-Za-z][A-Za-z0-9_. -]{0,63}|[\u4e00-\u9fff]{1,16})",
                r"(?:display_name|name)\s*[:=：]\s*([A-Za-z][A-Za-z0-9_. -]{0,63})",
                r"\bname\s*=\s*([A-Za-z][A-Za-z0-9_. -]{0,63})",
            ],
            message,
        )

    def _role_from_message(self, message: str, *, require_marker: bool = False) -> str:
        explicit = self._extract_first(
            [r"(?:角色|定位|role)\s*(?:是|为|改成|改为|更新为|设置为|to|=|:|：)\s*([^,，。;；\n]+)"],
            message,
        )
        value = explicit or ("" if require_marker else message)
        lowered = f" {value.lower()} "
        if "pv" in lowered or "验证" in value:
            return "AI PV"
        if "release" in lowered or "发布" in value:
            return "AI Release"
        if "architect" in lowered or "架构" in value:
            return "AI Architect"
        if "qa" in lowered or "harness" in lowered or "测试" in value:
            return "AI QA / Harness Runner"
        if "memory" in lowered or "记忆" in value:
            return "AI Memory Curator"
        if any(token in lowered for token in ("rd", "implementer", "developer", "engineer")) or any(token in value for token in ("研发", "开发")):
            return "AI RD / Implementer"
        return explicit.strip() if explicit else ""

    def _summary_from_message(self, message: str) -> str:
        return self._extract_first(
            [
                r"(?:summary|简介|摘要|描述)\s*(?:是|为|改成|改为|更新为|设置为|to|=|:|：)\s*([^,，。;；\n]+)",
                r"(?:负责|职责是|职责为)\s*([^,，。;；\n]+)",
            ],
            message,
        )

    def _skills_from_message(self, message: str) -> list[str]:
        value = self._extract_first(
            [
                r"(?:skills?|技能)\s*(?:是|为|改成|改为|更新为|设置为|to|=|:|：)\s*([^。;；\n]+)",
                r"(?:添加|增加|分配|add|assign)\s*(?:skills?|技能)\s*[:=：]?\s*([^。;；\n]+)",
            ],
            message,
        )
        if not value:
            return []
        return [item.strip(" ,，") for item in re.split(r"[,，、]\s*|\s+and\s+", value) if item.strip(" ,，")]

    def _default_skills_for_role(self, role: str) -> list[str]:
        defaults = {
            "AI Team OS Manager": ["ticket-specification", "employee-ticket-flow-design", "technical-decision", "validation-strategy", "product-model-review"],
            "AI Architect": ["system-architecture-design", "architecture-review", "technical-decision", "product-model-review"],
            "AI PV": ["test-engineering", "validation-strategy", "evidence-review", "regression-check", "product-model-review"],
            "AI Release": ["resource-planning", "validation-strategy", "evidence-review", "regression-check"],
            "AI QA / Harness Runner": ["test-engineering", "validation-strategy", "evidence-review", "regression-check"],
            "AI Memory Curator": ["technical-decision"],
            "AI RD / Implementer": ["backend-api-implementation", "frontend-api-integration", "test-engineering"],
        }
        return list(defaults.get(role, []))

    def _default_summary(self, display_name: str, role: str, responsibility: str) -> str:
        if responsibility:
            return f"{display_name} focuses on {responsibility}."
        return f"File-backed {role or 'AI Employee'} profile."

    def _dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            item = str(value).strip()
            if not item or item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result

    def _governance_result(
        self,
        request: ExecutionRequest,
        *,
        started_at: str,
        status: str,
        report: str,
        command_id: str,
        payload: dict[str, Any],
    ) -> ExecutionResult:
        finished_at = utc_now()
        phase = "completed" if status == "completed" else "blocked"
        return ExecutionResult(
            request_id=request.request_id,
            executor_id=self.id,
            status=status,
            report=report,
            output_ticket_id=request.ticket_id,
            artifacts=[{"kind": "local_governance_action", **payload}],
            trace_ref=str(request.trace_context.get("trace_ref") or ""),
            executor_session_ref=f"local-{request.request_id}",
            checkpoint_ref=f"local:{request.request_id}",
            tool_events=[
                self._command_event("command.called", command_id, {"status": "called"}),
                self._command_event(f"command.{phase}", command_id, payload),
            ],
            learning_delta={"action": request.action_plan.action, "executor": self.id, "source": "local_tool_executor"},
            usage={"runtime_steps": 1},
            errors=[] if status == "completed" else [{"reason": str(payload.get("reason") or "local_governance_blocked"), "detail": str(payload.get("detail") or report)}],
            started_at=started_at,
            finished_at=finished_at,
        )

    def _create_employee_result(self, request: ExecutionRequest, *, started_at: str) -> ExecutionResult:
        message = self._action_message(request)
        display_name = self._arg_str(request, "display_name", "name") or self._display_name_from_message(message)
        if not display_name:
            payload = {"status": "blocked", "reason": "missing_display_name", "detail": "Employee display name was not found."}
            return self._governance_result(request, started_at=started_at, status="blocked", report="没有识别到成员名字。", command_id="employees.manage:create", payload=payload)
        employee_id = self._slugify_id(self._arg_str(request, "employee_id", "id") or display_name, prefix="employee")
        if self._find_employee_file(request, employee_id) or self._find_employee_file(request, display_name):
            payload = {"status": "blocked", "reason": "employee_already_exists", "detail": f"Employee already exists: {employee_id}"}
            return self._governance_result(request, started_at=started_at, status="blocked", report=f"没有创建新成员，因为 {display_name} 已经存在。", command_id="employees.manage:create", payload=payload)
        kind = (self._arg_str(request, "kind") or ("human" if "human" in message.lower() or "人类" in message else "ai")).lower()
        kind = "human" if kind == "human" else "ai"
        role = self._arg_str(request, "role") or self._role_from_message(message) or ("Human Employee" if kind == "human" else "AI Employee")
        responsibility = self._arg_str(request, "responsibility") or self._summary_from_message(message)
        summary = self._arg_str(request, "summary") or self._default_summary(display_name, role, responsibility)
        skills = self._arg_list(request, "skills") or self._skills_from_message(message) or self._default_skills_for_role(role)
        now = utc_now()
        profile = {
            "id": employee_id,
            "display_name": display_name,
            "kind": kind,
            "role": role,
            "summary": summary,
            "personality": "Concise, evidence-driven, and explicit about blockers.",
            "responsibilities": [responsibility] if responsibility else ["Handle delegated AITeamOS Tickets within profile boundaries."],
            "skills": self._dedupe(skills),
            "memory_scopes": ["aiteamos", f"employee:{employee_id}"],
            "ai_engine": {"mode": "human" if kind == "human" else "external_or_file_stub", "engine_identity": employee_id, "default_engine": "system", "preserve_engine_thread": True},
            "permissions": ["chat", "read_local_assets", "write_trace"] if kind == "ai" else ["chat", "read_local_assets"],
            "handoff_rules": ["Ask for human approval before destructive or externally visible actions.", "Escalate cross-employee coordination needs to Clara."],
            "created_at": now,
            "updated_at": now,
        }
        profile_path = self._employees_dir(request) / f"{employee_id}.yaml"
        self._write_yaml(profile_path, profile)
        employee = self._employee_payload(profile)
        saved_path = str(profile_path.relative_to(self._workspace_root(request)))
        payload = {
            "status": "completed",
            "detail": f"Created employee profile: {employee_id}",
            "employee": employee,
            "saved_path": saved_path,
            "deep_links": {"employee": f"#/employees/{employee_id}", "employees": "#/employees"},
        }
        report = (
            f"已创建成员 {display_name}。\n\n"
            f"- ID: {employee_id}\n"
            f"- Type: {kind}\n"
            f"- Role: {role}\n"
            f"- Skills: {', '.join(employee['skills']) if employee['skills'] else 'none'}\n"
            f"- Profile: {saved_path}\n"
            f"- 查看：#/employees/{employee_id}"
        )
        return self._governance_result(request, started_at=started_at, status="completed", report=report, command_id="employees.manage:create", payload=payload)

    def _edit_employee_result(self, request: ExecutionRequest, *, started_at: str) -> ExecutionResult:
        message = self._action_message(request)
        target = self._arg_str(request, "target_employee_id", "employee_id", "id", "target_employee_name") or self._target_employee_from_message(request, message)
        found = self._find_employee_file(request, target)
        if found is None:
            payload = {"status": "blocked", "reason": "employee_not_found", "detail": f"Employee not found: {target}"}
            return self._governance_result(request, started_at=started_at, status="blocked", report=f"没有找到成员 {target}，所以没有修改 profile。", command_id="employees.manage:update", payload=payload)
        profile_path, profile = found
        updates: dict[str, Any] = {}
        summary = self._arg_str(request, "summary") or self._summary_from_message(message)
        role = self._arg_str(request, "role") or self._role_from_message(message, require_marker=True)
        add_skills = self._arg_list(request, "add_skills", "skills") or self._skills_from_message(message)
        if summary:
            profile["summary"] = summary
            updates["summary"] = summary
        if role:
            profile["role"] = role
            updates["role"] = role
        if add_skills:
            current = [str(item) for item in profile.get("skills", [])]
            profile["skills"] = self._dedupe([*current, *add_skills])
            updates["skills"] = profile["skills"]
        if not updates:
            payload = {"status": "blocked", "reason": "no_supported_updates", "detail": "No supported employee profile fields were found."}
            return self._governance_result(request, started_at=started_at, status="blocked", report="没有识别到可更新字段。", command_id="employees.manage:update", payload=payload)
        profile["updated_at"] = utc_now()
        self._write_yaml(profile_path, profile)
        employee = self._employee_payload(profile)
        saved_path = str(profile_path.relative_to(self._workspace_root(request)))
        payload = {"status": "completed", "detail": f"Updated employee profile: {employee['id']}", "employee": employee, "updates": updates, "saved_path": saved_path}
        changed = "\n".join(f"- {key}: {value}" for key, value in updates.items())
        report = f"已更新成员 {employee['display_name']} 的 profile。\n\n{changed}\n\n- Profile: {saved_path}\n- 查看：#/employees/{employee['id']}"
        return self._governance_result(request, started_at=started_at, status="completed", report=report, command_id="employees.manage:update", payload=payload)

    def _delete_employee_result(self, request: ExecutionRequest, *, started_at: str) -> ExecutionResult:
        message = self._action_message(request)
        target = self._arg_str(request, "target_employee_id", "employee_id", "id", "target_employee_name") or self._target_employee_from_message(request, message)
        found = self._find_employee_file(request, target)
        if found is None:
            payload = {"status": "blocked", "reason": "employee_not_found", "detail": f"Employee not found: {target}"}
            return self._governance_result(request, started_at=started_at, status="blocked", report=f"没有找到成员 {target}，所以没有删除任何 profile。", command_id="employees.manage:delete", payload=payload)
        profile_path, profile = found
        employee = self._employee_payload(profile)
        if employee["id"] == "clara":
            payload = {"status": "blocked", "reason": "protected_employee", "detail": "Clara is the protected default system employee.", "employee": employee}
            report = "没有删除 Clara。\n\n原因：Clara 是 AITeamOS 的系统默认 Employee，负责团队运营与系统资产管理，永远不允许删除。\n- 查看：#/employees/clara"
            return self._governance_result(request, started_at=started_at, status="blocked", report=report, command_id="employees.manage:delete", payload=payload)
        deleted_path = str(profile_path.relative_to(self._workspace_root(request)))
        profile_path.unlink(missing_ok=True)
        removed_keys = delete_engine_thread_states(self._workspace_dir(request), employee["id"])
        payload = {"status": "completed", "detail": f"Deleted employee profile: {employee['id']}", "employee": employee, "deleted_path": deleted_path, "engine_thread_keys_removed": removed_keys}
        report = (
            f"已删除成员 {employee['display_name']}。\n\n"
            f"- ID: {employee['id']}\n"
            f"- Profile: {deleted_path}\n"
            f"- 清理 AI Engine thread 映射：{len(removed_keys)} 条\n"
            "- 历史 conversation 和 trace 已保留，用于审计。\n"
            "- Employees: #/employees"
        )
        return self._governance_result(request, started_at=started_at, status="completed", report=report, command_id="employees.manage:delete", payload=payload)

    def _target_employee_from_message(self, request: ExecutionRequest, message: str) -> str:
        explicit = self._extract_first(
            [
                r"(?:target_employee_id|employee_id|id)\s*[:=：]\s*([A-Za-z0-9_-]{1,80})",
                r"(?:给|to)\s*([A-Z][A-Za-z0-9_-]{1,32})",
                r"(?:删除成员|删除|移除|删掉)\s*([A-Z][A-Za-z0-9_-]{1,32})",
                r"\bto\s+([A-Z][A-Za-z0-9_-]{1,32})\b",
            ],
            message,
        )
        if explicit:
            return self._slugify_id(explicit, prefix="employee")
        lowered = message.lower()
        for profile in self._employee_profiles(request):
            summary = self._employee_summary(profile)
            if summary["id"].lower() in lowered or summary["display_name"].lower() in lowered:
                return summary["id"]
        return ""

    def _list_skills(self, request: ExecutionRequest) -> tuple[str, dict[str, Any], str]:
        skills = self._load_skills(request)
        lines = [f"我找到了 {len(skills)} 个 Skills。", ""]
        if not skills:
            lines.append("- none")
        for skill in skills:
            assigned = ", ".join(skill["assigned_employees"]) if skill["assigned_employees"] else "unassigned"
            lines.append(f"- {skill['title']} ({skill['id']})；assigned: {assigned}；source={skill['source']}")
        lines.extend(["", "入口：", "- Skills: #/assets/capabilities/skills"])
        payload = {"status": "completed", "detail": "Listed Skill assets.", "skills": skills}
        return "\n".join(lines), payload, "assets.manage:list_skills"

    def _load_skills(self, request: ExecutionRequest) -> list[dict[str, Any]]:
        local: list[dict[str, Any]] = []
        skills_dir = self._skills_dir(request)
        if skills_dir.exists():
            for path in sorted(skills_dir.glob("*/SKILL.md")):
                local.append(self._skill_summary(request, path))
        local_ids = {skill["id"] for skill in local}
        builtin = [
            {
                "id": skill.id,
                "title": skill.title,
                "description": skill.description,
                "content": skill.content,
                "assigned_employees": self._assigned_employees_for_skill(request, skill.id),
                "resources": [],
                "saved_path": skill.source_ref,
                "source": "builtin",
            }
            for skill in VALIDATION_SKILL_DEFINITIONS
            if skill.id not in local_ids
        ]
        return [*local, *builtin]

    def _skill_summary(self, request: ExecutionRequest, skill_path: Path) -> dict[str, Any]:
        skill_id = skill_path.parent.name
        text = skill_path.read_text(encoding="utf-8")
        title = skill_id
        description = ""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                title = stripped.removeprefix("# ").strip() or title
            elif stripped.startswith(">") and not description:
                description = stripped.lstrip(">").strip()
            if title != skill_id and description:
                break
        return {
            "id": skill_id,
            "title": title,
            "description": description,
            "content": text,
            "assigned_employees": self._assigned_employees_for_skill(request, skill_id),
            "resources": [],
            "saved_path": str(skill_path.relative_to(self._workspace_root(request))),
            "source": "local",
        }

    def _find_skill(self, request: ExecutionRequest, lookup: str) -> dict[str, Any] | None:
        normalized = lookup.strip().lower()
        if not normalized:
            return None
        for skill in self._load_skills(request):
            if normalized in {skill["id"].lower(), skill["title"].lower()}:
                return skill
        slug = self._slugify_id(lookup, prefix="skill")
        path = self._skills_dir(request) / slug / "SKILL.md"
        return self._skill_summary(request, path) if path.exists() else None

    def _assigned_employees_for_skill(self, request: ExecutionRequest, skill_id: str) -> list[str]:
        assigned: list[str] = []
        employees_dir = self._employees_dir(request)
        if not employees_dir.exists():
            return assigned
        for path in sorted(employees_dir.glob("*.yaml")):
            profile = self._read_yaml(path)
            if skill_id in [str(item) for item in profile.get("skills", [])]:
                assigned.append(str(profile.get("id") or path.stem))
        return sorted(assigned)

    def _skill_lookup_from_message(self, request: ExecutionRequest, message: str) -> str:
        for skill in self._load_skills(request):
            lowered = message.lower()
            if re.search(rf"\b{re.escape(skill['id'].lower())}\b", lowered) or skill["title"].lower() in lowered:
                return skill["id"]
        value = self._extract_first(
            [
                r"(?:skill_id|skill id|技能\s*id|技能ID)\s*[:=：]\s*([A-Za-z0-9_-]{1,80})",
                r"(?:把|删除|移除|删掉|delete|remove|drop)\s*(?:skill\s*)?([A-Za-z0-9_.-]{2,80})",
                r"\b([A-Za-z][A-Za-z0-9_-]{2,80})\s+Skill\b",
            ],
            message,
        )
        return self._slugify_id(value, prefix="skill") if value else ""

    def _create_skill_result(self, request: ExecutionRequest, *, started_at: str) -> ExecutionResult:
        message = self._action_message(request)
        title = self._arg_str(request, "title", "name", "skill_name") or self._extract_first(
            [
                r"(?:名字叫|名为|叫做|叫|named|called)\s*([A-Za-z][A-Za-z0-9_. -]{0,79})",
                r"\bcreate_skill\s+([A-Za-z][A-Za-z0-9_. -]{0,79})",
            ],
            message,
        )
        if not title:
            payload = {"status": "blocked", "reason": "missing_skill_title", "detail": "Skill title was not found."}
            return self._governance_result(request, started_at=started_at, status="blocked", report="没有识别到 Skill 名称。", command_id="assets.manage:create_skill", payload=payload)
        skill_id = self._slugify_id(self._arg_str(request, "skill_id", "id") or title, prefix="skill")
        if self._find_skill(request, skill_id):
            payload = {"status": "blocked", "reason": "skill_already_exists", "detail": f"Skill already exists: {skill_id}"}
            return self._governance_result(request, started_at=started_at, status="blocked", report=f"没有创建新 Skill，因为 {title} 已经存在。", command_id="assets.manage:create_skill", payload=payload)
        description = self._arg_str(request, "description", "summary", "purpose") or self._extract_first([r"(?:用于|用来|description|用途|描述)\s*(?:是|为|:|：)?\s*([^。;；\n]+)"], message) or f"AITeamOS reusable skill: {skill_id}."
        body = f"# {title}\n\n> {description}\n\n## When To Use\n\n- Use this skill when Ticket work matches the description above.\n\n## Procedure\n\n1. Clarify the goal, constraints, and expected evidence.\n2. Apply the relevant product context and tools.\n3. Report outcome, evidence, blockers, and next actions.\n"
        skill_path = self._skills_dir(request) / skill_id / "SKILL.md"
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(body, encoding="utf-8")
        skill = self._skill_summary(request, skill_path)
        payload = {"status": "completed", "detail": f"Created skill: {skill_id}", "skill": skill, "saved_path": skill["saved_path"]}
        report = f"已创建 Skill {skill['title']}。\n\n- ID: {skill_id}\n- Description: {description}\n- Profile: {skill['saved_path']}\n- 查看：#/assets/capabilities/skills/{skill_id}"
        return self._governance_result(request, started_at=started_at, status="completed", report=report, command_id="assets.manage:create_skill", payload=payload)

    def _assign_skill_result(self, request: ExecutionRequest, *, started_at: str) -> ExecutionResult:
        message = self._action_message(request)
        skill_lookup = self._arg_str(request, "skill_id", "id", "skill_name", "title") or self._skill_lookup_from_message(request, message)
        target = self._arg_str(request, "target_employee_id", "employee_id", "target_employee_name") or self._target_employee_from_message(request, message)
        skill = self._find_skill(request, skill_lookup)
        found = self._find_employee_file(request, target)
        if skill is None:
            payload = {"status": "blocked", "reason": "skill_not_found", "detail": f"Skill not found: {skill_lookup}"}
            return self._governance_result(request, started_at=started_at, status="blocked", report=f"没有找到 Skill {skill_lookup}，所以没有分配。", command_id="assets.manage:assign_skill", payload=payload)
        if found is None:
            payload = {"status": "blocked", "reason": "employee_not_found", "detail": f"Employee not found: {target}"}
            return self._governance_result(request, started_at=started_at, status="blocked", report=f"没有找到成员 {target}，所以没有分配 Skill。", command_id="assets.manage:assign_skill", payload=payload)
        profile_path, profile = found
        current = [str(item) for item in profile.get("skills", [])]
        profile["skills"] = self._dedupe([*current, skill["id"]])
        profile["updated_at"] = utc_now()
        self._write_yaml(profile_path, profile)
        employee = self._employee_payload(profile)
        saved_path = str(profile_path.relative_to(self._workspace_root(request)))
        payload = {"status": "completed", "detail": f"Assigned skill {skill['id']} to employee {employee['id']}", "skill": skill, "employee": employee, "saved_path": saved_path}
        report = (
            f"已把 Skill {skill['title']} 分配给 {employee['display_name']}。\n\n"
            f"- Skill: {skill['id']}\n"
            f"- Employee: {employee['display_name']} ({employee['id']})\n"
            f"- Employee skills: {', '.join(employee['skills']) if employee['skills'] else 'none'}\n"
            f"- Profile: {saved_path}"
        )
        return self._governance_result(request, started_at=started_at, status="completed", report=report, command_id="assets.manage:assign_skill", payload=payload)

    def _delete_skill_result(self, request: ExecutionRequest, *, started_at: str) -> ExecutionResult:
        message = self._action_message(request)
        skill_lookup = self._arg_str(request, "skill_id", "id", "skill_name", "title") or self._skill_lookup_from_message(request, message)
        skill = self._find_skill(request, skill_lookup)
        if skill is None:
            payload = {"status": "blocked", "reason": "skill_not_found", "detail": f"Skill not found: {skill_lookup}"}
            return self._governance_result(request, started_at=started_at, status="blocked", report=f"没有找到 Skill {skill_lookup}，所以没有删除任何文件。", command_id="assets.manage:delete_skill", payload=payload)
        if skill["source"] != "local":
            payload = {"status": "blocked", "reason": "builtin_skill_read_only", "detail": f"Built-in validation Skill cannot be deleted: {skill['id']}", "skill": skill}
            report = f"不能删除内建验证 Skill {skill['title']}。\n\n- Skill: {skill['id']}\n- Source: {skill['source']}\n- 这些 Phase 5 验证 Skill 是只读基线。"
            return self._governance_result(request, started_at=started_at, status="blocked", report=report, command_id="assets.manage:delete_skill", payload=payload)
        unassigned: list[str] = []
        employees_dir = self._employees_dir(request)
        if employees_dir.exists():
            for profile_path in sorted(employees_dir.glob("*.yaml")):
                profile = self._read_yaml(profile_path)
                current = [str(item) for item in profile.get("skills", [])]
                next_skills = [item for item in current if item != skill["id"]]
                if len(next_skills) == len(current):
                    continue
                profile["skills"] = next_skills
                profile["updated_at"] = utc_now()
                self._write_yaml(profile_path, profile)
                unassigned.append(str(profile.get("id") or profile_path.stem))
        skill_dir = self._skills_dir(request) / skill["id"]
        deleted_path = str(skill_dir.relative_to(self._workspace_root(request)))
        if skill_dir.exists():
            shutil.rmtree(skill_dir)
        payload = {"status": "completed", "detail": f"Deleted skill: {skill['id']}", "skill": skill, "deleted_path": deleted_path, "unassigned_employees": unassigned}
        report = f"已删除 Skill {skill['title']}。\n\n- ID: {skill['id']}\n- Deleted: {deleted_path}\n- 已从成员移除：{', '.join(unassigned) if unassigned else 'none'}"
        return self._governance_result(request, started_at=started_at, status="completed", report=report, command_id="assets.manage:delete_skill", payload=payload)

    def _list_code_repositories(self) -> tuple[str, dict[str, Any], str]:
        repositories = [repository.model_dump(mode="json") for repository in list_code_repositories()]
        lines = [f"我找到了 {len(repositories)} 个代码仓库。", ""]
        if not repositories:
            lines.append("- none")
        for repository in repositories:
            branch = repository.get("current_branch") or repository.get("default_branch") or "-"
            plane_scope = "/".join(
                str(item)
                for item in (repository.get("plane_workspace_slug"), repository.get("plane_project_id"))
                if str(item or "").strip()
            ) or "-"
            lines.append(
                f"- {repository.get('name')} ({repository.get('id')})；source={repository.get('provider')}；"
                f"status={repository.get('status')}；branch={branch}；Plane={plane_scope}"
            )
            if repository.get("location"):
                lines.append(f"  {repository.get('location')}")
        lines.extend(["", "入口：", "- Code Repositories: #/settings/code-repositories"])
        payload = {
            "status": "completed",
            "detail": "Listed configured code repositories.",
            "count": len(repositories),
            "repositories": repositories,
            "deep_links": {"code_repositories": "#/settings/code-repositories"},
        }
        return "\n".join(lines), payload, "repositories.list:list"

    def _search_knowledge(self, request: ExecutionRequest) -> tuple[str, dict[str, Any], str]:
        query = str(request.action_plan.arguments.get("query") or request.action_plan.arguments.get("message") or "").strip()
        response = search_knowledge_sync(query, limit=5)
        results = [result.model_dump(mode="json") for result in response.results]
        lines = [f"我搜索了 Knowledge：{response.query}", ""]
        if not results:
            lines.append("- 没有找到匹配的 Docs、Memories 或 Decisions。")
        for result in results:
            lines.append(
                f"- {result.get('title')}；type={result.get('source_type')}；ref={result.get('source_ref')}；"
                f"score={result.get('score')}"
            )
            content = str(result.get("content") or "").strip()
            if content:
                lines.append(f"  {content[:220]}")
        lines.extend(["", "入口：", "- Knowledge: #/assets/knowledge"])
        payload = {
            "status": "completed",
            "detail": "Searched local Knowledge assets.",
            "query": response.query,
            "results": results,
            "deep_links": {"knowledge": "#/assets/knowledge"},
        }
        return "\n".join(lines), payload, "knowledge.search:search"

    def _inspect_code_repository_result(self, request: ExecutionRequest, *, started_at: str) -> ExecutionResult:
        if request.employee_id == "clara":
            return blocked_result(
                request,
                executor_id=self.id,
                reason="control_plane_employee_blocked",
                detail="Clara is the control-plane manager and does not directly inspect repository state.",
            )

        repository = self._resolve_inspection_repository(request)
        if repository is None:
            return blocked_result(
                request,
                executor_id=self.id,
                reason="missing_repository_context",
                detail="No enabled Code Repository could be resolved from the Ticket or message.",
            )

        query = str(request.action_plan.arguments.get("query") or request.action_plan.arguments.get("message") or "").strip()
        try:
            inspection = inspect_code_repository(repository, query=query, file_paths=self._inspection_file_paths(request))
        except ValueError as exc:
            return blocked_result(request, executor_id=self.id, reason="repository_inspection_blocked", detail=str(exc))

        matches = [match.model_dump(mode="json") for match in inspection.matches]
        files = [file.model_dump(mode="json") for file in inspection.files]
        employee = request.task_context.get("employee") if isinstance(request.task_context.get("employee"), dict) else {}
        display_name = str(employee.get("display_name") or request.employee_id)
        lines = [
            f"{display_name} 已检查代码仓库。",
            "",
            f"- Repository: {repository.name} ({repository.id})",
            f"- Status: {inspection.status}",
            f"- Query: {query}",
            f"- Matches: {len(matches)}",
            f"- Files read: {len(files)}",
            "",
            "主要证据：",
        ]
        if not matches and not files:
            lines.append("- 未找到匹配的文本文件或可读文件。")
        for match in matches[:8]:
            lines.append(f"- {match['path']}:{match['line']} {match['excerpt']}")
        for file in files[:2]:
            excerpt = str(file["content"])[:600].strip()
            lines.append(f"- Read {file['path']}:\n  {excerpt}")

        evidence_refs = [
            f"repo:{repository.id}",
            *[f"{match['path']}:{match['line']}" for match in matches[:8]],
            *[f"file:{file['path']}" for file in files[:3]],
        ]
        payload = {
            "status": inspection.status,
            "detail": inspection.detail,
            "repository": inspection.repository.model_dump(mode="json"),
            "query": query,
            "matches": matches,
            "files": files,
        }
        finished_at = utc_now()
        return ExecutionResult(
            request_id=request.request_id,
            executor_id=self.id,
            status="completed" if inspection.status == "completed" else "blocked",
            report="\n".join(lines),
            output_ticket_id=request.ticket_id,
            artifacts=[{"kind": "repository_inspection", **payload}],
            evidence=[
                {"kind": "repository_inspection", "ticket_id": request.ticket_id, "repository_id": repository.id, "ref": ref}
                for ref in evidence_refs
            ],
            trace_ref=str(request.trace_context.get("trace_ref") or ""),
            executor_session_ref=f"local-{request.request_id}",
            checkpoint_ref=f"local:{request.request_id}",
            tool_events=[self._command_event("command.called", "repositories.inspect:inspect", {"status": "called"})],
            learning_delta={"action": "inspect_code_repository", "executor": self.id, "source": "local_tool_executor"},
            usage={"runtime_steps": 1, "matches": len(matches), "files": len(files)},
            started_at=started_at,
            finished_at=finished_at,
        )

    def _resolve_inspection_repository(self, request: ExecutionRequest) -> CodeRepository | None:
        repositories = list_code_repositories()
        arguments = request.action_plan.arguments
        for key in ("code_repository_id", "repository_id", "repo_id", "code_repository_name", "repository_name", "repo_name"):
            found = self._match_repository(str(arguments.get(key) or ""), repositories)
            if found is not None:
                return found
        ticket = request.task_context.get("ticket") if isinstance(request.task_context.get("ticket"), dict) else {}
        for repo_id in ticket.get("code_repository_ids") or []:
            found = get_code_repository(str(repo_id))
            if found is not None:
                return found
        message = str(arguments.get("message") or request.trace_context.get("source_message") or "")
        lowered = message.lower()
        for repository in repositories:
            if repository.id.lower() in lowered or repository.name.lower() in lowered:
                return repository
        enabled = [repository for repository in repositories if repository.enabled]
        if len(enabled) == 1 and (self._message_mentions_repo_context(message) or request.ticket_id):
            return enabled[0]
        return None

    def _match_repository(self, value: str, repositories: list[CodeRepository]) -> CodeRepository | None:
        lookup = value.strip().lower()
        if not lookup:
            return None
        for repository in repositories:
            if lookup in {repository.id.lower(), repository.name.lower()}:
                return repository
        for repository in repositories:
            if lookup in repository.location.lower() or lookup in repository.name.lower():
                return repository
        return None

    def _message_mentions_repo_context(self, message: str) -> bool:
        compact = re.sub(r"\s+", "", message.lower())
        if any(token in compact for token in ("代码仓库", "代码库", "仓库", "代码", "源码", "文件", "实现")):
            return True
        return bool(re.search(r"\b(codebase|source|files?|repos?|repositories|repository|implementation)\b", message, re.IGNORECASE))

    def _inspection_file_paths(self, request: ExecutionRequest) -> list[str]:
        value = request.action_plan.arguments.get("file_paths")
        if isinstance(value, list):
            return [str(item).strip().lstrip("/") for item in value if str(item).strip()]
        return []

    async def _terminal_run_result(self, request: ExecutionRequest, *, started_at: str) -> ExecutionResult:
        ticket_id = str(request.ticket_id or request.ticket_binding.ticket_id or request.action_plan.arguments.get("ticket_id") or "").strip()
        if not ticket_id:
            return blocked_result(
                request,
                executor_id=self.id,
                reason="terminal_ticket_binding_required",
                detail="terminal.run requires a Ticket binding before command execution.",
            )
        if "terminal:run" not in set(request.capability_grants):
            return blocked_result(
                request,
                executor_id=self.id,
                reason="terminal_capability_required",
                detail="terminal.run requires the terminal:run governance capability grant.",
            )

        message = str(request.action_plan.arguments.get("message") or request.trace_context.get("source_message") or "")
        command_line = str(request.action_plan.arguments.get("command_line") or "").strip() or (extract_terminal_command_line(message) or "")
        if not command_line:
            return blocked_result(request, executor_id=self.id, reason="terminal_command_missing", detail="No terminal command was found.")
        argv, argv_error = terminal_argv_from_command(command_line)
        if argv is None:
            return blocked_result(request, executor_id=self.id, reason="terminal_command_blocked", detail=argv_error or "Terminal command is blocked.")

        workspace_value = str(request.workspace_id or "").strip()
        workspace = Path(os.environ.get("AITEAMOS_WORKSPACE_DIR") or ".").resolve() if workspace_value in {"", "local"} else Path(workspace_value).resolve()
        raw_cwd = str(request.action_plan.arguments.get("cwd") or "").strip() or None
        cwd, cwd_error = terminal_cwd_from_raw(raw_cwd, workspace)
        if cwd is None:
            return blocked_result(request, executor_id=self.id, reason="terminal_cwd_blocked", detail=cwd_error or "Terminal cwd is blocked.")
        workspace_error = validate_terminal_workspace_args(argv, cwd, workspace)
        if workspace_error:
            return blocked_result(request, executor_id=self.id, reason="terminal_workspace_blocked", detail=workspace_error)
        if self._approval_required(request, "terminal:run"):
            timestamp = utc_now()
            executor_session_ref = f"local-{request.request_id}"
            checkpoint_ref = f"local:{request.request_id}"
            source_state_ref = f"state://{self.id}/{request.request_id}/terminal_run_approval"
            approval = {
                "kind": "terminal_run",
                "ticket_id": ticket_id,
                "executor_id": self.id,
                "reason": "terminal.run requires governed approval before command execution.",
                "required_capability": "terminal:run",
                "risk_level": "high",
                "proposed_action": {
                    "action": "terminal_run",
                    "ticket_id": ticket_id,
                    "executor_id": self.id,
                    "capability": "terminal:run",
                    "command_line": command_line,
                    "cwd": str(cwd),
                    "summary": str(request.action_plan.arguments.get("message") or request.trace_context.get("source_message") or ""),
                },
                "checkpoint_ref": checkpoint_ref,
                "executor_session_ref": executor_session_ref,
                "source_state_ref": source_state_ref,
                "current_graph_node": "terminal_run_approval_gate",
            }
            return ExecutionResult(
                request_id=request.request_id,
                executor_id=self.id,
                status="needs_approval",
                report="terminal.run needs approval before command execution.",
                output_ticket_id=ticket_id,
                trace_ref=str(request.trace_context.get("trace_ref") or ""),
                executor_session_ref=executor_session_ref,
                checkpoint_ref=checkpoint_ref,
                approval_requests=[approval],
                errors=[{"reason": "terminal_run_approval_required", "detail": approval["reason"]}],
                tool_events=[
                    self._command_event(
                        "command.blocked",
                        "terminal.run:run",
                        {
                            "status": "needs_approval",
                            "reason": "terminal_run_approval_required",
                            "approval_request": approval,
                        },
                    )
                ],
                learning_delta={
                    "approval_interrupt": {
                        "source": "local_tool_guard",
                        "checkpoint_ref": checkpoint_ref,
                        "executor_session_ref": executor_session_ref,
                        "source_state_ref": source_state_ref,
                        "current_graph_node": "terminal_run_approval_gate",
                    }
                },
                started_at=timestamp,
                finished_at=timestamp,
            )

        exit_code, output, timed_out = await run_terminal_command_collect(argv=argv, cwd=cwd)
        evidence_ref = terminal_evidence_ref(request.request_id)
        report = terminal_reply(
            command_line=command_line,
            cwd=cwd,
            workspace=workspace,
            exit_code=exit_code,
            output=output,
            timed_out=timed_out,
        )
        report = f"{report}\n\nTicket evidence:\n- Ticket: {ticket_id}\n- Evidence: {evidence_ref}\n\n$ {command_line}"
        report_content = terminal_report_content(
            command_line=command_line,
            cwd=cwd,
            workspace=workspace,
            exit_code=exit_code,
            timed_out=timed_out,
            output=output,
        )
        try:
            updated_ticket = add_ticket_report(
                ticket_id,
                TicketReportRequest(
                    reporter_employee_id=request.employee_id,
                    reporter_role="AI Employee",
                    content=report_content,
                    evidence=[evidence_ref],
                    report_type="terminal_evidence",
                    source_run_id=str(request.trace_context.get("run_id") or request.request_id),
                ),
            )
        except Exception as exc:
            return blocked_result(request, executor_id=self.id, reason="terminal_evidence_report_blocked", detail=str(exc))
        report_id = updated_ticket.reports[-1].id if updated_ticket.reports else ""

        finished_at = utc_now()
        payload = {
            "status": "completed" if exit_code == 0 and not timed_out else "failed",
            "ticket_id": ticket_id,
            "command_line": command_line,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "ticket_evidence": {
                "ticket_id": ticket_id,
                "evidence_ref": evidence_ref,
                "report_id": report_id,
                "report_type": "terminal_evidence",
            },
        }
        return ExecutionResult(
            request_id=request.request_id,
            executor_id=self.id,
            status="completed" if exit_code == 0 and not timed_out else "failed",
            report=report,
            output_ticket_id=ticket_id,
            artifacts=[{"kind": "terminal_run", **payload}],
            evidence=[{"kind": "terminal_output", "ticket_id": ticket_id, "ref": evidence_ref, "command_line": command_line}],
            trace_ref=str(request.trace_context.get("trace_ref") or ""),
            executor_session_ref=f"local-{request.request_id}",
            checkpoint_ref=f"local:{request.request_id}",
            tool_events=[
                self._command_event("command.called", "terminal.run:run", {"status": "called"}),
                self._command_event("command.completed", "terminal.run:run", payload),
            ],
            learning_delta={"action": "terminal_run", "executor": self.id, "source": "local_tool_executor"},
            usage={"runtime_steps": 1, "exit_code": exit_code if exit_code is not None else -1},
            started_at=started_at,
            finished_at=finished_at,
        )

    def _approval_required(self, request: ExecutionRequest, required_capability: str) -> bool:
        policy = request.approval_policy if isinstance(request.approval_policy, dict) else {}
        required = {str(item) for item in policy.get("require_approval_for", []) if str(item).strip()} if isinstance(policy.get("require_approval_for"), list) else set()
        if required_capability not in required:
            return False
        approved = {str(item) for item in policy.get("approved_capabilities", []) if str(item).strip()} if isinstance(policy.get("approved_capabilities"), list) else set()
        refs = [str(item) for item in policy.get("approval_refs", []) if str(item).strip()] if isinstance(policy.get("approval_refs"), list) else []
        return required_capability not in approved or not refs

    def _self_bootstrap_start_result(self, request: ExecutionRequest, *, started_at: str) -> ExecutionResult:
        status = ticket_backend_status()
        if status.status == "setup_blocked":
            return blocked_result(
                request,
                executor_id=self.id,
                reason="ticket_backend_setup_blocker",
                detail=status.detail,
            )

        summary = self_bootstrap_learning_summary()
        batch_size = self._self_bootstrap_batch_size(request)
        specs = self._self_bootstrap_ticket_specs(summary.model_dump(mode="json"), batch_size)
        created: list[dict[str, Any]] = []
        try:
            for spec in specs:
                ticket = create_ticket(
                    TicketCreateRequest(
                        title=spec["title"],
                        description=spec["description"],
                        ticket_type="rd",
                        assigned_employee_id="alex",
                        assigned_role="AI RD / Implementer",
                        validation_employee_id="peter",
                        validation_role="AI PV",
                        knowledge_refs=spec["knowledge_refs"],
                        source_thread_id=str(request.trace_context.get("thread_id") or ""),
                        source_run_id=str(request.trace_context.get("run_id") or request.request_id),
                        actor_employee_id="clara",
                        actor_role="AI Team OS Manager",
                    )
                )
                created.append(ticket.model_dump(mode="json"))
        except Exception as exc:
            return blocked_result(request, executor_id=self.id, reason="self_bootstrap_ticket_create_blocked", detail=str(exc))

        finished_at = utc_now()
        first_ticket_id = str(created[0].get("id") or "") if created else ""
        payload = {
            "status": "completed",
            "detail": "Started governed self-bootstrap improvement Ticket batch.",
            "batch_size": len(created),
            "tickets": created,
            "self_bootstrap_summary": summary.model_dump(mode="json"),
            "deep_links": {"tickets": "#/tickets/tickets"},
        }
        report_lines = [
            f"已启动 self-bootstrap improvement batch：{len(created)} 个 Ticket。",
            "",
            f"- Learning summary: {summary.summary or 'No prior summary yet.'}",
            f"- Candidates produced: {summary.memory_candidates_produced}",
            f"- Approved assets recalled: {summary.approved_memories_recalled}",
            "",
            "新 Ticket：",
        ]
        for ticket in created:
            report_lines.append(
                f"- {ticket.get('id')}: {ticket.get('title')} -> assignee={ticket.get('assigned_employee_id')}; "
                f"validator={ticket.get('validation_employee_id') or ticket.get('validation_role')}"
            )
        report_lines.extend(["", "入口：", "- Tickets: #/tickets/tickets"])
        return ExecutionResult(
            request_id=request.request_id,
            executor_id=self.id,
            status="completed",
            report="\n".join(report_lines),
            output_ticket_id=first_ticket_id,
            artifacts=[{"kind": "self_bootstrap_batch", **payload}],
            evidence=[
                {
                    "kind": "self_bootstrap_learning_summary",
                    "ticket_id": first_ticket_id,
                    "ref": f"self-bootstrap-summary:{request.request_id}",
                    "summary": summary.summary,
                }
            ],
            trace_ref=str(request.trace_context.get("trace_ref") or ""),
            executor_session_ref=f"local-{request.request_id}",
            checkpoint_ref=f"local:{request.request_id}",
            tool_events=[
                self._command_event("command.called", "tickets.manage:self_bootstrap_start", {"status": "called"}),
                self._command_event("command.completed", "tickets.manage:self_bootstrap_start", payload),
            ],
            memory_candidates=[
                {
                    "content": (
                        f"Self-bootstrap batch {request.request_id} started {len(created)} governed improvement Tickets "
                        f"from learning summary: {summary.summary or 'no prior summary'}"
                    ),
                    "memory_type": "learning_summary",
                    "confidence": 0.78,
                    "tags": ["self-bootstrap", "learning-summary", "runtime-first"],
                    "future_recall_query_hints": ["self-bootstrap", "improvement batch", *[str(ticket.get("id") or "") for ticket in created]],
                }
            ],
            learning_delta={
                "action": "self_bootstrap_start",
                "executor": self.id,
                "source": "local_tool_executor",
                "created_ticket_ids": [str(ticket.get("id") or "") for ticket in created],
                "self_bootstrap_summary": summary.model_dump(mode="json"),
            },
            usage={"runtime_steps": 1, "tickets_created": len(created)},
            started_at=started_at,
            finished_at=finished_at,
        )

    def _self_bootstrap_close_result(self, request: ExecutionRequest, *, started_at: str) -> ExecutionResult:
        status = ticket_backend_status()
        if status.status == "setup_blocked":
            return blocked_result(
                request,
                executor_id=self.id,
                reason="ticket_backend_setup_blocker",
                detail=status.detail,
            )

        ticket_id = self._self_bootstrap_closure_ticket_id(request)
        if not ticket_id:
            return blocked_result(
                request,
                executor_id=self.id,
                reason="self_bootstrap_closure_ticket_required",
                detail="Closing a self-bootstrap batch requires an existing Ticket binding.",
            )
        ticket = get_ticket(ticket_id)
        if ticket is None:
            return blocked_result(
                request,
                executor_id=self.id,
                reason="self_bootstrap_closure_ticket_not_found",
                detail=f"Ticket not found: {ticket_id}",
            )

        before_summary = self_bootstrap_learning_summary()
        usefulness_status = self._self_bootstrap_usefulness_status(request)
        reviewed_usages = self._review_ticket_memory_recall_usages(
            ticket_id=ticket_id,
            usefulness_status=usefulness_status,
            request=request,
        )
        evidence_refs = [f"self-bootstrap-closure:{request.request_id}"]
        evidence_refs.extend(f"memory-recall:{usage['usage_id']}:{usage['usefulness_status']}" for usage in reviewed_usages)
        ticket_record = next((item for item in before_summary.tickets if item.ticket_id == ticket_id), None)
        report_lines = [
            f"Clara self-bootstrap closure for Ticket {ticket_id}.",
            "",
            f"- Ticket status: {ticket.status}",
            f"- Learning summary: {before_summary.summary}",
            f"- Memory candidates produced: {before_summary.memory_candidates_produced}",
            f"- Approved assets recalled: {before_summary.approved_memories_recalled}",
            f"- Recall usefulness reviews recorded: {len(reviewed_usages)}",
        ]
        if ticket_record is not None:
            report_lines.extend(
                [
                    f"- Ticket evidence count: {ticket_record.evidence_count}",
                    f"- Ticket next learning action: {ticket_record.next_learning_action}",
                ]
            )
        if usefulness_status == "unreviewed":
            report_lines.append("- Recall usefulness: still needs explicit Clara/PV review.")
        else:
            report_lines.append(f"- Recall usefulness: marked {usefulness_status}.")
        report_lines.extend(["", "入口：", f"- Ticket: #/tickets/tickets/{ticket_id}", "- Review Queue: #/assets/memory"])
        report = "\n".join(report_lines)

        try:
            updated_ticket = add_ticket_report(
                ticket_id,
                TicketReportRequest(
                    reporter_employee_id="clara",
                    reporter_role="AI Team OS Manager",
                    content=report,
                    evidence=evidence_refs,
                    report_type="learning_summary",
                    source_run_id=str(request.trace_context.get("run_id") or request.request_id),
                ),
            )
        except Exception as exc:
            return blocked_result(request, executor_id=self.id, reason="self_bootstrap_closure_report_blocked", detail=str(exc))

        after_summary = self_bootstrap_learning_summary()
        payload = {
            "status": "completed",
            "detail": "Closed a governed self-bootstrap batch Ticket with learning summary and recall usefulness feedback.",
            "ticket": updated_ticket.model_dump(mode="json"),
            "reviewed_recall_usages": reviewed_usages,
            "usefulness_status": usefulness_status,
            "self_bootstrap_summary": after_summary.model_dump(mode="json"),
            "deep_links": {"ticket": f"#/tickets/tickets/{ticket_id}", "review_queue": "#/assets/memory"},
        }
        finished_at = utc_now()
        return ExecutionResult(
            request_id=request.request_id,
            executor_id=self.id,
            status="completed",
            report=report,
            output_ticket_id=ticket_id,
            artifacts=[{"kind": "self_bootstrap_closure", **payload}],
            evidence=[
                {
                    "kind": "self_bootstrap_closure",
                    "ticket_id": ticket_id,
                    "ref": ref,
                    "reviewed_recall_usage_count": len(reviewed_usages),
                }
                for ref in evidence_refs
            ],
            trace_ref=str(request.trace_context.get("trace_ref") or ""),
            executor_session_ref=f"local-{request.request_id}",
            checkpoint_ref=f"local:{request.request_id}",
            tool_events=[
                self._command_event("command.called", "tickets.manage:self_bootstrap_close", {"status": "called"}),
                self._command_event("command.completed", "tickets.manage:self_bootstrap_close", payload),
            ],
            memory_candidates=[
                {
                    "content": (
                        f"Self-bootstrap Ticket {ticket_id} closed with Clara learning summary. "
                        f"Recall usefulness reviews recorded: {len(reviewed_usages)}. "
                        f"Current learning delta: {after_summary.learning_delta}"
                    ),
                    "memory_type": "learning_summary",
                    "confidence": 0.82,
                    "tags": ["self-bootstrap", "learning-summary", "recall-usefulness", "runtime-first"],
                    "future_recall_query_hints": ["self-bootstrap closure", "recall usefulness", ticket_id],
                }
            ],
            learning_delta={
                "action": "self_bootstrap_close",
                "executor": self.id,
                "source": "local_tool_executor",
                "ticket_id": ticket_id,
                "reviewed_recall_usages": reviewed_usages,
                "usefulness_status": usefulness_status,
                "self_bootstrap_summary": after_summary.model_dump(mode="json"),
            },
            usage={"runtime_steps": 1, "reviewed_recall_usages": len(reviewed_usages)},
            started_at=started_at,
            finished_at=finished_at,
        )

    def _self_bootstrap_closure_ticket_id(self, request: ExecutionRequest) -> str:
        return str(
            request.ticket_id
            or request.ticket_binding.ticket_id
            or request.action_plan.arguments.get("ticket_id")
            or ""
        ).strip()

    def _self_bootstrap_usefulness_status(self, request: ExecutionRequest) -> str:
        message = str(request.action_plan.arguments.get("message") or request.trace_context.get("source_message") or "").lower()
        compact = re.sub(r"\s+", "", message)
        if any(token in compact for token in ("harmful", "有害", "误导", "错误经验")):
            return "harmful"
        if any(token in compact for token in ("notuseful", "not_useful", "irrelevant", "无用", "没用", "没有用", "不相关", "不有用")):
            return "irrelevant"
        if any(token in compact for token in ("promoted", "promote", "沉淀为资产", "提升为资产", "可推广")):
            return "promoted"
        if any(token in compact for token in ("useful", "有用", "可复用", "复用有效", "帮助很大")):
            return "used"
        return "unreviewed"

    def _review_ticket_memory_recall_usages(
        self,
        *,
        ticket_id: str,
        usefulness_status: str,
        request: ExecutionRequest,
    ) -> list[dict[str, Any]]:
        if usefulness_status == "unreviewed":
            return []
        reviewed: list[dict[str, Any]] = []
        reason = f"Self-bootstrap closure {request.request_id} recorded recall usefulness as {usefulness_status}."
        for asset in ticket_asset_records():
            if asset.kind != "memory" or asset.source_ticket_id != ticket_id:
                continue
            memory_id = str(asset.metadata.get("memory_id") or asset.metadata.get("asset_id") or "").strip()
            usage_id = str(asset.metadata.get("usage_id") or "").strip()
            current_status = str(asset.metadata.get("usefulness_status") or "unreviewed").strip()
            if not memory_id or not usage_id or current_status != "unreviewed":
                continue
            try:
                review_memory_recall_usage(
                    memory_id,
                    usage_id,
                    MemoryRecallUsefulnessReviewRequest(
                        usefulness_status=usefulness_status,
                        reviewer_employee_id="clara",
                        reason=reason,
                    ),
                )
            except (KeyError, ValueError):
                continue
            reviewed.append(
                {
                    "memory_id": memory_id,
                    "usage_id": usage_id,
                    "ticket_id": ticket_id,
                    "usefulness_status": usefulness_status,
                    "reviewer_employee_id": "clara",
                }
            )
        return reviewed

    def _self_bootstrap_batch_size(self, request: ExecutionRequest) -> int:
        value = request.action_plan.arguments.get("batch_size", 2)
        try:
            return max(1, min(int(value), 5))
        except (TypeError, ValueError):
            return 2

    def _self_bootstrap_ticket_specs(self, summary: dict[str, Any], batch_size: int) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        if int(summary.get("tickets_missing_required_evidence") or 0):
            candidates.append(
                {
                    "title": "Self-bootstrap: close validation evidence gaps",
                    "focus": "Attach required evidence to self-bootstrap Tickets before validation passes.",
                }
            )
        if int(summary.get("approved_memories_recalled") or 0) and not int(summary.get("useful_memory_recalls") or 0):
            candidates.append(
                {
                    "title": "Self-bootstrap: review recall usefulness",
                    "focus": "PV reviews whether recalled approved assets were used, irrelevant, harmful, or promoted for each Ticket.",
                }
            )
        if int(summary.get("memory_candidates_produced") or 0) > int(summary.get("approved_memory_candidates") or 0):
            candidates.append(
                {
                    "title": "Self-bootstrap: review generated learning candidates",
                    "focus": "Review pending learning candidates before relying on them in later Tickets.",
                }
            )
        candidates.extend(
            [
                {
                    "title": "Self-bootstrap: project validated durable assets to Graphiti",
                    "focus": "Project validated Ticket summaries, Decisions, Docs, Skills, and Capabilities with provenance.",
                },
                {
                    "title": "Self-bootstrap: improve runtime-first execution evidence",
                    "focus": "Run a Ticket-bound implementation slice and record report, evidence, validation, candidate, and recall usefulness.",
                },
            ]
        )
        specs: list[dict[str, Any]] = []
        for candidate in candidates[:batch_size]:
            focus = candidate["focus"]
            specs.append(
                {
                    "title": candidate["title"],
                    "knowledge_refs": ["tickets:self-bootstrap/summary"],
                    "description": "\n".join(
                        [
                            focus,
                            "",
                            "Acceptance Criteria:",
                            "- Work remains Ticket-bound and assigned to an AI Employee.",
                            "- Alex records implementation report and evidence.",
                            "- Peter records PV validation or validation failure with blocker/rework path.",
                            "- Clara records a learning summary, proposed candidates, and recall usefulness.",
                            "- Approved durable assets retain AITeamOS provenance before Graphiti projection.",
                            "",
                            f"Source learning summary: {summary.get('summary') or 'No prior summary yet.'}",
                        ]
                    ),
                }
            )
        return specs

    def _self_bootstrap_summary(self) -> tuple[str, dict[str, Any], str]:
        summary = self_bootstrap_learning_summary()
        lines = [
            "这是 AITeamOS 当前 self-bootstrap learning summary：",
            "",
            (
                f"- Tickets: {summary.ticket_count}；validated={summary.validated_ticket_count}；"
                f"blocked={summary.blocked_ticket_count}；needs_evidence={summary.tickets_missing_required_evidence}"
            ),
            (
                f"- Assets: candidates={summary.memory_candidates_produced}；approved_candidates={summary.approved_memory_candidates}；"
                f"recalled={summary.approved_memories_recalled}；graphiti_recalled={summary.graphiti_memories_recalled}；"
                f"useful_recall={summary.useful_memory_recalls}；"
                f"stale_or_superseded={summary.stale_or_superseded_assets}"
            ),
            f"- Learning delta: {summary.learning_delta}",
        ]
        if summary.tickets:
            lines.extend(["", "需要关注的 Ticket："])
            for ticket in summary.tickets[:5]:
                lines.append(
                    f"- {ticket.ticket_id}: {ticket.title}；status={ticket.status}；"
                    f"evidence={ticket.evidence_count}；recalled={ticket.approved_memories_recalled}；"
                    f"next={ticket.next_learning_action}"
                )
        lines.extend(["", "入口：", "- Tickets: #/tickets/tickets"])
        payload = {
            "status": "completed",
            "detail": "Summarized self-bootstrap learning facts.",
            "self_bootstrap_summary": summary.model_dump(mode="json"),
        }
        return "\n".join(lines), payload, "tickets.manage:self_bootstrap_summary"

    def _command_event(self, event: str, command_id: str, data: dict[str, Any]) -> dict[str, Any]:
        capability, operation = command_id.split(":", 1) if ":" in command_id else (command_id, "")
        return {
            "event": event,
            "detail": data.get("detail") or f"{command_id} {event.removeprefix('command.')}",
            "data": {
                "command": {"id": command_id, "capability": capability, "operation": operation},
                **data,
            },
        }
