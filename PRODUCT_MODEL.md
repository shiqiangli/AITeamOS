# AITeamOS 产品模型

**状态**：产品模型决策  
**日期**：2026-06-03  
**范围**：核心产品对象、导航模型、资产模型，以及可吸收的外部产品设计经验

---

## 1. 核心模型

AITeamOS 应被建模为一个 **以 Ticket 为中心的 AI Workforce Operating System**。

Chat 是主要交互入口。Employees 是执行和协作主体。Ticket 是工作对象、流转锚点和团队账本，让多个 Employees 能围绕同一个真实任务跨时间协作。Knowledge assets 则围绕 Ticket flow 被生成、审核、分配、召回和演进。

AITeamOS 不应被理解为：

- 通用 AI 聊天客户端
- Employee CRUD 管理后台
- Plane / Jira 克隆
- Memory 数据库 UI
- Agent IDE

AITeamOS 应被理解为：

> 一个让 AI Employees 推进真实 Tickets、产出证据、生成可复用资产，并沉淀可追溯团队记忆的系统；这些团队资产不绑定到任何单一 agent 平台。

稳定的产品闭环是：

```text
Human goal
  -> Clara 创建或选择 Ticket
  -> Ticket 承载目标、上下文、负责人、验证人、关联 docs、repos 和验收条件
  -> AI Employees 通过接手、汇报、交接和请求验证来协作推进
  -> AI Engine 和 Tool execution 产出 evidence 和 trace
  -> Reports、Decisions、Memory candidates、Docs updates 和 Skill candidates 进入 Ticket Asset Graph
  -> Clara 汇总、交叉验证，并把结果回复给 human
  -> 审核通过的 assets 成为可复用团队知识，并可赋予给不同 Employees
```

---

## 2. 核心对象

### Ticket

Ticket 是最主要的工作对象。

它承载：

- 用户目标和验收条件
- 当前阶段和下一步期望动作
- 当前 owner Employee
- validator 或 PV Employee
- 关联代码仓库和 evidence
- 关联 Docs 和 Decisions
- reports 和 handoff records
- trace events 和 AI Engine runs
- 由本次工作产生的 Memory candidates 和 approved Memories

Plane 可以作为外部 Ticket / Docs 事实源，但 AITeamOS 拥有对这项工作的 AI-team 解释层。

### Employee

Employee 是 AI 或 human worker profile。

它承载：

- 身份、角色、使命、性格和边界
- Skills
- Knowledge access scopes
- Capability access policy
- AI Engine 偏好
- 当前和历史 Ticket 参与记录
- 贡献记录

Employees 不应拥有孤立 task 作为主要产品模型。它们的工作通常应表达为对 Tickets 的参与。

### Asset

Asset 是 Ticket flow 中被创建或使用的、可复用或可审计的产物。

核心 assets 包括：

- Docs
- Memories
- Decisions
- Skills
- Capabilities
- Reports
- Evidence
- Trace events

Assets 必须携带 provenance：

- 来源 Ticket
- 来源 run 或 trace
- 创建或贡献 Employee
- 审核状态
- 被分配的 Employees 或 scopes
- 新鲜度和使用历史

---

## 3. Ticket Asset Graph

AITeamOS 应明确引入 **Ticket Asset Graph**。

Ticket Asset Graph 不是长期 Memory 本身。它是 AITeamOS 的产品工作图，用来解释 work、Employees 和 assets 之间如何关联。

最小图实体包括：

- Ticket
- Employee
- Run
- Handoff
- Report
- Tool call
- AI Engine session
- Trace event
- Evidence
- Memory candidate
- Approved Memory
- Decision candidate
- Accepted Decision
- Doc
- Skill
- Capability
- Repository
- Harness 或 validation result

重要关系包括：

- Ticket assigned to Employee
- Ticket validated by Employee
- Employee produced Report
- Report belongs to Ticket
- Run uses AI Engine
- Run uses Skill
- Run calls Capability
- Run recalls Memory
- Run reads Doc
- Run produces Evidence
- Run proposes Memory candidate
- Run proposes Decision candidate
- Memory derived from Ticket
- Decision derived from Ticket
- Asset assigned to Employee
- Asset supersedes or conflicts with another Asset
- Ticket blocks, relates to, or follows another Ticket

这个图应能回答：

- 哪些 Employees 参与过这个 Ticket？
- 每个 Employee 贡献了什么？
- 最终结论有哪些 evidence 支撑？
- 执行过程中召回了哪些 Memories？
- 这个 Ticket 产生了哪些新的 Memories 或 Decisions？
- 新 asset 应该赋予给哪个 Employee 或 scope？
- 如果某条 Memory 过时，可能影响哪些 Tickets？
- 哪个外部 agent session 产出了某个结果？

---

## 4. Graphiti 与 Ticket Graph 边界

AITeamOS 已经选择的开源图记忆组件是 **Graphiti**。

Graphiti 应继续作为长期 temporal knowledge graph，用于 Memory 和语义召回。它适合承载事实、关系、时间语义、provenance，以及长期 Memory 的 hybrid search。

