import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Brain,
  ChevronRight,
  ClipboardCheck,
  Clock3,
  Database,
  FolderGit2,
  GitBranch,
  KeyRound,
  MessageSquare,
  Plug,
  Search,
  ShieldCheck,
  Sparkles,
  UserCheck,
  Users,
  Wrench,
  X,
} from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Select } from "../../components/ui/select";
import {
  ErrorState,
  LoadingState,
  navigateTo,
} from "../../components/shared";
import {
  getChatAiEngines,
  listChatEmployees,
  listChatThreads,
  updateChatEmployeeAiEngine,
  type ChatAiEngineSettings,
  type ChatEmployeeSummary,
  type ChatThreadListResponse,
} from "../../api/chat";
import { getCapabilities, type CapabilityRecord, type CapabilityRegistryResponse } from "../../api/capabilities";
import {
  getEmployeeWorkLedger,
  type EmployeeTicketReportRecord,
  type EmployeeWorkLedger,
  type TicketWorkItem,
} from "../../api/tickets";
import { cn } from "@/lib/utils";

type DetailTab = "overview" | "work" | "capabilities" | "governance" | "ai_engine";

const DETAIL_TABS: Array<{ key: DetailTab; label: string }> = [
  { key: "overview", label: "Overview" },
  { key: "work", label: "Work Ledger" },
  { key: "capabilities", label: "Capabilities" },
  { key: "governance", label: "Governance" },
  { key: "ai_engine", label: "AI Engine" },
];

function capabilitiesForEmployee(employee: ChatEmployeeSummary | null, registry: CapabilityRegistryResponse | null): CapabilityRecord[] {
  if (!employee) return [];
  const capabilities = registry?.capabilities ?? [];
  const isClara = employee.id === "clara";
  return capabilities.filter((capability) => {
    if (!capability.enabled) return false;
    if (capability.kind !== "tool") return false;
    if (isClara) return true;
    if (capability.source_kind === "mcp_server") return capability.configured;
    return [
      "search_knowledge",
      "list_tickets",
      "record_ticket_report",
      "list_code_repositories",
      "inspect_code_repository",
    ].includes(capability.id);
  });
}

function capabilityVariant(capability: CapabilityRecord): "success" | "warning" | "secondary" | "outline" {
  if (!capability.configured) return "outline";
  if (capability.status === "ready") return "success";
  if (capability.status === "planned") return "warning";
  return "secondary";
}

