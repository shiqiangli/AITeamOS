# AITeamOS plan_v5: From Runtime MVP to Autonomous AI Team OS

> Superseded for Chat / frontend runtime / Agent Workbench decisions by `plan_v6.md` on 2026-06-19. Keep this file as historical implementation context and runtime / assets / provider evidence; use `plan_v6.md` as the active plan for the direct LangGraph-native Chat rebuild.

状态：下一步实现计划  
日期：2026-06-14  
目标：在 `plan_v4` 已完成 LangGraph Universal Employee Agent Loop MVP 的基础上，把 AITeamOS 推进到最终目标：以 Ticket 流转为核心、Employees 像真实成员一样协作、Assets 成为长期组织记忆、LangGraph / 商业 Agent Runtime 承担通用 agent loop，AITeamOS 专注治理、资产、团队运行边界和供应商适配。

## 0. 最终目标基线

AITeamOS 的最终目标是做成一个以 Ticket 流转为核心的 AI Team Operating System：

- Employees 像真实成员一样拥有固定身份、能力标签、性格标签、权限边界、工作历史、技能资产和记忆范围。
- Tickets 是所有成员协作、交接、汇报、验证、审批、阻塞处理和沉淀结论的主通道。
- Assets 是系统最重要的长期资产层，Memory、Docs、Skills、Tooling calls、解决方案、建议、复盘、验证结果、settleoff / closeout 都以可审计 provenance 进入资产体系。
- Ticket、Employee、Assets 都支持外部供应商或自研实现，例如 Plane、Graphiti、本地轻量实现等。
- AITeamOS 不自研通用 Agent；通用 chat、agent loop、tool use、handoff、checkpoint、human approval、interrupt / resume 优先复用 LangGraph 或商业 Agent Runtime。
- LangGraph / LangSmith 已有的 Studio、Agent Chat UI、frontend SDK、trace、checkpoint、thread、assistant、memory、interrupt / resume、time travel、tool-call visualization 等能力，默认采用接入、嵌入、deep-link 或 SDK 方式复用；AITeamOS Dashboard 只做 Ticket / Employee / Asset / Approval / Provider governance 等领域 UI，不复制通用 graph IDE / agent chat / runtime observability。
- Chat route 只负责入口、request parsing、SSE / AG-UI bridge、response formatting；所有上下文编排、工具调用、Employee handoff、checkpoint、approval、resume 都进入 runtime / LangGraph 图。

## 1. v4 已完成状态

`plan_v4` 已经把 AITeamOS 从 Runtime-first 骨架推进到可验证的 LangGraph Universal Employee Agent Loop MVP：

- 普通 Chat 默认进入 `UniversalEmployeeAgentExecutor`。
- `ExecutionRequest` / `ExecutionResult` / `ExecutionEvent` 成为 runtime contract。
- `ExecutionContextService` 产出 `universal_context.v1`，包含 Employee、Ticket、Assets、Memory、backend status 和 provenance。
- LangGraph read-only tools 已能读取 tickets、assets、memory、employee context、system status。
- LangGraph write 类动作通过 governed artifacts 输出，由 `ExecutionResultIngestionService` 写回 Ticket / report / validation / handoff。
- Clara 可产生 governed Employee handoff artifact，把 Ticket 交给 Alex / Peter 等固定 Employee。
- Runtime approval records、execution sessions、checkpoint refs、compact tool events、Ticket / Memory / Context refs 已可在后端和 Dashboard Runtime Executors 面板中看到。
- 相关验证已通过：
  - `pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py tests/test_runtime_executor_routes.py`
  - `cd apps/dashboard && npm run build`

## 2. 与最终目标的核心差距

v4 是正确骨架，但还不是最终形态。主要差距：

1. **Approval 还不是 LangGraph interrupt / resume。**  
   当前是 `approval_request` + approved-run redispatch；长期目标是 graph node 原生中断、审批后恢复同一个 checkpoint state。

2. **Replay 还是 compact 视图。**  
   当前能看到 session、checkpoint、compact tool event 名称和 refs；长期目标是完整 timeline、payload、state diff、artifacts、evidence、context refs、memory refs、Ticket refs 可审计复盘。

3. **Assets 还不是统一长期资产生命周期。**  
   Memory、Docs、Skills、Tooling calls、solutions、suggestions、validation、closeout 仍散在多个服务里；长期目标是统一 Asset Registry + Candidate + Review + Relationship + Provider Projection。

4. **Employee 还不是完整“类人成员”。**  
   固定身份和 handoff 已有雏形，但 personality tags、skill ownership、memory scope、work history、performance feedback、permission boundary 还没形成完整系统。

5. **Autonomous loop 还不是 Ticket-native 长任务循环。**  
   当前是单次 request 的 runtime graph；长期目标是 Ticket 状态驱动的 plan -> execute -> report -> validate -> learn -> continue / block loop。

6. **供应商适配还需要产品级 contract。**  
   Plane / Graphiti / commercial agent runtime 已有入口或配置，但缺少统一 adapter conformance、端到端 smoke 和生产级 fallback。

7. **“越用越聪明”还没完全闭环。**  
   Memory candidate、recall、review 已有基础，但还需要 usefulness feedback、validated resolution -> durable memory、skill promotion、asset relationship graph 和 retrieval evaluation。

## 3. v5 架构目标

v5 要把 v4 的 MVP runtime 变成可持续运行的 AI Team OS：

```text
Human / Chat
  -> Clara / selected Employee
  -> ExecutionRequest
  -> UniversalEmployeeAgentExecutor
  -> LangGraph Ticket-native loop
      -> load universal context
      -> retrieve Employee / Ticket / Assets / Memory / Docs / Skills
      -> plan next step
      -> use governed read/write tools
      -> interrupt for approval when needed
      -> resume from checkpoint after approval
      -> handoff to fixed Employee when needed
      -> write reports/evidence/validation through ingestion
      -> propose durable Assets / Memory / Skill updates
      -> stop when Ticket done, blocked, or human decision needed
  -> ExecutionResult / session / replay timeline
  -> Ticket ledger / Employee ledger / Asset registry / Memory graph / Review queue
```

边界原则：

- Agent loop 由 LangGraph / commercial runtime 承担，AITeamOS 不在 Chat route 自研 generic agent。
- 所有写操作通过 AITeamOS governed artifacts 和 ingestion service。
- 外部供应商只能挂在 adapter 后面，不改变 AITeamOS 领域模型。
- Ticket 是协作事实主线，Assets 是长期组织资产，Employee 是固定身份和权限主体。

## 4. Target Contracts

### 4.1 ExecutionSession v2

```text
session_key
employee_id
thread_id
ticket_id
executor_id
executor_session_ref
checkpoint_ref
status
current_graph_node
approval_refs
ticket_refs
memory_refs
asset_refs
context_refs
tool_events
artifacts
evidence_refs
state_snapshot_ref
trace_ref
created_at
updated_at
```

要求：

- 能从 session 回放一次 run 的 timeline。
- 能从 session 找到审批、Ticket、Memory、Assets、trace。
- 能安全展示，不泄露 secret。

### 4.2 Approval v2

```text
approval_id
status
kind
required_capability
risk_level
reason
proposed_action
source_request
source_state_ref
checkpoint_ref
executor_session_ref
ticket_id
employee_id
reviewer_employee_id
review_reason
resume_result
run_history
```

要求：

- approval block 不丢 graph state。
- approval approved 后优先 resume checkpoint，而不是重新构造近似请求。
- rejected 后写入 Ticket / Employee ledger，说明拒绝原因和下一步。

### 4.3 Asset v2

```text
asset_id
asset_type
title
content_ref
status
scope_kind
scope_ref
owner_employee_id
source_kind
source_ref
provenance
provider
provider_ref
relationships
review_state
usefulness_stats
created_at
updated_at
```

Asset types:

- memory
- doc
- skill
- tool_call
- solution
- suggestion
- decision
- validation_result
- ticket_closeout
- employee_profile_summary
- capability

要求：

- Memory 是 Asset 的一种，不是独立孤岛。
- Tool call 和 solution 也能成为可审计资产。
- Graphiti 是资产图 / memory projection provider，不是唯一事实源。

### 4.4 Employee v2

```text
employee_id
display_name
role
personality_tags
capability_tags
skill_refs
memory_scopes
permission_policy
preferred_runtime
work_history_refs
handoff_policy
quality_feedback
current_load
```

要求：

- Employee 是固定身份，不是临时 prompt persona。
- Employee 的 skill、memory、work history 都能被 LangGraph 自动检索。
- Employee 的权限边界决定它能调用哪些 tools、能提出哪些 artifacts、需要哪些 approval。

## 5. Phase G: LangGraph Approval Interrupt / Resume

目标：把当前 approval request + redispatch 升级为真正的 graph interrupt / resume。

任务：

1. 在 `UniversalEmployeeAgentExecutor` 图中新增一等节点：
   - `governance_gate`
   - `request_approval_interrupt`
   - `resume_after_approval`
2. approval request 必须保存：
   - `checkpoint_ref`
   - `executor_session_ref`
   - `source_state_ref`
   - `current_graph_node`
   - `proposed_action`
3. `ExecutionApprovalRunService` 优先从 checkpoint / state 恢复，而不是只重建 `ExecutionRequest`。
4. rejected approval 写回 Ticket report 和 Employee work ledger。
5. Dashboard Review Queue 支持 approve / reject / resume，并显示风险、能力、Ticket 和 checkpoint。

验收：

- 一个 repo mutation run 被 approval block 后，session 中保留 checkpoint 和 current node。
- approve 后从同一 checkpoint resume，run history 能看到 resumed result。
- reject 后 Ticket 中出现 rejected report，且不会执行外部 mutation。
- Chat route 不新增 agent loop。

建议测试：

```bash
pytest tests/test_execution_dispatch_contract.py::test_langgraph_interrupt_approval_preserves_checkpoint
pytest tests/test_runtime_executor_routes.py::test_runtime_approval_resume_uses_checkpoint_state
cd apps/dashboard && npm test -- settings-page.test.tsx
```

### 2026-06-18: Phase G slice - approval interrupt metadata and governed resume refs

已完成：

- `UniversalEmployeeAgentExecutor` / `LangGraphExecutor` 新增 Phase G 一等节点：
  - `governance_gate`
  - `request_approval_interrupt`
  - `resume_after_approval`
- Chat 中 `implement_ticket` + 外部 runtime 选择现在先进入 Universal Employee Agent，而不是直接绕过 LangGraph：
  - `selected_executor=universal_employee_agent`
  - `requested_runtime_executor=claude_code / cursor / openhands / opencode ...`
- LangGraph approval interrupt 会输出 governed approval request：
  - `checkpoint_ref`
  - `executor_session_ref`
  - `source_state_ref`
  - `current_graph_node`
  - `proposed_action`
  - `risk_level`
- `ExecutionApprovalRecord` 扩展到 approval v2 metadata：
  - `risk_level`
  - `proposed_action`
  - `source_state_ref`
  - `current_graph_node`
  - `checkpoint_ref`
  - `executor_session_ref`
  - `resume_result`
- `ExecutionApprovalRunService` approved run 会把 resume refs 写入 `trace_context`：
  - `resume_from_checkpoint_ref`
  - `resume_from_executor_session_ref`
  - `source_state_ref`
  - `resume_graph_node`
  - `approval_resume`
- `execution_sessions.json` 现在记录：
  - `current_graph_node`
  - `source_state_ref`
- 外部 RuntimeExecutor 的直接 approval blocker 也补齐 v2 metadata。
- Dashboard Runtime Executors Review Queue 支持最小治理操作：
  - Approve
  - Reject
  - Resume
  - 显示 risk、checkpoint、state ref。
- rejected approval 会写回 `approval_rejected` Ticket report，并进入 reviewer Employee work ledger。

验证：

```bash
pytest tests/test_execution_dispatch_contract.py::test_chat_governance_routes_ticket_implementation_to_external_runtime_approval \
  tests/test_runtime_executor_routes.py::test_approved_claude_code_runtime_run_uses_approval_ref_and_ingests_repo_mutation

pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py tests/test_runtime_executor_routes.py

cd apps/dashboard && npm test

cd apps/dashboard && npm run build
```

结果：

- `2 passed, 1 warning`
- `100 passed, 1 warning`
- `28 passed`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

### 2026-06-18: Phase G slice - checkpoint state snapshot resume source

已完成：

- `execution_session_store.py` 新增 approval resume state snapshot：
  - `execution_state_snapshots_dir`
  - `save_execution_state_snapshot`
  - `load_execution_state_snapshot`
- 每个 governed approval request 现在会把 redacted graph state 写到 workspace 下的 `execution_state_snapshots/*.json`，并在 approval record 中保存：
  - `source_state_snapshot_ref`
  - `source_state_ref`
  - `checkpoint_ref`
  - `executor_session_ref`
  - `current_graph_node`
- snapshot payload 使用 `execution_state_snapshot.v1` schema，并包含 redacted：
  - source execution request
  - current graph node
  - approval interrupt
  - tool events
  - errors
  - learning delta
- approved run 会优先读取 snapshot，并把恢复来源写入 `trace_context`：
  - `resume_source=checkpoint_state`
  - `resume_snapshot_schema=execution_state_snapshot.v1`
  - `resume_source_state_snapshot_ref`
- approved run 的 `task_context.resume_checkpoint_state` 会收到 compact snapshot，用于后续接入 LangGraph native `Command(resume=...)` / checkpointer replay。
- `run_history` 和 `resume_result` 现在记录 `resume_source` 与 `source_state_snapshot_ref`，让 Review Queue / Replay 可以区分是 snapshot-backed resume 还是 fallback checkpoint-ref redispatch。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/execution_approval_service.py services/api/aiteamos_api/read/execution_session_store.py

pytest tests/test_runtime_executor_routes.py::test_approved_claude_code_runtime_run_uses_approval_ref_and_ingests_repo_mutation \
  tests/test_execution_dispatch_contract.py::test_chat_governance_routes_ticket_implementation_to_external_runtime_approval -q

pytest tests/test_runtime_executor_routes.py tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py -q
```

结果：

- `2 passed, 1 warning`
- `103 passed, 1 warning`

### 2026-06-18: Phase G slice - native LangGraph interrupt / Command resume

已完成：

- `LangGraphExecutor` 接入 workspace-aware checkpointer：
  - 优先使用 `AsyncSqliteSaver`
  - checkpoint path: `workspace_dir/langgraph/{executor_id}_checkpoints.sqlite`
  - 依赖缺失时回退 `InMemorySaver`
- `LangGraphExecutor` 的 repo-write governance gate 现在使用 LangGraph 原生 `interrupt(approval_payload)`：
  - 首次执行返回 `needs_approval`
  - approval payload 仍进入 AITeamOS governed approval record
  - `learning_delta.native_interrupts` 和 `learning_delta.checkpoint` 暴露 native checkpoint 信息
- approved LangGraph request 会在存在 pending interrupt 时使用 `Command(resume=...)`，并从原始 `source_request_id` 对应的 thread checkpoint 继续。
- resume 后图内写入：
  - `langgraph.approval.resume_command`
  - `langgraph.approval.resumed`
  - `external_runtime_resume_request` governed artifact
- Health / usage 暴露 checkpoint mode，便于后续 System Status / Replay 判断当前 runtime 是否真正 checkpoint-backed。

验证：

```bash
pytest tests/test_execution_dispatch_contract.py::test_langgraph_executor_native_interrupt_resumes_from_checkpoint \
  tests/test_execution_dispatch_contract.py::test_chat_governance_routes_ticket_implementation_to_external_runtime_approval \
  tests/test_runtime_executor_routes.py::test_approved_claude_code_runtime_run_uses_approval_ref_and_ingests_repo_mutation -q

pytest tests/test_runtime_executor_routes.py tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py -q
```

结果：

- `3 passed, 1 warning`
- `104 passed, 2 warnings`

仍未完成：

- LangGraphExecutor 本体已经支持 native interrupt / `Command(resume=...)`。
- approved external runtime run 仍通过 AITeamOS approval run service dispatch 到对应商业 / CLI runtime；下一步要把 native resume ack、external runtime execution、snapshot 和 ingestion 串成同一条 Replay timeline。
- 下一步进入 Phase H：实现 full replay timeline，让 checkpoint snapshot、native interrupt、approval review、external runtime result、Ticket report 和 Asset candidate 可以在同一个 session 里审计复盘。

## 6. Phase H: Full Replay Timeline

目标：让每一次 run 都可复盘，而不是只看 compact metadata。

任务：

1. 新增 execution replay service：
   - load session
   - load trace jsonl
   - load tool events
   - load artifacts / evidence
   - load approval records
   - load related Ticket / Memory / Asset refs
2. 新增 API：
   - `GET /api/v1/runtime-executors/sessions/{session_key}`
   - `GET /api/v1/runtime-executors/sessions/{session_key}/timeline`
3. Dashboard 新增 Replay detail view：
   - Timeline
   - Tool events
   - Context refs
   - Memory refs
   - Ticket refs
   - Artifacts / Evidence
   - Approval / Resume history
4. Replay payload 做 redaction：
   - secret
   - API key
   - raw provider auth headers

验收：

- 从 Runtime Executors 面板点开一个 session 能看到完整 timeline。
- 每个 tool event 能看到 input summary、output refs、provenance、errors。
- 能从 replay 跳转到 Ticket、Employee、Asset / Memory 页面。

建议测试：

```bash
pytest tests/test_runtime_executor_routes.py::test_runtime_session_timeline_returns_tool_events_and_refs
cd apps/dashboard && npm test -- settings-page.test.tsx
```

### 2026-06-18: Phase H backend slice - execution replay API

已完成：

- 新增 `ExecutionReplayService`，从 `execution_sessions.json` 关联读取：
  - session / checkpoint / current graph node
  - execution artifacts / evidence
  - approval records
  - trace jsonl events
  - compact tool events、Ticket refs、Memory refs、Context refs
- 新增后端 API：
  - `GET /api/v1/runtime-executors/sessions/{session_key}`
  - `GET /api/v1/runtime-executors/sessions/{session_key}/timeline`
- replay payload 会递归脱敏常见 secret 字段：
  - `api_key`
  - `authorization`
  - `token`
  - `secret`
  - `password`
- timeline 现在包含 session、tool event、artifact、evidence、approval、trace event，并保持稳定 index。
- session 不存在时返回 404。

验证：

```bash
pytest tests/test_runtime_executor_routes.py::test_runtime_execution_sessions_list_checkpoint_and_replay_refs -q

pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py tests/test_runtime_executor_routes.py
```

结果：

- `1 passed, 1 warning`
- `100 passed, 1 warning`

仍未完成：

- Dashboard Replay detail view 见下方 Phase H dashboard slice。
- Timeline 目前是 redacted replay view，还不是完整 LangGraph state diff 级别回放。
- Approval resume 仍是携带 checkpoint/state refs 的 governed redispatch，还不是 LangGraph 原生 checkpoint state replay。

### 2026-06-18: Phase H dashboard slice - Runtime Executors replay detail

已完成：

- Dashboard `runtimeExecutors` API 增加 replay 类型和 fetch helper：
  - `RuntimeExecutionReplayResponse`
  - `RuntimeExecutionTimelineResponse`
  - `getRuntimeExecutionSessionReplay`
  - `getRuntimeExecutionSessionTimeline`
- Runtime Executors 的 Execution Sessions 列表现在每条 session 可点击 `Replay`。
- Replay detail 在 Settings 面板内原地展示：
  - session key、checkpoint、graph node、trace
  - timeline event count
  - artifact / evidence count
  - session / tool event / artifact / evidence / approval / trace timeline
  - redacted artifacts、evidence、approval、trace preview
- Settings 页面测试覆盖：
  - encoded `session_key` replay endpoint
  - timeline event 展示
  - artifact / evidence 展示
  - redacted payload 展示

验证：

```bash
cd apps/dashboard && npm test -- settings-page.test.tsx

