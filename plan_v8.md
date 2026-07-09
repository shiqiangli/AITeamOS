# AITeamOS plan_v8: Stable Usable AI Team OS

状态：v5 / v6 / v7 之后的稳定落地基线  
日期：2026-06-21  
决策：`plan_v8.md` 不是新的实施日志，而是后续实现的稳定执行宪法。它继承 v5 / v6 / v7 的目标、原则、架构和初衷，同时把优先级调整为 backend/runtime 与 UI 成对推进，目标是让用户能够稳定使用真实的 AI Team OS。

## 0. 文档规则

`plan_v8.md` 一旦确认，默认不再频繁追加 implementation log。

允许修改 `plan_v8.md` 的情况：

- 发现 v5 / v6 / v7 原则与现实实现存在方向性冲突。
- 发现当前 v8 优先级会把系统带向错误架构。
- 用户明确要求调整 v8 目标、原则、优先级或完成定义。

不应写入 `plan_v8.md` 的内容：

- 每轮代码变更清单。
- 每轮测试 stdout。
- 单次 dogfood 的长 JSON 摘要。
- 已经 superseded 的临时 blocker 细节。

这些内容应进入：

- `.aiteamos/artifacts/plan_v8/...`
- `plan_v8_progress.md`
- 专门的 decision record / evidence summary

## 1. 一句话目标

把已经证明可跑通的 LangGraph-native AITeamOS 打磨成用户可稳定使用、长期可维护、可扩展、可运营的真实 AI Team Operating System：LangGraph 负责 autonomous team loop，DeepSeek 暂时作为 LangGraph / LangChain 后面的模型供应商；AITeamOS 只掌控 Ticket / Employees / Assets / Governance / Provenance / Provider Boundary；Chat、Tickets、Assets、Employees、Runtime Replay、System Status 等 UI 必须同步呈现真实 runtime 事实，而不是只让后端 artifact 通过。

## 2. 继承原则

v8 不推翻 v5 / v6 / v7。以下原则继续是硬约束：

- AITeamOS 的产品核心是 Ticket / Employees / Assets / Governance。
- Tickets 是所有 Employee 协作、交接、汇报、验证、阻塞处理、复盘和沉淀结论的主通道。
- Employees 像真实成员一样拥有固定身份、能力标签、性格标签、权限边界、工作历史、记忆范围、当前负载和 handoff 策略。
- Assets 是长期组织资产层；Memory、Docs、Skills、Tooling calls、解决方案、建议、复盘、验证结果和 closeout 都必须以可审计 provenance 进入资产体系。
- LangGraph 是默认 autonomous agent runtime；LangGraph 已有的 graph execution、checkpoint、interrupt、resume、thread、state 和 handoff 能力不在 AITeamOS 里重做。
- DeepSeek API 暂定为默认 LLM provider，但只能通过 LangGraph / LangChain model-provider wiring 使用；AITeamOS 不保留 primary direct LLM Chat / Ticket / Employee loop。
- Codex CLI、Claude Code、OpenHands、Cursor、OpenCode 等只属于可选 repo-write / coding RuntimeExecutor adapters，不能替代 LangGraph core loop 证明。
- Graphiti 是 approved Assets 的 projection / recall provider，不是 AITeamOS durable memory source of truth。
- Plane / Graphiti / commercial runtime / local fallback 都必须挂在 AITeamOS provider adapter 和 governance boundary 后面，不能反过来定义 AITeamOS 产品模型。
- Chat UI 可以很强，但不能重新实现 agent loop、runtime state machine、custom memory database 或 generic observability platform。

## 2.5 开源 / 外部模块分工

本节来自 v5 / v6 / v7 已经达成一致的设计，不重新调研或改方向。后续实现如果遇到模块边界不清，优先按本节判断。

核心规则：每一类 concern 只能有一个 primary owner。其它模块只能作为 reference、adapter、provider 或 compatibility layer，不能并列实现第二套主路径。

