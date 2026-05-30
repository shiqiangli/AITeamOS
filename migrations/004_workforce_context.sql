-- =============================================================================
-- Migration 004: Workforce Context DDL (arch.md §A.3, plan.md §1.4.3)
--
-- Tables:
--   department                 — 部门表（聚合根）
--   member                     — 成员表（聚合根）
--   project                    — 项目表（聚合根，经验生产场）
--   project_member             — 项目-成员关联
--   member_skill_assignment    — 成员-Skill 分配
--   member_memory_assignment   — 成员-Memory 分配
-- =============================================================================

CREATE TABLE department (
    id                      UUID PRIMARY KEY,
    name                    VARCHAR(128) NOT NULL,
    leader_member_id        UUID,
    backup_leader_member_id UUID,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE project (
    id                  UUID PRIMARY KEY,
    name                VARCHAR(128) NOT NULL,
    description         TEXT,
    department_id       UUID NOT NULL REFERENCES department(id),
    repository_refs     JSONB NOT NULL DEFAULT '[]',
    harness_config      JSONB NOT NULL DEFAULT '{}',
    status              VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    archived_at         TIMESTAMPTZ
);
CREATE INDEX idx_project_department ON project(department_id);

CREATE TABLE member (
    id                  UUID PRIMARY KEY,
    kind                VARCHAR(8) NOT NULL CHECK (kind IN ('ai', 'human')),
    department_id       UUID NOT NULL REFERENCES department(id),
    profile             JSONB NOT NULL DEFAULT '{}',
    concurrency_limit   INT NOT NULL DEFAULT 3,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    archived_at         TIMESTAMPTZ
);

CREATE TABLE project_member (
    project_id  UUID NOT NULL REFERENCES project(id),
    member_id   UUID NOT NULL REFERENCES member(id),
    role        VARCHAR(32) NOT NULL DEFAULT 'contributor',
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, member_id)
);

CREATE TABLE member_skill_assignment (
    member_id   UUID NOT NULL REFERENCES member(id),
    skill_id    UUID NOT NULL,
    is_base     BOOLEAN NOT NULL DEFAULT FALSE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (member_id, skill_id)
);

CREATE TABLE member_memory_assignment (
    member_id   UUID NOT NULL REFERENCES member(id),
    memory_id   UUID NOT NULL,
    weight      NUMERIC(4,3) NOT NULL DEFAULT 1.000,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (member_id, memory_id)
);
