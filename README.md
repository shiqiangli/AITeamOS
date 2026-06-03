# AITeamOS

> 以经验和能力为双核资产的团队操作系统。

AITeamOS 解决团队在人员切换和 Human-to-AI 转型过程中，隐性经验无法有效沉淀、流转和复用的问题。它让人类工程师和 AI 数字员工共享统一的身份、任务、权限、记忆与审查体系。

---

## 核心理念

AITeamOS 的资产模型围绕两个核心概念构建：

- **Memory（经验）** — 有状态的业务上下文，代表"在特定战场上怎么干"。分三层：Facts（事实）、Patterns（模式）、Principles（原则），带置信度、生命周期和关系图。
- **Skill（能力）** — 无状态的通用能力组件，代表"会干什么"。可插拔、可版本化、跨项目复用。

核心公式：

```
Capability = Skill (How to do) x Memory (What we know)
Evolution  = Capability --[Execute]--> Harness (Right or Wrong) --[Reflect]--> Delta Memory
```

**Harness（验证系统）** 是外部真理源，确保非确定性 AI 输出确定性结果，同时驱动 Memory 持续演进。

---

## 系统架构

### 边界上下文（Bounded Contexts）

基于 DDD 划分为 6 个边界上下文，跨上下文通过领域事件 + DTO 通信，同步读取通过 Anti-Corruption Layer（ACL）+ 依赖倒置：

| 上下文 | 聚合根 | 职责 |
|--------|--------|------|
| **Knowledge** | `MemoryNode`, `MemoryEdge` | Memory 提炼、关系图、置信度演进、生命周期管理 |
| **Capability** | `Skill` | Skill 注册、版本、加载、健康度、熔断 |
| **Workforce** | `Member`, `Department` | 成员管理、组织归属、能力画像 |
| **Execution** | `Task` | Task 状态机、Run、Deliverable、Context Snapshot |
| **Validation** | `HarnessAdapter` | 验证适配、回调、结果归一、Flaky 检测 |
| **Governance** | `ReviewCase`, `ConflictCase` | 审核流程、冲突仲裁、归因度量 |

### 三层逻辑架构

1. **Context/State Layer（上下文与状态层）** — Context Assembler 从 Knowledge + Capability 召回并组装不可变的 Context Snapshot，受 Token 预算硬约束。
2. **Driver/Execution Layer（驱动与执行层）** — Task 状态机驱动执行，Saga 编排异步流程，Cost Interceptor 全程计量。
3. **Assertion/Validation Layer（断言与验证层）** — Harness Gateway 路由到对应 Adapter，Reflection Engine 从执行结果中提炼 Memory 候选。

### 关键技术决策

- **CQRS + Event Sourcing Outbox**：写路径走 Command + Domain Event（PostgreSQL Outbox），读路径走幂等投影消费者（Kafka -> 多读模型）。
- **混合存储**：PostgreSQL（主存储）+ pgvector（语义向量检索 HNSW）+ 图库（Memory 关系拓扑多跳遍历）。
- **不可变快照**：Task 装配阶段产出的 Context Snapshot 一旦写入即只读，反思、归因、回放一律以快照为准。
- **幂等投影**：所有读侧投影消费者基于全局事件序列号实现 CAS 条件写，保证 At-least-once 投递下绝对幂等。

---

## 核心特性

- **多通道 Memory 召回** — assigned / scope / vector / graph 四通道并行召回，单通道降级不阻塞整体，排序综合置信度、语义相似度、作用域匹配和新鲜度。
- **置信度动态演进** — 基于使用反馈（正向提升 / 负向降低）+ 时间衰减的 4 因子方程，Facts 不衰减仅由级联失效驱动。
- **级联失效检测** — 代码/架构变更时沿 Memory 关系图 BFS 传播降级，带扇出上限和分批写回，超限自动降级为异步处理。
- **Review-First 安全模型** — Worker 隔离执行，所有产出必须通过审查；Secret 永不进入 prompt/log/界面。
- **Task 完整生命周期** — Draft -> Ready -> Assigned -> Running -> Verifying -> InReview -> Done，支持异步验证挂起和审核拒绝回退。

---

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.11+ / FastAPI / Pydantic v2 |
| 存储 | PostgreSQL + pgvector |
| 事件总线 | Kafka（Outbox Pattern） |
| Worker | aiokafka + 投影消费者 + Saga 引擎 |
| 前端 | React / TypeScript / Vite / Tailwind CSS / Radix UI |

