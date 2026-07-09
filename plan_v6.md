# AITeamOS plan_v6: LangGraph-native Agent Workbench

状态：新版主计划，取代 `plan_v5.md` 中关于 Chat UI / frontend runtime / agent workbench 的渐进式方案  
日期：2026-06-19  
决策：保留 `plan_v5.md` 作为 Runtime MVP 到 AI Team OS 的历史实现记录；从现在开始，Chat 与 Agent Workbench 相关新开发以本文件为准。

## 0. 一句话目标

直接重建 Chat 为 LangGraph-native Agent Workbench：以 Agent Chat UI 为页面蓝本，以 LangChain Frontend SDK 为 runtime，以 assistant-ui 作为组件复用来源，以 AITeamOS Ticket / Employees / Assets / Governance 作为唯一产品核心；AG-UI 只保留为可选协议兼容层。

## 1. 核心原则

保持我们的 Ticket / Employees / Assets / 治理核心，其它所有的都不应该重复造轮子，应该复用现有的成熟稳定可靠友好的方案。

这条原则是 `plan_v6` 的硬约束：

- AITeamOS 自己掌控：Ticket 流转、Employee 身份和权限、Assets 生命周期、治理审批、provenance、provider adapter、业务事实账本。
- AITeamOS 不自研：通用 Chat 线程体验、通用 agent loop、通用 streaming protocol、通用 tool-call UI、通用 checkpoint / interrupt UI、通用 trace / replay IDE。
- 所有 provider 都只能挂在 AITeamOS 领域边界后面，不能反过来定义 AITeamOS 的产品模型。
- 没有历史用户，不考虑旧 Chat UI 兼容；只选对的方案，直接切换。
- Chat 页面可以重写。重写目标不是做一个漂亮聊天框，而是做 AITeamOS 的 agent workbench。

## 2. 为什么要新建 plan_v6

`plan_v5.md` 已经包含大量已经完成的 Runtime / Assets / Provider / Replay / Graphiti / Employee work ledger 实现记录。继续在 `plan_v5` 上追加新版 Chat 方向，会把两个不同决策混在一起：

- `plan_v5`：在现有 Chat / AG-UI / Dashboard 形态上持续补强 runtime 和治理闭环。
- `plan_v6`：不再假设现有 Chat 页面值得保留，直接按 LangGraph-native Agent Workbench 重建。

因此 `plan_v6` 是主计划；`plan_v5` 是历史实现和可复用事实记录。

## 3. 外部方案定位

### 3.1 LangGraph

定位：后端 agent runtime / graph orchestration。

AITeamOS 用 LangGraph 负责：

- long-running stateful agent execution
- checkpoint
- interrupt / resume
- human approval
- graph state
- tool execution orchestration
- Employee handoff graph
- Ticket-native autonomous loop

LangGraph 不负责定义 AITeamOS 的 Ticket / Employee / Asset 业务模型。

### 3.2 LangChain

定位：agent framework 和应用构建层，不是单纯前端 UI。

AITeamOS 可以复用 LangChain 的：

- model abstraction
- tool schema / tool calling
- middleware
- context engineering
- agent harness
- frontend SDK
- LangGraph 集成能力

LangChain 和 LangGraph 是上下游协作关系：LangChain 提供 agent building blocks，LangGraph 提供 durable runtime。

### 3.3 LangChain Frontend SDK

定位：前端 agent runtime 连接层，不是完整 Chat 页面。

AITeamOS 用它负责：

- messages streaming
- tool call lifecycle
- interrupts
- checkpoint history
- thread rejoin
- custom graph state values
- frontend 与 LangGraph server 的 runtime state 同步

它替代我们手写 streaming / thread / tool-call state glue。

### 3.4 Agent Chat UI

定位：成熟 Chat app 蓝本和交互参考。

AITeamOS 用它作为：

- Chat Workbench 页面蓝本
- tool visualization 参考
- time-travel / state forking 参考
- thread / run / assistant 体验参考
- 可抽取组件和行为模式来源

如果 Agent Chat UI 的 Next.js 依赖过重，不强行整页嵌入；优先抽取行为、布局和组件模式，落到当前 Dashboard 技术栈。

### 3.5 assistant-ui

定位：React AI Chat 组件和 runtime primitives。

AITeamOS 用它作为：

- message thread
- composer
- message branching
- attachments
- markdown / action components
- LangChain / LangGraph bridge 组件来源

assistant-ui 是 UI 组件层；LangChain Frontend SDK 是 runtime state 层。两者可以组合。

### 3.6 AG-UI

定位：agent-user interaction protocol。

在 `plan_v6` 中，AG-UI 不再是主 Chat 方案。它只保留为：

- 兼容协议层
- 外部 agent UI adapter
- 未来多 runtime bridge 的可选入口

如果新版 Chat 已通过 LangChain Frontend SDK 直连 LangGraph runtime，AG-UI 不应继续决定主 Chat 页面结构。

### 3.7 Graphiti

定位：长期组织记忆的 temporal graph projection / retrieval provider。

Graphiti 不是 source of truth。AITeamOS Assets / Review Queue / Ticket ledger 才是 source of truth。

Graphiti 用于：

- approved Assets 投影
- temporal memory graph
- relationship search
- fact evolution
- Graph-based recall

### 3.8 LangSmith / Agent Server

定位：生产化 agent 平台和 observability / deployment 层。

它们属于运行平台层，不属于 AITeamOS 业务模型层。

可用于：

- hosted / managed LangGraph deployment
- assistant / thread / run API
- trace / eval / debugging
- production task queue
- observability

不能让 LangSmith / Agent Server 替代 AITeamOS 的 Ticket / Employee / Asset / Governance。

## 4. 目标架构

```text
User
  -> AITeamOS Dashboard
      -> Chat Agent Workbench
          -> Agent Chat UI / assistant-ui components
          -> LangChain Frontend SDK runtime
          -> LangGraph Agent API / Agent Server compatible endpoint
              -> AITeamOS LangGraph graph
                  -> load Employee identity
                  -> bind or create Ticket
                  -> retrieve Assets / Memory / Docs / Skills
                  -> plan and call tools
                  -> interrupt for approval
                  -> resume from checkpoint
                  -> handoff through Ticket assignee
                  -> ingest reports / evidence / candidates
          -> Workbench side panels
              -> FastAPI AITeamOS domain APIs
              -> Ticket ledger
              -> Employee ledger
              -> Assets / Review Queue
              -> Runtime Replay
              -> Provider status

AITeamOS Assets / Review Queue / Ticket ledger
  -> approved records
  -> Graphiti projection / recall

LangGraph checkpointer / store
  -> runtime continuity only
  -> thread state, checkpoint, interrupts
```

## 5. Source of Truth

### 5.1 AITeamOS source of truth

AITeamOS owns the durable product truth:

- Tickets: work intent, collaboration flow, reports, evidence, validation, blockers, closeout.
- Employees: fixed identity, skills, personality tags, capability tags, permission boundaries, work history, memory scopes.
- Assets: memory, docs, skills, tool calls, decisions, solutions, suggestions, validation results, closeout, employee profile improvements.
- Governance: approval records, review queue, risk policy, provenance.

### 5.2 Runtime source of truth

LangGraph owns execution continuity:

- graph state
- checkpoint refs
- interrupt state
- run state
- thread state
- transient tool-call lifecycle

LangGraph state can be replayed and referenced, but durable organizational knowledge must flow through AITeamOS Assets.

### 5.3 Projection source of truth

Graphiti owns no product truth. It is a projection and retrieval provider for approved AITeamOS Assets.

If Graphiti is down:

- approved Assets still exist
- Ticket ledger still exists
- Employee memory scopes still exist
- recall is degraded and surfaced as a setup blocker
- no fake successful memory recall is allowed

## 6. Chat Workbench Product Shape

The Chat page becomes the primary AITeamOS workbench, not a simple chat transcript.

### 6.1 Main thread

Reuse mature Chat components for:

- user / assistant messages
- streaming
- composer
- stop / retry
- branch / edit if provided by reused library
- markdown rendering
- attachment handling if needed
- tool-call visualization
- interrupt cards
- checkpoint / run controls

AITeamOS should not hand-roll these primitives unless no mature component exists.

### 6.2 AITeamOS state panels

Custom UI belongs here because it is our product core:

- Active Ticket panel
- Employee identity and permission panel
- Linked Assets panel
- Memory / Graphiti recall panel
- Approval / Review Queue panel
- Provenance / Replay panel
- Provider readiness panel

These panels consume LangGraph custom state plus AITeamOS FastAPI domain APIs.

### 6.3 Inline domain cards

The Chat thread can render AITeamOS-specific cards:

- Created Ticket
- Selected Ticket
- Assignee changed
- Employee handoff
- Approval required
- Approval resumed
- Memory candidate proposed
- Asset candidate proposed
- Report appended
- Evidence recorded
- Validation requested
- Ticket closeout proposed

These cards are domain-specific. We build them because they are AITeamOS, not generic Chat.

### 6.4 Required Workbench state

The LangGraph graph should expose custom state values shaped for the frontend:

```text
active_ticket
selected_employee
employee_identity
capability_scope
linked_assets
recalled_memory_refs
approval_requests
asset_candidates
provenance_events
runtime_status
provider_blockers
workbench_panels
```

The frontend should subscribe to these values through LangChain Frontend SDK instead of reconstructing them from raw text.

## 7. Backend Design

### 7.1 LangGraph graph entrypoint

Create a first-class graph entrypoint for the Agent Workbench.

Suggested location:

```text
services/api/aiteamos_api/agents/aiteamos_workbench_graph.py
langgraph.json
```

The graph must be runnable by LangGraph tooling or an Agent Server compatible endpoint.

### 7.2 Graph state contract

```python
class AITeamOSWorkbenchState(TypedDict, total=False):
    messages: list[AnyMessage]
    thread_id: str
    employee_id: str
    employee_identity: dict[str, Any]
    active_ticket: dict[str, Any] | None
    ticket_binding: dict[str, Any]
    capability_scope: dict[str, Any]
    context_bundle: dict[str, Any]
    linked_assets: list[dict[str, Any]]
    recalled_memory_refs: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    approval_requests: list[dict[str, Any]]
    asset_candidates: list[dict[str, Any]]
    provenance_events: list[dict[str, Any]]
    provider_blockers: list[dict[str, Any]]
    workbench_panels: dict[str, Any]
    final_response: str
```

### 7.3 Graph nodes

Minimum graph nodes:

- `bootstrap_request`
- `load_employee_identity`
- `bind_or_create_ticket`
- `retrieve_context`
- `plan_next_action`
- `execute_read_tools`
- `governance_gate`
- `approval_interrupt`
- `resume_after_approval`
- `execute_governed_action`
- `maybe_handoff_employee`
- `ingest_result`
- `propose_assets`
- `update_workbench_state`
- `final_response`

The graph may use subgraphs for:

- Ticket loop
- Employee handoff
- Asset proposal
- Memory recall
- Validation

### 7.4 Tool boundary

Read tools can directly query AITeamOS service boundaries:

- `tickets.search`
- `tickets.get`
- `employees.get_profile`
- `employees.get_work_history`
- `assets.search`
- `memory.recall`
- `docs.search`
- `skills.search`
- `system.status`

Write tools must be governed:

- `tickets.create`
- `tickets.append_report`
- `tickets.record_evidence`
- `tickets.request_validation`
- `tickets.change_assignee`
- `assets.propose_candidate`
- `memory.propose_candidate`
- `approvals.request`
- `runtime.record_trace`

Any risky write must pass `governance_gate` and use LangGraph interrupt / resume when approval is required.

### 7.5 Main API shape

Preferred target:

- expose the graph through LangGraph Agent Server compatible API
- connect frontend with LangChain Frontend SDK
- keep FastAPI as AITeamOS domain API and provider control plane

Fallback only if blocked:

- implement a thin FastAPI facade that is compatible with the LangChain Frontend SDK expectations
- do not invent a new event protocol
- do not rebuild AG-UI as the main path

### 7.6 Chat route cleanup

The old Chat route should stop owning agent behavior.

Allowed in route layer:

- auth / request parsing
- domain read APIs
- settings APIs
- static metadata
- bridge to graph server if unavoidable

Not allowed in route layer:

- generic agent loop
- tool dispatcher
- memory selection logic
- employee handoff logic
- approval state machine
- custom streaming protocol

