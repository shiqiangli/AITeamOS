import { type ComponentType, useEffect, useMemo, useState } from "react";
import {
  Archive,
  ClipboardList,
  Database,
  FileText,
  GitBranch,
  MessageSquare,
  RefreshCw,
  ShieldCheck,
  UserCheck,
  Workflow,
} from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { ErrorState, LoadingState, Status, navigateTo } from "../../components/shared";
import { ResizableDetailLayout } from "../../components/resizable-layout";
import {
  getTicketBackendSettings,
  getTicketBackendStatus,
  listTickets,
  type Ticket,
  type TicketBackendSettings,
  type TicketBackendStatus,
  type TicketReport,
} from "../../api/tickets";
import { cn } from "@/lib/utils";

type TicketSection = "overview" | "flow" | "reports";
type TicketFilter = "all" | "active" | "review" | "blocked" | "done";

const SECTIONS: { key: TicketSection; label: string; icon: ComponentType<{ className?: string }> }[] = [
  { key: "overview", label: "Overview", icon: ClipboardList },
  { key: "flow", label: "Flow Trace", icon: Workflow },
  { key: "reports", label: "Reports", icon: FileText },
];

const FILTERS: { key: TicketFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "active", label: "Active" },
  { key: "review", label: "Review" },
  { key: "blocked", label: "Blocked" },
  { key: "done", label: "Done" },
];

function sectionFromRoute(value?: string | null): TicketSection {
  if (value === "tickets") return "overview";
  if (value === "trace") return "flow";
  return SECTIONS.some((section) => section.key === value) ? value as TicketSection : "overview";
}

function formatTime(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function statusVariant(status: string): "success" | "warning" | "danger" | "secondary" | "outline" {
  const normalized = status.toLowerCase();
  if (["validated", "done", "completed", "closed"].includes(normalized)) return "success";
  if (["blocked", "failed"].includes(normalized)) return "danger";
  if (["reported", "review", "pending", "pending_validation", "validation"].includes(normalized)) return "warning";
  if (["assigned", "running", "active"].includes(normalized)) return "secondary";
  return "outline";
}

function backendVariant(status?: string): "success" | "warning" | "danger" | "secondary" | "outline" {
  if (status === "ready") return "success";
  if (status === "planned") return "warning";
  if (status === "missing" || status === "failed") return "danger";
  return "secondary";
}

function assigneeLabel(item: Ticket): string {
  return item.assigned_employee_id || item.assigned_role || "Unassigned";
}

function validationLabel(item: Ticket): string {
  return item.validation_employee_id || item.validation_role || "Not set";
}

function ticketFilterForStatus(status: string): TicketFilter {
  const normalized = status.toLowerCase();
  if (["validated", "completed", "done", "closed"].includes(normalized)) return "done";
  if (["blocked", "failed"].includes(normalized)) return "blocked";
  if (["reported", "review", "pending_validation", "validation"].includes(normalized)) return "review";
  return "active";
}

function matchesTicketFilter(item: Ticket, filter: TicketFilter): boolean {
  if (filter === "all") return true;
  return ticketFilterForStatus(item.status) === filter;
}

function nextAction(item: Ticket): string {
  const normalized = item.status.toLowerCase();
  if (["validated", "completed", "done", "closed"].includes(normalized)) return "Ready for Clara summary";
  if (["blocked", "failed"].includes(normalized)) return "Needs human or Clara unblock";
  if (["reported", "review", "pending_validation", "validation"].includes(normalized)) return `PV review by ${validationLabel(item)}`;
  return `${assigneeLabel(item)} investigates and reports`;
}

function evidenceCount(item: Ticket): number {
  return item.reports.reduce((count, report) => count + report.evidence.length, 0);
}

function TicketRow({
  active,
  item,
  onSelect,
}: {
  active: boolean;
  item: Ticket;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "grid w-full gap-2 border-b px-4 py-3 text-left text-sm transition-colors last:border-b-0",
        active ? "bg-primary/10" : "hover:bg-muted/60",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="line-clamp-2 font-medium leading-5">{item.title}</div>
          <div className="mt-1 truncate text-xs text-muted-foreground">{item.id} · {formatTime(item.updated_at)}</div>
        </div>
        <Badge variant={statusVariant(item.status)}>{item.status}</Badge>
      </div>
      <div className="grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
        <span className="truncate">Owner: {assigneeLabel(item)}</span>
        <span className="truncate">PV: {validationLabel(item)}</span>
        <span className="truncate sm:col-span-2">Next: {nextAction(item)}</span>
      </div>
    </button>
  );
}

function TicketWorkspace({ item }: { item: Ticket | null }) {
  if (!item) {
    return (
      <section className="rounded-md border bg-background px-4 py-10 text-center">
        <h3 className="text-sm font-semibold">No Ticket selected</h3>
        <p className="mt-1 text-sm text-muted-foreground">Ask Clara to create a Ticket, then select it here.</p>
      </section>
    );
  }

  return (
    <section className="rounded-md border bg-background">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b px-4 py-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold">{item.title}</h3>
            <Badge variant={statusVariant(item.status)}>{item.status}</Badge>
          </div>
          <p className="mt-1 truncate text-xs text-muted-foreground">{item.id}</p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={() => navigateTo("chat", item.id)}>
          <MessageSquare className="h-4 w-4" />
          Ask Clara
        </Button>
      </div>
      <div className="space-y-4 p-4">
        <section className="rounded-md border bg-muted/20 p-3">
          <div className="mb-1 text-xs uppercase text-muted-foreground">Next action</div>
          <div className="text-sm font-medium">{nextAction(item)}</div>
        </section>

        <section>
          <div className="mb-1 text-xs uppercase text-muted-foreground">Description</div>
          <p className="whitespace-pre-wrap text-sm leading-6">{item.description}</p>
        </section>

        <div className="grid gap-3 md:grid-cols-2">
          <Status label="Owner" value={assigneeLabel(item)} />
          <Status label="Validation" value={validationLabel(item)} />
          <Status label="Reports" value={item.reports.length} />
          <Status label="Evidence" value={evidenceCount(item)} />
        </div>

        <section className="grid gap-3 lg:grid-cols-2">
          <AssetChips title="Knowledge refs" items={item.knowledge_refs} empty="No refs yet" />
          <AssetChips title="Code repositories" items={item.code_repository_ids} empty="No repos linked" variant="secondary" />
        </section>

        <TraceView item={item} compact />
      </div>
    </section>
  );
}

function AssetChips({
  empty,
  items,
  title,
  variant = "outline",
}: {
  empty: string;
  items: string[];
  title: string;
  variant?: "outline" | "secondary";
}) {
  return (
    <section className="rounded-md border p-3">
      <div className="mb-2 text-xs uppercase text-muted-foreground">{title}</div>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{empty}</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {items.map((item) => <Badge key={item} variant={variant}>{item}</Badge>)}
        </div>
      )}
    </section>
  );
}

