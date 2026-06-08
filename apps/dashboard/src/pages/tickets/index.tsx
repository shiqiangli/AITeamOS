import { type ComponentType, useEffect, useMemo, useState } from "react";
import {
  Archive,
  BarChart3,
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
  getSelfBootstrapSummary,
  getTicketBackendSettings,
  getTicketBackendStatus,
  getTicketEvidenceRequirements,
  getTicketGraph,
  getTicketPerformance,
  listTicketAssets,
  listTickets,
  type SelfBootstrapLearningSummary,
  type Ticket,
  type TicketAssetRecord,
  type TicketBackendSettings,
  type TicketBackendStatus,
  type TicketEvent,
  type TicketEvidenceRequirements,
  type TicketPerformance,
  type TicketGraphProjection,
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

const QUALITY_SIGNAL_LABELS: Record<string, string> = {
  has_assignee: "Assignee",
  has_report: "Report",
  has_evidence: "Evidence",
  validation_requested: "Validation Requested",
  has_validation_report: "Validation Report",
  has_blocker: "Blocker",
  candidate_produced: "Candidate",
  used_recalled_asset: "Recalled Asset",
  graphiti_recall_recorded: "Graphiti Recall",
  provider_ref_recorded: "Provider Ref",
  missing_evidence: "Missing Evidence",
  waiting_report: "Waiting Report",
  waiting_validation: "Waiting Validation",
  blocked_or_failed: "Blocked Or Failed",
};

const WARNING_SIGNAL_KEYS = new Set(["has_blocker", "missing_evidence", "waiting_report", "waiting_validation", "blocked_or_failed"]);

function sectionFromRoute(value?: string | null): TicketSection {
  if (value === "tickets") return "overview";
  if (value === "trace") return "flow";
  return SECTIONS.some((section) => section.key === value) ? value as TicketSection : "overview";
}

function ticketIdFromRoute(value?: string | null): string {
  const trimmed = value?.trim() ?? "";
  if (!trimmed || trimmed === "tickets" || trimmed === "trace") return "";
  return SECTIONS.some((section) => section.key === trimmed) ? "" : trimmed;
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

function ticketEvents(item: Ticket): TicketEvent[] {
  return item.events ?? [];
}

function eventActor(event: TicketEvent): string {
  return event.actor?.id || event.actor?.role || "system";
}

function eventDetail(event: TicketEvent): string {
  const data = event.data ?? {};
  if (event.type === "created") return String(data.title || "Ticket created");
  if (event.type === "assigned") return `Assigned to ${String(data.assigned_employee_id || data.assigned_role || data.to_employee_id || data.to_role || "-")}`;
  if (event.type === "validation_requested") return `Validation by ${String(data.validation_employee_id || data.validation_role || data.to_employee_id || data.to_role || "-")}`;
  if (event.type === "status_changed") return `${String(data.from || "-")} -> ${String(data.to || data.status || "-")}`;
  if (event.type === "asset_linked") return `${String(data.target_kind || "asset")}: ${String(data.target_ref || "-")}`;
  if (event.type === "reported" || event.type === "validated" || event.type === "blocked") {
    const report = data.report && typeof data.report === "object" ? data.report as Record<string, unknown> : {};
    return String(report.content || `${event.type} report`);
  }
  return event.type;
}

function qualitySignalLabel(key: string): string {
  return QUALITY_SIGNAL_LABELS[key] ?? key.replace(/_/g, " ");
}

function qualitySignalValue(value: boolean | number | string): string {
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}

function qualitySignalVariant(key: string, value: boolean | number | string): "success" | "warning" | "secondary" | "outline" {
  if (typeof value === "boolean") {
    if (!value) return "outline";
    return WARNING_SIGNAL_KEYS.has(key) ? "warning" : "success";
  }
  if (typeof value === "number") return value > 0 ? "secondary" : "outline";
  return value ? "secondary" : "outline";
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

function TicketPerformanceCard({ item, performance }: { item: Ticket | null; performance: TicketPerformance | null }) {
  const metrics = [
    { label: "Reports", value: performance?.source_counts.reports ?? 0 },
    { label: "Evidence", value: performance?.source_counts.evidence ?? 0 },
    { label: "Candidates", value: performance?.source_counts.memory_candidates ?? 0 },
    { label: "Recalled Assets", value: performance?.source_counts.recalled_assets ?? 0 },
  ];
  const signals = Object.entries(performance?.quality_signals ?? {});
  return (
    <section className="rounded-md border bg-background p-4">
      <div className="mb-3 flex items-center gap-2">
        <BarChart3 className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold">Performance</h3>
      </div>
      {!item ? (
        <p className="text-sm text-muted-foreground">Select a Ticket to inspect contribution and quality signals.</p>
      ) : !performance ? (
        <p className="text-sm text-muted-foreground">Performance projection is unavailable for this Ticket.</p>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            {metrics.map((metric) => (
              <div key={metric.label} className="min-w-0">
                <div className="truncate text-xs text-muted-foreground">{metric.label}</div>
                <div className="text-xl font-semibold">{metric.value}</div>
              </div>
            ))}
          </div>

          <section>
            <h4 className="mb-2 text-sm font-semibold">Quality Signals</h4>
            <div className="flex flex-wrap gap-2">
              {signals.map(([key, value]) => (
                <Badge key={key} variant={qualitySignalVariant(key, value)}>
                  {qualitySignalLabel(key)}: {qualitySignalValue(value)}
                </Badge>
              ))}
            </div>
          </section>

          <section>
            <h4 className="mb-2 text-sm font-semibold">Contributors</h4>
            {performance.contribution.length === 0 ? (
              <p className="text-sm text-muted-foreground">No Employee contribution facts yet.</p>
            ) : (
              <div className="space-y-2">
                {performance.contribution.slice(0, 5).map((entry) => (
                  <div key={entry.employee_id} className="rounded-md border bg-muted/30 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium" title={entry.employee_id}>{entry.employee_id}</span>
                      <Badge variant={entry.validator ? "success" : entry.assigned ? "secondary" : "outline"}>
                        {entry.validator ? "validator" : entry.assigned ? "owner" : "contributor"}
                      </Badge>
                    </div>
                    {entry.role && <div className="mt-1 truncate text-xs text-muted-foreground" title={entry.role}>{entry.role}</div>}
                    <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-muted-foreground">
                      <span>Reports: {entry.report_count}</span>
                      <span>Evidence: {entry.evidence_count}</span>
                      <span>Candidates: {entry.candidate_count}</span>
                      <span>Recall: {entry.recalled_asset_count}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </section>
  );
}

function TicketEvidenceRequirementsCard({
  item,
  requirements,
}: {
  item: Ticket | null;
  requirements: TicketEvidenceRequirements | null;
}) {
  return (
    <section className="rounded-md border bg-background p-4">
      <div className="mb-3 flex items-center gap-2">
        <ShieldCheck className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold">Evidence Requirements</h3>
      </div>
      {!item ? (
        <p className="text-sm text-muted-foreground">Select a Ticket to inspect validation evidence requirements.</p>
      ) : !requirements ? (
        <p className="text-sm text-muted-foreground">Evidence requirements are unavailable for this Ticket.</p>
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline">{requirements.profile}</Badge>
            <Badge variant={requirements.satisfied ? "success" : "warning"}>
              {requirements.satisfied ? "satisfied" : "missing evidence"}
            </Badge>
            {requirements.evidence_refs.length > 0 && (
              <Badge variant="secondary">{requirements.evidence_refs.length} evidence refs</Badge>
            )}
          </div>
          {requirements.requirements.map((requirement) => (
            <div key={requirement.id} className="rounded-md border bg-muted/30 p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium" title={requirement.label}>{requirement.label}</span>
                <Badge variant={requirement.satisfied ? "success" : requirement.required ? "warning" : "outline"}>
                  {requirement.required ? "required" : "optional"}
                </Badge>
              </div>
              <div className="mt-1 text-xs text-muted-foreground">{requirement.satisfied ? "satisfied" : "not satisfied"}</div>
              {requirement.recommended_commands.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {requirement.recommended_commands.map((command) => (
                    <Badge key={command} variant="outline">{command}</Badge>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
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

  const events = ticketEvents(item);

  return (
    <section className={cn("rounded-md border bg-background", compact && "bg-transparent")}>
      <div className="border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Workflow className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Flow Trace</h3>
        </div>
      </div>
      <div className="divide-y">
        {events.length === 0 ? (
          <div className="px-4 py-4 text-sm text-muted-foreground">No event log is attached to this Ticket yet.</div>
        ) : events.map((event, index) => (
          <div key={event.event_id} className="grid gap-2 px-4 py-4 sm:grid-cols-[2rem_minmax(0,1fr)]">
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
              {index + 1}
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{event.type}</span>
                <Badge variant="outline">{eventActor(event)}</Badge>
                <span className="text-xs text-muted-foreground">{formatTime(event.at)}</span>
              </div>
              <div className="mt-1 line-clamp-3 text-sm text-muted-foreground">{eventDetail(event)}</div>
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
  const projectionPath =
    backend?.saved_paths?.plane_projection
    ?? settings?.saved_paths?.plane_projection
    ?? backend?.local_file_path
    ?? settings?.local_file_path;
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
          <div className="text-xs uppercase text-muted-foreground">Projection mirror</div>
          <div className="truncate text-sm font-medium" title={projectionPath}>
            {projectionPath ?? "-"}
          </div>
        </div>
        <Button type="button" variant="outline" size="sm" className="w-full" onClick={() => navigateTo("settings", "integrations")}>
          Settings
        </Button>
      </div>
    </section>
  );
}

function SelfBootstrapSummaryCard({ summary }: { summary: SelfBootstrapLearningSummary | null }) {
  const topTicket = summary?.tickets.find((ticket) => ticket.missing_required_evidence > 0 || ticket.blocked_or_failed)
    ?? summary?.tickets[0]
    ?? null;
  return (
    <section className="rounded-md border bg-background p-4">
      <div className="mb-3 flex items-center gap-2">
        <GitBranch className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold">Self-Bootstrap</h3>
      </div>
      {!summary ? (
        <p className="text-sm text-muted-foreground">Self-bootstrap summary is unavailable.</p>
      ) : (
        <div className="space-y-3">
          <p className="text-sm leading-6 text-muted-foreground">{summary.summary}</p>
          <div className="grid grid-cols-2 gap-3">
            <Status label="Tickets" value={summary.ticket_count} />
            <Status label="Validated" value={summary.validated_ticket_count} />
            <Status label="Candidates" value={summary.memory_candidates_produced} />
            <Status label="Recalled" value={summary.approved_memories_recalled} />
            <Status label="Useful recall" value={summary.useful_memory_recalls} />
            <Status label="Needs evidence" value={summary.tickets_missing_required_evidence} />
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant={summary.graphiti_memories_recalled > 0 ? "success" : "outline"}>
              Graphiti recall: {summary.graphiti_memories_recalled}
            </Badge>
            <Badge variant={summary.blocked_ticket_count > 0 ? "warning" : "outline"}>
              Blocked: {summary.blocked_ticket_count}
            </Badge>
            <Badge variant={summary.stale_or_superseded_assets > 0 ? "warning" : "outline"}>
              Stale: {summary.stale_or_superseded_assets}
            </Badge>
          </div>
          {topTicket && (
            <div className="rounded-md border bg-muted/30 p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium" title={topTicket.title}>{topTicket.ticket_id}</span>
                <Badge variant={statusVariant(topTicket.status)}>{topTicket.status}</Badge>
              </div>
              <p className="mt-2 line-clamp-3 text-xs leading-5 text-muted-foreground">{topTicket.next_learning_action}</p>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function metadataString(metadata: Record<string, unknown>, key: string): string {
  const value = metadata[key];
  return typeof value === "string" ? value : "";
}

function AssetGraphCard({ item, assets, graph }: { item: Ticket | null; assets: TicketAssetRecord[]; graph: TicketGraphProjection | null }) {
  const linkedAssets = item ? assets.filter((asset) => asset.source_ticket_id === item.id) : [];
  const memoryCandidateAssets = linkedAssets.filter((asset) => asset.kind === "memory_candidate");
  const recalledMemoryAssets = linkedAssets.filter((asset) => asset.kind === "memory" && asset.status === "approved");
  const groupedEdges = graph ? Object.entries(graph.grouped_edges).filter(([, edges]) => edges.length > 0) : [];
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
          <Status label="Events" value={ticketEvents(item).length} />
          <Status label="Graph edges" value={graph?.edges.length ?? 0} />
          <Status label="Memory candidates" value={memoryCandidateAssets.length} />
          {memoryCandidateAssets.length > 0 && (
            <div className="space-y-2">
              {memoryCandidateAssets.slice(0, 3).map((asset) => (
                <div key={asset.id} className="rounded-md border bg-muted/30 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-medium" title={asset.title}>{asset.title}</span>
                    <Badge variant={statusVariant(asset.status)}>{asset.status}</Badge>
                  </div>
                  <div className="mt-1 truncate text-xs text-muted-foreground" title={metadataString(asset.metadata, "source_trace_path") || asset.id}>
                    Trace: {metadataString(asset.metadata, "source_trace_path") || "-"}
                  </div>
                </div>
              ))}
            </div>
          )}
          <Status label="Approved memories used" value={recalledMemoryAssets.length} />
          {recalledMemoryAssets.length > 0 && (
            <div className="space-y-2">
              {recalledMemoryAssets.slice(0, 3).map((asset) => {
                const derivedFrom = metadataString(asset.metadata, "derived_from_ticket_id");
                const usefulness = metadataString(asset.metadata, "usefulness_status") || "unreviewed";
                return (
                  <div key={asset.id} className="rounded-md border bg-muted/30 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium" title={asset.title}>{asset.title}</span>
                      <Badge variant={usefulness === "useful" ? "success" : "outline"}>{usefulness}</Badge>
                    </div>
                    <div className="mt-1 truncate text-xs text-muted-foreground" title={derivedFrom || asset.id}>
                      Source: {derivedFrom || asset.id}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
          {groupedEdges.length > 0 && (
            <div>
              <h4 className="mb-2 text-sm font-semibold">Grouped Edges</h4>
              <div className="space-y-2">
                {groupedEdges.slice(0, 6).map(([edgeType, edges]) => (
                  <div key={edgeType} className="rounded-md border bg-muted/30 p-3">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <span className="truncate text-xs font-medium text-foreground" title={edgeType}>{edgeType}</span>
                      <Badge variant="outline">{edges.length}</Badge>
                    </div>
                    <div className="space-y-1">
                      {edges.slice(0, 3).map((edge) => (
                        <div key={edge.id} className="truncate text-xs text-muted-foreground" title={`${edge.source_id} -> ${edge.target_id}`}>
                          {edge.source_id} -&gt; {edge.target_id}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div className="rounded-md border bg-muted/30 p-3 text-xs leading-5 text-muted-foreground">
            Local graph facts are projected from Ticket events, reports, evidence, approved Memory usage, repositories, and Knowledge refs.
            Graphiti remains the long-term memory graph.
          </div>
        </div>
      )}
    </section>
  );
}

export function TicketsPage({ selectedSection }: { selectedSection?: string | null }) {
  const [section, setSection] = useState<TicketSection>(() => sectionFromRoute(selectedSection));
  const [items, setItems] = useState<Ticket[]>([]);
  const [ticketAssets, setTicketAssets] = useState<TicketAssetRecord[]>([]);
  const [ticketGraph, setTicketGraph] = useState<TicketGraphProjection | null>(null);
  const [ticketPerformance, setTicketPerformance] = useState<TicketPerformance | null>(null);
  const [ticketEvidenceRequirements, setTicketEvidenceRequirements] = useState<TicketEvidenceRequirements | null>(null);
  const [selfBootstrapSummary, setSelfBootstrapSummary] = useState<SelfBootstrapLearningSummary | null>(null);
  const [backend, setBackend] = useState<TicketBackendStatus | null>(null);
  const [backendSettings, setBackendSettings] = useState<TicketBackendSettings | null>(null);
  const [selectedId, setSelectedId] = useState(() => ticketIdFromRoute(selectedSection));
  const [filter, setFilter] = useState<TicketFilter>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSection(sectionFromRoute(selectedSection));
    const routeTicketId = ticketIdFromRoute(selectedSection);
    if (routeTicketId) setSelectedId(routeTicketId);
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
      const [loadedItems, loadedAssets, loadedSettings, loadedBackend, loadedSelfBootstrapSummary] = await Promise.all([
        listTickets(),
        listTicketAssets(),
        getTicketBackendSettings(),
        getTicketBackendStatus(),
        getSelfBootstrapSummary(),
      ]);
      setItems(loadedItems);
      setTicketAssets(loadedAssets);
      setBackendSettings(loadedSettings);
      setBackend(loadedBackend);
      setSelfBootstrapSummary(loadedSelfBootstrapSummary);
      setSelectedId((current) => {
        const routeTicketId = ticketIdFromRoute(selectedSection);
        if (routeTicketId && loadedItems.some((item) => item.id === routeTicketId)) return routeTicketId;
        return loadedItems.some((item) => item.id === current) ? current : loadedItems[0]?.id ?? "";
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load tickets");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadTickets();
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!selected?.id) {
      setTicketGraph(null);
      setTicketPerformance(null);
      setTicketEvidenceRequirements(null);
      return () => { cancelled = true; };
    }
    Promise.all([
      getTicketGraph(selected.id),
      getTicketPerformance(selected.id),
      getTicketEvidenceRequirements(selected.id),
    ])
      .then(([projection, performance, evidenceRequirements]) => {
        if (!cancelled) {
          setTicketGraph(projection);
          setTicketPerformance(performance);
          setTicketEvidenceRequirements(evidenceRequirements);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setTicketGraph(null);
          setTicketPerformance(null);
          setTicketEvidenceRequirements(null);
        }
      });
    return () => { cancelled = true; };
  }, [selected?.id]);

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

          <SelfBootstrapSummaryCard summary={selfBootstrapSummary} />

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

          <TicketEvidenceRequirementsCard item={selected} requirements={ticketEvidenceRequirements} />

          <TicketPerformanceCard item={selected} performance={ticketPerformance} />

          <AssetGraphCard item={selected} assets={ticketAssets} graph={ticketGraph} />
        </aside>
      )}
    />
  );
}