cd apps/dashboard && npm run build
```

结果：

- `28 passed`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

Phase H 仍未完成：

- Replay detail 目前是 Settings 内联诊断面板，后续可以升级为独立 route-backed detail surface。
- Timeline 还不是完整 LangGraph state diff。
- Approval resume 还不是 LangGraph 原生 checkpoint state replay。

### 2026-06-18: Phase H slice - approval snapshot and run-history replay

已完成：

- `ExecutionReplayService` 的 replay payload 新增 `state_snapshots`：
  - 通过 approval 的 `source_state_ref` / `source_state_snapshot_ref` 读取 redacted `execution_state_snapshot.v1`
  - 保留 `checkpoint_ref`、`executor_session_ref`、`current_graph_node`、`approval_request`、`graph_state`
- Replay timeline 新增两类一等事件：
  - `execution.state_snapshot`
  - `approval.run.<status>`
- `approval.run.<status>` timeline item 会携带：
  - `approval_id`
  - `run_request_id`
  - `checkpoint_ref`
  - `resume_source`
  - `source_state_snapshot_ref`
- Runtime Executors replay response model 增加 `state_snapshots`。
- Dashboard Runtime Executors Replay Detail 显示 state snapshot count，并在 redacted payload preview 中展示 `state_snapshots`。
- Dashboard replay timeline 现在能显示：
  - native / governed state snapshot
  - approval approved-run history
  - artifact / evidence / trace events

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/execution_replay_service.py services/api/aiteamos_api/read/runtime_executor_routes.py tests/test_runtime_executor_routes.py

pytest tests/test_runtime_executor_routes.py::test_approved_claude_code_runtime_run_uses_approval_ref_and_ingests_repo_mutation -q

pytest tests/test_runtime_executor_routes.py::test_runtime_execution_sessions_list_checkpoint_and_replay_refs \
  tests/test_runtime_executor_routes.py::test_approved_claude_code_runtime_run_uses_approval_ref_and_ingests_repo_mutation \
  tests/test_execution_dispatch_contract.py::test_chat_governance_routes_ticket_implementation_to_external_runtime_approval -q

pytest tests/test_runtime_executor_routes.py tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py -q

cd apps/dashboard && npm test -- settings-page.test.tsx

cd apps/dashboard && npm run build
```

结果：

- `1 passed, 1 warning`
- `3 passed, 1 warning`
- `104 passed, 2 warnings`
- Dashboard tests: `29 passed`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

Phase H 仍未完成：

- Replay detail 仍在 Settings 内联诊断面板，后续可升级为 route-backed detail surface。
- Timeline 已覆盖 session、tool、artifact、evidence、approval、approval run、state snapshot、trace，但还不是逐节点 LangGraph state diff。
- 下一步可以把 native LangGraph checkpoint metadata / state diff 摘要纳入 replay，或进入 Phase I 完善统一 Asset Registry。

### 2026-06-18: Phase H slice - replay state summary and delta

已完成：

- `ExecutionReplayService` 为每个 replay state snapshot 派生可扫描摘要：
  - `state_summary.request_id`
  - `employee_id`
  - `ticket_id`
  - `action`
  - `current_step`
  - `tool_event_count`
  - `error_count`
  - `native_interrupt_count`
  - `checkpoint_next`
- `ExecutionReplayService` 为每个 snapshot 派生轻量 state delta：
  - `from=execution_request`
  - `to=<current_step>`
  - `changed_keys`
  - `approval_interrupted`
  - `has_errors`
- Dashboard Replay Detail 的 payload preview 覆盖 `state_summary` / `state_delta`，用于快速判断一次 approval block 的图状态变化。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/execution_replay_service.py tests/test_runtime_executor_routes.py

pytest tests/test_runtime_executor_routes.py::test_approved_claude_code_runtime_run_uses_approval_ref_and_ingests_repo_mutation -q

cd apps/dashboard && npm test -- settings-page.test.tsx

pytest tests/test_runtime_executor_routes.py tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py -q

cd apps/dashboard && npm run build
```

结果：

- `1 passed, 1 warning`
- Dashboard tests: `29 passed`
- `104 passed, 2 warnings`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

Phase H 仍未完成：

- Replay 已有 state summary / delta，但还不是 LangGraph 每个节点之间的完整 state diff。
- Replay detail 已升级为 route-backed Runtime surface，但 refs 跳转还需要补齐到 Ticket / Employee / Asset / Memory。
- 进入 Phase I 前，Phase H 已具备可审计闭环的主要后端和 UI 诊断能力。

### 2026-06-19: Phase H slice - replay provenance links to domain surfaces

已完成：

- 共享 `RuntimeSessionReplayDetail` 增加可点击 provenance refs：
  - session employee -> `#/employees/{employee_id}`
  - session Ticket / timeline ticket ref -> `#/tickets/{ticket_id}`
  - session memory / timeline memory ref -> `#/assets/knowledge/memory:{memory_id}`
  - timeline asset / artifact / evidence ref -> `#/assets/asset/{asset_id}`
- Runtime Replay 页面和 Settings 内联 Replay 复用同一个组件，因此两处都获得同样的 refs navigation。
- Replay detail 新增 `Session Refs` 区块，先展示 Employee / Ticket / Memory 的 session-level refs，再在 timeline item 内展示 event-level refs。
- 该 slice 与 Phase O 的 Assets drawer deep-link 串起来，Replay 现在可以直接落到具体 Memory / Asset drawer。

验证：

```bash
cd apps/dashboard && npm test -- runtime-page.test.tsx settings-page.test.tsx

cd apps/dashboard && npm run build
```

结果：

- Dashboard Vitest suite: `54 passed`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

Phase H 仍未完成：

- Replay 已有 state summary / delta 和 domain refs navigation，但还不是 LangGraph 每个节点之间的完整 state diff。
- 若要彻底关闭 Phase H，需要 LangGraph checkpoint / state history 暴露逐节点 diff 或更细的 graph state transition event。

### 2026-06-19: Phase H slice - replay state transition stream

已完成：

- `ExecutionReplayService` 的 replay payload 新增 `state_transitions`：
  - 从 session 的 checkpoint / current graph node / source state ref 派生 session-level transition。
  - 从 approval state snapshot 的 `state_delta` / `state_summary` 派生 snapshot-level transition。
  - 从 trace event 中可识别的 graph node / current step 字段派生 trace-level transition。
- Replay timeline 新增一等事件：
  - `execution.state_transition`
  - title 使用 `from -> to`，并携带 checkpoint / state / state_snapshot refs。
- Runtime Executors replay response model 和 Dashboard API 类型新增 `state_transitions`。
- 共享 `RuntimeSessionReplayDetail` 新增 `State Transitions` 区块，展示前几条 transition、changed keys 和 refs。
- Runtime Replay 页面和 Settings 内联 Replay 都能看到 state transition count、transition summary 和 JSON preview。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/execution_replay_service.py services/api/aiteamos_api/read/runtime_executor_routes.py tests/test_runtime_executor_routes.py

pytest tests/test_runtime_executor_routes.py::test_runtime_execution_sessions_list_checkpoint_and_replay_refs -q

pytest tests/test_runtime_executor_routes.py::test_approved_claude_code_runtime_run_uses_approval_ref_and_ingests_repo_mutation -q

cd apps/dashboard && npm test -- runtime-page.test.tsx settings-page.test.tsx
```

结果：

- Backend focused tests: `2 passed, 2 warnings`
- Dashboard Vitest suite: `54 passed`

Phase H 仍未完成：

- Replay 现在有可审计 state transition stream，但它仍是从 session / snapshot / trace 派生的过渡层，不等同于 LangGraph checkpointer 的完整逐节点 raw state history。
- 若要彻底关闭 Phase H，需要把 LangGraph 原生 checkpoint state history / per-node diff 暴露给 replay service。

### 2026-06-19: Phase H slice - native LangGraph checkpoint history replay

已完成：

- `ExecutionReplayService` 新增 `native_checkpoint_history`：
  - 从 `.aiteamos/langgraph/langgraph_checkpoints.sqlite` 只读加载 LangGraph checkpoint history。
  - 使用同构 `LangGraphExecutor` graph + `SqliteSaver.get_state_history`，不在 Chat route 自研 replay loop。
  - 兼容 workspace 指向 `.aiteamos` 或其父目录两种形态。
- 每条 native checkpoint history 包含：
  - `thread_id`
  - `checkpoint_id`
  - `parent_checkpoint_id`
  - `metadata.step`
  - `next`
  - task / interrupt summary
  - `state_summary`
  - per-checkpoint `state_delta`
  - redacted raw `values`
- Replay timeline 新增一等事件：
  - `execution.native_checkpoint`
- `state_transitions` 现在也会从 native checkpoint history 派生 `source_kind=native_checkpoint` 的 graph transition。
- Runtime Executors replay response model、Dashboard API 类型和共享 Replay Detail 组件新增 native checkpoint history 展示。
- Runtime Replay 页面和 Settings 内联 Replay 都能看到 native checkpoint count、checkpoint id、step、next nodes、changed keys。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/execution_replay_service.py services/api/aiteamos_api/read/runtime_executor_routes.py tests/test_runtime_executor_routes.py

pytest tests/test_runtime_executor_routes.py::test_runtime_replay_includes_native_langgraph_checkpoint_history -q

cd apps/dashboard && npm test -- runtime-page.test.tsx settings-page.test.tsx
```

结果：

- Native checkpoint replay focused test: `1 passed, 1 warning`
- Dashboard Vitest suite: `54 passed`

Phase H core acceptance status:

- Replay API / timeline / Dashboard surface / redaction / provenance refs / approval run history / state snapshots / derived transitions / native LangGraph checkpoint history 已形成可审计闭环。
- 后续 hardening 可继续做 payload size controls、checkpoint history pagination、per-field diff visualization，但 Phase H 的核心目标已经具备。

## 7. Phase I: Unified Asset Registry v2

目标：把 Memory、Docs、Skills、Tooling calls、solutions、suggestions、validation、closeout 统一成 Assets 生命周期。

任务：

1. 定义 `AssetRecord`、`AssetCandidate`、`AssetReviewRecord`、`AssetRelationship`。
2. 把现有 memory candidates / durable candidates 映射到 Asset Candidate。
3. `ExecutionResultIngestionService` 输出和消费：
   - `asset_candidate`
   - `tool_call_asset`
   - `solution_candidate`
   - `ticket_closeout_candidate`
   - `skill_candidate`
4. Assets Review Queue 支持 approve / reject / merge / link。
5. Graphiti projection 从 approved Assets 生成，不直接绕过 Review Queue。
6. `search_assets` 成为统一入口，能查 memory/doc/skill/tool_call/solution。

验收：

- 一个 Ticket 的解决方案能成为 `solution_candidate`，审批后进入 Assets。
- 一个有效 tool call 能作为 `tool_call` asset 被检索和复盘。
- Graphiti disabled 时，本地 Asset Registry 仍可用。
- Graphiti enabled 时，approved asset 被 projection 到 graph provider。

建议测试：

```bash
pytest tests/test_file_memory_routes.py
pytest tests/test_execution_dispatch_contract.py::test_execution_ingestion_creates_asset_candidates_with_provenance
cd apps/dashboard && npm test -- assets-page.test.tsx
```

### 2026-06-18: Phase I slice - local Asset Candidate registry

已完成：

- 新增 `AssetCandidateRecord` 和本地 registry：
  - `.aiteamos/assets/candidates.json`
  - `id`
  - `asset_id`
  - `asset_type`
  - `title`
  - `content_ref`
  - `scope_kind / scope_ref`
  - `owner_employee_id`
  - `source_kind / source_ref`
  - `provenance`
  - `relationships`
  - `review_state`
  - `usefulness_stats`
- memory candidates 和 external runtime durable candidates 现在会同步为 AssetCandidate。
- memory candidate approve / reject / stale / superseded / recall usefulness 更新会同步 AssetCandidate 状态和 usefulness stats。
- `ExecutionResultIngestionService` 新增 `asset.candidates:propose` tool event，并把 `asset_candidates` 写入 `learning_delta`。
- 新增后端 API：
  - `GET /api/v1/assets/candidates`
  - 支持 `status`、`asset_type`、`q`
- Dashboard `assets.ts` 增加 `AssetCandidateRecord` 和 `listAssetCandidates` helper。

验证：

```bash
pytest tests/test_execution_dispatch_contract.py::test_external_runtime_durable_asset_candidates_enter_review_queue -q

pytest tests/test_execution_dispatch_contract.py tests/test_file_memory_routes.py tests/test_file_chat_routes.py tests/test_runtime_executor_routes.py

cd apps/dashboard && npm run build
```

结果：

- `1 passed, 1 warning`
- `115 passed, 1 warning`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

Phase I 仍未完成：

- `AssetReviewRecord` 和 approve / reject / merge / link 还没有统一替代 memory review queue。
- Tool call / solution / ticket closeout 还没有成为一等 AssetRecord。
- `/assets/search` 还没有统一查询 AssetCandidate / tool_call / solution。
- Graphiti projection 仍以 memory/durable projection 为主，还不是 approved AssetCandidate -> graph provider。

### 2026-06-18: Phase I slice - AssetCandidate review and AssetRecord promotion

已完成：

- `asset_candidate_service.py` 新增本地 Asset Registry v2 基础记录：
  - `AssetRecord`
  - `AssetReviewRecord`
  - `AssetCandidateReviewRequest`
  - `AssetCandidateReviewResponse`
- 新增本地持久化文件：
  - `.aiteamos/assets/index.json`
  - `.aiteamos/assets/reviews.json`
- `review_asset_candidate` 支持治理状态：
  - `approved`
  - `rejected`
  - `merged`
  - `linked`
- `approved` AssetCandidate 会提升为一等 `AssetRecord`，并保留：
  - source AssetCandidate provenance
  - reviewer / review reason
  - source Ticket / Employee / Runtime refs
  - relationships
  - content_ref
- 新增后端 API：
  - `POST /api/v1/assets/candidates/{candidate_id}/review`
  - `GET /api/v1/assets/records`
  - `GET /api/v1/assets/reviews`
- `/api/v1/assets/search` 现在合并：
  - 旧 knowledge / capability / ticket AssetRecord
  - approved local Asset Registry records
  - AssetCandidate records
- Dashboard Assets Review Queue 接入 AssetCandidate：
  - Review Queue 中显示 asset candidates
  - candidate drawer 展示 content、scope、source、provenance
  - 支持 Approve / Reject
  - approve 调用 `/assets/candidates/{id}/review`

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/asset_candidate_service.py services/api/aiteamos_api/read/asset_routes.py

pytest tests/test_execution_dispatch_contract.py::test_external_runtime_durable_asset_candidates_enter_review_queue -q

pytest tests/test_execution_dispatch_contract.py tests/test_file_memory_routes.py tests/test_file_chat_routes.py tests/test_runtime_executor_routes.py -q

cd apps/dashboard && npm test -- assets-page.test.tsx

cd apps/dashboard && npm run build
```

结果：

- `1 passed, 1 warning`
- `119 passed, 2 warnings`
- Dashboard tests: `30 passed`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。
- 后端广套件中仍有 LangGraph / aiosqlite 在 pytest 关闭 event loop 时的线程警告，需要后续 runtime checkpointer lifecycle cleanup。

该 slice 之后 Phase I 仍未完成：

- Tool call / solution / ticket closeout 已能作为 AssetCandidate，并且 approved 后可成为 AssetRecord；但还没有专门的 typed `tool_call` ingestion/report UI。
- Asset Review Queue 还没有完整 merge/link UI，只是后端 contract 已支持 `merged` / `linked`。
- approved AssetRecord -> graph provider projection 已在下一 slice 继续推进。

### 2026-06-18: Phase I slice - approved AssetRecord Graphiti provider projection

已完成：

- `asset_candidate_service.py` 新增 approved AssetRecord 到 Graphiti 的 provider projection：
  - 只允许 `approved` / `accepted` / `validated` AssetRecord 投影。
  - 复用 `memory_service.ingest_durable_asset_to_graphiti`，不新造 Graphiti ingestion。
  - 从 AssetRecord 构造 `DurableAssetIngestRequest`，保留 Ticket、Employee、run、report、evidence、review、candidate、relationship provenance。
  - 读取 `.aiteamos/memory/graphiti_state.json` 的 durable asset audit 做重复投影跳过。
  - 投影成功后把 `graphiti_status`、`graphiti_projected_at`、`provider_refs` 回写到 `.aiteamos/assets/index.json`。
- 新增后端 API：
  - `POST /api/v1/assets/records/{asset_id}/project/graphiti`
- Dashboard API 层新增：
  - `projectAssetRecordToGraphiti(assetId)`
- 新增测试覆盖：
  - Graphiti disabled 时，本地 AssetRecord 已存在但 projection 返回 setup blocker。
  - Graphiti enabled 时，approved AssetRecord 被投影到 Graphiti，并写入 episode / provenance。
  - 第二次 projection 通过 durable asset audit 去重，返回 `skipped`。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/asset_candidate_service.py services/api/aiteamos_api/read/asset_routes.py tests/test_execution_dispatch_contract.py

pytest tests/test_execution_dispatch_contract.py::test_external_runtime_durable_asset_candidates_enter_review_queue tests/test_execution_dispatch_contract.py::test_approved_asset_record_projects_to_graphiti_provider -q

pytest tests/test_execution_dispatch_contract.py tests/test_file_memory_routes.py tests/test_file_chat_routes.py tests/test_runtime_executor_routes.py -q

cd apps/dashboard && npm test -- assets-page.test.tsx

cd apps/dashboard && npm run build
```

结果：

- Focused backend tests: `2 passed, 1 warning`
- Broader backend suite: `120 passed, 1 warning`
- Dashboard tests: `30 passed`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

Phase I 仍未完成：

- Tool call / solution / ticket closeout 还需要专门的 typed ingestion/report UI。
- Asset Review Queue 还没有完整 merge/link UI。

### 2026-06-18: Phase I slice - AssetRecord relationship Graphiti provider projection

已完成：

- `asset_candidate_service.py` 新增 approved AssetRecord relationships 到 Graphiti 的 provider projection：
  - 只允许 `approved` / `accepted` / `validated` AssetRecord 的关系投影。
  - 复用 `memory_service.ingest_durable_asset_relationship_to_graphiti`，不新造 Graphiti relationship ingestion。
  - 将 Review Queue / AssetRecord 中明确指向 asset 的关系转换为 durable relationship。
  - 支持受控关系类型：
    - `supersedes`
    - `conflicts_with`
    - `derived_from`
    - `used_by`
    - `validated_by`
  - 非 asset target 或不支持的关系会进入 `unsupported_relationships`，不会误写 graph provider。
  - 投影或跳过后，把 `graphiti_relationships` 和 `graphiti_relationships_projected_at` 回写到 `.aiteamos/assets/index.json`。
- 新增后端 API：
  - `POST /api/v1/assets/records/{asset_id}/relationships/project/graphiti`
- Dashboard API 层新增：
  - `projectAssetRecordRelationshipsToGraphiti(assetId)`
- 新增测试覆盖：
  - Approved AssetRecord 通过 review link 指向另一个 AssetRecord。
  - Graphiti enabled 时，`supersedes` 关系被投影为 durable asset relationship。
  - provenance 保留 source / target asset、Ticket、Employee、run、report、evidence、confidence。
  - 第二次 projection 通过 durable relationship audit 去重，返回 `skipped`。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/asset_candidate_service.py services/api/aiteamos_api/read/asset_routes.py tests/test_execution_dispatch_contract.py

pytest tests/test_execution_dispatch_contract.py::test_external_runtime_durable_asset_candidates_enter_review_queue tests/test_execution_dispatch_contract.py::test_approved_asset_record_projects_to_graphiti_provider tests/test_execution_dispatch_contract.py::test_asset_record_review_relationship_projects_to_graphiti_provider -q

