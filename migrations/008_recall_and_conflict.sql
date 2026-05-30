-- =========================================================================
-- Migration 008: Recall Audit + Conflict Case (补全)
--
-- Tables:
--   conflict_case   — Memory 冲突案例 (Governance Context, 002 中遗漏)
--   recall_audit    — 召回审计日志 (Knowledge Context)
-- =========================================================================

-- conflict_case: Memory 冲突聚合根
CREATE TABLE IF NOT EXISTS conflict_case (
    id                  UUID PRIMARY KEY,
    memory_a_id         UUID NOT NULL,
    memory_b_id         UUID NOT NULL,
    conflict_kind       VARCHAR(16) NOT NULL,
    detected_by         VARCHAR(32) NOT NULL,
    resolution          VARCHAR(16),
    winner_id           UUID,
    resolved_by         UUID,
    detected_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at         TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_conflict_unresolved
    ON conflict_case(detected_at) WHERE resolved_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_conflict_memory_a
    ON conflict_case(memory_a_id);
CREATE INDEX IF NOT EXISTS idx_conflict_memory_b
    ON conflict_case(memory_b_id);

-- recall_audit: 召回审计日志
CREATE TABLE recall_audit (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id         UUID,
    run_id              UUID,
    memory_ids          UUID[] NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_recall_audit_created ON recall_audit(created_at);
