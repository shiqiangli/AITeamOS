# backend-api-implementation

> AITeamOS 后端 API 实现 — FastAPI 路由、CQRS Command/Query 分离、Outbox 模式。

## AITeamOS 后端 API 架构锚点

### API 层结构
```
services/api/aiteamos_api/
  ├── main.py              # FastAPI app 定义 + lifespan
  ├── composition.py        # Composition Root — 依赖注入、Handler 组装
  ├── acl_bridges.py        # ACL 跨 Context 桥接实现
  ├── middleware/
  │   ├── auth.py           # 认证中间件（Bearer token）
  │   └── error_handler.py  # 全局异常处理
  ├── command/              # CQRS 写路径
  │   ├── skill_commands.py # POST/PUT/DELETE + 领域操作
  │   ├── task_commands.py
  │   ├── employee_commands.py
  │   └── ...
  └── read/                 # CQRS 读路径
      ├── skill_routes.py   # GET 列表 + 详情
      ├── task_routes.py
      ├── employee_routes.py
      └── ...
```

### CQRS 分离原则
| | Command（写路径） | Query（读路径） |
|---|---|---|
| **目录** | `command/` | `read/` |
| **HTTP 方法** | POST, PUT, DELETE | GET |
| **请求模型** | Pydantic Request（验证输入） | 查询参数 |
| **响应模型** | 完整聚合 or 操作确认 | DTO（SkillSummary, SkillDetail） |
| **数据库** | 主库（强一致） | 主库 或 投影表（最终一致） |
| **事务** | 必须（同事务写聚合 + Outbox 事件） | 可选（只读查询） |

### FastAPI 路由注册模式
```python
# read/skill_routes.py
def init_routes(router: APIRouter, queries: SkillQueries):
    @router.get("/", response_model=list[SkillSummary])
    async def list_skills(user=Depends(get_current_user)):
        return await queries.list_all()

    @router.get("/{skill_id}", response_model=SkillDetail)
    async def get_skill(skill_id: UUID, user=Depends(get_current_user)):
        result = await queries.get_by_id(skill_id)
        if not result:
            raise HTTPException(status_code=404, detail="Skill not found")
        return result
```

```python
# command/skill_commands.py
def init_routes(router: APIRouter, handler: RegisterSkillHandler, ...):
    @router.post("/", response_model=SkillSummary, status_code=201)
    async def register_skill(body: RegisterSkillRequest, user=Depends(get_current_user)):
        cmd = RegisterSkillCommand(name=body.name, version=body.version, ...)
        return await handler.handle(cmd)
```

## API 实现检查清单

### 新增 Command 路由时
- [ ] Request 模型用 Pydantic 定义，包含字段验证（`min_length`, `regex`）
- [ ] 请求体转换为 Command 对象后传给 Handler，不在路由层写业务逻辑
- [ ] Handler 内使用 `tx_manager.transaction()` 包裹聚合保存 + Outbox 事件
- [ ] 返回 `status_code=201`（POST 创建）或 `200`（PUT 更新）
- [ ] 认证通过 `Depends(get_current_user)` 注入

### 新增 Query 路由时
- [ ] Response 模型定义为 DTO dataclass（`SkillSummary`, `SkillDetail`）
- [ ] 查询使用 asyncpg 参数化查询
- [ ] 404 处理：查无结果时抛 `HTTPException(status_code=404)`
- [ ] 列表查询支持分页（`LIMIT` + `OFFSET` 或游标）
- [ ] 跨 Context 数据通过 ACL Bridge 获取，不在 read 路由中直接 JOIN 其他 Context 的表

### Outbox 模式实现
```python
# ✅ 正确：同事务写聚合 + 事件
async with tx_manager.transaction() as tx:
    await repo.save(skill, tx=tx)
    await tx.execute(
        "INSERT INTO outbox (event_type, aggregate_id, payload, global_seq) VALUES ($1, $2, $3::jsonb, nextval('global_seq'))",
        "skill.registered", str(skill.id), json.dumps(event_payload)
    )

# ❌ 错误：事件在事务外发布（聚合保存成功但事件丢失的风险）
await repo.save(skill)
await event_bus.publish(event)  # 如果这里失败，聚合已保存但事件丢失
```

### ACL Bridge 实现
```python
# ✅ 正确：ACL 在 Composition Root 注入
# composition.py
knowledge_acl = RecallEngineKnowledgeACL(knowledge_repo)
task_handler = CreateTaskHandler(task_repo, knowledge_acl)

# ✅ 正确：ACL 接口定义在消费方（Execution），实现在提供方（Knowledge）
# packages/execution/.../ports.py
class KnowledgeACL(Protocol):
    async def recall_memories(self, query: str, limit: int) -> list[MemoryDTO]: ...

# services/api/aiteamos_api/acl_bridges.py
class RecallEngineKnowledgeACL:
    async def recall_memories(self, query: str, limit: int) -> list[MemoryDTO]:
        # 直接查 Knowledge Context 的数据库（读侧）
        rows = await self.db.fetch("SELECT id, title, content FROM memory_node ...")
        return [MemoryDTO(**row) for row in rows]
```

### 中间件与全局处理
- [ ] 认证中间件（`middleware/auth.py`）：校验 Bearer token
- [ ] 错误处理中间件（`middleware/error_handler.py`）：捕获未处理异常，返回 500
- [ ] CORS 配置：开发环境允许 `localhost:5173`
- [ ] Request ID 追踪：每个请求分配唯一 ID，传递到日志

### 数据库迁移
- [ ] 新表/列变更创建 migration 文件（`migrations/NNN_xxx.sql`）
- [ ] migration 文件包含 `CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ADD COLUMN IF NOT EXISTS`
- [ ] 新增索引使用 `CONCURRENTLY` 避免锁表
- [ ] 外键引用明确，跨 Context 引用使用 UUID 而非数据库外键

## API 端点命名规范
| 操作 | HTTP 方法 | 路径 | 示例 |
|------|----------|------|------|
| 列表 | GET | `/api/v1/{resource}` | `GET /api/v1/skills` |
| 详情 | GET | `/api/v1/{resource}/{id}` | `GET /api/v1/skills/{id}` |
| 创建 | POST | `/api/v1/{resource}` | `POST /api/v1/skills` |
| 更新 | PUT | `/api/v1/{resource}/{id}` | `PUT /api/v1/skills/{id}` |
| 删除 | DELETE | `/api/v1/{resource}/{id}` | `DELETE /api/v1/skills/{id}` |
| 领域操作 | POST | `/api/v1/{resource}/{id}/commands/{action}` | `POST /api/v1/skills/{id}/commands/publish` |
| 文件端点 | GET | `/api/v1/{resource}/{id}/file` | `GET /api/v1/skills/{id}/file` |

## 参考
- `services/api/aiteamos_api/` — API 层代码
- `services/api/aiteamos_api/composition.py` — Composition Root
- `services/api/aiteamos_api/acl_bridges.py` — ACL 实现
- `services/api/aiteamos_api/command/skill_commands.py` — Command 路由参考
- `services/api/aiteamos_api/read/skill_routes.py` — Query 路由参考
- `migrations/` — 数据库迁移文件
