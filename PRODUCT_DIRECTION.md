# AITeamOS 产品方向

**状态**：产品方向宪章  
**日期**：2026-06-03  
**用途**：约束后续 PRD、Architecture、Interaction Design 和实现决策

---

## 1. 文档定位

本文档回答一个问题：

> AITeamOS 为什么值得存在，以及它应该避免变成什么。

它位于 PRD、架构文档和交互设计之前。它不定义完整数据模型、API schema、页面细节、runtime 配置格式或具体实现目录。那些内容应在后续设计文档中展开。

本文档只定义：

- 产品核心论断
- 差异化边界
- 系统组成方式
- AI Member Role 模型
- WorkItem / Docs-first 流转原则
- Local-first 资产策略
- Member Chat Workbench 原型边界
- UI 和 Kernel 的职责边界
- 近期验证路径

---

## 2. 核心论断

AITeamOS 不是通用 Agent 聊天客户端、IDE、模型应用、Jira/Confluence 替代品或传统任务管理系统。

AITeamOS 是：

> **一个由 AI Member Roles 组装出来的、本地优先的 Agent Team OS。**

它的目标不是让用户在更多表单里配置更多对象，而是让用户能通过对话直接唤起一组具备角色、能力、记忆、工具和交接规则的 AI Members，围绕真实项目中的 WorkItem/Docs 系统、代码仓库、回归系统和本地知识资产，自动推进任务分解、执行、验证、沉淀和汇报。

一句话描述：

> 给 AITeamOS 一个真实任务，它应能让合适的 AI Members 自动协作，把任务推进到可验证结果，并把过程、证据、记忆和贡献留存在本地。

---

## 3. 差异化边界

AITeamOS 的差异化不在于重新做一个 Agent 客户端，也不在于重新做项目管理、Memory 数据库、CI、IDE 或通用 runtime。

它的差异化在于：

- **AI Member Role 管理**：为不同 AI Member 定义职责、性格、能力边界、Skill、工具权限、Memory 范围、runtime 偏好和交接规则。
- **中立资产层**：Memory、Skill、Knowledge、Prompt trace 和执行证据不绑定到某个商业客户端，而是成为团队本地资产。
- **WorkItem-first 协作流转**：任务、状态、沟通和交接尽量复用外部 WorkItem 系统，不重复开发用户可见 Task 系统。
- **Harness-first 验证闭环**：真实项目中的回归、构建、测试和发布系统是结果真理源，AITeamOS 负责驱动分析链条收敛。
- **Member-addressable 协作入口**：用户可以和 Clara 对话，也可以直接点名某个 AI Member，例如让 Alex 推进某个 ticket 并最终汇报。
- **Trace-first 可观察性**：UI 的价值不是替代 WorkItem/Docs 系统，而是让用户看清 Agent 团队背后发生了什么。
- **外部能力复用**：能复用现有 Agent IDE、CLI、API、MCP、CI、WorkItem/Docs、Memory 框架，就不在 AITeamOS 内重做。
- **团队贡献量化**：记录不同 AI Member 在问题分析、排除假设、交接、验证和沉淀中的有效贡献。

### Agent IDE 边界

AITeamOS 不应做另一个 Agent IDE。商业或开源 Agent IDE / Agent CLI / Deep Agent runtime 应被视为 **执行器**，而不是 AITeamOS 的竞争对象。

```text
Commercial / open-source Agent IDE = Executor
LangGraph / AG-UI / FastAPI = Orchestration bridge
AITeamOS = Agent Team control plane
```

AITeamOS 不重做 coding agent 的执行体验，例如 repo indexing、代码编辑器、terminal、diff/patch UI、PR 修改、repo chat、通用 tool loop 或通用长期记忆系统。AITeamOS 的职责是管理“谁在什么上下文、什么权限和什么团队目标下调用哪个成熟 Agent”，并把结果、证据、交接和 memory/skill candidate 留存在团队可审计资产中。

---

## 4. 系统模型

AITeamOS 的系统形态应保持简单：

```text
User
  -> Member Chat Workbench
  -> Clara or addressed AI Member
  -> Thin Kernel
  -> AI Member Roles
  -> MemberRuntimeAdapter
  -> Mature Agent Executors / Tools / MCP / External Systems
  -> WorkItem Flow + Docs + Local Trace + Memory + Skills
  -> Trace-first UI
```

关键组成如下：

- **Member Chat Workbench**：用户主要入口。用户可以默认与 Clara 对话，也可以直接选择或点名某个 AI Member，提出目标、约束、runtime 偏好和人工判断。
- **Thin Kernel**：极薄控制层。负责加载配置、管理权限、监听事件、唤醒成员、防重复触发和保存最小 trace。
- **AI Member Roles**：AITeamOS 的主要功能由 AI Members 完成，而不是由传统后端业务模块完成。
- **MemberRuntimeAdapter**：把 AI Member 的 profile、Skill、Memory、权限和 trace 边界映射到外部成熟 Agent、Agent CLI、模型 API、MCP 或本地 runtime。
- **Mature Agent Executors / Tools / MCP / External Systems**：Cursor、Claude Code、Deep Agents、OpenAI/Anthropic/DeepSeek provider、Plane、Repo、Harness、Memory、Skill、Runtime 等都作为可复用执行能力暴露给 AI Members。
- **WorkItem Flow**：外部 WorkItem 系统是任务与协作现场，Docs 系统是显性项目知识现场。
- **Local Assets**：本地保存 Member profiles、Skills、Memory 策略、Prompt/Context trace、执行证据和 Memory candidates。
- **Trace-first UI**：展示流转路径、证据、Prompt、Memory、runtime、Harness 结果和贡献。

设计原则：

- 能由 AI Member 调工具完成的，不优先做成表单。
- 能复用外部系统的，不优先自研。
- 能由外部 WorkItem 系统表达的任务状态，不在 AITeamOS 内重复建 Task 系统。
- 能直接对话唤起某个 Member 的，不强制绕行 Clara。
- AITeamOS 自己只保留让 Agent 团队稳定运行所必需的框架、策略、权限和 trace。

