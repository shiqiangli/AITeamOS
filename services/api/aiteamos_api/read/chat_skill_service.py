"""Route-free Skill catalog helpers for Chat runtime and API surfaces."""

from __future__ import annotations

from pathlib import Path

from .chat_models import ChatSkillSummary
from .chat_tool_args import clean_extracted_value
from .employee_profile_service import load_employee_profiles
from .skill_usage_service import skill_usage_summary
from .validation_skill_catalog import VALIDATION_SKILL_DEFINITIONS, ValidationSkillDefinition


class ChatSkillCatalogService:
    def __init__(self, *, workspace_root: Path, workspace_dir: Path) -> None:
        self.workspace_root = workspace_root
        self.workspace_dir = workspace_dir

    @property
    def skills_dir(self) -> Path:
        return self.workspace_dir / "skills"

    def skill_titles(self, skill_ids: list[str]) -> list[str]:
        titles: list[str] = []
        for skill_id in skill_ids:
            skill_path = self.skills_dir / skill_id / "SKILL.md"
            if not skill_path.exists():
                titles.append(skill_id)
                continue
            title = skill_id
            try:
                for line in skill_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith("# "):
                        title = line.removeprefix("# ").strip() or skill_id
                        break
            except OSError:
                title = skill_id
            titles.append(title)
        return titles

    def load_skills(self) -> list[ChatSkillSummary]:
        local_skills = [] if not self.skills_dir.exists() else [
            self.skill_summary(path)
            for path in sorted(self.skills_dir.glob("*/SKILL.md"))
        ]
        local_ids = {skill.id for skill in local_skills}
        seeded_skills = [
            self.seed_skill_summary(skill)
            for skill in VALIDATION_SKILL_DEFINITIONS
            if skill.id not in local_ids
        ]
        return [*local_skills, *seeded_skills]

    def skill_summary(self, skill_path: Path) -> ChatSkillSummary:
        skill_id = skill_path.parent.name
        text = self.read_skill_text(skill_path)
        title, description = self.skill_title_and_description(skill_id, text)
        resources = [
            str(path.relative_to(skill_path.parent))
            for path in sorted(skill_path.parent.rglob("*"))
            if path.is_file() and path.name != "SKILL.md"
        ]
        return ChatSkillSummary(
            id=skill_id,
            title=title,
            description=description,
            content=text,
            assigned_employees=self.assigned_employees_for_skill(skill_id),
            resources=resources,
            saved_path=self.relative_path(skill_path),
            **skill_usage_summary(self.workspace_dir, skill_id),
        )

    def seed_skill_summary(self, skill: ValidationSkillDefinition) -> ChatSkillSummary:
        return ChatSkillSummary(
            id=skill.id,
            title=skill.title,
            description=skill.description,
            content=skill.content,
            assigned_employees=self.assigned_employees_for_skill(skill.id),
            resources=[],
            saved_path=skill.source_ref,
            source="builtin",
            **skill_usage_summary(self.workspace_dir, skill.id),
        )

    def read_skill_text(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"Cannot read skill: {path.parent.name}") from exc

    @staticmethod
    def skill_title_and_description(skill_id: str, text: str) -> tuple[str, str]:
        title = skill_id
        description = ""
        lines = text.splitlines()
        body_start = 0
        if lines and lines[0].strip() == "---":
            for index, line in enumerate(lines[1:], start=1):
                if line.strip() == "---":
                    body_start = index + 1
                    break
                if line.lower().startswith("name:") and title == skill_id:
                    title = clean_extracted_value(line.split(":", 1)[1])
                if line.lower().startswith("description:") and not description:
                    description = clean_extracted_value(line.split(":", 1)[1])

        for line in lines[body_start:]:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("# "):
                title = stripped.removeprefix("# ").strip() or title
                continue
            if stripped.startswith(">") and not description:
                description = stripped.lstrip(">").strip()
                continue
            if not description and not stripped.startswith("#"):
                description = stripped[:240]
            if title and description:
                break
        return title, description

    def assigned_employees_for_skill(self, skill_id: str) -> list[str]:
        assigned: list[str] = []
        for profile in load_employee_profiles(workspace_root=self.workspace_root):
            profile_skills = profile.get("skills") if isinstance(profile.get("skills"), list) else []
            if skill_id in {str(skill) for skill in profile_skills}:
                assigned.append(str(profile.get("id") or ""))
        return sorted(employee_id for employee_id in assigned if employee_id)

    def relative_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.workspace_root))
        except ValueError:
            return str(path)


def skill_titles(skill_ids: list[str], *, workspace_root: Path, workspace_dir: Path) -> list[str]:
    return ChatSkillCatalogService(workspace_root=workspace_root, workspace_dir=workspace_dir).skill_titles(skill_ids)