| Concern | Primary owner | AITeamOS 使用方式 | 不允许 |
| --- | --- | --- | --- |
| Autonomous loop / checkpoint / interrupt / handoff | LangGraph | 主 Workbench graph 和 Agent Server runtime | 再用 LangChain Agent、Chat route 或前端状态机实现第二套 loop |
| Model provider wiring | LangChain | DeepSeek / OpenAI 等模型供应商接入 | AITeamOS 直接调用 DeepSeek/OpenAI 作为 primary path |
| Frontend runtime state bridge | LangChain Frontend SDK | message stream、tool lifecycle、interrupt、custom graph state | 手写 parallel streaming/thread/tool-call state glue |
| Message UI primitives | assistant-ui | thread、composer、message/action components | 自研通用 Chat component framework |
| Workbench UX reference | Agent Chat UI | 参考布局、交互、可抽取组件模式 | 整页强行嵌入并复制 AITeamOS domain shell |
| Compatibility protocol | AG-UI | named compatibility adapter / external agent bridge | 回流主 Chat path |
| Durable product truth | AITeamOS | Tickets / Employees / Assets / Governance | 让 LangGraph / Graphiti / Plane 成为业务 source of truth |
| Projection / recall | Graphiti | approved Asset temporal graph projection / search | 写入未经审批的 durable memory 或伪造 recall 成功 |
| Runtime API / deployment | Agent Server | assistant / thread / run API 和部署运行 | 替代 AITeamOS domain APIs |
| Trace / eval / observability | LangSmith | tracing、eval、debugging、observability | 替代 Ticket / Runtime Replay / Asset provenance |
| Repo-write coding execution | RuntimeExecutors | Codex CLI / Claude Code / OpenHands 等 governed adapters | 替代 LangGraph core-loop proof |
| Ticket backend provider | Plane adapter | Ticket provider refs、sync、comments、reports | 让 Plane 状态机定义 AITeamOS Ticket semantics |

### LangGraph

定位：默认后端 agent runtime / graph orchestration。

AITeamOS 使用 LangGraph 负责：

- long-running stateful execution
- graph nodes / edges / conditional routing
- checkpoint / thread / run state
- interrupt / resume
- human approval pause point
- tool execution orchestration
- Employee handoff graph
- Ticket-native autonomous loop

LangGraph 不负责定义 AITeamOS 的 Ticket / Employee / Asset / Governance 业务模型，也不保存 durable organizational memory。

### LangChain

定位：agent building blocks 和 model / tool / middleware / context engineering 层，不是单纯前端 UI。

AITeamOS 使用 LangChain 负责：

- model abstraction
- DeepSeek / OpenAI 等 model-provider wiring
- tool schema / tool calling primitives
- middleware / context engineering building blocks
- LangGraph integration
- frontend SDK runtime bridge

DeepSeek 暂时是 LangChain / LangGraph 后面的模型供应商，不是 AITeamOS 自己直接调用的 agent runtime。AITeamOS 不使用 LangChain Agent / agent harness 作为 primary autonomous loop；如需使用 LangChain agent building blocks，也必须被 LangGraph graph 和 AITeamOS governance contract 包住。

### LangChain Frontend SDK

定位：前端到 LangGraph / Agent Server 的 runtime state 连接层，不是完整 Chat 页面。

AITeamOS 使用它负责：

- messages streaming
- tool-call lifecycle
- interrupts
- checkpoint / thread rejoin
- custom graph state values
- frontend 与 LangGraph server 的 runtime state 同步

它应替代我们手写 streaming / thread / tool-call state glue。它不负责 AITeamOS 的 Ticket / Employee / Asset 业务 UI。

### Agent Chat UI

定位：成熟 Agent Chat 产品蓝本和交互参考，不是 primary component runtime。

AITeamOS 使用它作为：

- Chat Workbench 页面蓝本
- thread / run / assistant UX 参考
- tool visualization 参考
- time-travel / state forking 参考
- 可抽取组件和行为模式来源

它不一定整页嵌入 AITeamOS Dashboard。如果技术栈或依赖成本过高，优先抽取行为、布局和组件模式。不能同时引入 Agent Chat UI 和 assistant-ui 两套 message thread / composer / tool visualization 主实现；v8 默认 assistant-ui 是 primary component layer，Agent Chat UI 是 reference / selective extraction source。

### assistant-ui

