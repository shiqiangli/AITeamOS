-- =========================================================================
-- Migration 005: Execution Context (plan.md §2.1.2, arch.md §2.2.4)
--
-- Tables:
--   task                   — Task 聚合根
--   task_run               — TaskRun 实体
--   task_context_snapshot  — 不可变上下文快照
--   task_deliverable       — 交付物记录
--   task_dependency        — Task 依赖关系
--   task_project           — Task ↔ Project 多对多
--   llm_model              — Neutral LLM catalog
--   agent_profile          — Neutral Agent catalog
-- =========================================================================

CREATE TABLE llm_model (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                    TEXT NOT NULL UNIQUE,
    provider                TEXT NOT NULL DEFAULT '',
    model_id                TEXT NOT NULL DEFAULT '',
    endpoint_type           TEXT NOT NULL DEFAULT 'chat',
    context_window          INT NOT NULL DEFAULT 0,
    max_output_tokens       INT NOT NULL DEFAULT 0,
    supports_tools          BOOLEAN NOT NULL DEFAULT FALSE,
    supports_json           BOOLEAN NOT NULL DEFAULT FALSE,
    input_cost_per_1m       NUMERIC(12, 6) NOT NULL DEFAULT 0,
    output_cost_per_1m      NUMERIC(12, 6) NOT NULL DEFAULT 0,
    capability_tags         TEXT[] NOT NULL DEFAULT '{}',
    status                  TEXT NOT NULL DEFAULT 'active',
    notes                   TEXT NOT NULL DEFAULT '',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE agent_profile (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                    TEXT NOT NULL UNIQUE,
    description             TEXT NOT NULL DEFAULT '',
    runtime_kind            TEXT NOT NULL DEFAULT 'llm_agent',
    default_llm_model_id    UUID REFERENCES llm_model(id) ON DELETE SET NULL,
    system_prompt           TEXT NOT NULL DEFAULT '',
    tool_names              TEXT[] NOT NULL DEFAULT '{}',
    memory_policy           JSONB NOT NULL DEFAULT '{}'::jsonb,
    safety_policy           JSONB NOT NULL DEFAULT '{}'::jsonb,
    status                  TEXT NOT NULL DEFAULT 'active',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE task (
    id                  VARCHAR(32) PRIMARY KEY,  -- TASK-YYYYMMDDTHHMMSSmmm-XXXX
    department_id       UUID NOT NULL REFERENCES department(id),
    parent_task_id      VARCHAR(32),
    state               VARCHAR(20) NOT NULL DEFAULT 'draft',
    priority            VARCHAR(4) NOT NULL DEFAULT 'P2',
    title               TEXT NOT NULL,
    description         TEXT,
    deliverable_spec    JSONB NOT NULL DEFAULT '{}',
    declared_skills     UUID[] DEFAULT '{}',
    declared_memory_hints UUID[] DEFAULT '{}',
    budget              JSONB NOT NULL DEFAULT '{}',
    assigned_member_id  UUID,
    assigned_llm_model_id UUID REFERENCES llm_model(id) ON DELETE SET NULL,
    assigned_agent_profile_id UUID REFERENCES agent_profile(id) ON DELETE SET NULL,
    retry_count         INT NOT NULL DEFAULT 0,
    review_round        INT NOT NULL DEFAULT 0,
    workflow_id         VARCHAR(128),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_task_state ON task(state);
CREATE INDEX idx_task_member ON task(assigned_member_id) WHERE assigned_member_id IS NOT NULL;
CREATE INDEX idx_task_llm_model ON task(assigned_llm_model_id) WHERE assigned_llm_model_id IS NOT NULL;
CREATE INDEX idx_task_agent_profile ON task(assigned_agent_profile_id) WHERE assigned_agent_profile_id IS NOT NULL;

CREATE TABLE task_run (
    run_id          UUID PRIMARY KEY,
    task_id         VARCHAR(32) NOT NULL REFERENCES task(id),
    member_id       UUID NOT NULL,
    snapshot_id     UUID,
    state           VARCHAR(20) NOT NULL DEFAULT 'pending',
    cost            JSONB NOT NULL DEFAULT '{}',
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ
);
CREATE INDEX idx_run_task ON task_run(task_id);
CREATE INDEX idx_run_member_active ON task_run(member_id, state) WHERE state IN ('running', 'suspended');

CREATE TABLE task_context_snapshot (
    id              UUID PRIMARY KEY,
    task_id         VARCHAR(32) NOT NULL REFERENCES task(id),
    run_id          UUID NOT NULL,
    content         JSONB NOT NULL,     -- 密封的上下文快照
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE task_deliverable (
    id              UUID PRIMARY KEY,
    task_id         VARCHAR(32) NOT NULL REFERENCES task(id),
    run_id          UUID NOT NULL,
    deliverable_type VARCHAR(32) NOT NULL,
    uri             TEXT NOT NULL,
    metadata        JSONB NOT NULL DEFAULT '{}',
    submitted_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE task_dependency (
    task_id         VARCHAR(32) NOT NULL REFERENCES task(id),
    depends_on_id   VARCHAR(32) NOT NULL REFERENCES task(id),
    PRIMARY KEY (task_id, depends_on_id)
);

CREATE TABLE task_project (
    task_id     VARCHAR(32) NOT NULL REFERENCES task(id),
    project_id  UUID NOT NULL,
    PRIMARY KEY (task_id, project_id)
);
CREATE INDEX idx_task_project_project ON task_project(project_id);