---

## 项目结构

```
AITeamOS/
├── packages/                 # DDD 边界上下文（独立 Python 包）
│   ├── knowledge/            #   Knowledge Context — Memory 领域
│   ├── capability/           #   Capability Context — Skill 领域
│   ├── workforce/            #   Workforce Context — Member/Department 领域
│   ├── execution/            #   Execution Context — Task/Run 领域
│   ├── validation/           #   Validation Context — Harness 领域
│   ├── governance/           #   Governance Context — Review/Conflict 领域
│   └── shared_kernel/        #   跨上下文共享值对象与工具
├── services/
│   ├── api/                  # FastAPI 服务（Composition Root + CQRS 读写分离）
│   ├── worker/               # Worker 进程（投影消费者 + Kafka + Saga）
│   └── saga/                 # Saga 编排引擎
├── apps/
│   └── dashboard/            # Web Dashboard（React + Vite + Tailwind）
├── migrations/               # PostgreSQL 增量迁移脚本
├── tests/                    # 测试套件
├── docs/                     # 架构与设计文档
└── docker/                   # 容器化配置
```

---

## 快速开始

### P0 一键启动（推荐）

当前 file-first 路线只要求本地文件、FastAPI、Dashboard，以及作为 Graphiti 后端的 Neo4j。Graphiti/Neo4j 属于 AITeamOS 内部运行依赖，用户只需要在 Settings 中配置必要的 key 和连接信息。

```bash
./scripts/dev-up.sh
```

这个脚本会：

- 启动 `docker/docker-compose.yml` 中的 `neo4j` 服务
- 创建 `.venv` 并安装后端依赖，包括 Graphiti
- 初始化 `.aiteamos/graphiti.json` 和 `.aiteamos/secrets.local.json` 的本地默认项
- 启动 FastAPI: http://127.0.0.1:8000
- 启动 Dashboard: http://127.0.0.1:5173

进入 Dashboard 后，在 `Settings / Knowledge Backend` 中配置 Graphiti 使用的 OpenAI key。也可以在 `Settings / Runtimes` 配置 OpenAI key，Graphiti 会优先复用该 key，除非 Knowledge Backend 配置了专用 key。

### 外部 WorkItem / Docs 系统

AITeamOS 不内置用户可见的 Jira/Confluence 替代品。默认选型是 Plane：Plane Work Item 映射为 WorkItem / ticket，Plane Page 映射为 Docs。AI Member 通过 `Settings / MCP Connectors` 中配置的 connector capability 访问外部系统，例如 `work_items.search`、`work_items.create`、`work_items.comment`、`work_items.transition`、`knowledge.docs.search` 和 `knowledge.docs.read`。

P0 仍使用本地 file-backed WorkItems 和 Docs 来验证 Clara-led flow；后续优先接 Plane connector。AITeamOS 暂不实现 Redmine、Jira/Confluence 或 OpenProject connector，除非未来需要兼容更广泛的 ticket 系统生态。

Dashboard 中的 `Work / Tickets` 是 AI 团队运行视图：展示 Plane 连接状态、本地 P0 WorkItems、负责人、验证状态、report 数量和 Plane 深链接。完整 ticket 编辑、项目规划、权限和文档编辑仍在 Plane 中完成。`Knowledge / Docs` 是统一知识入口：本地 Markdown 作为 AITeamOS 自身文档源，Plane Pages 作为外部项目文档源。

`Settings / Capabilities` 是只读能力目录，用来查看 AITeamOS Kernel local tools、MCP connectors/capabilities 和 planned Agent Executors。它把边界保持清楚：Knowledge 是事实，Skill 是方法，Tool 是动作，MCP 是外部动作/资源接入层，Agent Executor 是成熟 agent runtime。普通工作仍从 Chat 发起，不从 Capabilities 页面点选执行。

代码仓库在 `Settings / Code Repositories` 中配置。AITeamOS 只记录 Plane workspace/project 到 repo source 的薄映射，支持本地路径、GitHub、Gitea、GitLab 和 generic Git URL。本地路径会做轻量 `.git` 检查；远端仓库的 API/MCP 访问由后续 provider connector 或 agent executor 负责。

Chat 中 Clara 可以列出这些仓库，并在创建本地 WorkItem 时把 `code_repository_ids` 写入上下文，供 RD/PV Member 后续通过 repo tools 或外部 agent executor 获取代码事实。

