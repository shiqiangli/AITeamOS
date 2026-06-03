import { type ComponentType, useEffect, useMemo, useState } from "react";
import {
  ClipboardList,
  ExternalLink,
  FileText,
  MessageSquare,
  Plug,
  RefreshCw,
  ShieldCheck,
  UserCheck,
  Workflow,
} from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { ErrorState, LoadingState, navigateTo, Status } from "../../components/shared";
import { getMcpConnectorSettings, type McpConnectorSettingsResponse } from "../../api/mcp";
import { listWorkItems, type WorkItem, type WorkItemReport } from "../../api/work";
import { cn } from "@/lib/utils";

type WorkSection = "tickets" | "trace" | "reports";

const SECTIONS: { key: WorkSection; label: string; icon: ComponentType<{ className?: string }> }[] = [
  { key: "tickets", label: "Tickets", icon: ClipboardList },
  { key: "trace", label: "Flow Trace", icon: Workflow },
  { key: "reports", label: "Reports", icon: FileText },
];

function sectionFromRoute(value?: string | null): WorkSection {
  return SECTIONS.some((section) => section.key === value) ? value as WorkSection : "tickets";
}

function formatTime(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function statusVariant(status: string): "success" | "warning" | "danger" | "secondary" | "outline" {
  const normalized = status.toLowerCase();
  if (["validated", "done", "completed"].includes(normalized)) return "success";
  if (["blocked", "failed"].includes(normalized)) return "danger";
  if (["reported", "review", "pending"].includes(normalized)) return "warning";
  if (["assigned", "running", "active"].includes(normalized)) return "secondary";
  return "outline";
}

function assigneeLabel(item: WorkItem): string {
  return item.assigned_member_id || item.assigned_role || "Unassigned";
}

function validationLabel(item: WorkItem): string {
  return item.validation_member_id || item.validation_role || "Not set";
}

function planeHref(settings: McpConnectorSettingsResponse | null): string {
  return settings?.base_url?.trim() || "http://localhost:8082";
}

function PlaneOverview({ settings }: { settings: McpConnectorSettingsResponse | null }) {
  const configured = Boolean(settings?.configured);
  const enabled = Boolean(settings?.enabled);
  return (
    <section className="rounded-md border bg-background p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-muted">
            <Plug className="h-4 w-4 text-muted-foreground" />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-semibold">Plane Connector</h3>
              <Badge variant={enabled ? "success" : "outline"}>{enabled ? "enabled" : "disabled"}</Badge>
              <Badge variant={configured ? "success" : "warning"}>{configured ? "configured" : "not configured"}</Badge>
            </div>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">
              Plane remains the WorkItem and Page fact source. This page shows the AI team running view.
            </p>
          </div>
        </div>
        <a
          className="inline-flex h-8 items-center justify-center gap-2 rounded-md border border-input bg-background px-3 text-xs font-medium hover:bg-accent hover:text-accent-foreground"
          href={planeHref(settings)}
          target="_blank"
          rel="noreferrer"
        >
          <ExternalLink className="h-4 w-4" />
          Open Plane
        </a>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <Status label="Workspace" value={settings?.workspace_slug || "-"} />
        <Status label="Project" value={settings?.project_id || "-"} />
        <Status label="API token" value={settings?.api_token_configured ? "configured" : "missing"} tone={settings?.api_token_configured ? "ok" : "warn"} />
      </div>
    </section>
  );
}

function TicketRow({
  active,
  item,
  onSelect,
}: {
  active: boolean;
  item: WorkItem;
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
      <div className="grid gap-2 text-xs text-muted-foreground sm:grid-cols-3">
        <span className="truncate">Owner: {assigneeLabel(item)}</span>
        <span className="truncate">PV: {validationLabel(item)}</span>
        <span>{item.code_repository_ids.length} repos · {item.reports.length} reports</span>
      </div>
    </button>
  );
}

function DetailPanel({
  item,
  planeSettings,
}: {
  item: WorkItem | null;
  planeSettings: McpConnectorSettingsResponse | null;
}) {
  if (!item) {
    return (
      <section className="rounded-md border bg-background p-4">
        <div className="mb-3 flex items-center gap-2">
          <ClipboardList className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Ticket Detail</h3>
        </div>
        <p className="text-sm text-muted-foreground">No WorkItem selected.</p>
      </section>
    );
  }

  return (
    <section className="rounded-md border bg-background p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold">{item.title}</h3>
            <Badge variant={statusVariant(item.status)}>{item.status}</Badge>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{item.id}</p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={() => navigateTo("chat")}>
          <MessageSquare className="h-4 w-4" />
          Ask Clara
        </Button>
      </div>
      <div className="space-y-4 text-sm">
        <p className="whitespace-pre-wrap leading-6">{item.description}</p>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
          <Status label="Assignee" value={assigneeLabel(item)} />
          <Status label="Validation" value={validationLabel(item)} />
          <Status label="Updated" value={formatTime(item.updated_at)} />
          <Status label="Reports" value={item.reports.length} />
        </div>
        {item.knowledge_refs.length > 0 && (
          <div>
            <div className="text-xs uppercase text-muted-foreground">Knowledge refs</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {item.knowledge_refs.map((ref) => <Badge key={ref} variant="outline">{ref}</Badge>)}
            </div>
          </div>
        )}
        {item.code_repository_ids.length > 0 && (
          <div>
            <div className="text-xs uppercase text-muted-foreground">Code repositories</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {item.code_repository_ids.map((repoId) => <Badge key={repoId} variant="secondary">{repoId}</Badge>)}
            </div>
          </div>
        )}
        <div className="space-y-2">
          <div className="text-xs uppercase text-muted-foreground">Sources</div>
          <div className="rounded-md border bg-muted/30 p-3 text-xs leading-5 text-muted-foreground">
            Local P0 record: {item.saved_path || "-"}
            <br />
            Plane source: {planeSettings?.configured ? "configured for sync/deep links" : "configure Plane connector in Settings"}
          </div>
        </div>
      </div>
    </section>
  );
}

function TraceView({ item }: { item: WorkItem | null }) {
  if (!item) {
    return <EmptyWorkMessage title="No WorkItem selected" description="Select a ticket to inspect its Clara to Member flow." />;
  }

  const steps = [
    { label: "Clara", detail: item.source_thread_id ? `Source thread ${item.source_thread_id}` : "Created or selected the WorkItem" },
    { label: assigneeLabel(item), detail: "Member investigates, executes, and writes progress reports" },
    { label: validationLabel(item), detail: "PV validates evidence and reports result" },
    { label: "Clara", detail: "Summarizes reports and returns to the human user" },
  ];

  return (
    <section className="rounded-md border bg-background">
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

function ReportRow({ item, report }: { item: WorkItem; report: WorkItemReport }) {
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
        <span>{report.reporter_member_id || report.reporter_role || "unknown reporter"}</span>
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

function EmptyWorkMessage({ title, description }: { title: string; description: string }) {
  return (
    <section className="rounded-md border bg-background px-4 py-10 text-center">
      <h3 className="text-sm font-semibold">{title}</h3>
      <p className="mt-1 text-sm text-muted-foreground">{description}</p>
    </section>
  );
}

export function WorkPage({ selectedSection }: { selectedSection?: string | null }) {
  const [section, setSection] = useState<WorkSection>(() => sectionFromRoute(selectedSection));
  const [items, setItems] = useState<WorkItem[]>([]);
  const [planeSettings, setPlaneSettings] = useState<McpConnectorSettingsResponse | null>(null);
  const [selectedId, setSelectedId] = useState("");
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
  const activeCount = items.filter((item) => !["validated", "completed", "done"].includes(item.status.toLowerCase())).length;
  const validationCount = items.filter((item) => item.validation_member_id || item.validation_role).length;

  async function loadWork() {
    setLoading(true);
    setError(null);
    try {
      const loadedItems = await listWorkItems();
      setItems(loadedItems);
      setSelectedId((current) => loadedItems.some((item) => item.id === current) ? current : loadedItems[0]?.id ?? "");
      try {
        setPlaneSettings(await getMcpConnectorSettings("plane"));
      } catch {
        setPlaneSettings(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load work items");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadWork();
  }, []);

  if (loading) return <LoadingState />;

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <section className="space-y-4">
        <PlaneOverview settings={planeSettings} />

        <section className="rounded-md border bg-background">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
            <div className="flex items-center gap-2">
              <ClipboardList className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold">Work</h3>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" size="sm" onClick={() => void loadWork()}>
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
              <ErrorState message={error} onRetry={loadWork} />
            </div>
          )}

          <div className="flex flex-wrap gap-2 border-b px-4 py-3">
            {SECTIONS.map((entry) => {
              const Icon = entry.icon;
              return (
                <Button
                  key={entry.key}
                  type="button"
                  variant={section === entry.key ? "default" : "outline"}
                  size="sm"
                  onClick={() => navigateTo("work", entry.key)}
                >
                  <Icon className="h-4 w-4" />
                  {entry.label}
                </Button>
              );
            })}
          </div>

          {section === "tickets" && (
            items.length === 0 ? (
              <EmptyWorkMessage title="No local WorkItems" description="Ask Clara to create a WorkItem from Chat, then it will appear here." />
            ) : (
              <div>
                {items.map((item) => (
                  <TicketRow
                    key={item.id}
                    item={item}
                    active={selected?.id === item.id}
                    onSelect={() => setSelectedId(item.id)}
                  />
                ))}
              </div>
            )
          )}

          {section === "trace" && (
            <div className="p-4">
              <TraceView item={selected} />
            </div>
          )}

          {section === "reports" && (
            reports.length === 0 ? (
              <EmptyWorkMessage title="No reports yet" description="Member and PV reports written to WorkItems will appear here." />
            ) : (
              <div className="grid gap-3 p-4">
                {reports.map(({ item, report }) => (
                  <ReportRow key={report.id} item={item} report={report} />
                ))}
              </div>
            )
          )}
        </section>
      </section>

      <aside className="space-y-4">
        <section className="rounded-md border bg-background p-4">
          <div className="mb-3 flex items-center gap-2">
            <ClipboardList className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold">Status</h3>
          </div>
          <div className="space-y-3">
            <Status label="Local WorkItems" value={items.length} />
            <Status label="Active" value={activeCount} />
            <Status label="With validation" value={validationCount} />
            <Status label="With repo" value={items.filter((item) => item.code_repository_ids.length > 0).length} />
            <Status label="Reports" value={reports.length} />
          </div>
        </section>

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
          </div>
        </section>

        <DetailPanel item={selected} planeSettings={planeSettings} />
      </aside>
    </div>
  );
}