定位：React AI Chat components 和 runtime primitives。

AITeamOS 使用 assistant-ui 负责：

- message thread
- composer
- message branching
- attachments
- markdown / action components
- LangChain / LangGraph bridge components

assistant-ui 是 UI component 层；LangChain Frontend SDK 是 runtime state bridge。两者可以组合，但都不能替代 AITeamOS 的 Ticket / Employee / Asset / Governance panels。

### AG-UI

定位：agent-user interaction protocol / compatibility layer。

在 AITeamOS 主线中，AG-UI 不再决定 Chat 页面结构，也不是 primary Chat runtime。

AITeamOS 只保留 AG-UI 用于：

- compatibility protocol
- external agent UI adapter
- optional multi-runtime bridge

如果 LangChain Frontend SDK 已经直连 LangGraph runtime，AG-UI 不应回流主 Chat path。主 Chat path 不应 import AG-UI；AG-UI 只能出现在明确命名的 compatibility adapter 中，且测试不能把 AG-UI path 当主路径验收。

### Graphiti

定位：approved Assets 的 temporal graph projection / retrieval provider。

AITeamOS 使用 Graphiti 负责：

- approved Asset projection
- temporal memory graph
- relationship search
- fact evolution
- graph-based recall

Graphiti 不是 source of truth。即使 Graphiti down，approved Assets、Ticket ledger、Employee memory scope 仍应存在；recall 降级必须显示 blocker，不能伪造成功 recall。

### Agent Server

定位：LangGraph 生产化 deployment/runtime API 层。

AITeamOS 可以使用 Agent Server 负责：

- hosted / managed LangGraph deployment
- assistant / thread / run API
- production task queue

Agent Server 不能替代 AITeamOS domain APIs，也不能成为 Ticket / Employee / Asset / Governance source of truth。

### LangSmith

定位：trace / eval / debugging / observability 层。

AITeamOS 可以使用 LangSmith 负责：

- trace / eval / debugging
- observability

LangSmith 不能替代 Ticket ledger、Runtime Replay、Asset provenance 或 provider blocker UI。

### External RuntimeExecutors

定位：可选 repo-write / coding / commercial agent adapters。

包括但不限于：

- Codex CLI
- Claude Code
- Claude Agent SDK
- Cursor
- OpenHands
- OpenCode
- future commercial agent APIs

这些 executor 必须位于 `ExecutionRequest` / `ExecutionResult` / approval / evidence contract 后面。它们可以执行 governed coding 或 repo mutation，但不能成为 AITeamOS 默认 autonomous team loop，也不能替代 LangGraph core-loop dogfood。

### Plane and Provider Adapters

定位：外部业务系统 provider，不是 AITeamOS 产品模型本身。

Plane 可以作为 Ticket backend provider，但 AITeamOS 仍然拥有：

- Ticket semantics
- Employee assignment / handoff rules
- reports / evidence / validation
- provider refs
- blocker visibility
- governance and provenance

任何 provider failure 都必须进入 backend evidence 和 UI，不允许被 answer-only summary、direct LLM fallback 或 repo-write adapter 证明掩盖。

## 3. v8 优先级调整

v7 的主要成果是证明了 core loop 和 production-readiness gate。v8 的重点是让系统稳定可用。

新的执行原则：

- Backend/runtime 与 UI 必须成对推进。
- 每个 runtime/backend slice 必须有对应 UI acceptance。
- 后端 artifact 通过但用户在 UI 看不到正确状态，不算完成。
- Chat 页面是最高优先级用户体验面；用户提问后必须看到可理解的 assistant reply、blocked reason、approval request、handoff、Ticket/Asset provenance 或 retry cause。
- Runtime contract 要清晰、清爽、干净；UI 只映射 contract，不在前端发明伪 runtime 状态。
- 任何 provider blocker 都要同时出现在 backend evidence 和用户可见页面。

## 4. 当前真实状态

当前状态以 v7 最新 evidence 为基线：

