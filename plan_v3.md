# Runtime-first AITeamOS: 用成熟开源/本地/官方 Agent Loop Runtime 补齐 AITeamOS 薄弱执行层，chat_routes.py 退回治理编排层

状态：架构修正计划  
日期：2026-06-08  
适用范围：AITeamOS Chat / AI Engine / Execution / Permission / Context / Session / Tool / Subagent 相关实现

## Executive Summary

AITeamOS 的核心产品价值是治理层，不是重新实现一个通用 Agent Runtime。

架构决策：

```text
AITeamOS 负责治理事实和执行调度。
LangGraph / Claude Agent SDK / Claude Code / OpenHands / OpenCode / LocalToolExecutor / SpecializedWorkflowExecutor 负责具体 agent loop。
chat_routes.py 只保留 API 入口、governance orchestration、request assembly、execution dispatch、result ingestion。
```

这意味着：

- AITeamOS 继续拥有 Ticket ledger、Employee ledger、Asset provenance、Review Queue、Learning pipeline、Clara action planning、Graphiti recall、audit / approval / evidence / trace。
- AITeamOS 不再把 `chat_routes.py` 扩张成通用 agent loop、generic tool dispatcher、permission runtime、context compaction runtime、session persistence runtime 或 subagent runtime。
- Phase 0 不再是“让 `chat_routes.py` 的 stub 变成 remote-first AI engine”。
- Phase 0 更新为“定义 Execution Dispatch Contract，并接入 `LangGraphExecutor` 作为第一 executor”。

第一步工程落点：

```text
services/api/aiteamos_api/read/execution_contract.py
services/api/aiteamos_api/read/execution_dispatch_service.py
services/api/aiteamos_api/read/runtime_executors/base.py
services/api/aiteamos_api/read/runtime_executors/langgraph_executor.py
```

`chat_routes.py` 的改造目标不是继续“拆大文件但保持 route 负责执行”，而是把 route 降级为治理编排入口。

## Current Problem

当前项目已经接入 LangGraph：

- `pyproject.toml` 中已有 `langgraph`、`langgraph-checkpoint-sqlite`、`ag-ui-langgraph[fastapi]`。
- `chat_routes.py` 已有 AG-UI `/agent` bridge、`StateGraph`、SQLite checkpoint。
- `.aiteamos/langgraph/checkpoints.sqlite` 已作为 checkpoint 目标路径出现。

但实际执行主路径仍然在 `chat_routes.py` 手写：

- 规划：`_call_deepseek_command_planner`、`_heuristic_kernel_command_plan`、`_plan_kernel_command_intent`。
- 工具路由：`_KERNEL_COMMAND_HANDLERS`、`_execute_kernel_command_plan`、`_maybe_execute_kernel_command`。
- 权限判断：route 内调用 `evaluate_kernel_policy` 后直接分发 handler。
- 上下文组装：`_prepare_chat_run`、`_employee_agent_context_bundle`、`_ai_engine_context_gate`。
- session/thread：conversation、trace、engine thread、AG-UI checkpoint 同时由 route 附近维护。
- streaming：`_stream_chat_turn`、`_stream_agui_chat_events`、`/messages/stream` 内重复执行分支。
- terminal execution：route 内完成命令解析、allowlist、运行、写 Ticket evidence。

这已经在朝通用 Agent Runtime 方向膨胀。

必须明确批评当前方向：

- 我一直强调不要重复造轮子。
- 项目已经接入 LangGraph，为什么 `chat_routes.py` 还在朝通用 Agent Runtime 方向膨胀？
- `chat_routes.py` 应该变薄，只做 governance orchestration、request assembly、execution dispatch、result ingestion。
- 不应该继续在 route 层手写状态机、工具调用、上下文流转、权限判断、会话恢复和 streaming runtime。
- 应优先复用 LangGraph 已有能力，而不是在 FastAPI route 内部继续堆一套简陋 agent loop。

现状不是“缺少更多 route helper”，而是“职责边界错了”。

## Non-goals

AITeamOS 不做：

- 通用 Agent Framework。
- 通用 Agent IDE。
- 通用 chat reasoning loop。
- 通用 tool dispatch runtime。
- 通用 runtime permission / sandbox。
- 通用 context compaction runtime。
- 通用 subagent delegation runtime。
- 通用 session persistence runtime。
- 通用 tool ecosystem。
- Claude Code / OpenHands / OpenCode / Cline 的重实现。
- 在 AITeamOS 主仓库中 vendor 或重实现 Claude Code / OpenHands / OpenCode 等外部 runtime。

短期也不做：

- 用 route 层继续扩写一套更复杂的 `_stream_*` / `_execute_*` / `_plan_*` 状态机。
- 让 Graphiti 接管 Ticket ledger、approval state、permission authority、raw trace 或 raw tool log。
- 让 MCP / Tool Connector 变成 AITeamOS 自研 tool runtime。
- 把 Employee assignee / handoff 误建成 AITeamOS 自研 subagent scheduler。

## Architecture Decision

采用 Runtime-first 架构：

