"""Clara product-level action planning for execution dispatch."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .ai_engine_config_store import ai_engine_secrets, load_ai_engine_config
from .ai_engine_runtime_config import AiEngineRuntimeConfig
from .chat_action_plan import ChatActionPlan, normalize_chat_action_plan
from .chat_kernel_catalog import CHAT_ACTION_TO_COMMAND_ID
from .chat_kernel_planning import local_kernel_heuristics_allowed, should_use_llm_command_planner
from .chat_terminal_utils import extract_terminal_command_line, is_terminal_run_request
from .capability_service import local_kernel_command_prompt, local_kernel_command_union
from .langchain_model_provider import LangChainModelProvider

_TICKET_ID_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b|\b(?:ticket-[A-Za-z0-9_.:-]+|(?:rd|pv|arch|rel|mem|doc|ops|trace)-\d{4,})\b", re.IGNORECASE)
_LIST_EMPLOYEES_EN_RE = re.compile(r"\b(list|show|display|view)\b.*\b(ai\s+)?employees\b|\bemployees\b.*\b(list|show|all|available)\b", re.IGNORECASE)
_LIST_CODE_REPOSITORIES_EN_RE = re.compile(r"\b(list|show|display|view)\b.*\b(code\s+)?(repos?|repositories)\b|\b(code\s+)?(repos?|repositories)\b.*\b(list|show|all|available)\b", re.IGNORECASE)
_INSPECT_CODE_REPOSITORY_EN_RE = re.compile(r"\b(inspect|search|read|check|review|analy[sz]e)\b.*\b(codebase|source|files?|repos?|repositories|repository|implementation)\b|\b(codebase|source|files?|repos?|repositories|repository|implementation)\b.*\b(inspect|search|read|check|review|analy[sz]e)\b", re.IGNORECASE)
_IMPLEMENT_TICKET_RE = re.compile(
    r"\b(implement|fix|patch|apply|modify|edit|change|update)\b.*\b(ticket|codebase|source|files?|repos?|repositories|repository|implementation|bug|feature)\b|"
    r"\b(ticket|codebase|source|files?|repos?|repositories|repository|implementation|bug|feature)\b.*\b(implement|fix|patch|apply|modify|edit|change|update)\b",
    re.IGNORECASE,
)
_SEARCH_KNOWLEDGE_EN_RE = re.compile(r"\b(search|query|find|read)\b.*\b(knowledge|docs?|documents?|memories|decisions)\b|\b(knowledge|docs?|documents?|memories|decisions)\b.*\b(search|query|find|read)\b", re.IGNORECASE)
_PERMISSION_RE = re.compile(r"kernel\.permissions|permissions?\.inspect|\bpermissions?\b|\bcapabilities\b|权限|授权|能不能|可以.*(创建|删除|执行)")
_SELF_BOOTSTRAP_RE = re.compile(r"self[- ]?bootstrap|自举|learning summary|学到了什么|复用了哪些经验|下一批怎么做", re.IGNORECASE)
_SELF_BOOTSTRAP_START_RE = re.compile(
    r"(start|create|open|run|launch|bootstrap)\b.*\b(self[- ]?bootstrap|improvement|batch)\b|"
    r"\bself[- ]?bootstrap\b.*\b(start|create|open|run|launch|batch)\b|"
    r"启动.*自举|创建.*自举|开始.*自举|运行.*自举|启动.*下一批|创建.*下一批|开始.*下一批|运行.*下一批|创建.*改进.*ticket",
    re.IGNORECASE,
)
_SELF_BOOTSTRAP_CLOSE_RE = re.compile(
    r"(close|complete|finish|summari[sz]e|review)\b.*\b(self[- ]?bootstrap|batch|learning|closure)\b|"
    r"\bself[- ]?bootstrap\b.*\b(close|complete|finish|closure|review)\b|"
    r"关闭.*自举|完成.*自举|收尾.*自举|复盘.*自举|自举.*收尾|自举.*复盘|批次.*复盘|批次.*收尾",
    re.IGNORECASE,
)
_CREATE_EMPLOYEE_RE = re.compile(r"\b(create_employee|create_ai_employee|add_employee|new_employee)\b|创建.*(?:ai)?(?:员工|成员)|新增.*(?:ai)?(?:员工|成员)|补一个.*(?:专家|成员|员工)", re.IGNORECASE)
_EDIT_EMPLOYEE_RE = re.compile(r"\b(edit_employee|edit_employee_profile|update_employee)\b|(?:更新|修改|编辑|调整|改成|改为).*(?:成员|员工|profile|summary|role|技能)|请把.*(?:summary|role|技能|profile).*?(?:改成|改为|添加)", re.IGNORECASE)
_DELETE_EMPLOYEE_RE = re.compile(r"\b(delete_employee|remove_employee|delete_ai_employee)\b|(?:删除|移除|删掉).*(?:成员|员工|employee|profile)", re.IGNORECASE)
_LIST_SKILLS_RE = re.compile(r"\b(list_skills|show_skills)\b|(?:列出|列表|有哪些|所有).*(?:skills?|技能)", re.IGNORECASE)
_CREATE_SKILL_RE = re.compile(r"\b(create_skill|new_skill|add_skill)\b|(?:创建|新增|新建|添加).*(?:skill|技能)", re.IGNORECASE)
_ASSIGN_SKILL_RE = re.compile(r"\b(assign_skill|assign_skill_to_employee|attach_skill)\b|(?:分配|关联|添加|assign|attach).*(?:skill|技能)|把\s*[A-Za-z0-9_.-]{2,80}(?:\s*skill)?\s*分配给", re.IGNORECASE)
_DELETE_SKILL_RE = re.compile(r"\b(delete_skill|remove_skill)\b|(?:删除|移除|删掉).*(?:skill|技能)", re.IGNORECASE)


class ChatActionPlanningService:
    def __init__(
        self,
        *,
        async_client_factory: Any | None = None,
        model_provider: LangChainModelProvider | None = None,
    ) -> None:
        self._model_provider = model_provider or LangChainModelProvider()

    async def plan_async(
        self,
        *,
        message: str,
        ticket_keys: list[str],
        employee_id: str,
        selected_ai_engine: str,
        workspace_id: str = "local",
        employee: dict[str, Any] | None = None,
        employee_profiles: list[dict[str, Any]] | None = None,
        recent_messages: list[dict[str, Any]] | None = None,
    ) -> tuple[ChatActionPlan, list[dict[str, Any]]]:
        local_plan = self.plan(
            message=message,
            ticket_keys=ticket_keys,
            employee_id=employee_id,
            employee_profiles=employee_profiles,
        )
        if not self._should_try_remote_planner(message, selected_ai_engine, workspace_id, local_plan):
            return local_plan, []
        try:
            remote_plan = await self._call_deepseek_action_planner(
                message=message,
                selected_ai_engine=selected_ai_engine,
                workspace_id=workspace_id,
                employee=employee or {},
                employee_profiles=employee_profiles or [],
                recent_messages=recent_messages or [],
            )
            planning_events = [
                {
                    "event": "command.intent_planner.completed",
                    "detail": "Planned governance action intent through DeepSeek.",
                    "data": {
                        **remote_plan.model_dump(mode="json"),
                        "kernel_command": CHAT_ACTION_TO_COMMAND_ID.get(remote_plan.action, "none"),
                    },
                }
            ]
            if remote_plan.action != "answer_only" and remote_plan.confidence >= 0.5:
                return remote_plan, planning_events
        except Exception as exc:
            planning_events = [
                {
                    "event": "command.intent_planner.failed",
                    "detail": "LLM command planner failed.",
                    "data": {"source": "langchain_deepseek_command_planner", "error": str(exc)[:300]},
                }
            ]
            if not local_kernel_heuristics_allowed(
                mode=os.environ.get("AITEAMOS_CHAT_KERNEL_COMMANDS", "fallback"),
                selected_ai_engine=selected_ai_engine,
            ):
                skipped_plan = normalize_chat_action_plan(
                    {
                        "action": "answer_only",
                        "arguments": {"message": message},
                        "confidence": 0,
                        "reason": "Remote AI Engine mode requires an explicit LLM ChatActionPlan; local heuristics were not used.",
                    },
                    source="remote_action_plan_required",
                )
                planning_events.append(
                    {
                        "event": "command.intent_planner.skipped",
                        "detail": "No explicit remote action plan was available; Kernel command execution was skipped.",
                        "data": {
                            **skipped_plan.model_dump(mode="json"),
                            "kernel_command": "none",
                        },
                    }
                )
                return skipped_plan, planning_events
            return local_plan, planning_events
        return local_plan, []

    def plan(
        self,
        *,
        message: str,
        ticket_keys: list[str],
        employee_id: str,
        employee_profiles: list[dict[str, Any]] | None = None,
    ) -> ChatActionPlan:
        text = message.strip()
        lowered = text.lower()
        arguments: dict[str, Any] = {"message": text}
        profiles = [profile for profile in employee_profiles or [] if isinstance(profile, dict)]
        ticket_id = ticket_keys[0] if ticket_keys else ""
        ticket_match = _TICKET_ID_RE.search(text)
        if not ticket_id and ticket_match:
            ticket_id = ticket_match.group(0)

        if _SELF_BOOTSTRAP_CLOSE_RE.search(text):
            if ticket_id:
                arguments["ticket_id"] = ticket_id
            return normalize_chat_action_plan(
                {"action": "self_bootstrap_close", "arguments": arguments, "confidence": 0.78, "reason": "User requested self-bootstrap batch closure and learning feedback."},
                source="clara_action_planning_service",
            )

        if _SELF_BOOTSTRAP_START_RE.search(text):
            arguments["batch_size"] = self._batch_size(text)
            return normalize_chat_action_plan(
                {"action": "self_bootstrap_start", "arguments": arguments, "confidence": 0.78, "reason": "User requested a governed self-bootstrap improvement batch."},
                source="clara_action_planning_service",
            )

        if _SELF_BOOTSTRAP_RE.search(text):
            return normalize_chat_action_plan(
                {"action": "self_bootstrap_summary", "arguments": arguments, "confidence": 0.76, "reason": "User requested self-bootstrap learning facts."},
                source="clara_action_planning_service",
            )

        if is_terminal_run_request(text):
            if ticket_id:
                arguments["ticket_id"] = ticket_id
            command_line = extract_terminal_command_line(text)
            if command_line:
                arguments["command_line"] = command_line
            return normalize_chat_action_plan(
                {"action": "terminal_run", "arguments": arguments, "confidence": 0.74, "reason": "User requested bounded terminal evidence for a Ticket."},
                source="clara_action_planning_service",
            )

        if ticket_id and ("human review" in lowered or "人工复核" in text or "人类复核" in text or "人工审核" in text):
            arguments.update({"ticket_id": ticket_id, "content": text, "report_type": "human_review_requested"})
            return normalize_chat_action_plan(
                {"action": "request_human_review", "arguments": arguments, "confidence": 0.76, "reason": "User requested human review for a Ticket."},
                source="clara_action_planning_service",
            )

        if _PERMISSION_RE.search(text):
            target = self._target_employee_hint(text)
            if target:
                arguments["target_employee_hint"] = target
            return normalize_chat_action_plan(
                {"action": "inspect_permissions", "arguments": arguments, "confidence": 0.74, "reason": "User requested deterministic Kernel permission facts."},
                source="clara_action_planning_service",
            )

        if _CREATE_SKILL_RE.search(text) and not _CREATE_EMPLOYEE_RE.search(text) and not _EDIT_EMPLOYEE_RE.search(text):
            arguments.update(
                {
                    "title": self._skill_name(text),
                    "description": self._skill_description(text),
                }
            )
            return normalize_chat_action_plan(
                {"action": "create_skill", "arguments": arguments, "confidence": 0.73, "reason": "User requested deterministic Skill asset creation."},
                source="clara_action_planning_service",
            )

        if _ASSIGN_SKILL_RE.search(text) and not _EDIT_EMPLOYEE_RE.search(text):
            arguments.update(
                {
                    "skill_id": self._skill_lookup(text),
                    "target_employee_id": self._target_employee_hint(text),
                }
            )
            return normalize_chat_action_plan(
                {"action": "assign_skill_to_employee", "arguments": arguments, "confidence": 0.72, "reason": "User requested deterministic Skill assignment to an Employee."},
                source="clara_action_planning_service",
            )

        if _DELETE_SKILL_RE.search(text):
            arguments["skill_id"] = self._skill_lookup(text) or self._skill_name(text)
            return normalize_chat_action_plan(
                {"action": "delete_skill", "arguments": arguments, "confidence": 0.72, "reason": "User requested deterministic Skill deletion."},
                source="clara_action_planning_service",
            )

        if _LIST_SKILLS_RE.search(text):
            return normalize_chat_action_plan(
                {"action": "list_skills", "arguments": arguments, "confidence": 0.7, "reason": "User requested Skill asset list."},
                source="clara_action_planning_service",
            )

        if _CREATE_EMPLOYEE_RE.search(text):
            arguments.update(
                {
                    "display_name": self._employee_display_name(text),
                    "kind": self._employee_kind(text),
                    "role": self._employee_role(text),
                    "responsibility": self._employee_summary_text(text),
                    "skills": self._skills(text),
                }
            )
            return normalize_chat_action_plan(
                {"action": "create_employee", "arguments": arguments, "confidence": 0.74, "reason": "User requested deterministic Employee creation."},
                source="clara_action_planning_service",
            )

        if _EDIT_EMPLOYEE_RE.search(text):
            arguments.update(
                {
                    "target_employee_id": self._target_employee_hint(text),
                    "summary": self._employee_summary_text(text),
                    "role": self._employee_role(text, require_marker=True),
                    "add_skills": self._skills(text),
                }
            )
            return normalize_chat_action_plan(
                {"action": "edit_employee_profile", "arguments": arguments, "confidence": 0.72, "reason": "User requested deterministic Employee profile update."},
                source="clara_action_planning_service",
            )

        if _DELETE_EMPLOYEE_RE.search(text):
            arguments["target_employee_id"] = self._target_employee_hint(text)
            return normalize_chat_action_plan(
                {"action": "delete_employee", "arguments": arguments, "confidence": 0.72, "reason": "User requested deterministic Employee deletion."},
                source="clara_action_planning_service",
            )

        if ticket_keys and ("human review" in lowered or "人工复核" in text or "人类复核" in text or "人工审核" in text):
            arguments.update({"ticket_id": ticket_keys[0], "content": text, "report_type": "human_review_requested"})
            return normalize_chat_action_plan(
                {"action": "request_human_review", "arguments": arguments, "confidence": 0.76, "reason": "User requested human review for a Ticket."},
                source="clara_action_planning_service",
            )

        if _LIST_EMPLOYEES_EN_RE.search(text) or ("列出" in text or "列表" in text or "有哪些" in text) and ("成员" in text or "员工" in text):
            return normalize_chat_action_plan(
                {"action": "list_employees", "arguments": arguments, "confidence": 0.7, "reason": "User requested Employee workforce list."},
                source="clara_action_planning_service",
            )

        if _LIST_CODE_REPOSITORIES_EN_RE.search(text) or ("列出" in text or "列表" in text or "有哪些" in text or "所有" in text) and (
            "代码仓库" in text or "代码库" in text or "仓库" in text
        ):
            return normalize_chat_action_plan(
                {"action": "list_code_repositories", "arguments": arguments, "confidence": 0.7, "reason": "User requested configured Code Repository list."},
                source="clara_action_planning_service",
            )

        if _SEARCH_KNOWLEDGE_EN_RE.search(text) or ("搜索" in text or "查询" in text or "读取" in text) and (
            "知识库" in text or "知识" in text or "文档" in text or "决策" in text or "记忆" in text or "Knowledge" in text
        ):
            arguments["query"] = self._knowledge_query(text)
            return normalize_chat_action_plan(
                {"action": "search_knowledge", "arguments": arguments, "confidence": 0.68, "reason": "User requested Knowledge search."},
                source="clara_action_planning_service",
            )

        if _INSPECT_CODE_REPOSITORY_EN_RE.search(text) or ticket_id and ("检查" in text or "读取" in text or "搜索" in text or "分析" in text or "查看" in text) and (
            "代码" in text or "源码" in text or "文件" in text or "实现" in text or "页面" in text
        ):
            arguments.update({"ticket_id": ticket_id, "query": text})
            return normalize_chat_action_plan(
                {"action": "inspect_code_repository", "arguments": arguments, "confidence": 0.68, "reason": "User requested bounded Code Repository inspection."},
                source="clara_action_planning_service",
            )

        if ticket_id and (_IMPLEMENT_TICKET_RE.search(text) or ("实现" in text or "修复" in text or "修改" in text or "改代码" in text or "打补丁" in text) and (
            "代码" in text or "源码" in text or "仓库" in text or "实现" in text or "ticket" in lowered
        )):
            arguments.update({"ticket_id": ticket_id, "query": text})
            return normalize_chat_action_plan(
                {"action": "implement_ticket", "arguments": arguments, "confidence": 0.7, "reason": "User requested Ticket-bound repository mutation through an external runtime."},
                source="clara_action_planning_service",
            )

        if (
            "create ticket" in lowered
            or "open ticket" in lowered
            or "新建" in text and ("工单" in text or "ticket" in lowered)
            or "创建" in text and ("工单" in text or "ticket" in lowered)
        ):
            assignee = self._mentioned_employee_id(text, fallback=employee_id if employee_id != "clara" else "")
            validator = self._mentioned_employee_id(text, preferred=("peter",))
            assigned_role = self._role_for_employee(assignee, profiles)
            validation_role = self._role_for_employee(validator, profiles)
            arguments.update(
                {
                    "title": self._title(text),
                    "description": text,
                    "assigned_employee_id": assignee,
                    "assigned_role": assigned_role if assignee else "AI Employee",
                    "validation_employee_id": validator,
                    "validation_role": validation_role if validator else "",
                }
            )
            return normalize_chat_action_plan(
                {"action": "create_ticket", "arguments": arguments, "confidence": 0.72, "reason": "User requested Ticket creation."},
                source="clara_action_planning_service",
            )

        validation_passed = (
            "validation passed" in lowered
            or "validated" in lowered
            or "验证通过" in text
            or "验收通过" in text
        )
        validation_failed = (
            "validation failed" in lowered
            or "validation rejected" in lowered
            or "验证失败" in text
            or "验收失败" in text
        )
        if ticket_keys and (validation_passed or validation_failed):
            arguments.update(
                {
                    "ticket_id": ticket_keys[0],
                    "content": text,
                    "report_type": "validation" if validation_passed else "validation_failed",
                }
            )
            return normalize_chat_action_plan(
                {
                    "action": "record_validation" if validation_passed else "record_failure",
                    "arguments": arguments,
                    "confidence": 0.72,
                    "reason": "User recorded a PV validation outcome for a Ticket.",
                },
                source="clara_action_planning_service",
            )

        if ticket_keys and (
            "request validation" in lowered
            or "请求验证" in text
            or "请求" in text and "验证" in text
            or "请求pv" in lowered
            or "pv review" in lowered
        ):
            validator = self._mentioned_employee_id(text, preferred=("peter",))
            arguments.update(
                {
                    "ticket_id": ticket_keys[0],
                    "validation_employee_id": validator,
                    "validation_role": "" if validator else "PV Validation",
                }
            )
            return normalize_chat_action_plan(
                {"action": "request_validation", "arguments": arguments, "confidence": 0.68, "reason": "User requested validation for a Ticket."},
                source="clara_action_planning_service",
            )

        explicit_report = (
            "report ticket" in lowered
            or "record ticket report" in lowered
            or "add ticket report" in lowered
            or "汇报" in text
            or "记录" in text and "工单" in text
            or "完成" in text and "工单" in text
        )
        if ticket_keys and explicit_report:
            arguments.update({"ticket_id": ticket_keys[0], "content": text, "report_type": "progress"})
            return normalize_chat_action_plan(
                {"action": "append_report", "arguments": arguments, "confidence": 0.66, "reason": "User requested Ticket report/update."},
                source="clara_action_planning_service",
            )

        if ticket_match and not ticket_keys:
            arguments["ticket_id"] = ticket_match.group(0)

        return normalize_chat_action_plan(
            {"action": "answer_only", "arguments": arguments, "confidence": 0.5, "reason": "No governed Ticket mutation requested."},
            source="clara_action_planning_service",
        )

    def _should_try_remote_planner(
        self,
        message: str,
        selected_ai_engine: str,
        workspace_id: str,
        local_plan: ChatActionPlan,
    ) -> bool:
        runtime = self._deepseek_runtime(workspace_id)
        if not should_use_llm_command_planner(
            message=message,
            selected_ai_engine=selected_ai_engine,
            has_deepseek_api_key=bool(runtime.secrets.get("deepseek_api_key")) if runtime is not None else False,
        ):
            return False
        heuristics_allowed = local_kernel_heuristics_allowed(
            mode=os.environ.get("AITEAMOS_CHAT_KERNEL_COMMANDS", "fallback"),
            selected_ai_engine=selected_ai_engine,
        )
        if not heuristics_allowed:
            return True
        return local_plan.action == "create_employee" and "补一个" in message

    async def _call_deepseek_action_planner(
        self,
        *,
        message: str,
        selected_ai_engine: str,
        workspace_id: str,
        employee: dict[str, Any],
        employee_profiles: list[dict[str, Any]],
        recent_messages: list[dict[str, Any]],
    ) -> ChatActionPlan:
        runtime = self._deepseek_runtime(workspace_id)
        if runtime is None or not runtime.deepseek_enabled(selected_ai_engine) or not runtime.secrets.get("deepseek_api_key"):
            raise RuntimeError("DeepSeek command planner is not configured")
        messages = [
            {
                "role": "system",
                "content": (
                    "You are AITeamOS Clara's Kernel command planner. "
                    "Classify the user's message into exactly one governed ChatActionPlan. "
                    "Do not answer the user. Return only a JSON object.\n\n"
                    f"Allowed commands:\n{local_kernel_command_prompt()}\n\n"
                    "JSON schema:\n"
                    "{"
                    f"\"command\":\"{local_kernel_command_union(include_none=True)}\","
                    "\"arguments\":{},"
                    "\"confidence\":0.0,"
                    "\"reason\":\"short reason\""
                    "}\n\n"
                    "Arguments for employees.manage:create: display_name, employee_id, kind, role, summary, responsibility, skills. "
                    "Arguments for tickets.manage:create: title, description, ticket_type, target_employee_id or target_employee_name, assigned_role, validation_employee_id, validation_role. "
                    "Choose a command only when the user intends to inspect or change AITeamOS governance facts, Ticket-flow assets, or workforce records. "
                    "Choose none when the user only needs a conversational answer."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "message": message,
                        "target_employee": employee,
                        "existing_employees": employee_profiles,
                        "recent_messages": self._recent_messages(recent_messages),
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        result = await self._model_provider.ainvoke(
            selected_engine="deepseek",
            runtime=runtime,
            messages=messages,
            max_tokens=600,
        )
        content = result.content
        if not content:
            raise RuntimeError("DeepSeek command planner returned no content")
        json_payload = self._extract_json_object(content)
        if json_payload is None:
            raise RuntimeError("DeepSeek command planner returned invalid JSON")
        return normalize_chat_action_plan(json_payload, source="langchain_deepseek_command_planner")

    def _deepseek_runtime(self, workspace_id: str) -> AiEngineRuntimeConfig | None:
        try:
            workspace = Path(workspace_id or ".").resolve()
            config = load_ai_engine_config(workspace / ".aiteamos" / "ai_engines.json")
            return AiEngineRuntimeConfig(config=config, secrets=ai_engine_secrets(config))
        except Exception:
            return None

    def _recent_messages(self, recent_messages: list[dict[str, Any]]) -> list[dict[str, str]]:
        history: list[dict[str, str]] = []
        for item in recent_messages[-8:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip()
            content = str(item.get("content") or "").strip()
            if role in {"user", "assistant"} and content:
                history.append({"role": role, "content": content})
        return history

    def _extract_json_object(self, content: str) -> dict[str, Any] | None:
        text = content.strip()
        if not text:
            return None
        try:
            payload = json.loads(text)
            return payload if isinstance(payload, dict) else None
        except json.JSONDecodeError:
            pass
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _title(self, text: str) -> str:
        normalized = " ".join(text.split())
        for marker in ("create ticket", "open ticket", "创建工单", "新建工单", "创建一个工单", "新建一个工单"):
            if marker in normalized.lower():
                normalized = normalized.lower().split(marker, 1)[-1].strip(" :：,，")
                break
        return normalized[:120] or "New Ticket"

    def _mentioned_employee_id(self, text: str, *, fallback: str = "", preferred: tuple[str, ...] = ()) -> str:
        lowered = text.lower()
        for candidate in preferred:
            if candidate.lower() in lowered:
                return candidate.lower()
        for name in ("alex", "peter", "clara", "nora", "victor"):
            if name in lowered:
                return name
        return fallback

    def _target_employee_hint(self, text: str) -> str:
        explicit = self._extract_first(
            [
                r"(?:target_employee_id|employee_id|id)\s*[:=：]\s*([A-Za-z0-9_-]{1,80})",
                r"(?:给|to)\s*([A-Z][A-Za-z0-9_-]{1,32})",
                r"(?:删除成员|删除|移除|删掉)\s*([A-Z][A-Za-z0-9_-]{1,32})",
                r"\bto\s+([A-Z][A-Za-z0-9_-]{1,32})\b",
            ],
            text,
        )
        if explicit:
            return self._slugify(explicit)
        mention = re.search(r"@([A-Za-z][\w-]*)", text)
        if mention:
            return mention.group(1)
        for match in re.finditer(r"\b([A-Z][A-Za-z0-9_-]{1,32})\b", text):
            value = match.group(1)
            if value.lower() not in {"clara", "kernel", "employee", "ticket"}:
                return value
        for name in ("Clara", "Alex", "Peter", "Nora", "Victor"):
            if name.lower() in text.lower():
                return name
        return ""

    def _extract_first(self, patterns: list[str], text: str) -> str:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            value = re.sub(r"\s+", " ", match.group(1)).strip(" :：,，。;；")
            if value:
                return value
        return ""

    def _slugify(self, value: str) -> str:
        slug = re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-_")
        slug = re.sub(r"-{2,}", "-", slug)
        return slug[:80]

    def _employee_display_name(self, text: str) -> str:
        return self._extract_first(
            [
                r"(?:名字叫|名为|叫做|叫)\s*([A-Za-z][A-Za-z0-9_. -]{0,63}|[\u4e00-\u9fff]{1,16})",
                r"(?:display_name|name)\s*[:=：]\s*([A-Za-z][A-Za-z0-9_. -]{0,63})",
                r"\bname\s*=\s*([A-Za-z][A-Za-z0-9_. -]{0,63})",
            ],
            text,
        )

    def _employee_kind(self, text: str) -> str:
        lowered = text.lower()
        return "human" if any(token in lowered for token in ("human", "user", "人类", "用户")) else "ai"

    def _employee_role(self, text: str, *, require_marker: bool = False) -> str:
        explicit = self._extract_first(
            [
                r"(?:角色|定位|role)\s*(?:是|为|改成|改为|更新为|设置为|to|=|:|：)\s*([^,，。;；\n]+)",
            ],
            text,
        )
        if explicit:
            return self._normalize_role(explicit)
        if require_marker:
            return ""
        lowered = f" {text.lower()} "
        if re.search(r"(?<![a-z0-9])pv(?![a-z0-9])", lowered) or "验证专家" in text:
            return "AI PV"
        for role, keywords in (
            ("AI Architect", ("architect", "架构")),
            ("AI Release", ("release", "发布")),
            ("AI QA / Harness Runner", ("qa", "harness", "测试")),
            ("AI Memory Curator", ("memory", "记忆")),
            ("AI RD / Implementer", ("implementer", "developer", "engineer", "研发", "开发")),
        ):
            if any(keyword in lowered for keyword in keywords):
                return role
        return ""

    def _normalize_role(self, value: str) -> str:
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
        return value.strip()

    def _employee_summary_text(self, text: str) -> str:
        return self._extract_first(
            [
                r"(?:summary|简介|摘要|描述)\s*(?:是|为|改成|改为|更新为|设置为|to|=|:|：)\s*([^,，。;；\n]+)",
                r"(?:负责|职责是|职责为)\s*([^,，。;；\n]+)",
            ],
            text,
        )

    def _skills(self, text: str) -> list[str]:
        value = self._extract_first(
            [
                r"(?:skills?|技能)\s*(?:是|为|改成|改为|更新为|设置为|to|=|:|：)\s*([^。;；\n]+)",
                r"(?:添加|增加|分配|add|assign)\s*(?:skills?|技能)\s*[:=：]?\s*([^。;；\n]+)",
            ],
            text,
        )
        if not value:
            return []
        return [item.strip(" ,，") for item in re.split(r"[,，、]\s*|\s+and\s+", value) if item.strip(" ,，")]

    def _skill_name(self, text: str) -> str:
        return self._extract_first(
            [
                r"(?:skill|技能)\s*(?:id|ID)?\s*[:=：]\s*([A-Za-z0-9_. -]{1,80})",
                r"(?:名字叫|名为|叫做|叫|named|called)\s*([A-Za-z][A-Za-z0-9_. -]{0,79})",
                r"\bcreate_skill\s+([A-Za-z][A-Za-z0-9_. -]{0,79})",
            ],
            text,
        )

    def _skill_lookup(self, text: str) -> str:
        explicit = self._extract_first(
            [
                r"(?:skill_id|skill id|技能\s*id|技能ID)\s*[:=：]\s*([A-Za-z0-9_-]{1,80})",
                r"(?:把|删除|移除|删掉|delete|remove|drop)\s*(?:skill\s*)?([A-Za-z0-9_.-]{2,80})(?:\s*skill|\s*分配|\s*给|。|$)",
                r"\b([A-Za-z][A-Za-z0-9_-]{2,80})\s+Skill\b",
            ],
            text,
        )
        return self._slugify(explicit) if explicit else ""

    def _skill_description(self, text: str) -> str:
        return self._extract_first(
            [
                r"(?:description|summary|用途|用于|用来|描述|说明)\s*(?:是|为|:|：)?\s*([^。;；\n]+)",
                r"(?:负责|能力是|能力为)\s*([^。;；\n]+)",
            ],
            text,
        )

    def _role_for_employee(self, employee_id: str, profiles: list[dict[str, Any]]) -> str:
        lookup = employee_id.strip().lower()
        if not lookup:
            return ""
        for profile in profiles:
            if str(profile.get("id") or "").strip().lower() == lookup:
                return str(profile.get("role") or "").strip()
        if lookup == "alex":
            return "AI RD / Implementer"
        if lookup == "peter":
            return "AI PV"
        if lookup == "clara":
            return "AI Team OS Manager"
        return ""

    def _knowledge_query(self, text: str) -> str:
        query = re.sub(r"\b(search|query|find|read)\b", " ", text, flags=re.IGNORECASE)
        for token in ("Clara", "请", "帮我", "搜索", "查询", "读取", "知识库", "知识", "文档", "决策", "记忆"):
            query = query.replace(token, " ")
        query = re.sub(r"\s+", " ", query).strip(" :：,，。")
        return query or text.strip()

    def _batch_size(self, text: str) -> int:
        match = re.search(r"\b([1-5])\b", text)
        if match:
            return int(match.group(1))
        chinese_numbers = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5}
        for token, value in chinese_numbers.items():
            if token in text:
                return value
        return 2