---

## 5. AI Member Role 模型

AI Member Role 是 AITeamOS 的核心抽象。

一个 Role 不是固定后端模块，而是一份可配置的 AI Member profile。它描述这个 Member 能做什么、不能做什么、如何使用工具、如何访问记忆、如何与其他 Member 交接，以及在什么条件下升级给人。

用户可以直接与任意 AI Member 对话。Clara 是默认协调者和兜底入口，但不是唯一对话对象。直接对话的典型形式包括：

```text
Alex，请你推进 ticket AIT-1234，必要时找 Release/PV 协作，最后汇报结果。
```

被点名的 Member 应按自己的 profile、Skill、Memory 策略、工具权限和升级规则行动；当任务需要拆分、转交或全局协调时，它可以把控制权交给 Clara 或触发 orchestration capability。

每个 AI Member Role 应包含：

- 职责和目标
- 性格与工作风格
- 负责模块、领域或能力范围
- 可用 Skill
- 可调用工具权限
- Memory 访问范围
- runtime 偏好与可用范围
- 成本、延迟和质量偏好
- WorkItem 流转和交接规则
- Harness、review 和验收规则
- 升级与人工介入规则
- 安全约束和禁止行为

典型内置 Members：

| Member | 核心职责 |
|---|---|
| **AI Team Lead** | 用户入口、需求理解、任务拆分、WorkItem 创建或选择、全局协调、最终汇报 |
| **AI Architect** | 架构分析、方案评估、边界审查、风险判断 |
| **AI RD / Implementer** | 代码实现、Bug 修复、技术产物落地 |
| **AI PV** | 回归失败、case、testbench、checker 和验证环境分析 |
| **AI Release** | release script、构建、集成、版本流和发布流程分析 |
| **AI QA / Harness Runner** | 触发测试、读取结果、组织验证证据 |
| **AI Memory Curator** | 从执行过程提炼 Memory 候选并维护质量 |
| **AI Trace Reporter** | 根据 WorkItem、trace、Memory 和 Harness 结果生成可观察视图 |

Clara 的职责边界必须保持清晰：Clara 是 **control-plane manager**，不是 Architecture/Tech Lead、RD 或 PV。她可以读取 Knowledge、创建或选择工作项、委派给合适 Member、收集报告、要求 PV 验证，并基于 LLM 对多方材料做一致性检查；但她不应直接读取代码仓库状态、执行 repo edit、运行测试或承担技术细节判断。代码仓库取证、技术方案、实现和验证应由 Architect、RD、PV 等 Member 完成，并以 report、trace、evidence、Decision candidate 或 Memory candidate 回传给 Clara。

### Orchestration Capability

Orchestrator 更适合被定义为一种 **orchestration capability**，而不是一开始就固定成用户必须理解的独立角色。

它的职责是：

- 观察 WorkItem 当前状态
- 判断下一步是否需要唤醒某个 Member
- 判断是否需要等待外部事件
- 判断是否需要触发 Harness
- 判断是否需要变更 assignee、status、link 或创建关联 WorkItem
- 判断是否失败、超预算、卡住或需要人工升级

实现上可以有两种形态：

- **原型阶段**：由 AI Team Lead 内置 orchestration mode，同一个 Member 负责用户对话和后台推进。
- **复杂流程阶段**：拆成独立 AI Orchestrator，用于多 WorkItem、长链路、定时轮询、失败重试、fan-out / fan-in 和预算控制。

无论哪种形态，用户都不需要理解 Orchestrator。Orchestration 是 AITeamOS 的执行策略，不应变成新的表单入口。

---

## 6. WorkItem / Docs-first 流转原则

AITeamOS 不开发用户可见 Task 系统，也不开发 Confluence 替代品。

文档中保留的“Jira/Confluence”可以理解为用户熟悉的概念速记：AITeamOS 真正依赖的是外部系统暴露的 **WorkItem capability** 和 **Docs capability**。从 1.0 方向看，默认且唯一主线的外部落点固定为 **Plane**：

- Plane Work Item 承载 WorkItem / ticket。
- Plane sub-issue、link、relation 和 page link 承载拆分、依赖、调查图谱和文档关联。
- Plane assignee、state、priority、label、type 和 custom property 承载流转和路由信号。
- Plane comment、activity 和 attachment 承载分析、状态变更、证据、结论、交接和汇总。
- Plane Page 承载项目 Docs、流程、规范、Decision 和可引用知识。
- Plane workspace、project、teamspace、member 和 permission 承载分组和权限边界。

选择 Plane 作为默认 WorkItem/Docs 后端后，AITeamOS 暂不实现 Redmine connector，也不同时维护多套 ticket 系统适配。只有当 AITeamOS 未来需要兼容更广泛团队生态时，再引入 Redmine、Jira/Confluence、OpenProject 或其它兼容 connector。

Adapter 仍然是必要边界：AITeamOS 内部只消费 `work_items.search/create/update/transition/comment/relate` 和 `knowledge.docs.search/read/write` 这类稳定 capability。AITeamOS Kernel 不复制 Plane 的完整产品模型；Cycle、Module、Intake、Initiative 等 Plane 特有概念先作为 PlaneAdapter 扩展，不升格为 AITeamOS 核心模型，除非后续产品需求证明它们是 Clara flow 的必要抽象。

产品形态上，Plane 是事实源，AITeamOS 是 AI Team Workbench：