function formatThreadTime(value?: string | null): string {
  if (!value) return "No activity";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "No activity";
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function latestThread(threads?: ChatThreadListResponse | null) {
  return threads?.threads?.[0] ?? null;
}

function threadCount(threads?: ChatThreadListResponse | null): number {
  return threads?.threads?.length ?? 0;
}

function totalMessages(threads?: ChatThreadListResponse | null): number {
  return threads?.threads?.reduce((sum, thread) => sum + (thread.message_count ?? 0), 0) ?? 0;
}

function employeeInitial(employee: ChatEmployeeSummary): string {
  return (employee.display_name || employee.id || "?").trim().charAt(0).toUpperCase() || "?";
}

function employeeState(employee: ChatEmployeeSummary, threads?: ChatThreadListResponse | null): {
  label: string;
  variant: "success" | "warning" | "secondary" | "outline";
} {
  if (employee.id === "clara") return { label: "operating", variant: "success" };
  if (totalMessages(threads) > 0) return { label: "active", variant: "success" };
  return { label: "ready", variant: "outline" };
}

function roleGroup(employee: ChatEmployeeSummary): string {
  const role = employee.role.toLowerCase();
  if (employee.id === "clara" || role.includes("manager") || role.includes("admin")) return "Operations";
  if (role.includes("rd") || role.includes("engineer") || role.includes("implementer")) return "Engineering";
  if (role.includes("pv") || role.includes("qa") || role.includes("validation")) return "Validation";
  if (role.includes("architect") || role.includes("lead")) return "Architecture";
  return "Specialist";
}

function aiEngineLabel(employee: ChatEmployeeSummary): string {
  return employee.ai_engine_mode.replace(/_/g, " ");
}

function defaultAiEngineLabel(value?: string | null): string {
  const engine = (value || "system").trim().toLowerCase();
  if (engine === "system") return "Settings default";
  if (engine === "stub") return "File stub";
  if (engine === "deepseek") return "DeepSeek";
  if (engine === "openai") return "OpenAI / ChatGPT";
  return engine || "Settings default";
}

function effectiveAiEngine(employee: ChatEmployeeSummary, aiEngines: ChatAiEngineSettings | null): string {
  const defaultEngine = (employee.default_ai_engine || "system").trim().toLowerCase();
  return defaultEngine === "system" ? aiEngines?.active_engine ?? "system" : defaultEngine;
}

function contributionValue(work: EmployeeWorkLedger | null, key: string): number {
  const value = work?.contribution?.[key];
  return typeof value === "number" ? value : 0;
}

function sourceKindLabel(sourceKind: string): string {
  if (sourceKind === "built_in") return "Built-in";
  if (sourceKind === "mcp_server") return "MCP";
  if (sourceKind === "native_api") return "Native API";
  if (sourceKind === "cli") return "CLI";
  if (sourceKind === "ci") return "CI";
  if (sourceKind === "ticket_backend") return "Ticket backend";
  if (sourceKind === "ai_engine_bridge") return "AI Engine bridge";
  return sourceKind.replace(/_/g, " ") || "Tool";
}

function capabilityGroups(capabilities: CapabilityRecord[]) {
  const tools = capabilities.filter((capability) => capability.kind === "tool");
  return {
    builtIn: tools.filter((capability) => capability.source_kind === "built_in"),
    mcp: tools.filter((capability) => capability.source_kind === "mcp_server"),
    other: tools.filter((capability) => !["built_in", "mcp_server"].includes(capability.source_kind)),
  };
}

function uniquePermissions(capabilities: CapabilityRecord[]): string[] {
  return Array.from(new Set(capabilities.flatMap((capability) => capability.permissions).filter(Boolean))).sort();
}

function uniqueConnectorIds(capabilities: CapabilityRecord[]): string[] {
  return Array.from(new Set(capabilities.map((capability) => capability.connector_id).filter(Boolean))).sort();
}

function handoffValue(handoff: Record<string, unknown>, key: string): string {
  const value = handoff[key];
  return typeof value === "string" ? value : "";
}

function handoffEventValue(handoff: Record<string, unknown>, key: string): string {
  const event = handoff.event;
  if (!event || typeof event !== "object") return "";
  const value = (event as Record<string, unknown>)[key];
  return typeof value === "string" ? value : "";
}

function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Users;
  label: string;
  value: string | number;
}) {
  return (
    <div className="rounded-md border bg-background p-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </div>
      <div className="text-2xl font-semibold leading-none">{value}</div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b py-2 text-sm last:border-b-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="min-w-0 truncate text-right font-medium" title={String(value)}>{value}</span>
    </div>
  );
}

function WorkItemButton({ item }: { item: TicketWorkItem }) {
  return (
    <button
      type="button"
      className="flex w-full items-center justify-between gap-3 rounded-md border bg-muted/30 px-3 py-2 text-left transition-colors hover:bg-muted"
      onClick={() => navigateTo("chat", item.ticket_id)}
    >
      <div className="min-w-0">
        <div className="truncate text-sm font-medium">{item.title}</div>
        <div className="mt-0.5 flex min-w-0 flex-wrap gap-2 text-xs text-muted-foreground">
          <span>{item.ticket_id}</span>
          <span>{item.status}</span>
          <span>{formatThreadTime(item.updated_at)}</span>
        </div>
        {item.next_action && (
          <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{item.next_action}</div>
        )}
      </div>
      <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
    </button>
  );
}

