"""Route-free Employee profile loading and normalization."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .ai_engine_selection import normalize_employee_default_ai_engine
from .chat_ai_engine_service import ChatAiEngineSettingsService

SAFE_EMPLOYEE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
CLARA_SYSTEM_EMPLOYEE_ID = "clara"
CLARA_SYSTEM_DISPLAY_NAME = "Clara"
CLARA_SYSTEM_ROLE = "AI Team OS Manager"

ROLE_DEFAULT_SKILLS: dict[str, list[str]] = {
    "AI Team OS Manager": [
        "ticket-specification",
        "employee-ticket-flow-design",
        "technical-decision",
        "validation-strategy",
        "product-model-review",
    ],
    "AI Architect": ["system-architecture-design", "architecture-review", "technical-decision", "product-model-review"],
    "AI PV": ["test-engineering", "validation-strategy", "evidence-review", "regression-check", "product-model-review"],
    "AI Release": ["resource-planning", "validation-strategy", "evidence-review", "regression-check"],
    "AI QA / Harness Runner": ["test-engineering", "validation-strategy", "evidence-review", "regression-check"],
    "AI Memory Curator": ["technical-decision"],
    "AI RD / Implementer": ["backend-api-implementation", "frontend-api-integration", "test-engineering"],
}


def load_employee_profiles(*, workspace_root: Path | None = None) -> list[dict[str, Any]]:
    """Load normalized Employee profiles without importing the chat route module."""

    _, workspace_dir = resolve_workspace_paths(workspace_root)
    employees_dir = workspace_dir / "employees"
    ensure_clara_system_employee(workspace_root=workspace_root)

    employees_by_id: dict[str, dict[str, Any]] = {}
    for path in sorted(employees_dir.glob("*.yaml")):
        profile = normalize_employee_profile(read_employee_profile(path), path, workspace_root=workspace_root)
        profile_id = str(profile.get("id") or path.stem).lower()
        existing = employees_by_id.get(profile_id)
        if existing is None or path.stem == profile.get("id"):
            employees_by_id[profile_id] = profile

    return list(employees_by_id.values()) or [ensure_clara_system_employee(workspace_root=workspace_root)]


def ensure_clara_system_employee(*, workspace_root: Path | None = None) -> dict[str, Any]:
    profile_path = employee_profile_path(CLARA_SYSTEM_EMPLOYEE_ID, workspace_root=workspace_root)
    if profile_path.exists():
        raw_profile = read_employee_profile(profile_path)
    else:
        raw_profile = default_clara_profile()
    normalized = normalize_employee_profile(raw_profile, profile_path, workspace_root=workspace_root)
    if raw_profile != normalized or not profile_path.exists():
        timestamp = now()
        normalized["updated_at"] = timestamp
        normalized.setdefault("created_at", timestamp)
        write_employee_profile(profile_path, normalized)
    return normalized


def find_employee_profile(employee_id_or_name: str, *, workspace_root: Path | None = None) -> tuple[Path, dict[str, Any]] | None:
    ensure_clara_system_employee(workspace_root=workspace_root)
    lookup = employee_id_or_name.strip().lower()
    _, workspace_dir = resolve_workspace_paths(workspace_root)
    employees_dir = workspace_dir / "employees"
    if not employees_dir.exists():
        return None
    for path in sorted(employees_dir.glob("*.yaml")):
        profile = read_employee_profile(path)
        profile_id = str(profile.get("id") or path.stem)
        display_name = str(profile.get("display_name") or profile_id)
        if lookup in {profile_id.lower(), display_name.lower()}:
            profile.setdefault("id", profile_id)
            return path, profile
    return None


def normalize_employee_profile(
    profile: dict[str, Any],
    path: Path,
    *,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    normalized = dict(profile)
    profile_id = str(normalized.get("id") or path.stem)
    normalized["id"] = profile_id

    if is_clara_system_employee_id(profile_id):
        default_profile = default_clara_profile()
        normalized["id"] = CLARA_SYSTEM_EMPLOYEE_ID
        normalized["display_name"] = CLARA_SYSTEM_DISPLAY_NAME
        normalized["kind"] = "ai"
        normalized["role"] = CLARA_SYSTEM_ROLE
        normalized["summary"] = default_profile["summary"]
        normalized["personality"] = default_profile["personality"]
        normalized["responsibilities"] = default_profile["responsibilities"]
        if not normalized.get("skills"):
            normalized["skills"] = default_skills_for_role(CLARA_SYSTEM_ROLE)
        normalized["permissions"] = default_profile["permissions"]

        ai_engine = normalized.get("ai_engine") if isinstance(normalized.get("ai_engine"), dict) else {}
        ai_engine = dict(ai_engine)
        if not str(ai_engine.get("engine_identity") or "").strip():
            ai_engine["engine_identity"] = CLARA_SYSTEM_EMPLOYEE_ID
        ai_engine["preserve_engine_thread"] = True
        normalized["ai_engine"] = ai_engine
        normalized["system"] = {"protected": True, "bootstrap": True}

    kind = str(normalized.get("kind") or "ai")
    role = str(normalized.get("role") or "AI Employee")
    permissions = normalized.get("permissions")
    if not isinstance(permissions, list) or not permissions:
        normalized["permissions"] = default_permissions(kind, role)
    normalized["permissions"] = string_items(normalized.get("permissions"))
    skills = string_items(normalized.get("skills")) or default_skills_for_role(role)
    normalized["skills"] = skills
    normalized["skill_refs"] = string_items(normalized.get("skill_refs")) or list(skills)
    normalized["personality_tags"] = personality_tags(normalized)
    normalized["capability_tags"] = capability_tags(
        normalized,
        role=role,
        skills=skills,
        permissions=normalized["permissions"],
    )
    normalized["memory_scopes"] = string_items(normalized.get("memory_scopes")) or ["aiteamos", f"employee:{profile_id}"]

    ai_engine = normalized.get("ai_engine") if isinstance(normalized.get("ai_engine"), dict) else {}
    ai_engine = dict(ai_engine)
    ai_engine.setdefault("mode", "human" if kind == "human" else "external_or_file_stub")
    ai_engine.setdefault("engine_identity", profile_id)
    ai_engine.setdefault("preserve_engine_thread", True)
    ai_engine["default_engine"] = require_employee_default_ai_engine(
        str(ai_engine.get("default_engine") or ai_engine.get("default_ai_engine") or "system"),
        workspace_root=workspace_root,
    )
    normalized["ai_engine"] = ai_engine
    normalized["preferred_runtime"] = str(
        normalized.get("preferred_runtime")
        or ai_engine.get("runtime")
        or ai_engine.get("default_engine")
        or "universal_employee_agent"
    )
    permission_policy = normalized.get("permission_policy") if isinstance(normalized.get("permission_policy"), dict) else {}
    normalized["permission_policy"] = {
        "permissions": normalized["permissions"],
        "requires_approval_for": permission_policy.get("requires_approval_for", []),
        **permission_policy,
    }
    handoff_policy = normalized.get("handoff_policy") if isinstance(normalized.get("handoff_policy"), dict) else {}
    normalized["handoff_policy"] = {
        "can_receive_handoffs": kind != "human",
        "escalate_to": "clara",
        **handoff_policy,
    }
    current_load = normalized.get("current_load") if isinstance(normalized.get("current_load"), dict) else {}
    normalized["current_load"] = {
        "active_ticket_count": int(current_load.get("active_ticket_count") or 0),
        "status": str(current_load.get("status") or "available"),
        **current_load,
    }
    return normalized


def employee_profile_path(employee_id: str, *, workspace_root: Path | None = None) -> Path:
    if not SAFE_EMPLOYEE_ID_RE.fullmatch(employee_id):
        raise ValueError("Invalid employee_id")
    _, workspace_dir = resolve_workspace_paths(workspace_root)
    return workspace_dir / "employees" / f"{employee_id}.yaml"


def read_employee_profile(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise RuntimeError(f"Cannot read {path.name}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid employee profile: {path.name}")
    return data


def write_employee_profile(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def resolve_workspace_paths(workspace_root: Path | None = None) -> tuple[Path, Path]:
    configured = workspace_root or (Path(os.environ["AITEAMOS_WORKSPACE_DIR"]) if os.environ.get("AITEAMOS_WORKSPACE_DIR") else None)
    root = (configured.expanduser() if configured is not None else Path(__file__).resolve().parents[4]).resolve()
    if root.name == ".aiteamos":
        return root.parent, root
    return root, root / ".aiteamos"


def require_employee_default_ai_engine(value: str, *, workspace_root: Path | None = None) -> str:
    root, workspace_dir = resolve_workspace_paths(workspace_root)
    service = ChatAiEngineSettingsService(workspace_root=root, workspace_dir=workspace_dir, now=now)
    return service.require_employee_default_ai_engine(value)


def default_skills_for_role(role: str) -> list[str]:
    return list(ROLE_DEFAULT_SKILLS.get(role, []))


def default_permissions(kind: str, role: str) -> list[str]:
    if kind == "human":
        return ["chat", "read_local_assets"]
    permissions = ["chat", "read_local_assets", "write_trace"]
    if role == "AI RD / Implementer":
        permissions.append("propose_code_change")
    if role in {"AI PV", "AI QA / Harness Runner", "AI Release"}:
        permissions.append("read_validation_evidence")
    return permissions


def string_items(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[,;/，；、]|\band\b", value) if part.strip()]
    return []


def is_clara_system_employee_id(value: str | None) -> bool:
    return (value or "").strip().lower() == CLARA_SYSTEM_EMPLOYEE_ID


def default_clara_profile() -> dict[str, Any]:
    timestamp = now()
    return {
        "id": CLARA_SYSTEM_EMPLOYEE_ID,
        "display_name": CLARA_SYSTEM_DISPLAY_NAME,
        "kind": "ai",
        "role": CLARA_SYSTEM_ROLE,
        "summary": (
            "User-facing AI Team OS Manager for Ticket flow, delegation, validation, "
            "assets, and final reporting."
        ),
        "personality": "Calm, concise, explicit about blockers, and careful with handoffs.",
        "responsibilities": [
            "Understand human goals and turn them into traceable Tickets with owner, validator, context, and acceptance criteria.",
            "Route Tickets to the right AI Employee, request handoffs or PV validation, and keep the Ticket event ledger current.",
            "Summarize reports, evidence, decisions, blockers, and next actions back to the human.",
            "Govern Ticket-flow assets such as Skills, Memories, Decisions, Reports, Evidence, Knowledge access, and Capabilities.",
        ],
        "skills": default_skills_for_role(CLARA_SYSTEM_ROLE),
        "ai_engine": {
            "mode": "external_or_file_stub",
            "engine_identity": CLARA_SYSTEM_EMPLOYEE_ID,
            "default_engine": normalize_employee_default_ai_engine("system"),
            "preserve_engine_thread": True,
        },
        "permissions": [
            "chat",
            "manage_employees",
            "manage_skills",
            "manage_memory",
            "manage_knowledge",
            "manage_tickets",
            "read_local_assets",
            "route_employee",
            "run_terminal",
            "write_trace",
        ],
        "system": {"protected": True, "bootstrap": True},
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def personality_tags(profile: dict[str, Any]) -> list[str]:
    explicit = string_items(profile.get("personality_tags"))
    if explicit:
        return explicit
    return string_items(profile.get("personality"))


def capability_tags(
    profile: dict[str, Any],
    *,
    role: str,
    skills: list[str],
    permissions: list[str],
) -> list[str]:
    explicit = string_items(profile.get("capability_tags"))
    if explicit:
        return sorted(set(explicit))
    role_tag = slug_tag(role)
    tags = [role_tag, *skills, *[permission.replace(":", "-") for permission in permissions]]
    return sorted({tag for tag in tags if tag})


def slug_tag(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def now() -> str:
    return datetime.now(UTC).isoformat()
