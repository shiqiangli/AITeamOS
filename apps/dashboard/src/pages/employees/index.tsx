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
  applyEmployeeImprovementAsset,
  getEmployeeAnalytics,
  getEmployeeGraph,
  getEmployeeGrowthEval,
  proposeEmployeeImprovementCandidate,
  type EmployeeAnalytics,
  type EmployeeGraphProjection,
  type EmployeeGrowthEvalCheck,
  type EmployeeGrowthEvalResponse,
  type EmployeeImprovementApplyResponse,
  type EmployeeImprovementCandidateResponse,
} from "../../api/employees";
import {
  getEmployeeWorkLedger,
  type EmployeeAssetWorkRecord,
  type EmployeeQualityFeedbackRecord,
  type EmployeeRuntimeRunRecord,
  type EmployeeTicketReportRecord,
  type EmployeeWorkLedger,
  type TicketWorkItem,
} from "../../api/tickets";
import { cn } from "@/lib/utils";

type DetailTab = "overview" | "work" | "analytics" | "capabilities" | "governance" | "ai_engine";

const DETAIL_TABS: Array<{ key: DetailTab; label: string }> = [
  { key: "overview", label: "Overview" },
  { key: "work", label: "Work Ledger" },
  { key: "analytics", label: "Analytics" },
  { key: "capabilities", label: "Capabilities" },
  { key: "governance", label: "Governance" },
  { key: "ai_engine", label: "AI Engine" },
];

function normalizedDetailTab(value: string | null | undefined): DetailTab {
  return DETAIL_TABS.some((item) => item.key === value) ? value as DetailTab : "overview";
}

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

function loadNumber(employee: ChatEmployeeSummary, key: string): number {
  const value = employee.current_load?.[key];
  return typeof value === "number" ? value : 0;
}

function loadString(employee: ChatEmployeeSummary, key: string): string {
  const value = employee.current_load?.[key];
  return typeof value === "string" ? value : "";
}

function loadList(employee: ChatEmployeeSummary, key: string): string[] {
  const value = employee.current_load?.[key];
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : [];
}

function unknownStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : [];
}

function employeeInitial(employee: ChatEmployeeSummary): string {
  return (employee.display_name || employee.id || "?").trim().charAt(0).toUpperCase() || "?";
}

