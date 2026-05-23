export type DashboardLocale = "en" | "zh";

export const dashboardLocales: DashboardLocale[] = ["en", "zh"];

export const dashboardLocaleLabels: Record<DashboardLocale, string> = {
  en: "English",
  zh: "中文",
};

export const dashboardStrings: Record<string, Record<DashboardLocale, string>> = {
  AITEAMOS: { en: "AITEAMOS", zh: "AITEAMOS" },
  "Team OS": { en: "Team OS", zh: "团队操作系统" },
  Home: { en: "Home", zh: "首页" },
  Projects: { en: "Projects", zh: "项目" },
  Employees: { en: "Employees", zh: "成员" },
  Tasks: { en: "Tasks", zh: "任务" },
  Runs: { en: "Runs", zh: "运行" },
  Automations: { en: "Automations", zh: "自动化" },
  Memory: { en: "Memory", zh: "记忆" },
  Reviews: { en: "Reviews", zh: "审查" },
  Skills: { en: "Skills", zh: "技能" },
  Permissions: { en: "Permissions", zh: "权限" },
  Settings: { en: "Settings", zh: "设置" },
  Workspace: { en: "Workspace", zh: "工作区" },
  "Auth URL": { en: "Auth URL", zh: "认证 URL" },
  Language: { en: "Language", zh: "语言" },
  "Dashboard Language": { en: "Dashboard Language", zh: "Dashboard 语言" },
  Refresh: { en: "Refresh", zh: "刷新" },
  Session: { en: "Session", zh: "会话" },
  "Product User": { en: "Product User", zh: "产品用户" },
  Governance: { en: "Governance", zh: "治理" },
  Viewer: { en: "Viewer", zh: "查看者" },
  Projection: { en: "Projection", zh: "投影" },
  Warnings: { en: "Warnings", zh: "警告" },
  "Dashboard API Session": { en: "Dashboard API Session", zh: "Dashboard API 会话" },
  "Product Session Token": { en: "Product Session Token", zh: "产品会话令牌" },
  "Product session token": { en: "Product session token", zh: "产品会话令牌" },
  "Login Product Session": { en: "Login Product Session", zh: "登录产品会话" },
  "Renew Product Session": { en: "Renew Product Session", zh: "续期产品会话" },
  "Logout Product Session": { en: "Logout Product Session", zh: "退出产品会话" },
  "Update API Token": { en: "Update API Token", zh: "更新 API 令牌" },
  "Set API Token": { en: "Set API Token", zh: "设置 API 令牌" },
  "Clear API Token": { en: "Clear API Token", zh: "清除 API 令牌" },
  "Session Projection": { en: "Session Projection", zh: "会话投影" },
  "Projection Viewer": { en: "Projection Viewer", zh: "投影查看者" },
  "Public / redacted": { en: "Public / redacted", zh: "公开 / 已脱敏" },
  "Loading workspace data...": { en: "Loading workspace data...", zh: "正在加载工作区数据..." },
  "Unavailable endpoints:": { en: "Unavailable endpoints:", zh: "不可用端点：" },
  "No records.": { en: "No records.", zh: "无记录。" },
  "No record selected.": { en: "No record selected.", zh: "未选择记录。" },
  ID: { en: "ID", zh: "ID" },
  Kind: { en: "Kind", zh: "类型" },
  Status: { en: "Status", zh: "状态" },
  Action: { en: "Action", zh: "操作" },
  Risk: { en: "Risk", zh: "风险" },
  Audit: { en: "Audit", zh: "审计" },
  Member: { en: "Member", zh: "成员" },
  Project: { en: "Project", zh: "项目" },
  Assignment: { en: "Assignment", zh: "分派" },
  Expires: { en: "Expires", zh: "过期时间" },
  "Source Request": { en: "Source Request", zh: "来源请求" },
  Revoke: { en: "Revoke", zh: "撤销" },
  "Workspace Health": { en: "Workspace Health", zh: "工作区健康" },
  Operations: { en: "Operations", zh: "运维" },
  Errors: { en: "Errors", zh: "错误" },
  "Manifest Load Failures": { en: "Manifest Load Failures", zh: "Manifest 加载失败" },
  "Vector Chunks": { en: "Vector Chunks", zh: "向量分块" },
  "Stale Worker Leases": { en: "Stale Worker Leases", zh: "过期 Worker 租约" },
  "Workspace Catalog": { en: "Workspace Catalog", zh: "工作区目录" },
  "Workspace API Base": { en: "Workspace API Base", zh: "工作区 API 地址" },
  "Apply API Base": { en: "Apply API Base", zh: "应用 API 地址" },
  "Clear API Base": { en: "Clear API Base", zh: "清除 API 地址" },
  "Cost / Model": { en: "Cost / Model", zh: "成本 / 模型" },
  "Active Projects": { en: "Active Projects", zh: "活跃项目" },
  "Active Employees": { en: "Active Employees", zh: "活跃成员" },
  "Open Tasks": { en: "Open Tasks", zh: "开放任务" },
  "Stalled Runs": { en: "Stalled Runs", zh: "停滞运行" },
  "Memory Proposals": { en: "Memory Proposals", zh: "记忆提案" },
  "Remediation Tasks": { en: "Remediation Tasks", zh: "修复任务" },
  "Remediation Runs": { en: "Remediation Runs", zh: "修复运行" },
  "Active Worker Runs": { en: "Active Worker Runs", zh: "活跃 Worker 运行" },
  "STALLED Runs": { en: "STALLED Runs", zh: "停滞运行" },
  "Automation Runs": { en: "Automation Runs", zh: "自动化运行" },
  "Code Reviews": { en: "Code Reviews", zh: "代码审查" },
  "Connector Reviews": { en: "Connector Reviews", zh: "Connector 审查" },
  "Open Reviews": { en: "Open Reviews", zh: "开放审查" },
  "Related Tasks": { en: "Related Tasks", zh: "相关任务" },
  "Related Runs": { en: "Related Runs", zh: "相关运行" },
  "Required Permissions": { en: "Required Permissions", zh: "必需权限" },
  "Memory Projection Viewer": { en: "Memory Projection Viewer", zh: "记忆投影查看器" },
  "Memory Health": { en: "Memory Health", zh: "记忆健康" },
  "Memory Health Remediation": { en: "Memory Health Remediation", zh: "记忆健康修复" },
  "Selected Memory Resource": { en: "Selected Memory Resource", zh: "已选记忆资源" },
  "Selected Memory Projection": { en: "Selected Memory Projection", zh: "已选记忆投影" },
  "Memory Review Console": { en: "Memory Review Console", zh: "记忆审查控制台" },
  "Memory Review Queue": { en: "Memory Review Queue", zh: "记忆审查队列" },
  "Skill Projection Viewer": { en: "Skill Projection Viewer", zh: "技能投影查看器" },
  "Connector Remediation Materialized Tasks": { en: "Connector Remediation Materialized Tasks", zh: "Connector 修复物化任务" },
  "Connector Remediation Run Follow-through": { en: "Connector Remediation Run Follow-through", zh: "Connector 修复运行跟进" },
  "Connector Remediation Task Launch Readiness": { en: "Connector Remediation Task Launch Readiness", zh: "Connector 修复任务启动就绪度" },
  "Materialized Connector Remediation Tasks": { en: "Materialized Connector Remediation Tasks", zh: "已物化 Connector 修复任务" },
  "Run Context Memory Injection": { en: "Run Context Memory Injection", zh: "运行上下文记忆注入" },
  "Memory Sources": { en: "Memory Sources", zh: "记忆来源" },
  "Injected Memory": { en: "Injected Memory", zh: "已注入记忆" },
  "API bearer token": { en: "API bearer token", zh: "API bearer 令牌" },
};

export function isDashboardLocale(value: string): value is DashboardLocale {
  return dashboardLocales.includes(value as DashboardLocale);
}

export function translateDashboardString(source: string, locale: DashboardLocale): string {
  const exact = dashboardStrings[source]?.[locale];
  if (exact) {
    return exact;
  }
  for (const [prefix, translations] of Object.entries(dashboardStrings)) {
    if (source.startsWith(`${prefix} `) && translations[locale] !== undefined) {
      return `${translations[locale]} ${source.slice(prefix.length + 1)}`;
    }
  }
  return source;
}
