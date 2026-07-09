# AITeamOS plan_v4: LangGraph Universal Employee Agent Loop

状态：下一步实现计划  
日期：2026-06-14  
目标：把 AITeamOS 从 Runtime-first 骨架推进到 LangGraph 主执行 runtime，让每一次 Chat 都能自动编排 Employee、Ticket、Assets、Memory、Docs、Skills、Tooling 和审批上下文，同时避免在 `chat_routes.py` 中自研通用 Agent。

## 0. 目标基线

AITeamOS 的最终目标是做成一个以 Ticket 流转为核心的 AI Team Operating System：

- Employees 像真实成员一样拥有固定身份、能力标签、性格标签、权限边界、工作历史和记忆范围。
- Tickets 是所有成员协作、交接、汇报、验证、阻塞处理和沉淀结论的主通道。
- Assets 是系统最重要的长期资产层，Memory、Docs、Skills、Tooling calls、解决方案、建议、复盘、验证结果都以可审计 provenance 进入资产体系。
- Ticket、Employee、Assets 都支持外部供应商或自研实现，例如 Plane、Graphiti、本地轻量实现等。
- AITeamOS 不自研通用 Agent；通用 chat、agent loop、tool use、handoff、checkpoint、human approval 优先复用 LangGraph 或商业 Agent Runtime。
- LangGraph 是 AITeamOS 的默认主执行 runtime；Chat route 只负责入口、request parsing、response formatting、SSE / AG-UI event bridge，不承载 agent loop。

## 1. 当前实现状态

已经具备的基础：

- `ExecutionRequest` / `ExecutionResult` / `ExecutionEvent` 边界已经开始落地。
- `ExecutionDispatchService` 已能选择 `direct_llm`、`langgraph`、`local_tool` 和外部 runtime executor。
- `ExecutionContextService` 已能从 Ticket / Employee / Memory / Assets 组装 scoped context。
- `ExecutionResultIngestionService` 已能消费 runtime 输出，并写回 Ticket report、evidence、approval、memory candidate、durable asset candidate 和 trace metadata。
- DeepSeek API 已经通过 `direct_llm` executor 跑通。
- `LangGraphExecutor` 已经存在，能接收 `ExecutionRequest` 并返回 `ExecutionResult`。
- Plane Ticket Backend 和 Graphiti Memory / Asset Graph Backend 已经出现在 System Status 和 Settings 路径中。

还没完成的部分：

- 普通 Chat 仍优先走 `direct_llm answer_only`，不是默认进入 LangGraph agent loop。
- `LangGraphExecutor` 目前还是浅层 workflow adapter，不是通用 autonomous employee agent。
- Ticket / Assets / Memory / Employee 还没有全部变成 LangGraph tools。
- Employee handoff / sub-agent routing 尚未进入 LangGraph 图。
- Agent 在回答前还不能自主多轮检索 related tickets、skills、docs、memories、backend status。
- Human approval、checkpoint、tool-call provenance 虽有边界，但还没成为 LangGraph loop 的一等节点。

## 2. v4 架构目标

新增或升级一个默认执行器：

```text
UniversalEmployeeAgentExecutor
  -> built on LangGraph
  -> receives ExecutionRequest
  -> runs employee-aware agent graph
  -> returns ExecutionResult
```

主链路：

```text
Dashboard Chat / AG-UI
  -> chat_routes.py
  -> ChatGovernanceService
  -> ExecutionRequest
  -> ExecutionDispatchService
  -> UniversalEmployeeAgentExecutor
  -> LangGraph graph
      -> load Employee context
      -> retrieve Tickets / Assets / Memory / Docs / Skills
      -> plan next action
      -> call read/write/governance tools
      -> maybe handoff to another Employee
      -> maybe request human approval
      -> produce final answer/report/evidence/candidates
  -> ExecutionResult
  -> ExecutionResultIngestionService
  -> Ticket / Employee / Assets / Memory / Trace / Review Queue
```

## 3. LangGraph State

第一版 universal state：

