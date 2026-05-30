"""
Execution Sandbox (arch.md §3.4.6, 不变量 N5)。

执行沙箱:
- git worktree 隔离
- 熔断时整体回滚（destroy）
- 不变量 N5: sandbox.state 只能 active → merged | destroyed
- 非 merged 状态的沙箱产出不得进入 submit_deliverable 路径
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SandboxState
# ---------------------------------------------------------------------------


class SandboxState(StrEnum):
    """沙箱状态 — 不变量 N5: active → merged | destroyed (单向)。"""

    ACTIVE = "active"
    MERGED = "merged"
    DESTROYED = "destroyed"


# ---------------------------------------------------------------------------
# IllegalSandboxTransition
# ---------------------------------------------------------------------------


class IllegalSandboxTransition(Exception):
    """非法沙箱状态转换。"""

    def __init__(self, from_state: str, to_state: str):
        super().__init__(f"Illegal sandbox transition: {from_state} → {to_state}")


# ---------------------------------------------------------------------------
# Deliverable (sandbox output)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Deliverable:
    """沙箱产出物 — 仅 merged 状态可提交。"""

    deliverable_type: str  # code | document | design | config
    uri: str  # s3:// or git:// reference
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ExecutionSandbox
# ---------------------------------------------------------------------------


class ExecutionSandbox:
    """执行沙箱 — git worktree 隔离的执行环境。

    不变量 N5:
    - state 只能 active → merged | destroyed
    - 非 merged 状态的产出不得进入 submit_deliverable
    """

    # Valid transitions
    _VALID_TRANSITIONS: dict[SandboxState, set[SandboxState]] = {
        SandboxState.ACTIVE: {SandboxState.MERGED, SandboxState.DESTROYED},
        SandboxState.MERGED: set(),  # terminal
        SandboxState.DESTROYED: set(),  # terminal
    }

    def __init__(
        self,
        *,
        sandbox_id: UUID | None = None,
        run_id: UUID | None = None,
        task_id: str = "",
        worktree_path: str = "",
        state: SandboxState = SandboxState.ACTIVE,
        created_at: datetime | None = None,
    ):
        self.id: UUID = sandbox_id or uuid4()
        self.run_id = run_id
        self.task_id = task_id
        self.worktree_path = worktree_path
        self.state = state
        self.created_at = created_at or datetime.now(timezone.utc)
        self._deliverable: Deliverable | None = None

    @property
    def deliverable(self) -> Deliverable | None:
        return self._deliverable

    def merge_to_deliverable(
        self,
        *,
        deliverable_type: str = "code",
        uri: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Deliverable:
        """合并沙箱产出 → 生成 Deliverable。

        仅 active 沙箱可 merge；merge 后变为 merged 状态。
        """
        self._transition_to(SandboxState.MERGED)
        self._deliverable = Deliverable(
            deliverable_type=deliverable_type,
            uri=uri or f"s3://artifacts/runs/{self.run_id}/output",
            metadata=metadata or {},
        )
        logger.info(
            "Sandbox %s merged → deliverable (type=%s, uri=%s)",
            self.id,
            deliverable_type,
            self._deliverable.uri,
        )
        return self._deliverable

    def destroy(self, *, reason: str = "circuit_break") -> None:
        """销毁沙箱 — 整体回滚，不留脏状态。"""
        self._transition_to(SandboxState.DESTROYED)
        self._deliverable = None
        logger.info(
            "Sandbox %s destroyed (reason=%s)", self.id, reason
        )

    def is_output_submittable(self) -> bool:
        """不变量 N5: 仅 merged 状态的产出可提交。"""
        return self.state == SandboxState.MERGED

    def _transition_to(self, new_state: SandboxState) -> None:
        valid = self._VALID_TRANSITIONS.get(self.state, set())
        if new_state not in valid:
            raise IllegalSandboxTransition(self.state.value, new_state.value)
        self.state = new_state

    def __repr__(self) -> str:
        return f"ExecutionSandbox(id={self.id}, state={self.state}, task={self.task_id})"


# ---------------------------------------------------------------------------
# SandboxPool (simplified for testing)
# ---------------------------------------------------------------------------


class SandboxPool:
    """沙箱池 — 管理沙箱生命周期。"""

    def __init__(self):
        self._active: dict[UUID, ExecutionSandbox] = {}

    async def acquire(
        self,
        *,
        run_id: UUID,
        task_id: str = "",
        worktree_path: str = "",
    ) -> ExecutionSandbox:
        """创建并获取沙箱。"""
        sandbox = ExecutionSandbox(
            run_id=run_id,
            task_id=task_id,
            worktree_path=worktree_path,
        )
        self._active[sandbox.id] = sandbox
        return sandbox

    async def release(self, sandbox: ExecutionSandbox) -> None:
        """释放沙箱。"""
        self._active.pop(sandbox.id, None)

    async def get(self, sandbox_id: UUID) -> ExecutionSandbox | None:
        return self._active.get(sandbox_id)
