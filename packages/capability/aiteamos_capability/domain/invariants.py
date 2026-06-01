"""
Capability Context — 不变量守护。

Skill 作为能力标签，不变量非常简单:
- Skill name 全局唯一
- 只有 draft 可以 publish
"""

from __future__ import annotations


class InvariantViolationError(ValueError):
    """不变量违反异常。"""

    def __init__(self, invariant: str, message: str):
        self.invariant = invariant
        super().__init__(f"[{invariant}] {message}")