function TraceView({ compact = false, item }: { compact?: boolean; item: Ticket | null }) {
  if (!item) {
    return <EmptyTicketMessage title="No Ticket selected" description="Select a Ticket to inspect its Clara to Employee flow." />;
  }

  const steps = [
    { label: "Clara", detail: item.source_thread_id ? `Source thread ${item.source_thread_id}` : "Created or selected the Ticket" },
    { label: assigneeLabel(item), detail: "Employee investigates, executes, and writes progress reports" },
    { label: validationLabel(item), detail: "PV validates evidence and reports result" },
    { label: "Clara", detail: "Summarizes reports and returns to the human user" },
  ];

  return (
    <section className={cn("rounded-md border bg-background", compact && "bg-transparent")}>
      <div className="border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Workflow className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Flow Trace</h3>
        </div>
      </div>
      <div className="divide-y">
        {steps.map((step, index) => (
          <div key={`${step.label}-${index}`} className="grid gap-2 px-4 py-4 sm:grid-cols-[2rem_minmax(0,1fr)]">
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
              {index + 1}
            </div>
            <div className="min-w-0">
              <div className="font-medium">{step.label}</div>
              <div className="mt-1 text-sm text-muted-foreground">{step.detail}</div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function ReportRow({ item, report }: { item: Ticket; report: TicketReport }) {
  return (
    <section className="rounded-md border bg-background p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
          <h4 className="truncate text-sm font-semibold">{item.title}</h4>
        </div>
        <Badge variant={report.report_type === "validation" ? "success" : "secondary"}>{report.report_type}</Badge>
      </div>
      <p className="text-sm leading-6">{report.content}</p>
      <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
        <span>{report.reporter_employee_id || report.reporter_role || "unknown reporter"}</span>
        <span>{formatTime(report.created_at)}</span>
        <span>{item.id}</span>
      </div>
      {report.evidence.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {report.evidence.map((entry) => <Badge key={entry} variant="outline">{entry}</Badge>)}
        </div>
      )}
    </section>
  );
}

function EmptyTicketMessage({ title, description }: { title: string; description: string }) {
  return (
    <section className="rounded-md border bg-background px-4 py-10 text-center">
      <h3 className="text-sm font-semibold">{title}</h3>
      <p className="mt-1 text-sm text-muted-foreground">{description}</p>
    </section>
  );
}

function BackendCard({
  backend,
  settings,
}: {
  backend: TicketBackendStatus | null;
  settings: TicketBackendSettings | null;
}) {
  return (
    <section className="rounded-md border bg-background p-4">
      <div className="mb-3 flex items-center gap-2">
        <Database className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold">Ticket Backend</h3>
      </div>
      <div className="space-y-3">
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline">{backend?.mode ?? settings?.mode ?? "-"}</Badge>
          <Badge variant={backendVariant(backend?.status)}>{backend?.status ?? "-"}</Badge>
        </div>
        <p className="text-sm leading-6 text-muted-foreground">
          {backend?.detail ?? "Ticket backend status is unavailable."}
        </p>
        <Status label="Tickets" value={backend?.ticket_count ?? 0} />
        <div className="min-w-0">
          <div className="text-xs uppercase text-muted-foreground">Local file</div>
          <div className="truncate text-sm font-medium" title={backend?.local_file_path ?? settings?.local_file_path}>
            {backend?.local_file_path ?? settings?.local_file_path ?? "-"}
          </div>
        </div>
        <Button type="button" variant="outline" size="sm" className="w-full" onClick={() => navigateTo("settings", "integrations")}>
          Settings
        </Button>
      </div>
    </section>
  );
}

function AssetGraphCard({ item }: { item: Ticket | null }) {
  return (
    <section className="rounded-md border bg-background p-4">
      <div className="mb-3 flex items-center gap-2">
        <Archive className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold">Ticket Asset Graph</h3>
      </div>
      {!item ? (
        <p className="text-sm text-muted-foreground">Select a Ticket to inspect linked assets.</p>
      ) : (
        <div className="space-y-3">
          <Status label="Knowledge refs" value={item.knowledge_refs.length} />
          <Status label="Reports" value={item.reports.length} />
          <Status label="Evidence" value={evidenceCount(item)} />
          <Status label="Repositories" value={item.code_repository_ids.length} />
          <Status label="Trace links" value={[item.source_thread_id, item.source_run_id].filter(Boolean).length} />
          <Status label="Decisions" value="0" />
          <div className="rounded-md border bg-muted/30 p-3 text-xs leading-5 text-muted-foreground">
            The graph view starts from local Ticket facts now. Graphiti remains the long-term memory graph; Ticket graph
            edges will be materialized from reports, decisions, memories, docs, and repository evidence as the flow grows.
          </div>
        </div>
      )}
    </section>
  );
}

export function TicketsPage({ selectedSection }: { selectedSection?: string | null }) {
  const [section, setSection] = useState<TicketSection>(() => sectionFromRoute(selectedSection));
  const [items, setItems] = useState<Ticket[]>([]);
  const [backend, setBackend] = useState<TicketBackendStatus | null>(null);
  const [backendSettings, setBackendSettings] = useState<TicketBackendSettings | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [filter, setFilter] = useState<TicketFilter>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSection(sectionFromRoute(selectedSection));
  }, [selectedSection]);

  const selected = items.find((item) => item.id === selectedId) ?? items[0] ?? null;
  const reports = useMemo(
    () => items.flatMap((item) => item.reports.map((report) => ({ item, report }))),
    [items],
  );
  const filteredItems = useMemo(
    () => items.filter((item) => matchesTicketFilter(item, filter)),
    [filter, items],
  );
  const activeCount = items.filter((item) => ticketFilterForStatus(item.status) === "active").length;
  const reviewCount = items.filter((item) => ticketFilterForStatus(item.status) === "review").length;
  const blockedCount = items.filter((item) => ticketFilterForStatus(item.status) === "blocked").length;
  const doneCount = items.filter((item) => ticketFilterForStatus(item.status) === "done").length;

  async function loadTickets() {
    setLoading(true);
    setError(null);
    try {
      const [loadedItems, loadedSettings, loadedBackend] = await Promise.all([
        listTickets(),
        getTicketBackendSettings(),
        getTicketBackendStatus(),
      ]);
      setItems(loadedItems);
      setBackendSettings(loadedSettings);
      setBackend(loadedBackend);
      setSelectedId((current) => loadedItems.some((item) => item.id === current) ? current : loadedItems[0]?.id ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load tickets");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadTickets();
  }, []);

  if (loading) return <LoadingState />;

  return (
    <ResizableDetailLayout
      id="aiteamos-tickets-layout"
      main={(
        <section className="space-y-4">
          <section className="rounded-md border bg-background">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
              <div className="flex items-center gap-2">
                <ClipboardList className="h-4 w-4 text-muted-foreground" />
                <div>
                  <h3 className="text-sm font-semibold">Ticket Cockpit</h3>
                  <p className="text-xs text-muted-foreground">Work ledger for Clara, Employees, PV validation, and generated assets.</p>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant={backendVariant(backend?.status)}>{backend?.mode ?? "backend"}</Badge>
                <Button type="button" variant="outline" size="sm" onClick={() => void loadTickets()}>
                  <RefreshCw className="h-4 w-4" />
                  Refresh
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={() => navigateTo("chat")}>
                  <MessageSquare className="h-4 w-4" />
                  Chat
                </Button>
              </div>
            </div>

            {error && (
              <div className="border-b p-4">
                <ErrorState message={error} onRetry={loadTickets} />
              </div>
            )}

            <div className="grid gap-3 border-b p-4 sm:grid-cols-2 xl:grid-cols-5">
              <Status label="Tickets" value={items.length} />
              <Status label="Active" value={activeCount} />
              <Status label="Review" value={reviewCount} />
              <Status label="Blocked" value={blockedCount} tone={blockedCount > 0 ? "warn" : undefined} />
              <Status label="Done" value={doneCount} />
            </div>

            <div className="flex flex-wrap gap-2 px-4 py-3">
              {SECTIONS.map((entry) => {
                const Icon = entry.icon;
                return (
                  <Button
                    key={entry.key}
                    type="button"
                    variant={section === entry.key ? "default" : "outline"}
                    size="sm"
                    onClick={() => navigateTo("tickets", entry.key)}
                  >
                    <Icon className="h-4 w-4" />
                    {entry.label}
                  </Button>
                );
              })}
            </div>
          </section>

          {section === "overview" && (
            <div className="grid gap-4 xl:grid-cols-[minmax(18rem,0.9fr)_minmax(0,1.1fr)]">
              <section className="rounded-md border bg-background">
                <div className="flex flex-wrap gap-2 border-b px-4 py-3">
                  {FILTERS.map((entry) => (
                    <Button
                      key={entry.key}
                      type="button"
                      variant={filter === entry.key ? "default" : "outline"}
                      size="sm"
                      onClick={() => setFilter(entry.key)}
                    >
                      {entry.label}
                    </Button>
                  ))}
                </div>
                {items.length === 0 ? (
                  <EmptyTicketMessage title="No local Tickets" description="Ask Clara to create a Ticket from Chat, then it will appear here." />
                ) : filteredItems.length === 0 ? (
                  <EmptyTicketMessage title="No matching Tickets" description="Try another status filter." />
                ) : (
                  filteredItems.map((item) => (
                    <TicketRow
                      key={item.id}
                      item={item}
                      active={selected?.id === item.id}
                      onSelect={() => setSelectedId(item.id)}
                    />
                  ))
                )}
              </section>
              <TicketWorkspace item={selected} />
            </div>
          )}

          {section === "flow" && <TraceView item={selected} />}

          {section === "reports" && (
            reports.length === 0 ? (
              <EmptyTicketMessage title="No reports yet" description="Employee and PV reports written to Tickets will appear here." />
            ) : (
              <div className="grid gap-3">
                {reports.map(({ item, report }) => (
                  <ReportRow key={report.id} item={item} report={report} />
                ))}
              </div>
            )
          )}
        </section>
      )}

      detail={(
        <aside className="space-y-4">
          <BackendCard backend={backend} settings={backendSettings} />

          <section className="rounded-md border bg-background p-4">
            <div className="mb-3 flex items-center gap-2">
              <UserCheck className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold">Ownership</h3>
            </div>
            <div className="space-y-3 text-sm">
              <div className="flex items-center gap-2">
                <UserCheck className="h-4 w-4 text-muted-foreground" />
                <span className="truncate">Owner: {selected ? assigneeLabel(selected) : "-"}</span>
              </div>
              <div className="flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-muted-foreground" />
                <span className="truncate">PV: {selected ? validationLabel(selected) : "-"}</span>
              </div>
              <div className="flex items-center gap-2">
                <GitBranch className="h-4 w-4 text-muted-foreground" />
                <span className="truncate">Repos: {selected?.code_repository_ids.length ?? 0}</span>
              </div>
            </div>
          </section>

          <AssetGraphCard item={selected} />
        </aside>
      )}
    />
  );
}