## 8. Frontend Design

### 8.1 App strategy

Keep AITeamOS Dashboard as the product shell unless a separate Agent Chat UI fork proves dramatically lower cost.

Rationale:

- Tickets / Assets / Employees pages are AITeamOS-specific and already exist in the Dashboard.
- The Chat page can be replaced without migrating the whole product shell.
- Agent Chat UI is a blueprint and component source, not necessarily the whole app shell.

Decision rule:

- If Agent Chat UI components are easy to extract into the existing Dashboard, port them.
- If extraction is expensive but the app works well as a standalone workbench, create `apps/agent-workbench` and route Dashboard Chat to it.
- Do not rewrite Tickets / Assets / Employees into a generic Chat app.

### 8.2 Dependencies

Expected frontend additions:

```text
@langchain/react
assistant-ui LangChain / LangGraph bridge package if needed
Agent Chat UI source or selected components
```

Expected frontend de-emphasis:

```text
@ag-ui/client
@assistant-ui/react-ag-ui
```

Do not remove AG-UI packages until the new Workbench path passes end-to-end and no main Chat code imports them.

### 8.3 Workbench component layout

Suggested file structure:

```text
apps/dashboard/src/pages/chat/
  index.tsx
  workbench/
    AgentWorkbench.tsx
    WorkbenchThread.tsx
    WorkbenchComposer.tsx
    WorkbenchPanels.tsx
    ActiveTicketPanel.tsx
    EmployeePanel.tsx
    AssetsPanel.tsx
    ApprovalPanel.tsx
    ProvenancePanel.tsx
    ProviderBlockerPanel.tsx
    cards/
      TicketCard.tsx
      HandoffCard.tsx
      ApprovalCard.tsx
      AssetCandidateCard.tsx
      MemoryRecallCard.tsx
      ToolCallCard.tsx
    runtime/
      useAiteamosWorkbenchStream.ts
      stateMapping.ts
      threadPersistence.ts
```

### 8.4 State mapping

The frontend should read from structured runtime state:

```text
LangChain Frontend SDK stream
  -> messages
  -> tool calls
  -> interrupts
  -> values.active_ticket
  -> values.selected_employee
  -> values.linked_assets
  -> values.approval_requests
  -> values.provenance_events
```

The frontend should not parse assistant text to discover Tickets, Assets, approvals, or memory refs.

### 8.5 UI acceptance

The Workbench must show, in one screen:

- who is working
- what Ticket is active
- what Assets / Memory were used
- what tools ran
- what approval is needed
- what changed in Ticket / Assets / Employee ledger
- how to replay or inspect the run

If the UI only looks like a chat transcript, it is not done.

## 9. Memory Design

### 9.1 Three memory layers

```text
LangGraph checkpointer / store
  -> runtime memory
  -> thread continuity
  -> interrupts
  -> short-lived or scoped facts

AITeamOS Assets / Review Queue
  -> durable organizational memory source of truth
  -> provenance
  -> approval
  -> usefulness feedback
  -> lifecycle

Graphiti
  -> approved Asset projection
  -> temporal graph recall
  -> relationship search
  -> fact evolution
```

### 9.2 What goes where

Runtime state:

- current messages
- graph node
- pending tool call
- pending interrupt
- checkpoint
- temporary context

AITeamOS Assets:

- validated solution
- approved memory
- ticket closeout
- skill improvement
- employee profile update
- useful tool-call pattern
- doc / decision / validation result

Graphiti:

- approved memory projection
- approved solution projection
- ticket closeout projection
- employee profile summary projection
- relationships among Ticket, Employee, Asset, Skill, Decision

### 9.3 Memory lifecycle

```text
Runtime result
  -> memory / asset candidate
  -> Review Queue
  -> approved AssetRecord
  -> Graphiti projection
  -> scoped recall
  -> usefulness feedback
  -> ranking / stale / promoted / rejected lifecycle
```

### 9.4 Hard memory rules

- Raw chat transcripts are not durable memory by default.
- LangGraph store is not the organizational memory source of truth.
- Graphiti is not the organizational memory source of truth.
- Memory writes must be Ticket-bound or Employee-bound when possible.
- Durable memory must preserve source Ticket, Employee, run, tool, approval, evidence, and review provenance.

## 10. Direct Implementation Tracks

This is not a compatibility migration plan. These tracks describe the fastest safe commit order for the final architecture.

### Track A: Architecture reset

Tasks:

1. Mark `plan_v6.md` as the active plan.
2. Identify all main Chat imports from AG-UI / `react-ag-ui`.
3. Identify reusable current domain APIs for Tickets, Employees, Assets, Runtime Replay, Provider Status.
4. Decide whether Agent Chat UI is ported into `apps/dashboard` or mounted as `apps/agent-workbench`.
5. Add a dependency decision note in the plan or architecture docs.

Acceptance:

- One chosen Chat Workbench implementation path.
- No ambiguity about AG-UI main path versus optional compatibility path.

### Track B: LangGraph-native Workbench graph

Tasks:

1. Add `aiteamos_workbench_graph.py`.
2. Add `langgraph.json` if using LangGraph server tooling.
3. Define `AITeamOSWorkbenchState`.
4. Move Chat context orchestration into graph nodes.
5. Expose active Ticket, selected Employee, linked Assets, approval requests, provider blockers, and provenance as custom state values.
6. Keep all writes behind governed tools and ingestion services.

Acceptance:

- A single LangGraph run can answer a Chat request and emit structured Workbench state.
- The run can bind to an existing Ticket or propose creating one.
- Tool calls and provider blockers are visible as structured state, not only text.

### Track C: LangChain Frontend SDK runtime

Tasks:

1. Add `@langchain/react`.
2. Create `useAiteamosWorkbenchStream`.
3. Connect to LangGraph Agent API / compatible endpoint.
4. Map SDK messages, tool calls, interrupts, thread id, checkpoint refs, and custom state values into Workbench components.
5. Remove custom Chat event parsing from the main path.

Acceptance:

- Chat messages stream through LangChain Frontend SDK.
- Tool calls render from SDK state.
- Interrupts render from SDK state.
- Thread rejoin works through SDK-supported thread state.

### Track D: Agent Chat UI / assistant-ui replacement

Tasks:

1. Audit Agent Chat UI components and UX flows.
2. Reuse or port mature thread / composer / tool-call / interrupt UX.
3. Use assistant-ui primitives where they reduce custom UI logic.
4. Build only AITeamOS-specific cards and side panels.
5. Delete or isolate the old self-built Chat thread implementation.

Acceptance:

- Chat page is no longer a hand-built generic chat UI.
- Core interaction quality comes from mature reused components.
- AITeamOS-specific UI is limited to domain cards and panels.

### Track E: Governance and approval interrupt

Tasks:

1. Move approval gating into LangGraph interrupt.
2. Store checkpoint / thread / run refs with approval records.
3. Resume from checkpoint after approval.
4. Render approval interrupts in the Workbench.
5. Record rejected approvals into Ticket / Employee ledger.

Acceptance:

- Approval does not redispatch an approximate new request.
- Approval resumes the same graph state.
- Workbench shows pending approval and resume result.

### Track F: Memory and Assets integration

Tasks:

1. Keep LangGraph checkpointer / store for runtime continuity.
2. Keep AITeamOS Assets / Review Queue as durable memory source of truth.
3. Keep Graphiti as approved Asset projection and recall provider.
4. Show recalled memories and asset candidates in Workbench state.
5. Require review before durable memory projection.

Acceptance:

- A Chat run can recall approved Graphiti-backed memory.
- A Chat run can propose a memory / solution / closeout candidate.
- Candidate review creates an approved AssetRecord.
- Approved AssetRecord can project to Graphiti.
- Raw transcript is not automatically durable memory.

### Track G: Old Chat / AG-UI isolation

Tasks:

1. Move AG-UI code into an explicit compatibility module.
2. Remove AG-UI imports from main Chat page.
3. Remove AG-UI assumptions from primary tests.
4. Keep optional endpoints only if they serve a clear external compatibility need.
5. Update system status to distinguish primary LangGraph-native Workbench from optional AG-UI compatibility.

Acceptance:

- Main Chat path does not depend on AG-UI.
- AG-UI can be disabled without breaking AITeamOS Chat.

### Track H: End-to-end dogfood

Tasks:

1. Start Dashboard, FastAPI, LangGraph graph server or compatible runtime.
2. Ask Clara to create or advance a real Ticket.
3. Route work to a fixed Employee.
4. Use related Tickets / Assets / Memory context.
5. Trigger a governed action requiring approval.
6. Resume from approval.
7. Write Ticket report / evidence.
8. Propose durable Asset candidate.
9. Review and approve candidate.
10. Project approved Asset to Graphiti.
11. Recall it in a later Chat run.

Acceptance:

- One real self-bootstrap loop proves the whole architecture.
- Replay can trace Chat -> LangGraph run -> Ticket -> Employee -> Assets -> Approval -> Graphiti recall.
- Blockers are surfaced honestly when provider config is missing.

## 11. Implementation Status

### 2026-06-19: Track A/B/C/G first slice - LangGraph-native Workbench entrypoint and frontend runtime switch

Completed:

- Added `langgraph.json` with `aiteamos_workbench` graph entrypoint.
- Added `services/api/aiteamos_api/agents/aiteamos_workbench_graph.py`.
- Added `services/api/aiteamos_api/agents/__init__.py`.
- Refactored `services/api/aiteamos_api/read/chat_routes.py` so the route calls a reusable `run_chat_message()` function.
- Added `@langchain/react` and `@assistant-ui/react-langchain` to Dashboard dependencies.
- Replaced the main Chat page runtime provider from AG-UI / `@assistant-ui/react-ag-ui` to assistant-ui's LangChain runtime adapter backed by LangChain Frontend SDK.
- Main Chat page no longer imports `@ag-ui/client` or `@assistant-ui/react-ag-ui`.
- Existing AITeamOS thread history, Ticket/Employee/Assets/Approval/Provenance panels remain in the product shell.
- Added a focused graph test proving `aiteamos_workbench` emits structured Workbench state: active Ticket, Employee identity, Ticket binding, linked Assets, recalled memories, approval requests, provider blockers, asset candidates, runtime checkpoint refs, and final AI message.
- Updated Chat page tests to assert LangChain Workbench runtime usage and approval `runConfig` propagation instead of AG-UI URL construction.

Validation:

```bash
python -m py_compile services/api/aiteamos_api/agents/__init__.py services/api/aiteamos_api/agents/aiteamos_workbench_graph.py services/api/aiteamos_api/read/chat_routes.py
pytest tests/test_aiteamos_workbench_graph.py -q
cd apps/dashboard && npm test -- chat-page.test.tsx
cd apps/dashboard && npm run build
```

Observed notes:

- `npm install` surfaced Node engine warnings because the current shell uses Node `v18.19.1`, while new LangChain packages and transitive packages request Node `>=20`.
- `npm audit` reports existing dependency vulnerabilities after install; no audit fix was run because that could introduce broad package churn unrelated to this slice.
- Python graph test still shows an existing Graphiti/Pydantic deprecation warning from `graphiti_core`.

Remaining gaps:

- The Workbench graph still delegates durable Chat execution to existing AITeamOS governance / ingestion, which is intentional for Ticket / Assets / Governance source-of-truth preservation.
- The graph exposes structured Workbench state, but the frontend still uses the existing details panel derived from `aiteamos_chat_response`; next slice should read more panels directly with `useLangChainState`.
- The main Chat path is LangChain runtime based, but local operation now expects a LangGraph Agent Server compatible endpoint at `VITE_LANGGRAPH_API_URL` or `http://localhost:2024`.
- AG-UI packages remain installed for compatibility and non-main-path endpoints; later Track G should isolate or remove them once no tests or optional routes require them.
- Per-run configurable is now set through assistant-ui composer runConfig; browser/server propagation is covered by the later Playwright smoke in this status log.

### 2026-06-19: Track B service-boundary cleanup - shared Chat execution runtime

Completed:

- Added `services/api/aiteamos_api/read/chat_execution_service.py` with `ChatExecutionRuntime`.
- Added `services/api/aiteamos_api/read/chat_execution_facade.py` as the non-HTTP runtime entrypoint used by LangGraph.
- Moved the durable Chat run/stream orchestration out of `chat_routes.py` into `ChatExecutionRuntime`.
- Kept the FastAPI `/messages` route as a thin call into the shared runtime.
- Kept `/messages/stream` and AG-UI compatibility paths on the same shared runtime instead of duplicating execution behavior.
- Updated `aiteamos_workbench_graph.py` to import `run_chat_message` from the execution facade instead of importing the route module directly.