- Plane 保留完整 Work Item / Page / project / permission / comment 体验。
- AITeamOS 不做 Plane 的表单克隆，不提供第二套完整 ticket 编辑器或 doc editor。
- AITeamOS 的 Work 页面提供 AI 团队运行视图：连接状态、活跃 WorkItems、负责人、阻塞点、验证状态、最近 report 和 trace 深链接。
- AITeamOS 的 Knowledge / Docs 页面提供统一知识入口：本地 Markdown、Plane Pages、Decisions 和 approved Memories 可以被统一搜索、引用和喂给 Clara/Member。
- 每个外部对象都应保留 `Open in Plane` 深链接；需要复杂编辑、权限治理或项目管理时回到 Plane。

选择 Plane 的长期原因：

- 体验现代，Work Items、Pages、comments、relations、attachments 和 project/workspace 语义更贴近 AI 团队协作。
- 官方 REST API 覆盖项目、Work Items、states、comments、links、activities、Pages、members 等 AITeamOS 需要的事实账本能力。
- 官方 MCP Server 路线与 AI Member 工具调用天然相容，后续可直接复用而不是自研协议层。
- Docker self-host 是官方路径，适合由 AITeamOS 作为 managed external service 固定版本、启动、监控和备份。
- AITeamOS 的主操作入口仍是 Chat；Plane 提供现代、可审计的 WorkItem/Docs 事实现场，而不是替代 Clara flow。

Plane 的部署形态：

- AITeamOS 不以 submodule/vendor 形式引入 Plane 源码。
- 开发和安装均通过 Docker 管理固定 Plane release，例如 `.aiteamos/plane` 下的官方 setup/compose/env 文件。
- AITeamOS 可一键启动本地 Plane，也可连接用户已有 Plane 实例。
- Settings / MCP Connectors 只暴露 Plane API base URL、API key、workspace slug、default project 等必要配置。
- Health 只确认 Plane service、API、auth 和 workspace 是否可用；不会直接操纵 Plane 内部数据库。

代码仓库不升格为复杂 Project 模型。Plane 已经承载 project、work item、page、成员和权限；AITeamOS 只需要知道某个 Plane workspace/project 关联哪些代码仓库：

- `local`：本地 checkout 路径，例如 `/home/me/project`。
- `github`：GitHub repository URL。
- `gitea`：Gitea repository URL。
- `gitlab` 或 `generic_git`：其它 Git repository URL。

这些配置归入 Settings / Code Repositories，保存为本地 ignored registry。它记录 repo name、provider、URL/path、default branch、Plane workspace/project 绑定和 enabled 状态。AITeamOS 不在这个 registry 内做 repo indexing、PR 编辑器、diff UI 或权限系统；真正的 repo 读取、搜索、修改、测试和报告由 Member Runtime、MCP repo connector 或外部 agent executor 执行。

Clara 可以通过 `list_code_repositories` 查看可用代码仓库，并在创建 WorkItem 时把 `code_repository_ids` 写入 WorkItem context。被委派的 RD/PV Member 再根据这些 repo ids 调用 repo tools 或外部 agent executor 获取代码事实。

P0 repo tools 只提供非常薄的本地能力：

- 对 `local` repository 做 bounded status / text search / read。
- 忽略 `.git`、`.aiteamos`、`node_modules`、`.venv`、`dist` 等目录。
- 限制读取文件大小，并只读取文本文件。
- 如果消息包含 WorkItem id，Member 的 repo inspection 可以写回 WorkItem report。
- 对 GitHub、Gitea、GitLab、generic Git 等 remote repository，只记录配置并提示需要 provider connector、MCP server 或 agent executor；AITeamOS 不自己实现 remote repo indexing。

AI Member 不需要在 comment 中重复标注自己的 role。当前负责方应由 WorkItem assignee 或 AITeamOS 归一化后的 assignee 表达。

典型流转：

```text
User
  -> Clara 理解目标
  -> Clara 创建或选择 WorkItem
  -> WorkItem 写入目标、上下文、验收条件和初始路由信息
  -> Kernel 监听 WorkItem 事件或定时查询
  -> 如果 assignee 明确，唤醒对应 Member
  -> 如果下一步不明确，触发 orchestration capability
  -> Member 读取 WorkItem、Docs、Memory、Skill、Repo、Harness 等上下文
  -> Member 执行分析或动作，并更新 WorkItem
  -> WorkItem assignee / status / relation / comment 驱动下一步
  -> Harness 或人工判断提供验证信号
  -> Clara 汇总链条结果
```

AI Member 可以根据上下文选择：

- 在现有 WorkItem comment 中继续分析
- 修改 assignee
- 修改 status
- link 到已有 WorkItem
- 创建新 WorkItem 或 subtask
- 读取或更新相关 Docs
- 触发 Harness
- 请求人工判断
- 汇总并关闭链条

核心不是“创建更多 ticket”，而是让 WorkItem assignee、status、comment、relation、Docs 和外部验证信号驱动问题收敛。

---

## 7. Local-first 资产策略

AITeamOS 必须让关键资产本地可控、可追踪、可迁移。

### File-first 原型策略

P0 阶段不优先设计数据库。

Member profiles、Skills、Memory policy、runtime 配置、provider thread 映射、conversation history 和 trace 应优先保存在本地文件中，例如：

```text
.aiteamos/
  members/
  skills/
  memories/
  conversations/
  traces/
  provider_threads.json
```

这样做的目的不是否定后续数据库，而是先验证真实协作闭环，避免过早把产品拉回以表、字段和 CRUD 为中心的实现方式。只有当文件化资产无法支撑并发、查询、权限、审计或迁移需求时，才引入数据库设计。

### Skill

Skill 是 AI Member 可复用的能力资产。初始版本应优先本地文件化，避免过早依赖外部 Skill Registry。

Clara 或被授权 Member 应能通过对话创建、修改和分配 Skill。例如：

```text
@Clara，请创建一个公开 Skill，用于分析 nightly regression log，
并关联给 PV 和 Release 使用。
```

UI 可以展示 Skill 列表、Skill 详情、Role 的 Skills 列表，以及某次 WorkItem 流转中使用了哪些 Skills，但创建和分配不应以表单为主路径。

### Knowledge