```text
Human / Chat UI
  -> chat_routes.py
  -> ChatGovernanceService
      -> Clara action planning
      -> scoped task context assembly
      -> governance permission / approval policy assembly
      -> ExecutionRequest
  -> ExecutionDispatchService
      -> choose executor
      -> call executor.run(request)
  -> Runtime Executor
      -> LangGraph / Claude Agent SDK / OpenHands / OpenCode / local workflow
      -> agent loop, tool loop, runtime permission, checkpoint, subagents
  -> ExecutionResult
  -> ResultIngestionService
      -> Ticket ledger
      -> Employee ledger
      -> Asset provenance
      -> Review Queue candidates
      -> learning_delta
      -> trace / evidence / audit
  -> Chat response / inspector
```

`ExecutionRequest` 和 `ExecutionResult` 是边界。AITeamOS 只负责：

1. 组装 `ExecutionRequest`。
2. 选择 executor。
3. 消费 `ExecutionResult`。
4. 将结果写回治理事实。

中间 agent loop 怎么运行，交给成熟 runtime。

## Governance Layer vs Execution Layer

| 范围 | AITeamOS Governance Layer | Execution Runtime Layer |
| --- | --- | --- |
| Work source of truth | Ticket ledger, Employee ledger, reports, evidence, validation, handoff | runtime-local task state |
| Planning | Clara action planning, expected outputs, approval policy | runtime internal step planning |
| Context | scoped task context from Ticket / Employee / assets / Graphiti | context use, compression, prompt assembly, memory window |
| Permission | governance permission, capability grants, approval policy | tool permission, sandbox, allow/deny, runtime safety |
| Tools | Capability Registry, Tool Connector catalog, Kernel capability facts | tool execution loop, MCP client use, shell/browser/file tools |
| Session | AITeamOS run id, ticket id, trace id, executor session refs | checkpoint, resume, internal messages, subagent sessions |
| Subagents | Employee records, assignee changes, handoff ledger | runtime-native subagents/delegation if supported |
| Output | reports, artifacts, evidence, memory candidates, learning delta | raw steps, tool events, generated artifacts |

AITeamOS 必须长期自建并拥有：

- Ticket ledger / accountability。
- Employee ledger / work journal。
- Asset provenance。
- Review Queue。
- Learning pipeline。
- Clara action planning。
- Graphiti / memory / asset recall。
- audit / approval / evidence / trace。

AITeamOS 不应该自研：

- chat reasoning loop。
- generic tool dispatch。
- permission runtime。
- context compaction。
- subagent delegation runtime。
- session persistence runtime。
- generic tool ecosystem。

## Runtime Adapter Strategy

定义统一 executor 插件接口：

```python
from collections.abc import AsyncIterator
from typing import Protocol


class RuntimeExecutor(Protocol):
    id: str
    display_name: str
    capabilities: set[str]

    async def run(self, request: ExecutionRequest) -> ExecutionResult:
        ...

    async def stream(self, request: ExecutionRequest) -> AsyncIterator[ExecutionEvent]:
        ...

    async def health(self) -> dict:
        ...
```

`run()` 是非流式收敛接口，`stream()` 是 Chat / AG-UI / SSE 保持原有交互体验的接口。第一版 executor 可以让 `run()` 消费同一条内部事件流并返回最终 `ExecutionResult`，但不能只设计 `run()` 后再让 route 层补一套 streaming runtime。

首批 executor：

- `LangGraphExecutor`
  - 第一优先 runtime。
  - 已接入依赖和 AG-UI bridge。
  - 作为默认 executor / fallback executor。
  - 负责最小 agent graph、checkpoint、tool loop、resume。
- `ClaudeAgentSDKExecutor`
  - 重要实验 executor。
  - 可用于 coding / repo work / long-running execution。
  - 不作为唯一关键路径。
- `ClaudeCodeExecutor`
  - 作为 Claude Code-compatible local CLI adapter，而不是绑定某一个 release 包来源。
  - AITeamOS 只配置 `binary_path`、`working_dir`、`command_template`、`model`、`api_base_url`、`api_key_env`、`mode`。
  - DeepSeek / OpenAI 等 LLM backend 可以通过 env / base URL / model 传给该本地 runtime。
  - 用于 inspect/report、repo edits with approval、test evidence。
  - approved repo mutation 必须返回 patch/diff 或 changed_files artifact，以及 runtime test evidence；否则 ingestion 前阻断。
  - 外部 runtime 源码、构建和本地 release 包存放在 AITeamOS 仓库之外，AITeamOS 只依赖本地兼容 CLI 边界。
- `OpenHandsExecutor`
  - 用于开源 coding agent runtime。
  - 适合 repo edit / test / browser-ish workflows。
  - 通过 `OPENHANDS_BASE_URL` + 可配置 `OPENHANDS_INSPECT_ENDPOINT` 走 HTTP inspect-and-report adapter；未配置 endpoint 时只产生 non-fake handoff。
- `OpenCodeExecutor`
  - 用于轻量 coding executor。
  - 适合本地 CLI 代理、review、patch proposal。
- `CursorExecutor`
  - 用于商业 agent backend。
  - 通过 `CURSOR_API_KEY`、`CURSOR_API_BASE_URL`、`CURSOR_INSPECT_ENDPOINT` 走可配置 HTTP inspect-and-report adapter。
  - 不在 AITeamOS 中硬编码非公开 provider route；缺少 endpoint 时返回 setup/handoff 状态，不伪装完成。
- `LocalToolExecutor`
  - 只承载 AITeamOS 内部确定性操作，例如 Ticket 写入、permission inspect、bounded local command evidence。
  - 不是通用 agent loop。