Validation:

```bash
python -m py_compile services/api/aiteamos_api/read/chat_execution_service.py services/api/aiteamos_api/read/chat_execution_facade.py services/api/aiteamos_api/read/chat_routes.py services/api/aiteamos_api/agents/aiteamos_workbench_graph.py tests/test_aiteamos_workbench_graph.py
pytest tests/test_aiteamos_workbench_graph.py tests/test_file_chat_routes.py -q
```

Observed notes:

- The service boundary now owns execution dispatch, result ingestion, execution session persistence, engine-state updates, and response persistence.
- `chat_routes.py` still owns historical helper dependencies for workspace, employees, thread store, skills, and context prep. The next backend cleanup should migrate those dependency providers into service modules without changing product behavior.
- The focused backend test run passed with the same existing Graphiti/Pydantic deprecation warning.

Additional backend validation:

```bash
pytest tests/test_execution_dispatch_contract.py tests/test_runtime_executor_routes.py tests/test_file_chat_routes.py tests/test_file_memory_routes.py tests/test_file_knowledge_and_tickets.py tests/test_file_system_status_routes.py -q
```

Result: 169 passed, with the same existing Graphiti/Pydantic deprecation warning.

Follow-up validation after installing LangGraph CLI in the shared environment: 169 passed with two dependency warnings, one existing Graphiti/Pydantic warning and one Starlette `httpx2` deprecation warning.

### 2026-06-19: Track C/D Workbench state panels - direct LangGraph custom state consumption

Completed:

- Extended `WorkbenchStateBridge` in `apps/dashboard/src/pages/chat/index.tsx` to read LangGraph custom state through `useLangChainState`.
- Added `WorkbenchSnapshot` state for `active_ticket`, `employee_identity`, `ticket_binding`, `linked_assets`, `recalled_memory_refs`, `approval_requests`, `asset_candidates`, `provider_blockers`, `runtime_status`, and `workbench_panels`.
- Added a compact Workbench State panel to the right-side AITeamOS details area.
- Updated existing details-panel derived data so Workbench state takes precedence over `aiteamos_chat_response` metadata for active Ticket, Employee, Ticket binding, linked Assets, recalled Memory refs, approval requests, provider blockers, and runtime status.
- Updated Chat page tests so the LangChain runtime mock returns multiple custom state keys instead of only `aiteamos_chat_response`.

Validation:

```bash
cd apps/dashboard && npm test -- chat-page.test.tsx
cd apps/dashboard && npm run build
```

Result:

- Dashboard Vitest run: 8 test files, 58 tests passed.
- Dashboard build passed.
- Vite still reports the existing large chunk warning for the generated dashboard bundle.

Remaining gaps:

- The Chat thread itself still uses the existing assistant-ui shell rather than a fuller Agent Chat UI component extraction.
- Browser smoke against the actual Dashboard and Agent Server is now covered by `apps/dashboard/e2e/chat-workbench.spec.ts`.
- Workbench state now feeds panels, but richer inline domain cards still need to be rendered from LangGraph state/tool-call events.

### 2026-06-19: Track H local Agent Server smoke - LangGraph API runnable path

Completed:

- Added `langgraph-cli[inmem]>=0.4.30` to the Python dev extra.
- Verified `langgraph validate --config langgraph.json` succeeds with one graph.
- Started local LangGraph Agent Server at `http://127.0.0.1:2024`.
- Verified `langgraph_sdk` can discover the `aiteamos_workbench` assistant.
- Ran a real SDK stream against `aiteamos_workbench` and observed final state with `aiteamos_chat_response`, `employee_identity`, `runtime_status`, `workbench_panels`, `linked_assets`, `recalled_memory_refs`, `provider_blockers`, and `final_response`.
- Updated `scripts/dev-up.sh` so local dev starts FastAPI, LangGraph Agent Server, and Dashboard together by default.
- Updated `README.md` with Agent Server URL and manual `langgraph dev` command.
- Added `.langgraph_api/` and `.aiteamos/assets/` to `.gitignore` because Agent Server checkpoint files and runtime Asset records are local workspace state.

Validation:

```bash
langgraph --version
langgraph validate --config langgraph.json
langgraph dev --host 127.0.0.1 --port 2024 --no-reload --allow-blocking
python - <<'PY'
from langgraph_sdk import get_sync_client
client = get_sync_client(url="http://127.0.0.1:2024")
print([a.get("graph_id") for a in client.assistants.search()])
PY
```

Observed notes:

- `langgraph-cli` available in this Python 3.13 environment is `0.4.30`.
- Plain `langgraph dev` blocks on AITeamOS file-backed sync I/O such as workspace directory creation; local dev currently needs `--allow-blocking`.
- The first blocker was heavy route import through `ag_ui_langgraph`; `chat_execution_facade.py` now runs the AITeamOS execution boundary in a worker thread for non-HTTP runtimes.
- The successful smoke surfaced a real Plane Ticket backend ingestion blocker (`502`), which is correct product behavior because provider failures must be visible rather than faked.
- Installing `langgraph-cli[inmem]` in the shared Python environment introduced non-project `pip check` conflicts with unrelated packages such as Gradio and Prometheus FastAPI instrumentator. A project-local `.venv` remains the recommended setup path.

Remaining gaps:

- `--allow-blocking` is acceptable for local file-backed development, but production Agent Server compatibility requires migrating blocking workspace operations to async drivers or explicit thread boundaries.
- The smoke did not cover approval interrupt resume.

### 2026-06-19: Track C/H browser Workbench smoke - Dashboard to LangGraph Agent Server

What changed:

- Added `@playwright/test` and `apps/dashboard/e2e/chat-workbench.spec.ts`.
- Added `npm run e2e` for Dashboard browser verification.
- Installed Playwright Chromium locally for WSL/headless browser testing only; Chromium is not embedded in AITeamOS and is not part of the product bundle.
- Fixed assistant-ui package skew by aligning `@assistant-ui/react`, `@assistant-ui/react-ag-ui`, `@assistant-ui/react-langchain`, `@assistant-ui/core`, and `@assistant-ui/store` to a deduped compatible set.
- Split AITeamOS business thread ids from LangGraph runtime thread ids. The browser now lets the LangChain/LangGraph SDK mint the actual Agent Server thread id, stores the mapping in `localStorage`, and keeps the AITeamOS thread id in graph state / run config.
- Added a stable assistant-ui `InMemoryThreadListAdapter` so React rerenders do not recreate the thread adapter and disconnect the stream.
- Added a LangGraph SDK checkpoint-state hydration fallback after Agent Server command acceptance so Workbench state panels update even when the SSE terminal event is not delivered to the React store.
- Updated Workbench State UI to show `runtime_status.graph` and the current runtime node/status.

Verified:

```bash
cd apps/dashboard
npm test -- chat-page.test.tsx
npm run build
npm run e2e -- --config=playwright.config.ts
```

The Playwright smoke proves:

- Browser Chat composer sends through `@assistant-ui/react-langchain` / LangChain Frontend SDK.
- The request reaches the local LangGraph Agent Server at `http://127.0.0.1:2024`.
- LangGraph executes `aiteamos_workbench`.
- The Dashboard renders Workbench State and Latest Run from LangGraph/AITeamOS state.
- The Chat page surfaces Clara, runtime dispatch, memory recall, provenance, trace, and replay links after the run.

Remaining gaps:

- Normal browser smoke and approval-resume browser smoke now run as separate modes. The normal mode still depends on a running local Agent Server plus configured provider; the approval mode uses a deterministic fixture graph.
- Production Agent Server compatibility still needs the blocking workspace operations removed or isolated without `--allow-blocking`.

### 2026-06-19: Track E approval interrupt/resume - native LangGraph resume slice

What changed:

- Updated `services/api/aiteamos_api/agents/aiteamos_workbench_graph.py` so `aiteamos_workbench` uses a real `approval_interrupt` graph node with LangGraph native `interrupt()`.
- Added conditional routing after `update_workbench_state`: runs with structured `approval_requests` and `needs_approval` status pause through LangGraph interrupt instead of ending as plain text.
- Resume now accepts a LangGraph `Command(resume={...})`, stores `approval_resume` state, carries the same `approval_ref`, and routes back to `execute_governed_action`.
- The resumed `execute_governed_action` reuses the existing AITeamOS governed approval path by passing `approval_ref` into `run_chat_message`; durable approval status and execution remain owned by AITeamOS governance services.
- Removed the custom checkpointer from exported Agent Server graphs. Local tests can still pass an `InMemorySaver`, but LangGraph Platform / Agent Server owns persistence for deployed graphs.
- Added deterministic fixture graph `aiteamos_workbench_approval_fixture` in `langgraph.json`; it pauses on `approval-fixture-1` and resumes to a completed state with linked asset, memory ref, report/evidence, and provenance.
- Updated `apps/dashboard/src/pages/chat/index.tsx` so approval resume uses the standard LangChain/LangGraph frontend protocol command: `POST /threads/:thread_id/commands` with integer `id`, `method: "input.respond"`, interrupt id, namespace, and governed approval response payload.
- The Chat page now stores the current LangGraph runtime thread id, can hydrate pending interrupts from `threads.getState()`, and polls completed values after resume.
- Latest Run now renders the final `aiteamos_chat_response.reply`, so the user can see the resumed answer in the Chat page instead of only seeing metadata.
- Approval requests in the Workbench now expose `Review` for the AITeamOS Assets / Review Queue record and `Resume` for the LangGraph native resume command.
- Removed the previous main-path habit of treating approval as only a future composer `approval_ref`; the Workbench can now resume a real LangGraph interrupted thread without parsing assistant text.
- Updated `tests/test_aiteamos_workbench_graph.py` with a two-step interrupt/resume proof: first run returns `__interrupt__`, second run resumes the same thread with `Command(resume=...)`, and the resumed durable Chat execution receives the same `approval_ref`.
- Added a fixture graph test proving Agent Server-compatible interrupt/resume behavior without external provider credentials.
- Updated `apps/dashboard/src/__tests__/chat-page.test.tsx` so the approval button sends `input.respond`, includes protocol `id`, handles pending interrupt state, and avoids repeat-render loops when the same interrupt is observed.
- Updated `apps/dashboard/e2e/chat-workbench.spec.ts` with a deterministic browser approval-resume test using `AITEAMOS_E2E_APPROVAL_FIXTURE=1`.

Verified:

```bash
python -m py_compile services/api/aiteamos_api/agents/aiteamos_workbench_graph.py tests/test_aiteamos_workbench_graph.py
pytest tests/test_aiteamos_workbench_graph.py -q
cd apps/dashboard && npx vitest run --environment jsdom src/__tests__/chat-page.test.tsx --reporter verbose --pool forks --maxWorkers 1 --minWorkers 1
cd apps/dashboard && AITEAMOS_E2E_APPROVAL_FIXTURE=1 AITEAMOS_E2E_LANGGRAPH_URL=http://127.0.0.1:2024 AITEAMOS_E2E_DASHBOARD_URL=http://127.0.0.1:15173 AITEAMOS_E2E_BROWSER_PROJECTS=chromium npx playwright test e2e/chat-workbench.spec.ts --config=playwright.config.ts
cd apps/dashboard && npm run build
langgraph validate --config langgraph.json
pytest tests/test_aiteamos_workbench_graph.py tests/test_file_chat_routes.py tests/test_execution_dispatch_contract.py -q
git diff --check
```

Result:

- Workbench graph tests: 3 passed.
- ChatPage focused Vitest run: 3 passed.
- Browser approval-resume E2E: 1 passed, 1 normal smoke skipped in fixture mode.
- Dashboard build passed with the existing large chunk warning.
- LangGraph config validation passed.
- Focused backend regression run: 119 passed, with existing Starlette `httpx2` and Graphiti/Pydantic warnings.
- `git diff --check` passed.

Remaining gaps:

- Real dogfood still needs an approved AITeamOS approval record, a LangGraph interrupted thread, SDK `resume`, Ticket report/evidence ingestion, Asset candidate approval, Graphiti projection, and later recall in one traceable loop.
- Production Agent Server compatibility still needs blocking workspace operations removed or isolated without relying on `--allow-blocking`.
- CI should wire the deterministic fixture mode into the automated browser suite and keep the normal provider-backed smoke as an environment-gated test.