Knowledge 是 AITeamOS 的一级资产域，包含 Docs、Memories、Decisions 和 Review Queue。Clara 和各 Member 都应优先从 Knowledge 获取项目原则、流程、历史经验和已接受决策，而不是凭通用 LLM 常识行动。

```text
Knowledge
  -> Docs
  -> Memories
  -> Decisions
  -> Review Queue
```

- **Docs**：稳定、显性、可引用的源文档，例如 `PRODUCT_DIRECTION.md`、交互设计、架构原则、流程规范、ADR、coding style。Docs 初期优先读取本地 Markdown；外部系统第一落点是 Plane Pages。
- **Memories**：从执行、沟通、WorkItem resolve、验证和复盘中沉淀的时间性事实与经验。
- **Decisions**：被接受的技术或产品判断，通常从 Decision candidate 经 Architect 或 Human approval 后形成，适合以 ADR-like 文档保存，并同时写入 Memory/Graphiti 便于召回。
- **Review Queue**：待审核入口，不是知识类型本身。它可以包含 Memory candidate、Decision candidate、Doc update candidate 和 Skill candidate。

Clara 在拆解和委派前应调用 `search_knowledge`，读取相关 Docs、Decisions 和 approved Memories。需要代码仓库状态时，她应委派给对应 Member 取证，再把 Member report 与 Knowledge、WorkItem、trace 交给 LLM 做交叉验证。AITeamOS 不应把这种交叉验证硬编码成规则引擎。

Docs 的职责边界：

- 本地 Docs 承载 AITeamOS 自身方向、架构原则、coding style、流程规范和启动约束。
- Plane Pages 承载项目协作文档、方案页、复盘页、需求背景和与 WorkItem 强绑定的长文档。
- Knowledge / Docs 可以展示摘要、来源、更新时间、关联 WorkItem 和 `Open in Plane`，但不在 P0 做完整 Page 编辑器。
- 需要沉淀成长期原则的内容，应通过 Decision 或 Memory candidate 进入 Review Queue，而不是散落在聊天记录里。

### Memory

Memory 后端应采用 **Graphiti-first** 路线，而不是在 AITeamOS 内逐步自研一个 Memory 数据库、embedding/ranking 引擎或通用 Memory runtime。

AITeamOS 需要负责的是：

- Member 与 Memory 的访问策略
- Memory 如何被召回并进入 prompt/context
- 哪些 Memory 被发送给了哪个 runtime 或 provider
- Memory candidate 的来源、证据、置信度和作用域
- Memory 与 Member 贡献、项目经验、重复问题之间的关系

长期设计应把 Graphiti 作为 temporal knowledge graph 后端：

```text
AITeamOS Memory Policy / Audit UI
  -> Local candidate / approval / audit mirror
  -> Graphiti temporal knowledge graph
  -> Chat / WorkItem / Decision / Project-doc recall
```

分层原则：

- **短期记忆**：由 LangGraph checkpointer 管理 thread-scoped state。
- **长期记忆**：由 Graphiti 管理事实、时间、关系、provenance 和 hybrid search。
- **本地镜像**：AITeamOS 保存 memory candidate、approval 状态、scope、source、trace path 和 Graphiti 写入状态，作为离线兜底和审计入口。
- **Skill / procedural memory**：继续使用 `SKILL.md` 文件和 progressive disclosure。
- **Memory candidate**：由 AITeamOS 从 trace、conversation、WorkItem、Docs 和 runtime output 中记录候选，经过 approval 后才写入长期 memory backend。

AITeamOS 不实现通用 memory extraction、embedding、graph update、dedup、ranking 或 consolidation engine。这些能力应委托给 Graphiti。Mem0 暂不作为默认依赖；如果未来发现 Graphiti 在自动抽取、用户画像或 per-agent preference memory 上有明确缺口，再评估是否引入，而不是预先做一层复杂 MemoryAdapter。

Graphiti、Neo4j 和必要的 ingestion/search 运行依赖应被视为 AITeamOS 的内部依赖，而不是要求用户自行理解和装配的外部产品。可安装版本应提供一键启动或等价部署入口来拉起本地 Neo4j/Graphiti 运行条件，并在 Settings / Knowledge Backend 中只暴露必要配置：Graphiti enabled、Neo4j URI/user/password、group id、Graphiti 使用的 LLM key。环境变量只作为部署和自动化兜底；交互式产品主路径应写入本地 ignored settings/secrets 文件。

同一个 Memory 后端应优先通过 member、project、work_item、run、organization 或 metadata 做隔离。只有强安全隔离场景才需要为每个 Member 运行独立 Memory 实例。

Knowledge UI 的 Memories / Review Queue 职责是观察和治理，不是重做 Memory 后端：

- 展示本次 run 召回了哪些 memory。
- 展示哪些 memory candidates 被生成、批准或拒绝。
- 展示 memory 来源 trace、关联 WorkItem、scope、置信度和最后使用时间。
- 控制某个 Member、项目或 WorkItem 可访问哪些 memory scope。
- 暴露 backend adapter 健康状态和审计入口。

### MCP

MCP 可以作为 AITeamOS 的工具连接模块引入，但它不应替代 Skill、Knowledge 或 Clara flow。AITeamOS 内部仍用清晰的 tool schema 和权限边界表达能力；MCP 负责把外部系统能力标准化接入，例如 Plane、repo tools、CI/Harness、filesystem、browser 或第三方服务。

推荐形态：

```text
Clara / Member
  -> AITeamOS tool schema and permission gate
  -> MCP Client / connector registry
  -> External MCP Servers
```

官方 MCP SDK 已支持构建 MCP server/client、tools/resources/prompts、本地和远程 transport。Python 方向可优先评估 `modelcontextprotocol/python-sdk` / `mcp` 包；TypeScript 方向可评估 `modelcontextprotocol/typescript-sdk` 的 client/server packages。AITeamOS 不应自研 MCP 协议层，只需要实现 connector registry、权限、trace 和 tool result normalization。

