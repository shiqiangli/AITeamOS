# AITeamOS 下一阶段提升计划

状态：执行路线图  
日期：2026-06-07  
目标：完成本计划后，AITeamOS 可以作为自身优化的运行系统使用，即用 AITeamOS 管理、执行、验证和复盘 AITeamOS 的后续改进，并且在自举过程中越用越聪明。

## 0. 总目标

本计划完成后，AITeamOS 应该能够流畅支撑下面的闭环：

```text
Human goal
  -> Clara 创建或选择 Ticket
  -> Ticket 带 assignee / validator / context / acceptance criteria
  -> AI Employee 接手、执行、汇报、交接、请求验证
  -> PV 或其他 Employee 验证结果并写入 evidence
  -> Clara 基于结构化事实总结结果和下一步
  -> Memory / Decision / Skill / Doc candidates 进入 Review Queue
  -> 审核通过的资产进入可复用团队知识
  -> 后续类似 Ticket 自动召回相关资产
  -> 系统能分析每个 AI Employee 的行为、贡献、质量和绩效
  -> 每一轮自举都减少重复错误、提升上下文质量和团队执行效率
```

这个计划不追求一次性把每个细节做到完美。它追求三件事：

1. 中长期产品和架构方向稳定，不再频繁大改。
2. 核心运行闭环真正可用，可以开始自举。
3. 自举过程本身会积累 Memory、Decision、Skill、Doc 和 Employee analytics，让下一轮 AITeamOS 优化更准确、更快、更少重复踩坑。
4. 已选开源库和技术栈尽量深化使用，除非有不得不换的证据，否则不再替换。

## 1. 方向锁定

### 1.1 产品定位

AITeamOS 不是：

- 通用 Agent Framework。
- 通用 AI 聊天客户端。
- Plane 克隆。
- Memory 数据库 UI。
- Agent IDE。
- 单纯的 Employee CRUD 管理后台。

AITeamOS 是：

> 以 Ticket 流转为核心的 AI Workforce Operating System。

它的独特价值是：

- **Ticket 问责链**：谁创建、谁执行、谁验证、谁阻塞、谁交接、产出了什么。
- **Employee 工作账本**：每个 AI Employee 的当前工作、历史工作、报告、验证、阻塞、交接和贡献。
- **资产溯源**：Memory、Decision、Skill、Doc、Report、Evidence 都知道来自哪个 Ticket、哪个 run、哪个 Employee。
- **治理式学习**：经验不是自动污染长期记忆，而是先进入 candidate，再经 Review Queue 审核。
- **绩效分析**：系统可以基于事实分析 AI Employee 的质量、效率、失败模式、工具熟练度和复用贡献。
- **自举式进化**：AITeamOS 优化 AITeamOS 的每一轮都要产生可审计经验，并在后续类似 Ticket 中被召回、验证和改进。
- **Clara-led 人机协作**：人类通过 Clara 发起目标、确认风险、审查资产、理解结果。

### 1.2 对 agent-first 的准确定义

以后在 AITeamOS 中使用 `agent-first` 时，只表达这个意思：

- Chat / Clara 是主要操作入口。
- 能由 AI Employee 完成的操作，优先通过委派、执行、汇报、验证完成，而不是表单式 CRUD。
- AI Employee 的工作必须落到 Ticket、Report、Evidence、Validation、Asset 这些可追踪事实上。

不要把 `agent-first` 理解为：

- AITeamOS 要自研通用多 Agent 框架。
- Chat transcript 比 Ticket ledger 更重要。
- Memory / Prompt / Tool calling 本身就是产品核心。

更准确的长期表述应该是：

```text
Ticket-flow-first
Clara-led
Employee-accountable
Asset-provenance-driven
Self-bootstrap-learning
```

### 1.3 自举越用越聪明的定义

AITeamOS 的“越用越聪明”不是依赖某个外部模型或 Agent 平台记住上下文，而是由 AITeamOS 自己沉淀、审核、召回和验证经验。

它至少包括四层：

1. **经验沉淀**：每个自举 Ticket 完成、失败、阻塞或验证后，都能提取 Memory / Decision / Skill / Doc candidates。
2. **治理筛选**：candidate 必须带 provenance，并经过 Review Queue 审核或明确拒绝。
3. **精准召回**：后续类似 Ticket 会自动注入相关 approved assets，并记录召回原因。
4. **效果验证**：系统能比较召回前后的执行质量，例如重复问题是否减少、验证失败率是否下降、完成时间是否缩短、证据质量是否提升。

因此，自举学习闭环必须可追踪：

```text
Self-bootstrap Ticket
  -> report / evidence / validation / blocker
  -> Memory or Decision candidate
  -> Review Queue approval
  -> approved asset recall in later Ticket
  -> measurable improvement or regression signal
  -> Clara summary of what AITeamOS learned
```

## 2. 技术选型冻结原则

### 2.1 已选库和技术栈

这些选择默认保持稳定，后续优先深化而不是替换。

前端：

- React 19
- Vite 6
- TypeScript
- Tailwind CSS
- Radix UI
- lucide-react
- assistant-ui
- AG-UI client / React AG-UI bridge

后端：

- FastAPI
- Pydantic
- httpx
- PyYAML
- Plane 作为目标 Ticket Backend
- Graphiti / Neo4j 作为目标 Memory / Asset Graph Backend
- 本地 `.aiteamos` 只承载配置、trace 和 audit mirror，不作为 Ticket Backend

Chat / Agent runtime：

- LangGraph 作为当前 AG-UI bridge 和 checkpoint 路径。
- assistant-ui + AG-UI 作为 Chat UI 和事件协议路径。
- 暂不引入 CrewAI、AutoGen 或其他多 Agent 框架，除非 LangGraph 在明确场景下无法支撑。

