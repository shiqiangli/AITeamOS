"""
Knowledge Context — 反思隔离缓冲区 (plan.md §3.2.3)。

ReflectionQuarantineBuffer:
- Flaky 结果进入隔离区，不直接驱动 Memory 提炼
- 自动释放条件: ≥3 次稳定一致
- 人工释放: 管理者显式批准
- 超时丢弃: 7 天未确认
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4

from aiteamos_shared.types import MemoryId, new_id

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

QUARANTINE_STABLE_COUNT = 3  # 自动释放所需稳定确认次数
QUARANTINE_TIMEOUT_DAYS = 7  # 超时丢弃天数


# ---------------------------------------------------------------------------
# 值对象
# ---------------------------------------------------------------------------


@dataclass
class QuarantineEntry:
    """隔离区条目。"""

    id: UUID = field(default_factory=uuid4)
    memory_id: MemoryId | None = None
    source_run_id: UUID | None = None
    reason: str = "flaky_result"
    stable_confirmations: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    released_at: datetime | None = None
    discarded_at: datetime | None = None
    released_by: str | None = None  # 'auto' | member_id


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class QuarantineStoreLike(Protocol):
    """隔离区存储协议。"""
    async def insert(self, entry: QuarantineEntry) -> None: ...
    async def get_by_id(self, entry_id: UUID) -> QuarantineEntry | None: ...
    async def get_by_memory_id(self, memory_id: MemoryId) -> QuarantineEntry | None: ...
    async def list_active(self) -> list[QuarantineEntry]: ...
    async def update(self, entry: QuarantineEntry) -> None: ...
    async def delete(self, entry_id: UUID) -> None: ...


# ---------------------------------------------------------------------------
# ReflectionQuarantineBuffer
# ---------------------------------------------------------------------------


class ReflectionQuarantineBuffer:
    """反思隔离缓冲区。

    防止 Flaky/不稳定结果污染 Memory 提炼:
    1. quarantine(): 将不稳定来源的 Memory 候选放入隔离区
    2. confirm_stable(): 确认一次稳定运行
    3. auto_release(): 稳定确认后自动释放
    4. discard_expired(): 超时丢弃
    5. manual_release(): 人工释放
    """

    def __init__(self, store: QuarantineStoreLike):
        self._store = store

    async def quarantine(
        self,
        *,
        memory_id: MemoryId | None = None,
        source_run_id: UUID | None = None,
        reason: str = "flaky_result",
    ) -> QuarantineEntry:
        """将条目放入隔离区。

        幂等: 同一 memory_id 不会重复隔离。
        """
        # 幂等检查
        if memory_id is not None:
            existing = await self._store.get_by_memory_id(memory_id)
            if existing is not None and existing.released_at is None and existing.discarded_at is None:
                return existing

        entry = QuarantineEntry(
            memory_id=memory_id,
            source_run_id=source_run_id,
            reason=reason,
        )
        await self._store.insert(entry)
        logger.info(
            "Quarantined: entry=%s memory=%s reason=%s",
            entry.id, memory_id, reason,
        )
        return entry

    async def confirm_stable(self, entry_id: UUID) -> QuarantineEntry | None:
        """确认一次稳定运行。

        达到 QUARANTINE_STABLE_COUNT 后自动释放。
        """
        entry = await self._store.get_by_id(entry_id)
        if entry is None:
            return None
        if entry.released_at is not None or entry.discarded_at is not None:
            return entry

        entry.stable_confirmations += 1
        await self._store.update(entry)

        if entry.stable_confirmations >= QUARANTINE_STABLE_COUNT:
            return await self.auto_release(entry_id)

        return entry

    async def auto_release(self, entry_id: UUID) -> QuarantineEntry | None:
        """自动释放: 稳定确认达标后释放。"""
        entry = await self._store.get_by_id(entry_id)
        if entry is None:
            return None
        if entry.released_at is not None:
            return entry

        entry.released_at = datetime.now(timezone.utc)
        entry.released_by = "auto"
        await self._store.update(entry)

        logger.info(
            "Auto-released quarantine entry=%s memory=%s",
            entry.id, entry.memory_id,
        )
        return entry

    async def manual_release(
        self, entry_id: UUID, *, released_by: str
    ) -> QuarantineEntry | None:
        """人工释放。"""
        entry = await self._store.get_by_id(entry_id)
        if entry is None:
            return None

        entry.released_at = datetime.now(timezone.utc)
        entry.released_by = released_by
        await self._store.update(entry)

        logger.info(
            "Manual-released quarantine entry=%s by=%s",
            entry.id, released_by,
        )
        return entry

    async def discard_expired(self) -> int:
        """丢弃超时条目 (7 天未确认)。

        Returns:
            丢弃的条目数量
        """
        active = await self._store.list_active()
        now = datetime.now(timezone.utc)
        timeout = timedelta(days=QUARANTINE_TIMEOUT_DAYS)
        discarded = 0

        for entry in active:
            if (now - entry.created_at) > timeout:
                entry.discarded_at = now
                await self._store.update(entry)
                discarded += 1

        if discarded > 0:
            logger.info("Discarded %d expired quarantine entries", discarded)
        return discarded

    async def is_quarantined(self, memory_id: MemoryId) -> bool:
        """检查 Memory 是否在隔离区中 (未释放、未丢弃)。"""
        entry = await self._store.get_by_memory_id(memory_id)
        if entry is None:
            return False
        return entry.released_at is None and entry.discarded_at is None