- `SpecializedWorkflowExecutor`
  - 用于固定工作流，例如 validation harness、Graphiti ingestion、Plane sync。
  - 适合 deterministic DAG，不适合通用聊天。

选择策略：

```text
1. 如果 action_plan 需要 general agent loop，优先 LangGraphExecutor。
2. 如果任务是 repo coding，并且 Claude Agent SDK / Claude Code 配置可用，可以实验使用 ClaudeAgentSDKExecutor / ClaudeCodeExecutor。
3. 如果需要开源 coding runtime，选择 OpenHandsExecutor 或 OpenCodeExecutor。
4. 如果是 AITeamOS 内部确定性 governance action，选择 LocalToolExecutor。
5. 如果是固定验证或同步流程，选择 SpecializedWorkflowExecutor。
6. executor 不可用时，返回 configuration blocker，不生成伪装完成的 stub。
```

## LangGraph Reuse Plan

LangGraph 是已接入的第一优先 runtime / fallback runtime，必须复用。

当前 LangGraph 主要在 `chat_routes.py` 中作为 AG-UI bridge 和 checkpoint 外壳。下一步要把它提升为正式 `LangGraphExecutor`：

```text
runtime_executors/langgraph_executor.py
  -> owns StateGraph
  -> owns checkpointer
  -> owns runtime state schema
  -> receives ExecutionRequest
  -> returns ExecutionResult
```

最小 LangGraph state：

```python
class LangGraphExecutionState(TypedDict, total=False):
    execution_request: dict
    messages: list
    current_step: str
    tool_events: list[dict]
    artifacts: list[dict]
    evidence: list[dict]
    approval_requests: list[dict]
    memory_candidates: list[dict]
    errors: list[dict]
    usage: dict
    final_report: str
```

第一版 graph 节点：

- `load_request`
  - 校验 `ExecutionRequest`。
  - 只读取 scoped context，不再全局拉取所有上下文。
- `plan_runtime_steps`
  - 交给 LangGraph / LLM / runtime node 规划。
  - AITeamOS 不在 route 中手写 heuristic state machine。
- `execute_tools`
  - 使用 LangGraph tool node 或 runtime-native tool integration。
  - AITeamOS 只提供 capability grants 和 approval policy。
- `request_approval`
  - 将高风险动作转成 `approval_requests`，由 AITeamOS ingestion 写入 Review / Approval。
- `produce_result`
  - 输出 `ExecutionResult`。

Checkpoint：

- LangGraph checkpoint 归 `LangGraphExecutor` 管。
- AITeamOS 只保存 `trace_context.executor_session_ref`、`checkpoint_ref`、`request_id`、`run_id`。
- Chat thread 不是 LangGraph internal session 的唯一来源。

AG-UI：

- `/api/v1/chat/agent` 可以保留 AG-UI streaming API。
- 但事件来源应从 `ExecutionResult` / executor stream 统一转换。
- 不再在 `/agent` 与 `/messages/stream` 中各写一套执行分支。

## Claude Agent SDK / Claude Code-compatible Runtime Positioning

Claude Code-compatible local runtime / Claude Agent SDK 可以作为重要 executor，但不应成为唯一关键路径。

原则：

- `ClaudeCodeExecutor` 面向 Claude Code-compatible local CLI，不绑定官方 release 包。
- AITeamOS 不在主仓库中 vendor、fork 或重实现外部 runtime；外部 runtime 由本地 `binary_path` / `command_template` 配置接入。
- DeepSeek / OpenAI 等 LLM backend 通过 `api_key_env`、`api_base_url`、`model` 等配置传给本地 runtime。
- 可以把 Claude Code-compatible local runtime / Claude Agent SDK 作为主要实验 executor。
- 不能让 Claude executor 变成 AITeamOS 的组织记忆层。
- 不能让 Claude executor 的 session 变成 AITeamOS 的 Ticket ledger。
- Claude 输出必须回收为 `ExecutionResult`，再由 AITeamOS 写入 report / artifacts / evidence / learning candidates。

建议先做 non-destructive 模式：

```text
ExecutionRequest
  -> ClaudeCodeExecutor / ClaudeAgentSDKExecutor inspect-and-report
  -> ExecutionResult(report, artifacts, evidence, trace_ref, tool_events)
  -> AITeamOS append Ticket report / evidence
```

repo mutation 必须满足：

- Ticket-bound。
- capability grant 包含 repo write。
- approval policy 允许或已有 approval。
- executor result 提供 patch / changed files / test evidence。
- AITeamOS ingestion 写入 Ticket report、evidence、trace 和 approval refs。
- 缺少 patch/changed files 或 test evidence 时返回 governance blocker，不写入成功 report。
- Chat / Clara 将已有 Ticket 上的实现类请求归一化为 `implement_ticket`，只生成 `ExecutionRequest` 和 approval request；真正执行仍由外部 `RuntimeExecutor` 完成。
- `ExecutionResultIngestionService` 必须作为第二道闸校验 approved repo mutation 的 patch/changed_files 和 runtime test evidence，防止伪造或绕过 executor guard 的结果写入成功 ledger。
- `ExecutionResult.approval_requests` 必须落为 AITeamOS approval records / Review Queue facts。
- approved external runtime run 必须从 approval record 重建 `ExecutionRequest`，注入 `approval_refs` / `approved_capabilities`，再通过 `ExecutionDispatchService` 执行。

## Execution Dispatch Contract

核心数据契约如下。第一版应放在：

