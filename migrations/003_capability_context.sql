-- =============================================================================
-- Migration 003: Capability Context DDL (arch.md §A.2)
--
-- Tables:
--   skill              — Skill 主表（聚合根）
--   skill_health_metric — Skill 健康度指标（熔断决策消费）
-- =============================================================================

CREATE TABLE skill (
    id              UUID PRIMARY KEY,
    name            TEXT NOT NULL,
    version_major   INT NOT NULL,
    version_minor   INT NOT NULL,
    version_patch   INT NOT NULL,
    manifest        JSONB NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft','published','recalibrating','deprecated','cancelled')),
    circuit_state   VARCHAR(10) NOT NULL DEFAULT 'closed'
                        CHECK (circuit_state IN ('closed','half_open','open')),
    description     TEXT NOT NULL DEFAULT '',
    domain          TEXT NOT NULL DEFAULT '',
    inputs          JSONB NOT NULL DEFAULT '[]'::jsonb,
    outputs         JSONB NOT NULL DEFAULT '[]'::jsonb,
    preconditions   JSONB NOT NULL DEFAULT '[]'::jsonb,
    side_effects    JSONB NOT NULL DEFAULT '[]'::jsonb,
    required_permissions JSONB NOT NULL DEFAULT '[]'::jsonb,
    capability_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    examples        JSONB NOT NULL DEFAULT '[]'::jsonb,
    reference_links JSONB NOT NULL DEFAULT '[]'::jsonb,
    quality_signals JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (name, version_major, version_minor, version_patch)
);
CREATE INDEX idx_skill_name_published ON skill(name) WHERE status = 'published';
CREATE INDEX idx_skill_status ON skill(status);

CREATE TABLE skill_health_metric (
    id              UUID PRIMARY KEY,
    skill_id        UUID NOT NULL REFERENCES skill(id),
    window_start    TIMESTAMPTZ NOT NULL,
    success_count   INT NOT NULL DEFAULT 0,
    failure_count   INT NOT NULL DEFAULT 0,
    distinct_failed_tasks INT NOT NULL DEFAULT 0,
    success_rate    NUMERIC(4,3),
    UNIQUE (skill_id, window_start)
);
