# AITeamOS 用户指南

> 面向系统管理员（Admin）的操作手册，帮助你使用 AITeamOS Dashboard 管理团队、推进项目、沉淀经验。

---

## 目录

1. [系统概述](#系统概述)
2. [核心概念](#核心概念)
3. [快速上手：推荐操作顺序](#快速上手推荐操作顺序)
4. [Dashboard 导航](#dashboard-导航)
5. [Departments — 部门管理](#departments--部门管理)
6. [Employees — 成员管理](#employees--成员管理)
7. [Projects — 项目管理](#projects--项目管理)
8. [Tasks — 任务管理](#tasks--任务管理)
9. [Memories — 经验管理](#memories--经验管理)
10. [Skills — 能力管理](#skills--能力管理)
11. [Agents — Agent / LLM 运行时配置](#agents--agent--llm-运行时配置)
12. [Memory Review — 审查与治理](#memory-review--审查与治理)
13. [Metrics — 系统度量](#metrics--系统度量)
14. [Home — 总览仪表盘](#home--总览仪表盘)
15. [删除与安全约束](#删除与安全约束)
16. [常见操作场景](#常见操作场景)

---

## 系统概述

AITeamOS 是一个**团队操作系统**，解决团队在人员切换和 Human-to-AI 转型过程中，隐性经验无法有效沉淀、流转和复用的问题。

系统中的人类工程师和 AI 数字员工共享统一的身份、任务、权限、记忆与审查体系。核心资产分为两类：

- **Memory（经验）** — 有状态的业务上下文，代表"在特定战场上怎么干"。
- **Skill（能力）** — 无状态的通用能力组件，代表"会干什么"。

Dashboard 是管理员操作系统的统一入口，覆盖从组织架构搭建到任务执行、审查、度量的完整流程。

---

## 核心概念

| 概念 | 说明 |
|------|------|
| **Department（部门）** | 组织架构单元，Employee 和 Project 的归属容器 |
| **Employee（成员）** | 团队成员，可以是人类（human）或 AI 数字员工（ai） |
| **Project（项目）** | 归属于某个部门的工作项目，可分配成员参与 |
| **Task（任务）** | 具体的工作单元，拥有完整的状态生命周期 |
| **Memory（经验/记忆）** | 团队沉淀的知识，分为 Facts（事实）、Patterns（模式）、Principles（原则）三层 |
| **Skill（技能）** | 可复用的能力组件，可版本化、跨项目使用 |
| **Review（审查）** | 对 Memory 候选、任务产出等的审核流程 |
| **Conflict（冲突）** | 两条 Memory 之间的矛盾，需要人工仲裁 |
| **Proposal（提案）** | 系统自动产生的 Memory 候选，等待人工审批 |

---

## 快速上手：推荐操作顺序

如果你是首次使用系统，建议按以下顺序初始化：

```
1. 创建 Department（部门）   ← 先搭组织架构
2. 创建 Employee（成员）       ← 将成员归入部门
3. 创建 Project（项目）      ← 在部门下建项目
4. 创建 Task（任务）         ← 在部门下创建任务并分配给成员
5. 管理 Memory（经验）       ← 沉淀和管理团队知识
6. 注册 Skill（技能）        ← 登记可复用的能力组件
7. 配置 Agent / LLM          ← 为 AI Employee 选择执行运行时
8. 在 Memory 详情中审查       ← 审核提案、处理冲突
9. 查看 Metrics 度量         ← 监控系统健康度
```

---

## Dashboard 导航

Dashboard 左侧为固定侧边栏，包含以下导航项：

| 图标 | 名称 | 用途 |
|------|------|------|
| 仪表盘 | **Home** | 系统总览，快速查看各项指标和最近活动 |
| 大脑 | **Memories** | 管理团队的经验和知识 |
| 扳手 | **Skills** | 管理可复用的能力组件 |
| 机器人 | **Agents** | 管理中性的 Agent Profile 与 LLM 模型 |
| 用户 | **Employees** | 管理团队成员（人类和 AI） |
| 建筑 | **Departments** | 管理组织架构中的部门 |
| 文件夹 | **Projects** | 管理项目 |
| 清单 | **Tasks** | 管理任务及其生命周期 |
| 图表 | **Metrics** | 系统度量和健康监控 |

所有页面通过浏览器访问 `http://localhost:5173`。

---

## Departments — 部门管理

**路径**：侧边栏 → Departments

部门是组织架构的基本单元，每个 Employee 和 Project 都必须归属于一个部门。

### 创建部门

1. 点击 **Create Department** 按钮
2. 填写 **Department Name**（必填，名称不可重复）
3. 选择 **Leader**（可选，从成员下拉菜单中选择，也可以手动输入成员名称）
4. 点击 **Create**

### 部门列表

列表展示所有部门，包含以下信息：
- **Name**：部门名称
- **Leader**：部门负责人名称（如已指定）
- **Created**：创建时间

> **提示**：部门名称在系统中必须唯一。如果尝试创建同名部门，系统会报错。

---

## Employees — 成员管理

**路径**：侧边栏 → Employees

成员是团队中的工作单元，分为 **AI（数字员工）** 和 **Human（人类工程师）** 两种类型。

### 创建成员

1. 点击 **Create Employee** 按钮
2. 填写以下信息：
   - **Display Name**（必填）：成员显示名称，不可重复
   - **Kind**：选择 `AI` 或 `Human`
   - **Department**（必填）：从下拉菜单选择所属部门，或手动输入部门名称
   - **Role**（可选）：角色描述，如 `developer`、`reviewer`
   - **Base Skills**（可选）：基础技能，用逗号分隔，如 `python, testing`
3. 点击 **Create**

### 查看成员详情

在列表中点击某个成员，右侧面板会显示：
- 显示名称、类型、角色、所属部门
- 并发限制（Concurrency Limit）
- 是否已归档
- 基础技能集
- 已关联的 Memory 列表

### 分配技能

1. 在详情面板中点击 **Assign Skill**
2. 从下拉菜单选择 Skill 名称，也可以手动输入唯一的 Skill 名称
3. 点击 **Confirm**

### 删除成员

在详情面板中点击 **Delete** 按钮。如果该成员被其他记录引用（如作为部门负责人、任务执行者等），系统将拒绝删除并提示。

---

## Projects — 项目管理

**路径**：侧边栏 → Projects

项目归属于部门，是组织工作的容器。AITeamOS 中只维护项目的概览信息，项目的完整内容（代码、文档等）存放在外部仓库中。AI 成员通过仓库地址访问项目内容并执行任务。

### 创建项目

1. 点击 **Create Project** 按钮
2. 填写以下信息：
   - **Project Name**（必填）：项目名称
   - **Department**（必填）：从下拉菜单选择所属部门
   - **Description**（可选）：项目描述
   - **Repository URL**（推荐）：项目的 Git 仓库地址或本地目录路径，AI 成员将通过此地址访问项目内容
3. 点击 **Create**

### 查看项目详情

点击项目后，右侧面板显示：
- 项目名称、描述
- **Repository**：仓库地址（AI 成员通过此地址访问项目代码）
- 状态、所属部门
- 已分配成员列表

### 分配成员到项目

1. 在详情面板中点击 **Assign Employee**
2. 从下拉菜单中选择成员名称
3. 点击 **Confirm**

### 删除项目

在详情面板中点击 **Delete**。如果项目存在关联数据，系统将拒绝删除。

---

## Tasks — 任务管理

**路径**：侧边栏 → Tasks

任务是系统中的核心工作单元，拥有完整的状态生命周期。

### 任务状态机

```
draft → ready → assigned → running → verifying → in_review → done
                         ↘ failed → (requeue) → ready
                         ↘ cancelled
```

| 状态 | 说明 |
|------|------|
| **draft** | 草稿，刚创建 |
| **ready** | 已就绪，等待分配 |
| **assigned** | 已分配给成员，等待执行 |
| **running** | 正在执行中 |
| **verifying** | 执行完毕，验证中 |
| **in_review** | 验证通过，等待审查 |
| **done** | 已完成 |
| **failed** | 执行失败，可重新排队 |
| **cancelled** | 已取消 |

### 创建任务

1. 点击 **Create Task** 按钮
2. 填写以下信息：
   - **Title**（必填）：任务标题
   - **Description**（可选）：任务描述
   - **Department**（必填）：从下拉菜单选择部门
   - **Agent**（可选）：从下拉菜单选择 Agent Profile，或手动输入 Agent 名称
   - **LLM**（可选）：从下拉菜单选择模型；为空时使用 Agent 的默认 LLM
   - **Priority**：优先级，P0（最高）到 P3（最低），默认 P2
   - **Deliverable Kind**：产出类型，可选 `Code Change`、`Document`、`Design`、`Configuration`
3. 点击 **Create**

### 任务操作

在详情面板中，根据当前状态可以执行不同操作：

- **Assign**（draft/ready 状态）：将任务分配给成员
- **Runtime**：调整该任务绑定的 Agent / LLM
- **Start Run**（assigned 状态）：启动任务执行
- **Requeue**（failed 状态）：将失败的任务重新排队为 ready
- **Cancel**：取消未结束的任务
- **Delete**：删除任务

### 按状态筛选

列表上方有状态下拉菜单，可以选择 **All States** 或某个具体状态来过滤任务。

### 统计指标

列表顶部显示三个统计数字：
- **Ready**：等待分配的任务数
- **Running**：正在执行的任务数
- **Done**：已完成的任务数

---

## Memories — 经验管理

**路径**：侧边栏 → Memories

Memory 是系统的核心资产之一，代表团队沉淀的知识和经验。

### Memory 三层模型

| 层级 | 说明 | 示例 |
|------|------|------|
| **Facts** | 客观事实 | "该项目使用 PostgreSQL 15 作为主数据库" |
| **Patterns** | 经验模式 | "当并发超过 100 时，连接池需要调整为 20" |
| **Principles** | 核心原则 | "所有 API 变更必须向后兼容" |

### 创建 Memory

1. 点击 **Create Memory** 按钮
2. 填写以下信息：
   - **Tier**：层级，选择 `Facts`、`Patterns` 或 `Principles`
   - **Scope Kind**：作用域类型，可选 `Project`、`Tech Stack`、`Department`、`Global`
   - **Source Kind**：来源类型，可选 `Manual Input`、`Task Execution`、`Review`、`Bulk Import`
   - **Scope ID**：作用域 ID（可选，默认为 global）
   - **Title**（必填）：Memory 标题
   - **Statement**（必填）：Memory 内容描述
3. 点击 **Create**

### Memory 生命周期

| 状态 | 说明 |
|------|------|
| **draft** | 草稿，刚创建 |
| **candidate** | 候选，等待审核 |
| **active** | 激活，正常参与召回 |
| **needs_verify** | 需要验证（可能因代码变更等导致置信度下降） |
| **archived** | 归档，不再参与召回但保留 |
| **deprecated** | 废弃，已被标记为过时 |

在详情面板中，可以根据当前状态执行：
- **Activate**（draft 状态）：激活 Memory
- **Archive**（active 状态）：归档 Memory
- **Deprecate**（active 状态）：废弃 Memory

### 关键字段

- **Confidence**：置信度（0~1），表示该 Memory 的可靠程度，会随使用反馈和时间衰减动态变化
- **Versions**：版本号，Memory 每次更新会递增
- **Tags**：标签，用于分类和检索

---

## Skills — 能力管理

**路径**：侧边栏 → Skills

Skill 代表可复用的能力组件，是无状态的通用能力，可跨项目使用。

### 注册 Skill

1. 点击 **Register Skill** 按钮
2. 填写以下信息：
   - **Skill Name**（必填）：技能名称
   - **Version**：版本号，默认 `1.0.0`
   - **Domain**：能力领域，如 `compiler`、`frontend`、`ops`
   - **Description**：能力说明，描述这个 Skill 能解决什么问题
   - **Inputs / Outputs**：输入要求与输出承诺
   - **Preconditions**：调用前置条件
   - **Side Effects**：副作用声明，建议按 `resource_kind:resource_pattern:mutation_kind` 分行填写
   - **Required Permissions**：需要的权限
   - **Capability Tags**：能力标签，逗号或换行分隔，如 `compiler, optimization`
   - **Examples / References / Quality Signals**：示例、参考资料和质量信号
3. 点击 **Register**

### Skill 生命周期

| 状态 | 说明 |
|------|------|
| **registered** | 已注册，可以发布 |
| **published** | 已发布，可以使用 |
| **deprecated** | 已废弃 |

在详情面板中可以执行：
- **Publish**（registered 状态）：发布 Skill
- **Deprecate**（published 状态）：废弃 Skill
- **Delete**：删除 Skill

### 关键字段

- **Circuit State**：熔断状态，当 Skill 连续失败时自动熔断保护
- **Inputs / Outputs / Preconditions**：接口和调用约束
- **Side Effects / Permissions**：执行副作用和权限边界
- **Examples / References / Quality Signals**：帮助成员理解和评估该能力

---

## Agents — Agent / LLM 运行时配置

**路径**：侧边栏 → Agents

Agents 页面用于维护中性的 AI 执行运行时配置。它不代表具体成员，而是供 Task 选择的执行策略和模型资源。

### 配置 LLM

1. 点击 **Create LLM**
2. 填写以下信息：
   - **LLM Name**（必填）：模型在系统内的唯一名称
   - **Provider**（必填）：模型提供方，如 `openai`、`anthropic`、`local`
   - **Provider Model ID**（必填）：供应商模型 ID
   - **Endpoint**：调用类型，如 `Chat`、`Responses`、`Completion`、`Embedding`
   - **Context Window / Max Output Tokens**：上下文与输出上限
   - **Supports tools / Supports JSON**：模型能力开关
   - **Input Cost / Output Cost**：成本记录，便于后续预算控制
   - **Capability Tags**：适用能力标签
3. 点击 **Create**

### 配置 Agent

1. 点击 **Create Agent**
2. 填写以下信息：
   - **Agent Name**（必填）：Agent Profile 在系统内的唯一名称
   - **Runtime Kind**：运行时类型，默认 `llm_agent`
   - **Default LLM**：默认使用的 LLM，可下拉选择或手动输入 LLM 名称
   - **Description**：Agent 的用途与工作方式
   - **System Prompt**：该 Agent 的系统级执行提示
   - **Tool Names**：可用工具名称
   - **Memory Policy / Safety Policy**：JSON 形式的记忆与安全策略
3. 点击 **Create**

### 在 Task 中使用 Agent / LLM

1. 进入 **Tasks**
2. 创建 Task 时填写 **Agent**，可选填 **LLM**
3. 如果只填 Agent，系统会自动使用 Agent 的 Default LLM
4. 如果同时填写 LLM，则以 Task 中显式选择的 LLM 为准
5. 在 Task 详情弹窗的 **Actions** tab 中点击 **Runtime**，可以重新绑定 Agent / LLM

---

## Memory Review — 审查与治理

**路径**：侧边栏 → Memories → 打开某条 Memory → Review tab

Memory 的审核、提案和冲突治理都在 Memory 详情弹窗内完成，避免从独立 Review 页面跳转造成上下文丢失。

### 审核 Memory

在 Memory 详情的 **Review** tab 中：
1. 查看 **Review Settlement** 区块
2. 选择 Reviewer
3. 对候选或待确认 Memory 点击：
   - `Approve`：通过
   - `Reject`：拒绝
   - `Merge`：合并
   - `Revise`：需要修改
4. 填写 Reason 和 Correction（如适用）
5. 系统会记录 Review Case，并在批准时把 Memory settle 到目标状态

### Proposals（提案）

在 Memory 页面可以看到 candidate 状态的提案。点击某条 Memory 后，直接在详情弹窗的 **Review** tab 中完成审核。

列表显示待审批提案的标题、层级、置信度和作用域。

### Conflicts（冲突）

Memory 冲突也在 Memory 详情的 **Review** tab 中处理。

**报告冲突**：
1. 打开某条 Memory
2. 进入 **Review** tab
3. 点击 **Report Conflict**
4. 选择 **Memory A** 和 **Memory B**（冲突的两条 Memory）
5. 选择 **Conflict Kind**（冲突类型）：
   - `Semantic`：语义冲突
   - `Contradiction`：矛盾
   - `Scope Overlap`：作用域重叠
6. 选择 **Detected By**（检测方式）：
   - `Embedding Similarity`：向量相似度检测
   - `Manual Report`：人工报告
   - `Reflection Engine`：反思引擎检测
7. 点击 **Report**

**解决冲突**：
在 Memory 详情的冲突列表中点击一个未解决冲突：
1. 选择 **Resolution**（解决方式）：
   - `Keep A`：保留 Memory A
   - `Keep B`：保留 Memory B
   - `Merge`：合并
   - `Deprecate Both`：全部废弃
2. 如果选择 Keep A 或 Keep B，填写 **Winner Memory ID**
3. 选择 **Resolved By**（解决人）
4. 点击 **Resolve**

---

## Metrics — 系统度量

**路径**：侧边栏 → Metrics

度量页面提供系统整体健康状况的可视化。

### System Overview（系统概览）

以卡片形式展示关键指标：
- **Memories**：Memory 总数
- **Active**：活跃 Memory 数量
- **Candidates**：候选 Memory 数量
- **Skills**：Skill 总数
- **Employees**：成员总数
- **Tasks**：任务总数
- **Recalls**：Memory 召回次数
- **Active Rate**：Memory 活跃率

### System Health（系统健康）

- **Database**：数据库连接状态
- **Status**：系统整体状态
- **First Pass Rate**：任务首次通过率（越高越好，>70% 为健康）
- **Open Conflicts**：未解决的冲突数
- **Pending Reviews**：待处理的审查数

### Memory Health（Memory 健康）

- **Active**：活跃状态的 Memory 数量
- **Candidate**：候选状态的数量（过多说明审核积压）
- **Needs Verify**：需要验证的数量（过多说明知识库稳定性不足）
- **Deprecated**：已废弃的数量
- **Candidate Ratio / Deprecated Ratio / Needs Verify Ratio**：各状态占比

---

## Home — 总览仪表盘

**路径**：侧边栏 → Home

首页提供系统的快速概览：

- **顶部统计卡片**：Memories 总数、Skills 总数、Employees 总数、Projects 总数、Running Tasks 数、Ready Tasks 数
- **Memory Health**：Memory 各状态的分布
- **Recent Memories**：最近创建的 Memory（点击可跳转详情）
- **Recent Tasks**：最近创建的任务（点击可跳转详情）
- **Recent Skills**：最近注册的 Skill
- **Recent Employees**：最近加入的成员

---

## 删除与安全约束

系统中所有实体都支持删除操作，但有以下安全约束：

1. **前向引用检查**：如果一个实体被其他实体引用（如部门被成员引用、成员被任务引用），系统将拒绝删除并返回错误提示
2. **确认对话框**：所有删除操作都会弹出确认对话框，需要用户二次确认
3. **不可恢复**：删除后数据无法恢复，请谨慎操作

### 推荐的删除顺序

由于引用关系的存在，推荐的删除顺序为（从叶子到根）：

```
Task → Review/Conflict → Project → Employee → Skill → Memory → Department
```

---

## 常见操作场景

### 场景一：搭建新团队

```
1. 创建部门 "Engineering"
2. 创建部门 "QA"
3. 创建 AI 成员 "CodeBot"，归入 Engineering
4. 创建 Human 成员 "Alice"，归入 Engineering，角色 "tech lead"
5. 创建 Human 成员 "Bob"，归入 QA，角色 "tester"
6. 更新 Engineering 部门，指定 Alice 为 Leader
```

### 场景二：启动新项目

```
1. 创建项目 "Website Redesign"，归入 Engineering 部门
2. 将 Alice 和 CodeBot 分配到该项目
3. 配置 LLM "Local Code Model" 或供应商模型
4. 配置 Agent "Frontend Agent"，选择默认 LLM
5. 创建任务 "Design new homepage"，归入 Engineering，优先级 P1，并选择 Frontend Agent
6. 将任务分配给 CodeBot
7. 启动任务执行（Start Run）
```

### 场景三：沉淀团队经验

```
1. 创建 Memory，Tier 选 Patterns，标题 "连接池配置经验"
2. 填写 Statement："当并发超过 100 时，PostgreSQL 连接池应调整为 max_connections * 0.8"
3. 设置 Scope 为 Project，关联到具体项目
4. 打开该 Memory 的详情，在 Review tab 中 Approve 有价值的提案
5. 在 Memory 详情的 Review tab 中处理矛盾 Memory，保持知识库一致性
```

### 场景四：监控团队健康度

```
1. 在 Home 页面查看任务运行状态和 Memory 概况
2. 在 Metrics 页面关注 First Pass Rate（首次通过率）
3. 检查 Open Conflicts 是否过多
4. 在 Memories 中筛选 candidate 状态，检查是否有积压的候选 Memory
5. 在 Metrics → Memory Health 中关注 Needs Verify 数量
```

### 场景五：管理 Skill 能力库

```
1. 注册 Skill "code-review"，版本 0.1.0，标签 "review, quality"
2. 发布 Skill（Publish）使其可用
3. 将 Skill 分配给成员（在成员详情页 Assign Skill）
4. 当 Skill 不再需要时，Deprecate 废弃
```

---

## 附录：下拉菜单使用技巧

系统中所有关联字段（如部门选择、成员选择等）都使用**可输入的下拉菜单（ComboInput）**：

- **下拉选择**：点击输入框会显示已有选项列表，点击即可选择
- **手动输入**：也可以直接输入名称，系统会在提交时自动匹配对应的实体
- **名称匹配**：系统优先按名称匹配，如果找不到则尝试按 ID 匹配

> **注意**：所有实体的名称在系统内必须唯一，这是实现"按名称查找"的基础。
