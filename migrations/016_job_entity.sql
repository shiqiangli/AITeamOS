-- Migration 016: Job entity — 替代 task_run，承载执行可观测性
-- Job = Task 的一次执行尝试 (Pre prompt + Middle status + Post result)

-- -----------------------------------------------------------------------
-- 1. 新建 job 表
-- -----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS job (
    job_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id             VARCHAR(64) NOT NULL REFERENCES task(id),
    member_id           UUID,
    llm_model_id        UUID,

    -- Pre: 组装后的完整 prompt + 上下文快照
    rendered_prompt     TEXT,
    context_snapshot    JSONB NOT NULL DEFAULT '{}',

    -- Middle: 执行阶段 + 错误信息
    phase               VARCHAR(32) NOT NULL DEFAULT 'queued',
    phase_entered_at    TIMESTAMPTZ,
    error               TEXT,

    -- Post: 结果报告 + 成本
    result_report       JSONB NOT NULL DEFAULT '{}',
    cost                JSONB NOT NULL DEFAULT '{}',

    -- Meta
    state               VARCHAR(20) NOT NULL DEFAULT 'pending',
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_job_task ON job(task_id);
CREATE INDEX IF NOT EXISTS idx_job_member ON job(member_id) WHERE member_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_job_state ON job(state) WHERE state IN ('pending', 'running');

-- -----------------------------------------------------------------------
-- 2. 迁移 task_run 数据到 job (如有)
-- -----------------------------------------------------------------------

INSERT INTO job (job_id, task_id, member_id, state, started_at, finished_at, cost)
SELECT run_id, task_id, member_id, state, started_at, finished_at, cost
FROM task_run
ON CONFLICT DO NOTHING;

-- -----------------------------------------------------------------------
-- 3. 删除 task_run 表
-- -----------------------------------------------------------------------

DROP TABLE IF EXISTS task_run CASCADE;

-- -----------------------------------------------------------------------
-- 4. 清理 task 表冗余列 (执行者信息已下沉到 Job)
-- -----------------------------------------------------------------------

ALTER TABLE task DROP COLUMN IF EXISTS assigned_member_id;
ALTER TABLE task DROP COLUMN IF EXISTS assigned_llm_model_id;
ALTER TABLE task DROP COLUMN IF EXISTS assigned_agent_profile_id;