Next concrete module:

- Turn the deterministic fixture proof into a real dogfood loop: create/approve an AITeamOS approval record, resume the interrupted LangGraph thread, ingest report/evidence into the Ticket, create governed Asset candidates, project approved memory to Graphiti, and prove later recall from the same Ticket/Employee context.

### 2026-06-19: Track F/H dogfood asset-memory loop - fixture resume to Assets, Graphiti, Recall

What changed:

- Extended `services/api/aiteamos_api/agents/aiteamos_workbench_graph.py` so the deterministic approval fixture no longer emits only a display-only `memory_candidate` placeholder after resume.
- The fixture resume now calls existing `memory_service.propose_memory_from_chat_turn()` to create a real Ticket-bound MemoryCandidate in the AITeamOS Review Queue.
- The MemoryCandidate is synced through existing `asset_candidate_service.upsert_asset_candidate_from_memory_candidate()`, so Workbench `asset_candidates` now includes the real Asset candidate id, memory candidate id, asset id, provider ref, source Ticket, source report, and evidence refs.
- This keeps the boundary correct: LangGraph creates runtime state and proposes a governed candidate; AITeamOS Assets / Review Queue remain the durable source of truth; Graphiti is only used after approval/projection.
- Added `test_approval_fixture_dogfoods_assets_graphiti_and_recall()` to prove a reproducible local dogfood path:
  - Chat fixture run reaches LangGraph interrupt.
  - `Command(resume=...)` resumes the same graph thread.
  - Resume creates a real MemoryCandidate and Asset candidate.
  - Asset candidate review creates an approved AssetRecord.
  - Memory candidate approval ingests to fake Graphiti.
  - Approved AssetRecord projects to fake Graphiti.
  - `memory_service.search_memory(... include_graphiti=True)` recalls the projected durable asset through the Graphiti path.

Verified:

```bash
python -m py_compile services/api/aiteamos_api/agents/aiteamos_workbench_graph.py tests/test_aiteamos_workbench_graph.py
pytest tests/test_aiteamos_workbench_graph.py -q
pytest tests/test_file_knowledge_and_tickets.py::test_ticket_assets_include_approved_memory_recall_usage -q
pytest tests/test_aiteamos_workbench_graph.py tests/test_file_chat_routes.py tests/test_execution_dispatch_contract.py -q
langgraph validate --config langgraph.json
git diff --check
```

Result:

- Workbench graph tests: 4 passed.
- Existing Ticket/Asset/Graphiti recall regression: 1 passed.
- Focused backend regression run: 120 passed.
- LangGraph config validation passed with 2 graphs.
- `git diff --check` passed.
- Warnings remain existing dependency/runtime warnings: Graphiti/Pydantic deprecation, Starlette `httpx2` deprecation, and one existing `aiosqlite` event-loop-close warning in the dispatch contract regression.

Remaining gaps:

- The dogfood path is now clearly reproducible and proves Assets -> Graphiti -> Recall, but it is still fixture-backed rather than a full live provider run through Plane plus a real external runtime executor.
- The fixture creates MemoryCandidate and Asset candidate, then the test performs review/approval/projection. The browser flow still shows the candidate but does not yet drive Assets review and Graphiti projection from the UI.
- AITeamOS execution approval records are not yet created/approved by this fixture path; the LangGraph interrupt resume is proven, but the durable approval record loop still needs to be tied in.
- Ticket report/evidence ingestion is represented in fixture state and candidate provenance, but a live Ticket ledger write in the same dogfood loop remains the next integration step.

Next concrete module:

- Add an AITeamOS approval-record-backed dogfood path that binds the LangGraph interrupt payload to `execution_approval_service`, records review status, resumes the same graph thread, and writes the approved resume result into the Ticket ledger before proposing/reviewing Assets.

### 2026-06-19: Track E/H approval-record-backed dogfood - interrupt to Ticket ledger

What changed:

- Extended `services/api/aiteamos_api/agents/aiteamos_workbench_graph.py` so the deterministic LangGraph approval fixture writes a real `ExecutionApprovalRecord` through existing `execution_approval_service.record_execution_approval_requests()`.
- The fixture interrupt payload now carries `approval_records`, `approval_record_ref`, `source_state_snapshot_ref`, checkpoint refs, executor session refs, and the active Ticket id as structured Workbench state.
- Resume now reviews the same AITeamOS approval record through `review_execution_approval()`, marks it `approved`, and records the approval resume into the real Ticket ledger through `ticket_service.add_ticket_report()`.
- The resumed Ticket report id is injected into Workbench `runtime_status`, `ticket_report_refs`, provenance events, and the MemoryCandidate / Asset candidate provenance.
- The dogfood tests now create a real local-file Ticket first and pass that Ticket id through the graph config, avoiding display-only placeholder Ticket provenance.
- Added `.aiteamos/execution_approvals.json`, `.aiteamos/execution_ingestions.json`, `.aiteamos/execution_sessions.json`, and `.aiteamos/execution_state_snapshots/` to `.gitignore` as local derived runtime state.

Files changed in this slice:

- `.gitignore`
- `services/api/aiteamos_api/agents/aiteamos_workbench_graph.py`
- `tests/test_aiteamos_workbench_graph.py`

Verified:

```bash
python -m py_compile services/api/aiteamos_api/agents/aiteamos_workbench_graph.py tests/test_aiteamos_workbench_graph.py
pytest tests/test_aiteamos_workbench_graph.py -q
pytest tests/test_aiteamos_workbench_graph.py tests/test_file_chat_routes.py tests/test_execution_dispatch_contract.py tests/test_file_knowledge_and_tickets.py::test_ticket_assets_include_approved_memory_recall_usage -q
langgraph validate --config langgraph.json
git diff --check
```

Result:

- Workbench graph tests: 4 passed.
- Focused backend regression run: 121 passed.
- LangGraph config validation passed with 2 graphs.
- `git diff --check` passed.
- Existing warnings remain: Starlette `httpx2` deprecation, Graphiti/Pydantic deprecation, and the known `aiosqlite` event-loop-close warning in the dispatch contract regression.

Not run:

- Dashboard Vitest / build / Playwright were not rerun in this slice because no frontend files changed. The previous browser approval fixture remains the frontend coverage baseline; the next frontend-relevant slice should rerun `npm test`, `npm run build`, and the approval fixture Playwright smoke.

Remaining gaps:

- The reproducible dogfood loop now proves LangGraph interrupt -> AITeamOS approval record -> LangGraph resume -> Ticket report -> MemoryCandidate / Asset candidate -> approved AssetRecord -> Graphiti projection -> recall, but it remains deterministic fixture-backed rather than a full live Plane plus external runtime executor run.
- The browser Workbench can resume an approval and show candidates, but it does not yet drive approval record review, Assets review, Graphiti projection, and later recall from the UI as one visible operator workflow.
- Production Agent Server compatibility still needs blocking workspace operations removed or isolated without relying on `--allow-blocking`.

Next concrete module:

- Add a browser-visible Review / Projection dogfood slice: from the Workbench approval fixture, expose the approved Ticket report and Asset candidate in the UI, drive Asset review/projection through existing Assets APIs, and show recalled Graphiti-backed memory in a later Workbench run without adding a custom chat/runtime protocol.

### 2026-06-19: Track D/F/H browser-visible Asset review and Graphiti projection controls

What changed:

- Extended `apps/dashboard/src/pages/chat/index.tsx` so the Chat Workbench Latest Run panel renders structured LangGraph `asset_candidates` as AITeamOS domain cards.
- Each Asset candidate card now shows candidate id, MemoryCandidate id, approved Asset id, source Ticket id, source report id, review state, and Graphiti projection status.
- Added Workbench actions that reuse existing Assets APIs:
  - `reviewAssetCandidate()` for approving a governed Asset candidate.
  - `projectAssetRecordToGraphiti()` for projecting the approved AssetRecord to Graphiti.
- Kept the generic message thread / composer untouched; this is only an AITeamOS-specific domain panel.
- Added local UI-only candidate overrides so API action results are visible immediately without mutating LangGraph runtime state or inventing a new frontend source of truth.
- Updated `apps/dashboard/src/__tests__/chat-page.test.tsx` with an API-level proof that Chat Workbench approval/projection calls the existing Assets endpoints rather than a custom Chat endpoint.

Files changed in this slice:

- `apps/dashboard/src/pages/chat/index.tsx`
- `apps/dashboard/src/__tests__/chat-page.test.tsx`
- `plan_v6.md`

Verified:

```bash
cd apps/dashboard && npx vitest run --environment jsdom src/__tests__/chat-page.test.tsx --reporter verbose --pool forks --maxWorkers 1 --minWorkers 1
cd apps/dashboard && npm run build
git diff --check
```

Result:

- ChatPage focused Vitest run: 4 passed.
- Dashboard build passed.
- `git diff --check` passed.
- Existing Vite large chunk warning remains.

Not run:

- Playwright approval fixture smoke was not rerun in this slice because it requires the local Dashboard and LangGraph Agent Server pair to be running together. The new unit test covers the newly added Workbench Asset review/projection controls; the next browser slice should rerun fixture Playwright with a live Agent Server.
- Backend tests were not rerun after this UI-only slice; the immediately preceding backend slice passed 121 focused tests and the code here only imports existing frontend API clients.

Remaining gaps:

- The Workbench can now approve and project visible Asset candidates from the Chat side panel, but the deterministic browser E2E does not yet click through approval resume -> Asset approve -> Graphiti projection in one Playwright flow.
- The UI shows Graphiti projection status after projection, but it still relies on a later run / later state hydration to show recalled Graphiti-backed memory in the same operator story.
- The live provider-backed dogfood path still needs Plane plus external runtime executor config, and production Agent Server compatibility still needs blocking workspace operations removed or isolated without `--allow-blocking`.

Next concrete module:

- Extend `apps/dashboard/e2e/chat-workbench.spec.ts` fixture mode to click the Workbench Asset candidate approval/projection controls after LangGraph approval resume, then hydrate a later run/state that displays Graphiti-backed recall in the Chat Workbench.

### 2026-06-19: Track H browser-visible approval -> Asset review -> Graphiti projection dogfood

What changed:

- Extended `apps/dashboard/e2e/chat-workbench.spec.ts` fixture mode so the browser test creates a real local-file Ticket through existing Ticket APIs before opening Chat.
- The fixture now fills the Chat Workbench Ticket key with that real `rd-####` Ticket id, so LangGraph approval resume writes the Ticket report and downstream Asset provenance against a real Ticket instead of the placeholder `rd-approval-fixture`.
- The browser flow now clicks:
  - LangGraph approval resume through `input.respond`.
  - Workbench Asset candidate approval through the existing Assets review API.
  - Approved AssetRecord Graphiti projection through the existing Assets projection API.
- The test accepts Graphiti setup blockers as honest product behavior: Asset review must return `200 OK`; Graphiti projection may return a provider/setup blocker and the UI must show it rather than fake success.
- Added root-level `execution_approvals.json`, `execution_ingestions.json`, `execution_sessions.json`, and `execution_state_snapshots/` to `.gitignore` because approval runtime state can be written at the workspace root as well as under `.aiteamos/`.

Files changed in this slice:

- `.gitignore`
- `apps/dashboard/e2e/chat-workbench.spec.ts`
- `plan_v6.md`

Verification environment:

- Kept the existing user-facing services untouched:
  - FastAPI: `127.0.0.1:8000`
  - LangGraph: `127.0.0.1:2024`
  - Dashboard: `127.0.0.1:5173`
- Started temporary isolated services with `AITEAMOS_WORKSPACE_DIR=/tmp/aiteamos-e2e-workspace-vZNbZ7`:
  - FastAPI: `127.0.0.1:18000`
  - LangGraph: `127.0.0.1:2025`
  - Dashboard: `127.0.0.1:15173`
- Stopped the temporary services after the run.

Verified:

```bash
AITEAMOS_E2E_APPROVAL_FIXTURE=1 \
  AITEAMOS_E2E_LANGGRAPH_URL=http://127.0.0.1:2025 \
  AITEAMOS_E2E_DASHBOARD_URL=http://127.0.0.1:15173 \
  AITEAMOS_E2E_BROWSER_PROJECTS=chromium \
  npx playwright test e2e/chat-workbench.spec.ts --config=playwright.config.ts
```