```python
class UniversalEmployeeAgentState(TypedDict, total=False):
    execution_request: dict[str, Any]
    user_message: str
    selected_employee: dict[str, Any]
    employee_profiles: list[dict[str, Any]]
    employee_skills: list[dict[str, Any]]
    permissions: list[str]
    ticket_binding: dict[str, Any]
    current_ticket: dict[str, Any]
    related_tickets: list[dict[str, Any]]
    related_assets: list[dict[str, Any]]
    recalled_memories: list[dict[str, Any]]
    docs_context: list[dict[str, Any]]
    backend_status: dict[str, Any]
    plan: dict[str, Any]
    messages: list[dict[str, Any]]
    tool_events: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    approval_requests: list[dict[str, Any]]
    memory_candidates: list[dict[str, Any]]
    handoff_target_employee_id: str
    final_report: str
    usage: dict[str, Any]
    errors: list[dict[str, Any]]
```

State 原则：

- AITeamOS 事实都进入 state，但敏感 secret 不进入 state。
- 外部 provider 原生字段只能作为 metadata，不改变 AITeamOS 的 Ticket / Employee / Asset 领域语言。
- 写操作不直接绕过 ingestion；LangGraph 可以提出 artifact / evidence / approval request，由 ingestion 写回治理事实。
- checkpoint 归 LangGraph executor 管，AITeamOS 只保存 executor session ref 和 checkpoint ref。

## 4. LangGraph Tools

第一批工具只做最小可体验闭环。

### 4.1 Employee tools

```text
get_employee_context(employee_id)
list_employees()
choose_employee_for_goal(goal, candidates)
get_employee_work_history(employee_id)
```

返回：

- profile
- role / personality tags
- skills
- permissions
- current work
- recent Ticket contribution
- memory scopes

### 4.2 Ticket tools

```text
search_tickets(query, status?, employee_id?)
get_ticket_context(ticket_id)
get_related_tickets(ticket_id_or_query)
prepare_create_ticket(title, description, assignee, validator, acceptance)
prepare_append_ticket_report(ticket_id, report, evidence)
prepare_request_validation(ticket_id, validator, evidence)
```

读工具可以直接返回事实。写工具第一版只产出 artifact / evidence / approval request，不直接调用 Plane；最终写入仍由 `ExecutionResultIngestionService` 统一处理。

### 4.3 Asset tools

```text
search_assets(query, asset_types?)
get_skill(skill_id)
get_doc(doc_id)
get_capability(capability_id)
propose_asset_candidate(kind, content, provenance)
```

Assets 工具必须返回 provenance：

- asset_id
- asset_type
- source_kind
- source_ref
- scope_kind
- scope_ref
- status
- graphiti_episode_id / provider_ref

### 4.4 Memory tools

```text
search_memory(query, employee_id?, ticket_id?, include_graphiti=True)
recall_memory_for_goal(goal, employee_id, ticket_keys)
propose_memory_candidate(content, source, scope, tags)
record_memory_recall_usefulness(memory_id, run_id, usefulness_status)
```

Memory 是 Assets 的一类，不是 chat transcript 的裸存档。只有候选、审核、召回、效果反馈都带 provenance，才算进入长期资产闭环。

### 4.5 Governance tools

```text
inspect_system_status()
inspect_permissions(employee_id)
request_human_approval(reason, risk, proposed_action)
finalize_answer(report, evidence, artifacts, candidates)
```

Governance tools 负责把 runtime 行为变成 AITeamOS 可审计事实。

## 5. LangGraph 图

第一版图结构：

```text
START
  -> load_request
  -> load_employee_context
  -> pre_retrieve_context
  -> plan_next_step
  -> agent_tool_loop
  -> governance_gate
  -> maybe_handoff
  -> produce_execution_result
  -> END
```

节点职责：

- `load_request`：校验 `ExecutionRequest`，初始化 state。
- `load_employee_context`：加载 Employee profile、skills、permissions、personality tags、work history summary。
- `pre_retrieve_context`：自动召回 related tickets、assets、memory、docs、backend status。
- `plan_next_step`：由 LLM 生成结构化 plan，决定 answer / create ticket / append report / request validation / handoff / approval。
- `agent_tool_loop`：使用 LangGraph tool node 或等价机制执行多轮 read tools；写动作只能形成 governed artifact。
- `governance_gate`：检查权限、Ticket binding、approval requirement、evidence requirement。
- `maybe_handoff`：如果应该交给另一个 Employee，生成 handoff artifact 或子图调用。
- `produce_execution_result`：输出标准 `ExecutionResult`。

第一版循环上限：

