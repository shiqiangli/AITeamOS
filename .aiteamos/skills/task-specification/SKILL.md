# task-specification

> AITeamOS Task 规格定义 — 将 PRD 需求分解为结构化 Task，声明 Skill 依赖、交付物规格和预算约束。

## AITeamOS Task 模型锚点

### Task 聚合根（arch.md §2.2.4）
```python
class Task:
    id: TaskId                    # TASK-YYYYMMDDTHHMMSSmmm-XXXX
    department_id: DepartmentId   # 必须 — 组织归属
    project_ids: list[ProjectId]  # 0..N — 项目关联
    parent_task_id: TaskId | None # 子任务层级
    state: TaskState              # Draft→Ready→Assigned→Running→Verifying→InReview→Done|Failed
    priority: Priority            # P0 | P1 | P2 | P3
    deliverable_spec: DeliverableSpec  # 交付物规格（PR 链接/文档 URI/设计稿 URI）
    declared_skills: list[SkillId]     # 所需 Skill 列表
    declared_memory_hints: list[MemoryId]  # 推荐的 Memory 提示
    budget: TaskBudget            # Token/时长/重试上限
    dependencies: list[TaskDependency]  # 任务间依赖
```

### Task 生命周期（arch.md §1.3）
| 阶段 | 触发者 | PM 关注点 |
|------|--------|----------|
| T0 创建 | **PM** | 创建 Task，填写完整规格 |
| T1 就绪 | Admin/PM | 信息完备校验：department_id + declared_skills + deliverable_spec 非空 |
| T2 分配 | **PM**/Auto-Router | 选择 Employee（基于 Skill+Memory 匹配度） |
| T8 审核 | Reviewer | PM 可作为 Reviewer 验收交付物是否符合 deliverable_spec |

### 核心公式（PRD §1.4）
$$\text{Capability} = \text{Skill (How to do)} \times \text{Memory (What we know)}$$

Task 的 `declared_skills` 定义"需要什么能力"，Context Assembler 在 T3 装配时召回匹配的 Memory。

## Task 创建检查清单

### 必填字段
- [ ] `department_id`：Task 归属哪个部门（如 Architecture / Engineering）
- [ ] `priority`：P0（阻塞）/ P1（紧急）/ P2（正常）/ P3（低优）
- [ ] `deliverable_spec`：交付物的可验证描述（不是"做好"，而是"产出 PR + 通过 CI + 覆盖测试"）
- [ ] `declared_skills`：完成该 Task 需要的 Skill ID 列表

### Skill 声明规则
- 每个 Skill 必须在 `skill` 表中存在且 `status=published`
- Skill 数量控制在 1-5 个（过多说明 Task 应该拆分）
- 至少有一个 Employee 的 `base_skill_set` 能覆盖全部 declared_skills
- 前后端分离的 Task 应拆为两个子 Task（前端 Skill vs 后端 Skill）

### 预算设定
- `token_budget`：基于 Task 复杂度估算（简单修复 ~2K，新功能 ~20K，复杂重构 ~50K）
- `max_retries`：默认 3，涉及外部 API 的可适当放宽
- `timeout_minutes`：简单任务 30min，复杂任务 4h，超长任务 24h

### 任务分解策略
- **功能拆分**：一个大 Feature → 多个子 Task（`parent_task_id` 关联）
- **前后端拆分**：API 变更 + UI 变更应作为两个子 Task，通过 `dependencies` 关联
- **验证前置**：复杂 Task 先创建一个"设计方案"子 Task，审核通过后再执行

## 质量守护

### 避免常见问题
| 反模式 | 正确做法 |
|--------|---------|
| declared_skills 为空 | 至少声明 1 个核心 Skill |
| deliverable_spec 写"完成 XX 功能" | 写可验证标准："PR 合并 + CI 通过 + 覆盖率 > 80%" |
| 单个 Task 包含 10+ 个 Skill | 拆分为多个子 Task |
| 没有设置 budget | 至少设置 timeout_minutes |
| Task 依赖形成环 | 依赖关系必须是 DAG |

### PRD → Task 映射规则
1. 每个 PRD 用户场景至少对应 1 个验收 Task
2. PRD 中的"非功能需求"（性能、安全）应单独建 Task
3. PRD 中的技术约束引用 arch.md 对应章节

## 参考
- `docs/arch.md` §1.3 — Task 完整生命周期（T0-T10）
- `docs/arch.md` §2.2.4 — Execution Context（Task 聚合根）
- `docs/arch.md` §3.3 — Task Budget 约束
- `docs/PRD-core.md` — 产品需求文档