但 Ticket Asset Graph 比 Memory 更宽：

```text
Ticket Asset Graph
  -> AITeamOS 拥有的 product / work graph
  -> 包含 Ticket、Employee、Run、Trace、Report、Evidence、Decisions、Docs、Skills、Capabilities、Repositories 和 Memories

Graphiti
  -> long-term Memory / temporal knowledge graph backend
  -> 存储或索引 approved Memories，以及部分被选中的 Decisions / Facts
```

推荐边界：

- 使用 Plane 作为外部 Ticket / Docs 事实源。
- 使用 AITeamOS 本地 trace 和 metadata 作为 AI work trace 的事实源。
- 使用 Graphiti 管理 approved long-term Memory 和语义关系召回。
- 不强行把每个 Ticket event 都写入 Graphiti。
- 不为了“未来灵活性”先构建第二套通用 graph database abstraction。
- 围绕 AITeamOS work events 建一个小而明确的 Ticket Asset Graph，让 Graphiti 服务其中的 Memory 子集。

---

## 5. 导航模型

当前导航可以保持紧凑：

```text
Chat
Tickets
Employees
Assets
Settings
```

推荐语义优先级：

1. **Chat**：自然语言操作入口。
2. **Tickets**：AI 工作 cockpit 和 flow ledger。
3. **Employees**：workforce system of record 和治理视图。
4. **Assets**：可复用团队资产和审核队列。
5. **Settings**：AI Engines、Tool Connectors、Code Repositories、Ticket Backend 和 Memory Backend。
6. **System Status**：System Summary 和 Secrets Health 的只读运行状态入口。

### 为什么叫 Assets

`Library` 可以理解，但它偏静态、偏文档中心。

`Assets` 更贴合 AITeamOS 的核心论断，因为 Docs、Memories、Decisions、Skills、Capabilities、Reports、Evidence 和 Trace 都是 Ticket flow 中产生的团队资产，并且可以赋予给不同 Employees。

推荐产品方向：

- 使用 **Assets** 作为产品概念。
- 一级 UI 入口使用 `Assets`，不再把 Knowledge、Skills、Tools、Connectors 拆成彼此竞争的一级概念。
- Assets 内部保持清晰分区：

```text
Assets
  -> Knowledge
       -> Docs
       -> Memories
       -> Decisions
  -> Capabilities
       -> Skills
       -> Built-in Tools
       -> MCP Tools
  -> Review Queue
       -> Memory candidates
       -> Decision candidates
       -> Skill candidates
       -> Tool / capability change requests
```

Review Queue 不应只是 Knowledge 的子页面。它应成为 Ticket flow 中产出的各类 assets 的统一审核队列。

---

## 6. 页面职责

### Chat

Chat 负责启动、重定向、中断、确认和汇总 Ticket flow。

它应该展示：

- 当前 active Employee
- 当前 active Ticket
- AI Engine
- 简洁 run metadata
- assistant reply 下方的 tool / trace footer
- 右侧 run inspector，用于深度调试

Chat 不应变成通用 settings 或 asset browsing UI。

### Tickets

Tickets 应成为核心 work cockpit。

它应该展示：

- 按 active、blocked、waiting validation、done、needs human 分组的 Ticket queue
- 当前 owner Employee
- 当前 stage
- next expected action
- validation status
- latest report
- 关联 Docs、Repos、Decisions、Memories 和 Evidence
- Clara -> Employee -> PV -> Clara timeline
- `Open in Plane`
- `Ask Clara`
- `Assign Employee`
- `Request PV`
- `Promote Decision`
- `Approve Memory`

Ticket 的承载层通过 `TicketAdapter` 接入。P0 使用 local file，让 AITeamOS 可以快速自举，并允许把本地 Ticket 文件放入仓库跟踪系统演进；长期默认后端可以切到 Plane。AITeamOS Tickets 始终是 AI-team operating view，不是 Plane/Jira/OpenProject 的表单克隆。

Adapter 只解决事实源访问问题，不改变产品模型：

- `local_file`：P0 默认，用于本地开发、自举和轻量团队验证。
- `plane`：长期默认目标，提供完整 project、ticket、page、comment、permission 现场。
- `jira`：未来兼容目标，只有在需要企业生态对接时再实现。

### Employees

Employees 应成为 workforce system of record。

每个 Employee detail 应展示：

- Overview
- Work
- Skills and Capabilities
- Knowledge Access
- Permissions
- AI Engine
- Activity

Work tab 必须以 Ticket 为中心：当前 Tickets、历史 Tickets、reports、validations、contribution、failures 和 handoffs。

### Assets

Assets 应展示可复用、可审计的团队资产。

每个 asset 应暴露：

- provenance
- source Ticket
- source Employee
- approval status
- assigned Employees or scopes
- usage history
- conflicts、supersession 或 staleness
- related Tickets

### Settings

Settings 只应承载运行条件：

- AI Engines
- Ticket backend
- Tool connectors
- Code repositories
- Memory Backend
- Security and approval policy

Employee Defaults 更适合逐步移动到 Employees，或在 System Status 中只读展示，而不是作为主要 Settings 概念。

