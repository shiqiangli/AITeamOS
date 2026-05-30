-- =============================================================================
-- Migration 010: Add display_name column and UNIQUE constraints
--
-- Ensures human-readable names are unique to avoid UUID exposure in UI.
-- =============================================================================

-- 1. Add display_name column to member (extract from profile JSONB)
ALTER TABLE member ADD COLUMN IF NOT EXISTS display_name TEXT;
UPDATE member SET display_name = profile->>'display_name' WHERE profile->>'display_name' IS NOT NULL;
ALTER TABLE member ALTER COLUMN display_name SET NOT NULL;
ALTER TABLE member ADD CONSTRAINT member_display_name_key UNIQUE (display_name);

-- 2. UNIQUE constraint on department.name
ALTER TABLE department ADD CONSTRAINT department_name_key UNIQUE (name);

-- 3. UNIQUE constraint on project.name per department
ALTER TABLE project ADD CONSTRAINT project_department_name_key UNIQUE (department_id, name);

-- 4. Create index for faster name-based lookups
CREATE INDEX IF NOT EXISTS idx_member_display_name ON member(display_name);
CREATE INDEX IF NOT EXISTS idx_department_name ON department(name);
CREATE INDEX IF NOT EXISTS idx_project_name ON project(name);