Result:

- Browser approval fixture: 1 passed, 1 skipped.
- The skipped test is expected in approval-fixture mode; it is the generic non-fixture browser smoke.
- Temporary API logs confirmed:
  - `POST /api/v1/assets/candidates/.../review` returned `200 OK`.
  - `POST /api/v1/assets/records/.../project/graphiti` returned `400 Bad Request` as an honest Graphiti setup blocker.

Finding from the first failed run:

- The existing FastAPI process on `127.0.0.1:8000` returned `404 Not Found` for `/api/v1/assets/candidates`, so it was not serving the current Assets routes.
- The first browser fixture also used placeholder `rd-approval-fixture`, which did not exist as a real local Ticket; the Workbench surfaced this as `approval_resume_ticket_report_failed`.
- The final passing run used a temporary current-code API plus an API-created Ticket, which proves the fixture is now self-contained and does not depend on manually pre-seeded product data.

Remaining gaps:

- Browser E2E now proves LangGraph approval resume -> Ticket report -> Asset candidate -> Asset review -> Graphiti projection UI behavior. The second-turn recall gap from this slice is closed by the follow-up recall slice below.
- Graphiti remains a provider/setup blocker in the local E2E environment until Neo4j/Graphiti are configured for the temporary workspace.
- The live provider-backed dogfood path still needs Plane plus external runtime executor config, and production Agent Server compatibility still needs blocking workspace operations removed or isolated without `--allow-blocking`.

Next concrete module:

- Add a second browser fixture turn or backend-backed state hydration that shows the approved/projected Asset being recalled in the Chat Workbench with Ticket / Asset / Graphiti provenance visible. Completed by the follow-up recall slice below.

### 2026-06-19: Track H second-turn Asset recall evidence in Workbench

What changed:

- Added a read-only recall branch to `aiteamos_workbench_approval_fixture` in `services/api/aiteamos_api/agents/aiteamos_workbench_graph.py`.
- The recall branch is triggered by a follow-up Workbench message containing `recall` plus `asset` or `memory`, then reads approved AssetRecords and AssetCandidates through the existing Assets service layer.
- The branch returns Workbench state with approved Asset refs, recalled memory refs, Ticket provenance, Graphiti episode id when available, and an honest Graphiti setup blocker when no projection exists.
- Changed fixture MemoryCandidate / AssetCandidate proposal to use Ticket-scoped `source_run_id` and trace refs, for example `fixture-approved-resume-rd-0004`, so repeated fixture runs do not dedupe a later Ticket into an earlier Ticket asset.
- Extended backend dogfood tests to run approval -> Asset review -> Graphiti projection -> recall through the same LangGraph fixture.
- Extended browser E2E to create a fresh Chat thread, clear LangGraph thread mapping, run approval/review/projection, send a second recall message, and assert `fixture-asset-recall`, Ticket source, and Graphiti yes/no visibility.

Files changed in this slice:

- `services/api/aiteamos_api/agents/aiteamos_workbench_graph.py`
- `tests/test_aiteamos_workbench_graph.py`
- `apps/dashboard/e2e/chat-workbench.spec.ts`
- `plan_v6.md`

Verified:

```bash
python -m py_compile services/api/aiteamos_api/agents/aiteamos_workbench_graph.py tests/test_aiteamos_workbench_graph.py
pytest tests/test_aiteamos_workbench_graph.py -q
pytest tests/test_aiteamos_workbench_graph.py tests/test_file_chat_routes.py tests/test_execution_dispatch_contract.py tests/test_file_knowledge_and_tickets.py::test_ticket_assets_include_approved_memory_recall_usage -q
langgraph validate --config langgraph.json
git diff --check
cd apps/dashboard && AITEAMOS_E2E_BROWSER_PROJECTS=chromium npx playwright test e2e/chat-workbench.spec.ts --config=playwright.config.ts --list
cd apps/dashboard && AITEAMOS_E2E_APPROVAL_FIXTURE=1 AITEAMOS_E2E_LANGGRAPH_URL=http://127.0.0.1:2025 AITEAMOS_E2E_DASHBOARD_URL=http://127.0.0.1:15173 AITEAMOS_E2E_BROWSER_PROJECTS=chromium npx playwright test e2e/chat-workbench.spec.ts --config=playwright.config.ts
```

Result:

- Workbench graph tests: 4 passed.
- Focused backend regression run: 121 passed.
- LangGraph config validation passed with 2 graphs.
- Playwright fixture mode: 1 passed, 1 skipped.
- `git diff --check` passed.
- Existing warnings remain: Starlette `httpx2` deprecation and Graphiti/Pydantic deprecation.

Verification environment:

- Kept existing user-facing services untouched on `127.0.0.1:8000`, `127.0.0.1:2024`, and `127.0.0.1:5173`.
- Used temporary isolated services with `AITEAMOS_WORKSPACE_DIR=/tmp/aiteamos-e2e-workspace-SqyYvY` on API `18000`, LangGraph `2025`, and Dashboard `15173`.
- Stopped the temporary services after the run.

Remaining gaps:

- The recall proof is deterministic fixture-backed and local-file backed. A live Plane plus external executor dogfood run is still required.
- Local E2E still treats Graphiti as a setup blocker unless Neo4j/Graphiti are configured for that temporary workspace.
- Production Agent Server compatibility still needs blocking workspace operations removed or isolated without `--allow-blocking`.

Next concrete module:

- Move from deterministic fixture proof to a live provider dogfood: configure Plane/Graphiti/runtime executor for a real Ticket, then run the same Chat -> Approval -> Ticket report -> Asset review -> Graphiti projection -> Recall loop without fixture-only fake state.

### 2026-06-19: Live provider dogfood readiness check

What was checked:

- Confirmed the long-running user-facing services were left untouched:
  - FastAPI: `127.0.0.1:8000`
  - LangGraph: `127.0.0.1:2024`
  - Dashboard: `127.0.0.1:5173`
- Checked local provider ports:
  - Plane proxy: `8082`
  - Neo4j bolt/browser: `7687` / `7474`
- Checked provider configuration without printing secrets:
  - `PLANE_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, and `AITEAMOS_GRAPHITI_PASSWORD` are present.
  - `.aiteamos/graphiti.json` enables Graphiti with `bolt://localhost:7687`, user `neo4j`, and DeepSeek as the Graphiti LLM engine.
  - `.aiteamos/tickets/backend.json` selects Plane with workspace `aiteamos` and the configured project id.
- Ran read-only environment smoke:

```bash
python scripts/environment_smoke.py --include-external --workspace-dir /home/shiqiangli/projects/AITeamOS
```

Result:

- Direct LLM readiness passed.
- Local Asset / Employee registry checks passed.
- LangGraph / universal employee agent runtime checks passed.
- Plane endpoint manual check with `X-API-Key` returned `200 OK` for the configured work-items endpoint.
- The first read-only provider smoke reported a Plane external smoke failure: `Plane Ticket Backend action blocker: 502`.
- A repeat read-only provider smoke surfaced Neo4j / Graphiti authentication rate limiting: `Neo.ClientError.Security.AuthenticationRateLimit`.
- `docker ps` shows `aiteamos-neo4j` is running but `unhealthy`.

Decision:

- Do not run the live provider-backed write dogfood yet. It would create or mutate real Plane Tickets and attempt Graphiti writes while Neo4j authentication/health is currently unstable.
- The deterministic local-file dogfood remains the verified implementation proof for now.

Remaining blockers:

- Fix Neo4j / Graphiti credentials and container health, then rerun the external smoke until Graphiti read/write readiness is stable.
- Re-run Plane external smoke; if the 502 repeats, inspect Plane proxy/API logs before creating a new live dogfood Ticket.
- After both providers are stable, run the non-fixture live dogfood loop and record its Ticket / Asset / Graphiti provenance.

### 2026-06-19: Live provider readiness hardening - Graphiti password source and Plane proxy bypass

What changed:

- Updated `services/api/aiteamos_api/read/memory_service.py` so Graphiti Neo4j password resolution now supports the same local compose env used by Docker:
  - `AITEAMOS_GRAPHITI_PASSWORD`
  - `NEO4J_PASSWORD`
  - `AITEAMOS_NEO4J_PASSWORD`
- Added non-secret Graphiti backend status fields:
  - `password_env`
  - `password_env_conflict`
  - `password_env_conflict_detail`
- Added a preflight blocker in `graphiti_provider_external_smoke()` so local Neo4j password env conflicts are reported before any external Graphiti/Neo4j call is attempted. This prevents repeated wrong-password smoke attempts from pushing Neo4j into authentication rate limiting.
- Updated System Status and Provider Conformance setup labels to list all supported Neo4j password env vars.
- Updated `services/api/aiteamos_api/read/ticket_service.py` so Plane adapter requests to localhost / loopback base URLs bypass proxy env (`trust_env=False`). This fixes the observed mismatch where curl to local Plane returned `200 OK`, but httpx-based Plane smoke returned `502` because `HTTP_PROXY` was set and `NO_PROXY` was missing.
- Updated README and Docker README with the local Neo4j / Graphiti password alignment rule.

Files changed in this slice:

- `README.md`
- `docker/README.md`
- `services/api/aiteamos_api/read/memory_service.py`
- `services/api/aiteamos_api/read/provider_conformance_service.py`
- `services/api/aiteamos_api/read/system_status_routes.py`
- `services/api/aiteamos_api/read/ticket_service.py`
- `tests/test_file_memory_routes.py`
- `tests/test_file_system_status_routes.py`
- `tests/test_file_knowledge_and_tickets.py`
- `apps/dashboard/src/__tests__/system-status-page.test.tsx`
- `plan_v6.md`

Verified:

```bash
python -m py_compile services/api/aiteamos_api/read/memory_service.py services/api/aiteamos_api/read/system_status_routes.py services/api/aiteamos_api/read/provider_conformance_service.py tests/test_file_memory_routes.py tests/test_file_system_status_routes.py
pytest tests/test_file_memory_routes.py::test_graphiti_settings_accept_local_neo4j_password_env tests/test_file_memory_routes.py::test_graphiti_external_smoke_reports_local_password_env_conflict_without_provider_call tests/test_file_system_status_routes.py::test_system_status_reports_secret_health_without_settings_compat_route tests/test_file_system_status_routes.py::test_environment_smoke_script_outputs_redacted_readiness_payload tests/test_file_system_status_routes.py::test_provider_conformance_external_smoke_uses_configured_plane_and_graphiti_adapters -q
pytest tests/test_file_memory_routes.py tests/test_file_system_status_routes.py -q
npm test -- system-status-page.test.tsx
python -m py_compile services/api/aiteamos_api/read/ticket_service.py tests/test_file_knowledge_and_tickets.py
pytest tests/test_file_knowledge_and_tickets.py::test_plane_ticket_backend_bypasses_proxy_env_for_localhost_base_url tests/test_file_knowledge_and_tickets.py::test_plane_ticket_backend_smoke_create_report_transition tests/test_file_system_status_routes.py::test_provider_conformance_external_smoke_uses_configured_plane_and_graphiti_adapters -q
python scripts/environment_smoke.py --include-external --workspace-dir /home/shiqiangli/projects/AITeamOS --output /tmp/aiteamos-provider-smoke-after-plane.json
pytest tests/test_file_knowledge_and_tickets.py tests/test_file_system_status_routes.py tests/test_file_memory_routes.py -q
pytest tests/test_aiteamos_workbench_graph.py tests/test_file_chat_routes.py tests/test_execution_dispatch_contract.py tests/test_file_knowledge_and_tickets.py::test_ticket_assets_include_approved_memory_recall_usage -q
langgraph validate --config langgraph.json
git diff --check
```

Result:

- Graphiti / System Status / provider focused tests: 5 passed.
- Memory + System Status full focused group: 21 passed.
- Dashboard System Status Vitest command ran the current dashboard test set: 8 files, 59 tests passed.
- Plane focused tests: 3 passed.
- Knowledge / System Status / Memory focused group: 41 passed.
- Workbench / Chat / dispatch focused regression: 121 passed.
- LangGraph config validation passed with 2 graphs.
- `git diff --check` passed.
- Current read-only external environment smoke now reports:
  - `ticket:plane`: passed
  - `memory:graphiti`: passed
  - overall environment: warning only because optional runtime executors such as Claude Code / Cursor / OpenHands are not configured.

