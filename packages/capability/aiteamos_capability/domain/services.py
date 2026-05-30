"""
Capability Context — 领域服务 (arch.md §4.1)。

SkillRegistry: entry-point 发现 + Hot-plug
SkillConflictDetector: 副作用碰撞检测 (§4.1.2)
SkillCircuitBreaker: 熔断逻辑 (§4.1.4)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any, Protocol

from aiteamos_shared.types import SkillId, SemVer

from .models import CircuitState, Skill, SkillHealth, SkillManifest, SkillStatus, SideEffect
from .spi import ConflictReport, SkillSPI

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class SkillRepoLike(Protocol):
    async def get_by_id(self, id: Any, *, tx: Any = None) -> Skill | None: ...
    async def save(self, aggregate: Skill, *, tx: Any = None) -> None: ...
    async def lock_for_update(self, id: Any, *, tx: Any) -> Skill | None: ...


class EventBusLike(Protocol):
    async def publish(self, event: Any, *, partition_key: str) -> None: ...


# ---------------------------------------------------------------------------
# SkillConflictDetector (arch.md §4.1.2)
# ---------------------------------------------------------------------------


class SkillConflictDetector:
    """Saga 在 Run 装配时调用，检测计划加载的 Skill 集是否冲突。"""

    def detect(
        self,
        manifests: list[SkillManifest],
    ) -> list[ConflictReport]:
        """检测 Skill 集合的冲突。"""
        conflicts: list[ConflictReport] = []
        for i, a in enumerate(manifests):
            for b in manifests[i + 1 :]:
                # 副作用资源碰撞
                collision = self._side_effect_collides(
                    a.name, b.name, a.side_effects, b.side_effects
                )
                if collision:
                    conflicts.append(collision)

        return conflicts

    def _side_effect_collides(
        self,
        a_name: str,
        b_name: str,
        effects_a: list[SideEffect],
        effects_b: list[SideEffect],
    ) -> ConflictReport | None:
        """检测副作用资源碰撞。

        当两个 Skill 对同一资源有 write/delete/exclusive_lock 操作时冲突。
        """
        from .models import MutationKind

        write_kinds = {MutationKind.WRITE, MutationKind.DELETE, MutationKind.EXCLUSIVE_LOCK}

        a_writes = {
            (se.resource_kind, se.resource_pattern)
            for se in effects_a
            if se.mutation_kind in write_kinds
        }
        b_writes = {
            (se.resource_kind, se.resource_pattern)
            for se in effects_b
            if se.mutation_kind in write_kinds
        }

        overlap = a_writes & b_writes
        if overlap:
            pattern = next(iter(overlap))[1]
            return ConflictReport.resource_collision(a_name, b_name, pattern)

        return None


# ---------------------------------------------------------------------------
# SkillCircuitBreaker (arch.md §4.1.4)
# ---------------------------------------------------------------------------


@dataclass
class FailureStats:
    """Skill 失败统计。"""

    distinct_failed_tasks: int = 0
    failure_rate: Decimal = Decimal("0")
    total_invocations: int = 0
    failed_invocations: int = 0


class SkillCircuitBreaker:
    """Skill 熔断器 (arch.md §4.1.4)。

    当某 Skill 连续在 N 个不同 Task 中导致异常终止 → 熔断。
    """

    THRESHOLD_CONSECUTIVE_FAILS = 5
    THRESHOLD_FAILURE_RATE = Decimal("0.30")
    WINDOW = timedelta(hours=24)

    def __init__(
        self,
        *,
        repository: SkillRepoLike,
        event_bus: EventBusLike | None = None,
    ):
        self._repo = repository
        self._bus = event_bus

    def should_open_circuit(self, stats: FailureStats) -> bool:
        """判断是否应该触发熔断。"""
        return (
            stats.distinct_failed_tasks >= self.THRESHOLD_CONSECUTIVE_FAILS
            or stats.failure_rate >= self.THRESHOLD_FAILURE_RATE
        )

    async def on_failure(
        self,
        skill_id: SkillId,
        stats: FailureStats,
        *,
        tx: Any = None,
    ) -> Skill | None:
        """处理 Skill 调用失败。如果达到阈值则熔断。"""
        if not self.should_open_circuit(stats):
            return None

        return await self._open_circuit(skill_id, stats, tx=tx)

    async def _open_circuit(
        self,
        skill_id: SkillId,
        stats: FailureStats,
        *,
        tx: Any = None,
    ) -> Skill | None:
        """I-C-3: 触发熔断 — status 自动转 recalibrating。"""
        skill = await self._repo.lock_for_update(skill_id, tx=tx)
        if skill is None:
            logger.warning("Skill %s not found for circuit break", skill_id)
            return None

        if skill.health.circuit_state == CircuitState.OPEN:
            return skill  # 已熔断，幂等

        skill.open_circuit()
        await self._repo.save(skill, tx=tx)

        logger.warning(
            "Circuit opened for skill %s (failed_tasks=%d, rate=%.2f)",
            skill_id,
            stats.distinct_failed_tasks,
            float(stats.failure_rate),
        )
        return skill

    async def attempt_recovery(
        self,
        skill_id: SkillId,
        *,
        tx: Any = None,
    ) -> Skill | None:
        """尝试恢复: open → half_open。"""
        skill = await self._repo.lock_for_update(skill_id, tx=tx)
        if skill is None:
            return None

        if skill.health.circuit_state != CircuitState.OPEN:
            return skill

        skill.half_open_circuit()
        await self._repo.save(skill, tx=tx)
        return skill

    async def confirm_recovery(
        self,
        skill_id: SkillId,
        *,
        tx: Any = None,
    ) -> Skill | None:
        """确认恢复: half_open → closed (published)。"""
        skill = await self._repo.lock_for_update(skill_id, tx=tx)
        if skill is None:
            return None

        skill.close_circuit()
        await self._repo.save(skill, tx=tx)
        return skill


# ---------------------------------------------------------------------------
# SkillRegistry (arch.md §4.1.3) — 简化版
# ---------------------------------------------------------------------------


class SkillRegistry:
    """Skill 注册中心 (arch.md §4.1.3)。

    通过 Python entry-point group 'aiteamos.skills' 自动发现。
    Stage 1.3 提供基础框架，完整 Hot-plug 在后续 Stage 加固。
    """

    def __init__(self):
        self._registry: dict[str, SkillSPI] = {}

    def register(self, name: str, skill_impl: SkillSPI) -> None:
        """注册一个 Skill 实现。"""
        self._registry[name] = skill_impl
        logger.info("Registered skill: %s", name)

    def get(self, name: str) -> SkillSPI | None:
        """获取已注册的 Skill。"""
        return self._registry.get(name)

    def list_skills(self) -> list[str]:
        """列出所有已注册 Skill 名称。"""
        return list(self._registry.keys())

    def discover_from_entry_points(self) -> int:
        """从 entry-point 扫描发现 Skill (简化版)。

        Returns: 发现的 Skill 数量。
        """
        try:
            from importlib.metadata import entry_points

            eps = entry_points(group="aiteamos.skills")
            count = 0
            for ep in eps:
                try:
                    cls = ep.load()
                    instance = cls()
                    if isinstance(instance, SkillSPI):
                        self.register(ep.name, instance)
                        count += 1
                except Exception:
                    logger.exception("Failed to load skill from entry-point: %s", ep.name)
            return count
        except Exception:
            logger.debug("No entry-points available for skill discovery")
            return 0