- 每次请求最多 6 次 tool loop。
- 最多 2 次 memory/ticket 扩展检索。
- 最多 1 次 Employee handoff。
- 如果缺少必要配置，返回 typed blocker，不生成 fake completion。

## 6. 分阶段实施

### Phase A: Universal Context Contract

目标：先把 context 做成 LangGraph 可消费的稳定结构。

任务：

1. 新增 `universal_agent_context.py` 或扩展 `execution_context_service.py`。
2. 输出统一 `employee_context`、`ticket_context`、`asset_context`、`memory_context`、`backend_context`。
3. 为每个 context item 增加 `provenance` 和 `source_confidence`。
4. Chat trace 中展示本轮实际注入了哪些 context。
5. 增加 tests 覆盖：
   - 有 Ticket binding 时能加载 Ticket + reports + evidence。
   - 无 Ticket binding 时能按 query 搜索 related tickets。
   - Employee skills 和 personality tags 可进入 context。
   - Graphiti memory recall 失败时返回 setup blocker 或 degraded context，不让请求崩溃。

验收：

- `ExecutionRequest.task_context` 能稳定包含 universal context。
- Dashboard Chat inspector 能看到 context provenance summary。

### Phase B: LangGraph Tool Registry

目标：把 Ticket / Assets / Memory / Employee 读能力变成 LangGraph tools。

任务：

1. 新增 `universal_agent_tools.py`。
2. 实现 read-only tools：
   - `get_employee_context`
   - `search_tickets`
   - `get_ticket_context`
   - `search_assets`
   - `search_memory`
   - `inspect_system_status`
3. tools 只调用 AITeamOS service API / service function，不直接操作 provider。
4. 每个 tool event 写入 `tool_events`，带 duration、input summary、output refs。
5. 增加 tests 覆盖 tool 输入、输出和 provenance。

验收：

- LangGraph executor 能在一次 answer 中至少调用 `search_tickets` 和 `search_memory`。
- 任何 tool failure 都变成 structured error / blocker，不吞掉。

### Phase C: UniversalEmployeeAgentExecutor MVP

目标：普通 Chat 默认进入 LangGraph employee agent loop。

任务：

1. 新增 `universal_employee_agent_executor.py`，或将 `LangGraphExecutor` 拆为：
   - `LangGraphWorkflowExecutor`
   - `UniversalEmployeeAgentExecutor`
2. `ExecutionDispatchService` 调整：
   - 普通 `answer_only` 默认选 `universal_employee_agent`。
   - 仅当用户或 config 明确选择 `direct_llm` 时，才走 `direct_llm`。
3. 使用 DeepSeek / OpenAI 作为 LangGraph 内部 LLM。
4. 第一版只允许 read tools + governed final answer。
5. `ExecutionResult` 必须带：
   - executor_id
   - tool_events
   - recalled memory refs
   - related ticket refs
   - asset refs
   - usage
   - checkpoint_ref

验收：

- 用户问普通问题时，metadata 显示 executor 为 `universal_employee_agent` 或 `langgraph`。
- trace 里能看到 Employee context、Ticket search、Memory search、Assets search。
- 不再只有 `direct_llm` answer-only。

### Phase D: Governed Write Actions

目标：让 LangGraph 能推进 Ticket flow，但写入仍受 AITeamOS 治理。

任务：

1. 添加 governed write artifacts：
   - `ticket_create_request`
   - `ticket_report_request`
   - `validation_request`
   - `memory_candidate`
   - `asset_candidate`
   - `approval_request`
2. LangGraph 不直接写 Plane / Graphiti；只输出 artifacts。
3. `ExecutionResultIngestionService` 统一消费并写入。
4. 高风险动作必须产生 approval request。
5. 增加 tests 覆盖 create ticket、append report、request validation、memory candidate。

验收：

- Clara 可以通过 LangGraph 创建 Plane-backed Ticket。
- Employee 可以通过 LangGraph 给已有 Ticket 写 report/evidence。
- Memory / Asset candidate 能进入 Review Queue。

### Phase E: Employee Handoff / Sub-agent

目标：让 fixed Employee 真正像 sub-agent 一样工作。

任务：

1. 实现 `choose_employee_for_goal`。
2. 在 LangGraph 中增加 handoff decision。
3. 第一版 handoff 只生成 Ticket assignee change / handoff report，不直接并发启动多个 agent。
4. 第二版再支持 nested executor run：
   - Clara supervisor run
   - Employee child run
   - child `ExecutionResult` 归并到 parent artifacts / evidence
