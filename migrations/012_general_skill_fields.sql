-- =============================================================================
-- Migration 012: General Skill attributes
--
-- Skill is a neutral capability definition. Assignment to members is expressed
-- through member_skill_assignment, not through Skill ownership.
-- =============================================================================

ALTER TABLE skill DROP COLUMN IF EXISTS entry_point;

ALTER TABLE skill ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT '';
ALTER TABLE skill ADD COLUMN IF NOT EXISTS domain TEXT NOT NULL DEFAULT '';
ALTER TABLE skill ADD COLUMN IF NOT EXISTS inputs JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE skill ADD COLUMN IF NOT EXISTS outputs JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE skill ADD COLUMN IF NOT EXISTS preconditions JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE skill ADD COLUMN IF NOT EXISTS side_effects JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE skill ADD COLUMN IF NOT EXISTS required_permissions JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE skill ADD COLUMN IF NOT EXISTS capability_tags JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE skill ADD COLUMN IF NOT EXISTS examples JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE skill ADD COLUMN IF NOT EXISTS reference_links JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE skill ADD COLUMN IF NOT EXISTS quality_signals JSONB NOT NULL DEFAULT '{}'::jsonb;

UPDATE skill SET
    description = COALESCE(manifest->>'description', description),
    domain = COALESCE(manifest->>'domain', domain),
    inputs = COALESCE(manifest->'inputs', inputs),
    outputs = COALESCE(manifest->'outputs', outputs),
    preconditions = COALESCE(manifest->'preconditions', preconditions),
    side_effects = COALESCE(manifest->'side_effects', side_effects),
    required_permissions = COALESCE(manifest->'required_permissions', required_permissions),
    capability_tags = COALESCE(manifest->'capability_tags', capability_tags),
    examples = COALESCE(manifest->'examples', examples),
    reference_links = COALESCE(manifest->'references', reference_links),
    quality_signals = COALESCE(manifest->'quality_signals', quality_signals);
