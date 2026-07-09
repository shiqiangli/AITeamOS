"""Route-free Chat thread metadata service."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .chat_models import (
    ChatEmployeeSummary,
    ChatRunContext,
    ChatThreadListResponse,
    ChatThreadSummary,
    ConversationMessage,
)
from .chat_thread_store import (
    conversation_path as store_conversation_path,
    conversation_saved_path as store_conversation_saved_path,
    load_conversation_messages as store_load_conversation_messages,
    load_thread_index as store_load_thread_index,
    thread_index_saved_path as store_thread_index_saved_path,
    thread_title_from_message as store_thread_title_from_message,
    write_thread_index as store_write_thread_index,
)

SAFE_THREAD_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class ChatThreadMetadataService:
    def __init__(
        self,
        *,
        workspace_root: Path,
        workspace_dir: Path,
        now: Callable[[], str] | None = None,
    ) -> None:
        self.workspace_root = workspace_root
        self.workspace_dir = workspace_dir
        self._now = now or (lambda: datetime.now(UTC).isoformat())

    def conversation_path(self, thread_id: str) -> Path:
        return store_conversation_path(
            self.workspace_dir,
            thread_id,
            require_safe_id=lambda value: self.require_safe_id(value, field="thread_id"),
        )

    def load_conversation_messages(self, thread_id: str, *, limit: int | None = None) -> list[ConversationMessage]:
        return store_load_conversation_messages(
            self.workspace_dir,
            thread_id,
            message_model=ConversationMessage,
            require_safe_id=lambda value: self.require_safe_id(value, field="thread_id"),
            limit=limit,
        )

    def load_thread_index(self) -> dict[str, Any]:
        return store_load_thread_index(self.workspace_dir)

    def write_thread_index(self, index: dict[str, Any]) -> None:
        store_write_thread_index(self.workspace_dir, index, updated_at=self._now())

    def thread_index_saved_path(self) -> str:
        return store_thread_index_saved_path(self.workspace_dir, self.workspace_root)

    def conversation_saved_path(self, thread_id: str) -> str:
        return store_conversation_saved_path(
            self.workspace_dir,
            self.workspace_root,
            thread_id,
            require_safe_id=lambda value: self.require_safe_id(value, field="thread_id"),
        )

    def thread_title_from_message(self, content: str) -> str:
        return store_thread_title_from_message(content)

    def employee_default_thread_id(self, employee_id: str) -> str:
        return self.require_safe_id(f"employee-{self.safe_thread_component(employee_id)}-default", field="thread_id")

    def default_thread_title(self, employee: ChatEmployeeSummary, thread_id: str) -> str:
        if thread_id == self.employee_default_thread_id(employee.id):
            return f"{employee.display_name} default"
        return f"{employee.display_name} thread"

    def infer_thread_employee_id(self, thread_id: str, employees: list[ChatEmployeeSummary]) -> str | None:
        for employee in sorted(employees, key=lambda item: len(item.id), reverse=True):
            safe_employee = self.safe_thread_component(employee.id)
            if thread_id == self.employee_default_thread_id(employee.id) or thread_id.startswith(f"employee-{safe_employee}-"):
                return employee.id
        return None

    def thread_summary_from_record(self, thread_id: str, record: dict[str, Any]) -> ChatThreadSummary:
        return ChatThreadSummary(
            id=thread_id,
            employee_id=str(record.get("employee_id") or ""),
            title=str(record.get("title") or "New thread"),
            created_at=str(record.get("created_at") or self._now()),
            updated_at=str(record.get("updated_at") or record.get("last_message_at") or self._now()),
            last_message_at=str(record["last_message_at"]) if record.get("last_message_at") else None,
            message_count=int(record.get("message_count") or 0),
            archived=bool(record.get("archived", False)),
            saved_path=self.conversation_saved_path(thread_id),
        )

    def conversation_metadata(self, thread_id: str, employees: list[ChatEmployeeSummary]) -> dict[str, Any]:
        messages = self.load_conversation_messages(thread_id)
        first_user = next((message for message in messages if message.role == "user" and message.content.strip()), None)
        first_assistant = next((message for message in messages if message.employee_id), None)
        created_at = messages[0].timestamp if messages else self._now()
        updated_at = messages[-1].timestamp if messages else created_at
        employee_id = first_assistant.employee_id if first_assistant and first_assistant.employee_id else None
        employee_id = employee_id or self.infer_thread_employee_id(thread_id, employees)
        return {
            "employee_id": employee_id,
            "title": self.thread_title_from_message(first_user.content) if first_user else None,
            "created_at": created_at,
            "updated_at": updated_at,
            "last_message_at": updated_at if messages else None,
            "message_count": len(messages),
        }

    def hydrate_thread_index(self, employees: list[ChatEmployeeSummary]) -> dict[str, Any]:
        index = self.load_thread_index()
        threads = index["threads"]
        active_by_employee = index["active_by_employee"]
        employees = sorted(employees, key=self.employee_sort_key)
        employee_by_id = {employee.id: employee for employee in employees}
        changed = False
        now = self._now()

        for employee in employees:
            default_thread_id = self.employee_default_thread_id(employee.id)
            if default_thread_id not in threads:
                threads[default_thread_id] = {
                    "id": default_thread_id,
                    "employee_id": employee.id,
                    "title": self.default_thread_title(employee, default_thread_id),
                    "created_at": now,
                    "updated_at": now,
                    "last_message_at": None,
                    "message_count": 0,
                    "archived": False,
                }
                changed = True

        conversations_dir = self.workspace_dir / "conversations"
        if conversations_dir.exists():
            for path in sorted(conversations_dir.glob("*.jsonl")):
                thread_id = path.stem
                if not SAFE_THREAD_ID_RE.fullmatch(thread_id):
                    continue
                metadata = self.conversation_metadata(thread_id, employees)
                employee_id = metadata["employee_id"]
                if not employee_id:
                    continue
                existing = threads.get(thread_id) or {}
                record = {
                    "id": thread_id,
                    "employee_id": str(existing.get("employee_id") or employee_id),
                    "title": str(existing.get("title") or metadata.get("title") or "New thread"),
                    "created_at": str(existing.get("created_at") or metadata["created_at"]),
                    "updated_at": str(metadata["updated_at"] or existing.get("updated_at") or now),
                    "last_message_at": metadata.get("last_message_at") or existing.get("last_message_at"),
                    "message_count": int(metadata.get("message_count") or existing.get("message_count") or 0),
                    "archived": bool(existing.get("archived", False)),
                }
                if threads.get(thread_id) != record:
                    threads[thread_id] = record
                    changed = True

        for employee in employees:
            employee_threads = [
                self.thread_summary_from_record(thread_id, record)
                for thread_id, record in threads.items()
                if record.get("employee_id") == employee.id and not bool(record.get("archived", False))
            ]
            if not employee_threads:
                continue
            active_thread_id = active_by_employee.get(employee.id)
            if active_thread_id not in {thread.id for thread in employee_threads}:
                latest = max(employee_threads, key=lambda thread: (thread.last_message_at or thread.updated_at, thread.id))
                active_by_employee[employee.id] = latest.id
                changed = True

        for employee_id, active_thread_id in list(active_by_employee.items()):
            record = threads.get(active_thread_id)
            if employee_id not in employee_by_id or not record or record.get("employee_id") != employee_id:
                active_by_employee.pop(employee_id, None)
                changed = True

        if changed:
            self.write_thread_index(index)
        return index

    def upsert_thread_metadata(
        self,
        *,
        employee: ChatEmployeeSummary,
        thread_id: str,
        title: str | None = None,
        set_active: bool = False,
        employees: list[ChatEmployeeSummary] | None = None,
    ) -> ChatThreadSummary:
        thread_id = self.require_safe_id(thread_id, field="thread_id")
        index = self.hydrate_thread_index(employees or [employee])
        threads = index["threads"]
        record = dict(threads.get(thread_id) or {})
        now = self._now()
        record.setdefault("id", thread_id)
        record["employee_id"] = str(record.get("employee_id") or employee.id)
        record.setdefault("created_at", now)
        record["updated_at"] = now
        record.setdefault("last_message_at", None)
        record.setdefault("message_count", 0)
        record.setdefault("archived", False)

        next_title = (title or "").strip()
        if next_title:
            record["title"] = self.thread_title_from_message(next_title)
        else:
            record.setdefault("title", self.default_thread_title(employee, thread_id))

        threads[thread_id] = record
        if set_active:
            index["active_by_employee"][employee.id] = thread_id
        self.write_thread_index(index)
        return self.thread_summary_from_record(thread_id, record)

    def record_chat_thread_turn(
        self,
        context: ChatRunContext,
        *,
        last_message_at: str,
        employees: list[ChatEmployeeSummary],
    ) -> ChatThreadSummary:
        index = self.hydrate_thread_index(employees)
        threads = index["threads"]
        record = dict(threads.get(context.thread_id) or {})
        now = self._now()
        existing_title = str(record.get("title") or "").strip()
        title = existing_title
        if not title or title == self.default_thread_title(context.employee, context.thread_id):
            title = self.thread_title_from_message(context.request.message)

        messages = self.load_conversation_messages(context.thread_id)
        created_at = str(record.get("created_at") or (messages[0].timestamp if messages else now))
        record.update({
            "id": context.thread_id,
            "employee_id": context.employee.id,
            "title": title,
            "created_at": created_at,
            "updated_at": last_message_at,
            "last_message_at": last_message_at,
            "message_count": len(messages),
            "archived": False,
        })
        threads[context.thread_id] = record
        index["active_by_employee"][context.employee.id] = context.thread_id
        self.write_thread_index(index)
        return self.thread_summary_from_record(context.thread_id, record)

    def thread_summary(self, thread_id: str, employees: list[ChatEmployeeSummary]) -> ChatThreadSummary | None:
        thread_id = self.require_safe_id(thread_id, field="thread_id")
        index = self.hydrate_thread_index(employees)
        record = index["threads"].get(thread_id)
        return self.thread_summary_from_record(thread_id, record) if isinstance(record, dict) else None

    def list_employee_threads(
        self,
        employee: ChatEmployeeSummary,
        *,
        employees: list[ChatEmployeeSummary],
    ) -> ChatThreadListResponse:
        index = self.hydrate_thread_index(employees)
        threads = [
            self.thread_summary_from_record(thread_id, record)
            for thread_id, record in index["threads"].items()
            if record.get("employee_id") == employee.id and not bool(record.get("archived", False))
        ]
        threads.sort(key=lambda thread: (thread.last_message_at or thread.updated_at, thread.id), reverse=True)
        active_thread_id = index["active_by_employee"].get(employee.id) or self.employee_default_thread_id(employee.id)
        if active_thread_id not in {thread.id for thread in threads} and threads:
            active_thread_id = threads[0].id
        return ChatThreadListResponse(employee_id=employee.id, active_thread_id=active_thread_id, threads=threads)

    def activate_thread_metadata(
        self,
        thread_id: str,
        *,
        employee_id: str | None,
        employees: list[ChatEmployeeSummary],
        require_employee: Callable[[str], ChatEmployeeSummary],
    ) -> ChatThreadSummary:
        thread_id = self.require_safe_id(thread_id, field="thread_id")
        summary = self.thread_summary(thread_id, employees)
        if summary is None:
            if not employee_id:
                raise KeyError(thread_id)
            employee = require_employee(employee_id)
            return self.upsert_thread_metadata(employee=employee, thread_id=thread_id, set_active=True, employees=employees)

        employee = require_employee(employee_id or summary.employee_id)
        if summary.employee_id != employee.id:
            raise ValueError("Thread does not belong to the requested employee")
        return self.upsert_thread_metadata(
            employee=employee,
            thread_id=thread_id,
            title=summary.title,
            set_active=True,
            employees=employees,
        )

    @staticmethod
    def safe_thread_component(value: str) -> str:
        component = re.sub(r"[^A-Za-z0-9_.:-]+", "-", value.strip()).strip("-")
        return component[:80] or "employee"

    @staticmethod
    def employee_sort_key(employee: ChatEmployeeSummary) -> tuple[int, str]:
        if employee.id.strip().lower() == "clara":
            return (0, employee.display_name.lower())
        return (1, employee.display_name.lower())

    @staticmethod
    def require_safe_id(value: str, *, field: str) -> str:
        if not SAFE_THREAD_ID_RE.fullmatch(value):
            raise ValueError(f"Invalid {field}")
        return value