5. 每个 handoff 必须写入 Ticket event / report / trace。

验收：

- Clara 能判断应该交给 RD / PV / PM / Memory curator。
- Handoff 后 Ticket assignee / report / evidence 可追踪。

### Phase F: Checkpoint, Approval, Replay

目标：让 LangGraph 长任务可恢复、可审批、可复盘。

任务：

1. LangGraph checkpoint refs 写入 execution session store。
2. Human approval 作为 graph interrupt / approval request 表达。
3. Dashboard Assets / Review Queue 能看到 runtime approval records。
4. Approved run 可从 approval record 重建 `ExecutionRequest`。
5. Replay 能显示每次 tool event、context refs、memory refs、Ticket refs。

验收：

- 被 approval block 的 run 不丢 state。
- 审批通过后可继续执行或重新 dispatch。

## 7. 推荐立即下一步

不要从大规模 UI 或外部 runtime adapter 开始。下一步按这个顺序：

1. **先做 Phase A：Universal Context Contract。**
2. **再做 Phase B：LangGraph read-only tools。**
3. **再做 Phase C：普通 Chat 默认进入 LangGraph employee agent loop。**

第一轮可见成功标准：

```text
用户在 Chat 问一个关于 AITeamOS 当前状态的问题
  -> Clara/Employee 进入 LangGraph universal loop
  -> 自动检索 Employee context
  -> 自动检索 related tickets
  -> 自动检索 Assets / Memory
  -> 返回带 provenance summary 的回答
  -> run_metadata 显示 executor、tool_events、ticket_refs、asset_refs、memory_refs
```

## 8. 验收清单

每次实现后必须检查：

- `chat_routes.py` 没有新增 agent loop、provider-specific call、tool dispatcher。
- 普通 Chat 默认不再只走 `direct_llm answer_only`。
- LangGraph graph 持有上下文编排、工具调用、handoff、checkpoint、approval 节点。
- Ticket / Employee / Assets / Memory 都通过 AITeamOS service boundary 暴露给 LangGraph。
- 所有写操作都回到 `ExecutionResultIngestionService`。
- Dashboard Chat inspector 能解释本轮用了哪些 Employee、Tickets、Assets、Memory。
- setup blocker 清晰可见，不生成伪装完成。
- focused backend tests 通过。
- 如涉及前端，dashboard tests / build 通过。

## 9. Loop 执行落地 Prompt

下面 prompt 用于连续执行本计划。可多次连续执行；如果能够一步到位，就不要求必须多次执行。

```text
你正在 `/home/shiqiangli/projects/AITeamOS` 中继续实现 `plan_v4.md`。

首先必须重申并遵守基线：
AITeamOS 是以 Ticket 流转为核心的 AI Team Operating System。Employees 拥有固定身份、能力标签、性格标签、权限边界、工作历史和记忆范围；Tickets 是协作、交接、汇报、验证、阻塞处理和沉淀结论的主通道；Assets 是最重要的长期资产层，Memory、Docs、Skills、Tooling calls、解决方案、建议、复盘、验证结果都以可审计 provenance 进入资产体系。AITeamOS 不自研通用 Agent，而是复用 LangGraph 或商业 Agent Runtime；Chat route 只做入口和格式转换，不承载 agent loop。

执行步骤：

1. 读取 `plan_v4.md`、`plan_v3.md`、`docs/arch.md`，并检查 `git status --short --branch`。
2. 找出 `plan_v4.md` 中最高优先级且尚未完成的 Phase。默认顺序是 Phase A -> Phase B -> Phase C -> Phase D -> Phase E -> Phase F。
3. 在动手前检查相关实现：
   - `services/api/aiteamos_api/read/chat_routes.py`
   - `services/api/aiteamos_api/read/chat_governance_service.py`
   - `services/api/aiteamos_api/read/execution_context_service.py`
   - `services/api/aiteamos_api/read/execution_dispatch_service.py`
   - `services/api/aiteamos_api/read/execution_result_ingestion_service.py`
   - `services/api/aiteamos_api/read/runtime_executors/langgraph_executor.py`
   - `services/api/aiteamos_api/read/memory_service.py`
   - `services/api/aiteamos_api/read/ticket_service.py`
4. 实现一个小而完整的 vertical slice。优先让普通 Chat 逐步进入 LangGraph universal employee agent loop，而不是继续强化 `direct_llm` 或 `chat_routes.py`。
5. 严格保持边界：
   - 不在 `chat_routes.py` 新增 generic agent loop、provider-specific execution、tool dispatcher、subprocess runtime。
   - LangGraph tools 只能调用 AITeamOS service boundary，不直接绕过 Ticket / Asset / Memory governance。
   - 写操作通过 `ExecutionResult` artifacts/evidence/approval_requests/memory_candidates 返回，再由 `ExecutionResultIngestionService` 写入治理事实。
6. 每个新增 tool / graph node 必须产生可审计 provenance：
   - tool event
   - input summary
   - output refs
   - source kind/ref
   - error/blocker if failed
7. 添加或更新 focused tests。至少覆盖本 slice 的核心事实和 blocker 语义。
8. 运行相关验证：
   - 后端 slice：`pytest <focused tests>`
   - 涉及 Chat 主路径：至少运行 `pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py`
   - 涉及前端：运行 `cd apps/dashboard && npm test`，必要时 `npm run build`
9. 更新 `plan_v4.md` 的进度状态或 notes，只记录真实完成的内容。
10. 总结：
   - 完成了哪个 Phase / slice
   - 修改了哪些关键文件
   - 验证命令和结果
   - 还剩什么 blocker

停止条件：

- 当前 highest-priority slice 完整实现并验证通过；或
- 遇到需要用户决策的真实 blocker；或
- 发现现有未提交用户改动与本 slice 直接冲突，且无法安全合并。

不要停止在纯分析或计划阶段。能实现就实现，能验证就验证。
```