Observed notes:

- The earlier Plane `502` was caused by `HTTP_PROXY=http://127.0.0.1:7890` with no `NO_PROXY`; httpx routed local Plane traffic through the proxy while curl returned `200 OK` directly.
- The current `aiteamos-neo4j` container still reports Docker health `unhealthy`; health logs show `The client is unauthorized due to authentication failure.` Graphiti read smoke passes, so this appears to be local volume / healthcheck password drift rather than a current Graphiti read blocker.
- The external Graphiti smoke still emitted graphiti_core / Neo4j async index-build stderr noise (`NoneType` has no attribute `complete`) even though the structured Graphiti search check passed. Treat this as a provider-library / Neo4j compatibility warning until a real write/projection dogfood confirms stability.

Not run:

- Full Dashboard build was not rerun in this slice because production frontend code did not change; only a System Status test fixture string changed.
- Browser Playwright was not rerun because this slice changed provider readiness and backend adapter behavior, not Workbench browser behavior.
- Live provider write dogfood was not run yet. Read-only Plane and Graphiti smoke now pass, but the Neo4j container health/password drift and Graphiti stderr warning should be resolved or explicitly accepted before mutating real Plane Tickets and Graphiti memory.

Remaining gaps:

- Full live provider dogfood still needs to run without fixture-only state: Chat -> Employee -> real Plane Ticket -> approval -> Ticket report/evidence -> Asset review -> Graphiti projection -> Recall.
- Neo4j Docker health should be fixed by aligning the existing volume password with `AITEAMOS_NEO4J_PASSWORD` / `AITEAMOS_GRAPHITI_PASSWORD` or by recreating the local development volume after backup/confirmation.
- The provider dogfood runner should record the exact Plane Ticket id, LangGraph thread id, AssetRecord id, Graphiti episode id, and recall evidence in the Ticket / Assets provenance.

Next concrete module:

- Add an explicit, opt-in live provider dogfood runner or Playwright mode that reuses the existing LangGraph Workbench, Plane adapter, Assets review APIs, and Graphiti projection APIs to perform the non-fixture write loop. It must be gated behind an env flag because it mutates real Plane / Graphiti provider state.

### 2026-06-19: Track H opt-in live provider dogfood runner

What changed:

- Added `services/api/aiteamos_api/read/live_provider_dogfood_service.py`.
- Added `scripts/live_provider_dogfood.py`.
- Added `tests/test_live_provider_dogfood_service.py`.
- The runner is explicitly mutation-gated:
  - default mode is dry-run
  - live writes require `--execute`
  - live writes also require `AITEAMOS_LIVE_PROVIDER_DOGFOOD=1`
- The runner composes existing AITeamOS / LangGraph boundaries instead of creating a new agent loop:
  - read-only provider smoke through existing Provider Conformance service
  - LangGraph Agent Server / `aiteamos_workbench` for the Chat / Employee / Ticket Workbench entry
  - Ticket service / Plane adapter for provider Ticket creation or binding
  - `RuntimeExecutorSmokeService.dogfood()` for governed approval and approved runtime execution
  - Asset candidate review through existing Assets service
  - MemoryCandidate approval through existing Review Queue / Graphiti ingestion
  - AssetRecord Graphiti projection through existing Assets projection service
  - Graphiti-backed recall through existing Memory search
- The CLI dry-run no longer runs external provider smoke by default, because live Graphiti / Neo4j smoke can block on provider-library behavior. Dry-run external smoke is available with `--include-provider-smoke`; execute mode still requires provider smoke unless `--skip-provider-smoke` is explicitly set.
- Added provider smoke timeout handling at the service level for async provider smoke runners. The real CLI dry-run path is now safe by default and does not enter provider writes or external smoke.

Files changed in this slice:

- `services/api/aiteamos_api/read/live_provider_dogfood_service.py`
- `scripts/live_provider_dogfood.py`
- `tests/test_live_provider_dogfood_service.py`
- `plan_v6.md`

Verified:

```bash
python -m py_compile services/api/aiteamos_api/read/live_provider_dogfood_service.py scripts/live_provider_dogfood.py tests/test_live_provider_dogfood_service.py
pytest tests/test_live_provider_dogfood_service.py -q
python -m py_compile scripts/live_provider_dogfood.py
python scripts/live_provider_dogfood.py --workspace-dir /home/shiqiangli/projects/AITeamOS --output /tmp/aiteamos-live-dogfood-dry-run-default.json
pytest tests/test_live_provider_dogfood_service.py tests/test_file_memory_routes.py tests/test_file_system_status_routes.py tests/test_file_knowledge_and_tickets.py::test_plane_ticket_backend_bypasses_proxy_env_for_localhost_base_url -q
pytest tests/test_aiteamos_workbench_graph.py tests/test_file_chat_routes.py tests/test_execution_dispatch_contract.py tests/test_live_provider_dogfood_service.py -q
langgraph validate --config langgraph.json
git diff --check
```

Result:

- New live provider dogfood service tests: 3 passed.
- CLI default dry-run returned:
  - `status=dry_run`
  - `dry_run=true`
  - `mutation_gate.open=false`
  - anti-wheel boundary: reuses LangGraph, RuntimeExecutor, Ticket, Assets, and Graphiti services.
- Runner + Memory/System Status/Plane proxy focused regression: 25 passed.
- Workbench / Chat / dispatch / live runner focused regression: 123 passed.
- LangGraph config validation passed with 2 graphs.
- `git diff --check` passed.

Observed notes:

- A previous CLI dry-run with external provider smoke enabled hung long enough to require stopping the test process. No AITeamOS services were stopped; only the spawned `scripts/live_provider_dogfood.py` verification process was killed.
- This confirmed the runner must keep default dry-run independent from external provider smoke. External provider smoke remains available but should be treated as a provider readiness step, not a mandatory dry-run gate.
- The fake completed test proves the service composition path: Workbench state -> Ticket -> runtime dogfood MemoryCandidate -> Asset review -> memory approval -> Graphiti projection -> recall. It does not mutate real Plane / Graphiti.

Not run:

- `AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute ...` was not run yet because it mutates real Plane / Graphiti state.
- Browser Playwright was not rerun because this slice adds backend service + CLI dogfood runner only; no Workbench browser code changed.
- Full Dashboard build was not rerun because no production frontend code changed.

Remaining gaps:

- The opt-in live provider dogfood runner exists and is tested in dry-run/fake-completed mode, but the actual live write run is still not executed.
- Before executing live writes, resolve or explicitly accept:
  - Neo4j Docker healthcheck password drift
  - Graphiti / Neo4j async index-build stderr warning
  - the selected runtime executor. The default CLI executor is `local_tool`; for a true runtime mutation dogfood, pass a configured executor id such as `claude_code`, `cursor`, `openhands`, or another ready RuntimeExecutor.
- After a successful live write run, record the exact Plane Ticket id, LangGraph thread id, approval id, AssetRecord id, Graphiti episode id, and recall evidence in this plan.

Next concrete module:

- Run or browser-drive the opt-in live provider dogfood against real providers once Neo4j health and the target RuntimeExecutor are accepted/configured:

```bash
AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 \
python scripts/live_provider_dogfood.py \
  --execute \
  --workspace-dir /home/shiqiangli/projects/AITeamOS \
  --executor-id <configured-runtime-executor>
```

### 2026-06-19: Track H live dogfood execute preflight - RuntimeExecutor repo-write gate

What changed:

- Updated `services/api/aiteamos_api/read/live_provider_dogfood_service.py` so live execution now performs a selected RuntimeExecutor preflight before any provider mutation.
- The preflight blocks execution before creating a Plane Ticket when the selected executor:
  - is not registered
  - is not ready
  - lacks `repo:write` capability while `require_repo_write_executor=true`
- Updated `scripts/live_provider_dogfood.py` with `--allow-non-mutating-executor` for controlled local tests only. The default remains safe: live provider dogfood requires a ready `repo:write` RuntimeExecutor.
- Updated `tests/test_live_provider_dogfood_service.py` so:
  - dry-run reports the selected executor preflight
  - execute mode with default `local_tool` is blocked before provider smoke or Ticket creation
  - provider smoke timeout remains covered when `require_repo_write_executor=false`
  - fake-completed composition test explicitly opts into non-mutating executor mode

Current external state checked:

- RuntimeExecutor health showed:
  - `local_tool`: ready, but no `repo:write`
  - `direct_llm`: ready, answer-only, no `repo:write`
  - `universal_employee_agent`: ready, no `repo:write`
  - `langgraph`: ready, no `repo:write`
  - `claude_agent_sdk`: setup blocked, missing `ANTHROPIC_API_KEY`
  - `claude_code`: setup blocked, missing `CLAUDE_CODE_BIN`
  - `cursor`: setup blocked, missing `CURSOR_API_KEY`
  - `openhands`: setup blocked, missing `OPENHANDS_BASE_URL`
  - `opencode`: setup blocked, missing `OPENCODE_BIN`
- `aiteamos-neo4j` is still running but Docker health is `unhealthy`.
- Because no ready `repo:write` RuntimeExecutor is currently available, a true live write dogfood would not satisfy the final architecture evidence yet.

Verified:

```bash
python -m py_compile services/api/aiteamos_api/read/live_provider_dogfood_service.py scripts/live_provider_dogfood.py tests/test_live_provider_dogfood_service.py
pytest tests/test_live_provider_dogfood_service.py -q
python scripts/live_provider_dogfood.py --workspace-dir /home/shiqiangli/projects/AITeamOS --output /tmp/aiteamos-live-dogfood-dry-run-preflight.json
AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --skip-provider-smoke --workspace-dir /home/shiqiangli/projects/AITeamOS --output /tmp/aiteamos-live-dogfood-execute-preflight-blocked.json
pytest tests/test_live_provider_dogfood_service.py tests/test_aiteamos_workbench_graph.py tests/test_file_chat_routes.py tests/test_execution_dispatch_contract.py -q
pytest tests/test_live_provider_dogfood_service.py tests/test_file_memory_routes.py tests/test_file_system_status_routes.py tests/test_file_knowledge_and_tickets.py::test_plane_ticket_backend_bypasses_proxy_env_for_localhost_base_url -q
langgraph validate --config langgraph.json
git diff --check
```

Result:

- Live dogfood service tests: 4 passed.
- CLI dry-run reports:
  - `status=dry_run`
  - selected executor `local_tool`
  - blocker `runtime_executor_lacks_repo_write`
- CLI execute with `AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 --execute --skip-provider-smoke` is safely blocked before mutation:
  - result status `blocked`
  - blocker `runtime_executor_lacks_repo_write`
  - exit code `2`
- Workbench / Chat / dispatch / live runner focused regression: 124 passed.
- Runner + Memory/System Status/Plane proxy focused regression: 26 passed.
- LangGraph config validation passed with 2 graphs.
- `git diff --check` passed.

Observed notes:

- A one-off RuntimeExecutor health inspection process had to be killed after printing health results because an async sqlite/checkpointer resource kept the Python process alive. This did not affect AITeamOS services.
- The live dogfood runner now fails fast before external provider mutation when the target executor cannot produce a true repo-write dogfood.

Not run:

- Full live write dogfood was not run because no ready `repo:write` RuntimeExecutor is currently configured.
- Browser Playwright and Dashboard build were not rerun because this slice changed backend service / CLI / tests only.

Remaining gaps:

- Configure or select a ready RuntimeExecutor with `repo:write`, such as `claude_code`, `cursor`, `openhands`, `opencode`, or another real repo-write executor.
- Resolve or explicitly accept Neo4j Docker health drift before relying on live Graphiti writes as production-quality evidence.
- Then run the opt-in live provider dogfood with the configured executor and record exact provenance ids in this plan.

Next concrete module:

- Add System Status / runner visibility for live dogfood readiness so the UI can show why the live provider loop is blocked: selected executor lacks `repo:write`, external repo-write executors are setup-blocked, and Neo4j health is unhealthy.

### 2026-06-19: Track H live dogfood readiness observability - System Status and CLI

What changed:

- Added a read-only live provider dogfood readiness contract in `services/api/aiteamos_api/read/live_provider_dogfood_service.py`.
- Added `live_provider_dogfood` to `/api/v1/system-status` so System Status now reports:
  - selected executor preflight
  - whether `repo:write` is required
  - repo-write RuntimeExecutor candidates and setup blockers
  - Ticket provider prerequisite status
  - Graphiti / Memory provider prerequisite status
  - mutation gate state for opt-in live provider writes