Memory / Asset Graph：

- Graphiti / Neo4j 是持久资产 temporal knowledge graph 投影后端。
- Graphiti 承载 approved / validated durable assets 的语义关系、时间关系和 provenance，包括 approved Memories、accepted Decisions、Docs、Skills、Capabilities、Tooling facts、validated Ticket summaries 和 durable Employee facts。
- Graphiti 不接管 Ticket event ledger、trace ledger、approval state、permissions、secrets 或 raw execution logs。
- AITeamOS 仍拥有 Review Queue / approval state，但不为此保留 local-file Ticket mode。

Ticket Backend：

- Plane 是目标 Ticket Backend，也是自举和后续测试的默认底座。
- AITeamOS 内部只使用 Ticket 概念；Plane provider-native names 只留在 adapter metadata / external link。
- 不维护旧文件型 Ticket Backend 作为并行路线。
- 其他 Ticket providers 不进入近期路线；如果未来新增，必须映射到同一套 AITeamOS Ticket contract。

Tooling：

- MCP 是外部工具连接协议方向。
- Kernel Commands 是 AITeamOS 自有能力边界。
- AI Engines 是统一产品概念，覆盖 LLM API、本地模型、agent platform handoff。

### 2.2 换库条件

不因为偏好、新鲜感、局部便利而换库。

只有同时满足以下条件，才允许替换已选库：

1. 关键产品能力被阻塞，而不是只是实现麻烦。
2. 已做 focused spike，证明当前库不能安全支持该能力。
3. 替换不会推翻 Ticket / Employee / Asset 领域模型。
4. 有 ADR 或计划说明迁移成本、风险和回滚路径。
5. 新旧路径可以短期共存，或改动爆炸半径很小。

### 2.3 分层边界

AITeamOS 自建并长期拥有：

- Ticket lifecycle
- Employee work ledger
- Ticket Asset Graph
- Review Queue
- Governance / permissions
- Asset provenance
- Employee analytics
- Clara-led operating loop

开源库可以承载：

- Chat UI primitives
- graph/checkpoint runtime
- LLM API client mechanics
- tool protocol adapters
- persistent asset graph internals

领域事实不能被藏进某个 runtime 或 vendor black box。无论调用哪个模型或 Agent 平台，AITeamOS 都必须能解释：谁做了什么、为什么做、证据是什么、结果被谁验证、产出了哪些资产。

## 3. 当前基线和主要缺口

### 3.1 当前已有基线

- Chat 可以选择 Clara 或某个 Employee。
- conversation、trace、run metadata、engine thread state 已有本地持久化。
- 旧文件型 Ticket backend 已有 append-only event ledger，但这是需要替换的旧实现路径，不再作为目标底座。
- Ticket reports 和 evidence 已能投射到资产概念。
- Employee 页面已经接近 work ledger 视角。
- Assets 页面统一了 Knowledge、Capabilities、Review Queue。
- Settings 对齐 AI Engines、Tool Connectors、Code Repositories、Ticket Backend、Memory / Asset Graph Backend。
- System Status 是只读状态入口，并展示 secrets health。
- Memory candidate 和 approved memory 已有本地路径。
- Graphiti 后端已经在当前实现中以 Memory Backend 名义出现，后续需要升级为 Memory / Asset Graph Backend，并尽早进入真实运行底座。
- 已经具备开始记录自举经验的基础事实：conversation、trace、Ticket event、report、memory candidate。

### 3.2 当前主要缺口

- Chat 还没有稳定成为 Ticket 工作流的执行入口。
- Plane 还没有成为可执行的 Ticket Backend。
- Graphiti 还没有成为可执行的持久资产召回底座。
- Remote AI Engine、Kernel command planning、本地 command execution 之间的契约还不够清晰。
- Ticket Asset Graph 目前多是隐式事实，还没有明确 graph read model。
- Memory candidate 生成还偏 chat-turn，不够 Ticket-completion-aware。
- Review Queue 还没有覆盖 Memory / Decision / Skill / Doc / Tool candidate 的完整治理。
- Employee analytics 还只是贡献计数雏形，不足以支持绩效分析。
- 自举学习还没有形成闭环：早期 AITeamOS improvement Ticket 产生的经验，尚不能稳定影响后续类似 Ticket。
- 缺少学习效果指标：还不能回答“这次自举后，下一次是否更快、更准、更少失败”。
- Validation flow 已有 report/event 概念，但 RD -> PV -> Clara 的工作流还不够一等公民。
- AI Engine 选择和 configuration blocker 需要更稳定，避免用户看到“选了模型却像 stub”的体验。

## 4. 阶段路线

### 4.0 三层杀手路径

下面的 Phase 是完整路线，但执行时必须按三层推进。第一层没有跑通前，不进入大规模可视化、完整 analytics 或复杂治理。

第一层：最小自举闭环。

- 覆盖范围：Phase 0 + Phase 0.5 + Phase 1 + Phase 3a。
- 目标：在 Plane + Graphiti 真实底座上尽快上线到“粗糙但能学”的状态。
- 预计周期：3-4 周聚焦开发。
- 交付物：
  - Chat AI Engine 选择稳定。
  - Plane 成为可执行 Ticket Backend。
  - Graphiti 成为可执行 persistent asset recall backend。
  - Clara 能创建 Plane-backed Ticket 并委派。
  - Employee 能执行并汇报。
  - Ticket 完成后能提取 Memory candidate。
  - 审批后的 Memory / durable asset 能经 Graphiti 在下一个类似 Ticket 中被 recall。
  - Clara 能总结“本轮 AITeamOS 学到了什么”。