```text
services/api/aiteamos_api/read/execution_contract.py
```

```python
from typing import Any
from pydantic import BaseModel, Field

from .chat_action_plan import ChatActionPlan


class TicketBinding(BaseModel):
    mode: str = "existing"  # existing | create | none
    ticket_id: str = ""
    required: bool = True


class ExecutionEvent(BaseModel):
    event: str
    request_id: str
    data: dict[str, Any] = Field(default_factory=dict)


class ExecutionRequest(BaseModel):
    request_id: str
    tenant_id: str
    workspace_id: str
    employee_id: str
    ticket_id: str
    ticket_binding: TicketBinding = Field(default_factory=TicketBinding)
    action_plan: ChatActionPlan
    task_context: dict[str, Any]
    capability_grants: list[str]
    permission_policy: dict[str, Any]
    budget: dict[str, Any]
    approval_policy: dict[str, Any]
    expected_outputs: dict[str, Any]
    trace_context: dict[str, Any]


class ExecutionResult(BaseModel):
    request_id: str
    executor_id: str
    status: str
    report: str
    output_ticket_id: str = ""
    artifacts: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    trace_ref: str
    executor_session_ref: str = ""
    checkpoint_ref: str = ""
    tool_events: list[dict[str, Any]]
    approval_requests: list[dict[str, Any]]
    memory_candidates: list[dict[str, Any]]
    learning_delta: dict[str, Any]
    errors: list[dict[str, Any]]
    usage: dict[str, Any]
    started_at: str = ""
    finished_at: str = ""
```

Required `ExecutionRequest` semantics:

- `request_id`
  - AITeamOS generated id.
  - Idempotency key for dispatch and ingestion.
- `tenant_id`
  - Keep default `local` until multi-tenant exists.
- `workspace_id`
  - Workspace or repo root logical id, not necessarily absolute path.
- `employee_id`
  - The Employee accountable for this execution.
- `ticket_id`
  - Convenience mirror for the active Ticket id when one already exists.
  - May be empty for `answer_only` or for `create_ticket` before the executor/runtime creates the Ticket.
- `ticket_binding`
  - `mode="existing"` means the task must bind to an existing Ticket.
  - `mode="create"` means the task is allowed to create a Ticket and must return `output_ticket_id`.
  - `mode="none"` is only for pure answer/governance read-only turns.
  - `required=True` means dispatch must return a typed blocker if the required binding cannot be satisfied.
- `action_plan`
  - Clara/AITeamOS action intent.
  - Should remain small and product-level.
- `task_context`
  - Scoped task context only.
  - No global dump.
- `capability_grants`
  - Governance-approved capabilities exposed to runtime.
- `permission_policy`
  - AITeamOS governance rules, not runtime sandbox implementation.
- `budget`
  - Time, token, cost, step, tool-call limits.
- `approval_policy`
  - What requires approval, who may approve, whether to pause or return request.
- `expected_outputs`
  - Required report/evidence/artifact schema.
- `trace_context`
  - AITeamOS run id, thread id, source message id, trace path, provider refs, executor session ref.

Required `ExecutionResult.status` values:

- `completed`
- `failed`
- `blocked`
- `needs_approval`
- `partial`
- `cancelled`

Required `ExecutionEvent.event` values for the first streaming adapter:

- `started`
- `delta`
- `tool_event`
- `approval_requested`
- `artifact_produced`
- `evidence_produced`
- `blocked`
- `error`
- `completed`

Streaming adapters must transform these events to SSE / AG-UI events. They must not rebuild executor-specific state machines in `chat_routes.py`.

Required ingestion behavior:

| Result field | AITeamOS ingestion target |
| --- | --- |
| `request_id` | idempotency / duplicate ingestion guard |
| `executor_id` | run metadata / System Status / analytics |
| `output_ticket_id` | created Ticket id or confirmed active Ticket id |
| `report` | Ticket report / Chat reply summary |
| `artifacts` | Asset registry / Ticket asset graph |
| `evidence` | Ticket evidence / validation evidence |
| `trace_ref` | run metadata / Chat inspector |
| `executor_session_ref` | execution session correlation |
| `checkpoint_ref` | resume/checkpoint correlation |
| `tool_events` | trace summary, not raw tool log as durable memory |
| `approval_requests` | Review Queue / approval records |
| `memory_candidates` | governed candidate queue |
| `learning_delta` | self-bootstrap learning summary |
| `errors` | blocker / failed report / system status signal |
| `usage` | analytics / cost / latency / executor health |

AITeamOS 只负责组装 `ExecutionRequest`、选择 executor、消费 `ExecutionResult`。中间 agent loop 怎么运行，交给 LangGraph / Claude Agent SDK / OpenHands / OpenCode 等 runtime。

## Context / Permission / Session / Tool / Subagent Strategy

### Context Strategy

AITeamOS 的 context 不应该变成全局大杂烩。

Context 应仅围绕“某个 Employee 发给某个 agent 的具体任务”组装。

允许来源：

- Ticket。
- Employee profile / role / skills。
- Employee memory。
- relevant assets。
- prior evidence。
- Graphiti recall。
- current approval policy。
- selected code repository scope。
- active validation requirements。

最终传给 runtime 的必须是 scoped task context：

```python
class ScopedTaskContext(BaseModel):
    task_summary: str
    ticket: dict
    employee: dict
    relevant_assets: list[dict]
    recalled_memories: list[dict]
    prior_evidence: list[dict]
    repository_scope: dict
    validation_requirements: list[dict]
    approval_policy_summary: dict
    exclusions: list[str]
```

