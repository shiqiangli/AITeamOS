"""Knowledge Context — Application Layer."""

from .cascade_invalidation import (
    CascadeInvalidationService,
    CascadeResult,
    DeferredCascadeRequired,
    StructuralChangeEvent,
)
from .commands import (
    AppendMemoryVersionCommand,
    ChangeLifecycleCommand,
    CreateMemoryEdgeCommand,
    CreateMemoryNodeCommand,
    DeprecateMemoryNodeCommand,
    MergeMemoryNodesCommand,
    RemoveMemoryEdgeCommand,
    UpdateMemoryContentCommand,
)
from .extraction import ExtractionInput, MemoryCandidate, MemoryReviewQueue, ReflectionEngine
from .feedback import (
    ConfidenceAdjustmentService,
    MemoryFeedback,
    MemoryFeedbackCollector,
    FeedbackStats,
)
from .graph_projection import (
    GraphProjectionService,
    GraphTraversalChannel,
    ProjectionResult,
)
from .handlers import (
    AppendMemoryVersionHandler,
    ChangeLifecycleHandler,
    CreateMemoryEdgeHandler,
    CreateMemoryNodeHandler,
    DeprecateMemoryNodeHandler,
    MergeMemoryNodesHandler,
    RemoveMemoryEdgeHandler,
    UpdateMemoryContentHandler,
)
from .health import (
    BulkGovernanceService,
    BulkOperationResult,
    ExportImportService,
    ExportPayload,
    ImportResult,
    MemoryHealthMetrics,
    MemoryHealthService,
)
from .promotion import (
    MemorySpreadService,
    MemoryTierPromotionService,
    PromotionCandidate,
    PromotionEvaluation,
    SpreadRecommendation,
)
from .queries import (
    GetMemoryNodeDetailExecutor,
    GetMemoryNodeDetailQuery,
    ListMemoryNodesExecutor,
    ListMemoryNodesQuery,
    SearchMemoryByKeywordExecutor,
    SearchMemoryByKeywordQuery,
)