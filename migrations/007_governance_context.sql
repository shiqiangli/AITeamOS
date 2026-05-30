-- =========================================================================
-- Migration 007: Governance Context (plan.md §3.3, arch.md §2.2.6 + §A.6)
--
-- Tables:
--   review_case             — 审核案例聚合根
--   conflict_case           — 冲突案例聚合根
--   reflection_quarantine   — 反思隔离缓冲区
--   member_activity_event   — Member 活动流 (Stage 4.3 提前建表)
-- =========================================================================

CREATE TABLE review_case (
    id                  UUID PRIMARY KEY,
    target_kind         VARCHAR(32) NOT NULL,
    target_id           UUID NOT NULL,
    reviewer_member_id  UUID NOT NULL,
    verdict             VARCHAR(16),
    reason              TEXT,
    correction          TEXT,
    decision_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_review_pending ON review_case(created_at) WHERE verdict IS NULL;
CREATE INDEX idx_review_target ON review_case(target_kind, target_id);

-- conflict_case 已在 002 中创建, 此处补充索引
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE indexname = 'idx_conflict_unresolved'
    ) THEN
        CREATE INDEX idx_conflict_unresolved ON conflict_case(detected_at)
            WHERE resolved_at IS NULL;
    END IF;
END $$;

-- Reflection Quarantine Buffer（防 Flaky 污染）
CREATE TABLE reflection_quarantine (
    id                  UUID PRIMARY KEY,
    invocation_id       UUID NOT NULL,
    run_id              UUID NOT NULL,
    flaky_kind          VARCHAR(32) NOT NULL,
    raw_evidence        JSONB NOT NULL,
    state               VARCHAR(20) NOT NULL DEFAULT 'pending',
    confirm_count       INT NOT NULL DEFAULT 0,
    consensus_outcome   VARCHAR(20),
    quarantined_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    released_at         TIMESTAMPTZ,
    released_by         UUID,
    expire_at           TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_quarantine_pending ON reflection_quarantine(expire_at)
    WHERE state = 'pending';

-- Member 活动流表（Stage 4.3 使用，提前建表）
CREATE TABLE member_activity_event (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    member_id       UUID NOT NULL,
    event_kind      VARCHAR(32) NOT NULL,
    event_payload   JSONB NOT NULL DEFAULT '{}',
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_activity_member_time ON member_activity_event(member_id, occurred_at DESC);
