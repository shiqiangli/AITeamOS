"""Route-free Employee projection helpers for Chat surfaces and runtime."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .ai_engine_selection import normalize_employee_default_ai_engine
from .chat_models import ChatEmployeeSummary
from .employee_load_service import employee_current_load
from .employee_profile_service import CLARA_SYSTEM_EMPLOYEE_ID

SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class ChatEmployeeProjectionService:
    def __init__(self, *, workspace_dir: Path) -> None:
        self.workspace_dir = workspace_dir

    @staticmethod
    def safe_thread_component(value: str) -> str:
        component = re.sub(r"[^A-Za-z0-9_.:-]+", "-", value.strip()).strip("-")
        return component[:80] or "employee"

    @classmethod
    def employee_default_thread_id(cls, employee_id: str) -> str:
        thread_id = f"employee-{cls.safe_thread_component(employee_id)}-default"
        if not SAFE_ID_RE.fullmatch(thread_id):
            raise ValueError("Invalid thread_id")
        return thread_id

    @staticmethod
    def is_clara_system_employee_id(value: str | None) -> bool:
        return (value or "").strip().lower() == CLARA_SYSTEM_EMPLOYEE_ID

    def employee_summary(self, profile: dict[str, Any]) -> ChatEmployeeSummary:
        ai_engine = profile.get("ai_engine") if isinstance(profile.get("ai_engine"), dict) else {}
        employee_id = str(profile.get("id", ""))
        current_load = employee_current_load(
            employee_id,
            base_load=profile.get("current_load") if isinstance(profile.get("current_load"), dict) else {},
            workspace_dir=self.workspace_dir,
        )
        return ChatEmployeeSummary(
            id=employee_id,
            display_name=str(profile.get("display_name") or profile.get("id") or "Unknown"),
            kind=str(profile.get("kind", "ai")),
            role=str(profile.get("role", "AI Employee")),
            summary=str(profile.get("summary", "")),
            skills=[str(skill) for skill in profile.get("skills", [])],
            skill_refs=[str(skill) for skill in profile.get("skill_refs", [])],
            capability_tags=[str(tag) for tag in profile.get("capability_tags", [])],
            personality_tags=[str(tag) for tag in profile.get("personality_tags", [])],
            memory_scopes=[str(scope) for scope in profile.get("memory_scopes", [])],
            preferred_runtime=str(profile.get("preferred_runtime") or ""),
            permission_policy=profile.get("permission_policy") if isinstance(profile.get("permission_policy"), dict) else {},
            handoff_policy=profile.get("handoff_policy") if isinstance(profile.get("handoff_policy"), dict) else {},
            current_load=current_load,
            ai_engine_mode=str(ai_engine.get("mode", "external_or_file_stub")),
            default_ai_engine=normalize_employee_default_ai_engine(str(ai_engine.get("default_engine") or "system")),
            preserve_engine_thread=bool(ai_engine.get("preserve_engine_thread", True)),
            default_thread_id=self.employee_default_thread_id(employee_id),
        )

    def employee_sort_key(self, employee: ChatEmployeeSummary) -> tuple[int, str]:
        if self.is_clara_system_employee_id(employee.id):
            return (0, employee.display_name.lower())
        return (1, employee.display_name.lower())

    def all_employee_summaries(self, profiles: list[dict[str, Any]]) -> list[ChatEmployeeSummary]:
        return sorted((self.employee_summary(profile) for profile in profiles), key=self.employee_sort_key)

    def employee_by_id(self, employee_id: str, profiles: list[dict[str, Any]]) -> ChatEmployeeSummary | None:
        lookup = employee_id.strip().lower()
        for profile in profiles:
            employee = self.employee_summary(profile)
            if employee.id.lower() == lookup:
                return employee
        return None

    @staticmethod
    def select_profile(
        profiles: list[dict[str, Any]],
        *,
        requested_employee_id: str | None,
        message: str,
    ) -> dict[str, Any]:
        by_id = {str(profile.get("id", "")).lower(): profile for profile in profiles}
        by_name = {
            str(profile.get("display_name", "")).lower(): profile
            for profile in profiles
            if profile.get("display_name")
        }

        mention = re.search(r"@([A-Za-z][\w-]*)", message)
        if mention:
            key = mention.group(1).lower()
            if key in by_id:
                return by_id[key]
            if key in by_name:
                return by_name[key]

        trimmed = message.strip().lower()
        for key, profile in {**by_id, **by_name}.items():
            if trimmed.startswith(f"{key},") or trimmed.startswith(f"{key}:") or trimmed.startswith(f"{key}，"):
                return profile

        if requested_employee_id:
            key = requested_employee_id.lower()
            if key in by_id:
                return by_id[key]
            raise KeyError(requested_employee_id)

        return by_id.get(CLARA_SYSTEM_EMPLOYEE_ID) or profiles[0]
