# AITeamOS

> **把 AI 当作长期同事来管理的团队操作系统。**

AITeamOS 是一个面向工程团队的 AI 协作管理平台。它让人类工程师和 AI 数字员工共享统一的身份、任务、权限、记忆与审查体系——像管理一支真实团队一样管理你的 AI 同事。

---

## 为什么需要 AITeamOS

当前的 AI 编程工具围绕"一次会话"设计，每次都要重新交代背景、重新把控质量。当你想让 AI 真正融入团队日常时：

| 痛点 | AITeamOS 的解法 |
|------|----------------|
| AI 没有持久身份，换会话就失忆 | 长期存在的 TeamMember，积累技能、记忆与工作履历 |
| 缺少统一的任务分派和产出审查 | 任务 → 运行 → 审查闭环，人机共用一套流程 |
| AI 行为无边界、无审计 | allow / ask / deny 三态权限引擎 + 全链路决策审计 |
| 团队知识散落各处 | 中立记忆体系，按 ACL 精确投影到人/项目/任务 |
| 多 IDE、多模型无法统一治理 | 模型无关，Cursor / VSCode / Codex / Qoder / 任何 LLM 统一接入 |

---

## 核心特性

- **统一成员目录** — human / digital / hybrid / service 四种角色，共享档案、技能、活动、成长记录
- **项目化协作** — 仓库、模块、Assignment、任务、运行、审查、知识健康度，一站管理
- **中立团队记忆** — store → entry → binding → grant，带 ACL、生命周期与审计；不会悄悄注入过期/冲突内容
- **任务-运行-审查闭环** — 每次执行产生可追溯的 context capsule、diff/PR、日志与记忆提议
- **Review-First 安全模型** — Worker 隔离执行，所有产出必须通过审查；Secret 永不进入 prompt/log/界面
- **自动化控制面** — webhook、定时任务、CI 事件先落审批门，再决定执行
- **三种执行模式** — Managed（托管执行）/ Assisted IDE（接收 IDE 产出）/ Manual（人工登记）

---

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 20+（Dashboard 构建）
- Git

### 一键启动

```bash
# 1. 克隆项目
git clone https://github.com/your-org/AITeamOS.git && cd AITeamOS

# 2. 校验工作区协议
./aiteamos workspace validate --workspace .aiteamos

# 3. 重建派生索引（SQLite + 向量索引，可重建的缓存）
./aiteamos workspace index --workspace .aiteamos

# 4. 构建 Dashboard
cd apps/dashboard && npm install && npm run build && cd ../..

# 5. 启动 API + Dashboard
./aiteamos serve --workspace .aiteamos
```

打开 **http://127.0.0.1:8765** 即可进入 Dashboard。

### 启用模型调用（可选）

```bash
export OPENAI_API_KEY=sk-...
./aiteamos serve --workspace .aiteamos
```

Dashboard 会按 Model Profile 配置自动路由模型调用，结果写回 run journal。Secret 永远不会显示在界面上。

---

## 三种工作模式

| 模式 | 适合场景 | AITeamOS 的角色 |
|------|---------|----------------|
| **Managed** | 全自动执行 + 严格审查 | 创建隔离 worktree、调用模型、生成 diff/PR、登记 review |
| **Assisted IDE** | 你在 IDE 里写代码 | 准备 context capsule、接收 ingest 后走审查流程 |
| **Manual** | 人工完成的工作 | 登记 task/run、关联评审目标、沉淀记忆提议 |

---

## 工作区（Workspace）

AITeamOS 把所有可追溯的协作数据存储在 `.aiteamos/` 目录中。

### 两种部署形态

| 形态 | 说明 | 推荐场景 |
|------|------|---------|
| **Embedded** | `.aiteamos/` 直接放在源码仓库根目录 | 开源项目、demo、个人自托管 |
| **Shadow** | 独立仓库 `<project>-aiteamos-shadow/` 存放 `.aiteamos/`，通过 `repositories/` 引用源码仓库 | **私有/商业项目**（避免成员档案、记忆、运行历史泄漏到源码仓库） |

### 数据分层

