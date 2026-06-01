# architecture-review

> AITeamOS 架构评审 — 对照 arch.md 设计纪律和不变量，评估系统架构合规性。

## AITeamOS 评审基准

### 十三条设计纪律快速检查（arch.md §0.2）
| # | 纪律 | 评审问题 |
|---|------|---------|
| 1 | DDD 边界即代码边界 | 6 个 Python 包之间是否存在跨包直接 import 仓储？ |
| 2 | 状态/能力分离 | Memory 与 Skill 是否共表或共聚合根？ |
| 3 | 真理源外置 | 系统是否内建了业务验证逻辑（应通过 Harness Adapter）？ |
| 4 | 事件驱动 + CQRS | 写路径是否走 Command + Event？读路径是否走投影？ |
| 5 | 预算硬约束 | Token/时长/召回上限是否在 Interceptor 入口拦截？ |
| 6 | 元递归隔离 | `system_meta=true` 的活动是否被 DB Trigger 阻断写入 Memory？ |
| 7 | 不可变快照 | Reflection 阶段是否读取快照而非实时图？ |
| 8 | 失败优先 | 安全/治理决策的不确定结果是否默认拒绝？ |
| 9 | 补偿优先 | 有副作用的执行是否在沙箱中？熔断时是否整体回滚？ |
| 10 | 幂等投影 | 投影消费者是否基于 `source_event_seq` CAS 写入？ |
| 11 | Saga 补偿链强制 | 分布式 Workflow 是否声明了 Compensation Activity 栈？ |
| 12 | 基础设施 SPOF 零容忍 | Outbox Relay / Sandbox Pool 等是否分片+多实例？ |
| 13 | DB-Saga 状态零分裂 | 可过期 DB 记录的 GC 是否先驱动 Saga 转终态？ |

### 8 个不变量逐项验证（arch.md §1.4）
| 不变量 | 验证方法 |
|--------|---------|
| N1 快照不可变 | 检查 `task_context_snapshot` 表是否存在 UPDATE 操作 |
| N2 事件单调 | 检查 `run_event.seq` 在同一 `run_id` 内是否严格递增 |
| N3 回调幂等 | 检查 `webhook_inbox` 的 UNIQUE 约束是否生效 |
| N4 反思隔离 | 检查 Reflection Engine 输入流是否过滤了 `system_meta=true` |
| N5 沙箱原子性 | 检查沙箱 `state` 是否只有 `active → merged/destroyed` 单向转换 |
| N6 投影只进不退 | 检查投影消费者的 `source_event_seq` 是否只递增 |
| N7 资源补偿闭环 | 检查 Saga Workflow 终态时补偿栈是否为空 |
| N8 DB-Saga 一致 | 检查 `harness_invocation` 的 GC 是否先驱动 Saga 转终态 |

### 跨 Context 依赖健康度
- Knowledge → Execution：只通过 `TaskCompleted` 事件（无同步依赖）
- Execution → Knowledge：只通过 Context Assembler ACL（无直接 import）
- Governance → Knowledge：`ConflictResolved` 事件驱动（无同步调用）
- Capability → Workforce：Skill 通过 `base_skill_set` 引用（无聚合耦合）

## 评审流程

### 1. 静态分析
- 扫描 `packages/` 下 6 个包的 import 关系，检测跨包仓储直接引用
- 检查 `services/api/aiteamos_api/acl_bridges.py` 中 ACL 的覆盖完整性
- 验证 `migrations/` 中的 DDL 是否符合 arch.md §2.3 存储矩阵

### 2. 不变量测试
- 针对 N1-N8 设计专项测试用例（`tests/` 目录）
- 特别关注：幂等投影（N6）和 Saga 补偿（N7）的混沌测试

### 3. 风险定级
- **Critical**: 违反十三条纪律中的任一条（阻塞发布）
- **Major**: 不变量测试未覆盖或存在已知绕过路径
- **Minor**: ACL 覆盖不完整或投影延迟超标
- **Info**: 性能指标接近阈值但未突破

## 输出产物
- 纪律合规报告（13 条逐项，标注 PASS/FAIL/WARN）
- 不变量测试覆盖报告（N1-N8，标注测试存在性和通过率）
- 改进路线图（按 Critical → Major → Minor 排序，含具体修复步骤）

## 参考
- `docs/arch.md` §0.2 — 十三条设计纪律
- `docs/arch.md` §1.4 — 8 个不变量
- `docs/arch.md` §2.1 — Bounded Context 跨上下文契约
- `tests/` — 集成测试目录