function WorkReportSection({
  empty,
  records,
  title,
}: {
  empty: string;
  records: EmployeeTicketReportRecord[];
  title: string;
}) {
  return (
    <section className="rounded-md border p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold">{title}</h4>
        <Badge variant="outline">{records.length}</Badge>
      </div>
      {records.length ? (
        <div className="space-y-2">
          {records.slice(0, 6).map((record) => (
            <button
              key={`${record.ticket_id}-${record.report_id}`}
              type="button"
              className="w-full rounded-md px-2 py-2 text-left transition-colors hover:bg-muted"
              onClick={() => navigateTo("chat", record.ticket_id)}
            >
              <div className="flex min-w-0 items-center justify-between gap-2">
                <span className="truncate text-sm font-medium">{record.ticket_title}</span>
                <Badge variant="secondary" className="shrink-0">{record.report_type}</Badge>
              </div>
              <div className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{record.content}</div>
              <div className="mt-1 flex min-w-0 flex-wrap gap-2 text-[10px] text-muted-foreground">
                <span>{record.ticket_id}</span>
                <span>{formatThreadTime(record.created_at)}</span>
                {record.evidence.length > 0 && <span>{record.evidence.length} evidence</span>}
              </div>
            </button>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">{empty}</p>
      )}
    </section>
  );
}

function CapabilityGroupSection({
  capabilities,
  empty,
  title,
}: {
  capabilities: CapabilityRecord[];
  empty: string;
  title: string;
}) {
  return (
    <section className="rounded-md border p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold">{title}</h4>
        <Badge variant="outline">{capabilities.length}</Badge>
      </div>
      {capabilities.length ? (
        <div className="space-y-2">
          {capabilities.map((capability) => (
            <div key={capability.id} className="rounded-md border bg-muted/30 px-3 py-2">
              <div className="flex min-w-0 items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{capability.name}</div>
                  <div className="mt-0.5 flex flex-wrap gap-1.5 text-[10px] text-muted-foreground">
                    <span>{sourceKindLabel(capability.source_kind)}</span>
                    {capability.domain && <span>{capability.domain}</span>}
                    {capability.connector_id && <span>{capability.connector_id}</span>}
                  </div>
                </div>
                <Badge variant={capabilityVariant(capability)} className="shrink-0">{capability.status}</Badge>
              </div>
              {capability.description && (
                <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{capability.description}</p>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">{empty}</p>
      )}
    </section>
  );
}

function HandoffSection({ handoffs }: { handoffs: Record<string, unknown>[] }) {
  return (
    <section className="rounded-md border p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold">Handoffs</h4>
        <Badge variant="outline">{handoffs.length}</Badge>
      </div>
      {handoffs.length ? (
        <div className="space-y-2">
          {handoffs.slice(0, 6).map((handoff, index) => {
            const ticketId = handoffValue(handoff, "ticket_id");
            const title = handoffValue(handoff, "title") || ticketId || "Ticket handoff";
            const type = handoffEventValue(handoff, "type") || "handoff";
            const at = handoffEventValue(handoff, "at");
            return (
              <button
                key={`${ticketId || "handoff"}-${index}`}
                type="button"
                className="flex w-full items-center justify-between gap-3 rounded-md border bg-muted/30 px-3 py-2 text-left transition-colors hover:bg-muted"
                onClick={() => ticketId && navigateTo("chat", ticketId)}
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{title}</div>
                  <div className="mt-0.5 flex flex-wrap gap-2 text-xs text-muted-foreground">
                    {ticketId && <span>{ticketId}</span>}
                    <span>{type}</span>
                    {at && <span>{formatThreadTime(at)}</span>}
                  </div>
                </div>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
              </button>
            );
          })}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No handoff records yet.</p>
      )}
    </section>
  );
}

function ActivityThreadSection({ employee, threads }: { employee: ChatEmployeeSummary; threads: ChatThreadListResponse | null }) {
  return (
    <section className="rounded-md border p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold">Communication Signal</h4>
        <Badge variant="outline">{threadCount(threads)} threads</Badge>
      </div>
      {threads?.threads?.length ? (
        <div className="space-y-2">
          {threads.threads.slice(0, 4).map((thread) => (
            <button
              key={thread.id}
              type="button"
              className="flex w-full items-center justify-between gap-3 rounded-md border bg-muted/30 px-3 py-2 text-left transition-colors hover:bg-muted"
              onClick={() => navigateTo("chat", employee.id)}
            >
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{thread.title || thread.id}</div>
                <div className="text-xs text-muted-foreground">{thread.message_count} msgs</div>
              </div>
              <span className="shrink-0 text-xs text-muted-foreground">
                {formatThreadTime(thread.last_message_at || thread.updated_at)}
              </span>
            </button>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No recent communication threads.</p>
      )}
    </section>
  );
}

function EmployeeAvatar({ employee, size = "md" }: { employee: ChatEmployeeSummary; size?: "sm" | "md" | "lg" }) {
  return (
    <div className={cn(
      "flex shrink-0 items-center justify-center rounded-md bg-primary font-semibold text-primary-foreground",
      size === "sm" && "h-8 w-8 text-xs",
      size === "md" && "h-10 w-10 text-sm",
      size === "lg" && "h-12 w-12 text-base",
    )}>
      {employeeInitial(employee)}
    </div>
  );
}

function EmployeeDrawer({
  aiEngines,
  capabilities,
  employee,
  onDefaultEngineChange,
  threads,
  work,
}: {
  aiEngines: ChatAiEngineSettings | null;
  capabilities: CapabilityRecord[];
  employee: ChatEmployeeSummary;
  onDefaultEngineChange: (employeeId: string, defaultAiEngine: string) => Promise<ChatEmployeeSummary>;
  threads: ChatThreadListResponse | null;
  work: EmployeeWorkLedger | null;
}) {
  const [tab, setTab] = useState<DetailTab>("overview");
  const [defaultEngineInput, setDefaultEngineInput] = useState(employee.default_ai_engine || "system");
  const [savingDefaultEngine, setSavingDefaultEngine] = useState(false);
  const [defaultEngineError, setDefaultEngineError] = useState<string | null>(null);
  const latest = latestThread(threads);
  const state = employeeState(employee, threads);
  const readyCapabilities = capabilities.filter((capability) => capability.configured && capability.status === "ready");
  const groupedCapabilities = capabilityGroups(capabilities);
  const permissions = uniquePermissions(capabilities);
  const connectorIds = uniqueConnectorIds(capabilities);
  const currentTicket = work?.current_tickets?.[0] ?? null;
  const aiEngineOptions = useMemo(() => {
    const engines = Object.values(aiEngines?.engines ?? {}).filter((engine) => (engine.support_status ?? "supported") === "supported");
    return [
      { id: "system", label: `Settings default (${aiEngines?.active_engine ?? "system"})` },
      ...engines.map((engine) => ({ id: engine.id, label: engine.display_name })),
    ];
  }, [aiEngines]);

  useEffect(() => {
    setDefaultEngineInput(employee.default_ai_engine || "system");
    setDefaultEngineError(null);
  }, [employee.default_ai_engine, employee.id]);

  async function handleDefaultEngineSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (savingDefaultEngine) return;
    setSavingDefaultEngine(true);
    setDefaultEngineError(null);
    try {
      const updated = await onDefaultEngineChange(employee.id, defaultEngineInput.trim() || "system");
      setDefaultEngineInput(updated.default_ai_engine || "system");
    } catch (err) {
      setDefaultEngineError(err instanceof Error ? err.message : "Failed to update default AI Engine");
    } finally {
      setSavingDefaultEngine(false);
    }
  }

  return (
    <aside className="absolute inset-y-0 right-0 z-20 flex w-full max-w-[34rem] flex-col border-l bg-background shadow-xl">
      <div className="border-b p-4">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <EmployeeAvatar employee={employee} size="lg" />
            <div className="min-w-0">
              <div className="flex min-w-0 items-center gap-2">
                <h3 className="truncate text-lg font-semibold">{employee.display_name}</h3>
                <Badge variant={state.variant} className="shrink-0">{state.label}</Badge>
              </div>
              <p className="truncate text-sm text-muted-foreground">{employee.role}</p>
              <p className="mt-1 truncate text-xs text-muted-foreground">{employee.id}</p>
            </div>
          </div>
          <Button type="button" variant="ghost" size="icon" onClick={() => navigateTo("employees")} title="Close details">
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" onClick={() => navigateTo("chat", employee.id)}>
            <MessageSquare className="h-4 w-4" />
            Chat
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => navigateTo("assets", "capabilities", "skills")}>
            <Sparkles className="h-4 w-4" />
            Skills
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => navigateTo("assets", "capabilities", "built-in-tools")}>
            <Wrench className="h-4 w-4" />
            Tools
          </Button>
        </div>
      </div>

      <div className="border-b px-3">
        <div className="flex gap-1 overflow-hidden">
          {DETAIL_TABS.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setTab(item.key)}
              className={cn(
                "min-w-0 border-b-2 px-2 py-2 text-xs font-medium transition-colors",
                tab === item.key
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              <span className="block truncate">{item.label}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {tab === "overview" && (
          <div className="space-y-4">
            <section className="rounded-md border p-4">
              <div className="mb-2 flex items-center justify-between gap-2">
                <h4 className="text-sm font-semibold">Workforce Record</h4>
                <Badge variant="outline">{roleGroup(employee)}</Badge>
              </div>
              <p className="text-sm leading-6 text-muted-foreground">
                {employee.summary || "No mission summary configured yet."}
              </p>
            </section>

            <section className="grid gap-3 sm:grid-cols-3">
              <StatCard icon={GitBranch} label="Current Tickets" value={contributionValue(work, "current_ticket_count")} />
              <StatCard icon={ClipboardCheck} label="Reports" value={contributionValue(work, "report_count")} />
              <StatCard icon={ShieldCheck} label="Validations" value={contributionValue(work, "validation_count")} />
            </section>

            <section className="rounded-md border p-4">
              <div className="mb-3 flex items-center gap-2">
                <GitBranch className="h-4 w-4 text-muted-foreground" />
                <h4 className="text-sm font-semibold">Current Focus</h4>
              </div>
              {currentTicket ? (
                <WorkItemButton item={currentTicket} />
              ) : (
                <p className="text-sm text-muted-foreground">No active Ticket assignment in the work ledger.</p>
              )}
            </section>

            <section className="rounded-md border p-4">
              <h4 className="mb-2 text-sm font-semibold">Identity Boundary</h4>
              <InfoRow label="Role group" value={roleGroup(employee)} />
              <InfoRow label="Employee ID" value={employee.id} />
              <InfoRow label="Kind" value={employee.kind} />
              <InfoRow label="AI Engine" value={defaultAiEngineLabel(effectiveAiEngine(employee, aiEngines))} />
              <InfoRow label="Engine thread" value={employee.preserve_engine_thread ? "preserved" : "per run"} />
            </section>

            <ActivityThreadSection employee={employee} threads={threads} />

            <section className="grid gap-3 sm:grid-cols-3">
              <StatCard icon={MessageSquare} label="Threads" value={threadCount(threads)} />
              <StatCard icon={Activity} label="Messages" value={totalMessages(threads)} />
              <StatCard icon={Wrench} label="Ready Capabilities" value={readyCapabilities.length} />
            </section>
          </div>
        )}

        {tab === "work" && (
          <div className="space-y-4">
            <section className="grid gap-3 sm:grid-cols-2">
              <StatCard icon={GitBranch} label="Current Tickets" value={contributionValue(work, "current_ticket_count")} />
              <StatCard icon={Clock3} label="Historical Tickets" value={contributionValue(work, "ticket_count")} />
              <StatCard icon={ClipboardCheck} label="Reports" value={contributionValue(work, "report_count")} />
              <StatCard icon={AlertTriangle} label="Blocked" value={contributionValue(work, "blocked_count")} />
            </section>

            <section className="rounded-md border p-4">
              <div className="mb-3 flex items-center justify-between gap-2">
                <h4 className="text-sm font-semibold">Current Tickets</h4>
                <Badge variant="outline">{work?.current_tickets.length ?? 0}</Badge>
              </div>
              {work?.current_tickets.length ? (
                <div className="space-y-2">
                  {work.current_tickets.map((item) => <WorkItemButton key={item.ticket_id} item={item} />)}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No active Ticket assignment in the ledger.</p>
              )}
            </section>

            <section className="rounded-md border p-4">
              <div className="mb-3 flex items-center justify-between gap-2">
                <h4 className="text-sm font-semibold">Historical Tickets</h4>
                <Badge variant="outline">{work?.historical_tickets.length ?? 0}</Badge>
              </div>
              {work?.historical_tickets.length ? (
                <div className="space-y-2">
                  {work.historical_tickets.slice(0, 8).map((item) => <WorkItemButton key={item.ticket_id} item={item} />)}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No historical Ticket involvement yet.</p>
              )}
            </section>

            <WorkReportSection
              title="Reports"
              records={work?.reports ?? []}
              empty="No report records yet."
            />

            <WorkReportSection
              title="PV Validations"
              records={work?.validations ?? []}
              empty="No validation records yet."
            />

            <WorkReportSection
              title="Blocked / Failed Records"
              records={work?.blocked_records ?? []}
              empty="No blocked records yet."
            />

            <HandoffSection handoffs={work?.handoffs ?? []} />
          </div>
        )}

        {tab === "capabilities" && (
          <div className="space-y-4">
            <section className="rounded-md border p-4">
              <h4 className="mb-3 text-sm font-semibold">Assigned Skills</h4>
              {employee.skills.length ? (
                <div className="flex flex-wrap gap-2">
                  {employee.skills.map((skill) => (
                    <button key={skill} type="button" onClick={() => navigateTo("assets", "capabilities", "skills")}>
                      <Badge variant="secondary">{skill}</Badge>
                    </button>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No skills assigned.</p>
              )}
            </section>

            <CapabilityGroupSection
              title="Built-in Tools"
              capabilities={groupedCapabilities.builtIn}
              empty="No built-in tools mapped."
            />

            <CapabilityGroupSection
              title="MCP Tools"
              capabilities={groupedCapabilities.mcp}
              empty="No MCP tools mapped."
            />

            <CapabilityGroupSection
              title="Other Tool Sources"
              capabilities={groupedCapabilities.other}
              empty="No native API, CLI, CI, ticket backend, or AI engine bridge tools mapped."
            />
          </div>
        )}

        {tab === "governance" && (
          <div className="space-y-4">
            <section className="rounded-md border p-4">
              <div className="mb-3 flex items-center gap-2">
                <Brain className="h-4 w-4 text-muted-foreground" />
                <h4 className="text-sm font-semibold">Knowledge Scope</h4>
              </div>
              <p className="text-sm leading-6 text-muted-foreground">
                Employee-level knowledge scope is tracked through assigned skills and tool permissions. Dedicated
                per-employee memory scopes can be added after the Memory Backend becomes part of the operating loop.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button type="button" variant="outline" size="sm" onClick={() => navigateTo("assets", "knowledge", "docs")}>
                  <Database className="h-4 w-4" />
                  Docs
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={() => navigateTo("assets", "knowledge", "memories")}>
                  <Brain className="h-4 w-4" />
                  Memories
                </Button>
              </div>
            </section>

            <section className="rounded-md border p-4">
              <div className="mb-3 flex items-center gap-2">
                <FolderGit2 className="h-4 w-4 text-muted-foreground" />
                <h4 className="text-sm font-semibold">Ticket Scope</h4>
              </div>
              <InfoRow label="Default thread" value={employee.default_thread_id || "-"} />
              <InfoRow label="Ticket scopes" value="via assigned Tickets" />
              <InfoRow label="Repository scopes" value="via Ticket code refs" />
            </section>

            <section className="rounded-md border p-4">
              <div className="mb-3 flex items-center gap-2">
                <KeyRound className="h-4 w-4 text-muted-foreground" />
                <h4 className="text-sm font-semibold">Permissions</h4>
              </div>
              {permissions.length ? (
                <div className="flex flex-wrap gap-2">
                  {permissions.map((permission) => <Badge key={permission} variant="outline">{permission}</Badge>)}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No explicit tool permission claims exposed yet.</p>
              )}
            </section>

            <section className="rounded-md border p-4">
              <div className="mb-3 flex items-center gap-2">
                <Plug className="h-4 w-4 text-muted-foreground" />
                <h4 className="text-sm font-semibold">Connector Visibility</h4>
              </div>
              {connectorIds.length ? (
                <div className="flex flex-wrap gap-2">
                  {connectorIds.map((connectorId) => <Badge key={connectorId} variant="secondary">{connectorId}</Badge>)}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No external connector grants mapped for this employee.</p>
              )}
            </section>
          </div>
        )}

        {tab === "ai_engine" && (
          <div className="space-y-4">
            <section className="rounded-md border p-4">
              <div className="mb-3 flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-muted-foreground" />
                <h4 className="text-sm font-semibold">Default Engine</h4>
              </div>
              <div className="space-y-3">
                <InfoRow label="Effective engine" value={defaultAiEngineLabel(effectiveAiEngine(employee, aiEngines))} />
                <InfoRow label="Profile default" value={defaultAiEngineLabel(employee.default_ai_engine)} />
                <InfoRow label="Settings active" value={defaultAiEngineLabel(aiEngines?.active_engine)} />
                <form onSubmit={handleDefaultEngineSubmit} className="space-y-3">
                  <label className="block space-y-1">
                    <span className="text-xs uppercase text-muted-foreground">Default AI Engine</span>
                    <input
                      aria-label="Default AI Engine"
                      list={`employee-${employee.id}-ai-engine-options`}
                      value={defaultEngineInput}
                      onChange={(event) => setDefaultEngineInput(event.target.value)}
                      className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                    <datalist id={`employee-${employee.id}-ai-engine-options`}>
                      {aiEngineOptions.map((option) => (
                        <option key={option.id} value={option.id}>{option.label}</option>
                      ))}
                    </datalist>
                  </label>
                  {defaultEngineError && (
                    <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                      {defaultEngineError}
                    </div>
                  )}
                  <Button type="submit" size="sm" disabled={savingDefaultEngine}>
                    {savingDefaultEngine ? "Saving" : "Save default engine"}
                  </Button>
                </form>
              </div>
            </section>

            <section className="rounded-md border p-4">
              <h4 className="mb-2 text-sm font-semibold">Boundary</h4>
              <InfoRow label="AI Engine mode" value={aiEngineLabel(employee)} />
              <InfoRow label="Engine thread" value={employee.preserve_engine_thread ? "preserved" : "not preserved"} />
              <InfoRow label="Kind" value={employee.kind} />
            </section>
          </div>
        )}
      </div>
    </aside>
  );
}

export function EmployeesPage({ selectedId }: { selectedId: string | null }) {
  const [employees, setEmployees] = useState<ChatEmployeeSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [threadsMap, setThreadsMap] = useState<Record<string, ChatThreadListResponse>>({});
  const [workMap, setWorkMap] = useState<Record<string, EmployeeWorkLedger>>({});
  const [capabilityRegistry, setCapabilityRegistry] = useState<CapabilityRegistryResponse | null>(null);
  const [aiEngines, setAiEngines] = useState<ChatAiEngineSettings | null>(null);
  const [query, setQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");
  const [aiEngineFilter, setAiEngineFilter] = useState("all");

  const loadEmployees = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [loaded, loadedCapabilities, loadedAiEngines] = await Promise.all([
        listChatEmployees(),
        getCapabilities().catch(() => null),
        getChatAiEngines().catch(() => null),
      ]);
      setEmployees(loaded);
      setCapabilityRegistry(loadedCapabilities);
      setAiEngines(loadedAiEngines);

      const [threadsResults, workResults] = await Promise.all([
        Promise.allSettled(loaded.map((m) => listChatThreads(m.id))),
        Promise.allSettled(loaded.map((m) => getEmployeeWorkLedger(m.id))),
      ]);
      const newMap: Record<string, ChatThreadListResponse> = {};
      threadsResults.forEach((result, idx) => {
        if (result.status === "fulfilled") {
          newMap[loaded[idx].id] = result.value;
        }
      });
      setThreadsMap(newMap);
      const newWorkMap: Record<string, EmployeeWorkLedger> = {};
      workResults.forEach((result, idx) => {
        if (result.status === "fulfilled") {
          newWorkMap[loaded[idx].id] = result.value;
        }
      });
      setWorkMap(newWorkMap);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load employees");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadEmployees();
  }, [loadEmployees]);

  const roleGroups = useMemo(() => Array.from(new Set(employees.map(roleGroup))).sort(), [employees]);
  const aiEngineGroups = useMemo(
    () => Array.from(new Set(employees.map((employee) => defaultAiEngineLabel(effectiveAiEngine(employee, aiEngines))))).sort(),
    [aiEngines, employees],
  );

  const filteredEmployees = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return employees.filter((employee) => {
      const matchesQuery = !normalized || [
        employee.display_name,
        employee.id,
        employee.role,
        employee.summary,
        ...employee.skills,
      ].some((value) => value.toLowerCase().includes(normalized));
      const matchesRole = roleFilter === "all" || roleGroup(employee) === roleFilter;
      const matchesAiEngine = aiEngineFilter === "all" || defaultAiEngineLabel(effectiveAiEngine(employee, aiEngines)) === aiEngineFilter;
      return matchesQuery && matchesRole && matchesAiEngine;
    });
  }, [aiEngines, employees, query, roleFilter, aiEngineFilter]);

  const selectedEmployee = useMemo(() => {
    return selectedId ? employees.find((employee) => employee.id === selectedId) ?? null : null;
  }, [employees, selectedId]);

  const selectedThreads = selectedEmployee ? threadsMap[selectedEmployee.id] ?? null : null;
  const selectedWork = selectedEmployee ? workMap[selectedEmployee.id] ?? null : null;
  const selectedCapabilities = useMemo(
    () => capabilitiesForEmployee(selectedEmployee, capabilityRegistry),
    [capabilityRegistry, selectedEmployee],
  );

  const aggregateThreadCount = useMemo(
    () => employees.reduce((sum, employee) => sum + threadCount(threadsMap[employee.id]), 0),
    [employees, threadsMap],
  );
  const aggregateMessageCount = useMemo(
    () => employees.reduce((sum, employee) => sum + totalMessages(threadsMap[employee.id]), 0),
    [employees, threadsMap],
  );

  async function handleDefaultEngineChange(employeeId: string, defaultAiEngine: string): Promise<ChatEmployeeSummary> {
    const updated = await updateChatEmployeeAiEngine(employeeId, { default_ai_engine: defaultAiEngine });
    setEmployees((current) => current.map((employee) => (employee.id === updated.id ? updated : employee)));
    return updated;
  }

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={loadEmployees} />;

  return (
    <div className="relative h-[calc(100vh-8rem)] min-h-[34rem] overflow-hidden rounded-md border bg-background">
      <section className={cn("flex h-full min-w-0 flex-col transition-[padding] duration-200", selectedEmployee && "pr-[34rem]")}>
        <div className="border-b p-4">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <Users className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-base font-semibold">AI Employee Directory</h3>
              </div>
              <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
                Manage AI Team OS employees as digital employees: identity, mission, work record, skills, tools, knowledge, and AI Engine boundary.
              </p>
            </div>
            <Button type="button" variant="outline" onClick={() => navigateTo("chat")}>
              <MessageSquare className="h-4 w-4" />
              Ask Clara
            </Button>
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <StatCard icon={UserCheck} label="Employees" value={employees.length} />
            <StatCard icon={Clock3} label="Threads" value={aggregateThreadCount} />
            <StatCard icon={Activity} label="Messages" value={aggregateMessageCount} />
          </div>
        </div>

        <div className="border-b p-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex h-9 min-w-[14rem] flex-1 items-center gap-2 rounded-md border bg-background px-3">
              <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
              <input
                aria-label="Search employees"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search by name, role, skill, mission"
                className="h-full min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
              />
            </div>
            <Select
              aria-label="Role group"
              value={roleFilter}
              onChange={(event) => setRoleFilter(event.target.value)}
              className="w-[11rem]"
            >
              <option value="all">All roles</option>
              {roleGroups.map((group) => (
                <option key={group} value={group}>{group}</option>
              ))}
            </Select>
            <Select
              aria-label="AI Engine"
              value={aiEngineFilter}
              onChange={(event) => setAiEngineFilter(event.target.value)}
              className="w-[11rem]"
            >
              <option value="all">All engines</option>
              {aiEngineGroups.map((group) => (
                <option key={group} value={group}>{group}</option>
              ))}
            </Select>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {filteredEmployees.length === 0 ? (
            <div className="p-8 text-sm text-muted-foreground">No employees match the current filters.</div>
          ) : (
            <div className="divide-y">
              {filteredEmployees.map((employee) => {
                const active = selectedEmployee?.id === employee.id;
                const threads = threadsMap[employee.id] ?? null;
                const work = workMap[employee.id] ?? null;
                const latest = latestThread(threads);
                const currentTicket = work?.current_tickets?.[0] ?? null;
                const capabilities = capabilitiesForEmployee(employee, capabilityRegistry);
                const state = employeeState(employee, threads);
                return (
                  <button
                    key={employee.id}
                    type="button"
                    onClick={() => navigateTo("employees", employee.id)}
                    className={cn(
                      "grid w-full grid-cols-[minmax(16rem,1.35fr)_minmax(10rem,0.8fr)_minmax(12rem,1fr)_minmax(10rem,0.8fr)_auto] items-center gap-4 px-4 py-3 text-left transition-colors hover:bg-muted/70",
                      active && "bg-primary/10",
                    )}
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <EmployeeAvatar employee={employee} />
                      <div className="min-w-0">
                        <div className="flex min-w-0 items-center gap-2">
                          <span className="truncate font-medium">{employee.display_name}</span>
                          <Badge variant={state.variant} className="shrink-0 px-1.5 text-[10px]">{state.label}</Badge>
                        </div>
                        <div className="mt-0.5 truncate text-xs text-muted-foreground">{employee.role}</div>
                      </div>
                    </div>

                    <div className="min-w-0">
                      <div className="text-[10px] font-medium uppercase text-muted-foreground">Mission</div>
                      <div className="truncate text-sm">{employee.summary || "No mission configured."}</div>
                    </div>

                    <div className="min-w-0">
                      <div className="text-[10px] font-medium uppercase text-muted-foreground">Current signal</div>
                      <div className="truncate text-sm">
                        {currentTicket ? `${currentTicket.ticket_id} · ${currentTicket.title}` : latest?.title || "No recent thread"}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {currentTicket
                          ? `${currentTicket.status} · ${currentTicket.next_action || "ledger updated"}`
                          : latest ? `${latest.message_count} msgs · ${formatThreadTime(latest.last_message_at || latest.updated_at)}` : "Ready for delegation"}
                      </div>
                    </div>

                    <div className="min-w-0">
                      <div className="text-[10px] font-medium uppercase text-muted-foreground">Assets</div>
                      <div className="flex min-w-0 flex-wrap gap-1">
                        <Badge variant="secondary" className="px-1.5 text-[10px]">{employee.skills.length} skills</Badge>
                        <Badge variant="outline" className="px-1.5 text-[10px]">{capabilities.length} tools</Badge>
                        <Badge variant="outline" className="px-1.5 text-[10px]">{defaultAiEngineLabel(effectiveAiEngine(employee, aiEngines))}</Badge>
                      </div>
                    </div>

                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </section>

      {selectedEmployee && (
        <EmployeeDrawer
          aiEngines={aiEngines}
          capabilities={selectedCapabilities}
          employee={selectedEmployee}
          onDefaultEngineChange={handleDefaultEngineChange}
          threads={selectedThreads}
          work={selectedWork}
        />
      )}
    </div>
  );
}