- 判断标准：系统开始在真实底座上越用越聪明，即使 UI 和 analytics 还很朴素。

第二层：可解释性。

- 覆盖范围：Phase 2 + Phase 4a。
- 目标：解释为什么学到了、谁贡献了、哪些资产被复用。
- 预计周期：2-3 周。
- 交付物：
  - Ticket Asset Graph read model。
  - grouped edge list，而不是 canvas graph。
  - Employee 基础贡献指标。
  - Asset provenance detail。
- 判断标准：从 Ticket / Employee / Asset 任一入口都能追踪来源和贡献。

第三层：治理强化和外部扩展。

- 覆盖范围：Phase 5 + Phase 6 + Phase 7 + Phase 3b + Phase 4b。
- 目标：让系统在自举中持续加强验证、治理、外部协作和长期资产图。
- 预计周期：4-6 周，可由 AITeamOS 自己拆 Ticket 执行。
- 交付物：
  - validation harness / evidence discipline。
  - 完整 self-bootstrap batch learning summary。
  - 更完整的 Graphiti persistent asset projection。
  - 更深入的 Plane sync / provenance。
  - agent-platform handoff。
- 判断标准：外部集成增加能力，但不改变 Ticket / Employee / Asset 核心模型。

### Phase 0：稳定 1.0 基线

目标：

让当前系统可靠到可以承载后续自举 Ticket。

任务：

1. 固化 Chat 默认策略：
   - remote AI Engine selected：先把 profile / skill / memory / knowledge / capability / ticket context 打包给远程模型。
   - 没有可用 remote AI Engine：返回 configuration blocker，不生成伪装成真实回答的本地 stub 内容。
   - Kernel command 只执行通过 policy 的明确 action plan，不再用本地 heuristic 抢答自然对话。
2. 修复当前测试契约：
   - command intercept 与 remote-first 策略的冲突。
   - trace metadata 中 Memory / Knowledge count 命名不稳定的问题。
3. 明确 reply provenance：
   - remote engine reply
   - kernel command reply
   - configuration blocker
4. OpenAI / DeepSeek 配置错误不再转成 stub 内容，而是明确返回 blocker。
5. 如果需要，轻量拆分 `chat_routes.py`，但只做无行为变化的模块化：
   - AI Engine clients
   - context bundle assembly
   - Kernel command planning / execution
   - persistence helpers
   - 采用 extract-and-delegate：先提取纯函数或小 service，再由原入口调用；不要一次性大拆文件和改行为。
   - 每次拆分只允许一个边界移动，并配 focused test / smoke 覆盖。
6. 增加或整理 Phase 0 smoke。Phase 0 只验证基础稳定性，不验证跨阶段学习闭环：
   - Clara 中文身份/能力回答。
   - Remote AI Engine answer-only。
   - Remote AI Engine action-plan blocker。
   - AI Engine configuration blocker。
7. 将 PV validation smoke 下沉到 Phase 1。
8. 将 Ticket creation、Memory candidate / recall / self-bootstrap learning smoke 下沉到 Phase 0.5 / Phase 1 / Phase 3a。

验收：

- `pytest` 通过。
- `cd apps/dashboard && npm test` 通过。
- `cd apps/dashboard && npm run build` 通过。
- Chat UI 中选 DeepSeek 时，Clara 能自然中文回答。
- OpenAI quota / missing key 等错误表现为配置 blocker。
- 用户能看出每次回复来自 remote engine、Kernel command 或 blocker。

不做：

- 新图形 UI。
- 替换 LangGraph 或引入其他 Agent framework。

### Phase 0.5：Plane + Graphiti Base 上线

目标：

让 AITeamOS 从一开始就在真实底座上运行，不再为 local-file Ticket Backend 继续投入。

原则：

1. AITeamOS 内部只叫 Ticket。
2. Plane provider-native names 只保留在 adapter metadata / external link。
3. Graphiti 是持久资产知识图投影，不写入 raw trace / raw tool log / secrets / permission authority。
4. 如果 Plane 或 Graphiti 未配置，系统返回 setup blocker，而不是切回 local-file mode。

前三天 focused spike：

Phase 0.5 开始后先做一个不超过 3 天的可行性 spike。spike 不追求完整 UI，只验证真实底座是否能承载后续第一层开发。

必须验证：

1. Plane：
   - create 一个 AITeamOS Ticket。
   - read 回 provider ref 和 current state。
   - append 一条 report/comment。
   - transition 一次 state。
   - external deep link 可打开。
2. Graphiti：
   - ingest 一条 approved Memory。
   - search 能召回。
   - recall result 能带回 AITeamOS provenance。
   - episode / structured fact 能承载核心 provenance 字段。
3. Chat / Trace：
   - Chat action 能绑定 Plane-backed Ticket。
   - trace 能记录 Plane provider ref 和 Graphiti episode ref。

如果 spike 阻塞，不进入 Phase 1。处理方式是修正 Plane / Graphiti adapter、配置、schema 或权限模型；不新增 local-file Ticket mode。

Plane 映射表：

Phase 0.5 必须先冻结最小映射，后续 UI 和 ChatActionPlan 都依赖这张表。

```text
AITeamOS Ticket       -> Plane provider record
AITeamOS namespace    -> Plane project 或 label，Phase 0.5 必须二选一并写入 adapter config
AITeamOS Employee     -> Plane user / member mapping；无法映射时保留 AITeamOS employee_id 并写入 comment metadata
AITeamOS assignee     -> Plane assignee 或 AITeamOS event projection assignee
AITeamOS report       -> Plane comment with AITeamOS metadata
AITeamOS validation   -> Plane comment + AITeamOS validation event projection
AITeamOS state        -> Plane state mapping table
AITeamOS evidence     -> Plane attachment 或 tagged comment link
AITeamOS asset link   -> AITeamOS asset graph edge + optional Plane comment backlink
```

