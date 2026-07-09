import { type ComponentType, useEffect, useMemo, useState } from "react";
import {
  Activity,
  Archive,
  BarChart3,
  ClipboardList,
  Database,
  FileText,
  GitBranch,
  MessageSquare,
  PlayCircle,
  RefreshCw,
  ShieldCheck,
  UserCheck,
  Workflow,
} from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { ErrorState, LoadingState, Status, navigateTo } from "../../components/shared";
import { ResizableDetailLayout } from "../../components/resizable-layout";
import { getSystemStatus, type SystemStatusResponse } from "../../api/systemStatus";
import {
  controlTicketLoop,
  getSelfBootstrapSummary,
  getTicketBackendSettings,
  getTicketBackendStatus,
  getTicketEvidenceRequirements,
  getTicketGraph,
  getTicketLoopRun,
  getTicketPerformance,
  getTicketRuntimeEvidence,
  listTicketAssets,
  listTicketLoopQueue,
  listTicketLoopRuns,
  listTickets,
  getTicketLoopQueueStatus,
  getTicketLoopQueueWorkerStatus,
  getTicketLoopTimeline,
  pumpTicketLoopQueue,
  proposeTicketCloseoutCandidates,
  proposeTicketFailureRetrospectiveCandidates,
  resumeTicketLoop,
  runTicketLoop,
  settleTicketCloseout,
  startTicketLoopQueueWorker,
  stopTicketLoopQueueWorker,
  tickTicketLoopQueueWorker,
  type SelfBootstrapLearningSummary,
  type Ticket,
  type TicketAssetRecord,
  type TicketBackendSettings,
  type TicketBackendStatus,
  type TicketCloseoutAssetCandidateResponse,
  type TicketCloseoutSettlementResponse,
  type TicketEvent,
  type TicketEvidenceRequirements,
  type TicketFailureRetrospectiveAssetCandidateResponse,
  type TicketLoopControlResponse,
  type TicketLoopQueueItem,
  type TicketLoopQueuePumpResponse,
  type TicketLoopQueueStatus,
  type TicketLoopQueueWorkerStatus,
  type TicketLoopQueueWorkerTickResponse,
  type TicketLoopApprovalResumeState,
  type TicketLoopQueueReliability,
  type TicketLoopRunRecord,
  type TicketLoopRunResponse,
  type TicketLoopResumeResponse,
  type TicketLoopRetryRequirement,
  type TicketLoopTimelineItem,
  type TicketLoopTimelineResponse,
  type TicketPerformance,
  type TicketGraphProjection,
  type TicketReport,
  type TicketRuntimeEvidence,
} from "../../api/tickets";
import { cn } from "@/lib/utils";

type TicketSection = "overview" | "flow" | "reports" | "queue";
type TicketFilter = "all" | "active" | "review" | "blocked" | "done";

interface TicketRouteFocus {
  ticketId: string;
  reportId: string;
  evidenceReportId: string;
  evidenceIndex: number | null;
}

const SECTIONS: { key: TicketSection; label: string; icon: ComponentType<{ className?: string }> }[] = [
  { key: "overview", label: "Overview", icon: ClipboardList },
  { key: "flow", label: "Flow Trace", icon: Workflow },
  { key: "reports", label: "Reports", icon: FileText },
  { key: "queue", label: "Queue", icon: Workflow },
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
  const [section] = (value?.trim() ?? "").split("/").filter(Boolean);
  if (section === "tickets") return "overview";
  if (section === "trace") return "flow";
  return SECTIONS.some((entry) => entry.key === section) ? section as TicketSection : "overview";
}

function ticketIdFromRoute(value?: string | null): string {
  const trimmed = value?.trim() ?? "";
  if (!trimmed) return "";
  const parts = trimmed.split("/").filter(Boolean);
  if (parts.length > 1 && (parts[0] === "tickets" || parts[0] === "overview" || parts[0] === "trace" || SECTIONS.some((section) => section.key === parts[0]))) {
    return routeFocusFromSegment(parts[1]).ticketId;
  }
  if (trimmed === "tickets" || trimmed === "trace") return "";
  return SECTIONS.some((section) => section.key === trimmed) ? "" : trimmed;
}

function routeFocusFromRoute(value?: string | null): TicketRouteFocus {
  const parts = (value?.trim() ?? "").split("/").filter(Boolean);
  if (parts.length < 2) return { ticketId: "", reportId: "", evidenceReportId: "", evidenceIndex: null };
  return routeFocusFromSegment(parts[1]);
}

function routeFocusFromSegment(segment?: string | null): TicketRouteFocus {
  const [ticketId = "", kind = "", reportId = "", evidenceIndex = ""] = (segment ?? "").split("::");
  if (kind === "report") {
    return { ticketId, reportId, evidenceReportId: "", evidenceIndex: null };
  }
  if (kind === "evidence") {
    const parsedIndex = Number.parseInt(evidenceIndex, 10);
    return { ticketId, reportId: "", evidenceReportId: reportId, evidenceIndex: Number.isNaN(parsedIndex) ? null : parsedIndex };
  }
  return { ticketId: segment ?? "", reportId: "", evidenceReportId: "", evidenceIndex: null };
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
  if (["reported", "review", "pending", "pending_validation", "validation", "waiting_approval", "waiting_changes", "waiting_evidence", "waiting_validation"].includes(normalized)) return "warning";
  if (["assigned", "running", "active", "in_progress", "ready_to_resume"].includes(normalized)) return "secondary";
  return "outline";
}

function closeoutSettlementVariant(status: string): "success" | "warning" | "danger" | "secondary" | "outline" {
  const normalized = status.toLowerCase();
  if (["approved", "projected"].includes(normalized)) return "success";
  if (normalized === "blocked") return "danger";
  if (normalized === "proposed") return "warning";
  return "secondary";
}

function readinessVariant(status?: string | null): "success" | "warning" | "danger" | "secondary" | "outline" {
  const normalized = (status ?? "").toLowerCase();
  if (["ready", "passed", "completed", "open"].includes(normalized)) return "success";
  if (["blocked", "setup_blocked", "disabled", "confirmation_required", "not_run"].includes(normalized)) return "warning";
  if (["failed", "error"].includes(normalized)) return "danger";
  return normalized ? "secondary" : "outline";
}

function compactStatus(value?: string | null): string {
  const text = (value ?? "").trim();
  return text ? text.replace(/_/g, " ") : "-";
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function recordArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(recordValue).filter((item) => Object.keys(item).length > 0) : [];
}

function textValue(value: unknown, fallback = ""): string {
  if (value === null || value === undefined || value === "") return fallback;
  return typeof value === "string" ? value : String(value);
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => textValue(item)).filter(Boolean) : [];
}