pytest tests/test_execution_dispatch_contract.py tests/test_file_memory_routes.py tests/test_file_chat_routes.py tests/test_runtime_executor_routes.py -q

cd apps/dashboard && npm test -- assets-page.test.tsx

cd apps/dashboard && npm run build
```

结果：

- Focused backend tests: `3 passed, 1 warning`
- Broader backend suite: `121 passed, 1 warning`
- Dashboard tests: `30 passed`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

Phase I 仍未完成：

- Tool call / solution / ticket closeout 还需要专门的 typed ingestion/report UI。
- Asset Review Queue 还没有完整 merge/link UI。

### 2026-06-18: Phase I slice - Asset Review Queue merge / link UI

已完成：

- Dashboard Assets Review Queue 的 AssetCandidate drawer 新增治理操作：
  - `Target Asset ID`
  - `Relationship`
  - `Approve`
  - `Link`
  - `Merge`
  - `Reject`
- `Approve` 支持可选 link relationship：
  - 用户填写 target asset 后，approve 会携带 `link_relationships`。
  - 关系类型使用受控选项：`derived_from`、`supersedes`、`conflicts_with`、`used_by`、`validated_by`。
- `Link` / `Merge` 支持走后端已有 `linked` / `merged` contract：
  - 需要 `Target Asset ID`。
  - 请求写入 `merge_target_asset_id`，由后端 AssetReviewRecord 记录。
- Review Queue 列表上的快速 Approve / Reject 保持不变，drawer 内提供更完整的 merge/link 控制。
- 新增前端测试覆盖：
  - approve asset candidate 时携带 relationship target。
  - link asset candidate 到已有 AssetRecord，不提升为新 AssetRecord。

验证：

```bash
cd apps/dashboard && npm test -- assets-page.test.tsx

cd apps/dashboard && npm run build
```

结果：

- Dashboard tests: `32 passed`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

Phase I 仍未完成：

- Tool call 仍需要专门的 typed report UI；solution / ticket closeout 还需要专门的 typed ingestion/report UI。

### 2026-06-18: Phase I slice - opt-in tool_call AssetCandidate ingestion

已完成：

- `ExecutionResultIngestionService` 新增 opt-in tool call 资产化：
  - runtime tool event 明确标记 `record_as_asset: true` 时，生成 `tool_call` AssetCandidate。
  - `learning_delta.tool_call_candidates` 也进入现有 durable candidate 管道。
  - 默认不把所有 tool_events 自动资产化，避免污染普通 chat metadata、Memory refs 和 session replay。
- tool_call AssetCandidate 保留：
  - source Ticket
  - source Employee
  - source run / trace
  - executor id
  - command id
  - tool event index
  - derived_from_ticket relationship
- tool event payload 写入资产前会 redaction：
  - `secret`
  - `token`
  - `password`
  - `api_key` / `apikey`
  - `authorization`
- `AssetCandidate` 类型归一化显式支持 `tool_call`。
- 新增测试覆盖：
  - opt-in `terminal.run` tool event 进入 AssetCandidate Review Queue。
  - secret/token 字段不会进入 asset content。
  - 未显式 opt-in 的普通 runtime/chat tool events 不会产生额外候选项。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/execution_result_ingestion_service.py services/api/aiteamos_api/read/asset_candidate_service.py tests/test_execution_dispatch_contract.py

pytest tests/test_execution_dispatch_contract.py::test_execution_tool_events_enter_asset_candidate_review_queue tests/test_execution_dispatch_contract.py::test_chat_can_start_governed_self_bootstrap_improvement_batch tests/test_runtime_executor_routes.py::test_runtime_execution_sessions_list_checkpoint_and_replay_refs -q

pytest tests/test_execution_dispatch_contract.py tests/test_file_memory_routes.py tests/test_file_chat_routes.py tests/test_runtime_executor_routes.py -q
```

结果：

- Focused backend tests: `3 passed, 1 warning`
- Broader backend suite: `122 passed, 2 warnings`
- 后端广套件仍有 Graphiti/Pydantic warning，以及既有 LangGraph / aiosqlite 在 pytest 关闭 event loop 时的线程警告。

### 2026-06-18: Phase I slice - Ticket closeout / solution typed UI verification

已完成：

- Ticket detail 已有 `Closeout Assets` typed action：
  - 调用 `POST /api/v1/tickets/{ticket_id}/closeout-candidates`
  - 只允许 validated / completed / done / closed Ticket 生成候选资产。
  - 生成 `ticket_closeout`、`solution`、`validation_result` AssetCandidate。
  - 写入 `ticket_closeout_candidates` report，并把 `asset-candidate:*` evidence refs 留在 Ticket ledger。
- Dashboard Ticket detail 展示：
  - closeout proposal status
  - candidate asset types
  - generated report id
- 后端验收补强：
  - `solution` candidate 可被 approve 为 `AssetRecord`。
  - approved solution AssetRecord 保留 Ticket scope。

验证：

```bash
pytest tests/test_execution_dispatch_contract.py::test_validated_ticket_closeout_generates_reviewable_asset_candidates -q

cd apps/dashboard && npm test -- tickets-page.test.tsx
```

结果：

- Backend closeout test passed。
- Dashboard Tickets tests passed。

### 2026-06-18: Phase I slice - typed tool_call review UI and approved Asset search

已完成：

- Assets Review Queue 的 `tool_call` AssetCandidate drawer 新增 typed detail：
  - Command
  - Event
  - Run
  - Trace
  - Index
  - Executor
- `tool_call` candidate 不再只能靠 raw provenance JSON 复盘。
- 后端验收补强：
  - opt-in `tool_call` candidate 可被 approve 为 `AssetRecord`。
  - approved `tool_call` AssetRecord 可通过 `/api/v1/assets/search` 检索。

验证：

```bash
pytest tests/test_execution_dispatch_contract.py::test_execution_tool_events_enter_asset_candidate_review_queue -q

cd apps/dashboard && npm test -- assets-page.test.tsx

cd apps/dashboard && npm run build
```

结果：

- Backend tool_call test passed。
- Dashboard Assets tests: `33 passed`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

Phase I core acceptance status:

- Ticket solution 可以成为 `solution_candidate`，审批后进入 Assets。
- 有效 tool call 可以作为 `tool_call` asset 被检索和复盘。
- Graphiti disabled 时，本地 Asset Registry 仍可用。
- Graphiti enabled 时，approved asset 可 projection 到 graph provider。
- Review Queue 已支持 approve / reject / merge / link。

Phase I 后续硬化项：

- Tool call typed UI 后续可增加 payload diff / replay deep link。
- Solution / closeout 后续可增加批量 approve / Graphiti projection UI。

## 8. Phase J: Employee System v2

目标：让 Employees 真正像固定团队成员，而不是一次性 prompt 角色。

任务：

1. 扩展 Employee profile：
   - personality tags
   - capability tags
   - skill refs
   - memory scopes
   - preferred runtime
   - permission policy
   - handoff policy
2. 建立 Employee Work Ledger v2：
   - assigned tickets
   - reports written
   - handoffs sent / received
   - validations requested / completed
   - assets proposed / approved
   - quality feedback
3. LangGraph context 自动加载：
   - selected employee profile
   - relevant skills
   - recent work history
   - memory scope
   - permission policy
4. Dashboard Employee detail 展示：
   - capabilities
   - personality
   - skills
   - work history
   - memory scope
   - current tickets
5. Employee handoff 从 deterministic first version 升级为 policy-aware routing。

验收：

- Clara 收到实现类 Ticket 时能基于 Employee profile / load / skills 选择 assignee。
- Alex / Peter 的回答和可用工具受自己的权限和 skill scope 影响。
- Employee detail 可以看到该成员做过什么、知道什么、能做什么。

建议测试：

```bash
pytest tests/test_execution_dispatch_contract.py::test_employee_profile_controls_langgraph_context_and_handoff
cd apps/dashboard && npm test -- employees-page.test.tsx
```

### 2026-06-18: Phase J slice - Employee v2 profile contract in Chat and LangGraph context

已完成：

- `ChatEmployeeSummary` 扩展 Employee v2 字段：
  - `skill_refs`
  - `capability_tags`
  - `personality_tags`
  - `memory_scopes`
  - `preferred_runtime`
  - `permission_policy`
  - `handoff_policy`
  - `current_load`
- `chat_routes._normalize_employee_profile` 现在向后兼容地从旧字段派生 v2 字段：
  - `skills -> skill_refs`
  - `permissions -> permission_policy.permissions`
  - `personality -> personality_tags`
  - role / skills / permissions -> `capability_tags`
  - default `memory_scopes = ["aiteamos", "employee:{id}"]`
  - default `handoff_policy.can_receive_handoffs`
- Clara bootstrap profile 会持久化这些字段，仍保持 protected system employee。
- `ExecutionContextService` 的 `universal_context.employee_context` 现在给 LangGraph 提供：
  - selected employee 的 v2 profile contract
  - available employee refs 的 `skill_refs`、`capability_tags`、`preferred_runtime`、`current_load`
- Dashboard `chat.ts` 类型已同步。

验证：

```bash
pytest tests/test_execution_dispatch_contract.py::test_execution_context_builds_universal_context_with_ticket_assets_and_memory_refs \
  tests/test_file_chat_routes.py::test_chat_employees_bootstraps_protected_clara_system_employee -q

pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py tests/test_runtime_executor_routes.py

cd apps/dashboard && npm run build
```

结果：

- `2 passed, 1 warning`
- `100 passed, 1 warning`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

### 2026-06-18: Phase J slice - real Employee current_load from Tickets and runtime sessions

已完成：

- 新增 `employee_load_service`，把 Employee 的实时负载从 AITeamOS-owned facts 聚合出来：
  - active / assigned / validation Tickets
  - blocked Tickets
  - active runtime sessions
  - waiting approval runtime sessions
  - active Ticket ids / run ids
  - `available` / `active` / `busy` / `running` / `needs_attention` 状态
- `ChatEmployeeSummary.current_load` 不再只是 profile 静态字段：
  - Chat employee list 会用真实 Ticket / runtime session facts 覆盖 stale profile value。
  - Ticket backend 不可用时保留 profile fallback，并带 load blocker。
- `ExecutionContextService.universal_context.employee_context` 现在给 LangGraph 提供同一份真实负载投影：
  - selected employee 的 `current_load`
  - available employee refs 的 `current_load`
- Dashboard Employee detail 新增 `Load Snapshot`：
  - Active Tickets
  - Runtime Runs
  - Waiting Approval
  - active Ticket / run refs
- Employee list 状态 badge 现在会反映 `needs_attention`、`running`、`busy`、`active`。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/employee_load_service.py \
  services/api/aiteamos_api/read/chat_routes.py \
  services/api/aiteamos_api/read/execution_context_service.py \
  tests/test_execution_dispatch_contract.py

pytest tests/test_execution_dispatch_contract.py::test_execution_context_builds_universal_context_with_ticket_assets_and_memory_refs \
  tests/test_execution_dispatch_contract.py::test_employee_current_load_uses_active_tickets_and_runtime_sessions -q

pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py tests/test_runtime_executor_routes.py -q

cd apps/dashboard && npm test -- employees-page.test.tsx
```

结果：

- py_compile passed
- `2 passed, 1 warning`
- `108 passed, 2 warnings`
- Dashboard Vitest matched suite passed：`33 passed`

### 2026-06-18: Phase J slice - Employee Work Ledger v2 assets / runtime / feedback projection

已完成：

- `EmployeeWorkLedger` 向后兼容扩展 v2 projection：
  - `asset_candidates`
  - `approved_assets`
  - `asset_reviews`
  - `runtime_runs`
  - `quality_feedback`
- local / Plane-backed ledger 返回前统一 augment：
  - AssetCandidate / AssetRecord / AssetReview 进入 Employee ledger。
  - execution artifact mirror 进入 Employee runtime run ledger。
  - blocked / failed runtime run 进入 quality feedback。
  - asset review reason 进入 quality feedback。
- Dashboard Employee `Work Ledger` tab 新增：
  - `Asset Contributions`
  - `Runtime Run Ledger`
  - `Quality Feedback`
  - work summary stats: Assets Proposed / Runtime Runs
- 保持 Ticket-flow-first 边界：
  - Work Ledger 是 read model projection。
  - 没有绕过 Ticket / Asset / Runtime artifact provenance 写新状态。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/ticket_service.py \
  tests/test_execution_dispatch_contract.py

pytest tests/test_execution_dispatch_contract.py::test_employee_work_ledger_v2_projects_assets_reviews_and_runtime_runs -q

pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py tests/test_runtime_executor_routes.py -q

cd apps/dashboard && npm test -- employees-page.test.tsx
cd apps/dashboard && npm run build
git diff --check
```

结果：

- py_compile passed
- `1 passed, 1 warning`
- `109 passed, 1 warning`
- Dashboard Vitest matched suite passed：`33 passed`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。
- `git diff --check` passed

### 2026-06-18: Phase J slice - policy-aware Employee handoff routing

已完成：

- `employee_handoff_service.choose_employee_for_goal` 从基础 deterministic routing 升级为 policy-aware scoring：
  - `handoff_policy.can_receive_handoffs=false` 会排除候选。
  - `handoff_policy.accepts_lanes` / `preferred_lanes` / `blocked_lanes` 会影响或限制候选。
  - `handoff_policy.max_active_tickets` 会防止把工作交给已满载 Employee。
  - `skill_refs`、`capability_tags`、`permission_policy.permissions` 参与 lane score。
  - `current_load.status` 和 `active_ticket_count` 参与负载惩罚。
- 保持向后兼容：
  - 没有 v2 policy 字段的旧 profile 仍按 role / skills / summary 路由。
  - 没有合格 profile 时保留旧 fallback，但如果 fallback profile 明确禁止接收，会返回 no-handoff。
- LangGraph handoff artifact / tool event 现在带 `policy` 摘要：
  - `policy_aware`
  - score
  - active ticket count
  - load status

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/employee_handoff_service.py \
  services/api/aiteamos_api/read/runtime_executors/langgraph_executor.py \
  tests/test_execution_dispatch_contract.py

pytest tests/test_execution_dispatch_contract.py::test_choose_employee_for_goal_routes_to_fixed_employee_profiles \
  tests/test_execution_dispatch_contract.py::test_choose_employee_for_goal_uses_handoff_policy_and_current_load \
  tests/test_execution_dispatch_contract.py::test_universal_agent_handoff_artifact_records_ticket_events_and_report -q

pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py tests/test_runtime_executor_routes.py -q
git diff --check
```

结果：

- py_compile passed
- `3 passed, 1 warning`
- `110 passed, 1 warning`
- `git diff --check` passed

### 2026-06-18: Phase J slice - Employee provider projection visibility

已完成：

- Graphiti Employee profile durable asset ingestion audit 现在有只读状态投影：
  - `employee_profile_projection_status(employee_id)`
  - status / backend_status / episode_id / asset_id / ingested_at
- `EmployeeGraphProjection` 扩展 `provider_projection`：
  - `provider_projection.employee_profile`
  - 不触发 Graphiti 写入，只读取本地 audit。
- Dashboard Employee detail 新增 `Provider Projection`：
  - Graphiti profile asset
  - backend status
  - episode id
  - projection status
- 后端测试覆盖：
  - Employee profile projected to Graphiti 后，`/api/v1/employees/{id}/graph` 返回 provider projection 状态。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/memory_service.py \
  services/api/aiteamos_api/read/ticket_service.py \
  tests/test_file_memory_routes.py

pytest tests/test_file_memory_routes.py::test_approved_employee_profile_durable_assets_project_to_graphiti -q

pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py \
  tests/test_file_memory_routes.py tests/test_runtime_executor_routes.py -q

cd apps/dashboard && npm test -- employees-page.test.tsx
cd apps/dashboard && npm run build
git diff --check
```

结果：

- py_compile passed
- `1 passed, 1 warning`
- `125 passed, 1 warning`
- Dashboard Vitest matched suite passed：`33 passed`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。
- `git diff --check` passed

### 2026-06-19: Phase J hardening slice - quality feedback to governed Employee improvement candidate

已完成：

- `Employee Work Ledger v2` 中的 actionable quality feedback 现在可以转成 governed `AssetCandidate`：
  - 新增 `POST /api/v1/employees/{employee_id}/quality-feedback/{feedback_id}/improvement-candidate`。
  - candidate 使用 `asset_type=employee_improvement`、`scope_kind=employee`、`owner_employee_id={employee_id}`、`source_kind=employee_quality_feedback`。
  - candidate provenance 保留 source feedback、source ticket、reviewer / actor employee、proposal reason、relationships。
  - API 幂等：同一 Employee + feedback 会 upsert 同一个 deterministic candidate id。
- Dashboard Employee detail 的 quality feedback 区域新增 `Propose Improvement` action：
  - reviewer 可以从 feedback 直接提出 Employee improvement candidate。
  - 成功后可跳转到 Asset Review candidate 页面继续走治理流程。
- 该 slice 只实现 AITeamOS 的治理 / 资产候选流转，不实现通用 agent reasoning、自我改写 personality、自动运行 agent loop；后续改进执行仍由 LangGraph runtime、Approval、Asset Review 和 Employee profile/skill promotion 规则承接。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/ticket_service.py services/api/aiteamos_api/read/employees_routes.py tests/test_execution_dispatch_contract.py
pytest tests/test_execution_dispatch_contract.py::test_employee_work_ledger_v2_projects_assets_reviews_and_runtime_runs -q
cd apps/dashboard && npm test -- employees-page.test.tsx
```

结果：

- py_compile passed
- `1 passed, 1 warning`
- Dashboard Vitest matched suite passed：`56 passed`

### 2026-06-19: Phase J hardening slice - approved Employee improvement Asset application

已完成：

- 新增 `employee_improvement_service.py`，把 approved `employee_improvement` AssetRecord 受控应用到 Employee profile：
  - 只允许 `approved` / `accepted` / `validated` AssetRecord。
  - 只允许 `asset_type=employee_improvement`。
  - AssetRecord 必须通过 `scope_kind=employee` / `scope_ref` 或 `improves_employee` relationship 指向目标 Employee。
  - 只做 allowlisted 加法更新：`skill_refs`、`memory_scopes`、`capability_tags`、`personality_tags`。
  - 自动写入 `applied_improvement_refs` 和 `work_history_refs`，保留 asset / review / feedback / Ticket provenance。
- `EmployeeImprovementCandidateRequest` 新增可审批的 proposed profile updates：
  - `proposed_skill_refs`
  - `proposed_memory_scopes`
  - `proposed_capability_tags`
  - `proposed_personality_tags`
  - repeated propose 不再覆盖已有 proposed updates，避免幂等 upsert 丢失审批准入内容。
- 新增 Employee API：
  - `POST /api/v1/employees/{employee_id}/improvement-assets/{asset_id}/apply`
- 应用成功会：
  - 更新 `.aiteamos/employees/{employee_id}.yaml`。
  - 回写 AssetRecord provenance：`employee_improvement_application`。
  - 增加 `applied_to_employee` relationship。
  - 若来源 Ticket 存在，写入 `employee_improvement_applied` Ticket report。
- Dashboard Assets drawer 对 approved `employee_improvement` AssetRecord 新增：
  - `Employee Improvement` 状态卡。
  - `Apply Improvement` action。
  - action 调用 Employee API，不在前端做 profile mutation。
- 该 slice 仍不实现通用 agent 自我改写；它只是 Asset Review approved 之后的一道显式 Employee governance application gate。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/employee_improvement_service.py services/api/aiteamos_api/read/employees_routes.py services/api/aiteamos_api/read/ticket_service.py tests/test_execution_dispatch_contract.py
pytest tests/test_execution_dispatch_contract.py::test_employee_work_ledger_v2_projects_assets_reviews_and_runtime_runs -q
cd apps/dashboard && npm test -- assets-page.test.tsx employees-page.test.tsx
cd apps/dashboard && npm run build
git diff --check
```

结果：