- Added a `Live Provider Dogfood Readiness` panel to the Dashboard System Status page.
- Added `scripts/live_provider_dogfood.py --readiness` so the same read-only contract is available from CLI without mutating Plane, LangGraph, Tickets, Assets, or Graphiti.
- Added and updated tests for:
  - live dogfood readiness service behavior
  - System Status backend response
  - System Status frontend rendering

Current external state checked:

- `python scripts/live_provider_dogfood.py --readiness --workspace-dir /home/shiqiangli/projects/AITeamOS --output /tmp/aiteamos-live-dogfood-readiness.json` returned exit code `2`, which is expected while readiness is blocked.
- In the current local environment:
  - Plane Ticket backend is `ready`.
  - Graphiti Memory backend is `ready`.
  - selected executor is still `local_tool`, which lacks `repo:write`.
  - no repo-write RuntimeExecutor is currently ready.
  - repo-write candidates are setup-blocked:
    - `claude_agent_sdk`: missing `ANTHROPIC_API_KEY`
    - `claude_code`: missing `CLAUDE_CODE_BIN`
    - `cursor`: missing `CURSOR_API_KEY`
    - `opencode`: missing `OPENCODE_BIN`
    - `openhands`: missing `OPENHANDS_BASE_URL`
  - mutation gate is closed because `AITEAMOS_LIVE_PROVIDER_DOGFOOD=1` is not set for the readiness check.
  - Docker reports `aiteamos-neo4j` as `running unhealthy`.

Verified:

```bash
python -m py_compile services/api/aiteamos_api/read/live_provider_dogfood_service.py services/api/aiteamos_api/read/system_status_routes.py scripts/live_provider_dogfood.py tests/test_live_provider_dogfood_service.py tests/test_file_system_status_routes.py
pytest tests/test_live_provider_dogfood_service.py -q
pytest tests/test_file_system_status_routes.py -q
npx vitest run --environment jsdom src/__tests__/system-status-page.test.tsx
npm --prefix apps/dashboard run build
python scripts/live_provider_dogfood.py --readiness --workspace-dir /home/shiqiangli/projects/AITeamOS --output /tmp/aiteamos-live-dogfood-readiness.json
pytest tests/test_live_provider_dogfood_service.py tests/test_aiteamos_workbench_graph.py tests/test_file_chat_routes.py tests/test_execution_dispatch_contract.py -q
pytest tests/test_live_provider_dogfood_service.py tests/test_file_memory_routes.py tests/test_file_system_status_routes.py tests/test_file_knowledge_and_tickets.py::test_plane_ticket_backend_bypasses_proxy_env_for_localhost_base_url -q
langgraph validate --config langgraph.json
git diff --check
docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' aiteamos-neo4j
```

Result:

- Live dogfood service tests: 5 passed.
- System Status backend tests: 4 passed.
- System Status frontend tests: 8 passed.
- Dashboard build passed.
- Workbench / Chat / dispatch / live runner focused regression: 125 passed.
- Runner + Memory/System Status/Plane proxy focused regression: 27 passed.
- LangGraph config validation passed with 2 graphs.
- `git diff --check` passed.
- CLI readiness reports the truthful current blocker set instead of attempting a fake live loop:
  - `runtime_executor_lacks_repo_write`
  - `no_ready_repo_write_runtime_executor`
  - `live_provider_dogfood_not_confirmed`

Not run:

- Full live write dogfood was not run because no ready `repo:write` RuntimeExecutor is configured, and the opt-in mutation gate is closed.
- Browser Playwright was not run because this slice used System Status unit tests and production build; no canvas/3D/browser-only behavior was added.

Remaining gaps:

- Configure or select a ready repo-write RuntimeExecutor.
- Decide whether to fix Neo4j Docker healthcheck drift before treating Graphiti evidence as production-quality.
- Run the opt-in live provider dogfood with the configured executor and record exact Plane Ticket id, LangGraph thread id, approval id, AssetRecord id, Graphiti episode id, and recall evidence.

Anti-Wheel Audit for this slice:

- Did we hand-roll a new agent loop? No. Readiness composes RuntimeExecutor health plus existing Ticket and Graphiti provider status.
- Did we hand-roll a new monitoring system? No. The read model is embedded into existing System Status and CLI runner visibility.
- Did we bypass Ticket / Employee / Asset governance? No. The live runner still blocks before provider mutation unless repo-write RuntimeExecutor and mutation gate requirements are satisfied.
- Did we turn Docker health into app business logic? No. Docker health is recorded in the plan/CLI operator context, while the API reports provider-level readiness.

Next concrete module:

- Configure one real repo-write RuntimeExecutor path, preferably `claude_code` first if a compatible local CLI is available, then run the opt-in live provider dogfood end to end and record provenance ids.

### 2026-06-19: Track H repo-write RuntimeExecutor unblocked - Codex CLI adapter

What changed:

- Added `codex_cli` as an optional repo-write RuntimeExecutor adapter in `services/api/aiteamos_api/read/runtime_executors/codex_cli_executor.py`.
- Registered `codex_cli` in the existing `ExecutionDispatchService` and runtime executor package exports.
- Reused the existing `ExternalRuntimeExecutor` safety wrapper instead of creating a new agent loop:
  - Ticket binding remains required for repo mutation.
  - `repo:write` capability remains approval-gated.
  - patch / changed-files artifact remains required for approved repo mutation.
  - runtime test evidence remains required before completion is accepted.
  - output still normalizes into the existing `ExecutionResult` contract.
- Extended the shared external CLI wrapper with optional `{output_schema_path}` and `{output_last_message_path}` command-template placeholders.
- The Codex CLI adapter uses `codex exec --output-schema ... --output-last-message ... -`, so the mature Codex CLI owns agent execution while AITeamOS owns governance and result acceptance.
- `codex_cli` discovers `CODEX_CLI_BIN` first and falls back to `codex` on `PATH`.
- Updated live dogfood readiness so ready repo-write candidates do not show optional blank config fields as setup blockers.
- Updated System Status backend/frontend fixtures and tests so `codex_cli` appears as a ready repo-write candidate when a Codex binary is available.

Files changed in this slice:

- `services/api/aiteamos_api/read/runtime_executors/external_runtime_executor.py`
- `services/api/aiteamos_api/read/runtime_executors/codex_cli_executor.py`
- `services/api/aiteamos_api/read/runtime_executors/__init__.py`
- `services/api/aiteamos_api/read/execution_dispatch_service.py`
- `services/api/aiteamos_api/read/live_provider_dogfood_service.py`
- `tests/test_execution_dispatch_contract.py`
- `tests/test_live_provider_dogfood_service.py`
- `tests/test_file_system_status_routes.py`
- `apps/dashboard/src/__tests__/system-status-page.test.tsx`
- `plan_v6.md`

Current external state checked:

- `codex doctor` reports Codex CLI auth is configured and the local executable is available at `/home/shiqiangli/.local/bin/codex`.
- `python scripts/live_provider_dogfood.py --readiness --executor-id codex_cli --workspace-dir /home/shiqiangli/projects/AITeamOS --output /tmp/aiteamos-live-dogfood-readiness-codex-fixed.json` returned exit code `2`, expected because the live mutation gate is closed.
- The readiness summary now shows:
  - selected executor `codex_cli`
  - selected preflight `passed`
  - `repo_write_ready_count=1`
  - `codex_cli.setup_required=[]`
  - only blocker: `live_provider_dogfood_not_confirmed`
- Plane Ticket backend remains `ready`.
- Graphiti Memory backend remains `ready`.

Verified:

```bash
python -m py_compile services/api/aiteamos_api/read/runtime_executors/external_runtime_executor.py services/api/aiteamos_api/read/runtime_executors/codex_cli_executor.py services/api/aiteamos_api/read/execution_dispatch_service.py tests/test_execution_dispatch_contract.py tests/test_live_provider_dogfood_service.py tests/test_file_system_status_routes.py
pytest tests/test_execution_dispatch_contract.py::test_codex_cli_executor_uses_output_schema_contract_and_path_discovery tests/test_live_provider_dogfood_service.py::test_live_provider_dogfood_readiness_reports_codex_repo_write_candidate_and_provider_blockers -q
pytest tests/test_file_system_status_routes.py -q
npx vitest run --environment jsdom src/__tests__/system-status-page.test.tsx
pytest tests/test_runtime_executor_routes.py -q
python scripts/live_provider_dogfood.py --readiness --executor-id codex_cli --workspace-dir /home/shiqiangli/projects/AITeamOS --output /tmp/aiteamos-live-dogfood-readiness-codex-fixed.json
pytest tests/test_execution_dispatch_contract.py tests/test_runtime_executor_routes.py tests/test_live_provider_dogfood_service.py tests/test_file_system_status_routes.py -q
pytest tests/test_aiteamos_workbench_graph.py tests/test_file_chat_routes.py tests/test_execution_dispatch_contract.py -q
langgraph validate --config langgraph.json
git diff --check
```

Result:

- Codex adapter + live readiness focused tests: 2 passed.
- System Status backend tests: 4 passed.
- System Status frontend tests: 8 passed.
- RuntimeExecutor route tests: 15 passed.
- Execution / Runtime / Live readiness / System Status backend group: 103 passed.
- Workbench / Chat / dispatch focused regression: 121 passed.
- LangGraph config validation passed with 2 graphs.
- `git diff --check` passed.

Not run:

- Full live provider write dogfood was not run in this slice because it would open `AITEAMOS_LIVE_PROVIDER_DOGFOOD=1`, create or mutate real Plane / Graphiti state, and invoke a nested Codex CLI repo-write run. The repo-write RuntimeExecutor blocker is now removed; the remaining gate is an intentional live mutation confirmation.
- Dashboard build was not rerun because production frontend code did not change in this slice; only the System Status test fixture changed. The focused System Status Vitest test was rerun.

Anti-Wheel Audit for this slice:

- Did we build a new agent loop? No. `codex_cli` delegates execution to Codex CLI and reuses `ExternalRuntimeExecutor`.
- Did we invent a new result protocol? No. Codex output is constrained through Codex `--output-schema` and normalized into existing `ExecutionResult`.
- Did we bypass governance? No. Existing Ticket binding, approval, patch, evidence, and ingestion gates remain in force.
- Did we make Codex the source of AITeamOS truth? No. Codex is only a RuntimeExecutor provider; Tickets, Employees, Assets, and Graphiti projection boundaries remain AITeamOS-owned.

Next concrete module:

- Run the opt-in live provider dogfood with `--executor-id codex_cli` after deliberately opening `AITEAMOS_LIVE_PROVIDER_DOGFOOD=1`, then record the real Plane Ticket id, LangGraph thread id, approval id, Codex runtime evidence, AssetRecord id, Graphiti episode id, and recall evidence.

### 2026-06-19: Track H live provider dogfood completed - Codex CLI, Plane, Assets, Graphiti, Recall

What changed:

- Fixed `codex_cli` compatibility with the installed `codex-cli 0.137.0`:
  - removed the unsupported `--ask-for-approval` flag from the default command template;
  - kept `codex exec --sandbox workspace-write --skip-git-repo-check --output-schema ... --output-last-message ... -`;
  - kept Codex CLI as the external RuntimeExecutor provider, not an AITeamOS agent loop.
- Tightened `ExternalRuntimeExecutor` output schema for Codex structured output:
  - root and nested object schemas now use `additionalProperties: false`;
  - required structured fields force Codex output into the existing `ExecutionResult` contract instead of stdout parsing.
- Hardened RuntimeExecutor dogfood reuse:
  - dogfood MemoryCandidate dedupe now uses Ticket/report-scoped `source_run_id`;
  - repeated runs can reuse an existing completed approval record instead of re-running a long Codex smoke;
  - summary reports now expose a real `report_id` separately from `ticket_id`.
- Hardened live provider dogfood recall:
  - recall now retries with targeted approved Asset content/title/id when the default recall query misses;
  - final completion requires the projected Asset id to be returned by `source=graphiti`, not merely by local file fallback.
