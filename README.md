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

### 环境要求

- Python 3.11+
- Node.js 18+
- Docker（用于 PostgreSQL）

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