P0 中 MCP 先落为 file-backed connector registry，例如 `.aiteamos/mcp_connectors.json`。Registry 记录 connector id、transport、enabled/configured 状态、capabilities、permissions 和 required settings。Clara 和 Member 只读取 AITeamOS 归一化后的 capability，不直接依赖某个外部 MCP server 的配置形状。Plane 作为默认 WorkItem/Docs connector 优先挂到 registry 后面；Redmine、Jira/Confluence、OpenProject 等兼容 connector 暂不实现，除非未来需要更广泛的 ticket 系统兼容。

AITeamOS 不应在产品模型里区分 WorkItem/Docs 系统是本地部署还是 Cloud。对 Kernel、Clara 和 Member 来说，它们都是 connector 暴露的稳定 capability，例如 `knowledge.docs.search`、`knowledge.docs.read`、`knowledge.docs.write`、`work_items.search`、`work_items.create`、`work_items.comment` 和 `work_items.transition`。部署形态只体现在 connector settings 里的 API base URL、auth 和 adapter normalization；UI 不提供 local/cloud 分叉路径。

### Capability Registry

Tool、MCP、Skill 和 Knowledge 不应混成同一个概念。AITeamOS 使用一个只读的 **Capability Registry** 把可执行能力收拢起来：

- **Knowledge** 是事实和历史，用于 grounding，不执行动作。
- **Skill** 是 Member 的工作方法、流程和判断标准，可以声明需要哪些 tools 或 knowledge scopes。
- **Tool** 是确定性可执行动作，例如 `create_work_item`、`search_knowledge`、`inspect_code_repository`。
- **MCP** 是外部 tools/resources 的标准接入层，例如 Plane、GitHub、filesystem 或 CI/Harness。
- **Agent Executor** 是成熟 Agent runtime，例如 Codex、Cursor、Qoder 或 Claude Code，负责更深的 coding、repo edit、test 和报告能力。

Capability Registry 是 Clara、MemberRuntimeAdapter、权限系统、trace 和 Settings UI 共享的能力目录。它记录 capability id、kind、domain、source、status、enabled/configured、permissions、required settings、arguments、produces、boundary 和 deep link。它不替代 Chat，也不提供普通用户点选执行入口；用户仍然通过 Chat 让 Clara 或某个 Member 选择并调用合适能力。

P0 中 registry 聚合三类内容：

- AITeamOS Kernel 内置 local tools。
- MCP connector registry 暴露的 connector capabilities。
- planned Agent Executors。

进入 1.0 后，Chat tool planner 应从 Capability Registry 读取可用 tool schema，而不是在多个模块里维护重复工具清单。Member profile 则引用 permissions、Skill 和 Knowledge scopes，表达“谁能用哪些能力”。

### Runtime / API

Runtime、API 和 LLM 配置不应成为独立产品层，而应是 Kernel 配置和 Clara 的运行条件。

可见配置入口应归入 **Settings**，而不是把 Runtime 做成主要业务导航。Settings 承载系统运行条件：Runtimes、Providers、Agent Executors、Capabilities、Code Repositories、MCP Connectors、Secrets、Defaults 和 Health。Chat 只保留当前 runtime 状态、轻量选择或跳转入口，不承担 API key、connector、agent executor 的完整配置。

Settings 还承载 Code Repositories。它不是 Project 管理系统，只是将 Plane workspace/project 与本地路径、GitHub、Gitea、GitLab 或 generic Git URL 关联起来，供 Clara 在创建/委派 WorkItem 时选择 repo context，并供 RD/PV Member 调用 repo tools 时定位目标代码源。

Settings 也承载 Knowledge Backend 配置。Graphiti 作为长期 memory backend 时，用户不需要理解 Graphiti/Neo4j 的内部调用链，只需要配置本机或托管图数据库连接、Graphiti group id、以及用于 Graphiti ingestion/search 的 LLM key。AITeamOS 负责把这些配置映射到 Graphiti runtime。

`Settings / Runtimes` 应采用 **runtime policy + provider-specific config** 的结构。Runtime policy 只决定 active provider、fallback policy 等跨 provider 运行规则；DeepSeek、OpenAI、File stub 或未来 provider 应拥有各自独立的配置卡片和保存动作。不要把多个 provider 的 model、thinking、API key 混在一个大表单里。

Clara 必须有默认 runtime，否则系统无法启动自动化流程。普通 Member 不应硬绑定某个 API。用户可以在对话中指定本次使用默认 runtime、特定 LLM API、Agent CLI、IDE Agent、本地模型或 CI 能力。

AITeamOS 不应抹掉商业或开源 Agent 自身的长期上下文能力。如果某个 AI Member 长期绑定同一个外部 agent、provider thread、IDE workspace 或 CLI session，外部 agent 可以继续积累它自己的经验。AITeamOS 在它前面增加的是一层本地可控的上下文闸门：

- 决定本次发送哪些 Member profile、Skill、Memory、WorkItem、Docs 和工具上下文。
- 记录哪些上下文被发送给了哪个 runtime/provider/thread。
- 约束权限、成本、安全和升级规则。
- 把执行过程、证据和 memory candidate 留存在本地。

成熟 Agent IDE、Agent CLI 和 Deep Agent runtime 是 AITeamOS 优先复用的执行层。AITeamOS 不做 repo indexing、diff/patch UI、terminal agent、PR 编辑器、通用 coding agent 或通用 Agent workbench；这些能力应由 MemberRuntimeAdapter 委托给外部执行器。AITeamOS 只决定调用哪个执行器、附带哪些上下文、使用哪个 session/thread、允许哪些工具和如何把结果回写到 WorkItem、Docs、trace、Memory candidate 或 Skill candidate。

AITeamOS 关注的是：

