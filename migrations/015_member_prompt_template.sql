-- =============================================================================
-- Migration 015: Add prompt_template column to member table
--
-- Stores the per-member prompt template with {variable} placeholders.
-- Context Assembler fills placeholders at T3 assembly time using
-- current skills, memories, and project context.
-- =============================================================================

ALTER TABLE member ADD COLUMN IF NOT EXISTS prompt_template TEXT NOT NULL DEFAULT '';