映射原则：

1. AITeamOS 内部字段名仍然叫 Ticket / Employee / Report / Evidence。
2. Plane 原生名称只出现在 `provider_ref`、adapter config、external link 和 debug metadata 中。
3. 如果某个字段不能可靠写入 Plane，先保留为 AITeamOS event projection，并在 provider capability status 中标出限制。

Plane 任务：

1. 实现 Plane-backed `TicketAdapter`：
   - list Tickets
   - create Ticket
   - read Ticket detail
   - append report / comment
   - transition state
   - external deep link
2. 增加 normalized `ProviderTicketRef`：
   - `provider="plane"`
   - `provider_record_id`
   - `provider_project_id`
   - `provider_url`
   - `synced_at`
3. AITeamOS API / UI / Chat 只暴露 Ticket，不暴露 Plane provider-native object 名称。
4. Ticket events、reports、validation、asset links 使用 AITeamOS event schema 投影。

Graphiti 任务：

1. Graphiti / Neo4j settings 和 System Status 必须可用。
2. approved Memory smoke：
   - approve 一条 Memory
   - ingest 到 Graphiti
   - search 回来
   - 结果回链到 AITeamOS asset / Ticket / run
3. durable asset summary smoke：
   - ingest 一条 validated Ticket summary
   - search 回来
   - 在 Chat inspector / trace 中看到 Graphiti recall provenance
4. Graphiti ingestion failure 返回 setup / ingestion blocker，不把数据悄悄留在只本地可见的临时路径。
5. Graphiti episode / structured fact schema 必须在 Phase 0.5 定义最小版本：
   - `asset_id`
   - `asset_type`
   - `asset_status`
   - `source_ticket_id`
   - `source_employee_id`
   - `source_run_id`
   - `source_report_id`
   - `evidence_id`
   - `scope`
   - `version` 或 content hash
   - `provider_refs`
   - `source_ref`
6. Phase 0.5 smoke 要证明这些字段至少能被写入、搜索结果能回链，不等到 Phase 3b 才发现 schema 不够。

验收：

- Clara 能创建 Plane-backed Ticket。
- Employee report 能追加到 Plane-backed Ticket，并在 AITeamOS Ticket event projection 中出现。
- Graphiti 能 ingest approved Memory，并在后续类似问题中 recall。
- Graphiti recall 结果带 AITeamOS provenance。
- Plane 映射表已写入 adapter config 或文档，并被 focused tests 使用。
- Graphiti 最小 episode schema 已被 smoke 覆盖。
- 未配置 Plane / Graphiti 时，UI 和 API 返回清晰 setup blocker。
- 没有新的 local-file Ticket Backend 功能被加入。

### Phase 1：Clara-led Ticket Operating Loop

目标：

让 Chat 成为真正的 Ticket 操作入口，而不是只会聊天。

目标工作流：

```text
用户给 Clara 一个目标
  -> Clara 创建或选择 Plane-backed AITeamOS Ticket
  -> Ticket 带 owner / validator / acceptance criteria / linked docs / repos
  -> Clara 委派给 Employee
  -> Employee 汇报 progress / result / blocker
  -> PV 验证 pass / fail / blocked
  -> Clara 汇总并关闭、重开或继续委派
```

后端任务：

1. 定义 `ChatActionPlan`，第一批只实现 4 种最小动作：
   - `answer_only`
   - `create_ticket`
   - `append_report`
   - `request_validation`
2. 第一批暂不单独实现以下动作，闭环稳定后再加入：
   - `assign_ticket`
   - `record_validation`
   - `link_asset`
   - `request_approval`
3. 第一批 validation 可以通过 `append_report(report_type=validation)` 承载，等 RD -> PV -> Clara 跑通后再拆出独立 `record_validation`。
4. 让远程 AI Engine 可以输出自然回答或结构化 action plan。
5. Kernel 只执行通过 policy 的 action plan。
6. 工作类 action 必须绑定 Ticket，简单问答除外。
7. 扩展 Ticket event：
   - `created`
   - `assigned`
   - `handoff_requested`
   - `handoff_accepted`
   - `status_changed`
   - `reported`
   - `validation_requested`
   - `validation_started`
   - `validated`
   - `validation_failed`
   - `blocked`
   - `asset_linked`
   - `summary_posted`
8. 每次 Ticket 完成、阻塞、验证失败时，Clara 写入 summary record。
9. 统一 run-to-ticket 链接：
   - Plane provider ref
   - source thread
   - source run
   - engine thread
   - selected AI Engine
   - tool / command calls
   - saved trace path
10. 在 Clara summary 中记录可学习内容：
   - 本 Ticket 有什么可复用经验。
   - 是否需要 Memory / Decision / Skill / Doc candidate。
   - 后续类似 Ticket 应该注意什么。

前端任务：

1. Chat 顶部展示 active Employee、active Ticket、selected AI Engine、run status。
2. Chat run inspector 展示：
   - loaded context
   - recalled memories
   - action plan
   - command execution
   - policy decision
   - Ticket events written
   - saved paths
3. Ticket detail 展示：
   - owner
   - validator
   - acceptance criteria
   - current stage
   - next action
   - learnings / candidate assets
   - timeline
4. 增加清晰动作入口：
   - Ask Clara
   - Assign Employee
   - Request Validation
   - Add Report
   - Mark Blocked

验收：