- Fixed local Neo4j / Graphiti provider state:
  - current shell `AITEAMOS_GRAPHITI_PASSWORD`, `NEO4J_PASSWORD`, and `AITEAMOS_NEO4J_PASSWORD` matched each other but not the old container env;
  - recreated only the Neo4j compose service with the current password env;
  - `aiteamos-neo4j` health changed from `running unhealthy` to `running healthy`;
  - Graphiti recall probes now return Graphiti results carrying the projected Asset id.

Files changed in this final slice:

- `.gitignore`
- `services/api/aiteamos_api/read/runtime_executors/codex_cli_executor.py`
- `services/api/aiteamos_api/read/runtime_executors/external_runtime_executor.py`
- `services/api/aiteamos_api/read/runtime_executor_smoke_service.py`
- `services/api/aiteamos_api/read/live_provider_dogfood_service.py`
- `tests/test_execution_dispatch_contract.py`
- `tests/test_runtime_executor_routes.py`
- `plan_v6.md`

Live dogfood evidence:

```text
CLI output: /tmp/aiteamos-live-dogfood-codex-execute-completed.json
status: completed
Plane/AITeamOS Ticket: ops-0005
Plane provider_record_id: 86146d58-bc2b-4ac7-877a-3a8bc4330656
LangGraph thread_id: 019edf2f-fc80-7051-b0ea-b2f8b2677514
Execution approval_id: approval-dogfood-codex_cli-ops-0005-1
Codex repo evidence artifact: .aiteamos/live-dogfood/ops-0005-codex-cli-approved-attempt-1.json
Approved MemoryCandidate / AssetRecord: mem-9a0726fe4121
Approved-memory Graphiti episode_id: 7ce0bc8c-cf02-438b-96e2-45c981c4199d
AssetRecord Graphiti projection episode_id: 1f75ca14-1d82-43c6-a2e9-c857f5fe8d39
Graphiti projection status: ingested
Recall result count: 10
Graphiti recall count: 10
Graphiti recalled asset_id: mem-9a0726fe4121
Blockers: []
```

The real path proven by the run:

```text
Dashboard/Chat-compatible LangGraph Workbench entry
  -> Employee context Clara / Alex
  -> real Plane-backed Ticket ops-0005
  -> governed repo-write approval approval-dogfood-codex_cli-ops-0005-1
  -> Codex CLI RuntimeExecutor repo evidence
  -> Ticket report/evidence
  -> governed MemoryCandidate / Asset candidate
  -> approved AssetRecord mem-9a0726fe4121
  -> Graphiti projection
  -> later Graphiti-backed recall of the same Asset id
```

Verified:

```bash
python -m py_compile services/api/aiteamos_api/read/runtime_executors/codex_cli_executor.py tests/test_execution_dispatch_contract.py
pytest tests/test_execution_dispatch_contract.py::test_codex_cli_executor_uses_output_schema_contract_and_path_discovery -q
python -m py_compile services/api/aiteamos_api/read/runtime_executors/external_runtime_executor.py tests/test_execution_dispatch_contract.py
pytest tests/test_execution_dispatch_contract.py::test_codex_cli_executor_uses_output_schema_contract_and_path_discovery -q
python -m py_compile services/api/aiteamos_api/read/runtime_executor_smoke_service.py tests/test_runtime_executor_routes.py
pytest tests/test_runtime_executor_routes.py::test_runtime_dogfood_harness_creates_ticket_approval_and_ingests_approved_run -q
python -m py_compile services/api/aiteamos_api/read/live_provider_dogfood_service.py tests/test_live_provider_dogfood_service.py
pytest tests/test_live_provider_dogfood_service.py::test_live_provider_dogfood_composes_workbench_assets_graphiti_and_recall -q
pytest tests/test_execution_dispatch_contract.py tests/test_runtime_executor_routes.py tests/test_live_provider_dogfood_service.py tests/test_file_system_status_routes.py -q
pytest tests/test_aiteamos_workbench_graph.py tests/test_file_chat_routes.py tests/test_execution_dispatch_contract.py tests/test_runtime_executor_routes.py tests/test_live_provider_dogfood_service.py -q
npm --prefix apps/dashboard run build
npx vitest run --environment jsdom src/__tests__/chat-page.test.tsx src/__tests__/system-status-page.test.tsx
langgraph validate --config langgraph.json
git diff --check
docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' aiteamos-neo4j
```

Result:

- Codex adapter focused test: 1 passed.
- Runtime dogfood repeated-approval test: 1 passed.
- Live provider dogfood fake Graphiti composition test: 1 passed.
- Execution / Runtime / Live / System Status backend group: 103 passed.
- Workbench / Chat / Execution / Runtime / Live backend group: 141 passed.
- Dashboard build passed with the existing Vite large chunk warning.
- Chat + System Status Vitest: 12 passed.
- LangGraph config validation passed with 2 graphs.
- `git diff --check` passed.
- Neo4j Docker health is now `running healthy`.

Observed notes:

- The first live write attempt created the real Plane Ticket but exposed a Codex CLI template mismatch.
- The second attempt exposed Codex strict schema requirements.
- The first successful Codex approved run created repo evidence but was blocked by MemoryCandidate dedupe, which is now fixed.
- Repeated live attempts showed why dogfood must reuse completed approval evidence after downstream failures instead of repeatedly invoking long repo-write runtimes.
- Graphiti/Neo4j was a real external provider blocker until the container was recreated with the current password env. The final run did not fake recall; it completed only after Graphiti returned the projected Asset id.
- `.aiteamos/live-dogfood/`, `.aiteamos/execution_artifacts.json`, and root `execution_artifacts.json` are now ignored as local derived runtime state.

Not run:

- Playwright browser smoke was not rerun in this final backend/provider slice. The deterministic browser approval / Asset review / projection / recall fixture had passed earlier, and this slice changed RuntimeExecutor, live runner, Graphiti provider health, and tests rather than production browser code.

Remaining post-completion hardening:

- Production Agent Server compatibility should still remove or isolate blocking file-backed operations without relying on local `--allow-blocking`.
- The live dogfood runner can be made less noisy by suppressing Graphiti provider library stderr from index-building background tasks.
- Codex CLI runtime prompts can be shortened further so repeated fresh live runs are faster, though the completed-approval reuse path now prevents unnecessary reruns after downstream failures.

Anti-Wheel Audit for completion:

- Did we hand-roll a new agent loop? No. Chat execution stays in LangGraph / Agent Server compatible graph, and repo work is delegated to Codex CLI RuntimeExecutor.
- Did we invent a new streaming protocol? No. The Chat page remains LangChain / assistant-ui based; this slice did not add Chat streaming glue.
- Did we bypass Ticket / Employee / Asset governance? No. The live path is bound to Plane Ticket `ops-0005`, fixed Employees, approval record, Ticket report/evidence, Review Queue, approved AssetRecord, and Graphiti projection.
- Did we use LangGraph store as durable memory? No. Durable memory is Asset/Review-backed; Graphiti is projection and recall.
- Did AG-UI return to the main Chat path? No. AG-UI remains optional compatibility only.
- Did route handlers gain orchestration logic? No. The changes are in RuntimeExecutor, live dogfood service, and provider/runtime tests.

Completion status:

- `plan_v6` completion criteria are met for the local/live provider environment: Chat is LangGraph-native, the frontend runtime is LangChain/assistant-ui based, Ticket / Employees / Assets / Governance remain product truth, LangGraph owns execution/checkpoint/interrupt/resume shape, durable memory remains Assets/Graphiti-backed, AG-UI is optional, and one real dogfood run proves Chat -> Employee -> Ticket -> Approval -> Assets -> Graphiti -> Recall.

## 12. Tests and Verification

Backend tests:

```bash
pytest tests/test_execution_dispatch_contract.py \
  tests/test_runtime_executor_routes.py \
  tests/test_file_chat_routes.py \
  tests/test_file_memory_routes.py \
  tests/test_file_knowledge_and_tickets.py \
  tests/test_file_system_status_routes.py -q
```

Frontend tests:

```bash
cd apps/dashboard
npm test -- chat-page.test.tsx assets-page.test.tsx employees-page.test.tsx tickets-page.test.tsx system-status-page.test.tsx
npm run build
```

Workbench-specific tests to add:

- renders LangChain SDK messages and tool calls
- renders custom state active Ticket
- renders selected Employee identity
- renders approval interrupt card
- resumes from approval
- shows memory refs and asset candidates
- deep-links to Ticket / Employee / Assets / Runtime Replay
- shows provider blocker instead of fake success

Manual verification:

- Chat Workbench loads without AG-UI main path.
- A new thread can be created and rejoined.
- Tool-call state is visible while streaming.
- Interrupt state is visible and actionable.
- Ticket / Employee / Assets panels update without parsing message text.

## 13. Anti-Wheel Audit

Before calling the implementation done, answer these checks:

- Did we hand-roll generic streaming state that LangChain Frontend SDK already provides?
- Did we hand-roll message thread / composer / tool-call UI that Agent Chat UI or assistant-ui already provides?
- Did we implement a custom agent loop instead of LangGraph?
- Did we store durable memory directly from chat text instead of Assets Review Queue?
- Did AG-UI remain in the primary path without a clear reason?
- Did any provider bypass AITeamOS Ticket / Employee / Asset governance?
- Did Chat route grow new orchestration logic that belongs in the graph?

If any answer is yes, the implementation violates `plan_v6`.

## 14. Out of Scope

Do not do these as part of `plan_v6` unless explicitly revisited:

- Rebuild Tickets / Assets / Employees pages as generic Chat UI.
- Replace Graphiti with LangGraph store.
- Make LangSmith required for local development.
- Make Agent Server the source of AITeamOS product truth.
- Keep old AG-UI Chat behavior for compatibility at the cost of final architecture.
- Create a new AITeamOS-specific generic agent framework.
- Create a new memory database when Assets + Graphiti already cover the boundary.

## 15. Completion Definition

`plan_v6` is complete when:

- Chat is a LangGraph-native Agent Workbench, not the old self-built Chat page.
- The primary frontend runtime is LangChain Frontend SDK or a clearly compatible LangGraph-native runtime.
- Agent Chat UI / assistant-ui provide the generic Chat interaction primitives.
- Ticket / Employees / Assets / Governance remain the visible product core.
- LangGraph owns agent execution, interrupt, checkpoint, resume, and handoff orchestration.
- LangGraph runtime memory is separated from AITeamOS durable Assets memory.
- Graphiti remains an approved Asset projection and recall provider.
- AG-UI is optional compatibility, not the main Chat path.
- A real dogfood run proves Chat -> Employee -> Ticket -> Approval -> Assets -> Graphiti -> Recall.

## 16. Reusable Execution Prompt

Use this prompt for implementation runs:

```text
You are working in /home/shiqiangli/projects/AITeamOS.

Read plan_v6.md first and treat it as the active product and architecture plan. plan_v5.md is historical context only.

Core principle:
Keep AITeamOS Ticket / Employees / Assets / Governance as the product source of truth. Reuse mature LangGraph / LangChain / Agent Chat UI / assistant-ui capabilities for everything else. Do not rebuild generic Chat UI, generic agent loop, generic streaming protocol, generic memory store, or generic runtime observability.

Target:
Directly rebuild Chat as a LangGraph-native Agent Workbench:
- Agent Chat UI is the page blueprint.
- LangChain Frontend SDK is the frontend runtime.
- assistant-ui is the component reuse source.
- LangGraph is the execution runtime.
- AITeamOS Ticket / Employees / Assets / Governance are the only durable product core.
- AG-UI is optional compatibility only.

Execution rules:
1. Inspect current git status and preserve unrelated user changes.
2. Do not continue extending the current Chat page as a custom generic chat implementation.
3. Move orchestration out of route handlers and into LangGraph graph/runtime modules.
4. Prefer LangGraph server / Agent Server compatible APIs and LangChain Frontend SDK over custom event protocols.
5. Build custom UI only for AITeamOS-specific cards and panels: Ticket, Employee, Assets, Approval, Provenance, Memory, Provider blockers.
6. Keep durable memory writes behind Asset candidates, Review Queue, approved AssetRecord, and Graphiti projection.
7. Keep LangGraph checkpointer/store for runtime continuity only.
8. Validate with focused backend tests, frontend tests, and npm build.
9. Before finishing, run the Anti-Wheel Audit in plan_v6.md and report any remaining violations.

If the whole plan cannot be completed in one run, complete the highest-value verifiable slice that moves the main Chat path toward LangGraph-native Agent Workbench, then update plan_v6.md with exact status, tests, blockers, and next concrete file/module.
```