硬规则：

- 不把所有 memory、所有 docs、所有 tickets、所有 tools 塞给 runtime。
- 不把 secrets、raw approval authority、raw permission policy、raw terminal logs 塞给 runtime。
- Graphiti recall 必须记录 query、scope、source asset、reason、confidence。
- Context assembly 应迁出 route，成为 `execution_context_service.py`。

### Permission Strategy

AITeamOS 定义 governance permission / approval policy。

Runtime 执行自己的 tool permission / sandbox / safety。

两者通过 `capability_grants` 和 `approval_policy` 对齐，而不是 AITeamOS 复制 runtime 的权限系统。

当前 `kernel_command_service.py` 已经明确 Kernel command layer 是 thin policy check，不是 agent framework。这个边界要保留。

分层规则：

- AITeamOS:
  - Employee 是否允许请求某类能力。
  - Ticket 是否绑定。
  - high-risk action 是否需要 approval。
  - result 是否能进入 ledger / asset / memory。
- Runtime:
  - 具体工具怎么调用。
  - shell/file/browser/network sandbox。
  - runtime-native permission prompts。
  - tool retry / failure / timeout。

映射示例：

```python
capability_grants = [
    "tickets:read",
    "tickets:write",
    "repo:read",
    "terminal:run",
]

approval_policy = {
    "require_approval_for": [
        "repo:write",
        "destructive_file_delete",
        "external_connector_write",
        "memory_approve",
    ],
    "on_missing_approval": "return_needs_approval",
}
```

### Session Strategy

AITeamOS session 不是 runtime session。

AITeamOS 保存：

- `request_id`
- `run_id`
- `thread_id`
- `ticket_id`
- `employee_id`
- `executor_id`
- `executor_session_ref`
- `checkpoint_ref`
- `trace_ref`
- result ingestion status

Runtime 保存：

- internal messages。
- checkpoint。
- compaction。
- subagent session。
- retry state。

当前 `.aiteamos/engine_threads.json` 可以演进为：

```text
.aiteamos/execution_sessions.json
```

第一版可以兼容旧字段，但新代码应使用 executor session vocabulary：

```json
{
  "employee_id::thread_id::ticket_id": {
    "executor_id": "langgraph",
    "executor_session_ref": "lg-...",
    "checkpoint_ref": "checkpoint-...",
    "last_request_id": "exec-...",
    "updated_at": "..."
  }
}
```

### Tool Strategy

AITeamOS 不做 generic tool ecosystem。

保留：

- Capability Registry:
  - 暴露 Kernel Commands、MCP Tools、native API tools、CLI/CI capabilities。
  - 用于 governance、visibility、planning、Settings、System Status。
- Tool Connectors:
  - 外部能力来源配置。
  - MCP Server 是 connector kind。
  - 不在 AITeamOS route 层实现所有 MCP/client tool loop。

执行：

- LangGraphExecutor / Claude / OpenHands / OpenCode 使用 runtime-native tools。
- AITeamOS 通过 `capability_grants` 告诉 runtime 哪些能力被治理层允许。
- runtime 返回 `tool_events` 摘要。
- AITeamOS 不把 raw tool logs 默认写入 Graphiti。
- `LocalToolExecutor` 只承载确定性 AITeamOS 内部操作，不演变成通用 tool loop。

### Subagent Strategy

AITeamOS 的 Employee 不是 runtime subagent。

AITeamOS 只记录：

- Ticket assignee。
- validator。
- handoff。
- report。
- evidence。
- accountability。

Runtime 可以内部使用 subagents，但必须满足：

- subagent 细节不替代 AITeamOS Employee ledger。
- 如果 runtime subagent 对结果有实质贡献，应在 `ExecutionResult.tool_events` 或 `artifacts/evidence` 中带 provenance summary。
- AITeamOS ingestion 可以把关键贡献映射为 Ticket report / evidence / handoff，但不要求复制 runtime 内部 subagent tree。

## Migration Plan

### Phase 0: Execution Dispatch Contract + LangGraphExecutor

目标：

把执行边界从 `chat_routes.py` 中抽出来，建立 Runtime-first 主路径。

任务：

1. 新增 `execution_contract.py`
   - `ExecutionRequest`
   - `ExecutionResult`
   - `ExecutionEvent`
   - `TicketBinding`
   - `ScopedTaskContext`
   - `ExecutorHealth`
2. 新增 `runtime_executors/base.py`
   - `RuntimeExecutor` protocol。
   - `run()` and `stream()`。
   - common status/error helpers。
3. 新增 `runtime_executors/langgraph_executor.py`
   - 使用已有 LangGraph 依赖。
   - 使用 SQLite checkpoint。
   - 第一版可以只支持 `answer_only`、`create_ticket`、`append_report`、`request_validation`。
4. 新增 `execution_context_service.py`
   - 从 Ticket / Employee / assets / Graphiti / prior evidence 组装 scoped task context。
5. 新增 `chat_action_planning_service.py`
   - Clara action planning 边界。
   - 负责把用户意图转成产品级 `ChatActionPlan`。
   - 不把旧的 route 内 heuristic planner 原样搬进去。
6. 新增 `execution_dispatch_service.py`
   - 根据 `ChatActionPlan`、AI Engine config、capability grants 选择 executor。