- LangGraph core loop 已被 fresh Agent Server live dogfood 证明。
- DeepSeek 已收敛到 LangChain / LangGraph model-provider boundary 后面。
- `direct_llm` 不应存在于默认 RuntimeExecutor registry、dispatch、System Status 或 production-readiness evidence 中。
- Plane Ticket backend、governed handoff/report、MemoryCandidate、AssetRecord、Graphiti projection/recall 已有真实 dogfood 证据。
- Chat Workbench 已接入 LangGraph-native runtime 和多个 AITeamOS state panels。
- Runtime Replay、Agent Server matrix、Ticket-loop queue worker、provider conformance 和 artifact summary 已有较强验证基础。

但仍未达到 v8 目标：

- Chat 正常问答路径仍可能出现用户看不到 assistant reply、只在 Thread Context 看到内部 Reply、或界面只显示 Retry 的问题。
- Backend/runtime 仍有少量 route/runtime compatibility residue，需要继续清理到更干净的 graph/service 边界。
- Chat 页面和部分 panels 仍偏重，需要继续削薄 runtime bridge、thread state、approval panel 和 error mapping。
- Ticket-loop reliability 还需要 fresh Agent Server / live-provider 条件下的 repeated soak。
- Graphiti / Neo4j、Plane 等 provider 稳定性需要更长时间和更高压力下的证据。
- Employee 长期成长、质量反馈、能力演进和完整 profile UI 仍不够成熟。
- Worktree / artifact / generated data 需要形成可提交、可回滚、可审计的 release hygiene。

## 5. Track A: Chat 可用性和 Reply Contract

目标：用户在 Chat 页面提问后，主线程必须正确显示最终回复或可理解的状态，而不是把结果藏在 Thread Context 或只显示 Retry。

必须完成：

- 定义 Chat-visible response contract：
  - assistant message
  - runtime status
  - blocked reason
  - retry cause
  - approval request
  - handoff summary
  - Ticket refs
  - Asset / Memory refs
  - provider blockers
- 后端只能输出一套权威 contract；前端不猜测 runtime 状态。
- Chat main thread 必须渲染普通 assistant reply。
- 如果 runtime blocked，主线程显示 blocker 摘要，并提供对应 panel deep link。
- 如果需要 approval，主线程和 Approval panel 同步显示。
- 如果发生 handoff，主线程、Ticket panel、Employee panel 同步显示。
- 如果有 Asset candidate / Memory candidate，主线程可见摘要，Assets panel 显示详情。

验收：

- 用户输入一个普通测试问题，Chat 主线程出现 assistant reply。
- 同一个回复在 Thread Context 中可追溯，但 Thread Context 不是唯一可见位置。
- 任何 Retry 状态都必须有具体原因和可操作路径。
- Chat page test / E2E 覆盖 completed、blocked、needs approval、handoff、provider blocker 五类状态。

## 6. Track B: Backend / Runtime Boundary Cleanup

目标：让 backend/runtime 清晰、清爽、干净，继续收敛到 LangGraph-native graph + domain services。

必须完成：

- Chat route 只保留入口、request parsing、response/stream adapter。
- Orchestration 留在 LangGraph nodes 或 domain services。
- 清理 domain services 对 `chat_routes.py` 的依赖。
- 将剩余 `chat_runtime_factory` compatibility 明确包在 Workbench runtime context boundary 内，并逐步替换成 route-free services。
- Runtime dispatch 只通过 `ExecutionRequest` / `ExecutionResult` / `ExecutionEvent`。
- Direct LLM residue scan 继续作为 gate。
- DeepSeek/OpenAI 只能通过 `LangChainModelProvider` 或 LangGraph-compatible provider wiring。

验收：

- 新增 runtime 功能不修改 route handler 内部 agent loop。
- direct LLM scan 只允许负向 guard / historical docs 命中。
- LangGraph Agent Server fresh smoke 能跑主图，不依赖 stale server 或 `--allow-blocking`。
- Backend tests 能证明 Chat response contract 与 ExecutionResult 一致。

## 7. Track C: Fresh Agent Server + Live Provider Soak

目标：从“单次 live dogfood 通过”升级到“重复运行仍稳定”。

必须完成：