```
.aiteamos/                  ← Source of Truth（入 Git）
├── members/                ← 成员定义
├── assignments/            ← 任务分配
├── tasks/ & runs/          ← 任务与运行记录
├── memory/                 ← 团队记忆
├── permissions/            ← 权限策略
├── reviews/                ← 审查记录
├── automations/            ← 自动化配置
├── project.yaml            ← 项目配置
├── workspace.yaml          ← 工作区配置
└── indexes/                ← 🚫 派生缓存（.gitignore 排除）
    ├── aiteamos.sqlite     ← 可重建的 SQLite 投影
    └── vector_*.json       ← 可重建的向量索引
```

> **核心原则：** `.aiteamos/` YAML 文件是 source of truth。SQLite、向量索引、Dashboard 缓存全部是可重建的派生状态。

### 重建派生数据

当你从远程拉取代码、还原备份或清理缓存后，只需一条命令重建所有派生状态：

```bash
./aiteamos workspace index --workspace .aiteamos
```

---

## 安全边界

AITeamOS 默认 **Review-First**，遵循最小权限原则：

- Worker 只能在隔离 worktree/分支中操作，patch 逐路径审批
- 不会自动合并 PR、批准记忆或修改治理面
- Secret 值通过环境变量传递，永不进入 prompt、log、Dashboard 或 export 包
- 非交互模式下 `ask` 权限自动转 `deny`
- 跨成员的记忆共享必须通过有时限的 grant + 审计记录

---

## 项目结构

```
AITeamOS/
├── .aiteamos/              # 工作区数据（Source of Truth）
├── apps/dashboard/         # Web Dashboard（React + Vite）
├── packages/
│   ├── schema/             # Pydantic 模型 → JSON Schema → TypeScript 类型
│   ├── workspace/          # 工作区加载、校验、索引
│   └── connectors/         # 连接器注册表与适配器
├── services/
│   ├── api/                # FastAPI 服务（HTTP + MCP）
│   └── worker/             # 受管 Worker 进程
├── tools/cli/              # 极薄 CLI 入口
├── extensions/             # VSCode/Cursor 扩展
├── docs/                   # 架构与部署文档
├── tests/                  # 测试套件
└── aiteamos                # Shell 入口脚本
```

---

## 面向开发者

### 自举（Self-Bootstrapping）

本仓库自身使用 embedded `.aiteamos/` 工作区来管理 AITeamOS 的开发——这意味着 AITeamOS 用自己来管理自己的开发团队。Worker 可以推进 `aiteamos-architecture`、`aiteamos-backend-runtime`、`aiteamos-dashboard` 等 assignment，但不能无审查地修改自己的治理规则、安全边界或生产部署配置。

### 影子工作区（Shadow Workspace）

对于私有项目，推荐单独建仓存放 `.aiteamos/`：

```bash
# 源码仓库不包含 .aiteamos/
my-project/
  └── src/ ...

# 独立的影子仓库
my-project-aiteamos-shadow/
  └── .aiteamos/
      ├── repositories/aiteamos.yaml   ← 引用源码仓库
      ├── members/
      └── ...
```

这样源码仓库保持干净，协作数据独立管理与审计。

### CLI 速查

```bash
./aiteamos serve --workspace .aiteamos          # 启动 API + Dashboard
./aiteamos workspace validate --workspace .aiteamos  # 校验清单
./aiteamos workspace index --workspace .aiteamos     # 重建索引
./aiteamos worker --workspace .aiteamos              # 启动 Worker
./aiteamos schema export                             # 重新生成 Schema
```

### 技术栈

- **后端：** Python 3.11+ / FastAPI / Pydantic / SQLite / LiteLLM
- **前端：** React / Vite / TypeScript
- **协议：** YAML manifests → JSON Schema → OpenAPI → TypeScript types
- **模型：** 通过 LiteLLM 网关支持 OpenAI / Anthropic / Gemini / 本地模型

---

## 当前状态

AITeamOS 的第一切片是 **UI-first、协议优先、CLI 极薄**。Dashboard + API + Workspace 校验已可用，受管 Worker 支持隔离执行与 diff 校验。

整体仍处于活跃迭代中。终态语义以 [`docs/architecture.md`](./docs/architecture.md) 为准。

---

## License

见 [LICENSE](./LICENSE)。
