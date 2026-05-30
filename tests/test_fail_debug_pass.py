"""
Stage 3.2 测试 — Fail→Debug→Pass 闭环。

验证标准:
- Flaky 检测: retry_diverge, retry_no_change_pass
- ReflectionQuarantineBuffer: 隔离、稳定确认、自动释放、超时丢弃
- Harness fail → retry → pass 状态转换 (已有 test_execution_domain 覆盖)
- 高价值 Memory 提炼标记 (已有 extraction 测试覆盖)
"""

import pytest
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from aiteamos_validation.domain.models import (
    HarnessInvocation,
    HarnessOutcome,
    HarnessResult,
    HarnessTier,
    InvocationState,
)
from aiteamos_validation.application.flaky_detector import (
    FlakyDetector,
    FlakyVerdict,
)

from aiteamos_knowledge.application.quarantine import (
    QuarantineEntry,
    ReflectionQuarantineBuffer,
    QUARANTINE_STABLE_COUNT,
    QUARANTINE_TIMEOUT_DAYS,
)
from aiteamos_shared.types import new_id


# ---------------------------------------------------------------------------
# Mock Infrastructure
# ---------------------------------------------------------------------------


class InMemoryQuarantineStore:
    """In-memory 隔离区存储。"""

    def __init__(self):
        self._entries: dict[UUID, QuarantineEntry] = {}

    async def insert(self, entry: QuarantineEntry) -> None:
        self._entries[entry.id] = entry

    async def get_by_id(self, entry_id: UUID) -> QuarantineEntry | None:
        return self._entries.get(entry_id)

    async def get_by_memory_id(self, memory_id) -> QuarantineEntry | None:
        for e in self._entries.values():
            if e.memory_id == memory_id:
                return e
        return None

    async def list_active(self) -> list[QuarantineEntry]:
        return [
            e for e in self._entries.values()
            if e.released_at is None and e.discarded_at is None
        ]

    async def update(self, entry: QuarantineEntry) -> None:
        self._entries[entry.id] = entry

    async def delete(self, entry_id: UUID) -> None:
        self._entries.pop(entry_id, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_done_invocation(
    *,
    outcome: str = "pass",
    adapter_id: str = "test-adapter",
) -> HarnessInvocation:
    inv = HarnessInvocation(
        adapter_id=adapter_id,
        run_id=uuid4(),
        deliverable_ref="s3://test/patch",
        state=InvocationState.DONE,
    )
    inv.result = {"outcome": outcome, "metrics": {}}
    return inv


# ===========================================================================
# 1. FlakyDetector 测试
# ===========================================================================


class TestFlakyDetector:
    """测试 Flaky 检测器。"""

    def test_single_invocation_not_flaky(self):
        """单次调用 → 不 flaky。"""
        detector = FlakyDetector()
        inv = _make_done_invocation(outcome="pass")
        verdict = detector.detect_from_invocations([inv])
        assert not verdict.is_flaky

    def test_consistent_pass_not_flaky(self):
        """一致 pass → 不 flaky。"""
        detector = FlakyDetector()
        invocations = [_make_done_invocation(outcome="pass") for _ in range(3)]
        verdict = detector.detect_from_invocations(invocations)
        assert not verdict.is_flaky

    def test_retry_diverge_detected(self):
        """结果不一致 (pass + fail) → flaky。"""
        detector = FlakyDetector()
        invocations = [
            _make_done_invocation(outcome="pass"),
            _make_done_invocation(outcome="fail"),
            _make_done_invocation(outcome="pass"),
        ]
        verdict = detector.detect_from_invocations(invocations)
        assert verdict.is_flaky
        assert verdict.signal is not None
        assert verdict.signal.suspected_root_cause == "retry_diverge"
        assert verdict.signal.pass_count == 2
        assert verdict.signal.fail_count == 1

    def test_retry_no_change_pass_detected(self):
        """连续 fail 后 pass → flaky (retry_no_change_pass)。"""
        detector = FlakyDetector()
        invocations = [
            _make_done_invocation(outcome="fail"),
            _make_done_invocation(outcome="fail"),
            _make_done_invocation(outcome="pass"),
        ]
        verdict = detector.detect_from_invocations(invocations)
        assert verdict.is_flaky
        assert verdict.signal is not None
        # 可能匹配 retry_no_change_pass 或 retry_diverge
        assert verdict.signal.suspected_root_cause in (
            "retry_diverge", "retry_no_change_pass",
        )

    def test_pending_invocations_ignored(self):
        """pending 状态的 invocation 不参与检测。"""
        detector = FlakyDetector()
        invocations = [
            _make_done_invocation(outcome="pass"),
            HarnessInvocation(
                adapter_id="test", run_id=uuid4(),
                deliverable_ref="s3://test",
                state=InvocationState.PENDING,
            ),
        ]
        verdict = detector.detect_from_invocations(invocations)
        assert not verdict.is_flaky

    def test_detect_from_result_diverge(self):
        """从 HarnessResult 序列检测 diverge。"""
        from decimal import Decimal

        detector = FlakyDetector()
        prev = [
            HarnessResult(
                invocation_id=uuid4(), callback_token="cb1",
                outcome=HarnessOutcome.PASS, tier=HarnessTier.SPEC,
            ),
        ]
        current = HarnessResult(
            invocation_id=uuid4(), callback_token="cb2",
            outcome=HarnessOutcome.FAIL, tier=HarnessTier.SPEC,
        )
        verdict = detector.detect_from_result(current, prev)
        assert verdict.is_flaky

    def test_detect_from_result_consistent(self):
        """一致结果 → 不 flaky。"""
        detector = FlakyDetector()
        prev = [
            HarnessResult(
                invocation_id=uuid4(), callback_token="cb1",
                outcome=HarnessOutcome.PASS, tier=HarnessTier.SPEC,
            ),
        ]
        current = HarnessResult(
            invocation_id=uuid4(), callback_token="cb2",
            outcome=HarnessOutcome.PASS, tier=HarnessTier.SPEC,
        )
        verdict = detector.detect_from_result(current, prev)
        assert not verdict.is_flaky


# ===========================================================================
# 2. ReflectionQuarantineBuffer 测试
# ===========================================================================


class TestReflectionQuarantineBuffer:
    """测试反思隔离缓冲区。"""

    def _make_buffer(self):
        store = InMemoryQuarantineStore()
        return ReflectionQuarantineBuffer(store=store), store

    @pytest.mark.asyncio
    async def test_quarantine_entry(self):
        """放入隔离区。"""
        buffer, store = self._make_buffer()
        memory_id = new_id()

        entry = await buffer.quarantine(
            memory_id=memory_id, reason="flaky_result",
        )

        assert entry.memory_id == memory_id
        assert entry.reason == "flaky_result"
        assert entry.stable_confirmations == 0
        assert await buffer.is_quarantined(memory_id) is True

    @pytest.mark.asyncio
    async def test_quarantine_idempotent(self):
        """同一 memory_id 幂等隔离。"""
        buffer, store = self._make_buffer()
        memory_id = new_id()

        entry1 = await buffer.quarantine(memory_id=memory_id)
        entry2 = await buffer.quarantine(memory_id=memory_id)

        assert entry1.id == entry2.id
        assert len(store._entries) == 1

    @pytest.mark.asyncio
    async def test_confirm_stable(self):
        """稳定确认计数递增。"""
        buffer, _ = self._make_buffer()
        entry = await buffer.quarantine(memory_id=new_id())

        updated = await buffer.confirm_stable(entry.id)
        assert updated is not None
        assert updated.stable_confirmations == 1

    @pytest.mark.asyncio
    async def test_auto_release_after_stable_confirmations(self):
        """达到 QUARANTINE_STABLE_COUNT → 自动释放。"""
        buffer, _ = self._make_buffer()
        entry = await buffer.quarantine(memory_id=new_id())

        for _ in range(QUARANTINE_STABLE_COUNT):
            entry = await buffer.confirm_stable(entry.id)

        assert entry is not None
        assert entry.released_at is not None
        assert entry.released_by == "auto"
        assert await buffer.is_quarantined(entry.memory_id) is False

    @pytest.mark.asyncio
    async def test_manual_release(self):
        """人工释放。"""
        buffer, _ = self._make_buffer()
        entry = await buffer.quarantine(memory_id=new_id())

        released = await buffer.manual_release(
            entry.id, released_by="admin-member-123",
        )

        assert released is not None
        assert released.released_by == "admin-member-123"
        assert await buffer.is_quarantined(released.memory_id) is False

    @pytest.mark.asyncio
    async def test_discard_expired(self):
        """超时丢弃 (7 天未确认)。"""
        buffer, store = self._make_buffer()

        # 创建 2 个条目: 1 个超时, 1 个未超时
        old_entry = await buffer.quarantine(memory_id=new_id())
        old_entry.created_at = datetime.now(timezone.utc) - timedelta(days=QUARANTINE_TIMEOUT_DAYS + 1)
        await store.update(old_entry)

        new_entry = await buffer.quarantine(memory_id=new_id())

        discarded = await buffer.discard_expired()

        assert discarded == 1
        assert old_entry.discarded_at is not None
        assert new_entry.discarded_at is None

    @pytest.mark.asyncio
    async def test_is_quarantined_false_when_not_present(self):
        """不在隔离区 → False。"""
        buffer, _ = self._make_buffer()
        assert await buffer.is_quarantined(new_id()) is False

    @pytest.mark.asyncio
    async def test_is_quarantined_false_when_released(self):
        """已释放 → False。"""
        buffer, _ = self._make_buffer()
        entry = await buffer.quarantine(memory_id=new_id())
        await buffer.manual_release(entry.id, released_by="admin")

        assert await buffer.is_quarantined(entry.memory_id) is False

    @pytest.mark.asyncio
    async def test_is_quarantined_false_when_discarded(self):
        """已丢弃 → False。"""
        buffer, store = self._make_buffer()
        entry = await buffer.quarantine(memory_id=new_id())
        entry.discarded_at = datetime.now(timezone.utc)
        await store.update(entry)

        assert await buffer.is_quarantined(entry.memory_id) is False

    @pytest.mark.asyncio
    async def test_confirm_stable_nonexistent(self):
        """不存在的 entry → None。"""
        buffer, _ = self._make_buffer()
        result = await buffer.confirm_stable(uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_confirm_stable_already_released(self):
        """已释放的 entry → 直接返回。"""
        buffer, _ = self._make_buffer()
        entry = await buffer.quarantine(memory_id=new_id())
        await buffer.auto_release(entry.id)

        # 再次 confirm 不应改变状态
        result = await buffer.confirm_stable(entry.id)
        assert result is not None
        assert result.stable_confirmations == 0  # 未递增