## 10. Progress Notes

### 2026-06-18: Phase A slice - universal context contract

已完成：

- `ScopedTaskContext` 增加 `universal_context` 字段，保留原有扁平 context 字段兼容当前 executor。
- `ExecutionContextService` 输出 `universal_context.v1`，包含：
  - `employee_context`
  - `ticket_context`
  - `asset_context`
  - `memory_context`
  - `backend_context`
  - `provenance_summary`
- 无 Ticket binding 时，context service 会用当前消息和 Employee 信息做轻量 related Ticket 搜索。
- Memory / Graphiti recall 异常会降级为 `setup_blockers`，不让 context build 崩溃。
- Chat run metadata 暴露 `scoped_context.universal_context` compact summary。
- Chat trace 增加 `execution.context.loaded` 事件，展示 universal context 的 counts 和 provenance summary。
- Dashboard Chat inspector 增加 `Universal Context` 区块，展示 context counts、backend status 和 provenance summary。

验证：

```bash
pytest tests/test_execution_dispatch_contract.py::test_execution_context_builds_universal_context_with_ticket_assets_and_memory_refs \
  tests/test_execution_dispatch_contract.py::test_execution_context_universal_context_searches_related_tickets_without_binding \
  tests/test_file_chat_routes.py::test_file_backed_employee_chat_roundtrip

pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py

cd apps/dashboard && npm test
cd apps/dashboard && npm run build
```

结果：

- `3 passed, 1 warning`
- `79 passed, 1 warning`
- `28 passed`
- `dashboard build passed`，保留 Vite chunk size warning

下一步：

- Phase A 的核心 contract / trace / inspector / degraded blocker 验收已完成；进入 Phase B，新增 LangGraph read-only tool registry。

### 2026-06-18: Phase B slice - read-only universal agent tools

已完成：

- 新增 `universal_agent_tools.py`，提供 LangGraph Universal Agent 可调用的 read-only tool registry。
- 第一版 tools：
  - `get_employee_context`
  - `search_tickets`
  - `get_ticket_context`
  - `search_assets`
  - `search_memory`
  - `inspect_system_status`
- Tools 只调用 AITeamOS service boundary，不直接操作 Plane / Graphiti provider SDK。
- 每次 tool call 输出统一 `universal_agent.tool.completed` / `universal_agent.tool.failed` event，包含：
  - `duration_ms`
  - `input_summary`
  - `output_refs`
  - `provenance`
  - `errors`
- `LangGraphExecutor` 图中新增 `read_context_tools` 节点，answer 路径会先调用 `search_tickets` 和 `search_memory`。
- Tool failure 会进入 `ExecutionResult.errors`，并保留 failed tool event，不静默吞掉。

验证：