7. 新增 `execution_result_ingestion_service.py`
   - 消费 `ExecutionResult`。
   - 写 Ticket report / evidence / asset refs / memory candidates / learning delta。
8. `chat_routes.py`
   - route 只调用 `ChatGovernanceService.handle_message()`。
   - 不再直接运行 tool loop。

验收：

- `chat_routes.py` 中不再新增 agent loop 分支。
- `LangGraphExecutor.run()` 可以接收 `ExecutionRequest` 并返回 `ExecutionResult`。
- `LangGraphExecutor.stream()` 可以产生 `ExecutionEvent`，并由 Chat route 转为 SSE / AG-UI。
- `create_ticket` 使用 `ticket_binding.mode="create"`，并在结果中返回 `output_ticket_id`。
- Chat message path 通过 dispatch service 执行，而不是 route 内 `_maybe_execute_kernel_command` + `_call_deepseek_agent` 组合。
- configuration blocker 由 dispatch/executor 返回，route 只透传并记录。
- focused tests 覆盖 contract validation、executor selection、result ingestion。

### Phase 1: Thin chat_routes.py

目标：

让 `chat_routes.py` 退回 API boundary。

迁移内容：

- Pydantic chat API response/request 可以暂留 route 或迁入 `chat_models.py`。
- AI Engine settings routes 可以短期保留，但 AI Engine execution 不留在 route。
- AG-UI event encoding 可以保留在 route，但事件来源必须是 executor stream。
- 删除 route 内重复 streaming branch。
- `_prepare_chat_run` 拆为 governance request assembly。
- `_persist_chat_response` 拆为 result ingestion + chat transcript persistence。

验收：

- route 只包含 API handlers、request parsing、response formatting。
- route 不包含 provider-specific agent calls。
- route 不包含 terminal subprocess execution。
- route 不包含 kernel command handler registry。
- route 不包含 LangGraph graph definition。

### Phase 2: Governance Result Ingestion

目标：

把 runtime 输出稳定落回 AITeamOS 治理事实。

任务：

- `ExecutionResult.report` -> Ticket report。
- `ExecutionResult.evidence` -> Ticket evidence refs。
- `ExecutionResult.artifacts` -> Asset Registry / Ticket Asset Graph。
- `ExecutionResult.approval_requests` -> Review Queue / approval events。
- `ExecutionResult.memory_candidates` -> candidate queue。
- 外部 runtime 通过 `artifacts` / `learning_delta` 返回的 Decision / Doc / Skill / Capability / validated Ticket summary candidates 先归一化为 Review Queue candidates，approval 之后再投影到 Graphiti。
- `ExecutionResult.learning_delta` -> self-bootstrap summary。
- `ExecutionResult.tool_events` -> trace summary。
- `ExecutionResult.usage` -> Employee analytics / system status。

验收：

- Executor 换成不同 runtime，Ticket/Employee/Asset 视图不需要理解 runtime internals。
- 从 Ticket detail 能看到报告、证据、trace、artifact、approval、learning refs。

### Phase 3: Executor Expansion

目标：

在 LangGraph 主路径稳定后，按 adapter 接入外部 executor。

顺序：

1. `LocalToolExecutor`
   - deterministic governance actions。
   - permission inspect、Ticket append、Graphiti ingestion、bounded evidence command。
2. `ClaudeAgentSDKExecutor` 或 `ClaudeCodeExecutor`
   - inspect-and-report。
   - repo write 只在 approval 后启用。
3. `OpenHandsExecutor`
   - coding tasks。
4. `OpenCodeExecutor`
   - lightweight coding/review。
5. `SpecializedWorkflowExecutor`
   - validation harness、Plane sync、Graphiti projection。

每个 executor 必须提供：

- health。
- config status。
- capability declaration。
- supported action types。
- result normalization。
- failure/blocker semantics。
- non-destructive smoke diagnostics, routed through `ExecutionDispatchService` and `RuntimeExecutor` instead of route-level subprocess or provider helpers。
- optional smoke-result ingestion that is Ticket-bound; if no Ticket is supplied, diagnostics must report setup/blocker/result facts without fake ledger completion。
- 对本地 CLI 或 HTTP API runtime，必须把 report / artifacts / evidence / usage 规范化为 `ExecutionResult`。
- 对外部 runtime 产出的 durable asset candidates，必须保留 Ticket / Employee / run / executor provenance，并进入 AITeamOS Review Queue；runtime 不能绕过 approval 直接成为 durable memory。

### Phase 4: Self-bootstrap On Runtime-first

目标：

用新 execution dispatch 主路径跑 AITeamOS 自身改进 Ticket。

Carry-over 自 `next_plan.md` 的自举目标仍然保留：

- Clara 创建或选择 Ticket。
- Ticket 带 assignee / validator / context / acceptance criteria。
- AI Employee 接手、执行、汇报、交接、请求验证。
- PV 或其他 Employee 验证结果并写入 evidence。
- Clara 基于结构化事实总结结果和下一步。
- Memory / Decision / Skill / Doc candidates 进入 Review Queue。
- 审核通过的资产进入 Graphiti / durable asset recall。
- 后续类似 Ticket 自动召回相关资产。
- 系统能分析每个 AI Employee 的行为、贡献、质量和绩效。

差异：

- 执行 loop 不在 `chat_routes.py`。
- 任务执行交给 executor runtime。
- AITeamOS 保留治理、学习和问责。

