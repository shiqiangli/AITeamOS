# resource-planning

> AITeamOS 资源规划 — Employee 分配策略、Skill-Memory 匹配、并发容量管理。

## AITeamOS 资源模型锚点

### Workforce Context（arch.md §2.2.3）
```python
class Employee:
    kind: EmployeeKind              # ai | human
    department_id: DepartmentId   # 组织归属
    base_skill_set: list[SkillId] # 能力集
    assigned_memories: list[MemoryId]  # 知识分配
    concurrency_limit: int        # AI: 执行节点约束; Human: 时间约束

class Department:
    leader_employee_id: EmployeeId | None
    backup_leader_employee_id: EmployeeId | None  # 负责人不可用时的备选
```

### Task 分配流程（arch.md §1.3 T2）
```
Task.declared_skills ∩ Employee.base_skill_set ≠ ∅  → 候选 Employee
候选 Employee 中按以下优先级排序：
  1. Skill 完全覆盖 > 部分覆盖
  2. assigned_memories 与 Task.declared_memory_hints 重合度高
  3. 当前并发数 < concurrency_limit
  4. 历史任务成功率（通过 Memory 反馈推断）
```

### 人机同构约束（arch.md §0.2 纪律 #2）
- AI 和 Human 共用同一个 `Employee` 领域模型，通过 `kind` 区分
- 执行差异下沉到 Adapter 层（AI → LLM Runtime；Human → 通知/审批流）
- `concurrency_limit` 语义不同：AI = 并行执行槽位；Human = 可承担任务数

## 资源规划检查清单

### Employee 能力覆盖
- [ ] 每个 Department 至少有 1 个 AI Employee 和 1 个 Human Employee（Human 做审核）
- [ ] 每个 Department 的 `leader_employee_id` 和 `backup_leader_employee_id` 都已设置
- [ ] 每个 Skill 至少有 2 个 Employee 持有（避免单点 Agent）
- [ ] Human Employee 必须持有 `review` 类 Skill（审核是人的核心职责）

### 容量规划
- [ ] AI Employee 的 `concurrency_limit` 是否匹配执行节点资源（通常 3-5）
- [ ] Human Employee 的 `concurrency_limit` 是否合理（通常 2-3，含审核任务）
- [ ] 高优任务（P0/P1）是否有专用 Employee 或预留容量？
- [ ] 是否监控了 Employee 的实际并发数 vs 上限？

### Memory 分配策略
- [ ] 新 Employee 入职时：分配 Department 级 Memory（scope=department）+ 项目级 Memory（scope=project）
- [ ] 专项任务前：通过 `declared_memory_hints` 提示 Context Assembler 召回特定 Memory
- [ ] 关键成员离职：其 Memory 已通过 Review 过程固化为系统 Memory，不随人走
- [ ] Memory 分配遵循最小权限：只分配与 Employee 职责相关的 Memory

### 团队扩展规划
- [ ] 新增 Bounded Context 功能时，是否同步规划了对应 Skill 和持有 Employee？
- [ ] 新增 Department 时，是否规划了 leader + backup？
- [ ] Human-to-AI 转型路径：哪些 Human 任务可以逐步交给 AI？

## 常见场景与操作

### 场景 1：新 AI Employee 上岗
1. 创建 Employee（kind=ai）→ 指定 department_id
2. 分配 `base_skill_set`（从已有 published Skill 中选择）
3. 分配 `assigned_memories`（Department scope + Project scope 的 active Memory）
4. 设置 `concurrency_limit`（初始 3，根据执行节点资源调整）
5. 创建 1-2 个低优先级 Task 验证 Skill-Memory 匹配度

### 场景 2：关键 Employee 不可用
1. 检查该 Employee 当前持有的 Skill 是否有其他 Employee 覆盖
2. 若无覆盖：临时分配 Skill 给其他 Employee
3. 将该 Employee 的活跃 Task 重新分配给其他可用 Employee
4. 更新 Department 的 `leader_employee_id` / `backup_leader_employee_id`

### 场景 3：Skill 缺口识别
1. 检查所有 Task 的 `declared_skills`，统计每种 Skill 的需求频次
2. 检查每个 Skill 的持有 Employee 数量
3. 需求频次高但持有者少 → Skill 缺口 → 注册新 Skill 或培训更多 Employee

## 参考
- `docs/arch.md` §2.2.3 — Workforce Context（Employee, Department）
- `docs/arch.md` §1.3 — Task T2 分配阶段
- `packages/workforce/` — Workforce Context 代码包