- 哪个 Member 在什么上下文下使用了哪个 runtime
- runtime 输入了哪些 prompt、memory 和工具结果
- runtime 输出如何进入 WorkItem、Docs、trace、Memory candidate 或 Harness 流程
- 外部 agent thread/session 是否被稳定复用，以及复用时是否经过 AITeamOS 的上下文闸门
- 成本、延迟、权限和安全约束是否被满足

真实 provider adapter 应接在 FastAPI / Kernel 后面，而不是绕过 AITeamOS 直接从 UI 调用。active provider、provider-specific model、thinking mode、fallback policy 等运行设置应由 UI 写入本地 runtime settings 文件；用户真正使用时只需要在 UI 中提供对应 provider 的 API key。环境变量只作为开发兜底，不应成为主要产品配置入口。

API key 应保存到本地 ignored secrets 文件或后续 secret store，不写入 trace、conversation、runtime settings、Git 或前端响应。没有 API key、没有选择 provider 或达到成本边界时，应回退到本地 file-backed stub 或本地开源模型。

### Trace

WorkItem/Docs 系统是协作现场，但不适合承载所有执行细节。

AITeamOS 应在本地保存最小但关键的 trace：

- WorkItem 流转快照
- Prompt 和 context 摘要或引用
- Memory recall 记录
- runtime 调用记录
- Repo、Harness、CI、测试和发布证据
- Member 判断、交接和贡献记录
- Memory candidates

这些 trace 是事实证据，不应只依赖 AI 生成摘要。

---

## 8. Harness-first 验证闭环

对真实工程项目，AITeamOS 的价值不只是“让 Agent 执行任务”，而是让问题经过验证闭环收敛。

Harness 可以来自外部系统：

- 源码仓库
- case 仓库
- regression 脚本仓库
- release 脚本仓库
- CI / nightly regression
- logs、reports、artifacts、baseline 和历史结果

典型问题链：

```text
regression fail
  -> Release 判断是否是构建、发布或环境问题
  -> PV 判断是否是 case、testbench、checker 或 regression 脚本问题
  -> RD 判断是否是实现或产品 bug
  -> 修复后触发 PV / Release / Harness 验证
  -> Clara 汇总 root cause、修复证据和后续 Memory candidate
```

WorkItem 负责流转，Docs 负责显性知识，Harness 负责验证，Memory 负责沉淀，Trace UI 负责解释过程。

---

## 9. UI 模型

AITeamOS UI 的主要价值不是替代 WorkItem/Docs 系统，也不是做一个更复杂的管理后台。

UI 应服务两个目标：

- **Conversation-first 操作**：用户主要通过 Member Chat Workbench 提出目标、补充约束、指定 runtime、批准高风险动作和要求汇报。Clara 是默认入口，但用户也可以直接选择或点名任意 AI Member。
- **Trace-first 观察**：用户能看清 WorkItem 背后的 Agent 团队路径、证据、Prompt、Memory、runtime、Harness 结果和贡献。

第一版 UI 可以非常克制：

- Member Chat Workbench
- Work / Tickets
- WorkItem Flow Trace

`Work` 是 AITeamOS 对 Plane / 本地 WorkItems 的 AI 运行视图，而不是另一个项目管理系统：

```text
Work
  -> Tickets
  -> Flow Trace
  -> Reports
```

- **Tickets**：显示 Plane connector 状态、本地 P0 WorkItems、后续 Plane Work Items 摘要、assignee、status、validation 和 deep links。
- **Flow Trace**：显示某个 WorkItem 背后的 Clara -> Member -> PV -> Clara 链路。
- **Reports**：显示 Member/PV 写回的结果、证据、阻塞点和 Clara 汇总。

WorkItem Flow Trace 可以展示：

- WorkItem、subtask、relation 的流转图
- assignee 和 status 变化
- 关键 comment 摘要
- 哪些 Member 被唤醒
- 使用了哪些 Skills
- 召回了哪些 Memory
- 调用了哪些 runtime 和 tools
- Harness 的 fail / pass / evidence
- 当前阻塞点和下一步建议

后续可以增加 Member View、Memory View、Skill View、Project View、Prompt Path View 和 Contribution View，但这些都应是观察视图，不应变成主要表单操作中心。

### Conversation Command 与 Entity View

AITeamOS 仍然需要 Work、Members、Skills、Knowledge、Settings 等导航视图，但它们不应成为主要操作路径。默认产品形式应是：

- **Chat 是主入口**：用户通过 Clara 或直接点名 Member 发出目标和命令。
- **工具结果先在对话中解释**：例如 `list_members` 应由 Clara 在当前对话中返回成员摘要、风险、缺口和建议下一步，而不是默认跳转页面。
- **实体页作为可检查视图**：当结果需要浏览、筛选、比较、审计或编辑细节时，对话回复应附带 deep link，例如 `Open Work`、`Open Members`、`Open Skill`、`Open Trace`。
- **高频动作可由工具完成**：创建 Member、创建 Skill、分配 Skill、读取 runtime settings 等优先做成 AI Member tool。
- **复杂管理仍可有页面**：当用户需要批量查看、手工修正、审计历史或调试运行条件时，Members / Skills / Knowledge / Settings 页面仍然有价值。

因此，导航栏应保留，但其角色应从“产品主流程”降级为“观察、审计、调试和手工维护视图”。用户能在 Chat 中完成的动作，不应强制跳转到表单页。

---

## 10. Thin Kernel 边界

AITeamOS 需要 Kernel，但 Kernel 必须保持薄。

Kernel 应负责确定性、安全性和可回放性：

- 加载 Member profiles、Skills 和 runtime 配置
- 管理工具权限、secret 和安全边界
- 暴露 Tools / MCP capability
- 监听 WorkItem webhook、WorkItem 查询或定时触发器
- 唤醒对应 Member 或 orchestration capability
- 防止同一 WorkItem 被重复触发或并发踩踏
- 保存最小 trace 和执行证据
- 执行预算、权限、重试、停止和人工升级策略

Kernel 不应负责：