```bash
pytest tests/test_execution_dispatch_contract.py::test_universal_agent_tool_registry_searches_tickets_with_provenance \
  tests/test_execution_dispatch_contract.py::test_langgraph_executor_answer_calls_read_only_context_tools \
  tests/test_execution_dispatch_contract.py::test_langgraph_executor_records_structured_read_tool_failure

pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py
```

结果：

- `3 passed, 1 warning`
- `82 passed, 1 warning`

下一步：

- Phase C：新增或拆出 `UniversalEmployeeAgentExecutor`，让普通 Chat 默认进入 LangGraph employee agent loop；第一版只允许 read tools + governed final answer。

### 2026-06-18: Phase C slice - default Universal Employee Agent runtime

已完成：

- 新增 `UniversalEmployeeAgentExecutor`，复用 LangGraph graph 和 Phase B read-only tools。
- `UniversalEmployeeAgentExecutor` 关闭 graph 前 provider 直连回答，改为 graph-first：
  - `load_request`
  - `plan_runtime_steps`
  - `read_context_tools`
  - `produce_result`
- 普通 `answer_only` 默认路由到 `universal_employee_agent`。
- `direct_llm` 仍可通过显式 `executor_id` / `selected_executor` 选择，用于纯 DeepSeek / OpenAI API 调用。
- graph-first answer 会先调用：
  - `search_tickets`
  - `search_memory`
  - `search_assets`
- DeepSeek / OpenAI 作为 Universal Employee Agent 的最终回答 LLM 时，会收到 LangGraph read-tool context。
- `ExecutionResult` 会包含：
  - `executor_id=universal_employee_agent`
  - `tool_events`
  - `errors`
  - `learning_delta.tool_outputs`
  - `checkpoint_ref`

验证：

```bash
pytest tests/test_execution_dispatch_contract.py::test_direct_llm_executor_is_available_when_explicitly_selected \
  tests/test_execution_dispatch_contract.py::test_answer_only_defaults_to_universal_employee_agent_with_read_tools \
  tests/test_execution_dispatch_contract.py::test_langgraph_executor_answer_calls_read_only_context_tools

pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py
```

结果：

- `3 passed, 1 warning`
- `83 passed, 1 warning`

下一步：

- Phase D：让 LangGraph 输出 governed write artifacts，由 `ExecutionResultIngestionService` 统一写入 Ticket / Memory / Asset review facts。

### 2026-06-18: Phase D slice - governed Ticket write artifacts

已完成：

- LangGraph report 类动作输出 `ticket_report_request` artifact：
  - `append_report`
  - `record_validation`
  - `record_failure`
- LangGraph validation 请求输出 `validation_request` artifact。
- `ExecutionResultIngestionService` 优先消费 governed artifacts，再写入 Ticket ledger。
- Runtime 仍不直接写 Plane / Ticket backend；写入集中在 ingestion service。
- `ticket_report_request` 会携带 content、report_type、evidence_refs、reporter 和 provenance。
- `validation_request` 会携带 validator、role、content、actor 和 provenance。

验证：

```bash
pytest tests/test_execution_dispatch_contract.py::test_ingestion_appends_report_to_existing_ticket \
  tests/test_execution_dispatch_contract.py::test_langgraph_validation_request_artifact_is_ingested

pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py
```

结果：

- `2 passed, 1 warning`
- `84 passed, 1 warning`

下一步：

- Phase E：Employee handoff / sub-agent artifact。第一版先产 governed handoff artifact，不直接创建递归 agent loop。

### 2026-06-18: Phase E slice - governed Employee handoff artifact

已完成：

- 新增 `employee_handoff_service.py`，实现确定性 `choose_employee_for_goal`。
- 覆盖第一版固定 Employee 路由：
  - RD / implementation -> Alex
  - PV / validation -> Peter
  - PM / planning -> PM-like profile 或 Clara fallback
  - Memory / Assets / Docs -> Memory curator profile 或 Clara fallback
- LangGraph 图中新增 `decide_handoff` 节点。
- Clara 在 Ticket-bound answer 场景中可生成 `employee_handoff_request` artifact。
- 第一版 handoff 不递归启动 child agent，只生成 governed artifact。
- `ExecutionResultIngestionService` 消费 handoff artifact：
  - 写入 `handoff_requested` Ticket event
  - 写入 `assigned` Ticket event
  - 写入 `employee_handoff` Ticket report
  - 追加 `tickets.manage:handoff` tool event
