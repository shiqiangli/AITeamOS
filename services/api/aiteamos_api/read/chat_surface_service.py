"""Route-free Chat API surface helpers.

FastAPI routes should own transport and status mapping. This service keeps
Employee, thread, skills, and AI-engine surface operations outside the route
module so the route stays a thin adapter around domain services.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .chat_ai_engine_service import ChatAiEngineSettingsService
from .chat_engine_thread_store import delete_thread_engine_state_mappings
from .chat_employee_projection_service import ChatEmployeeProjectionService
from .chat_models import (
    ChatAiEngineSettings,
    ChatAiEngineSettingsRequest,
    ChatAiEngineUpdateRequest,
    ChatEmployeeAiEngineUpdateRequest,
    ChatEmployeeSummary,
    ChatSkillSummary,
    ChatThreadActivateRequest,
    ChatThreadCreateRequest,
    ChatThreadListResponse,
    ChatThreadSummary,
    ConversationResponse,
)
from .chat_skill_service import ChatSkillCatalogService
from .chat_thread_service import ChatThreadMetadataService
from .employee_profile_service import (
    find_employee_profile,
    load_employee_profiles,
    normalize_employee_profile,
    write_employee_profile,
)

SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class ChatSurfaceError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class ChatSurfaceService:
    def __init__(
        self,
        *,
        workspace_root: Path | None = None,
        now: Callable[[], str] | None = None,
    ) -> None:
        self.workspace_root = workspace_root or _workspace_root()
        self.workspace_dir = self.workspace_root / ".aiteamos"
        self._now = now or (lambda: datetime.now(UTC).isoformat())

    def list_employees(self) -> list[ChatEmployeeSummary]:
        return [self._employee_summary(profile) for profile in self._load_employee_profiles()]

    def update_employee_ai_engine(
        self,
        employee_id: str,
        request: ChatEmployeeAiEngineUpdateRequest,
    ) -> ChatEmployeeSummary:
        safe_employee_id = self._require_safe_id(employee_id, field="employee_id")
        found = find_employee_profile(safe_employee_id, workspace_root=self.workspace_root)
        if found is None:
            raise ChatSurfaceError(404, "Employee not found")

        profile_path, profile = found
        default_ai_engine = self._call_ai_engine(
            lambda: self._ai_engine_service().require_employee_default_ai_engine(request.default_ai_engine)
        )
        ai_engine = profile.get("ai_engine") if isinstance(profile.get("ai_engine"), dict) else {}
        ai_engine = dict(ai_engine)
        ai_engine["default_engine"] = default_ai_engine
        profile["ai_engine"] = ai_engine
        profile["updated_at"] = self._now()
        normalized = normalize_employee_profile(profile, profile_path, workspace_root=self.workspace_root)
        write_employee_profile(profile_path, normalized)
        return self._employee_summary(normalized)

    def list_skills(self) -> list[ChatSkillSummary]:
        try:
            return sorted(self._skill_service().load_skills(), key=lambda skill: skill.id)
        except RuntimeError as exc:
            raise ChatSurfaceError(500, str(exc)) from exc

    def ai_engine_settings(self) -> ChatAiEngineSettings:
        return self._ai_engine_service().response()

    def update_ai_engine_settings(self, request: ChatAiEngineSettingsRequest) -> ChatAiEngineSettings:
        return self._call_ai_engine(lambda: self._ai_engine_service().update_legacy_settings(request))

    def update_ai_engine(self, engine_id: str, request: ChatAiEngineUpdateRequest) -> ChatAiEngineSettings:
        return self._call_ai_engine(lambda: self._ai_engine_service().update_engine(engine_id, request))

    def list_threads(self, employee_id: str) -> ChatThreadListResponse:
        employee = self._require_employee_summary(employee_id)
        return self._thread_service().list_employee_threads(employee, employees=self._all_employee_summaries())

    def create_thread(self, request: ChatThreadCreateRequest) -> ChatThreadSummary:
        employee = self._require_employee_summary(request.employee_id)
        thread_id = self._require_safe_id(
            f"employee-{ChatThreadMetadataService.safe_thread_component(employee.id)}-{uuid4().hex[:12]}",
            field="thread_id",
        )
        try:
            return self._thread_service().upsert_thread_metadata(
                employee=employee,
                thread_id=thread_id,
                title=request.title or f"New chat with {employee.display_name}",
                set_active=True,
                employees=self._all_employee_summaries(),
            )
        except ValueError as exc:
            raise ChatSurfaceError(400, str(exc)) from exc

    def activate_thread(self, thread_id: str, request: ChatThreadActivateRequest) -> ChatThreadSummary:
        try:
            return self._thread_service().activate_thread_metadata(
                thread_id,
                employee_id=request.employee_id,
                employees=self._all_employee_summaries(),
                require_employee=self._require_employee_summary,
            )
        except KeyError as exc:
            raise ChatSurfaceError(404, f"Thread not found: {thread_id}") from exc
        except ValueError as exc:
            raise ChatSurfaceError(400, str(exc)) from exc

    def delete_thread(self, thread_id: str) -> dict[str, Any]:
        thread_id = self._require_safe_id(thread_id, field="thread_id")
        summary = self._thread_summary(thread_id)
        if summary is None:
            raise ChatSurfaceError(404, f"Thread not found: {thread_id}")

        employee_id = summary.employee_id
        thread_service = self._thread_service()
        index = thread_service.hydrate_thread_index(self._all_employee_summaries())
        removed = False
        if thread_id in index["threads"]:
            del index["threads"][thread_id]
            removed = True
        if index["active_by_employee"].get(employee_id) == thread_id:
            index["active_by_employee"].pop(employee_id, None)
        if removed:
            thread_service.write_thread_index(index)

        try:
            thread_service.conversation_path(thread_id).unlink(missing_ok=True)
        except OSError:
            pass

        delete_thread_engine_state_mappings(self.workspace_dir, employee_id, thread_id)
        return {"status": "deleted", "thread_id": thread_id, "employee_id": employee_id}

    def get_thread(self, thread_id: str) -> ConversationResponse:
        thread_id = self._require_safe_id(thread_id, field="thread_id")
        return ConversationResponse(
            thread_id=thread_id,
            messages=self._thread_service().load_conversation_messages(thread_id),
            thread=self._thread_summary(thread_id),
        )

    def _ai_engine_service(self) -> ChatAiEngineSettingsService:
        return ChatAiEngineSettingsService(
            workspace_root=self.workspace_root,
            workspace_dir=self.workspace_dir,
            now=self._now,
        )

    def _employee_projection_service(self) -> ChatEmployeeProjectionService:
        return ChatEmployeeProjectionService(workspace_dir=self.workspace_dir)

    def _thread_service(self) -> ChatThreadMetadataService:
        return ChatThreadMetadataService(
            workspace_root=self.workspace_root,
            workspace_dir=self.workspace_dir,
            now=self._now,
        )

    def _skill_service(self) -> ChatSkillCatalogService:
        return ChatSkillCatalogService(workspace_root=self.workspace_root, workspace_dir=self.workspace_dir)

    def _load_employee_profiles(self) -> list[dict[str, Any]]:
        return load_employee_profiles(workspace_root=self.workspace_root)

    def _employee_summary(self, profile: dict[str, Any]) -> ChatEmployeeSummary:
        return self._employee_projection_service().employee_summary(profile)

    def _all_employee_summaries(self) -> list[ChatEmployeeSummary]:
        return self._employee_projection_service().all_employee_summaries(self._load_employee_profiles())

    def _require_employee_summary(self, employee_id: str) -> ChatEmployeeSummary:
        employee_id = self._require_safe_id(employee_id, field="employee_id")
        employee = self._employee_projection_service().employee_by_id(employee_id, self._load_employee_profiles())
        if employee is None:
            raise ChatSurfaceError(404, f"Employee not found: {employee_id}")
        return employee

    def _thread_summary(self, thread_id: str) -> ChatThreadSummary | None:
        try:
            return self._thread_service().thread_summary(thread_id, self._all_employee_summaries())
        except ValueError as exc:
            raise ChatSurfaceError(400, str(exc)) from exc

    @staticmethod
    def _require_safe_id(value: str, *, field: str) -> str:
        if not SAFE_ID_RE.fullmatch(value):
            raise ChatSurfaceError(400, f"Invalid {field}")
        return value

    @staticmethod
    def _call_ai_engine(callback: Callable[[], Any]) -> Any:
        try:
            return callback()
        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            detail = getattr(exc, "detail", None)
            if isinstance(status_code, int) and detail:
                raise ChatSurfaceError(status_code, str(detail)) from exc
            raise


def _workspace_root() -> Path:
    explicit = os.environ.get("AITEAMOS_WORKSPACE_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().parents[4]
