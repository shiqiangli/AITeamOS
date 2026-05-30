-- =============================================================================
-- Migration 011: Global human-readable name uniqueness
--
-- UI workflows address resources by name. These indexes prevent duplicate
-- names from forcing users back to UUIDs.
-- =============================================================================

CREATE UNIQUE INDEX IF NOT EXISTS idx_skill_name_unique ON skill(name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_title_unique ON memory_node(title);
CREATE UNIQUE INDEX IF NOT EXISTS idx_project_name_unique ON project(name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_task_title_unique ON task(title);
