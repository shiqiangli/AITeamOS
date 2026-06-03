# frontend-component-design

> AITeamOS 前端组件设计 — 基于 shadcn/ui 的 Dashboard 页面模式与组件复用体系。

## AITeamOS 前端技术栈锚点

### 技术栈
- **框架**: React 18 + TypeScript + Vite
- **UI 库**: shadcn/ui（基于 Radix UI + Tailwind CSS）
- **组件路径**: `apps/dashboard/src/components/`
  - `ui/` — shadcn 基础组件（Button, Card, Dialog, Table, Tabs, Input, Select, Badge, Skeleton, Separator, Toaster）
  - `shared.tsx` — 跨页面共享组件
- **页面路径**: `apps/dashboard/src/pages/`（每个页面一个目录 + `index.tsx`）
- **状态管理**: 无全局状态库，页面级 useState + useEffect + API 调用

### 现有页面模式
| 页面 | 路径 | 核心模式 |
|------|------|---------|
| Agents | `/agents` | 表格列表 + 详情 Dialog（Tabs 分区） |
| Tasks | `/tasks` | 表格列表 + 状态 Badge + 操作按钮 |
| Employees | `/employees` | 表格列表 + Skill/Memory 分配面板 |
| Skills | `/skills` | 表格列表 + 详情 Dialog（Overview/Edit/SKILL.md/Actions Tabs） |
| Memory | `/memory` | 知识图谱可视化 + 详情面板 |
| Metrics | `/metrics` | 指标卡片 + 时序图表 |
| Projects | `/projects` | 项目管理表格 |

### 通用页面结构
```tsx
export default function XxxPage() {
  // 1. 状态声明
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedItem, setSelectedItem] = useState<Item | null>(null);

  // 2. 数据加载
  useEffect(() => { fetchItems().then(setItems).finally(() => setLoading(false)); }, []);

  // 3. 渲染
  return (
    <div className="space-y-6">
      <PageHeader title="..." description="..." action={<Button onClick={...}>新建</Button>} />
      {loading ? <LoadingState /> : (
        <DataTable columns={columns} data={items} onRowClick={setSelectedItem} />
      )}
      {/* 详情 Dialog */}
      <Dialog open={!!selectedItem} onOpenChange={() => setSelectedItem(null)}>
        <DialogContent>
          <Tabs defaultValue="overview">...</Tabs>
        </DialogContent>
      </Dialog>
    </div>
  );
}
```

## 组件设计检查清单

### 新增页面时
- [ ] 页面组件放在 `pages/{name}/index.tsx`，不放在 `components/`
- [ ] 使用 shadcn/ui 组件，**不引入额外 UI 库**
- [ ] 列表页统一使用 `DataTable` + `columns` 定义（type-safe 列配置）
- [ ] 详情展示统一使用 `Dialog` + `Tabs` 模式
- [ ] 加载状态统一使用 `Skeleton` 组件，不使用 spinner
- [ ] 空状态统一使用 `shared.tsx` 中的 `EmptyState` 组件
- [ ] 错误提示统一使用 `useToast` hook

### 新增共享组件时
- [ ] 判断是否被 ≥2 个页面使用 → 放 `components/shared.tsx`
- [ ] 判断是否是 UI 原子组件 → 放 `components/ui/`（通过 shadcn CLI 添加）
- [ ] 组件接受 `className` prop 支持样式覆盖
- [ ] 组件使用 TypeScript 泛型（如 `DataTable<T>`）保证类型安全

### Tailwind CSS 规范
- [ ] 使用 `cn()` 工具函数合并 class（`lib/utils.ts`）
- [ ] 颜色使用 CSS 变量（`bg-primary`, `text-muted-foreground`），不硬编码颜色值
- [ ] 响应式使用 Tailwind 前缀（`sm:`, `md:`, `lg:`）
- [ ] 间距使用 Tailwind 的 spacing scale（`space-y-4`, `gap-2`, `p-6`）

### 可访问性
- [ ] 交互元素有 `aria-label` 或可见文本
- [ ] Dialog 有 `DialogTitle`
- [ ] 表格有 `TableHeader` + `TableBody`
- [ ] 表单控件有 `<Label htmlFor="...">`

## 常用 shadcn 组件使用指南

### DataTable（表格）
```tsx
const columns: ColumnDef<SkillSummary>[] = [
  { accessorKey: "name", header: "Name" },
  { accessorKey: "domain", header: "Domain", cell: ({ row }) => <Badge>{row.original.domain}</Badge> },
  { id: "actions", cell: ({ row }) => <Button variant="ghost" onClick={() => onEdit(row.original)}>编辑</Button> },
];
<DataTable columns={columns} data={skills} />
```

### Dialog + Tabs（详情弹窗）
```tsx
<Dialog open={!!selected} onOpenChange={() => setSelected(null)}>
  <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
    <DialogHeader><DialogTitle>{selected.name}</DialogTitle></DialogHeader>
    <Tabs defaultValue="overview">
      <TabsList>
        <TabsTrigger value="overview">Overview</TabsTrigger>
        <TabsTrigger value="edit">Edit</TabsTrigger>
      </TabsList>
      <TabsContent value="overview">...</TabsContent>
      <TabsContent value="edit">...</TabsContent>
    </Tabs>
  </DialogContent>
</Dialog>
```

## 参考
- `apps/dashboard/src/components/ui/` — shadcn 组件库
- `apps/dashboard/src/components/shared.tsx` — 共享组件
- `apps/dashboard/src/lib/utils.ts` — `cn()` 工具函数
- `apps/dashboard/src/pages/skills/index.tsx` — 参考实现（最完整的页面）