推荐 Settings 与 System Status 导航：

```text
Settings
  -> AI Engines
       -> llm_api
       -> agent_platform
  -> Tool Connectors
       -> mcp_server
       -> native_api
       -> cli
       -> ci
  -> Code Repositories
       -> product repos
       -> harness / regression repos
  -> Ticket Backend
       -> local_file
       -> plane
       -> jira
  -> Memory Backend
       -> Graphiti / Neo4j

System Status
  -> System Summary
  -> Secrets Health
```

AI Engines 是 Clara 和 Employees 思考或执行的后端。DeepSeek、OpenAI / ChatGPT API、Kimi、Gemini、Ollama、LM Studio、vLLM 等都可表达为 `llm_api`；Codex、Claude Code、Cursor、Qoder 等可表达为 `agent_platform`。本地模型不是单独的产品层级，而是 `llm_api` 的本地 deployment。

Tool Connector 是外部能力来源的配置入口。MCP Server 是 Tool Connector 的一种 `kind`，不是和 Connector 并列的产品概念。AITeamOS 作为 host / client 连接 MCP Server，发现其 tools / resources / prompts，并把可执行动作归一化到 Capabilities / MCP Tools。AITeamOS Kernel 自带动作进入 Capabilities / Built-in Tools。Plane、Jira 等 Ticket 事实源优先归入 Ticket Backend；它们派生出的 `tickets.create`、`tickets.comment`、`tickets.transition` 等动作进入对应的 capability tool 分类，但配置不在 Tool Connectors 中重复。

System Status 是一级只读状态入口，放在 Settings 之后。API key、token、password 等敏感值只通过环境变量提供；Settings 的各业务页面只配置非敏感信息和环境变量引用。System Status / Secrets Health 只展示需要哪些环境变量、用途、是否已配置、如何配置，以及被哪个 AI Engine、Ticket Backend、Tool Connector 或 Memory Backend 使用。

---

## 7. 可吸收的外部产品模式

### QoderWake

可吸收模式：

- digital employee role templates
- Employee profile sections：Memory、Skills、Connectors、Projects、Permissions
- conversation tasks 和 triggered tasks
- local-first control console
- 面向高风险操作的 approval cards

AITeamOS 的吸收方式：

- 保留 rich Employee profile 的思路。
- 让 Ticket 成为主要工作对象，而不是让每个 Employee 拥有孤立 task。
- 将 triggered tasks 理解为 Ticket triggers 或 orchestration rules。

参考：https://docs.qoder.com/qoderwake/quick-start

### Workday Agent System Of Record

可吸收模式：

- agent lifecycle governance
- 统一 visibility 和 accountability
- permissioning
- agent work analytics
- third-party agent gateway 思路

AITeamOS 的吸收方式：

- 用 Employees 承载 workforce records。
- 用 Tickets 承载 accountability ledger。
- 用 Ticket Asset Graph 承载 contribution、traceability 和 analytics。

参考：https://www.workday.com/en-us/artificial-intelligence/agent-system-of-record.html

### Copilot Studio / Agentforce

可吸收模式：

- 将 knowledge 与 executable actions 分离
- action / tool schema
- connectors 作为外部 capability sources
- 治理 agent 能做什么

AITeamOS 的吸收方式：

- 继续区分 Knowledge、Capabilities 和 Connectors：Capabilities 内含 Skills、Built-in Tools 和 MCP Tools；Connectors 只负责接入配置。
- 让 Clara 和 Employees 通过 Capability Registry 发现 executable tools。
- 用户仍然通过 Chat 操作，而不是把所有 action 都做成按钮。

参考：

- https://learn.microsoft.com/en-us/microsoft-copilot-studio/add-tools-custom-agent
- https://developer.salesforce.com/docs/ai/agentforce/guide/get-started-actions.html

### Plane

可吸收模式：

- 现代 Ticket 和 project model
- Pages / Docs 作为 linked knowledge
- comments、activities、relations、labels、states 和 attachments
- API-first integration path

AITeamOS 的吸收方式：

- Plane 仍然是 Ticket / Docs fact source。
- AITeamOS 拥有 AI-team flow、trace、asset generation 和 Employee accountability。
- AITeamOS 不复制 Plane 的 editing 或 planning surfaces。

参考：https://docs.plane.so/

---

## 8. 设计原则

1. Ticket 是工作主线。
2. Employees 围绕 Tickets 协作。
3. Assets 从 Ticket flow 中产生。
4. Assets 可以赋予给 Employees，但不归属于任何单一 agent 平台。
5. Chat 是操作入口，不是数据模型。
6. Tickets 是 work cockpit，不是 project-management clone。
7. Employees 是 workforce ledger，不只是 profile list。
8. Assets 是共享记忆和能力库存，不是被动文档库。
9. Settings 是 AI Engine、backend、connector、repo 和 memory 的运行条件，不是业务页面；System Status 是只读运行状态入口。
10. 外部 agent platforms 是 AI Engines；AITeamOS 是 control plane 和 asset graph。