- 代替 AI Member 做复杂产品判断
- 固化所有业务流转逻辑
- 重做 WorkItem/Docs、CI、Memory DB、IDE、Agent runtime 或通用聊天客户端
- 把能力重新包装成传统 CRUD 模块

随着产品演进，Kernel 可以变强，但它增强的方向应是安全、权限、触发、追踪和可回放，而不是变成传统业务系统中心。

---

## 11. Non-goals

AITeamOS 不应该做：

- Plane 或其它外部 WorkItem/Docs 系统的替代品
- 通用 Agent 聊天客户端
- Agent IDE 或 IDE 替代品
- repo indexing、代码编辑、terminal、diff/patch、PR 修改等 coding agent 执行体验
- 通用 LLM runtime
- 完整 Memory 数据库
- 完整 Skill Marketplace
- CI / regression 系统
- 表单式项目管理后台
- 以数据库实体为中心的内部任务或执行管理系统

判断一项能力是否应该进入 AITeamOS，先问：

- 这件事能否由 AI Member 调用工具完成？
- 是否已有成熟工具、MCP、开源框架或商业系统可复用？
- 是否真的需要新表单、新表或新内部任务系统？
- 它是否增强了 Role、WorkItem Flow、Docs、Memory、Skill、Harness、Trace 或本地资产沉淀？

如果可以由 Agent 调工具完成，就优先委托给 Agent。

---

## 12. 近期验证路径

近期不追求做大而全的 MVP，而是快速验证 AITeamOS 的核心闭环：

### P0：Member Chat Workbench

用户能通过 Member Chat Workbench 与 Clara 或任意 AI Member 对话：

- 选择或点名一个 AI Member，例如 Alex、PV、RD 或 Clara
- 绑定或识别一个 WorkItem key
- 用本地文件加载 Member profile、Skill、Memory policy 和 runtime 偏好
- 复用稳定的外部 provider thread/session 映射
- 将 conversation 和 trace 写入本地文件
- 返回当前处理状态、下一步计划和可追踪证据路径

P0 不要求：

- 设计数据库 schema
- 真实同步外部 WorkItem/Docs 系统
- 真实触发 Harness
- 实现完整多 agent 编排
- 取代外部 agent 自身的长期记忆能力

### P0.1：Real Clara Runtime

在 P0 chat 闭环之后，优先把 Clara 接到一个真实 runtime：

- 通过 FastAPI runtime adapter 调用真实 Agent 或模型 provider。
- 每轮请求前由 AITeamOS 组装 Member profile、Skill、Memory、WorkItem、Docs 和权限上下文。
- 稳定保存 provider conversation、thread、session 或 previous response id。
- 将 provider 输入摘要、输出、模型、usage 和 response id 写入本地 trace。
- provider、model 和 API key 由 Settings / Runtimes 配置，保存为本地 file-backed settings/secrets；Chat 只显示当前 runtime 状态和配置入口。
- 默认不开启付费 provider；只有用户在 UI 中显式配置后才允许真实调用。

开发阶段可以先用 DeepSeek 作为低成本真实模型 provider。此时暂时假设 provider 具备 agent session 能力，只保存本地 provider state，不为了“越用越聪明”额外组装大量历史上下文；等验证完 chat 和 trace 链路后，再接入更完整的 agent session、Memory recall 或 coding agent runtime。

### P0.2：assistant-ui Chat Workbench

在真实 runtime 接通后，Member Chat Workbench 应接入 assistant-ui 作为前端聊天 primitives/runtime，而不是长期维护自研聊天框架。assistant-ui 负责 composer、message list、运行状态、自动滚动和后续 tool call 展示；AITeamOS 仍负责 member routing、runtime settings、context gate、trace、provider state 和 file-backed persistence。

### P0.3：Chat-to-LLM Flow

Chat Workbench 到 LLM/API 的长期主路径应使用成熟开源协议和 runtime 组合，而不是继续扩大 AITeamOS 自研 chat bridge：

```text
assistant-ui
  -> @assistant-ui/react-ag-ui
  -> AG-UI protocol
  -> FastAPI AG-UI gateway
  -> ag-ui-langgraph adapter
  -> LangGraph default AgentRuntime
  -> AITeamOS MemberRuntimeAdapter
  -> mature Agent executors / provider adapters / file-backed assets
```

该 flow 的边界是：

- **assistant-ui** 负责聊天窗口、composer、message list、运行状态、取消、重试和后续 tool 展示。
- **AG-UI** 负责前后端 agent event protocol，包括 text events、tool events、state snapshot、interrupt 和 future generative UI。
- **FastAPI** 负责 API gateway、鉴权、runtime settings、secret 边界、错误处理和本地文件访问入口。
- **ag-ui-langgraph** 负责把 AG-UI request/event 与 LangGraph graph state/message 互相转换。
- **LangGraph** 是默认后端 AgentRuntime，负责 stateful graph、tool planning/execution loop、HITL、checkpoint 和长任务编排。
- **MemberRuntimeAdapter** 负责把 Member 身份、上下文、权限和 provider/session/thread 映射到外部成熟 Agent 或模型 provider。
- **AITeamOS Kernel** 只负责产品内核：Member、Skill、Memory、permission、trace、provider state、deterministic local tools 和对成熟 Agent 的委托边界。

前端不应做语义 intent parsing，也不应直接调用 provider API。后端 graph 可以调用 LLM 做 tool planning、task planning、handoff planning、approval planning 或 memory planning；真正执行 coding、repo edit、terminal、PR、CI 和复杂 agent loop 时，应优先委托给成熟 Agent IDE / Agent CLI / Deep Agent runtime。AITeamOS 本地工具只负责确定性元操作和 trace。

这一设计应作为 1.0/2.0/3.0 的基础边界。允许替换默认 AgentRuntime，例如未来从 LangGraph 切到 Microsoft Agent Framework、PydanticAI、CrewAI 或其它 runtime，但前端仍应优先保持 AG-UI 协议层稳定，AITeamOS Kernel 不应被某个 runtime 的内部 state schema 绑死。

