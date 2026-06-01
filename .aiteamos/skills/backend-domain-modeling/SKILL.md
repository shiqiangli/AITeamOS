# backend-domain-modeling

> AITeamOS 后端领域建模 — DDD 聚合设计、Bounded Context 边界守护、领域事件建模。

## AITeamOS 后端领域模型锚点

### 6 个 Bounded Context 与聚合根（arch.md §2.1-2.2）
| Context | 包路径 | 聚合根 | 核心不变量 |
|---------|--------|--------|-----------|
| Knowledge | `packages/knowledge/` | `MemoryNode`, `MemoryEdge` | I-K-1~5: 置信度受控、Edge 独立聚合、quarantined 屏蔽召回 |
| Capability | `packages/capability/` | `Skill` | 版本 SemVer、status 状态机（draft→published→deprecated） |
| Workforce | `packages/workforce/` | `Member`, `Department` | base_skill_set 绑定、kind 人机同构 |
| Execution | `packages/execution/` | `Task` | 状态机（Draft→Ready→Assigned→Running→Verifying→InReview→Done/Failed） |
| Validation | `packages/validation/` | `HarnessAdapter`, `HarnessInvocation` | 回调幂等、沙箱原子性 |
| Governance | `packages/governance/` | `ReviewCase`, `ConflictCase` | verdict 迁移、冲突仲裁 |

### 包结构规范
```
packages/{context}/aiteamos_{context}/
  ├── domain/
  │   ├── __init__.py      # 聚合根 + 实体 + 值对象
  │   ├── commands.py      # Command 定义
  │   └── handlers.py      # Command Handler
  ├── application/
  │   ├── __init__.py      # CQRS 入口
  │   └── queries.py       # Query DTO（SkillSummary, SkillDetail 等）
  └── infrastructure/
      ├── __init__.py
      └── repository.py    # 聚合持久化（SQL）
```

### 聚合设计规则
1. **一个事务只修改一个聚合** — 跨聚合一致性通过领域事件实现最终一致
2. **聚合间通过 ID 引用** — 不持有对方的对象引用（如 `TaskRun.member_id` 而非 `Member` 对象）
3. **值对象不可变** — 用 `@dataclass(frozen=True)` 声明
4. **聚合根有明确的 Identity** — UUID，不使用自增 ID

### 跨 Context 通信规则
```
写路径（事件驱动）:
  Command Handler → 保存聚合 → 发布 Domain Event → Outbox 同事务写入
  → Outbox Relay → Kafka → 消费者

同步读取（ACL + 依赖倒置）:
  Context A 定义 ACL 接口 → Context B 实现 → Composition Root 注入
  例：Execution 定义 KnowledgeACL 接口 → Knowledge 实现 RecallEngineKnowledgeACL
```

**禁止**：
- 跨包直接 `import` 其他 Context 的 repository
- 跨包直接调用其他 Context 的 handler
- 在一个事务中修改多个 Context 的聚合

## 领域建模检查清单

### 新增聚合根时
- [ ] 属于哪个 Bounded Context？是否违反该 Context 的唯一职责？
- [ ] 聚合根有独立 Identity（UUID）？
- [ ] 聚合内的实体和值对象是否都通过聚合根访问？
- [ ] 聚合边界是否合理？（热门引用应拆为独立聚合，如 MemoryEdge 从 MemoryNode 拆出）
- [ ] 聚合根的状态迁移是否有明确的状态机定义？

### 新增领域事件时
- [ ] 事件是 Context 内部还是跨 Context？
- [ ] 跨 Context 事件是否继承 `VersionedDomainEvent`（含 `event_version`、`correlation_id`）？
- [ ] 事件是否携带 `global_seq`（Outbox 全局序列号）？
- [ ] 事件命名是否用过去时（`TaskCreated`、`DeliverableSubmitted`）？
- [ ] 新增可选字段保持同版本号，破坏性变更必须升 `event_version`

### Repository 实现时
- [ ] SQL 使用 asyncpg 参数化查询（`$1`, `$2`...），防注入
- [ ] UPSERT 使用 `ON CONFLICT (id) DO UPDATE`
- [ ] 行映射函数（`_row_to_aggregate`）处理所有列，不遗漏
- [ ] 事务内同时写聚合 + Outbox 事件（同事务原子性）
- [ ] JSON 字段使用 `::jsonb` 类型转换

### 值对象设计
```python
# ✅ 正确：不可变值对象
@dataclass(frozen=True)
class Confidence:
    value: Decimal          # 0.000 ~ 1.000
    state: ConfidenceState  # valid | needs_verify | deprecated
    last_updated: datetime

# ✅ 正确：枚举值对象
class SkillStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    CANCELLED = "cancelled"

# ❌ 错误：可变值对象
@dataclass
class MutableValue:
    value: str  # 值对象不应被原地修改
```

## 常见 DDD 反模式与修正

| 反模式 | 修正 |
|--------|------|
| 一个 Handler 里修改多个聚合 | 拆为多个 Command，每个只改一个聚合 |
| 聚合根暴露 setter 方法 | 通过领域方法修改（如 `task.assign(member_id)`） |
| 跨 Context 直接 JOIN 查询 | 通过 ACL Bridge 或投影到读侧专用视图 |
| 事件中包含聚合完整状态 | 事件只携带变更的 delta 和 ID |
| Repository 返回 DTO 而非聚合 | Repository 只负责聚合的持久化和恢复 |

## 参考
- `docs/arch.md` §2.1-2.2 — Bounded Context 与领域模型
- `docs/arch.md` §0.2 — 纪律 #1（DDD 边界即代码边界）、#4（CQRS）
- `packages/shared_kernel/` — 共享内核（VersionedDomainEvent 等基类）
- `packages/capability/` — Capability Context 参考实现
