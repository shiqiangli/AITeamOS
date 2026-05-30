"""
Knowledge Context — 不变量守护 (arch.md §2.2.1)。

I-K-1: confidence.value ∈ [0, 1]
I-K-2: tier=Facts 不参与时间衰减 (λ=0)
I-K-3: lifecycle=quarantined 时召回屏蔽
I-K-4: MemoryEdge 独立聚合（不在 Node 聚合内）
I-K-5: Edge CRUD 不锁定 Node
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import MemoryEdge, MemoryNode


# ---------------------------------------------------------------------------
# 异常类型
# ---------------------------------------------------------------------------


class InvariantViolationError(ValueError):
    """不变量违反异常。"""

    def __init__(self, invariant: str, message: str):
        self.invariant = invariant
        super().__init__(f"[{invariant}] {message}")


# ---------------------------------------------------------------------------
# I-K-1: Confidence 范围
# ---------------------------------------------------------------------------

CONFIDENCE_MIN = Decimal("0.000")
CONFIDENCE_MAX = Decimal("1.000")
THRESHOLD_QUARANTINE = Decimal("0.300")


def validate_confidence_value(value: Decimal) -> None:
    """I-K-1: confidence.value must be in [0, 1]."""
    if not (CONFIDENCE_MIN <= value <= CONFIDENCE_MAX):
        raise InvariantViolationError(
            "I-K-1",
            f"Confidence value {value} out of range [0, 1]",
        )


# ---------------------------------------------------------------------------
# I-K-2: Facts 不参与时间衰减
# ---------------------------------------------------------------------------


def is_decay_eligible(node: MemoryNode) -> bool:
    """I-K-2: tier=Facts 的 confidence 不参与时间衰减 (λ=0)。

    仅由级联失效驱动置信度变更。
    """
    from .models import Tier

    return node.tier != Tier.FACTS


# ---------------------------------------------------------------------------
# I-K-3: Quarantined 时召回屏蔽
# ---------------------------------------------------------------------------


def is_recallable(node: MemoryNode) -> bool:
    """I-K-3: lifecycle=quarantined/deprecated/archived 时，召回路径必须屏蔽。

    分配/查询/审计仍可见。
    """
    from .models import LifecycleState

    _NON_RECALLABLE = frozenset({
        LifecycleState.QUARANTINED,
        LifecycleState.DEPRECATED,
        LifecycleState.ARCHIVED,
    })
    return node.lifecycle not in _NON_RECALLABLE


def assert_recallable(node: MemoryNode) -> None:
    """Raise if node is not recallable."""
    if not is_recallable(node):
        raise InvariantViolationError(
            "I-K-3",
            f"Memory {node.id} is quarantined and cannot be recalled",
        )


# ---------------------------------------------------------------------------
# I-K-4: MemoryEdge 独立聚合
# ---------------------------------------------------------------------------


def assert_edge_not_in_node_aggregate(edge: MemoryEdge) -> None:
    """I-K-4: MemoryEdge 是独立聚合根，不归属 MemoryNode 聚合。

    这是架构约束，通过代码结构保证（Edge 有独立 Repository）。
    此函数作为运行时断言，确保 Edge 不持有对 Node 聚合的引用。
    """
    if hasattr(edge, "_node_aggregate"):
        raise InvariantViolationError(
            "I-K-4",
            "MemoryEdge must not hold reference to MemoryNode aggregate",
        )


# ---------------------------------------------------------------------------
# I-K-5: Edge CRUD 不锁定 Node
# ---------------------------------------------------------------------------


def assert_edge_operation_no_node_lock(
    source_id: "MemoryId",
    target_id: "MemoryId",
    *,
    locked_ids: set["MemoryId"] | None = None,
) -> None:
    """I-K-5: Edge 操作不需要锁定 source/target MemoryNode。

    在测试中验证 Edge 仓储操作不涉及 Node 的 lock_for_update。
    """
    if locked_ids and (source_id in locked_ids or target_id in locked_ids):
        raise InvariantViolationError(
            "I-K-5",
            f"Edge operation must not lock source/target nodes "
            f"(source={source_id}, target={target_id})",
        )


# ---------------------------------------------------------------------------
# 衰减参数 (arch.md §2.6)
# ---------------------------------------------------------------------------

# 衰减系数 λ: 半衰期 = ln(2)/λ
# patterns: 半衰期 ~180 天 → λ = 1/180
# principles: 半衰期 ~365 天 → λ = 1/365
DECAY_LAMBDA = {
    "patterns": Decimal("1") / Decimal("180"),
    "principles": Decimal("1") / Decimal("365"),
}


def compute_decay_factor(tier_name: str, days_elapsed: float) -> Decimal:
    """计算衰减因子: exp(-λ * days)。"""
    import math

    lam = DECAY_LAMBDA.get(tier_name)
    if lam is None or lam == 0:
        return Decimal("1")
    factor = math.exp(-float(lam) * days_elapsed)
    return Decimal(str(factor))