P0 的 repo tool 只支持配置过的本地仓库：非 Clara Member 可以搜索/读取有界文本文件，并在消息包含 WorkItem id 时把 repo evidence 写回 WorkItem report。GitHub/Gitea/GitLab 等远端仓库在 P0 只保存配置，真实读取由后续 provider connector、MCP server 或 agent executor 承接。

### 可选：Plane 本地服务

开发机可以通过 Docker 启动 Plane。AITeamOS 不以 submodule/vendor 形式引入 Plane 源码；`scripts/plane-up.sh` 会下载固定 Plane release 的官方 setup 脚本，并把 Plane 运行文件放到 `.aiteamos/plane/`。

```bash
AITEAMOS_WITH_PLANE=1 ./scripts/dev-up.sh
```

也可以只启动或管理 Plane：

```bash
./scripts/plane-up.sh up
./scripts/plane-up.sh stop
./scripts/plane-up.sh logs
```

默认本地端点：

- Plane: http://localhost:8082

启动后，在 Plane 中创建 API key，然后到 `Settings / MCP Connectors` 配置 Plane API base URL、API key、workspace slug 和默认 project。AITeamOS 与 Plane 通信始终通过 connector/API 层完成，不把 Plane 的完整产品模型复制进 AITeamOS Kernel。

### Legacy DDD Stack

### 环境要求

- Python 3.11+
- Node.js 18+
- Docker + Docker Compose（用于 AITeamOS 内部运行依赖，例如 Neo4j）

### 1. 启动 PostgreSQL

```bash
docker run -d \
  --name aiteamos-postgres \
  -p 5432:5432 \
  -e POSTGRES_DB=aiteamos \
  -e POSTGRES_USER=aiteamos \
  -e POSTGRES_PASSWORD=dev_password \
  pgvector/pgvector:pg15
```

等待 PostgreSQL 就绪（约 5 秒）：

```bash
docker exec aiteamos-postgres pg_isready -U aiteamos -d aiteamos
```

### 2. 初始化数据库

按序执行所有迁移脚本：

```bash
for f in migrations/*.sql; do
  docker exec -i aiteamos-postgres psql -U aiteamos -d aiteamos < "$f"
done
```

### 3. 安装后端依赖

```bash
# 创建虚拟环境（推荐）
python -m venv .venv
source .venv/bin/activate

# 安装项目依赖
pip install -e ".[dev]"
```

### 4. 启动后端服务

```bash
export AITEAMOS_DATABASE_URL="postgresql://aiteamos:dev_password@localhost:5432/aiteamos"
uvicorn aiteamos_api.main:create_app --factory --host 0.0.0.0 --port 8000 --reload
```

验证后端健康：

```bash
curl http://localhost:8000/health
# 预期输出: {"status":"ok","database":"connected"}
```

### 5. 启动前端开发服务器

另开终端：

```bash
cd apps/dashboard
npm install
npm run dev
```

### 6. 访问

- **前端 Dashboard**: http://localhost:5173
- **后端 API**: http://localhost:8000
- **API 文档 (Swagger)**: http://localhost:8000/docs

### 运行测试

```bash
# 后端测试
pytest

# 前端测试
cd apps/dashboard && npm run test
```

---

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `AITEAMOS_DATABASE_URL` | PostgreSQL 连接字符串 | `postgresql://postgres:postgres@localhost:5432/aiteamos` |
| `AITEAMOS_ADMIN_API_KEY` | Admin API 密钥（未设置时放行所有请求） | 空（开发模式） |
| `AITEAMOS_EMBEDDING_MODEL` | Embedding 模型 | `text-embedding-3-small` |
| `AITEAMOS_LLM_MODEL` | LLM 模型 | `gpt-4o-mini` |
| `OPENAI_API_KEY` | OpenAI API 密钥（未设置时使用 mock） | 空 |

---

## 文档

- [产品需求文档 (PRD)](./docs/PRD-core.md) — 产品定位、核心概念、功能需求
- [系统架构文档 (ADD/TDD)](./docs/arch.md) — 领域模型、存储策略、运行时引擎、设计纪律
- [用户指南 (User Guide)](./docs/USER_GUIDE.md) — 管理员操作手册，Dashboard 使用流程

---

## License

见 [LICENSE](./LICENSE)。