- Ticket service 新增 `record_ticket_handoff` service boundary，本地和 Plane projection mirror 都支持记录 handoff events。

验证：

```bash
pytest tests/test_execution_dispatch_contract.py::test_choose_employee_for_goal_routes_to_fixed_employee_profiles \
  tests/test_execution_dispatch_contract.py::test_universal_agent_handoff_artifact_records_ticket_events_and_report

pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py
```

结果：

- `2 passed, 1 warning`
- `86 passed, 1 warning`

下一步：

- Phase F：把 checkpoint/session、approval record replay 和 tool/context refs 串起来，让被 approval block 的 run 可复盘、可重建。

### 2026-06-18: Phase F slice - execution session checkpoint and replay refs

已完成：

- `execution_session_store.py` 扩展为可记录 runtime replay metadata：
  - `status`
  - `trace_ref`
  - `tool_event_count`
  - `ticket_refs`
  - `memory_refs`
  - `context_refs`
  - `approval_refs`
- `ExecutionResultIngestionService` 在 completed / partial / needs_approval / blocked 路径都会保存 execution session。
- 被 approval block 的 external runtime run 会保留：
  - `checkpoint_ref`
  - `executor_session_ref`
  - `approval_refs`
  - source request，可重新 `ExecutionRequest.model_validate(...)`。
- Universal Employee Agent handoff run 会保留：
  - Ticket refs
  - read-tool provenance context refs
  - tool event count
  - checkpoint ref
- Phase F 本轮先完成后端 replay/checkpoint 最小闭环；Dashboard Review Queue / replay UI 仍保留为下一轮 UI slice。

验证：

```bash
pytest tests/test_execution_dispatch_contract.py::test_chat_governance_routes_ticket_implementation_to_external_runtime_approval \
  tests/test_execution_dispatch_contract.py::test_universal_agent_handoff_artifact_records_ticket_events_and_report

pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py
```

结果：

- `2 passed, 1 warning`
- `86 passed, 1 warning`

下一步：

- Phase F UI slice：在 Dashboard Review Queue / Runtime Execution surfaces 中展示 approval records、execution sessions、checkpoint、tool events 和 context / memory / Ticket refs，形成可点开的 replay 视图。

### 2026-06-18: Phase F UI slice - runtime approval queue and replay sessions

已完成：

- RuntimeExecutor 后端新增只读治理视图：
  - `GET /api/v1/runtime-executors/approvals`
  - `GET /api/v1/runtime-executors/sessions`
- `execution_sessions.json` 记录增加自描述字段：
  - `session_key`
  - `employee_id`
  - `thread_id`
  - `ticket_id`
  - compact `tool_events`
- Dashboard Runtime Executors 面板新增：
  - Review Queue：展示 approval id、status、Ticket、required capability、reason、last run、run history count。
  - Execution Sessions：展示 request id、status、checkpoint、trace、Ticket、tool event count、compact tool event names、Ticket / Memory / Context / Approval refs count。
- 前端 API 新增 `RuntimeExecutionSessionRecord`、`listRuntimeApprovals`、`listRuntimeExecutionSessions`。
- 本轮 UI 保持只读，不直接在 Settings 页面执行 approve / run，避免把高风险写操作塞进配置页。

验证：

```bash
pytest tests/test_runtime_executor_routes.py::test_runtime_execution_sessions_list_checkpoint_and_replay_refs

cd apps/dashboard && npm test -- settings-page.test.tsx

pytest tests/test_execution_dispatch_contract.py tests/test_file_chat_routes.py tests/test_runtime_executor_routes.py

cd apps/dashboard && npm run build
```

结果：

- `1 passed, 1 warning`
- `28 passed`
- `99 passed, 1 warning`
- Dashboard build passed；Vite 仍提示已有 chunk-size warning。

当前状态：

- Phase A-F 的主要 backend/runtime/dashboard slice 已完成。
- 剩余增强项：
  - 把 approval 真正升级为 LangGraph interrupt/resume，而不仅是 `approval_request` + approved-run redispatch。
  - 做更完整的 Replay detail 页面，展示每个 tool event 的完整 payload、context refs、memory refs、Ticket refs 和 trace 时间线。
  - 对接真实 Plane / Graphiti 生产配置后的端到端 smoke。
