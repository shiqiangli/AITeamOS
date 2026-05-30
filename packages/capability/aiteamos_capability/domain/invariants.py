"""
Capability Context — 不变量守护 (arch.md §2.2.2)。

I-C-1: published 后 schema 只能向后兼容变更
I-C-2: Run 启动绑定具体版本，生命周期内不动态升级
I-C-3: circuit_state=open 时 status 自动转 recalibrating
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aiteamos_shared.types import SemVer

if TYPE_CHECKING:
    from .models import Skill, SkillManifest


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class InvariantViolationError(ValueError):
    """不变量违反异常。"""

    def __init__(self, invariant: str, message: str):
        self.invariant = invariant
        super().__init__(f"[{invariant}] {message}")


# ---------------------------------------------------------------------------
# I-C-1: Schema 向后兼容
# ---------------------------------------------------------------------------


def validate_schema_compatibility(
    old_schema: dict[str, Any],
    new_schema: dict[str, Any],
) -> bool:
    """检查 schema 变更是否向后兼容。

    向后兼容定义:
    - 新增字段必须是 optional (无 required 约束)
    - 不可删除已有字段
    - 不可变更已有字段类型

    简化版实现: 检查 required 字段集合不被缩小。
    """
    old_required = set(old_schema.get("required", []))
    new_required = set(new_schema.get("required", []))
    old_properties = set(old_schema.get("properties", {}).keys())
    new_properties = set(new_schema.get("properties", {}).keys())

    # 已有字段不可删除
    if not old_properties.issubset(new_properties):
        return False

    # 新增字段不能加入 required
    added_properties = new_properties - old_properties
    new_required_only = new_required - old_required
    if new_required_only.intersection(added_properties):
        return False

    return True


def assert_backward_compatible(
    old_manifest: SkillManifest,
    new_manifest: SkillManifest,
) -> None:
    """I-C-1: published Skill 的 schema 变更必须向后兼容。"""
    if not validate_schema_compatibility(
        old_manifest.input_schema, new_manifest.input_schema
    ):
        raise InvariantViolationError(
            "I-C-1",
            "input_schema change is not backward compatible",
        )
    if not validate_schema_compatibility(
        old_manifest.output_schema, new_manifest.output_schema
    ):
        raise InvariantViolationError(
            "I-C-1",
            "output_schema change is not backward compatible",
        )


# ---------------------------------------------------------------------------
# I-C-2: Run 绑定版本
# ---------------------------------------------------------------------------


def assert_version_locked_for_run(
    skill: Skill,
    bound_version: SemVer,
) -> None:
    """I-C-2: Run 启动时绑定的 Skill 版本在 Run 生命周期内不变。

    此检查确保绑定的版本与 Skill 当前注册版本一致。
    """
    if str(skill.version) != str(bound_version):
        raise InvariantViolationError(
            "I-C-2",
            f"Skill version mismatch: bound={bound_version}, current={skill.version}",
        )


# ---------------------------------------------------------------------------
# I-C-3: 熔断联动
# ---------------------------------------------------------------------------


def assert_circuit_status_consistent(skill: Skill) -> None:
    """I-C-3: circuit_state=open 时 status 必须为 recalibrating。"""
    from .models import CircuitState, SkillStatus

    if (
        skill.health.circuit_state == CircuitState.OPEN
        and skill.status != SkillStatus.RECALIBRATING
    ):
        raise InvariantViolationError(
            "I-C-3",
            f"circuit_state=open requires status=recalibrating, "
            f"got status={skill.status}",
        )


def is_skill_assignable(skill: Skill) -> bool:
    """Skill 是否可被分配 (published 且未熔断)。"""
    from .models import CircuitState, SkillStatus

    return (
        skill.status == SkillStatus.PUBLISHED
        and skill.health.circuit_state != CircuitState.OPEN
    )
