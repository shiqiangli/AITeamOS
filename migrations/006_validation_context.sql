-- =========================================================================
-- Migration 006: Validation Context (plan.md §3.1, arch.md §2.2.5 + §A.5)
--
-- Tables:
--   harness_adapter     — 验证适配器配置 (配置型聚合根)
--   harness_invocation  — 验证调用记录 (运行时聚合根)
-- =========================================================================

CREATE TABLE harness_adapter (
    id                      VARCHAR(64) PRIMARY KEY,
    tier                    VARCHAR(16) NOT NULL CHECK (tier IN ('spec','functional','system')),
    protocol                VARCHAR(8) NOT NULL CHECK (protocol IN ('sync','async')),
    endpoint                TEXT NOT NULL,
    auth_secret_ref         VARCHAR(128) NOT NULL,
    callback_secret_ref     VARCHAR(128),
    health                  JSONB NOT NULL DEFAULT '{}',
    project_bindings        UUID[] NOT NULL DEFAULT '{}',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE harness_invocation (
    id                  UUID PRIMARY KEY,
    adapter_id          VARCHAR(64) NOT NULL REFERENCES harness_adapter(id),
    run_id              UUID NOT NULL,
    deliverable_ref     TEXT NOT NULL,
    callback_token      VARCHAR(128) NOT NULL,
    state               VARCHAR(20) NOT NULL DEFAULT 'pending'
                        CHECK (state IN ('pending','done','expired','flaky','adapter_error')),
    triggered_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ,
    expire_at           TIMESTAMPTZ NOT NULL,
    result              JSONB,
    flaky_signal        JSONB,
    archived_at         TIMESTAMPTZ
);
CREATE INDEX idx_harness_invocation_callback ON harness_invocation(callback_token);
CREATE UNIQUE INDEX idx_harness_invocation_callback_unique ON harness_invocation(callback_token);
CREATE INDEX idx_harness_invocation_expire ON harness_invocation(expire_at)
    WHERE state = 'pending';
CREATE INDEX idx_harness_invocation_run ON harness_invocation(run_id);
CREATE INDEX idx_harness_invocation_adapter ON harness_invocation(adapter_id);