- py_compile passed
- backend focused test: `1 passed, 1 warning`
- Dashboard Vitest matched suite passed：`57 passed`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。
- `git diff --check` passed

Phase J core acceptance status:

- Employee v2 profile contract 已进入 Chat summary 和 LangGraph context。
- `current_load` 已从 active Ticket / runtime sessions 真实计算。
- Work Ledger v2 已统一 Ticket reports / handoffs / validations 与 Asset proposed / approved / reviews、runtime runs、quality feedback。
- handoff routing 已使用 `handoff_policy`、capability / skill tags、permissions 和 current load。
- Employee detail 已展示 load、work ledger v2、analytics、graph provenance 和 provider projection。
- approved Employee improvement Asset 已能通过显式 governance gate 应用到 Employee profile / skill refs / memory scopes / tags，并回写 Ticket / Asset provenance。

Phase J 后续硬化项：

- Provider projection 目前只显示 Employee profile durable asset；后续可增加 Employee 相关 skills / memories / decisions projection rollup。
- quality feedback 已能转成 governed Employee improvement candidate，approved 后也能显式应用到 Employee profile；后续可补 approved improvement -> Skill asset promotion / Memory candidate promotion 的更细自动化建议，但仍必须走 Asset Review / governance gate。
- handoff 已是 policy-aware first slice，但还没有引入历史质量分、长期成功率和 explicit escalation workflow。

## 9. Phase K: Ticket-native Autonomous Loop

目标：把单次 Chat run 升级为 Ticket 状态驱动的 autonomous loop。

核心原则：

- Autonomous loop 不是开放式后台乱跑。
- 每一轮 loop 必须绑定 Ticket、Employee、budget、permissions、stop condition。
- 每一轮结果必须写入 Ticket report / evidence / validation / blocker / asset candidate。

第一版 loop：

```text
load_ticket_state
  -> load_employee_state
  -> retrieve_assets_memory_skills
  -> plan_next_step
  -> execute_read_or_prepare_write
  -> governance_gate
  -> maybe_approval_interrupt
  -> write_report_or_evidence
  -> maybe_request_validation
  -> maybe_handoff
  -> maybe_create_asset_candidates
  -> decide_continue_or_stop
```

任务：

1. 新增 `TicketAutonomousLoopService`，只负责调度 runtime，不实现 agent reasoning。
2. 新增 Ticket loop policy：
   - max steps
   - max runtime seconds
   - allowed capabilities
   - approval requirements
   - validation requirements
   - stop statuses
3. LangGraph state 增加：
   - loop_step
   - ticket_status_before / after
   - next_stop_reason
   - validation_gate
4. Dashboard Ticket detail 增加 `Run loop` / `Continue loop` / `Stop loop` 控制。
5. 所有 loop step 写入 Ticket event ledger 和 execution session。

验收：

- 一个 Ticket 可以自动推进多个 step，直到 done、blocked、needs_approval 或 needs_validation。
- 每一步都可 replay。
- 不满足 approval / evidence / validation 条件时不会假装完成。
- Human 可以随时 stop loop。

建议测试：

```bash
pytest tests/test_execution_dispatch_contract.py::test_ticket_autonomous_loop_stops_at_approval_gate
pytest tests/test_execution_dispatch_contract.py::test_ticket_autonomous_loop_records_each_step_in_ticket_events
cd apps/dashboard && npm test -- tickets-page.test.tsx
```

### 2026-06-18: Phase K slice - Ticket-native single-step loop primitive

已完成：

- 新增 `TicketAutonomousLoopService`，作为 autonomous loop 的安全单步 primitive：
  - 必须绑定 existing Ticket。
  - 必须绑定 Employee。
  - `max_steps` 固定为 1。
  - 带 `stop_condition`、budget、selected executor / AI engine。
  - 通过 `ExecutionDispatchService` 调用 runtime，不在 route 层自研 agent loop。
  - 通过 `ExecutionResultIngestionService` 写回 Ticket report、evidence、session。
- 新增后端 API：
  - `POST /api/v1/tickets/{ticket_id}/loop/step`
- loop step 会生成 Ticket-bound `ExecutionRequest`：
  - action `append_report`
  - `ticket_binding=existing|required`
  - `trace_context.loop_kind=ticket_native_step`
  - `thread_id=ticket-loop-{ticket_id}`
  - `approval_policy.require_approval_for=["repo:write"]`
- loop response 返回：
  - `stop_reason`
  - request / result
  - ingestion status
  - compact `loop_state`
- Plane validation request metadata 小修：
  - validation request-like report comment 也会带 `request_type=validation_request` 和 validation target，避免 provider comment provenance 丢失。

验证：

```bash
pytest tests/test_execution_dispatch_contract.py::test_ticket_native_loop_step_dispatches_ticket_bound_request_and_ingests_report \
  tests/test_execution_dispatch_contract.py::test_ticket_loop_step_route_returns_404_for_missing_ticket -q

pytest tests/test_file_knowledge_and_tickets.py::test_chat_request_validation_uses_phase1_action_plan_and_plane_provider_ref -q

pytest tests/test_execution_dispatch_contract.py tests/test_file_knowledge_and_tickets.py tests/test_file_chat_routes.py tests/test_runtime_executor_routes.py
```

结果：

- `2 passed, 1 warning`
- `1 passed, 1 warning`
- `121 passed, 1 warning`

### 2026-06-18: Phase K slice - bounded multi-step Ticket loop and dashboard run control

已完成：

- 将 `TicketAutonomousLoopService` 从单步 primitive 扩展为 bounded multi-step loop：
  - 新增 `TicketLoopRunRequest` / `TicketLoopRunResponse`。
  - 新增 `POST /api/v1/tickets/{ticket_id}/loop/run`。
  - `max_steps` 限制为 1-5，`max_runtime_seconds` 限制为 1-300。
  - 支持 `stop_statuses`，默认在 `validated`、`completed`、`done`、`closed`、`blocked`、`failed` 停止。
  - 每一步仍然调用 `run_step`，不在 route 层实现 agent reasoning。
- 每个 loop step 写入独立 execution session：
  - `thread_id=ticket-loop-{ticket_id}-step-{n}`。
  - 避免多步 loop 覆盖同一 Ticket 的执行 session。
  - 每步仍保留 Ticket binding、approval policy、trace context、ingestion flow。
- loop stop reason 已覆盖：
  - `max_steps_reached`
  - `runtime_budget_exhausted`
  - `approval_required`
  - `blocked_or_failed`
  - `ticket_status:{status}`
- Dashboard Ticket detail 新增 `Run Loop` 控制：
  - 调用 `/loop/run`，默认从当前 assignee employee 执行。
  - 显示 `Autonomous Loop` 结果面板。
  - 展示整体 stop reason、step count、前三个 step 的 status / stop reason。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/ticket_loop_service.py \
  services/api/aiteamos_api/read/ticket_routes.py \
  tests/test_execution_dispatch_contract.py

pytest tests/test_execution_dispatch_contract.py::test_ticket_native_loop_step_dispatches_ticket_bound_request_and_ingests_report \
  tests/test_execution_dispatch_contract.py::test_ticket_native_loop_run_records_each_step_until_max_steps \
  tests/test_execution_dispatch_contract.py::test_ticket_native_loop_run_stops_at_approval_gate -q

cd apps/dashboard && npm test -- tickets-page.test.tsx

pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py tests/test_file_memory_routes.py tests/test_runtime_executor_routes.py -q

cd apps/dashboard && npm run build
```

结果：

- `3 passed, 1 warning`
- `34 passed`
- `127 passed, 1 warning`
- Dashboard build passed，仍有既有 Vite large chunk warning。

### 2026-06-18: Phase K slice - loop state facts for replay and LangGraph alignment

已完成：

- `TicketAutonomousLoopService.run_step` 现在把 loop state facts 写入 `ExecutionRequest.trace_context`：
  - `loop_step`
  - `ticket_status_before`
  - `validation_gate`
- `TicketLoopStepResponse.loop_state` 现在返回执行后的状态事实：
  - `loop_step`
  - `ticket_status_before`
  - `ticket_status_after`
  - `validation_gate`
  - `next_stop_reason`
- `run_loop` 会把每一步的 `loop_step` 同时写入 budget 和 runtime config，保证 dispatch / trace / replay 看到同一轮次。
- `validation_gate` 当前是 deterministic projection：
  - 是否 required / requested / satisfied
  - 是否已有 validation report
  - validator employee / role

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/ticket_loop_service.py \
  tests/test_execution_dispatch_contract.py

pytest tests/test_execution_dispatch_contract.py::test_ticket_native_loop_step_dispatches_ticket_bound_request_and_ingests_report \
  tests/test_execution_dispatch_contract.py::test_ticket_native_loop_run_records_each_step_until_max_steps \
  tests/test_execution_dispatch_contract.py::test_ticket_native_loop_run_stops_at_approval_gate -q
```

结果：

- `3 passed, 1 warning`

### 2026-06-18: Phase K slice - LangGraph graph-level loop state schema

已完成：

- `LangGraphExecutionState` 新增 `loop_state` 字段。
- `LangGraphExecutor._initial_graph_state` 会从 `ExecutionRequest.trace_context` 投影 Ticket-native loop facts：
  - `loop_kind`
  - `loop_step`
  - `stop_condition`
  - `ticket_status_before`
  - `ticket_status_after`
  - `validation_gate`
  - `thread_id`
- `runtime.load_request` tool event 会携带 `loop_state`，方便 replay timeline 看到 LangGraph 入图时的 loop facts。
- `produce_result` 会回写 graph-level runtime facts：
  - `runtime_status`
  - `current_graph_node`
  - `next_stop_reason`
- `ExecutionResult.learning_delta.loop_state` 暴露最终 graph-level loop state，后续 replay / analytics / policy 可以复用。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/runtime_executors/langgraph_executor.py \
  tests/test_execution_dispatch_contract.py

pytest tests/test_execution_dispatch_contract.py::test_langgraph_executor_projects_ticket_loop_state_into_graph_state \
  tests/test_execution_dispatch_contract.py::test_ticket_native_loop_step_dispatches_ticket_bound_request_and_ingests_report \
  tests/test_execution_dispatch_contract.py::test_ticket_native_loop_run_records_each_step_until_max_steps \
  tests/test_execution_dispatch_contract.py::test_ticket_native_loop_run_stops_at_approval_gate -q
```

结果：

- `4 passed, 1 warning`

### 2026-06-18: Phase K slice - Ticket-level loop policy registry

已完成：

- 新增 Ticket-native loop policy registry：
  - 默认 policy。
  - Ticket `provider_metadata.loop_policy` override。
  - `.aiteamos/ticket_loop_policies.json` registry override。
- 新增 policy models：
  - `TicketLoopPolicy`
  - `TicketLoopPolicyUpdateRequest`
- 新增后端 API：
  - `GET /api/v1/tickets/{ticket_id}/loop/policy`
  - `PUT /api/v1/tickets/{ticket_id}/loop/policy`
- policy 控制项：
  - `max_steps`
  - `max_runtime_seconds`
  - `stop_statuses`
  - `allowed_capabilities`
  - `approval_requirements`
  - `validation_required`
- `run_loop` 会用 policy cap request：
  - request 可以要求更少 steps/runtime。
  - request 不能超过 Ticket policy 上限。
- `run_step` 会从 policy 读取：
  - capability grants
  - approval requirements
  - loop policy provenance
- policy update 会写入 registry，并追加 `loop_policy_updated` Ticket report，留下可审计 evidence 指向 `.aiteamos/ticket_loop_policies.json`。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/ticket_loop_service.py \
  services/api/aiteamos_api/read/ticket_routes.py \
  tests/test_execution_dispatch_contract.py

pytest tests/test_execution_dispatch_contract.py::test_ticket_loop_policy_registry_caps_run_and_controls_approval_policy \
  tests/test_execution_dispatch_contract.py::test_ticket_loop_policy_routes_read_and_update_registry \
  tests/test_execution_dispatch_contract.py::test_langgraph_executor_projects_ticket_loop_state_into_graph_state \
  tests/test_execution_dispatch_contract.py::test_ticket_native_loop_run_records_each_step_until_max_steps \
  tests/test_execution_dispatch_contract.py::test_ticket_native_loop_run_stops_at_approval_gate -q
```

结果：

- `5 passed, 1 warning`

### 2026-06-18: Phase K slice - governed loop control and session audit

已完成：

- 新增 Ticket-native loop control model：
  - `TicketLoopControlRequest`
  - `TicketLoopControlState`
  - `TicketLoopControlResponse`
- 新增后端 API：
  - `POST /api/v1/tickets/{ticket_id}/loop/control`
- 支持 control action：
  - `stop`
  - `pause`
  - `continue`
  - `cancel`
- 新增 `.aiteamos/ticket_loop_controls.json` control registry：
  - 每个 Ticket 保存 latest control state。
  - 同时保存 control event history。
- 新增 execution session control audit：
  - `control_state`
  - `control_events`
  - action 后 session status 映射为 `stopped`、`paused`、`cancelled`、`ready_to_continue`。
- `run_loop` 现在会在每一步前后检查 active control：
  - 遇到 `stop` / `pause` / `cancel` 会停止继续调度。
  - 返回 `stop_reason=control:{action}`。
  - `loop_state.control` 暴露 control provenance。
- control request 会写入 Ticket report：
  - `report_type=loop_control`
  - evidence 指向 `.aiteamos/ticket_loop_controls.json`
  - 通过 Ticket event ledger 的 `reported` event 留下审计记录。
- Dashboard Ticket detail 新增：
  - `Continue Loop`
  - `Stop Loop`
  - `Loop Control` 结果面板
- `Continue Loop` 会先写 `continue` control，再触发一次 bounded `Run Loop`。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/execution_session_store.py \
  services/api/aiteamos_api/read/ticket_loop_service.py \
  services/api/aiteamos_api/read/ticket_routes.py \
  tests/test_execution_dispatch_contract.py

pytest tests/test_execution_dispatch_contract.py::test_ticket_loop_control_stop_blocks_run_and_continue_unblocks_sessions \
  tests/test_execution_dispatch_contract.py::test_ticket_loop_control_route_records_ticket_report_and_session_control \
  tests/test_execution_dispatch_contract.py::test_ticket_loop_policy_registry_caps_run_and_controls_approval_policy -q

cd apps/dashboard && npm test -- tickets-page.test.tsx

pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py tests/test_file_memory_routes.py tests/test_runtime_executor_routes.py -q

cd apps/dashboard && npm run build
```

结果：

- `3 passed, 1 warning`
- `35 passed`
- `132 passed, 2 warnings`
- Dashboard build passed，仍有既有 Vite large chunk warning。

### 2026-06-18: Phase K slice - Dashboard pause/cancel loop controls

已完成：

- Dashboard Ticket detail 的 loop control 从 `Continue Loop` / `Stop Loop` 扩展为完整 control set：
  - `Continue Loop`
  - `Pause Loop`
  - `Stop Loop`
  - `Cancel Loop`
- `Pause Loop` / `Stop Loop` / `Cancel Loop` 都调用同一个 governed control API：
  - `POST /api/v1/tickets/{ticket_id}/loop/control`
  - 写入 Ticket report / control registry / session control audit。
- `Continue Loop` 仍然先写 `continue` control，再触发一次 bounded `Run Loop`。
- `Loop Control` 结果面板会展示：
  - control status
  - reason
  - action
  - updated session count
  - report id

验证：

```bash
cd apps/dashboard && npm test -- tickets-page.test.tsx
cd apps/dashboard && npm run build
```

结果：

- `36 passed`
- Dashboard build passed，仍有既有 Vite large chunk warning。

### 2026-06-18: Phase K slice - loop run registry and Ticket detail run list

已完成：

- 新增 Ticket-native loop run registry：
  - `.aiteamos/ticket_loop_runs.json`
  - 每次 `run_loop` 都写入 `TicketLoopRunRecord`。
- 新增 run record model：
  - `TicketLoopRunRecord`
  - `run_id`
  - `ticket_id`
  - `status`
  - `stop_reason`
  - `active`
  - request / response snapshot
  - step count
  - policy / control snapshot
  - queued / started / finished / updated time
- `run_loop` 现在会：
  - 在开始时写 `running` active record。
  - 在结束时写 final record。
  - 在 `loop_state` 返回 `run_id`。
- 新增后端 API：
  - `GET /api/v1/tickets/{ticket_id}/loop/runs`
  - `GET /api/v1/tickets/{ticket_id}/loop/runs/{run_id}`
- Dashboard Ticket detail 新增 `Loop Runs` 面板：
  - 展示最近 run id
  - active / status
  - step count
  - stop reason
  - updated time
- `Run Loop` / `Continue Loop` 后会刷新 run list。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/ticket_loop_service.py \
  services/api/aiteamos_api/read/ticket_routes.py \
  tests/test_execution_dispatch_contract.py

pytest tests/test_execution_dispatch_contract.py::test_ticket_native_loop_run_records_each_step_until_max_steps \
  tests/test_execution_dispatch_contract.py::test_ticket_loop_run_routes_list_and_detail_records \
  tests/test_execution_dispatch_contract.py::test_ticket_loop_control_stop_blocks_run_and_continue_unblocks_sessions -q

cd apps/dashboard && npm test -- tickets-page.test.tsx

pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py tests/test_file_memory_routes.py tests/test_runtime_executor_routes.py -q

cd apps/dashboard && npm run build
```

结果：

- `3 passed, 1 warning`
- `36 passed`
- `133 passed, 1 warning`
- Dashboard build passed，仍有既有 Vite large chunk warning。

### 2026-06-18: Phase K slice - loop queue and worker pump primitive

已完成：

- 新增 Ticket-native loop queue registry：
  - `.aiteamos/ticket_loop_queue.json`
  - 保存 queued / running / completed loop queue item。
- 新增 queue models：
  - `TicketLoopEnqueueRequest`
  - `TicketLoopQueueItem`
  - `TicketLoopQueuePumpRequest`
  - `TicketLoopQueuePumpResponse`
- 新增后端 API：
  - `POST /api/v1/tickets/{ticket_id}/loop/queue`
  - `GET /api/v1/tickets/loop/queue`
  - `POST /api/v1/tickets/loop/queue/pump`
- enqueue 会：
  - 生成 queue id / run id。
  - 写入 queued `TicketLoopRunRecord`，让 Dashboard 立即可见 queued run。
  - 写入 Ticket `loop_queued` report，evidence 指向 `.aiteamos/ticket_loop_queue.json`。
- pump 会：
  - 按 priority / enqueued time 取 queued item。
  - 将 item 标记为 running。
  - 调用现有 `TicketAutonomousLoopService.run_loop`，不在 route 层实现 agent loop。
  - 将 item 更新为 completed / needs_approval / failed 等最终状态。
  - 保持 run registry 与 queue registry 的状态联动。
- Dashboard `Loop Runs` 面板现在会直接展示 `queued` / `running` / `completed` 等 run status，而不是只显示 active。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/ticket_loop_service.py \
  services/api/aiteamos_api/read/ticket_routes.py \
  tests/test_execution_dispatch_contract.py

pytest tests/test_execution_dispatch_contract.py::test_ticket_loop_queue_enqueue_and_pump_runs_existing_loop_service \
  tests/test_execution_dispatch_contract.py::test_ticket_loop_queue_routes_enqueue_list_and_pump \
  tests/test_execution_dispatch_contract.py::test_ticket_native_loop_run_records_each_step_until_max_steps -q

cd apps/dashboard && npm test -- tickets-page.test.tsx

pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py tests/test_file_memory_routes.py tests/test_runtime_executor_routes.py -q

