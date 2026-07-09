# AITeamOS plan_v7: Production Autonomous Team Loop

状态：`plan_v6.md` 之后的生产化主计划
日期：2026-06-19
决策：`plan_v6.md` 已经证明本地/live provider 闭环可跑通；`plan_v7.md` 不推翻 v6，而是在同一句话目标、核心原则、基本方案和架构上，把 AITeamOS 打磨成可靠、可维护、可扩展的真实 AI Team Operating System。

## 0. 继承 v6 的一句话目标

直接重建 Chat 为 LangGraph-native Agent Workbench：以 Agent Chat UI 为页面蓝本，以 LangChain Frontend SDK 为 runtime，以 assistant-ui 作为组件复用来源，以 AITeamOS Ticket / Employees / Assets / Governance 作为唯一产品核心；AG-UI 只保留为可选协议兼容层。

`plan_v7` 的一句话补充：

在 v6 已打通 Chat -> Employee -> Ticket -> Approval -> Assets -> Graphiti -> Recall 的基础上，让 LangGraph 真正成为生产级 autonomous team loop 的编排大脑，让 AITeamOS 的 Ticket / Employees / Assets / Governance 成为长期稳定的团队运行系统，而不是只证明一次闭环可跑通。

### 0.1 方向纠偏：core loop 与 repo-write adapter 分层

2026-06-21 更新：后续实现必须把两个概念严格分开，避免 production-readiness 走向错误道路。

- **核心 autonomous team loop**：默认必须是 `LangGraph / Agent Server -> AITeamOS Workbench graph -> Ticket / Employees / Assets / Governance -> Graphiti projection / recall`。
- **默认 LLM provider**：暂定为 DeepSeek API，但 DeepSeek 只能作为 LangGraph / LangChain model layer 后面的模型供应商；AITeamOS 不应该在 Chat route、Ticket loop、Employee orchestration 或领域服务里直接自研一条 LLM 调用链。
- **Codex CLI / Claude Code / OpenHands 等**：只属于可选的 external repo-write / coding RuntimeExecutor adapter conformance；它们可以被 governed dispatch 调用，但不能成为 AITeamOS 的默认 agent runtime 或 production-readiness 主证明。
- **direct LLM 残留处理**：`direct_llm` 不再允许作为默认 registry / dispatch executor 存在；`chat_ai_engine_service` 只能负责设置、provider config、model metadata 和 blocker visibility，不能定义另一条 AITeamOS-owned agent/runtime path。旧 `direct_llm` 参数只能 fail closed 或落回 LangGraph / Universal Employee Agent，不能重新打开直接模型 executor。
- **dogfood 证明顺序**：先证明 LangGraph + DeepSeek provider 的 core loop dogfood，再单独证明 Codex CLI 等 repo-write adapter dogfood；不能用 Codex CLI dogfood 代替 LangGraph core loop 证明。

### 0.2 最新控制门禁：DirectLLM 不得回流

2026-06-21 更新：本节是后续 loop 的硬门禁，优先于下方任何较早的历史执行记录。

- **当前实现标准**：AITeamOS 不保留自己拥有的 direct LLM executor；`DirectLLMExecutor` 已删除，默认 RuntimeExecutor registry、dispatch、System Status、provider conformance 和 production-readiness 最新 evidence 都必须保持 direct-free。
- **DeepSeek 的位置**：DeepSeek API 暂定为默认 LLM provider，但只能通过 `LangChainModelProvider` / LangGraph model layer 使用。非 mutating smoke 只能证明 provider config / blocker visibility；真实 live dogfood 必须证明请求进入 LangGraph core loop 后再触达 DeepSeek provider。
- **历史记录处理**：下方早于 `Track H2 hard removal of DirectLLMExecutor from runtime registry` 的执行记录里，如果出现“explicit diagnostic DirectLLMExecutor remains”等表述，一律视为已 superseded 的历史状态，不能作为未来实现依据。
- **允许出现的位置**：`direct_llm` 字符串只允许出现在负向回归测试、artifact summary guard、历史 artifact 或历史计划记录里；不得出现在当前 production implementation、默认 runtime evidence 或完成条件里。
- **证据门禁**：`plan_v7_artifact_summary.py` 必须在最新 runtime registry evidence 中发现 `direct_llm` 时报告 `runtime_registry_direct_llm_present`，在 core loop selected executor 不是 `langgraph` 时报告 `runtime_registry_core_loop_not_langgraph`。
- **legacy 输入**：历史 `executor_id=direct_llm` 只能落回 LangGraph / Universal Employee Agent，或 fail closed 并显示 blocker；不能重新创建 AITeamOS 直连模型 runtime。

### 0.3 最新控制门禁：Live dogfood 成功不能只看 final node

2026-06-21 更新：live-provider dogfood 已暴露一个关键风险：LangGraph graph 可以到达 `final_response` / `runtime_status.status=completed`，但 AITeamOS governed execution 仍可能因为 Plane / Graphiti / provider 写入失败而处于 `blocked`。后续 loop 必须按本节判断成功。

- **成功判定**：core-loop live dogfood 必须同时满足 `profile=core_loop`、`executor_id=langgraph`、DeepSeek 只在 LangGraph / LangChain model layer 后面、Workbench final state 完成、`aiteamos_chat_response.run_metadata.execution.status` 为 `completed` 或可接受的 `partial`、Ticket / Assets / Graphiti 所需写入完成、artifact summary 无 evidence gap。
- **自然 handoff 判定**：如果本轮目标是证明真实长期 Employee profile 下的 natural handoff，必须看到 durable Ticket-backed handoff：`handoff_summary.status=durable_handoff_recorded`、target Employee 符合预期、`ticket_handoff_refs` 至少 1 条。仅看到模型提出 handoff 或 trace event 不算完成。
- **provider blocker 判定**：Plane 502、Graphiti projection / recall failure、MemoryCandidate approval failure、Ticket report 写入失败，都必须作为 blocker 显示和记录；不能通过改走 Codex CLI、直接 DeepSeek、answer-only summary 或跳过 Asset/Graphiti 来伪造成功。
- **证据保存**：失败的 live run 也是有价值证据，必须写入 `plan_v7.md` 和 artifacts，标清是 provider/blocker 风险，而不是架构方向失败。后续优先修 provider/action health 或 provider mapping，再重跑同一个 LangGraph core-loop gate。
- **防偏航要求**：遇到 live provider blocker 时，不允许新增 AITeamOS-owned direct LLM path；不允许把 Codex CLI/repo-write adapter dogfood 作为 core-loop 替代证明；不允许在 route handler 里临时塞 agent loop。

## 1. v7 的硬原则

这些原则延续 v6，且优先级高于任何实现便利：

- AITeamOS 自己掌控：Ticket 流转、Employee 身份和权限、Assets 生命周期、治理审批、provenance、provider adapter、业务事实账本。
- AITeamOS 不自研：通用 Chat UI、通用 agent loop、通用 streaming protocol、通用 checkpoint / interrupt UI、通用 trace IDE、通用 memory database。
- LangGraph 是 default agent runtime；LangGraph 已经有的 execution / interrupt / checkpoint / resume / thread / graph state 能力，不在 AITeamOS 里重做。DeepSeek API 是暂定默认 LLM provider，但必须挂在 LangGraph / LangChain model layer 后面。
- LangChain Frontend SDK / assistant-ui 提供 Chat runtime 和交互 primitives；AITeamOS 只做 Ticket / Employee / Asset / Approval / Provenance 等业务面板。
- Graphiti 是 approved Assets 的 projection / retrieval provider，不是 source of truth。
- LangGraph store/checkpointer 只保存 runtime continuity，不保存 AITeamOS durable memory。
- Provider 可以是 Plane、Graphiti、DeepSeek model provider、Codex CLI、商业 agent API 或本地实现，但必须挂在 AITeamOS governance boundary 后面；其中 Codex CLI 等外部 coding agent 只是 optional RuntimeExecutor adapter，不是主 runtime。
- AITeamOS 不允许把 Chat route / Ticket loop / Employee orchestration 重新变成直接 LLM 调用器；任何 direct LLM 残留都必须被降级为 diagnostics/compatibility 或迁移清理项。
- 不为了兼容旧实现而保留错误架构；现在没有正式用户，直接走正确方案。

## 2. 当前状态判断

v6 已经达到 local/live provider proof，但 v7 从 2026-06-21 起采用更严格的证据分层：

- 主 Chat 路线已经切到 LangGraph-native Workbench。
- 前端 runtime 已接入 LangChain / assistant-ui。
- AG-UI 已从主 Chat 路线降级为 optional compatibility。
- RuntimeExecutor 可以调用 Codex CLI 作为外部 repo-write / coding agent adapter；这只是 optional adapter evidence，不是 core-loop production-readiness 主证明。
- Plane Ticket、ExecutionApproval、Ticket report/evidence、MemoryCandidate、AssetRecord、Graphiti projection、Graphiti recall 已经被真实 dogfood 证明；`live_provider_dogfood` 已有 `core_loop` / `repo_write_adapter` profile 分层，且已有生产 readiness run 用 `executor_id=langgraph` 完成 `core_loop` live dogfood。2026-06-21 新增的更严格 natural handoff gate 发现 Plane 502 可让 graph final node 完成但 governed execution blocked；因此后续不能只沿用旧 completed 证据，必须按 0.3 重新证明 live-provider natural handoff / provider writes。后续不能再把 `repo_write_adapter` 或 Codex CLI dogfood 当作 core-loop 完成证据。
- LangGraph / Universal Employee Agent 的模型调用已收敛到 `LangChainModelProvider`；DeepSeek/OpenAI 通过 LangChain provider integration 进入 graph 内部，Chat command planner 也不再自建 DeepSeek HTTP 调用链。`DirectLLMExecutor` 已从默认 RuntimeExecutor registry / dispatch 中移除。
- Durable memory 仍由 AITeamOS Assets / Review Queue / AssetRecord 管理，Graphiti 只是投影和召回。
- 旧的 `--executor-id codex_cli` live dogfood 命令不得再作为 v7 complete 的默认证明；它只证明 repo-write adapter conformance。

但这只是“能跑通的闭环”，不是完整生产级 autonomous agent loop。

当前离最终目标的主要差距：

- LangGraph graph 的主执行路径已经通过 `ExecutionRequest` / `ExecutionResult` 进入 Workbench node/service 边界；context/session/transcript 准备已经集中到 `WorkbenchRuntimeContextService`，`close_or_continue_ticket_loop` 已读取 Ticket loop timeline / policy facts 并进入 graph state，且 `propose_closeout_assets` 决策已能复用既有 closeout Asset candidate 服务幂等落地候选资产；剩余兼容性主要是该服务仍复用 `chat_runtime_factory` 的共享领域能力。
- 本地 LangGraph Agent Server 关键路径已可不带 `--allow-blocking` 跑通，并已有 read-only、answer-only、provider-blocker、approval/resume、approval review 三分支、memory-scope/risk-aware Employee handoff policy matrix smoke；Runtime Replay artifact smoke / summary gate 已直接 assert handoff target、memory-scope、risk-boundary 和 refs。生产兼容 smoke 仍需继续扩大到 repeated Ticket loop under Agent Server/live load、更多 external runtime/provider 路径。
- Chat 页面已经接入成熟 runtime，但单文件仍偏大；Ticket loop resubmit UX、Latest Run / Runtime Dispatch、Asset candidate review/projection、run provenance / recalled memory / provider refs、Scoped/Universal Context provider blockers、current Employee、trace、details shell / Thread Context chrome、Thread History/sidebar chrome、Employee selector chrome、quick engine controls、Ticket / pending approval chrome、main composer/thread shell 已在 Workbench panel 侧接入，run metadata / Workbench snapshot 的 panel view-model 装配已收束到专门模块，并复用现有 assistant-ui primitives、Ticket timeline / resume API、Assets API、Runtime Replay 路由和 AI Engine settings API，剩余问题是继续拆分 runtime adapter bridge callbacks、thread/API state 和未来 code splitting。
- Approval review 已有 reject、request changes、补证据的 Chat/route/Ticket loop 路径，并已纳入默认 v7 artifact 检查；Agent Server matrix 已覆盖 evidence_requested、rejected、changes_requested review；Workbench 现在可从 `waiting_changes` / `waiting_evidence` 直接排队 governed retry，仍需补长期拒绝/abandonment 的沉淀体验。
- Context retrieval 已能汇总 Employee / Ticket / Assets / Memory / related tickets，LangGraph `retrieve_context` 节点已接入 Graphiti-backed scoped recall，并有 Graphiti fake-provider eval / artifact smoke 证明 approved Asset 能进入 `universal_context.memory_context`、错误 Ticket scope 会被过滤、stale/conflicted Graphiti results 会进入 `stale_memory_hints` / retrieval audit excluded，且 artifact summary 已能暴露 active/excluded 计数；approved AssetRecord 的 `supersedes` / `conflicts_with` relationships 已能把被替代/冲突的 Asset 移出 active relevant Assets，并进入 `asset_context.relationship_hints` / retrieval audit excluded；相关性排序仍偏 heuristic，真实 Neo4j / Graphiti provider dogfood 仍需补。
- Employee 已有 Ticket-backed work ledger、current load projection、work-history-aware handoff、load-aware handoff，并已补上 memory scope / risk boundary 参与 handoff policy；Agent Server matrix 已证明 Clara -> Ticket -> LangGraph graph -> durable handoff 可以保留 memory/risk policy facts 并把 Ticket 交接给符合范围和风险边界的 Employee；Runtime Replay、Runtime Replay artifact smoke / summary gate 和 Employee detail UI 已能展示并验证 handoff target / memory-scope / risk-boundary facts。仍未完成能力成长记录、长期质量反馈闭环、完整 Employee detail UI 和 live-provider natural handoff dogfood。
- Ticket loop queue reliability 已有默认 v7 artifact 覆盖：重复队列、stale running、provider blocked、重复失败 retrospective candidate、worker policy action、多 tick daemon worker evidence、6-tick long-soak artifact evidence，且 artifact summary 已能同时暴露 daemon tick / processed / min_ticks / soak_passed / last_error 以及 repeated-failure policy evidence，包括 `failed_delta`、`processed_statuses`、`asset_candidate_ids`、`policy_action_kinds`、`worker_policy_action_delta`；SLA / recurrence / closeout policy metadata 已进入 Ticket loop policy 和 timeline summary，SLA breach preflight 已由既有 queue worker 写入 Ticket report / policy_actions、通过现有 Ticket handoff 交接给 escalation Employee，并通过既有 `enqueue_ticket_loop()` 排队 targeted escalation governed run；recurrence due 已能通过既有 queue worker / `enqueue_ticket_loop()` 幂等自动排队并推进 `next_run_at`，queue worker policy actions 已投影进 Workbench graph `ticket_loop_decision`，并已在 Chat Workbench 的 Ticket Loop Policy panel 渲染 action / handoff / queue / run / report refs，closeout Asset candidate proposal 已可从 LangGraph 节点调用既有服务幂等执行，Ticket closeout settlement 已可通过显式 request 复用 Review Queue / AssetRecord / Graphiti projection 完成 approved Assets 沉淀，并已在 Tickets UI 暴露显式 settlement 控制与 provider blocker 呈现；closeout policy 已支持显式 `auto_settle_assets` / `auto_approve_candidates` / Graphiti projection criteria，并由 LangGraph `close_or_continue_ticket_loop` 复用既有 settlement 服务自动沉淀 approved Assets；仍需补真实部署级长时 worker soak 和 repeated queued Ticket-loop under live-provider load。
- Assets 体系已成型，approved closeout solution Asset 已有 retrieval golden eval 覆盖并会优先进入 Ticket-scoped context，Graphiti-backed scoped recall 已进入 LangGraph context node 并有 eval 覆盖，stale/conflicted Graphiti results 已能作为 excluded hints 呈现；approved AssetRecord relationship projection、Graphiti relationship replay 幂等性、stale-memory cleanup 已有默认 artifact smoke / summary evidence 覆盖；relationship-level `supersedes` / `conflicts_with` 已进入 universal context 和 audit；仍需要更强的 schema、真实 Graphiti provider dogfood 和更丰富的 ranking / conflict-resolution policy。

## 3. v7 目标

v7 不是再证明一次 dogfood，而是把系统打磨到可长期运行。

完成 v7 时，AITeamOS 应该具备：

- 用户在 Chat 提问时，LangGraph 自动编排 Employee identity、Ticket state、Assets、Memory、Docs、Skills、related tickets、provider blockers，并给出带 provenance 的回答或行动。
- 每个高风险行动都通过 LangGraph interrupt 和 AITeamOS approval record 进入治理流程。
- 每个行动结果都写回 Ticket report/evidence，并按规则提出 Asset candidates。
- 被 approve 的 memory/docs/solutions/decisions/tooling calls 会进入 AssetRecord，并可投影到 Graphiti 召回。
- Employee 像真实成员一样拥有固定身份、能力标签、性格标签、权限边界、工作历史、记忆范围、当前负载和 handoff 策略。
- Tickets 是所有 Employee 交接、沟通、验证、复盘和沉淀的主通道。
- Chat 页面不再膨胀成自研 agent UI，而是一个 thin LangGraph-native Agent Workbench。
- Agent Server 可以在不依赖 local `--allow-blocking` 的条件下运行主 graph。
- 有可重复的 eval / dogfood / smoke 套件证明系统质量不会回退。

## 4. Target Runtime Shape

```text
User
  -> AITeamOS Dashboard
      -> Chat Agent Workbench
          -> assistant-ui / LangChain Frontend SDK
          -> LangGraph Agent API / Agent Server
              -> aiteamos_workbench graph
                  -> DeepSeek API through LangGraph / LangChain model adapter
                  -> load_employee_identity
                  -> bind_or_create_ticket
                  -> retrieve_team_context
                  -> plan_next_action
                  -> execute_read_tools
                  -> governance_gate
                  -> interrupt_for_approval
                  -> dispatch_runtime_executor
                  -> ingest_ticket_report_evidence
                  -> propose_asset_candidates
                  -> maybe_handoff_employee
                  -> maybe_request_validation
                  -> close_or_continue_ticket_loop
      -> Ticket / Employee / Assets / Runtime panels

AITeamOS durable truth
  -> Tickets
  -> Employees
  -> Assets
  -> Governance
  -> Provider refs

Projection and recall
  -> Graphiti for approved Asset projection / retrieval
  -> optional provider adapters

External agent runtimes
  -> LangGraph-native executors
  -> Codex CLI / Claude Code / OpenHands / commercial agent APIs
  -> optional repo-write / coding adapters only
  -> all behind ExecutionRequest / ExecutionResult / approval / evidence contracts
```

Runtime boundary:

- Primary Chat / Employee / Ticket execution must enter the LangGraph Workbench graph first.
- DeepSeek is the default model provider behind LangGraph, not a separate AITeamOS agent loop.
- `direct_llm` style executors must not be registered in the default Chat / Employee / Ticket runtime path. Historical `direct_llm` parameters must not create a direct model executor; they either route into the LangGraph / Universal Employee Agent path or fail closed with a visible blocker.
- Codex CLI and similar tools are downstream RuntimeExecutors for governed coding/repo actions, not the system's default autonomous loop.

## 5. Track A: Make LangGraph the Real Orchestrator

目标：把当前 graph 中的占位节点变成真实编排节点，不再让 `execute_governed_action` 一步包办大部分工作。

Work items:

- Split `aiteamos_workbench_graph.py` into graph plus node modules:
  - `agents/workbench/state.py`
  - `agents/workbench/nodes/context.py`
  - `agents/workbench/nodes/planning.py`
  - `agents/workbench/nodes/governance.py`
  - `agents/workbench/nodes/execution.py`
  - `agents/workbench/nodes/assets.py`
  - `agents/workbench/nodes/handoff.py`
- Move context retrieval into a graph node that calls existing `ExecutionContextService`.
- Move action planning into a graph node that calls existing `ChatActionPlanningService`.
- Move governance gate into a graph node that creates or loads `ExecutionApprovalRecord`.
- Move runtime dispatch into a graph node that calls existing `ExecutionDispatchService`.
- Move ingestion into graph node boundaries that call existing `ExecutionResultIngestionService`.
- Keep `ChatExecutionRuntime` only as compatibility / shared domain service during migration, then reduce its authority.
- Preserve `ExecutionRequest` / `ExecutionResult` as the contract between LangGraph and runtime executors.

Acceptance:

- `aiteamos_workbench` graph state clearly shows each real node output.
- A normal answer-only run, inspect run, approval-required run, approved mutation run, and asset proposal run each traverse different graph paths.
- Route handlers do not gain new orchestration logic.
- LangGraph tests assert node-level transitions, not only final response.

Primary files:

- `services/api/aiteamos_api/agents/aiteamos_workbench_graph.py`
- `services/api/aiteamos_api/agents/workbench/`
- `services/api/aiteamos_api/read/chat_execution_facade.py`
- `tests/test_aiteamos_workbench_graph.py`

## 6. Track B: Agent Server Production Compatibility

目标：主 graph 可以在 LangGraph Agent Server / production-compatible runtime 中运行，不依赖 local `--allow-blocking`。

Work items:

- Identify all blocking file-backed operations hit by Agent Server import/run.
- Move sync file I/O behind explicit service functions callable through `asyncio.to_thread` or equivalent executor boundary.
- Avoid importing FastAPI route modules from graph modules.
- Ensure graph module imports are light and side-effect-safe.
- Keep exported graphs free of local-only checkpointer assumptions.
- Add a production compatibility smoke that runs without `--allow-blocking` or documents the exact remaining blocker.

Acceptance:

- `langgraph validate --config langgraph.json` passes.
- Local Agent Server can start with the production-compatible command.
- Graph smoke can create a thread, stream a run, interrupt, resume, and read final values.
- Any remaining blocking operation is listed as a provider limitation, not hidden runtime behavior.

Primary files:

- `services/api/aiteamos_api/agents/aiteamos_workbench_graph.py`
- `services/api/aiteamos_api/read/chat_execution_facade.py`
- `services/api/aiteamos_api/read/*_service.py`
- `scripts/dev-up.sh`
- `README.md`

## 7. Track C: Keep Chat Thin and Maintainable

目标：Chat 页面保持成熟 runtime + AITeamOS panels，不继续长成自研 agent UI。

Work items:

- Split `apps/dashboard/src/pages/chat/index.tsx`:
  - `chat/runtime/LangGraphWorkbenchProvider.tsx`
  - `chat/runtime/workbenchState.ts`
  - `chat/panels/TicketPanel.tsx`
  - `chat/panels/EmployeePanel.tsx`
  - `chat/panels/AssetsPanel.tsx`
  - `chat/panels/ApprovalPanel.tsx`
  - `chat/panels/ProvenancePanel.tsx`
  - `chat/panels/ProviderBlockersPanel.tsx`
  - `chat/components/ThreadChrome.tsx`
- Replace hand-written LangGraph command calls with the closest official SDK / assistant-ui primitive where available.
- Keep any remaining manual Agent Server call in one adapter module, not scattered through UI components.
- Move Asset review/projection UI out of Chat message rendering and into Workbench panels.
- Add stable panel contracts typed from graph state.

Acceptance:

- Chat page file becomes a composition shell, not a large mixed runtime/UI module.
- No AG-UI import in primary Chat path.
- All raw LangGraph API calls live in one adapter module.
- UI tests cover Workbench state panels and approval actions.

Primary files:

- `apps/dashboard/src/pages/chat/index.tsx`
- `apps/dashboard/src/pages/chat/runtime/`
- `apps/dashboard/src/pages/chat/panels/`
- `apps/dashboard/src/__tests__/chat-page.test.tsx`

## 8. Track D: Complete Governance and Approval UX

目标：approval 不只是 happy path approve/resume，而是完整团队治理流程。

Work items:

- Add Workbench UI actions:
  - Approve
  - Reject
  - Request changes
  - Ask for more evidence
  - Retry after changes
- Ensure every review action writes a Ticket report.
- Ensure rejected approvals become durable provenance and can be recalled later.
- Ensure approval resume requires a matching `ExecutionApprovalRecord`, not just a raw `approval_ref`.
- Add reviewer identity, reason, timestamp, risk level, required capability, proposed action, source checkpoint and source Ticket to the panel.
- Show approval run history and last ingestion blocker.

Acceptance:

- A rejected approval does not execute runtime mutation.
- Request-changes creates a Ticket report and keeps loop open.
- Approved execution resumes from the right checkpoint/session and writes evidence.
- UI can show pending, approved, rejected, run failed, run completed.

Primary files:

- `services/api/aiteamos_api/read/execution_approval_service.py`
- `services/api/aiteamos_api/read/runtime_executor_routes.py`
- `apps/dashboard/src/pages/chat/panels/ApprovalPanel.tsx`
- `apps/dashboard/src/api/runtimeExecutors.ts`
- `tests/test_runtime_executor_routes.py`

## 9. Track E: Retrieval Quality and Context Engineering

目标：每个问题自动编排最相关的 employee skill、backend knowledge、docs、related tickets、assets、memory，而不是简单关键词拼装。

Work items:

- Define a `UniversalContextBundle` schema as the graph-facing context contract.
- Add source-specific retrievers:
  - current Ticket
  - related Tickets
  - Ticket reports/evidence
  - Employee profile and work history
  - Skills
  - Docs / knowledge
  - approved Assets
  - Graphiti memory recall
  - provider blockers
- Add reranking / scoring layer using existing provider capabilities where possible.
- Add provenance and confidence for every included context item.
- Add retrieval budget controls so context is useful, not bloated.
- Add stale-memory detection and conflict hints.
- Build retrieval eval fixtures with golden queries.

Acceptance:

- A test query can prove which Ticket/Asset/Memory was selected and why.
- Graph state exposes context items with source, score, provenance, and exclusion reason.
- Retrieval eval reports precision-like metrics for golden queries.
- Context failures appear as provider blockers, not silent empty context.

Primary files:

- `services/api/aiteamos_api/read/execution_context_service.py`
- `services/api/aiteamos_api/read/chat_context_enrichment_service.py`
- `services/api/aiteamos_api/read/memory_service.py`
- `services/api/aiteamos_api/read/knowledge_service.py`
- `services/api/aiteamos_api/read/asset_candidate_service.py`
- `tests/test_context_retrieval_eval.py`

## 10. Track F: Employee System as Real Team Members

目标：Employees 不只是 profiles，而是有身份、能力、性格、权限、记忆范围、工作历史、负载和成长记录的团队成员。

Work items:

- Define durable Employee facts:
  - identity
  - role
  - capability tags
  - personality tags
  - skills
  - permission policy
  - memory scopes
  - current load
  - work history
  - improvement suggestions
  - preferred runtime
- Add Employee work ledger derived from Tickets and ExecutionResults.
- Add Employee handoff policy:
  - capability match
  - workload
  - validation role
  - memory scope
  - risk boundary
- Add graph node `maybe_handoff_employee`.
- Ensure handoff changes Ticket assignee / report instead of only changing Chat text.
- Add Employee detail UI panels for work history, memory scope, assigned skills, current blockers.

Acceptance:

- LangGraph can choose or recommend a handoff with explicit reasons.
- Ticket assignee changes are durable and visible.
- Employee workload affects routing.
- Employee memories are scoped and auditable.

Primary files:

- `services/api/aiteamos_api/read/employee_load_service.py`
- `services/api/aiteamos_api/read/employee_handoff_service.py`
- `services/api/aiteamos_api/read/employee_improvement_service.py`
- `services/api/aiteamos_api/read/ticket_service.py`
- `apps/dashboard/src/pages/employees/`
- `tests/test_employee_handoff_service.py`

## 11. Track G: Ticket Loop as the Operating System

目标：Tickets 成为 autonomous team loop 的主通道，而不是只作为 metadata。

Work items:

- Define Ticket loop states:
  - proposed
  - accepted
  - in_progress
  - waiting_approval
  - waiting_changes
  - waiting_validation
  - blocked
  - completed
  - closed
- Add graph node `close_or_continue_ticket_loop`.
- Add validation request and validation result flow.
- Add retry and pause/resume controls.
- Add SLA / blocker / recurrence metadata.
- Add closeout report that proposes Assets and Employee improvements.
- Add Ticket timeline UI that merges reports, evidence, approvals, assets, runtime sessions, validations.

Acceptance:

- Every autonomous run is bound to a Ticket unless it is explicitly read-only answer-only.
- A Ticket can drive multiple Employee handoffs.
- Validation is explicit and durable.
- Ticket closeout creates governed Assets and does not silently mutate memory.

Primary files:

- `services/api/aiteamos_api/read/ticket_loop_service.py`
- `services/api/aiteamos_api/read/ticket_service.py`
- `services/api/aiteamos_api/read/ticket_routes.py`
- `apps/dashboard/src/pages/tickets/`
- `tests/test_ticket_loop_service.py`

## 12. Track H: Assets as Durable Organizational Memory

目标：Assets 成为 AITeamOS 最重要的长期资产层，覆盖 memory、docs、skills、tool calls、solutions、suggestions、closeout、validation。

Work items:

- Normalize Asset schemas:
  - Memory
  - Doc
  - Skill
  - Decision
  - Tooling call
  - Solution
  - Suggestion
  - Validation result
  - Closeout
  - Employee improvement
- Enforce provenance:
  - source Ticket
  - source report
  - source Employee
  - source run
  - source tool
  - approval/review record
  - provider projection ids
- Add relationship projection:
  - Ticket -> Asset
  - Employee -> Asset
  - Skill -> Employee
  - Asset -> Graphiti episode
  - Tool call -> evidence
- Add stale/conflict review states.
- Add batch review UI with clear governance.
- Add retrieval evaluation over approved Assets.

Acceptance:

- No durable memory enters the system without Asset candidate / review / approved AssetRecord.
- Graphiti projection can be rebuilt from AssetRecords.
- Assets page shows provenance and relationship graph.
- Recall results link back to source Ticket/report/approval.

Primary files:

- `services/api/aiteamos_api/read/asset_candidate_service.py`
- `services/api/aiteamos_api/read/asset_routes.py`
- `services/api/aiteamos_api/read/memory_service.py`
- `apps/dashboard/src/pages/assets/`
- `tests/test_file_memory_routes.py`
- `tests/test_asset_retrieval_eval.py`

## 12.5 Track H2: Model Provider Boundary and Direct LLM Cleanup

目标：DeepSeek API 可以作为默认 LLM provider，但只能被 LangGraph / LangChain model layer 使用；AITeamOS 不保留绕过 LangGraph 的 primary direct-LLM agent path。

Work items:

- Inventory direct model-call surfaces:
  - `direct_llm` RuntimeExecutor
  - `chat_ai_engine_service`
  - Chat route / stream paths that call DeepSeek/OpenAI directly
  - tests or smokes that treat direct LLM as production-ready core evidence
- Move any primary Chat / Employee / Ticket-loop LLM invocation behind LangGraph graph nodes or a LangGraph-compatible model adapter.
- Keep AI Engine settings as provider configuration and blocker visibility only; it should not define a separate AITeamOS agent runtime.
- Remove `DirectLLMExecutor` from default registry / dispatch / System Status surfaces. If legacy `direct_llm` input is encountered, route it into LangGraph / Universal Employee Agent or fail closed; do not keep a direct model executor as a compatibility surface.
- Update System Status and artifact summary language so `ai_engine:deepseek` proves provider configuration/readiness, not that AITeamOS may bypass LangGraph.
- Add regression tests that fail if primary Chat / Workbench execution invokes DeepSeek directly without passing through the LangGraph runtime boundary.

Acceptance:

- A normal Chat Workbench answer, Ticket loop continuation, Employee handoff, and Asset proposal path all start from LangGraph / Agent Server.
- DeepSeek API calls are reachable only through LangGraph / LangChain model-provider wiring.
- `direct_llm` is absent from the default RuntimeExecutor registry, System Status runtime list, runtime provider conformance, and production-readiness artifact evidence.
- Provider blockers still show missing DeepSeek configuration clearly without making external model calls in read-only smokes.

Primary files:

- `services/api/aiteamos_api/agents/`
- `services/api/aiteamos_api/read/chat_execution_facade.py`
- `services/api/aiteamos_api/read/chat_ai_engine_service.py`
- `services/api/aiteamos_api/read/execution_dispatch_service.py`
- `services/api/aiteamos_api/read/runtime_executors/`
- `tests/test_aiteamos_workbench_graph.py`
- `tests/test_execution_dispatch_contract.py`
- `tests/test_file_chat_routes.py`

## 13. Track I: Runtime Executor Reliability for Optional External Adapters

目标：外部商业 agent / 开源 coding runtime 可以长期安全接入，而不是一次性 dogfood；它们是 optional RuntimeExecutor adapters，不是 LangGraph core loop 的替代品。

Work items:

- Keep `ExternalRuntimeExecutor` contract strict.
- Add executor capability manifest:
  - `agent_loop`
  - `repo:read`
  - `repo:write`
  - `terminal:run`
  - `browser:use`
  - `long_running`
  - `approval_required`
- Add cancel/pause/resume controls visible from Ticket loop.
- Add bounded retries and timeout policy.
- Add output validation and ingestion blocker surfacing.
- Add provider-specific conformance tests for Codex CLI and future providers.
- Keep unsupported providers as setup blockers, not fake success.
- Split dogfood evidence into:
  - core loop dogfood: LangGraph + DeepSeek provider + Ticket / Employees / Assets / Governance + Graphiti.
  - repo-write adapter dogfood: Codex CLI / Claude Code / OpenHands behind RuntimeExecutor governance.

Acceptance:

- Runtime executor cannot mutate repo without Ticket + approval + evidence.
- Long-running executor can be cancelled from AITeamOS control state.
- Failed runtime output becomes Ticket blocker and provider status, not hidden logs.
- At least one external runtime can pass live dogfood repeatedly without manual cleanup.
- External runtime success cannot be used to claim the LangGraph core loop is production-ready.

Primary files:

- `services/api/aiteamos_api/read/runtime_executors/`
- `services/api/aiteamos_api/read/execution_dispatch_service.py`
- `services/api/aiteamos_api/read/execution_result_ingestion_service.py`
- `services/api/aiteamos_api/read/runtime_executor_smoke_service.py`
- `services/api/aiteamos_api/read/live_provider_dogfood_service.py`
- `tests/test_execution_dispatch_contract.py`

## 14. Track J: Observability, Replay, and Evals

目标：AITeamOS 可以解释为什么做某个动作、用了哪些上下文、哪个 Employee 做的、谁批准的、产生了哪些资产，以及后来如何召回。

Work items:

- Add run trace schema aligned to:
  - LangGraph thread/run/checkpoint
  - Ticket id/report id/evidence
  - Employee id/handoff
  - ExecutionRequest/ExecutionResult
  - Approval record
  - Asset candidate/AssetRecord
  - Graphiti episode
- Add replay UI linking Chat -> Graph -> Ticket -> Runtime -> Assets.
- Add eval suites:
  - graph path eval
  - retrieval quality eval
  - approval safety eval
  - asset provenance eval
  - provider readiness eval
  - live dogfood eval
- Optional: integrate LangSmith for traces/evals without making it product truth.

Acceptance:

- Every important answer/action has a traceable provenance chain.
- A replay can reconstruct the loop from Ticket to Graphiti recall.
- CI or local smoke can catch regressions in retrieval, approval, and provider readiness.

Primary files:

- `services/api/aiteamos_api/read/execution_replay_service.py`
- `services/api/aiteamos_api/read/execution_session_store.py`
- `apps/dashboard/src/pages/runtime/`
- `tests/test_runtime_executor_routes.py`
- `tests/test_live_provider_dogfood_service.py`

## 15. Implementation Order

This is not a compatibility migration. Implement in the order that removes the largest production risk first:

1. Runtime/provider boundary correction: remove primary direct LLM paths, set DeepSeek as LangGraph-backed model provider, and split core-loop dogfood from repo-write adapter dogfood.
2. Production Agent Server compatibility.
3. LangGraph node decomposition and real orchestration.
4. Chat page decomposition into runtime adapter plus AITeamOS panels.
5. Full approval UX and rejected/request-changes flows.
6. Retrieval quality and golden evals.
7. Employee handoff and work ledger.
8. Ticket loop states and validation/closeout.
9. Assets schema/provenance/relationship hardening.
10. Runtime executor conformance and repeated repo-write adapter dogfood.
11. Observability/replay/eval dashboard.

Each implementation run should finish one verifiable slice and update this file with:

- files changed
- behavior changed
- tests run
- remaining blockers
- next concrete module
- Anti-Wheel Audit result

## 16. Tests and Verification

Minimum verification for v7 slices:

```bash
langgraph validate --config langgraph.json
pytest tests/test_aiteamos_workbench_graph.py -q
pytest tests/test_execution_dispatch_contract.py tests/test_runtime_executor_routes.py -q
pytest tests/test_file_chat_routes.py tests/test_file_memory_routes.py tests/test_file_knowledge_and_tickets.py tests/test_file_system_status_routes.py -q
npm --prefix apps/dashboard run build
npx vitest run --environment jsdom src/__tests__/chat-page.test.tsx src/__tests__/system-status-page.test.tsx
git diff --check
```

Additional verification before calling v7 complete:

```bash
pytest tests/test_context_retrieval_eval.py tests/test_asset_retrieval_eval.py -q
pytest tests/test_employee_handoff_service.py tests/test_ticket_loop_service.py -q

# Required core-loop dogfood target:
# This profile must prove LangGraph + DeepSeek provider + Ticket / Employees / Assets / Governance + Graphiti.
# The CLI now exposes this profile by default; live execution still requires explicit mutation-gate authorization.
AITEAMOS_AI_ENGINE=deepseek python scripts/live_provider_dogfood.py --readiness --profile core-loop --executor-id langgraph --workspace-dir /home/shiqiangli/projects/AITeamOS
AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 AITEAMOS_AI_ENGINE=deepseek python scripts/live_provider_dogfood.py --execute --profile core-loop --executor-id langgraph --workspace-dir /home/shiqiangli/projects/AITeamOS

# Optional repo-write adapter conformance:
# This is useful evidence for Codex CLI / Claude Code / OpenHands, but it never replaces the core-loop dogfood.
AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --profile repo-write-adapter --executor-id codex_cli --workspace-dir /home/shiqiangli/projects/AITeamOS
```

Browser verification:

- Chat Workbench normal run.
- Approval interrupt and resume.
- Reject and request-changes approval flow.
- Asset candidate review and Graphiti projection.
- Later Chat run recalls the approved Asset.
- Ticket timeline shows reports/evidence/approval/assets/runtime session.
- Runtime replay links back to LangGraph thread/checkpoint.

## 17. v7 Completion Definition

`plan_v7` is complete when:

- LangGraph nodes own the real autonomous loop, not only a wrapper around legacy Chat runtime.
- The required production dogfood proves the LangGraph core loop with DeepSeek as model provider; Codex CLI dogfood is optional repo-write adapter evidence only.
- No primary Chat / Employee / Ticket-loop path bypasses LangGraph through direct LLM calls.
- Agent Server can run the primary graph in a production-compatible mode without hidden blocking I/O assumptions.
- Chat is thin, maintainable, and based on LangChain / assistant-ui runtime primitives.
- Approval supports approve, reject, request changes, retry, and durable Ticket reports.
- Retrieval has golden evals and exposes provenance, confidence, and exclusion reasons.
- Employee handoff is driven by capabilities, load, memory scope, risk, and Ticket state.
- Ticket loop supports validation, blockers, retries, handoff, closeout, and Asset proposal.
- Assets enforce candidate -> review -> approved AssetRecord -> Graphiti projection.
- External RuntimeExecutors are governed, cancelable, observable, and repeatedly dogfooded.
- Replay/eval can trace Chat -> LangGraph -> Ticket -> Employee -> Runtime -> Approval -> Assets -> Graphiti -> Recall.
- Anti-Wheel Audit passes with no main-path custom generic agent loop, generic chat runtime, generic streaming protocol, or custom memory database.

## 18. Anti-Wheel Audit

Before marking any v7 slice done, answer:

- Did this add a generic agent loop that LangGraph should own?
- Did this add custom streaming/thread/tool-call state that LangChain Frontend SDK or assistant-ui should own?
- Did this add durable memory outside Assets / Review / AssetRecord?
- Did this make Graphiti or LangGraph store the source of truth?
- Did this bypass Ticket / Employee / Approval governance?
- Did this let AITeamOS call DeepSeek/OpenAI directly from the primary Chat / Ticket / Employee loop instead of through LangGraph / LangChain model-provider wiring?
- Did this treat Codex CLI or another repo-write adapter as the default autonomous loop instead of optional RuntimeExecutor conformance?
- Did this grow route handlers with orchestration that belongs in graph/services?
- Did this make Chat UI responsible for business facts instead of graph state / domain APIs?
- Did this duplicate an existing provider feature instead of adapting it behind AITeamOS boundaries?

If any answer is yes, revise the implementation before continuing.

## 19. Execution Log

### 2026-06-19: Track B/A route-free Chat runtime boundary

Goal: make the LangGraph non-HTTP execution path production-compatible enough to start through LangGraph Agent Server without importing the FastAPI Chat route module as its runtime factory.

Files changed:

- Added `services/api/aiteamos_api/read/chat_runtime_factory.py`.
- Updated `services/api/aiteamos_api/read/chat_execution_facade.py`.
- Updated `services/api/aiteamos_api/read/chat_routes.py`.

What changed:

- Introduced a route-free `build_chat_execution_runtime()` factory that assembles the existing `ChatExecutionRuntime`, governance, action planning, execution dispatch, result ingestion, context enrichment, transcript persistence, run metadata, thread metadata, and employee load services without importing `chat_routes.py`.
- Switched `chat_execution_facade.py` to build the runtime from the new factory, so LangGraph graph execution no longer reaches back into the FastAPI route module.
- Kept the HTTP Chat route behavior aligned by delegating `get_chat_execution_runtime()` to the same factory.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/chat_runtime_factory.py services/api/aiteamos_api/read/chat_execution_facade.py services/api/aiteamos_api/read/chat_routes.py services/api/aiteamos_api/agents/aiteamos_workbench_graph.py`
- `pytest tests/test_aiteamos_workbench_graph.py tests/test_file_chat_routes.py -q` -> 42 passed.
- `pytest tests/test_execution_dispatch_contract.py tests/test_runtime_executor_routes.py -q` -> 94 passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check`
- `timeout 25 langgraph dev --host 127.0.0.1 --port 2030 --no-reload` started successfully without `--allow-blocking`; the process exited only because `timeout` stopped the healthy dev server.
- LangGraph SDK smoke against `http://127.0.0.1:2031` ran `aiteamos_workbench_approval_fixture` and returned `runtime_status.status=needs_approval`, `interrupt_count=1`, and `approval_ref=approval-fixture-1`.

Remaining gaps:

- This proves Agent Server startup plus deterministic approval interrupt wiring, not the full normal business graph under production load.
- `chat_routes.py` still contains route-local helper history that should be removed or merged after the new factory fully owns runtime assembly.
- The primary graph still needs node decomposition into `context_prepare`, `employee_select`, `plan`, `dispatch`, `approval_gate`, `ticket_update`, `asset_candidate`, and `respond` modules.
- Some runtime services still use file-backed synchronous I/O internally; v7 should continue pushing those boundaries behind explicit service/executor calls rather than route or graph import side effects.

Anti-Wheel Audit:

- No custom generic agent loop was added.
- No custom streaming protocol or checkpoint UI was added.
- No durable memory store was added outside Assets / Review / AssetRecord / Graphiti projection.
- No Ticket / Employee / Approval governance path was bypassed.
- The slice reduced route-handler orchestration coupling by moving non-HTTP runtime assembly into a service factory.

### 2026-06-19: Track A/B graph node decomposition and production run smoke

Goal: move the main Workbench graph closer to real LangGraph node orchestration while removing the blocking I/O failures exposed by running the primary graph through LangGraph Agent Server without `--allow-blocking`.

Files changed:

- Added `services/api/aiteamos_api/agents/workbench/state.py`.
- Added `services/api/aiteamos_api/agents/workbench/nodes/context.py`.
- Added `services/api/aiteamos_api/agents/workbench/nodes/planning.py`.
- Added `services/api/aiteamos_api/agents/workbench/__init__.py`.
- Added `services/api/aiteamos_api/agents/workbench/nodes/__init__.py`.
- Updated `services/api/aiteamos_api/agents/aiteamos_workbench_graph.py`.
- Updated `services/api/aiteamos_api/read/chat_execution_facade.py`.
- Updated `services/api/aiteamos_api/read/chat_execution_service.py`.
- Updated `services/api/aiteamos_api/read/chat_governance_service.py`.
- Updated `services/api/aiteamos_api/read/memory_service.py`.
- Updated `tests/test_aiteamos_workbench_graph.py`.

What changed:

- Extracted shared graph state and helpers into `agents/workbench/state.py`.
- Replaced placeholder `load_employee_identity` with a real async LangGraph node that reuses route-free runtime helpers for Employee selection, AI Engine selection, Ticket key extraction, recent messages, initial memory/docs context, and current load metadata.
- Replaced placeholder `retrieve_context` with a real async LangGraph node that calls `ExecutionContextService` and exposes `context_bundle.source=langgraph_context_node`, `universal_context`, recalled memory refs, linked assets, provider blockers, and provenance events in graph state.
- Replaced placeholder `plan_next_action` with a real async LangGraph node that calls `ChatActionPlanningService` and exposes `action_plan` plus planner events in graph state.
- Preserved the existing `run_chat_message` compatibility seam for the still-migrating execution node, but removed the previous "thread that starts a nested event loop" facade shape.
- Moved sync file-backed runtime steps behind explicit `asyncio.to_thread` boundaries in `ChatExecutionRuntime` and `ChatGovernanceService`.
- Moved file-backed memory recall and Graphiti backend config/status lookups behind `asyncio.to_thread` where they are called from async memory search.
- Added test assertions that final graph state retains the new context/planning node outputs.

Validation:

- `python -m py_compile services/api/aiteamos_api/agents/aiteamos_workbench_graph.py services/api/aiteamos_api/agents/workbench/state.py services/api/aiteamos_api/agents/workbench/nodes/context.py services/api/aiteamos_api/agents/workbench/nodes/planning.py`
- `python -m py_compile services/api/aiteamos_api/read/chat_execution_facade.py services/api/aiteamos_api/read/chat_execution_service.py services/api/aiteamos_api/read/chat_governance_service.py services/api/aiteamos_api/read/memory_service.py`
- `pytest tests/test_aiteamos_workbench_graph.py tests/test_file_chat_routes.py -q` -> 42 passed.
- `pytest tests/test_aiteamos_workbench_graph.py tests/test_file_chat_routes.py tests/test_file_memory_routes.py -q` -> 59 passed.
- `pytest tests/test_execution_dispatch_contract.py tests/test_runtime_executor_routes.py -q` -> 94 passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check`
- `langgraph dev --host 127.0.0.1 --port 2036 --no-reload` started without `--allow-blocking`.
- LangGraph SDK primary graph smoke ran `aiteamos_workbench` with `List employees` and reached `runtime_status.status=completed`, `current_node=final_response`, `context_source=langgraph_context_node`, `planned_action=list_employees`, `employee_id=clara`.
- LangGraph SDK approval fixture smoke ran `aiteamos_workbench_approval_fixture` and returned `runtime_status.status=needs_approval`, `current_node=approval_interrupt`, `interrupt_count=1`, `approval_ref=approval-fixture-1`.

Remaining gaps:

- The main `execute_governed_action` node still delegates to `run_chat_message()`, so the graph is no longer just placeholders but still not fully decomposed into dispatch / ingestion / asset / handoff nodes.
- Graphiti enabled environments can produce noisy provider logs and a non-fatal third-party PostHog telemetry blocking warning during Graphiti search/index setup; v7 should either disable that telemetry at process startup or record it as a provider compatibility blocker.
- The primary smoke was read-only and did not prove approval resume through the main business graph; approval fixture still proves the interrupt path.
- The next concrete module remains `services/api/aiteamos_api/agents/workbench/nodes/execution.py`, splitting `execute_governed_action` into `dispatch_runtime_executor`, `ingest_ticket_report_evidence`, and `propose_asset_candidates` without duplicating LangGraph's loop.

Anti-Wheel Audit:

- No custom generic agent loop was added.
- No custom streaming protocol, checkpoint UI, or observability platform was added.
- No durable memory store was added outside Assets / Review / AssetRecord / Graphiti projection.
- Existing AITeamOS services were reused behind graph nodes instead of rebuilding context retrieval, planning, approval, memory, or runtime dispatch.
- Ticket / Employee / Asset / Approval governance remained the product boundary.

### 2026-06-19: Track A execution/assets node extraction

Goal: split the remaining execution compatibility node into graph-visible dispatch, ingestion, and asset proposal boundaries while still reusing `ChatExecutionRuntime` during migration.

Files changed:

- Added `services/api/aiteamos_api/agents/workbench/nodes/execution.py`.
- Added `services/api/aiteamos_api/agents/workbench/nodes/assets.py`.
- Updated `services/api/aiteamos_api/agents/workbench/state.py`.
- Updated `services/api/aiteamos_api/agents/aiteamos_workbench_graph.py`.
- Updated `tests/test_aiteamos_workbench_graph.py`.

What changed:

- Replaced graph node `execute_governed_action` with `dispatch_runtime_executor`.
- Replaced `ingest_result` with `ingest_ticket_report_evidence`.
- Replaced `propose_assets` with `propose_asset_candidates`.
- Preserved the existing `run_chat_message` monkeypatch/test seam through a thin wrapper while moving the visible graph boundary to execution node modules.
- Added graph state outputs for `execution_summary`, `ticket_evidence_refs`, `ticket_report_refs`, and `asset_proposal_summary`.
- Kept `ChatExecutionRuntime` as a migration compatibility service, not a new generic agent loop.

Validation:

- `python -m py_compile services/api/aiteamos_api/agents/aiteamos_workbench_graph.py services/api/aiteamos_api/agents/workbench/state.py services/api/aiteamos_api/agents/workbench/nodes/execution.py services/api/aiteamos_api/agents/workbench/nodes/assets.py`
- `pytest tests/test_aiteamos_workbench_graph.py -q` -> 4 passed.
- `python -m py_compile services/api/aiteamos_api/agents/aiteamos_workbench_graph.py services/api/aiteamos_api/agents/workbench/state.py services/api/aiteamos_api/agents/workbench/nodes/context.py services/api/aiteamos_api/agents/workbench/nodes/planning.py services/api/aiteamos_api/agents/workbench/nodes/execution.py services/api/aiteamos_api/agents/workbench/nodes/assets.py`
- `pytest tests/test_aiteamos_workbench_graph.py tests/test_file_chat_routes.py tests/test_file_memory_routes.py -q` -> 59 passed, with existing third-party warnings including a transient aiosqlite worker event-loop warning.
- `pytest tests/test_execution_dispatch_contract.py tests/test_runtime_executor_routes.py -q` -> 94 passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- LangGraph Agent Server primary graph smoke ran `aiteamos_workbench` with `List employees` and reached `runtime_status.status=completed`, `current_node=final_response`, `context_source=langgraph_context_node`, `planned_action=list_employees`, `dispatch_node=dispatch_runtime_executor`, `ingestion_node=ingest_ticket_report_evidence`, `asset_node=propose_asset_candidates`.
- LangGraph Agent Server approval fixture smoke ran `aiteamos_workbench_approval_fixture` and returned `runtime_status.status=needs_approval`, `current_node=approval_interrupt`, `interrupt_count=1`, `approval_ref=approval-fixture-1`.

Remaining gaps:

- `dispatch_runtime_executor` still delegates through the `ChatExecutionRuntime` / `run_chat_message` compatibility boundary; the next slice should build `ExecutionRequest` in graph state and call `ExecutionDispatchService` directly.
- `governance_gate` is still mostly status-oriented and should become a first-class approval record creation / load / resume node.
- `maybe_handoff_employee` still infers from the runtime response and should move to `employee_handoff_service` with durable Ticket assignee/report writes.
- The primary smoke remains read-only; v7 still needs full approval resume plus Ticket evidence/report ingestion through the main business graph.

Anti-Wheel Audit:

- No generic agent loop, chat runtime, streaming protocol, checkpoint UI, observability platform, or memory database was added.
- Existing AITeamOS runtime, context, planning, approval, memory, and execution services were reused behind LangGraph nodes.
- Ticket / Employee / Asset / Approval governance remained the source-of-truth product boundary.

### 2026-06-19: Track A direct ExecutionRequest dispatch

Goal: move the main Workbench dispatch node off the `run_chat_message()` compatibility path and onto the existing `ExecutionRequest` / `ExecutionResult` runtime contract, while preserving the Chat-compatible response payload needed by the current UI.

Files changed:

- Updated `services/api/aiteamos_api/agents/workbench/state.py`.
- Updated `services/api/aiteamos_api/agents/workbench/nodes/execution.py`.
- Updated `services/api/aiteamos_api/agents/aiteamos_workbench_graph.py`.
- Updated `tests/test_aiteamos_workbench_graph.py`.

What changed:

- Added graph state outputs for `execution_request` and `execution_result`.
- Changed the main graph `dispatch_runtime_executor` path to build an `ExecutionRequest` with `ChatGovernanceService.build_request()`.
- Injected the LangGraph context node's `scoped_context` / `universal_context` into the `ExecutionRequest.task_context`, so retrieved Employee / Ticket / Asset / Memory context becomes real runtime input.
- Dispatched through the existing `ExecutionDispatchService` and ingested through the existing `ExecutionResultIngestionService`.
- Preserved Chat-compatible `aiteamos_chat_response` by reusing route-free `chat_runtime_factory` response/metadata helpers.
- Kept an explicit compatibility helper for tests or temporary migration cases, but removed `run_chat_message()` injection from the main graph.
- Added a direct approval-interrupt graph test using a fake runtime executor while still writing real `ExecutionApprovalRecord` data through ingestion.

Validation:

- `python -m py_compile services/api/aiteamos_api/agents/aiteamos_workbench_graph.py services/api/aiteamos_api/agents/workbench/state.py services/api/aiteamos_api/agents/workbench/nodes/execution.py services/api/aiteamos_api/agents/workbench/nodes/assets.py services/api/aiteamos_api/agents/workbench/nodes/context.py services/api/aiteamos_api/agents/workbench/nodes/planning.py`
- `pytest tests/test_aiteamos_workbench_graph.py -q` -> 4 passed.
- `pytest tests/test_aiteamos_workbench_graph.py tests/test_file_chat_routes.py tests/test_file_memory_routes.py -q` -> 59 passed.
- `pytest tests/test_execution_dispatch_contract.py tests/test_runtime_executor_routes.py -q` -> 94 passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- LangGraph Agent Server primary graph smoke ran `aiteamos_workbench` with `List employees` and reached `runtime_status.status=completed`, `current_node=final_response`, `planned_action=list_employees`, `request_action=list_employees`, `result_executor=local_tool`, `result_status=completed`, `dispatch_contract=ExecutionRequest/ExecutionResult`.
- LangGraph Agent Server approval fixture smoke ran `aiteamos_workbench_approval_fixture` and returned `runtime_status.status=needs_approval`, `current_node=approval_interrupt`, `interrupt_count=1`, `approval_ref=approval-fixture-1`.

Remaining gaps:

- `governance_gate` is still status-oriented; the next concrete slice should move approval record creation / resume loading into `agents/workbench/nodes/governance.py`.
- Direct main graph approval resume still depends on the UI/API approving an `ExecutionApprovalRecord` before LangGraph resume; this must be proven end-to-end on the main business graph, not only the deterministic fixture.
- `maybe_handoff_employee` still infers from response state and should be replaced by a node backed by `employee_handoff_service`.
- Chat-compatible response construction still happens inside `dispatch_runtime_executor`; a later slice should move response shaping into a final response/panel state adapter.

Anti-Wheel Audit:

- No generic agent loop, chat runtime, streaming protocol, checkpoint UI, observability platform, or memory database was added.
- The slice reused LangGraph orchestration plus existing AITeamOS `ExecutionRequest` / `ExecutionResult` / dispatch / ingestion / approval contracts.
- Durable memory still flows through Asset candidates / Review Queue / AssetRecord / Graphiti projection.
- Ticket / Employee / Asset / Approval governance remained the source-of-truth product boundary.

### 2026-06-19: Track A governance gate and main-graph approval resume

Goal: turn `governance_gate` into a real graph node that creates the governed `ExecutionRequest`, exposes approval policy/resume state, and proves the main business graph can resume an approved runtime mutation through the existing approval contracts.

Files changed:

- Added `services/api/aiteamos_api/agents/workbench/nodes/governance.py`.
- Updated `services/api/aiteamos_api/agents/workbench/nodes/execution.py`.
- Updated `services/api/aiteamos_api/agents/workbench/state.py`.
- Updated `services/api/aiteamos_api/agents/aiteamos_workbench_graph.py`.
- Updated `services/api/aiteamos_api/read/chat_runtime_factory.py`.
- Updated `tests/test_aiteamos_workbench_graph.py`.

What changed:

- Replaced the local `governance_gate` placeholder with `agents/workbench/nodes/governance.py`.
- `governance_gate` now builds the graph-facing `ExecutionRequest` with `ChatGovernanceService.build_request()`.
- The node injects LangGraph context output into `ExecutionRequest.task_context` and writes `governance_summary`, `capability_scope`, `approval_resume`, and `approval_records` state.
- LangGraph resume now routes `approval_interrupt -> governance_gate -> dispatch_runtime_executor`, so approval record loading happens at the governance node before dispatch resumes.
- `dispatch_runtime_executor` now reuses the `ExecutionRequest` created by `governance_gate` instead of rebuilding it.
- Route-free `prepare_chat_run()` now accepts an internal graph `run_id` only when `runtime_config.source=aiteamos_workbench_graph`, keeping Chat-compatible response `run_id` aligned with `ExecutionRequest.request_id`.
- Main graph tests now prove `needs_approval -> review approval record -> Command(resume) -> approved mutation completed` using a fake runtime executor behind the existing `ExecutionDispatchService` / `ExecutionApprovalRunService` / ingestion contracts.

Validation:

- `python -m py_compile services/api/aiteamos_api/agents/aiteamos_workbench_graph.py services/api/aiteamos_api/agents/workbench/state.py services/api/aiteamos_api/agents/workbench/nodes/governance.py services/api/aiteamos_api/agents/workbench/nodes/execution.py services/api/aiteamos_api/read/chat_runtime_factory.py`
- `pytest tests/test_aiteamos_workbench_graph.py -q` -> 4 passed.
- `pytest tests/test_aiteamos_workbench_graph.py tests/test_file_chat_routes.py tests/test_file_memory_routes.py -q` -> 59 passed.
- `pytest tests/test_execution_dispatch_contract.py tests/test_runtime_executor_routes.py -q` -> 94 passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- LangGraph Agent Server primary graph smoke ran `aiteamos_workbench` with `List employees` and reached `runtime_status.status=completed`, `current_node=final_response`, `governance_summary.node=governance_gate`, `request_id=response_run_id`, `result_executor=local_tool`, `dispatch_contract=ExecutionRequest/ExecutionResult`.
- LangGraph Agent Server approval fixture smoke ran `aiteamos_workbench_approval_fixture` and returned `runtime_status.status=needs_approval`, `current_node=approval_interrupt`, `interrupt_count=1`, `approval_ref=approval-fixture-1`.

Remaining gaps:

- The main graph approval resume is proven in tests with a fake runtime executor; a later dogfood run should prove the same path with a real configured external runtime.
- Approval UX still needs reject / request changes / ask for more evidence / retry actions in the Workbench panel.
- `maybe_handoff_employee` still infers from response state and should move into `agents/workbench/nodes/handoff.py` backed by `employee_handoff_service`.
- Chat-compatible response construction still happens inside `dispatch_runtime_executor`; a later slice should move response shaping into a final response/panel-state adapter.

Anti-Wheel Audit:

- No generic agent loop, chat runtime, streaming protocol, checkpoint UI, observability platform, or memory database was added.
- The slice reused LangGraph interrupt/resume plus existing AITeamOS `ExecutionApprovalRecord`, `ExecutionApprovalRunService`, `ExecutionDispatchService`, and `ExecutionResultIngestionService`.
- Durable memory still flows through Asset candidates / Review Queue / AssetRecord / Graphiti projection.
- Ticket / Employee / Asset / Approval governance remained the source-of-truth product boundary.

### 2026-06-19: Track A/F Employee handoff graph node

Goal: move Workbench handoff from response inference into a real LangGraph node using the existing Employee handoff / execution artifact / Ticket ingestion contracts.

Files changed:

- Added `services/api/aiteamos_api/agents/workbench/nodes/handoff.py`.
- Updated `services/api/aiteamos_api/agents/workbench/state.py`.
- Updated `services/api/aiteamos_api/agents/aiteamos_workbench_graph.py`.
- Updated `services/api/aiteamos_api/read/runtime_executors/langgraph_executor.py`.
- Updated `services/api/aiteamos_api/read/universal_agent_tools.py`.
- Updated `tests/test_aiteamos_workbench_graph.py`.

What changed:

- Added `maybe_handoff_employee` as a real graph node after runtime dispatch and before Ticket ingestion.
- The node reads standard `employee_handoff_request` artifacts or `learning_delta.employee_handoff`, then exposes `handoff_decision`, `handoff_summary`, `ticket_handoff_refs`, selected Employee state, provenance, runtime status, and the Workbench handoff panel flag.
- The node reads `tickets.manage:handoff` ingestion events to distinguish durable Ticket handoffs from proposal-only handoff artifacts.
- `choose_employee_for_goal()` is now used only for no-write policy preview when no artifact exists; durable writes remain owned by `ExecutionResultIngestionService`.
- `update_workbench_state` preserves panel flags emitted by earlier graph nodes so handoff / approval panels survive final state shaping.
- `LangGraphExecutor._build_checkpointer()` now creates sqlite checkpoint directories via `asyncio.to_thread` for Agent Server compatibility.
- `LangGraphExecutor._read_context_tools()` and `UniversalAgentToolRegistry.run()` now move synchronous capability / Ticket / Asset / system-status reads behind thread boundaries when running inside async LangGraph nodes.

Validation:

- `python -m py_compile services/api/aiteamos_api/agents/aiteamos_workbench_graph.py services/api/aiteamos_api/agents/workbench/state.py services/api/aiteamos_api/agents/workbench/nodes/handoff.py services/api/aiteamos_api/read/runtime_executors/langgraph_executor.py services/api/aiteamos_api/read/universal_agent_tools.py`
- `pytest tests/test_aiteamos_workbench_graph.py -q` -> 5 passed.
- `pytest tests/test_aiteamos_workbench_graph.py tests/test_file_chat_routes.py tests/test_file_memory_routes.py -q` -> 60 passed.
- `pytest tests/test_execution_dispatch_contract.py tests/test_runtime_executor_routes.py -q` -> 94 passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check` -> passed.
- LangGraph Agent Server primary graph smoke ran `aiteamos_workbench` without `--allow-blocking`; `universal_employee_agent` produced an `employee_handoff_request`, Ticket `rd-0001` was durably handed from `clara` to `alex`, and final state reached `runtime_status.status=completed`, `executor=universal_employee_agent`, `handoff_summary.status=durable_handoff_recorded`, `workbench_panels.handoff=True`.

Remaining gaps:

- This proves the handoff node with the built-in Universal Employee Agent and local Agent Server; a later dogfood run should prove the same path with a configured external commercial runtime.
- Handoff UI can now render from graph state, but the panel still needs richer history, reason, load, policy, and approval affordances.
- Employee work ledger, capability growth, memory boundary, SLA, retry, validation, and closeout still need to be integrated into the long-running Ticket loop.
- Chat-compatible response construction still happens inside `dispatch_runtime_executor`; a later slice should move response shaping into a final response / panel-state adapter.

Anti-Wheel Audit:

- No generic agent loop, handoff protocol, memory database, streaming protocol, or checkpoint UI was added.
- The slice reused LangGraph graph nodes, existing `employee_handoff_service`, `ExecutionRequest` / `ExecutionResult`, `ExecutionResultIngestionService`, Ticket handoff records, and Universal Agent tooling.
- Durable handoff truth remains in Ticket events / reports; Graph state only exposes runtime and UI-facing projections.
- Ticket / Employee / Asset / Approval governance remained the source-of-truth product boundary.

### 2026-06-19: Track C/F Chat runtime adapter and handoff panel contract

Goal: keep Chat moving toward a thin LangGraph-native Workbench by moving LangChain / assistant-ui runtime glue out of the page file and rendering the new Employee handoff graph state from a dedicated AITeamOS panel.

Files changed:

- Added `apps/dashboard/src/pages/chat/runtime/workbenchState.ts`.
- Added `apps/dashboard/src/pages/chat/runtime/LangGraphWorkbenchProvider.tsx`.
- Added `apps/dashboard/src/pages/chat/panels/WorkbenchSnapshotPanel.tsx`.
- Updated `apps/dashboard/src/pages/chat/index.tsx`.
- Updated `apps/dashboard/src/__tests__/chat-page.test.tsx`.

What changed:

- Moved LangGraph API URL / assistant id resolution, LangGraph thread mapping, thread-state fetch, pending interrupt fetch, `input.respond` resume command, and Workbench graph-state projection into `chat/runtime/workbenchState.ts`.
- Moved `useStreamRuntime`, `useLangChainState`, `useLangChainError`, `useLangChainInterruptState`, composer run config, and assistant runtime provider wiring into `chat/runtime/LangGraphWorkbenchProvider.tsx`.
- Kept the Chat page as a composition shell for selected Employee, Ticket key, thread history, details panel, and business actions; it no longer imports `@assistant-ui/react-langchain` or `@langchain/langgraph-sdk` directly.
- Extracted the Workbench state summary into `chat/panels/WorkbenchSnapshotPanel.tsx`.
- Extended the frontend Workbench state contract with `handoff_decision`, `handoff_summary`, and `ticket_handoff_refs`.
- Rendered Employee handoff status, route, report ref, and reason in the Workbench panel so the durable Ticket handoff from the graph is visible in Chat.
- Reduced `apps/dashboard/src/pages/chat/index.tsx` from 2899 lines to 2415 lines without changing the primary Chat UX.

Validation:

- `npm --prefix apps/dashboard run build` -> passed.
- `npx vitest run --environment jsdom src/__tests__/chat-page.test.tsx` from `apps/dashboard/` -> 4 passed.
- `npx vitest run --environment jsdom src/__tests__/chat-page.test.tsx src/__tests__/system-status-page.test.tsx` from `apps/dashboard/` -> 12 passed.
- `pytest tests/test_aiteamos_workbench_graph.py -q` -> 5 passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check` -> passed.
- `rg` check confirmed primary `apps/dashboard/src/pages/chat/index.tsx` no longer directly imports LangChain runtime hooks or the LangGraph SDK; those calls live in `chat/runtime/`.

Remaining gaps:

- Chat is thinner but still too large; next slices should extract `ApprovalPanel`, `AssetsPanel`, `ProvenancePanel`, thread chrome, and Employee/Ticket panels.
- Approval UI still only covers approve/resume; reject, request changes, ask for evidence, and retry need durable Ticket reports.
- Handoff panel now shows status/route/reason/report ref, but should later include full handoff history, load, policy details, and approval affordances.
- Raw `input.respond` command is contained in the runtime adapter; a later pass should replace it with the closest official SDK primitive if LangGraph / LangChain exposes one for this exact resume command path.

Anti-Wheel Audit:

- No generic Chat UI, agent loop, streaming protocol, checkpoint UI, or memory database was added.
- The slice reused assistant-ui and LangChain Frontend SDK runtime primitives, plus the official LangGraph SDK for thread state reads.
- AITeamOS UI code only projects Ticket / Employee / Asset / Approval / Handoff business state from graph values.
- Durable handoff truth remains in Ticket reports/events; Chat only renders the graph projection.
- No route handler or backend orchestration logic was added.

### 2026-06-19: Track D Approval review actions and panel

Goal: make approval governance more than happy-path resume by adding durable review states and a dedicated Chat Workbench panel for approval, rejection, change requests, and evidence requests.

Files changed:

- Updated `services/api/aiteamos_api/read/execution_approval_service.py`.
- Updated `apps/dashboard/src/api/runtimeExecutors.ts`.
- Added `apps/dashboard/src/pages/chat/panels/ApprovalPanel.tsx`.
- Updated `apps/dashboard/src/pages/chat/index.tsx`.
- Updated `apps/dashboard/src/__tests__/chat-page.test.tsx`.
- Updated `tests/test_runtime_executor_routes.py`.

What changed:

- Added canonical approval review statuses: `approved`, `rejected`, `changes_requested`, and `evidence_requested`.
- Added aliases for operator-friendly review inputs such as `request_changes` and `ask_evidence`.
- Every review action now writes an auditable Ticket report with `approval_<status>` report type.
- Non-approved reviews remain non-mutating and keep runtime execution blocked until a later approval.
- Approved reviews record governance state but still require the governed LangGraph resume / runtime run path before any external runtime mutation happens.
- Extracted Approval Policy rendering and actions into `chat/panels/ApprovalPanel.tsx`.
- Chat approve now first records the runtime approval review, then resumes the LangGraph interrupt through the existing runtime adapter.
- Chat can now reject, request changes, and ask for more evidence from the Workbench approval panel.

Validation:

- `pytest tests/test_runtime_executor_routes.py -q` -> 16 passed.
- `pytest tests/test_aiteamos_workbench_graph.py -q` -> 5 passed.
- `npm --prefix apps/dashboard run build` -> passed.
- `npx vitest run --environment jsdom src/__tests__/chat-page.test.tsx src/__tests__/system-status-page.test.tsx` from `apps/dashboard/` -> 13 passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check` -> passed.

Remaining gaps:

- Approval review reasons are still deterministic button reasons; the panel still needs a compact free-form reviewer reason input.
- Retry-after-changes, full run history, and approval decision timeline are not yet first-class Chat panel affordances.
- Ticket loop status transitions such as waiting_changes, waiting_evidence, waiting_validation, and ready_to_resume still need tighter integration.
- A real external-runtime dogfood run is still needed to prove the approval states against a commercial runtime, not only tests and local graph paths.

Anti-Wheel Audit:

- No generic approval engine, agent loop, chat runtime, checkpoint UI, streaming protocol, or memory store was added.
- The slice reused the existing runtime approval API, ExecutionRequest / ExecutionResult contracts, Ticket reports, LangGraph interrupt resume path, LangChain runtime adapter, and assistant-ui page shell.
- AITeamOS only added product-specific governance states and UI projections around Ticket / Employee / Asset / Approval boundaries.
- Durable approval truth remains in runtime approval records plus Ticket reports; Chat only renders and triggers those governed transitions.

### 2026-06-19: Track D Approval audit details and reviewer reasons

Goal: make the Chat approval panel useful for real governance review by exposing the existing `ExecutionApprovalRecord` details, reviewer reason, run history, and ingestion blockers without adding a new approval engine.

Files changed:

- Updated `services/api/aiteamos_api/read/chat_response_metadata.py`.
- Updated `apps/dashboard/src/pages/chat/runtime/workbenchState.ts`.
- Updated `apps/dashboard/src/pages/chat/runtime/LangGraphWorkbenchProvider.tsx`.
- Updated `apps/dashboard/src/pages/chat/panels/ApprovalPanel.tsx`.
- Updated `apps/dashboard/src/pages/chat/index.tsx`.
- Updated `apps/dashboard/src/__tests__/chat-page.test.tsx`.
- Updated `tests/test_file_chat_routes.py`.

What changed:

- Added `approval_records` to Chat run metadata so replayed Chat runs can show durable approval records even without a live graph snapshot.
- Extended the Workbench frontend state contract with `approvalRecords` read from LangGraph `approval_records`.
- `ApprovalPanel` now correlates approval requests with approval records by approval ref / id.
- The panel now shows risk level, action, checkpoint ref, state ref, snapshot ref, reviewer, last run status, run history, and last ingestion blocker.
- Added a compact free-form reviewer reason field; approve, reject, request changes, and ask evidence now send the operator-provided reason when present.
- The panel can render record-only approval state after `approval_requests` is cleared by a resumed graph state.
- Chat tests now verify approval records, run history, ingestion blockers, and custom review reasons.
- `test_file_chat_routes.py` now selects the terminal evidence Plane comment by `report_type`, because approval review reports also correctly write Ticket comments.

Validation:

- `npm --prefix apps/dashboard run build` -> passed; Vite reported only the existing large chunk warning.
- `npx vitest run --environment jsdom src/__tests__/chat-page.test.tsx src/__tests__/system-status-page.test.tsx` from `apps/dashboard/` -> 13 passed.
- `pytest tests/test_aiteamos_workbench_graph.py tests/test_runtime_executor_routes.py -q` -> 21 passed.
- `pytest tests/test_file_chat_routes.py -q` -> 38 passed; only existing deprecation / aiosqlite thread warnings.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check` -> passed.

Remaining gaps:

- Retry-after-changes is still not a first-class Chat panel action.
- Approval timeline still lives inside compact run history; a dedicated Ticket timeline merge for reports, approvals, assets, runtime sessions, and validation remains Track G/J work.
- Ticket loop status transitions such as waiting_changes, waiting_evidence, waiting_validation, and ready_to_resume still need domain-level integration.
- A real external-runtime dogfood should still prove custom review reasons and approval history against a commercial runtime.

Next concrete module:

- `services/api/aiteamos_api/read/ticket_loop_service.py` plus Ticket loop UI/state projection should be the next high-value slice, because approval review states now need to drive durable Ticket loop status.

Anti-Wheel Audit:

- No generic approval runtime, timeline engine, chat UI framework, agent loop, memory database, or checkpoint viewer was added.
- The slice reused existing `ExecutionApprovalRecord`, Ticket reports, Chat metadata, LangGraph state, LangChain runtime hooks, and assistant-ui panel primitives.
- AITeamOS only added governance-specific projection and reviewer input around the existing approval contract.
- Durable truth remains in approval records and Ticket reports; Chat remains a Workbench surface.

### 2026-06-19: Track D/G approval review to Ticket loop status

Goal: make approval review outcomes drive durable Ticket loop state, so the autonomous loop, queue, Ticket UI, and later Employee handoff / validation paths can reason from Ticket status instead of only reading approval reports.

Files changed:

- Updated `services/api/aiteamos_api/read/ticket_loop_service.py`.
- Updated `services/api/aiteamos_api/read/execution_approval_service.py`.
- Updated `tests/test_runtime_executor_routes.py`.
- Updated `plan_v7.md`.

What changed:

- Added `sync_ticket_loop_after_approval_review()` as a Ticket-loop domain helper.
- Mapped approval review outcomes to Ticket states:
  - `approved -> ready_to_resume`
  - `rejected -> blocked`
  - `changes_requested -> waiting_changes`
  - `evidence_requested -> waiting_evidence`
- `review_execution_approval()` now persists the approval record, writes the approval Ticket report, then attempts Ticket loop status sync.
- Ticket state transition uses the existing `transition_ticket_state()` contract and emits existing `status_changed` Ticket events; no new workflow engine or state machine was added.
- Provider transition failures are surfaced as `loop_state_transition_blocked` Ticket reports instead of failing or hiding the approval review.
- Added `waiting_approval`, `waiting_changes`, `waiting_evidence`, and `waiting_validation` to default loop stop statuses so autonomous workers pause on human/evidence/validation wait states.
- Added `waiting_validation` to the validation gate status set.
- Runtime approval route tests now assert Ticket status transitions and `status_changed` provenance for approved, rejected, request-changes, and ask-evidence review actions.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/ticket_loop_service.py services/api/aiteamos_api/read/execution_approval_service.py`
- `pytest tests/test_runtime_executor_routes.py -q` -> 16 passed.
- `pytest tests/test_execution_dispatch_contract.py -q` -> 79 passed.
- `pytest tests/test_aiteamos_workbench_graph.py -q` -> 5 passed.
- `pytest tests/test_file_chat_routes.py -q` -> 38 passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check` -> passed.
- Frontend build was not run because this slice changed only backend services, backend tests, and this plan file.

Remaining gaps:

- Approval creation still does not automatically set `waiting_approval`; the next Ticket loop slice should sync requested approvals to waiting state before review.
- `ready_to_resume` is now durable, but queue / Chat / Ticket UI still need first-class retry-after-changes and resume affordances.
- Plane status mapping for new loop states still requires provider configuration; missing mappings now surface as blockers, but production setup should define explicit Plane state ids.
- The merged Ticket timeline still needs to combine reports, approvals, runtime sessions, assets, validation, and closeout.

Next concrete module:

- Continue in `services/api/aiteamos_api/read/ticket_loop_service.py` and `apps/dashboard/src/pages/tickets/` to add requested-approval `waiting_approval`, retry/resume controls, and Ticket timeline projection.

Anti-Wheel Audit:

- No generic agent loop, approval engine, workflow state machine, memory database, streaming protocol, or checkpoint UI was added.
- The slice reused LangGraph-owned runtime semantics plus existing AITeamOS approval records, Ticket reports, and Ticket state transitions.
- Durable truth remains in Ticket events/reports and approval records; provider failures are visible as Ticket blockers.
- Route handlers did not gain orchestration logic; the new behavior lives in domain services.

### 2026-06-19: Track G approval request waiting state

Goal: close the front half of the approval-status loop by moving Tickets into `waiting_approval` as soon as a runtime approval request is durably recorded.

Files changed:

- Updated `services/api/aiteamos_api/read/ticket_loop_service.py`.
- Updated `services/api/aiteamos_api/read/execution_approval_service.py`.
- Updated `tests/test_runtime_executor_routes.py`.
- Updated `tests/test_execution_dispatch_contract.py`.
- Updated `tests/test_file_chat_routes.py`.
- Updated `plan_v7.md`.

What changed:

- Added `sync_ticket_loop_after_approval_request()` to translate durable `ExecutionApprovalRecord(status=requested)` into Ticket status `waiting_approval`.
- `record_execution_approval_requests()` now syncs requested approvals after saving approval records, while skipping already-reviewed reused approval records.
- The sync uses existing `transition_ticket_state()` and `status_changed` events, preserving the Ticket ledger as the durable status source.
- If a provider such as Plane lacks a state mapping for `waiting_approval`, AITeamOS writes a `loop_state_transition_blocked` Ticket report instead of faking success or failing approval persistence.
- Ticket native loop tests now assert that an approval-gated autonomous run leaves the Ticket in `waiting_approval`.
- Runtime approval route tests now assert `waiting_approval` before approval review and later `ready_to_resume` after approval.
- Plane-backed terminal command stream tests now assert the real safety boundary: unapproved runs do not write `terminal_evidence`, while provider blocker comments are allowed and visible.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/ticket_loop_service.py services/api/aiteamos_api/read/execution_approval_service.py services/api/aiteamos_api/read/execution_result_ingestion_service.py`
- `pytest tests/test_runtime_executor_routes.py -q` -> 16 passed.
- `pytest tests/test_execution_dispatch_contract.py -q` -> 79 passed.
- `pytest tests/test_file_chat_routes.py -q` -> 38 passed, with existing third-party warnings including an aiosqlite closed-loop warning.
- `pytest tests/test_aiteamos_workbench_graph.py -q` -> 5 passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check` -> passed.
- Frontend build was not run because this slice changed backend services/tests and no frontend files.

Remaining gaps:

- Ticket UI still needs a first-class timeline projection that shows `waiting_approval`, blocker reports, approval reviews, runtime sessions, evidence, assets, validation, and closeout together.
- Queue / worker controls should expose retry/resume after approval and avoid treating `ready_to_resume` as invisible state.
- Plane production settings should define explicit state ids for `waiting_approval`, `ready_to_resume`, `waiting_changes`, `waiting_evidence`, and `waiting_validation`.
- Retry-after-changes still needs a domain action that turns `waiting_changes` back into an executable Ticket state after a new report/evidence is supplied.

Next concrete module:

- Implement Ticket timeline projection and retry/resume controls in `services/api/aiteamos_api/read/ticket_loop_service.py`, `services/api/aiteamos_api/read/ticket_routes.py`, and `apps/dashboard/src/pages/tickets/`.

Anti-Wheel Audit:

- No generic workflow engine, approval engine, agent loop, streaming protocol, memory database, or checkpoint UI was added.
- The slice reused existing approval records, Ticket state transitions, Ticket reports, and LangGraph runtime output ingestion.
- Durable truth remains in Ticket status/events/reports plus approval records; external provider limitations are visible as blockers.
- Route handlers did not gain orchestration logic; status sync stays in domain services.

### 2026-06-19: Track G/J Ticket timeline projection and resume controls

Goal: make the Ticket page a real team operating surface by projecting the Ticket loop timeline from existing durable facts, and by exposing a governed resume/retry control for Tickets that are ready after approval or waiting on changes/evidence.

Files changed:

- Updated `services/api/aiteamos_api/read/ticket_loop_service.py`.
- Updated `services/api/aiteamos_api/read/ticket_routes.py`.
- Updated `apps/dashboard/src/api/tickets.ts`.
- Updated `apps/dashboard/src/pages/tickets/index.tsx`.
- Updated `apps/dashboard/src/__tests__/tickets-page.test.tsx`.
- Updated `tests/test_execution_dispatch_contract.py`.
- Updated `plan_v7.md`.

What changed:

- Added `TicketLoopTimelineResponse` and `GET /api/v1/tickets/{ticket_id}/loop/timeline`.
- Timeline is a projection, not a new source of truth. It merges existing:
  - Ticket events
  - Ticket reports/evidence
  - runtime approval records
  - Ticket loop runs
  - loop queue items
  - runtime execution sessions
  - Ticket-linked assets
- Added timeline summary fields for current Ticket status, waiting reason, next action, `can_run`, `can_resume`, `can_retry`, source counts, and provider blockers.
- Added `TicketLoopResumeRequest` and `POST /api/v1/tickets/{ticket_id}/loop/resume`.
- Resume transitions resumable Tickets to `in_progress` via existing `transition_ticket_state()`, then queues a governed Ticket loop run through existing `enqueue_ticket_loop()`.
- Resume refuses `waiting_approval` and terminal statuses instead of bypassing approval/validation governance.
- Resume provider failures write `loop_resume_blocked` Ticket reports before returning a visible blocker.
- Tickets frontend now fetches timeline projection with each selected Ticket.
- Flow tab now renders `Team Timeline` from backend projection instead of only local Ticket events.
- Ticket detail shows timeline next action and enables `Resume Loop` / `Retry Loop` from the timeline summary.
- Frontend tests cover timeline rendering and resume API calls.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/ticket_loop_service.py services/api/aiteamos_api/read/ticket_routes.py tests/test_execution_dispatch_contract.py`
- `pytest tests/test_execution_dispatch_contract.py::test_ticket_loop_timeline_and_resume_route_project_ticket_os_facts -q` -> 1 passed.
- `pytest tests/test_execution_dispatch_contract.py -q` -> 80 passed.
- `pytest tests/test_runtime_executor_routes.py tests/test_file_chat_routes.py -q` -> 54 passed.
- `npx vitest run --environment jsdom src/__tests__/tickets-page.test.tsx` from `apps/dashboard/` -> 15 passed.
- `npm --prefix apps/dashboard run build` -> passed; Vite reported the existing large chunk warning.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check` -> passed.

Remaining gaps:

- Timeline projection is useful, but still compact; later Track J work should deep-link each item to runtime replay, asset review, approval detail, and source report/evidence.
- Resume currently queues a new governed loop run; it does not itself perform LangGraph native approval resume inside the Ticket page. Actual runtime resume remains owned by runtime approval APIs and LangGraph.
- Retry-after-changes/evidence still depends on the human or Employee having attached a new report/evidence; the UI does not yet verify that prerequisite before retry.
- Plane production configuration still needs explicit state ids for `in_progress`, `ready_to_resume`, and waiting states.

Next concrete module:

- Continue Track G/J by deep-linking timeline items to Runtime Replay / Approval / Assets, and by adding evidence-aware retry guards for `waiting_changes` and `waiting_evidence`.

Anti-Wheel Audit:

- No generic timeline engine, workflow engine, approval engine, agent loop, memory database, streaming protocol, or checkpoint UI was added.
- Timeline is a Ticket-OS projection over existing AITeamOS facts, not a new durable store.
- Resume reuses existing Ticket state transitions and loop queue contracts instead of creating a second executor path.
- Route handlers only expose domain service calls; orchestration remains in services / LangGraph runtime boundaries.

### 2026-06-19: Track G/J timeline deep links and evidence-aware retry guard

Goal: make the Ticket timeline operational, not just informational, by deep-linking timeline facts to their owning work surfaces and by preventing reviewer-requested evidence/changes from being bypassed through a blind retry.

Files changed:

- Updated `services/api/aiteamos_api/read/ticket_loop_service.py`.
- Updated `apps/dashboard/src/api/tickets.ts`.
- Updated `apps/dashboard/src/pages/tickets/index.tsx`.
- Updated `apps/dashboard/src/__tests__/tickets-page.test.tsx`.
- Updated `tests/test_execution_dispatch_contract.py`.
- Updated `plan_v7.md`.

What changed:

- Added `target_route` to Ticket loop timeline items and refs.
- Runtime sessions now link to Runtime Replay via `runtime/{session_key}`.
- Ticket-linked Assets now link to Asset detail via `assets/asset/{asset_id}`.
- Runtime approvals now link to review detail via `assets/review/runtime-approval:{executor_id}:{approval_id}`.
- Tickets `Team Timeline` now renders compact open actions for approval, runtime, and asset timeline entries.
- Timeline refs with routes are rendered as actionable controls while non-routable refs remain provenance badges.
- `resume_ticket_loop()` now enforces retry prerequisites for `waiting_changes` and `waiting_evidence`.
- `retry_after_changes` requires a new non-approval Ticket report after the latest `changes_requested` review.
- `retry_after_evidence` requires new non-approval Ticket evidence after the latest `evidence_requested` review.
- Approval review reports such as `approval_evidence_requested` no longer count as the follow-up report/evidence requested by that same review.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py` -> passed.
- `pytest tests/test_execution_dispatch_contract.py -k "ticket_loop_timeline_and_resume_route_project_ticket_os_facts or ticket_loop_retry_requires_new_evidence_and_projects_deep_links"` -> 2 passed.
- `npm exec vitest run --environment jsdom src/__tests__/tickets-page.test.tsx` from `apps/dashboard/` -> 15 passed.
- `npm test` from `apps/dashboard/` -> 62 passed.
- `npm run build` from `apps/dashboard/` -> passed; Vite reported the existing large chunk warning.

Remaining gaps:

- Timeline deep links now cover approval, runtime, and asset surfaces, but report/evidence refs still need a first-class detail surface or source drawer.
- Retry guard is backend-enforced and surfaced through existing resume errors; the UI can still be improved with preflight hints before the user clicks retry.
- Runtime approval resume is still owned by runtime approval APIs and LangGraph checkpoints; Ticket resume queues the governed next loop run rather than reimplementing native checkpoint resume.
- Plane production state mapping still needs explicit state ids for `waiting_changes`, `waiting_evidence`, `ready_to_resume`, and `waiting_validation`.

Next concrete module:

- Continue Track J by adding report/evidence detail navigation and a small retry-preflight panel on the Ticket page, then continue Track E/G with approval resume visibility and worker reliability checks.

Anti-Wheel Audit:

- No generic workflow engine, timeline engine, checkpoint UI, approval engine, agent loop, memory database, or routing framework was added.
- Deep links reuse existing AITeamOS hash routing and existing Runtime / Assets surfaces.
- Retry policy reuses existing approval records, Ticket reports, Ticket state transitions, and loop queue contracts.
- Durable truth remains in Ticket facts, approval records, runtime sessions, and Assets; LangGraph remains the runtime orchestration boundary.

### 2026-06-19: Track J report/evidence navigation and retry preflight

Goal: close the remaining Ticket timeline usability gap by making report/evidence facts navigable and by showing retry prerequisites before a user queues another governed loop run.

Files changed:

- Updated `services/api/aiteamos_api/read/ticket_loop_service.py`.
- Updated `apps/dashboard/src/api/tickets.ts`.
- Updated `apps/dashboard/src/pages/tickets/index.tsx`.
- Updated `apps/dashboard/src/__tests__/tickets-page.test.tsx`.
- Updated `tests/test_execution_dispatch_contract.py`.
- Updated `plan_v7.md`.

What changed:

- Added `TicketLoopRetryRequirement` and `summary.retry_requirements` to the Ticket loop timeline projection.
- Timeline report items now deep-link to `tickets/reports/{ticket_id}::report::{report_id}`.
- Timeline evidence refs now deep-link to `tickets/reports/{ticket_id}::evidence::{report_id}::{index}`.
- Evidence routes use report id plus index instead of embedding raw evidence text, so refs containing `/` or `::` do not break hash routing.
- Tickets route parsing now understands report/evidence focus payloads.
- Reports view can scope to a focused Ticket and highlight the selected report or evidence ref.
- Ticket detail now renders a compact `Retry Preflight` panel from backend requirements.
- `waiting_changes` shows whether a non-approval report exists after the latest `changes_requested` review.
- `waiting_evidence` shows whether a non-approval evidence ref exists after the latest `evidence_requested` review.
- Preflight rows reuse existing target routes to jump to the approval review or report location.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py` -> passed.
- `pytest tests/test_execution_dispatch_contract.py -k "ticket_loop_timeline_and_resume_route_project_ticket_os_facts or ticket_loop_retry_requires_new_evidence_and_projects_deep_links"` -> 2 passed.
- `npm exec vitest run --environment jsdom src/__tests__/tickets-page.test.tsx` from `apps/dashboard/` -> 17 passed.
- `npm test` from `apps/dashboard/` -> 64 passed.
- `npm run build` from `apps/dashboard/` -> passed; Vite reported the existing large chunk warning.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check` on tracked frontend files -> passed.
- `rg -n "[ \t]+$" services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py plan_v7.md apps/dashboard/src/api/tickets.ts apps/dashboard/src/pages/tickets/index.tsx apps/dashboard/src/__tests__/tickets-page.test.tsx` -> no matches.

Remaining gaps:

- Ticket timeline now reaches approval, runtime, asset, report, and evidence surfaces, but runtime approval resume visibility still needs to be clearer from the Ticket page.
- Retry preflight is read-only; attaching new evidence/report remains an external Employee/human action through existing Ticket report flows.
- Queue worker reliability still needs broader smoke coverage for approval resume, provider failures, and long-running queue states.
- Plane production state mapping still needs explicit state ids for `waiting_changes`, `waiting_evidence`, `ready_to_resume`, and `waiting_validation`.

Next concrete module:

- Continue Track E/G with runtime approval resume visibility in the Ticket page and queue worker reliability checks, without reimplementing LangGraph checkpoint resume in Ticket UI.

Anti-Wheel Audit:

- No generic detail router, evidence database, workflow engine, checkpoint UI, approval engine, agent loop, or memory store was added.
- Report/evidence navigation reuses the existing Tickets page and hash routing.
- Retry preflight reuses existing approval records, Ticket reports, and the backend retry guard.
- Durable truth remains in Ticket facts and approval records; the UI is only a projection and navigation layer.

### 2026-06-19: Track E/G runtime approval resume visibility and queue reliability projection

Goal: make Ticket detail show whether a runtime approval can be resumed from the existing approval surface, and whether queued Ticket loop work will actually be picked up by the queue worker, without copying LangGraph checkpoint resume into Ticket UI.

Files changed:

- Updated `services/api/aiteamos_api/read/ticket_loop_service.py`.
- Updated `apps/dashboard/src/api/tickets.ts`.
- Updated `apps/dashboard/src/pages/tickets/index.tsx`.
- Updated `apps/dashboard/src/__tests__/tickets-page.test.tsx`.
- Updated `tests/test_execution_dispatch_contract.py`.
- Updated `plan_v7.md`.

What changed:

- Added `TicketLoopApprovalResumeState` to timeline summary.
- Ticket summary now projects each related runtime approval's status, executor, capability, attempt count, last run status, ingestion blocker, and approval detail target route.
- Approved approvals with no run history are shown as ready to run from the existing Assets review / runtime approval surface.
- Requested approvals are shown as needing review before LangGraph can resume the approved runtime path.
- `changes_requested`, `evidence_requested`, and `rejected` approvals now clearly point back to Ticket next-action flow instead of appearing runnable.
- Added `TicketLoopQueueReliability` to timeline summary.
- Ticket summary now projects per-Ticket queued/running/completed/failed/active queue counts plus worker status, running state, latest activity, and last worker error.
- Ticket detail now renders `Runtime Approval Resume` and `Queue Reliability` cards from backend projection.
- The Ticket page provides `Open Approval` navigation but does not add a runtime run button; execution remains owned by Runtime Approval APIs and LangGraph checkpoint semantics.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py` -> passed.
- `pytest tests/test_execution_dispatch_contract.py -k "ticket_loop_timeline_and_resume_route_project_ticket_os_facts or ticket_loop_retry_requires_new_evidence_and_projects_deep_links"` -> 2 passed.
- `npm exec vitest run --environment jsdom src/__tests__/tickets-page.test.tsx` from `apps/dashboard/` -> 18 passed.
- `npm test` from `apps/dashboard/` -> 65 passed.
- `npm run build` from `apps/dashboard/` -> passed; Vite reported the existing large chunk warning.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check` on tracked frontend files -> passed.
- `rg -n "[ \t]+$" services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py plan_v7.md apps/dashboard/src/api/tickets.ts apps/dashboard/src/pages/tickets/index.tsx apps/dashboard/src/__tests__/tickets-page.test.tsx` -> no matches.

Remaining gaps:

- Runtime approval run itself still lives only in Assets review / Runtime approval UI; Ticket page intentionally opens that surface instead of executing it.
- Queue reliability is now visible per Ticket, but broader worker smoke coverage should still include provider failures, repeated failed queue items, and long-running queue states.
- Ticket loop still needs richer autonomous policies for recurrence, SLA, validation closeout, and failure retrospectives.
- Plane production state mapping still needs explicit state ids for `waiting_changes`, `waiting_evidence`, `ready_to_resume`, and `waiting_validation`.

Next concrete module:

- Continue Track G by adding queue worker reliability smoke cases for failed provider runs and repeated queued work, then continue Track A/B toward LangGraph node decomposition and Agent Server production compatibility.

Anti-Wheel Audit:

- No runtime approval runner, checkpoint resume UI, workflow engine, queue engine, or observability platform was added.
- Ticket detail reuses existing Assets review runtime approval routes for resume/run actions.
- Queue reliability is a projection over existing queue records and worker state, not a second scheduler.
- LangGraph remains the owner of checkpoint/resume semantics; AITeamOS only exposes Ticket-native governance visibility.

### 2026-06-19: Track G queue reliability failed-provider and duplicate-queue smoke

Goal: harden the Ticket loop queue from "visible" to "operationally trustworthy" by proving provider-blocked runs and repeated queued work surface as Ticket-native reliability signals.

Files changed:

- Updated `services/api/aiteamos_api/read/ticket_loop_service.py`.
- Updated `tests/test_execution_dispatch_contract.py`.
- Updated `apps/dashboard/src/api/tickets.ts`.
- Updated `apps/dashboard/src/pages/tickets/index.tsx`.
- Updated `apps/dashboard/src/__tests__/tickets-page.test.tsx`.
- Updated `plan_v7.md`.

What changed:

- `TicketLoopQueueReliability` now includes `duplicate_queued_count`.
- Queue reliability now treats `blocked` queue items as failed, matching `ticket_loop_queue_status()`.
- Queue reliability now treats `partial` and `needs_approval` as completed work, matching the queue status projection.
- Repeated queued work for the same Ticket now surfaces as `duplicate_queued` with a warning detail before the worker starts.
- The Ticket detail Queue Reliability card now shows `duplicate_queued` as a warning and displays duplicate queued count.
- Added a backend smoke test proving repeated queued work is visible on the Ticket timeline summary.
- Added a backend smoke test proving a blocked provider run is retained as queue item `blocked`, queue status `needs_attention`, run status `blocked`, and timeline reliability `error`.
- Frontend fixtures and types were updated so the Ticket page continues to render queue reliability from the backend contract.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py` -> passed.
- `pytest tests/test_execution_dispatch_contract.py -k "queue_reliability or ticket_loop_queue"` -> 6 passed.
- `pytest tests/test_execution_dispatch_contract.py` -> 83 passed.
- `npm exec vitest run --environment jsdom src/__tests__/tickets-page.test.tsx` from `apps/dashboard/` -> 18 passed.
- `npm test` from `apps/dashboard/` -> 65 passed.
- `npm run build` from `apps/dashboard/` -> passed; Vite reported the existing large chunk warning.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check` on tracked frontend files -> passed.
- `rg -n "[ \t]+$" services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py plan_v7.md apps/dashboard/src/api/tickets.ts apps/dashboard/src/pages/tickets/index.tsx apps/dashboard/src/__tests__/tickets-page.test.tsx` -> no matches.

Remaining gaps:

- Queue reliability now covers blocked provider runs and duplicate queued work, but still needs long-running/stale-running detection and repeated-failure retrospectives.
- Ticket loop policies still need richer recurrence, SLA, validation closeout, and failure-retrospective behavior.
- LangGraph node decomposition and Agent Server production compatibility remain the next architectural hardening area.
- Plane production state mapping still needs explicit state ids for `waiting_changes`, `waiting_evidence`, `ready_to_resume`, and `waiting_validation`.

Next concrete module:

- Continue Track A/B by decomposing the autonomous loop into LangGraph-native nodes and validating the graph against Agent Server production constraints, while keeping Ticket/Assets/Employees/Governance as the durable product layer.

Anti-Wheel Audit:

- No queue engine, retry engine, scheduler, provider health platform, observability platform, or generic agent loop was added.
- The new reliability signal is a projection over existing queue records, run records, and worker state.
- Provider failure remains visible as governed Ticket/queue state instead of being hidden behind a fake success path.
- LangGraph remains the runtime owner; AITeamOS only strengthens Ticket-native operational visibility.

### 2026-06-19: Track A/B approval and response node extraction

Goal: keep moving the primary Workbench graph from a large graph file toward explicit LangGraph node modules that are easier to test, validate under Agent Server, and maintain without recreating LangGraph runtime behavior.

Files changed:

- Updated `services/api/aiteamos_api/agents/aiteamos_workbench_graph.py`.
- Added `services/api/aiteamos_api/agents/workbench/nodes/approval.py`.
- Added `services/api/aiteamos_api/agents/workbench/nodes/response.py`.
- Updated `tests/test_aiteamos_workbench_graph.py`.
- Updated `plan_v7.md`.

What changed:

- Moved main-graph approval routing and interrupt payload construction into `workbench/nodes/approval.py`.
- Moved Workbench response projection and final AI message emission into `workbench/nodes/response.py`.
- Kept the graph file focused on graph assembly while preserving the existing fixture graph support code.
- Added node-level tests for approval interrupt routing, approval-ref bypass, response projection, provider blocker projection, and final response emission.
- Preserved the existing LangGraph interrupt/resume flow and existing `ExecutionRequest` / `ExecutionResult` contracts.

Validation:

- `python -m py_compile services/api/aiteamos_api/agents/aiteamos_workbench_graph.py services/api/aiteamos_api/agents/workbench/nodes/approval.py services/api/aiteamos_api/agents/workbench/nodes/response.py tests/test_aiteamos_workbench_graph.py` -> passed.
- `pytest tests/test_aiteamos_workbench_graph.py` -> 7 passed.
- `pytest tests/test_execution_dispatch_contract.py` -> 83 passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `rg -n "[ \t]+$" services/api/aiteamos_api/agents/aiteamos_workbench_graph.py services/api/aiteamos_api/agents/workbench/nodes/approval.py services/api/aiteamos_api/agents/workbench/nodes/response.py tests/test_aiteamos_workbench_graph.py` -> no matches.

Remaining gaps:

- `bootstrap_request`, `bind_or_create_ticket`, and `execute_read_tools` are still lightweight inline graph nodes.
- The approval fixture graph still lives in the main graph file; it is useful for deterministic Agent Server smoke, but should eventually move into a fixture/testing module if LangGraph packaging allows it.
- The next production-hardening step should prove the primary graph through a real Agent Server command again after node extraction, not only `langgraph validate`.
- The autonomous Ticket loop still needs stale-running queue detection, recurrence/SLA policy, and failure-retrospective behavior.

Next concrete module:

- Continue Track B by running/automating an Agent Server primary-graph smoke after node extraction, then continue Track A by extracting the remaining small inline nodes only if doing so improves testability rather than creating ceremony.

Anti-Wheel Audit:

- No new agent loop, checkpoint mechanism, interrupt protocol, approval engine, Chat runtime, or workflow engine was added.
- The slice only reorganized existing LangGraph node logic into node modules and tests.
- Approval semantics remain LangGraph interrupt/resume plus AITeamOS approval records.
- Workbench response state remains a projection over existing Chat/Execution metadata, not a new durable store.

### 2026-06-19: Track B repeatable Agent Server primary graph smoke

Goal: turn the previously manual primary-graph Agent Server proof into a reusable smoke command so future graph/node changes can be validated against a real running LangGraph Agent Server.

Files changed:

- Added `scripts/langgraph_agent_server_smoke.py`.
- Updated `plan_v7.md`.

What changed:

- Added a CLI smoke script that connects to an already-running LangGraph Agent Server through the official `langgraph_sdk`.
- The script creates an Agent Server thread, runs `aiteamos_workbench`, and validates expected `runtime_status.status`, `runtime_status.current_node`, `context_bundle.source`, and optional `action_plan.action`.
- Defaults target the primary graph with `List employees`, which exercises the production-compatible route-free Workbench path without external provider credentials.
- The script prints a structured JSON result and can optionally write the same payload to a file for CI or dogfood evidence.
- It intentionally does not start LangGraph, implement an agent loop, or replace LangGraph's runtime protocol.

Validation:

- `python -m py_compile scripts/langgraph_agent_server_smoke.py` -> passed.
- `python scripts/langgraph_agent_server_smoke.py --help` -> passed.
- `langgraph dev --host 127.0.0.1 --port 2047 --no-reload` was started temporarily without `--allow-blocking`.
- `python scripts/langgraph_agent_server_smoke.py --url http://127.0.0.1:2047 --assistant-id aiteamos_workbench --message "List employees" --thread-id "agent-server-smoke-after-node-extraction" --expect-action list_employees` -> passed.
- Smoke result reached `runtime_status.status=completed`, `runtime_status.current_node=final_response`, `context_bundle.source=langgraph_context_node`, and `action_plan.action=list_employees`.
- `rg -n "[ \t]+$" scripts/langgraph_agent_server_smoke.py plan_v7.md services/api/aiteamos_api/agents/aiteamos_workbench_graph.py services/api/aiteamos_api/agents/workbench/nodes/approval.py services/api/aiteamos_api/agents/workbench/nodes/response.py tests/test_aiteamos_workbench_graph.py` -> no matches.

Remaining gaps:

- The smoke assumes a separately running Agent Server; it does not manage server lifecycle for CI.
- Approval fixture smoke is still covered by graph tests and prior manual SDK runs, but this script currently validates the primary completed path only.
- A later CI wrapper could start `langgraph dev` on a free port, run this script, capture JSON evidence, and shut the server down.
- Production readiness still needs provider-backed dogfood with configured external runtime, Plane, Graphiti, and approval resume.

Next concrete module:

- Continue Track G/E by adding stale-running queue detection or Track B by wrapping Agent Server startup plus smoke into a CI-friendly command, depending on whether operational reliability or CI automation is the higher priority in the next run.

Anti-Wheel Audit:

- No custom Agent Server protocol, stream client, agent loop, checkpointer, or runtime server was added.
- The smoke uses official `langgraph_sdk` and validates existing Workbench graph state.
- Durable product state remains in Ticket / Employees / Assets / Governance; the script is only verification evidence.

### 2026-06-19: Track G stale-running queue reliability

Goal: make long-running queue items visible as an operational reliability risk so autonomous Ticket loops cannot remain stuck in `running` without a Ticket-native signal.

Files changed:

- Updated `services/api/aiteamos_api/read/ticket_loop_service.py`.
- Updated `tests/test_execution_dispatch_contract.py`.
- Updated `apps/dashboard/src/api/tickets.ts`.
- Updated `apps/dashboard/src/pages/tickets/index.tsx`.
- Updated `apps/dashboard/src/__tests__/tickets-page.test.tsx`.
- Updated `plan_v7.md`.

What changed:

- Added `QUEUE_STALE_RUNNING_SECONDS` with a conservative 15-minute threshold.
- `TicketLoopQueueReliability` now includes `stale_running_count` and `stale_running_after_seconds`.
- Queue reliability now marks stale running work as `stale_running` after failed/provider-error states and before duplicate/waiting states.
- The Ticket Queue Reliability card now renders `stale_running` as a danger state and shows stale count.
- Added a backend smoke test that rewrites a fixture queue item to old `running` state and verifies queue status plus timeline reliability projection.
- Frontend API types and fixtures were updated to preserve the queue reliability contract.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py` -> passed.
- `pytest tests/test_execution_dispatch_contract.py -k "queue_reliability or ticket_loop_queue"` -> 7 passed.
- `pytest tests/test_execution_dispatch_contract.py` -> 84 passed.
- `npm exec vitest run --environment jsdom src/__tests__/tickets-page.test.tsx` from `apps/dashboard/` -> 18 passed.
- `npm test` from `apps/dashboard/` -> 65 passed.
- `npm run build` from `apps/dashboard/` -> passed; Vite reported the existing large chunk warning.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `rg -n "[ \t]+$" services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py apps/dashboard/src/api/tickets.ts apps/dashboard/src/pages/tickets/index.tsx apps/dashboard/src/__tests__/tickets-page.test.tsx plan_v7.md` -> no matches.

Remaining gaps:

- Stale-running is now visible but not automatically remediated; a later worker policy can offer retry, cancel, or human approval options.
- Repeated failure retrospectives are still missing as durable Ticket/Asset candidates.
- Queue reliability thresholds are currently constants; they may need per-policy tuning once real production workloads exist.
- Production readiness still needs provider-backed dogfood with configured external runtime, Plane, Graphiti, and approval resume.

Next concrete module:

- Continue Track G by adding repeated-failure retrospective Asset candidates or continue Track E by proving approval resume through the real runtime approval path, while keeping LangGraph as the runtime owner.

Anti-Wheel Audit:

- No watchdog service, queue engine, scheduler, retry engine, or agent loop was added.
- Stale-running is only a projection over existing queue item timestamps and worker state.
- The UI remains a Ticket-native visibility layer; remediation stays for governed Ticket/approval/runtime flows.

### 2026-06-19: Track G repeated-failure retrospective Asset candidates

Goal: turn repeated autonomous loop failures into governed reusable learning by proposing a reviewable Asset candidate from existing Ticket loop queue facts.

Files changed:

- Updated `services/api/aiteamos_api/read/asset_candidate_service.py`.
- Updated `services/api/aiteamos_api/read/ticket_routes.py`.
- Updated `tests/test_execution_dispatch_contract.py`.
- Updated `apps/dashboard/src/api/tickets.ts`.
- Updated `plan_v7.md`.

What changed:

- Added `TicketFailureRetrospectiveAssetCandidateRequest` and `TicketFailureRetrospectiveAssetCandidateResponse`.
- Added `propose_ticket_failure_retrospective_asset_candidates()`.
- The service reads existing `TicketLoopQueueItem` facts and requires a configurable minimum number of failed/blocked queue items.
- It proposes a `failure_retrospective` `AssetCandidateRecord` with Ticket scope, queue item ids, run ids, failure statuses, queue relationships, and source Ticket provenance.
- It writes a Ticket report of type `ticket_loop_failure_retrospective_candidate` with `asset-candidate:{id}` evidence.
- Repeated calls are idempotent: existing candidate plus existing report returns `skipped` and does not duplicate reports.
- Added `POST /api/v1/tickets/{ticket_id}/failure-retrospective-candidates`.
- Added a dashboard API client function without adding a new custom UI flow.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/asset_candidate_service.py services/api/aiteamos_api/read/ticket_routes.py tests/test_execution_dispatch_contract.py` -> passed.
- `pytest tests/test_execution_dispatch_contract.py -k "failure_retrospective or closeout_candidates or queue_reliability or ticket_loop_queue"` -> 7 passed.
- `pytest tests/test_execution_dispatch_contract.py` -> 85 passed.
- `npm exec vitest run --environment jsdom src/__tests__/tickets-page.test.tsx` from `apps/dashboard/` -> 18 passed.
- `npm test` from `apps/dashboard/` -> 65 passed.
- `npm run build` from `apps/dashboard/` -> passed; Vite reported the existing large chunk warning.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `rg -n "[ \t]+$" services/api/aiteamos_api/read/asset_candidate_service.py services/api/aiteamos_api/read/ticket_routes.py tests/test_execution_dispatch_contract.py apps/dashboard/src/api/tickets.ts plan_v7.md` -> no matches.
- `git diff --check -- apps/dashboard/src/api/tickets.ts` -> passed.

Remaining gaps:

- Failure retrospectives are now reviewable candidates, but there is not yet an automated policy that proposes them immediately after the threshold is crossed.
- The Ticket UI has an API client entry but no dedicated action card for proposing failure retrospectives from Queue Reliability.
- The retrospective candidate is local-file/Asset-review backed; Graphiti projection still happens only after review/approval through the existing Asset path.
- Production readiness still needs provider-backed dogfood with configured external runtime, Plane, Graphiti, and approval resume.

Next concrete module:

- Continue Track E/G by surfacing a small Ticket Queue Reliability action for failure retrospective proposals, or Track B by wrapping Agent Server startup plus smoke into a CI-friendly command.

Anti-Wheel Audit:

- No new memory database, retrospective store, queue engine, retry engine, scheduler, agent loop, or review system was added.
- The slice reuses existing Ticket reports, `AssetCandidateRecord`, review queue, provenance, and existing queue facts.
- Durable learning remains gated by Asset candidate review and later Graphiti projection; failed runtime facts are not written straight into memory.

### 2026-06-19: Track E/G Ticket UI failure retrospective action

Status: completed.

Files changed:

- Updated `apps/dashboard/src/pages/tickets/index.tsx`.
- Updated `apps/dashboard/src/__tests__/tickets-page.test.tsx`.
- Updated `plan_v7.md`.

What changed:

- Surfaced a `Failure Retrospective` action inside the Ticket detail Queue Reliability card when repeated failed/blocked queue items cross the threshold.
- The action calls the existing `POST /api/v1/tickets/{ticket_id}/failure-retrospective-candidates` endpoint through the dashboard API client.
- The result panel shows the proposed/skipped status, failed item count, candidate Asset types, and generated Ticket report id.
- The Ticket detail resets proposal result/error state when the selected Ticket changes.
- Added a focused Ticket page test that simulates queue reliability failure, clicks the action, verifies the POST payload, and verifies the resulting Asset candidate/report projection.

Validation:

- `npm exec vitest run --environment jsdom src/__tests__/tickets-page.test.tsx` from `apps/dashboard/` -> 19 passed.
- `npm test` from `apps/dashboard/` -> 66 passed.
- `pytest tests/test_execution_dispatch_contract.py` -> 85 passed.
- `npm run build` from `apps/dashboard/` -> passed; Vite reported the existing large chunk warning.
- `python -m py_compile services/api/aiteamos_api/read/asset_candidate_service.py services/api/aiteamos_api/read/ticket_routes.py tests/test_execution_dispatch_contract.py` -> passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `rg -n "[ \t]+$" apps/dashboard/src/pages/tickets/index.tsx apps/dashboard/src/__tests__/tickets-page.test.tsx apps/dashboard/src/api/tickets.ts services/api/aiteamos_api/read/asset_candidate_service.py services/api/aiteamos_api/read/ticket_routes.py tests/test_execution_dispatch_contract.py plan_v7.md` -> no matches.
- `git diff --check -- apps/dashboard/src/pages/tickets/index.tsx apps/dashboard/src/__tests__/tickets-page.test.tsx apps/dashboard/src/api/tickets.ts services/api/aiteamos_api/read/asset_candidate_service.py services/api/aiteamos_api/read/ticket_routes.py tests/test_execution_dispatch_contract.py plan_v7.md` -> passed.

Remaining gaps:

- Failure retrospective proposal is now operator-triggered from Ticket UI; an autonomous policy node can still propose it after the threshold is crossed.
- Review/approval and Graphiti projection still rely on the existing Asset candidate path; this is correct, but needs provider-backed dogfood evidence.
- Queue reliability is visible in Ticket detail, but a broader operations view for repeated failures across Tickets is still missing.
- Production readiness still needs real configured external runtime, Plane, Graphiti, and approval-resume dogfood.

Next concrete module:

- Continue Track G by adding an autonomous policy/service that proposes failure retrospective candidates when queue reliability crosses the threshold, or continue Track B by wrapping Agent Server startup plus smoke into a CI-friendly command.

Anti-Wheel Audit:

- No new review UI, memory UI, queue engine, scheduler, agent loop, or retrospective store was added.
- The UI reuses the existing Ticket cockpit, Queue Reliability projection, dashboard API client, Ticket report path, and Asset candidate review path.
- Durable memory remains behind reviewable Assets; the UI does not write runtime failures directly into Graphiti or any memory store.

### 2026-06-19: Track G autonomous repeated-failure policy action

Status: completed.

Files changed:

- Updated `services/api/aiteamos_api/read/ticket_loop_service.py`.
- Updated `tests/test_execution_dispatch_contract.py`.
- Updated `plan_v7.md`.

What changed:

- Added `TicketLoopPolicyAction` and `policy_actions` to `TicketLoopQueuePumpResponse`.
- The existing queue pump now checks processed failed/blocked queue items after each item completes.
- When a Ticket reaches the repeated-failure threshold, the pump calls the existing governed `propose_ticket_failure_retrospective_asset_candidates()` service.
- The automatic action returns `kind`, `status`, `detail`, `candidate_ids`, and `report_id`, so worker/API callers can see the governance action instead of relying on a hidden side effect.
- Added a contract test where two blocked queue items trigger exactly one `failure_retrospective` Asset candidate and one Ticket report.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py` -> passed.
- `pytest tests/test_execution_dispatch_contract.py -k "auto_proposes_failure_retrospective or failure_retrospective or queue_reliability or ticket_loop_queue"` -> 8 passed.
- `pytest tests/test_execution_dispatch_contract.py` -> 86 passed.
- `npm test` from `apps/dashboard/` -> 66 passed.
- `npm run build` from `apps/dashboard/` -> passed; Vite reported the existing large chunk warning.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `rg -n "[ \t]+$" services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py plan_v7.md` -> no matches.
- `git diff --check -- services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py plan_v7.md` -> passed.

Remaining gaps:

- The repeated-failure threshold is still a small built-in default; a future policy registry extension can make it per Ticket or per workspace.
- The action proposes a reviewable Asset candidate, but production dogfood still needs an approved Asset projection into Graphiti and later recall evidence.
- Queue worker status records total processed items, but does not yet summarize recent `policy_actions` in worker state.
- Production readiness still needs real provider/Plane/Graphiti/approval-resume dogfood.

Next concrete module:

- Continue Track B by wrapping Agent Server startup plus smoke into a CI-friendly command, or continue Track G by adding worker-state visibility for recent policy actions.

Anti-Wheel Audit:

- No new scheduler, queue runner, memory writer, review system, or agent loop was introduced.
- The implementation reuses the existing queue pump, `AssetCandidateRecord`, Ticket report ledger, and idempotent candidate proposal service.
- Durable learning remains governed: failed queue facts become reviewable candidates, not direct memory writes.

### 2026-06-19: Track B CI-friendly Agent Server smoke wrapper

Status: completed.

Files changed:

- Added `scripts/langgraph_agent_server_ci_smoke.py`.
- Updated `README.md`.
- Updated `plan_v7.md`.

What changed:

- Added a repeatable smoke command that chooses an available local port, starts official `langgraph dev --no-reload --no-browser`, runs the existing SDK-based `langgraph_agent_server_smoke.py`, emits structured JSON, and terminates the Agent Server process group.
- The wrapper passes `AITEAMOS_WORKSPACE_DIR`, `AITEAMOS_LANGGRAPH_URL`, and `AITEAMOS_LANGGRAPH_ASSISTANT_ID` into the child process instead of inventing new configuration.
- The script preserves server logs in a temporary file and includes log tails in blocked/failed payloads.
- README now documents the one-command smoke path for local and CI use.
- A live run passed without `--allow-blocking`, which gives stronger evidence that the primary graph can run under stricter Agent Server behavior.

Validation:

- `python scripts/langgraph_agent_server_ci_smoke.py --startup-timeout 120` -> passed; selected a temporary local port and smoke checks passed.
- `ps -ef | rg "langgraph dev|47455"` -> no temporary `47455` server remained; an existing unrelated `127.0.0.1:2024` LangGraph dev process was left untouched.
- `python -m py_compile scripts/langgraph_agent_server_ci_smoke.py scripts/langgraph_agent_server_smoke.py services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py` -> passed.
- `pytest tests/test_execution_dispatch_contract.py` -> 86 passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `rg -n "[ \t]+$" scripts/langgraph_agent_server_ci_smoke.py README.md services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py plan_v7.md` -> no matches.
- `git diff --check -- scripts/langgraph_agent_server_ci_smoke.py README.md services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py plan_v7.md` -> passed.

Remaining gaps:

- This is still a local CI smoke using official `langgraph dev`; deployment-grade Agent Server packaging and hosted runtime config remain future work.
- The smoke validates the primary graph happy path; approval resume, Ticket-bound handoff, and provider-backed execution still need Agent Server smoke variants.
- The script preserves logs but does not yet upload them as CI artifacts because there is no CI workflow in the repo.

Next concrete module:

- Continue Track B by adding additional Agent Server smoke scenarios for approval resume and Ticket-bound handoff, or continue Track G by exposing recent queue `policy_actions` in worker state.

Anti-Wheel Audit:

- No new server, runtime, SDK client, graph runner, or process supervisor was introduced.
- The script wraps the official `langgraph dev` command and reuses the existing `langgraph_sdk` smoke.
- AITeamOS only adds repeatable verification and structured evidence around the chosen LangGraph runtime.

### 2026-06-19: Track G queue worker policy-action visibility

Status: completed.

Files changed:

- Updated `services/api/aiteamos_api/read/ticket_loop_service.py`.
- Updated `tests/test_execution_dispatch_contract.py`.
- Updated `apps/dashboard/src/api/tickets.ts`.
- Updated `apps/dashboard/src/pages/tickets/index.tsx`.
- Updated `apps/dashboard/src/__tests__/tickets-page.test.tsx`.
- Updated `plan_v7.md`.

What changed:

- Added `total_policy_actions` and `recent_policy_actions` to `TicketLoopQueueWorkerStatus`.
- Worker ticks now persist the most recent 20 queue policy actions from the existing pump response.
- The dashboard API types now include `TicketLoopPolicyAction` and `policy_actions` on pump responses.
- The Queue tab now shows policy action count plus the latest policy action status/kind/report id.
- Added backend coverage proving worker state persists the automatic failure retrospective policy action.
- Added dashboard coverage proving the Queue tab surfaces recent policy actions.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py scripts/langgraph_agent_server_ci_smoke.py` -> passed.
- `pytest tests/test_execution_dispatch_contract.py -k "worker_status_records_recent_policy_actions or auto_proposes_failure_retrospective or ticket_loop_queue_worker or ticket_loop_queue"` -> 9 passed.
- `npm exec vitest run --environment jsdom src/__tests__/tickets-page.test.tsx` from `apps/dashboard/` -> 19 passed.
- `pytest tests/test_execution_dispatch_contract.py` -> 87 passed.
- `npm test` from `apps/dashboard/` -> 66 passed.
- `npm run build` from `apps/dashboard/` -> passed; Vite reported the existing large chunk warning.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `rg -n "[ \t]+$" services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py apps/dashboard/src/api/tickets.ts apps/dashboard/src/pages/tickets/index.tsx apps/dashboard/src/__tests__/tickets-page.test.tsx README.md scripts/langgraph_agent_server_ci_smoke.py plan_v7.md` -> no matches.
- `git diff --check -- services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py apps/dashboard/src/api/tickets.ts apps/dashboard/src/pages/tickets/index.tsx apps/dashboard/src/__tests__/tickets-page.test.tsx README.md scripts/langgraph_agent_server_ci_smoke.py plan_v7.md` -> passed.

Remaining gaps:

- The Queue tab shows the latest policy action only; a full operations history view across Tickets is still missing.
- Worker status exposes policy actions, but there is not yet a dedicated notification or review queue shortcut from that UI block.
- Production dogfood still needs real provider failures, review approval, Graphiti projection, and later recall evidence.

Next concrete module:

- Continue Track B with Agent Server approval fixture smoke, or continue Track E/G by linking recent worker policy actions directly to the generated Ticket report and Asset candidate review route.

Anti-Wheel Audit:

- No new observability store, queue dashboard, or audit ledger was added.
- The slice reuses the existing worker state JSON, pump response, Ticket report ids, and dashboard Queue tab.
- Policy actions remain pointers to governed Asset candidates; no direct memory writes or Graphiti writes were introduced.

### 2026-06-19: Track E/G policy-action navigation

Status: completed.

Files changed:

- Updated `apps/dashboard/src/pages/tickets/index.tsx`.
- Updated `apps/dashboard/src/__tests__/tickets-page.test.tsx`.
- Updated `plan_v7.md`.

What changed:

- The Queue tab recent policy action block now includes a `Report` button when a Ticket report id is available.
- The same block includes a `Review Asset` button when an Asset candidate id is available.
- Both buttons reuse existing hash routes: `tickets/reports/...` and `assets/review/...`.
- Added dashboard coverage that clicks both buttons and verifies the resulting routes.

Validation:

- `npm exec vitest run --environment jsdom src/__tests__/tickets-page.test.tsx` from `apps/dashboard/` -> 19 passed.
- `npm test` from `apps/dashboard/` -> 66 passed.
- `pytest tests/test_execution_dispatch_contract.py` -> 87 passed.
- `npm run build` from `apps/dashboard/` -> passed; Vite reported the existing large chunk warning.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `rg -n "[ \t]+$" apps/dashboard/src/pages/tickets/index.tsx apps/dashboard/src/__tests__/tickets-page.test.tsx apps/dashboard/src/api/tickets.ts services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py plan_v7.md` -> no matches.
- `git diff --check -- apps/dashboard/src/pages/tickets/index.tsx apps/dashboard/src/__tests__/tickets-page.test.tsx apps/dashboard/src/api/tickets.ts services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py plan_v7.md` -> passed.

Remaining gaps:

- The navigation opens existing review/report surfaces, but there is not yet a dedicated operations inbox for all policy actions across Tickets.
- Asset candidate review still requires human approval, as intended; real Graphiti projection and recall evidence remain dogfood work.
- Agent Server smoke still needs approval fixture and Ticket-bound handoff variants.

Next concrete module:

- Continue Track B with Agent Server approval fixture smoke, or continue Track J by adding an operations/replay summary over queue policy actions.

Anti-Wheel Audit:

- No new report viewer, asset review UI, router, or queue operations page was added.
- The slice only connects existing policy action refs to existing product surfaces.
- Review and memory projection remain governed by the established Assets workflow.

### 2026-06-19: Track B Agent Server approval fixture smoke

Status: completed.

Files changed:

- Updated `scripts/langgraph_agent_server_smoke.py`.
- Updated `scripts/langgraph_agent_server_ci_smoke.py`.
- Updated `README.md`.
- Updated `plan_v7.md`.

What changed:

- Made the SDK smoke assertions configurable for fixture graphs that do not pass through the normal context node.
- Added optional `--expect-context-source` and `--expect-approval-ref` checks.
- The CI wrapper now forwards those assertions to the underlying SDK smoke.
- README documents both the primary happy-path smoke and the approval fixture smoke.
- A live approval fixture run now verifies `needs_approval`, `approval_interrupt`, and `approval-fixture-1` through official LangGraph Agent Server.

Validation:

- `python scripts/langgraph_agent_server_ci_smoke.py --startup-timeout 120` -> passed for `aiteamos_workbench`.
- `python scripts/langgraph_agent_server_ci_smoke.py --startup-timeout 120 --assistant-id aiteamos_workbench_approval_fixture --thread-id agent-server-ci-smoke-approval-fixture --message "Trigger deterministic approval fixture" --ticket-key rd-agent-server-approval-fixture --expect-status needs_approval --expect-current-node approval_interrupt --expect-context-source "" --expect-approval-ref approval-fixture-1` -> passed.
- `ps -ef | rg "langgraph dev|48385|48567"` -> no temporary Agent Server ports remained; an existing unrelated `127.0.0.1:2024` process was left untouched.
- `python -m py_compile scripts/langgraph_agent_server_smoke.py scripts/langgraph_agent_server_ci_smoke.py` -> passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `rg -n "[ \t]+$" scripts/langgraph_agent_server_smoke.py scripts/langgraph_agent_server_ci_smoke.py README.md plan_v7.md` -> no matches.
- `git diff --check -- scripts/langgraph_agent_server_smoke.py scripts/langgraph_agent_server_ci_smoke.py README.md plan_v7.md` -> passed.

Remaining gaps:

- Approval fixture smoke proves interrupt creation, but not full remote resume through Agent Server SDK.
- Ticket-bound handoff Agent Server smoke still needs a real non-monkeypatched fixture path.
- There is still no CI workflow file to run these commands automatically.

Next concrete module:

- Continue Track B by adding an Agent Server approval resume smoke, or continue Track J by adding CI artifact output conventions for smoke JSON/log files.

Anti-Wheel Audit:

- No custom Agent Server protocol, approval runtime, or checkpoint mechanism was introduced.
- The slice reuses official LangGraph Agent Server plus existing AITeamOS fixture graph and approval records.
- AITeamOS only made smoke assertions configurable enough to cover different existing graph shapes.

### 2026-06-19: Track B Agent Server approval resume smoke

Status: completed.

Files changed:

- Updated `scripts/langgraph_agent_server_smoke.py`.
- Updated `scripts/langgraph_agent_server_ci_smoke.py`.
- Updated `README.md`.
- Updated `plan_v7.md`.

What changed:

- Extended the SDK smoke with optional `--resume-approval-ref`.
- Resume runs submit a LangGraph Agent Server `command={"resume": ...}` against the same server thread.
- Added configurable resume checks for final runtime status and graph node.
- The smoke summary now reports resume runtime status, approval ref, active Ticket, linked asset count, and Asset candidate count.
- README now documents the approval fixture as a full interrupt-and-resume smoke.

Validation:

- `python scripts/langgraph_agent_server_ci_smoke.py --startup-timeout 120 --assistant-id aiteamos_workbench_approval_fixture --thread-id agent-server-ci-smoke-approval-resume --message "Trigger deterministic approval fixture" --ticket-key rd-agent-server-approval-resume --expect-status needs_approval --expect-current-node approval_interrupt --expect-context-source "" --expect-approval-ref approval-fixture-1 --resume-approval-ref approval-fixture-1 --expect-resume-status completed --expect-resume-current-node final_response` -> passed.
- The smoke verified initial `needs_approval` / `approval_interrupt` / `approval-fixture-1`, then resume `completed` / `final_response` / `approval-fixture-1`, with 1 linked asset and 1 Asset candidate in the resume summary.
- `ps -ef | rg "langgraph dev|45671"` -> no temporary `45671` server remained; an existing unrelated `127.0.0.1:2024` process was left untouched.
- `python -m py_compile scripts/langgraph_agent_server_smoke.py scripts/langgraph_agent_server_ci_smoke.py` -> passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `rg -n "[ \t]+$" scripts/langgraph_agent_server_smoke.py scripts/langgraph_agent_server_ci_smoke.py README.md plan_v7.md` -> no matches.
- `git diff --check -- scripts/langgraph_agent_server_smoke.py scripts/langgraph_agent_server_ci_smoke.py README.md plan_v7.md` -> passed.

Remaining gaps:

- The resume smoke uses the deterministic fixture graph; the primary graph still needs a real approval-producing Agent Server scenario.
- Ticket report id was empty in the resume summary because the fixture smoke does not seed a full local Ticket object before Agent Server execution.
- No CI workflow currently runs the smoke commands automatically.

Next concrete module:

- Continue Track B by seeding a real Ticket before Agent Server approval fixture smoke, or continue Track J by writing CI artifact conventions for smoke JSON/log files.

Anti-Wheel Audit:

- No custom resume protocol or approval engine was introduced.
- The implementation uses the official LangGraph Agent Server SDK `command` path and existing fixture graph.
- AITeamOS adds only repeatable evidence that its chosen runtime supports human approval resume.

### 2026-06-19: Track B seeded Agent Server approval resume evidence

Status: completed.

Files changed:

- Updated `scripts/langgraph_agent_server_ci_smoke.py`.
- Updated `scripts/langgraph_agent_server_smoke.py`.
- Updated `README.md`.
- Updated `plan_v7.md`.

What changed:

- Added explicit `--seed-ticket` support to the CI smoke wrapper.
- The seed path writes a minimal local-file Ticket event fixture only when requested and leaves default smoke behavior unchanged.
- Added stronger optional resume assertions: `--require-resume-ticket-report`, `--min-resume-asset-candidates`, and `--min-resume-linked-assets`.
- README now documents the seeded approval resume smoke as the recommended approval fixture command.

Validation:

- `python scripts/langgraph_agent_server_ci_smoke.py --workspace-dir /tmp/aiteamos-agent-server-seed-smoke-strong --startup-timeout 120 --assistant-id aiteamos_workbench_approval_fixture --thread-id agent-server-ci-smoke-approval-seeded-resume --message "Trigger deterministic approval fixture" --ticket-key ticket-agent-server-approval-resume --seed-ticket --expect-status needs_approval --expect-current-node approval_interrupt --expect-context-source "" --expect-approval-ref approval-fixture-1 --resume-approval-ref approval-fixture-1 --expect-resume-status completed --expect-resume-current-node final_response --require-resume-ticket-report --min-resume-asset-candidates 1 --min-resume-linked-assets 1` -> passed.
- The smoke verified a present resume Ticket report id plus at least 1 Asset candidate and 1 linked asset.
- `ps -ef | rg "langgraph dev|45653"` -> no temporary `45653` server remained; an existing unrelated `127.0.0.1:2024` process was left untouched.
- `python -m py_compile scripts/langgraph_agent_server_smoke.py scripts/langgraph_agent_server_ci_smoke.py` -> passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `rg -n "[ \t]+$" scripts/langgraph_agent_server_smoke.py scripts/langgraph_agent_server_ci_smoke.py README.md plan_v7.md` -> no matches.
- `git diff --check -- scripts/langgraph_agent_server_smoke.py scripts/langgraph_agent_server_ci_smoke.py README.md plan_v7.md` -> passed.

Remaining gaps:

- The seeded Ticket fixture is local-file only; Plane-backed Ticket smoke remains future work.
- The approval-producing path is still the deterministic fixture graph, not a primary graph runtime mutation scenario.
- There is still no CI workflow file or artifact retention policy for the smoke JSON/log files.

Next concrete module:

- Continue Track J by adding a CI workflow or artifact convention for Agent Server smoke outputs, or continue Track B by designing a primary-graph approval-producing smoke that does not rely on monkeypatching.

Anti-Wheel Audit:

- No new Ticket backend or fixture framework was added.
- The seed path writes the same local-file Ticket event format used by the existing Ticket service.
- Runtime execution, interrupt, resume, and checkpoint behavior stay inside official LangGraph Agent Server.

### 2026-06-19: Current verification checkpoint

Status: completed.

Validation:

- `pytest tests/test_execution_dispatch_contract.py` -> 87 passed.
- `npm test` from `apps/dashboard/` -> 66 passed.
- `npm run build` from `apps/dashboard/` -> passed; Vite reported the existing large chunk warning.
- `python -m py_compile scripts/langgraph_agent_server_smoke.py scripts/langgraph_agent_server_ci_smoke.py services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py` -> passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `python scripts/langgraph_agent_server_ci_smoke.py --workspace-dir /tmp/aiteamos-agent-server-seed-smoke-final --startup-timeout 120 --assistant-id aiteamos_workbench_approval_fixture --thread-id agent-server-ci-smoke-approval-seeded-resume --message "Trigger deterministic approval fixture" --ticket-key ticket-agent-server-approval-resume --seed-ticket --expect-status needs_approval --expect-current-node approval_interrupt --expect-context-source "" --expect-approval-ref approval-fixture-1 --resume-approval-ref approval-fixture-1 --expect-resume-status completed --expect-resume-current-node final_response --require-resume-ticket-report --min-resume-asset-candidates 1 --min-resume-linked-assets 1` -> passed.
- `ps -ef | rg "langgraph dev|46779"` -> no temporary `46779` server remained; an existing unrelated `127.0.0.1:2024` process was left untouched.
- `rg -n "[ \t]+$" scripts/langgraph_agent_server_smoke.py scripts/langgraph_agent_server_ci_smoke.py README.md services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py apps/dashboard/src/api/tickets.ts apps/dashboard/src/pages/tickets/index.tsx apps/dashboard/src/__tests__/tickets-page.test.tsx plan_v7.md` -> no matches.
- `git diff --check -- scripts/langgraph_agent_server_smoke.py scripts/langgraph_agent_server_ci_smoke.py README.md services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py apps/dashboard/src/api/tickets.ts apps/dashboard/src/pages/tickets/index.tsx apps/dashboard/src/__tests__/tickets-page.test.tsx plan_v7.md` -> passed.

Current remaining top gaps:

- Primary graph approval-producing Agent Server smoke now passes; the next primary-graph gap is repeated live external-runtime dogfood with real provider configuration.
- Ticket/Assets/Memory dogfood still needs real configured Plane, Graphiti projection, and later recall evidence.
- No CI workflow currently runs the smoke/test/build suite automatically.
- Cross-Ticket operations view for policy actions remains future Track J work.

### 2026-06-19: Track B primary graph approval interrupt and resume smoke

Status: completed.

Files changed:

- Updated `services/api/aiteamos_api/agents/aiteamos_workbench_graph.py`.
- Updated `services/api/aiteamos_api/agents/workbench/nodes/governance.py`.
- Updated `services/api/aiteamos_api/agents/workbench/nodes/execution.py`.
- Updated `services/api/aiteamos_api/read/execution_approval_service.py`.
- Updated `scripts/langgraph_agent_server_smoke.py`.
- Updated `scripts/langgraph_agent_server_ci_smoke.py`.
- Updated `README.md`.
- Updated `plan_v7.md`.

What changed:

- The primary `aiteamos_workbench` graph now routes conditionally after `governance_gate`; `implement_ticket` requests that require `repo:write` create an AITeamOS `ExecutionApprovalRecord` before nested runtime dispatch.
- The graph now interrupts at the Workbench boundary with `runtime_status.status=needs_approval`, `runtime_status.current_node=approval_interrupt`, deterministic checkpoint/session refs, and an approval record snapshot.
- Approval resume now reloads the approved `ExecutionApprovalRecord` and only then dispatches the governed runtime executor.
- `ExecutionApprovalRunService.run()` now performs approval load, ingestion, and run-result persistence through `asyncio.to_thread`, avoiding LangGraph Agent Server blocking I/O during resume.
- Workbench ingestion now exposes primary `ticket_report_id` / `evidence_id` fields when available.
- Agent Server smoke now supports deterministic `--runtime-run-id` and optional `--review-resume-approval`.
- Smoke Ticket-report validation now accepts either graph state `ticket_report_id` or the latest report from the Ticket provider, matching the real approval-review report flow.
- README now includes the primary graph interrupt/review/resume smoke command.

Validation:

- `python -m py_compile services/api/aiteamos_api/agents/aiteamos_workbench_graph.py services/api/aiteamos_api/agents/workbench/nodes/governance.py services/api/aiteamos_api/agents/workbench/nodes/execution.py services/api/aiteamos_api/read/execution_approval_service.py scripts/langgraph_agent_server_smoke.py scripts/langgraph_agent_server_ci_smoke.py` -> passed.
- `pytest tests/test_aiteamos_workbench_graph.py` -> 7 passed.
- `pytest tests/test_execution_dispatch_contract.py tests/test_runtime_executor_routes.py` -> 103 passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `python scripts/langgraph_agent_server_ci_smoke.py --workspace-dir /tmp/aiteamos-primary-approval-smoke-deterministic --startup-timeout 120 --assistant-id aiteamos_workbench --thread-id agent-server-ci-smoke-primary-approval-deterministic --message "Implement code changes for ticket ticket-primary-approval-smoke" --ticket-key ticket-primary-approval-smoke --seed-ticket --runtime-run-id run-primary-approval-smoke --expect-status needs_approval --expect-current-node approval_interrupt --expect-action implement_ticket --expect-approval-ref approval-run-primary-approval-smoke-1` -> passed.
- `python scripts/langgraph_agent_server_ci_smoke.py --workspace-dir /tmp/aiteamos-primary-approval-resume-smoke-4 --startup-timeout 120 --assistant-id aiteamos_workbench --thread-id agent-server-ci-smoke-primary-approval-resume --message "Implement code changes for ticket ticket-primary-approval-resume-smoke" --ticket-key ticket-primary-approval-resume-smoke --seed-ticket --runtime-run-id run-primary-approval-resume-smoke --expect-status needs_approval --expect-current-node approval_interrupt --expect-action implement_ticket --expect-approval-ref approval-run-primary-approval-resume-smoke-1 --resume-approval-ref approval-run-primary-approval-resume-smoke-1 --review-resume-approval --expect-resume-status completed --expect-resume-current-node final_response --require-resume-ticket-report --min-resume-linked-assets 1` -> passed.

Remaining gaps:

- The primary smoke proves approval interrupt/review/resume and governed handoff to the runtime executor, but it intentionally does not perform a real repository mutation.
- Historical note: this line pre-dates the 2026-06-21 boundary correction. Repo-write adapter dogfood still needs configured Codex CLI or another external runtime, but core production-readiness now requires a separate LangGraph + DeepSeek provider core-loop dogfood.
- Plane-backed Ticket smoke and Graphiti projection/recall smoke remain future Track B/H/J work.
- CI still needs a workflow or artifact convention for smoke JSON/log retention.

Next concrete module:

- Continue Track I/J by adding repeated live external-runtime dogfood evidence and CI artifact conventions, or continue Track E by adding retrieval golden evals.

Anti-Wheel Audit:

- No custom generic agent loop, checkpoint mechanism, streaming protocol, or approval store was added.
- The slice reused LangGraph conditional edges, official Agent Server resume commands, existing `ExecutionApprovalRecord`, existing Ticket provider reports, and existing `ExecutionRequest` / `ExecutionResult`.
- AITeamOS logic stayed in graph nodes and domain services, not route handlers.
- Durable memory remains behind Asset candidates / review / AssetRecord; Graphiti remains a future projection layer, not source of truth.

### 2026-06-19: Track E retrieval golden eval and context audit

Status: completed.

Files changed:

- Updated `services/api/aiteamos_api/read/execution_context_service.py`.
- Added `services/api/aiteamos_api/read/context_retrieval_eval_service.py`.
- Added `tests/test_context_retrieval_eval.py`.
- Updated `plan_v7.md`.

What changed:

- `ExecutionContextService` now includes approved, Ticket-scoped `AssetRecord` items in `universal_context.asset_context.relevant_assets`; it no longer relies only on Ticket asset projections and Memory usage records.
- Asset refs now normalize provenance from both Ticket asset records and durable AssetRecords, including source Ticket/report/Employee references.
- `universal_context` now exposes `retrieval_audit` with selected context refs, scores, provenance, provider-blocker counts, and explicit exclusion reasons for empty sources.
- Added a small `context_retrieval_eval_service.py` that evaluates a `ScopedTaskContext` against golden expected refs and reports matched refs, missing refs, recall, and precision-like metrics.
- Added a golden retrieval test that seeds a local Ticket, related Ticket, validation report/evidence, approved Memory, and approved AssetRecord, then proves the query retrieves the expected Employee/Ticket/related Ticket/Asset/Memory/evidence refs.
- Added exclusion coverage proving empty current Ticket / Asset / Memory sources surface explicit exclusion reasons rather than silent empty context.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/execution_context_service.py services/api/aiteamos_api/read/context_retrieval_eval_service.py tests/test_context_retrieval_eval.py` -> passed.
- `pytest tests/test_context_retrieval_eval.py` -> 2 passed.
- `pytest tests/test_aiteamos_workbench_graph.py tests/test_context_retrieval_eval.py` -> 9 passed.
- `pytest tests/test_execution_dispatch_contract.py -q` -> 87 passed; existing warnings included Graphiti Pydantic deprecation and aiosqlite event-loop-close warnings.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `rg -n "[ \t]+$" services/api/aiteamos_api/read/execution_context_service.py services/api/aiteamos_api/read/context_retrieval_eval_service.py tests/test_context_retrieval_eval.py plan_v7.md` -> no matches.
- `git diff --check -- services/api/aiteamos_api/read/execution_context_service.py services/api/aiteamos_api/read/context_retrieval_eval_service.py tests/test_context_retrieval_eval.py plan_v7.md` -> passed.

Remaining gaps:

- This is the first golden eval slice; it covers local-file Ticket, local approved Memory, and local approved AssetRecord retrieval, not live Graphiti search ranking.
- There is no persisted eval report registry or CI artifact convention yet.
- Stale/conflict memory detection still needs product behavior and eval coverage.
- Retrieval scoring remains heuristic; this slice makes it measurable but does not replace ranking with a learned reranker.

Next concrete module:

- Continue Track E by adding stale/conflict memory hints and Graphiti-backed recall evals, or continue Track J by adding CI artifact conventions for eval/smoke JSON output.

Anti-Wheel Audit:

- No generic memory database, vector store, or reranker was added.
- The slice reuses existing Tickets, approved Memory, approved AssetRecords, and `ExecutionContextService` as the product retrieval boundary.
- Graphiti remains a projection/recall provider; the eval monkeypatch only avoids requiring live Neo4j/OpenAI during local tests.
- No route-handler orchestration or custom agent loop was introduced.

### 2026-06-19: Track E stale memory conflict hints

Status: completed.

Files changed:

- Updated `services/api/aiteamos_api/read/execution_context_service.py`.
- Updated `tests/test_context_retrieval_eval.py`.
- Updated `plan_v7.md`.

What changed:

- `ExecutionContextService` now scans stale and superseded Memory candidates that match the current query and Ticket/Employee scope.
- Stale/superseded Memory never enters `recalled_memories`; instead it appears in `universal_context.memory_context.stale_memory_hints`.
- `retrieval_audit.excluded` now includes stale/superseded Memory refs with explicit exclusion reasons, so the graph can explain why a plausible memory was not used.
- The golden retrieval eval now seeds a stale parser-fallback memory and proves it is excluded while the approved replacement memory is recalled.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/execution_context_service.py services/api/aiteamos_api/read/context_retrieval_eval_service.py tests/test_context_retrieval_eval.py` -> passed.
- `pytest tests/test_context_retrieval_eval.py` -> 2 passed.
- `pytest tests/test_aiteamos_workbench_graph.py tests/test_context_retrieval_eval.py` -> 9 passed.
- `pytest tests/test_execution_dispatch_contract.py -q` -> 87 passed; existing warnings included Graphiti Pydantic deprecation and Starlette/httpx deprecation.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `rg -n "[ \t]+$" services/api/aiteamos_api/read/execution_context_service.py services/api/aiteamos_api/read/context_retrieval_eval_service.py tests/test_context_retrieval_eval.py plan_v7.md` -> no matches.
- `git diff --check -- services/api/aiteamos_api/read/execution_context_service.py services/api/aiteamos_api/read/context_retrieval_eval_service.py tests/test_context_retrieval_eval.py plan_v7.md` -> passed.

Remaining gaps:

- Conflict detection is still local-file Memory-candidate based; live Graphiti conflict hints remain future work.
- Stale/superseded hints are exposed in graph context but do not yet drive UI affordances or automatic review workflows.
- There is no persisted eval report registry yet.

Next concrete module:

- Continue Track J with CI/eval artifact conventions, or continue Track E with Graphiti-backed recall evals when provider configuration is available.

Anti-Wheel Audit:

- No new memory database, ranking engine, or generic observability system was added.
- Stale detection reuses existing Memory candidate review statuses and keeps approved Memory as the only active recall source.
- Explanations are exposed as AITeamOS context/provenance facts, not hidden runtime state.

### 2026-06-19: Track J CI/eval artifact convention

Status: completed.

Goal: make v7 smoke/eval evidence repeatable locally and CI-friendly without introducing a custom observability platform or replacing existing pytest / LangGraph / dashboard commands.

Files changed:

- Added `scripts/plan_v7_ci_artifacts.py`.
- Added `.github/workflows/plan-v7-verification.yml`.
- Updated `.gitignore`.
- Updated `README.md`.
- Updated `plan_v7.md`.

What changed:

- Added a thin artifact wrapper that runs existing verification commands and writes `manifest.json`, per-command JSON records, and stdout/stderr logs under `.aiteamos/artifacts/plan_v7/<run-id>/`.
- Default command set covers core `py_compile`, retrieval golden eval tests, Workbench graph/context tests, `langgraph validate`, and `git diff --check`.
- `--full` adds the broader backend execution dispatch contract suite.
- `--include-frontend` adds dashboard `npm test` and `npm run build`.
- `--include-agent-server-smoke` adds the primary graph Agent Server approval/resume smoke using the existing `scripts/langgraph_agent_server_ci_smoke.py` and stores its JSON/log artifacts in the same run directory.
- README now documents the repeatable local/CI commands and artifact location.
- Added a GitHub Actions workflow that runs the default artifact script on pushes and pull requests, uploads the manifest/logs, and lets manual `workflow_dispatch` runs opt into `--full`, `--include-frontend`, or `--include-agent-server-smoke`.
- `.gitignore` now ignores `.aiteamos/artifacts/plan_v7/` so generated evidence does not dirty the repo.

Validation:

- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-artifact-smoke` -> passed.
- The artifact run executed 5 commands: `py_compile_plan_v7_core`, `pytest_context_retrieval_eval`, `pytest_workbench_graph_and_context`, `langgraph_validate`, and `git_diff_check_plan_v7_slice`.
- The artifact manifest was written to `.aiteamos/artifacts/plan_v7/local-v7-artifact-smoke/manifest.json`.
- `pytest tests/test_context_retrieval_eval.py -q` -> 2 passed inside the artifact run.
- `pytest tests/test_aiteamos_workbench_graph.py tests/test_context_retrieval_eval.py -q` -> 9 passed inside the artifact run.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found inside the artifact run.
- `python -m py_compile scripts/plan_v7_ci_artifacts.py` -> passed.
- `git diff --check -- scripts/plan_v7_ci_artifacts.py README.md plan_v7.md .gitignore` -> passed before the workflow addition; final checks below cover the workflow too.
- `python -c "import pathlib, yaml; yaml.safe_load(pathlib.Path('.github/workflows/plan-v7-verification.yml').read_text())"` -> passed.
- `rg -n "[ \t]+$" scripts/plan_v7_ci_artifacts.py README.md plan_v7.md .gitignore .github/workflows/plan-v7-verification.yml` -> no matches.
- `git diff --check -- scripts/plan_v7_ci_artifacts.py README.md plan_v7.md .gitignore .github/workflows/plan-v7-verification.yml` -> passed.

Remaining gaps:

- CI provider wiring now exists, but it has not yet run on GitHub-hosted runners in this workspace.
- Default CI verification intentionally avoids live providers, frontend build, and long Agent Server startup unless manually requested.
- Graphiti-backed retrieval evals and Plane-backed Ticket smoke still need real provider configuration before they can be made required checks.

Next concrete module:

- Continue Track E/H by adding Graphiti-backed recall/projection evals once live provider configuration is available, or continue Track J by adding a small operations summary over saved artifact manifests.

Anti-Wheel Audit:

- No custom test runner, trace database, dashboard, generic observability system, or agent-loop logic was added.
- The script only wraps existing pytest, LangGraph CLI, dashboard npm scripts, and existing Agent Server smoke commands.
- Durable product facts remain in Tickets, Assets, approvals, runtime sessions, and memory records; artifacts are only verification evidence.

### 2026-06-19: Track A basic Workbench node extraction

Status: completed.

Goal: keep the primary Workbench graph moving toward explicit LangGraph node modules by moving remaining basic bootstrap/bind/read nodes out of the graph assembly file without changing graph behavior.

Files changed:

- Added `services/api/aiteamos_api/agents/workbench/nodes/bootstrap.py`.
- Updated `services/api/aiteamos_api/agents/aiteamos_workbench_graph.py`.
- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `plan_v7.md`.

What changed:

- Moved `bootstrap_request`, `bind_or_create_ticket`, and `execute_read_tools` into a dedicated Workbench node module.
- The primary graph file now imports those nodes and remains closer to pure graph assembly.
- The artifact wrapper now compiles the new bootstrap node module by default.
- The initial implementation briefly emitted a LangGraph annotation warning because of postponed annotations; this was removed so CI artifacts stay quieter.

Validation:

- `python -m py_compile services/api/aiteamos_api/agents/aiteamos_workbench_graph.py services/api/aiteamos_api/agents/workbench/nodes/bootstrap.py` -> passed.
- `pytest tests/test_aiteamos_workbench_graph.py -q` -> 7 passed; only the existing Graphiti Pydantic deprecation warning remained.
- `pytest tests/test_aiteamos_workbench_graph.py tests/test_plan_v7_artifact_summary.py -q` -> 9 passed after the Track J summary addition.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.

Remaining gaps:

- The deterministic approval fixture graph still lives in `aiteamos_workbench_graph.py`; it should eventually move to a fixture module so the production graph file contains only production wiring.
- Some production nodes still carry compatibility glue for `ChatExecutionRuntime`; this should keep shrinking only where the existing `ExecutionRequest` / `ExecutionResult` contract already covers behavior.

Next concrete module:

- Continue Track A by extracting the approval fixture graph into a dedicated fixture module, or continue Track E/H with Graphiti-backed evals when provider configuration is available.

Anti-Wheel Audit:

- No new orchestration behavior, graph runtime, checkpoint layer, or tool dispatcher was added.
- The change only relocates existing LangGraph node functions into the established Workbench node package.

### 2026-06-19: Track J artifact operations summary

Status: completed.

Goal: make saved v7 verification artifacts operationally readable by summarizing recent manifest outcomes without introducing a custom observability platform.

Files changed:

- Added `scripts/plan_v7_artifact_summary.py`.
- Added `tests/test_plan_v7_artifact_summary.py`.
- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `README.md`.
- Updated `plan_v7.md`.

What changed:

- Added a thin summary script that reads `.aiteamos/artifacts/plan_v7/*/manifest.json` and reports inspected run count, passed/failed/running/non-passed counts, latest run status, and failed command details.
- The summary distinguishes `running` from actual failed statuses such as `failed`, `blocked`, `error`, and `timed_out`.
- Added focused tests for latest-run ordering, failed command projection, missing artifact directories, and running-vs-failed semantics.
- The default `plan_v7_ci_artifacts.py` suite now includes `tests/test_plan_v7_artifact_summary.py`.
- README now documents `python scripts/plan_v7_artifact_summary.py`.

Validation:

- `python -m py_compile scripts/plan_v7_ci_artifacts.py scripts/plan_v7_artifact_summary.py services/api/aiteamos_api/agents/aiteamos_workbench_graph.py services/api/aiteamos_api/agents/workbench/nodes/bootstrap.py tests/test_plan_v7_artifact_summary.py` -> passed.
- `pytest tests/test_plan_v7_artifact_summary.py -q` -> 3 passed.
- `pytest tests/test_aiteamos_workbench_graph.py tests/test_plan_v7_artifact_summary.py -q` -> 9 passed; only the existing Graphiti Pydantic deprecation warning remained.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-summary-smoke-2` -> passed with 6 commands, including `pytest_plan_v7_artifact_summary`.
- `python scripts/plan_v7_artifact_summary.py --limit 3` -> latest status `passed`, 3 inspected runs, 0 failed, 0 running.
- `rg -n "[ \t]+$" services/api/aiteamos_api/agents/aiteamos_workbench_graph.py services/api/aiteamos_api/agents/workbench/nodes/bootstrap.py scripts/plan_v7_ci_artifacts.py scripts/plan_v7_artifact_summary.py tests/test_plan_v7_artifact_summary.py README.md plan_v7.md` -> no matches.
- `git diff --check -- services/api/aiteamos_api/agents/aiteamos_workbench_graph.py services/api/aiteamos_api/agents/workbench/nodes/bootstrap.py scripts/plan_v7_ci_artifacts.py scripts/plan_v7_artifact_summary.py tests/test_plan_v7_artifact_summary.py README.md plan_v7.md` -> passed.

Remaining gaps:

- Artifact summary is local/CI manifest-oriented; it does not replace LangSmith, LangGraph Studio, or provider-native observability.
- CI workflow exists but has still not run on a GitHub-hosted runner in this workspace.
- Live Graphiti/Plane provider evals remain optional until real provider configuration is available.

Next concrete module:

- Continue Track A by moving the deterministic approval fixture graph out of the production graph file, or continue Track E/H by adding Graphiti-backed recall/projection evals when provider configuration is available.

Anti-Wheel Audit:

- No generic observability database, trace UI, eval platform, or dashboard was added.
- The summary script only reads existing artifact manifests generated by the existing wrapper around pytest, LangGraph CLI, and Agent Server smoke commands.

### 2026-06-19: Track A approval fixture graph extraction

Status: completed.

Goal: keep the production Workbench graph file focused on production graph assembly by moving the deterministic approval fixture graph into a dedicated fixture module while preserving Agent Server smoke behavior.

Files changed:

- Updated `services/api/aiteamos_api/agents/aiteamos_workbench_graph.py`.
- Added `services/api/aiteamos_api/agents/workbench/approval_fixture_graph.py`.
- Updated `langgraph.json`.
- Updated `tests/test_aiteamos_workbench_graph.py`.
- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `plan_v7.md`.

What changed:

- `aiteamos_workbench_graph.py` now contains only the production `aiteamos_workbench` graph assembly and the tiny dispatch adapter.
- The deterministic approval fixture graph moved to `agents/workbench/approval_fixture_graph.py`.
- `langgraph.json` now points `aiteamos_workbench_approval_fixture` at the dedicated fixture module.
- Workbench graph tests now import fixture helpers from the fixture module instead of the production graph module.
- The artifact wrapper now compiles the fixture module by default.
- Removed postponed annotations from the fixture module so LangGraph node signature warnings do not pollute smoke artifacts.

Validation:

- `python -m py_compile services/api/aiteamos_api/agents/aiteamos_workbench_graph.py services/api/aiteamos_api/agents/workbench/approval_fixture_graph.py scripts/plan_v7_ci_artifacts.py tests/test_aiteamos_workbench_graph.py` -> passed.
- `pytest tests/test_aiteamos_workbench_graph.py -q` -> 7 passed; only the existing Graphiti Pydantic deprecation warning remained.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-fixture-extraction-smoke` -> passed with 6 commands, including Workbench graph/context tests and `langgraph_validate`.
- `python scripts/langgraph_agent_server_ci_smoke.py --workspace-dir /tmp/aiteamos-fixture-extraction-agent-server-smoke --startup-timeout 120 --assistant-id aiteamos_workbench_approval_fixture --thread-id agent-server-ci-smoke-fixture-extraction --message "Trigger deterministic approval fixture" --ticket-key ticket-fixture-extraction-approval-resume --seed-ticket --expect-status needs_approval --expect-current-node approval_interrupt --expect-context-source "" --expect-approval-ref approval-fixture-1 --resume-approval-ref approval-fixture-1 --expect-resume-status completed --expect-resume-current-node final_response --require-resume-ticket-report --min-resume-asset-candidates 1 --min-resume-linked-assets 1` -> passed.
- `ps -ef | rg "langgraph dev|48067"` -> no temporary `48067` Agent Server remained; the existing unrelated `127.0.0.1:2024` dev server was left untouched.
- `python scripts/plan_v7_artifact_summary.py --limit 3` -> latest status `passed`, 3 inspected runs, 0 failed, 0 running.
- `rg -n "[ \t]+$" services/api/aiteamos_api/agents/aiteamos_workbench_graph.py services/api/aiteamos_api/agents/workbench/approval_fixture_graph.py langgraph.json tests/test_aiteamos_workbench_graph.py scripts/plan_v7_ci_artifacts.py plan_v7.md` -> no matches.
- `git diff --check -- services/api/aiteamos_api/agents/aiteamos_workbench_graph.py services/api/aiteamos_api/agents/workbench/approval_fixture_graph.py langgraph.json tests/test_aiteamos_workbench_graph.py scripts/plan_v7_ci_artifacts.py plan_v7.md` -> passed.

Remaining gaps:

- Production graph nodes still contain some compatibility glue around `ChatExecutionRuntime`; this should shrink only when existing domain services already cover the behavior through `ExecutionRequest` / `ExecutionResult`.
- The fixture module is still intentionally local-file and deterministic; it is smoke infrastructure, not provider dogfood.
- Live Graphiti/Plane provider evals still require real provider configuration before they can become required checks.

Next concrete module:

- Continue Track A by reducing remaining compatibility glue in execution/governance nodes where the `ExecutionRequest` contract already covers the behavior, or continue Track E/H with Graphiti-backed recall/projection evals when provider configuration is available.

Anti-Wheel Audit:

- No custom graph runtime, checkpoint system, fixture framework, or approval engine was added.
- The slice only moved deterministic smoke infrastructure out of the production graph file and reused LangGraph, existing approval records, Ticket reports, Asset candidates, and existing smoke scripts.

### 2026-06-19: Track A remove ChatExecutionRuntime fallback from Workbench dispatch

Status: completed.

Goal: remove the unused `run_chat_message_fn` / `ChatExecutionRuntime` fallback branch from `dispatch_runtime_executor`, so the production Workbench dispatch path only uses the existing `ExecutionRequest` / `ExecutionResult` contract.

Files changed:

- Updated `services/api/aiteamos_api/agents/workbench/nodes/execution.py`.
- Updated `tests/test_aiteamos_workbench_graph.py`.
- Updated `plan_v7.md`.

What changed:

- Removed the `RunChatMessage` type alias, `run_chat_message_fn` parameter, `_dispatch_through_compatibility_chat_runtime()` helper, and `"compatibility_runtime": "ChatExecutionRuntime"` projection.
- `dispatch_runtime_executor` now always enters `_dispatch_through_execution_contract()`.
- The graph test now asserts `compatibility_runtime` is absent from `execution_summary`, guarding against reintroducing the old fallback.

Validation:

- `rg -n "run_chat_message_fn|_dispatch_through_compatibility|compatibility_runtime|RunChatMessage" services/api/aiteamos_api/agents tests` -> only the negative assertion in `tests/test_aiteamos_workbench_graph.py` remained.
- `python -m py_compile services/api/aiteamos_api/agents/workbench/nodes/execution.py tests/test_aiteamos_workbench_graph.py` -> passed.
- `pytest tests/test_aiteamos_workbench_graph.py -q` -> 7 passed; only the existing Graphiti Pydantic deprecation warning remained.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-no-chat-runtime-fallback-final` -> passed with 6 commands, including Workbench graph/context tests, artifact summary tests, `langgraph_validate`, and `git diff --check`.
- `python scripts/langgraph_agent_server_ci_smoke.py --workspace-dir /tmp/aiteamos-no-chat-runtime-agent-server-smoke --startup-timeout 120 --assistant-id aiteamos_workbench --thread-id agent-server-ci-smoke-no-chat-runtime-fallback --message "Implement code changes for ticket ticket-no-chat-runtime-fallback" --ticket-key ticket-no-chat-runtime-fallback --seed-ticket --runtime-run-id run-no-chat-runtime-fallback --expect-status needs_approval --expect-current-node approval_interrupt --expect-action implement_ticket --expect-approval-ref approval-run-no-chat-runtime-fallback-1 --resume-approval-ref approval-run-no-chat-runtime-fallback-1 --review-resume-approval --expect-resume-status completed --expect-resume-current-node final_response --require-resume-ticket-report --min-resume-linked-assets 1` -> passed.
- `ps -ef` after the primary Agent Server smoke showed no temporary `48301` Agent Server remained; the existing unrelated `127.0.0.1:2024` dev server was left untouched.

Remaining gaps:

- The execution node still uses `ChatMessageRequest` plus `runtime_factory.prepare_chat_run()` / `chat_governance_input()` / response persistence to reuse existing context, session, transcript, and UI response behavior.
- Shrinking that further should happen by extracting or reusing domain services for context/session/transcript preparation, not by rebuilding a second chat runtime or generic dispatcher.
- Live provider dogfood, Graphiti-backed recall/projection evals, and Plane-backed ticket-loop evals still require real provider configuration before becoming required checks.

Next concrete module:

- Continue Track A by extracting the context/session preparation inside the execution node into a dedicated domain helper if it reduces `ChatExecutionRuntime` authority without duplicating existing runtime behavior.
- Alternatively continue Track E/H with Graphiti-backed retrieval/projection evals when provider configuration is available.

Anti-Wheel Audit:

- No new dispatcher, agent loop, Chat runtime, checkpoint layer, or generic approval engine was added.
- The slice removed an unused compatibility branch and preserved the existing `ExecutionRequest` / `ExecutionResult` boundary behind LangGraph.

### 2026-06-19: Track A Workbench runtime context service extraction

Status: completed.

Goal: move Workbench execution context/session/transcript preparation out of the LangGraph execution node into a small domain service, reducing direct `chat_runtime_factory` coupling in graph nodes without creating another Chat runtime.

Files changed:

- Added `services/api/aiteamos_api/read/workbench_runtime_context_service.py`.
- Updated `services/api/aiteamos_api/agents/workbench/nodes/execution.py`.
- Updated `tests/test_aiteamos_workbench_graph.py`.
- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `plan_v7.md`.

What changed:

- Added `WorkbenchRuntimeContextService` as the Workbench boundary for preparing `ChatRunContext`, Graphiti recall enrichment, `ChatGovernanceInput`, and response/session/transcript persistence.
- `dispatch_runtime_executor` now delegates those context/session/transcript concerns to the new service and no longer imports or calls `chat_runtime_factory` directly.
- The graph node still owns graph state, existing `ExecutionRequest` / `ExecutionResult` orchestration, approval resume, and Workbench state projection.
- The Workbench graph test now asserts `runtime_context_service == "WorkbenchRuntimeContextService"` in `execution_summary`.
- The plan v7 artifact wrapper now compiles and checks the new service file by default.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/workbench_runtime_context_service.py services/api/aiteamos_api/agents/workbench/nodes/execution.py tests/test_aiteamos_workbench_graph.py scripts/plan_v7_ci_artifacts.py` -> passed.
- `pytest tests/test_aiteamos_workbench_graph.py -q` -> 7 passed; only the existing Graphiti Pydantic deprecation warning remained.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `rg -n "prepare_chat_run|chat_governance_input|persist_chat_response_for_context|save_execution_session|execution_trace_events|execution_engine_state|ChatMessageRequest|ChatMessageResponse|runtime_factory" services/api/aiteamos_api/agents/workbench/nodes/execution.py` -> no matches.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-workbench-runtime-context-service` -> passed with 6 commands, including Workbench graph/context tests, artifact summary tests, `langgraph_validate`, and `git diff --check`.
- `python scripts/langgraph_agent_server_ci_smoke.py --workspace-dir /tmp/aiteamos-workbench-runtime-context-agent-server-smoke --startup-timeout 120 --assistant-id aiteamos_workbench --thread-id agent-server-ci-smoke-workbench-runtime-context --message "Implement code changes for ticket ticket-workbench-runtime-context" --ticket-key ticket-workbench-runtime-context --seed-ticket --runtime-run-id run-workbench-runtime-context --expect-status needs_approval --expect-current-node approval_interrupt --expect-action implement_ticket --expect-approval-ref approval-run-workbench-runtime-context-1 --resume-approval-ref approval-run-workbench-runtime-context-1 --review-resume-approval --expect-resume-status completed --expect-resume-current-node final_response --require-resume-ticket-report --min-resume-linked-assets 1` -> passed.
- `ps -ef | rg "langgraph dev|46801"` after the primary Agent Server smoke showed no temporary `46801` Agent Server remained; the existing unrelated `127.0.0.1:2024` dev server was left untouched.

Remaining gaps:

- `WorkbenchRuntimeContextService` is intentionally still a thin adapter over existing `chat_runtime_factory` functions; the next cleanup should extract reusable context/session/transcript functions from the factory only when doing so reduces duplication without creating a second runtime.
- Broader production compatibility smoke still needs more paths than the current approval/resume run: answer-only, inspect/read-only, provider blocker, reject/request-changes, and repeated queued ticket-loop work.
- Live Graphiti/Plane provider evals still require real provider configuration before becoming required checks.

Next concrete module:

- Continue Track B by expanding Agent Server production-compatible smoke coverage beyond approval/resume into answer-only and provider-blocker paths.
- Then continue Track D with reject/request-changes approval behavior, keeping all governance state in AITeamOS approval records and Tickets.

Anti-Wheel Audit:

- No new Chat runtime, generic dispatcher, agent loop, transcript store, or checkpoint layer was added.
- The new service only centralizes Workbench-specific use of existing Chat context, governance input, transcript, and execution-session services behind the LangGraph node boundary.

### 2026-06-19: Track B Agent Server matrix smoke coverage

Status: completed.

Goal: expand production-compatible LangGraph Agent Server smoke coverage beyond a single approval/resume happy path, while keeping the verification layer a thin wrapper around existing LangGraph CLI, pytest, and AITeamOS smoke scripts.

Files changed:

- Updated `scripts/langgraph_agent_server_smoke.py`.
- Updated `scripts/langgraph_agent_server_ci_smoke.py`.
- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `.github/workflows/plan-v7-verification.yml`.
- Updated `README.md`.
- Updated `plan_v7.md`.

What changed:

- Added smoke assertions for initial approval request count, provider blocker min/max count, expected provider blocker reason, initial asset candidates, and initial linked assets.
- Added `--use-local-ticket-backend` to the Agent Server CI smoke wrapper so read-only and answer-only paths can assert zero provider blockers deterministically.
- Added `--include-agent-server-matrix-smoke` to `plan_v7_ci_artifacts.py`.
- The matrix runs seven production-compatible Agent Server paths:
  - read-only `list_employees` with local Ticket backend and zero provider blockers.
  - answer-only with local Ticket backend, zero approvals, and zero provider blockers.
  - answer-only with default Plane backend setup missing, proving `plane_setup_blocker` is surfaced as a provider blocker instead of hidden.
  - primary `implement_ticket` approval/resume, proving interrupt, approval record, resume, ticket report, and linked asset still work.
  - primary `implement_ticket` approval/evidence review, proving interrupt, approval record review, Ticket `waiting_evidence`, `approval_evidence_requested` report, and Ticket timeline all stay coherent without resuming runtime mutation.
  - primary `implement_ticket` approval/rejected review, proving Ticket `blocked`, `approval_rejected` report, and `rejected` timeline status.
  - primary `implement_ticket` approval/changes review, proving Ticket `waiting_changes`, `approval_changes_requested` report, and `changes_requested` timeline status.
- README and GitHub workflow dispatch now expose the matrix smoke option without making it required by default.

Validation:

- `python -m py_compile scripts/langgraph_agent_server_smoke.py scripts/langgraph_agent_server_ci_smoke.py scripts/plan_v7_ci_artifacts.py` -> passed.
- `python scripts/langgraph_agent_server_smoke.py --help` -> showed new provider blocker / approval count assertions.
- `python scripts/langgraph_agent_server_ci_smoke.py --help` -> showed `--use-local-ticket-backend` and new assertions.
- `python scripts/plan_v7_ci_artifacts.py --help` -> showed `--include-agent-server-matrix-smoke`.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-agent-server-matrix-smoke --include-agent-server-matrix-smoke --fail-fast` -> passed with 10 commands.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-agent-server-nonapprove-matrix --include-agent-server-matrix-smoke --fail-fast` -> passed with 12 commands after adding the live `evidence_requested` review smoke.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-agent-server-all-review-outcomes --include-agent-server-matrix-smoke --fail-fast` -> passed with 14 commands after adding live `rejected` and `changes_requested` review smoke.
- Matrix command details:
  - `agent_server_readonly_list_smoke` -> passed, action `list_employees`, approval requests `0`, provider blockers `0`.
  - `agent_server_answer_only_smoke` -> passed, action `answer_only`, approval requests `0`, provider blockers `0`.
  - `agent_server_provider_blocker_smoke` -> passed, action `answer_only`, provider blocker reason `plane_setup_blocker`.
  - `agent_server_primary_approval_resume_matrix_smoke` -> passed, initial status `needs_approval`, resumed status `completed`, ticket report present, linked asset count `>=1`.
  - `agent_server_approval_evidence_review_smoke` -> passed, initial status `needs_approval`, approval review status `evidence_requested`, Ticket status `waiting_evidence`, report type `approval_evidence_requested`, timeline status includes `evidence_requested`.
  - `agent_server_approval_rejected_review_smoke` -> passed, initial status `needs_approval`, approval review status `rejected`, Ticket status `blocked`, report type `approval_rejected`, timeline status includes `rejected`.
  - `agent_server_approval_changes_review_smoke` -> passed, initial status `needs_approval`, approval review status `changes_requested`, Ticket status `waiting_changes`, report type `approval_changes_requested`, timeline status includes `changes_requested`.
- `ps -ef | rg "langgraph dev|47805|46609|47859|48645"` after the matrix showed no temporary matrix Agent Server ports remained; the existing unrelated `127.0.0.1:2024` dev server was left untouched.
- `python scripts/plan_v7_artifact_summary.py --limit 4` -> latest status `passed`, latest run `local-v7-agent-server-matrix-smoke`, 4 inspected runs, 0 failed, 0 running.

Remaining gaps:

- The matrix still does not cover repeated queued Ticket loop work or every external runtime executor.
- GitHub-hosted workflow has the new matrix option but has not run in this workspace.
- Provider-blocker coverage currently uses deterministic Plane setup-blocker behavior; live Plane/Graphiti provider evals still require real provider configuration.

Next concrete module:

- Continue Track G by adding repeated queued Ticket loop reliability smoke.
- Then continue Track G by adding repeated queued Ticket loop reliability smoke.

Anti-Wheel Audit:

- No custom CI runner, trace UI, observability backend, or agent-loop harness was added.
- The matrix only composes the existing Agent Server smoke script with existing LangGraph CLI startup and existing artifact manifest storage.

### 2026-06-19: Track D approval review outcome contract

Status: completed for route-level/default artifact coverage and live Agent Server matrix coverage of `evidence_requested`, `rejected`, and `changes_requested`.

Goal: harden non-approve approval outcomes as a durable AITeamOS governance contract without adding a second approval engine or custom agent loop.

Files changed:

- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `README.md`.
- Updated `plan_v7.md`.

What changed:

- Added `tests/test_runtime_executor_routes.py` to the default plan v7 compile and diff-check scope.
- Added a default artifact command `pytest_runtime_approval_outcomes`.
- Added Agent Server smoke options for reviewing an approval after a live interrupt without sending a resume command.
- Added Agent Server matrix paths `agent_server_approval_evidence_review_smoke`, `agent_server_approval_rejected_review_smoke`, and `agent_server_approval_changes_review_smoke`.
- The focused command runs existing route-level contracts for:
  - rejected runtime approvals writing Ticket reports, changing Ticket state to `blocked`, and recording employee work ledger evidence.
  - request-changes and request-evidence reviews writing `approval_changes_requested` / `approval_evidence_requested` reports, moving Ticket state to `waiting_changes` / `waiting_evidence`, and blocking runtime resume until approval is actually approved.
- The live Agent Server matrix now proves `evidence_requested`, `rejected`, and `changes_requested` reviews after real LangGraph interrupts update the approval record, Ticket status, Ticket report, and Ticket timeline without resuming runtime mutation.
- README now states that default plan v7 verification includes reject, request-changes, and request-evidence approval outcome contracts.

Validation:

- `python -m py_compile scripts/plan_v7_ci_artifacts.py tests/test_runtime_executor_routes.py` -> passed.
- `python -m pytest tests/test_runtime_executor_routes.py -q -k "rejected_runtime_approval_writes_ticket_and_employee_ledger or runtime_approval_request_changes_and_evidence_reviews_write_ticket_reports"` -> 2 passed, 14 deselected; only existing FastAPI/TestClient and Graphiti/Pydantic deprecation warnings remained.
- `git diff --check -- scripts/plan_v7_ci_artifacts.py README.md` -> passed.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-approval-outcomes --fail-fast` -> passed with 7 commands, including the new `pytest_runtime_approval_outcomes` command.
- `python -m py_compile scripts/langgraph_agent_server_smoke.py scripts/langgraph_agent_server_ci_smoke.py scripts/plan_v7_ci_artifacts.py` -> passed.
- `python scripts/langgraph_agent_server_smoke.py --help` and `python scripts/langgraph_agent_server_ci_smoke.py --help` -> showed the new review-only approval smoke assertions.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-agent-server-nonapprove-matrix --include-agent-server-matrix-smoke --fail-fast` -> passed with 12 commands, including `agent_server_approval_evidence_review_smoke`.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-agent-server-all-review-outcomes --include-agent-server-matrix-smoke --fail-fast` -> passed with 14 commands, including `agent_server_approval_rejected_review_smoke` and `agent_server_approval_changes_review_smoke`.

Remaining gaps:

- Workbench UX still needs a clearer resubmit flow after `waiting_changes` / `waiting_evidence`.
- Long-term refusal/abandonment should become an auditable Asset/retrospective pattern, not just a Ticket status.

Next concrete module:

- Continue Track G with repeated queued Ticket loop reliability smoke.
- Then improve Workbench resubmit UX after `waiting_changes` / `waiting_evidence`.

Anti-Wheel Audit:

- No new approval framework, queue runner, agent runtime, or UI protocol was introduced.
- The work only pulled existing approval/Ticket governance tests into the default artifact evidence chain.

### 2026-06-19: Track G Ticket loop queue reliability artifact coverage

Status: completed for focused default artifact coverage and short-lived queue worker smoke.

Goal: make repeated Ticket loop queue reliability part of the default production-hardening evidence chain without introducing a second queue runner or new autonomous loop.

Files changed:

- Updated `scripts/plan_v7_ci_artifacts.py`.
- Added `scripts/ticket_loop_queue_worker_smoke.py`.
- Updated `README.md`.
- Updated `plan_v7.md`.

What changed:

- Added `tests/test_execution_dispatch_contract.py` to default plan v7 compile and diff-check scope.
- Added a default artifact command `pytest_ticket_loop_queue_reliability`.
- Added `ticket_loop_queue_worker_smoke.py`, a thin deterministic smoke around the existing `TicketLoopQueueWorker`.
- Added the queue worker smoke to the default plan v7 artifact command list.
- The focused command runs existing Ticket loop reliability contracts for:
  - enqueue and pump through the existing `TicketAutonomousLoopService`.
  - duplicate queued work visibility.
  - stale running queue work detection.
  - provider-blocked queue runs surfacing on Ticket timeline.
  - repeated blocked queue runs proposing a governed failure retrospective Asset candidate.
  - worker status recording recent policy actions.
- The short-lived worker smoke queues two deterministic blocked loop items, ticks the existing worker once, and asserts:
  - pre-tick queue reliability is `duplicate_queued`.
  - processed queue items are `blocked`.
  - queue status becomes `needs_attention`.
  - Ticket timeline includes blocked queue state.
  - a `failure_retrospective` Asset candidate is proposed with both queue item ids.
  - worker status records `total_processed == 2` and `total_policy_actions == 1`.
- README now states that default plan v7 verification includes these Ticket loop queue reliability contracts.

Validation:

- `python -m py_compile scripts/plan_v7_ci_artifacts.py tests/test_execution_dispatch_contract.py` -> passed.
- `python -m pytest tests/test_execution_dispatch_contract.py -q -k "ticket_loop_queue_enqueue_and_pump_runs_existing_loop_service or ticket_loop_queue_reliability_flags_duplicate_queued_work or ticket_loop_queue_reliability_flags_stale_running_work or ticket_loop_queue_reliability_surfaces_blocked_provider_runs or ticket_loop_queue_pump_auto_proposes_failure_retrospective_after_repeated_failures or ticket_loop_queue_worker_status_records_recent_policy_actions"` -> 6 passed, 81 deselected; only existing FastAPI/TestClient and Graphiti/Pydantic deprecation warnings remained.
- `git diff --check -- scripts/plan_v7_ci_artifacts.py` -> passed.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-queue-reliability --fail-fast` -> passed with 8 commands, including `pytest_ticket_loop_queue_reliability`.
- `python -m py_compile scripts/ticket_loop_queue_worker_smoke.py scripts/plan_v7_ci_artifacts.py` -> passed.
- `python scripts/ticket_loop_queue_worker_smoke.py --workspace-dir /tmp/aiteamos-ticket-loop-worker-smoke-compact --output /tmp/aiteamos-ticket-loop-worker-smoke-compact.json` -> passed.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-queue-worker-smoke --fail-fast` -> passed with 9 commands, including `ticket_loop_queue_worker_smoke`.

Remaining gaps:

- The default artifact checks deterministic service-level queue reliability plus a short-lived worker tick, not a long-lived daemon run in a production-like process.
- Queue coverage still does not prove recurrence schedules, SLA escalation, closeout policy, or Workbench resubmit UX after `waiting_changes` / `waiting_evidence`.

Next concrete module:

- Continue Workbench resubmit UX for `waiting_changes` / `waiting_evidence`.
- Then add recurrence / SLA / closeout policy smoke once the queue worker and resubmit paths are stable.

Anti-Wheel Audit:

- No new queue runner, scheduler, worker daemon, or loop runtime was added.
- The smoke only drives the existing `TicketLoopQueueWorker` and existing Ticket / Asset candidate services.

### 2026-06-20: Track C/G Workbench Ticket loop resubmit panel

Status: completed for thin Chat Workbench resubmit UX.

Goal: let Chat Workbench users continue a governed Ticket loop after `ready_to_resume`, `waiting_changes`, or `waiting_evidence` without rebuilding Ticket loop logic in Chat.

Files changed:

- Added `apps/dashboard/src/pages/chat/panels/TicketLoopResumePanel.tsx`.
- Updated `apps/dashboard/src/pages/chat/index.tsx`.
- Updated `apps/dashboard/src/__tests__/chat-page.test.tsx`.
- Updated `plan_v7.md`.

What changed:

- Added a compact `TicketLoopResumePanel` to the Chat right-side Workbench context.
- The panel fetches the existing `GET /api/v1/tickets/{ticket_id}/loop/timeline` projection and renders Ticket loop status, next action, waiting reason, and retry preflight requirements.
- The panel calls the existing `POST /api/v1/tickets/{ticket_id}/loop/resume` API with:
  - `ready_to_resume -> resume`
  - `waiting_changes -> retry_after_changes`
  - `waiting_evidence -> retry_after_evidence`
- Retry buttons are disabled until backend-provided retry requirements are satisfied.
- Result feedback shows the queued loop run id from the existing queue response.
- Chat now exposes resubmit from Workbench while keeping Ticket loop policy, retry guards, queueing, and durable state inside the existing Ticket domain APIs.
- Added dashboard test coverage proving `waiting_evidence` in Chat Workbench queues `retry_after_evidence` through the existing resume endpoint.

Validation:

- `npm --prefix apps/dashboard test -- src/__tests__/chat-page.test.tsx` -> passed; due the existing npm script shape this ran the dashboard suite, 8 files and 67 tests passed.
- `npm --prefix apps/dashboard run build` -> passed; Vite reported the existing large chunk warning.
- `git diff --check -- apps/dashboard/src/pages/chat/index.tsx apps/dashboard/src/pages/chat/panels/TicketLoopResumePanel.tsx apps/dashboard/src/__tests__/chat-page.test.tsx` -> passed.

Remaining gaps:

- The Workbench panel is intentionally compact; richer report/evidence attachment still belongs in Tickets or Employee work surfaces.
- Chat page remains too large and should continue being split into ThreadChrome, Asset, Provenance, ProviderBlockers, and Employee/Ticket panels.
- Long-term refusal/abandonment should become an auditable Ticket/Asset retrospective pattern.
- Recurrence, SLA, closeout policy, and long-running worker evidence remain Track G/J work.

Next concrete module:

- Continue Track C by extracting the remaining Asset/Provenance/ProviderBlockers panels from Chat, or continue Track G/J by adding recurrence / SLA / closeout policy smoke.

Anti-Wheel Audit:

- No generic agent loop, Chat runtime, Ticket workflow engine, queue runner, or retry engine was added.
- The Workbench panel only renders existing Ticket timeline facts and calls the existing Ticket loop resume API.
- LangGraph remains the runtime owner; AITeamOS Ticket / Approval / Assets remain the durable governance boundary.

### 2026-06-20: Track C Asset candidate panel extraction

Status: completed for Asset candidate Workbench panel extraction.

Goal: keep Chat moving toward a thin LangGraph-native Workbench by moving Asset candidate review/projection UI and local panel state out of the main Chat page, without creating a new Assets workflow.

Files changed:

- Added `apps/dashboard/src/pages/chat/panels/AssetCandidatesPanel.tsx`.
- Updated `apps/dashboard/src/pages/chat/index.tsx`.
- Updated `plan_v7.md`.

What changed:

- Extracted the inline `Asset Candidates` block from `apps/dashboard/src/pages/chat/index.tsx` into `AssetCandidatesPanel`.
- Moved local approve/project UI state, projection status, and candidate override display state into the panel.
- The panel still calls the existing Assets APIs:
  - `reviewAssetCandidate()`
  - `projectAssetRecordToGraphiti()`
- The main Chat page now composes the panel and no longer imports Asset review/projection APIs directly.
- Chat page line count dropped from 2243 to 2020 lines after this slice.
- Asset candidate durable writes remain behind Asset candidate review, approved AssetRecord, and Graphiti projection.

Validation:

- `npm --prefix apps/dashboard test -- src/__tests__/chat-page.test.tsx` -> passed; due the existing npm script shape this ran the dashboard suite, 8 files and 67 tests passed.
- `npm --prefix apps/dashboard run build` -> passed; Vite reported the existing large chunk warning.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check -- apps/dashboard/src/pages/chat/index.tsx apps/dashboard/src/pages/chat/panels/AssetCandidatesPanel.tsx apps/dashboard/src/__tests__/chat-page.test.tsx plan_v7.md` -> passed.

Remaining gaps:

- Chat still contains inline provenance, recalled memory, provider refs, setup blockers, current Employee, and trace rendering.
- `AssetCandidatesPanel` covers candidate review/projection only; broader Assets context and recalled memory can still become their own Workbench panels.
- The dashboard build still has the existing large chunk warning; code splitting remains future frontend hardening.
- Long-term refusal/abandonment, recurrence, SLA, closeout policy, and long-running worker evidence remain Track G/J work.

Next concrete module:

- Continue Track C by extracting Provenance/RecalledMemory/ProviderRefs or ProviderBlockers panels from Chat, then continue Track G/J with recurrence / SLA / closeout policy smoke.

Anti-Wheel Audit:

- No new Chat runtime, generic Assets workflow, memory database, Graphiti writer, agent loop, or approval system was added.
- The panel reuses existing Assets APIs and keeps durable memory behind the established Asset candidate -> review -> approved AssetRecord -> Graphiti projection path.
- Chat remains a Workbench projection surface, not a source of durable Asset truth.

### 2026-06-20: Track C run provenance panel extraction

Status: completed for read-only run provenance / memory projection extraction.

Goal: keep Chat moving toward a thin LangGraph-native Workbench by moving read-only run provenance, recalled memory, Graphiti episode, provider ref, and learning summary rendering out of the main Chat page.

Files changed:

- Added `apps/dashboard/src/pages/chat/panels/RunProvenancePanel.tsx`.
- Updated `apps/dashboard/src/pages/chat/index.tsx`.
- Updated `plan_v7.md`.

What changed:

- Extracted inline rendering for:
  - Commands
  - Recalled Memories
  - Graphiti Episodes
  - Provider Refs
  - Learning summary / next guidance
- `RunProvenancePanel` is read-only and receives already-prepared graph/run metadata from Chat.
- The panel does not call backend APIs, write memory, project Graphiti, or own runtime state.
- Chat page line count dropped from 2020 to 1934 lines after this slice.
- Existing Chat tests still verify recalled memory, Graphiti episode, and provider ref rendering through the new panel.

Validation:

- `npm --prefix apps/dashboard test -- src/__tests__/chat-page.test.tsx` -> passed; due the existing npm script shape this ran the dashboard suite, 8 files and 67 tests passed.
- `npm --prefix apps/dashboard run build` -> passed; Vite reported the existing large chunk warning.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check -- apps/dashboard/src/pages/chat/index.tsx apps/dashboard/src/pages/chat/panels/AssetCandidatesPanel.tsx apps/dashboard/src/pages/chat/panels/RunProvenancePanel.tsx apps/dashboard/src/__tests__/chat-page.test.tsx plan_v7.md` -> passed.

Remaining gaps:

- Chat still contains inline provider blockers inside Scoped Context, current Employee rendering, trace rendering, and thread chrome.
- Broader Assets context and stale/conflict memory hints still need stronger panel treatment and eval-backed behavior.
- The dashboard build still has the existing large chunk warning; code splitting remains future frontend hardening.
- Recurrence, SLA, closeout policy, long-running worker evidence, and live provider dogfood remain Track G/J/I work.

Next concrete module:

- Continue Track C by extracting ProviderBlockers / CurrentEmployee / Trace panels from Chat, or continue Track G/J by adding recurrence / SLA / closeout policy smoke.

Anti-Wheel Audit:

- No new Chat runtime, provenance store, observability backend, Graphiti writer, memory database, or agent loop was added.
- The panel only renders existing LangGraph / AITeamOS metadata and keeps durable truth in Tickets, Assets, approvals, runtime sessions, and approved memory records.
- Chat remains a Workbench projection surface, not an owner of product facts.

### 2026-06-20: Track C scoped context panel extraction

Status: completed for read-only Scoped/Universal Context panel extraction.

Goal: make Chat thinner by moving scoped context, universal context, context provenance, exclusions, and provider/setup blocker rendering into a dedicated Workbench panel.

Files changed:

- Added `apps/dashboard/src/pages/chat/panels/ScopedContextPanel.tsx`.
- Updated `apps/dashboard/src/pages/chat/index.tsx`.
- Updated `plan_v7.md`.

What changed:

- Extracted inline rendering for:
  - Scoped Context metrics
  - context exclusions
  - Universal Context metrics
  - Context Provenance rows
  - provider/setup blockers
- `ScopedContextPanel` is read-only and receives the existing context bundle projection from Chat.
- The panel does not retrieve context, rank context, mutate provider state, or hide blockers.
- Chat page line count dropped from 1934 to 1847 lines after this slice.
- Existing Chat tests still verify Scoped Context, Universal Context, Context Provenance, and setup blocker rendering through the new panel.

Validation:

- `npm --prefix apps/dashboard test -- src/__tests__/chat-page.test.tsx` -> passed; due the existing npm script shape this ran the dashboard suite, 8 files and 67 tests passed.
- `npm --prefix apps/dashboard run build` -> passed; Vite reported the existing large chunk warning.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check -- apps/dashboard/src/pages/chat/index.tsx apps/dashboard/src/pages/chat/panels/AssetCandidatesPanel.tsx apps/dashboard/src/pages/chat/panels/RunProvenancePanel.tsx apps/dashboard/src/pages/chat/panels/ScopedContextPanel.tsx apps/dashboard/src/__tests__/chat-page.test.tsx plan_v7.md` -> passed.

Remaining gaps:

- Chat still contains inline current Employee, Trace, Latest Run, Runtime Dispatch, and thread chrome rendering.
- `ScopedContextPanel` only renders existing context; retrieval quality, ranking, stale/conflict hints, and provider-backed evals remain Track E/H work.
- The dashboard build still has the existing large chunk warning; code splitting remains future frontend hardening.
- Recurrence, SLA, closeout policy, long-running worker evidence, and live provider dogfood remain Track G/J/I work.

Next concrete module:

- Continue Track C by extracting CurrentEmployee / Trace panels from Chat, or continue Track G/J by adding recurrence / SLA / closeout policy smoke.

Anti-Wheel Audit:

- No custom context retrieval engine, provider blocker system, observability backend, memory database, Graphiti writer, or agent loop was added.
- The panel only renders existing context/provenance/provider-blocker facts generated by LangGraph and AITeamOS services.
- Provider blockers remain visible as product facts; Chat does not fake success or mutate provider state.

### 2026-06-20: Track C current employee and trace panel extraction

Status: completed for Current Employee / Trace panel extraction.

Goal: keep Chat moving toward a thin LangGraph-native Workbench by moving Employee summary, capability badges, trace events, and saved path rendering into dedicated read-only panels.

Files changed:

- Added `apps/dashboard/src/pages/chat/panels/CurrentEmployeePanel.tsx`.
- Added `apps/dashboard/src/pages/chat/panels/TracePanel.tsx`.
- Updated `apps/dashboard/src/pages/chat/index.tsx`.
- Updated `plan_v7.md`.

What changed:

- Extracted the inline Current Employee section into `CurrentEmployeePanel`.
- Extracted the inline Trace event / saved paths section into `TracePanel`.
- Moved `capabilityVariant()` into `CurrentEmployeePanel`.
- Moved `dataPreview()` into `TracePanel`.
- Chat page line count dropped from 1847 to 1758 lines after this slice.
- Both panels are read-only and receive existing Chat props; they do not own Employee truth, trace storage, runtime state, or memory writes.

Validation:

- `npm --prefix apps/dashboard test -- src/__tests__/chat-page.test.tsx` -> passed; due the existing npm script shape this ran the dashboard suite, 8 files and 67 tests passed.
- `npm --prefix apps/dashboard run build` -> passed; Vite reported the existing large chunk warning.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check -- apps/dashboard/src/pages/chat/index.tsx apps/dashboard/src/pages/chat/panels/CurrentEmployeePanel.tsx apps/dashboard/src/pages/chat/panels/TracePanel.tsx apps/dashboard/src/__tests__/chat-page.test.tsx plan_v7.md` -> passed.

Remaining gaps:

- Chat still contains inline Latest Run, Runtime Dispatch, provenance links, and thread chrome rendering.
- `CurrentEmployeePanel` only renders existing employee/capability facts; work history, load, capability growth, and memory boundaries remain Employee Track F.
- `TracePanel` only renders local trace/saved paths; replay, evals, and deeper observability remain Track J.
- The dashboard build still has the existing large chunk warning; code splitting remains future frontend hardening.

Next concrete module:

- Continue Track C by extracting LatestRun / RuntimeDispatch or thread chrome, or continue Track G/J with recurrence / SLA / closeout policy smoke.

Anti-Wheel Audit:

- No new employee system, trace store, observability backend, Chat runtime, agent loop, or memory store was added.
- The panels only render existing Chat, Capability, and Trace props; durable truth remains in Tickets, Employees, Assets, Governance, and runtime sessions.
- Chat remains a Workbench projection surface, not the owner of product facts or execution state.

### 2026-06-20: Track C latest run and runtime dispatch panel extraction

Status: completed for Latest Run / Runtime Dispatch panel extraction.

Goal: keep Chat moving toward a thin LangGraph-native Workbench by moving run summary, provenance links, action plans, runtime dispatch facts, execution refs, governance refs, and capability grants into a dedicated read-only panel.

Files changed:

- Added `apps/dashboard/src/pages/chat/panels/LatestRunPanel.tsx`.
- Updated `apps/dashboard/src/pages/chat/index.tsx`.
- Updated `plan_v7.md`.

What changed:

- Extracted inline Latest Run rendering into `LatestRunPanel`.
- Extracted inline Runtime Dispatch rendering into the same run-focused panel.
- Moved Ticket / Employee / Runtime Replay / Asset provenance navigation buttons into the panel while reusing existing `navigateTo` routes.
- Kept all runtime facts as existing props prepared by Chat; the panel does not fetch runtime state, dispatch executors, mutate Tickets, write Assets, or manage memory.
- Chat page line count dropped from 1758 to 1500 lines after this slice.
- The first focused test run caught a missing `ticketReportRefs` prop during extraction; the prop was added before final validation.

Validation:

- `npm --prefix apps/dashboard test -- src/__tests__/chat-page.test.tsx` -> passed; due the existing npm script shape this ran the dashboard suite, 8 files and 67 tests passed.
- `npm --prefix apps/dashboard run build` -> passed; Vite reported the existing large chunk warning.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check -- apps/dashboard/src/pages/chat/index.tsx apps/dashboard/src/pages/chat/panels/LatestRunPanel.tsx apps/dashboard/src/__tests__/chat-page.test.tsx plan_v7.md` -> passed.

Remaining gaps:

- Chat still contains inline thread context chrome, details panel shell, and runtime adapter wiring.
- `LatestRunPanel` is a read-only projection only; runtime replay, eval summaries, and deeper observability remain Track J.
- The dashboard build still has the existing large chunk warning; code splitting remains future frontend hardening.
- Recurrence, SLA, closeout policy, long-running worker evidence, and live provider dogfood remain Track G/J/I work.

Next concrete module:

- Continue Track C by extracting thread context chrome / details shell into a panel, or continue Track G/J with recurrence / SLA / closeout policy smoke.

Anti-Wheel Audit:

- No new Chat runtime, generic checkpoint UI, RuntimeExecutor dispatcher, trace store, observability backend, memory database, Graphiti writer, or agent loop was added.
- The panel only renders existing LangGraph/AITeamOS run metadata and links to existing Ticket, Employee, Runtime Replay, and Assets routes.
- Durable truth remains in Tickets, Employees, Assets, Governance, runtime sessions, and approved Asset/Graphiti projection paths.

### 2026-06-20: Track C Workbench details shell extraction

Status: completed for right-side details shell / Thread Context chrome extraction.

Goal: keep Chat moving toward a thin LangGraph-native Workbench by moving the right details sidebar shell, Thread Context header, active thread summary, and close affordance into a dedicated layout panel.

Files changed:

- Added `apps/dashboard/src/pages/chat/panels/WorkbenchDetailsPanel.tsx`.
- Updated `apps/dashboard/src/pages/chat/index.tsx`.
- Updated `plan_v7.md`.

What changed:

- Extracted the details sidebar `<aside>` and Thread Context header into `WorkbenchDetailsPanel`.
- Kept the existing Workbench child panels composed by Chat in the same order:
  - Workbench snapshot
  - Ticket loop resume
  - Latest run / runtime dispatch
  - Scoped context
  - approval
  - Asset candidates
  - run provenance
  - current Employee
  - trace
- The panel only receives `activeThread`, `children`, and `onClose`; it does not own runtime state, retrieve data, mutate Tickets, write Assets, or manage memory.
- Chat page line count dropped from 1500 to 1472 lines after this slice.

Validation:

- `npm --prefix apps/dashboard test -- src/__tests__/chat-page.test.tsx` -> passed; due the existing npm script shape this ran the dashboard suite, 8 files and 67 tests passed.
- `npm --prefix apps/dashboard run build` -> passed; Vite reported the existing large chunk warning.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check -- apps/dashboard/src/pages/chat/index.tsx apps/dashboard/src/pages/chat/panels/WorkbenchDetailsPanel.tsx apps/dashboard/src/__tests__/chat-page.test.tsx plan_v7.md` -> passed.

Remaining gaps:

- Chat still contains Thread History sidebar chrome, composer/main thread chrome, and runtime adapter wiring.
- `WorkbenchDetailsPanel` is layout only; runtime replay, eval summaries, and deeper observability remain Track J.
- The dashboard build still has the existing large chunk warning; code splitting remains future frontend hardening.
- Recurrence, SLA, closeout policy, long-running worker evidence, and live provider dogfood remain Track G/J/I work.

Next concrete module:

- Continue Track C by extracting Thread History/sidebar chrome or main composer/thread shell, or continue Track G/J with recurrence / SLA / closeout policy smoke.

Anti-Wheel Audit:

- No new Chat runtime, generic streaming protocol, checkpoint UI, RuntimeExecutor dispatcher, observability backend, memory database, Graphiti writer, or agent loop was added.
- The panel is a pure layout wrapper around existing Workbench panels and active thread facts.
- Durable truth remains in Tickets, Employees, Assets, Governance, runtime sessions, and approved Asset/Graphiti projection paths.

### 2026-06-20: Track C Thread History panel extraction

Status: completed for left-side Thread History/sidebar chrome extraction.

Goal: keep Chat moving toward a thin LangGraph-native Workbench by moving thread history filtering, open-thread markers, create/collapse affordances, and delete buttons into a dedicated sidebar panel.

Files changed:

- Added `apps/dashboard/src/pages/chat/panels/ThreadHistoryPanel.tsx`.
- Updated `apps/dashboard/src/pages/chat/index.tsx`.
- Updated `plan_v7.md`.

What changed:

- Extracted the local `ThreadHistory` component into `ThreadHistoryPanel`.
- Moved Thread History search/filtering UI, open-thread badge rendering, create thread button, collapse button, and delete button rendering into the panel.
- Removed the now-local `formatThreadTime()` helper from Chat and kept it inside the sidebar panel.
- Chat still owns thread state, API calls, selected/open thread ids, and callbacks; the panel only renders props and calls the passed handlers.
- Chat page line count dropped from 1472 to 1343 lines after this slice.

Validation:

- `npm --prefix apps/dashboard test -- src/__tests__/chat-page.test.tsx` -> passed; due the existing npm script shape this ran the dashboard suite, 8 files and 67 tests passed.
- `npm --prefix apps/dashboard run build` -> passed; Vite reported the existing large chunk warning.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check -- apps/dashboard/src/pages/chat/index.tsx apps/dashboard/src/pages/chat/panels/ThreadHistoryPanel.tsx apps/dashboard/src/__tests__/chat-page.test.tsx plan_v7.md` -> passed.

Remaining gaps:

- Chat still contains main composer/thread shell, Employee switcher chrome, quick engine controls, and runtime adapter wiring.
- `ThreadHistoryPanel` is UI chrome only; thread persistence and assistant runtime behavior remain in existing Chat/runtime services.
- The dashboard build still has the existing large chunk warning; code splitting remains future frontend hardening.
- Recurrence, SLA, closeout policy, long-running worker evidence, and live provider dogfood remain Track G/J/I work.

Next concrete module:

- Continue Track C by extracting main composer/thread shell or Employee/engine chrome, or continue Track G/J with recurrence / SLA / closeout policy smoke.

Anti-Wheel Audit:

- No new Chat runtime, thread store, generic streaming protocol, checkpoint UI, RuntimeExecutor dispatcher, observability backend, memory database, Graphiti writer, or agent loop was added.
- The panel reuses existing Chat state/callbacks and does not introduce new persistence, orchestration, or runtime ownership.
- Durable truth remains in Tickets, Employees, Assets, Governance, runtime sessions, and approved Asset/Graphiti projection paths.

### 2026-06-20: Track C Employee selector panel extraction

Status: completed for Employee selector chrome extraction.

Goal: keep Chat moving toward a thin LangGraph-native Workbench by moving the Employee combobox UI, employee search, selected employee avatar, dropdown state, and outside-click behavior into a dedicated panel.

Files changed:

- Added `apps/dashboard/src/pages/chat/panels/EmployeeSelectPanel.tsx`.
- Updated `apps/dashboard/src/pages/chat/index.tsx`.
- Updated `plan_v7.md`.

What changed:

- Extracted the local `EmployeeSelect` combobox into `EmployeeSelectPanel`.
- Moved employee search/filtering, dropdown open state, outside-click close behavior, selected initial avatar, and option rendering into the panel.
- Chat still owns selected employee state, Employee API loading, default thread selection, and `onSelectEmployee`; the panel only renders props and calls the passed selection handler.
- Chat page line count dropped from 1343 to 1245 lines after this slice.

Validation:

- `npm --prefix apps/dashboard test -- src/__tests__/chat-page.test.tsx` -> passed; due the existing npm script shape this ran the dashboard suite, 8 files and 67 tests passed.
- `npm --prefix apps/dashboard run build` -> passed; Vite reported the existing large chunk warning.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check -- apps/dashboard/src/pages/chat/index.tsx apps/dashboard/src/pages/chat/panels/EmployeeSelectPanel.tsx apps/dashboard/src/__tests__/chat-page.test.tsx plan_v7.md` -> passed.

Remaining gaps:

- Chat still contains quick engine controls, main composer/thread shell, pending approval chip, Ticket input chrome, and runtime adapter wiring.
- `EmployeeSelectPanel` is UI chrome only; Employee truth, permissions, work history, load, and handoff policy remain in Employees/Track F and runtime services.
- The dashboard build still has the existing large chunk warning; code splitting remains future frontend hardening.
- Recurrence, SLA, closeout policy, long-running worker evidence, and live provider dogfood remain Track G/J/I work.

Next concrete module:

- Continue Track C by extracting quick engine controls or main composer/thread shell, or continue Track G/J with recurrence / SLA / closeout policy smoke.

Anti-Wheel Audit:

- No new Employee system, Chat runtime, thread store, generic streaming protocol, checkpoint UI, RuntimeExecutor dispatcher, observability backend, memory database, Graphiti writer, or agent loop was added.
- The panel reuses existing Chat state/callbacks and does not introduce new persistence, orchestration, permission, memory, or handoff ownership.
- Durable truth remains in Tickets, Employees, Assets, Governance, runtime sessions, and approved Asset/Graphiti projection paths.

### 2026-06-20: Track C AI Engine controls panel extraction

Status: completed for AI Engine selector and quick settings chrome extraction.

Goal: keep Chat moving toward a thin LangGraph-native Workbench by moving AI Engine selection, readiness indicator, quick config popover, DeepSeek presets, option filtering, and quick settings payload shaping into a dedicated panel.

Files changed:

- Added `apps/dashboard/src/pages/chat/panels/AiEngineControlPanel.tsx`.
- Updated `apps/dashboard/src/pages/chat/index.tsx`.
- Updated `plan_v7.md`.

What changed:

- Extracted the inline AI Engine selector block into `AiEngineControlPanel`.
- Moved `EngineQuickConfig` and its quick-setting helpers into the panel:
  - DeepSeek context/output presets
  - quick field filtering
  - draft value construction
  - quick payload creation
  - popover open/close and outside-click handling
- Preserved the original quick setting input placeholder/help behavior during extraction.
- Chat still owns AI Engine state, active-engine persistence, backend API calls, and `updateChatAiEngine`; the panel only renders props and calls the passed change/save handlers.
- Chat page line count dropped from 1245 to 953 lines after this slice.

Validation:

- `npm --prefix apps/dashboard test -- src/__tests__/chat-page.test.tsx` -> passed; due the existing npm script shape this ran the dashboard suite, 8 files and 67 tests passed.
- `npm --prefix apps/dashboard run build` -> passed; Vite reported the existing large chunk warning.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check -- apps/dashboard/src/pages/chat/index.tsx apps/dashboard/src/pages/chat/panels/AiEngineControlPanel.tsx apps/dashboard/src/__tests__/chat-page.test.tsx plan_v7.md` -> passed.

Remaining gaps:

- Chat still contains main composer/thread shell, Ticket input chrome, pending approval chip, and runtime adapter wiring.
- `AiEngineControlPanel` is UI/control chrome only; provider config truth, provider blockers, and runtime execution remain in existing AI Engine settings, provider services, and LangGraph/runtime services.
- The dashboard build still has the existing large chunk warning; code splitting remains future frontend hardening.
- Recurrence, SLA, closeout policy, long-running worker evidence, and live provider dogfood remain Track G/J/I work.

Next concrete module:

- Continue Track C by extracting Ticket / pending approval chrome or main composer/thread shell, or continue Track G/J with recurrence / SLA / closeout policy smoke.

Anti-Wheel Audit:

- No new AI Engine provider system, Chat runtime, thread store, generic streaming protocol, checkpoint UI, RuntimeExecutor dispatcher, observability backend, memory database, Graphiti writer, or agent loop was added.
- The panel reuses existing Chat state/callbacks and existing AI Engine settings API behavior; it does not introduce new provider persistence, orchestration, approval, memory, or runtime ownership.
- Durable truth remains in Tickets, Employees, Assets, Governance, AI Engine settings, runtime sessions, and approved Asset/Graphiti projection paths.

### 2026-06-20: Track C Ticket context panel extraction

Status: completed for Ticket input and pending approval chrome extraction.

Goal: keep Chat moving toward a thin LangGraph-native Workbench by moving the Ticket key input and pending approval chip into a dedicated panel while keeping Ticket binding and approval state owned by Chat/runtime services.

Files changed:

- Added `apps/dashboard/src/pages/chat/panels/TicketContextPanel.tsx`.
- Updated `apps/dashboard/src/pages/chat/index.tsx`.
- Updated `plan_v7.md`.

What changed:

- Extracted the inline Ticket key input into `TicketContextPanel`.
- Extracted the pending approval chip and clear action into the same Ticket-context panel.
- Chat still owns `ticketKey`, `pendingApprovalRef`, ticket key updates, and approval-ref clearing; the panel only renders props and calls the passed handlers.
- Chat page line count dropped from 953 to 925 lines after this slice.

Validation:

- `npm --prefix apps/dashboard test -- src/__tests__/chat-page.test.tsx` -> passed; due the existing npm script shape this ran the dashboard suite, 8 files and 67 tests passed.
- `npm --prefix apps/dashboard run build` -> passed; Vite reported the existing large chunk warning.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check -- apps/dashboard/src/pages/chat/index.tsx apps/dashboard/src/pages/chat/panels/TicketContextPanel.tsx apps/dashboard/src/__tests__/chat-page.test.tsx plan_v7.md` -> passed.

Remaining gaps:

- Chat still contains main composer/thread shell and runtime adapter wiring.
- `TicketContextPanel` is UI chrome only; Ticket truth, approval records, Ticket loop state, runtime interrupts, and governed resume remain in Tickets/Governance/runtime services.
- The dashboard build still has the existing large chunk warning; code splitting remains future frontend hardening.
- Recurrence, SLA, closeout policy, long-running worker evidence, and live provider dogfood remain Track G/J/I work.

Next concrete module:

- Continue Track C by extracting main composer/thread shell, or continue Track G/J with recurrence / SLA / closeout policy smoke.

Anti-Wheel Audit:

- No new Ticket system, approval system, Chat runtime, thread store, generic streaming protocol, checkpoint UI, RuntimeExecutor dispatcher, observability backend, memory database, Graphiti writer, or agent loop was added.
- The panel reuses existing Chat state/callbacks and does not introduce new Ticket persistence, approval persistence, orchestration, memory, or runtime ownership.
- Durable truth remains in Tickets, Employees, Assets, Governance, AI Engine settings, runtime sessions, and approved Asset/Graphiti projection paths.

### 2026-06-20: Track C Workbench thread shell extraction

Status: completed for main composer/thread shell extraction.

Goal: keep Chat moving toward a thin LangGraph-native Workbench by moving assistant-ui message rendering, thread viewport, footer control row, composer input, and send button into a dedicated thread panel.

Files changed:

- Added `apps/dashboard/src/pages/chat/panels/WorkbenchThreadPanel.tsx`.
- Updated `apps/dashboard/src/pages/chat/index.tsx`.
- Updated `plan_v7.md`.

What changed:

- Extracted local `UserMessage`, `AssistantMessage`, and `AiteamosThread` into `WorkbenchThreadPanel`.
- Moved assistant-ui primitives into the panel:
  - `ThreadPrimitive.Root`
  - `ThreadPrimitive.Viewport`
  - `ThreadPrimitive.Messages`
  - `ThreadPrimitive.ViewportFooter`
  - `ComposerPrimitive.Root`
  - `ComposerPrimitive.Input`
  - `ComposerPrimitive.Send`
- Kept the previously extracted footer panels composed inside the thread shell:
  - Employee selector
  - AI Engine controls
  - Ticket context / pending approval chip
- Chat still owns employee/thread/Ticket/AI Engine state, runtime bridge state, API calls, and callbacks; the panel only renders existing assistant-ui primitives and calls passed handlers.
- Chat page line count dropped from 925 to 796 lines after this slice.

Validation:

- `npm --prefix apps/dashboard test -- src/__tests__/chat-page.test.tsx` -> passed; due the existing npm script shape this ran the dashboard suite, 8 files and 67 tests passed.
- `npm --prefix apps/dashboard run build` -> passed; Vite reported the existing large chunk warning.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check -- apps/dashboard/src/pages/chat/index.tsx apps/dashboard/src/pages/chat/panels/WorkbenchThreadPanel.tsx apps/dashboard/src/__tests__/chat-page.test.tsx plan_v7.md` -> passed.

Remaining gaps:

- Chat still contains runtime adapter wiring, bridge callbacks, data loading, state derivation, and Workbench panel composition.
- `WorkbenchThreadPanel` reuses assistant-ui primitives only; it does not introduce a new Chat runtime, generic streaming protocol, custom thread store, or agent loop.
- The dashboard build still has the existing large chunk warning; code splitting remains future frontend hardening.
- Recurrence, SLA, closeout policy, long-running worker evidence, and live provider dogfood remain Track G/J/I work.

Next concrete module:

- Continue Track C by extracting runtime adapter wiring / Workbench bridge composition, or continue Track G/J with recurrence / SLA / closeout policy smoke.

Anti-Wheel Audit:

- No new Chat runtime, thread store, generic streaming protocol, checkpoint UI, RuntimeExecutor dispatcher, observability backend, memory database, Graphiti writer, or agent loop was added.
- The panel reuses assistant-ui primitives and existing AITeamOS props/callbacks; it does not introduce persistence, orchestration, approval, memory, or runtime ownership.
- Durable truth remains in Tickets, Employees, Assets, Governance, AI Engine settings, runtime sessions, and approved Asset/Graphiti projection paths.

### 2026-06-20: Track C Workbench run view-model extraction

Status: completed for run metadata / Workbench snapshot panel state assembly extraction.

Goal: keep Chat moving toward a thin LangGraph-native Workbench by moving the derived `runMetadata` / `workbenchSnapshot` parsing for the right-side panels out of the Chat route component and into a dedicated view-model module.

Files changed:

- Added `apps/dashboard/src/pages/chat/runtime/workbenchRunViewModel.ts`.
- Updated `apps/dashboard/src/pages/chat/index.tsx`.
- Updated `plan_v7.md`.

What changed:

- Extracted the derived props for `LatestRunPanel`, `ScopedContextPanel`, `ApprovalPanel`, `AssetCandidatesPanel`, and `RunProvenancePanel` into `createWorkbenchRunViewModel`.
- Kept Chat responsible for loading employees/threads/capabilities/AI Engine settings, handling callbacks, and passing AITeamOS state into panels.
- Kept LangGraph / assistant-ui runtime behavior inside existing runtime provider and bridge modules; the new module only normalizes already-returned runtime values into panel props.
- Fixed the initial Hook-order issue found by the first test run by creating the view-model before the loading early return.
- Chat page line count dropped from 796 to 612 lines after this slice.

Validation:

- Initial `npm --prefix apps/dashboard test -- src/__tests__/chat-page.test.tsx` caught a React Hook order regression; fixed by moving `useMemo(createWorkbenchRunViewModel)` before the `loading` early return.
- Final `npm --prefix apps/dashboard test -- src/__tests__/chat-page.test.tsx` -> passed; due the existing npm script shape this ran the dashboard suite, 8 files and 67 tests passed.
- `npm --prefix apps/dashboard run build` -> passed; Vite reported the existing large chunk warning.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.

Remaining gaps:

- Chat still owns runtime provider composition, bridge callbacks, thread/API loading state, and top-level Workbench layout wiring.
- `workbenchRunViewModel` is a deterministic frontend view-model only; it does not create a new runtime, thread store, streaming protocol, checkpoint UI, memory layer, or agent loop.
- The dashboard build still has the existing large chunk warning; route-level/code-splitting remains future frontend hardening.
- Recurrence, SLA, closeout policy, long-running worker evidence, and live provider dogfood remain Track G/J/I work.

Next concrete module:

- Continue Track C by extracting runtime bridge callbacks / thread API state into narrower hooks or modules if it reduces ownership confusion, or continue Track G/J with recurrence / SLA / closeout policy smoke.

Anti-Wheel Audit:

- No new Chat runtime, thread store, generic streaming protocol, checkpoint UI, RuntimeExecutor dispatcher, observability backend, memory database, Graphiti writer, or agent loop was added.
- The view-model reuses existing LangGraph state, run metadata, and Workbench panel contracts; it only moves parsing and prop assembly out of the route component.
- Durable truth remains in Tickets, Employees, Assets, Governance, AI Engine settings, runtime sessions, and approved Asset/Graphiti projection paths.

### 2026-06-20: Track G Ticket loop SLA / recurrence / closeout policy metadata

Status: completed for Ticket loop policy metadata and timeline visibility.

Goal: make SLA, recurrence, and closeout policy first-class, durable Ticket loop facts before adding any scheduler or escalation runner, so operators and future autonomous nodes can inspect the intended operating policy from the existing Ticket loop policy API and timeline summary.

Files changed:

- Updated `services/api/aiteamos_api/read/ticket_loop_service.py`.
- Updated `tests/test_execution_dispatch_contract.py`.
- Updated `plan_v7.md`.

What changed:

- Added typed `TicketLoopSlaPolicy`, `TicketLoopRecurrencePolicy`, and `TicketLoopCloseoutPolicy` models.
- Extended `TicketLoopPolicy` and `TicketLoopPolicyUpdateRequest` with nested `sla`, `recurrence`, and `closeout` fields.
- Extended policy merging so metadata, registry updates, and route PUT payloads can persist these fields in `.aiteamos/ticket_loop_policies.json`.
- Added `TicketLoopPolicyStatus` to `TicketLoopTimelineSummary` so Ticket timeline clients can see policy source, validation requirement, SLA settings, recurrence settings, closeout settings, configured flags, and saved path.
- Confirmed loop execution carries these fields through `ExecutionRequest.permission_policy.loop_policy`, preserving the existing ExecutionRequest / ExecutionResult contract.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/ticket_loop_service.py services/api/aiteamos_api/read/ticket_routes.py tests/test_execution_dispatch_contract.py` -> passed.
- `pytest tests/test_execution_dispatch_contract.py -k "ticket_loop_policy_registry_caps_run_and_controls_approval_policy or ticket_loop_policy_routes_read_and_update_registry"` -> 2 passed.
- `pytest tests/test_execution_dispatch_contract.py -k "ticket_loop_policy or ticket_loop_queue or closeout"` -> 14 passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.

Remaining gaps:

- This is policy metadata and timeline visibility, not a new recurrence scheduler or SLA escalation engine.
- SLA breach detection, escalation Ticket reports, recurring queue enqueue rules, closeout automation, and long-running worker evidence remain Track G/J work.
- The policy is now visible to graph nodes and UI clients, but no LangGraph node currently makes routing decisions from these new fields.

Next concrete module:

- Continue Track G by adding SLA breach / recurrence preflight smoke over the existing queue worker, or continue Track A/B by adding a graph node that reads the policy status before `close_or_continue_ticket_loop`.

Anti-Wheel Audit:

- No new scheduler, queue runner, Chat runtime, agent loop, streaming protocol, memory database, Graphiti writer, or observability backend was added.
- The change extends the existing Ticket loop policy API, existing timeline summary, and existing `ExecutionRequest.permission_policy.loop_policy` payload.
- Durable truth remains in Tickets, Ticket loop policy registry, Ticket reports, Assets, Governance, runtime sessions, and approved Asset/Graphiti projection paths.

### 2026-06-20: Track A/G close-or-continue Ticket loop graph node

Status: completed for graph-level Ticket loop policy/timeline read and close-or-continue decision projection.

Goal: move the previously added Ticket loop SLA / recurrence / closeout policy facts into the LangGraph execution state so the Workbench graph can reason about Ticket loop continuation without adding a new scheduler, queue runner, or route-layer orchestration.

Files changed:

- Added `services/api/aiteamos_api/agents/workbench/nodes/ticket_loop.py`.
- Updated `services/api/aiteamos_api/agents/aiteamos_workbench_graph.py`.
- Updated `services/api/aiteamos_api/agents/workbench/state.py`.
- Updated `services/api/aiteamos_api/agents/workbench/nodes/response.py`.
- Updated `tests/test_aiteamos_workbench_graph.py`.
- Updated `plan_v7.md`.

What changed:

- Added `close_or_continue_ticket_loop` as a real Workbench LangGraph node between `propose_asset_candidates` and `update_workbench_state`.
- The node resolves the current Ticket from graph state, calls the existing `ticket_loop_timeline()` service through `asyncio.to_thread`, and exposes `ticket_loop_summary`, `ticket_loop_policy`, and `ticket_loop_decision` in graph state.
- The decision currently projects actions such as `not_applicable`, `wait_for_approval`, `resume_available`, `inspect_queue`, `await_queue_worker`, `retry_available`, `request_validation`, `propose_closeout_assets`, `recurrence_scheduled`, and `terminal`.
- Graph state now has typed keys for `ticket_loop_summary`, `ticket_loop_policy`, and `ticket_loop_decision`.
- `update_workbench_state` now preserves provider blockers emitted by prior nodes, so Ticket loop blockers remain visible instead of being overwritten by response projection.
- Workbench graph integration tests now prove a Ticket-bound run reads SLA / recurrence / closeout policy from the Ticket loop registry and surfaces it through LangGraph state.

Validation:

- `python -m py_compile services/api/aiteamos_api/agents/aiteamos_workbench_graph.py services/api/aiteamos_api/agents/workbench/state.py services/api/aiteamos_api/agents/workbench/nodes/ticket_loop.py services/api/aiteamos_api/agents/workbench/nodes/response.py tests/test_aiteamos_workbench_graph.py` -> passed.
- `pytest tests/test_aiteamos_workbench_graph.py -k "structured_state or records_employee_handoff"` -> 2 passed.
- `pytest tests/test_aiteamos_workbench_graph.py` -> 7 passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.

Remaining gaps:

- The node reads and projects policy/timeline facts, but it does not yet enqueue recurring work, escalate SLA breaches, or auto-close Tickets.
- No graph conditional edge branches on `ticket_loop_decision` yet; the next production slice should use this state for close/continue routing only where existing Ticket services already own durable writes.
- Long-running worker evidence and live provider dogfood remain Track G/J/I work.

Next concrete module:

- Continue Track A/G by adding a graph conditional or service-backed preflight that uses `ticket_loop_decision` for SLA breach / recurrence / closeout routing, or continue Track G by adding SLA breach / recurrence smoke over the existing queue worker.

Anti-Wheel Audit:

- No new scheduler, queue worker, Chat runtime, generic agent loop, generic streaming protocol, memory database, Graphiti writer, or observability backend was added.
- The node reuses the existing Ticket loop timeline / policy service and only projects facts into LangGraph state.
- Durable truth remains in Tickets, Ticket loop policy registry, Ticket reports, Assets, Governance, runtime sessions, and approved Asset/Graphiti projection paths.

### 2026-06-20: Track A/G graph-applied closeout candidate decision

Status: completed for graph-applied, service-backed closeout Asset candidate proposal.

Goal: turn `ticket_loop_decision.action=propose_closeout_assets` from a read-only projection into a governed action that reuses the existing Ticket closeout Asset candidate service, without creating a new scheduler, memory writer, Graphiti projection path, or route-layer agent loop.

Files changed:

- Updated `services/api/aiteamos_api/agents/workbench/nodes/ticket_loop.py`.
- Updated `services/api/aiteamos_api/agents/workbench/nodes/response.py`.
- Updated `tests/test_aiteamos_workbench_graph.py`.
- Updated `plan_v7.md`.

What changed:

- `close_or_continue_ticket_loop` now calls `_apply_ticket_loop_decision` after reading Ticket timeline and loop policy facts.
- For `propose_closeout_assets`, the graph node calls the existing `propose_ticket_closeout_asset_candidates()` service.
- The default closeout guard requires validation evidence before proposal; Ticket loop policy can explicitly set `closeout.require_validation_evidence=false`.
- Applied action details are projected into `ticket_loop_decision.applied_action`, including status, detail, report id, candidate ids, saved paths, and candidate count.
- Full closeout candidate records are merged into `asset_candidates` so Workbench can show them through the existing Assets panel.
- Provider blockers from closeout guard failures stay visible in graph state.
- Existing closeout service idempotency is preserved: if transition/report logic already proposed candidates, the graph-applied action returns the existing candidates without duplicating durable assets.
- `update_workbench_state` now preserves an upstream `workbench_panels.assets=true` flag so graph-proposed candidates are not hidden by final response projection.

Validation:

- `pytest tests/test_aiteamos_workbench_graph.py -k "closeout_decision"` -> 1 passed.
- `python -m py_compile services/api/aiteamos_api/agents/workbench/nodes/ticket_loop.py services/api/aiteamos_api/agents/workbench/nodes/response.py tests/test_aiteamos_workbench_graph.py` -> passed.
- `pytest tests/test_aiteamos_workbench_graph.py` -> 8 passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `pytest tests/test_execution_dispatch_contract.py -k "closeout"` -> 3 passed.

Remaining gaps:

- No recurrence scheduler, SLA escalation, auto-approval, closeout settlement, memory write, or Graphiti projection was added.
- Graph still does not branch on SLA / recurrence preflight.
- This closes the closeout candidate proposal action only; approval, settlement, projection, stale cleanup, and long-running worker evidence remain v7 work.
- Need live provider dogfood proving the graph-applied closeout action in a real runtime run.

Next concrete module:

- Continue Track A/G by adding SLA breach or recurrence preflight over existing Ticket loop services, or continue Track G by proving those policies with the existing queue worker.

Anti-Wheel Audit:

- No new scheduler, queue worker, Chat runtime, agent loop, memory database, Graphiti writer, or observability backend was added.
- Reused existing closeout candidate service, Ticket loop policy/timeline state, and Workbench graph state.
- Durable truth remains in Tickets, Ticket reports, Asset candidates/review queue, Governance, runtime sessions, and approved Asset/Graphiti projection paths.

### 2026-06-20: Track G queue-worker SLA / recurrence policy preflight

Status: completed for Ticket-native SLA breach and recurrence-due preflight signals from the existing queue worker.

Goal: make SLA / recurrence policy metadata operationally visible in the autonomous loop by reusing the existing Ticket loop queue worker and `TicketLoopPolicyAction` mechanism, without adding a second scheduler, worker daemon, memory writer, Graphiti writer, or route-layer agent loop.

Files changed:

- Updated `services/api/aiteamos_api/read/ticket_loop_service.py`.
- Updated `tests/test_execution_dispatch_contract.py`.
- Updated `plan_v7.md`.

What changed:

- Added `run_ticket_loop_policy_preflight()` to inspect existing Ticket loop policy registry and active queue tickets.
- `pump_ticket_loop_queue()` now runs policy preflight before processing queued work and returns those signals through the existing `policy_actions` list.
- SLA response deadline breaches create a `ticket_loop_sla_breach` Ticket report and return a `sla_breach_report` policy action.
- Due recurrence policies create a `ticket_loop_recurrence_due` Ticket report and return a `recurrence_due_report` policy action.
- Both preflight actions are idempotent through Ticket event `source_run_id`, so repeated worker ticks do not duplicate reports for the same policy due event.
- Existing queue-worker status automatically records these actions in `recent_policy_actions` through the existing worker status path.
- No recurrence auto-enqueue or SLA assignment/escalation runner was added; this slice only turns policy metadata into Ticket-native operational signals.

Validation:

- `pytest tests/test_execution_dispatch_contract.py -k "sla_and_recurrence_preflight"` -> 1 passed.
- `python -m py_compile services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py` -> passed.
- `pytest tests/test_execution_dispatch_contract.py -k "ticket_loop_policy or ticket_loop_queue or closeout or failure_retrospective or sla_and_recurrence_preflight"` -> 15 passed.
- `pytest tests/test_aiteamos_workbench_graph.py` -> 8 passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `python scripts/ticket_loop_queue_worker_smoke.py --workspace-dir /tmp/aiteamos-ticket-loop-worker-smoke-v7` -> passed.

Remaining gaps:

- SLA escalation is not yet assigning or handing off to the escalation Employee.
- Recurrence due preflight does not yet enqueue the next governed run or update `next_run_at`.
- There is still no long-running production worker evidence for SLA / recurrence policies.
- Graph nodes do not yet branch on `sla_breach_report` / `recurrence_due_report` policy actions.

Next concrete module:

- Continue Track G by adding governed recurrence auto-enqueue through the existing Ticket loop queue worker, or continue Track A/G by projecting SLA / recurrence preflight actions into the Workbench graph decision state.

Anti-Wheel Audit:

- No new scheduler, queue worker, Chat runtime, agent loop, memory database, Graphiti writer, or observability backend was added.
- Reused existing Ticket loop policy registry, queue pump, queue worker, Ticket reports, timeline projection, and `TicketLoopPolicyAction` status path.
- Durable truth remains in Tickets, Ticket reports, queue worker state, Asset candidates/review queue, Governance, runtime sessions, and approved Asset/Graphiti projection paths.

### 2026-06-20: Track G governed recurrence auto-enqueue

Status: completed for recurrence-due auto-enqueue through the existing Ticket loop queue worker.

Goal: move recurrence from "due signal recorded" to "next governed loop run is automatically queued and processed by the existing queue worker", without adding a second scheduler, worker daemon, generic agent loop, memory writer, or Graphiti projection path.

Files changed:

- Updated `services/api/aiteamos_api/read/ticket_loop_service.py`.
- Updated `tests/test_execution_dispatch_contract.py`.
- Updated `plan_v7.md`.

What changed:

- Extended `TicketLoopPolicyAction` with `queue_ids` and `run_ids` so policy actions can point to existing queue/run records.
- `run_ticket_loop_policy_preflight()` still runs inside the existing queue pump/worker path.
- Due recurrence policy now calls the existing `enqueue_ticket_loop()` service and returns `recurrence_auto_enqueued`.
- The queued run receives recurrence provenance in `runtime_config`: source run id, due timestamp, occurrence count, and next scheduled timestamp.
- The recurrence due Ticket report now links the generated queue item and run id.
- Recurrence policy `next_run_at` is advanced after enqueue; if `max_occurrences` is reached, recurrence is disabled in the policy registry.
- Idempotency is preserved through Ticket event `source_run_id` and existing queue request `runtime_config.recurrence_source_run_id`.
- The existing queue worker may process the auto-enqueued run in the same tick, using normal `TicketAutonomousLoopService` / `ExecutionRequest` / `ExecutionResult` behavior.

Validation:

- `pytest tests/test_execution_dispatch_contract.py -k "auto_enqueues_recurrence"` -> 1 passed.
- `python -m py_compile services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py` -> passed.
- `pytest tests/test_execution_dispatch_contract.py -k "ticket_loop_policy or ticket_loop_queue or closeout or failure_retrospective or auto_enqueues_recurrence"` -> 15 passed.
- `pytest tests/test_aiteamos_workbench_graph.py` -> 8 passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `python scripts/ticket_loop_queue_worker_smoke.py --workspace-dir /tmp/aiteamos-ticket-loop-worker-smoke-v7-auto-enqueue` -> passed.
- `pytest tests/test_execution_dispatch_contract.py` -> 88 passed.

Remaining gaps:

- SLA escalation now has a Ticket-native signal, but assignment / handoff is covered by the next Track G slice below.
- Recurrence auto-enqueue has deterministic tests and a worker-smoke non-regression check, but not long-running production worker evidence.
- Workbench graph state does not yet project `policy_actions.queue_ids` / `run_ids` as first-class `ticket_loop_decision` evidence.
- No auto-approval, closeout settlement, memory write, or Graphiti projection was added.

Next concrete module:

- Continue Track G by adding SLA escalation assignment / handoff through existing Ticket services, or continue Track A/G by projecting queue policy action refs into the Workbench graph and panels.

Anti-Wheel Audit:

- No new scheduler, queue worker, Chat runtime, generic agent loop, memory database, Graphiti writer, or observability backend was added.
- Reused existing Ticket loop policy registry, queue pump, queue worker, `enqueue_ticket_loop()`, Ticket reports, runtime request/result contracts, and worker `policy_actions`.
- Durable truth remains in Tickets, Ticket reports, queue records, queue worker state, Asset candidates/review queue, Governance, runtime sessions, and approved Asset/Graphiti projection paths.

### 2026-06-20: Track G SLA escalation handoff

Status: completed for SLA breach escalation assignment via existing Ticket handoff events.

Goal: turn SLA breach from "report-only signal" into a Ticket-native escalation handoff to the configured escalation Employee, without adding a new escalation runner, scheduler, agent loop, memory writer, Graphiti projection path, or route-layer orchestration.

Files changed:

- Updated `services/api/aiteamos_api/read/ticket_loop_service.py`.
- Updated `tests/test_execution_dispatch_contract.py`.
- Updated `plan_v7.md`.

What changed:

- Extended `TicketLoopPolicyAction` with `handoff_refs` so worker policy actions can point to durable Ticket handoff / assignment events.
- `run_ticket_loop_policy_preflight()` now refreshes the Ticket after each policy action, so later actions in the same worker tick see updated assignee state.
- SLA response breach preflight now calls existing `record_ticket_handoff()` when `policy.sla.escalation_employee_id` or `policy.sla.escalation_role` is configured and differs from the current assignee.
- The SLA policy action becomes `sla_escalation_handoff` with status `escalated` and durable `handoff_requested` / `assigned` refs.
- The existing recurrence auto-enqueue in the same tick now uses the refreshed assignee after SLA escalation, so the next governed run is owned by the escalated Employee.
- If there is no escalation target, or the target is already assigned, the action remains a normal `sla_breach_report`.

Validation:

- `pytest tests/test_execution_dispatch_contract.py -k "auto_enqueues_recurrence"` -> 1 passed.
- `python -m py_compile services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py` -> passed.
- `pytest tests/test_execution_dispatch_contract.py -k "ticket_loop_policy or ticket_loop_queue or closeout or failure_retrospective or auto_enqueues_recurrence or employee_handoff"` -> 15 passed.
- `pytest tests/test_aiteamos_workbench_graph.py` -> 8 passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `pytest tests/test_execution_dispatch_contract.py` -> 88 passed.
- `python scripts/ticket_loop_queue_worker_smoke.py --workspace-dir /tmp/aiteamos-ticket-loop-worker-smoke-v7-sla-handoff` -> passed.

Remaining gaps:

- SLA escalation handoff does not yet create a targeted escalation queue run unless recurrence also queues work in the same tick.
- Workbench graph projection of `policy_actions.handoff_refs`, `queue_ids`, and `run_ids` is covered by the next Track A/G slice below.
- Long-running worker evidence and live provider dogfood remain Track G/J/I work.
- No auto-approval, closeout settlement, memory write, or Graphiti projection was added.

Next concrete module:

- Continue Track A/G by projecting queue policy action refs into the Workbench graph and panels, or continue Track G by adding a targeted SLA escalation queue run through existing `enqueue_ticket_loop()`.

Anti-Wheel Audit:

- No new scheduler, queue worker, escalation runner, Chat runtime, generic agent loop, memory database, Graphiti writer, or observability backend was added.
- Reused existing Ticket loop policy registry, queue pump, queue worker, `record_ticket_handoff()`, Ticket events/reports, runtime request/result contracts, and worker `policy_actions`.
- Durable truth remains in Tickets, Ticket reports, Ticket handoff/assigned events, queue records, queue worker state, Asset candidates/review queue, Governance, runtime sessions, and approved Asset/Graphiti projection paths.

### 2026-06-20: Track A/G Workbench graph policy action projection

Status: completed for projecting queue worker policy actions into Workbench LangGraph state.

Goal: make SLA handoff / recurrence queue policy actions visible to the LangGraph Workbench loop as decision evidence, while keeping all durable writes owned by existing Ticket loop worker and Ticket services.

Files changed:

- Updated `services/api/aiteamos_api/agents/workbench/state.py`.
- Updated `services/api/aiteamos_api/agents/workbench/nodes/ticket_loop.py`.
- Updated `tests/test_aiteamos_workbench_graph.py`.
- Updated `plan_v7.md`.

What changed:

- Added `ticket_loop_policy_actions` to `AITeamOSWorkbenchState`.
- `close_or_continue_ticket_loop` now reads existing `ticket_loop_queue_worker_status()` and filters `recent_policy_actions` for the current Ticket.
- Recent policy actions are projected into `ticket_loop_decision.policy_actions`, `policy_action_count`, `policy_action_kinds`, and `policy_action_refs`.
- `handoff_refs`, `queue_ids`, `run_ids`, and report refs are normalized into graph-visible refs.
- SLA handoff refs are merged into `ticket_handoff_refs` with source `ticket_loop_policy_action`.
- Workbench `handoff` panel is enabled when Ticket loop policy actions contain handoff refs.
- Runtime status now includes `ticket_loop_policy_action_count` and `ticket_loop_policy_action_kinds`.
- Provenance events include `ticket_loop_policy_action` summaries sourced from the queue worker.
- The node only reads existing worker state; it does not pump the queue, enqueue work, mutate Tickets, write memory, or project to Graphiti.

Validation:

- `pytest tests/test_aiteamos_workbench_graph.py -k "policy_actions"` -> 1 passed.
- `python -m py_compile services/api/aiteamos_api/agents/workbench/state.py services/api/aiteamos_api/agents/workbench/nodes/ticket_loop.py tests/test_aiteamos_workbench_graph.py` -> passed.
- `pytest tests/test_aiteamos_workbench_graph.py` -> 9 passed.
- `pytest tests/test_execution_dispatch_contract.py -k "ticket_loop_policy or ticket_loop_queue or closeout or failure_retrospective or auto_enqueues_recurrence or employee_handoff"` -> 15 passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.

Remaining gaps:

- Workbench UI panels still need to render these `policy_action_refs` directly instead of only receiving them in graph state.
- SLA escalation handoff still does not create a targeted escalation queue run unless recurrence also queues work in the same tick.
- Long-running worker evidence and live provider dogfood remain Track G/J/I work.
- No auto-approval, closeout settlement, memory write, or Graphiti projection was added.

Next concrete module:

- Continue Track C/A by rendering `ticket_loop_policy_actions` / refs in the existing Workbench Ticket loop panel, or continue Track G by adding a targeted SLA escalation queue run through existing `enqueue_ticket_loop()`.

Anti-Wheel Audit:

- No new scheduler, queue worker, escalation runner, Chat runtime, generic agent loop, memory database, Graphiti writer, or observability backend was added.
- Reused existing Ticket loop worker state, Workbench LangGraph node, Ticket events/reports, queue records, and worker `policy_actions`.
- Durable truth remains in Tickets, Ticket reports, Ticket handoff/assigned events, queue records, queue worker state, Asset candidates/review queue, Governance, runtime sessions, and approved Asset/Graphiti projection paths.

### 2026-06-20: Track C/A Workbench Ticket loop policy panel

Status: completed for rendering LangGraph-projected Ticket loop policy actions in Chat Workbench.

Goal: show SLA escalation handoff and recurrence queue refs inside the existing LangGraph-native Workbench surface, without adding a new Chat runtime, polling loop, scheduler, route-layer orchestration, or generic agent UI.

Files changed:

- Updated `apps/dashboard/src/pages/chat/runtime/workbenchState.ts`.
- Updated `apps/dashboard/src/pages/chat/runtime/LangGraphWorkbenchProvider.tsx`.
- Updated `apps/dashboard/src/pages/chat/runtime/workbenchRunViewModel.ts`.
- Added `apps/dashboard/src/pages/chat/panels/TicketLoopPolicyPanel.tsx`.
- Updated `apps/dashboard/src/pages/chat/index.tsx`.
- Updated `apps/dashboard/src/api/tickets.ts`.
- Updated `apps/dashboard/src/__tests__/chat-page.test.tsx`.
- Updated `plan_v7.md`.

What changed:

- `WorkbenchSnapshot` now includes `ticketLoopDecision` and `ticketLoopPolicyActions` from LangGraph state.
- `WorkbenchStateBridge` subscribes to `ticket_loop_decision` and `ticket_loop_policy_actions` through the existing LangChain state bridge.
- `createWorkbenchRunViewModel()` now exposes `ticketLoopPolicyProps`, including normalized `policy_action_refs`.
- Chat Workbench now renders a compact `Ticket Loop Policy` panel beside the existing Ticket loop resume panel.
- The panel displays action kind/status/detail plus handoff, queue, run, candidate, and report refs from graph state.
- Chat page remains a composition shell; no generic agent loop, streaming protocol, queue worker, scheduler, memory writer, or Graphiti projector was added.
- Frontend test fixtures now assert that SLA handoff and recurrence enqueue policy actions are visible in the Workbench UI.

Validation:

- `npm --prefix apps/dashboard test -- --run src/__tests__/chat-page.test.tsx` -> 8 files / 67 tests passed. Note: the current dashboard test script expands this invocation to the full `src` test suite.
- `npm --prefix apps/dashboard run build` -> passed; Vite reported the existing large chunk warning.
- `pytest tests/test_aiteamos_workbench_graph.py -k "policy_actions"` -> 1 passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `rg -n "[ \t]+$" apps/dashboard/src/pages/chat/runtime/workbenchState.ts apps/dashboard/src/pages/chat/runtime/LangGraphWorkbenchProvider.tsx apps/dashboard/src/pages/chat/runtime/workbenchRunViewModel.ts apps/dashboard/src/pages/chat/panels/TicketLoopPolicyPanel.tsx apps/dashboard/src/pages/chat/index.tsx apps/dashboard/src/api/tickets.ts apps/dashboard/src/__tests__/chat-page.test.tsx` -> no matches.
- `git diff --check -- apps/dashboard/src/pages/chat/runtime/workbenchState.ts apps/dashboard/src/pages/chat/runtime/LangGraphWorkbenchProvider.tsx apps/dashboard/src/pages/chat/runtime/workbenchRunViewModel.ts apps/dashboard/src/pages/chat/panels/TicketLoopPolicyPanel.tsx apps/dashboard/src/pages/chat/index.tsx apps/dashboard/src/api/tickets.ts apps/dashboard/src/__tests__/chat-page.test.tsx plan_v7.md` -> passed.

Remaining gaps:

- SLA escalation handoff still does not create a targeted escalation queue run unless recurrence also queues work in the same tick.
- Long-running worker evidence and live provider dogfood remain Track G/J/I work.
- No auto-approval, closeout settlement, memory write, or Graphiti projection was added.
- Chat runtime adapter callbacks and thread/API state can still be split further, but the Ticket loop policy rendering gap is closed.

Next concrete module:

- Continue Track G by adding a targeted SLA escalation queue run through existing `enqueue_ticket_loop()`, or continue Track J/I by adding long-running worker / live-provider dogfood evidence.

Anti-Wheel Audit:

- No new Chat runtime, generic agent UI, scheduler, queue worker, escalation runner, memory database, Graphiti writer, or observability backend was added.
- Reused existing LangChain state bridge, assistant-ui Workbench shell, Workbench graph state, Ticket loop worker state, Ticket reports, handoff refs, queue refs, and existing UI panel composition.
- Durable truth remains in Tickets, Ticket reports, Ticket handoff/assigned events, queue records, queue worker state, Asset candidates/review queue, Governance, runtime sessions, and approved Asset/Graphiti projection paths.

### 2026-06-20: Track G targeted SLA escalation queue run

Status: completed for new SLA escalation breaches creating targeted governed queue runs through the existing Ticket loop queue.

Goal: make SLA escalation not only report and handoff the Ticket, but also queue the next governed loop run for the escalation Employee, without adding a second scheduler, escalation daemon, generic agent loop, memory writer, Graphiti projection path, or route-layer orchestration.

Files changed:

- Updated `services/api/aiteamos_api/read/ticket_loop_service.py`.
- Updated `tests/test_execution_dispatch_contract.py`.
- Updated `plan_v7.md`.

What changed:

- SLA response breach preflight now reuses existing `enqueue_ticket_loop()` when an escalation Employee or role is configured.
- The targeted escalation queue item uses priority `40`, ahead of recurrence's priority `80`, so the escalated run is processed first when both policies are due in the same tick.
- The queued SLA run carries provenance in `runtime_config`: `sla_escalation_source_run_id`, `sla_due_at`, response due seconds, escalation Employee, and escalation role.
- `sla_escalation_handoff` policy actions now include `queue_ids` and `run_ids` in addition to existing `handoff_refs` and `report_id`.
- A shared `_queue_item_for_runtime_source()` helper now supports both recurrence and SLA queue idempotency by reading existing queue request `runtime_config`.
- Idempotency remains Ticket-native: once the SLA source run id is present on Ticket events, preflight does not create another report, handoff, or queue item; if a queue item exists but the Ticket source event was not written yet, the next preflight can reuse the existing queue item.
- The existing queue worker processes the targeted SLA run through normal `TicketAutonomousLoopService` / `ExecutionRequest` / `ExecutionResult` behavior.
- Historical report-only SLA breach events are not replayed or backfilled automatically.

Validation:

- `pytest tests/test_execution_dispatch_contract.py -k "records_sla_and_auto_enqueues_recurrence"` -> 1 passed.
- `python -m py_compile services/api/aiteamos_api/read/ticket_loop_service.py tests/test_execution_dispatch_contract.py` -> passed.
- `pytest tests/test_execution_dispatch_contract.py -k "ticket_loop_policy or ticket_loop_queue or closeout or failure_retrospective or auto_enqueues_recurrence or employee_handoff"` -> 15 passed.
- `pytest tests/test_execution_dispatch_contract.py` -> 88 passed.
- `pytest tests/test_aiteamos_workbench_graph.py -k "policy_actions"` -> 1 passed.
- `pytest tests/test_aiteamos_workbench_graph.py` -> 9 passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `python scripts/ticket_loop_queue_worker_smoke.py --workspace-dir /tmp/aiteamos-ticket-loop-worker-smoke-v7-sla-targeted-queue` -> passed.

Remaining gaps:

- Long-running worker evidence and live provider dogfood remain Track G/J/I work.
- No auto-approval, closeout settlement, memory write, or Graphiti projection was added.
- Historical report-only SLA breach events are not auto-backfilled into queue work.
- Closeout policy can propose Asset candidates, but settlement / approval automation is still incomplete.

Next concrete module:

- Continue Track G/J/I by adding long-running worker / live-provider dogfood evidence, or continue Track G/F by implementing governed closeout settlement and approved Asset projection through existing Review Queue / AssetRecord / Graphiti paths.

Anti-Wheel Audit:

- No new scheduler, queue worker, escalation runner, Chat runtime, generic agent loop, memory database, Graphiti writer, or observability backend was added.
- Reused existing Ticket loop policy registry, queue pump, queue worker, `enqueue_ticket_loop()`, `record_ticket_handoff()`, Ticket reports/events, runtime request/result contracts, and worker `policy_actions`.
- Durable truth remains in Tickets, Ticket reports, Ticket handoff/assigned events, queue records, queue worker state, Asset candidates/review queue, Governance, runtime sessions, and approved Asset/Graphiti projection paths.

### 2026-06-20: Track G/F governed closeout settlement

Status: completed for explicit closeout settlement through existing Asset review, AssetRecord, and Graphiti projection services.

Goal: turn validated Ticket closeout from "candidates proposed" into a governed settlement path that can approve reviewable closeout Assets and project approved AssetRecords to Graphiti, without adding a new memory database, Graphiti writer, generic agent loop, route-layer orchestration, or bypassing review provenance.

Files changed:

- Updated `services/api/aiteamos_api/read/asset_candidate_service.py`.
- Updated `services/api/aiteamos_api/read/ticket_routes.py`.
- Updated `tests/test_execution_dispatch_contract.py`.
- Updated `plan_v7.md`.

What changed:

- Added `TicketCloseoutSettlementRequest`, `TicketCloseoutSettlementProjection`, and `TicketCloseoutSettlementResponse`.
- Added `settle_ticket_closeout_assets()` as a service-level composition point.
- Added `POST /api/v1/tickets/{ticket_id}/closeout-settlement`.
- Settlement reuses existing `propose_ticket_closeout_asset_candidates()`, `review_asset_candidates()`, `project_asset_record_to_graphiti()`, and optional relationship projection.
- Settlement is explicit and conservative: by default it only proposes candidates; callers must request `approve_candidates` and `project_graphiti`.
- Approved/rejected/merged/linked closeout candidates are no longer overwritten back to `proposed` by repeated closeout candidate proposal.
- Settlement writes a durable `ticket_closeout_settlement` Ticket report with candidate, AssetRecord, and Graphiti evidence refs.
- Repeated settlement is idempotent for reviews, projections, and settlement report creation.
- Graphiti provider blockers are returned as `blocked` projection entries instead of being hidden or treated as success.

Validation:

- `pytest tests/test_execution_dispatch_contract.py -k "closeout_settlement"` -> 1 passed.
- `python -m py_compile services/api/aiteamos_api/read/asset_candidate_service.py services/api/aiteamos_api/read/ticket_routes.py tests/test_execution_dispatch_contract.py` -> passed.
- `pytest tests/test_execution_dispatch_contract.py -k "closeout or graphiti_projection or approved_asset_record_projects or asset_record_review_relationship"` -> 6 passed.
- `pytest tests/test_aiteamos_workbench_graph.py -k "closeout"` -> 1 passed.
- `pytest tests/test_execution_dispatch_contract.py` -> 89 passed.
- `pytest tests/test_aiteamos_workbench_graph.py` -> 9 passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check -- services/api/aiteamos_api/read/asset_candidate_service.py services/api/aiteamos_api/read/ticket_routes.py tests/test_execution_dispatch_contract.py plan_v7.md` -> passed.
- `rg -n "[ \t]+$" services/api/aiteamos_api/read/asset_candidate_service.py services/api/aiteamos_api/read/ticket_routes.py tests/test_execution_dispatch_contract.py plan_v7.md` -> no matches.

Remaining gaps:

- Policy-driven closeout auto-approval is not enabled; settlement requires explicit request flags.
- Long-running worker evidence and live provider dogfood remain Track G/J/I work.
- Tickets UI now exposes explicit closeout settlement controls; Workbench-side shortcut remains optional follow-up.
- Historical closeout candidates are not automatically backfilled into settlement reports unless settlement is requested.

Next concrete module:

- Continue Track G/J/I by adding long-running worker / live-provider dogfood evidence, or continue Track G/F by defining policy-driven closeout auto-approval rules through existing governance boundaries.

Anti-Wheel Audit:

- No new Chat runtime, generic agent loop, memory database, Graphiti writer, scheduler, queue worker, or observability backend was added.
- Reused existing Ticket closeout candidate proposal, Asset candidate batch review, AssetRecord registry, Graphiti projection, relationship projection, and Ticket report/evidence contracts.
- Durable truth remains in Tickets, Ticket reports, Asset candidates/review queue, approved AssetRecords, Graphiti projection audit, Governance, runtime sessions, and provider refs.

### 2026-06-20: Track C/G Tickets UI closeout settlement controls

Status: completed for explicit closeout settlement controls in the Tickets workspace.

Goal: expose the existing governed closeout settlement path to human operators from the Ticket detail surface, while keeping settlement explicit and preserving existing Review Queue / AssetRecord / Graphiti projection contracts.

Files changed:

- Updated `apps/dashboard/src/api/tickets.ts`.
- Updated `apps/dashboard/src/pages/tickets/index.tsx`.
- Updated `apps/dashboard/src/__tests__/tickets-page.test.tsx`.
- Updated `plan_v7.md`.

What changed:

- Added dashboard API types and client for `POST /api/v1/tickets/{ticket_id}/closeout-settlement`.
- Added a `Settle Closeout` Ticket workspace action that explicitly requests candidate approval, Graphiti projection, and relationship projection.
- Added a `Closeout Settlement` result panel that shows settlement status, review counts, AssetRecord ids, Graphiti projection statuses, provider blockers, report id, and saved paths.
- Preserved `Closeout Assets` as the candidate proposal action; settlement remains a separate governed human-triggered action.
- Added frontend test coverage for settlement request flags and Graphiti provider blocker rendering.

Validation:

- `npm --prefix apps/dashboard test -- --run src/__tests__/tickets-page.test.tsx` -> 8 files / 68 tests passed.
- `npm --prefix apps/dashboard run build` -> passed; existing large chunk warning remains.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check -- apps/dashboard/src/api/tickets.ts apps/dashboard/src/pages/tickets/index.tsx apps/dashboard/src/__tests__/tickets-page.test.tsx plan_v7.md` -> passed.

Remaining gaps:

- Policy-driven closeout auto-approval is now available only when Ticket loop closeout policy explicitly enables `auto_settle_assets` and `auto_approve_candidates`; it remains off by default.
- Workbench-side settlement shortcut is not necessary for the core flow yet, but can be added later if Ticket loop policy panels need a direct action.
- Long-running worker evidence and live provider dogfood remain Track G/J/I work.

Next concrete module:

- Continue Track G/J/I with long-running worker / live-provider dogfood evidence, or continue Track I/K by expanding retrieval / stale-memory eval coverage around approved closeout Assets.

Anti-Wheel Audit:

- No new Chat runtime, generic agent loop, memory database, Graphiti writer, scheduler, queue worker, or observability backend was added.
- Reused the existing closeout settlement backend, Review Queue / AssetRecord contracts, Graphiti projection response shape, Ticket report/evidence contracts, and Tickets workspace layout.
- Durable truth remains in Tickets, Ticket reports, Asset candidates/review queue, approved AssetRecords, Graphiti projection audit, Governance, runtime sessions, and provider refs.

### 2026-06-20: Track G/F policy-driven closeout auto-settlement

Status: completed for explicit Ticket loop policy-driven closeout auto-settlement through existing Review Queue / AssetRecord / Graphiti services.

Goal: let LangGraph closeout policy turn a validated Ticket into approved/projection-ready Assets without requiring a manual dashboard settlement click, while keeping default behavior conservative and preserving AITeamOS review/provenance boundaries.

Files changed:

- Updated `services/api/aiteamos_api/read/ticket_loop_service.py`.
- Updated `services/api/aiteamos_api/agents/workbench/nodes/ticket_loop.py`.
- Updated `tests/test_aiteamos_workbench_graph.py`.
- Updated `tests/test_execution_dispatch_contract.py`.
- Updated `plan_v7.md`.

What changed:

- Added conservative closeout policy fields: `auto_settle_assets`, `auto_approve_candidates`, `project_graphiti`, and `project_relationships`; all default to `False`.
- Kept existing `auto_propose_assets` behavior as the default closeout action.
- Updated LangGraph `close_or_continue_ticket_loop` so validated Tickets choose `settle_closeout_assets` only when policy explicitly enables both `auto_settle_assets` and `auto_approve_candidates`.
- Auto-settlement reuses existing `settle_ticket_closeout_assets()`, which itself reuses closeout candidate proposal, Asset candidate review, AssetRecord registry, Graphiti projection, and Ticket report/evidence contracts.
- Graphiti projection errors from policy-driven settlement are surfaced as `provider_blockers` with reason `closeout_settlement_projection_blocked`.
- Ticket loop policy registry and route contracts now preserve and expose the new closeout settlement criteria.

Validation:

- `pytest tests/test_aiteamos_workbench_graph.py -k "auto_settles_closeout_assets or applies_closeout_decision"` -> 2 passed.
- `pytest tests/test_execution_dispatch_contract.py -k "ticket_loop_policy_registry_caps_run_and_controls_approval_policy or ticket_loop_policy_routes_read_and_update_registry"` -> 2 passed.
- `python -m py_compile services/api/aiteamos_api/read/ticket_loop_service.py services/api/aiteamos_api/agents/workbench/nodes/ticket_loop.py tests/test_aiteamos_workbench_graph.py tests/test_execution_dispatch_contract.py` -> passed.
- `pytest tests/test_aiteamos_workbench_graph.py` -> 10 passed.
- `pytest tests/test_execution_dispatch_contract.py` -> 89 passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check -- services/api/aiteamos_api/read/ticket_loop_service.py services/api/aiteamos_api/agents/workbench/nodes/ticket_loop.py tests/test_aiteamos_workbench_graph.py tests/test_execution_dispatch_contract.py plan_v7.md` -> passed.

Remaining gaps:

- Long-running worker evidence and live provider dogfood remain Track G/J/I work.
- Policy-driven settlement is intentionally off by default and still requires explicit policy criteria.
- Approved closeout solution Assets now have a local retrieval golden eval; Graphiti-backed and stale-memory eval coverage still needs expansion.

Next concrete module:

- Continue Track G/J/I with long-running worker / live-provider dogfood evidence, or continue Track E/K by adding Graphiti-backed retrieval / stale-memory eval fixtures for approved closeout solution Assets.

Anti-Wheel Audit:

- No new Chat runtime, generic agent loop, memory database, Graphiti writer, scheduler, queue worker, or observability backend was added.
- Reused existing Ticket loop policy registry, LangGraph node boundary, closeout settlement service, Asset candidate review, AssetRecord registry, Graphiti projection, and Ticket report/evidence contracts.
- Durable truth remains in Tickets, Ticket reports, Asset candidates/review queue, approved AssetRecords, Graphiti projection audit, Governance, runtime sessions, and provider refs.

### 2026-06-20: Track E/K closeout solution retrieval golden eval

Status: completed for local retrieval eval coverage of approved closeout solution Assets.

Goal: prove that closeout Assets created through the governed settlement path are not just stored, but are actually available to later Ticket-scoped context retrieval with provenance and measurable recall.

Files changed:

- Updated `services/api/aiteamos_api/read/execution_context_service.py`.
- Updated `tests/test_context_retrieval_eval.py`.
- Updated `plan_v7.md`.

What changed:

- Added a golden retrieval eval fixture that creates a validated Ticket, settles only the `solution` closeout Asset through `settle_ticket_closeout_assets()`, then asks a follow-up Graphiti auth recovery query.
- The eval proves `ExecutionContextService` includes the approved closeout solution Asset in `universal_context.asset_context.relevant_assets`.
- The eval verifies `evaluate_context_retrieval()` gets full recall for Employee, current Ticket, approved solution Asset, and validation evidence refs.
- Updated `ExecutionContextService._relevant_assets_for_ticket()` so approved `AssetRecord` items are prioritized ahead of Ticket report/evidence projections. This prevents durable approved Assets from being pushed out of the top context window by raw Ticket projections.

Validation:

- `pytest tests/test_context_retrieval_eval.py -k "closeout"` -> 1 passed.
- `pytest tests/test_context_retrieval_eval.py` -> 3 passed.
- `pytest tests/test_execution_dispatch_contract.py -k "execution_context_builds_universal_context_with_ticket_assets_and_memory_refs or asset_retrieval_evaluation_records_expected_asset_recall"` -> 2 passed.
- `python -m py_compile tests/test_context_retrieval_eval.py services/api/aiteamos_api/read/context_retrieval_eval_service.py services/api/aiteamos_api/read/execution_context_service.py` -> passed.
- `langgraph validate --config langgraph.json` -> valid, 2 graphs found.
- `git diff --check -- services/api/aiteamos_api/read/execution_context_service.py tests/test_context_retrieval_eval.py plan_v7.md` -> passed.

Remaining gaps:

- This is a local AssetRecord retrieval eval; Graphiti-backed recall evals still require configured provider state.
- Stale/conflict eval coverage should be extended specifically around closeout solution Assets.
- Long-running worker evidence and live provider dogfood remain Track G/J/I work.

Next concrete module:

- Continue Track E/K with Graphiti-backed retrieval / stale-memory evals when provider configuration is available, or continue Track G/J/I with long-running worker / live-provider dogfood evidence.

Anti-Wheel Audit:

- No new eval framework, memory database, Graphiti writer, scheduler, observability backend, or generic retrieval engine was added.
- Reused existing closeout settlement service, AssetRecord registry, `ExecutionContextService`, `evaluate_context_retrieval()`, and existing pytest-based golden eval style.
- Durable truth remains in Tickets, Ticket reports, Asset candidates/review queue, approved AssetRecords, Graphiti projection audit, Governance, runtime sessions, and provider refs.

### 2026-06-20: Track G/J multi-tick queue worker daemon evidence

Status: completed for local multi-tick daemon evidence in the default v7 artifact run.

Goal: turn the short queue worker smoke into CI-friendly evidence that the existing `TicketLoopQueueWorker` can run as a daemon across repeated ticks, process queued work, persist state, and stop cleanly, without adding a scheduler, runner, or second queue engine.

Files changed:

- Updated `scripts/ticket_loop_queue_worker_smoke.py`.
- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `plan_v7.md`.

What changed:

- Upgraded the queue worker smoke output to `aiteamos.ticket_loop_queue_worker_smoke.v2`.
- Preserved the original single-tick repeated-failure retrospective smoke.
- Added default daemon evidence with explicit controls: `--daemon-min-ticks`, `--daemon-interval-seconds`, `--daemon-timeout-seconds`, and `--skip-daemon`.
- The daemon scenario creates a Ticket, enqueues two governed loop items, starts the existing `TicketLoopQueueWorker` with `max_items=1`, waits for at least 3 ticks, verifies both queue/run records complete, verifies `processed_delta=2`, verifies `last_error` is empty, and verifies the persisted worker state path.
- The default `plan_v7_ci_artifacts.py` worker smoke command now passes explicit daemon evidence args and stores the JSON output beside the artifact manifest.

Validation:

- `python -m py_compile scripts/ticket_loop_queue_worker_smoke.py scripts/plan_v7_ci_artifacts.py` -> passed.
- `python scripts/ticket_loop_queue_worker_smoke.py --workspace-dir /tmp/aiteamos-ticket-loop-worker-smoke-v7-daemon-2 --output /tmp/aiteamos-ticket-loop-worker-smoke-v7-daemon-2.json` -> passed; emitted `daemon_status=passed`, `tick_delta=3`, and `processed_delta=2`.
- `python -m pytest tests/test_execution_dispatch_contract.py -q -k "ticket_loop_queue_worker_daemon_pumps_queue_and_records_status or ticket_loop_queue_worker_status_records_recent_policy_actions"` -> 2 passed.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-daemon-worker-smoke --fail-fast` -> passed with 9 commands, including the v2 worker smoke, retrieval evals, Workbench graph/context tests, runtime approval outcome tests, `langgraph validate`, and `git diff --check`.

Remaining gaps:

- This is deterministic local daemon evidence, not a multi-hour production worker soak.
- Real configured external runtime / Plane / Graphiti live dogfood remains required before calling v7 production-ready.
- Artifact summary can later add first-class assertions for `daemon_status`, `tick_delta`, and live-provider dogfood freshness.

Next concrete module:

- Continue Track I/J with repeated live external-runtime dogfood evidence and provider readiness, or continue Track E/K with Graphiti-backed retrieval evals when provider configuration is available.

Anti-Wheel Audit:

- No new scheduler, queue runner, queue engine, observability backend, generic agent loop, or memory writer was added.
- Reused the existing `TicketLoopQueueWorker`, queue records, run records, Ticket reports, Asset candidate policy action path, and v7 artifact wrapper.
- Provider blockers remain visible; local deterministic worker evidence is not presented as live provider success.

### 2026-06-20: Track E/A Graphiti-backed scoped context recall

Status: completed for LangGraph context-node Graphiti-backed recall with local fake-provider eval coverage.

Goal: make Graphiti recall part of the real LangGraph `retrieve_context` path, not only a later Chat runtime enrichment side effect, while keeping Graphiti as a provider projection and preserving AITeamOS `universal_context` as the durable context contract.

Files changed:

- Updated `services/api/aiteamos_api/agents/workbench/nodes/context.py`.
- Updated `services/api/aiteamos_api/read/memory_service.py`.
- Updated `tests/test_context_retrieval_eval.py`.
- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `plan_v7.md`.

What changed:

- `retrieve_context` now asynchronously calls existing `search_memory(include_graphiti=True)` before building `ExecutionContextService` context.
- Graphiti results are converted into explicit memory refs and passed through the existing `ExecutionContextService` path, so they appear in `universal_context.memory_context`, recall trace, provenance summary, and retrieval audit.
- Graphiti recall metadata is preserved in `context_bundle.graphiti_recall`, and `runtime_status.graphiti_recall_count` exposes the count to Workbench state.
- Graphiti provider blockers are surfaced only when Graphiti is explicitly enabled but not ready, so disabled optional Graphiti does not break local read-only flows.
- `search_memory()` now filters Graphiti results by requested `employee_id`, `ticket_key`, and project scope, preventing unrelated graph facts from entering a Ticket context.
- The default v7 artifact py_compile / diff-check file list now includes `nodes/context.py` and `memory_service.py`.

Validation:

- `python -m py_compile services/api/aiteamos_api/agents/workbench/nodes/context.py services/api/aiteamos_api/read/memory_service.py tests/test_context_retrieval_eval.py` -> passed.
- `python -m pytest tests/test_context_retrieval_eval.py -q -k "graphiti_scoped_asset"` -> 1 passed.
- `python -m pytest tests/test_context_retrieval_eval.py -q` -> 4 passed.
- `python -m pytest tests/test_aiteamos_workbench_graph.py -q` -> 10 passed.
- `python -m pytest tests/test_execution_dispatch_contract.py -q -k "context_records_graphiti_recall_provenance or execution_context_builds_universal_context_with_ticket_assets_and_memory_refs or asset_retrieval_evaluation_records_expected_asset_recall"` -> 3 passed.

Remaining gaps:

- This proves provider-backed behavior through a fake Graphiti class, not a real Neo4j / Graphiti deployment.
- Ranking is still mostly lexical / provider score based; a broader retrieval eval set should cover noisy Graphiti results, stale/superseded Assets, and multi-Ticket conflicts.
- Live-provider dogfood still needs configured Plane, Graphiti, external runtime, approval resume, Asset projection, and later recall evidence in one repeated run.

Next concrete module:

- Continue Track E/K by extending stale/conflict evals to Graphiti-backed results, or continue Track I/J with repeated live external-runtime dogfood evidence once provider configuration is ready.

Anti-Wheel Audit:

- No new memory database, vector store, retrieval engine, Graphiti writer, chat runtime, agent loop, scheduler, or observability backend was added.
- Reused existing `search_memory()`, Graphiti provider adapter, `ExecutionContextService`, LangGraph `retrieve_context` node, and pytest eval style.
- Graphiti remains a projection / recall provider; AITeamOS context, provenance, Tickets, Assets, and governance remain the product source of truth.

### 2026-06-20: Track E/K Graphiti stale and conflict hints

Status: completed for fake-provider Graphiti stale/conflict hint coverage in LangGraph context retrieval.

Goal: ensure Graphiti provider results that represent stale, superseded, rejected, or conflicted Assets are visible as excluded context hints instead of being silently dropped or incorrectly recalled as active memory.

Files changed:

- Updated `services/api/aiteamos_api/read/memory_service.py`.
- Updated `services/api/aiteamos_api/read/execution_context_service.py`.
- Updated `services/api/aiteamos_api/agents/workbench/nodes/context.py`.
- Updated `tests/test_context_retrieval_eval.py`.
- Updated `plan_v7.md`.

What changed:

- `MemorySearchResponse` now carries `excluded_results` alongside active `results`.
- Graphiti search normalization now classifies non-recallable statuses such as `stale`, `superseded`, `rejected`, or `conflicted` as excluded provider results with an explicit `exclusion_reason`.
- Excluded Graphiti results are still filtered by requested Employee / Ticket / project scope, so unrelated graph facts stay out of both active context and stale hints.
- LangGraph `retrieve_context` passes Graphiti excluded results into `ExecutionContextService` as `stale_memory_refs`.
- `ExecutionContextService` now merges provider-side stale refs into existing `stale_memory_hints`, dedupes them, and exposes Graphiti episode/result ids in the stale hint payload.
- The retrieval audit continues to select only active context while listing stale/conflicted Graphiti results under `excluded`.
- Graphiti search failure / missing `search()` capability now returns empty active/excluded results instead of breaking the Workbench graph.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/memory_service.py services/api/aiteamos_api/read/execution_context_service.py services/api/aiteamos_api/agents/workbench/nodes/context.py tests/test_context_retrieval_eval.py` -> passed.
- `python -m pytest tests/test_context_retrieval_eval.py -q -k "graphiti_scoped_asset"` -> 1 passed.
- `python -m pytest tests/test_context_retrieval_eval.py -q` -> 4 passed.
- `python -m pytest tests/test_aiteamos_workbench_graph.py -q` -> 10 passed after fixing the Graphiti search exception path.
- `python -m pytest tests/test_live_provider_dogfood_service.py -q -k "composes_workbench_assets_graphiti_and_recall"` -> 1 passed.
- `python -m pytest tests/test_execution_dispatch_contract.py -q -k "context_records_graphiti_recall_provenance or execution_context_builds_universal_context_with_ticket_assets_and_memory_refs or asset_retrieval_evaluation_records_expected_asset_recall"` -> 3 passed.

Remaining gaps:

- This is still fake-provider Graphiti coverage, not real Neo4j / Graphiti provider dogfood.
- Conflict semantics are status-based today; richer relationship-level conflict reasoning should later use approved Asset relationships such as `conflicts_with` / `supersedes`.
- Ranking is still provider-score / heuristic based and needs broader noisy-query evals.

Next concrete module:

- Continue Track I/J with repeated live external-runtime dogfood and real Graphiti provider evidence when configured, or continue Track J by adding artifact summary assertions for retrieval exclusion counts and dogfood freshness.

Anti-Wheel Audit:

- No new memory database, vector store, retrieval engine, Graphiti writer, agent loop, scheduler, observability backend, or stale-memory store was added.
- Reused existing `search_memory()`, Graphiti provider adapter, `ExecutionContextService`, LangGraph `retrieve_context`, and the existing `stale_memory_hints` / retrieval audit contract.
- Durable truth remains in AITeamOS Tickets, Assets, Governance, Review Queue, approved AssetRecords, and Graphiti projection refs; Graphiti remains provider-side recall evidence only.

### 2026-06-20: Track J evidence summary signals

Status: completed for first-class local artifact evidence extraction.

Goal: make the saved v7 artifact manifests report production-relevant autonomous-loop evidence, not only command pass/fail status, while still avoiding a custom observability platform or eval database.

Files changed:

- Added `scripts/context_retrieval_eval_smoke.py`.
- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `scripts/plan_v7_artifact_summary.py`.
- Updated `tests/test_plan_v7_artifact_summary.py`.
- Updated `README.md`.
- Updated `plan_v7.md`.

What changed:

- Added a thin deterministic context retrieval smoke around the real LangGraph `retrieve_context` node and existing `search_memory()` / `ExecutionContextService` path.
- The smoke emits JSON evidence for Graphiti-backed context recall: active recall count, excluded stale/conflict count, active Asset ids, stale hint Asset ids, wrong-Ticket filtering, provider blocker count, and check results.
- The default `plan_v7_ci_artifacts.py` run now includes this smoke and stores `context_retrieval_eval_smoke.json` beside the run manifest.
- `plan_v7_artifact_summary.py` now emits schema `aiteamos.plan_v7.artifact_summary.v2` and extracts `latest_evidence` / `latest_evidence_gaps`.
- Summary evidence now includes `context_retrieval`, `queue_worker_daemon`, and optional `live_provider_dogfood`.
- Missing live dogfood evidence is surfaced as `live_provider_dogfood_missing` instead of being inferred away from a passing local run.

Validation:

- `python -m py_compile scripts/context_retrieval_eval_smoke.py scripts/plan_v7_ci_artifacts.py scripts/plan_v7_artifact_summary.py tests/test_plan_v7_artifact_summary.py` -> passed.
- `python -m pytest tests/test_plan_v7_artifact_summary.py -q` -> 5 passed.
- `python scripts/context_retrieval_eval_smoke.py --workspace-dir /tmp/aiteamos-context-retrieval-eval-smoke-v7 --output /tmp/aiteamos-context-retrieval-eval-smoke-v7.json` -> passed; emitted `graphiti_result_count=1`, `graphiti_excluded_result_count=2`, and `wrong_ticket_filtered=true`.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-evidence-summary-smoke --fail-fast` -> passed with 10 commands, including context retrieval smoke, context eval tests, Workbench graph/context tests, runtime approval outcomes, Ticket loop queue reliability, worker daemon smoke, `langgraph validate`, and `git diff --check`.
- `python scripts/plan_v7_artifact_summary.py --limit 1` -> latest run `local-v7-evidence-summary-smoke`, status `passed`, latest context evidence `graphiti_result_count=1` / `graphiti_excluded_result_count=2`, latest queue daemon evidence `tick_delta=3` / `processed_delta=2`, and latest gap `live_provider_dogfood_missing`.

Remaining gaps:

- The context retrieval smoke is fake-provider Graphiti evidence; real Neo4j / Graphiti provider dogfood is still required.
- Live provider dogfood freshness is now summary-ready, but no current run has live external runtime / Plane / Graphiti dogfood evidence.
- Summary evidence is local artifact evidence, not a replacement for LangSmith, LangGraph Studio, or provider-native traces.

Next concrete module:

- Continue Track I/J with repeated live external-runtime dogfood and real Graphiti provider evidence when provider configuration is available, or continue Track H/J by adding approved Asset relationship / stale cleanup evidence to the same artifact summary style.

Anti-Wheel Audit:

- No generic observability backend, eval database, agent loop, retriever, streaming protocol, memory store, scheduler, or Chat UI was added.
- The retrieval smoke calls the existing LangGraph context node and provider adapter; the summary only reads existing JSON artifacts.
- Durable truth remains in Tickets, Employees, Assets, Governance, Review Queue, AssetRecords, provider refs, and Graphiti projection/recall.

### 2026-06-20: Track H/J Asset provenance evidence smoke

Status: completed for local approved Asset relationship and stale-memory cleanup evidence.

Goal: strengthen the v7 artifact evidence around Assets as durable organizational memory by proving approved AssetRecord relationship projection, idempotent Graphiti relationship replay, and stale memory filtering through existing service boundaries.

Files changed:

- Added `scripts/asset_provenance_eval_smoke.py`.
- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `scripts/plan_v7_artifact_summary.py`.
- Updated `tests/test_plan_v7_artifact_summary.py`.
- Updated `README.md`.
- Updated `plan_v7.md`.

What changed:

- Added a thin deterministic smoke that creates two approved `AssetRecord` items and projects a `supersedes` relationship through the existing `project_asset_record_relationships_to_graphiti()` service.
- The smoke verifies first projection status `ingested`, repeat projection status `skipped`, Graphiti relationship search result count, and the persisted `graphiti_relationships` provenance on the source AssetRecord.
- The same smoke creates and approves a memory candidate, proves it is recalled before stale review, marks it `stale` through existing `review_memory_candidate()`, then proves it is absent from active recall and present in excluded Graphiti results.
- The default `plan_v7_ci_artifacts.py` run now stores `asset_provenance_eval_smoke.json` next to the manifest.
- `plan_v7_artifact_summary.py` now exposes an `asset_provenance` evidence block with relationship projection, replay, and stale cleanup counters.

Validation:

- `python -m py_compile scripts/asset_provenance_eval_smoke.py scripts/context_retrieval_eval_smoke.py scripts/plan_v7_ci_artifacts.py scripts/plan_v7_artifact_summary.py tests/test_plan_v7_artifact_summary.py` -> passed.
- `python -m pytest tests/test_plan_v7_artifact_summary.py -q` -> 5 passed.
- `python scripts/asset_provenance_eval_smoke.py --workspace-dir /tmp/aiteamos-asset-provenance-eval-smoke-v7-2 --output /tmp/aiteamos-asset-provenance-eval-smoke-v7-2.json` -> passed; emitted `relationship_ingested_count=1`, `relationship_skipped_count=1`, and `stale_active_filtered=true`.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-asset-provenance-smoke --fail-fast` -> passed with 11 commands, including context retrieval smoke, Asset provenance smoke, context eval tests, Workbench graph/context tests, runtime approval outcomes, Ticket loop queue reliability, worker daemon smoke, `langgraph validate`, and `git diff --check`.
- `python scripts/plan_v7_artifact_summary.py --limit 1 --fail-on-failed` -> latest run `local-v7-asset-provenance-smoke`, status `passed`, latest Asset provenance evidence `relationship_projection_status=ingested`, `relationship_repeated_status=skipped`, `stale_after_active_count=0`, `stale_after_excluded_count=1`, and `stale_active_filtered=true`.

Remaining gaps:

- This is fake-provider Graphiti evidence; real Neo4j / Graphiti provider dogfood remains required.
- Relationship-level conflict reasoning is still mostly projection/provenance evidence; future work should use approved `conflicts_with` / `supersedes` relationships in context ranking and conflict hints.
- Live provider dogfood remains the latest explicit summary gap.

Next concrete module:

- Continue Track I/J with repeated live external-runtime dogfood and real Graphiti provider evidence when configured, or continue Track H/E by making approved Asset relationships influence retrieval conflict hints and ranking.

Anti-Wheel Audit:

- No generic memory database, Graphiti writer, eval platform, scheduler, agent loop, Chat runtime, or observability backend was added.
- The smoke reuses `AssetRecord`, `project_asset_record_relationships_to_graphiti()`, `create_memory_candidate()`, `approve_memory_candidate()`, `review_memory_candidate()`, and `search_memory()`.
- Durable truth remains in AITeamOS Assets / Review / AssetRecord / provenance plus Graphiti projection refs; Graphiti remains only provider-side projection and recall evidence.

### 2026-06-20: Track H/E Asset relationship context hints

Status: completed for approved AssetRecord `supersedes` / `conflicts_with` relationship hints in `UniversalContext`.

Goal: make approved Asset relationships operationally affect context selection, so stale or conflicting Assets do not remain active relevant Assets once a newer approved AssetRecord relationship says otherwise.

Files changed:

- Updated `services/api/aiteamos_api/read/execution_context_service.py`.
- Updated `tests/test_context_retrieval_eval.py`.
- Updated `plan_v7.md`.

What changed:

- `ExecutionContextService` now derives `asset_relationship_hints` from approved Ticket-scoped AssetRecords.
- Relationships of type `supersedes` and `conflicts_with` mark the target Asset as `superseded` or `conflicted`.
- Superseded/conflicted target Assets are removed from active `asset_context.relevant_assets`.
- The target Assets are preserved as `asset_context.relationship_hints` with source Asset id, target Asset id, relationship type, status, exclusion reason, provenance, and confidence.
- Retrieval audit now lists relationship-excluded Assets under `excluded`, so LangGraph context consumers can explain why an Asset was not active context.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/execution_context_service.py tests/test_context_retrieval_eval.py` -> passed.
- `python -m pytest tests/test_context_retrieval_eval.py -q -k "asset_relationships or golden_query or graphiti_scoped_asset"` -> 3 passed.
- `python -m pytest tests/test_context_retrieval_eval.py -q` -> 5 passed.
- `python -m pytest tests/test_aiteamos_workbench_graph.py -q` -> 10 passed.
- `python -m pytest tests/test_execution_dispatch_contract.py -q -k "execution_context_builds_universal_context_with_ticket_assets_and_memory_refs or asset_retrieval_evaluation_records_expected_asset_recall"` -> 2 passed.

Remaining gaps:

- Relationship hints are deterministic and status-based; ranking still does not use a learned or provider-backed reranker.
- Real Graphiti provider dogfood should prove the same relationship facts with actual Neo4j / Graphiti state.
- Future UI work can surface `asset_context.relationship_hints` in the Workbench Assets / Provenance panels.

Next concrete module:

- Continue Track I/J with repeated live external-runtime dogfood and real Graphiti provider evidence when configured, or continue Track C/H by surfacing `asset_context.relationship_hints` in Chat Workbench Assets / Provenance panels.

Anti-Wheel Audit:

- No new memory store, relationship database, retriever, reranker, Graphiti writer, agent loop, Chat runtime, or observability backend was added.
- The change reuses approved `AssetRecord.relationships` as durable truth and only changes `ExecutionContextService` context assembly.
- Graphiti remains a projection / recall provider; AITeamOS Assets and provenance remain the source of truth.

### 2026-06-20: Track C/H Asset relationship hints in Chat Workbench

Status: completed for Workbench-side visibility of approved Asset relationship exclusions.

Goal: make the Chat Workbench show why approved Assets were excluded from active context when `UniversalContext.asset_context.relationship_hints` marks them as superseded or conflicted.

Files changed:

- Updated `apps/dashboard/src/pages/chat/panels/ScopedContextPanel.tsx`.
- Updated `apps/dashboard/src/__tests__/chat-page.test.tsx`.
- Updated `plan_v7.md`.

What changed:

- `ScopedContextPanel` now reads both legacy flat `universal_context` fields and the current nested `universal_context.summary` shape.
- The panel now renders `asset_context.relationship_hints` as a compact list with target Asset id, status, source Asset id, relationship type, confidence, and exclusion reason.
- Ticket backend status now also supports the nested `backend_context.ticket_backend.status` shape.
- The ChatPage fixture now includes `supersedes` and `conflicts_with` relationship hints, proving the Workbench surfaces stale/conflicting Asset exclusions.

Validation:

- `npx vitest run --environment jsdom src/__tests__/chat-page.test.tsx` from `apps/dashboard` -> 6 passed.
- `npm run build` from `apps/dashboard` -> passed (`tsc && vite build`); Vite still reports the existing large bundle warning.

Remaining gaps:

- The relationship hint UI is read-only; it does not yet deep-link to the Asset detail page or relationship review history.
- Chat page code splitting remains a future maintainability item, consistent with the build chunk warning.
- Real provider dogfood is still required to prove the same hints with live Plane / Graphiti / external runtime evidence.

Next concrete module:

- Continue Track C by code-splitting the Chat Workbench details panels/runtime adapters, or continue Track I/J with live provider dogfood when credentials and services are available.

Anti-Wheel Audit:

- No Chat runtime, generic Chat UI, agent loop, memory store, relationship service, or custom observability layer was added.
- The UI only presents existing LangGraph/AITeamOS `UniversalContext` state through the existing `ScopedContextPanel`.
- Durable truth remains in approved AITeamOS Assets / AssetRecord relationships / provenance; Chat remains a thin Workbench surface.

### 2026-06-20: Track C Thread workspace tabs panel extraction

Status: completed for top Chat thread chrome extraction.

Goal: continue shrinking `ChatPage` into a composition shell by moving the open-thread tab strip, history toggle, new-thread affordance, tab close affordance, and details toggle into a dedicated Workbench panel.

Files changed:

- Added `apps/dashboard/src/pages/chat/panels/ThreadWorkspaceTabsPanel.tsx`.
- Updated `apps/dashboard/src/pages/chat/index.tsx`.
- Updated `plan_v7.md`.

What changed:

- Added `ThreadWorkspaceTabsPanel` as a pure UI/callback component over existing thread state.
- Removed top-thread tab JSX, lucide icon imports, and button import from `ChatPage`.
- `ChatPage` still owns thread loading, active/open thread ids, creation, switching, closing, deletion behavior, and LangGraph runtime wiring.

Validation:

- `npx vitest run --environment jsdom src/__tests__/chat-page.test.tsx` from `apps/dashboard` -> 6 passed.
- `npm run build` from `apps/dashboard` -> passed (`tsc && vite build`); Vite still reports the existing large bundle warning.

Remaining gaps:

- Chat still owns main thread/API state and runtime adapter wiring.
- The dashboard bundle is still a single large route chunk; future code splitting remains frontend hardening work.
- This extraction does not add persisted thread state or new runtime behavior by design.

Next concrete module:

- Continue Track C by extracting remaining thread/API state into a hook or introducing route-level/panel-level lazy loading, or continue Track I/J with live provider dogfood when services are configured.

Anti-Wheel Audit:

- No Chat runtime, thread store, generic streaming protocol, checkpoint UI, memory store, RuntimeExecutor dispatcher, or agent loop was added.
- The panel reuses existing Chat state/callbacks and assistant-ui/LangChain runtime remains untouched.
- Durable product truth remains in AITeamOS Tickets / Employees / Assets / Governance; this is presentation-only decomposition.

### 2026-06-20: Track C Chat thread workspace hook extraction

Status: completed for local thread/API state extraction.

Goal: continue moving `ChatPage` toward a thin LangGraph-native Workbench shell by extracting thread list loading, active/open thread ids, create/switch/close/delete actions, thread history query, and deleting/loading state into a focused hook.

Files changed:

- Added `apps/dashboard/src/pages/chat/runtime/useChatThreadWorkspace.ts`.
- Updated `apps/dashboard/src/pages/chat/index.tsx`.
- Updated `plan_v7.md`.

What changed:

- Added `useChatThreadWorkspace()` to own existing Chat thread API calls and local thread workspace state.
- `ChatPage` now delegates `listChatThreads`, `createChatThread`, `activateChatThread`, and `deleteChatThread` behavior to the hook.
- The hook preserves existing page behavior: active thread fallback, open thread ids, new thread creation, active thread switch, tab close fallback, deletion fallback, and run/pending approval clearing callbacks.
- `ChatPage` dropped direct thread API imports and shrank from 546 lines to 455 lines in the current worktree.

Validation:

- `npx vitest run --environment jsdom src/__tests__/chat-page.test.tsx` from `apps/dashboard` -> 6 passed.
- `npm run build` from `apps/dashboard` -> passed (`tsc && vite build`); Vite still reports the existing large bundle warning.

Remaining gaps:

- This is still local React state, not route-level code splitting.
- Chat still owns Employee/API loading, AI Engine controls state, LangGraph runtime bridge wiring, and Workbench panel composition.
- The dashboard bundle is still large; route-level or panel-level lazy loading remains future frontend hardening work.

Next concrete module:

- Continue Track C by extracting initial Chat surface loading into a hook or adding route-level lazy loading, or continue Track I/J with live provider dogfood when services are configured.

Anti-Wheel Audit:

- No Chat runtime, thread store, generic streaming protocol, checkpoint UI, observability backend, memory database, RuntimeExecutor dispatcher, or agent loop was added.
- The hook only wraps existing AITeamOS Chat thread APIs and existing local page state; LangChain / assistant-ui / LangGraph runtime ownership remains untouched.
- Durable product truth remains in AITeamOS Tickets / Employees / Assets / Governance; this is maintainability-only decomposition.

### 2026-06-20: Track C Dashboard route-level code splitting

Status: completed for route-level lazy loading and vendor chunk separation.

Goal: close the repeated dashboard large-bundle warning by using mature React / Vite / Rollup code splitting instead of building custom routing, custom Chat UI, or custom runtime loading logic.

Files changed:

- Updated `apps/dashboard/src/state/App.tsx`.
- Updated `apps/dashboard/vite.config.ts`.
- Added `apps/dashboard/src/__tests__/app-shell.test.tsx`.
- Updated `plan_v7.md`.

What changed:

- `App.tsx` now loads page modules with `React.lazy()` and `Suspense` instead of statically importing every route page into the shell.
- The App shell keeps the existing hash routing, navigation, and `RouteState` model.
- Added Vite/Rollup `manualChunks()` boundaries for mature vendor libraries: assistant-ui, LangChain/LangGraph SDK packages, Radix, lucide icons, and react-resizable-panels.
- Added a focused App shell test that mocks route pages and verifies lazy route loading preserves nested Ticket route props.

Validation:

- `npx vitest run --environment jsdom src/__tests__/app-shell.test.tsx src/__tests__/chat-page.test.tsx` from `apps/dashboard` -> 8 passed.
- `npm run build` from `apps/dashboard` -> passed (`tsc && vite build`).
- Build output no longer reports the previous `Some chunks are larger than 500 kB` warning.
- Largest emitted JS chunks in the verified build: `vendor-CoHfteHC.js` 353.22 kB, `vendor-assistant-ui-2z2Xb-1R.js` 256.54 kB, `vendor-langchain-7i0NDO68.js` 230.25 kB.

Remaining gaps:

- Route-level splitting is complete, but Chat still owns Employee/API loading, AI Engine controls state, LangGraph bridge wiring, and Workbench panel composition.
- This does not replace real runtime/provider dogfood or Agent Server production smoke.
- Future frontend hardening can split particularly large individual pages or add route prefetching if measured UX requires it.

Next concrete module:

- Continue Track C by extracting initial Chat surface loading into a hook, or continue Track B/I/J with Agent Server and live provider dogfood when services are available.

Anti-Wheel Audit:

- No new router, Chat runtime, streaming protocol, checkpoint UI, state store, observability backend, memory database, RuntimeExecutor dispatcher, or agent loop was added.
- The slice reuses React `lazy` / `Suspense` and Vite/Rollup `manualChunks`, keeping assistant-ui / LangChain / LangGraph as external mature runtime libraries.
- Durable product truth remains in AITeamOS Tickets / Employees / Assets / Governance; this is build and maintainability hardening only.

### 2026-06-20: Track E/F Employee work-history context projection

Status: completed for compact Employee work-history projection into LangGraph-facing Universal Context.

Goal: make each autonomous agent step automatically receive the selected Employee's recent Ticket/runtime/Asset/quality-feedback work facts without building a second Employee memory system or stuffing full dashboard ledgers into prompts.

Files changed:

- Updated `services/api/aiteamos_api/read/execution_context_service.py`.
- Updated `services/api/aiteamos_api/read/universal_agent_tools.py`.
- Updated `tests/test_execution_dispatch_contract.py`.
- Updated `apps/dashboard/src/pages/chat/panels/ScopedContextPanel.tsx`.
- Updated `apps/dashboard/src/__tests__/chat-page.test.tsx`.
- Updated `plan_v7.md`.

What changed:

- `ExecutionContextService` now reuses existing `employee_work_ledger()` to build `universal_context.employee_context.work_history`.
- The work-history projection includes compact counts plus bounded refs for current/historical Tickets, reports, blocked records, handoffs, Asset candidates, approved Assets, Asset reviews, runtime runs, and quality feedback.
- `selected_employee.work_history_summary` gives LangGraph nodes a short Employee-history summary next to identity, skills, permissions, handoff policy, and current load.
- `provenance_summary` and `retrieval_audit.selected` now include `employee_work_history`, keeping context selection explainable.
- `universal_agent.get_employee_context` returns the same `work_history` block so LangGraph read-only tools do not perform a second lookup or drift from the scoped context.
- Chat Workbench `ScopedContextPanel` now shows a compact Work History section from `universal_context.employee_context.work_history.summary`.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/execution_context_service.py services/api/aiteamos_api/read/universal_agent_tools.py` -> passed.
- `python -m pytest tests/test_execution_dispatch_contract.py -q -k "universal_context or employee_work_history or tool_registry_returns_employee_work_history"` -> 3 passed, 87 deselected.
- `npx vitest run --environment jsdom src/__tests__/chat-page.test.tsx` from `apps/dashboard` -> 6 passed.
- `npm run build` from `apps/dashboard` -> passed (`tsc && vite build`), with the existing split vendor chunks and no large-chunk warning.

Remaining gaps:

- The projection is read-only context; it does not yet drive automatic handoff scoring from historical success/failure patterns.
- Work-history refs are compact and bounded, but there is not yet a retrieval eval that scores whether the most useful historical Ticket/Asset was selected for a task.
- Live provider dogfood is still required to prove these facts improve real LangGraph runs with configured external runtimes.

Next concrete module:

- Continue Track E/F by letting Employee handoff selection consume compact work-history signals, or continue Track I/J by adding retrieval eval coverage for work-history selection quality before live provider dogfood.

Anti-Wheel Audit:

- No Employee memory database, custom agent loop, new work-history store, generic tool dispatcher, or duplicate dashboard ledger was created.
- The slice reuses the existing Ticket-backed `employee_work_ledger()`, existing Universal Context contract, existing Universal Agent tool registry, and existing Chat Workbench panel.
- Durable product truth remains in AITeamOS Tickets / Employees / Assets / Governance; LangGraph receives a governed projection instead of owning product state.

### 2026-06-20: Track E/F Work-history-aware Employee handoff scoring

Status: completed for deterministic handoff scoring that can consume Employee work-history signals.

Goal: make Employee/sub-agent handoff selection prefer Employees with relevant prior governed work while still respecting fixed identity, capability tags, `handoff_policy`, and `current_load`.

Files changed:

- Updated `services/api/aiteamos_api/read/employee_handoff_service.py`.
- Updated `tests/test_execution_dispatch_contract.py`.
- Updated `plan_v7.md`.

What changed:

- `choose_employee_for_goal()` now adds a bounded `work_history_score` to the existing deterministic lane score.
- Work-history scoring first uses `profile.work_history_summary` or `profile.work_history.summary` when already provided by the caller.
- If the profile does not include a summary, the service safely reuses the existing Ticket-backed `employee_work_ledger()` and converts it into a compact summary.
- RD handoff now favors prior reports, runtime runs, and approved Assets, with small penalties for blocked/failed recent runtime history.
- PV handoff now favors validation and Asset-review history.
- Memory-curator handoff now favors Asset candidate, approved Asset, and review history.
- The returned handoff `policy` includes `work_history_score` and a compact `work_history_summary` so LangGraph traces can explain why an Employee was selected.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/employee_handoff_service.py` -> passed.
- `python -m pytest tests/test_execution_dispatch_contract.py -q -k "choose_employee_for_goal"` -> 4 passed, 88 deselected.
- `python -m pytest tests/test_execution_dispatch_contract.py -q` -> 92 passed.

Remaining gaps:

- Handoff work-history scoring is deterministic and compact, but not yet eval-tuned against a corpus of historical Tickets.
- The service still uses simple lane heuristics; LangGraph should keep owning the broader agent loop and handoff execution nodes.
- Live provider dogfood should verify that handoff decisions improve real Ticket loop outcomes rather than only unit behavior.

Next concrete module:

- Continue Track I/J by adding retrieval/handoff eval smoke coverage that checks whether relevant historical Ticket/Asset facts are selected for a task.

Anti-Wheel Audit:

- No sub-agent framework, custom router, Employee memory DB, or learned ranking system was added.
- The slice reuses the existing deterministic handoff service and Ticket-backed `employee_work_ledger()`.
- Durable product truth remains in AITeamOS Tickets / Employees / Assets / Governance; handoff scoring consumes governed work facts rather than creating new state.

### 2026-06-20: Track I/J Work-history retrieval eval refs

Status: completed for golden-query evaluation visibility into Employee work-history context.

Goal: make retrieval evals able to prove that Employee work-history facts were selected into LangGraph-facing context, instead of only checking Tickets, Assets, Memory, and prior evidence.

Files changed:

- Updated `services/api/aiteamos_api/read/context_retrieval_eval_service.py`.
- Updated `tests/test_context_retrieval_eval.py`.
- Updated `plan_v7.md`.

What changed:

- `evaluate_context_retrieval()` now extracts `employee_work_history` refs from `universal_context.employee_context.work_history`.
- The eval ref extractor now recognizes bounded work-history refs for current/historical work Tickets, recent work reports, blocked reports, handoffs, Asset candidates, approved Assets, Asset reviews, runtime runs, and quality feedback.
- Added a golden-query test proving that an Alex Ticket/report appears as `employee_work_history`, `work_ticket`, and `work_report` retrieval refs.
- The existing retrieval audit remains the explainability source; the eval service only reads the Universal Context output.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/context_retrieval_eval_service.py` -> passed.
- `python -m pytest tests/test_context_retrieval_eval.py -q` -> 6 passed.

Remaining gaps:

- Work-history evals now measure recall of selected refs, but they do not yet score ranking quality or task-outcome improvement.
- The smoke script still focuses on Graphiti active/stale/conflict behavior; it could emit work-history eval evidence in a future slice.

Next concrete module:

- Extend `scripts/context_retrieval_eval_smoke.py` or Plan v7 artifact summary to include work-history retrieval evidence, then continue live provider dogfood when external provider configuration is available.

Anti-Wheel Audit:

- No retriever, vector index, ranking engine, memory database, or agent loop was added.
- The slice reuses the existing golden-query eval helper and Universal Context shape.
- Durable product truth remains in AITeamOS Tickets / Employees / Assets / Governance; evals only check whether governed projections were present.

### 2026-06-20: Track I/J Work-history retrieval smoke and artifact evidence

Status: completed for smoke/artifact visibility into Employee work-history retrieval evidence.

Goal: make the default Plan v7 verification artifact prove that work-history context was selected and measurable, not only the focused pytest suite.

Files changed:

- Updated `scripts/context_retrieval_eval_smoke.py`.
- Updated `scripts/plan_v7_artifact_summary.py`.
- Updated `tests/test_plan_v7_artifact_summary.py`.
- Updated `README.md`.
- Updated `plan_v7.md`.

What changed:

- The context retrieval smoke now creates a governed Alex Ticket report before running the real LangGraph `retrieve_context` node.
- The smoke reuses existing `evaluate_context_retrieval()` to verify `employee_work_history`, `work_ticket`, and `work_report` refs.
- The smoke payload summary now includes work-history report id, report count, current Ticket count, eval recall, precision-like score, matched refs, missing refs, and retrieved work-history refs.
- `plan_v7_artifact_summary.py` now extracts those work-history fields into first-class `latest_evidence.context_retrieval`.
- `README.md` now documents Employee work-history retrieval refs as first-class Plan v7 artifact evidence.

Validation:

- `python -m py_compile scripts/context_retrieval_eval_smoke.py scripts/plan_v7_artifact_summary.py` -> passed.
- `python scripts/context_retrieval_eval_smoke.py --workspace-dir /tmp/aiteamos-context-smoke-work-history --output /tmp/aiteamos-context-smoke-work-history/context_retrieval_eval_smoke.json` -> passed, including `work_history.eval_recall=1.0`.
- `python -m pytest tests/test_plan_v7_artifact_summary.py -q` -> 5 passed.
- `python -m pytest tests/test_context_retrieval_eval.py tests/test_plan_v7_artifact_summary.py -q` -> 11 passed.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-work-history-evidence-smoke --fail-fast` -> passed with 11 commands, including context retrieval smoke, Asset provenance smoke, context eval tests, Workbench graph/context tests, runtime approval outcomes, Ticket loop queue reliability, queue worker smoke, `langgraph validate`, and `git diff --check`.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 1 --fail-on-failed` -> passed and extracted `work_history_eval_recall=1.0`, `work_history_missing_ref_count=0`, `work_history_report_count=1`.
- `python scripts/live_provider_dogfood.py --readiness --executor-id codex_cli --workspace-dir /home/shiqiangli/projects/AITeamOS` -> blocked by explicit mutation gate; Plane status `ready`, Graphiti status `ready`, `codex_cli` status `ready`, but `AITEAMOS_LIVE_PROVIDER_DOGFOOD=1` was not set.

Remaining gaps:

- Smoke coverage is deterministic fake-provider evidence; real Neo4j / Graphiti provider dogfood and live external runtime runs remain required before v7 can be called production-ready.
- Work-history evidence now proves selected refs and measurable recall, but not ranking quality or long-term outcome improvement.
- Live provider dogfood is environment-gated and remains unexecuted until the mutation gate is explicitly opened.

Next concrete module:

- Continue Track B/I/J by running or improving Agent Server/live provider dogfood evidence where external provider configuration is available, or harden runtime replay/eval summary if live provider remains unavailable.

Anti-Wheel Audit:

- No retriever, memory DB, artifact runner, generic observability backend, custom agent loop, or duplicate Employee history store was added.
- The slice reuses the existing LangGraph context node, existing `evaluate_context_retrieval()` helper, existing Plan v7 artifact manifest format, and existing Ticket-backed work ledger.
- Durable product truth remains in AITeamOS Tickets / Employees / Assets / Governance; smoke evidence only checks governed projections.

### 2026-06-20: Track J Runtime replay coverage summary

Status: completed for machine-checkable runtime replay coverage and dashboard visibility.

Goal: make Runtime Replay able to state whether a session has enough evidence to reconstruct the governed loop across Ticket, Employee, Runtime, Evidence, Trace, State, Checkpoint, and optional Approval/Asset/Memory references.

Files changed:

- Updated `services/api/aiteamos_api/read/execution_replay_service.py`.
- Updated `services/api/aiteamos_api/read/runtime_executor_routes.py`.
- Updated `apps/dashboard/src/api/runtimeExecutors.ts`.
- Updated `apps/dashboard/src/components/runtimeReplay.tsx`.
- Updated `apps/dashboard/src/__tests__/runtime-page.test.tsx`.
- Updated `tests/test_runtime_executor_routes.py`.
- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `plan_v7.md`.

What changed:

- `ExecutionReplayService.session_replay()` now returns `coverage_summary` with schema `execution_replay_coverage.v1`.
- The coverage summary reports required chain completeness, gaps, counts, and bounded refs for Tickets, Employees, approvals, Assets, Memory, evidence, checkpoints, state, trace, and requests.
- Approval coverage is required only when the session actually references approvals; Asset/Memory coverage is surfaced but not required for every runtime session.
- Runtime Replay UI now shows a compact Replay Coverage panel with chain completeness, core coverage states, counts, Asset/Memory presence, and any gaps.
- The default Plan v7 artifact runner now includes `pytest_runtime_replay_coverage`, so replay coverage cannot silently regress outside the UI.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/execution_replay_service.py services/api/aiteamos_api/read/runtime_executor_routes.py` -> passed.
- `python -m pytest tests/test_runtime_executor_routes.py -q -k "runtime_execution_sessions_list_checkpoint_and_replay_refs"` -> 1 passed, 15 deselected.
- `python -m pytest tests/test_runtime_executor_routes.py -q` -> 16 passed.
- `npx vitest run --environment jsdom src/__tests__/runtime-page.test.tsx` from `apps/dashboard` -> 3 passed.
- `npm run build` from `apps/dashboard` -> passed (`tsc && vite build`).
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-runtime-replay-coverage --fail-fast` -> passed with 12 commands, including the new `pytest_runtime_replay_coverage`, context retrieval smoke, Asset provenance smoke, Workbench graph/context tests, Ticket loop queue worker smoke, `langgraph validate`, and `git diff --check`.

Remaining gaps:

- Coverage summary is deterministic replay evidence, not a full visual graph trace IDE.
- Live provider dogfood remains environment-gated and still needs an explicit mutation gate before production readiness can be claimed.
- Replay coverage is now checked for representative runtime sessions; broader live long-running executor replay still needs real provider runs.

Next concrete module:

- Continue Track J/I by exposing replay coverage in artifact summary or by running live provider dogfood after explicitly opening the mutation gate.

Anti-Wheel Audit:

- No observability database, trace IDE, custom checkpoint UI, generic agent loop, or streaming runtime was added.
- The slice reuses existing execution sessions, artifacts, approvals, state snapshots, native LangGraph checkpoint history, timeline, and dashboard Runtime Replay surface.
- Durable product truth remains in AITeamOS Tickets / Employees / Assets / Governance; coverage is a derived replay view only.

### 2026-06-20: Track J Runtime replay coverage artifact evidence

Status: completed for first-class Runtime Replay coverage evidence in the default Plan v7 artifact suite.

Goal: make replay coverage auditable from saved CI/local artifacts instead of relying only on pytest stdout or the dashboard view.

Files changed:

- Added `scripts/runtime_replay_eval_smoke.py`.
- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `scripts/plan_v7_artifact_summary.py`.
- Updated `tests/test_plan_v7_artifact_summary.py`.
- Updated `README.md`.
- Updated `plan_v7.md`.

What changed:

- Added a deterministic Runtime Replay smoke that creates a local Ticket, writes a trace with sensitive fields, ingests an `ExecutionResult` through `ExecutionResultIngestionService`, then reads `ExecutionReplayService.session_replay()`.
- The smoke verifies `execution_replay_coverage.v1`, `required_chain_complete=true`, no required gaps, Ticket / Employee / Runtime / Evidence / Trace / State / Checkpoint / Asset-Memory coverage, refs, counts, and trace/artifact redaction.
- The default `plan_v7_ci_artifacts.py` run now stores `runtime_replay_eval_smoke.json` beside context retrieval, Asset provenance, and queue worker evidence.
- `plan_v7_artifact_summary.py` now exposes `latest_evidence.runtime_replay` with coverage booleans, refs, counts, redaction flags, and gap count.
- README now lists Runtime Replay coverage as first-class Plan v7 artifact evidence.

Validation:

- `python -m py_compile scripts/runtime_replay_eval_smoke.py scripts/plan_v7_ci_artifacts.py scripts/plan_v7_artifact_summary.py tests/test_plan_v7_artifact_summary.py` -> passed.
- `python scripts/runtime_replay_eval_smoke.py --workspace-dir /tmp/aiteamos-runtime-replay-smoke-v7 --output /tmp/aiteamos-runtime-replay-smoke-v7/runtime_replay_eval_smoke.json` -> passed with `required_chain_complete=true`, `gaps=[]`, `trace_redacted=true`, and `artifact_secret_redacted=true`.
- `python -m pytest tests/test_plan_v7_artifact_summary.py -q` -> 5 passed.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-runtime-replay-artifact-evidence --fail-fast` -> passed with 13 commands, including Runtime Replay smoke, replay coverage pytest, context retrieval smoke, Asset provenance smoke, queue worker smoke, `langgraph validate`, and `git diff --check`.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 1 --fail-on-failed` -> passed and extracted `latest_evidence.runtime_replay.required_chain_complete=true`, `gap_count=0`, `timeline_event_count=11`, `trace_event_count=1`, and latest gap `live_provider_dogfood_missing`.

Remaining gaps:

- Runtime Replay artifact evidence is still deterministic local evidence, not repeated live provider dogfood.
- Real external runtime replay needs configured provider runs with Plane / Graphiti / external executor evidence.
- Live provider dogfood remains the only latest artifact summary gap and still requires the explicit mutation gate.

Next concrete module:

- Continue Track I/J by running live provider dogfood after explicitly opening the mutation gate, or harden provider-backed replay/eval freshness once real external runtime runs are available.

Anti-Wheel Audit:

- No observability database, trace pipeline, custom agent loop, checkpoint UI, or second artifact runner was added.
- The smoke reuses `ExecutionResultIngestionService`, `ExecutionReplayService`, existing local Ticket backend, and the existing Plan v7 artifact manifest/summary format.
- Durable product truth remains AITeamOS Tickets / Employees / Assets / Governance; this slice only makes existing replay evidence auditable.

### 2026-06-20: Track B/J Agent Server matrix artifact evidence

Status: completed for first-class Agent Server production-compatibility evidence in Plan v7 artifact summary.

Goal: make Agent Server compatibility visible as structured evidence, not only command pass/fail status, while still reusing the existing Agent Server smoke runner.

Files changed:

- Updated `scripts/plan_v7_artifact_summary.py`.
- Updated `tests/test_plan_v7_artifact_summary.py`.
- Updated `README.md`.
- Updated `plan_v7.md`.

What changed:

- `plan_v7_artifact_summary.py` now extracts `latest_evidence.agent_server` from the existing `agent-server-matrix/*.json` smoke outputs.
- The summary now reports case count, passed/failed counts, per-case compact facts, and matrix coverage for read-only, answer-only, provider-blocker visibility, approval interrupt, approval resume, evidence-requested review, rejected review, and changes-requested review.
- Missing Agent Server matrix evidence now appears as `agent_server_matrix_smoke_missing`, so a green local artifact run cannot hide the absence of production-compatible Agent Server evidence.
- Duplicate provider blocker reasons and repeated Ticket timeline statuses are deduped in summary output to keep the operations view compact.
- README now documents Agent Server matrix coverage as first-class Plan v7 artifact evidence.

Validation:

- `python -m py_compile scripts/plan_v7_artifact_summary.py tests/test_plan_v7_artifact_summary.py` -> passed.
- `python -m pytest tests/test_plan_v7_artifact_summary.py -q` -> 5 passed.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 1 --fail-on-failed` before running matrix -> passed and correctly surfaced `agent_server_matrix_smoke_missing` plus `live_provider_dogfood_missing`.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-agent-server-matrix-summary-evidence --include-agent-server-matrix-smoke --fail-fast` -> passed with 20 commands, including the seven Agent Server matrix smokes.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 1 --fail-on-failed` after running matrix -> passed and extracted `agent_server.coverage_complete=true`, `case_count=7`, `passed_case_count=7`, all Agent Server coverage flags true, and latest gap only `live_provider_dogfood_missing`.

Remaining gaps:

- Agent Server matrix evidence is local production-compatible smoke evidence, not repeated live external-runtime dogfood.
- Live provider dogfood remains the final explicit latest artifact summary gap and still requires the mutation gate.
- More provider-specific Agent Server matrix cases can be added later for real external runtime providers once credentials/services are intentionally enabled.

Next concrete module:

- Continue Track I/J with live provider dogfood once the mutation gate is explicitly opened, or harden provider conformance / freshness evidence for external runtime runs without faking provider success.

Anti-Wheel Audit:

- No new Agent Server runner, custom graph runtime, trace system, generic agent loop, or observability backend was added.
- The slice reuses `scripts/langgraph_agent_server_ci_smoke.py`, existing matrix artifact outputs, and the existing Plan v7 artifact summary format.
- Durable product truth remains AITeamOS Tickets / Employees / Assets / Governance; Agent Server evidence only proves runtime compatibility and governed review behavior.

### 2026-06-20: Track I/J Live provider readiness artifact evidence

Status: completed for non-mutating live provider readiness evidence in Plan v7 artifacts.

Goal: make the remaining live dogfood blocker auditable without opening the mutation gate or pretending readiness equals dogfood completion.

Files changed:

- Added `scripts/live_provider_readiness_smoke.py`.
- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `scripts/plan_v7_artifact_summary.py`.
- Updated `tests/test_plan_v7_artifact_summary.py`.
- Updated `README.md`.
- Updated `plan_v7.md`.

What changed:

- Added a read-only readiness smoke that calls existing `LiveProviderDogfoodService.readiness()` and exits successfully when readiness evidence is produced, even if readiness itself is `blocked`.
- The smoke records selected executor preflight, repo-write executor candidates, Ticket backend status, Graphiti backend status, mutation gate state, blocker reasons, and blocker scopes.
- The default Plan v7 artifact runner now stores `live_provider_readiness_smoke.json` without mutating Plane, Graphiti, Tickets, Assets, or repo state.
- `plan_v7_artifact_summary.py` now exposes `latest_evidence.live_provider_readiness`.
- Readiness evidence does not satisfy `live_provider_dogfood_missing`; the summary keeps live dogfood as the remaining explicit gap until a real opt-in dogfood run exists.
- README now distinguishes non-mutating readiness from live provider dogfood completion.

Validation:

- `python -m py_compile scripts/live_provider_readiness_smoke.py scripts/plan_v7_ci_artifacts.py scripts/plan_v7_artifact_summary.py tests/test_plan_v7_artifact_summary.py` -> passed.
- Historical note: this line pre-dates the 2026-06-21 boundary correction. `python scripts/live_provider_readiness_smoke.py --output /tmp/aiteamos-live-provider-readiness-smoke.json` then emitted `selected_executor_id=codex_cli`; the current default readiness profile is `core_loop` with `selected_executor_id=langgraph`.
- `python -m pytest tests/test_plan_v7_artifact_summary.py -q` -> 5 passed.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-live-provider-readiness-evidence --include-agent-server-matrix-smoke --fail-fast` -> passed with 21 commands, including live provider readiness, Runtime Replay smoke, Agent Server matrix smoke, context retrieval smoke, Asset provenance smoke, queue worker smoke, `langgraph validate`, and `git diff --check`.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 1 --fail-on-failed` -> passed and extracted readiness with `ready_for_live_dogfood=false`, `ticket_backend_status=ready`, `memory_backend_status=ready`, `repo_write_ready_count=1`, and latest gap only `live_provider_dogfood_missing`.

Remaining gaps:

- Live provider dogfood has still not been executed because the mutation gate is closed.
- Readiness confirms current prerequisites are mostly ready, but it deliberately does not run provider smoke, create Tickets, approve Assets, project Graphiti, or test later recall.
- A real opt-in run with `AITEAMOS_LIVE_PROVIDER_DOGFOOD=1` is still required before v7 can be called production-ready.

Next concrete module:

- Continue Track I/J with an explicit live provider dogfood run when the mutation gate is opened, or add repeated live dogfood freshness / retention checks after the first real run exists.

Anti-Wheel Audit:

- No provider runner, custom dogfood loop, memory store, Ticket backend, or observability platform was added.
- The slice reuses `LiveProviderDogfoodService.readiness()`, RuntimeExecutor health, Ticket backend status, Graphiti backend status, and the existing Plan v7 artifact wrapper.
- Durable product truth remains AITeamOS Tickets / Employees / Assets / Governance; readiness is only a non-mutating provider preflight.

### 2026-06-20: Track I/J Opt-in live dogfood artifact command

Status: completed for the gated opt-in artifact command. Real live provider dogfood was not executed.

Goal: allow future real live dogfood evidence to be retained in the same Plan v7 artifact manifest without making the default CI/artifact path mutate provider state.

Files changed:

- Updated `scripts/plan_v7_ci_artifacts.py`.
- Added `tests/test_plan_v7_ci_artifacts.py`.
- Updated `scripts/context_retrieval_eval_smoke.py`.
- Updated `scripts/runtime_replay_eval_smoke.py`.
- Updated `scripts/ticket_loop_queue_worker_smoke.py`.
- Updated `README.md`.
- Updated `plan_v7.md`.

What changed:

- Added `--include-live-provider-dogfood`, `--live-provider-executor-id`, and `--live-provider-ticket-id` to the Plan v7 artifact runner.
- Default artifact runs still execute only live provider readiness evidence; they do not call `scripts/live_provider_dogfood.py`.
- When `--include-live-provider-dogfood` is explicitly set, the runner appends `live_provider_dogfood_execute`, which calls `scripts/live_provider_dogfood.py --execute --workspace-dir ... --executor-id ... --output .../live_provider_dogfood.json`.
- The underlying dogfood script still requires `AITEAMOS_LIVE_PROVIDER_DOGFOOD=1`; if the gate is closed, live mutation fails visibly instead of being inferred from readiness.
- Added artifact-runner tests that prove the live dogfood command is absent by default and present only under the explicit flag.
- Added `pytest_plan_v7_ci_artifacts` to the default artifact suite so the opt-in safety contract is continuously verified.
- Hardened context retrieval, Runtime Replay, and Ticket loop worker smoke scripts for repeated runs against the same artifact workspace:
  - context retrieval now requires the current work-history target refs and `report_count >= 1` instead of exact historical ledger size.
  - Runtime Replay now uses a per-ticket request id and resolves replay sessions by both request id and ticket id.
  - Ticket loop worker smoke now validates failed/processed/policy-action deltas for the current run instead of cumulative worker totals.

Validation:

- `python -m py_compile scripts/plan_v7_ci_artifacts.py tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_artifact_summary.py` -> passed.
- `python -m pytest tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_artifact_summary.py -q` -> 7 passed.
- `python scripts/plan_v7_ci_artifacts.py --help | rg -n "live-provider|include-live"` -> showed the new opt-in flags.
- `python scripts/context_retrieval_eval_smoke.py --workspace-dir .aiteamos/artifacts/plan_v7/local-v7-live-dogfood-opt-in-command/context-retrieval-eval-smoke-workspace --output /tmp/aiteamos-context-retrieval-rerun.json` -> passed on a previously used workspace.
- `python scripts/runtime_replay_eval_smoke.py --workspace-dir .aiteamos/artifacts/plan_v7/local-v7-live-dogfood-opt-in-command/runtime-replay-eval-smoke-workspace --output /tmp/aiteamos-runtime-replay-rerun.json` -> passed on a previously used workspace.
- `python scripts/ticket_loop_queue_worker_smoke.py --workspace-dir .aiteamos/artifacts/plan_v7/local-v7-live-dogfood-opt-in-command/ticket-loop-queue-worker-smoke-workspace --output /tmp/aiteamos-ticket-loop-worker-rerun.json --daemon-min-ticks 3 --daemon-interval-seconds 0.1 --daemon-timeout-seconds 5` -> passed on a previously used workspace.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-live-dogfood-opt-in-command --fail-fast` -> passed with 15 default commands; `include_live_provider_dogfood=false`.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 1 --fail-on-failed` -> passed; latest run `local-v7-live-dogfood-opt-in-command` has live provider readiness evidence, no failed commands, and explicit gaps `agent_server_matrix_smoke_missing` plus `live_provider_dogfood_missing`.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-live-dogfood-opt-in-command-matrix --include-agent-server-matrix-smoke --fail-fast` -> passed with 22 commands and Agent Server matrix coverage.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 1 --fail-on-failed` after the matrix run -> passed; latest run `local-v7-live-dogfood-opt-in-command-matrix` has `agent_server.coverage_complete=true`, 7/7 matrix cases passed, and the only evidence gap is `live_provider_dogfood_missing`.
- The default artifact run also passed `langgraph validate --config langgraph.json` and `git diff --check` for the Plan v7 slice.

Remaining gaps:

- Real live provider dogfood is still not executed because the mutation gate is closed.
- The default artifact run still lacks Agent Server matrix evidence unless `--include-agent-server-matrix-smoke` is passed.
- Live dogfood freshness / retention thresholds should be added after the first real opt-in dogfood run exists.

Next concrete module:

- Either run the opt-in live provider dogfood command when `AITEAMOS_LIVE_PROVIDER_DOGFOOD=1` is explicitly authorized, or add freshness/retention checks that consume real dogfood artifacts once they exist.

Anti-Wheel Audit:

- No new agent loop, provider adapter, dogfood runner, memory database, checkpoint UI, or observability layer was added.
- The slice reuses the existing `live_provider_dogfood.py`, `LiveProviderDogfoodService`, RuntimeExecutor health/readiness, Ticket loop worker, Runtime Replay service, and Plan v7 artifact wrapper.
- Durable product truth remains AITeamOS Tickets / Employees / Assets / Governance; live provider mutation remains an explicit, auditable opt-in.

### 2026-06-20: Track I/J Live dogfood freshness and retention summary

Status: completed for live provider dogfood freshness / retention summary checks. Real live provider dogfood was not executed.

Goal: make future real dogfood evidence auditable across later non-mutating verification runs, while keeping readiness and dry-run outputs from satisfying production dogfood completion.

Files changed:

- Updated `scripts/plan_v7_artifact_summary.py`.
- Updated `tests/test_plan_v7_artifact_summary.py`.
- Updated `README.md`.
- Updated `plan_v7.md`.

What changed:

- Added `--live-dogfood-max-age-hours` to `scripts/plan_v7_artifact_summary.py`; default freshness window is 168 hours.
- Summary output now includes `freshness_policy`, `retained_evidence`, and `retained_evidence_gaps`.
- Per-run live dogfood evidence now exposes `fresh`, `freshness_status`, `freshness_reason`, `age_seconds`, `max_age_seconds`, `run_finished_at`, `ticket_id`, `executor_id`, `runtime_dogfood_status`, `asset_record_ids`, `graphiti_projection_statuses`, `graphiti_recall_count`, and `blocker_count`.
- Only `completed`, `passed`, or `ready` live dogfood statuses can be fresh. `dry_run`, readiness, blocked, stale, or unknown-age artifacts produce explicit gaps.
- Retained evidence scans the inspected manifest window, so a real fresh dogfood artifact can remain visible after later non-mutating matrix / default runs.
- README now documents the freshness threshold flag and states that readiness / dry-run outputs do not satisfy live dogfood completion.

Validation:

- `python -m py_compile scripts/plan_v7_artifact_summary.py tests/test_plan_v7_artifact_summary.py scripts/plan_v7_ci_artifacts.py tests/test_plan_v7_ci_artifacts.py` -> passed.
- `python -m pytest tests/test_plan_v7_artifact_summary.py tests/test_plan_v7_ci_artifacts.py -q` -> 10 passed.
- `langgraph validate --config langgraph.json` -> passed, 2 graphs found.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 5 --fail-on-failed` -> passed and exposed `freshness_policy.live_dogfood_max_age_seconds=604800`.
- Targeted summary extraction after the matrix run showed `latest_run_id=local-v7-live-dogfood-opt-in-command-matrix`, `latest_evidence_gaps=["live_provider_dogfood_missing"]`, `retained_evidence_keys=[]`, and `retained_evidence_gaps=["live_provider_dogfood_missing"]`.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-live-dogfood-retention-summary --fail-fast` -> passed with 15 default commands and did not include live dogfood execution.
- Targeted summary extraction after the default run showed `latest_run_id=local-v7-live-dogfood-retention-summary`, `latest_evidence_gaps=["agent_server_matrix_smoke_missing","live_provider_dogfood_missing"]`, `retained_evidence_keys=[]`, and `retained_evidence_gaps=["live_provider_dogfood_missing"]`.
- The default artifact run also passed `langgraph validate --config langgraph.json` and `git diff --check` for the Plan v7 slice.

Remaining gaps:

- Real live provider dogfood is still not executed because the mutation gate is closed.
- Retention logic is now ready, but it has no completed live dogfood artifact to retain.
- The latest default artifact run lacks Agent Server matrix evidence because `--include-agent-server-matrix-smoke` was intentionally not passed.

Next concrete module:

- Run the opt-in live provider dogfood command only when `AITEAMOS_LIVE_PROVIDER_DOGFOOD=1` is explicitly authorized, then verify the retained evidence turns fresh and later recall/projection evidence remains present.

Anti-Wheel Audit:

- No new dogfood runner, observability store, memory database, agent loop, provider adapter, or CI runner was added.
- The slice reuses existing Plan v7 manifests, existing live dogfood CLI output, existing readiness evidence, and the artifact summary wrapper.
- Durable product truth remains AITeamOS Tickets / Employees / Assets / Governance; the summary only audits whether real external evidence exists and is fresh.

### 2026-06-20: Track J production readiness evidence gates

Status: completed for optional strict artifact-summary gates. Defaults remain read-only / non-blocking.

Goal: prevent v7 from being called production-ready merely because tests passed when latest evidence or retained live dogfood evidence still has explicit gaps.

Files changed:

- Updated `scripts/plan_v7_artifact_summary.py`.
- Updated `tests/test_plan_v7_artifact_summary.py`.
- Updated `README.md`.
- Updated `plan_v7.md`.

What changed:

- Added `--fail-on-latest-evidence-gaps` to fail when the latest inspected manifest lacks required evidence such as Agent Server matrix or live dogfood.
- Added `--fail-on-retained-evidence-gaps` to fail when retained cross-run evidence lacks fresh live dogfood.
- Added `--fail-on-evidence-gaps` as a combined readiness gate for both latest and retained evidence gaps.
- Preserved default summary behavior: without the new flags, the command remains a read-only operations report and still only fails on `--fail-on-failed`.
- Added explicit exit-code coverage:
  - `2` for failed runs when `--fail-on-failed` is enabled.
  - `3` for latest evidence gaps.
  - `4` for retained evidence gaps.
- README now documents the strict gate flags separately from the normal read-only summary command.

Validation:

- `python -m py_compile scripts/plan_v7_artifact_summary.py tests/test_plan_v7_artifact_summary.py` -> passed.
- `python -m pytest tests/test_plan_v7_artifact_summary.py -q` -> 9 passed.
- `python -m pytest tests/test_plan_v7_artifact_summary.py tests/test_plan_v7_ci_artifacts.py -q` -> 11 passed.
- `python scripts/plan_v7_artifact_summary.py --help | rg -n "fail-on|live-dogfood-max"` -> showed `--fail-on-latest-evidence-gaps`, `--fail-on-retained-evidence-gaps`, and `--fail-on-evidence-gaps`.
- `langgraph validate --config langgraph.json` -> passed, 2 graphs found.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-summary-readiness-gates --fail-fast` -> passed with 15 default commands and did not include live dogfood execution.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 5 --fail-on-latest-evidence-gaps` over current real artifacts returned exit code `3`, with latest gaps `agent_server_matrix_smoke_missing` and `live_provider_dogfood_missing`.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 5 --fail-on-retained-evidence-gaps` over current real artifacts returned exit code `4`, with retained gap `live_provider_dogfood_missing`.
- The default artifact run also passed `langgraph validate --config langgraph.json` and `git diff --check` for the Plan v7 slice.

Remaining gaps:

- Real live provider dogfood is still not executed because the mutation gate is closed.
- A production-ready strict gate will keep failing until a fresh completed live dogfood artifact exists.
- The latest default run still lacks Agent Server matrix evidence unless `--include-agent-server-matrix-smoke` is passed.

Next concrete module:

- Run the opt-in live provider dogfood command only when `AITEAMOS_LIVE_PROVIDER_DOGFOOD=1` is explicitly authorized, then run `plan_v7_artifact_summary.py --fail-on-evidence-gaps` over an artifact window containing Agent Server matrix and the fresh live dogfood evidence.

Anti-Wheel Audit:

- No new CI runner, observability platform, agent loop, provider adapter, or dogfood executor was added.
- The slice reuses existing saved Plan v7 manifests and the existing artifact summary wrapper as the readiness gate.
- Durable product truth remains AITeamOS Tickets / Employees / Assets / Governance; the gate only prevents incomplete evidence from being treated as completion.

### 2026-06-20: Track J production readiness artifact profile

Status: completed for a strict local production-readiness profile. Real live provider dogfood was not executed.

Goal: make the "production readiness" command explicit so future verification cannot accidentally omit Agent Server matrix evidence or strict artifact evidence gates, while keeping live provider dogfood behind its existing opt-in mutation gate.

Files changed:

- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `tests/test_plan_v7_ci_artifacts.py`.
- Updated `README.md`.
- Updated `plan_v7.md`.

What changed:

- Added `--production-readiness` to `scripts/plan_v7_ci_artifacts.py`.
- The production-readiness profile expands to the broader backend dispatch contract suite, includes the Agent Server matrix smoke, and appends `plan_v7_artifact_summary.py --fail-on-evidence-gaps` as the final evidence gate.
- The profile does not enable `live_provider_dogfood_execute`; live dogfood still requires both `--include-live-provider-dogfood` and `AITEAMOS_LIVE_PROVIDER_DOGFOOD=1`.
- The manifest records `production_readiness=true`, `full=true`, `include_agent_server_matrix_smoke=true`, and `include_live_provider_dogfood=false` for this profile.
- README now documents `--production-readiness` as a strict local readiness gate that should fail without fresh retained live dogfood evidence.

Validation:

- `python -m py_compile scripts/plan_v7_ci_artifacts.py tests/test_plan_v7_ci_artifacts.py` -> passed.
- `python -m pytest tests/test_plan_v7_ci_artifacts.py -q` -> 3 passed.
- `python scripts/plan_v7_ci_artifacts.py --help | rg -n "production-readiness|include-live|include-agent-server-matrix|full"` -> showed the new profile and preserved opt-in live dogfood flags.
- `python -m pytest tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_artifact_summary.py -q` -> 12 passed.
- `langgraph validate --config langgraph.json` -> passed, 2 graphs found.
- `git diff --check -- scripts/plan_v7_ci_artifacts.py tests/test_plan_v7_ci_artifacts.py README.md plan_v7.md` -> passed before this log entry.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-production-readiness-profile --production-readiness --fail-fast` -> all non-summary commands passed, including broader backend dispatch contracts and 7/7 Agent Server matrix cases; the final summary gate failed with exit code `3` because `live_provider_dogfood_missing` remains.
- The saved manifest confirmed `live_provider_dogfood_execute` was not run.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 1 --fail-on-evidence-gaps` after the run returned exit code `3`, with latest run `local-v7-production-readiness-profile`, `agent_server.coverage_complete=true`, latest gap `live_provider_dogfood_missing`, and retained gap `live_provider_dogfood_missing`.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 1 --fail-on-retained-evidence-gaps` returned exit code `4`, proving no fresh retained live dogfood evidence exists.

Remaining gaps:

- v7 still cannot be called production-ready until a real opt-in live provider dogfood run succeeds and remains fresh.
- The production-readiness profile is intentionally strict and will keep failing without that evidence.
- GitHub Actions still runs the default non-mutating profile by default; the strict production-readiness profile is documented for local / manually authorized readiness verification.

Next concrete module:

- Superseded by the 2026-06-21 boundary correction as a core production-readiness command. The `codex_cli` form is only repo-write adapter conformance; core readiness must instead use the required LangGraph + DeepSeek provider core-loop dogfood profile, then require `plan_v7_artifact_summary.py --fail-on-evidence-gaps` to pass over the saved artifact window.

Anti-Wheel Audit:

- No new CI framework, observability store, dogfood executor, agent loop, memory database, or provider adapter was added.
- The profile only composes existing pytest, LangGraph Agent Server smoke, live readiness, dogfood opt-in, and artifact summary commands.
- Durable product truth remains AITeamOS Tickets / Employees / Assets / Governance; the profile only audits whether required evidence exists.

### 2026-06-20: Track J post-run production readiness summary gate

Status: completed for post-run readiness summary gating. Real live provider dogfood was not executed.

Goal: make the production-readiness summary artifact inspect a completed provisional manifest instead of reading the current run while it is still marked `running`.

Files changed:

- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `tests/test_plan_v7_ci_artifacts.py`.
- Updated `plan_v7.md`.

What changed:

- Moved the `plan_v7_production_readiness_summary_gate` out of the normal `_commands()` list and into a post-run command phase.
- `plan_v7_ci_artifacts.py` now writes the manifest as provisionally `passed` after all ordinary commands pass, then runs the strict production summary gate.
- If the post-run summary gate fails, the gate result is appended as a command artifact and the final manifest becomes `failed`.
- Added `_post_commands()` so production readiness post-gates remain explicit and testable without mixing them into the ordinary smoke command list.
- Preserved the live dogfood safety contract: `live_provider_dogfood_execute` is still absent unless `--include-live-provider-dogfood` is passed.

Validation:

- `python -m py_compile scripts/plan_v7_ci_artifacts.py tests/test_plan_v7_ci_artifacts.py` -> passed.
- `python -m pytest tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_artifact_summary.py -q` -> 12 passed.
- `langgraph validate --config langgraph.json` -> passed, 2 graphs found.
- `git diff --check -- scripts/plan_v7_ci_artifacts.py tests/test_plan_v7_ci_artifacts.py README.md plan_v7.md` -> passed before this log entry.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-production-readiness-post-gate --production-readiness --fail-fast` -> all 23 ordinary commands passed, including broader backend dispatch contracts and 7/7 Agent Server matrix; post-run summary gate failed with return code `3` because `live_provider_dogfood_missing` remains.
- The generated `production_readiness_summary.json` now reports `latest_run_id=local-v7-production-readiness-post-gate`, `latest_status=passed`, `agent_server.coverage_complete=true`, and latest/retained gaps `live_provider_dogfood_missing`.
- The final manifest then records `status=failed`, command count `24`, failed command `plan_v7_production_readiness_summary_gate`, and confirms `live_provider_dogfood_execute` was not run.
- Re-running `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 1 --fail-on-evidence-gaps` returned exit code `3`, with final latest status `failed` and the same live dogfood gap.

Remaining gaps:

- The only production-readiness evidence gap remains a fresh real live provider dogfood artifact.
- The strict profile still cannot pass until the mutation gate is explicitly opened and real dogfood succeeds.

Next concrete module:

- Continue hardening around live-provider readiness / provider conformance, or run the already documented production-readiness live dogfood command after explicit authorization.

Anti-Wheel Audit:

- No new runner, summary database, observability system, dogfood executor, agent loop, or memory store was added.
- The slice only changed when the existing artifact summary command runs so its evidence reflects a completed provisional manifest.
- Durable product truth remains AITeamOS Tickets / Employees / Assets / Governance; the post-run gate only audits saved evidence.

### 2026-06-20: Track I/J environment provider conformance artifact evidence

Status: completed for read-only environment / provider conformance evidence in the default Plan v7 artifact suite.

Goal: surface provider readiness and setup blockers as structured artifact evidence, instead of leaving Plane / Graphiti / RuntimeExecutor conformance only in API responses or stdout logs.

Files changed:

- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `scripts/plan_v7_artifact_summary.py`.
- Updated `tests/test_plan_v7_ci_artifacts.py`.
- Updated `tests/test_plan_v7_artifact_summary.py`.
- Updated `README.md`.
- Updated `plan_v7.md`.

What changed:

- Added the existing read-only `scripts/environment_smoke.py` command to the default artifact suite.
- Added `environment_smoke.json` extraction to `plan_v7_artifact_summary.py`.
- Summary now reports environment status, contract version, external-call flag, non-destructive flag, check counts, provider smoke counts, per-check statuses, and blocker ids.
- Missing environment smoke, failed environment checks, provider failures, and non-warning/non-passed environment statuses now appear as evidence gaps.
- README now documents environment/provider conformance as first-class Plan v7 artifact evidence.

Validation:

- `python scripts/environment_smoke.py --workspace-dir /tmp/aiteamos-environment-smoke-v7 --output /tmp/aiteamos-environment-smoke-v7/environment_smoke.json` -> passed; emitted read-only provider conformance evidence with no external calls.
- `python -m py_compile scripts/plan_v7_ci_artifacts.py scripts/plan_v7_artifact_summary.py tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_artifact_summary.py scripts/environment_smoke.py` -> passed.
- `python -m pytest tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_artifact_summary.py -q` -> 13 passed.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-environment-smoke-evidence --fail-fast` -> passed with 16 default commands and included `environment_smoke`.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 1 --fail-on-failed` after the run reported `latest_evidence.environment_smoke.status=warning`, `check_statuses.ai_engine:deepseek=passed`, `check_statuses.fallback:local=passed`, `check_statuses.runtime:agent_loop=passed`, `check_statuses.providers:core=warning`, and `external_calls=false`.
- The same summary showed latest gaps `agent_server_matrix_smoke_missing` and `live_provider_dogfood_missing`, because the default run intentionally did not include Agent Server matrix or live dogfood.
- `langgraph validate --config langgraph.json` -> passed, 2 graphs found.

Remaining gaps:

- Environment smoke is read-only local/provider conformance evidence; it is not a substitute for fresh real live provider dogfood.
- The default artifact profile still omits Agent Server matrix unless explicitly requested or `--production-readiness` is used.
- Optional external provider smoke remains opt-in through `environment_smoke.py --include-external`; it was not enabled in this non-mutating default artifact run.

Next concrete module:

- Continue Track I/J by adding production-readiness workflow wiring or by running opt-in live provider dogfood after explicit mutation-gate authorization.

Anti-Wheel Audit:

- No provider health platform, CI framework, observability backend, RuntimeExecutor dispatcher, dogfood executor, agent loop, or memory store was added.
- The slice reuses existing `provider_environment_smoke()`, existing RuntimeExecutor health checks, existing provider conformance contracts, and the existing Plan v7 artifact wrapper.
- Durable product truth remains AITeamOS Tickets / Employees / Assets / Governance; provider smoke only exposes readiness and blockers.

### 2026-06-20: Track J GitHub production-readiness workflow wiring

Status: completed for manual GitHub Actions wiring of the strict production-readiness profile. Live provider dogfood remains unavailable from the workflow.

Goal: make the strict `--production-readiness` profile runnable from `workflow_dispatch` without adding a CI mutation path for live dogfood.

Files changed:

- Updated `.github/workflows/plan-v7-verification.yml`.
- Added `tests/test_plan_v7_workflow.py`.
- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `README.md`.
- Updated `plan_v7.md`.

What changed:

- Added a `production_readiness` manual workflow input, defaulting to `false`.
- When manually selected, the workflow appends `--production-readiness` to the existing artifact runner.
- The workflow does not expose or pass `--include-live-provider-dogfood`, so GitHub Actions cannot accidentally open the live provider mutation path.
- Added a workflow test that parses the YAML, verifies the `production_readiness` input, verifies the runner argument mapping, and asserts that live dogfood is not wired into the workflow run script.
- Added `tests/test_plan_v7_workflow.py` to the default Plan v7 artifact runner py_compile and pytest coverage.
- README now explains that workflow production readiness is strict but non-mutating and should fail with a live dogfood evidence gap until authorized dogfood evidence exists.

Validation:

- YAML parse smoke over `.github/workflows/plan-v7-verification.yml` -> passed; `production_readiness` input exists and defaults to `false`.
- `python -m py_compile scripts/plan_v7_ci_artifacts.py tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_workflow.py` -> passed.
- `python -m pytest tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_workflow.py -q` -> 4 passed.
- `python -m pytest tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_artifact_summary.py tests/test_plan_v7_workflow.py -q` -> 14 passed.
- `python scripts/plan_v7_ci_artifacts.py --help | rg -n "production-readiness|include-agent-server-matrix|include-live"` -> showed the production readiness and live opt-in flags.
- `git diff --check -- .github/workflows/plan-v7-verification.yml README.md plan_v7.md scripts/plan_v7_ci_artifacts.py tests/test_plan_v7_ci_artifacts.py` -> passed before this log entry.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-workflow-production-readiness-input --fail-fast` -> passed with 16 default commands; the default runner now includes `tests/test_plan_v7_workflow.py`.

Remaining gaps:

- GitHub production readiness remains non-mutating and therefore cannot satisfy the fresh live dogfood requirement by itself.
- A true production-ready run still requires explicitly authorized live provider dogfood outside this workflow path or a separately governed CI mutation design.

Next concrete module:

- Continue hardening RuntimeExecutor/live provider conformance evidence, or run the documented live dogfood production-readiness command only after explicit mutation-gate authorization.

Anti-Wheel Audit:

- No new CI framework, workflow runner, dogfood executor, provider adapter, observability system, agent loop, or memory store was added.
- The workflow only invokes the existing Plan v7 artifact runner and existing production-readiness profile.
- Durable product truth remains AITeamOS Tickets / Employees / Assets / Governance; workflow wiring only improves evidence execution ergonomics.

### 2026-06-20: Track I/J live readiness blocker detail summary

Status: completed for compact live provider readiness blocker details in artifact summary. Real live provider dogfood was not executed.

Goal: make `live_provider_readiness_smoke.json` explain exactly why production dogfood is not ready, including setup requirements and repo-write RuntimeExecutor candidates, instead of only surfacing blocker counts and reason strings.

Files changed:

- Updated `scripts/plan_v7_artifact_summary.py`.
- Updated `tests/test_plan_v7_artifact_summary.py`.
- Updated `README.md`.
- Updated `plan_v7.md`.

What changed:

- `latest_evidence.live_provider_readiness` now includes compact `blockers` with reason, scope, status, and setup requirements.
- It also includes a de-duplicated `setup_required` list across blockers.
- It includes compact `repo_write_candidates` with executor id, status, blocker reasons, and setup requirements.
- README now documents live readiness blocker details, setup requirements, and repo-write RuntimeExecutor candidates as part of Plan v7 artifact summary evidence.

Validation:

- `python -m py_compile scripts/plan_v7_artifact_summary.py tests/test_plan_v7_artifact_summary.py` -> passed.
- `python -m pytest tests/test_plan_v7_artifact_summary.py -q` -> 10 passed.
- `python -m pytest tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_artifact_summary.py tests/test_plan_v7_workflow.py -q` -> 14 passed.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 1 --fail-on-failed` over the latest real artifact run reported live readiness blocker `live_provider_dogfood_not_confirmed`, scope `mutation_gate`, setup requirements `--execute` and `AITEAMOS_LIVE_PROVIDER_DOGFOOD=1`, plus six repo-write candidate records.
- `langgraph validate --config langgraph.json` -> passed, 2 graphs found.
- `git diff --check -- scripts/plan_v7_artifact_summary.py tests/test_plan_v7_artifact_summary.py README.md plan_v7.md` -> passed before this log entry.

Remaining gaps:

- The readiness blocker details make the blocker auditable, but they do not replace a real fresh live dogfood artifact.
- Production-readiness strict gates still fail until live dogfood is explicitly authorized and completes.

Next concrete module:

- Continue Track I/J by using the readiness blocker details in UI/system status, or proceed to the documented opt-in live dogfood run only after explicit mutation-gate authorization.

Anti-Wheel Audit:

- No provider health platform, dogfood runner, executor dispatcher, observability system, agent loop, or memory store was added.
- The slice only extracts more structure from the existing live provider readiness artifact.
- Durable product truth remains AITeamOS Tickets / Employees / Assets / Governance; readiness details only explain provider and mutation-gate blockers.

### 2026-06-20: Track I/J System Status live readiness blocker surfacing

Status: completed for System Status API/UI surfacing of structured live provider readiness blockers. Real live provider dogfood was not executed.

Goal: move the live readiness blocker detail from artifact-only evidence into the product System Status surface, so operators can see the exact blocker reasons, setup requirements, mutation gate state, and repo-write RuntimeExecutor candidates without inspecting CI JSON.

Files changed:

- Updated `services/api/aiteamos_api/read/system_status_routes.py`.
- Updated `apps/dashboard/src/api/systemStatus.ts`.
- Updated `apps/dashboard/src/pages/system-status/index.tsx`.
- Updated `apps/dashboard/src/__tests__/system-status-page.test.tsx`.
- Updated `tests/test_file_system_status_routes.py`.
- Updated `plan_v7.md`.

What changed:

- `SystemStatusBlocker` now supports structured `reasons`, `related_blockers`, `related_candidates`, and `summary` fields.
- The `live_provider_dogfood` top-level blocker now includes compact readiness blocker details, setup requirements, selected executor, mutation gate state, provider smoke status, and repo-write RuntimeExecutor candidate summaries.
- The System Status `Operating Blockers` panel renders structured readiness details and runtime candidates directly in the global blocker view.
- Frontend and backend tests now assert that live dogfood blockers remain visible instead of being reduced to a generic blocked count.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/system_status_routes.py` -> passed.
- `python -m pytest tests/test_file_system_status_routes.py -q` -> 4 passed.
- `npm exec vitest run --environment jsdom src/__tests__/system-status-page.test.tsx` from `apps/dashboard` -> 8 passed.
- `npm --prefix apps/dashboard run build` -> passed.
- `langgraph validate --config langgraph.json` -> passed, 2 graphs found.
- `git diff --check -- services/api/aiteamos_api/read/system_status_routes.py apps/dashboard/src/api/systemStatus.ts apps/dashboard/src/pages/system-status/index.tsx apps/dashboard/src/__tests__/system-status-page.test.tsx tests/test_file_system_status_routes.py` -> passed.

Notes:

- `npm --prefix apps/dashboard exec vitest run --environment jsdom src/__tests__/system-status-page.test.tsx` from the repo root failed because the Vite `@` alias was not resolved under that invocation; rerunning from `apps/dashboard` with the project config passed.
- No live provider mutation was attempted; `AITEAMOS_LIVE_PROVIDER_DOGFOOD=1` was not set or used.

Remaining gaps:

- The UI now makes live readiness blockers actionable, but production-readiness strict gates still require an explicitly authorized fresh live dogfood run.
- The next production hardening step should either reuse these structured blocker details in the Runtime page/replay evidence surfaces or continue non-mutating provider conformance until live dogfood is authorized.

Next concrete module:

- Continue Track I/J by connecting structured readiness blockers into Runtime replay/system evidence summaries, or proceed to the documented opt-in live dogfood run only after explicit mutation-gate authorization.

Anti-Wheel Audit:

- No generic agent loop, chat runtime, streaming protocol, memory database, provider health platform, or dogfood runner was added.
- The slice reuses the existing `LiveProviderDogfoodService.readiness()` contract and System Status page instead of creating a parallel readiness dashboard.
- Durable product truth remains AITeamOS Tickets / Employees / Assets / Governance; Graphiti remains only a projection/recall provider; external runtimes remain behind RuntimeExecutor readiness and approval boundaries.

### 2026-06-20: Track I/J Runtime registry live readiness evidence

Status: completed for Runtime registry and Runtime Replay page surfacing of structured live provider readiness. Real live provider dogfood was not executed.

Goal: reuse the structured live readiness blocker projection beyond System Status, so Runtime Replay operators can see whether the RuntimeExecutor layer can safely run the full live provider loop before opening individual execution sessions.

Files changed:

- Updated `services/api/aiteamos_api/read/live_provider_dogfood_service.py`.
- Updated `services/api/aiteamos_api/read/system_status_routes.py`.
- Updated `services/api/aiteamos_api/read/runtime_executor_routes.py`.
- Updated `apps/dashboard/src/api/runtimeExecutors.ts`.
- Updated `apps/dashboard/src/pages/runtime/index.tsx`.
- Updated `apps/dashboard/src/__tests__/runtime-page.test.tsx`.
- Updated `tests/test_runtime_executor_routes.py`.
- Updated `tests/test_file_system_status_routes.py`.
- Updated `plan_v7.md`.

What changed:

- Added shared `live_provider_readiness_projection()` in `LiveProviderDogfoodService` module so System Status and Runtime surfaces use one compact readiness contract.
- `/api/v1/runtime-executors` now includes `live_provider_readiness` plus summary fields for live provider status and blocker count without changing the existing executor `blockers` semantics.
- Runtime Replay page now loads RuntimeExecutor registry alongside sessions and renders a compact `Runtime Provider Readiness` band with live blocker reasons, mutation gate state, Ticket/Memory/provider smoke statuses, and repo-write RuntimeExecutor candidates.
- System Status now consumes the shared projection instead of route-local compacting helpers.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/live_provider_dogfood_service.py services/api/aiteamos_api/read/system_status_routes.py services/api/aiteamos_api/read/runtime_executor_routes.py` -> passed.
- `python -m pytest tests/test_runtime_executor_routes.py::test_runtime_executor_registry_lists_backends_capabilities_and_setup_blockers tests/test_file_system_status_routes.py::test_system_status_reports_secret_health_without_settings_compat_route -q` -> 2 passed.
- `npm exec vitest run --environment jsdom src/__tests__/runtime-page.test.tsx` from `apps/dashboard` -> 3 passed.
- `python -m pytest tests/test_runtime_executor_routes.py tests/test_file_system_status_routes.py -q` -> 20 passed.
- `npm --prefix apps/dashboard run build` -> passed.
- `langgraph validate --config langgraph.json` -> passed, 2 graphs found.
- `git diff --check -- services/api/aiteamos_api/read/live_provider_dogfood_service.py services/api/aiteamos_api/read/system_status_routes.py services/api/aiteamos_api/read/runtime_executor_routes.py apps/dashboard/src/api/runtimeExecutors.ts apps/dashboard/src/pages/runtime/index.tsx apps/dashboard/src/__tests__/runtime-page.test.tsx tests/test_runtime_executor_routes.py tests/test_file_system_status_routes.py` -> passed.

Remaining gaps:

- Runtime Replay now exposes live provider readiness before session inspection, but strict production readiness still requires an explicitly authorized fresh live provider dogfood run.
- The next non-mutating hardening step should connect the same readiness projection into artifact summary/system evidence reports or broaden Agent Server matrix coverage for repeated Ticket loop/provider paths.

Next concrete module:

- Continue Track J by wiring shared live readiness projection into Plan v7 artifact summary/system evidence output, or continue Track B/A Agent Server graph matrix coverage until live provider mutation is authorized.

Anti-Wheel Audit:

- No new provider health system, observability platform, RuntimeExecutor dispatcher, dogfood runner, memory database, chat runtime, streaming protocol, or agent loop was added.
- The slice reuses `LiveProviderDogfoodService.readiness()` and the existing Runtime registry/page instead of building a parallel readiness dashboard.
- Durable product truth remains AITeamOS Tickets / Employees / Assets / Governance; Graphiti remains projection/recall only; RuntimeExecutor remains the external runtime boundary.

### 2026-06-20: Track J Runtime registry artifact evidence

Status: completed for non-mutating RuntimeExecutor registry evidence in the Plan v7 artifact suite and artifact summary. Real live provider dogfood was not executed.

Goal: make the RuntimeExecutor registry and shared live provider readiness projection part of the repeatable evidence chain, so production-readiness reviews can inspect runtime boundary health, repo-write candidates, and mutation-gate blockers without manually opening the Runtime page.

Files changed:

- Added `scripts/runtime_registry_smoke.py`.
- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `scripts/plan_v7_artifact_summary.py`.
- Updated `tests/test_plan_v7_ci_artifacts.py`.
- Updated `tests/test_plan_v7_artifact_summary.py`.
- Updated `plan_v7.md`.

What changed:

- Added a read-only `runtime_registry_smoke` CLI that calls the existing RuntimeExecutor registry contract and writes `aiteamos.runtime_registry_smoke.v1` evidence.
- The smoke evidence summarizes executor counts, ready/blocked executor ids, RuntimeExecutor boundary, repo-write candidates, live provider readiness status, setup requirements, mutation gate state, and Ticket/Memory/provider smoke statuses.
- The default Plan v7 artifact runner now writes `runtime_registry_smoke.json` alongside environment, replay, retrieval, provenance, queue worker, and readiness evidence.
- Artifact summary now exposes `latest_evidence.runtime_registry` and reports a specific `runtime_registry_smoke_missing` gap if the evidence file is absent.
- Runtime registry gaps focus on missing or invalid registry evidence; a blocked live provider readiness state remains visible but is not treated as a failed smoke unless the registry evidence itself is invalid.

Validation:

- `python -m py_compile scripts/runtime_registry_smoke.py scripts/plan_v7_ci_artifacts.py scripts/plan_v7_artifact_summary.py tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_artifact_summary.py` -> passed.
- `python scripts/runtime_registry_smoke.py --workspace-dir /tmp/aiteamos-runtime-registry-smoke --output /tmp/aiteamos-runtime-registry-smoke.json` -> passed after fixing the CLI exit path for async resources.
- `python -m pytest tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_artifact_summary.py -q` -> 13 passed.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-runtime-registry-evidence --fail-fast` -> passed with 17 default commands, including `runtime_registry_smoke`.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 1 --fail-on-failed --output /tmp/plan_v7_latest_summary.json` -> passed and populated `latest_evidence.runtime_registry`.

Remaining gaps:

- The artifact suite now records RuntimeExecutor registry evidence, but strict production readiness still requires an explicitly authorized fresh live provider dogfood run.
- The latest non-mutating artifact summary still shows `agent_server_matrix_smoke_missing` when the matrix profile is not requested.
- Runtime registry evidence currently proves the boundary and blocker visibility; it does not yet broaden Agent Server matrix coverage for repeated Ticket loop/provider paths.

Next concrete module:

- Continue Track B/A by broadening Agent Server graph matrix coverage in the artifact suite, or proceed to the documented opt-in live dogfood run only after explicit mutation-gate authorization.

Anti-Wheel Audit:

- No new provider health platform, runtime dispatcher, observability database, dogfood executor, chat runtime, streaming protocol, memory database, checkpoint UI, or agent loop was added.
- The slice reuses the existing RuntimeExecutor registry route contract, shared live provider readiness projection, and Plan v7 artifact runner.
- Durable product truth remains AITeamOS Tickets / Employees / Assets / Governance; registry evidence only makes runtime readiness auditable.

### 2026-06-20: Track B/J retained Agent Server matrix evidence

Status: completed for retained Agent Server matrix evidence in Plan v7 artifact summaries. Real live provider dogfood was not executed.

Goal: prevent a later lightweight artifact run from hiding the fact that production-compatible Agent Server matrix evidence already exists in the inspected artifact window, while still requiring fresh live dogfood evidence for full production readiness.

Files changed:

- Updated `scripts/plan_v7_artifact_summary.py`.
- Updated `tests/test_plan_v7_artifact_summary.py`.
- Updated `README.md`.
- Updated `plan_v7.md`.

What changed:

- `retained_evidence` now independently retains the latest available `agent_server` matrix evidence and the latest available `live_provider_dogfood` evidence across the inspected runs.
- `retained_evidence_gaps` now reports `agent_server_matrix_smoke_missing` or Agent Server matrix coverage gaps when no complete matrix evidence is available in the window.
- A lightweight latest run can still show `latest_evidence_gaps.agent_server_matrix_smoke_missing`, but retained evidence can prove that a recent heavier matrix run exists.
- README now documents retained evidence as both Agent Server matrix retention and live dogfood freshness retention.
- Test fixtures now include a reusable complete Agent Server matrix helper and assert retained matrix provenance.

Validation:

- `python -m py_compile scripts/plan_v7_artifact_summary.py tests/test_plan_v7_artifact_summary.py` -> passed.
- `python -m pytest tests/test_plan_v7_artifact_summary.py -q` -> 10 passed.
- `python -m pytest tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_artifact_summary.py -q` -> 13 passed.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 10 --output /tmp/plan_v7_retained_summary.json` -> passed.
- Inspecting `/tmp/plan_v7_retained_summary.json` showed latest run `local-v7-runtime-registry-evidence`, retained Agent Server matrix from `local-v7-production-readiness-post-gate`, `coverage_complete=true`, and retained gaps only `live_provider_dogfood_missing`.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 10 --fail-on-failed --output /tmp/plan_v7_retained_summary.json` returned exit code `2` because the inspected historical window includes prior production-readiness summary-gate failures. That is expected artifact history, not a failure of this slice.

Remaining gaps:

- Retained Agent Server matrix evidence is now stable across lightweight runs, but full production readiness still requires explicitly authorized fresh live provider dogfood.
- The matrix still covers the current production-compatible paths; repeated queued Ticket loop/provider-runtime paths remain future expansion work.

Next concrete module:

- Continue Track B/A by adding repeated queued Ticket loop or provider-runtime paths to the Agent Server matrix, or proceed to the documented opt-in live dogfood run only after explicit mutation-gate authorization.

Anti-Wheel Audit:

- No new CI runner, Agent Server runner, graph runtime, memory store, observability platform, provider checker, chat runtime, or dogfood executor was added.
- The slice only reuses existing artifact manifests, existing Agent Server matrix evidence, and the existing summary gate.
- Durable product truth remains AITeamOS Tickets / Employees / Assets / Governance; retained evidence only improves verification continuity.

### 2026-06-21: Direction correction for LangGraph core loop, DeepSeek provider, and Codex adapter boundary

Status: completed for plan-level correction only. No code was changed in this slice.

Goal: prevent future autonomous implementation loops from treating Codex CLI repo-write dogfood or direct LLM calls as the production core of AITeamOS.

Files changed:

- Updated `plan_v7.md`.

What changed:

- Added section `0.1` as the latest controlling direction for v7.
- Clarified that the required production dogfood is the LangGraph-native core loop: LangGraph / Agent Server -> AITeamOS Workbench graph -> Ticket / Employees / Assets / Governance -> Graphiti projection / recall.
- Set DeepSeek API as the temporary default LLM provider, but only behind LangGraph / LangChain model-provider wiring.
- Clarified that Codex CLI, Claude Code, OpenHands, and similar tools are optional repo-write / coding RuntimeExecutor adapters, not the default AITeamOS runtime.
- Added Track H2 for direct LLM cleanup and model provider boundary hardening.
- Updated Track I, tests/verification, completion definition, anti-wheel audit, and the reusable Goal prompt so future loops do not use `codex_cli` dogfood as the core production-readiness gate.

Validation:

- Documentation-only update; no backend/frontend tests were required.
- `plan_v7.md` now explicitly says that if `--profile core-loop` does not exist yet, implementing that profile is the next required v7 slice before claiming completion.

Remaining gaps:

- Code still needs to implement the split between core-loop dogfood and repo-write adapter dogfood.
- Current direct LLM surfaces must be audited and removed from primary Chat / Employee / Ticket-loop paths if they still bypass LangGraph.
- Existing scripts/tests may still mention `direct_llm` or `codex_cli` for diagnostics/conformance; the next implementation slice must decide which are legacy diagnostics and which must be removed from primary readiness evidence.

Next concrete module:

- Start with `scripts/live_provider_dogfood.py`, `services/api/aiteamos_api/read/live_provider_dogfood_service.py`, `scripts/plan_v7_ci_artifacts.py`, and direct LLM call sites under `services/api/aiteamos_api/read/` to implement a required `core-loop` profile using LangGraph + DeepSeek provider.

Anti-Wheel Audit:

- No new agent loop, chat runtime, streaming protocol, checkpoint UI, memory database, observability backend, or provider adapter was added.
- This update strengthens reuse boundaries: LangGraph owns the loop, LangChain/LangGraph own model-provider wiring, Graphiti remains projection/recall, and AITeamOS owns Ticket / Employees / Assets / Governance.
- Codex CLI is explicitly demoted to optional repo-write adapter conformance and cannot satisfy the core-loop completion gate.

### 2026-06-21: Track H2/I core-loop dogfood profile and direct LLM primary-path cleanup

Status: completed for the first code-level boundary correction slice. Real live provider dogfood was not executed.

Goal: make the 2026-06-21 direction correction executable, so future autonomous loops default to LangGraph core-loop evidence instead of Codex CLI repo-write dogfood or pre-graph direct LLM calls.

Files changed:

- Updated `services/api/aiteamos_api/read/live_provider_dogfood_service.py`.
- Updated `services/api/aiteamos_api/read/runtime_executors/langgraph_executor.py`.
- Updated `services/api/aiteamos_api/read/runtime_executors/direct_llm_executor.py`.
- Updated `services/api/aiteamos_api/read/execution_dispatch_service.py`.
- Updated `services/api/aiteamos_api/read/runtime_executor_routes.py`.
- Updated `services/api/aiteamos_api/read/system_status_routes.py`.
- Updated `services/api/aiteamos_api/read/provider_conformance_service.py`.
- Updated `scripts/live_provider_dogfood.py`.
- Updated `scripts/live_provider_readiness_smoke.py`.
- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `tests/test_live_provider_dogfood_service.py`.
- Updated `tests/test_plan_v7_ci_artifacts.py`.
- Updated `tests/test_runtime_executor_routes.py`.
- Updated `tests/test_file_system_status_routes.py`.
- Updated `tests/test_execution_dispatch_contract.py`.
- Updated `plan_v7.md`.

What changed:

- Added explicit live dogfood profiles: `core_loop` is now the default and selects `langgraph`; `repo_write_adapter` must be selected explicitly and defaults to `codex_cli`.
- Core-loop readiness no longer requires a repo-write executor; repo-write candidates remain visible as optional adapter evidence.
- `LiveProviderDogfoodService` now creates core-loop evidence through the LangGraph Workbench state, Ticket report, and governed MemoryCandidate path, while repo-write adapter dogfood still uses `RuntimeExecutorDogfood`.
- `live_provider_dogfood.py`, `live_provider_readiness_smoke.py`, and `plan_v7_ci_artifacts.py` now default to core-loop/langgraph evidence.
- System Status and RuntimeExecutor registry now report `profile=core_loop`, `selected_executor_id=langgraph`, and do not surface `runtime_executor_lacks_repo_write` for the default core-loop readiness path.
- `LangGraphExecutor` no longer uses the pre-graph direct LLM shortcut for answer-only DeepSeek/OpenAI requests; explicit `direct_llm` remains only as legacy/diagnostic compatibility.
- `DirectLLMExecutor` health now declares `production_role=diagnostic_compatibility`, `primary_runtime=false`, and `core_loop_completion_eligible=false`.
- Temporary health/readiness reads now close LangGraph SQLite checkpointer resources through `ExecutionDispatchService.aclose()`, so CLI smoke scripts exit cleanly after writing evidence.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/runtime_executors/langgraph_executor.py services/api/aiteamos_api/read/runtime_executors/direct_llm_executor.py services/api/aiteamos_api/read/execution_dispatch_service.py services/api/aiteamos_api/read/live_provider_dogfood_service.py services/api/aiteamos_api/read/runtime_executor_routes.py services/api/aiteamos_api/read/system_status_routes.py services/api/aiteamos_api/read/provider_conformance_service.py scripts/live_provider_dogfood.py scripts/live_provider_readiness_smoke.py scripts/plan_v7_ci_artifacts.py tests/test_execution_dispatch_contract.py tests/test_live_provider_dogfood_service.py tests/test_plan_v7_ci_artifacts.py tests/test_runtime_executor_routes.py tests/test_file_system_status_routes.py` -> passed.
- `python -m pytest tests/test_live_provider_dogfood_service.py tests/test_plan_v7_ci_artifacts.py tests/test_execution_dispatch_contract.py::test_direct_llm_executor_is_available_when_explicitly_selected tests/test_execution_dispatch_contract.py::test_langgraph_executor_does_not_use_pre_graph_direct_llm tests/test_execution_dispatch_contract.py::test_answer_only_defaults_to_universal_employee_agent_with_read_tools tests/test_runtime_executor_routes.py::test_runtime_executor_registry_lists_backends_capabilities_and_setup_blockers tests/test_file_system_status_routes.py::test_system_status_reports_secret_health_without_settings_compat_route -q` -> 15 passed.
- `timeout 20s python scripts/live_provider_dogfood.py --workspace-dir "$tmp" --output "$tmp/live_provider_dogfood_dry_run.json"` -> exited cleanly; result `status=dry_run`, `profile=core_loop`, `executor_id=langgraph`, `require_repo_write_executor=false`.
- `timeout 20s python scripts/live_provider_readiness_smoke.py --workspace-dir "$tmp" --output "$tmp/live_provider_readiness_smoke.json"` -> exited cleanly; summary `profile=core_loop`, `selected_executor_id=langgraph`, `readiness_status=blocked`, `repo_write_ready_count=1`.

Remaining gaps:

- Real live provider dogfood still needs explicit mutation-gate authorization and should prove `core_loop` with DeepSeek provider behind LangGraph.
- `direct_llm` still exists for explicit diagnostics/compatibility; it is no longer a core completion path, but future cleanup should remove it from any artifact language that could be read as production core evidence.
- Superseded by the next H2 slice: LangGraph graph execution now calls model providers through the LangChain model-provider adapter, not the old AI Engine HTTP helpers.

Next concrete module:

- Historical note: superseded by the following H2 slice, which converted LangGraph's in-graph DeepSeek/OpenAI call site to a LangChain model-provider adapter. The next current module is LangChain provider readiness evidence or explicitly authorized `core_loop` live dogfood.

Anti-Wheel Audit:

- No new agent loop, chat runtime, streaming protocol, memory database, checkpoint UI, provider health platform, or observability backend was added.
- The slice reuses LangGraph executor health, the existing Workbench/Ticket/MemoryCandidate services, RuntimeExecutor registry, System Status, and Plan v7 artifact scripts.
- AITeamOS remains responsible for Ticket / Employees / Assets / Governance; LangGraph remains the core loop; Codex CLI remains optional repo-write adapter conformance; direct LLM is explicitly diagnostic only.

### 2026-06-21: Track H2 LangChain model-provider boundary for LangGraph and planner

Status: completed for LangGraph/Universal/DirectLLM answer paths and Clara command-planner model-provider boundary. Real live provider dogfood was not executed.

Goal: remove AITeamOS-owned DeepSeek/OpenAI HTTP calls from the primary Chat / Employee / Ticket-loop model path and reuse LangChain provider integrations behind LangGraph.

Files changed:

- Added `services/api/aiteamos_api/read/langchain_model_provider.py`.
- Updated `services/api/aiteamos_api/read/runtime_executors/langgraph_executor.py`.
- Updated `services/api/aiteamos_api/read/runtime_executors/direct_llm_executor.py`.
- Updated `services/api/aiteamos_api/read/execution_dispatch_service.py`.
- Updated `services/api/aiteamos_api/read/chat_action_planning_service.py`.
- Updated `services/api/aiteamos_api/read/provider_conformance_service.py`.
- Updated `pyproject.toml`.
- Updated `tests/test_execution_dispatch_contract.py`.
- Updated `tests/test_file_chat_routes.py`.
- Updated `tests/test_file_system_status_routes.py`.
- Updated `tests/test_plan_v7_artifact_summary.py`.
- Updated `plan_v7.md`.

What changed:

- Introduced a thin `LangChainModelProvider` adapter around LangChain `init_chat_model`; AITeamOS passes provider config and messages, LangChain owns DeepSeek/OpenAI integration.
- Added explicit runtime dependencies for `langchain`, `langchain-deepseek`, and `langchain-openai`.
- `LangGraphExecutor` no longer imports or calls AITeamOS `ai_engine_clients` for non-stream answer execution.
- `UniversalEmployeeAgentExecutor` and explicit diagnostic `DirectLLMExecutor` now receive model completions through the same LangChain provider boundary.
- Clara's remote command planner now uses `LangChainModelProvider` with `source=langchain_deepseek_command_planner` instead of posting directly to DeepSeek.
- Provider conformance environment smoke now checks `langchain_model_provider_config_inspected` and records `langchain_model_provider` evidence; `direct_llm` is no longer marked required for core runtime readiness.
- Explicit diagnostic `DirectLLMExecutor` remains, but model calls are routed through `LangChainModelProvider`; it is not a native DeepSeek/OpenAI HTTP client and does not satisfy core-loop readiness.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/langchain_model_provider.py services/api/aiteamos_api/read/runtime_executors/langgraph_executor.py services/api/aiteamos_api/read/runtime_executors/direct_llm_executor.py services/api/aiteamos_api/read/execution_dispatch_service.py services/api/aiteamos_api/read/chat_action_planning_service.py services/api/aiteamos_api/read/provider_conformance_service.py tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py tests/test_file_system_status_routes.py tests/test_plan_v7_artifact_summary.py` -> passed.
- `python -m pytest tests/test_execution_dispatch_contract.py::test_direct_llm_executor_is_available_when_explicitly_selected tests/test_execution_dispatch_contract.py::test_langgraph_executor_does_not_use_pre_graph_direct_llm tests/test_execution_dispatch_contract.py::test_answer_only_defaults_to_universal_employee_agent_with_read_tools tests/test_file_chat_routes.py::test_employee_chat_streams_universal_agent_deepseek_answer tests/test_file_chat_routes.py::test_employee_chat_uses_deepseek_tool_planner_for_create_employee tests/test_file_chat_routes.py::test_employee_chat_can_use_deepseek_ai_engine tests/test_file_chat_routes.py::test_remote_chat_does_not_fallback_to_local_ticket_heuristics_when_planner_fails tests/test_file_chat_routes.py::test_employee_chat_can_use_openai_ai_engine tests/test_file_chat_routes.py::test_employee_capability_question_uses_openai_agent_bundle_without_kernel_intercept tests/test_file_chat_routes.py::test_openai_auth_error_returns_configuration_blocker_without_stub_reply tests/test_file_chat_routes.py::test_openai_quota_error_returns_configuration_blocker_without_stub_reply tests/test_runtime_executor_routes.py::test_runtime_executor_registry_lists_backends_capabilities_and_setup_blockers tests/test_file_system_status_routes.py::test_system_status_reports_secret_health_without_settings_compat_route tests/test_file_system_status_routes.py::test_environment_smoke_script_outputs_redacted_readiness_payload tests/test_file_system_status_routes.py::test_provider_conformance_external_smoke_uses_configured_plane_and_graphiti_adapters tests/test_plan_v7_artifact_summary.py -q` -> 25 passed.
- `langgraph validate --config langgraph.json` -> passed, 2 graphs found.
- `timeout 20s python scripts/live_provider_readiness_smoke.py --workspace-dir "$tmp" --output "$tmp/live_provider_readiness_smoke.json"` -> exited cleanly; summary `profile=core_loop`, `selected_executor_id=langgraph`, `readiness_status=blocked`, `repo_write_ready_count=1`.
- Static scan over touched executor/planner/conformance/tests showed no `call_deepseek_chat_completion`, `call_openai_responses`, `deepseek_command_planner`, `direct_llm_executor_health_read`, or `langgraph_remote_ai_engine` references in the primary paths.
- `git diff --check -- pyproject.toml services/api/aiteamos_api/read/langchain_model_provider.py services/api/aiteamos_api/read/runtime_executors/langgraph_executor.py services/api/aiteamos_api/read/runtime_executors/direct_llm_executor.py services/api/aiteamos_api/read/execution_dispatch_service.py services/api/aiteamos_api/read/chat_action_planning_service.py services/api/aiteamos_api/read/provider_conformance_service.py tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py tests/test_file_system_status_routes.py tests/test_plan_v7_artifact_summary.py` -> passed.

Remaining gaps:

- Real live provider dogfood still needs explicit mutation-gate authorization and should prove `core_loop` with DeepSeek provider through LangChain/LangGraph in a real Plane/Graphiti environment.
- `direct_llm` still exists as explicit diagnostic/compatibility surface, but it no longer embeds native DeepSeek/OpenAI HTTP calls. Future cleanup can either remove it or move it behind a separate diagnostics namespace.
- Provider package installation was declared in `pyproject.toml`; deployment environments still need dependency installation before a real DeepSeek/OpenAI LangChain call can succeed.
- Broader Agent Server matrix should keep proving LangChain model-provider configuration without external model calls.

Next concrete module:

- Proceed to the explicitly authorized `core_loop` live provider dogfood only when Plane/Graphiti/provider mutation readiness is intended; otherwise continue Track B/G with repeated Ticket loop and long-running Agent Server reliability evidence.

Anti-Wheel Audit:

- No new model client, agent loop, chat runtime, streaming protocol, memory database, checkpoint UI, or observability backend was added.
- The slice replaces hand-written model HTTP calls with LangChain provider integration and keeps AITeamOS focused on provider config, governance, Ticket/Employee/Asset facts, and provenance.
- Codex CLI remains optional repo-write adapter conformance; DeepSeek is now a model provider behind LangChain/LangGraph, not an AITeamOS-owned direct agent loop.

### 2026-06-21: Track H2/J direct LLM residue removal and provider-boundary evidence gate

Status: completed for residual direct HTTP cleanup and non-mutating readiness evidence. Real live provider dogfood was not executed.

Goal: remove the remaining AITeamOS-owned native DeepSeek/OpenAI HTTP helper path and make plan_v7 artifact evidence fail if LangChain provider-boundary readiness is not visible.

Files changed:

- Deleted `services/api/aiteamos_api/read/ai_engine_clients.py`.
- Updated `services/api/aiteamos_api/read/runtime_executors/langgraph_executor.py`.
- Updated `services/api/aiteamos_api/read/runtime_executors/direct_llm_executor.py`.
- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `scripts/plan_v7_artifact_summary.py`.
- Updated `tests/test_execution_dispatch_contract.py`.
- Updated `tests/test_plan_v7_artifact_summary.py`.
- Updated `plan_v7.md`.

What changed:

- Removed the unused AITeamOS-owned `ai_engine_clients.py` native DeepSeek/OpenAI HTTP helper module.
- Removed the native DeepSeek `/chat/completions` streaming method from `LangGraphExecutor`; `stream()` now delegates through normal graph/runtime execution.
- Removed `DirectLLMExecutor.stream()`'s special native DeepSeek streaming branch; explicit diagnostic runs now use the same `LangChainModelProvider` boundary as non-stream runs.
- Renamed the explicit compatibility executor display text to `Diagnostic Model Provider Executor` and clarified that it is not the primary runtime.
- Extended `plan_v7_artifact_summary.py` to extract `langchain_model_provider` evidence from `environment_smoke.json`, including `selected_provider=deepseek`, `provider_packages_required`, `config_inspected`, and `no_external_llm_call`.
- Extended Agent Server matrix evidence with `coverage.langchain_provider_boundary_visible`; production evidence now treats missing LangChain provider-boundary visibility as a gap instead of accepting direct LLM readiness.
- Added a static regression test that fails if `LangGraphExecutor` or `DirectLLMExecutor` embeds `/chat/completions`, `call_deepseek_chat_completion`, `call_openai_responses`, or `langgraph_deepseek_stream`.
- Added provider-boundary files to the plan_v7 CI artifact wrapper's py_compile and diff-check file set.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/langchain_model_provider.py services/api/aiteamos_api/read/runtime_executors/langgraph_executor.py services/api/aiteamos_api/read/runtime_executors/direct_llm_executor.py services/api/aiteamos_api/read/execution_dispatch_service.py services/api/aiteamos_api/read/chat_action_planning_service.py services/api/aiteamos_api/read/provider_conformance_service.py scripts/plan_v7_ci_artifacts.py scripts/plan_v7_artifact_summary.py tests/test_execution_dispatch_contract.py tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_artifact_summary.py` -> passed.
- `python -m pytest tests/test_execution_dispatch_contract.py::test_direct_llm_executor_is_available_when_explicitly_selected tests/test_execution_dispatch_contract.py::test_langgraph_and_diagnostic_llm_executors_do_not_embed_native_deepseek_http tests/test_execution_dispatch_contract.py::test_langgraph_executor_does_not_use_pre_graph_direct_llm tests/test_execution_dispatch_contract.py::test_answer_only_defaults_to_universal_employee_agent_with_read_tools tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_artifact_summary.py -q` -> 17 passed.
- `python -m pytest tests/test_file_chat_routes.py::test_employee_chat_streams_universal_agent_deepseek_answer tests/test_file_chat_routes.py::test_employee_chat_uses_deepseek_tool_planner_for_create_employee tests/test_file_chat_routes.py::test_employee_chat_can_use_deepseek_ai_engine tests/test_file_chat_routes.py::test_remote_chat_does_not_fallback_to_local_ticket_heuristics_when_planner_fails tests/test_file_chat_routes.py::test_employee_chat_can_use_openai_ai_engine tests/test_file_chat_routes.py::test_employee_capability_question_uses_openai_agent_bundle_without_kernel_intercept tests/test_file_chat_routes.py::test_openai_auth_error_returns_configuration_blocker_without_stub_reply tests/test_file_chat_routes.py::test_openai_quota_error_returns_configuration_blocker_without_stub_reply tests/test_runtime_executor_routes.py::test_runtime_executor_registry_lists_backends_capabilities_and_setup_blockers tests/test_file_system_status_routes.py::test_system_status_reports_secret_health_without_settings_compat_route tests/test_file_system_status_routes.py::test_environment_smoke_script_outputs_redacted_readiness_payload tests/test_file_system_status_routes.py::test_provider_conformance_external_smoke_uses_configured_plane_and_graphiti_adapters -q` -> 12 passed.
- `langgraph validate --config langgraph.json` -> passed, 2 graphs found.
- `timeout 20s python scripts/live_provider_readiness_smoke.py --workspace-dir "$tmp" --output "$tmp/live_provider_readiness_smoke.json"` -> exited cleanly; summary `profile=core_loop`, `selected_executor_id=langgraph`, `readiness_status=blocked`, `repo_write_ready_count=1`.
- Static scan over primary executor/planner/dispatch paths found no remaining `ai_engine_clients`, `call_deepseek_chat_completion`, `call_openai_responses`, `/chat/completions`, or `langgraph_deepseek_stream` outside the new regression test assertions and unrelated external runtime adapter tests.
- `git diff --check -- pyproject.toml services/api/aiteamos_api/read/langchain_model_provider.py services/api/aiteamos_api/read/runtime_executors/langgraph_executor.py services/api/aiteamos_api/read/runtime_executors/direct_llm_executor.py services/api/aiteamos_api/read/execution_dispatch_service.py services/api/aiteamos_api/read/chat_action_planning_service.py services/api/aiteamos_api/read/provider_conformance_service.py services/api/aiteamos_api/read/ai_engine_clients.py scripts/plan_v7_ci_artifacts.py scripts/plan_v7_artifact_summary.py tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py tests/test_file_system_status_routes.py tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_artifact_summary.py plan_v7.md` -> passed.

Remaining gaps:

- `direct_llm` still exists by id for explicit diagnostic/compatibility use, but it no longer owns native DeepSeek/OpenAI HTTP calls and cannot satisfy core-loop completion.
- `chat_ai_engine_service` remains as AI Engine settings/configuration and provider blocker plumbing; it must not become a separate agent runtime.
- Real `core_loop` live provider dogfood remains blocked until Plane, Graphiti, provider secrets, and the mutation gate are intentionally opened.
- Existing frontend/system-status mock text may still use historical `Direct LLM Runtime Provider` wording in fixtures; product semantics now treat that surface as diagnostic compatibility only.

Next concrete module:

- With the direct LLM residue removed, the next production-readiness step is either an explicitly authorized `core_loop` live dogfood against the configured DeepSeek/LangChain/LangGraph provider path, or Track B/G reliability evidence for repeated Ticket-loop / Agent Server runs without mutating live providers.

Anti-Wheel Audit:

- No model HTTP client, agent loop, streaming protocol, checkpoint system, memory database, readiness platform, or CI runner was added.
- The slice deletes a hand-written model HTTP helper and strengthens evidence around the existing LangChain provider adapter, existing LangGraph runtime, existing Agent Server matrix, and existing artifact summary.
- AITeamOS remains focused on Ticket / Employees / Assets / Governance; LangGraph/LangChain own agent/model execution; Codex CLI remains optional repo-write adapter conformance.

### 2026-06-21: Track G/J queue worker long-soak artifact evidence

Status: completed for local deterministic long-soak Ticket loop worker evidence. Real live provider dogfood was not executed.

Goal: strengthen Ticket loop reliability evidence from a short daemon smoke into a repeatable long-soak artifact signal, without adding a second scheduler, worker, queue runner, or observability system.

Files changed:

- Updated `scripts/ticket_loop_queue_worker_smoke.py`.
- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `scripts/plan_v7_artifact_summary.py`.
- Updated `tests/test_plan_v7_ci_artifacts.py`.
- Updated `tests/test_plan_v7_artifact_summary.py`.
- Updated `plan_v7.md`.

What changed:

- Raised the default Ticket loop queue worker daemon smoke from 3 ticks to 6 ticks.
- Updated the default plan_v7 artifact wrapper to run `ticket_loop_queue_worker_smoke.py` with `--daemon-min-ticks 6`, `--daemon-interval-seconds 0.1`, and `--daemon-timeout-seconds 10`.
- Extended artifact summary queue worker evidence with `daemon_ticket_id`, `min_ticks`, `interval_seconds`, `timeout_seconds`, `queue_statuses`, `run_statuses`, `long_soak`, and `soak_passed`.
- Added evidence gaps for queue worker daemon failures, insufficient soak, or non-empty `last_error`.
- Added a negative artifact-summary test proving a short 3-tick daemon run now reports `queue_worker_daemon_soak_missing`.
- Added CI command tests so future edits cannot silently reduce the default queue worker soak back to a short smoke.

Validation:

- `python -m py_compile scripts/ticket_loop_queue_worker_smoke.py scripts/plan_v7_ci_artifacts.py scripts/plan_v7_artifact_summary.py tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_artifact_summary.py` -> passed.
- `python -m pytest tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_artifact_summary.py -q` -> 14 passed.
- `timeout 30s python scripts/ticket_loop_queue_worker_smoke.py --workspace-dir "$tmp" --output "$tmp/ticket_loop_queue_worker_smoke.json"` -> passed; emitted `daemon_status=passed`, `tick_delta=6`, `min_ticks=6`, `processed_delta=2`, `last_error=""`.
- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-queue-worker-long-soak --fail-fast` -> passed with 17 commands, including context retrieval smoke, Asset provenance smoke, Runtime Replay smoke, environment/runtime readiness smokes, focused runtime/Ticket-loop tests, 6-tick queue worker daemon smoke, `langgraph validate`, and `git diff --check`.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 1 --output /tmp/plan_v7_queue_worker_long_soak_summary.json` -> passed; latest run `local-v7-queue-worker-long-soak`, queue worker evidence `tick_delta=6`, `min_ticks=6`, `soak_passed=true`; latest gaps were only `agent_server_matrix_smoke_missing` and `live_provider_dogfood_missing` because this was the lightweight non-matrix profile.

Remaining gaps:

- This is deterministic local long-soak artifact evidence, not a real always-on deployment soak under live provider load.
- The default lightweight artifact run still omits Agent Server matrix evidence unless `--include-agent-server-matrix-smoke` or `--production-readiness` is used.
- Full production readiness still requires explicitly authorized fresh `core_loop` live provider dogfood with DeepSeek behind LangChain/LangGraph and Plane/Graphiti mutation readiness.

Next concrete module:

- Continue Track B/J by combining the 6-tick queue worker long-soak evidence with Agent Server matrix evidence in the production-readiness profile, or proceed to the explicitly authorized `core_loop` live provider dogfood when live provider mutation is intended.

Anti-Wheel Audit:

- No new scheduler, queue runner, worker daemon, agent loop, observability backend, artifact runner, or memory store was added.
- The slice reuses the existing Ticket loop queue worker, existing artifact wrapper, existing artifact summary, existing Runtime Replay/Ticket loop tests, and existing `langgraph validate`.
- Durable truth remains in Tickets, Ticket loop queue/runs, Ticket reports, Asset candidates, Runtime sessions, and approved Assets; the new fields only make the existing evidence harder to misread.

### 2026-06-21: Track H2 hard removal of DirectLLMExecutor from runtime registry

Status: completed for default runtime registry / dispatch / System Status / artifact fixture cleanup. Real live provider dogfood was not executed.

Goal: close the remaining architecture risk that future autonomous loops could treat a diagnostic `direct_llm` executor as an acceptable AITeamOS runtime path.

Files changed:

- Deleted `services/api/aiteamos_api/read/runtime_executors/direct_llm_executor.py`.
- Updated `services/api/aiteamos_api/read/execution_dispatch_service.py`.
- Updated `services/api/aiteamos_api/read/runtime_executors/__init__.py`.
- Updated `services/api/aiteamos_api/read/runtime_executors/universal_employee_agent_executor.py`.
- Updated `services/api/aiteamos_api/read/runtime_executor_smoke_service.py`.
- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `tests/test_execution_dispatch_contract.py`.
- Updated `tests/test_runtime_executor_routes.py`.
- Updated `tests/test_file_system_status_routes.py`.
- Updated `tests/test_plan_v7_artifact_summary.py`.
- Updated `apps/dashboard/src/__tests__/system-status-page.test.tsx`.
- Updated `plan_v7.md`.

What changed:

- Removed `DirectLLMExecutor` from default RuntimeExecutor construction and package exports.
- Removed `direct_llm` aliases from dispatch selection; legacy `executor_id=direct_llm` no longer creates a direct model executor and falls back into the Universal Employee Agent / LangGraph path for normal answer-only work.
- Deleted the DirectLLM executor implementation file.
- Removed `direct_llm_executor.py` from the default plan_v7 py_compile / diff-check artifact wrapper.
- Updated RuntimeExecutor smoke selection so DeepSeek-backed answer-only diagnostics apply to `langgraph` / `universal_employee_agent`, not a direct provider executor.
- Updated System Status, RuntimeExecutor registry, provider conformance, artifact summary fixtures, and frontend System Status fixtures so `direct_llm` no longer appears as a runtime/provider.
- Kept regression tests that assert `direct_llm` is absent from registry/status/provider evidence and that legacy input routes through LangGraph / Universal Employee Agent provider wiring.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/execution_dispatch_service.py services/api/aiteamos_api/read/runtime_executors/__init__.py services/api/aiteamos_api/read/runtime_executors/universal_employee_agent_executor.py services/api/aiteamos_api/read/runtime_executor_smoke_service.py scripts/plan_v7_ci_artifacts.py tests/test_execution_dispatch_contract.py tests/test_runtime_executor_routes.py tests/test_file_system_status_routes.py tests/test_plan_v7_artifact_summary.py` -> passed.
- `python -m pytest tests/test_execution_dispatch_contract.py::test_legacy_direct_llm_selection_falls_back_to_universal_agent tests/test_execution_dispatch_contract.py::test_langgraph_executors_do_not_embed_native_deepseek_http tests/test_execution_dispatch_contract.py::test_langgraph_executor_does_not_use_pre_graph_direct_llm tests/test_runtime_executor_routes.py::test_runtime_executor_registry_lists_backends_capabilities_and_setup_blockers tests/test_runtime_executor_routes.py::test_runtime_smoke_chooses_executor_compatible_action_for_deepseek_backends tests/test_file_system_status_routes.py::test_system_status_reports_secret_health_without_settings_compat_route tests/test_file_system_status_routes.py::test_provider_conformance_external_smoke_uses_configured_plane_and_graphiti_adapters tests/test_plan_v7_artifact_summary.py -q` -> 18 passed.
- `npm test -- system-status-page.test.tsx` in `apps/dashboard` -> 9 test files / 70 tests passed.
- `rg -n "direct_llm|DirectLLM|direct-llm|Direct LLM|direct_llm_executor" services scripts apps --glob '!node_modules/**' --glob '!dist/**' --glob '!build/**' --glob '!*.lock'` -> no matches.

Remaining gaps:

- Historical plan/test names still mention direct LLM only as negative regression context; future loops must treat the current section and section 0.1 as controlling over older historical notes.
- `chat_ai_engine_service` remains for AI Engine settings, provider config, selected model metadata, and provider blocker plumbing; it must not become an agent/runtime path.
- Full production readiness still requires explicitly authorized fresh `core_loop` live provider dogfood with DeepSeek behind LangChain/LangGraph and Plane/Graphiti mutation readiness.

Next concrete module:

- Continue Track B/J by combining 6-tick Ticket loop worker long-soak evidence with Agent Server matrix evidence, or proceed to explicitly authorized `core_loop` live provider dogfood when live provider mutation is intended.

Anti-Wheel Audit:

- No new model provider, agent loop, runtime dispatcher, smoke runner, observability system, memory store, checkpoint UI, or chat runtime was added.
- This slice removes a wheel-shaped compatibility executor and reuses the existing LangGraph / Universal Employee Agent path plus LangChain provider adapter.
- AITeamOS remains focused on Ticket / Employees / Assets / Governance; DeepSeek is only the temporary model provider behind LangGraph / LangChain; Codex CLI remains optional repo-write adapter conformance.

### 2026-06-21: Track B/G/J retained queue worker long-soak evidence

Status: completed for retained queue-worker long-soak summary gates. Real live provider dogfood was not executed.

Goal: make production-readiness summaries retain the latest valid Ticket loop queue worker long-soak evidence alongside Agent Server matrix evidence and live provider dogfood evidence, so lightweight runs cannot hide missing queue reliability proof.

Files changed:

- Updated `scripts/plan_v7_artifact_summary.py`.
- Updated `tests/test_plan_v7_artifact_summary.py`.
- Updated `plan_v7.md`.

What changed:

- `retained_evidence` now retains three independent production-readiness signals across the inspected artifact window:
  - `agent_server`
  - `queue_worker_daemon`
  - `live_provider_dogfood`
- `retained_evidence_gaps` now reports `queue_worker_daemon_missing`, `queue_worker_daemon_soak_missing`, daemon status gaps, or daemon `last_error` gaps when no retained queue-worker long-soak evidence is available.
- Added fixture helper coverage for valid 6-tick queue-worker long-soak evidence.
- Added regression coverage proving:
  - a newer Agent Server / dogfood run can retain queue-worker long-soak evidence from a previous run;
  - a retained short 3-tick queue run fails the retained summary gate.
- Kept the implementation inside the existing artifact summary model; no new runner, scheduler, worker, observability store, or readiness platform was added.

Validation:

- `python -m py_compile scripts/plan_v7_artifact_summary.py tests/test_plan_v7_artifact_summary.py` -> passed.
- `python -m pytest tests/test_plan_v7_artifact_summary.py -q` -> 13 passed.
- `python -m pytest tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_artifact_summary.py -q` -> 16 passed.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 10 --output /tmp/plan_v7_retained_queue_worker_summary.json` -> passed.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 10 --fail-on-retained-evidence-gaps --output /tmp/plan_v7_retained_queue_worker_strict_summary.json` -> exited `4`, as expected for the current historical artifact window.

Observed current artifact window:

- Retained keys are now `agent_server`, `queue_worker_daemon`, and `live_provider_dogfood`.
- Retained `queue_worker_daemon.soak_passed=true`, sourced from `local-v7-queue-worker-long-soak`.
- Retained gaps remain:
  - `agent_server_coverage:langchain_provider_boundary_visible_missing`
  - `live_provider_dogfood_not_completed`

Remaining gaps:

- The retained queue-worker long-soak evidence is now stable, but current retained Agent Server evidence is from an older artifact window that does not satisfy the newer LangChain provider-boundary gate.
- Current retained live dogfood evidence is not completed; full production readiness still requires explicitly authorized fresh `core_loop` live provider dogfood with DeepSeek behind LangChain/LangGraph and Plane/Graphiti mutation readiness.
- A fresh production-readiness artifact run should now include current direct-LLM-free RuntimeExecutor registry evidence, current LangChain provider-boundary visibility, retained/actual queue-worker long-soak, and explicit live dogfood status.

Next concrete module:

- Run or broaden the non-mutating production-readiness profile so retained Agent Server matrix evidence is refreshed under the current LangChain provider-boundary and DirectLLM-free registry constraints; then proceed to explicitly authorized `core_loop` live provider dogfood when live provider mutation is intended.

Anti-Wheel Audit:

- No new scheduler, queue runner, CI runner, artifact system, readiness platform, agent loop, memory database, checkpoint UI, or observability backend was added.
- The slice reuses the existing Ticket loop queue worker smoke, existing Agent Server matrix artifacts, existing live provider dogfood artifacts, and existing plan_v7 artifact summary gate.
- AITeamOS remains focused on Ticket / Employees / Assets / Governance; LangGraph/LangChain own the loop/model-provider boundary; Codex CLI remains optional repo-write adapter conformance.

### 2026-06-21: Track B/H2/J production-readiness refresh and runtime-registry guard

Status: completed for non-mutating production-readiness refresh and direct-runtime regression guard. Real live provider dogfood was not executed.

Goal: lock the current boundary into evidence so future autonomous loops cannot accidentally treat direct LLM or repo-write adapter evidence as LangGraph core-loop completion.

Files changed:

- Updated `scripts/plan_v7_artifact_summary.py`.
- Updated `tests/test_plan_v7_artifact_summary.py`.
- Updated `plan_v7.md`.
- Generated evidence under `.aiteamos/artifacts/plan_v7/local-v7-production-readiness-refresh-current-boundary/`.

What changed:

- Ran the non-mutating `--production-readiness` artifact profile under the current LangChain provider-boundary and DirectLLM-free registry constraints.
- Confirmed latest Agent Server matrix evidence is complete: read-only, answer-only, provider blocker, approval interrupt/resume, evidence requested, rejected, changes requested, and LangChain provider-boundary visibility.
- Confirmed latest queue worker evidence includes a 6-tick long-soak daemon run with `soak_passed=true`.
- Confirmed latest RuntimeExecutor registry is direct-free and selects `langgraph` for live provider core-loop readiness; optional repo-write adapters remain visible only as adapters.
- Added artifact-summary regression gaps:
  - `runtime_registry_direct_llm_present`
  - `runtime_registry_core_loop_not_langgraph`
- Added a negative test proving production-readiness summary fails if `direct_llm` returns to latest runtime registry evidence or if core-loop selected executor is not `langgraph`.

Validation:

- `python scripts/plan_v7_ci_artifacts.py --run-id local-v7-production-readiness-refresh-current-boundary --production-readiness --fail-fast` -> exited `2` because the final summary gate correctly failed on missing live dogfood. The non-mutating main commands passed before the gate.
- `.aiteamos/artifacts/plan_v7/local-v7-production-readiness-refresh-current-boundary/production_readiness_summary.json` -> latest inspected evidence `latest_status=passed`, `latest_evidence_gaps=["live_provider_dogfood_missing"]`, retained gaps `["live_provider_dogfood_not_completed"]`.
- Latest runtime registry evidence: executor ids are `local_tool`, `universal_employee_agent`, `langgraph`, `claude_agent_sdk`, `claude_code`, `codex_cli`, `cursor`, `openhands`, `opencode`; selected core-loop executor is `langgraph`; `direct_llm` is absent.
- `python -m py_compile scripts/plan_v7_artifact_summary.py tests/test_plan_v7_artifact_summary.py` -> passed.
- `python -m pytest tests/test_plan_v7_artifact_summary.py -q` -> 14 passed.
- `python -m pytest tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_artifact_summary.py -q` -> 17 passed.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 1 --output /tmp/plan_v7_latest_after_registry_guard.json` -> ran and reported the latest wrapper manifest as failed only because the post summary gate failed on missing live dogfood.
- `rg -n "direct_llm|DirectLLM|direct-llm|Direct LLM|direct_llm_executor" services scripts apps --glob '!node_modules/**' --glob '!dist/**' --glob '!build/**' --glob '!*.lock'` -> only current artifact-summary guard code mentions `direct_llm`; production implementation paths remain direct-free.

Remaining gaps:

- Full production readiness is still not complete because fresh live provider dogfood has not completed.
- The next live dogfood must be `core_loop` with selected executor `langgraph`, DeepSeek behind LangChain/LangGraph, and Plane/Graphiti/provider mutation readiness intentionally opened.
- Historical production-readiness summaries may still contain old `direct_llm` strings in retained historical `runs` entries; current/latest runtime registry evidence is direct-free, and the new summary guard prevents future latest-registry regression.
- `chat_ai_engine_service` remains allowed only for AI Engine settings, selected model metadata, provider config, and blocker visibility; it must not become a separate runtime.

Next concrete module:

- Run explicitly authorized `core_loop` live provider dogfood when live mutation is intended:
  - selected executor: `langgraph`
  - model provider: DeepSeek behind LangChain/LangGraph
  - durable truth: Ticket / Employees / Assets / Governance
  - projection/recall: Graphiti only from approved Assets
- If live mutation is not intended, continue Track B/G/J with repeated Ticket-loop / Agent Server reliability evidence while keeping the same direct-free registry gate.

Anti-Wheel Audit:

- No new agent loop, model client, scheduler, summary platform, observability backend, chat runtime, memory database, or provider checker was added.
- The slice reuses the existing plan_v7 artifact summary, existing Agent Server matrix, existing queue worker smoke, existing RuntimeExecutor registry smoke, existing LangGraph runtime, and existing LangChain model-provider boundary.
- AITeamOS remains focused on Ticket / Employees / Assets / Governance; LangGraph owns orchestration; LangChain owns provider wiring; DeepSeek is only the temporary LLM provider; Codex CLI remains an optional repo-write adapter.

### 2026-06-21: Track B/H2/J live core-loop production-readiness closure

Status: completed for fresh LangGraph core-loop live provider dogfood and production-readiness summary gate. This does not complete all of v7; it closes the previously blocking live-dogfood evidence gap.

Goal: prove the production-readiness path with LangGraph as the core loop, DeepSeek only behind LangChain/LangGraph model-provider wiring, Plane as Ticket backend, approved Assets/Memory as durable truth, and Graphiti as projection/recall.

Files changed:

- Updated `scripts/plan_v7_artifact_summary.py`.
- Updated `tests/test_plan_v7_artifact_summary.py`.
- Updated `plan_v7.md`.
- Generated live evidence under `.aiteamos/artifacts/plan_v7/local-v7-production-readiness-live-core-loop/`.
- Created/updated governed live-provider data for Ticket `ops-0014`, approved Asset/Memory `mem-baa1c8dcff53`, and Graphiti projection/recall evidence.

What changed:

- Ran a read-only core-loop readiness preflight; Plane Ticket backend, Graphiti memory backend, LangGraph executor, and DeepSeek LangChain provider config were ready. The only blocker was the mutation gate.
- Executed the opt-in live provider dogfood with `AITEAMOS_LIVE_PROVIDER_DOGFOOD=1`, profile `core_loop`, executor `langgraph`, and Ticket `ops-0014`.
- The live run completed through LangGraph Workbench:
  - LangGraph thread: `019ee628-c16b-7532-99d5-29d3927d298f`
  - Workbench runtime run: `run-e97707f3ea39`
  - Runtime dogfood status: `completed`
  - Workbench runtime status: `completed`
  - Memory candidate / AssetRecord: `mem-baa1c8dcff53`
  - Graphiti projection status: `ingested`
  - Graphiti recall count: `2`
- Ran the full non-frontend production-readiness artifact wrapper with live dogfood included. The wrapper passed 27 commands and the final strict summary gate.
- Strengthened `plan_v7_artifact_summary.py` so live dogfood evidence now exposes:
  - `profile`
  - `executor_id`
  - `langgraph_thread_id`
  - `workbench_runtime_run_id`
  - `memory_candidate_ids`
  - `asset_record_ids`
  - `graphiti_projection_statuses`
  - `graphiti_recall_count`
  - `recall_result_count`
- Added guard gaps so repo-write adapter dogfood cannot satisfy core-loop production readiness:
  - `live_provider_dogfood_profile_not_core_loop`
  - `live_provider_dogfood_executor_not_langgraph`
  - `live_provider_dogfood_runtime_not_completed`
- Added regression coverage proving a completed `repo_write_adapter` / `codex_cli` dogfood still fails production-readiness evidence gates.

Validation:

- `python scripts/live_provider_dogfood.py --readiness --profile core-loop --executor-id langgraph --output /tmp/plan_v7_live_core_loop_readiness.json` -> returned blocked only by mutation gate; Ticket backend ready, memory backend ready, selected executor `langgraph` passed.
- `python scripts/live_provider_readiness_smoke.py --profile core-loop --executor-id langgraph --output /tmp/plan_v7_live_provider_readiness_smoke_current.json` -> passed readiness smoke with `readiness_status=blocked` only because the mutation gate was not opened.
- `python scripts/environment_smoke.py --output /tmp/plan_v7_environment_smoke_current.json` -> completed; DeepSeek LangChain provider config inspected, no external LLM call in smoke, LangGraph runtime ready, Plane/Graphiti provider checks visible.
- `AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --profile core-loop --executor-id langgraph --output /tmp/plan_v7_live_core_loop_dogfood.json` -> `status=completed`, `profile=core_loop`, `ticket=ops-0014`, `asset_record_ids=["mem-51888b331ce9"]`, Graphiti projection `ingested`.
- `AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/plan_v7_ci_artifacts.py --run-id local-v7-production-readiness-live-core-loop --production-readiness --include-live-provider-dogfood --live-provider-profile core-loop --live-provider-executor-id langgraph --live-provider-ticket-id ops-0014 --fail-fast` -> passed with 27 commands.
- `.aiteamos/artifacts/plan_v7/local-v7-production-readiness-live-core-loop/production_readiness_summary.json` -> latest run `local-v7-production-readiness-live-core-loop`, latest status `passed`, latest evidence gaps `[]`, retained evidence gaps `[]`.
- Latest runtime registry evidence remains direct-free and selects `langgraph`; executor ids are `local_tool`, `universal_employee_agent`, `langgraph`, `claude_agent_sdk`, `claude_code`, `codex_cli`, `cursor`, `openhands`, `opencode`.
- Latest Agent Server matrix coverage is complete and LangChain provider-boundary visibility is true.
- Latest queue worker long-soak evidence has `soak_passed=true`.
- `python -m pytest tests/test_plan_v7_artifact_summary.py -q` -> 15 passed.
- `python -m pytest tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_artifact_summary.py -q` -> 18 passed.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 1 --fail-on-evidence-gaps --output /tmp/plan_v7_summary_latest_live_core_loop_guarded.json` -> passed with no latest or retained gaps.
- `git diff --check -- scripts/plan_v7_artifact_summary.py tests/test_plan_v7_artifact_summary.py plan_v7.md` -> passed.
- `rg -n "direct_llm|DirectLLM|direct-llm|Direct LLM|direct_llm_executor" services scripts apps --glob '!node_modules/**' --glob '!dist/**' --glob '!build/**' --glob '!*.lock'` -> only artifact-summary guard code mentions `direct_llm`; production implementation paths remain direct-free.

Remaining gaps:

- This closes the live-provider production-readiness evidence gap, but v7 still needs broader hardening before the full objective is complete.
- Frontend build/tests were not run in this slice because no frontend code changed.
- Long-running always-on deployment soak, repeated queued Ticket-loop under live provider load, richer Employee work-history/handoff policy, and further Chat runtime decomposition remain future production-hardening work.
- Optional repo-write adapter conformance remains separate; Codex CLI readiness is visible but does not count as core-loop completion.

Next concrete module:

- Continue Track B/G/J by adding repeated queued Ticket-loop live/Agent Server reliability coverage, or Track F by deepening Employee work-history / load-driven handoff evidence now that core-loop live dogfood is proven.
- Keep section 0.2 as the active gate: future production-readiness must keep latest live dogfood `profile=core_loop`, `executor_id=langgraph`, runtime status `completed`, and direct LLM absent.

Anti-Wheel Audit:

- No new agent loop, model client, scheduler, memory database, checkpoint system, Chat UI runtime, provider adapter, observability platform, or CI runner was added.
- The slice reused existing LangGraph Workbench, LangChain provider boundary, Plane Ticket adapter, governed MemoryCandidate / AssetReview / AssetRecord flows, Graphiti projection/recall, existing Agent Server matrix, existing queue worker smoke, and existing artifact summary gate.
- AITeamOS remained responsible for Ticket / Employees / Assets / Governance; LangGraph owned orchestration; LangChain owned model-provider wiring; DeepSeek was only the temporary LLM provider; Codex CLI stayed an optional repo-write adapter.

### 2026-06-21: Track G/J repeated Ticket-loop reliability evidence gate

Status: completed for artifact-summary evidence strengthening around repeated Ticket-loop failure policy. No runtime worker, scheduler, agent loop, or live-provider mutation was added in this slice.

Goal: make production-readiness evidence prove that the Ticket loop queue worker can surface repeated blocked/failed work into governed policy action and Asset candidate evidence, instead of only proving that a daemon ticked for a short soak window.

Files changed:

- Updated `scripts/plan_v7_artifact_summary.py`.
- Updated `tests/test_plan_v7_artifact_summary.py`.
- Updated `plan_v7.md`.

What changed:

- Extended queue-worker daemon evidence extraction to include:
  - `queue_ids`
  - `processed_statuses`
  - `failed_delta`
  - `after_reliability_status`
  - `after_reliability_failed_count`
  - `asset_candidate_ids`
  - `policy_action_kinds`
  - `worker_processed_delta`
  - `worker_policy_action_delta`
  - `repeated_failure_policy_evidence`
- Added artifact-summary gap `queue_worker_repeated_failure_policy_missing` when repeated failures do not produce the expected failure-retrospective policy action and Asset candidate evidence.
- Strengthened tests so a passing production-readiness summary must prove repeated blocked/failed queue work, a failed-count delta, a failure retrospective action, and generated Asset candidate refs.
- Kept this as an evidence gate over the existing queue-worker smoke output; the queue worker and Ticket-loop service behavior were not reimplemented.

Latest evidence from `.aiteamos/artifacts/plan_v7/local-v7-production-readiness-live-core-loop/`:

- `queue_worker_daemon.status="passed"`
- `queue_worker_daemon.soak_passed=true`
- `processed_statuses=["blocked","blocked"]`
- `failed_delta=2`
- `after_reliability_status="error"`
- `after_reliability_failed_count=2`
- `asset_candidate_ids=["asset-candidate-ticket-loop-failure-retrospective-ops-0001"]`
- `policy_action_kinds=["failure_retrospective_candidate"]`
- `worker_processed_delta=2`
- `worker_policy_action_delta=1`
- `repeated_failure_policy_evidence=true`

Validation:

- `python -m py_compile scripts/plan_v7_artifact_summary.py tests/test_plan_v7_artifact_summary.py` -> passed.
- `python -m pytest tests/test_plan_v7_artifact_summary.py -q` -> 15 passed.
- `python -m pytest tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_artifact_summary.py -q` -> 18 passed.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 1 --fail-on-evidence-gaps --output /tmp/plan_v7_summary_latest_worker_reliability_guarded.json` -> passed with no latest evidence gaps.

Remaining gaps:

- This is deterministic artifact evidence over the current queue-worker smoke, not a replacement for an always-on deployment soak.
- Repeated queued Ticket-loop reliability under real live-provider load is still future evidence.
- Employee work-history / handoff policy and Chat runtime decomposition remain unfinished v7 hardening areas.

Next concrete module:

- Continue Track F by deepening Employee work-history / load-driven handoff evidence, or Track B/G by running repeated queued Ticket-loop reliability through Agent Server / live-provider conditions while keeping LangGraph as the core loop.

Anti-Wheel Audit:

- No new scheduler, worker, agent loop, memory database, observability platform, provider adapter, or queue system was added.
- The slice reuses the existing queue-worker smoke artifact, existing production-readiness summary, existing tests, and existing AITeamOS Ticket / Asset candidate policy actions.
- AITeamOS remains focused on Ticket / Employees / Assets / Governance; LangGraph owns orchestration; LangChain owns provider wiring; DeepSeek stays only the temporary model provider; Codex CLI stays an optional repo-write adapter.

### 2026-06-21: Track F memory-scope and risk-aware Employee handoff policy

Status: completed for deterministic Employee handoff policy hardening around memory scope and risk boundary. This does not complete all of Track F; it closes one routing-quality gap inside the existing handoff service and LangGraph handoff call sites.

Goal: make Employee routing more like real team assignment by considering whether a candidate Employee is allowed for the required memory scope and risk level, while keeping LangGraph as the orchestration runtime and AITeamOS Tickets / Employees / Assets / Governance as durable truth.

Files changed:

- Updated `services/api/aiteamos_api/read/employee_handoff_service.py`.
- Updated `services/api/aiteamos_api/agents/workbench/nodes/handoff.py`.
- Updated `services/api/aiteamos_api/read/runtime_executors/langgraph_executor.py`.
- Updated `tests/test_execution_dispatch_contract.py`.
- Updated `plan_v7.md`.

What changed:

- Extended `choose_employee_for_goal()` with optional `required_memory_scopes` and `risk_level` inputs.
- Added deterministic goal-derived context:
  - `employee:<id>` scoped context becomes a required memory scope.
  - `global` / `aiteamos` scope hints are recognized.
  - production/destructive/credential/payment language maps to `critical` risk.
  - deploy/release/migration/write/external/security language maps to `high` risk when no stronger signal exists.
- Existing `memory_scopes` on Employee profiles and `handoff_policy.memory_scopes` now influence eligibility and scoring.
- Existing `handoff_policy.max_risk_level` / `risk_boundary` / `max_risk` now constrains eligibility.
- Decision `policy` now exposes auditable routing facts:
  - `required_memory_scopes`
  - `matched_memory_scopes`
  - `available_memory_scopes`
  - `memory_scope_match`
  - `risk_level`
  - `max_risk_level`
  - `risk_allowed`
- Existing Workbench handoff node and Universal Employee Agent / LangGraph executor now pass through `task_context.required_memory_scopes` and `task_context.risk_level` when present; otherwise the service derives them from the goal text.
- Added regression coverage proving a high-risk production RD handoff with `employee:victor` scoped context routes to the Employee whose memory scope and risk boundary allow that work.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/employee_handoff_service.py services/api/aiteamos_api/agents/workbench/nodes/handoff.py services/api/aiteamos_api/read/runtime_executors/langgraph_executor.py tests/test_execution_dispatch_contract.py` -> passed.
- `pytest tests/test_execution_dispatch_contract.py -k "choose_employee_for_goal" -q` -> 5 passed.
- `pytest tests/test_execution_dispatch_contract.py -q` -> 96 passed.
- `pytest tests/test_aiteamos_workbench_graph.py -k "handoff or structured_state or graph" -q` -> 10 passed.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 1 --fail-on-evidence-gaps --output /tmp/plan_v7_summary_after_employee_handoff_policy.json` -> passed with no latest evidence gaps.
- `rg -n "direct_llm|DirectLLM|direct-llm|Direct LLM|direct_llm_executor" services scripts apps --glob '!node_modules/**' --glob '!dist/**' --glob '!build/**' --glob '!*.lock'` -> only artifact-summary guard code mentions `direct_llm`; production implementation paths remain direct-free.
- `git diff --check -- services/api/aiteamos_api/read/employee_handoff_service.py services/api/aiteamos_api/agents/workbench/nodes/handoff.py services/api/aiteamos_api/read/runtime_executors/langgraph_executor.py tests/test_execution_dispatch_contract.py plan_v7.md` -> passed.
- Observed warnings were pre-existing dependency/runtime warnings from FastAPI/Starlette, Graphiti/Pydantic, and an aiosqlite thread warning during the broader execution contract test run; they did not fail the suite.

Remaining gaps:

- Employee capability growth, long-term quality feedback, memory-boundary UI, and full Employee detail work-history panels remain unfinished.
- The current routing policy is deterministic and conservative; richer semantic routing should still be provided by LangGraph / mature model runtime, not by creating a custom AITeamOS agent loop.
- Live-provider dogfood has not yet specifically proven memory-scope/risk-aware handoff under a real Ticket run.

Next concrete module:

- Continue Track F by projecting memory-scope / risk-boundary handoff facts into Employee detail UI and Runtime Replay, or add a focused Agent Server smoke proving these policy fields survive a full Clara -> Ticket -> handoff graph run.

Anti-Wheel Audit:

- No new agent loop, scheduler, memory database, risk engine, permission engine, provider adapter, or Chat runtime was added.
- The slice reuses the existing Employee profiles, handoff service, Ticket-backed work ledger, current-load projection, Workbench handoff node, Universal Employee Agent executor, and existing execution contract tests.
- Durable truth remains in Employees, Tickets, Ticket handoff/report events, Assets, Governance, and Graphiti projection only after Asset approval; LangGraph remains the runtime orchestrator and DeepSeek remains only the temporary provider behind LangGraph/LangChain.

### 2026-06-21: Track B/F Agent Server handoff-policy evidence gate

Status: completed for production-compatible Agent Server evidence that memory-scope/risk-aware Employee handoff policy survives a full Workbench graph run. This does not complete all of v7; it closes the previous Track F next-step gap and strengthens Track B production-readiness coverage.

Goal: prove the path Clara -> Ticket -> LangGraph Agent Server -> Universal Employee Agent -> durable Ticket handoff preserves target Employee, memory-scope match, risk level, risk allowance, and Ticket handoff references without adding a custom AITeamOS agent loop.

Files changed:

- Updated `scripts/langgraph_agent_server_smoke.py`.
- Updated `scripts/langgraph_agent_server_ci_smoke.py`.
- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `scripts/plan_v7_artifact_summary.py`.
- Updated `tests/test_plan_v7_ci_artifacts.py`.
- Updated `tests/test_plan_v7_artifact_summary.py`.
- Updated `plan_v7.md`.

What changed:

- Added optional handoff assertions to the Agent Server smoke:
  - expected target Employee
  - expected handoff status
  - expected matched memory scope
  - expected risk level
  - expected risk allowance
  - minimum durable Ticket handoff refs
- Added CI-smoke seeding for temporary Clara/Alex/Victor profiles inside the smoke workspace only. Victor is configured with `employee:victor` memory scope and `critical` risk allowance; Alex remains intentionally narrower, so the smoke proves policy-driven selection instead of default routing.
- Added `agent_server_handoff_policy_smoke` to the default production-readiness matrix.
- Extended artifact summary extraction with `handoff_policy_memory_risk` coverage and handoff fields:
  - `handoff_target_employee_id`
  - `handoff_status`
  - `handoff_matched_memory_scopes`
  - `handoff_risk_level`
  - `handoff_risk_allowed`
  - `ticket_handoff_ref_count`
- Updated tests and fixtures so the Agent Server matrix is now an 8-case matrix.

Validation:

- `python -m py_compile scripts/langgraph_agent_server_smoke.py scripts/langgraph_agent_server_ci_smoke.py scripts/plan_v7_ci_artifacts.py scripts/plan_v7_artifact_summary.py tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_artifact_summary.py` -> passed.
- `pytest tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_artifact_summary.py -q` -> 18 passed.
- Focused fresh Agent Server handoff-policy smoke -> passed with `handoff_target_employee_id=victor`, `handoff_status=durable_handoff_recorded`, matched scope `employee:victor`, `handoff_risk_level=critical`, `handoff_risk_allowed=true`, and `ticket_handoff_ref_count=1`.
- `AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/plan_v7_ci_artifacts.py --run-id local-v7-production-readiness-handoff-policy --production-readiness --include-live-provider-dogfood --live-provider-profile core-loop --live-provider-executor-id langgraph --live-provider-ticket-id ops-0014 --fail-fast` -> passed, 28 commands.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 1 --fail-on-evidence-gaps --output /tmp/plan_v7_summary_latest_handoff_policy.json` -> passed with no latest evidence gaps.
- `rg -n "direct_llm|DirectLLM|direct-llm|Direct LLM|direct_llm_executor" services scripts apps --glob '!node_modules/**' --glob '!dist/**' --glob '!build/**' --glob '!*.lock'` -> only artifact-summary guard code mentions `direct_llm`; production implementation paths remain direct-free.

Latest evidence snapshot:

- latest run id: `local-v7-production-readiness-handoff-policy`
- latest status: `passed`
- latest evidence gaps: `[]`
- Agent Server matrix: 8/8 cases passed
- `handoff_policy_memory_risk=true`
- handoff target: `victor`
- handoff status: `durable_handoff_recorded`
- matched memory scopes: `employee:victor`
- risk level: `critical`
- risk allowed: `true`
- durable Ticket handoff refs: 1
- live profile: `core_loop`
- live executor: `langgraph`
- live runtime status: `completed`
- live memory candidate: `mem-9657552108bf`
- Graphiti projection status: `ingested`

Remaining gaps:

- This proves deterministic workspace profiles through Agent Server; it does not yet prove natural handoff quality under the real long-lived team profile set and live-provider workload.
- Employee capability growth, long-term quality feedback, Employee detail UI, and Runtime Replay surfacing for handoff policy facts remain unfinished.
- Repeated queued Ticket-loop reliability under Agent Server/live-provider load remains a separate production-hardening gap.

Next concrete module:

- Project handoff target / memory-scope / risk-boundary facts into Runtime Replay and Employee detail UI, or run a live-provider natural handoff dogfood with real team profiles while keeping `executor_id=langgraph` and DeepSeek only behind LangGraph/LangChain.

Anti-Wheel Audit:

- No new agent loop, memory database, risk engine, provider adapter, queue system, or custom Chat runtime was added.
- The slice reuses LangGraph Agent Server, the existing Workbench graph, existing Universal Employee Agent executor, existing Employee handoff service, existing Ticket handoff/report refs, and existing artifact-summary gate.
- AITeamOS remains focused on Ticket / Employees / Assets / Governance; LangGraph owns orchestration; LangChain owns model-provider wiring; DeepSeek stays only the temporary model provider; Codex CLI stays an optional repo-write adapter.

### 2026-06-21: Track F/J handoff policy replay and Employee boundary UI

Status: completed for projecting memory-scope/risk-aware handoff facts into Runtime Replay and Employee detail UI. This does not complete all of v7; it closes the previous Runtime Replay / Employee detail surfacing gap for handoff policy facts.

Goal: make the already-proven handoff policy facts visible to humans during replay and Employee inspection, while keeping LangGraph as the runtime owner and AITeamOS Tickets / Employees / Assets / Governance as durable truth.

Files changed:

- Updated `services/api/aiteamos_api/read/execution_replay_service.py`.
- Updated `services/api/aiteamos_api/read/execution_result_ingestion_service.py`.
- Updated `services/api/aiteamos_api/read/runtime_executor_routes.py`.
- Updated `services/api/aiteamos_api/read/ticket_service.py`.
- Updated `apps/dashboard/src/api/runtimeExecutors.ts`.
- Updated `apps/dashboard/src/components/runtimeReplay.tsx`.
- Updated `apps/dashboard/src/pages/employees/index.tsx`.
- Updated `apps/dashboard/src/__tests__/runtime-page.test.tsx`.
- Updated `apps/dashboard/src/__tests__/employees-page.test.tsx`.
- Updated `tests/test_runtime_executor_routes.py`.
- Updated `plan_v7.md`.

What changed:

- Runtime Replay now returns a top-level `handoff_summary` with schema `execution_replay_handoff_policy.v1`.
- The replay summary extracts handoff facts from existing sources in this order:
  - execution artifact `employee_handoff_request`
  - native LangGraph checkpoint state
  - approval/state snapshot learning delta
- Replay coverage now exposes non-required `handoff` and `handoff_policy` coverage flags plus `handoff_ref_count`.
- Runtime Replay UI now renders a `Handoff Policy` panel with source Employee, target Employee, scope match, required/matched/available memory scopes, risk level, risk boundary, policy payload, and refs.
- Employee work ledger handoffs now include the actor, source Employee, and target Employee perspectives, so the receiving Employee can see inbound Ticket handoffs instead of only the actor seeing them.
- Employee detail UI now has a `Memory & Handoff Boundary` panel showing memory scopes, handoff readiness, accepted/preferred lanes, risk boundary, max active Tickets, escalation target, and preferred runtime.
- Employee handoff ledger rows now show relation, from -> to, source run, and content.
- Execution artifacts now persist `learning_delta` so replay can reuse existing runtime facts without re-running graph logic.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/execution_replay_service.py services/api/aiteamos_api/read/execution_result_ingestion_service.py services/api/aiteamos_api/read/runtime_executor_routes.py services/api/aiteamos_api/read/ticket_service.py tests/test_runtime_executor_routes.py` -> passed.
- `pytest tests/test_runtime_executor_routes.py -k "runtime_execution_sessions_list_checkpoint_and_replay_refs" -q` -> 1 passed, 19 deselected.
- `npx vitest run --environment jsdom src/__tests__/employees-page.test.tsx src/__tests__/runtime-page.test.tsx` from `apps/dashboard` -> 7 passed.
- `npm -C apps/dashboard run build` -> passed.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 1 --fail-on-evidence-gaps --output /tmp/plan_v7_summary_after_handoff_replay_ui.json` -> passed with no latest evidence gaps.
- `rg -n "direct_llm|DirectLLM|direct-llm|Direct LLM|direct_llm_executor" services scripts apps --glob '!node_modules/**' --glob '!dist/**' --glob '!build/**' --glob '!*.lock'` -> only artifact-summary guard code mentions `direct_llm`; production implementation paths remain direct-free.

Remaining gaps:

- Runtime Replay now surfaces handoff policy facts for replayed sessions, but the v7 artifact smoke does not yet assert `handoff_summary` directly.
- Employee detail now shows boundary facts and inbound/outbound handoffs, but full Employee detail UI is still not complete: capability growth history, quality trend over time, and richer profile evolution remain unfinished.
- Live-provider natural handoff dogfood with real long-lived team profiles remains unproven.
- Repeated queued Ticket-loop reliability under Agent Server/live-provider load remains a separate production-hardening gap.

Next concrete module:

- Add Runtime Replay smoke/artifact summary coverage for `handoff_summary`, or run live-provider natural handoff dogfood with real team profiles while keeping `executor_id=langgraph` and DeepSeek only behind LangGraph/LangChain.

Anti-Wheel Audit:

- No new agent loop, replay engine, memory database, risk engine, provider adapter, queue system, or custom Chat runtime was added.
- The slice reuses existing ExecutionReplayService, execution artifact store, LangGraph checkpoint history, Ticket work ledger, Employee profiles, Runtime Replay component, Employees page, and existing tests.
- AITeamOS remains focused on Ticket / Employees / Assets / Governance; LangGraph owns orchestration; LangChain owns model-provider wiring; DeepSeek stays only the temporary model provider; Codex CLI stays an optional repo-write adapter.

### 2026-06-21: Track J runtime replay handoff-summary evidence gate

Status: completed for making Runtime Replay handoff policy facts part of the production-readiness artifact gate. This closes the previous gap where humans could see `handoff_summary`, but the v7 smoke / summary gate did not yet assert it.

Goal: ensure future Goal-mode loops cannot drift away from the LangGraph -> Ticket handoff evidence path by requiring replay artifacts to prove target Employee, memory-scope match, risk boundary, and replay refs.

Files changed:

- Updated `scripts/runtime_replay_eval_smoke.py`.
- Updated `scripts/plan_v7_artifact_summary.py`.
- Updated `tests/test_plan_v7_artifact_summary.py`.
- Updated `plan_v7.md`.

What changed:

- `runtime_replay_eval_smoke.py` now seeds an existing `employee_handoff_request` execution artifact for `alex -> victor` with `employee:victor` scoped memory and `critical` risk policy.
- The smoke asserts `handoff_summary.schema`, `status`, source kind, target Employee, required/matched memory scopes, scope match, risk level, max risk, risk allowance, handoff refs, and the `employee_handoff_request` timeline event.
- The smoke summary now emits `handoff`, `handoff_policy`, `handoff_status`, target Employee, lane, memory-scope fields, risk fields, `handoff_ref_count`, and refs for artifact summary consumption.
- `plan_v7_artifact_summary.py` now extracts those Runtime Replay handoff fields and reports evidence gaps when latest replay smoke is missing handoff summary, missing handoff policy, or has incomplete target/scope/risk/ref facts.
- Added regression coverage proving old-format replay smoke without handoff summary fails the latest evidence gate.
- Generated fresh production-readiness evidence under run id `local-v7-runtime-replay-handoff-summary`; latest artifact summary now has no evidence gaps.

Validation:

- `python -m py_compile scripts/runtime_replay_eval_smoke.py scripts/plan_v7_artifact_summary.py tests/test_plan_v7_artifact_summary.py` -> passed.
- `pytest tests/test_plan_v7_artifact_summary.py -q` -> 16 passed.
- `python scripts/runtime_replay_eval_smoke.py --workspace-dir /tmp/aiteamos-runtime-replay-handoff-summary-smoke --output /tmp/runtime_replay_handoff_summary_smoke.json` -> passed with `handoff_target_employee_id=victor`, matched scope `employee:victor`, `handoff_risk_level=critical`, `handoff_risk_allowed=true`, and `handoff_ref_count=4`.
- `AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/plan_v7_ci_artifacts.py --run-id local-v7-runtime-replay-handoff-summary --production-readiness --include-live-provider-dogfood --live-provider-profile core-loop --live-provider-executor-id langgraph --live-provider-ticket-id ops-0014 --fail-fast` -> passed, 28 commands.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 1 --fail-on-evidence-gaps --output /tmp/plan_v7_summary_after_runtime_replay_handoff_gate.json` -> passed with no latest evidence gaps.
- `rg -n "direct_llm|DirectLLM|direct-llm|Direct LLM|direct_llm_executor" services scripts apps --glob '!node_modules/**' --glob '!dist/**' --glob '!build/**' --glob '!*.lock'` -> only artifact-summary negative guard code mentions `direct_llm`; production implementation paths remain direct-free.
- `git diff --check -- scripts/runtime_replay_eval_smoke.py scripts/plan_v7_artifact_summary.py tests/test_plan_v7_artifact_summary.py plan_v7.md` -> passed.

Remaining gaps:

- Live-provider natural handoff dogfood with real long-lived team profiles remains unproven; current handoff-policy evidence is deterministic smoke / matrix coverage.
- Repeated queued Ticket-loop reliability under Agent Server/live-provider load remains a separate production-hardening gap.
- Full Employee detail maturity is still incomplete: capability growth history, quality trends, and richer profile evolution are not done.

Next concrete module:

- Run a live-provider natural handoff dogfood with real team profiles while keeping `executor_id=langgraph` and DeepSeek only behind LangGraph/LangChain, or add repeated queued Ticket-loop Agent Server/live-provider reliability evidence.

Anti-Wheel Audit:

- No new agent loop, replay engine, memory database, handoff protocol, risk engine, provider adapter, queue system, observability backend, or custom Chat runtime was added.
- The slice reuses existing ExecutionResult ingestion, Ticket handoff events/reports, ExecutionReplayService, Runtime Replay coverage summary, v7 artifact wrapper, and artifact summary gate.
- AITeamOS remains focused on Ticket / Employees / Assets / Governance; LangGraph owns orchestration; LangChain owns model-provider wiring; DeepSeek stays only the temporary model provider; Codex CLI stays an optional repo-write adapter.

### 2026-06-21: Track B/F live natural handoff blocker gate

Status: completed for updating the v7 control gates and regression tests so future loops do not treat an incomplete live-provider natural handoff as success. This does not complete all of v7; it records a real Plane provider blocker and keeps the next loop pointed at the correct risk.

Goal: preserve the v5/v6/v7 principles while tightening the live dogfood success definition: LangGraph remains the core runtime, DeepSeek remains only the temporary model provider behind LangGraph / LangChain, and AITeamOS must not fall back to a direct LLM loop or Codex CLI core proof when provider writes fail.

Files changed:

- Updated `plan_v7.md`.
- Updated `services/api/aiteamos_api/read/live_provider_dogfood_service.py`.
- Updated `services/api/aiteamos_api/agents/workbench/nodes/response.py`.
- Updated `scripts/live_provider_dogfood.py`.
- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `scripts/plan_v7_artifact_summary.py`.
- Updated `tests/test_live_provider_dogfood_service.py`.
- Updated `tests/test_plan_v7_artifact_summary.py`.
- Updated `tests/test_plan_v7_ci_artifacts.py`.
- Updated `tests/test_aiteamos_workbench_graph.py`.

What changed:

- Added section 0.3 as a hard gate: LangGraph `final_response` / `runtime_status.status=completed` is not sufficient for live dogfood success if the governed execution result is blocked.
- Required core-loop live dogfood to keep `executor_id=langgraph` and treat DeepSeek only as the LangGraph / LangChain model provider.
- Added natural handoff requirements for live dogfood: durable Ticket-backed `handoff_summary.status=durable_handoff_recorded`, expected target Employee, and at least one handoff ref.
- Made live dogfood block before Asset review / Graphiti projection when `aiteamos_chat_response.run_metadata.execution.status` is blocked, even if the graph reached a final node.
- Preserved `handoff_decision`, `handoff_summary`, and `ticket_handoff_refs` through the final Workbench response projection so final graph state can carry handoff evidence.
- Added artifact-summary gates that reject a core-loop live dogfood missing natural handoff proof.
- Updated the reusable Goal prompt so future autonomous runs honor sections 0.1, 0.2, and 0.3 before continuing.

Evidence and risk finding:

- Local Agent Server natural handoff probe with real long-lived team profiles proved Clara -> Alex durable Ticket handoff through the LangGraph Workbench path.
- The stricter production-readiness run `local-v7-live-natural-handoff` failed at `live_provider_dogfood_execute`: Plane returned a 502 during governed Ticket handoff / ingestion, while the graph final node still reached `completed`.
- This is the exact risk now captured by 0.3: provider/action write failure must remain visible as a blocker and cannot be bypassed by direct DeepSeek calls, Codex CLI core proof, answer-only summaries, or skipped Asset/Graphiti steps.
- Current latest artifact summary correctly reports `latest_status=failed` with `live_provider_dogfood_not_completed` and `live_provider_dogfood_natural_handoff_missing`.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/live_provider_dogfood_service.py services/api/aiteamos_api/agents/workbench/nodes/response.py scripts/live_provider_dogfood.py scripts/plan_v7_ci_artifacts.py scripts/plan_v7_artifact_summary.py tests/test_live_provider_dogfood_service.py tests/test_plan_v7_artifact_summary.py tests/test_plan_v7_ci_artifacts.py tests/test_aiteamos_workbench_graph.py` -> passed.
- `pytest tests/test_live_provider_dogfood_service.py -q` -> 10 passed.
- `pytest tests/test_plan_v7_artifact_summary.py tests/test_plan_v7_ci_artifacts.py -q` -> 20 passed.
- `pytest tests/test_aiteamos_workbench_graph.py -k "handoff or response_nodes" -q` -> 2 passed.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 1 --output /tmp/plan_v7_summary_after_risk_update.json` -> completed and intentionally reported latest failed live-provider evidence gaps.
- `rg -n "direct_llm|DirectLLM|direct-llm|Direct LLM|direct_llm_executor" services scripts apps --glob '!node_modules/**' --glob '!dist/**' --glob '!build/**' --glob '!*.lock'` -> only artifact-summary negative guard code mentions `direct_llm`; production implementation paths remain direct-free.
- `git diff --check -- services/api/aiteamos_api/read/live_provider_dogfood_service.py services/api/aiteamos_api/agents/workbench/nodes/response.py scripts/live_provider_dogfood.py scripts/plan_v7_ci_artifacts.py scripts/plan_v7_artifact_summary.py tests/test_live_provider_dogfood_service.py tests/test_plan_v7_artifact_summary.py tests/test_plan_v7_ci_artifacts.py tests/test_aiteamos_workbench_graph.py plan_v7.md` -> passed.

Remaining gaps:

- Live-provider natural handoff dogfood with real long-lived team profiles remains blocked by Plane 502 / provider action state until the Ticket handoff write path is diagnosed and rerun.
- Repeated queued Ticket-loop reliability under Agent Server/live-provider load remains a separate production-hardening gap.
- Full Employee detail maturity is still incomplete: capability growth history, quality trends, and richer profile evolution are not done.

Next concrete module:

- Diagnose and harden the Plane provider action path for Ticket handoff/report writes, preferably with a focused provider health/action smoke that exercises the same handoff write before running full live dogfood again.
- Rerun `AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/plan_v7_ci_artifacts.py --run-id local-v7-live-natural-handoff --production-readiness --include-live-provider-dogfood --live-provider-profile core-loop --live-provider-executor-id langgraph --live-provider-ticket-id ops-0014 --fail-fast` only after the Plane handoff write blocker is understood or fixed.

Anti-Wheel Audit:

- No new agent loop, LLM caller, memory database, Chat runtime, queue system, provider adapter, or repo-write substitution was added.
- The slice reuses the existing LangGraph Workbench, LangChain model-provider boundary, ExecutionResult ingestion metadata, Ticket handoff service, live dogfood wrapper, artifact summary gate, and existing tests.
- AITeamOS remains focused on Ticket / Employees / Assets / Governance; LangGraph owns orchestration; LangChain owns provider wiring; DeepSeek stays only the temporary model provider; Codex CLI stays an optional repo-write adapter.

### 2026-06-21: Track B/F Plane Ticket action smoke before live natural handoff

Status: completed for adding a focused provider action-smoke gate that isolates the Plane Ticket handoff/report write path before full live natural handoff dogfood. This does not complete all of v7; it makes the next live loop fail earlier and more clearly if Plane comment/report writes are still blocked.

Goal: keep the v5/v6/v7 architecture intact while diagnosing the real blocker. LangGraph remains the autonomous runtime, DeepSeek remains only the temporary LLM provider behind LangGraph / LangChain, and AITeamOS must not bypass provider failures by reintroducing a direct LLM loop or treating a graph final response as enough.

Files changed:

- Updated `services/api/aiteamos_api/read/ticket_service.py`.
- Added `scripts/plane_ticket_action_smoke.py`.
- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `scripts/plan_v7_artifact_summary.py`.
- Updated `tests/test_file_knowledge_and_tickets.py`.
- Updated `tests/test_plan_v7_ci_artifacts.py`.
- Updated `tests/test_plan_v7_artifact_summary.py`.
- Updated `plan_v7.md`.

What changed:

- Added `TicketProviderActionSmokeRequest` and `TicketProviderActionSmokeResponse`.
- Added `action_smoke()` to the Ticket adapter protocol.
- Added non-mutating local-file and planned-adapter action-smoke responses.
- Added `PlaneTicketAdapter.action_smoke()` that uses the existing Ticket service methods to load or create a Ticket, record a governed Employee handoff projection, and append the same `employee_handoff` report/comment path used by live dogfood ingestion.
- Added `ticket_provider_action_smoke()` as the domain-service entrypoint.
- Added `scripts/plane_ticket_action_smoke.py` as a thin CLI wrapper over the Ticket service. It is gated by `--execute` and `AITEAMOS_LIVE_PROVIDER_DOGFOOD=1`; dry run does not mutate provider state.
- Added the Plane action-smoke command to `plan_v7_ci_artifacts.py` only when `--include-live-provider-dogfood` is explicit. It runs before full `live_provider_dogfood_execute`.
- Added artifact-summary extraction for `plane_ticket_action_smoke.json`; if present and not passed, the summary reports `plane_ticket_action_smoke_not_passed`.
- Added regression tests for dry-run behavior, successful create/handoff/report action path, comment-write blocker surfacing, CI command wiring, and artifact-summary evidence gaps.
- Fixed brittle Ticket-provider tests that assumed the second HTTP call was always the comment POST; they now find the POST ending in `/comments/` so provider refresh calls do not mask the real assertion.

Evidence and risk finding:

- The previous `local-v7-live-natural-handoff` failure reached the LangGraph final node but then failed during governed Ticket ingestion. The focused review found that `record_ticket_handoff()` records the local/projection handoff event, while `add_ticket_report(report_type="employee_handoff")` is the path that calls the Plane comments endpoint.
- Official Plane API docs confirm the current comments path family and payload shape are plausible for work-item comments, so the right next step is provider action validation, not replacing LangGraph or adding a direct model call.
- The new smoke isolates three blocker stages: `plane_ticket_load_or_create_failed`, `plane_ticket_handoff_projection_failed`, and `plane_handoff_report_action_failed`.
- If the earlier Plane 502 still reproduces, the smoke should now block at `append_handoff_report` and produce provider-action evidence before the heavier live dogfood run starts.
- A dry/no-setup smoke against a temp workspace returned a setup blocker instead of fake success, preserving the rule that provider blockers stay visible.
- The current latest artifact summary still reports the older `local-v7-live-natural-handoff` run as failed with `live_provider_dogfood_not_completed` and `live_provider_dogfood_natural_handoff_missing`. That is expected because the latest recorded run predates the new Plane action-smoke artifact.

Validation:

- `python -m py_compile services/api/aiteamos_api/read/ticket_service.py scripts/plane_ticket_action_smoke.py scripts/plan_v7_ci_artifacts.py scripts/plan_v7_artifact_summary.py tests/test_file_knowledge_and_tickets.py tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_artifact_summary.py` -> passed.
- `pytest tests/test_file_knowledge_and_tickets.py -k "plane_ticket_action_smoke or plane_ticket_mapping" -q` -> 4 passed, 19 deselected.
- `pytest tests/test_plan_v7_ci_artifacts.py -q` -> 3 passed.
- `pytest tests/test_plan_v7_artifact_summary.py -k "live_dogfood_freshness or plane_ticket_action_smoke or natural_handoff" -q` -> 3 passed, 15 deselected.
- `pytest tests/test_file_knowledge_and_tickets.py -q` -> 23 passed.
- `pytest tests/test_plan_v7_artifact_summary.py tests/test_plan_v7_ci_artifacts.py -q` -> 21 passed.
- `pytest tests/test_file_system_status_routes.py::test_provider_conformance_external_smoke_uses_configured_plane_and_graphiti_adapters -q` -> 1 passed.
- `python scripts/plane_ticket_action_smoke.py --workspace-dir /tmp/aiteamos-plane-action-smoke-gate --output /tmp/aiteamos-plane-action-smoke-gate.json` -> exited with the expected setup blocker for missing Plane config in that temp workspace.
- `python scripts/plan_v7_artifact_summary.py --artifact-dir .aiteamos/artifacts/plan_v7 --limit 1 --output /tmp/plan_v7_summary_after_plane_action_smoke.json` -> completed and preserved the older live-provider failure evidence.
- `rg -n "direct_llm|DirectLLM|direct-llm|Direct LLM|direct_llm_executor" services scripts apps --glob '!node_modules/**' --glob '!dist/**' --glob '!build/**' --glob '!*.lock'` -> only artifact-summary negative guard code mentions `direct_llm`; production implementation paths remain direct-free.
- `git diff --check -- services/api/aiteamos_api/read/ticket_service.py scripts/plane_ticket_action_smoke.py scripts/plan_v7_ci_artifacts.py scripts/plan_v7_artifact_summary.py tests/test_file_knowledge_and_tickets.py tests/test_plan_v7_ci_artifacts.py tests/test_plan_v7_artifact_summary.py plan_v7.md` -> passed.

Remaining gaps:

- The new Plane action smoke still needs to run against the real configured Plane workspace and Ticket `ops-0014`.
- Live-provider natural handoff dogfood with real long-lived team profiles remains blocked/unproven until Plane action smoke and the full live dogfood run both pass.
- Repeated queued Ticket-loop reliability under Agent Server/live-provider load remains a separate production-hardening gap.
- Full Employee detail maturity is still incomplete: capability growth history, quality trends, and richer profile evolution are not done.

Next concrete module:

Run the focused Plane provider action smoke first:

```bash
AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/plane_ticket_action_smoke.py --execute --workspace-dir /home/shiqiangli/projects/AITeamOS --ticket-id ops-0014 --no-create-ticket --source-run-id plan-v7-plane-action-smoke-ops-0014 --output /tmp/plan_v7_plane_action_smoke_ops_0014.json
```

If it passes, rerun the full production-readiness live dogfood:

```bash
AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/plan_v7_ci_artifacts.py --run-id local-v7-live-natural-handoff --production-readiness --include-live-provider-dogfood --live-provider-profile core-loop --live-provider-executor-id langgraph --live-provider-ticket-id ops-0014 --fail-fast
```

If it fails, diagnose the Plane comment/report permission, service state, or payload using provider evidence. Do not change the architecture direction, do not bypass LangGraph, and do not reintroduce any AITeamOS direct-LLM Chat/Ticket/Employee loop.

Anti-Wheel Audit:

- No new agent loop, LLM caller, memory database, Chat runtime, queue system, provider adapter, or repo-write substitution was added.
- The slice reuses the existing Ticket service, Plane Ticket adapter, live dogfood wrapper, production artifact wrapper, artifact summary gate, and existing tests.
- AITeamOS remains focused on Ticket / Employees / Assets / Governance; LangGraph owns orchestration; LangChain owns provider wiring; DeepSeek stays only the temporary model provider; Codex CLI stays an optional repo-write adapter.

### 2026-06-21: Track B/F Agent Server fresh live dogfood and provider evidence hardening

Status: completed for the current fresh Agent Server live natural handoff production-readiness gate. This supersedes the previous Plane action-smoke "still needs to run" gap, but it does not complete all of v7; it closes the most dangerous drift risk where a stale Agent Server, graph final node, direct LLM fallback, or repo-write adapter proof could be mistaken for LangGraph core-loop readiness.

Goal: keep the v5/v6/v7 architecture intact while proving the real path: LangGraph Agent Server starts from current code, DeepSeek remains only behind LangChain/LangGraph model-provider wiring, Plane remains the Ticket backend, AITeamOS owns Ticket / Employees / Assets / Governance, and Graphiti remains approved Asset projection/recall.

Files changed:

- Updated `services/api/aiteamos_api/read/ticket_service.py`.
- Updated `services/api/aiteamos_api/read/execution_result_ingestion_service.py`.
- Updated `services/api/aiteamos_api/read/live_provider_dogfood_service.py`.
- Updated `services/api/aiteamos_api/read/memory_service.py`.
- Updated workspace-root fallback helpers in `knowledge_service.py`, `asset_candidate_service.py`, `ticket_loop_service.py`, `schema_registry_service.py`, `employee_improvement_service.py`, `asset_routes.py`, `runtime_executors/external_runtime_executor.py`, and `agents/workbench/approval_fixture_graph.py`.
- Updated `scripts/live_provider_dogfood.py`.
- Updated `scripts/plan_v7_ci_artifacts.py`.
- Updated `tests/test_execution_dispatch_contract.py`.
- Updated `tests/test_file_knowledge_and_tickets.py`.
- Updated `tests/test_file_memory_routes.py`.
- Updated `tests/test_live_provider_dogfood_service.py`.
- Updated `tests/test_plan_v7_ci_artifacts.py`.
- Updated `plan_v7.md`.
- Generated production-readiness evidence under `.aiteamos/artifacts/plan_v7/local-v7-live-natural-handoff-after-fresh-server/`.

What changed:

- Ran the focused real Plane action smoke against Ticket `ops-0014`; it passed and recorded both the governed handoff projection and the `employee_handoff` report/comment path.
- Added transient retry in the Plane Ticket adapter for 429 / 502 / 503 / 504 so short provider hiccups remain visible but do not fail before retrying the same governed action.
- Fixed idempotent ExecutionResult ingestion so an already-ingested handoff artifact can rehydrate durable `tickets.manage:handoff` evidence from the existing Ticket instead of losing handoff refs in graph state.
- Hardened live dogfood evidence extraction so it reads nested LangGraph Agent Server state, governed execution status, and Ticket-ledger handoff fallback instead of misreporting natural handoff as missing.
- Added `scripts/live_provider_dogfood.py --start-agent-server` and wired production-readiness to use it, so live dogfood starts a fresh temporary LangGraph Server from current code instead of relying on a possibly stale long-running `:2024` server.
- Removed eager `Path.cwd()` default evaluation in hot Agent Server paths and changed the memory read path so recall/search does not call `mkdir` inside the LangGraph event loop.
- Made core-loop dogfood block if Agent Server returns `__error__` or lacks completed runtime evidence, preventing false Asset/Memory success reports after blocking runtime errors.

Evidence:

- Real Plane action smoke passed:
  - Ticket: `ops-0014`
  - Plane provider record: `42902f62-12cc-4ef4-b3b8-2214f58035f5`
  - Report: `report-586b64510d`
  - Handoff recorded: `true`
  - Handoff report recorded: `true`
- Fresh Agent Server live dogfood passed:
  - Agent Server: temporary fresh server started by `--start-agent-server`
  - Profile: `core_loop`
  - Executor: `langgraph`
  - LangGraph thread: `019ee79b-345f-7e53-a844-0c49e9d53213`
  - Runtime run: `run-6a3616707c23`
  - Workbench runtime status: `completed`
  - Selected AI engine: `deepseek`
  - Natural handoff: `durable_handoff_recorded`
  - Handoff target: `alex`
  - Handoff refs: `1`
  - Memory / Asset: `mem-ae61f299a812`
  - Graphiti projection: `ingested`
  - Graphiti recall count: `1`
- Full production-readiness wrapper passed:
  - Run id: `local-v7-live-natural-handoff-after-fresh-server`
  - Commands: `29`
  - Latest status: `passed`
  - Latest evidence gaps: `[]`
  - Retained evidence gaps: `[]`

Validation:

- `python -m py_compile services/api/aiteamos_api/read/execution_result_ingestion_service.py tests/test_execution_dispatch_contract.py` -> passed.
- `pytest tests/test_execution_dispatch_contract.py -k "idempotent_handoff or execution_contract_supports_ticket_binding_modes" -q` -> 2 passed.
- `python -m py_compile services/api/aiteamos_api/read/ticket_service.py services/api/aiteamos_api/read/execution_result_ingestion_service.py tests/test_file_knowledge_and_tickets.py tests/test_execution_dispatch_contract.py` -> passed.
- `pytest tests/test_file_knowledge_and_tickets.py -k "plane_ticket_action_smoke" -q` -> 4 passed.
- `python -m py_compile services/api/aiteamos_api/read/live_provider_dogfood_service.py tests/test_live_provider_dogfood_service.py` -> passed.
- `pytest tests/test_live_provider_dogfood_service.py -k "nested_agent_server_state or ticket_ledger_fallback or workbench_execution_result_is_blocked or natural_handoff" -q` -> 5 passed.
- `python -m py_compile scripts/live_provider_dogfood.py scripts/plan_v7_ci_artifacts.py tests/test_plan_v7_ci_artifacts.py` -> passed.
- `pytest tests/test_plan_v7_ci_artifacts.py -q` -> 3 passed.
- `python -m py_compile services/api/aiteamos_api/read/memory_service.py services/api/aiteamos_api/read/live_provider_dogfood_service.py tests/test_file_memory_routes.py tests/test_live_provider_dogfood_service.py` -> passed.
- `pytest tests/test_file_memory_routes.py -k "read_paths_do_not_create_directory or memory_candidate_approval_requires_graphiti_backend" -q` -> 2 passed.
- `pytest tests/test_live_provider_dogfood_service.py -k "agent_server_error or workbench_execution_result_is_blocked or nested_agent_server_state or ticket_ledger_fallback" -q` -> 4 passed.
- `AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --server-log /tmp/plan_v7_live_provider_agent_server_after_memory_dir_fix.log --workspace-dir /home/shiqiangli/projects/AITeamOS --profile core_loop --executor-id langgraph --ticket-id ops-0014 --no-create-ticket --require-natural-handoff --expected-handoff-target alex --output /tmp/plan_v7_live_provider_dogfood_with_fresh_server_after_memory_dir_fix.json` -> completed.
- `AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/plan_v7_ci_artifacts.py --run-id local-v7-live-natural-handoff-after-fresh-server --production-readiness --include-live-provider-dogfood --live-provider-profile core-loop --live-provider-executor-id langgraph --live-provider-ticket-id ops-0014 --fail-fast` -> passed with 29 commands.

Remaining gaps:

- This closes the current live natural handoff production-readiness evidence gap, but v7 still needs repeated queued Ticket-loop reliability under Agent Server / live-provider load.
- Graphiti / Neo4j emitted background index-task connection warnings during the fresh Agent Server run even though projection/recall and the production-readiness gate passed. Treat this as provider stability noise to harden with longer soak, not as a reason to bypass Graphiti or replace it with a custom memory database.
- Long-running deployment soak, richer Employee quality/capability growth history, and fuller production observability remain incomplete.
- Frontend tests/build were not run in this slice because no frontend code changed.

Next concrete module:

- Continue Track B/G/J with repeated queued Ticket-loop reliability under fresh Agent Server / live-provider conditions, including longer Graphiti/Neo4j provider soak and explicit evidence for repeated queued work, failures, policy action, Asset candidate creation, and recall.
- Keep sections 0.1, 0.2, and 0.3 as controlling gates: no direct LLM primary path, no Codex CLI substitution for core-loop proof, no false success when governed Ticket / Asset / Graphiti evidence is incomplete.

Anti-Wheel Audit:

- No new agent loop, model client, memory database, Chat runtime, queue system, scheduler, provider adapter, observability platform, or repo-write substitution was added.
- The slice reused LangGraph Agent Server, the existing Workbench graph, LangChain provider wiring, Plane Ticket adapter, Ticket handoff/report services, ExecutionResult ingestion, MemoryCandidate / AssetReview / AssetRecord flows, Graphiti projection/recall, existing live dogfood wrapper, existing production artifact wrapper, and existing tests.
- AITeamOS remains focused on Ticket / Employees / Assets / Governance; LangGraph owns orchestration; LangChain owns provider wiring; DeepSeek stays only the temporary model provider; Codex CLI stays an optional repo-write adapter.

## 20. Reusable Goal Prompt

Use this prompt for Codex Goal mode:

```text
You are working in /home/shiqiangli/projects/AITeamOS.

Read plan_v7.md first. Treat plan_v7.md as the active production-hardening plan. Treat sections 0.1, 0.2, and 0.3 as the latest controlling corrections. Treat plan_v6.md as the completed architecture baseline and evidence record. plan_v5.md, plan_v4.md, and plan_v3.md are historical context only.

Core principle:
Keep AITeamOS Ticket / Employees / Assets / Governance as the product source of truth. Reuse mature LangGraph / LangChain / assistant-ui / Agent Chat UI / Graphiti / external agent runtimes for everything else. Do not rebuild generic Chat UI, generic agent loop, generic streaming protocol, generic memory database, generic checkpoint UI, or generic observability platform.
DeepSeek API is the temporary default LLM provider, but only behind LangGraph / LangChain model-provider wiring. AITeamOS must not keep a primary direct-LLM Chat / Ticket / Employee loop.
`DirectLLMExecutor` must remain absent from the default RuntimeExecutor registry, System Status runtime list, runtime provider conformance, and production-readiness artifact evidence. Legacy `direct_llm` input may only fall back into LangGraph / Universal Employee Agent or fail closed.
Codex CLI and similar tools are optional repo-write / coding RuntimeExecutor adapters only. They cannot replace LangGraph as the core autonomous team loop.

Target:
Turn the v6 proven loop into a production-grade autonomous AI Team OS:
- LangGraph owns the real autonomous loop and node orchestration.
- DeepSeek backs the LangGraph model layer until a different provider is deliberately selected.
- Agent Server can run the graph in a production-compatible mode.
- Chat stays thin and uses LangChain / assistant-ui runtime primitives.
- Ticket / Employees / Assets / Governance remain the durable product core.
- Graphiti remains only an approved Asset projection and recall provider.
- External agent runtimes remain optional adapters behind ExecutionRequest / ExecutionResult / approval / evidence contracts.

Execution rules:
1. Inspect git status first and preserve unrelated user changes.
2. Do not stop at analysis. Implement the highest-value unblocked v7 slice.
3. First honor the 2026-06-21 boundary correction: split core-loop dogfood from repo-write adapter dogfood, keep DeepSeek behind LangGraph, and keep `DirectLLMExecutor` out of default registry / dispatch / readiness evidence.
   Ignore any older historical plan note that says an explicit diagnostic `DirectLLMExecutor` remains; that state is superseded by the hard-removal section and section 0.2.
4. Honor the 2026-06-21 live dogfood success gate: LangGraph `final_response` or `runtime_status.status=completed` alone is not sufficient. Core-loop live dogfood must also show governed execution status completed/acceptable partial, required Ticket / Asset / Graphiti writes, and no artifact-summary evidence gaps. If natural handoff is required, assert durable Ticket-backed `handoff_summary.status=durable_handoff_recorded`, expected target Employee, and handoff refs.
5. Treat `local-v7-live-natural-handoff-after-fresh-server` as the latest passed live core-loop evidence. Future live dogfood must start a fresh Agent Server or otherwise prove it is using current code; do not rely on a stale long-running `:2024` server. The next preferred hardening slice is repeated queued Ticket-loop reliability under fresh Agent Server / live-provider conditions.
6. Prioritize production Agent Server compatibility, LangGraph node decomposition, Chat maintainability, approval UX, retrieval evals, Employee handoff, Ticket loop, Assets provenance, RuntimeExecutor reliability, and replay/evals in that order unless the repo state clearly says otherwise.
7. Avoid wheel-building aggressively. Before adding logic, check whether LangGraph, LangChain, assistant-ui, Graphiti, or an existing AITeamOS service already provides the capability.
8. Move orchestration out of route handlers and into LangGraph graph nodes or domain services.
9. Keep durable memory writes behind Asset candidates, Review Queue, approved AssetRecord, and Graphiti projection.
10. Keep all provider blockers visible instead of faking success. Plane 502 / Graphiti / MemoryCandidate / Ticket-write failures are blockers to diagnose, not reasons to bypass LangGraph or skip governance.
11. Do not use Codex CLI live dogfood as the primary production-readiness proof. It is only repo-write adapter conformance.
12. Validate each slice with focused backend tests, frontend tests/build when relevant, langgraph validate, direct-LLM residue scan, production artifact summary gate when relevant, and git diff --check.
13. Update plan_v7.md with exact files changed, tests run, blockers, remaining gaps, next concrete module, and Anti-Wheel Audit result.

Completion:
Continue autonomously until plan_v7 completion criteria are met or a real external blocker prevents meaningful progress. If the whole plan cannot be completed in one run, finish the highest-value verifiable slice and leave plan_v7.md ready for the next run.
```
