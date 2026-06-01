"""
Capability Context — 领域服务。

SkillRegistry: Skill 名称注册中心，支持 entry-point 自动发现。
"""

from __future__ import annotations

import logging
from typing import Any

from .models import Skill

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SkillRegistry — 简化版
# ---------------------------------------------------------------------------


class SkillRegistry:
    """Skill 注册中心。

    通过 Python entry-point group 'aiteamos.skills' 自动发现。
    """

    def __init__(self) -> None:
        self._registry: dict[str, Any] = {}

    def register(self, name: str, skill_impl: Any) -> None:
        """注册一个 Skill 实现。"""
        self._registry[name] = skill_impl
        logger.info("Registered skill: %s", name)

    def get(self, name: str) -> Any | None:
        """获取已注册的 Skill。"""
        return self._registry.get(name)

    def list_skills(self) -> list[str]:
        """列出所有已注册 Skill 名称。"""
        return list(self._registry.keys())

    def discover_from_entry_points(self) -> int:
        """从 entry-point 扫描发现 Skill。"""
        try:
            from importlib.metadata import entry_points

            eps = entry_points(group="aiteamos.skills")
            count = 0
            for ep in eps:
                try:
                    cls = ep.load()
                    instance = cls()
                    self.register(ep.name, instance)
                    count += 1
                except Exception:
                    logger.exception("Failed to load skill from entry-point: %s", ep.name)
            return count
        except Exception:
            logger.debug("No entry-points available for skill discovery")
            return 0
