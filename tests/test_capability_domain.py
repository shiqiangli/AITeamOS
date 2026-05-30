"""
Capability Context — 领域模型 + 不变量 + 服务测试。

验证标准 (plan.md §1.3):
- Skill 注册 → 发布 → 废弃全流程
- 版本兼容性校验（向后兼容变更不升 major）
- 熔断触发条件正确
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

from aiteamos_shared.types import SemVer, new_id
from aiteamos_capability.domain.models import (
    CircuitState,
    CostEstimate,
    MutationKind,
    SideEffect,
    Skill,
    SkillHealth,
    SkillManifest,
    SkillStatus,
)
from aiteamos_capability.domain.events import (
    SkillCircuitOpened,
    SkillDeprecated,
    SkillPublished,
    SkillRegistered,
)
from aiteamos_capability.domain.invariants import (
    InvariantViolationError,
    assert_backward_compatible,
    assert_circuit_status_consistent,
    assert_version_locked_for_run,
    is_skill_assignable,
    validate_schema_compatibility,
)
from aiteamos_capability.domain.services import (
    FailureStats,
    SkillCircuitBreaker,
    SkillConflictDetector,
    SkillRegistry,
)
from aiteamos_capability.domain.spi import ConflictReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_skill(
    *,
    status: SkillStatus = SkillStatus.DRAFT,
    circuit: CircuitState = CircuitState.CLOSED,
    version: SemVer | None = None,
) -> Skill:
    manifest = SkillManifest(
        name="test-skill",
        version=version or SemVer(major=1, minor=0, patch=0),
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"result": {"type": "string"}}},
        side_effects=[
            SideEffect(resource_kind="filesystem", resource_pattern="src/**/*.py", mutation_kind=MutationKind.WRITE),
        ],
        capability_tags=["test"],
    )
    return Skill(
        name="test-skill",
        version=version or SemVer(major=1, minor=0, patch=0),
        manifest=manifest,
        status=status,
        health=SkillHealth(circuit_state=circuit),
    )


# ===========================================================================
# Test Value Objects
# ===========================================================================


class TestSkillManifest:
    def test_to_dict_roundtrip(self):
        m = SkillManifest(
            name="test",
            version=SemVer(major=1, minor=0, patch=0),
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            side_effects=[SideEffect("filesystem", "*.py", MutationKind.WRITE)],
            capability_tags=["code"],
        )
        d = m.to_dict()
        restored = SkillManifest.from_dict(d)
        assert restored.name == "test"
        assert restored.side_effects[0].mutation_kind == MutationKind.WRITE

    def test_from_dict_defaults(self):
        m = SkillManifest.from_dict({})
        assert m.name == ""
        assert m.side_effects == []


class TestSkillHealth:
    def test_defaults(self):
        h = SkillHealth()
        assert h.success_rate == Decimal("1.000")
        assert h.circuit_state == CircuitState.CLOSED

    def test_to_dict_roundtrip(self):
        h = SkillHealth(success_rate=Decimal("0.85"), recent_failures=3, circuit_state=CircuitState.HALF_OPEN)
        d = h.to_dict()
        restored = SkillHealth.from_dict(d)
        assert restored.success_rate == Decimal("0.85")
        assert restored.circuit_state == CircuitState.HALF_OPEN


class TestSideEffect:
    def test_creation(self):
        se = SideEffect("filesystem", "src/**/*.py", MutationKind.WRITE)
        assert se.resource_kind == "filesystem"
        assert se.mutation_kind == MutationKind.WRITE


# ===========================================================================
# Test Skill Aggregate
# ===========================================================================


class TestSkill:
    def test_creation(self):
        skill = _make_skill()
        assert skill.status == SkillStatus.DRAFT
        assert skill.name == "test-skill"

    def test_publish(self):
        skill = _make_skill()
        skill.publish()
        assert skill.status == SkillStatus.PUBLISHED
        assert any(isinstance(e, SkillPublished) for e in skill.pending_events)

    def test_publish_non_draft_raises(self):
        skill = _make_skill(status=SkillStatus.PUBLISHED)
        with pytest.raises(ValueError, match="Only draft"):
            skill.publish()

    def test_deprecate(self):
        skill = _make_skill(status=SkillStatus.PUBLISHED)
        skill.deprecate(reason="outdated")
        assert skill.status == SkillStatus.DEPRECATED
        events = skill.pending_events
        assert any(isinstance(e, SkillDeprecated) for e in events)

    def test_cancel_draft(self):
        skill = _make_skill()
        skill.cancel()
        assert skill.status == SkillStatus.CANCELLED

    def test_cancel_published_raises(self):
        skill = _make_skill(status=SkillStatus.PUBLISHED)
        with pytest.raises(ValueError, match="Only draft/recalibrating"):
            skill.cancel()

    def test_open_circuit(self):
        skill = _make_skill(status=SkillStatus.PUBLISHED)
        skill.open_circuit()
        assert skill.status == SkillStatus.RECALIBRATING
        assert skill.health.circuit_state == CircuitState.OPEN
        events = skill.pending_events
        assert any(isinstance(e, SkillCircuitOpened) for e in events)

    def test_close_circuit(self):
        skill = _make_skill(status=SkillStatus.RECALIBRATING, circuit=CircuitState.OPEN)
        skill.close_circuit()
        assert skill.status == SkillStatus.PUBLISHED
        assert skill.health.circuit_state == CircuitState.CLOSED

    def test_half_open_circuit(self):
        skill = _make_skill(status=SkillStatus.RECALIBRATING, circuit=CircuitState.OPEN)
        skill.half_open_circuit()
        assert skill.health.circuit_state == CircuitState.HALF_OPEN

    def test_is_assignable(self):
        skill = _make_skill(status=SkillStatus.PUBLISHED)
        assert skill.is_assignable is True

    def test_not_assignable_when_circuit_open(self):
        skill = _make_skill(status=SkillStatus.RECALIBRATING, circuit=CircuitState.OPEN)
        assert skill.is_assignable is False

    def test_not_assignable_when_draft(self):
        skill = _make_skill()
        assert skill.is_assignable is False

    def test_clear_pending_events(self):
        skill = _make_skill()
        skill.publish()
        assert len(skill.pending_events) > 0
        skill.clear_pending_events()
        assert len(skill.pending_events) == 0


# ===========================================================================
# Test Invariants
# ===========================================================================


class TestInvariantIC1:
    """I-C-1: published 后 schema 只能向后兼容变更。"""

    def test_compatible_add_optional_field(self):
        old = {"type": "object", "properties": {"a": {"type": "string"}}}
        new = {"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "int"}}}
        assert validate_schema_compatibility(old, new) is True

    def test_incompatible_remove_field(self):
        old = {"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "int"}}}
        new = {"type": "object", "properties": {"a": {"type": "string"}}}
        assert validate_schema_compatibility(old, new) is False

    def test_incompatible_add_required_field(self):
        old = {"type": "object", "properties": {"a": {"type": "string"}}}
        new = {"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "int"}}, "required": ["b"]}
        assert validate_schema_compatibility(old, new) is False

    def test_assert_backward_compatible_passes(self):
        old_m = SkillManifest(input_schema={"properties": {"a": {}}}, output_schema={})
        new_m = SkillManifest(input_schema={"properties": {"a": {}, "b": {}}}, output_schema={})
        assert_backward_compatible(old_m, new_m)  # no exception

    def test_assert_backward_compatible_fails(self):
        old_m = SkillManifest(input_schema={"properties": {"a": {}, "b": {}}}, output_schema={})
        new_m = SkillManifest(input_schema={"properties": {"a": {}}}, output_schema={})
        with pytest.raises(InvariantViolationError, match="I-C-1"):
            assert_backward_compatible(old_m, new_m)


class TestInvariantIC2:
    """I-C-2: Run 绑定版本。"""

    def test_matching_version_passes(self):
        skill = _make_skill(version=SemVer(major=1, minor=0, patch=0))
        assert_version_locked_for_run(skill, SemVer(major=1, minor=0, patch=0))

    def test_mismatched_version_raises(self):
        skill = _make_skill(version=SemVer(major=1, minor=0, patch=0))
        with pytest.raises(InvariantViolationError, match="I-C-2"):
            assert_version_locked_for_run(skill, SemVer(major=2, minor=0, patch=0))


class TestInvariantIC3:
    """I-C-3: circuit_state=open 时 status 必须为 recalibrating。"""

    def test_consistent_state_passes(self):
        skill = _make_skill(status=SkillStatus.RECALIBRATING, circuit=CircuitState.OPEN)
        assert_circuit_status_consistent(skill)

    def test_inconsistent_state_raises(self):
        skill = _make_skill(status=SkillStatus.PUBLISHED, circuit=CircuitState.OPEN)
        with pytest.raises(InvariantViolationError, match="I-C-3"):
            assert_circuit_status_consistent(skill)

    def test_closed_circuit_any_status_passes(self):
        skill = _make_skill(status=SkillStatus.PUBLISHED, circuit=CircuitState.CLOSED)
        assert_circuit_status_consistent(skill)


class TestIsSkillAssignable:
    def test_published_closed(self):
        skill = _make_skill(status=SkillStatus.PUBLISHED, circuit=CircuitState.CLOSED)
        assert is_skill_assignable(skill) is True

    def test_draft(self):
        skill = _make_skill()
        assert is_skill_assignable(skill) is False

    def test_published_open(self):
        skill = _make_skill(status=SkillStatus.PUBLISHED, circuit=CircuitState.OPEN)
        assert is_skill_assignable(skill) is False


# ===========================================================================
# Test SkillConflictDetector
# ===========================================================================


class TestSkillConflictDetector:
    def test_no_conflict_different_resources(self):
        detector = SkillConflictDetector()
        m1 = SkillManifest(
            name="skill-a",
            side_effects=[SideEffect("filesystem", "src/**/*.py", MutationKind.WRITE)],
        )
        m2 = SkillManifest(
            name="skill-b",
            side_effects=[SideEffect("network", "api.example.com", MutationKind.WRITE)],
        )
        conflicts = detector.detect([m1, m2])
        assert len(conflicts) == 0

    def test_conflict_same_resource_write(self):
        detector = SkillConflictDetector()
        m1 = SkillManifest(
            name="skill-a",
            side_effects=[SideEffect("filesystem", "src/**/*.py", MutationKind.WRITE)],
        )
        m2 = SkillManifest(
            name="skill-b",
            side_effects=[SideEffect("filesystem", "src/**/*.py", MutationKind.DELETE)],
        )
        conflicts = detector.detect([m1, m2])
        assert len(conflicts) == 1
        assert conflicts[0].conflict_kind == "resource_collision"

    def test_no_conflict_read_only(self):
        detector = SkillConflictDetector()
        m1 = SkillManifest(
            name="skill-a",
            side_effects=[SideEffect("filesystem", "src/**/*.py", MutationKind.READ)],
        )
        m2 = SkillManifest(
            name="skill-b",
            side_effects=[SideEffect("filesystem", "src/**/*.py", MutationKind.READ)],
        )
        conflicts = detector.detect([m1, m2])
        assert len(conflicts) == 0

    def test_empty_manifests(self):
        detector = SkillConflictDetector()
        conflicts = detector.detect([])
        assert len(conflicts) == 0


# ===========================================================================
# Test SkillCircuitBreaker
# ===========================================================================


class TestSkillCircuitBreaker:
    @pytest.fixture
    def mock_repo(self):
        return AsyncMock()

    @pytest.fixture
    def breaker(self, mock_repo):
        return SkillCircuitBreaker(repository=mock_repo)

    def test_should_open_below_threshold(self, breaker):
        stats = FailureStats(distinct_failed_tasks=2, failure_rate=Decimal("0.10"))
        assert breaker.should_open_circuit(stats) is False

    def test_should_open_by_task_count(self, breaker):
        stats = FailureStats(distinct_failed_tasks=5, failure_rate=Decimal("0.10"))
        assert breaker.should_open_circuit(stats) is True

    def test_should_open_by_failure_rate(self, breaker):
        stats = FailureStats(distinct_failed_tasks=2, failure_rate=Decimal("0.35"))
        assert breaker.should_open_circuit(stats) is True

    @pytest.mark.asyncio
    async def test_on_failure_triggers_circuit(self, breaker, mock_repo):
        skill = _make_skill(status=SkillStatus.PUBLISHED)
        mock_repo.lock_for_update.return_value = skill
        stats = FailureStats(distinct_failed_tasks=5, failure_rate=Decimal("0.50"))

        result = await breaker.on_failure(skill.id, stats)
        assert result is not None
        assert result.health.circuit_state == CircuitState.OPEN
        assert result.status == SkillStatus.RECALIBRATING
        mock_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_failure_no_trigger(self, breaker, mock_repo):
        skill = _make_skill(status=SkillStatus.PUBLISHED)
        stats = FailureStats(distinct_failed_tasks=1, failure_rate=Decimal("0.05"))

        result = await breaker.on_failure(skill.id, stats)
        assert result is None

    @pytest.mark.asyncio
    async def test_attempt_recovery(self, breaker, mock_repo):
        skill = _make_skill(status=SkillStatus.RECALIBRATING, circuit=CircuitState.OPEN)
        mock_repo.lock_for_update.return_value = skill

        result = await breaker.attempt_recovery(skill.id)
        assert result is not None
        assert result.health.circuit_state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_confirm_recovery(self, breaker, mock_repo):
        skill = _make_skill(status=SkillStatus.RECALIBRATING, circuit=CircuitState.HALF_OPEN)
        mock_repo.lock_for_update.return_value = skill

        result = await breaker.confirm_recovery(skill.id)
        assert result is not None
        assert result.health.circuit_state == CircuitState.CLOSED
        assert result.status == SkillStatus.PUBLISHED


# ===========================================================================
# Test SkillRegistry
# ===========================================================================


class TestSkillRegistry:
    def test_register_and_get(self):
        registry = SkillRegistry()
        mock_skill = AsyncMock()
        registry.register("test-skill", mock_skill)
        assert registry.get("test-skill") is mock_skill

    def test_list_skills(self):
        registry = SkillRegistry()
        registry.register("a", AsyncMock())
        registry.register("b", AsyncMock())
        assert sorted(registry.list_skills()) == ["a", "b"]

    def test_get_nonexistent(self):
        registry = SkillRegistry()
        assert registry.get("nonexistent") is None


# ===========================================================================
# Test Domain Events
# ===========================================================================


class TestCapabilityEvents:
    def test_skill_registered(self):
        evt = SkillRegistered(
            skill_id=new_id(), name="test", version="1.0.0"
        )
        assert evt.event_type == "capability.skill.registered"

    def test_skill_published(self):
        evt = SkillPublished(skill_id=new_id(), name="test", version="1.0.0")
        assert evt.event_type == "capability.skill.published"

    def test_skill_circuit_opened(self):
        evt = SkillCircuitOpened(
            skill_id=new_id(), recent_failures=5, success_rate=0.2
        )
        assert evt.event_type == "capability.skill.circuit_opened"