- 所有 live dogfood 默认启动 fresh Agent Server，或明确证明当前 Agent Server 使用的是当前代码。
- repeated Ticket-loop under fresh Agent Server / live-provider conditions。
- 覆盖 completed、blocked、retry、handoff、approval、closeout、Asset proposal。
- Graphiti / Neo4j provider 长时稳定性观察。
- Plane handoff/report/comment 写入的 retry、blocker、evidence、UI 呈现。
- artifact summary 能区分 temporary provider noise、real blocker、architecture regression。

验收：

- 多轮 Ticket-loop soak 通过，且每轮都有 Ticket report/evidence。
- repeated failure 能产生 governed retrospective / Asset candidate。
- provider blocker 不会被 answer-only summary、Codex CLI 或 direct LLM fallback 掩盖。
- System Status / Runtime Replay / Tickets UI 可见 live-provider health 和 blocker。

## 8. Track D: Workbench UI and Domain Pages

目标：让 UI 成为真实操作系统界面，而不是 backend JSON 的旁观者。

Chat 页面必须呈现：

- main assistant reply
- runtime status
- current Employee
- active Ticket
- pending approval
- handoff summary
- provider blockers
- Ticket loop policy / retry / resume
- Asset candidates
- recalled Memory / Assets
- provenance and replay links

Tickets 页面必须呈现：

- Ticket timeline
- current assignee / validation owner
- reports / evidence
- blockers
- retry / resume / closeout settlement
- linked Assets / Memory
- provider sync status

Assets 页面必须呈现：

- candidates
- review state
- approved AssetRecord
- Graphiti projection state
- relationships such as supersedes / conflicts_with
- provenance back to Ticket / Employee / runtime run

Employees 页面必须呈现：

- identity and capability tags
- personality / role summary
- permissions
- current load
- work history
- handoff policy facts
- quality feedback and improvement candidates

Runtime Replay / System Status 必须呈现：

- core loop health
- Agent Server evidence
- provider readiness
- direct-free runtime registry
- replay coverage
- setup blockers

验收：

- 用户不需要打开 artifact JSON 才能理解当前工作状态。
- UI 不显示裸 `Retry`、空白回复或无解释 blocker。
- 每个 backend/runtime slice 都有对应页面验收。

## 9. Track E: Employee Growth and Team Operation

目标：让 Employees 更像长期团队成员，而不是静态 profile。

必须完成：

- work history 自动更新并可用于 handoff。
- quality feedback 进入 governed Employee improvement candidate。
- approved improvement 可以更新 Employee profile / skills / memory scope。
- current load 和 risk boundary 影响 assignment。
- handoff reason 解释 capability、memory scope、load、risk、Ticket state。
- Employee detail UI 展示长期变化，而不是只显示静态 YAML。

验收：

- 一个 Ticket 的执行、反馈、复盘能沉淀为 Employee work history。
- 后续 handoff 能引用该 history。
- Employee improvement 不绕过 Review / Asset governance。

## 10. Track F: Durable Assets and Recall Quality

目标：让 Assets 成为 AITeamOS 最重要的长期组织资产层。

必须完成：

- Memory / Docs / Skills / Tooling calls / decisions / solutions / validation / closeout 统一进入 Asset lifecycle。
- Candidate -> Review -> approved AssetRecord -> Graphiti projection -> recall 可审计。
- stale / conflicted / superseded Assets 不应污染 active context。
- recall result 必须带 source, scope, confidence, exclusion reason, provenance。
- usefulness feedback 能影响后续 retrieval。

验收：

- 一个已验证解决方案能从 Ticket closeout 进入 approved Asset，再被后续 Chat / Ticket loop 召回。
- Graphiti failure 显示 blocker，不导致 durable Asset 丢失。
- recall eval 覆盖 active / stale / conflict / wrong-ticket scope。

## 11. Track G: Release Hygiene and Operability

目标：把当前大量原型/验证变更收敛成可维护工程状态。

必须完成：

- 区分 source files、generated artifacts、local provider projections、test outputs。
- `.aiteamos/artifacts` 不应无限污染普通代码 review。
- 建立 plan_v8 artifact summary。
- 建立可重复 local production-readiness command。
- 建立最小 frontend + backend + Agent Server verification set。
- 清理或记录 dirty worktree 中的长期变更边界。
- 重要 provider config / setup blocker 在 UI 和 CLI 一致。