cd apps/dashboard && npm run build
```

结果：

- `3 passed, 1 warning`
- `36 passed`
- `135 passed, 1 warning`
- Dashboard build passed，仍有既有 Vite large chunk warning。

### 2026-06-18: Phase K slice - queue status and worker health visibility

已完成：

- 新增 queue status model：
  - `TicketLoopQueueStatus`
- 新增后端 API：
  - `GET /api/v1/tickets/loop/queue/status`
- queue status 从 queue registry 派生：
  - queued / running / completed / failed count
  - active count
  - total count
  - oldest queued time
  - latest activity time
  - next queue / Ticket / run id
  - queue / run registry saved paths
- Dashboard 右侧栏新增 `Loop Queue` 卡片：
  - 展示 queue status
  - queued / running / completed / failed 指标
  - next run / Ticket
  - `Pump Queue` 控制按钮
  - pump 结果摘要
- `Pump Queue` 调用：
  - `POST /api/v1/tickets/loop/queue/pump`
  - 处理后刷新 Tickets、queue status 和当前 Ticket loop runs。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/ticket_loop_service.py \
  services/api/aiteamos_api/read/ticket_routes.py \
  tests/test_execution_dispatch_contract.py

pytest tests/test_execution_dispatch_contract.py::test_ticket_loop_queue_enqueue_and_pump_runs_existing_loop_service \
  tests/test_execution_dispatch_contract.py::test_ticket_loop_queue_routes_enqueue_list_and_pump -q

cd apps/dashboard && npm test -- tickets-page.test.tsx

pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py tests/test_file_memory_routes.py tests/test_runtime_executor_routes.py -q

cd apps/dashboard && npm run build
```

结果：

- `2 passed, 1 warning`
- `37 passed`
- `135 passed, 1 warning`
- Dashboard build passed，仍有既有 Vite large chunk warning。

### 2026-06-18: Phase K slice - cross-Ticket loop queue tab

已完成：

- Dashboard Tickets 新增独立 `Queue` tab：
  - 作为跨 Ticket 的 autonomous loop queue cockpit。
  - 使用现有 `GET /api/v1/tickets/loop/queue` 和 `GET /api/v1/tickets/loop/queue/status`。
  - 展示 queued / running / completed / failed / total 指标。
  - 展示 queue item 的 status、run id、queue id、Ticket id、priority、reason / error 和 updated time。
  - 提供 `Pump Queue` 控制，复用 queue pump contract。
  - 每个 queue item 提供 `Ticket` 按钮，可跳转回对应 Ticket overview。
- Dashboard API client 新增：
  - `TicketLoopQueueItem`
  - `listTicketLoopQueue(status = "")`
- Tickets page load / pump 后会刷新 queue items，让右侧 health card 和 Queue tab 保持一致。
- 测试 fixture 覆盖 queued / completed queue items，并验证 Queue tab 可见、可导航。

验证：

```bash
cd apps/dashboard && npm test -- tickets-page.test.tsx

cd apps/dashboard && npm run build

pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py tests/test_file_memory_routes.py tests/test_runtime_executor_routes.py -q
```

结果：

- `38 passed`
- Dashboard build passed，仍有既有 Vite large chunk warning。
- `135 passed, 1 warning`

### 2026-06-18: Phase K slice - loop run detail drill-in

已完成：

- Dashboard Ticket workspace 的 `Loop Runs` 列表新增 `Details` 操作：
  - 点击后调用既有后端 detail endpoint：
    - `GET /api/v1/tickets/{ticket_id}/loop/runs/{run_id}`
  - 不复用列表简略对象，确保 drill-in 来自可审计 run registry detail contract。
- Dashboard API client 新增：
  - `getTicketLoopRun(ticketId, runId)`
- 详情面板展示：
  - run id / Ticket id / status / active
  - step count / stop reason
  - saved path
  - request snapshot
  - response snapshot
  - policy snapshot
  - control snapshot
- 测试 fixture 覆盖 detail endpoint，并验证 Dashboard 可以从 Ticket workspace drill into 某次 loop run。

验证：

```bash
cd apps/dashboard && npm test -- tickets-page.test.tsx

cd apps/dashboard && npm run build

pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py tests/test_file_memory_routes.py tests/test_runtime_executor_routes.py -q
```

结果：

- `39 passed`
- Dashboard build passed，仍有既有 Vite large chunk warning。
- `135 passed, 2 warnings`

### 2026-06-18: Phase K slice - loop queue worker daemon contract

已完成：

- 新增 Ticket loop queue worker daemon contract：
  - `TicketLoopQueueWorker`
  - `TicketLoopQueueWorkerControlRequest`
  - `TicketLoopQueueWorkerStatus`
  - `TicketLoopQueueWorkerTickResponse`
- worker 复用既有 governed queue pump：
  - 后台 daemon tick 调用 `pump_ticket_loop_queue`。
  - 每次处理仍然通过 `TicketAutonomousLoopService.run_loop`。
  - 不在 route 层或 Dashboard 内自研 agent loop。
- 新增 worker 状态 registry：
  - `.aiteamos/ticket_loop_queue_worker.json`
  - 记录 status / running / interval / max_items / last_tick / total_ticks / total_processed / last_error / last_control_reason。
- 新增后端 API：
  - `GET /api/v1/tickets/loop/queue/worker/status`
  - `POST /api/v1/tickets/loop/queue/worker/start`
  - `POST /api/v1/tickets/loop/queue/worker/stop`
  - `POST /api/v1/tickets/loop/queue/worker/tick`
- Dashboard `Queue` tab 新增 Worker Daemon 面板：
  - 展示 worker status、state path、tick count、processed count、last tick、interval。
  - 支持 `Start Worker` / `Stop Worker` / `Tick Worker`。
  - `Tick Worker` 后刷新 Tickets、queue items、queue status 和当前 Ticket loop runs。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/ticket_loop_service.py \
  services/api/aiteamos_api/read/ticket_routes.py \
  tests/test_execution_dispatch_contract.py

pytest tests/test_execution_dispatch_contract.py::test_ticket_loop_queue_worker_daemon_pumps_queue_and_records_status \
  tests/test_execution_dispatch_contract.py::test_ticket_loop_queue_worker_routes_status_and_tick -q

cd apps/dashboard && npm test -- tickets-page.test.tsx

cd apps/dashboard && npm run build

pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py tests/test_file_memory_routes.py tests/test_runtime_executor_routes.py -q
```

结果：

- `2 passed, 1 warning`
- `40 passed`
- Dashboard build passed，仍有既有 Vite large chunk warning。
- `137 passed, 1 warning`

### 2026-06-18: Phase K slice - in-flight external CLI runtime interrupt

已完成：

- 外部 CLI RuntimeExecutor 现在支持 Ticket control 的 in-flight interrupt：
  - CLI 进程启动后立即写入 active execution session。
  - session 写入包含 executor id、executor session ref、checkpoint ref、thread id、Ticket id、request id 和 `status=running`。
  - 执行期间并行运行 control watcher。
  - watcher 读取 `.aiteamos/execution_sessions.json` 中对应 session 的 `control_state`。
  - 发现 `stop` / `pause` / `cancel` 后会 terminate / kill 正在运行的 CLI process。
  - RuntimeExecutor 返回 `status=cancelled`，而不是等到进程自然结束或只在下一步 loop 边界停止。
- `save_execution_session` 现在保留既有 `control_state` / `control_events`：
  - 避免最终 session 保存覆盖掉中断审计。
- cancelled result 会携带：
  - `errors[0].reason=external_runtime_interrupted`
  - control action / reason
  - `learning_delta.interrupt.in_flight=true`
  - `runtime.external.cli.interrupted` tool event
- 新增测试用 slow fake Claude Code-compatible CLI：
  - 启动 dispatch。
  - 等 active session 出现。
  - 通过 Ticket control 写入 `stop`。
  - 验证 CLI 被提前中断，结果为 `cancelled`，且 session 保留 control audit。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/runtime_executors/external_runtime_executor.py \
  services/api/aiteamos_api/read/execution_session_store.py \
  tests/test_execution_dispatch_contract.py

pytest tests/test_execution_dispatch_contract.py::test_external_cli_runtime_is_interrupted_by_ticket_control_in_flight -q

pytest tests/test_execution_dispatch_contract.py::test_claude_code_compatible_cli_runs_non_destructive_inspect_and_receives_deepseek_config \
  tests/test_execution_dispatch_contract.py::test_claude_code_compatible_cli_missing_report_is_blocked_contract_result \
  tests/test_execution_dispatch_contract.py::test_claude_code_compatible_cli_failure_returns_failed_result \
  tests/test_execution_dispatch_contract.py::test_external_cli_runtime_is_interrupted_by_ticket_control_in_flight -q

pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py tests/test_file_memory_routes.py tests/test_runtime_executor_routes.py -q
```

结果：

- `1 passed, 1 warning`
- `4 passed, 1 warning`
- `138 passed, 1 warning`

### 2026-06-18: Phase K slice - in-flight external HTTP runtime cancellation

已完成：

- 外部 HTTP/API RuntimeExecutor 现在支持 Ticket control 的 in-flight request cancellation：
  - HTTP request 发出前立即写入 active execution session。
  - session 写入包含 executor id、executor session ref、checkpoint ref、thread id、Ticket id、request id 和 `status=running`。
  - 执行期间并行等待 HTTP request 与 control watcher。
  - watcher 读取 `.aiteamos/execution_sessions.json` 中对应 session 的 `control_state`。
  - 发现 `stop` / `pause` / `cancel` 后会 cancel 本地 HTTP request task。
  - RuntimeExecutor 返回 `status=cancelled`，不会等到 HTTP provider 自然返回，也不会只在下一步 loop 边界停止。
- cancelled result 会携带：
  - `errors[0].reason=external_runtime_interrupted`
  - control action / reason
  - `learning_delta.interrupt.in_flight=true`
  - `learning_delta.interrupt.request_cancelled=true`
  - `runtime.external.http.interrupted` tool event
- 新增测试用 slow fake Cursor HTTP adapter：
  - 启动 dispatch。
  - 等 active session 出现。
  - 通过 Ticket control 写入 `cancel`。
  - 验证 HTTP request task 被取消，结果为 `cancelled`，且 session 保留 control audit。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/runtime_executors/external_runtime_executor.py \
  tests/test_execution_dispatch_contract.py

pytest tests/test_execution_dispatch_contract.py::test_external_http_runtime_request_is_cancelled_by_ticket_control_in_flight -q

pytest tests/test_execution_dispatch_contract.py::test_cursor_executor_runs_configured_http_inspect \
  tests/test_execution_dispatch_contract.py::test_external_http_runtime_request_is_cancelled_by_ticket_control_in_flight \
  tests/test_execution_dispatch_contract.py::test_cursor_http_invalid_runtime_status_is_failed_contract_result -q

pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py tests/test_file_memory_routes.py tests/test_runtime_executor_routes.py -q
```

结果：

- `1 passed, 1 warning`
- `3 passed, 1 warning`
- `139 passed, 1 warning`

Phase K 当前状态：

- 已有 queue/enqueue/pump primitive、worker health visibility 和可启动/停止的后台 worker daemon contract；后续仍可增加生产化 autostart / multi-worker lease / backoff 策略。
- Dashboard Ticket detail 已有 `Run Loop` / `Continue Loop` / `Pause Loop` / `Stop Loop` / `Cancel Loop`。
- `stop` / `pause` / `cancel` 已进入 session + Ticket report 审计，并且已能中断正在执行中的外部 CLI runtime step，也能 cancel 正在执行中的 HTTP/API request task。
- 已有 Ticket detail 的 loop run list、loop run detail drill-in、右侧 queue health card、独立跨 Ticket `Queue` tab、worker daemon controls、external CLI in-flight interrupt 和 external HTTP in-flight request cancellation。
- Phase K 核心验收已覆盖；生产化 autostart / multi-worker lease / backoff / provider-native remote cancellation 可作为 Phase P hardening 或 provider-specific Phase M conformance 继续深化。

## 10. Phase L: Tool / Skill Governance

目标：让 Skills 和 Tooling calls 成为 Assets 和 governed capabilities，而不是散落的 helper。

任务：

1. 建立 `ToolCapabilityRecord`：
   - id
   - domain
   - read/write/destructive
   - required approval
   - provider
   - schema
   - output asset policy
2. Skills 进入 Asset Registry：
   - skill doc
   - owner employee
   - examples
   - validation command
   - last used
   - usefulness stats
3. LangGraph tools 从 governed registry 暴露。
4. Tool call result 可生成 `tool_call_asset`。
5. 高风险 tool 默认只产 approval request，不直接执行。

验收：

- Agent 调用任何 tool 都能在 replay 和 Assets 里查到 provenance。
- Skill 可被 Employee 自动检索、引用、使用、反馈。
- Tool 权限不在 prompt 里硬编码，而由 registry / policy 决定。

### 2026-06-18: Phase L slice - governed capability policy fields

已完成：

- `CapabilityRecord` 扩展为 ToolCapabilityRecord 的第一版 contract：
  - `access`
  - `destructive`
  - `required_approval`
  - `provider`
  - `schema`（内部字段为 `tool_schema`，API alias 保持 `schema`）
  - `output_asset_policy`
- capability registry 输出时会自动补齐治理策略：
  - permissions -> read / write / destructive
  - `repo:write` / `terminal:run` / destructive -> approval hints
  - arguments -> JSON-like input schema
  - produces -> output asset policy / candidate asset types
- Dashboard capability API 类型已同步。

验证：

```bash
pytest tests/test_file_capability_routes.py -q

pytest tests/test_file_capability_routes.py tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py tests/test_runtime_executor_routes.py

cd apps/dashboard && npm run build
```

结果：

- `2 passed, 1 warning`
- `104 passed, 1 warning`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

Phase L 仍未完成：

- LangGraph tools 还没有完全从 capability registry 动态暴露。
- Tool call result 还没有系统性生成 `tool_call_asset`。
- Skill usage / last used / usefulness stats 还没有闭环。
- 高风险 tool 的 approval policy 还只是 registry hint，尚未统一接到所有执行路径。

### 2026-06-18: Phase L slice - registry-driven LangGraph tool exposure

已完成：

- 将 LangGraph Universal Employee Agent 的只读 context tools 注册为 capability registry 中的 `native_api` tools：
  - `universal_agent.get_employee_context`
  - `universal_agent.search_tickets`
  - `universal_agent.get_ticket_context`
  - `universal_agent.search_assets`
  - `universal_agent.search_memory`
  - `universal_agent.inspect_system_status`
- `CapabilityRegistryStatus.native_api_tool_count` 开始反映 native API tools。
- `UniversalAgentToolRegistry` 不再只依赖硬编码名称；它会从 `list_capabilities()` 投影可暴露工具 manifest，并只暴露：
  - enabled / configured / ready
  - read-only
  - non-destructive
  - no required approval
- LangGraph `read_context_tools` 节点会记录 `runtime.load_tools` event，明确来源为 `capability_registry`，并记录 loaded tool manifest。
- Universal Agent tool event 会携带：
  - `capability`
  - `command`
  - `output_asset_policy`
  - `record_as_asset`
- Universal Agent tool calls 现在会通过既有 execution result ingestion 生成 `tool_call` Asset candidates。
- 修复 Chat metadata / trace 语义：
  - result ingestion 产生的 `memory.candidates:propose` / `asset.candidates:propose` 不再被算作 Chat 主动 Kernel command。
  - tool-call candidates 不会阻止同一 run 生成 ticket-aware chat memory candidate。

验证：

```bash
pytest tests/test_file_capability_routes.py -q

pytest tests/test_execution_dispatch_contract.py::test_universal_agent_tool_registry_searches_tickets_with_provenance tests/test_execution_dispatch_contract.py::test_langgraph_executor_answer_calls_read_only_context_tools tests/test_execution_dispatch_contract.py::test_langgraph_executor_records_structured_read_tool_failure tests/test_execution_dispatch_contract.py::test_execution_tool_events_enter_asset_candidate_review_queue -q

pytest tests/test_file_chat_routes.py tests/test_execution_dispatch_contract.py tests/test_file_capability_routes.py tests/test_file_memory_routes.py tests/test_runtime_executor_routes.py -q
```

结果：

- `2 passed, 1 warning`
- `4 passed, 1 warning`
- `141 passed, 2 warnings`

Phase L 剩余：

- Skill usage / last used / usefulness stats 还没有闭环。
- 高风险 tool 的 approval policy 还只是 registry hint，尚未统一接到所有执行路径。
- `tool_call_asset` 已覆盖 Universal Agent read tools 和显式 `record_as_asset` tool events；后续还需要把 provider / MCP / external runtime 的 tool result conformance 统一到 Phase M/P。

### 2026-06-18: Phase L slice - Skill usage ledger and Asset projection

已完成：

- 新增 Skill usage ledger：
  - 保存位置：`.aiteamos/assets/skill_usage.json`
  - 记录字段：skill_id / employee_id / run_id / thread_id / ticket_keys / trace_path / usefulness_status / provenance / used_at
- Chat 响应持久化时会记录 Employee 已加载 Skill 的使用事实：
  - trace event: `skill.usage.recorded`
  - run metadata: `skill_usage_refs`
- `/api/v1/chat/skills` 的 `ChatSkillSummary` 开始返回：
  - `usage_count`
  - `last_used_at`
  - `last_used_by_employee_id`
  - `last_used_run_id`
  - `last_used_ticket_id`
  - `usefulness_stats`
  - `usage_history`
- `/api/v1/assets/capabilities/skills` 的 Skill asset metadata 同步投影 Skill usage summary。
- Dashboard Skills 表格和详情页显示 usage count、last used、latest ticket、usefulness stats。

验证：

```bash
pytest tests/test_file_chat_routes.py::test_chat_records_skill_usage_into_skill_assets -q

pytest tests/test_file_chat_routes.py tests/test_execution_dispatch_contract.py tests/test_file_capability_routes.py tests/test_file_memory_routes.py tests/test_runtime_executor_routes.py tests/test_file_knowledge_and_tickets.py::test_builtin_validation_skills_are_queryable_capability_assets -q

cd apps/dashboard && npm run build
```

结果：

- `1 passed, 1 warning`
- `143 passed, 4 warnings`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

Phase L 剩余：

- 高风险 tool 的 approval policy 还只是 registry hint，尚未统一接到所有执行路径。
- Skill usefulness 目前先记录为 `unreviewed` usage stats；后续可以增加 Clara/PV 对 Skill usage 的 usefulness review endpoint。
- `tool_call_asset` 已覆盖 Universal Agent read tools 和显式 `record_as_asset` tool events；后续还需要把 provider / MCP / external runtime 的 tool result conformance 统一到 Phase M/P。

### 2026-06-18: Phase L slice - registry-backed terminal approval gate

已完成：

- `ChatGovernanceService` 的 approval policy 不再只使用固定高风险列表；`terminal_run` 会读取 capability registry 中 `terminal.run.required_approval`，把 `terminal:run` / `destructive_tool_call` 纳入 `require_approval_for`。
- `LocalToolExecutor.terminal_run` 现在先完成 Ticket binding、capability grant、command、cwd、workspace boundary 校验；如果 `terminal:run` 未审批，只返回 `needs_approval`，不会执行命令。
- terminal approval request 保存：
  - `kind=terminal_run`
  - `required_capability=terminal:run`
  - `risk_level=high`
  - `proposed_action.command_line`
  - `checkpoint_ref`
  - `executor_session_ref`
  - `source_state_ref`
  - `current_graph_node=terminal_run_approval_gate`
- Chat route 传入任意 `approval_ref` 时统一走 `ExecutionApprovalRunService`，不仅限于 `implement_ticket`；审批后的 `local_tool` run 会通过 runtime approval endpoint 恢复执行并写入 Ticket evidence。
- `ExecutionResultIngestionService` 现在把 Chat 产生的 approval records 写到 runtime approval workspace root，避免 `.aiteamos` 与 workspace root 双路径导致 Dashboard / runtime route 看不到审批。
- `execution_state_snapshot` 的 `source_state_snapshot_ref` 改为相对 approval workspace 自身，runtime approval route 和 replay 能稳定解析 snapshot。

验证：

```bash
pytest tests/test_file_chat_routes.py::test_clara_can_run_allowlisted_terminal_command_as_ticket_evidence tests/test_file_chat_routes.py::test_terminal_command_streams_progress -q

