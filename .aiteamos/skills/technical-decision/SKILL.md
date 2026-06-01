# technical-decision

> AITeamOS 技术决策 — 已采纳技术方案的 ADR 管理、选型评估与架构规范制定。

## AITeamOS 已有技术决策基线

### 已确定的技术选型
| 决策 | 选型 | 理由 | 参考 |
|------|------|------|------|
| 主存储 | PostgreSQL | 强事务、JSONB 灵活、pgvector 扩展 | arch.md §2.3 |
| 向量检索 | pgvector (HNSW) | P95 < 200ms、增量插入无需 REINDEX | arch.md §2.3 |
| 图存储 | Neo4j / Apache AGE | 多跳遍历（级联失效 BFS）、CDC 投影 | arch.md §2.3 |
| 事件总线 | Kafka + Outbox Pattern | 顺序保障 + At-least-once + Replay | arch.md §2.3 |
| Saga 编排 | Temporal / Cadence | Durable Timer、Signal 原语、补偿栈 | arch.md §2.3 |
| API 框架 | FastAPI | 异步原生、OpenAPI 自动生成 | 项目技术栈 |
| 前端框架 | React + Vite + TypeScript | 热重载、类型安全 | 项目技术栈 |
| DDD 实现 | CQRS + Outbox + ACL | 读写分离、事件原子性、跨 Context 隔离 | arch.md §0.2 |

### 已确定的架构模式
| 模式 | AITeamOS 中的应用 |
|------|-------------------|
| Bounded Context | 6 个独立 Python 包，跨包仅通过事件 + ACL |
| CQRS | 写路径 Command + Domain Event → Outbox；读路径专用投影 |
| Outbox Pattern | 主聚合事务与领域事件同事务原子写入 |
| Saga + Compensation | Task 执行链路的资源占用与补偿栈管理 |
| ACL Bridge | `RecallEngineKnowledgeACL`、`SqlCapabilityACL` 隔离跨 Context 读取 |
| Immutable Snapshot | Task 上下文快照写入后只读，反思阶段基于快照 |
| Idempotent Projection | 所有投影消费者基于 `source_event_seq` CAS 写入 |

### 已确定的关键约束
- **双加载模式**：Memory 走图+关系混合存储，Skill 走 Registry，二者绝不共聚合
- **知识图谱强制约束**：Memory 关系必须投影到图存储（Neo4j/AGE）
- **元递归隔离**：`system_meta=true` 的事件被 DB Trigger 硬性阻断进入 Memory
- **预算硬约束**：Token/时长/召回上限在 Interceptor 入口拦截，不依赖软提示
- **失败优先**：安全/治理决策不确定时默认拒绝

## ADR 管理流程

### ADR 生命周期
```
Proposed → Accepted → [Deprecated → Superseded by ADR-NNN]
```

### 新 ADR 触发条件
- 引入新的外部依赖（数据库、消息队列、SDK）
- 变更跨 Context 通信模式（同步 ↔ 异步）
- 修改存储策略（新增表、变更索引策略）
- 调整不变量（N1-N8）的保护机制

### ADR 必须包含的 AITeamOS 特有章节
```markdown
# ADR-{NNN}: {Title}

## Status
Accepted | Deprecated | Superseded by ADR-{NNN}

## Context
描述驱动该决策的 AITeamOS 具体场景（引用 arch.md 章节）。

## Decision
描述最终决策。

## Consequences
- 对 6 个 Bounded Context 的影响：...
- 对不变量 N1-N8 的影响：...
- 对存储矩阵（§2.3）的影响：...

## Alternatives Considered
| 方案 | 优点 | 缺点 | 未选择原因 |
|------|------|------|-----------|

## Revisit Trigger
什么条件下需要重新评估该决策（如：Memory 总量超过 X 条时重新评估 pgvector 方案）。
```

## 架构规范制定

### 编码规范（基于 AITeamOS 实际约束）
- 跨 Context 通信只允许通过 `acl_bridges.py` 和领域事件
- Command Handler 必须通过 `tx_manager.transaction()` 包裹聚合保存和事件发布
- 投影消费者必须继承 `IdempotentProjectionConsumer` 基类
- Skill 表只存元数据，程序性上下文走 `.aiteamos/skills/{name}/SKILL.md`

### 接口契约规范
- 跨 Context 事件必须继承 `VersionedDomainEvent`（含 `event_version`、`correlation_id`）
- 新增可选字段：同版本号，`extra='ignore'` 自动兼容
- 破坏性变更：必须升 `event_version`，旧消费者通过版本分派器处理

### 测试规范
- 每个不变量（N1-N8）必须有对应的集成测试
- Saga 补偿路径必须有混沌测试（模拟中途失败后补偿正确性）
- 幂等投影必须有重复事件投递测试

## 输出产物
- ADR 文档集（按编号归档，存放位置待定）
- 技术选型评估矩阵（含 AITeamOS 特有维度：对 Bounded Context 的影响、对不变量的影响）
- 架构规范文档（编码/接口/测试三方面）

## 参考
- `docs/arch.md` §0.2 — 十三条设计纪律（决策必须遵守）
- `docs/arch.md` §2.3 — 混合存储矩阵（选型基线）
- `packages/shared_kernel/aiteamos_shared/events.py` — `VersionedDomainEvent` 基类