## Changes to chat_routes.py

`chat_routes.py` 最终职责：

- `GET /employees`
- `GET /skills`
- `GET/PUT /ai-engines`
- `GET/POST/DELETE /threads`
- `POST /messages`
- `POST /messages/stream`
- `POST /agent`
- request/response model glue
- call governance service
- convert executor stream to SSE / AG-UI events

`chat_routes.py` 不再负责：

- provider-specific LLM API call。
- hand-written command planner。
- heuristic intent classifier。
- generic kernel command dispatch。
- terminal subprocess execution。
- LangGraph graph construction。
- checkpoint implementation。
- context bundle internals。
- Graphiti recall internals。
- memory candidate extraction。
- result ingestion business rules。

Recommended module split:

```text
services/api/aiteamos_api/read/chat_routes.py
services/api/aiteamos_api/read/chat_models.py
services/api/aiteamos_api/read/chat_governance_service.py
services/api/aiteamos_api/read/chat_action_planning_service.py
services/api/aiteamos_api/read/execution_contract.py
services/api/aiteamos_api/read/execution_context_service.py
services/api/aiteamos_api/read/execution_dispatch_service.py
services/api/aiteamos_api/read/execution_result_ingestion_service.py
services/api/aiteamos_api/read/execution_session_store.py
services/api/aiteamos_api/read/runtime_executors/
  __init__.py
  base.py
  langgraph_executor.py
  local_tool_executor.py
  claude_agent_sdk_executor.py
  claude_code_executor.py
  openhands_executor.py
  opencode_executor.py
  specialized_workflow_executor.py
```

Migration style：

- 先新增 contract 和 service。
- 再让 route 委托新 service。
- 再删除 route 内旧分支。
- 每次只移动一个边界。
- 每次保留 focused tests。

## Carry-over from next_plan.md

`next_plan.md` 中仍然合理、应并入 `plan_v3.md` 后续实现的内容：

- Ticket-flow-first 总目标。
- Clara-led Ticket Operating Loop。
- Plane-backed Ticket Backend。
- Graphiti 作为 Persistent Asset Knowledge Graph projection。
- Review Queue 和 Memory / Decision / Skill / Doc candidates。
- Ticket Asset Graph read model。
- Employee analytics。
- validation / harness / evidence discipline。
- self-bootstrap learning summary。
- learning effectiveness。
- stale / superseded / conflicts asset handling。
- System Status secrets health。
- Chat run inspector 展示 loaded context、recalled memories、action plan、execution dispatch、policy decision、Ticket events、saved paths。
- agent-platform handoff 的上下文、artifact import、approval、evidence 要求。

必须修正的内容：

- Phase 0 不再是“稳定 remote AI Engine answer-only + local command intercept”。
- Phase 0 不再继续强化 `chat_routes.py` 内部 command planner / remote-first 分支。
- Phase 0 改为 Execution Dispatch Contract + `LangGraphExecutor`。
- `ChatActionPlan` 不直接等于 route 内 Kernel handler。
- `ChatActionPlan` 由 `ChatGovernanceService` / `chat_action_planning_service.py` 生成，不能回流成 `chat_routes.py` 里的 heuristic planner。
- `AI Engine` 概念要升级为可覆盖 model API 和 agent platform executor，但执行通过 Runtime Adapter。
- `Kernel Commands` 保留为 AITeamOS governance capabilities，不是通用 runtime tools。
- `terminal.run` 如果保留，应作为 `LocalToolExecutor` 或 runtime tool，不在 route 层执行。
- 如果 action 所需的 Plane / Graphiti / repository / connector 基础事实不可用，dispatch 必须返回 setup blocker，不能继续生成 local-only fake completion。

从 `next_plan.md` 继承的 Phase 目标重排：

```text
Phase 0: Execution Dispatch Contract + LangGraphExecutor
Phase 0.5: Plane + Graphiti base remains important, but must integrate through result ingestion
Phase 1: Clara-led Ticket Operating Loop over Execution Dispatch
Phase 2: Ticket Asset Graph MVP
Phase 3a: candidate -> approval -> Graphiti recall
Phase 3b: broader durable assets -> Graphiti projection
Phase 4a: Employee analytics core metrics
Phase 4b: behavior quality and learning effectiveness
Phase 5: Validation / Harness / Evidence Discipline
Phase 6: Self-bootstrap Mode
Phase 7: Additional executor adapters and advanced external execution
```

## Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| LangGraph integration remains a thin wrapper | route continues to grow | Make `LangGraphExecutor` the first acceptance target, not just AG-UI bridge |
| Runtime result is too unstructured | ingestion becomes brittle | Enforce `ExecutionResult` schema and expected_outputs |
| Executor-specific details leak into Ticket model | vendor lock-in | Store provider refs and executor refs as metadata only |
| AITeamOS permission duplicates runtime sandbox | complexity and false safety | Keep governance permission in `capability_grants`; runtime owns tool sandbox |
| Context becomes global dump | cost, leakage, poor reasoning | Require `ScopedTaskContext` and trace recall provenance |
| Claude Code becomes single critical path | commercial and operational risk | Keep LangGraph default/fallback; support pluggable executors |
| Runtime implementation becomes tightly coupled to one package source | vendor lock-in and brittle upgrades | Keep runtime source/build out of AITeamOS; configure compatible local CLI/API through adapter settings |
| LocalToolExecutor becomes another agent runtime | wheel reinvention returns | Limit it to deterministic AITeamOS governance operations |
| Result ingestion hides failures | false accountability | Require status, errors, evidence, trace_ref, usage |
| Streaming duplicated across endpoints | inconsistent behavior | Normalize executor stream -> SSE / AG-UI adapters |