验收：

- 新人能从 README / plan_v8 / scripts 跑起系统并理解当前状态。
- 一次 release review 能清楚看到 source diff、artifact evidence、known blockers。
- CI / local verification 不依赖隐藏 stale process。

## 12. 执行顺序

默认优先级：

1. Chat 可用性和 Reply Contract。
2. Backend/runtime boundary cleanup。
3. Fresh Agent Server + live-provider repeated Ticket-loop soak。
4. Workbench UI and domain pages 同步适配。
5. Employee growth and team operation。
6. Durable Assets and recall quality。
7. Release hygiene and operability。

执行中允许交叉推进，但不能只做 backend/runtime 而不修 UI，也不能只做 UI 而绕过 runtime contract。

## 13. 完成定义

v8 完成时必须满足：

- 用户在 Chat 页面提问能稳定看到 assistant reply 或明确 blocker。
- Chat / Tickets / Assets / Employees / Runtime Replay / System Status 都能呈现对应 runtime facts。
- LangGraph Agent Server 是默认 core loop runtime。
- DeepSeek 只通过 LangGraph / LangChain model-provider boundary 使用。
- `direct_llm` 不存在于默认 runtime implementation 和 evidence 中。
- Core loop live dogfood 可重复运行，且 fresh Agent Server / live-provider soak 通过。
- Ticket loop 能处理 retry、approval、handoff、blocker、validation、closeout、Asset proposal。
- Assets lifecycle 完整且 Graphiti 只作为 projection / recall。
- Employees 有 work history、load、risk、memory scope、quality feedback 和 improvement path。
- Provider blockers 同时出现在 backend evidence 和 UI。
- Release / artifact / generated data hygiene 足以支持长期维护。

## 14. 禁止事项

- 不在 Chat route 里继续扩写 generic agent loop。
- 不新增 AITeamOS-owned direct DeepSeek/OpenAI call path。
- 不用 Codex CLI / repo-write adapter dogfood 替代 LangGraph core-loop proof。
- 不让 Graphiti 或 LangGraph 成为 AITeamOS durable source of truth。
- 不把 backend artifact pass 当作用户体验完成。
- 不让 UI 自己推断或伪造 runtime state。
- 不把 `plan_v8.md` 变成滚动实施日志。

## 15. Loop 执行 Prompt

```text
You are working in /home/shiqiangli/projects/AITeamOS.

Read plan_v8.md first. Treat it as the stable baseline. Read plan_v5.md, plan_v6.md, and plan_v7.md only as inherited architecture/history/evidence context. Do not append implementation logs to plan_v8.md unless the user explicitly asks to amend the plan.

Core principle:
AITeamOS is a Ticket / Employees / Assets / Governance operating system. LangGraph owns the autonomous agent runtime. LangChain owns model-provider wiring. DeepSeek is only the temporary LLM provider behind LangGraph / LangChain. Graphiti is approved Asset projection / recall, not source of truth. External coding agents are optional RuntimeExecutor adapters, not the default loop.

Primary v8 execution rule:
Backend/runtime and UI must advance together. A backend/runtime change is not complete unless the user-visible UI state is correct or the plan explicitly marks the UI slice as the next immediate blocker.

Start each run by:
1. Inspecting git status and preserving unrelated user changes.
2. Checking latest plan_v8 artifacts / plan_v7 production evidence if relevant.
3. Choosing the highest-priority unfinished v8 track, starting with Chat visible reply correctness if still broken.
4. Implementing a focused slice without adding custom generic agent loop, direct LLM path, custom memory DB, or frontend pseudo-runtime.
5. Verifying backend tests, frontend tests/build or E2E when UI changed, LangGraph / Agent Server smoke when runtime changed, direct-LLM residue scan when provider/runtime changed, and artifact summary when production readiness changed.
6. Writing implementation evidence to plan_v8_progress.md or .aiteamos/artifacts/plan_v8, not to plan_v8.md.

Default next priority:
Fix Chat visible response correctness and runtime contract mapping so a normal user question produces a visible assistant reply in the main Chat thread, with blocker/approval/handoff/provider states rendered clearly when applicable.
```
