-- =============================================================================
-- Migration 014: Simplify Skill table — keep only capability-label fields
--
-- Removes: manifest, circuit_state, inputs, outputs, preconditions,
--          side_effects, required_permissions, examples, reference_links,
--          quality_signals, version_major/minor/patch
-- Keeps:   id, name, version (text), description, domain, status,
--          capability_tags, created_at
-- =============================================================================

-- Delete all existing skills (replaced by new design)
DELETE FROM skill_health_metric;
DELETE FROM skill;

-- Drop the old unique constraint and indexes
ALTER TABLE skill DROP CONSTRAINT IF EXISTS skill_name_version_major_version_minor_ve_key;
DROP INDEX IF EXISTS idx_skill_name_published;
DROP INDEX IF EXISTS idx_skill_status;

-- Drop unnecessary columns
ALTER TABLE skill
    DROP COLUMN IF EXISTS manifest,
    DROP COLUMN IF EXISTS circuit_state,
    DROP COLUMN IF EXISTS version_major,
    DROP COLUMN IF EXISTS version_minor,
    DROP COLUMN IF EXISTS version_patch,
    DROP COLUMN IF EXISTS inputs,
    DROP COLUMN IF EXISTS outputs,
    DROP COLUMN IF EXISTS preconditions,
    DROP COLUMN IF EXISTS side_effects,
    DROP COLUMN IF EXISTS required_permissions,
    DROP COLUMN IF EXISTS examples,
    DROP COLUMN IF EXISTS reference_links,
    DROP COLUMN IF EXISTS quality_signals;

-- Add version as a simple text field
ALTER TABLE skill ADD COLUMN IF NOT EXISTS version TEXT NOT NULL DEFAULT '1.0.0';

-- Add unique constraint on name (skill names must be globally unique)
ALTER TABLE skill ADD CONSTRAINT skill_name_unique UNIQUE (name);

-- Recreate useful indexes
CREATE INDEX idx_skill_status ON skill(status);
CREATE INDEX idx_skill_domain ON skill(domain);