- 用户能通过 Clara 创建 Ticket 并委派给 Employee。
- Employee report 会追加到 Plane-backed Ticket，并投影为 AITeamOS Ticket event，出现在 Employee Work Ledger。
- PV validation 会更新 Ticket 状态，并生成 validation evidence。
- Clara summary 基于结构化事实，而不是只基于聊天文本。
- Clara summary 能指出本次 Ticket 是否产生了可复用经验。
- 测试覆盖 Plane-backed `created -> assigned -> reported -> validation_requested -> validated`。

### Phase 2：Ticket Asset Graph MVP

目标：

让 provenance 显式、可查询、可解释，但暂不引入新的图数据库。

后端任务：

1. 增加 graph read model：
   - `TicketGraphNode`
   - `TicketGraphEdge`
   - `TicketGraphProjection`
2. 从现有本地事实投射 graph：
   - Ticket events
   - reports
   - evidence
   - trace events
   - Memory candidates
   - Decisions
   - Docs
   - Skills
   - Capabilities
   - repositories
   - AI Engine runs
3. 首批 edge types：
   - `ticket.assigned_to.employee`
   - `ticket.validated_by.employee`
   - `employee.produced.report`
   - `report.belongs_to.ticket`
   - `report.has_evidence`
   - `run.uses_ai_engine`
   - `run.calls_capability`
   - `run.recalls_memory`
   - `run.reads_doc`
   - `run.proposes_memory_candidate`
   - `run.proposes_decision_candidate`
   - `memory.derived_from.ticket`
   - `decision.derived_from.ticket`
   - `asset.assigned_to.employee`
   - `ticket.references_repository`
4. 增加 API：
   - `GET /api/v1/tickets/{ticket_id}/graph`
   - `GET /api/v1/tickets/{ticket_id}/assets`
   - `GET /api/v1/employees/{employee_id}/graph`
   - `GET /api/v1/assets/{asset_id}/graph`
   - `GET /api/v1/asset-graph/status`
5. graph projection 必须可由本地事实重建，不能成为不可解释的第二套事实源。

前端任务：

1. Ticket detail 增加 Graph / Provenance 区域。
2. Employee Work Ledger 展示 graph-derived contribution groups。
3. Asset detail 展示 source Ticket、source Employee、source run、downstream usage。
4. P1 UI 使用 grouped edge list，不急着做复杂 canvas graph。

验收：

- 从 Ticket 可以回答：
  - 哪些 Employees 参与过？
  - 每个 Employee 贡献了什么？
  - 最终结论有哪些 evidence？
  - 产生了哪些 Memory / Decision candidates？
- 从 Employee 可以回答：
  - owned / validated / reported / blocked 了哪些 Tickets？
  - 产出了哪些 assets？
- 测试覆盖 RD -> PV Ticket flow 的 graph projection。

### Phase 3：Governed Persistent Asset Learning Loop

目标：

让系统能从完成的 Ticket 中学习，同时避免长期资产图被自动污染。对于 AITeamOS 自举来说，这一阶段的核心目标是：每一轮自举都能把有价值经验沉淀成可审核资产，并让后续类似改进实际受益。

执行拆分：

- **Phase 3a：candidate -> approval -> Graphiti recall。** 这是第一层最小自举闭环的一部分，必须在 Graphiti 可用的底座上完成。第一批可以从 Memory candidate 开始，但 schema 要能扩展到 Decision / Skill / Doc / Tool candidates。
- **Phase 3b：broader durable assets -> Graphiti projection。** 等 3a 有真实验证数据后再做，把 Docs、Skills、Capabilities、validated Ticket summaries 等更多持久资产纳入 Graphiti。

后端任务：

Phase 3a：

1. candidate extraction 从 generic chat-turn 转为 Ticket-aware。
2. 触发点：
   - Ticket completed
   - validation passed
   - validation failed
   - blocker resolved
   - Clara summary posted
3. candidate 类型：
   - Memory candidate
   - Decision candidate
   - Skill candidate
   - Doc update candidate
   - Tool / capability change request
4. 每个 candidate 必须包含：
   - source Ticket
   - source Employee
   - source run / trace
   - source report / evidence
   - confidence
   - proposed scope
   - why it should be remembered
5. Approval 保持 AITeamOS 显式治理；Graphiti 只接收 approved / validated durable assets。
6. recall 需要记录：
   - query
   - employee
   - ticket
   - scopes
   - source trace
   - confidence / reason
7. recalled memory ids / Graphiti result refs 写入 run metadata 和 Ticket Asset Graph。
8. 为自举 Ticket 增加 learning summary：
   - learned facts
   - avoided pitfalls
   - reusable decisions
   - suggested skill/doc updates
   - future recall query hints
9. 增加 learning effectiveness 记录：
   - asset 是否被后续 Ticket recall
   - recall 后是否减少 blocker / validation failure
   - recall 后是否缩短 completion time
   - recall 是否被 Clara / PV 标记为 useful
10. 支持 asset supersedes / conflicts 关系，避免旧经验长期误导自举。

Phase 3b：

1. Graphiti 配置可用时，把 approved / validated durable assets 分批投影到 Graphiti：
   - approved Memories
   - accepted Decisions
   - Docs 或 Doc summaries
   - Skills 和 Skill summaries
   - Kernel Commands / MCP Tools / Tooling capability facts
   - validated Ticket summaries
   - validated Report / Evidence summaries
   - durable Employee profile facts
2. 每个 Graphiti episode / structured fact 必须携带 provenance：
   - `asset_id`
   - `asset_type`
   - `asset_status`
   - `version` 或 content hash
   - `source_ticket_id`
   - `source_employee_id`
   - `source_run_id` 或 trace ref
   - `source_report_id` / `evidence_id`，如适用
   - `scope`
   - `source_ref`