## Acceptance Criteria

Architecture acceptance:

- `plan_v3.md` exists at project root and supersedes `next_plan.md` Phase 0 direction.
- AITeamOS governance boundary is explicit.
- Execution runtime boundary is explicit.
- Dashboard Chat remains the primary work surface; executor details appear as inspector/status, not as a required new execution console.
- `chat_routes.py` target responsibility is thin and non-runtime.
- LangGraph is the first executor, not just a side bridge.
- Claude Agent SDK / Claude Code are optional executor adapters, not the only key path.
- Claude Code is modeled as a compatible local CLI adapter; AITeamOS does not vendor or reimplement its runtime source.
- RuntimeExecutor non-sensitive adapter configuration is persisted in `.aiteamos/runtime_executors.json`; secrets remain environment variable references.
- Runtime executor smoke diagnostics exist for non-destructive CLI/HTTP adapter checks, dispatch through `RuntimeExecutor`, and only ingest results when bound to a Ticket.
- Ticket-bound repo implementation requests can flow from Chat into `implement_ticket`, return external runtime approval requests, and remain blocked from successful ingestion without patch/changed_files plus runtime test evidence.
- Runtime executor approval APIs can list/review approval records and run an approved external runtime request without route-level subprocess execution.
- Assets / Review Queue UI lists runtime approval records beside memory / decision / skill / tool candidates, can approve or reject them, and can trigger an approved runtime run through the RuntimeExecutor API while surfacing setup blockers instead of fake completion.

Phase 0 engineering acceptance:

- `ExecutionRequest` and `ExecutionResult` Pydantic models exist.
- `TicketBinding` supports existing Ticket, create Ticket, and no Ticket cases.
- `ExecutionEvent` supports streaming without route-level executor branching.
- `ExecutionDispatchService` can choose `LangGraphExecutor`.
- `LangGraphExecutor` can execute an `ExecutionRequest` and return `ExecutionResult`.
- `LangGraphExecutor` can stream `ExecutionEvent` for Chat / AG-UI.
- `chat_routes.py` calls dispatch service for `/messages`.
- `ExecutionResult` ingestion writes report/evidence/trace metadata.
- `ExecutionResult` carries `request_id`, `executor_id`, `executor_session_ref`, `checkpoint_ref`, and `output_ticket_id`.
- configuration blockers are represented as `ExecutionResult(status="blocked")` or equivalent typed blocker.
- no new generic agent loop code is added to `chat_routes.py`.

Context acceptance:

- Context assembly is scoped to one Employee and one task.
- Context includes Ticket, Employee memory, relevant assets, prior evidence, Graphiti recall, approval policy as needed.
- Context excludes raw secrets, raw permission authority, raw terminal logs, and unrelated global memory dumps.
- Trace records what was recalled and why.

Permission acceptance:

- AITeamOS produces `capability_grants` and `approval_policy`.
- Runtime owns tool permission and sandbox implementation.
- High-risk actions return approval requests instead of silently executing.
- Approval requests land in Review Queue / approval records.
- Runtime approval records are visible and actionable from the existing Assets Review Queue, not from a separate agent console.

Tool acceptance:

- Capability Registry remains catalog/governance/read-model.
- Runtime adapters execute tools through runtime-native mechanisms.
- Tool events return as normalized summaries.
- Raw tool logs are trace/audit material, not durable Graphiti memory by default.

Session acceptance:

- AITeamOS stores `executor_session_ref` and `checkpoint_ref`.
- Runtime owns internal checkpoint/resume.
- Chat thread, Ticket id, Employee id, request id, and executor session can be correlated in trace.

Subagent acceptance:

- AITeamOS Employee ledger remains based on assignee/report/validation/handoff facts.
- Runtime subagents do not replace Employee records.
- Runtime subagent contributions are imported only as result provenance where useful.

Verification acceptance for implementation slices:

```bash
pytest
cd apps/dashboard && npm test
cd apps/dashboard && npm run build
```

Focused tests to add first:

```text
tests/test_execution_contract.py
tests/test_execution_dispatch_service.py
tests/test_langgraph_executor.py
tests/test_execution_result_ingestion.py
tests/test_file_chat_routes.py
```

## Immediate Next Step

先改 `services/api/aiteamos_api/read/execution_contract.py`，一次性把 `ExecutionRequest`、`ExecutionResult`、`ExecutionEvent`、`TicketBinding` 和 `ScopedTaskContext` 放进去。

顺序：

1. 新增 execution contract，先覆盖 Ticket 创建绑定、result correlation 和 streaming event。
2. 新增 executor base protocol，包含 `run()` 和 `stream()`。
3. 新增 `chat_action_planning_service.py`，让 Clara action planning 离开 route 层。
4. 新增 minimal `LangGraphExecutor`。
5. 新增 dispatch service。
6. 让 `chat_routes.py` 的 `/messages` 走 dispatch service。
7. 再迁移 streaming 和 AG-UI bridge 到 executor event adapter。

不要从继续扩写 `chat_routes.py` 的 remote AI Engine 分支开始。
