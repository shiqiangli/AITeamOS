-- ============================================================================
-- AITeamOS Greenfield — 001 Shared Infrastructure DDL
--
-- 基础设施表：Outbox、投影水位、Webhook 幂等、补偿 DLQ、
-- Outbox 发布水位（多实例 Relay 分片用）。
--
-- 执行方式：
--   psql -h localhost -U aiteamos -d aiteamos -f migrations/001_shared_infrastructure.sql
-- ============================================================================

-- --------------------------------------------------------------------------
-- Outbox 表 (Transactional Outbox Pattern)
-- 领域事件与业务数据在同一事务中写入，由 OutboxRelay 异步投递到 Kafka。
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS outbox (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type      VARCHAR(128) NOT NULL,
    partition_key   VARCHAR(128) NOT NULL,
    payload         JSONB NOT NULL,
    global_seq      BIGSERIAL NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at    TIMESTAMPTZ
);

-- 快速扫描未发布事件
CREATE INDEX IF NOT EXISTS idx_outbox_unpublished
    ON outbox(created_at) WHERE published_at IS NULL;

-- 多实例 Relay 分片用（arch.md §6.1）
-- partition_no: 按 partition_key hash 分 16 个逻辑分区
ALTER TABLE outbox ADD COLUMN IF NOT EXISTS partition_no SMALLINT NOT NULL
    GENERATED ALWAYS AS (abs(hashtext(partition_key)) % 16) STORED;

CREATE INDEX IF NOT EXISTS idx_outbox_pub_pending
    ON outbox(partition_no, global_seq) WHERE published_at IS NULL;


-- --------------------------------------------------------------------------
-- Outbox 发布水位表 (多实例 Relay 分片租约)
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS outbox_publish_watermark (
    partition_no            SMALLINT PRIMARY KEY,
    last_published_seq      BIGINT NOT NULL DEFAULT 0,
    leased_by               VARCHAR(64),
    leased_until            TIMESTAMPTZ,
    last_heartbeat_at       TIMESTAMPTZ
);

-- 初始化 16 个分区水位记录
INSERT INTO outbox_publish_watermark (partition_no)
SELECT g FROM generate_series(0, 15) AS g
ON CONFLICT (partition_no) DO NOTHING;


-- --------------------------------------------------------------------------
-- 投影水位表 (Idempotent Projection Consumer)
-- 所有 CQRS 读侧投影消费者基于此表实现 CAS 水位推进。
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS projection_watermark (
    consumer_id     VARCHAR(64) PRIMARY KEY,
    last_event_id   UUID NOT NULL,
    last_seq        BIGINT NOT NULL,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- --------------------------------------------------------------------------
-- Webhook 入站幂等表
-- (adapter_id, invocation_id) 唯一约束保证回调幂等。
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS webhook_inbox (
    adapter_id      VARCHAR(64) NOT NULL,
    invocation_id   VARCHAR(128) NOT NULL,
    payload         JSONB NOT NULL,
    received_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    expire_at       TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '30 days'),
    PRIMARY KEY (adapter_id, invocation_id)
);

CREATE INDEX IF NOT EXISTS idx_webhook_inbox_expire ON webhook_inbox(expire_at);


-- --------------------------------------------------------------------------
-- 补偿失败 DLQ (Dead Letter Queue)
-- Saga 补偿链中补偿失败的项目进入此表，等待人工介入。
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS compensation_failure_dlq (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id     VARCHAR(128) NOT NULL,
    item            JSONB NOT NULL,
    reason          TEXT NOT NULL,
    error           TEXT NOT NULL,
    raised_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at     TIMESTAMPTZ,
    resolved_by     UUID,
    resolution_kind VARCHAR(32)
);

CREATE INDEX IF NOT EXISTS idx_dlq_unresolved
    ON compensation_failure_dlq(raised_at) WHERE resolved_at IS NULL;
