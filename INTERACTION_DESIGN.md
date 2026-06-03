# AITeamOS Interaction Design

**Status**: P0 interaction decision  
**Date**: 2026-06-03  
**Scope**: Member Chat Workbench, secondary entity views, and first tool behavior

---

## 1. Core Decision

AITeamOS should feel like an agent team workbench, not a CRUD admin console.

Chat is the primary operational surface. Entity pages are secondary surfaces for inspection, comparison, audit, debugging, and manual maintenance.

This means the same capability may appear in two places:

- In Chat, the user asks a member to do something.
- In an entity page, the user inspects or manually adjusts the underlying asset.

Both surfaces should call the same underlying action or tool contract whenever possible.

---

## 2. Surface Roles

### Chat

Chat handles intent, delegation, tool execution, and next-step recommendations.

Typical requests:

- "Clara, list all members."
- "Alex, please move Jira SV-1234 forward and report back."
- "Create a skill for nightly regression log triage and assign it to PV."

Chat responses should include:

- A concise result summary.
- Relevant evidence or trace pointer.
- Suggested next actions.
- Deep links when browsing or manual inspection is useful.

### Entity Views

Entity views are not the main path for work execution.

They are useful when the user needs to:

- Browse or filter many assets.
- Compare member or skill details.
- Audit what changed and why.
- Debug trace, runtime, memory, or permission behavior.
- Make a manual correction when Chat is too indirect.

P0 entity views can be read-only until a clear manual edit workflow is needed.

---

## 3. Navigation Model

The navigation should keep Chat first and keep other areas available as supporting views:

- Chat
- Members
- Skills
- Memory
- Trace
- Settings

P0 should not keep a separate Home page. The empty hash route should open Chat directly, because the first screen should be the operational workbench.

Runtime/provider settings belong near Chat during P0 because they directly affect the current conversation. Later they may move into Settings while keeping a compact Chat-side runtime indicator.

---

## 4. Tool Result Pattern

Every local tool result should follow one stable shape:

1. What happened.
2. What AITeamOS found or changed.
3. Gaps, risks, or blockers.
4. Suggested next actions.
5. Deep links for inspection.
6. Trace events for replay and debugging.

The user should not need to open another page to understand the result. A link is an optional expansion path, not a forced redirect.

P0 tool routing should not depend on fixed command phrasing. When a configured model provider is available, Clara first asks an LLM tool planner to return a structured tool call. AITeamOS then executes the selected local tool deterministically. Local keyword parsing is only a fallback for development, offline mode, or planner failure.

---

## 5. `list_members`

`list_members` is the first local tool because it proves the Chat-plus-entity-view pattern.

When the user asks to list members, Clara should answer in the current conversation with:

- Total member count.
- One-line summary per member.
- Skill count and runtime mode per member.
- Obvious team gaps when built-in roles are missing.
- Links to `#/members` and specific member anchors.

The Members page should show the same file-backed member source in a browseable view. It should not own a separate member model or duplicate action logic.

P0 behavior:

- Tool execution is deterministic and local.
- Remote chat generation is bypassed after the tool is selected.
- Conversation and trace are still persisted.
- The streaming API emits normal `start`, `delta`, and `final` events for the tool result.

## 6. `create_member` and `edit_member_profile`

Member profile changes should start in Chat during P0.

Examples:

- "Clara, create an AI PV member named Victor, responsible for regression and harness fail triage."
- "Clara, update Alex summary to backend API implementation owner."
- "Clara, add skill test-engineering to Alex."

P0 behavior:

- `create_member` writes a new `.aiteamos/members/<id>.yaml` file.
- `edit_member_profile` updates supported safe fields in an existing member profile: display name, role, summary, skills, and runtime mode.
- Both tools use LLM planning when available, execute locally, and write trace events.
- The chat response includes the changed fields, saved profile path, and `#/members/<id>` deep link.
- The Members page remains a read-only inspection surface for confirming profile state.

## 7. Skill tools

Skill changes should also start in Chat during P0.

Examples:

- "Clara, list all skills."
- "Clara, create a Skill named nightly-regression-log-triage for analyzing nightly regression logs."
- "Clara, assign nightly-regression-log-triage to Alex."
- "Clara, delete Skill nightly-regression-log-triage."

P0 behavior:

- `list_skills` reads local `.aiteamos/skills/*/SKILL.md` files.
- `create_skill` writes a new `.aiteamos/skills/<id>/SKILL.md` file.
- `assign_skill_to_member` updates the target member profile's `skills` list.
- `delete_skill` removes the skill directory and removes that skill id from all member profiles.
- The Skills page remains a read-only inspection surface for confirming file-backed state.