3. 记录 Graphiti episode / ingestion status，并保存在 AITeamOS ingestion audit record。
4. Graphiti recall 结果必须回写到 run metadata，并能和本地 approved / validated asset 对齐。
5. Graphiti 不接管 candidate approval，不写入每个 Ticket event，不写入 raw trace、terminal output、tool-call raw log、secrets 或 permission authority。

前端任务：

1. Review Queue 支持 Memory / Decision / Skill / Doc / Tool candidates。
2. Candidate detail 展示 provenance 和 proposed scope。
3. Approval 操作支持：
   - approve
   - reject
   - edit then approve
   - assign to Employee / scope
4. Chat inspector 展示本轮注入了哪些 approved memories，以及为什么注入。
5. Asset detail 展示 usage history 和 freshness。
6. 自举 Ticket detail 展示：
   - 本 Ticket 产生了哪些 candidates
   - 哪些 approved assets 被召回
   - 召回资产是否被验证为有用
   - 本轮 AITeamOS 学到了什么

验收：

- 完成一个有复用价值的 Ticket 后，会生成 candidate。
- 审核通过 candidate 后，它能在类似 Ticket 中被 recall。
- recall 会写入 trace 和 graph。
- 用户能解释为什么某条 Memory 被使用。
- 后续类似自举 Ticket 能显示它使用了前序 Ticket 沉淀的 approved asset。
- Clara 能总结“本轮 AITeamOS 学到了什么，以及下一轮如何利用”。
- 至少一个 stale / superseded asset 可以被标记为不再适用。
- Phase 3a 验收必须依赖 Graphiti：approved asset 能被 Graphiti recall，并回链到 AITeamOS asset / Ticket / run。
- Phase 3b 验收时 Graphiti 能覆盖多类 durable assets；AITeamOS 仍拥有 approval state、Ticket event projection 和治理决策。

### Phase 4：Employee Behavior / Performance Analytics

目标：

让 AITeamOS 能分析每个 AI Employee 的行为和绩效，而不仅仅展示 profile。

执行拆分：

- **Phase 4a：基础贡献指标。** 只做 5 个核心指标，验证 analytics 数据通路。
- **Phase 4b：行为质量和学习效果指标。** 等自举数据积累后再扩展。

Phase 4a 核心指标：

- assigned Ticket count
- completed Ticket count
- validation pass rate
- candidates produced
- recalled asset count

Phase 4b 扩展指标：

- validation failure rate
- blocked rate
- rework count
- average time to first report
- average time to completion
- evidence count
- evidence quality flags
- Memory / Decision / Skill candidates produced
- approved candidate rate
- recalled asset usefulness
- prior learning reuse rate
- repeated issue reduction
- repeated validation failure reduction
- stale asset usage count
- self-bootstrap improvement delta
- tool call success/failure rate
- AI Engine cost / latency
- handoff count
- handoff success rate

后端任务：

1. 增加 Employee analytics read model。Phase 4a 只覆盖 5 个核心指标。
2. analytics 必须来自 Ticket graph、events、reports、trace，不手工编辑。
3. 增加 API：
   - `GET /api/v1/employees/{employee_id}/analytics`
   - `GET /api/v1/employees/analytics/summary`
   - `GET /api/v1/tickets/{ticket_id}/performance`
4. Phase 4b 再增加质量信号：
   - missing evidence
   - repeated blocker
   - validation rejected
   - stale memory used
   - high-cost run
   - command/tool failure
5. Phase 4b 再增加自举学习信号：
   - 上一批 Ticket 产出的 approved assets 是否被本批 recall
   - recall 的资产是否减少了重复问题
   - 同类 Ticket 的平均完成时间是否下降
   - 同类 Ticket 的验证失败率是否下降
   - 哪些 Memory / Decision / Skill 帮助最大
6. 早期不要做单一黑盒分数。先做可解释指标和 flags。

前端任务：

1. Employee detail 增加 Analytics 区域。
2. Ticket detail 展示 contribution 和 quality signals。
3. 自举批次页面或区域展示 learning delta：
   - 本批复用了哪些前序经验
   - 本批新增了哪些经验
   - 哪些重复问题被减少或仍然存在
4. Clara 可以回答一段时间内某个 Employee 的表现。
5. Clara 可以回答“AITeamOS 最近几轮自举学到了什么”。
6. System Status 展示整体 operating health。

验收：

- 用户能基于具体事实比较不同 Employees。
- 每个指标都能追溯到 Ticket / event / report / evidence。
- Clara 能回答“Alex 本周表现如何？”并给出证据。
- Clara 能回答“AITeamOS 最近几轮自举是否更聪明了？”并给出可追踪证据。
- 低质量、阻塞、失败验证会产生可见信号。

### Phase 5：Validation / Harness / Evidence Discipline

目标：

让验证足够强，避免系统自举时自我感觉良好但事实不足。

后端任务：

1. formalize validation Skills：
   - validation-strategy
   - evidence-review
   - regression-check
   - product-model-review
2. 增加 validation action plans：
   - request_validation
   - record_validation
   - record_failure
   - request_human_review
3. 按 Ticket 类型定义 evidence requirement：
   - docs change
   - frontend change
   - backend change
   - integration change
   - model/prompt change
4. 可选 local command evidence：
   - `pytest`
   - `npm test`
   - `npm run build`
   - focused smoke command
5. terminal execution 保持 allowlist，并且必须 Ticket-bound。

前端任务：

1. Ticket validation stage 可见。
2. Evidence requirement 作为事实 checklist 展示。
3. Validation failure 自动形成 blocker 或 rework next action。

验收：

- code-change Ticket 没有 evidence 时不能标记为 validated。
- failed validation 会产生清晰 rework path。
- evidence 出现在 Ticket graph 和 Assets 中。

