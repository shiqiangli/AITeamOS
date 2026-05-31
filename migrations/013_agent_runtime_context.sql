-- =============================================================================
-- Migration 013: Neutral Agent and LLM runtime catalog
--
-- LLMs and Agents are neutral reusable resources. A task can select a member,
-- an Agent profile, and an LLM model independently.
-- =============================================================================

CREATE TABLE IF NOT EXISTS llm_model (
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

CREATE TABLE IF NOT EXISTS agent_profile (
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

ALTER TABLE task ADD COLUMN IF NOT EXISTS assigned_llm_model_id UUID REFERENCES llm_model(id) ON DELETE SET NULL;
ALTER TABLE task ADD COLUMN IF NOT EXISTS assigned_agent_profile_id UUID REFERENCES agent_profile(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_task_llm_model
    ON task(assigned_llm_model_id) WHERE assigned_llm_model_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_task_agent_profile
    ON task(assigned_agent_profile_id) WHERE assigned_agent_profile_id IS NOT NULL;
