# test-engineering

> AITeamOS 测试工程 — 基于 arch.md 不变量的测试设计、幂等投影验证、Saga 补偿混沌测试。

## AITeamOS 测试体系锚点

### 测试分层（对应 Harness 三层）
| 测试层 | 对应 Harness Tier | 执行环境 | 自动化程度 |
|--------|------------------|---------|-----------|
| 单元测试 | — | `tests/` 目录 + pytest | 100% 自动 |
| 不变量测试 | Spec | `tests/` 目录 + pytest | 100% 自动 |
| 集成测试 | Functional | `tests/integration/` | 100% 自动 |
| 混沌测试 | System | 专用测试环境 | 半自动 |

### 不变量测试矩阵（arch.md §1.4 — 必须覆盖）

| 不变量 | 测试场景 | 测试方法 |
|--------|---------|---------|
| **N1 快照不可变** | T3 写入快照后，T4-T10 不能修改 | 尝试 UPDATE `task_context_snapshot`，断言被拒绝 |
| **N2 事件单调** | 同一 `run_id` 内 `run_event.seq` 严格递增 | 并发写入 run_event，验证 seq 无重复无回退 |
| **N3 回调幂等** | 重复 Webhook 投递不产生重复处理 | 同一 `(adapter_id, invocation_id)` 投递两次，验证 `webhook_inbox` UNIQUE 约束生效 |
| **N4 反思隔离** | `system_meta=true` 的事件不进入 Reflection Engine | 发布 system_meta 事件，验证 Reflection 输入流不含该事件 |
| **N5 沙箱原子性** | 非 `merged` 沙箱的产出不能提交 Deliverable | 在 `active` 状态沙箱中尝试 submit_deliverable，断言被拒绝 |
| **N6 投影只进不退** | `source_event_seq` 只递增 | 模拟乱序事件投递，验证 `source_event_seq < EXCLUDED.source_event_seq` WHERE 条件 |
| **N7 资源补偿闭环** | Saga 终态时补偿栈为空 | 正常/异常/取消三种路径都验证补偿栈清空 |
| **N8 DB-Saga 一致** | DB 记录 GC 不先于 Saga 终态 | 模拟 `harness_invocation` 过期，验证 Saga 先转终态再 GC |

### 幂等投影测试（arch.md §2.3）
投影消费者继承 `IdempotentProjectionConsumer`，必须测试：

```python
# 测试模板：幂等投影
async def test_pgvector_projection_idempotent(conn, sample_event):
    """同一事件投递两次，embedding 只写入一次"""
    projection = PgvectorProjection(conn)

    # 第一次投递
    await projection.process(sample_event)
    row1 = await conn.fetchrow("SELECT source_event_seq FROM memory_embedding WHERE memory_id = $1", sample_event.memory_id)

    # 第二次投递（同一 global_seq）
    await projection.process(sample_event)
    row2 = await conn.fetchrow("SELECT source_event_seq FROM memory_embedding WHERE memory_id = $1", sample_event.memory_id)

    assert row1["source_event_seq"] == row2["source_event_seq"]  # 水位未变

async def test_pgvector_projection_no_rollback(conn, event_seq_10, event_seq_5):
    """低序号事件不能覆盖高序号事件"""
    projection = PgvectorProjection(conn)
    await projection.process(event_seq_10)
    await projection.process(event_seq_5)  # 乱序到达

    row = await conn.fetchrow("SELECT source_event_seq FROM memory_embedding WHERE memory_id = $1", event_seq_10.memory_id)
    assert row["source_event_seq"] == 10  # 保持高水位
```

### Saga 补偿测试（arch.md §3.5）
```python
# 测试模板：Saga 补偿
async def test_saga_compensation_on_employee_failure(saga_client):
    """Employee 执行失败时，补偿栈正确释放"""
    workflow = await saga_client.start_task_workflow(task_id, employee_id)

    # 模拟 Employee 执行异常
    await saga_client.signal_failure(workflow.id, "employee_crash")

    # 等待补偿完成
    result = await saga_client.wait_terminal(workflow.id, timeout=30)

    assert result.status == "Failed"
    assert result.compensation_stack == []  # N7: 补偿栈清空
    assert result.employee_concurrency_released == True
    assert result.sandbox_destroyed == True
```

### 混沌测试场景
| 场景 | 注入方式 | 预期行为 |
|------|---------|---------|
| Kafka 分区 leader 切换 | 重启 Kafka broker | Outbox Relay 自动重连，事件不丢失 |
| Neo4j 网络抖动 | 网络 partition 5s | Recall Engine graph 通道降级，其余通道补充 |
| 数据库主从切换 | 触发 pg_failover | 写路径短暂阻塞，CQRS 读侧继续服务 |
| Saga Engine 重启 | kill + restart Temporal | Workflow 从持久化状态恢复执行 |
| 全部召回通道降级 | 同时阻断 4 个通道 | 召回为空，Task 仍可执行（告警但不阻塞） |

## 测试检查清单

### 每个 Bounded Context 的测试
- [ ] Knowledge: Memory 置信度衰减公式验证（Facts λ=0, Patterns λ=1/180d, Principles λ=1/365d）
- [ ] Knowledge: 级联失效 BFS 深度上限 3、扇出上限 200
- [ ] Capability: Skill 版本 SemVer 解析和比较
- [ ] Workforce: Employee 并发上限校验（当前并发 < concurrency_limit）
- [ ] Execution: Task 状态机迁移合法性（Draft→Ready→Assigned→Running→Verifying→InReview→Done）
- [ ] Validation: Webhook 回调幂等（UNIQUE 约束 + HMAC 校验）
- [ ] Governance: ReviewCase verdict 迁移（approve/reject/merge/revise）

### 跨 Context 集成测试
- [ ] Outbox → Kafka → 投影全链路（事件不丢失、不重复）
- [ ] Context Assembler 装配（Memory 召回 + Skill 解析 + 预算裁剪）
- [ ] Reflection Engine 全流程（Snapshot → Memory 候选 → Quarantine → 审核）

### 性能基线
- [ ] Context Assembler P95 < 800ms（含 Memory 召回）
- [ ] Cost Interceptor 拦截开销 < 5ms
- [ ] 异步回调入站 P99 < 200ms

## 参考
- `docs/arch.md` §1.4 — 8 个不变量（N1-N8）
- `docs/arch.md` §2.3 — 幂等投影消费者基类
- `docs/arch.md` §3.5 — Saga 补偿链
- `tests/` — 测试目录
- `tests/integration/` — 集成测试目录
