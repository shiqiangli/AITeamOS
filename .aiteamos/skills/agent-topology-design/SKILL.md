# agent-topology-design

> AITeamOS Agent 协作拓扑 — Employee/Skill/Memory 的分配模型与 Task 路由机制。

## AITeamOS Agent 协作锚点

### 核心模型关系
```
Employee (kind: ai | human)
  ├── base_skill_set: list[SkillId]      ← 角色身份（持久绑定）
  ├── assigned_memories: list[MemoryId]  ← 知识范围（软性偏好）
  └── concurrency_limit: int             ← 执行容量
```

**Skill 是角色的能力标签**（`packages/capability/`），通过 `base_skill_set` 绑定到 Employee。
**Memory 是角色的知识积累**（`packages/knowledge/`），通过 `assigned_memories` 分配给 Employee。
**两者绝不在同一聚合内耦合**（纪律 #2）。

### Task 生命周期中的 Agent 协作（arch.md §1.3）
| 阶段 | 参与者 | Agent 协作行为 |
|---|---|---|
| T2 分配 | PM/Auto-Router | 基于 `declared_skills` ∩ Employee.`base_skill_set` 匹配；并发上限校验 |
| T3 装配 | Context Assembler | 从 Knowledge（Memory 召回）+ Capability（Skill 解析）+ Workforce（Profile）装配 Sealed Bundle |
| T4 执行 | Employee Runtime | 装载 Skill+Memory Bundle；Cost Interceptor 全程计量 token/时长 |
| T5 提交 | Employee → Harness | 提交 Deliverable，触发验证链 |
| T8 审核 | Reviewer Employee | 结构化 Review（decision + reason + correction） |
| T9 反思 | Reflection Engine | 基于 Snapshot + Run + Result 抽取 Memory 候选 → Quarantine → 审核 |

### Context Assembler 装配流程
```
Task → ContextAssembler.assemble()
  ├── Knowledge ACL: RecallEngine.top_k(snapshot, query) → Memory 列表
  ├── Capability ACL: SqlCapabilityACL.get_skill_bundle(skill_ids) → Skill 元数据
  ├── Workforce: Employee profile + base_skill_set + assigned_memories
  └── Budget Controller: token/时长/召回上限预检
  → Sealed Context Bundle（不可变快照，写入 snapshot_store）
```

### Saga 编排与补偿（arch.md §3.5）
Task 执行涉及多个资源占用，Saga Workflow 必须管理补偿栈：
- Employee concurrency 占用 → 补偿释放
- Sandbox 创建 → 补偿销毁
- Skill bundle 锁定 → 补偿解锁
- Outbox half-commit → 补偿回滚

**不变量 N7**：Workflow 终态时补偿栈必须为空，含残留即资源泄漏。

## 设计检查清单

### Skill-Memory 分配
- [ ] Employee 的 `base_skill_set` 是否覆盖其所有任务类型的 `declared_skills`？
- [ ] 是否存在冗余 Skill 分配（Employee 拥有 Skill 但其任务从不使用）？
- [ ] `assigned_memories` 的 scope 是否与 Employee 的 Department/Project 匹配？
- [ ] Skill 是否只分配给了真正需要的角色（最小权限原则）？

### Task 路由
- [ ] 每个 Task 的 `declared_skills` 是否至少有一个 Employee 的 `base_skill_set` 能覆盖？
- [ ] 并发上限是否合理（AI 受执行节点约束，Human 受时间约束）？
- [ ] 任务分解策略是否明确（子任务的 parent_task_id 和依赖关系）？

### 协作拓扑健康度
- [ ] 是否存在单点 Agent（唯一拥有某个 Skill 的 Employee，且无 backup）？
- [ ] Department 的 `leader_employee_id` 和 `backup_leader_employee_id` 是否都设置？
- [ ] Context Assembler 装配耗时是否在 P95 < 800ms 以内？
- [ ] Saga 补偿栈在所有正常/异常路径下都能正确释放？

### 人机同构（纪律 #2）
- [ ] AI Employee 和 Human Employee 是否共用同一个领域模型（`Employee.kind` 区分）？
- [ ] 执行差异是否下沉到 Adapter 层而非混入领域逻辑？
- [ ] Human Employee 的 `concurrency_limit` 是否基于时间而非执行节点？

## 输出产物
- Agent 协作拓扑图（Employee → Skill/Memory 映射 + 通信路径）
- Task 路由规则表（Task.declared_skills → 候选 Employee 列表）
- Skill-Memory 分配矩阵（每个 Employee 的能力集和知识集）
- Saga 补偿栈清单（每个 Workflow 的资源占用与对应补偿）

## 参考
- `docs/arch.md` §1.3 — Task 完整生命周期（T0-T10）
- `docs/arch.md` §2.2.3 — Workforce Context（Employee, Department）
- `docs/arch.md` §2.2.4 — Execution Context（Task, TaskRun）
- `docs/arch.md` §3.5 — Saga 补偿链
- `services/api/aiteamos_api/acl_bridges.py` — ACL 实现