pytest tests/test_execution_dispatch_contract.py::test_terminal_run_is_ticket_bound_and_records_evidence -q

pytest tests/test_execution_dispatch_contract.py::test_chat_governance_routes_ticket_implementation_to_external_runtime_approval -q

pytest tests/test_runtime_executor_routes.py::test_approved_claude_code_runtime_run_uses_approval_ref_and_ingests_repo_mutation -q

pytest tests/test_execution_dispatch_contract.py tests/test_runtime_executor_routes.py -q

pytest tests/test_file_chat_routes.py tests/test_execution_dispatch_contract.py tests/test_file_capability_routes.py tests/test_file_memory_routes.py tests/test_runtime_executor_routes.py tests/test_file_knowledge_and_tickets.py::test_builtin_validation_skills_are_queryable_capability_assets -q
```

结果：

- Chat terminal focused tests: `2 passed, 1 warning`
- terminal dispatch focused test: `1 passed, 1 warning`
- Chat governance approval focused test: `1 passed, 1 warning`
- runtime approval focused test: `1 passed, 1 warning`
- execution dispatch + runtime executor suite: `87 passed, 1 warning`
- broader backend suite: `143 passed, 2 warnings`

Phase L 剩余：

- 高风险 tool approval 已覆盖 `terminal.run` 本地执行路径；provider / MCP / external runtime 的 tool result 和 approval conformance 仍应进入 Phase M/P。
- capability registry 仍需要更细的 operation-level 权限粒度，例如 `employees.manage` 下不同 mutation 操作的独立审批策略。

### 2026-06-19: Phase L slice - Skill usage usefulness review endpoint

已完成：

- `skill_usage_service.py` 新增 Skill usage review contract：
  - `SkillUsageReviewRequest`
  - `SkillUsageReviewResponse`
  - `review_skill_usage`
- Skill usage usefulness 状态与 Memory recall feedback 对齐：
  - `used`
  - `irrelevant`
  - `harmful`
  - `promoted`
  - `unreviewed`
  - 兼容 aliases：`useful`、`not_useful`、`neutral`、`promote`
- 新增 Assets capabilities 侧治理入口：
  - `POST /api/v1/assets/capabilities/skills/usage/{usage_id}/review`
- review 后会更新 `.aiteamos/assets/skill_usage.json`：
  - `usefulness_status`
  - reviewer employee
  - review reason
  - reviewed timestamp
  - review history
- `/api/v1/chat/skills` 与 `/api/v1/assets/capabilities/skills` 的 Skill asset projection 会同步展示：
  - `used_count`
  - `irrelevant_count`
  - `harmful_count`
  - `promoted_count`
  - `unreviewed_count`
  - latest reviewer / review time
- Chat route 仍只负责入口和上下文；Skill usage review 写入发生在 Assets governance API 下。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/skill_usage_service.py \
  services/api/aiteamos_api/read/asset_routes.py \
  tests/test_file_chat_routes.py

pytest tests/test_file_chat_routes.py::test_chat_records_skill_usage_into_skill_assets -q
```

结果：

- focused Skill usage review test: `1 passed, 1 warning`

Phase L 剩余：

- 高风险 tool approval 已覆盖 `terminal.run` 本地执行路径；provider / MCP / external runtime 的 tool result 和 approval conformance 仍应进入 Phase M/P。
- capability registry 仍需要更细的 operation-level 权限粒度，例如 `employees.manage` 下不同 mutation 操作的独立审批策略。

### 2026-06-19: Phase L slice - operation-level capability policies

已完成：

- `CapabilityRecord` 新增 `operation_policies`，保留既有 capability-level `access` / `destructive` / `required_approval` 兼容字段。
- Kernel command capability 的 operation policies 现在由 `KERNEL_COMMAND_SPECS` 自动投影：
  - `command_id`
  - `access`
  - `destructive`
  - `required_approval`
  - `permissions`
  - `risk`
  - `streaming`
  - `description`
- `employees.manage` 已能区分：
  - `list`: read / no approval
  - `create`: write / no approval
  - `update`: write / no approval
  - `delete`: destructive / `destructive_tool_call`
- `assets.manage` 已能区分：
  - `list_skills`: read / no approval
  - `create_skill`: write / no approval
  - `assign_skill`: write / no approval
  - `delete_skill`: destructive / `destructive_tool_call`
- `terminal.run:run` operation policy 暴露为 destructive execution，并要求 `terminal:run` + `destructive_tool_call`。
- `CapabilityRecord.provider` 默认值改为空，由 governance enrichment 按 source_kind / connector_id 填充，避免 MCP connector 被误投影为 `aiteamos_kernel` provider。
- 新增 capability policy helper：
  - `capability_operation_policy`
  - `capability_operation_policy_for_command`
  - `capability_required_approval_for_operation`
  - `capability_required_approval_for_command`
- `ChatGovernanceService` 的 approval policy 现在通过 `CHAT_ACTION_TO_COMMAND_ID` 读取 operation-level approval requirements；不再只读取旧的 capability-level 字段。
- Dashboard capability API 类型同步新增 `operation_policies`。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/capability_service.py \
  services/api/aiteamos_api/read/chat_governance_service.py \
  tests/test_file_capability_routes.py

pytest tests/test_file_capability_routes.py -q

pytest tests/test_execution_dispatch_contract.py::test_terminal_run_is_ticket_bound_and_records_evidence -q

pytest tests/test_file_chat_routes.py::test_clara_can_run_allowlisted_terminal_command_as_ticket_evidence \
  tests/test_file_chat_routes.py::test_terminal_command_streams_progress -q

pytest tests/test_file_chat_routes.py::test_employee_chat_deletes_employee_with_local_tool \
  tests/test_file_chat_routes.py::test_employee_chat_blocks_deleting_clara -q

cd apps/dashboard && npm run build
```

结果：

- py_compile passed。
- capability route tests: `3 passed, 1 warning`
- terminal dispatch focused test: `1 passed, 1 warning`
- Chat terminal focused tests: `2 passed, 1 warning`
- Employee delete focused tests: `2 passed, 1 warning`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

Phase L 剩余：

- operation-level policy 已在 registry / governance request 层落地；非 terminal 的 destructive operation 仍未统一接入 `needs_approval` interrupt gate，后续可以在 Phase M/P 的 provider/runtime conformance 中一起收口。
- provider / MCP / external runtime 的 tool result、tool_call_asset、approval conformance 仍应进入 Phase M/P。

## 11. Phase M: Provider Adapter Conformance

目标：让 Plane、Graphiti、商业 Agent Runtime 都成为可替换 provider，而不是写死的实现细节。

任务：

1. 定义 adapter contract：
   - TicketProvider
   - AssetProvider
   - MemoryProvider
   - EmployeeProvider
   - RuntimeProvider
2. 每个 provider 必须有：
   - status
   - setup blockers
   - capabilities
   - conformance smoke
   - projection direction
   - failure semantics
3. Plane adapter：
   - create / update ticket
   - append report comment
   - assignment / handoff
   - validation state projection
4. Graphiti adapter：
   - approved asset projection
   - memory recall
   - relationship search
   - disabled fallback
5. Commercial runtime adapter：
   - request contract
   - result contract
   - approval / checkpoint semantics
   - evidence requirements

验收：

- Provider missing config 时 UI 显示 setup blocker，不制造假成功。
- 本地 provider 和外部 provider 跑同一套 conformance tests。
- Plane / Graphiti 开关不改变 AITeamOS 的核心 Ticket / Asset / Employee 语言。

### 2026-06-18: Phase M slice - Provider Adapter Conformance read model

已完成：

- 新增 `ProviderConformanceRecord` / `ProviderConformanceResponse` 第一版 contract：
  - `provider_kind`
  - `implementation`
  - `status`
  - `setup_blockers`
  - `capabilities`
  - `conformance_smoke`
  - `projection_direction`
  - `failure_semantics`
  - `domain_boundary`
  - `fallback_provider`
  - `provider_ref`
- 新增 `ProviderConformanceService`，统一汇总：
  - TicketProvider：Plane / local_file Ticket adapter 状态、能力、setup blocker、fallback。
  - AssetProvider：local Asset Candidate registry 作为 Graphiti disabled fallback。
  - MemoryProvider：Graphiti projection / recall / relationship search 状态和缺配置 blocker。
  - EmployeeProvider：local Employee profiles、v2 profile fields、work ledger projection。
  - RuntimeProvider：所有 RuntimeExecutor 的 health、smoke endpoint、repo:write approval / evidence failure semantics。
- System Status API 增加：
  - `provider_conformance`
  - `GET /api/v1/system-status/providers`
- Dashboard System Status 增加 `Provider Adapter Conformance` 面板：
  - provider 列表
  - setup blockers
  - conformance smoke endpoint
  - projection direction
  - failure semantics
  - fallback provider
- Plane / Graphiti / RuntimeExecutor 缺配置时现在能在同一套 provider contract 中暴露 blocker，不制造假成功。

验证：

```bash
pytest tests/test_file_system_status_routes.py -q

pytest tests/test_file_system_status_routes.py tests/test_runtime_executor_routes.py -q

pytest tests/test_file_system_status_routes.py tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py tests/test_runtime_executor_routes.py -q

cd apps/dashboard && npm test -- system-status-page.test.tsx

cd apps/dashboard && npm run build
```

结果：

- `1 passed, 1 warning`
- `15 passed, 1 warning`
- `103 passed, 1 warning`
- `28 passed`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

### 2026-06-18: Phase M slice - provider contract expectations and UI guards

已完成：

- `ProviderConformanceRecord` 新增 `contract_expectations`：
  - `id`
  - `category`
  - `required`
  - `satisfied`
  - `missing`
  - `status`
- TicketProvider / AssetProvider / MemoryProvider / EmployeeProvider / RuntimeProvider 都声明了各自的 AITeamOS 边界 contract：
  - required capabilities
  - required failure semantics
  - required domain boundary
  - runtime projection direction
  - repo-write runtime guard
- `/api/v1/system-status/providers/checks` 不再只检查字段存在；现在会把缺失的 `contract_expectations` 或 missing contract 项作为 conformance failure。
- Runtime provider contract 明确：
  - RuntimeProvider 在 `ExecutionRequest` / `ExecutionResult` 后面执行。
  - Chat route 只做入口 / bridge，不承载 agent loop。
  - 写操作必须返回 governed artifacts，并通过 ingestion 写入 Ticket / Assets / evidence。
- Dashboard System Status 的 Provider Adapter Conformance 面板新增 `Contract Guards`，能直接看到 provider contract 是否通过。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/provider_conformance_service.py services/api/aiteamos_api/read/system_status_routes.py

pytest tests/test_file_system_status_routes.py -q

cd apps/dashboard && npm test -- system-status-page.test.tsx

pytest tests/test_file_system_status_routes.py tests/test_runtime_executor_routes.py tests/test_execution_dispatch_contract.py tests/test_file_memory_routes.py tests/test_file_knowledge_and_tickets.py -q

cd apps/dashboard && npm run build
```

结果：

- system-status backend test: `1 passed, 1 warning`
- dashboard tests: `40 passed`
- broader provider/backend suite: `122 passed, 2 warnings`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

Phase M 仍未完成：

- Plane / Graphiti 的外部真实服务 smoke 仍依赖配置，不在本 slice 中执行真实 provider 调用。
- EmployeeProvider 仍是 local profile provider，没有外部 Employee provider adapter。
- Provider contract 尚未接入迁移 / schema version / production evaluation harness。

### 2026-06-18: Phase M slice - non-destructive provider smoke harness

已完成：

- 新增 provider conformance smoke contract：
  - `ProviderConformanceSmokeRecord`
  - `ProviderConformanceSmokeResponse`
- 新增后端 API：
  - `GET /api/v1/system-status/providers/smoke`
- smoke harness 默认不调用外部服务、不写 Ticket / Asset / Employee，只执行当前 adapter 的 read-only 状态 / health 检查：
  - TicketProvider：读取 `ticket_backend_status`
  - AssetProvider：检查本地 Asset Registry contract
  - EmployeeProvider：检查本地 Employee provider contract
  - MemoryProvider：读取 Graphiti backend status
  - RuntimeProvider：读取 RuntimeExecutor health / provider_ref
- 缺配置 provider 返回 blocker 和真实状态，例如 `ticket:plane=setup_blocked`、`memory:graphiti=disabled`，同时保留 `no_fake_success_for_blocked_provider` check。
- System Status 的 Provider Adapter Conformance 面板新增 provider-level `Smoke` 按钮和 smoke result 摘要：
  - provider count / blocked / failed
  - no external calls
  - evaluation scope
  - 每个 provider card 显示 `Provider Smoke`、smoke kind、warnings / failures。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/provider_conformance_service.py services/api/aiteamos_api/read/system_status_routes.py

pytest tests/test_file_system_status_routes.py -q

cd apps/dashboard && npm test -- system-status-page.test.tsx

pytest tests/test_file_system_status_routes.py tests/test_runtime_executor_routes.py tests/test_execution_dispatch_contract.py tests/test_file_memory_routes.py tests/test_file_knowledge_and_tickets.py -q

cd apps/dashboard && npm run build

test ! -e langgraph
```

结果：

- system-status backend test: `1 passed, 1 warning`
- dashboard tests: `41 passed`
- broader provider/backend suite: `122 passed, 2 warnings`
- main backend regression with Chat / Runtime / Memory / System Status: `144 passed, 2 warnings`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。
- repo root `langgraph/` artifact 未生成。

### 2026-06-18: Phase M slice - opt-in external Plane / Graphiti smoke

已完成：

- Provider smoke harness 支持显式 `include_external=true`：
  - 默认 `/api/v1/system-status/providers/smoke` 仍然不打外部服务。
  - `/api/v1/system-status/providers/smoke?include_external=true` 才会触发已配置 provider 的外部 read-only smoke。
- Plane TicketProvider 增加 adapter-level external smoke：
  - 缺配置时返回 setup blocker，不发外部请求。
  - 配置 ready 时调用 Plane project `GET /work-items/`，只读、不创建/更新 Ticket。
  - 成功返回 `plane_project_work_items_read`、`plane_external_call_completed` 和 redacted evidence。
  - 失败返回 `plane_external_smoke_failed`，不会假成功。
- Graphiti MemoryProvider 增加 provider-level external smoke：
  - 缺配置时返回 setup blocker，不构造外部 client。
  - 配置 ready 时执行 read-only `search("AITeamOS provider conformance smoke")`，不写 episode、不投影 Asset。
  - 成功返回 `graphiti_read_search`、`graphiti_external_call_completed`、group_id 和 result_count。
  - 失败返回 `graphiti_external_smoke_failed`，不会假成功。
- Dashboard Provider Adapter Conformance 面板新增显式 `External Smoke` 按钮；普通 `Smoke` 仍保持本地/adapter health 检查。
- Provider Smoke UI 开始显示前几个 `checks`，能看见 `plane_project_work_items_read` 等真实检查项。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/provider_conformance_service.py services/api/aiteamos_api/read/system_status_routes.py services/api/aiteamos_api/read/ticket_service.py services/api/aiteamos_api/read/memory_service.py

pytest tests/test_file_system_status_routes.py -q

cd apps/dashboard && npm test -- system-status-page.test.tsx

pytest tests/test_file_system_status_routes.py tests/test_runtime_executor_routes.py tests/test_execution_dispatch_contract.py tests/test_file_memory_routes.py tests/test_file_knowledge_and_tickets.py -q

cd apps/dashboard && npm run build
```

结果：

- system-status backend tests: `2 passed, 2 warnings`
- dashboard tests: `42 passed`
- broader provider/backend suite: `123 passed, 2 warnings`
- main backend regression with Chat / Runtime / Memory / System Status: `145 passed, 2 warnings`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

### 2026-06-18: Phase M slice - environment smoke readiness API / UI

已完成：

- 新增 environment-level smoke contract：
  - `GET /api/v1/system-status/environment-smoke`
  - `GET /api/v1/system-status/environment-smoke?include_external=true`
- Environment smoke 聚合四类核心 readiness：
  - DeepSeek / Direct LLM 配置检查，不发模型 API 调用。
  - Provider adapter smoke 汇总，复用 `/providers/smoke`，不绕过 provider contract。
  - Local fallback 检查：local Asset Registry、local Employee profiles、Ticket local_file fallback、Memory -> Asset fallback。
  - LangGraph / Universal Employee Agent runtime 检查，确认 agent loop 仍在 RuntimeExecutor / LangGraph 边界内。
- Provider 聚合现在区分核心 blocker 与可选 runtime warning：
  - Plane / Graphiti / direct_llm / universal_employee_agent / langgraph 的 blocker 会阻断 environment readiness。
  - Claude / Cursor / OpenHands / OpenCode 等可选商业 runtime 缺配置会作为 warning，不阻断核心环境 smoke。
- Dashboard System Status 新增 `Environment Smoke` 面板：
  - `Environment Smoke` 默认只读，不调用外部 provider。
  - `External Environment Smoke` 显式触发 Plane / Graphiti read-only external smoke。
  - UI 展示 overall status、blocked / warning / failed count、external calls、core boundary、每个检查卡的 checks / blockers / warnings。
- 后端和前端测试覆盖：
  - 默认 environment smoke 不发外部调用，能暴露 DeepSeek / Plane / Graphiti blocker。
  - external environment smoke 会复用 fake Plane / Graphiti adapter，确认 `provider:ticket:plane:passed` 和 `provider:memory:graphiti:passed`。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/provider_conformance_service.py services/api/aiteamos_api/read/system_status_routes.py

pytest tests/test_file_system_status_routes.py -q

cd apps/dashboard && npm test -- system-status-page.test.tsx

pytest tests/test_file_system_status_routes.py tests/test_runtime_executor_routes.py tests/test_execution_dispatch_contract.py tests/test_file_memory_routes.py tests/test_file_knowledge_and_tickets.py -q

cd apps/dashboard && npm run build
```

结果：

- system-status backend tests: `2 passed, 1 warning`
- Dashboard related Vitest suite: `44 passed`
- broader provider/backend suite: `123 passed, 6 warnings`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

### 2026-06-18: Phase M slice - repeatable environment smoke CLI and real-run evidence

已完成：

- 新增可重复运行脚本：
  - `python scripts/environment_smoke.py`
  - `python scripts/environment_smoke.py --include-external`
  - `python scripts/environment_smoke.py --include-external --output /tmp/aiteamos_environment_smoke_external.json`
  - `python scripts/environment_smoke.py --fail-on-blocker`
- 脚本直接复用 `provider_environment_smoke()`，不启动 API server，也不维护另一套 smoke 逻辑。
- 默认模式只读、不调用外部 provider；`--include-external` 才触发 Plane GET / Graphiti search。
- 输出为 redacted JSON：
  - 不输出 secret/token/password/api key value。
  - 保留安全诊断字段，例如 `*_configured`、`*_env`、`setup_required`、`missing_env`。
- CLI 针对 LangGraph / aiosqlite 后台线程做一次性进程退出处理，避免 JSON 输出后被 checkpointer worker 卡住。
- 测试覆盖脚本 subprocess 输出：
  - schema
  - workspace_dir
  - default no external calls
  - DeepSeek blocker
  - secret value 不出现在 stdout。

真实当前环境运行证据：

- 默认脚本：
  - command: `python scripts/environment_smoke.py`
  - result: `status=warning`
  - `external_calls=false`
  - DeepSeek / OpenAI configured。
  - Plane、Graphiti、local fallback、Universal Employee Agent / LangGraph 核心 readiness 通过。
  - warning 来自可选商业 runtime 未配置，以及 external provider smoke 默认未启用。
- External 脚本：
  - command: `python scripts/environment_smoke.py --include-external --output /tmp/aiteamos_environment_smoke_external.json`
  - result: `status=failed`
  - `external_calls=true`
  - DeepSeek / local fallback / LangGraph agent loop 通过。
  - Provider core failed，且没有假成功：
    - `ticket:plane`: `plane_external_smoke_failed`，Plane `GET /work-items/` 返回 `502` blocker。
    - `memory:graphiti`: `graphiti_external_smoke_failed`，Neo4j 返回 `Neo.ClientError.Security.AuthenticationRateLimit / 50N42`，说明当前 Graphiti/Neo4j 凭证或 rate-limit 状态需要修复。

验证：

```bash
python -m py_compile scripts/environment_smoke.py services/api/aiteamos_api/read/provider_conformance_service.py services/api/aiteamos_api/read/system_status_routes.py

