# system-architecture-design

> AITeamOS 系统架构设计 — 6 个 Bounded Context 的边界守护与三层逻辑架构。

## AITeamOS 架构锚点

### 三层逻辑架构（arch.md §1.1）
| 层 | 职责 | 关键组件 |
|---|---|---|
| Context/State | 上下文装配与状态管理 | Context Assembler, Memory Graph, Skill Registry, Snapshot Store |
| Driver/Execution | 任务驱动与执行 | Task State Machine, Saga Orchestrator, Cost Interceptor |
| Assertion/Validation | 验证与反思 | Harness Gateway, Callback Receiver, Reflection Engine |

**层间约束**：
- Context/State → Driver/Execution：只通过 Sealed Context Bundle（不可变快照）传递
- Driver/Execution → Assertion/Validation：只通过 DeliverableSubmitted 事件触发
- Assertion/Validation → Context/State：Reflection Engine 输出的 Memory 候选须通过 Quarantine Buffer

### 6 个 Bounded Context（arch.md §2.1）
| Context | 聚合根 | 包路径 | 唯一职责 |
|---|---|---|---|
| Knowledge | MemoryNode, MemoryEdge | `packages/knowledge/` | Memory 提炼、关系图、置信度演进 |
| Capability | Skill | `packages/capability/` | Skill 注册、版本、可分配性 |
| Workforce | Employee, Department | `packages/workforce/` | Employee 组织归属、Skill-Memory 分配 |
| Execution | Task | `packages/execution/` | Task 状态机（T0-T10）、Run、Deliverable |
| Validation | HarnessAdapter, HarnessInvocation | `packages/validation/` | 验证适配、回调、结果归一 |
| Governance | ReviewCase, ConflictCase | `packages/governance/` | 审核、冲突仲裁、归因 |

### 跨 Context 通信规则
- **禁止**跨包直接 import 仓储（纪律 #1）
- 写路径：Command → Domain Event → Outbox → Kafka
- 同步读取：ACL Bridge + 依赖倒置（如 `RecallEngineKnowledgeACL`、`SqlCapabilityACL`）
- 跨 Context 事件必须继承 `VersionedDomainEvent`，`extra='ignore'` 保向前兼容

## 设计检查清单

### 新增模块/功能时
- [ ] 该功能归属于哪个 Bounded Context？是否存在跨 Context 的聚合？
- [ ] 跨 Context 通信是否走事件 + ACL？有无直接 import？
- [ ] 新聚合根是否满足：同一事务内只修改一个聚合？
- [ ] 是否遵守 CQRS（写路径 Command + Event，读路径专用投影）？

### 依赖方向检查
- [ ] Knowledge Context 不引用 Execution 内部类型
- [ ] Capability Context 不引用 Workforce 的 Employee 细节（Skill 是独立能力标签）
- [ ] Execution Context 不直接操作 Memory Graph（通过 Context Assembler 间接获取）
- [ ] Validation Context 不感知 Task 的业务语义（只看 Deliverable）

### 存储层检查
- [ ] 关系型数据 → PostgreSQL
- [ ] 向量检索 → pgvector HNSW（`memory_embedding` 表）
- [ ] 图遍历 → Neo4j/AGE 投影（`memory_edge` CDC 同步）
- [ ] 不可变快照 → 对象存储（S3 兼容）
- [ ] 事件流 → Kafka + Outbox Pattern

### 不变量守护
- N1 快照不可变：`task_context_snapshot` 写入后只读
- N4 反思隔离：`system_meta=true` 的事件不进入 Reflection Engine
- N6 投影只进不退：`source_event_seq` 只递增，CAS 写入
- N7 资源补偿闭环：Saga 占用资源必须有对应补偿

## 输出产物
- Bounded Context 映射图（含跨 Context 事件契约）
- 模块依赖矩阵（包级别，标注同步/异步通信方式）
- 不变量检查报告（对照 arch.md §1.4 逐条确认）

## 参考
- `docs/arch.md` §0.2 — 十三条设计纪律
- `docs/arch.md` §1.1 — 三层逻辑架构
- `docs/arch.md` §2.1 — Bounded Context 划分
- `docs/arch.md` §2.3 — 混合存储矩阵
