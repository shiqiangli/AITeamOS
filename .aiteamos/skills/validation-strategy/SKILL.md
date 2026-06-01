# validation-strategy

> AITeamOS 验证策略 — Harness 三层体系设计与 Adapter 管理，确保非确定性 AI 输出可验证。

## AITeamOS 验证体系锚点

### Validation Context（arch.md §2.2.5）
```python
class HarnessAdapter:              # 配置型聚合根
    tier: HarnessTier              # spec | functional | system
    protocol: ProtocolKind         # sync | async
    endpoint: str
    health: AdapterHealth

class HarnessInvocation:           # 运行时聚合根
    adapter_id: AdapterId
    run_id: RunId
    deliverable_ref: str
    state: InvocationState         # pending | done | timeout | flaky | adapter_error
    callback_token: str            # 幂等键
    result: HarnessResult | None
```

### Harness 三层体系（arch.md §2.2.5, PRD §1.4）
AITeamOS 的核心命题：AI 的非确定性（幻觉）必须通过验证闭环来保证输出质量。

| Tier | 验证目标 | 同步/异步 | 典型 Adapter | 触发时机 |
|------|---------|----------|-------------|---------|
| **Spec** | 交付物是否符合规格（schema、格式、接口契约） | sync | JSON Schema Validator, OpenAPI Linter | T6a — 立即返回 |
| **Functional** | 交付物是否功能正确（测试通过、编译通过） | sync | Test Runner, Compiler, Static Analyzer | T6a — 立即返回 |
| **System** | 交付物在系统环境中是否正常（集成测试、E2E） | async | CI/CD Pipeline, Staging Deploy | T6b — 等 Callback |

### 验证流程（arch.md §1.3 T6-T7）
```
T5 DeliverableSubmitted
  → Harness Gateway 路由到对应 Adapter(s)
    → Spec Adapter (sync): Pass/Fail → 立即可用
    → Functional Adapter (sync): Pass/Fail → 立即可用
    → System Adapter (async): pending → Saga 注册 Callback
      → T7 Webhook 回调入站（HMAC 校验 + 幂等）→ HarnessResult 事件
        → 所有 Adapter Pass → InReview; 任一 Fail → Running（重试）
```

### 关键不变量
- **N3 回调幂等**：`(adapter_id, invocation_id)` 为幂等键，重复投递是 no-op
- **N5 沙箱原子性**：非 `merged` 状态的沙箱产出不得进入 `submit_deliverable`
- **纪律 #3**：系统不内建任何业务验证逻辑，一律通过 Harness Adapter 外置
- **纪律 #9**：有副作用的执行必须在沙箱中，熔断时整体回滚

## Adapter 设计检查清单

### 新增 Adapter 时
- [ ] 明确属于哪个 Tier（spec / functional / system）
- [ ] 明确 `protocol`：sync（<5s 返回）还是 async（>5s，走 Webhook）
- [ ] `auth_secret_ref` 引用 EnvVar，**不存明文**（安全约束）
- [ ] 实现了幂等回调（async 类型必须有 `callback_token`）
- [ ] Adapter 端点的 health check 已接入 `AdapterHealth` 监控
- [ ] Adapter 返回的 `HarnessResult` 格式统一（pass/fail + evidence_ref）

### Adapter 路由规则
- Spec Tier：每个 Deliverable 必经（自动路由，无需配置）
- Functional Tier：按 Skill 类型路由（如 `backend-api-implementation` → Test Runner）
- System Tier：仅高优任务或跨 Context 变更时触发

### Adapter 健康监控
- [ ] Adapter 端点可用性 > 99.5%
- [ ] sync Adapter P95 < 5s
- [ ] async Adapter Callback 入站 P99 < 200ms（arch.md §1.2）
- [ ] Flaky 检测：同一 Adapter 对同一 Deliverable 多次结果不一致 → 标记 `flaky`

## 验证覆盖策略

### 按 Task 类型配置验证链
| Task 类型 | Spec Adapter | Functional Adapter | System Adapter |
|-----------|-------------|-------------------|---------------|
| 后端 API 开发 | OpenAPI Schema | pytest + coverage | CI Pipeline (async) |
| 前端组件开发 | TypeScript 编译 | Playwright E2E | Staging Deploy (async) |
| 数据库迁移 | SQL 语法检查 | Migration Dry Run | Staging Apply (async) |
| 文档编写 | Markdown Linter | — | — |
| 架构设计 | — | — | — (人审) |

### 验证失败处理
1. **Spec Fail** → 直接打回 Running，无需 Saga 补偿
2. **Functional Fail** → 打回 Running，附带失败日志（`evidence_ref`）
3. **System Fail** → 打回 Running，Saga 触发补偿（释放沙箱、恢复并发槽位）
4. **Adapter Error** → 不惩罚 Member，排队重试或升级给人工

## 参考
- `docs/arch.md` §2.2.5 — Validation Context
- `docs/arch.md` §1.3 — T6-T7 验证阶段
- `docs/arch.md` §0.2 — 纪律 #3（真理源外置）、#9（补偿优先）
- `packages/validation/` — Validation Context 代码包