### Phase 6：AITeamOS Self-Bootstrap Mode

目标：

开始用 AITeamOS 自己管理 AITeamOS 的优化工作，并让每一批自举都反过来提升 AITeamOS 的上下文质量、执行质量、验证质量和团队资产质量。

执行说明：

- 第一层只要求跑通最小自举闭环：一个改进 Ticket 能创建、汇报、完成、产生 Memory candidate，并在后续类似 Ticket 中 recall。
- Phase 6 的完整 batch mode 属于第三层。角色分工、批次 summary、系统性 analytics review 可以在第一层上线后，用 AITeamOS 自己逐步实现。

建议角色：

- Clara：AI Team OS Manager。
- RD Employee：实现和修复。
- PV Employee：验证和测试。
- Architect Employee：架构边界和技术决策。
- Memory Curator Employee：Memory / Decision / Skill candidate 审核和 scope 卫生。
- Trace/Product Employee：用户流程、trace 质量和产品一致性。

自举流程：

1. Human 给 Clara 一个改进目标。
2. Clara 创建 Plane-backed Ticket。
3. Clara 指定 RD 和 PV。
4. RD 执行或汇报 bounded work。
5. PV 基于 evidence 验证。
6. Clara 汇总 outcome 和 next action。
7. Memory / Decision / Skill / Doc candidates 进入 Review Queue。
8. Human 或授权 Employee 审批关键资产。
9. Approved asset 在后续类似 Ticket 中被 recall。
10. Clara 在后续 Ticket 中说明召回了哪些前序自举经验。
11. PV 验证这些经验是否真的帮助了本次执行。
12. 每批 Ticket 后查看 Employee analytics 和 learning delta。

自举学习批次要求：

1. 每批自举至少选择一个主题，例如 Chat 稳定性、Ticket Graph、Memory recall、Employee analytics。
2. 每批开始前，Clara 必须列出本批会召回的 approved assets。
3. 每批结束后，Clara 必须写 batch learning summary：
   - 本批解决了什么。
   - 复用了哪些旧经验。
   - 新增了哪些候选经验。
   - 哪些旧经验失效、冲突或需要更新。
   - 下一批应该如何更快或更稳。
4. 每批至少有一个 PV validation 检查“经验复用是否有效”。
5. 每批至少审查一次 Employee analytics，寻找重复 blocker、重复 validation failure 或高价值 Employee pattern。

建议 Ticket namespaces：

- `ops-*`：系统运行和流程改进。
- `rd-*`：实现和修复。
- `pv-*`：验证和测试。
- `arch-*`：架构决策和边界检查。
- `mem-*`：Memory / Decision / Skill curation。
- `doc-*`：产品文档和用户指南。

验收：

- 至少 5 个 AITeamOS improvement Tickets 通过自身系统端到端运行。
- 每个 Ticket 都有 assignee、report、validation、evidence、Clara summary。
- 至少 3 个 reusable candidates 被提出。
- 至少 1 条 approved Memory 被后续 Ticket recall。
- 至少 1 条前序自举经验被后续 Ticket 证明有用，并写入 learning delta。
- 至少 1 条无效、过时或冲突的经验被 reject、supersede 或标记为 stale。
- Employee analytics 能展示 work、validation、blocker、asset production 的差异。
- Clara 能生成一份“本批 AITeamOS 学到了什么”的 summary，并能关联到 Ticket / asset / validation evidence。

### Phase 7：Agent Platform Handoff / Advanced External Execution

目标：

在 Plane + Graphiti 底座已经可用后，接入更复杂的外部执行系统，但不改变 AITeamOS 的产品模型。

Plane / Graphiti：

1. Plane 和 Graphiti 不在 Phase 7 才上线；它们已经是 Phase 0.5 / Phase 3a 的基础底座。
2. 本阶段只做加深：
   - richer Plane sync / provenance
   - broader Graphiti durable asset projection
   - cross-asset conflict / supersession checks
   - external deep-link quality
3. 加深过程中仍保持 AITeamOS 内部只使用 Ticket 概念。

Agent-platform AI Engines：

1. Codex、Qoder、Claude Code、Cursor 等都作为 AI Engine handoff backend。
2. handoff contract 必须包含：
   - Ticket id
   - Employee id
   - repository scope
   - allowed actions
   - context bundle
   - expected report schema
   - artifact import path
3. 先做 non-destructive inspect-and-report handoff。
4. repo edits 必须有明确审批和 evidence。

验收：

- 外部集成增加能力，但不替换 Ticket / Employee / Asset 模型。
- 外部系统输出能导入为 Ticket report / evidence。
- handoff trace 展示发送的 context 和收到的 artifacts。

## 5. 横向要求

### 5.1 Persistence

目标状态：

- Plane 承载 Ticket / Docs 外部事实源。
- AITeamOS 承载 Ticket event projection、Review Queue、approval state、trace 和 governance facts。
- Graphiti 承载 approved / validated durable assets 的语义图投影。
- `.aiteamos` 只承载配置、trace、conversation、ingestion audit mirror 等可检查记录，不作为 Ticket Backend。
- config 文件可以由 Settings 重写。
- secret 永不写入 JSON/YAML。
- 尽量让 read model 可由事实重建。

### 5.2 Trace

每个 meaningful action 必须能看到：

- selected Employee
- selected AI Engine
- loaded context
- recalled Memory ids
- action plan
- command/tool calls
- policy decision
- Ticket events written
- assets proposed/linked
- saved paths

### 5.3 Governance

以下高风险动作必须审批或产生 blocked record：

- destructive file or asset deletion
- external connector write
- repository mutation
- Memory approval
- validation failed 时强制关闭 Ticket
- agent-platform handoff with write capability

