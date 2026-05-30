-- =============================================================================
-- Migration 002: Knowledge Context DDL (arch.md §2.4)
--
-- Tables:
--   memory_node        — Memory 节点主表（聚合根）
--   memory_version     — Memory 版本表
--   memory_edge        — Memory 关系边表（独立聚合根）
--   memory_embedding   — 向量索引（pgvector + HNSW）
--   memory_feedback    — Memory 反馈（驱动置信度演进）
--   memory_recall_log  — Memory 召回审计
--
-- NOTE: conflict_case 属于 Governance Context，见 migration 007
-- NOTE: projection_watermark / webhook_inbox 已在 migration 001 创建
-- =============================================================================

-- Memory 节点主表（聚合根）
CREATE TABLE memory_node (
    id                  UUID PRIMARY KEY,
    tier                VARCHAR(16) NOT NULL CHECK (tier IN ('facts','patterns','principles')),
    scope_kind          VARCHAR(16) NOT NULL CHECK (scope_kind IN ('project','tech_stack','department','global')),
    scope_ref           UUID,                       -- 指向具体 project/dept/null
    title               TEXT NOT NULL,
    content             JSONB NOT NULL,             -- {statement, applicable_when, counter_example, tags}
    confidence_value    NUMERIC(4,3) NOT NULL DEFAULT 0.500,
    confidence_state    VARCHAR(20) NOT NULL DEFAULT 'needs_verify',
    last_decay_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    lifecycle_state     VARCHAR(20) NOT NULL DEFAULT 'candidate',
    provenance          JSONB NOT NULL,             -- {source_kind, task_id, run_id, member_id, system_meta}
    current_version     INT NOT NULL DEFAULT 1,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at        TIMESTAMPTZ,
    expire_at           TIMESTAMPTZ,
    CHECK (confidence_value >= 0 AND confidence_value <= 1)
);
CREATE INDEX idx_memory_node_tier_scope ON memory_node(tier, scope_kind, scope_ref);
CREATE INDEX idx_memory_node_lifecycle ON memory_node(lifecycle_state) WHERE lifecycle_state IN ('active','needs_verify');
CREATE INDEX idx_memory_node_provenance_meta ON memory_node((provenance->>'system_meta'));

-- Memory 版本表
CREATE TABLE memory_version (
    id                  UUID PRIMARY KEY,
    memory_id           UUID NOT NULL REFERENCES memory_node(id),
    version_no          INT NOT NULL,
    diff                JSONB NOT NULL,
    reason              TEXT NOT NULL,
    author_member_id    UUID NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (memory_id, version_no)
);

-- Memory 关系边表（独立聚合根，v1.3 拆分）
CREATE TABLE memory_edge (
    id                  UUID PRIMARY KEY,
    source_id           UUID NOT NULL REFERENCES memory_node(id),
    target_id           UUID NOT NULL REFERENCES memory_node(id),
    relation_type       VARCHAR(16) NOT NULL CHECK (relation_type IN ('causal','depends','derived','conflicts')),
    weight              NUMERIC(4,3),
    created_by          UUID NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_id, target_id, relation_type)
);
CREATE INDEX idx_memory_edge_source ON memory_edge(source_id);
CREATE INDEX idx_memory_edge_target ON memory_edge(target_id);

-- 向量索引（pgvector + HNSW，支持增量插入，无需全量重建）
CREATE TABLE memory_embedding (
    memory_id           UUID PRIMARY KEY REFERENCES memory_node(id),
    embedding           vector(1536) NOT NULL,
    model_version       VARCHAR(64) NOT NULL,
    source_event_seq    BIGINT NOT NULL DEFAULT 0,   -- 幂等投影水位，防乱序回滚
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_memory_embedding_hnsw ON memory_embedding
    USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);

-- Memory 反馈（驱动置信度演进）
CREATE TABLE memory_feedback (
    id                  UUID PRIMARY KEY,
    memory_id           UUID NOT NULL REFERENCES memory_node(id),
    task_run_id         UUID NOT NULL,
    outcome             VARCHAR(16) NOT NULL CHECK (outcome IN ('positive','negative','neutral')),
    delta               NUMERIC(4,3) NOT NULL,
    reviewer_member_id  UUID,                        -- 仅 human_approval 才计入正向
    occurred_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_system_meta      BOOLEAN NOT NULL DEFAULT FALSE  -- 元递归隔离
);

-- Memory 召回审计（防循环 + 归因）
CREATE TABLE memory_recall_log (
    id                  UUID PRIMARY KEY,
    snapshot_id         UUID NOT NULL,               -- 关联到不可变快照
    memory_id           UUID NOT NULL,
    task_run_id         UUID NOT NULL,
    rank                INT NOT NULL,
    score               NUMERIC(6,4) NOT NULL,
    used_in_decision    BOOLEAN,                     -- 反思阶段回填
    occurred_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