function employeeState(employee: ChatEmployeeSummary, threads?: ChatThreadListResponse | null): {
  label: string;
  variant: "success" | "warning" | "secondary" | "outline";
} {
  const loadStatus = loadString(employee, "status");
  if (loadStatus === "needs_attention") return { label: "attention", variant: "warning" };
  if (loadNumber(employee, "active_run_count") > 0 || loadStatus === "running") return { label: "running", variant: "success" };
  if (loadNumber(employee, "active_ticket_count") > 0 || ["active", "busy"].includes(loadStatus)) return { label: loadStatus || "active", variant: "secondary" };
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

function analyticsValue(analytics: EmployeeAnalytics | null, key: keyof EmployeeAnalytics): number {
  const value = analytics?.[key];
  return typeof value === "number" ? value : 0;
}

function formatRate(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function formatCost(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "$0.00";
  return `$${value.toFixed(value < 1 ? 4 : 2)}`;
}

function formatLatency(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "0 ms";
  if (value >= 1000) return `${(value / 1000).toFixed(1)} s`;
  return `${Math.round(value)} ms`;
}

function sourceCount(analytics: EmployeeAnalytics | null, key: string): number {
  const value = analytics?.source_counts?.[key];
  return typeof value === "number" ? value : 0;
}

function graphSourceCount(graph: EmployeeGraphProjection | null, key: string): number {
  const value = graph?.source_counts?.[key];
  return typeof value === "number" ? value : 0;
}

function providerProjectionValue(graph: EmployeeGraphProjection | null, key: string): string {
  const profile = graph?.provider_projection?.employee_profile;
  const value = profile?.[key];
  return typeof value === "string" ? value : "";
}

function statusVariant(status: string): "success" | "warning" | "danger" | "secondary" | "outline" {
  if (["passed", "ready", "applied", "already_applied"].includes(status)) return "success";
  if (["warning", "blocked", "needs_attention"].includes(status)) return "warning";
  if (["failed", "error"].includes(status)) return "danger";
  return status ? "secondary" : "outline";
}

function assetStatusLabel(item: EmployeeAssetWorkRecord): string {
  return [item.asset_type, item.status || item.review_state].filter(Boolean).join(" · ") || "asset";
}

function isEmployeeImprovementAsset(item: EmployeeAssetWorkRecord): boolean {
  return item.asset_type === "employee_improvement";
}

function isImprovementApplied(item: EmployeeAssetWorkRecord, localStatus = ""): boolean {
  return ["applied", "already_applied"].includes((localStatus || item.application_status || "").trim().toLowerCase());
}

function sourceKindLabel(sourceKind: string): string {
  if (sourceKind === "kernel_command") return "Kernel Command";
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
    kernelCommands: tools.filter((capability) => capability.source_kind === "kernel_command"),
    mcp: tools.filter((capability) => capability.source_kind === "mcp_server"),
    other: tools.filter((capability) => !["kernel_command", "mcp_server"].includes(capability.source_kind)),
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

function handoffEventData(handoff: Record<string, unknown>): Record<string, unknown> {
  const event = handoff.event;
  if (!event || typeof event !== "object") return {};
  const data = (event as Record<string, unknown>).data;
  return data && typeof data === "object" && !Array.isArray(data) ? data as Record<string, unknown> : {};
}

function handoffDataValue(handoff: Record<string, unknown>, key: string): string {
  const value = handoffEventData(handoff)[key];
  return typeof value === "string" ? value : "";
}

function employeePolicy(employee: ChatEmployeeSummary): Record<string, unknown> {
  return employee.handoff_policy && typeof employee.handoff_policy === "object" && !Array.isArray(employee.handoff_policy)
    ? employee.handoff_policy
    : {};
}

function policyText(policy: Record<string, unknown>, key: string): string {
  const value = policy[key];
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function policyList(policy: Record<string, unknown>, key: string): string[] {
  return unknownStringArray(policy[key]);
}

function policyEnabled(policy: Record<string, unknown>, key: string): boolean {
  return policy[key] === true;
}

function riskBoundaryLabel(policy: Record<string, unknown>): string {
  return policyText(policy, "max_risk_level") || policyText(policy, "risk_boundary") || policyText(policy, "max_risk") || "-";
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
      aria-label={`Open Ticket ${item.ticket_id}`}
      className="flex w-full items-center justify-between gap-3 rounded-md border bg-muted/30 px-3 py-2 text-left transition-colors hover:bg-muted"
      onClick={() => navigateTo("tickets", item.ticket_id)}
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
              aria-label={`Open Ticket ${record.ticket_id} report ${record.report_id}`}
              className="w-full rounded-md px-2 py-2 text-left transition-colors hover:bg-muted"
              onClick={() => navigateTo("tickets", record.ticket_id)}
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
            const relation = handoffValue(handoff, "relation");
            const type = handoffEventValue(handoff, "type") || "handoff";
            const at = handoffEventValue(handoff, "at");
            const fromEmployeeId = handoffDataValue(handoff, "from_employee_id");
            const toEmployeeId = handoffDataValue(handoff, "to_employee_id");
            const sourceRunId = handoffDataValue(handoff, "source_run_id");
            const content = handoffDataValue(handoff, "content");
            return (
              <button
                key={`${ticketId || "handoff"}-${index}`}
                type="button"
                aria-label={ticketId ? `Open Ticket ${ticketId} handoff` : "Open handoff"}
                className="flex w-full items-center justify-between gap-3 rounded-md border bg-muted/30 px-3 py-2 text-left transition-colors hover:bg-muted"
                onClick={() => ticketId && navigateTo("tickets", ticketId)}
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{title}</div>
                  <div className="mt-0.5 flex flex-wrap gap-2 text-xs text-muted-foreground">
                    {ticketId && <span>{ticketId}</span>}
                    <span>{type}</span>
                    {relation && <span>{relation}</span>}
                    {(fromEmployeeId || toEmployeeId) && <span>{`${fromEmployeeId || "-"} -> ${toEmployeeId || "-"}`}</span>}
                    {at && <span>{formatThreadTime(at)}</span>}
                  </div>
                  {sourceRunId && (
                    <div className="mt-1 truncate text-xs text-muted-foreground" title={sourceRunId}>Run: {sourceRunId}</div>
                  )}
                  {content && (
                    <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{content}</div>
                  )}
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

function HandoffBoundarySection({ employee }: { employee: ChatEmployeeSummary }) {
  const policy = employeePolicy(employee);
  const acceptsLanes = policyList(policy, "accepts_lanes");
  const preferredLanes = policyList(policy, "preferred_lanes");
  const memoryScopes = employee.memory_scopes.length ? employee.memory_scopes : policyList(policy, "memory_scopes");
  return (
    <section className="rounded-md border p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Brain className="h-4 w-4 text-muted-foreground" />
          <h4 className="text-sm font-semibold">Memory & Handoff Boundary</h4>
        </div>
        <Badge variant={policyEnabled(policy, "can_receive_handoffs") ? "success" : "warning"}>
          {policyEnabled(policy, "can_receive_handoffs") ? "handoff ready" : "handoff gated"}
        </Badge>
      </div>
      <div className="space-y-3">
        <div>
          <div className="mb-1 text-xs font-medium uppercase text-muted-foreground">Memory Scopes</div>
          <div className="flex flex-wrap gap-1.5">
            {memoryScopes.length ? memoryScopes.map((scope) => <Badge key={scope} variant="secondary">{scope}</Badge>) : <Badge variant="outline">none</Badge>}
          </div>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <InfoRow label="Risk boundary" value={riskBoundaryLabel(policy)} />
          <InfoRow label="Escalates to" value={policyText(policy, "escalate_to") || "-"} />
          <InfoRow label="Max active tickets" value={policyText(policy, "max_active_tickets") || "-"} />
          <InfoRow label="Preferred runtime" value={employee.preferred_runtime || "-"} />
        </div>
        {(acceptsLanes.length || preferredLanes.length) ? (
          <div className="grid gap-2 sm:grid-cols-2">
            <div>
              <div className="mb-1 text-xs font-medium uppercase text-muted-foreground">Accepts Lanes</div>
              <div className="flex flex-wrap gap-1.5">
                {acceptsLanes.length ? acceptsLanes.map((lane) => <Badge key={lane} variant="outline">{lane}</Badge>) : <Badge variant="outline">none</Badge>}
              </div>
            </div>
            <div>
              <div className="mb-1 text-xs font-medium uppercase text-muted-foreground">Preferred Lanes</div>
              <div className="flex flex-wrap gap-1.5">
                {preferredLanes.length ? preferredLanes.map((lane) => <Badge key={lane} variant="outline">{lane}</Badge>) : <Badge variant="outline">none</Badge>}
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function assetContributionTarget(item: EmployeeAssetWorkRecord): { id: string; detail: string } {
  if (item.status === "approved" && item.asset_id) {
    return { id: "asset", detail: item.asset_id };
  }
  return { id: "review", detail: item.candidate_id ? `candidate:${item.candidate_id}` : item.asset_id };
}

function AssetContributionSection({ work }: { work: EmployeeWorkLedger | null }) {
  const candidates = work?.asset_candidates ?? [];
  const approved = work?.approved_assets ?? [];
  const visible = [...candidates, ...approved].slice(0, 8);
  return (
    <section className="rounded-md border p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold">Asset Contributions</h4>
        <Badge variant="outline">{candidates.length} proposed / {approved.length} approved</Badge>
      </div>
      {visible.length ? (
        <div className="space-y-2">
          {visible.map((item) => {
            const target = assetContributionTarget(item);
            return (
              <button
                key={`${item.asset_id || item.candidate_id}-${item.status}`}
                type="button"
                aria-label={`Open Asset ${target.detail.replace(/^candidate:/, "")}`}
                className="flex w-full items-center justify-between gap-3 rounded-md border bg-muted/30 px-3 py-2 text-left transition-colors hover:bg-muted"
                onClick={() => navigateTo("assets", target.id, target.detail)}
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{item.title || item.asset_id || item.candidate_id}</div>
                  <div className="mt-0.5 flex flex-wrap gap-2 text-xs text-muted-foreground">
                    <span>{assetStatusLabel(item)}</span>
                    {item.source_ticket_id && <span>{item.source_ticket_id}</span>}
                    {item.source_run_id && <span>{item.source_run_id}</span>}
                  </div>
                </div>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
              </button>
            );
          })}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No Asset candidates or approved Assets yet.</p>
      )}
    </section>
  );
}

function runtimeSessionKey(run: EmployeeRuntimeRunRecord, employeeId: string): string {
  return run.session_key || `${employeeId}::${run.run_id || run.request_id || "runtime"}::${run.ticket_id || "none"}`;
}

function RuntimeRunSection({ employeeId, runs }: { employeeId: string; runs: EmployeeRuntimeRunRecord[] }) {
  return (
    <section className="rounded-md border p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold">Runtime Run Ledger</h4>
        <Badge variant="outline">{runs.length}</Badge>
      </div>
      {runs.length ? (
        <div className="space-y-2">
          {runs.slice(0, 8).map((run) => (
            <button
              key={run.request_id}
              type="button"
              aria-label={`Open Runtime Replay ${runtimeSessionKey(run, employeeId)}`}
              className="w-full rounded-md border bg-muted/30 px-3 py-2 text-left transition-colors hover:bg-muted"
              onClick={() => navigateTo("runtime", runtimeSessionKey(run, employeeId))}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{run.request_id}</div>
                  <div className="mt-0.5 flex flex-wrap gap-2 text-xs text-muted-foreground">
                    <span>{run.status}</span>
                    {run.action && <span>{run.action}</span>}
                    {run.executor_id && <span>{run.executor_id}</span>}
                  </div>
                </div>
                <Badge variant="outline" className="shrink-0">{run.tool_event_count} tools</Badge>
              </div>
              <div className="mt-2 grid gap-2 text-xs text-muted-foreground sm:grid-cols-3">
                <span>{run.evidence_count} evidence</span>
                <span>{formatLatency(run.latency_ms)}</span>
                <span>{formatCost(run.total_cost)}</span>
              </div>
            </button>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No runtime execution records yet.</p>
      )}
    </section>
  );
}

function QualityFeedbackSection({
  employeeId,
  feedback,
  onProposeImprovement,
}: {
  employeeId: string;
  feedback: EmployeeQualityFeedbackRecord[];
  onProposeImprovement: (employeeId: string, feedback: EmployeeQualityFeedbackRecord) => Promise<EmployeeImprovementCandidateResponse>;
}) {
  const [proposingId, setProposingId] = useState("");
  const [proposal, setProposal] = useState<{ feedbackId: string; candidateId: string } | null>(null);
  const [proposalError, setProposalError] = useState("");

  async function handleProposeImprovement(item: EmployeeQualityFeedbackRecord) {
    if (proposingId) return;
    setProposingId(item.id);
    setProposalError("");
    try {
      const response = await onProposeImprovement(employeeId, item);
      const candidateId = typeof response.candidate.id === "string" ? response.candidate.id : "";
      setProposal(candidateId ? { feedbackId: item.id, candidateId } : null);
    } catch (err) {
      setProposalError(err instanceof Error ? err.message : "Failed to propose improvement");
    } finally {
      setProposingId("");
    }
  }

  return (
    <section className="rounded-md border p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold">Quality Feedback</h4>
        <Badge variant="outline">{feedback.length}</Badge>
      </div>
      {proposalError ? (
        <div className="mb-3 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {proposalError}
        </div>
      ) : null}
      {feedback.length ? (
        <div className="space-y-2">
          {feedback.slice(0, 8).map((item) => (
            <div key={item.id} className="rounded-md border bg-muted/30 px-3 py-2">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium">{item.summary || item.id}</span>
                <Badge variant="outline" className="shrink-0">{item.status}</Badge>
              </div>
              <div className="mt-1 flex flex-wrap gap-2 text-xs text-muted-foreground">
                <span>{item.kind || "feedback"}</span>
                {item.source_ref && <span>{item.source_ref}</span>}
                {item.reviewer_employee_id && <span>{item.reviewer_employee_id}</span>}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={Boolean(proposingId)}
                  onClick={() => void handleProposeImprovement(item)}
                >
                  <Sparkles className="h-3.5 w-3.5" />
                  {proposingId === item.id ? "Proposing" : "Propose Improvement"}
                </Button>
                {proposal?.feedbackId === item.id ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => navigateTo("assets", "review", `candidate:${proposal.candidateId}`)}
                  >
                    <Database className="h-3.5 w-3.5" />
                    {proposal.candidateId}
                  </Button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No quality feedback records yet.</p>
      )}
    </section>
  );
}

function EmployeeImprovementPathSection({
  employeeId,
  onApplyImprovement,
  work,
}: {
  employeeId: string;
  onApplyImprovement: (employeeId: string, assetId: string) => Promise<EmployeeImprovementApplyResponse>;
  work: EmployeeWorkLedger | null;
}) {
  const candidates = (work?.asset_candidates ?? []).filter(isEmployeeImprovementAsset);
  const approvedAssets = (work?.approved_assets ?? []).filter(isEmployeeImprovementAsset);
  const [applyingAssetId, setApplyingAssetId] = useState("");
  const [localStatusByAssetId, setLocalStatusByAssetId] = useState<Record<string, string>>({});
  const [applyError, setApplyError] = useState("");
  const appliedCount = approvedAssets.filter((item) => isImprovementApplied(item, localStatusByAssetId[item.asset_id])).length;

  async function handleApplyImprovement(item: EmployeeAssetWorkRecord) {
    if (applyingAssetId || !item.asset_id) return;
    setApplyingAssetId(item.asset_id);
    setApplyError("");
    try {
      const response = await onApplyImprovement(employeeId, item.asset_id);
      setLocalStatusByAssetId((current) => ({ ...current, [item.asset_id]: response.status }));
    } catch (err) {
      setApplyError(err instanceof Error ? err.message : "Failed to apply improvement");
    } finally {
      setApplyingAssetId("");
    }
  }

  return (
    <section className="rounded-md border p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold">Improvement Path</h4>
        <Badge variant="outline">{appliedCount}/{approvedAssets.length} applied</Badge>
      </div>
      <div className="mb-3 grid gap-3 sm:grid-cols-3">
        <StatCard icon={AlertTriangle} label="Feedback" value={work?.quality_feedback.length ?? 0} />
        <StatCard icon={Sparkles} label="Candidates" value={candidates.length} />
        <StatCard icon={ShieldCheck} label="Approved" value={approvedAssets.length} />
      </div>
      {applyError ? (
        <div className="mb-3 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {applyError}
        </div>
      ) : null}
      {candidates.length ? (
        <div className="mb-3 space-y-2">
          <h5 className="text-xs font-semibold uppercase text-muted-foreground">Candidate Review</h5>
          {candidates.slice(0, 4).map((item) => (
            <div key={item.candidate_id || item.asset_id} className="rounded-md border bg-muted/30 px-3 py-2">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium">{item.title || item.candidate_id}</span>
                <Badge variant="outline" className="shrink-0">{item.review_state || item.status}</Badge>
              </div>
              <div className="mt-1 flex flex-wrap gap-2 text-xs text-muted-foreground">
                {item.source_ticket_id && <span>{item.source_ticket_id}</span>}
                {item.source_ref && <span>{item.source_ref}</span>}
              </div>
              {item.candidate_id && (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="mt-3"
                  onClick={() => navigateTo("assets", "review", `candidate:${item.candidate_id}`)}
                >
                  <Database className="h-3.5 w-3.5" />
                  Open Candidate
                </Button>
              )}
            </div>
          ))}
        </div>
      ) : null}
      {approvedAssets.length ? (
        <div className="space-y-2">
          <h5 className="text-xs font-semibold uppercase text-muted-foreground">Approved Assets</h5>
          {approvedAssets.slice(0, 4).map((item) => {
            const localStatus = localStatusByAssetId[item.asset_id];
            const applied = isImprovementApplied(item, localStatus);
            const status = localStatus || item.application_status || "not applied";
            return (
              <div key={item.asset_id || item.candidate_id} className="rounded-md border bg-muted/30 px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium">{item.title || item.asset_id}</span>
                  <Badge variant={applied ? "success" : "outline"} className="shrink-0">{status}</Badge>
                </div>
                <div className="mt-1 flex flex-wrap gap-2 text-xs text-muted-foreground">
                  {item.source_ticket_id && <span>{item.source_ticket_id}</span>}
                  {item.application_report_id && <span>{item.application_report_id}</span>}
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {item.asset_id && (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => navigateTo("assets", "asset", item.asset_id)}
                    >
                      <Database className="h-3.5 w-3.5" />
                      Open Asset
                    </Button>
                  )}
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={applied || Boolean(applyingAssetId)}
                    onClick={() => void handleApplyImprovement(item)}
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    {applyingAssetId === item.asset_id ? "Applying" : "Apply Improvement"}
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      ) : candidates.length ? null : (
        <p className="text-sm text-muted-foreground">No governed improvement assets yet.</p>
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

function LoadSnapshotSection({ employee }: { employee: ChatEmployeeSummary }) {
  const activeTicketIds = loadList(employee, "active_ticket_ids");
  const activeRunIds = loadList(employee, "active_run_ids");
  return (
    <section className="rounded-md border p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold">Load Snapshot</h4>
        <Badge variant="outline">{loadString(employee, "status") || "available"}</Badge>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard icon={GitBranch} label="Active Tickets" value={loadNumber(employee, "active_ticket_count")} />
        <StatCard icon={Activity} label="Runtime Runs" value={loadNumber(employee, "active_run_count")} />
        <StatCard icon={ShieldCheck} label="Waiting Approval" value={loadNumber(employee, "needs_approval_run_count")} />
      </div>
      <div className="mt-3 space-y-2 text-xs text-muted-foreground">
        <div className="truncate" title={activeTicketIds.join(", ") || "none"}>
          Tickets: {activeTicketIds.join(", ") || "none"}
        </div>
        <div className="truncate" title={activeRunIds.join(", ") || "none"}>
          Runs: {activeRunIds.join(", ") || "none"}
        </div>
      </div>
    </section>
  );
}

function ProviderProjectionSection({ graph }: { graph: EmployeeGraphProjection | null }) {
  const status = providerProjectionValue(graph, "status") || "not_projected";
  const assetId = providerProjectionValue(graph, "asset_id");
  const backendStatus = providerProjectionValue(graph, "backend_status");
  const episodeId = providerProjectionValue(graph, "episode_id");
  return (
    <section className="rounded-md border p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold">Provider Projection</h4>
        <Badge variant="outline">{status}</Badge>
      </div>
      <InfoRow label="Provider" value="Graphiti" />
      <InfoRow label="Profile asset" value={assetId || "-"} />
      <InfoRow label="Backend" value={backendStatus || "-"} />
      <InfoRow label="Episode" value={episodeId || "-"} />
    </section>
  );
}

function formatGrowthEvidenceValue(value: unknown): string {
  if (value === null) return "null";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.length ? value.map((item) => formatGrowthEvidenceValue(item)).join(", ") : "none";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return "";
}

function EmployeeGrowthCheckItem({ check }: { check: EmployeeGrowthEvalCheck }) {
  const evidenceEntries = Object.entries(check.evidence ?? {});
  return (
    <div className="rounded-md border bg-muted/30 px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <span className="min-w-0 truncate text-sm font-medium" title={check.id}>{check.id}</span>
        <Badge variant={statusVariant(check.status)} className="shrink-0">{check.status}</Badge>
      </div>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">{check.detail}</p>
      {evidenceEntries.length ? (
        <div className="mt-2 flex flex-wrap gap-2">
          {evidenceEntries.map(([key, value]) => {
            const formatted = formatGrowthEvidenceValue(value);
            return (
              <Badge key={key} variant="outline" className="max-w-full truncate" title={`${key}: ${formatted}`}>
                {key}: {formatted}
              </Badge>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function EmployeeGrowthEvidenceSection({
  growthEval,
  loading,
}: {
  growthEval: EmployeeGrowthEvalResponse | null;
  loading: boolean;
}) {
  const summary = growthEval?.summary;
  const warningCount = growthEval?.warnings.length ?? 0;
  const blockerCount = growthEval?.blockers.length ?? 0;
  const checks = growthEval?.checks ?? [];
  const warnings = growthEval?.warnings ?? [];
  const blockers = growthEval?.blockers ?? [];
  const commands = growthEval?.commands ?? [];
  return (
    <section className="rounded-md border p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-muted-foreground" />
          <h4 className="text-sm font-semibold">Growth Evidence</h4>
        </div>
        <Badge variant={statusVariant(growthEval?.status ?? "")}>
          {loading && !growthEval ? "loading" : growthEval?.status ?? "pending"}
        </Badge>
      </div>
      {!growthEval ? (
        <p className="text-sm text-muted-foreground">
          {loading ? "Loading Employee growth evidence." : "Employee growth evidence is not available yet."}
        </p>
      ) : (
        <div className="space-y-3">
          <p className="text-sm leading-6 text-muted-foreground">{growthEval.detail}</p>
          <div className="grid gap-3 sm:grid-cols-3">
            <StatCard icon={AlertTriangle} label="Feedback" value={summary?.quality_feedback_count ?? 0} />
            <StatCard icon={Activity} label="Runtime Runs" value={summary?.runtime_run_count ?? 0} />
            <StatCard icon={ShieldCheck} label="Handoff Score" value={summary?.handoff_work_history_score ?? 0} />
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant={statusVariant(summary?.current_load_status ?? "")}>
              load {summary?.current_load_status?.replace(/_/g, " ") || "-"}
            </Badge>
            <Badge variant={statusVariant(summary?.improvement_loop_proof_status ?? "")}>
              proof {summary?.improvement_loop_proof_status?.replace(/_/g, " ") || "-"}
            </Badge>
            <Badge variant={statusVariant(summary?.improvement_loop_application_status ?? "")}>
              application {summary?.improvement_loop_application_status?.replace(/_/g, " ") || "-"}
            </Badge>
            <Badge variant="outline">{summary?.improvement_loop_applied_change_count ?? 0} proof changes</Badge>
            {summary?.improvement_loop_ticket_report_id ? (
              <Badge variant="outline">{summary.improvement_loop_ticket_report_id}</Badge>
            ) : null}
            {warningCount ? <Badge variant="warning">{warningCount} warnings</Badge> : null}
            {blockerCount ? <Badge variant="danger">{blockerCount} blockers</Badge> : null}
          </div>
          {checks.length ? (
            <div className="space-y-2">
              <h5 className="text-xs font-semibold uppercase text-muted-foreground">Growth Checks</h5>
              <div className="grid gap-2 md:grid-cols-2">
                {checks.map((check) => <EmployeeGrowthCheckItem key={check.id} check={check} />)}
              </div>
            </div>
          ) : null}
          {warnings.length || blockers.length ? (
            <div className="space-y-2">
              <h5 className="text-xs font-semibold uppercase text-muted-foreground">Signals</h5>
              <div className="flex flex-wrap gap-2">
                {warnings.map((warning) => (
                  <Badge key={`warning-${warning}`} variant="warning" className="max-w-full truncate" title={warning}>
                    warning {warning}
                  </Badge>
                ))}
                {blockers.map((blocker) => (
                  <Badge key={`blocker-${blocker}`} variant="danger" className="max-w-full truncate" title={blocker}>
                    blocker {blocker}
                  </Badge>
                ))}
              </div>
            </div>
          ) : null}
          {commands.length ? (
            <div className="space-y-2">
              <h5 className="text-xs font-semibold uppercase text-muted-foreground">Evidence Commands</h5>
              <div className="space-y-2">
                {commands.map((command) => (
                  <code
                    key={command}
                    className="block min-w-0 truncate rounded-md border bg-background px-3 py-2 font-mono text-[11px] text-muted-foreground"
                    title={command}
                  >
                    {command}
                  </code>
                ))}
              </div>
            </div>
          ) : null}
        </div>
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
  analytics,
  capabilities,
  employee,
  graph,
  growthEval,
  growthEvalLoading,
  initialTab,
  onApplyImprovement,
  onDefaultEngineChange,
  onProposeImprovement,
  threads,
  work,
}: {
  aiEngines: ChatAiEngineSettings | null;
  analytics: EmployeeAnalytics | null;
  capabilities: CapabilityRecord[];
  employee: ChatEmployeeSummary;
  graph: EmployeeGraphProjection | null;
  growthEval: EmployeeGrowthEvalResponse | null;
  growthEvalLoading: boolean;
  initialTab: DetailTab;
  onApplyImprovement: (employeeId: string, assetId: string) => Promise<EmployeeImprovementApplyResponse>;
  onDefaultEngineChange: (employeeId: string, defaultAiEngine: string) => Promise<ChatEmployeeSummary>;
  onProposeImprovement: (employeeId: string, feedback: EmployeeQualityFeedbackRecord) => Promise<EmployeeImprovementCandidateResponse>;
  threads: ChatThreadListResponse | null;
  work: EmployeeWorkLedger | null;
}) {
  const [tab, setTab] = useState<DetailTab>(initialTab);
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
  const groupedGraphEdges = Object.entries(graph?.grouped_edges ?? {});
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

  useEffect(() => {
    setTab(initialTab);
  }, [employee.id, initialTab]);

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
          <Button type="button" variant="outline" size="sm" onClick={() => navigateTo("assets", "capabilities", "kernel-commands")}>
            <Wrench className="h-4 w-4" />
            Commands
          </Button>
        </div>
      </div>

      <div className="border-b px-3">
        <div className="flex gap-1 overflow-hidden">
          {DETAIL_TABS.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => {
                setTab(item.key);
                navigateTo("employees", employee.id, item.key);
              }}
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

            <LoadSnapshotSection employee={employee} />

            <EmployeeGrowthEvidenceSection growthEval={growthEval} loading={growthEvalLoading} />

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

            <HandoffBoundarySection employee={employee} />

            <ProviderProjectionSection graph={graph} />

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
              <StatCard icon={Sparkles} label="Assets Proposed" value={contributionValue(work, "asset_candidate_count")} />
              <StatCard icon={Activity} label="Runtime Runs" value={contributionValue(work, "runtime_run_count")} />
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

            <AssetContributionSection work={work} />

            <RuntimeRunSection employeeId={employee.id} runs={work?.runtime_runs ?? []} />

            <QualityFeedbackSection
              employeeId={employee.id}
              feedback={work?.quality_feedback ?? []}
              onProposeImprovement={onProposeImprovement}
            />

            <EmployeeImprovementPathSection
              employeeId={employee.id}
              work={work}
              onApplyImprovement={onApplyImprovement}
            />
          </div>
        )}

        {tab === "analytics" && (
          <div className="space-y-4">
            <section className="rounded-md border p-4">
              <div className="mb-3 flex items-center justify-between gap-2">
                <h4 className="text-sm font-semibold">Phase 4a Core Metrics</h4>
                <Badge variant="outline">Ticket facts</Badge>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <StatCard icon={GitBranch} label="Assigned Tickets" value={analyticsValue(analytics, "assigned_ticket_count")} />
                <StatCard icon={ClipboardCheck} label="Completed Tickets" value={analyticsValue(analytics, "completed_ticket_count")} />
                <StatCard icon={ShieldCheck} label="Validation Pass Rate" value={formatRate(analyticsValue(analytics, "validation_pass_rate"))} />
                <StatCard icon={Sparkles} label="Candidates Produced" value={analyticsValue(analytics, "candidates_produced")} />
                <StatCard icon={Brain} label="Recalled Assets" value={analyticsValue(analytics, "recalled_asset_count")} />
              </div>
            </section>

            <section className="rounded-md border p-4">
              <div className="mb-3 flex items-center justify-between gap-2">
                <h4 className="text-sm font-semibold">Phase 4b Quality Signals</h4>
                <Badge variant="outline">Runtime facts</Badge>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <StatCard icon={AlertTriangle} label="Blockers" value={analyticsValue(analytics, "blocker_count")} />
                <StatCard icon={ShieldCheck} label="Validation Failures" value={analyticsValue(analytics, "validation_failure_count")} />
                <StatCard icon={Database} label="Stale Assets" value={analyticsValue(analytics, "stale_asset_count")} />
                <StatCard icon={Brain} label="Useful Recalls" value={analyticsValue(analytics, "useful_recall_count")} />
                <StatCard icon={Activity} label="Execution Runs" value={analyticsValue(analytics, "execution_run_count")} />
                <StatCard icon={Clock3} label="Avg Latency" value={formatLatency(analyticsValue(analytics, "average_latency_ms"))} />
                <StatCard icon={Sparkles} label="Total Cost" value={formatCost(analyticsValue(analytics, "total_cost"))} />
              </div>
            </section>

            <section className="rounded-md border p-4">
              <h4 className="mb-3 text-sm font-semibold">Evidence Sources</h4>
              <InfoRow label="Tickets" value={sourceCount(analytics, "tickets")} />
              <InfoRow label="Reports" value={sourceCount(analytics, "reports")} />
              <InfoRow label="Events" value={sourceCount(analytics, "events")} />
              <InfoRow label="Assets" value={sourceCount(analytics, "assets")} />
              <InfoRow label="Execution Runs" value={sourceCount(analytics, "execution_runs")} />
            </section>

            <section className="rounded-md border p-4">
              <div className="mb-3 flex items-center justify-between gap-2">
                <h4 className="text-sm font-semibold">Graph Provenance</h4>
                <Badge variant="outline">Employee graph</Badge>
              </div>
              {!graph ? (
                <p className="text-sm text-muted-foreground">Employee graph facts are not available yet.</p>
              ) : (
                <div className="space-y-3">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <StatCard icon={GitBranch} label="Graph Nodes" value={graph.nodes.length} />
                    <StatCard icon={Activity} label="Graph Edges" value={graph.edges.length} />
                  </div>
                  <div>
                    <h5 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Source Counts</h5>
                    <div className="grid gap-2 sm:grid-cols-2">
                      <InfoRow label="Tickets" value={graphSourceCount(graph, "tickets")} />
                      <InfoRow label="Reports" value={graphSourceCount(graph, "reports")} />
                      <InfoRow label="Events" value={graphSourceCount(graph, "events")} />
                      <InfoRow label="Assets" value={graphSourceCount(graph, "assets")} />
                    </div>
                  </div>
                  {groupedGraphEdges.length > 0 && (
                    <div>
                      <h5 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Grouped Edges</h5>
                      <div className="space-y-2">
                        {groupedGraphEdges.slice(0, 5).map(([edgeType, edges]) => (
                          <div key={edgeType} className="rounded-md border bg-muted/30 p-3">
                            <div className="mb-2 flex items-center justify-between gap-2">
                              <span className="truncate text-sm font-medium" title={edgeType}>{edgeType}</span>
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
                </div>
              )}
            </section>

            <ProviderProjectionSection graph={graph} />

            {!analytics && (
              <section className="rounded-md border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-900">
                Analytics facts are not available for this Employee yet.
              </section>
            )}
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
              title="Kernel Commands"
              capabilities={groupedCapabilities.kernelCommands}
              empty="No Kernel commands mapped."
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
            <HandoffBoundarySection employee={employee} />

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

export function EmployeesPage({ selectedDetail, selectedId }: { selectedDetail?: string | null; selectedId: string | null }) {
  const [employees, setEmployees] = useState<ChatEmployeeSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [threadsMap, setThreadsMap] = useState<Record<string, ChatThreadListResponse>>({});
  const [workMap, setWorkMap] = useState<Record<string, EmployeeWorkLedger>>({});
  const [analyticsMap, setAnalyticsMap] = useState<Record<string, EmployeeAnalytics>>({});
  const [graphMap, setGraphMap] = useState<Record<string, EmployeeGraphProjection>>({});
  const [growthEvalMap, setGrowthEvalMap] = useState<Record<string, EmployeeGrowthEvalResponse>>({});
  const [growthEvalLoadingId, setGrowthEvalLoadingId] = useState("");
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

      const [threadsResults, workResults, analyticsResults, graphResults] = await Promise.all([
        Promise.allSettled(loaded.map((m) => listChatThreads(m.id))),
        Promise.allSettled(loaded.map((m) => getEmployeeWorkLedger(m.id))),
        Promise.allSettled(loaded.map((m) => getEmployeeAnalytics(m.id))),
        Promise.allSettled(loaded.map((m) => getEmployeeGraph(m.id))),
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
      const newAnalyticsMap: Record<string, EmployeeAnalytics> = {};
      analyticsResults.forEach((result, idx) => {
        if (result.status === "fulfilled") {
          newAnalyticsMap[loaded[idx].id] = result.value;
        }
      });
      setAnalyticsMap(newAnalyticsMap);
      const newGraphMap: Record<string, EmployeeGraphProjection> = {};
      graphResults.forEach((result, idx) => {
        if (result.status === "fulfilled") {
          newGraphMap[loaded[idx].id] = result.value;
        }
      });
      setGraphMap(newGraphMap);
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
  const selectedAnalytics = selectedEmployee ? analyticsMap[selectedEmployee.id] ?? null : null;
  const selectedGraph = selectedEmployee ? graphMap[selectedEmployee.id] ?? null : null;
  const selectedGrowthEval = selectedEmployee ? growthEvalMap[selectedEmployee.id] ?? null : null;
  const selectedCapabilities = useMemo(
    () => capabilitiesForEmployee(selectedEmployee, capabilityRegistry),
    [capabilityRegistry, selectedEmployee],
  );
  const selectedTab = normalizedDetailTab(selectedDetail);

  const aggregateThreadCount = useMemo(
    () => employees.reduce((sum, employee) => sum + threadCount(threadsMap[employee.id]), 0),
    [employees, threadsMap],
  );
  const aggregateMessageCount = useMemo(
    () => employees.reduce((sum, employee) => sum + totalMessages(threadsMap[employee.id]), 0),
    [employees, threadsMap],
  );

  useEffect(() => {
    if (!selectedEmployee) return;
    if (growthEvalMap[selectedEmployee.id]) return;
    let active = true;
    setGrowthEvalLoadingId(selectedEmployee.id);
    getEmployeeGrowthEval(selectedEmployee.id)
      .then((growthEval) => {
        if (!active) return;
        setGrowthEvalMap((current) => ({ ...current, [selectedEmployee.id]: growthEval }));
      })
      .catch(() => {
        if (!active) return;
      })
      .finally(() => {
        if (active) setGrowthEvalLoadingId("");
      });
    return () => {
      active = false;
    };
  }, [growthEvalMap, selectedEmployee]);

  async function handleDefaultEngineChange(employeeId: string, defaultAiEngine: string): Promise<ChatEmployeeSummary> {
    const updated = await updateChatEmployeeAiEngine(employeeId, { default_ai_engine: defaultAiEngine });
    setEmployees((current) => current.map((employee) => (employee.id === updated.id ? updated : employee)));
    return updated;
  }

  async function handleProposeImprovement(
    employeeId: string,
    feedback: EmployeeQualityFeedbackRecord,
  ): Promise<EmployeeImprovementCandidateResponse> {
    const response = await proposeEmployeeImprovementCandidate(employeeId, feedback.id, {
      actor_employee_id: "clara",
      reason: `Proposed from Employee work ledger feedback ${feedback.id}.`,
    });
    const [updatedWork, updatedGrowthEval] = await Promise.all([
      getEmployeeWorkLedger(employeeId),
      getEmployeeGrowthEval(employeeId).catch(() => null),
    ]);
    setWorkMap((current) => ({ ...current, [employeeId]: updatedWork }));
    if (updatedGrowthEval) {
      setGrowthEvalMap((current) => ({ ...current, [employeeId]: updatedGrowthEval }));
    }
    return response;
  }

  async function handleApplyImprovement(employeeId: string, assetId: string): Promise<EmployeeImprovementApplyResponse> {
    const response = await applyEmployeeImprovementAsset(employeeId, assetId, {
      actor_employee_id: "clara",
      reason: "Applied from Employee work ledger improvement path.",
    });
    const [updatedWork, updatedEmployees, updatedGrowthEval] = await Promise.all([
      getEmployeeWorkLedger(employeeId),
      listChatEmployees(),
      getEmployeeGrowthEval(employeeId).catch(() => null),
    ]);
    setWorkMap((current) => ({ ...current, [employeeId]: updatedWork }));
    setEmployees(updatedEmployees);
    if (updatedGrowthEval) {
      setGrowthEvalMap((current) => ({ ...current, [employeeId]: updatedGrowthEval }));
    }
    return response;
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
                    onClick={() => navigateTo("employees", employee.id, selectedTab)}
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
          analytics={selectedAnalytics}
          capabilities={selectedCapabilities}
          employee={selectedEmployee}
          graph={selectedGraph}
          growthEval={selectedGrowthEval}
          growthEvalLoading={growthEvalLoadingId === selectedEmployee.id}
          initialTab={selectedTab}
          onApplyImprovement={handleApplyImprovement}
          onDefaultEngineChange={handleDefaultEngineChange}
          onProposeImprovement={handleProposeImprovement}
          threads={selectedThreads}
          work={selectedWork}
        />
      )}
    </div>
  );
}
