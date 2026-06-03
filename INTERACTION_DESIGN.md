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
- "Alex, please move ticket AIT-1234 forward and report back."
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
- Knowledge
- Settings

P0 should not keep a separate Home page. The empty hash route should open Chat directly, because the first screen should be the operational workbench.

Runtime/provider settings belong in Settings because they are Kernel running conditions, not the operational work surface. Chat should keep a compact runtime indicator and a deep link to `#/settings/runtimes`.

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

## 8. Member thread persistence

Each member owns a stable default chat thread, such as `member-clara-default`.

P0 behavior:

- Opening Chat selects the last active member if available; otherwise Clara.
- Switching member loads that member's active thread through assistant-ui history.
- Leaving Chat for Members or Skills and returning restores the same member thread.
- Starting a new thread calls the backend thread API; the backend creates the member-scoped thread id and marks it active.
- The Thread panel lists backend-owned thread metadata, including title, message count, updated time, and active state.
- The backend remains the canonical transcript store under `.aiteamos/conversations/<thread_id>.jsonl`.
- The backend remains the canonical thread metadata store under `.aiteamos/threads/index.json`.

Conversation history is not long-term memory. It is thread-scoped transcript state used for UI restore and short-term provider context. LangGraph checkpoint state is persisted locally through SQLite under `.aiteamos/langgraph/checkpoints.sqlite` and should handle pending approvals and interrupt/resume as the graph grows.

## 9. Graphiti memory governance

Long-term memory uses Graphiti as the primary backend. AITeamOS keeps a local
file mirror only for candidate review, approval state, provenance, and offline
recall.

P0 behavior:

- Chat responses can create memory candidates when a turn contains WorkItem,
  decision, root-cause, style, architecture, or validation signals.
- Candidates are not injected into member context until approved.
- Approved memories are available to Chat through the local mirror and can be
  ingested into Graphiti when Graphiti and Neo4j are configured.
- Graphiti `disabled` means the package may be installed, but the Graphiti
  backend is not enabled; the local memory mirror remains active.
- Graphiti configuration belongs in Settings / Knowledge Backend. Users should
  provide only the required runtime choices and credentials; Neo4j and
  Graphiti remain internal AITeamOS dependencies.
- Memory page shows Graphiti status, candidates, approved memories, search
  results, source trace, scope, confidence, member assignment, and ingestion
  state.
- LangGraph checkpoint remains thread-scoped state; it is not the long-term
  memory backend.

## 10. Knowledge navigation

Memory is promoted into a first-level Knowledge area.

P0 behavior:

- Sidebar shows `Knowledge` as the first-level entry.
- Expanding Knowledge reveals `Docs`, `Memories`, `Decisions`, and `Review Queue`.
- `Docs` reads local Markdown first and shows Plane Pages as the external Docs
  source once the Plane connector is configured. It does not inspect source code
  files.
- `Memories` shows approved Graphiti/file-backed memories.
- `Decisions` shows accepted decision documents under `.aiteamos/knowledge/decisions`.
- `Review Queue` shows pending candidate items, initially memory candidates.
- A unified search calls `search_knowledge` across Docs, Decisions, and approved Memories.
- Docs detail surfaces may show an `Open in Plane` deep link for Plane Pages, but
  AITeamOS does not clone Plane's full Page editor in P0.

## 11. Work navigation

Work is promoted into a first-level AI running view over local P0 WorkItems and
the Plane connector. It is not a replacement project-management UI.

P0 behavior:

- Sidebar shows `Work` as the first-level entry.
- Expanding Work reveals `Tickets`, `Flow Trace`, and `Reports`.
- `Tickets` shows Plane connector readiness, workspace/project configuration,
  local WorkItems, assignee/validation signals, report counts, and `Open in
  Plane` when a Plane base URL is configured.
- `Flow Trace` shows the Clara -> Member -> PV -> Clara path for a selected
  WorkItem. P0 can start with local traces and empty states.
- `Reports` shows Member/PV reports written back to WorkItems.
- Complex ticket editing, permissions, project planning, and page authoring stay
  in Plane.

## 12. Local WorkItem delegation

P0 uses local WorkItems to prove the Clara-led flow before wiring a real
external WorkItem/Docs connector. The fixed default external target is Plane:
Plane work items map to WorkItems, and Plane pages map to Docs. Redmine,
Jira / Confluence, and OpenProject are not implemented unless AITeamOS later
needs broad ticket-system compatibility.

P0 behavior:

- Clara can create a local WorkItem from chat.
- The WorkItem records title, description, assigned member or role, validation
  member or role, source thread/run, and Knowledge refs.
- The assigned Member is responsible for technical investigation and repo state.
  Clara does not inspect repo state directly.
- Member/PV outputs are recorded as WorkItem reports.
- Clara summarizes and cross-checks reports with Knowledge through the LLM,
  while AITeamOS only persists the evidence and trace.

## 13. Settings navigation

Settings is the first-level configuration and operations area for Kernel
running conditions. It is not the primary work surface.

P0 behavior:

- `Runtimes` owns runtime policy plus provider-specific cards. Runtime policy
  selects the active provider and fallback behavior; DeepSeek, OpenAI, file
  stub, and future providers keep separate model/key/config save actions.
- `Providers` shows configured LLM providers such as file stub, DeepSeek, and
  OpenAI.
- `Agent Executors` shows external coding/agent runtimes such as Codex, Cursor,
  Qoder, and Claude Code.
- `Capabilities` is the read-only capability registry view. It groups local
  tools, MCP connectors, MCP capabilities, and planned agent executors, and it
  explains the product boundary between Knowledge, Skill, Tool, MCP, and
  Executor. It is for planning, permission review, health, and debugging, not
  for ordinary work execution.
- `Code Repositories` stores the thin mapping from Plane workspace/project to
  repo source. Supported source types are local path, GitHub, Gitea, GitLab, and
  generic Git URL. Local paths get a lightweight `.git` health check; remote
  repositories are recorded for provider connectors and agent executors.
- Clara can call `list_code_repositories` from Chat. `create_work_item` can
  attach `code_repository_ids` so the delegated Member knows which repo context
  to inspect.
- Non-Clara Members can call `inspect_code_repository` against configured local
  repositories. The tool searches/reads bounded text files and, when a WorkItem
  id is present, records a WorkItem report with repo evidence. Clara receives a
  boundary message if asked to inspect repo state directly.
- `MCP Connectors` reads the file-backed connector registry and shows each
  connector's transport, readiness, capabilities, permissions, and required
  settings. It is the entry point for Plane, GitHub, filesystem, and CI/Harness
  connector wiring.
- Connector settings expose API base URL, credentials, readiness, and
  capabilities. The UI should not branch WorkItem/Docs behavior into local
  versus cloud paths; that is an endpoint concern hidden behind connector
  adapters.
- `Knowledge Backend` owns Graphiti enablement, Neo4j connection settings,
  Graphiti group id, and the LLM key used by Graphiti ingestion/search.
- `Secrets` shows local configured/missing secret state without revealing secret
  values.
- `Defaults` shows member runtime modes and default thread ids.
- `Health` summarizes runtime, Knowledge, Capabilities, MCP, Memory/Graphiti,
  repository, and member readiness.
- Chat keeps only a compact runtime indicator plus a link to
  `#/settings/runtimes`.