pytest tests/test_file_system_status_routes.py -q

python scripts/environment_smoke.py

python scripts/environment_smoke.py --include-external --output /tmp/aiteamos_environment_smoke_external.json
```

结果：

- script-focused test: `1 passed, 1 warning`
- system-status backend tests after CLI: `3 passed, 1 warning`
- default real environment smoke: `status=warning`, `external_calls=false`
- external real environment smoke: `status=failed`, `external_calls=true`，真实 blocker 已暴露。

Phase M 仍未完成：

- Plane / Graphiti external smoke、environment smoke API/UI、CLI 和真实运行证据已有；还需要修复当前 Plane 502 与 Graphiti Neo4j auth/rate-limit blocker 后，重新跑 external smoke 到通过。
- EmployeeProvider 仍是 local profile provider，没有外部 Employee provider adapter。
- Provider contract 尚未接入迁移 / schema version / production evaluation harness。

### 2026-06-19: Phase M slice - provider production readiness evaluation

已完成：

- `ProviderConformanceRecord` 新增 `production_evaluation`：
  - `schema_version`
  - `migration_status`
  - `required_for_core`
  - `production_ready`
  - `readiness_level`
  - `blockers`
  - `warnings`
- `ProviderConformanceSummary` 新增生产就绪聚合：
  - `core_required_count`
  - `production_ready_count`
  - `core_blocked_count`
  - `optional_warning_count`
- readiness 规则保持只读，不触发外部 provider 调用：
  - Ticket / Asset / Employee / Memory provider 默认是 core provider。
  - `direct_llm` / `universal_employee_agent` / `langgraph` runtime 是 core runtime provider。
  - 其他商业 runtime 未配置记为 optional warning，不阻断 core readiness。
  - 带 fallback 的核心 provider 若未 ready，标记为 `degraded_with_fallback`，不假装 production-ready。
  - contract expectation missing 会进入 blocker 或 warning。
- `/api/v1/system-status/providers/checks` 现在会记录：
  - `production_evaluation`
  - `readiness:<level>`
  - `contract_schema_current`
  - `core_provider`
- Dashboard System Status 的 Provider Adapter Conformance 面板显示：
  - production-ready provider 数量
  - 每个 provider 的 readiness level
  - core / optional
  - schema migration status

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/provider_conformance_service.py \
  services/api/aiteamos_api/read/system_status_routes.py \
  tests/test_file_system_status_routes.py

pytest tests/test_file_system_status_routes.py -q

cd apps/dashboard && npm test -- system-status-page.test.tsx

cd apps/dashboard && npm run build
```

结果：

- py_compile passed。
- system-status backend tests: `3 passed, 2 warnings`
- Dashboard related Vitest suite: `54 passed`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

Phase M 剩余：

- Plane / Graphiti external smoke 真实环境仍需要修复当前 Plane 502 与 Graphiti Neo4j auth/rate-limit blocker 后重跑到通过。
- EmployeeProvider 仍是 local profile provider，没有外部 Employee provider adapter。
- Production readiness 已有 read model / UI，但还没有独立的长期趋势、历史快照或 release gate 评估。

## 12. Phase N: Durable Learning Loop

目标：让系统真的“越用越聪明”，并且聪明来自 AITeamOS Assets，而不是某个 chat session。

任务：

1. Memory recall usefulness feedback：
   - used
   - irrelevant
   - harmful
   - promoted
2. Ticket closeout 生成 durable asset candidates：
   - validated solution
   - failure pattern
   - reusable skill
   - decision
   - doc update suggestion
3. Review Queue 支持 batch review。
4. Retrieval evaluation：
   - 给定 Ticket / question，检查是否召回 expected asset。
   - 记录 recall precision / usefulness。
5. Employee quality feedback 进入 work ledger，不直接改 personality。

验收：

- 一个被验证解决的 Ticket 能自动产生 closeout candidate。
- 下次相关问题能召回该 validated solution。
- 被标记 irrelevant 的 memory 降权或进入 review。

### 2026-06-18: Phase N slice - validated Ticket closeout Asset candidates

已完成：

- 新增 Ticket closeout AssetCandidate 生成闭环：
  - `ticket_closeout`
  - `solution`
  - `validation_result`
- 新增后端 API：
  - `POST /api/v1/tickets/{ticket_id}/closeout-candidates`
- 生成规则：
  - 只有 `validated` / `completed` / `done` / `closed` Ticket，或带 validation pass report 的 Ticket，才能生成 closeout candidates。
  - 未验证 Ticket 会返回治理 blocker，不制造 durable learning 假成功。
  - 候选进入本地 Asset Candidate registry，状态为 `proposed` / `review_state=proposed`。
  - candidate provenance 记录 Ticket、Employee、report、evidence、provider refs、relationships 和生成原因。
  - Ticket 主线会写入 `ticket_closeout_candidates` report，并把候选 id 作为 evidence ref。
  - 重复调用保持幂等，不重复写入 closeout report。

验证：

```bash
pytest tests/test_execution_dispatch_contract.py::test_validated_ticket_closeout_generates_reviewable_asset_candidates -q

pytest tests/test_execution_dispatch_contract.py tests/test_file_memory_routes.py tests/test_file_knowledge_and_tickets.py -q
```

结果：

- `1 passed, 1 warning`
- `86 passed, 1 warning`

### 2026-06-18: Phase N slice - recall usefulness canonical statuses and Asset sync

已完成：

- Memory recall usefulness review 支持 Phase N 目标状态：
  - `used`
  - `irrelevant`
  - `harmful`
  - `promoted`
- 保持旧接口兼容：
  - `useful -> used`
  - `not_useful / not-useful / not useful -> irrelevant`
  - `neutral -> used`
  - `promote -> promoted`
- `usage_summary` 扩展为 durable learning stats：
  - `used_count`
  - `irrelevant_count`
  - `harmful_count`
  - `promoted_count`
  - `unreviewed_count`
  - `status_counts`
  - 兼容保留 `useful_count` / `not_useful_count`
- Memory recall usage 新增或 review 后，会同步到 Asset layer：
  - `AssetCandidateRecord.usefulness_stats`
  - `AssetCandidateRecord.provenance.usage_summary`
  - 已存在的 `AssetRecord.usefulness_stats`
  - 已存在的 `AssetRecord.provenance.usage_summary`
- 同步只更新本地 AITeamOS Asset read model，不绕过 review，不直接投影 Graphiti。
- Ticket / Employee / self-bootstrap summary 的正向 recall 统计兼容 `used` / `promoted` / legacy `useful`。
- Dashboard Assets memory detail 现在可以对 latest recall 标记：
  - `Mark Used`
  - `Mark Irrelevant`
  - `Mark Harmful`
  - `Promote`
- Dashboard usage stats 展示 Used / Irrelevant / Harmful / Promoted。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/memory_service.py \
  services/api/aiteamos_api/read/asset_candidate_service.py \
  services/api/aiteamos_api/read/ticket_service.py \
  services/api/aiteamos_api/read/runtime_executors/local_tool_executor.py

pytest tests/test_file_memory_routes.py::test_ticket_aware_candidate_approval_is_recalled_through_graphiti_in_chat -q

pytest tests/test_file_knowledge_and_tickets.py::test_ticket_assets_include_approved_memory_recall_usage -q

pytest tests/test_execution_dispatch_contract.py::test_chat_can_close_self_bootstrap_batch_with_learning_and_recall_usefulness -q

pytest tests/test_file_chat_routes.py::test_clara_answers_self_bootstrap_learning_summary_from_kernel_facts -q

cd apps/dashboard && npm test -- assets-page.test.tsx

pytest tests/test_file_memory_routes.py tests/test_file_knowledge_and_tickets.py tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py -q

cd apps/dashboard && npm run build
```

结果：

- focused memory recall / Asset sync test: `1 passed, 1 warning`
- ticket asset projection test: `1 passed, 1 warning`
- self-bootstrap recall usefulness test: `1 passed, 1 warning`
- chat learning summary test: `1 passed, 1 warning`
- Dashboard related Vitest suite: `44 passed`
- backend Chat / Memory / Ticket / Runtime regression: `145 passed, 2 warnings`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

### 2026-06-18: Phase N slice - validated Ticket auto closeout trigger

已完成：

- Ticket validated 后会自动触发 closeout AssetCandidate proposal：
  - `add_ticket_report(... report_type="validation" / validation pass)` 会自动生成 closeout candidates。
  - `transition_ticket_state(... status="validated" / "completed" / "done" / "closed")` 会尝试自动生成 closeout candidates。
- 自动生成仍走既有 governed Asset Candidate lifecycle：
  - 生成 `ticket_closeout`、`solution`、`validation_result` candidates。
  - 不直接写 durable AssetRecord。
  - 不绕过 review。
  - 重复显式调用 `POST /api/v1/tickets/{ticket_id}/closeout-candidates` 返回 `skipped`，不重复写 closeout report。
- state transition 自动 closeout 增加 evidence gate：
  - 缺少验证证据时不制造 durable learning 假成功。
  - Ticket ledger 写入 `ticket_closeout_blocked` report，说明缺失验证证据。
- Graphiti / durable report projection 边界补齐：
  - `ticket_closeout_candidates` 和 `ticket_closeout_blocked` 是 Ticket governance ledger 事件，不作为普通 validated report / evidence asset 投影。
  - Ticket summary 的 `report_count` / `evidence_count` 也排除这些非 durable report 类型。

验证：

```bash
pytest tests/test_execution_dispatch_contract.py::test_validated_ticket_closeout_generates_reviewable_asset_candidates \
  tests/test_execution_dispatch_contract.py::test_ticket_closeout_auto_trigger_blocks_without_validation_evidence -q

pytest tests/test_file_memory_routes.py::test_validated_ticket_report_and_evidence_assets_project_to_graphiti -q

pytest tests/test_execution_dispatch_contract.py tests/test_file_memory_routes.py tests/test_file_knowledge_and_tickets.py tests/test_file_chat_routes.py -q
```

结果：

- auto closeout focused tests: `2 passed, 1 warning`
- Graphiti durable report projection regression: `1 passed, 1 warning`
- backend Chat / Memory / Ticket / Runtime regression: `146 passed, 1 warning`

### 2026-06-18: Phase N slice - AssetCandidate batch review

已完成：

- 新增 governed batch review 后端 contract：
  - `POST /api/v1/assets/candidates/review-batch`
  - `AssetCandidateBatchReviewRequest`
  - `AssetCandidateBatchReviewResponse`
- batch review 复用既有单条 `review_asset_candidate()` 流程：
  - 更新 `AssetCandidateRecord.status/review_state`
  - 写入 `AssetReviewRecord`
  - approved 时生成 / upsert `AssetRecord`
  - merged / linked 时仍走既有 relationship review 逻辑
  - 不绕过 Review Queue，不直接投影 Graphiti
- batch request 会对 candidate ids 去重，并返回：
  - `requested_count`
  - `reviewed_count`
  - `failed_count`
  - per-candidate result / error
  - governed saved paths
- Dashboard Assets Review Queue 增加当前 tab 范围内的 AssetCandidate batch 操作：
  - `Approve All`
  - `Reject All`
  - 只作用于当前可见 `proposed` AssetCandidates，避免跨 tab 误审。
- Dashboard API client 新增 `reviewAssetCandidatesBatch()`。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/asset_candidate_service.py \
  services/api/aiteamos_api/read/asset_routes.py \
  tests/test_execution_dispatch_contract.py

pytest tests/test_execution_dispatch_contract.py::test_asset_candidate_batch_review_uses_governed_single_review_flow \
  tests/test_execution_dispatch_contract.py::test_external_runtime_durable_asset_candidates_enter_review_queue -q

cd apps/dashboard && npm test -- assets-page.test.tsx

pytest tests/test_execution_dispatch_contract.py tests/test_file_memory_routes.py tests/test_file_knowledge_and_tickets.py tests/test_file_chat_routes.py -q

cd apps/dashboard && npm run build
```

结果：

- backend batch focused test: `1 passed, 1 warning`
- backend asset review focused tests: `2 passed, 1 warning`
- Dashboard related Vitest suite: `45 passed`
- backend Chat / Memory / Ticket / Runtime regression: `147 passed, 1 warning`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

### 2026-06-18: Phase N slice - retrieval evaluation harness

已完成：

- 新增 Assets retrieval evaluation ledger：
  - `.aiteamos/assets/retrieval_evaluations.json`
- 新增后端 API：
  - `POST /api/v1/assets/retrieval-evaluations`
  - `GET /api/v1/assets/retrieval-evaluations`
- evaluation 输入：
  - query
  - expected asset ids
  - top_k
  - source_ticket_id
  - source_run_id
  - evaluator_employee_id
  - usefulness_status
- evaluation 复用当前 Assets 聚合搜索结果，不另造 retrieval 路径：
  - Knowledge assets
  - approved AssetRecords
  - AssetCandidates
- evaluation 记录：
  - retrieved_asset_ids
  - matched_asset_ids
  - missing_asset_ids
  - precision
  - recall
  - saved path
- expected id 匹配支持 raw id 和带前缀 id：
  - `asset-registry:<id>`
  - `asset-candidate:<id>`
  - raw AssetRecord / AssetCandidate / Memory id
- 该 slice 只做可审计 evaluation harness，不改变 retrieval ranking。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/asset_candidate_service.py \
  services/api/aiteamos_api/read/asset_routes.py \
  tests/test_execution_dispatch_contract.py

pytest tests/test_execution_dispatch_contract.py::test_asset_retrieval_evaluation_records_expected_asset_recall -q

pytest tests/test_execution_dispatch_contract.py tests/test_file_memory_routes.py tests/test_file_knowledge_and_tickets.py tests/test_file_chat_routes.py -q
```

结果：

- retrieval evaluation focused test: `1 passed, 1 warning`
- backend Chat / Memory / Ticket / Runtime regression: `148 passed, 1 warning`

### 2026-06-18: Phase N slice - local retrieval ranking feedback penalty

已完成：

- Assets 聚合搜索开始使用 recall usefulness stats 做本地排序调整：
  - `harmful_count` 强降权
  - `irrelevant_count` 降权
  - `promoted_count` / `used_count` 轻微加权
- 降权只影响 AITeamOS local Assets 聚合搜索 / retrieval evaluation 的排序：
  - 不改变 AssetRecord / AssetCandidate 状态
  - 不写新的 ReviewRecord
  - 不绕过 Graphiti provider ranking
- Asset 搜索 item metadata 显式带上 `usefulness_stats`，便于 UI / evaluation 解释排序原因。
- 新增测试覆盖：
  - 一个更新时间更新但被标记 harmful / irrelevant 的 AssetRecord，会在同 query 的 neutral AssetRecord 后面出现。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/asset_routes.py tests/test_execution_dispatch_contract.py

pytest tests/test_execution_dispatch_contract.py::test_asset_search_downranks_irrelevant_or_harmful_recall_feedback -q

pytest tests/test_execution_dispatch_contract.py tests/test_file_memory_routes.py tests/test_file_knowledge_and_tickets.py tests/test_file_chat_routes.py -q
```

结果：

- local ranking feedback focused test: `1 passed, 1 warning`
- backend Chat / Memory / Ticket / Runtime regression: `149 passed, 1 warning`

### 2026-06-19: Phase N slice - closeout / solution Graphiti projection review provenance

已完成：

- approved `ticket_closeout` / `solution` AssetRecord 现在有专门验收覆盖 Graphiti provider projection。
- projection 仍复用既有 approved AssetRecord provider boundary：
  - `POST /api/v1/assets/records/{asset_id}/project/graphiti`
  - 不绕过 AssetReviewRecord
  - 不从 Ticket report 直接写 Graphiti
- Graphiti durable asset metadata 补齐 review provenance：
  - `asset_review_id`
  - `reviewer_employee_id`
  - `review_reason`
  - `source_asset_candidate_id`
- 新增测试覆盖：
  - `ticket_closeout` 与 `solution` candidate batch approve 后成为 AssetRecord。
  - 两个 approved AssetRecord 分别投影到 Graphiti。
  - Graphiti episode provenance 保留 Ticket、Employee、Candidate、ReviewRecord 和 review reason。
  - 本地 AssetRecord 写回 `graphiti_status` 与 `provider_refs`。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/asset_candidate_service.py \
  services/api/aiteamos_api/read/asset_routes.py \
  tests/test_execution_dispatch_contract.py

pytest tests/test_execution_dispatch_contract.py::test_approved_closeout_and_solution_assets_project_to_graphiti_with_review_provenance -q

pytest tests/test_execution_dispatch_contract.py tests/test_file_memory_routes.py tests/test_file_knowledge_and_tickets.py tests/test_file_chat_routes.py -q
```

结果：

- closeout / solution Graphiti projection focused test: `1 passed, 1 warning`
- backend Chat / Memory / Ticket / Runtime regression: `150 passed, 1 warning`

Phase N core acceptance status:

- 一个被验证解决的 Ticket 能自动产生 closeout candidate。
- closeout / solution / validation_result 能进入 governed AssetCandidate lifecycle。
- Review Queue 支持 batch review。
- Retrieval evaluation harness 能记录 expected asset recall、precision、recall。
- irrelevant / harmful recall feedback 已进入 local Assets retrieval ranking 降权。
- approved closeout / solution AssetRecord 能通过 Graphiti provider boundary 投影，并保留 AssetReviewRecord provenance。

## 13. Phase O: Product UX for Daily Use

目标：让最终能力不是藏在 API 里，而是能在 Web UI 日常使用。

重点页面：

1. Homepage Chat：
   - Clara / Employee selected identity
   - selected Ticket context
   - runtime / LangGraph status
   - approval prompts
   - context inspector
   - answer provenance
2. Ticket detail：
   - event ledger
   - reports / evidence
   - assignee / handoff
   - validation
   - loop controls
   - linked assets
3. Employee detail：
   - profile
   - skills
   - permissions
   - memory scope
   - work history
   - quality feedback
4. Assets：
   - registry
   - review queue
   - relationship graph
   - source provenance
   - provider projection status
5. Runtime / Replay：
   - session list
   - timeline
   - approval / resume
   - tool events
   - errors / blockers

验收：

- 用户可以从一个 Chat 问题一路追溯到 Ticket、Employee、Assets、tool events、approval 和 replay。
- 用户能在 UI 中 approve / reject / resume / stop loop。
- UI 不暴露 raw transport errors，而是显示治理语义 blocker。

### 2026-06-18: Phase O slice - Ticket detail closeout candidate action

已完成：

- Dashboard Ticket detail 增加 `Closeout Assets` 操作入口。
- 操作调用：
  - `POST /api/v1/tickets/{ticket_id}/closeout-candidates`
- UI 展示：
  - proposed / skipped 状态
  - closeout detail
  - candidate asset types
  - Ticket report id
  - backend 返回的治理 blocker 文案
- Ticket API 类型增加：
  - `TicketCloseoutAssetCandidate`
  - `TicketCloseoutAssetCandidateResponse`
  - `proposeTicketCloseoutCandidates`
- 成功后刷新 Ticket / Asset graph 相关数据，让 closeout report 和 asset candidates 能进入日常 Ticket surface。

验证：

```bash
cd apps/dashboard && npm test -- tickets-page.test.tsx

