"""Capability Context — Domain Layer."""

from .events import (
    SkillCircuitOpened,
    SkillDeprecated,
    SkillPublished,
    SkillRegistered,
)
from .invariants import (
    InvariantViolationError,
    assert_backward_compatible,
    assert_circuit_status_consistent,
    assert_version_locked_for_run,
    is_skill_assignable,
    validate_schema_compatibility,
)
from .models import (
    CircuitState,
    CostEstimate,
    MutationKind,
    SideEffect,
    Skill,
    SkillHealth,
    SkillManifest,
    SkillStatus,
)
from .services import SkillCircuitBreaker, SkillConflictDetector, SkillRegistry
from .spi import (
    ConflictReport,
    Fixture,
    SkillContext,
    SkillReadiness,
    SkillResult,
    SkillSPI,
)
