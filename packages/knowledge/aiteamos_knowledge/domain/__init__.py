"""
Knowledge Context — Domain Layer.

Re-exports core domain types for convenient access.
"""

from .events import (
    MemoryBatchNeedsVerifyEvent,
    MemoryEdgeAdded,
    MemoryEdgeRemoved,
    MemoryFeedbackRecorded,
    MemoryNodeCreated,
    MemoryNodeLifecycleChanged,
    MemoryNodeUpdated,
    MemoryQuarantinedEvent,
    MemoryVersionAppended,
)
from .invariants import (
    InvariantViolationError,
    assert_edge_not_in_node_aggregate,
    assert_edge_operation_no_node_lock,
    assert_recallable,
    compute_decay_factor,
    is_decay_eligible,
    is_recallable,
    validate_confidence_value,
)
from .models import (
    Confidence,
    ConfidenceState,
    LifecycleState,
    MemoryContent,
    MemoryEdge,
    MemoryNode,
    MemoryVersion,
    Provenance,
    RelationType,
    Scope,
    ScopeKind,
    SourceKind,
    Tier,
)
from .services import ConfidenceAdjustmentService, MemoryConflictDetector