function compactJson(value: Record<string, unknown> | unknown[]): string {
  if (Array.isArray(value) ? value.length === 0 : Object.keys(value).length === 0) return "{}";
  return JSON.stringify(value, null, 2);
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
  if (["reported", "review", "pending_validation", "validation", "waiting_approval", "waiting_changes", "waiting_evidence", "waiting_validation", "ready_to_resume"].includes(normalized)) return "review";
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
  if (normalized === "waiting_approval") return "Approval review required";
  if (normalized === "ready_to_resume") return "Resume governed loop";
  if (normalized === "waiting_changes") return "Attach requested changes";
  if (normalized === "waiting_evidence") return "Attach evidence";
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

function runtimeGovernanceString(evidence: TicketRuntimeEvidence | null, key: string): string {
  const value = evidence?.governance_state[key];
  return typeof value === "string" ? value : "";
}

function runtimeGovernanceNumber(evidence: TicketRuntimeEvidence | null, key: string): number {
  const value = evidence?.governance_state[key];
  return typeof value === "number" ? value : 0;
}

function runtimeIssueLabel(reason: string): string {
  return reason.replace(/_/g, " ");
}

function TicketRuntimeEvidenceCard({ item, evidence }: { item: Ticket | null; evidence: TicketRuntimeEvidence | null }) {
  const latest = evidence?.latest_loop_run ?? null;
  const providerName = evidence?.provider_state.provider || evidence?.provider_state.mode || "-";
  const providerStatus = evidence?.provider_state.status || "-";
  const queueStatus = runtimeGovernanceString(evidence, "queue_reliability_status");
  const nextTimelineAction = runtimeGovernanceString(evidence, "next_action");
  const metrics = [
    { label: "Reports", value: evidence?.source_counts.reports ?? 0 },
    { label: "Evidence", value: evidence?.source_counts.evidence ?? 0 },
    { label: "Graph Edges", value: evidence?.source_counts.graph_edges ?? 0 },
    { label: "Loop Count", value: evidence?.source_counts.loop_runs ?? 0 },
  ];
  return (
    <section className="rounded-md border bg-background p-4">
      <div className="mb-3 flex items-center gap-2">
        <Activity className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold">Runtime Evidence</h3>
      </div>
      {!item ? (
        <p className="text-sm text-muted-foreground">Select a Ticket to inspect runtime evidence.</p>
      ) : !evidence ? (
        <p className="text-sm text-muted-foreground">Runtime evidence is unavailable for this Ticket.</p>
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

          <div className="rounded-md border bg-muted/30 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="text-sm font-medium">Latest run: {latest?.status || "not recorded"}</div>
                <div className="mt-1 truncate text-xs text-muted-foreground" title={latest?.run_id || ""}>
                  {latest?.run_id ? "Latest loop run recorded" : "No governed loop run"}
                </div>
              </div>
              {latest?.session_key ? (
                <Button type="button" variant="outline" size="sm" onClick={() => navigateTo("runtime", latest.session_key)}>
                  <PlayCircle className="h-4 w-4" />
                  Latest Replay
                </Button>
              ) : null}
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {latest?.stop_reason ? <Badge variant="outline">Latest stop {latest.stop_reason}</Badge> : null}
              {latest?.step_count ? <Badge variant="secondary">{latest.step_count} steps</Badge> : null}
              {latest?.session_key ? <Badge variant="outline">Session linked</Badge> : null}
            </div>
          </div>

          <div className="space-y-2 text-sm">
            <div className="flex flex-wrap gap-2">
              <Badge variant={evidence.provider_state.provider_ref_recorded ? "success" : "warning"}>
                Provider ref {evidence.provider_state.provider_ref_recorded ? "recorded" : "missing"}
              </Badge>
              <Badge variant={providerStatus === "ready" ? "success" : "warning"}>Provider: {providerName} {providerStatus}</Badge>
              {queueStatus ? <Badge variant={queueStatus === "healthy" ? "success" : "warning"}>Queue {queueStatus}</Badge> : null}
              {runtimeGovernanceNumber(evidence, "approval_resume_count") > 0 ? (
                <Badge variant="secondary">Approvals {runtimeGovernanceNumber(evidence, "approval_resume_count")}</Badge>
              ) : null}
              {runtimeGovernanceNumber(evidence, "retry_requirement_count") > 0 ? (
                <Badge variant="warning">Retry checks {runtimeGovernanceNumber(evidence, "retry_requirement_count")}</Badge>
              ) : null}
              <Badge variant="outline">Handoffs {evidence.source_counts.handoffs ?? 0}</Badge>
            </div>
            {nextTimelineAction ? <p className="text-xs text-muted-foreground">{nextTimelineAction}</p> : null}
          </div>

          {evidence.blockers.length > 0 ? (
            <section>
              <h4 className="mb-2 text-sm font-semibold">Runtime Blockers</h4>
              <div className="flex flex-wrap gap-2">
                {evidence.blockers.map((blocker, index) => (
                  <Badge key={`${blocker.reason}-${index}`} variant="warning">
                    {runtimeIssueLabel(blocker.reason || "blocker")}
                  </Badge>
                ))}
              </div>
            </section>
          ) : null}

          {evidence.gaps.length > 0 ? (
            <section>
              <h4 className="mb-2 text-sm font-semibold">Runtime Gaps</h4>
              <div className="flex flex-wrap gap-2">
                {evidence.gaps.map((gap, index) => (
                  <Badge key={`${gap.reason}-${index}`} variant="outline">
                    {runtimeIssueLabel(gap.reason || "gap")}
                  </Badge>
                ))}
              </div>
            </section>
          ) : null}
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

function TicketWorkspace({
  closeoutError,
  closeoutResult,
  closeoutSettlementError,
  closeoutSettlementResult,
  controlError,
  controlResult,
  controllingLoopAction,
  item,
  loopError,
  loopRunDetail,
  loopRunDetailError,
  loopResult,
  loopRuns,
  loadingLoopRunId,
  failureRetrospectiveError,
  failureRetrospectiveResult,
  onControlLoop,
  onProposeFailureRetrospective,
  onProposeCloseout,
  onResumeLoop,
  onSelectLoopRun,
  onRunLoop,
  onSettleCloseout,
  proposingCloseout,
  proposingFailureRetrospective,
  resumeError,
  resumeResult,
  resumingLoop,
  runningLoop,
  settlingCloseout,
  timeline,
}: {
  closeoutError: string | null;
  closeoutResult: TicketCloseoutAssetCandidateResponse | null;
  closeoutSettlementError: string | null;
  closeoutSettlementResult: TicketCloseoutSettlementResponse | null;
  controlError: string | null;
  controlResult: TicketLoopControlResponse | null;
  controllingLoopAction: string;
  item: Ticket | null;
  loopError: string | null;
  loopRunDetail: TicketLoopRunRecord | null;
  loopRunDetailError: string | null;
  loopResult: TicketLoopRunResponse | null;
  loopRuns: TicketLoopRunRecord[];
  loadingLoopRunId: string;
  failureRetrospectiveError: string | null;
  failureRetrospectiveResult: TicketFailureRetrospectiveAssetCandidateResponse | null;
  onControlLoop: (item: Ticket, action: "stop" | "pause" | "continue" | "cancel") => void;
  onProposeFailureRetrospective: (item: Ticket) => void;
  onProposeCloseout: (item: Ticket) => void;
  onResumeLoop: (item: Ticket, action: "resume" | "retry_after_changes" | "retry_after_evidence") => void;
  onSelectLoopRun: (item: Ticket, runId: string) => void;
  onRunLoop: (item: Ticket) => void;
  onSettleCloseout: (item: Ticket) => void;
  proposingCloseout: boolean;
  proposingFailureRetrospective: boolean;
  resumeError: string | null;
  resumeResult: TicketLoopResumeResponse | null;
  resumingLoop: boolean;
  runningLoop: boolean;
  settlingCloseout: boolean;
  timeline: TicketLoopTimelineResponse | null;
}) {
  if (!item) {
    return (
      <section className="rounded-md border bg-background px-4 py-10 text-center">
        <h3 className="text-sm font-semibold">No Ticket selected</h3>
        <p className="mt-1 text-sm text-muted-foreground">Ask Clara to create a Ticket, then select it here.</p>
      </section>
    );
  }
  const resumeAction: "resume" | "retry_after_changes" | "retry_after_evidence" =
    item.status === "waiting_changes"
      ? "retry_after_changes"
      : item.status === "waiting_evidence"
        ? "retry_after_evidence"
        : "resume";
  const canResume = Boolean(timeline?.summary.can_resume);

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
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" disabled={!canResume || resumingLoop} onClick={() => onResumeLoop(item, resumeAction)}>
            <RefreshCw className="h-4 w-4" />
            {resumingLoop ? "Queueing" : item.status === "ready_to_resume" ? "Resume Loop" : "Retry Loop"}
          </Button>
          <Button type="button" variant="outline" size="sm" disabled={runningLoop} onClick={() => onRunLoop(item)}>
            <Workflow className="h-4 w-4" />
            {runningLoop ? "Running" : "Run Loop"}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={runningLoop || Boolean(controllingLoopAction)}
            onClick={() => onControlLoop(item, "continue")}
          >
            <RefreshCw className="h-4 w-4" />
            {controllingLoopAction === "continue" ? "Continuing" : "Continue Loop"}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={Boolean(controllingLoopAction)}
            onClick={() => onControlLoop(item, "pause")}
          >
            <ShieldCheck className="h-4 w-4" />
            {controllingLoopAction === "pause" ? "Pausing" : "Pause Loop"}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={Boolean(controllingLoopAction)}
            onClick={() => onControlLoop(item, "stop")}
          >
            <ShieldCheck className="h-4 w-4" />
            {controllingLoopAction === "stop" ? "Stopping" : "Stop Loop"}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={Boolean(controllingLoopAction)}
            onClick={() => onControlLoop(item, "cancel")}
          >
            <ShieldCheck className="h-4 w-4" />
            {controllingLoopAction === "cancel" ? "Cancelling" : "Cancel Loop"}
          </Button>
          <Button type="button" variant="outline" size="sm" disabled={proposingCloseout} onClick={() => onProposeCloseout(item)}>
            <Archive className="h-4 w-4" />
            {proposingCloseout ? "Proposing" : "Closeout Assets"}
          </Button>
          <Button type="button" variant="outline" size="sm" disabled={settlingCloseout} onClick={() => onSettleCloseout(item)}>
            <Database className="h-4 w-4" />
            {settlingCloseout ? "Settling" : "Settle Closeout"}
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => navigateTo("chat", item.id)}>
            <MessageSquare className="h-4 w-4" />
            Ask Clara
          </Button>
        </div>
      </div>
      <div className="space-y-4 p-4">
        {(resumeResult && resumeResult.ticket_id === item.id) || resumeError ? (
          <section className="rounded-md border bg-muted/20 p-3">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <div className="text-xs uppercase text-muted-foreground">Loop Resume</div>
              {resumeResult && resumeResult.ticket_id === item.id ? (
                <Badge variant="secondary">{resumeResult.status}</Badge>
              ) : null}
            </div>
            {resumeError ? (
              <p className="text-sm text-orange-600">{resumeError}</p>
            ) : resumeResult && resumeResult.ticket_id === item.id ? (
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">{resumeResult.detail}</p>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">From {resumeResult.previous_status}</Badge>
                  <Badge variant="secondary">Queued {resumeResult.queue_item.run_id}</Badge>
                </div>
              </div>
            ) : null}
          </section>
        ) : null}

        {timeline?.summary.waiting_reason ? (
          <section className="rounded-md border bg-muted/20 p-3">
            <div className="mb-1 text-xs uppercase text-muted-foreground">Timeline Next Action</div>
            <div className="text-sm font-medium">{timeline.summary.next_action}</div>
            <p className="mt-1 text-sm text-muted-foreground">{timeline.summary.waiting_reason}</p>
          </section>
        ) : null}

        <RetryPreflightCard requirements={timeline?.summary.retry_requirements ?? []} />

        <RuntimeApprovalResumeCard approvals={timeline?.summary.approval_resume ?? []} />
        <QueueReliabilityCard
          reliability={timeline?.summary.queue_reliability ?? null}
          onProposeFailureRetrospective={() => onProposeFailureRetrospective(item)}
          proposingFailureRetrospective={proposingFailureRetrospective}
        />

        {(failureRetrospectiveResult && failureRetrospectiveResult.ticket_id === item.id) || failureRetrospectiveError ? (
          <section className="rounded-md border bg-muted/20 p-3">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <div className="text-xs uppercase text-muted-foreground">Failure Retrospective</div>
              {failureRetrospectiveResult && failureRetrospectiveResult.ticket_id === item.id ? (
                <Badge variant={failureRetrospectiveResult.status === "proposed" ? "success" : "secondary"}>{failureRetrospectiveResult.status}</Badge>
              ) : null}
            </div>
            {failureRetrospectiveError ? (
              <p className="text-sm text-orange-600">{failureRetrospectiveError}</p>
            ) : failureRetrospectiveResult && failureRetrospectiveResult.ticket_id === item.id ? (
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">{failureRetrospectiveResult.detail}</p>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">{failureRetrospectiveResult.failed_item_count} failed items</Badge>
                  {failureRetrospectiveResult.candidates.map((candidate) => (
                    <Badge key={candidate.id} variant="outline">{candidate.asset_type}</Badge>
                  ))}
                  {failureRetrospectiveResult.report_id ? <Badge variant="secondary">Report {failureRetrospectiveResult.report_id}</Badge> : null}
                </div>
              </div>
            ) : null}
          </section>
        ) : null}

        {(controlResult && controlResult.ticket_id === item.id) || controlError ? (
          <section className="rounded-md border bg-muted/20 p-3">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <div className="text-xs uppercase text-muted-foreground">Loop Control</div>
              {controlResult && controlResult.ticket_id === item.id ? (
                <Badge variant={controlResult.state.active ? "warning" : "success"}>{controlResult.state.status}</Badge>
              ) : null}
            </div>
            {controlError ? (
              <p className="text-sm text-orange-600">{controlError}</p>
            ) : controlResult && controlResult.ticket_id === item.id ? (
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">{controlResult.state.reason}</p>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">{controlResult.state.action}</Badge>
                  <Badge variant="secondary">{controlResult.state.updated_session_count} sessions</Badge>
                  {controlResult.report_id ? <Badge variant="outline">Report {controlResult.report_id}</Badge> : null}
                </div>
              </div>
            ) : null}
          </section>
        ) : null}

        {(loopResult && loopResult.ticket_id === item.id) || loopError ? (
          <section className="rounded-md border bg-muted/20 p-3">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <div className="text-xs uppercase text-muted-foreground">Autonomous Loop</div>
              {loopResult && loopResult.ticket_id === item.id ? (
                <Badge variant={loopResult.status === "completed" ? "success" : statusVariant(loopResult.status)}>{loopResult.status}</Badge>
              ) : null}
            </div>
            {loopError ? (
              <p className="text-sm text-orange-600">{loopError}</p>
            ) : loopResult && loopResult.ticket_id === item.id ? (
              <div className="space-y-2">
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">Stop {loopResult.stop_reason}</Badge>
                  <Badge variant="secondary">{loopResult.steps.length} steps</Badge>
                </div>
                {loopResult.steps.length > 0 ? (
                  <div className="space-y-2">
                    {loopResult.steps.slice(0, 3).map((step, index) => (
                      <div key={`${step.ticket_id}-${index}-${step.stop_reason}`} className="rounded-md border bg-background p-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant={statusVariant(step.status)}>{step.status}</Badge>
                          <span className="text-xs text-muted-foreground">Step {index + 1}</span>
                          <span className="text-xs text-muted-foreground">{step.stop_reason}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No loop step was executed.</p>
                )}
              </div>
            ) : null}
          </section>
        ) : null}

        <section className="rounded-md border bg-muted/20 p-3">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <div className="text-xs uppercase text-muted-foreground">Loop Runs</div>
            {loopRuns.length > 0 ? <Badge variant="outline">{loopRuns.length} recorded</Badge> : null}
          </div>
          {loopRuns.length === 0 ? (
            <p className="text-sm text-muted-foreground">No loop runs recorded for this Ticket.</p>
          ) : (
            <div className="space-y-2">
              {loopRuns.slice(0, 5).map((run) => (
                <div key={run.run_id} className="rounded-md border bg-background p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="truncate text-sm font-medium" title={run.run_id}>{run.run_id}</span>
                    <div className="flex items-center gap-2">
                      <Badge variant={run.active ? "warning" : statusVariant(run.status)}>{run.status}</Badge>
                      <Button type="button" variant="outline" size="sm" onClick={() => onSelectLoopRun(item, run.run_id)}>
                        {loadingLoopRunId === run.run_id ? "Loading" : "Details"}
                      </Button>
                      {run.session_key ? (
                        <Button type="button" variant="outline" size="sm" onClick={() => navigateTo("runtime", run.session_key)}>
                          Replay
                        </Button>
                      ) : null}
                    </div>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
                    <span>{run.step_count} steps</span>
                    <span>{run.stop_reason || "running"}</span>
                    <span>{formatTime(run.updated_at || run.started_at || run.queued_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
          {loopRunDetailError ? (
            <div className="mt-3 rounded-md border bg-background p-3">
              <div className="mb-1 text-xs uppercase text-muted-foreground">Loop Run Detail</div>
              <p className="text-sm text-orange-600">{loopRunDetailError}</p>
            </div>
          ) : loopRunDetail && loopRunDetail.ticket_id === item.id ? (
            <div className="mt-3 rounded-md border bg-background p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-xs uppercase text-muted-foreground">Loop Run Detail</div>
                  <div className="truncate text-sm font-medium" title={loopRunDetail.run_id}>{loopRunDetail.run_id}</div>
                </div>
                <Badge variant={loopRunDetail.active ? "warning" : statusVariant(loopRunDetail.status)}>
                  {loopRunDetail.status}
                </Badge>
              </div>
              {loopRunDetail.session_key ? (
                <Button type="button" variant="outline" size="sm" onClick={() => navigateTo("runtime", loopRunDetail.session_key)}>
                  <Activity className="h-4 w-4" />
                  Runtime Replay
                </Button>
              ) : null}
              <div className="grid gap-2 text-xs text-muted-foreground md:grid-cols-2">
                <div>Ticket {loopRunDetail.ticket_id}</div>
                <div>{loopRunDetail.step_count} steps</div>
                <div>Stop {loopRunDetail.stop_reason || "running"}</div>
                <div>Saved {loopRunDetail.saved_path}</div>
              </div>
              <div className="mt-3 grid gap-3 lg:grid-cols-2">
                <div className="min-w-0">
                  <div className="mb-1 text-xs uppercase text-muted-foreground">Request</div>
                  <pre className="max-h-40 overflow-auto rounded-md bg-muted/40 p-2 text-xs leading-5">{compactJson(loopRunDetail.request)}</pre>
                </div>
                <div className="min-w-0">
                  <div className="mb-1 text-xs uppercase text-muted-foreground">Response</div>
                  <pre className="max-h-40 overflow-auto rounded-md bg-muted/40 p-2 text-xs leading-5">{compactJson(loopRunDetail.response)}</pre>
                </div>
                <div className="min-w-0">
                  <div className="mb-1 text-xs uppercase text-muted-foreground">Policy</div>
                  <pre className="max-h-32 overflow-auto rounded-md bg-muted/40 p-2 text-xs leading-5">{compactJson(loopRunDetail.policy)}</pre>
                </div>
                <div className="min-w-0">
                  <div className="mb-1 text-xs uppercase text-muted-foreground">Control</div>
                  <pre className="max-h-32 overflow-auto rounded-md bg-muted/40 p-2 text-xs leading-5">{compactJson(loopRunDetail.control)}</pre>
                </div>
              </div>
            </div>
          ) : null}
        </section>

        {(closeoutResult && closeoutResult.ticket_id === item.id) || closeoutError ? (
          <section className="rounded-md border bg-muted/20 p-3">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <div className="text-xs uppercase text-muted-foreground">Closeout Assets</div>
              {closeoutResult && closeoutResult.ticket_id === item.id ? (
                <Badge variant={closeoutResult.status === "proposed" ? "success" : "secondary"}>{closeoutResult.status}</Badge>
              ) : null}
            </div>
            {closeoutError ? (
              <p className="text-sm text-orange-600">{closeoutError}</p>
            ) : closeoutResult && closeoutResult.ticket_id === item.id ? (
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">{closeoutResult.detail}</p>
                <div className="flex flex-wrap gap-2">
                  {closeoutResult.candidates.map((candidate) => (
                    <Badge key={candidate.id} variant="outline">{candidate.asset_type}</Badge>
                  ))}
                  {closeoutResult.report_id ? <Badge variant="secondary">Report {closeoutResult.report_id}</Badge> : null}
                </div>
              </div>
            ) : null}
          </section>
        ) : null}

        {(closeoutSettlementResult && closeoutSettlementResult.ticket_id === item.id) || closeoutSettlementError ? (
          <section className="rounded-md border bg-muted/20 p-3">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <div className="text-xs uppercase text-muted-foreground">Closeout Settlement</div>
              {closeoutSettlementResult && closeoutSettlementResult.ticket_id === item.id ? (
                <Badge variant={closeoutSettlementVariant(closeoutSettlementResult.status)}>{closeoutSettlementResult.status}</Badge>
              ) : null}
            </div>
            {closeoutSettlementError ? (
              <p className="text-sm text-orange-600">{closeoutSettlementError}</p>
            ) : closeoutSettlementResult && closeoutSettlementResult.ticket_id === item.id ? (
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground">{closeoutSettlementResult.detail}</p>
                <div className="flex flex-wrap gap-2">
                  {closeoutSettlementResult.review ? (
                    <Badge variant={closeoutSettlementResult.review.failed_count > 0 ? "warning" : "secondary"}>
                      Reviewed {closeoutSettlementResult.review.reviewed_count}/{closeoutSettlementResult.review.requested_count}
                    </Badge>
                  ) : null}
                  <Badge variant="outline">{closeoutSettlementResult.asset_ids.length} AssetRecords</Badge>
                  <Badge variant="outline">{closeoutSettlementResult.projections.length} Graphiti projections</Badge>
                  {closeoutSettlementResult.report_id ? <Badge variant="secondary">Report {closeoutSettlementResult.report_id}</Badge> : null}
                </div>
                {closeoutSettlementResult.asset_ids.length > 0 ? (
                  <div className="space-y-1">
                    <div className="text-xs uppercase text-muted-foreground">Asset Records</div>
                    <div className="flex flex-wrap gap-2">
                      {closeoutSettlementResult.asset_ids.map((assetId) => (
                        <Badge key={assetId} variant="outline">{assetId}</Badge>
                      ))}
                    </div>
                  </div>
                ) : null}
                {closeoutSettlementResult.projections.length > 0 ? (
                  <div className="space-y-2">
                    <div className="text-xs uppercase text-muted-foreground">Graphiti Projection</div>
                    {closeoutSettlementResult.projections.map((projection) => (
                      <div key={projection.asset_id} className="rounded-md border bg-background p-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="truncate text-sm font-medium" title={projection.asset_id}>{projection.asset_id}</span>
                          <Badge variant={closeoutSettlementVariant(projection.status)}>{projection.status}</Badge>
                        </div>
                        {projection.error ? (
                          <p className="mt-2 text-sm text-orange-600">{projection.error}</p>
                        ) : null}
                      </div>
                    ))}
                  </div>
                ) : null}
                <div className="flex flex-wrap gap-2">
                  {closeoutSettlementResult.saved_paths.asset_records ? (
                    <Badge variant="outline">AssetRecords {closeoutSettlementResult.saved_paths.asset_records}</Badge>
                  ) : null}
                  {closeoutSettlementResult.saved_paths.graphiti_state ? (
                    <Badge variant="outline">Graphiti {closeoutSettlementResult.saved_paths.graphiti_state}</Badge>
                  ) : null}
                </div>
              </div>
            ) : null}
          </section>
        ) : null}

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

function RetryPreflightCard({ requirements }: { requirements: TicketLoopRetryRequirement[] }) {
  if (requirements.length === 0) return null;
  return (
    <section className="rounded-md border bg-muted/20 p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <div className="text-xs uppercase text-muted-foreground">Retry Preflight</div>
        <Badge variant={requirements.every((item) => item.satisfied) ? "success" : "warning"}>
          {requirements.filter((item) => item.satisfied).length}/{requirements.length}
        </Badge>
      </div>
      <div className="space-y-2">
        {requirements.map((requirement) => (
          <div key={requirement.id} className="rounded-md border bg-background p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <Badge variant={requirement.satisfied ? "success" : "warning"}>
                  {requirement.satisfied ? "ready" : "needed"}
                </Badge>
                <span className="truncate text-sm font-medium" title={requirement.label}>{requirement.label}</span>
              </div>
              {requirement.target_route ? (
                <Button type="button" variant="outline" size="sm" onClick={() => navigateToTimelineRoute(requirement.target_route)}>
                  Open
                </Button>
              ) : null}
            </div>
            {requirement.detail ? <p className="mt-2 text-sm text-muted-foreground">{requirement.detail}</p> : null}
          </div>
        ))}
      </div>
    </section>
  );
}

function RuntimeApprovalResumeCard({ approvals }: { approvals: TicketLoopApprovalResumeState[] }) {
  if (approvals.length === 0) return null;
  return (
    <section className="rounded-md border bg-muted/20 p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <div className="text-xs uppercase text-muted-foreground">Runtime Approval Resume</div>
        <Badge variant="outline">{approvals.length} approvals</Badge>
        {approvals.some((item) => item.ready_to_run) ? <Badge variant="success">ready</Badge> : null}
        {approvals.some((item) => item.blocked) ? <Badge variant="warning">blocked run</Badge> : null}
      </div>
      <div className="space-y-2">
        {approvals.slice(0, 3).map((approval) => (
          <div key={approval.approval_id} className="rounded-md border bg-background p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <Badge variant={approval.blocked ? "warning" : approval.ready_to_run ? "success" : statusVariant(approval.status)}>
                  {approval.status}
                </Badge>
                <span className="truncate text-sm font-medium" title={approval.approval_id}>{approval.approval_id}</span>
                <Badge variant="outline">{approval.executor_id}</Badge>
                {approval.attempt_count > 0 ? <Badge variant="secondary">{approval.attempt_count} attempts</Badge> : null}
              </div>
              {approval.target_route ? (
                <Button type="button" variant="outline" size="sm" onClick={() => navigateToTimelineRoute(approval.target_route)}>
                  Open Approval
                </Button>
              ) : null}
            </div>
            <p className="mt-2 text-sm text-muted-foreground">{approval.detail}</p>
            {approval.last_run_request_id ? (
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
                <span>Last run: {approval.last_run_request_id}</span>
                <span>Status: {approval.last_run_status || "-"}</span>
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}

function QueueReliabilityCard({
  reliability,
  onProposeFailureRetrospective,
  proposingFailureRetrospective,
}: {
  reliability: TicketLoopQueueReliability | null;
  onProposeFailureRetrospective: () => void;
  proposingFailureRetrospective: boolean;
}) {
  if (!reliability || reliability.total_count === 0) return null;
  const statusVariant =
    reliability.status === "error" || reliability.status === "stale_running"
      ? "danger"
      : reliability.status === "waiting_worker" || reliability.status === "duplicate_queued"
        ? "warning"
        : "secondary";
  const canProposeRetrospective = reliability.failed_count >= 2;
  return (
    <section className="rounded-md border bg-muted/20 p-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <div className="text-xs uppercase text-muted-foreground">Queue Reliability</div>
          <Badge variant={statusVariant}>{reliability.status}</Badge>
          <Badge variant={reliability.worker_running ? "success" : "outline"}>
            Worker {reliability.worker_status || "unknown"}
          </Badge>
        </div>
        {canProposeRetrospective ? (
          <Button type="button" variant="outline" size="sm" disabled={proposingFailureRetrospective} onClick={onProposeFailureRetrospective}>
            <Archive className="h-4 w-4" />
            {proposingFailureRetrospective ? "Proposing" : "Failure Retrospective"}
          </Button>
        ) : null}
      </div>
      <p className="text-sm text-muted-foreground">{reliability.detail}</p>
      <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
        <span>Queued: {reliability.queued_count}</span>
        {reliability.duplicate_queued_count ? <span>Duplicates: {reliability.duplicate_queued_count}</span> : null}
        <span>Running: {reliability.running_count}</span>
        {reliability.stale_running_count ? <span>Stale: {reliability.stale_running_count}</span> : null}
        <span>Failed: {reliability.failed_count}</span>
        <span>Total: {reliability.total_count}</span>
        {reliability.latest_activity_at ? <span>Updated: {formatTime(reliability.latest_activity_at)}</span> : null}
      </div>
      {reliability.worker_last_error ? <p className="mt-2 text-sm text-orange-600">{reliability.worker_last_error}</p> : null}
    </section>
  );
}

function timelineKindLabel(kind: string): string {
  return {
    approval: "Approval",
    asset: "Asset",
    loop_queue: "Queue",
    loop_run: "Loop Run",
    runtime_session: "Runtime",
    ticket_event: "Ticket Event",
    ticket_report: "Report",
  }[kind] ?? kind.replace(/_/g, " ");
}

function timelineRouteLabel(kind: string): string {
  return {
    approval: "Open Approval",
    asset: "Open Asset",
    runtime_session: "Open Runtime",
    ticket_report: "Open Report",
  }[kind] ?? "Open";
}

function navigateToTimelineRoute(route: string): void {
  const [page, id, detail] = route.split("/").filter(Boolean);
  if (!page) return;
  navigateTo(page, id, detail);
}

function TicketTimelineView({ item, timeline }: { item: Ticket | null; timeline: TicketLoopTimelineResponse | null }) {
  if (!item) {
    return <EmptyTicketMessage title="No Ticket selected" description="Select a Ticket to inspect its team timeline." />;
  }
  if (!timeline) {
    return <EmptyTicketMessage title="Timeline unavailable" description="Ticket timeline projection is still loading or unavailable." />;
  }
  const summary = timeline.summary;
  return (
    <section className="rounded-md border bg-background">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b px-4 py-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Workflow className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold">Team Timeline</h3>
            <Badge variant={statusVariant(summary.status)}>{summary.status}</Badge>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{summary.next_action}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {Object.entries(summary.counts).slice(0, 6).map(([kind, count]) => (
            <Badge key={kind} variant="outline">{timelineKindLabel(kind)}: {count}</Badge>
          ))}
        </div>
      </div>
      {summary.waiting_reason || summary.provider_blockers.length > 0 ? (
        <div className="grid gap-3 border-b p-4 md:grid-cols-2">
          {summary.waiting_reason ? (
            <div className="rounded-md border bg-muted/30 p-3">
              <div className="mb-1 text-xs uppercase text-muted-foreground">Loop State</div>
              <p className="text-sm leading-6">{summary.waiting_reason}</p>
            </div>
          ) : null}
          {summary.provider_blockers.length > 0 ? (
            <div className="rounded-md border bg-muted/30 p-3">
              <div className="mb-1 text-xs uppercase text-muted-foreground">Provider Blockers</div>
              <p className="text-sm leading-6">{String(summary.provider_blockers[0].detail ?? "Provider transition needs configuration.")}</p>
            </div>
          ) : null}
        </div>
      ) : null}
      <div className="divide-y">
        {timeline.items.length === 0 ? (
          <div className="px-4 py-4 text-sm text-muted-foreground">No timeline facts are attached to this Ticket yet.</div>
        ) : (
          timeline.items.slice(0, 30).map((entry: TicketLoopTimelineItem) => (
            <div key={entry.timeline_id} className="grid gap-2 px-4 py-4 sm:grid-cols-[7rem_minmax(0,1fr)]">
              <div className="min-w-0">
                <Badge variant={statusVariant(entry.status || entry.kind)}>{timelineKindLabel(entry.kind)}</Badge>
                <div className="mt-2 truncate text-xs text-muted-foreground">{formatTime(entry.at)}</div>
              </div>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{entry.title}</span>
                  {entry.status ? <Badge variant="outline">{entry.status}</Badge> : null}
                  {entry.actor_employee_id || entry.actor_role ? (
                    <Badge variant="secondary">{entry.actor_employee_id || entry.actor_role}</Badge>
                  ) : null}
                  {entry.target_route ? (
                    <Button type="button" variant="outline" size="sm" onClick={() => navigateToTimelineRoute(entry.target_route)}>
                      {timelineRouteLabel(entry.kind)}
                    </Button>
                  ) : null}
                </div>
                {entry.detail ? <div className="mt-1 line-clamp-3 text-sm text-muted-foreground">{entry.detail}</div> : null}
                {entry.refs.length > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {entry.refs.slice(0, 4).map((ref) => (
                      ref.target_route ? (
                        <Button
                          key={`${entry.timeline_id}-${ref.kind}-${ref.ref}`}
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => navigateToTimelineRoute(ref.target_route)}
                        >
                          {ref.kind}: {ref.ref}
                        </Button>
                      ) : (
                        <Badge key={`${entry.timeline_id}-${ref.kind}-${ref.ref}`} variant="outline">
                          {ref.kind}: {ref.ref}
                        </Badge>
                      )
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
          ))
        )}
      </div>
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

function ReportRow({
  evidenceIndex,
  focused,
  item,
  report,
}: {
  evidenceIndex: number | null;
  focused: boolean;
  item: Ticket;
  report: TicketReport;
}) {
  return (
    <section className={cn("rounded-md border bg-background p-4", focused && "border-primary bg-primary/5")}>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
          <h4 className="truncate text-sm font-semibold">{item.title}</h4>
        </div>
        <div className="flex flex-wrap gap-2">
          {focused ? <Badge variant="secondary">selected</Badge> : null}
          <Badge variant={report.report_type === "validation" ? "success" : "secondary"}>{report.report_type}</Badge>
        </div>
      </div>
      <p className="text-sm leading-6">{report.content}</p>
      <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
        <span>{report.reporter_employee_id || report.reporter_role || "unknown reporter"}</span>
        <span>{formatTime(report.created_at)}</span>
        <span>{item.id}</span>
      </div>
      {report.evidence.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {report.evidence.map((entry, index) => (
            <Badge key={`${report.id}-${index}-${entry}`} variant={evidenceIndex === index ? "secondary" : "outline"}>
              {entry}
            </Badge>
          ))}
        </div>
      )}
    </section>
  );
}

function TicketReportsView({
  focus,
  reports,
}: {
  focus: TicketRouteFocus;
  reports: { item: Ticket; report: TicketReport }[];
}) {
  const scopedReports = focus.ticketId
    ? reports.filter(({ item }) => item.id === focus.ticketId)
    : reports;
  if (scopedReports.length === 0) {
    return <EmptyTicketMessage title="No reports yet" description="Employee and PV reports written to Tickets will appear here." />;
  }
  return (
    <div className="grid gap-3">
      {scopedReports.map(({ item, report }) => {
        const focusedReport = focus.reportId === report.id;
        const focusedEvidence = focus.evidenceReportId === report.id;
        return (
          <ReportRow
            key={report.id}
            evidenceIndex={focusedEvidence ? focus.evidenceIndex : null}
            focused={focusedReport || focusedEvidence}
            item={item}
            report={report}
          />
        );
      })}
    </div>
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
        <Button type="button" variant="outline" size="sm" className="w-full" onClick={() => navigateTo("settings", "ticket-backend")}>
          Settings
        </Button>
      </div>
    </section>
  );
}

function LiveProviderTicketReadinessCard({ systemStatus }: { systemStatus: SystemStatusResponse | null }) {
  const readiness = systemStatus?.live_provider_dogfood ?? null;
  const summary = recordValue(readiness?.summary);
  const mutationGate = recordValue(readiness?.mutation_gate);
  const providerPrerequisites = recordValue(readiness?.provider_prerequisites);
  const ticketBackend = recordValue(providerPrerequisites.ticket_backend);
  const memoryBackend = recordValue(providerPrerequisites.memory_backend);
  const providerSmoke = recordValue(providerPrerequisites.provider_smoke);
  const selectedPreflight = recordValue(readiness?.selected_executor_preflight);
  const blockers = recordArray(readiness?.blockers).slice(0, 3);
  const candidates = readiness?.repo_write_executor_candidates ?? [];
  const readyCandidateCount = Number(summary.repo_write_ready_count ?? candidates.filter((candidate) => candidate.ready).length);
  const candidateCount = Number(summary.repo_write_candidate_count ?? candidates.length);
  const ticketBackendStatus = textValue(ticketBackend.status, textValue(summary.ticket_backend_status));
  const memoryBackendStatus = textValue(memoryBackend.status, textValue(summary.memory_backend_status));
  const providerSmokeStatus = textValue(providerSmoke.status, "not_run");
  const selectedStatus = textValue(selectedPreflight.status, readiness?.selected_executor_id ? "unknown" : "");
  const profile = textValue(readiness?.profile, textValue(summary.profile, "core_loop"));

  return (
    <section className="rounded-md border bg-background p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <PlayCircle className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Live Provider Loop</h3>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant={readinessVariant(readiness?.status)}>{compactStatus(readiness?.status)}</Badge>
          <Badge variant={mutationGate.open ? "success" : "warning"}>{mutationGate.open ? "gate open" : "gate closed"}</Badge>
        </div>
      </div>
      {!readiness ? (
        <p className="text-sm text-muted-foreground">Live provider readiness is unavailable.</p>
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline">{profile}</Badge>
            <Badge variant={readiness.require_repo_write_executor ? "warning" : "secondary"}>
              {readiness.require_repo_write_executor ? "repo:write required" : "repo:write optional"}
            </Badge>
            {readiness.selected_executor_id ? <Badge variant={readinessVariant(selectedStatus)}>{readiness.selected_executor_id}</Badge> : null}
            <Badge variant={readyCandidateCount > 0 ? "success" : "warning"}>
              {readyCandidateCount}/{candidateCount || candidates.length} repo-write ready
            </Badge>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Status label="Ticket provider" value={compactStatus(ticketBackendStatus)} tone={ticketBackendStatus === "ready" ? "ok" : "warn"} />
            <Status label="Memory provider" value={compactStatus(memoryBackendStatus)} tone={memoryBackendStatus === "ready" ? "ok" : "warn"} />
            <Status label="Provider smoke" value={compactStatus(providerSmokeStatus)} tone={providerSmokeStatus === "passed" ? "ok" : "warn"} />
            <Status label="Blockers" value={blockers.length} tone={blockers.length ? "warn" : "ok"} />
          </div>

          {textValue(summary.anti_wheel_boundary) ? (
            <p className="text-xs leading-5 text-muted-foreground">{textValue(summary.anti_wheel_boundary)}</p>
          ) : null}

          {blockers.length ? (
            <div className="space-y-2 border-t pt-3">
              <div className="text-xs uppercase text-muted-foreground">Live Blockers</div>
              {blockers.map((blocker, index) => {
                const reason = textValue(blocker.reason, `blocker-${index + 1}`);
                const setupRequired = stringArray(blocker.setup_required).slice(0, 4);
                return (
                  <div key={`${reason}-${index}`} className="space-y-2 rounded-md bg-muted/30 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-sm font-medium">{compactStatus(reason)}</span>
                      <Badge variant={readinessVariant(textValue(blocker.status, "blocked"))}>
                        {compactStatus(textValue(blocker.status, "blocked"))}
                      </Badge>
                    </div>
                    {textValue(blocker.detail) ? <p className="text-xs leading-5 text-muted-foreground">{textValue(blocker.detail)}</p> : null}
                    {setupRequired.length ? (
                      <div className="flex flex-wrap gap-2">
                        {setupRequired.map((item) => <Badge key={`${reason}-${item}`} variant="outline">{item}</Badge>)}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          ) : null}

          {candidates.length ? (
            <div className="space-y-2 border-t pt-3">
              <div className="text-xs uppercase text-muted-foreground">Repo-Write Providers</div>
              <div className="flex flex-wrap gap-2">
                {candidates.slice(0, 4).map((candidate) => (
                  <Badge key={candidate.executor_id} variant={candidate.ready ? "success" : readinessVariant(candidate.status)}>
                    {candidate.display_name || candidate.executor_id}
                  </Badge>
                ))}
              </div>
            </div>
          ) : null}

          <div className="grid gap-2 sm:grid-cols-2">
            <Button type="button" variant="outline" size="sm" onClick={() => navigateTo("settings", "ticket-backend")}>
              <ClipboardList className="h-4 w-4" />
              Ticket Backend
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={() => navigateTo("settings", "memory-backend")}>
              <Database className="h-4 w-4" />
              Memory Backend
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={() => navigateTo("system-status")}>
              <Activity className="h-4 w-4" />
              System Status
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={() => navigateTo("runtime")}>
              <Workflow className="h-4 w-4" />
              Runtime Replay
            </Button>
          </div>
        </div>
      )}
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

function LoopQueueCard({
  onPump,
  pumping,
  pumpResult,
  status,
}: {
  onPump: () => void;
  pumping: boolean;
  pumpResult: TicketLoopQueuePumpResponse | null;
  status: TicketLoopQueueStatus | null;
}) {
  return (
    <section className="rounded-md border bg-background p-4">
      <div className="mb-3 flex items-center gap-2">
        <Workflow className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold">Loop Queue</h3>
      </div>
      {!status ? (
        <p className="text-sm text-muted-foreground">Loop queue status is unavailable.</p>
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <Badge variant={status.active_count > 0 ? "warning" : "outline"}>{status.status}</Badge>
            <Badge variant="outline">{status.active_count} active</Badge>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Status label="Queued" value={status.queued_count} tone={status.queued_count > 0 ? "warn" : undefined} />
            <Status label="Running" value={status.running_count} tone={status.running_count > 0 ? "warn" : undefined} />
            <Status label="Completed" value={status.completed_count} />
            <Status label="Failed" value={status.failed_count} tone={status.failed_count > 0 ? "warn" : undefined} />
          </div>
          {status.next_run_id ? (
            <div className="rounded-md border bg-muted/30 p-3">
              <div className="truncate text-sm font-medium" title={status.next_run_id}>{status.next_run_id}</div>
              <div className="mt-1 truncate text-xs text-muted-foreground" title={status.next_ticket_id}>
                Ticket {status.next_ticket_id}
              </div>
            </div>
          ) : null}
          {pumpResult ? (
            <div className="rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
              Pump {pumpResult.status}: {pumpResult.processed.length} processed, {pumpResult.remaining_queued} queued
            </div>
          ) : null}
          <Button type="button" variant="outline" size="sm" className="w-full" disabled={pumping || status.queued_count === 0} onClick={onPump}>
            <RefreshCw className="h-4 w-4" />
            {pumping ? "Pumping" : "Pump Queue"}
          </Button>
        </div>
      )}
    </section>
  );
}

function LoopQueueSection({
  items,
  onPump,
  onSelectTicket,
  onWorkerStart,
  onWorkerStop,
  onWorkerTick,
  pumping,
  pumpResult,
  status,
  workerBusy,
  workerError,
  workerStatus,
  workerTickResult,
}: {
  items: TicketLoopQueueItem[];
  onPump: () => void;
  onSelectTicket: (ticketId: string) => void;
  onWorkerStart: () => void;
  onWorkerStop: () => void;
  onWorkerTick: () => void;
  pumping: boolean;
  pumpResult: TicketLoopQueuePumpResponse | null;
  status: TicketLoopQueueStatus | null;
  workerBusy: boolean;
  workerError: string | null;
  workerStatus: TicketLoopQueueWorkerStatus | null;
  workerTickResult: TicketLoopQueueWorkerTickResponse | null;
}) {
  const recentPolicyAction =
    workerStatus && workerStatus.recent_policy_actions.length > 0
      ? workerStatus.recent_policy_actions[workerStatus.recent_policy_actions.length - 1]
      : null;
  const recentPolicyCandidateId = recentPolicyAction?.candidate_ids[0] || "";
  return (
    <section className="rounded-md border bg-background">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Workflow className="h-4 w-4 text-muted-foreground" />
          <div>
            <h3 className="text-sm font-semibold">Loop Queue</h3>
            <p className="text-xs text-muted-foreground">Cross-Ticket queue for governed autonomous loop runs.</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {status ? <Badge variant={status.active_count > 0 ? "warning" : "outline"}>{status.status}</Badge> : null}
          <Button type="button" variant="outline" size="sm" disabled={pumping || !status || status.queued_count === 0} onClick={onPump}>
            <RefreshCw className="h-4 w-4" />
            {pumping ? "Pumping" : "Pump Queue"}
          </Button>
        </div>
      </div>
      {status ? (
        <div className="grid gap-3 border-b p-4 sm:grid-cols-2 xl:grid-cols-5">
          <Status label="Queued" value={status.queued_count} tone={status.queued_count > 0 ? "warn" : undefined} />
          <Status label="Running" value={status.running_count} tone={status.running_count > 0 ? "warn" : undefined} />
          <Status label="Completed" value={status.completed_count} />
          <Status label="Failed" value={status.failed_count} tone={status.failed_count > 0 ? "warn" : undefined} />
          <Status label="Total" value={status.total_count} />
        </div>
      ) : null}
      {pumpResult ? (
        <div className="border-b px-4 py-3 text-sm text-muted-foreground">
          Pump {pumpResult.status}: {pumpResult.processed.length} processed, {pumpResult.remaining_queued} queued
          {pumpResult.policy_actions.length > 0 ? `, ${pumpResult.policy_actions.length} policy action` : ""}
        </div>
      ) : null}
      <div className="border-b p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <div className="text-xs uppercase text-muted-foreground">Worker Daemon</div>
              {workerStatus ? (
                <Badge variant={workerStatus.running ? "warning" : statusVariant(workerStatus.status)}>
                  {workerStatus.status}
                </Badge>
              ) : null}
            </div>
            <div className="mt-1 truncate text-xs text-muted-foreground" title={workerStatus?.saved_path || ""}>
              {workerStatus ? `State ${workerStatus.saved_path}` : "Worker status unavailable."}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" size="sm" disabled={workerBusy || Boolean(workerStatus?.running)} onClick={onWorkerStart}>
              <Workflow className="h-4 w-4" />
              Start Worker
            </Button>
            <Button type="button" variant="outline" size="sm" disabled={workerBusy || !workerStatus?.running} onClick={onWorkerStop}>
              <ShieldCheck className="h-4 w-4" />
              Stop Worker
            </Button>
            <Button type="button" variant="outline" size="sm" disabled={workerBusy} onClick={onWorkerTick}>
              <RefreshCw className="h-4 w-4" />
              Tick Worker
            </Button>
          </div>
        </div>
        {workerStatus ? (
          <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <Status label="Worker ticks" value={workerStatus.total_ticks} />
            <Status label="Worker processed" value={workerStatus.total_processed} />
            <Status label="Policy actions" value={workerStatus.total_policy_actions} />
            <Status label="Last tick" value={workerStatus.last_tick_status || "-"} />
            <Status label="Interval" value={`${workerStatus.interval_seconds}s`} />
          </div>
        ) : null}
        {recentPolicyAction ? (
          <div className="mt-3 rounded-md border bg-muted/30 p-3">
            <div className="text-xs text-muted-foreground">
              Recent policy action {recentPolicyAction.status}: {recentPolicyAction.kind}
              {recentPolicyAction.report_id ? `, report ${recentPolicyAction.report_id}` : ""}
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {recentPolicyAction.report_id ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => navigateTo("tickets", "reports", `${recentPolicyAction.ticket_id}::report::${recentPolicyAction.report_id}`)}
                >
                  <FileText className="h-4 w-4" />
                  Report
                </Button>
              ) : null}
              {recentPolicyCandidateId ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => navigateTo("assets", "review", recentPolicyCandidateId)}
                >
                  <Archive className="h-4 w-4" />
                  Review Asset
                </Button>
              ) : null}
            </div>
          </div>
        ) : null}
        {workerTickResult ? (
          <div className="mt-3 rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
            Worker tick {workerTickResult.pump.status}: {workerTickResult.pump.processed.length} processed, {workerTickResult.pump.remaining_queued} queued
            {workerTickResult.pump.policy_actions.length > 0 ? `, ${workerTickResult.pump.policy_actions.length} policy action` : ""}
          </div>
        ) : null}
        {workerError ? (
          <div className="mt-3 rounded-md border bg-muted/30 p-3 text-sm text-orange-600">{workerError}</div>
        ) : null}
      </div>
      {items.length === 0 ? (
        <EmptyTicketMessage title="No queued loop work" description="Queued autonomous loop runs will appear here." />
      ) : (
        <div className="divide-y">
          {items.map((item) => (
            <div key={item.queue_id} className="grid gap-3 px-4 py-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(12rem,0.8fr)_auto]">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={statusVariant(item.status)}>{item.status}</Badge>
                  <span className="truncate text-sm font-medium" title={item.run_id}>{item.run_id}</span>
                </div>
                <div className="mt-1 truncate text-xs text-muted-foreground" title={item.queue_id}>{item.queue_id}</div>
                <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">{item.reason || item.error || "Queued autonomous loop run."}</p>
              </div>
              <div className="min-w-0 text-sm">
                <div className="truncate" title={item.ticket_id}>Ticket {item.ticket_id}</div>
                <div className="mt-1 text-xs text-muted-foreground">Priority {item.priority}</div>
                <div className="mt-1 text-xs text-muted-foreground">Updated {formatTime(item.updated_at || item.enqueued_at)}</div>
              </div>
              <div className="flex flex-wrap items-start gap-2 lg:justify-end">
                <Button type="button" variant="outline" size="sm" onClick={() => onSelectTicket(item.ticket_id)}>
                  <ClipboardList className="h-4 w-4" />
                  Ticket
                </Button>
              </div>
            </div>
          ))}
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
                      <Badge variant={["used", "promoted", "useful"].includes(usefulness) ? "success" : "outline"}>{usefulness}</Badge>
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
  const [ticketRuntimeEvidence, setTicketRuntimeEvidence] = useState<TicketRuntimeEvidence | null>(null);
  const [ticketEvidenceRequirements, setTicketEvidenceRequirements] = useState<TicketEvidenceRequirements | null>(null);
  const [ticketLoopRuns, setTicketLoopRuns] = useState<TicketLoopRunRecord[]>([]);
  const [ticketLoopTimeline, setTicketLoopTimeline] = useState<TicketLoopTimelineResponse | null>(null);
  const [loopQueueItems, setLoopQueueItems] = useState<TicketLoopQueueItem[]>([]);
  const [closeoutResult, setCloseoutResult] = useState<TicketCloseoutAssetCandidateResponse | null>(null);
  const [closeoutError, setCloseoutError] = useState<string | null>(null);
  const [proposingCloseoutTicketId, setProposingCloseoutTicketId] = useState("");
  const [closeoutSettlementResult, setCloseoutSettlementResult] = useState<TicketCloseoutSettlementResponse | null>(null);
  const [closeoutSettlementError, setCloseoutSettlementError] = useState<string | null>(null);
  const [settlingCloseoutTicketId, setSettlingCloseoutTicketId] = useState("");
  const [failureRetrospectiveResult, setFailureRetrospectiveResult] = useState<TicketFailureRetrospectiveAssetCandidateResponse | null>(null);
  const [failureRetrospectiveError, setFailureRetrospectiveError] = useState<string | null>(null);
  const [proposingFailureRetrospectiveTicketId, setProposingFailureRetrospectiveTicketId] = useState("");
  const [loopResult, setLoopResult] = useState<TicketLoopRunResponse | null>(null);
  const [loopError, setLoopError] = useState<string | null>(null);
  const [runningLoopTicketId, setRunningLoopTicketId] = useState("");
  const [loopRunDetail, setLoopRunDetail] = useState<TicketLoopRunRecord | null>(null);
  const [loopRunDetailError, setLoopRunDetailError] = useState<string | null>(null);
  const [loadingLoopRunId, setLoadingLoopRunId] = useState("");
  const [controlResult, setControlResult] = useState<TicketLoopControlResponse | null>(null);
  const [controlError, setControlError] = useState<string | null>(null);
  const [controllingLoopTicketId, setControllingLoopTicketId] = useState("");
  const [controllingLoopAction, setControllingLoopAction] = useState("");
  const [resumeResult, setResumeResult] = useState<TicketLoopResumeResponse | null>(null);
  const [resumeError, setResumeError] = useState<string | null>(null);
  const [resumingLoopTicketId, setResumingLoopTicketId] = useState("");
  const [loopQueueStatus, setLoopQueueStatus] = useState<TicketLoopQueueStatus | null>(null);
  const [loopQueuePumpResult, setLoopQueuePumpResult] = useState<TicketLoopQueuePumpResponse | null>(null);
  const [pumpingLoopQueue, setPumpingLoopQueue] = useState(false);
  const [loopQueueWorkerStatus, setLoopQueueWorkerStatus] = useState<TicketLoopQueueWorkerStatus | null>(null);
  const [loopQueueWorkerTickResult, setLoopQueueWorkerTickResult] = useState<TicketLoopQueueWorkerTickResponse | null>(null);
  const [loopQueueWorkerBusy, setLoopQueueWorkerBusy] = useState(false);
  const [loopQueueWorkerError, setLoopQueueWorkerError] = useState<string | null>(null);
  const [selfBootstrapSummary, setSelfBootstrapSummary] = useState<SelfBootstrapLearningSummary | null>(null);
  const [backend, setBackend] = useState<TicketBackendStatus | null>(null);
  const [backendSettings, setBackendSettings] = useState<TicketBackendSettings | null>(null);
  const [systemStatus, setSystemStatus] = useState<SystemStatusResponse | null>(null);
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
  const routeFocus = useMemo(() => routeFocusFromRoute(selectedSection), [selectedSection]);
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
      const [
        loadedItems,
        loadedAssets,
        loadedSettings,
        loadedBackend,
        loadedSelfBootstrapSummary,
        loadedLoopQueueStatus,
        loadedLoopQueueItems,
        loadedLoopQueueWorkerStatus,
        loadedSystemStatus,
      ] = await Promise.all([
        listTickets(),
        listTicketAssets(),
        getTicketBackendSettings(),
        getTicketBackendStatus(),
        getSelfBootstrapSummary(),
        getTicketLoopQueueStatus(),
        listTicketLoopQueue(),
        getTicketLoopQueueWorkerStatus(),
        getSystemStatus(),
      ]);
      setItems(loadedItems);
      setTicketAssets(loadedAssets);
      setBackendSettings(loadedSettings);
      setBackend(loadedBackend);
      setSelfBootstrapSummary(loadedSelfBootstrapSummary);
      setLoopQueueStatus(loadedLoopQueueStatus);
      setLoopQueueItems(loadedLoopQueueItems);
      setLoopQueueWorkerStatus(loadedLoopQueueWorkerStatus);
      setSystemStatus(loadedSystemStatus);
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
      setTicketRuntimeEvidence(null);
      setTicketEvidenceRequirements(null);
      setTicketLoopRuns([]);
      setTicketLoopTimeline(null);
      setLoopRunDetail(null);
      setLoopRunDetailError(null);
      return () => { cancelled = true; };
    }
    Promise.all([
      getTicketGraph(selected.id),
      getTicketPerformance(selected.id),
      getTicketRuntimeEvidence(selected.id),
      getTicketEvidenceRequirements(selected.id),
      listTicketLoopRuns(selected.id),
      getTicketLoopTimeline(selected.id),
    ])
      .then(([projection, performance, runtimeEvidence, evidenceRequirements, loopRuns, timeline]) => {
        if (!cancelled) {
          setTicketGraph(projection);
          setTicketPerformance(performance);
          setTicketRuntimeEvidence(runtimeEvidence);
          setTicketEvidenceRequirements(evidenceRequirements);
          setTicketLoopRuns(loopRuns);
          setTicketLoopTimeline(timeline);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setTicketGraph(null);
          setTicketPerformance(null);
          setTicketRuntimeEvidence(null);
          setTicketEvidenceRequirements(null);
          setTicketLoopRuns([]);
          setTicketLoopTimeline(null);
        }
      });
    return () => { cancelled = true; };
  }, [selected?.id]);

  useEffect(() => {
    setCloseoutError(null);
    setCloseoutResult(null);
    setCloseoutSettlementError(null);
    setCloseoutSettlementResult(null);
    setFailureRetrospectiveError(null);
    setFailureRetrospectiveResult(null);
    setLoopError(null);
    setLoopResult(null);
    setLoopRunDetail(null);
    setLoopRunDetailError(null);
    setControlError(null);
    setControlResult(null);
    setResumeError(null);
    setResumeResult(null);
  }, [selected?.id]);

  async function handleSelectLoopRun(item: Ticket, runId: string) {
    setLoadingLoopRunId(runId);
    setLoopRunDetailError(null);
    try {
      const response = await getTicketLoopRun(item.id, runId);
      setLoopRunDetail(response);
    } catch (err) {
      setLoopRunDetail(null);
      setLoopRunDetailError(err instanceof Error ? err.message : "Ticket loop run detail is unavailable.");
    } finally {
      setLoadingLoopRunId("");
    }
  }

  async function handleControlLoop(item: Ticket, action: "stop" | "pause" | "continue" | "cancel") {
    setControllingLoopTicketId(item.id);
    setControllingLoopAction(action);
    setControlError(null);
    try {
      const response = await controlTicketLoop(item.id, {
        action,
        actor_employee_id: "clara",
        actor_role: "AI Team OS Manager",
        reason: `Dashboard requested a governed Ticket loop ${action}.`,
      });
      setControlResult(response);
      await loadTickets();
      setTicketLoopRuns(await listTicketLoopRuns(item.id));
      setTicketLoopTimeline(await getTicketLoopTimeline(item.id));
      if (action === "continue") {
        await handleRunLoop(item);
      }
    } catch (err) {
      setControlResult(null);
      setControlError(err instanceof Error ? err.message : "Ticket loop control was blocked.");
    } finally {
      setControllingLoopTicketId("");
      setControllingLoopAction("");
    }
  }

  async function handleRunLoop(item: Ticket) {
    setRunningLoopTicketId(item.id);
    setLoopError(null);
    try {
      const response = await runTicketLoop(item.id, {
        employee_id: item.assigned_employee_id || "clara",
        message: `Advance Ticket ${item.id}: ${item.title}`,
        max_steps: 2,
        selected_executor: "universal_employee_agent",
        selected_ai_engine: "universal_employee_agent",
      });
      setLoopResult(response);
      await loadTickets();
      setTicketLoopRuns(await listTicketLoopRuns(item.id));
      setTicketLoopTimeline(await getTicketLoopTimeline(item.id));
    } catch (err) {
      setLoopResult(null);
      setLoopError(err instanceof Error ? err.message : "Ticket autonomous loop was blocked.");
    } finally {
      setRunningLoopTicketId("");
    }
  }

  async function handleResumeLoop(item: Ticket, action: "resume" | "retry_after_changes" | "retry_after_evidence") {
    setResumingLoopTicketId(item.id);
    setResumeError(null);
    try {
      const response = await resumeTicketLoop(item.id, {
        action,
        employee_id: item.assigned_employee_id || "clara",
        message: `Resume Ticket ${item.id}: ${item.title}`,
        max_steps: 2,
        selected_executor: "universal_employee_agent",
        selected_ai_engine: "universal_employee_agent",
        reason: `Dashboard requested governed Ticket loop ${action}.`,
      });
      setResumeResult(response);
      await loadTickets();
      setTicketLoopRuns(await listTicketLoopRuns(item.id));
      setTicketLoopTimeline(await getTicketLoopTimeline(item.id));
      setLoopQueueItems(await listTicketLoopQueue());
      setLoopQueueStatus(await getTicketLoopQueueStatus());
    } catch (err) {
      setResumeResult(null);
      setResumeError(err instanceof Error ? err.message : "Ticket loop resume was blocked.");
    } finally {
      setResumingLoopTicketId("");
    }
  }

  async function handlePumpLoopQueue() {
    setPumpingLoopQueue(true);
    try {
      const response = await pumpTicketLoopQueue({ max_items: 1 });
      setLoopQueuePumpResult(response);
      await loadTickets();
      setLoopQueueItems(await listTicketLoopQueue());
      if (selected?.id) {
        setTicketLoopRuns(await listTicketLoopRuns(selected.id));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ticket loop queue pump was blocked.");
    } finally {
      setPumpingLoopQueue(false);
    }
  }

  async function refreshLoopQueueWorkerStatus() {
    setLoopQueueWorkerStatus(await getTicketLoopQueueWorkerStatus());
  }

  async function handleStartLoopQueueWorker() {
    setLoopQueueWorkerBusy(true);
    setLoopQueueWorkerError(null);
    try {
      const response = await startTicketLoopQueueWorker({
        interval_seconds: 5,
        max_items: 1,
        reason: "Dashboard started the governed Ticket loop queue worker.",
      });
      setLoopQueueWorkerStatus(response);
      await loadTickets();
    } catch (err) {
      setLoopQueueWorkerError(err instanceof Error ? err.message : "Ticket loop queue worker start was blocked.");
    } finally {
      setLoopQueueWorkerBusy(false);
    }
  }

  async function handleStopLoopQueueWorker() {
    setLoopQueueWorkerBusy(true);
    setLoopQueueWorkerError(null);
    try {
      const response = await stopTicketLoopQueueWorker();
      setLoopQueueWorkerStatus(response);
      await refreshLoopQueueWorkerStatus();
    } catch (err) {
      setLoopQueueWorkerError(err instanceof Error ? err.message : "Ticket loop queue worker stop was blocked.");
    } finally {
      setLoopQueueWorkerBusy(false);
    }
  }

  async function handleTickLoopQueueWorker() {
    setLoopQueueWorkerBusy(true);
    setLoopQueueWorkerError(null);
    try {
      const response = await tickTicketLoopQueueWorker({
        interval_seconds: loopQueueWorkerStatus?.interval_seconds || 5,
        max_items: loopQueueWorkerStatus?.max_items || 1,
        reason: "Dashboard requested a governed Ticket loop queue worker tick.",
      });
      setLoopQueueWorkerTickResult(response);
      setLoopQueueWorkerStatus(response.status);
      await loadTickets();
      setLoopQueueItems(await listTicketLoopQueue());
      if (selected?.id) {
        setTicketLoopRuns(await listTicketLoopRuns(selected.id));
      }
    } catch (err) {
      setLoopQueueWorkerTickResult(null);
      setLoopQueueWorkerError(err instanceof Error ? err.message : "Ticket loop queue worker tick was blocked.");
    } finally {
      setLoopQueueWorkerBusy(false);
    }
  }

  async function handleProposeCloseout(item: Ticket) {
    setProposingCloseoutTicketId(item.id);
    setCloseoutError(null);
    try {
      const response = await proposeTicketCloseoutCandidates(item.id, {
        actor_employee_id: "clara",
        actor_role: "AI Team OS Manager",
        reason: "Dashboard Ticket detail closeout proposal.",
      });
      setCloseoutResult(response);
      await loadTickets();
    } catch (err) {
      setCloseoutResult(null);
      setCloseoutError(err instanceof Error ? err.message : "Ticket closeout Asset candidate proposal was blocked.");
    } finally {
      setProposingCloseoutTicketId("");
    }
  }

  async function handleSettleCloseout(item: Ticket) {
    setSettlingCloseoutTicketId(item.id);
    setCloseoutSettlementError(null);
    try {
      const response = await settleTicketCloseout(item.id, {
        actor_employee_id: "clara",
        actor_role: "AI Team OS Manager",
        reviewer_employee_id: "clara",
        reason: "Dashboard governed Ticket closeout settlement.",
        approve_candidates: true,
        project_graphiti: true,
        project_relationships: true,
      });
      setCloseoutSettlementResult(response);
      await loadTickets();
    } catch (err) {
      setCloseoutSettlementResult(null);
      setCloseoutSettlementError(err instanceof Error ? err.message : "Ticket closeout settlement was blocked.");
    } finally {
      setSettlingCloseoutTicketId("");
    }
  }

  async function handleProposeFailureRetrospective(item: Ticket) {
    setProposingFailureRetrospectiveTicketId(item.id);
    setFailureRetrospectiveError(null);
    try {
      const response = await proposeTicketFailureRetrospectiveCandidates(item.id, {
        actor_employee_id: "clara",
        actor_role: "AI Team OS Manager",
        reason: "Dashboard Ticket queue reliability failure retrospective proposal.",
        min_failed_items: 2,
      });
      setFailureRetrospectiveResult(response);
      await loadTickets();
      setTicketLoopTimeline(await getTicketLoopTimeline(item.id));
    } catch (err) {
      setFailureRetrospectiveResult(null);
      setFailureRetrospectiveError(err instanceof Error ? err.message : "Ticket failure retrospective proposal was blocked.");
    } finally {
      setProposingFailureRetrospectiveTicketId("");
    }
  }

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
              <TicketWorkspace
                closeoutError={closeoutError}
                closeoutResult={closeoutResult}
                closeoutSettlementError={closeoutSettlementError}
                closeoutSettlementResult={closeoutSettlementResult}
                controlError={controlError}
                controlResult={controlResult}
                controllingLoopAction={selected?.id && controllingLoopTicketId === selected.id ? controllingLoopAction : ""}
                failureRetrospectiveError={failureRetrospectiveError}
                failureRetrospectiveResult={failureRetrospectiveResult}
                item={selected}
                loopError={loopError}
                loopRunDetail={loopRunDetail}
                loopRunDetailError={loopRunDetailError}
                loopResult={loopResult}
                loopRuns={ticketLoopRuns}
                loadingLoopRunId={loadingLoopRunId}
                onControlLoop={(item, action) => void handleControlLoop(item, action)}
                onProposeFailureRetrospective={(item) => void handleProposeFailureRetrospective(item)}
                onProposeCloseout={(item) => void handleProposeCloseout(item)}
                onResumeLoop={(item, action) => void handleResumeLoop(item, action)}
                onSelectLoopRun={(item, runId) => void handleSelectLoopRun(item, runId)}
                onRunLoop={(item) => void handleRunLoop(item)}
                onSettleCloseout={(item) => void handleSettleCloseout(item)}
                proposingCloseout={Boolean(selected?.id && proposingCloseoutTicketId === selected.id)}
                proposingFailureRetrospective={Boolean(selected?.id && proposingFailureRetrospectiveTicketId === selected.id)}
                resumeError={resumeError}
                resumeResult={resumeResult}
                resumingLoop={Boolean(selected?.id && resumingLoopTicketId === selected.id)}
                runningLoop={Boolean(selected?.id && runningLoopTicketId === selected.id)}
                settlingCloseout={Boolean(selected?.id && settlingCloseoutTicketId === selected.id)}
                timeline={ticketLoopTimeline}
              />
            </div>
          )}

          {section === "flow" && <TicketTimelineView item={selected} timeline={ticketLoopTimeline} />}

          {section === "reports" && (
            <TicketReportsView focus={routeFocus} reports={reports} />
          )}

          {section === "queue" && (
            <LoopQueueSection
              items={loopQueueItems}
              status={loopQueueStatus}
              pumpResult={loopQueuePumpResult}
              pumping={pumpingLoopQueue}
              workerBusy={loopQueueWorkerBusy}
              workerError={loopQueueWorkerError}
              workerStatus={loopQueueWorkerStatus}
              workerTickResult={loopQueueWorkerTickResult}
              onPump={() => void handlePumpLoopQueue()}
              onWorkerStart={() => void handleStartLoopQueueWorker()}
              onWorkerStop={() => void handleStopLoopQueueWorker()}
              onWorkerTick={() => void handleTickLoopQueueWorker()}
              onSelectTicket={(ticketId) => {
                setSelectedId(ticketId);
                navigateTo("tickets", "overview", ticketId);
              }}
            />
          )}
        </section>
      )}

      detail={(
        <aside className="space-y-4">
          <BackendCard backend={backend} settings={backendSettings} />

	          <LiveProviderTicketReadinessCard systemStatus={systemStatus} />

	          <TicketRuntimeEvidenceCard item={selected} evidence={ticketRuntimeEvidence} />

	          <LoopQueueCard
	            status={loopQueueStatus}
            pumpResult={loopQueuePumpResult}
            pumping={pumpingLoopQueue}
            onPump={() => void handlePumpLoopQueue()}
          />

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
