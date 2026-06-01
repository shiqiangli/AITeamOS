# frontend-api-integration

> AITeamOS 前端 API 集成 — TypeScript 类型安全、CQRS 读侧消费、错误处理体系。

## AITeamOS 前端 API 架构锚点

### API Client 设计（`apps/dashboard/src/api/client.ts`）
```
API Client 职责：
  1. 封装 fetch 调用，统一处理 Authorization header
  2. 定义 TypeScript 接口与后端响应匹配
  3. 提供类型安全的 CRUD 函数
  4. 统一错误处理（HTTP 状态码 → 用户可理解的提示）
```

### 后端 API 结构（CQRS 分离）
| 路径模式 | 职责 | 对应 |
|---------|------|------|
| `GET /api/v1/{resource}` | 读路径 — 列表查询 | CQRS Query |
| `GET /api/v1/{resource}/{id}` | 读路径 — 详情查询 | CQRS Query |
| `POST /api/v1/{resource}` | 写路径 — 创建 | CQRS Command |
| `PUT /api/v1/{resource}/{id}` | 写路径 — 更新 | CQRS Command |
| `DELETE /api/v1/{resource}/{id}` | 写路径 — 删除 | CQRS Command |
| `POST /api/v1/{resource}/{id}/commands/{action}` | 写路径 — 领域操作 | CQRS Command |

### 认证
- 所有请求必须携带 `Authorization: Bearer {token}` header
- 前端统一在 API client 中注入，页面组件不感知认证细节

## API Client 设计检查清单

### 新增 API 函数时
- [ ] 定义 TypeScript 接口（Request + Response），与后端 schema 对齐
- [ ] 函数名使用动词前缀（`fetch` 读、`create` 写、`update` 修改、`delete` 删除）
- [ ] 统一使用 `async/await`，不使用 `.then()` 链
- [ ] HTTP 错误统一通过 `handleApiError()` 处理，不在每个函数中单独 try/catch
- [ ] 返回类型是具体接口，不是 `any` 或 `unknown`

### TypeScript 接口规范
```typescript
// ✅ 正确：接口名与后端领域模型对齐
interface SkillSummary {
  id: string;
  name: string;
  version: string;
  description: string;
  domain: string;
  status: string;
  capability_tags: string[];
  created_at: string;
}

// ✅ 正确：Payload 类型只含可写字段
interface RegisterSkillPayload {
  name: string;
  version: string;
  description: string;
  domain: string;
  capability_tags: string[];
}

// ❌ 错误：使用 any
function fetchSkills(): Promise<any> { ... }

// ❌ 错误：接口与后端字段不匹配
interface Skill { name: string; /* 缺少 id, version 等 */ }
```

### 错误处理
```typescript
// 统一错误处理
async function handleApiError(response: Response) {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const message = body.detail || `HTTP ${response.status}`;
    toast({ title: "Error", description: message, variant: "destructive" });
    throw new Error(message);
  }
}

// API 函数模板
async function fetchSkills(): Promise<SkillSummary[]> {
  const res = await fetch(`${BASE}/skills`, { headers: authHeaders() });
  await handleApiError(res);
  return res.json();
}

async function createSkill(payload: RegisterSkillPayload): Promise<SkillSummary> {
  const res = await fetch(`${BASE}/skills`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  await handleApiError(res);
  return res.json();
}
```

### 前端与后端字段对齐规则
- UUID 类型在后端是 `UUID`，前端用 `string`
- datetime 在后端是 `datetime`，前端用 `string`（ISO 8601）
- JSON 数组在后端是 `list`，前端用 `Array<T>`
- Optional 字段在后端是 `Optional[T]`，前端用 `T | undefined`

### CQRS 读侧注意事项
- 读 API 可能有投影延迟（最终一致），刚写入的数据可能不会立即出现在列表中
- 创建/更新操作后，建议延迟 500ms 再刷新列表，或使用乐观更新
- 详情 API（`GET /{id}`）直接查主库，是强一致的

## 数据流模式

### 列表加载
```tsx
const [items, setItems] = useState<Item[]>([]);
const [loading, setLoading] = useState(true);

const refresh = useCallback(async () => {
  setLoading(true);
  try {
    const data = await fetchItems();
    setItems(data);
  } catch { /* handleApiError 已 toast */ }
  finally { setLoading(false); }
}, []);

useEffect(() => { refresh(); }, [refresh]);
```

### 表单提交
```tsx
const handleSubmit = async (e: React.FormEvent) => {
  e.preventDefault();
  try {
    await createItem(formData);
    toast({ title: "Created", description: "..." });
    setOpen(false);
    refresh();  // 刷新列表
  } catch { /* handleApiError 已 toast */ }
};
```

### 详情加载（Dialog 打开时）
```tsx
const [detail, setDetail] = useState<Detail | null>(null);

const openDetail = async (id: string) => {
  const data = await fetchItemDetail(id);
  setDetail(data);
  setSelectedId(id);
};
```

## 参考
- `apps/dashboard/src/api/client.ts` — API Client 实现
- `apps/dashboard/src/components/ui/use-toast.ts` — Toast 通知
- `services/api/aiteamos_api/read/` — 后端读路由
- `services/api/aiteamos_api/command/` — 后端命令路由