### 5.4 Docs

只在行为或模型变化时更新文档：

- `PRODUCT_DIRECTION.md`：产品 thesis 或边界变化。
- `PRODUCT_MODEL.md`：实体、关系、核心模型变化。
- `docs/PRD-core.md`：功能需求变化。
- `docs/arch.md`：API、持久化、runtime、服务边界变化。
- `docs/USER_GUIDE.md`：用户可见流程变化。
- `next_plan.md`：路线、阶段和优先级变化。

### 5.5 Verification

每个实现切片都应至少验证：

```bash
pytest
cd apps/dashboard && npm test
cd apps/dashboard && npm run build
```

每个新增事实模型优先加 backend focused tests，再做 UI polish。

## 6. 自举首批 Ticket 建议

Phase 0 稳定后，用这些 Ticket 开始自举。按三层执行，不要一次性展开所有 Ticket。

第一层：最小自举闭环。

1. `ops`：稳定 Chat AI Engine contract 和 trace metadata。
2. `ops`：上线 Plane Ticket Backend settings、secrets health 和 setup blocker。
3. `rd`：实现 Plane-backed `TicketAdapter` 最小切片。
4. `mem`：上线 Graphiti settings、secrets health、ingestion 和 search smoke。
5. `pv`：验证 Plane-backed Ticket create/report/transition。
6. `pv`：验证 Graphiti approved Memory ingest/search/provenance。
7. `rd`：实现第一批 `ChatActionPlan` schema 和 executor path。
8. `rd`：把 Chat action execution 绑定到 Plane-backed Ticket events。
9. `pv`：验证 RD -> PV -> Clara Ticket loop。
10. `mem`：让 candidate extraction 变成 Ticket-completion-aware。
11. `mem`：增加 candidate provenance 和 Review Queue detail。
12. `pv`：验证 approved Memory 经 Graphiti 在类似 Ticket 中 recall。
13. `ops`：让 Clara 汇总第一轮 AITeamOS 学到了什么。

第二层：可解释性。

1. `rd`：实现 Ticket Asset Graph read model。
2. `pv`：测试 graph projection from Ticket reports / evidence。
3. `rd`：增加 Ticket graph API 和 grouped edge list UI。
4. `rd`：增加 Phase 4a Employee analytics 核心 5 指标。
5. `pv`：用 Plane-backed Ticket event fixtures 验证 analytics。

第三层：治理强化和外部扩展。

1. `mem`：增加 self-bootstrap learning summary 和 learning delta 记录。
2. `pv`：验证前序自举经验是否减少了重复 blocker 或 validation failure。
3. `arch`：review framework/library boundaries，必要时补 ADR。
4. `doc`：更新 self-bootstrap operating loop 用户指南。
5. `rd`：按自举结果推进 validation harness、broader Graphiti persistent asset projection、richer Plane sync 或 agent-platform handoff。

## 7. 本计划完成标准

当下面条件满足时，本计划视为完成：

- Human 可以通过 Clara 创建并运行 AITeamOS improvement Tickets。
- AITeamOS improvement Tickets 运行在 Plane-backed Ticket Backend 上。
- Graphiti 能在自举中完成 approved asset ingest / search / recall。
- Ticket flow 可以完成 report、evidence、validation、Clara summary。
- Memory / Decision / Skill candidates 可以从完成的工作中产生。
- Review Queue 审批后，至少一条 Memory 可以被后续类似 Ticket recall。
- Ticket Asset Graph 可以解释 report、evidence、approved memory 的 provenance。
- Employee analytics 可以基于事实描述贡献和质量信号。
- 自举运行能证明“越用越聪明”：后续 Ticket 召回了前序 approved assets，并能看到质量、速度、阻塞或验证结果上的改善信号。
- Clara 能回答“AITeamOS 最近学到了什么、复用了什么、哪些经验过时了、下一轮应该怎么做”。
- 至少一批 AITeamOS 自身优化 Ticket 不需要大改架构即可端到端运行。
- 已选开源库保持稳定，除非满足明确换库条件。

## 8. 在计划完成前不做

- 替换 LangGraph 为其他 Agent framework。
- 替换 Graphiti 作为持久资产 knowledge graph 投影方向。
- 构建通用 Agent IDE。
- 构建通用项目管理克隆。
- 把所有 Ticket events、trace lines、chat turns 或 raw execution logs 写入 Graphiti。
- 在 graph facts 不稳定前做复杂 canvas graph。
- 继续投资 local-file Ticket Backend 作为并行路线。
- 把第三方 provider-native 名称暴露成 AITeamOS 内部产品概念。
- 做一个单一黑盒 Employee score。

## 9. 立即下一步

先执行 Phase 0 和 Phase 0.5：稳定 Chat/AI Engine 契约，同时把 Plane + Graphiti 作为真实底座上线。之后所有第一层自举 Ticket 都在这个底座上跑。

建议第一个 implementation pull：

1. 修复当前后端测试契约。
2. 固化 remote-engine-first 与 configuration-blocker 行为。
3. 稳定 memory / knowledge recall trace metadata。
4. 增加 Phase 0 / 0.5 smoke：
   - Clara 身份/能力回答。
   - Plane-backed Ticket create/report/transition。
   - Graphiti approved Memory ingest/search/provenance。
   - AI Engine configuration blocker。

第一层的第一个可见成功不应该是一个新页面，而应该是一个能端到端检查的真实 Plane-backed AITeamOS improvement Ticket。learning assertion 放到 Phase 3a：前一个 Ticket 产生的 approved Memory 能经 Graphiti 被后一个类似 Ticket recall，并出现在 trace / graph / Clara summary 中。
