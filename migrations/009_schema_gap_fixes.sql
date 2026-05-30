-- =============================================================================
-- Migration 009: Schema Gap Fixes
--
-- Fixes column-level mismatches discovered during code/schema audit:
--   1. member.health             — JSONB column used by repository but missing from DDL
-- =============================================================================

-- 1. Add health metrics column to member table (referenced by PostgresMemberRepository)
ALTER TABLE member ADD COLUMN IF NOT EXISTS health JSONB NOT NULL DEFAULT '{}';