旧的 AITeamOS 自研 SSE 协议只作为迁移期兼容路径，最小事件包括：

- `start`：返回 thread、run、target member、provider thread 和 WorkItem keys。
- `delta`：返回增量文本。
- `final`：返回完整 ChatMessageResponse，包括 trace 和 saved paths。
- `error`：返回可展示的 provider 或 runtime 错误。

新功能不应继续扩展该自研协议；应优先映射到 AG-UI events。

### P0.3.1：Native Provider Streaming

对已接入的 provider，应优先把其原生流式输出映射到 AG-UI text events。例如 DeepSeek Chat Completions 的 `delta.content` 应转为 AG-UI `TEXT_MESSAGE_CONTENT` 或经 LangGraph/AG-UI adapter 映射到 assistant-ui 可消费的消息事件，最终 `usage`、model、response id 和 provider state 进入 AG-UI state snapshot 与本地 trace。迁移期可以继续保留旧 SSE stream，直到 assistant-ui AG-UI runtime 覆盖同等体验。

### P0.3.2：Member Threads and Short-Term State

每个 Member 应有稳定的默认 conversation thread，例如 `member-clara-default`。Thread metadata 由后端 file-backed index 管理，记录 `member_id`、title、active thread、message count、updated time 和 archived 状态；前端只负责通过 assistant-ui history/thread adapter 加载和切换，不再把 member/thread 映射作为浏览器本地事实源。

Conversation history、LangGraph checkpoint 和长期 Memory 必须分层：

- **Conversation history**：用户和 Member 看得见的 transcript，用于 UI 恢复和短期上下文回放。
- **LangGraph checkpoint**：graph execution cursor，用于 pending tool、approval、interrupt/resume、time travel 和失败恢复。
- **Long-term Memory**：跨 thread、跨任务沉淀的可治理知识，不用于替代当前 thread 状态。

P0 使用 file-backed conversation history 恢复 UI，并把同一 thread 的最近消息送入 provider/tool planner 作为短期上下文。LangGraph checkpoint 的本地 baseline 是 `langgraph-checkpoint-sqlite`，写入 `.aiteamos/langgraph/checkpoints.sqlite`；进入 1.0 后再按部署形态迁移到 Postgres、Redis、MongoDB 或 LangGraph Agent Server 托管 checkpoint。

### P0.4：Clara Tools

Clara 的第一组工具应服务本地 file-backed 资产：

- `list_members`
- `create_member`
- `edit_member_profile`
- `delete_member`
- `list_skills`
- `create_skill`
- `assign_skill_to_member`
- `delete_skill`
- `search_knowledge`
- `create_work_item`
- `list_work_items`
- `record_work_item_report`
- `list_code_repositories`
- `inspect_code_repository`
- `read_runtime_settings`

工具调用的默认结果应在对话中返回结构化摘要，并写入 trace。需要进一步浏览或手工调整时，再提供实体页 deep link，而不是把用户从对话中强制跳走。

工具意图识别不应依赖固定句式。P0 可以先由配置好的 LLM provider 产出结构化 tool plan，再由 AITeamOS 本地确定性执行 tool；本地规则只作为离线、开发和 planner 失败时的兜底。

### P1：Role-composed Kernel

最小 Kernel 能：

- 加载 Member profiles
- 加载本地 Skills
- 加载默认 runtime
- 暴露 WorkItem、Docs、Memory、Skill、Repo、Harness、Runtime tools
- 监听 WorkItem 并唤醒 Member
- 记录最小 trace
- 管理权限、secret 和重复触发

### P2：WorkItem Flow Trace

第一版 UI 只需清楚展示一个 WorkItem 链条：

- 发生了什么
- 谁处理过
- 为什么转交
- 使用了哪些 Memory、Skill、runtime 和工具
- Harness 结果是什么
- 当前阻塞点在哪里

### P3：Local Skill 与 Memory 接入

验证：

- Clara 能通过对话创建本地 Skill
- Skill 能关联到 Member
- Member 执行时能使用 Skill
- Memory 能按 Member、项目和 WorkItem 上下文召回
- Memory candidate 能从执行过程产生

### P4：Harness / Regression 调查链

选择一个真实 regression fail 场景，验证：

- Release、PV、RD 等 Members 能通过 WorkItem 流转协作
- Harness 结果能驱动下一步判断
- root cause、修复证据和 Memory candidate 能被汇总
- 人能通过 Trace UI 看懂背后发生了什么

---

## 13. 成功指标

AITeamOS 应以“AI Member 团队是否能在真实项目中自动推进问题收敛”来衡量成功。

关键指标包括：

- Clara 创建或推进 WorkItem 的数量
- AI Members 完成的有效交接次数
- 从问题出现到 root cause 确认的时间
- 从 root cause 到 Harness 验证通过的时间
- 自动生成并被采纳的分析、判断和交接说明数量
- 人工介入次数与介入原因
- 重复问题是否减少
- Memory candidate 生成数、批准率和复用率
- Skill 创建数、复用率和关联覆盖率
- Prompt、Memory、runtime、Harness 和 WorkItem trace 完整率
- 不同 Member 的有效贡献占比

---

## 14. 战略原则

AITeamOS 的长期方向是：

> 用极薄 Kernel 和本地优先资产层，把一组 AI Member Roles 组织成可以围绕 WorkItem/Docs 和真实工程系统自动协作的 Agent Team OS。

它应该持续遵守三条原则：

- **Agent-first**：凡是能由 AI Member 调用工具完成的，不优先做成表单。
- **Reuse-first**：凡是已有成熟外部系统可复用的，不优先自研。
- **Trace-first**：凡是 Agent 团队做过的重要判断、上下文、工具调用和验证结果，都应可本地追踪、可解释、可沉淀。