cd apps/dashboard && npm run build
```

结果：

- `29 passed`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

### 2026-06-19: Phase O slice - Assets provider projection action

已完成：

- Dashboard Assets 的通用 Asset drawer 增加 provider projection 状态：
  - Asset registry id
  - Graphiti status
  - Graphiti episode id
- approved AssetRecord 可以直接从 Assets drawer 触发 Graphiti projection：
  - 调用 `POST /api/v1/assets/records/{asset_id}/project/graphiti`
  - 成功后刷新 Assets 数据
  - 若 Graphiti 缺配置，沿用后端治理 blocker，不在 UI 伪装成功
- Search Results drawer 和普通 Asset drawer 都支持该 projection surface。
- Dashboard API client 复用既有 `projectAssetRecordToGraphiti()`。
- UI 测试覆盖：
  - 搜索 approved AssetRecord
  - 打开 drawer
  - 显示 Provider Projection 状态
  - 点击 `Project Graphiti`
  - 调用正确 provider projection endpoint

验证：

```bash
cd apps/dashboard && npm test -- assets-page.test.tsx

cd apps/dashboard && npm run build

pytest tests/test_execution_dispatch_contract.py tests/test_file_memory_routes.py tests/test_file_knowledge_and_tickets.py tests/test_file_chat_routes.py -q
```

结果：

- Dashboard related Vitest suite: `46 passed`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。
- backend Chat / Memory / Ticket / Runtime regression: `150 passed, 1 warning`

### 2026-06-19: Phase O slice - route-backed Runtime Replay surface

已完成：

- 新增 Dashboard daily-use Runtime 页面：
  - `#/runtime/sessions`
  - `#/runtime/{session_key}`
- Runtime 页面展示：
  - execution sessions list
  - selected session status / Ticket / checkpoint / trace
  - tool event count
  - Replay Detail timeline
  - artifacts / evidence / approvals / state snapshots redacted payload preview
- `RuntimeSessionReplayDetail` 从 Settings 内联实现抽为共享组件：
  - Settings Runtime Executors 仍可内联查看 Replay。
  - Runtime 页面复用同一组件，不新造第二套 replay renderer。
- App shell 和 sidebar 增加 `Runtime` 顶层入口，让 Replay 不再只藏在 Settings 里。
- Route-backed replay 支持直接用 session key 打开具体执行复盘。

验证：

```bash
cd apps/dashboard && npm test -- runtime-page.test.tsx settings-page.test.tsx

cd apps/dashboard && npm run build
```

结果：

- Dashboard related Vitest suite: `48 passed`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

### 2026-06-19: Phase O slice - Ticket loop run to Runtime Replay deep link

已完成：

- Ticket loop run record 类型补充 `session_key`。
- Dashboard Ticket detail 的 Loop Runs 列表支持直接跳转 Runtime Replay：
  - 有 `session_key` 的 run 显示 `Replay`。
  - 点击后进入 `#/runtime/{session_key}`。
- Loop Run Detail 中也显示 `Runtime Replay` 操作。
- 该 slice 把 Ticket detail 的 autonomous loop 运行记录和 route-backed Runtime Replay surface 串起来。
- 当前 Ticket detail 已覆盖完整 loop control set：
  - Run Loop
  - Continue Loop
  - Pause Loop
  - Stop Loop
  - Cancel Loop

验证：

```bash
cd apps/dashboard && npm test -- tickets-page.test.tsx runtime-page.test.tsx

cd apps/dashboard && npm run build
```

结果：

- Dashboard related Vitest suite: `49 passed`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

### 2026-06-19: Phase O slice - Chat provenance navigation to Ticket / Runtime / Assets

已完成：

- Homepage Chat 的 `Latest Run` provenance inspector 增加 `Provenance Links`：
  - `Ticket`：跳转到 `#/tickets/{ticket_id}`。
  - `Replay`：跳转到 `#/runtime/{session_key}`。
  - `Asset Review` / `Memories` / `Assets`：按当前 run metadata 跳转到 Assets review 或 knowledge memory surface。
- Runtime Replay 链接优先使用 metadata 中显式 `session_key`；没有时按 Chat execution session store 规则推导：
  - `employee_id::thread_id::ticket_id`
- Chat run metadata 现在能从同一个 UI 面板串起：
  - Ticket binding / output Ticket
  - LangGraph executor / checkpoint / executor session ref
  - artifacts / evidence / Ticket reports
  - approval refs / approval requests
  - scoped context / universal context / provenance summary
  - recalled memories / Graphiti episodes / provider refs
- Ticket loop Replay test 改成等待异步 loop run 记录渲染后再点击，避免只等到 section title 的时序假阳性。

验证：

```bash
cd apps/dashboard && npm test -- chat-page.test.tsx runtime-page.test.tsx tickets-page.test.tsx assets-page.test.tsx

cd apps/dashboard && npm run build
```

结果：

- Dashboard related Vitest suite: `50 passed`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

### 2026-06-19: Phase O slice - Assets drawer deep-link provenance targets

已完成：

- Assets 页面支持 route-backed drawer targets，不再只能进入 tab：
  - `#/assets/knowledge/memory:{memory_id}` 打开具体 approved memory drawer。
  - `#/assets/review/candidate:{candidate_id}` 打开具体 AssetCandidate drawer。
  - `#/assets/asset/{asset_record_id}` 打开具体 AssetRecord drawer。
- Assets route 解析区分“已知 sub-tab”和“未知 route target”：
  - `docs / memories / decisions`
  - `skills / kernel-commands / mcp-tools`
  - `memories / decisions / skills / tools`
  - 未知第三段不再误传给 `/assets/{area}/{detail}` 查询，而是用于 drawer target resolution。
- Chat `Latest Run` provenance links 增加 Employee 跳转：
  - `Employee` -> `#/employees/{employee_id}`
- Chat 的 Assets provenance 在已有 recalled memory id 时直接跳到具体 memory drawer：
  - `Memory` -> `#/assets/knowledge/memory:{memory_id}`
  - 有新 candidate 但没有 candidate id 时仍进入 `Asset Review` tab，避免伪造不存在的深链。

验证：

```bash
cd apps/dashboard && npm test -- assets-page.test.tsx chat-page.test.tsx

cd apps/dashboard && npm run build
```

结果：

- Dashboard Vitest suite: `53 passed`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

Phase O 仍未完成：

- Chat -> Ticket -> Runtime Replay -> Assets 的基础可点击链路已打通。
- Assets asset id / memory id / candidate id drawer deep-link 已覆盖基础路径。
- 仍需要补 route-backed Employee work-ledger 子视图 / work-history provenance links。
- Chat 只有在 metadata 暴露具体 memory id 时能深链到具体 memory；若后端只给 candidate count，仍只能进入 Asset Review tab，后续可在 runtime ingestion metadata 中补 candidate ids。

### 2026-06-19: Phase O slice - route-backed Employee work-ledger provenance

已完成：

- Employee detail 支持 route-backed 子视图：
  - `#/employees/{employee_id}/overview`
  - `#/employees/{employee_id}/work`
  - `#/employees/{employee_id}/analytics`
  - `#/employees/{employee_id}/capabilities`
  - `#/employees/{employee_id}/governance`
  - `#/employees/{employee_id}/ai_engine`
- Chat `Latest Run` provenance 中的 Employee 链接现在直达：
  - `#/employees/{employee_id}/work`
- Employee Work Ledger 中的 provenance links 改为真实日常使用路径：
  - Ticket work item / report / handoff -> `#/tickets/{ticket_id}`
  - Runtime run -> `#/runtime/{session_key}`
  - proposed AssetCandidate -> `#/assets/review/candidate:{candidate_id}`
  - approved AssetRecord -> `#/assets/asset/{asset_id}`
- `EmployeeRuntimeRunRecord` 新增 `session_key`：
  - ingestion mirror 会保存 `employee_id::thread_id::ticket_id`
  - old records 缺 `session_key` 时由 work ledger 使用 `employee_id::run_id/request_id::ticket_id` fallback
- Work Ledger provenance buttons 增加明确 aria-label，测试和用户辅助导航都能稳定定位。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/ticket_service.py \
  services/api/aiteamos_api/read/execution_result_ingestion_service.py

pytest tests/test_execution_dispatch_contract.py::test_employee_work_ledger_v2_projects_assets_reviews_and_runtime_runs -q

cd apps/dashboard && npm test -- employees-page.test.tsx chat-page.test.tsx

cd apps/dashboard && npm run build
```

结果：

- py_compile passed。
- Employee work ledger backend focused test: `1 passed, 1 warning`
- Dashboard related Vitest suite: `55 passed`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

Phase O 剩余：

- Chat -> Ticket -> Employee Work Ledger -> Runtime Replay -> Assets 的基础可点击链路已打通。
- 后端 runtime ingestion metadata 仍可继续补更完整的 candidate ids，减少只能跳 Asset Review tab 的模糊路径。
- Employee work history 已 route-backed；后续可补更细的 report/evidence/asset anchored deep-link。

## 14. Phase P: Production Hardening and Evaluation

目标：把系统从可用推进到可信。

任务：

1. Migration / schema version：
   - execution_sessions
   - approvals
   - assets
   - employees
   - tickets projection
2. Security:
   - secret redaction
   - permission checks
   - destructive action approval
   - provider token never enters replay payload
3. Observability:
   - structured trace
   - latency
   - token usage
   - tool success / failure
   - retrieval quality
4. Evaluation harness:
   - context assembly tests
   - retrieval expected refs
   - Ticket loop golden cases
   - approval safety cases
   - provider conformance
5. Failure semantics:
   - setup_blocked
   - needs_approval
   - needs_validation
   - blocked
   - partial
   - completed

验收：

- 真实 DeepSeek + Plane + Graphiti + local fallback 的 smoke 可重复执行。
- 每个高风险路径都有 approval / evidence / replay。
- 系统失败时不假完成，能把 blocker 写入 Ticket。

### 2026-06-18: Phase P slice - provider conformance metadata check harness

已完成：

- 在 Provider Adapter Conformance 基础上新增只读 check harness：
  - `ProviderConformanceCheckRecord`
  - `ProviderConformanceCheckResponse`
- 新增后端 API：
  - `GET /api/v1/system-status/providers/checks`
- check harness 只检查 metadata contract，不调用外部 provider：
  - provider identity
  - capabilities
  - conformance smoke metadata
  - projection direction
  - failure semantics
  - domain boundary
  - setup blocker 是否与 provider status 一致
  - external provider fallback
  - `repo:write` RuntimeProvider 是否声明 ticket / approval / evidence guard
- 缺配置 provider 只要正确报告 setup blocker / fallback / failure semantics，就不会被误判为 contract failure。
- ready provider 的可选 lane 缺配置不会被误报为 setup blocker，例如 Direct LLM 在 OpenAI ready、DeepSeek missing 时仍可通过 contract check。

验证：

```bash
pytest tests/test_file_system_status_routes.py -q

pytest tests/test_file_system_status_routes.py tests/test_runtime_executor_routes.py tests/test_execution_dispatch_contract.py tests/test_file_memory_routes.py tests/test_file_knowledge_and_tickets.py -q
```

结果：

- `1 passed, 1 warning`
- `101 passed, 1 warning`

### 2026-06-18: Phase P slice - LangGraph checkpoint workspace isolation

已完成：

- `LangGraphExecutor` 现在会归一化 checkpoint workspace：
  - 如果传入的是 workspace root，则使用 `workspace/.aiteamos`。
  - 如果传入的已经是 `.aiteamos`，则保持原路径。
- LangGraph / Universal Employee Agent checkpoint SQLite 统一落到 `.aiteamos/langgraph`。
- 修复在 `AITEAMOS_WORKSPACE_DIR=/path/to/repo` 时生成根目录 `langgraph/` 产物的问题。
- 清理了本地测试生成的根目录 `langgraph/` checkpoint artifact。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/runtime_executors/langgraph_executor.py services/api/aiteamos_api/read/provider_conformance_service.py

pytest tests/test_execution_dispatch_contract.py::test_langgraph_executor_native_interrupt_resumes_from_checkpoint tests/test_file_system_status_routes.py -q

test ! -e langgraph
```

结果：

- focused checkpoint/status tests: `2 passed, 1 warning`
- repo root `langgraph/` artifact 不再生成。

Phase P 仍未完成：

- 还没有真实 DeepSeek + Plane + Graphiti + local fallback 的可重复 smoke 脚本。
- latency / token usage / retrieval quality 还没有形成统一 observability dashboard。
- provider conformance check 目前是 metadata contract harness，还不是外部 provider 端到端 harness。

### 2026-06-19: Phase P slice - schema registry and migration readiness

已完成：

- 新增只读 Schema / Migration Readiness registry：
  - `aiteamos_schema_registry.v1`
  - 覆盖 `execution_sessions`、`execution_approvals`、Asset candidates / records / reviews / retrieval evaluations、Employee local profiles、Ticket projection。
- 新增后端 service：
  - `schema_registry_service.py`
  - 不重写现有 ledger，不隐式迁移；只声明 schema version、expected shape、actual shape、path、item count、migration status、provenance boundary。
- 新增后端 API：
  - `GET /api/v1/system-status/schema`
  - `GET /api/v1/system-status` payload 现在包含 `schema_registry`。
- Schema registry 能区分：
  - `current`
  - `missing` / `not_created_yet`
  - `legacy` / `legacy_shape_supported`
  - `invalid` / `migration_blocked`
- System Status 页面新增 `Schema / Migration Readiness` 面板：
  - 显示 store count、current count、missing / legacy / invalid、migration required count。
  - 每个 store 展示 schema version、path、actual / expected shape、migration status、checks / warnings / blockers。
- 覆盖坏 JSON blocker 测试，确保 invalid ledger 不会被误报为 ready。

验证：

```bash
python -m py_compile services/api/aiteamos_api/read/schema_registry_service.py \
  services/api/aiteamos_api/read/system_status_routes.py \
  tests/test_file_system_status_routes.py

pytest tests/test_file_system_status_routes.py::test_system_status_reports_secret_health_without_settings_compat_route \
  tests/test_file_system_status_routes.py::test_schema_registry_reports_invalid_json_blocker -q

pytest tests/test_file_system_status_routes.py -q

cd apps/dashboard && npm test -- system-status-page.test.tsx

cd apps/dashboard && npm run build
```

结果：

- py_compile passed。
- Schema focused backend tests: `2 passed, 2 warnings`
- Full System Status backend tests: `4 passed, 1 warning`
- Dashboard System Status Vitest suite: `55 passed`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

Phase P 剩余：

- 还没有真实 DeepSeek + Plane + Graphiti + local fallback 的可重复 smoke 脚本。
- latency / token usage / retrieval quality 还没有形成统一 observability dashboard。
- provider conformance check 目前是 metadata contract harness，还不是外部 provider 端到端 harness。

## 15. 推荐执行顺序

不要先做大 UI，也不要先重构所有 provider。v5 建议按这个顺序：

1. **Phase G：LangGraph Approval Interrupt / Resume。**  
   这是 autonomous loop 的安全基础。

2. **Phase H：Full Replay Timeline。**  
   没有 replay，长任务和 approval resume 很难调试。

3. **Phase I：Unified Asset Registry v2。**  
   把长期资产统一起来，避免 Memory / Skills / Docs 继续分裂。

4. **Phase J：Employee System v2。**  
   让 handoff、skill、memory scope 和权限真正落到固定 Employee 身上。

5. **Phase K：Ticket-native Autonomous Loop。**  
   在 approval、replay、assets、employee 都更稳后，再做多步自动推进。

6. **Phase L-M：Tool / Skill Governance + Provider Conformance。**  
   把工具和供应商变成可治理、可替换的边界。

7. **Phase N-P：Durable Learning、Product UX、Hardening。**  
   让系统越用越聪明，并能在真实日常工作中稳定使用。

## 16. 第一轮可见成功标准

第一轮 v5 成功不要求完成所有最终目标，只要求证明“安全长任务闭环”：

```text
用户在 Chat 里要求 Alex 修改一个 Ticket-bound repo task
  -> Clara / Alex 进入 LangGraph Universal Employee Agent Loop
  -> 自动读取 Employee / Ticket / Asset / Memory context
  -> 发现 repo:write 需要 approval
  -> LangGraph graph interrupt
  -> session 保存 checkpoint、current node、state ref、approval ref
  -> Dashboard Review Queue 显示 approval
  -> Human approve
  -> runtime 从 checkpoint resume
  -> 写入 Ticket report / evidence
  -> replay detail 显示完整 tool events、context refs、approval resume timeline
```

## 17. 不做事项

明确不要做：

- 不在 `chat_routes.py` 里新增 generic agent loop。
- 不让外部 provider 直接绕过 AITeamOS Ticket / Asset / Employee model。
- 不把 chat transcript 裸存成长期 memory。
- 不让 approval approved 之后用不透明的新请求假装 resume。
- 不为了演示效果制造 fake Ticket completion、fake evidence、fake memory。
- 不把 Settings 页变成高风险操作主入口；高风险 approve / resume 应进入 Review / Runtime governance surface。

## 18. Loop 执行落地 Prompt

可用于 `/Goal` 的执行 prompt：

```text
继续实现 /home/shiqiangli/projects/AITeamOS/plan_v5.md。

先读取 plan_v5.md，严格遵守最终目标基线：
- AITeamOS 是以 Ticket 流转为核心的 AI Team Operating System。
- Employees 是固定身份、技能、性格、权限、工作历史和记忆范围的成员。
- Tickets 是协作、交接、汇报、验证、审批、阻塞处理和沉淀结论的主通道。
- Assets 是 Memory、Docs、Skills、Tooling calls、解决方案、建议、复盘、验证结果和 closeout 的长期资产层。
- AITeamOS 不自研通用 Agent；通用 agent loop、tool use、handoff、checkpoint、approval、interrupt/resume 优先复用 LangGraph 或商业 Agent Runtime。
- Chat route 只做入口和桥接，不承载 agent loop。

执行方式：
1. 先检查 git status，识别已有未提交改动；不得回滚用户或既有改动。
2. 阅读 plan_v5.md 中最高优先级尚未完成 Phase。默认顺序：Phase G -> Phase H -> Phase I -> Phase J -> Phase K -> Phase L -> Phase M -> Phase N -> Phase O -> Phase P。
3. 每轮只做一个可验证 slice，但如果上下文和测试允许，可以连续完成多个 slice。
4. 每个 slice 必须小步实现、写测试、运行相关验证，并把进展记录回 plan_v5.md。
5. 所有写操作必须通过 AITeamOS governed artifacts / ingestion / provider adapter 边界；不要绕过 Ticket / Asset / Employee model。
6. Approval / checkpoint / replay / provenance 是高优先级，不要为了表面完成跳过。
7. 如果遇到真实 blocker，把 blocker、证据、下一步决策点写入 plan_v5.md 并停止。
8. 如果一个 Phase 完成，继续下一个 Phase，直到 plan_v5.md 完成、遇到真实 blocker，或需要用户产品决策。

第一轮从 Phase G 开始：实现 LangGraph approval interrupt / resume 的最小可验证闭环。
```

## 19. 完成定义

达到最终目标至少需要满足：

- 任意 Chat 问题都能进入 Employee-aware LangGraph runtime，并自动编排 Employee / Ticket / Assets / Memory / Skills / Docs / Tooling context。
- 复杂任务能以 Ticket 为核心持续推进，多 Employee handoff、approval、validation、report、evidence 都有 ledger。
- 所有长期知识都进入 Assets 生命周期，带 provenance、review、provider projection 和 retrieval feedback。
- Employees 有固定身份、能力、性格、权限、工作历史和记忆范围，并能影响 agent behavior。
- Human 能在 UI 中看到、审批、恢复、复盘每一次 runtime execution。
- Plane / Graphiti / commercial runtime / local fallback 都是可替换 provider。
- 系统遇到 blocker 时不假完成，而是写入 Ticket、Review Queue 和 Replay。
