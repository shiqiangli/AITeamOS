import { type FormEvent, type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import {
  Archive, BookOpen, Brain, Check, ClipboardCheck, Layers3, Link2,
  FileText, RefreshCw, Search, Sparkles,
  Wrench, X,
} from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "../../components/ui/dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "../../components/ui/table";
import { Input } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import { Textarea } from "../../components/ui/textarea";
import { ErrorState, EmptyState, Status, navigateTo } from "../../components/shared";
import { Skeleton } from "../../components/ui/skeleton";
import {
  listAssetCandidates,
  listAssets,
  projectAssetRecordRelationshipsToGraphiti,
  projectAssetRecordToGraphiti,
  reviewAssetCandidate,
  reviewAssetCandidatesBatch,
  type AssetCandidateRecord,
  type AssetRecord,
} from "../../api/assets";
import {
  getKnowledgeStatus, listKnowledgeDocs, listKnowledgeDecisions,
  listKnowledgeReviewQueue,
  type DecisionRecord, type KnowledgeDocSummary,
  type KnowledgeStatusResponse, type ReviewQueueItem,
} from "../../api/knowledge";
import {
  approveMemoryCandidate, listApprovedMemory, type MemoryCandidate,
  reviewMemoryCandidate, reviewMemoryRecallUsage,
} from "../../api/memory";
import {
  listRuntimeExecutorApprovals, reviewRuntimeExecutorApproval, runRuntimeExecutorApproval,
  type RuntimeApprovalRecord,
} from "../../api/runtimeExecutors";
import { getSystemStatus, type PlanV8ArtifactSummary } from "../../api/systemStatus";
import {
  getCapabilities, type CapabilityRecord, type CapabilityRegistryResponse,
} from "../../api/capabilities";
import { listChatSkills, type ChatSkillSummary } from "../../api/chat";
import { applyEmployeeImprovementAsset } from "../../api/employees";
import { cn } from "@/lib/utils";

/* ── types & constants ─────────────────────────────────────────────────────── */

type AssetArea = "knowledge" | "capabilities" | "review";
type KnowledgeTab = "docs" | "memories" | "decisions";
type CapabilityTab = "skills" | "kernel-commands" | "mcp-tools";
type ReviewTab = "memories" | "decisions" | "skills" | "tools";
type AssetCandidateReviewStatus = "approved" | "rejected" | "merged" | "linked";

const AREA_TABS: Array<{ key: AssetArea; label: string; icon: typeof Brain }> = [
  { key: "knowledge", label: "Knowledge", icon: Brain },
  { key: "capabilities", label: "Capabilities", icon: Wrench },
  { key: "review", label: "Review Queue", icon: ClipboardCheck },
];

const KNOWLEDGE_TABS: Array<{ key: KnowledgeTab; label: string }> = [
  { key: "docs", label: "Docs" },
  { key: "memories", label: "Memories" },
  { key: "decisions", label: "Decisions" },
];
const KNOWLEDGE_TAB_KEYS = new Set<string>(KNOWLEDGE_TABS.map((tab) => tab.key));

const CAPABILITY_TABS: Array<{ key: CapabilityTab; label: string }> = [
  { key: "skills", label: "Skills" },
  { key: "kernel-commands", label: "Kernel Commands" },
  { key: "mcp-tools", label: "MCP Tools" },
];
const CAPABILITY_TAB_KEYS = new Set<string>(CAPABILITY_TABS.map((tab) => tab.key));
const REVIEW_TAB_KEYS = new Set<string>(["memories", "decisions", "skills", "tools"]);

/* ── helpers ───────────────────────────────────────────────────────────────── */

function areaFromRoute(v?: string | null): AssetArea | null {
  if (!v || v === "all") return null;
  if (v === "skills" || v === "kernel-commands" || v === "mcp-tools") return "capabilities";
  return AREA_TABS.some((t) => t.key === v) ? (v as AssetArea) : null;
}

function routeTargetFromDetail(area: AssetArea | null, selectedArea?: string | null, selectedDetail?: string | null): string {
  const rawArea = selectedArea?.trim() ?? "";
  const detail = selectedDetail?.trim() ?? "";
  if (rawArea === "asset") return detail;
  if (!detail || !area) return "";
  if (area === "knowledge" && KNOWLEDGE_TAB_KEYS.has(detail)) return "";
  if (area === "capabilities" && CAPABILITY_TAB_KEYS.has(detail)) return "";
  if (area === "review" && REVIEW_TAB_KEYS.has(detail)) return "";
  return detail;
}

function stripRoutePrefix(value: string, prefix: string): string {
  return value.startsWith(`${prefix}:`) ? value.slice(prefix.length + 1) : value;
}

function knowledgeTabFromRouteTarget(target: string): KnowledgeTab {
  if (target.startsWith("doc:")) return "docs";
  if (target.startsWith("decision:")) return "decisions";
  return "memories";
}

function routeTargetId(target: string): string {
  let value = target.trim();
  for (const prefix of ["asset", "memory", "doc", "decision", "candidate", "approval", "skill"]) {
    value = stripRoutePrefix(value, prefix);
  }
  return value;
}

function fmtTime(v?: string | null): string {
  if (!v) return "-";
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? "-" : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function statusVar(s: string): "default" | "secondary" | "warning" | "success" | "danger" | "outline" {
  if (["approved", "accepted", "ready", "configured", "active", "local", "available", "used", "promoted", "passed"].includes(s)) return "success";
  if (["proposed", "candidate", "planned", "pending", "held", "warning"].includes(s)) return "warning";
  if (["failed", "blocked", "invalid", "missing", "harmful"].includes(s)) return "danger";
  if (["irrelevant", "unreviewed"].includes(s)) return "outline";
  return "secondary";
}

function assetDomain(a: AssetRecord): string {
  return typeof a.metadata.asset_domain === "string" ? a.metadata.asset_domain : "";
}
function assetType(a: AssetRecord): string {
  return typeof a.metadata.asset_type === "string" ? a.metadata.asset_type : a.kind;
}
function metaStr(a: AssetRecord, k: string): string {
  return typeof a.metadata[k] === "string" ? a.metadata[k] as string : "";
}

type FullTextPayload = {
  title: string;
  source?: string;
  content: string;
};

function prettyJson(value: unknown): string {
  if (value === undefined || value === null || value === "") return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function metadataBlock(metadata: Record<string, unknown>): string {
  const entries = Object.entries(metadata).filter(([key]) => !["asset_domain", "asset_type", "content", "description"].includes(key));
  return entries.length ? JSON.stringify(Object.fromEntries(entries), null, 2) : "";
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item).trim()).filter(Boolean);
}

function numberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function summaryList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item).trim()).filter(Boolean) : [];
}

function provenanceText(provenance: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = provenance[key];
    if (value === undefined || value === null || value === "") continue;
    if (typeof value === "string") {
      const trimmed = value.trim();
      if (trimmed) return trimmed;
    } else if (typeof value === "number" || typeof value === "boolean") {
      return String(value);
    } else if (Array.isArray(value)) {
      const text = value.map((item) => typeof item === "string" ? item : prettyJson(item)).filter(Boolean).join(", ");
      if (text) return text;
    } else {
      const text = prettyJson(value);
      if (text) return text;
    }
  }
  return "";
}

function graphitiStatusText(mem: MemoryCandidate): string {
  const status = mem.graphiti_status?.status;
  if (typeof status === "string" && status.trim()) return status.trim();
  return prettyJson(mem.graphiti_status) || "-";
}

function assetRegistryId(asset: AssetRecord): string {
  return metaStr(asset, "asset_registry_id");
}

function assetGraphitiStatus(asset: AssetRecord): { status: string; episodeId: string } {
  const provenance = asRecord(asset.metadata.provenance);
  const graphiti = asRecord(provenance?.graphiti_status);
  return {
    status: typeof graphiti?.status === "string" ? graphiti.status : "",
    episodeId: typeof graphiti?.episode_id === "string" ? graphiti.episode_id : "",
  };
}

function assetRelationships(asset: AssetRecord): Record<string, unknown>[] {
  const relationships = asset.metadata.relationships;
  if (!Array.isArray(relationships)) return [];
  return relationships.map(asRecord).filter((item): item is Record<string, unknown> => Boolean(item));
}

function assetGraphitiRelationshipStatus(asset: AssetRecord): { status: string; projected: number; total: number; relationshipIds: string[] } {
  const relationships = assetRelationships(asset);
  const provenance = asRecord(asset.metadata.provenance);
  const projected = Array.isArray(provenance?.graphiti_relationships)
    ? provenance.graphiti_relationships.map(asRecord).filter((item): item is Record<string, unknown> => Boolean(item))
    : [];
  const projectedIds = projected
    .map((item) => provenanceText(item, ["relationship_id", "asset_id"]))
    .filter(Boolean);
  const ingestedCount = projected.filter((item) => provenanceText(item, ["status"]) === "ingested").length;
  const status = relationships.length === 0
    ? "no relationships"
    : projected.length >= relationships.length
      ? "projected"
      : projected.length > 0
        ? "partial"
        : "not projected";
  return { status, projected: projected.length || ingestedCount, total: relationships.length, relationshipIds: projectedIds };
}

function employeeImprovementTarget(asset: AssetRecord): string {
  if (asset.kind !== "employee_improvement") return "";
  if (asset.source_employee) return asset.source_employee;
  const employeeScope = asset.scopes.find((scope) => scope.startsWith("employee:"));
  return employeeScope ? employeeScope.replace(/^employee:/, "") : "";
}

function employeeImprovementApplicationStatus(asset: AssetRecord): string {
  const provenance = asRecord(asset.metadata.provenance);
  const application = asRecord(provenance?.employee_improvement_application);
  return typeof application?.status === "string" ? application.status : "";
}

function ProvenanceRow({ children, label, title }: { children: ReactNode; label: string; title?: string }) {
  return (
    <div className="grid gap-1 text-xs sm:grid-cols-[7rem_minmax(0,1fr)]">
      <div className="font-medium uppercase text-muted-foreground">{label}</div>
      <div className="min-w-0 truncate font-medium text-foreground" title={title}>
        {children}
      </div>
    </div>
  );
}

function memoryUsageSummary(mem: MemoryCandidate): Record<string, unknown> | null {
  return asRecord(mem.provenance.usage_summary);
}

function memoryUsageHistory(mem: MemoryCandidate): Record<string, unknown>[] {
  const history = mem.provenance.usage_history;
  if (!Array.isArray(history)) return [];
  return history.map(asRecord).filter((item): item is Record<string, unknown> => Boolean(item));
}

function latestMemoryUsage(mem: MemoryCandidate): Record<string, unknown> | null {
  const history = memoryUsageHistory(mem);
  return history[history.length - 1] ?? null;
}

function memoryRelatedTicketIds(mem: MemoryCandidate): string[] {
  const ids = new Set<string>();
  const sourceTicketId = typeof mem.provenance.source_ticket_id === "string" ? mem.provenance.source_ticket_id.trim() : "";
  if (sourceTicketId) ids.add(sourceTicketId);
  if (mem.scope_kind === "ticket" && mem.scope_ref.trim()) ids.add(mem.scope_ref.trim());
  const usageSummary = memoryUsageSummary(mem);
  const latestTicketId = typeof usageSummary?.last_recalled_ticket_id === "string" ? usageSummary.last_recalled_ticket_id.trim() : "";
  if (latestTicketId) ids.add(latestTicketId);
  for (const usage of memoryUsageHistory(mem)) {
    for (const ticketId of asStringArray(usage.source_ticket_ids)) ids.add(ticketId);
  }
  return Array.from(ids);
}

function capabilitySourceForTab(tab: CapabilityTab | null): string | null {
  if (tab === "kernel-commands") return "kernel_command";
  if (tab === "mcp-tools") return "mcp_server";
  return null;
}

function decisionText(decision: DecisionRecord): string {
  return [
    `# ${decision.title}`,
    "",
    `Status: ${decision.status}`,
    `ID: ${decision.id}`,
    decision.saved_path ? `File: ${decision.saved_path}` : "",
    "",
    "## Context",
    decision.context || "-",
    "",
    "## Decision",
    decision.decision || "-",
    "",
    "## Consequences",
    decision.consequences || "-",
    "",
    "## Links",
    `Tickets: ${decision.linked_tickets.join(", ") || "-"}`,
    `Memories: ${decision.linked_memories.join(", ") || "-"}`,
  ].filter((line) => line !== "").join("\n");
}

function reviewText(item: ReviewQueueItem): string {
  const metadata = metadataBlock(item.metadata);
  return [
    `# ${item.title}`,
    "",
    `Kind: ${item.kind}`,
    `Status: ${item.status}`,
    `Source: ${item.source_ref || "-"}`,
    `Created: ${item.created_at || "-"}`,
    `Updated: ${item.updated_at || "-"}`,
    "",
    "## Content",
    item.content || "-",
    ...(metadata ? ["", "## Metadata", metadata] : []),
  ].join("\n");
}

function runtimeApprovalText(item: RuntimeApprovalRecord): string {
  const runHistory = runtimeApprovalRunHistory(item);
  return [
    `# ${runtimeApprovalTitle(item)}`,
    "",
    `Status: ${item.status}`,
    `Executor: ${item.executor_id}`,
    `Ticket: ${item.ticket_id || "-"}`,
    `Employee: ${item.employee_id || "-"}`,
    `Required capability: ${item.required_capability || "-"}`,
    `Created: ${item.created_at || "-"}`,
    `Updated: ${item.updated_at || "-"}`,
    item.reviewed_at ? `Reviewed: ${item.reviewed_at} by ${item.reviewer_employee_id || "-"}` : "",
    item.last_run_request_id ? `Last run: ${item.last_run_request_id} (${item.last_run_status || "-"})` : "",
    item.last_ingestion_blocker ? `Ingestion blocker: ${item.last_ingestion_blocker}` : "",
    "",
    "## Reason",
    item.reason || "-",
    "",
    "## Approval Request",
    prettyJson(item.approval_request) || "-",
    "",
    "## Run History",
    ...(runHistory.length > 0
      ? runHistory.flatMap((entry, index) => [
          `### Attempt ${index + 1}`,
          `Run request: ${String(entry.run_request_id ?? "-")}`,
          `Status: ${String(entry.status ?? "-")}`,
          `Ingested: ${String(entry.ingested ?? "-")}`,
          `Executor session: ${String(entry.executor_session_ref ?? "-")}`,
          `Checkpoint: ${String(entry.checkpoint_ref ?? "-")}`,
          `Trace: ${String(entry.trace_ref ?? "-")}`,
          `Approval refs: ${asStringArray(entry.approval_refs).join(", ") || "-"}`,
          `Approved capabilities: ${asStringArray(entry.approved_capabilities).join(", ") || "-"}`,
          `Artifacts: ${String(entry.artifact_count ?? 0)}`,
          `Evidence: ${String(entry.evidence_count ?? 0)}`,
          `Errors: ${String(entry.error_count ?? 0)}`,
          entry.ingestion_blocker ? `Ingestion blocker: ${String(entry.ingestion_blocker)}` : "",
          "",
        ])
      : ["-"]),
    "",
    "## Source Request",
    prettyJson(item.source_request) || "-",
    "",
    "## Last Result",
    prettyJson(item.last_result) || "-",
  ].filter((line) => line !== "").join("\n");
}

function assetFullText(asset: AssetRecord): string {
  const report = asset.metadata.report;
  const reportContent = report && typeof report === "object" && "content" in report
    ? prettyJson((report as { content?: unknown }).content)
    : "";
  const content = metaStr(asset, "content") || reportContent || metaStr(asset, "description") || metaStr(asset, "evidence");
  const metadata = metadataBlock(asset.metadata);
  return [
    `# ${asset.title}`,
    "",
    `Kind: ${asset.kind}`,
    `Status: ${asset.status}`,
    asset.source_ticket ? `Source ticket: ${asset.source_ticket}` : "",
    asset.source_employee ? `Source employee: ${asset.source_employee}` : "",
    "",
    "## Content",
    content || "-",
    ...(metadata ? ["", "## Metadata", metadata] : []),
  ].filter((line) => line !== "").join("\n");
}

/* ── AssetRow (generic fallback) ───────────────────────────────────────────── */

function AssetRow({ active, asset, onSelect }: { active: boolean; asset: AssetRecord; onSelect: () => void }) {
  return (
    <button type="button" onClick={onSelect} className={cn(
      "grid w-full gap-2 border-b px-4 py-3 text-left text-sm transition-colors last:border-b-0",
      active ? "bg-primary/10" : "hover:bg-muted/60",
    )}>
      <div className="flex min-w-0 items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="line-clamp-2 font-medium leading-5">{asset.title}</div>
          <div className="mt-1 flex min-w-0 flex-wrap gap-1.5 text-xs text-muted-foreground">
            <span>{asset.kind}</span>
            {assetDomain(asset) && <span>{assetDomain(asset)}</span>}
          </div>
        </div>
        <Badge variant={statusVar(asset.status)}>{asset.status}</Badge>
      </div>
      <div className="flex min-w-0 flex-wrap gap-1.5">
        {asset.source_ticket && <Badge variant="secondary" className="px-1.5 text-[10px]">{asset.source_ticket}</Badge>}
        {asset.source_employee && <Badge variant="outline" className="px-1.5 text-[10px]">{asset.source_employee}</Badge>}
      </div>
      <div className="line-clamp-1 text-xs text-muted-foreground">
        {asset.scopes.length ? asset.scopes.join(" / ") : "No scope"} · {fmtTime(asset.updated_at || asset.created_at)}
      </div>
    </button>
  );
}

/* ── Overview ──────────────────────────────────────────────────────────────── */

/** Determine which asset area a record belongs to */
function assetArea(a: AssetRecord): AssetArea {
  const dom = assetDomain(a).toLowerCase();
  if (dom.includes("capab") || dom.includes("skill") || dom.includes("tool")) return "capabilities";
  if (a.status === "proposed" || a.status === "candidate" || dom.includes("review")) return "review";
  return "knowledge";
}

function runtimeApprovalDrawerId(item: RuntimeApprovalRecord): string {
  return `runtime-approval:${item.executor_id}:${item.id}`;
}

function runtimeApprovalTitle(item: RuntimeApprovalRecord): string {
  const action = typeof item.source_request?.action_plan === "object" && item.source_request.action_plan !== null
    ? String((item.source_request.action_plan as Record<string, unknown>).action || "runtime action")
    : "runtime action";
  const ticket = item.ticket_id ? ` for ${item.ticket_id}` : "";
  return `${item.executor_id} ${item.required_capability || "approval"}${ticket} · ${action}`;
}

function runtimeApprovalLastResultDetail(item: RuntimeApprovalRecord): string {
  if (item.last_ingestion_blocker) return item.last_ingestion_blocker;
  const result = asRecord(item.last_result);
  if (!result) return "";
  const status = typeof result.status === "string" ? result.status : "";
  const report = typeof result.report === "string" ? result.report : "";
  const errors = Array.isArray(result.errors) ? result.errors.map(prettyJson).filter(Boolean).join("; ") : "";
  return [status, report || errors].filter(Boolean).join(" · ");
}

function runtimeApprovalRunHistory(item: RuntimeApprovalRecord): Record<string, unknown>[] {
  return Array.isArray(item.run_history)
    ? item.run_history.map(asRecord).filter((entry): entry is Record<string, unknown> => Boolean(entry))
    : [];
}

function assetCandidateDrawerId(item: AssetCandidateRecord): string {
  return `asset-candidate:${item.id}`;
}

function assetCandidateDrawerIdForTarget(target: string, candidates: AssetCandidateRecord[]): string {
  if (target.startsWith("asset-candidate:")) return target;
  const raw = stripRoutePrefix(target, "candidate");
  const match = candidates.find((item) => item.id === raw || item.asset_id === raw || assetCandidateDrawerId(item) === target);
  return match ? assetCandidateDrawerId(match) : "";
}

function runtimeApprovalDrawerIdForTarget(target: string, approvals: RuntimeApprovalRecord[]): string {
  if (target.startsWith("runtime-approval:")) return target;
  const raw = stripRoutePrefix(target, "approval");
  const match = approvals.find((item) => item.id === raw || runtimeApprovalDrawerId(item) === target);
  return match ? runtimeApprovalDrawerId(match) : "";
}

function resolveRouteDrawerId({
  allAssets,
  area,
  assetCandidates,
  decisions,
  docs,
  memories,
  reviewItems,
  runtimeApprovals,
  selectedArea,
  skills,
  target,
}: {
  allAssets: AssetRecord[];
  area: AssetArea | null;
  assetCandidates: AssetCandidateRecord[];
  decisions: DecisionRecord[];
  docs: KnowledgeDocSummary[];
  memories: MemoryCandidate[];
  reviewItems: ReviewQueueItem[];
  runtimeApprovals: RuntimeApprovalRecord[];
  selectedArea?: string | null;
  skills: ChatSkillSummary[];
  target: string;
}): string {
  const normalized = target.trim();
  if (!normalized) return "";
  if (selectedArea?.trim() === "asset") {
    const assetId = routeTargetId(normalized);
    return allAssets.some((item) => item.id === assetId) ? assetId : "";
  }
  if (area === "knowledge") {
    const id = routeTargetId(normalized);
    if (normalized.startsWith("doc:")) return docs.some((item) => item.id === id) ? id : "";
    if (normalized.startsWith("decision:")) return decisions.some((item) => item.id === id) ? id : "";
    if (normalized.startsWith("memory:")) return memories.some((item) => item.id === id) ? id : "";
    if (memories.some((item) => item.id === id)) return id;
    if (docs.some((item) => item.id === id)) return id;
    if (decisions.some((item) => item.id === id)) return id;
    return "";
  }
  if (area === "review") {
    const candidateId = assetCandidateDrawerIdForTarget(normalized, assetCandidates);
    if (candidateId) return candidateId;
    const approvalId = runtimeApprovalDrawerIdForTarget(normalized, runtimeApprovals);
    if (approvalId) return approvalId;
    const raw = routeTargetId(normalized);
    return reviewItems.some((item) => item.id === raw) ? raw : "";
  }
  if (area === "capabilities") {
    const id = routeTargetId(normalized);
    return skills.some((item) => item.id === id) ? id : "";
  }
  const assetId = routeTargetId(normalized);
  return allAssets.some((item) => item.id === assetId) ? assetId : "";
}

function assetCandidateTitle(item: AssetCandidateRecord): string {
  return `${item.asset_type.replace(/_/g, " ")} · ${item.title || item.id}`;
}

function assetCandidateText(item: AssetCandidateRecord): string {
  return [
    `# ${assetCandidateTitle(item)}`,
    "",
    `Status: ${item.status}`,
    `Review state: ${item.review_state}`,
    `Scope: ${item.scope_kind}:${item.scope_ref}`,
    `Owner: ${item.owner_employee_id || "-"}`,
    `Source: ${item.source_kind}:${item.source_ref || "-"}`,
    `Candidate: ${item.id}`,
    `Asset ID: ${item.asset_id || "-"}`,
    "",
    "## Content",
    item.content || "-",
    "",
    "## Provenance",
    prettyJson(item.provenance) || "-",
    "",
    "## Relationships",
    prettyJson(item.relationships) || "-",
  ].join("\n");
}

function assetCandidateProvenanceValue(item: AssetCandidateRecord, key: string): string {
  const value = item.provenance[key];
  if (value === undefined || value === null || value === "") return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return prettyJson(value);
}

function ToolCallCandidateDetails({ item }: { item: AssetCandidateRecord }) {
  if (item.asset_type !== "tool_call") return null;
  return (
    <div className="rounded-md border bg-muted/30 p-3">
      <div className="mb-2 text-xs font-medium uppercase text-muted-foreground">Tool Call</div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Status label="Command" value={assetCandidateProvenanceValue(item, "command_id") || item.title} />
        <Status label="Event" value={assetCandidateProvenanceValue(item, "tool_event_name") || "-"} />
        <Status label="Run" value={assetCandidateProvenanceValue(item, "source_run_id") || "-"} />
        <Status label="Trace" value={assetCandidateProvenanceValue(item, "source_trace_path") || item.source_ref || "-"} />
        <Status label="Index" value={assetCandidateProvenanceValue(item, "tool_event_index") || "0"} />
        <Status label="Executor" value={assetCandidateProvenanceValue(item, "executor_id") || "-"} />
      </div>
    </div>
  );
}

function AssetRecallQualityEvidenceSection({ artifacts }: { artifacts: PlanV8ArtifactSummary | null }) {
  const contextEval = artifacts?.latest_context_retrieval_eval ?? null;
  const provenanceEval = artifacts?.latest_asset_provenance_eval ?? null;
  const contextSummary = asRecord(contextEval?.summary) ?? {};
  const provenanceSummary = asRecord(provenanceEval?.summary) ?? {};
  const evidenceGaps = artifacts?.evidence_gaps ?? [];
  const activeAssetIds = summaryList(contextSummary.active_asset_ids);
  const recalledMemoryIds = summaryList(contextSummary.recalled_memory_ids);
  const staleHintAssetIds = summaryList(contextSummary.stale_hint_asset_ids);
  const excludedAssetIds = summaryList(contextSummary.excluded_asset_ids);
  const wrongTicketFiltered = contextSummary.wrong_ticket_filtered === true;
  const staleActiveFiltered = provenanceSummary.stale_active_filtered === true;

  return (
    <section className="rounded-md border bg-background p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Brain className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Recall Quality Evidence</h3>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant={statusVar(artifacts?.status ?? "")}>{artifacts?.status || "missing"}</Badge>
          <Badge variant={(artifacts?.context_retrieval_eval_count ?? 0) ? "success" : "warning"}>
            {artifacts?.context_retrieval_eval_count ?? 0} retrieval
          </Badge>
          <Badge variant={(artifacts?.asset_provenance_eval_count ?? 0) ? "success" : "warning"}>
            {artifacts?.asset_provenance_eval_count ?? 0} provenance
          </Badge>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="rounded-md border bg-muted/20 p-3">
          <div className="flex items-center justify-between gap-2">
            <h4 className="text-sm font-semibold">Scoped Retrieval</h4>
            <Badge variant={statusVar(contextEval?.status ?? "")}>{contextEval?.status || "missing"}</Badge>
          </div>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <Status label="Active recall" value={String(numberValue(contextSummary.graphiti_result_count))} />
            <Status label="Memory recall" value={String(recalledMemoryIds.length)} />
            <Status label="Excluded hints" value={String(numberValue(contextSummary.graphiti_excluded_result_count))} />
            <Status label="Work recall" value={`${Math.round(numberValue(contextSummary.work_history_eval_recall) * 100)}%`} />
            <Status label="Wrong ticket" value={wrongTicketFiltered ? "filtered" : "not proven"} />
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {activeAssetIds.slice(0, 3).map((id) => <Badge key={`active-${id}`} variant="success" className="text-[10px]">{id}</Badge>)}
            {recalledMemoryIds.slice(0, 3).map((id) => <Badge key={`memory-${id}`} variant="secondary" className="text-[10px]">{id}</Badge>)}
            {staleHintAssetIds.slice(0, 3).map((id) => <Badge key={`stale-${id}`} variant="warning" className="text-[10px]">{id}</Badge>)}
            {excludedAssetIds.slice(0, 3).map((id) => <Badge key={`excluded-${id}`} variant="outline" className="text-[10px]">{id}</Badge>)}
          </div>
          {contextEval?.name ? <div className="mt-3 truncate text-xs text-muted-foreground" title={contextEval.name}>{contextEval.name}</div> : null}
        </div>

        <div className="rounded-md border bg-muted/20 p-3">
          <div className="flex items-center justify-between gap-2">
            <h4 className="text-sm font-semibold">Provenance Exclusion</h4>
            <Badge variant={statusVar(provenanceEval?.status ?? "")}>{provenanceEval?.status || "missing"}</Badge>
          </div>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <Status label="Relationship" value={String(provenanceSummary.relationship_projection_status || "-")} />
            <Status label="Projected" value={String(numberValue(provenanceSummary.relationship_ingested_count))} />
            <Status label="Recall hits" value={String(numberValue(provenanceSummary.relationship_search_result_count))} />
            <Status label="Stale cleanup" value={staleActiveFiltered ? "filtered" : "not proven"} />
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {String(provenanceSummary.source_asset_id || "") && (
              <Badge variant="success" className="text-[10px]">{String(provenanceSummary.source_asset_id)}</Badge>
            )}
            {String(provenanceSummary.target_asset_id || "") && (
              <Badge variant="outline" className="text-[10px]">{String(provenanceSummary.target_asset_id)}</Badge>
            )}
            {String(provenanceSummary.stale_memory_id || "") && (
              <Badge variant="warning" className="text-[10px]">{String(provenanceSummary.stale_memory_id)}</Badge>
            )}
          </div>
          {provenanceEval?.name ? <div className="mt-3 truncate text-xs text-muted-foreground" title={provenanceEval.name}>{provenanceEval.name}</div> : null}
        </div>
      </div>

      {evidenceGaps.length > 0 ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {evidenceGaps.slice(0, 4).map((gap) => <Badge key={gap} variant="warning" className="text-[10px]">{gap}</Badge>)}
          <Button type="button" size="sm" variant="outline" onClick={() => navigateTo("system-status")}>
            <Link2 className="h-3.5 w-3.5" />
            System Status
          </Button>
        </div>
      ) : null}
    </section>
  );
}

function AssetOverview({
  allAssets, assetCandidates, knowledgeStatus, reviewItems, runtimeApprovals, skills, capRegistry, planV8Artifacts,
}: {
  allAssets: AssetRecord[]; assetCandidates: AssetCandidateRecord[]; knowledgeStatus: KnowledgeStatusResponse | null;
  reviewItems: ReviewQueueItem[]; runtimeApprovals: RuntimeApprovalRecord[]; skills: ChatSkillSummary[];
  capRegistry: CapabilityRegistryResponse | null; planV8Artifacts: PlanV8ArtifactSummary | null;
}) {
  const docs = knowledgeStatus?.docs_count ?? 0;
  const memories = knowledgeStatus?.memories_count ?? 0;
  const decisions = knowledgeStatus?.decisions_count ?? 0;

  const caps = capRegistry?.capabilities ?? [];
  const kernelCommandCount = caps.filter((c) => c.kind === "tool" && c.source_kind === "kernel_command").length;
  const mcpToolCount = caps.filter((c) => c.kind === "tool" && c.source_kind === "mcp_server").length;
  const toolCount = kernelCommandCount + mcpToolCount;

  // Review sub-counts by kind
  const revMemories = reviewItems.filter((i) => i.kind === "memory").length;
  const revDecisions = reviewItems.filter((i) => i.kind === "decision").length;
  const revSkills = reviewItems.filter((i) => i.kind === "skill").length;
  const revAssetCandidates = assetCandidates.length;
  const revTools = reviewItems.filter((i) => i.kind === "tool" || i.kind === "capability").length + runtimeApprovals.length;
  const pendingReviewItems = [
    ...reviewItems.map((item) => ({ id: item.id, title: item.title, kind: item.kind, content: item.content, target: REVIEW_TAB_KEYS.has(item.kind) ? item.kind : undefined })),
    ...assetCandidates.map((item) => ({
      id: assetCandidateDrawerId(item),
      title: assetCandidateTitle(item),
      kind: "asset",
      content: item.content,
      target: item.asset_type === "skill" ? "skills" : item.asset_type === "decision" ? "decisions" : item.asset_type === "memory" ? "memories" : undefined,
    })),
    ...runtimeApprovals.map((item) => ({
      id: runtimeApprovalDrawerId(item),
      title: runtimeApprovalTitle(item),
      kind: "runtime",
      content: item.reason || runtimeApprovalLastResultDetail(item) || item.required_capability,
      target: "tools",
    })),
  ];

  const recentAssets = useMemo(() =>
    [...allAssets].sort((a, b) => {
      const da = new Date(a.updated_at || a.created_at).getTime();
      const db = new Date(b.updated_at || b.created_at).getTime();
      return db - da;
    }).slice(0, 8), [allAssets]);

  /** Distribution with hierarchical sub-category breakdown for all areas */
  const distribution = [
    {
      area: "knowledge" as AssetArea, total: docs + memories + decisions,
      subs: [
        { label: "Docs", count: docs, detail: "docs" },
        { label: "Memories", count: memories, detail: "memories" },
        { label: "Decisions", count: decisions, detail: "decisions" },
      ],
    },
    {
      area: "capabilities" as AssetArea, total: skills.length + toolCount,
      subs: [
        { label: "Skills", count: skills.length, detail: "skills" },
        { label: "Kernel Commands", count: kernelCommandCount, detail: "kernel-commands" },
        { label: "MCP Tools", count: mcpToolCount, detail: "mcp-tools" },
      ],
    },
    {
      area: "review" as AssetArea, total: reviewItems.length + runtimeApprovals.length + assetCandidates.length,
      subs: [
        { label: "Memories", count: revMemories, detail: "memories" },
        { label: "Decisions", count: revDecisions, detail: "decisions" },
        { label: "Skills", count: revSkills, detail: "skills" },
        { label: "Tools", count: revTools, detail: "tools" },
        { label: "Assets", count: revAssetCandidates, detail: "assets" },
      ],
    },
  ];

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
      {/* Recent Changes — narrower column, each row clickable */}
      <section className="rounded-md border bg-background">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <h3 className="text-sm font-semibold">Recent Changes</h3>
          <Badge variant="secondary">{recentAssets.length}</Badge>
        </div>
        {recentAssets.length === 0 ? (
          <EmptyState title="No assets recorded yet" description="Assets are created automatically from knowledge docs, skills, capabilities, and review items." action={<Button variant="outline" size="sm" onClick={() => navigateTo("assets", "knowledge")}>Browse Knowledge</Button>} />
        ) : recentAssets.map((a) => (
          <button key={`${a.kind}-${a.id}`} type="button"
            onClick={() => navigateTo("assets", assetArea(a))}
            className="flex w-full items-center justify-between gap-3 border-b px-4 py-2.5 text-left text-sm last:border-b-0 transition-colors hover:bg-muted/60">
            <div className="min-w-0">
              <div className="truncate font-medium">{a.title}</div>
              <div className="mt-0.5 flex gap-2 text-xs text-muted-foreground">
                <span>{a.kind}</span><span>{assetDomain(a) || assetType(a)}</span>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Badge variant={statusVar(a.status)} className="text-[10px]">{a.status}</Badge>
              <span className="text-xs text-muted-foreground">{fmtTime(a.updated_at || a.created_at)}</span>
            </div>
          </button>
        ))}
      </section>

      {/* Right column — Distribution + Pending Review */}
      <div className="space-y-4">
        {/* Asset Distribution with hierarchical sub-category counts */}
        <section className="rounded-md border bg-background p-4">
          <h3 className="mb-3 text-sm font-semibold">Asset Distribution</h3>
          <div className="space-y-2">
            {distribution.map((cat) => {
              const label = AREA_TABS.find((t) => t.key === cat.area)?.label ?? cat.area;
              return (
                <div key={cat.area} className="rounded-md border bg-muted/20">
                  <button type="button" onClick={() => navigateTo("assets", cat.area)}
                    className="flex w-full items-center justify-between px-3 py-2 text-sm font-medium transition-colors hover:bg-muted">
                    <span>{label}</span>
                    <Badge variant="outline">{cat.total}</Badge>
                  </button>
                  {cat.subs.length > 0 && (
                    <div className="flex flex-wrap gap-1 border-t px-3 py-1.5">
                      {cat.subs.map((s) => (
                        <button key={s.detail} type="button"
                          onClick={() => navigateTo("assets", cat.area, s.detail)}
                          className="rounded px-2 py-0.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
                          {s.label} <span className="font-medium text-foreground">{s.count}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>

        {/* Pending Review — each item clickable */}
        {pendingReviewItems.length > 0 && (
          <section className="rounded-md border bg-background p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold">Pending Review</h3>
              <Button variant="outline" size="sm" onClick={() => navigateTo("assets", "review")}>View all</Button>
            </div>
            <div className="space-y-2">
              {pendingReviewItems.slice(0, 3).map((item) => (
                <button key={item.id} type="button"
                  onClick={() => navigateTo("assets", "review", item.target)}
                  className="w-full rounded-md border bg-muted/20 px-3 py-2 text-left text-sm transition-colors hover:bg-muted">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-medium">{item.title}</span>
                    <Badge variant="warning" className="shrink-0 text-[10px]">{item.kind}</Badge>
                  </div>
                  <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{item.content}</div>
                </button>
              ))}
            </div>
          </section>
        )}
      </div>

      <div className="xl:col-span-2">
        <AssetRecallQualityEvidenceSection artifacts={planV8Artifacts} />
      </div>
    </div>
  );
}

/* ── Knowledge Deep View ───────────────────────────────────────────────────── */

function KnowledgeDocsList({ docs, selectedId, onSelect }: { docs: KnowledgeDocSummary[]; selectedId: string; onSelect: (id: string) => void }) {
  if (docs.length === 0) return <EmptyState title="No docs found" description="Add Markdown files to .aiteamos/knowledge/docs or configure a docs source through Settings." action={<Button variant="outline" size="sm" onClick={() => navigateTo("settings", "ticket-backend")}>Ticket Backend</Button>} />;
  return <div>{docs.map((doc) => (
    <button key={doc.id} type="button" onClick={() => onSelect(doc.id)} className={cn(
      "grid w-full gap-1.5 border-b px-4 py-3 text-left text-sm transition-colors last:border-b-0",
      selectedId === doc.id ? "bg-primary/10" : "hover:bg-muted/60",
    )}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0"><div className="line-clamp-2 font-medium leading-5">{doc.title}</div>
          <div className="mt-0.5 truncate text-xs text-muted-foreground">{doc.path}</div></div>
        <Badge variant={doc.source === "plane" ? "secondary" : "outline"}>{doc.source}</Badge>
      </div>
      <div className="line-clamp-2 text-xs leading-5 text-muted-foreground">{doc.excerpt}</div>
      <div className="flex gap-2 text-[10px] text-muted-foreground">
        {doc.tags.slice(0, 3).map((t) => <Badge key={t} variant="outline" className="text-[10px]">{t}</Badge>)}
        <span>{fmtTime(doc.updated_at)}</span>
      </div>
    </button>
  ))}</div>;
}

function KnowledgeMemoriesList({ memories, selectedId, onSelect, onApprove, approving }: {
  memories: MemoryCandidate[]; selectedId: string; onSelect: (id: string) => void;
  onApprove: (id: string) => void; approving: boolean;
}) {
  if (memories.length === 0) return <EmptyState title="No approved memories yet" description="Memories are accumulated from team interactions and approved candidates. They will appear here once approved." />;
  return <div>{memories.map((m) => (
    <div key={m.id} className={cn(
      "grid w-full gap-1.5 border-b px-4 py-3 text-left text-sm transition-colors last:border-b-0",
      selectedId === m.id ? "bg-primary/10" : "hover:bg-muted/60",
    )}>
      <button type="button" onClick={() => onSelect(m.id)} className="min-w-0 text-left">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0"><div className="line-clamp-2 font-medium leading-5">{m.scope_kind}:{m.scope_ref}</div>
            <div className="mt-0.5 truncate text-xs text-muted-foreground">{m.source_kind}:{m.source_ref || "-"}</div></div>
          <Badge variant={statusVar(m.status)}>{m.status}</Badge>
        </div>
        <div className="line-clamp-2 text-xs leading-5 text-muted-foreground">{m.content}</div>
      </button>
      <div className="flex items-center gap-2">
        {m.tags.slice(0, 4).map((t) => <Badge key={t} variant="outline" className="text-[10px]">{t}</Badge>)}
        <span className="text-[10px] text-muted-foreground">{fmtTime(m.updated_at)}</span>
        {m.status === "proposed" && (
          <Button size="sm" variant="outline" className="ml-auto h-6 px-2 text-[10px]" disabled={approving} onClick={() => onApprove(m.id)}>
            <Check className="h-3 w-3" />Approve
          </Button>
        )}
      </div>
    </div>
  ))}</div>;
}

function KnowledgeDecisionsList({ decisions, selectedId, onSelect }: { decisions: DecisionRecord[]; selectedId: string; onSelect: (id: string) => void }) {
  if (decisions.length === 0) return <EmptyState title="No decisions recorded" description="Decisions capture architectural and technical choices. Ask the team to create an ADR in Chat." action={<Button variant="outline" size="sm" onClick={() => navigateTo("chat")}>Create in Chat</Button>} />;
  return <div>{decisions.map((d) => (
    <button key={d.id} type="button" onClick={() => onSelect(d.id)} className={cn(
      "grid w-full gap-1.5 border-b px-4 py-3 text-left text-sm transition-colors last:border-b-0",
      selectedId === d.id ? "bg-primary/10" : "hover:bg-muted/60",
    )}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0"><div className="line-clamp-2 font-medium leading-5">{d.title}</div>
          <div className="mt-0.5 truncate text-xs text-muted-foreground">{d.saved_path}</div></div>
        <Badge variant={statusVar(d.status)}>{d.status}</Badge>
      </div>
      <div className="line-clamp-2 text-xs leading-5 text-muted-foreground">{d.decision}</div>
      {d.consequences && <div className="line-clamp-1 text-xs text-muted-foreground">Consequences: {d.consequences}</div>}
    </button>
  ))}</div>;
}

/* ── Skills Deep View ──────────────────────────────────────────────────────── */

function SkillsTableView({ skills, selectedId, onSelect }: { skills: ChatSkillSummary[]; selectedId: string; onSelect: (id: string) => void }) {
  if (skills.length === 0) return (
    <div className="px-4 py-8 text-center text-sm text-muted-foreground">
      No skills configured. <button type="button" className="font-medium text-primary hover:underline" onClick={() => navigateTo("chat")}>Ask Clara to create a Skill</button>.
    </div>
  );
  return (
    <Table>
      <TableHeader><TableRow><TableHead>Name</TableHead><TableHead>Description</TableHead><TableHead className="text-right">Uses</TableHead><TableHead className="text-right">Employees</TableHead><TableHead className="text-right">Files</TableHead></TableRow></TableHeader>
      <TableBody>{skills.map((skill) => (
        <TableRow key={skill.id} className={cn("cursor-pointer", selectedId === skill.id && "bg-muted/60")} onClick={() => onSelect(skill.id)}>
          <TableCell><div className="flex items-center gap-2"><BookOpen className="h-4 w-4 text-muted-foreground" /><div><div className="font-medium">{skill.title}</div><div className="text-xs text-muted-foreground">{skill.id}</div></div></div></TableCell>
          <TableCell className="max-w-[32rem] truncate text-muted-foreground">{skill.description || "No description configured."}</TableCell>
          <TableCell className="text-right">{skill.usage_count ?? 0}</TableCell>
          <TableCell className="text-right">{skill.assigned_employees.length}</TableCell>
          <TableCell className="text-right">{skill.resources.length + 1}</TableCell>
        </TableRow>
      ))}</TableBody>
    </Table>
  );
}

/* ── Capabilities Deep View ────────────────────────────────────────────────── */

function capabilityGroupLabel(k: string): string {
  if (k === "kernel_command") return "Kernel Commands";
  if (k === "mcp_server") return "MCP Tools";
  if (k === "native_api") return "Native API Tools";
  if (k === "cli") return "CLI Tools";
  if (k === "ci") return "CI Tools";
  if (k === "ticket_backend") return "Ticket Backend Tools";
  if (k === "ai_engine_bridge") return "AI Engine Tools";
  return k.replace(/_/g, " ");
}

function CapabilitiesGroupedView({
  onSelect,
  registry,
  selectedId,
  tab,
}: {
  onSelect: (id: string) => void;
  registry: CapabilityRegistryResponse;
  selectedId: string;
  tab: CapabilityTab | null;
}) {
  const sourceKind = capabilitySourceForTab(tab);
  const caps = registry.capabilities.filter((c) => c.kind === "tool" && (!sourceKind || c.source_kind === sourceKind));
  const order: string[] = ["kernel_command", "mcp_server", "native_api", "cli", "ci", "ticket_backend", "ai_engine_bridge"];
  const groups = new Map<string, CapabilityRecord[]>();
  for (const c of caps) {
    const key = c.source_kind || "kernel_command";
    groups.set(key, [...(groups.get(key) ?? []), c]);
  }
  const sorted = [
    ...order.filter((k) => groups.has(k)).map((k) => [k, groups.get(k)!] as const),
    ...Array.from(groups.entries()).filter(([k]) => !order.includes(k)),
  ];

  if (tab === "skills") return null;
  const currentLabel = CAPABILITY_TABS.find((item) => item.key === tab)?.label ?? "Tools";
  if (sorted.length === 0) return <EmptyState title={`No ${currentLabel}`} description="Capabilities are discovered from Kernel commands and configured Tool Connectors." action={<Button variant="outline" size="sm" onClick={() => navigateTo("settings", "tool-connectors")}>Tool Connectors</Button>} />;
  return <div className="space-y-4">{sorted.map(([kind, items]) => (
    <section key={kind} className="rounded-md border bg-background">
      <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
        <h3 className="text-sm font-semibold">{capabilityGroupLabel(kind)}</h3><Badge variant="secondary">{items.length}</Badge>
      </div>
      <div className="divide-y">{items.map((c) => (
        <div key={c.id} className={cn(
          "grid gap-3 px-4 py-3 text-sm transition-colors xl:grid-cols-[minmax(0,1fr)_12rem]",
          selectedId === c.id ? "bg-primary/10" : "hover:bg-muted/50",
        )}>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{c.name}</span><Badge variant="outline">{c.domain}</Badge>
              <Badge variant={statusVar(c.status)}>{c.status}</Badge>
              {!c.enabled && <Badge variant="secondary">disabled</Badge>}
            </div>
            <div className="mt-1 text-muted-foreground">{c.description}</div>
            {c.boundary && <div className="mt-2 rounded-md bg-muted px-3 py-2 text-xs leading-5 text-muted-foreground">{c.boundary}</div>}
            <div className="mt-2 flex flex-wrap gap-2">
              {c.permissions.slice(0, 4).map((p) => <Badge key={p} variant="outline">{p}</Badge>)}
              {c.required_settings.slice(0, 3).map((s) => <Badge key={s} variant="secondary">{s}</Badge>)}
            </div>
          </div>
          <aside className="min-w-0 space-y-2 text-xs text-muted-foreground">
            <div><div className="uppercase">Source</div><div className="truncate font-medium text-foreground" title={c.source}>{c.source}</div></div>
            <div><div className="uppercase">Owner scope</div><div className="truncate font-medium text-foreground">{c.owner_scope || "-"}</div></div>
            <div className="flex flex-wrap gap-2">
              <Button type="button" size="sm" variant="outline" onClick={() => onSelect(c.id)}>
                Details
              </Button>
              {c.deep_link && <a className="inline-flex items-center text-sm font-medium text-primary hover:underline" href={c.deep_link}>Open surface</a>}
            </div>
          </aside>
        </div>
      ))}</div>
    </section>
  ))}</div>;
}

/* ── Review Queue View ─────────────────────────────────────────────────────── */

function ReviewQueueList({
  assetCandidates, items, runtimeApprovals, selectedId, onSelect, onApprove, onAssetCandidateReview, onAssetCandidateBatchReview, onRuntimeReview, onRuntimeRun, approving, tab,
}: {
  assetCandidates: AssetCandidateRecord[]; items: ReviewQueueItem[]; runtimeApprovals: RuntimeApprovalRecord[]; selectedId: string; onSelect: (id: string) => void;
  onApprove: (id: string) => void;
  onAssetCandidateReview: (item: AssetCandidateRecord, status: AssetCandidateReviewStatus) => void;
  onAssetCandidateBatchReview: (items: AssetCandidateRecord[], status: "approved" | "rejected") => void;
  onRuntimeReview: (item: RuntimeApprovalRecord, status: "approved" | "rejected") => void;
  onRuntimeRun: (item: RuntimeApprovalRecord) => void;
  approving: boolean; tab: ReviewTab | null;
}) {
  const filtered = tab ? items.filter((i) => {
    if (tab === "memories") return i.kind === "memory";
    if (tab === "decisions") return i.kind === "decision";
    if (tab === "skills") return i.kind === "skill";
    if (tab === "tools") return i.kind === "tool" || i.kind === "capability";
    return true;
  }) : items;
  const filteredAssetCandidates = tab ? assetCandidates.filter((item) => {
    if (tab === "memories") return item.asset_type === "memory";
    if (tab === "decisions") return item.asset_type === "decision";
    if (tab === "skills") return item.asset_type === "skill";
    if (tab === "tools") return !["memory", "decision", "skill"].includes(item.asset_type);
    return true;
  }) : assetCandidates;
  const filteredRuntimeApprovals = tab && tab !== "tools" ? [] : runtimeApprovals;
  const batchableAssetCandidates = filteredAssetCandidates.filter((item) => item.status === "proposed");
  if (filtered.length === 0 && filteredAssetCandidates.length === 0 && filteredRuntimeApprovals.length === 0) return <EmptyState title="No review items" description={tab ? `No pending ${tab} reviews. Items will appear here when candidates are proposed.` : "Review queue is clear. Proposed memories, decisions, skills, tool changes, and runtime approvals will appear here for approval."} />;
  return <div>
  {batchableAssetCandidates.length > 1 && (
    <div className="flex flex-wrap items-center gap-2 border-b bg-muted/30 px-4 py-2">
      <Badge variant="secondary" className="text-[10px]">{batchableAssetCandidates.length} asset candidates</Badge>
      <Button size="sm" variant="outline" className="ml-auto h-7 px-2 text-[11px]" disabled={approving} onClick={() => onAssetCandidateBatchReview(batchableAssetCandidates, "approved")}>
        <Check className="h-3 w-3" />Approve All
      </Button>
      <Button size="sm" variant="outline" className="h-7 px-2 text-[11px]" disabled={approving} onClick={() => onAssetCandidateBatchReview(batchableAssetCandidates, "rejected")}>
        <X className="h-3 w-3" />Reject All
      </Button>
    </div>
  )}
  {filtered.map((item) => (
    <div key={item.id} className={cn(
      "grid w-full gap-1.5 border-b px-4 py-3 text-left text-sm transition-colors last:border-b-0",
      selectedId === item.id ? "bg-primary/10" : "hover:bg-muted/60",
    )}>
      <button type="button" onClick={() => onSelect(item.id)} className="min-w-0 text-left">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0"><div className="line-clamp-2 font-medium leading-5">{item.title}</div>
            <div className="mt-0.5 truncate text-xs text-muted-foreground">{item.kind} · {item.source_ref}</div></div>
          <Badge variant={statusVar(item.status)}>{item.status}</Badge>
        </div>
        <div className="line-clamp-2 text-xs leading-5 text-muted-foreground">{item.content}</div>
      </button>
      <div className="flex items-center gap-2">
        <span className="text-[10px] text-muted-foreground">{fmtTime(item.updated_at)}</span>
        {item.kind === "memory" && item.status === "proposed" && (
          <Button size="sm" variant="outline" className="ml-auto h-6 px-2 text-[10px]" disabled={approving} onClick={() => onApprove(item.id)}>
            <Check className="h-3 w-3" />Approve
          </Button>
        )}
      </div>
    </div>
  ))}
  {filteredAssetCandidates.map((item) => {
    const selected = selectedId === assetCandidateDrawerId(item);
    return (
      <div key={assetCandidateDrawerId(item)} className={cn(
        "grid w-full gap-1.5 border-b px-4 py-3 text-left text-sm transition-colors last:border-b-0",
        selected ? "bg-primary/10" : "hover:bg-muted/60",
      )}>
        <button type="button" onClick={() => onSelect(assetCandidateDrawerId(item))} className="min-w-0 text-left">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="line-clamp-2 font-medium leading-5">{assetCandidateTitle(item)}</div>
              <div className="mt-0.5 truncate text-xs text-muted-foreground">asset candidate · {item.scope_kind}:{item.scope_ref}</div>
            </div>
            <Badge variant={statusVar(item.status)}>{item.status}</Badge>
          </div>
          <div className="line-clamp-2 text-xs leading-5 text-muted-foreground">{item.content}</div>
        </button>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10px] text-muted-foreground">{fmtTime(item.updated_at)}</span>
          <Badge variant="secondary" className="text-[10px]">{item.asset_type}</Badge>
          {item.status === "proposed" && (
            <>
              <Button size="sm" variant="outline" className="ml-auto h-6 px-2 text-[10px]" disabled={approving} onClick={() => onAssetCandidateReview(item, "approved")}>
                <Check className="h-3 w-3" />Approve
              </Button>
              <Button size="sm" variant="outline" className="h-6 px-2 text-[10px]" disabled={approving} onClick={() => onAssetCandidateReview(item, "rejected")}>
                <X className="h-3 w-3" />Reject
              </Button>
            </>
          )}
        </div>
      </div>
    );
  })}
  {filteredRuntimeApprovals.map((item) => {
    const selected = selectedId === runtimeApprovalDrawerId(item);
    const lastResult = runtimeApprovalLastResultDetail(item);
    return (
      <div key={runtimeApprovalDrawerId(item)} className={cn(
        "grid w-full gap-1.5 border-b px-4 py-3 text-left text-sm transition-colors last:border-b-0",
        selected ? "bg-primary/10" : "hover:bg-muted/60",
      )}>
        <button type="button" onClick={() => onSelect(runtimeApprovalDrawerId(item))} className="min-w-0 text-left">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="line-clamp-2 font-medium leading-5">{runtimeApprovalTitle(item)}</div>
              <div className="mt-0.5 truncate text-xs text-muted-foreground">runtime approval · {item.executor_id} · {item.id}</div>
            </div>
            <Badge variant={statusVar(item.status)}>{item.status}</Badge>
          </div>
          <div className="line-clamp-2 text-xs leading-5 text-muted-foreground">{item.reason || lastResult || item.required_capability}</div>
        </button>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10px] text-muted-foreground">{fmtTime(item.updated_at)}</span>
          {item.ticket_id && <Badge variant="outline" className="text-[10px]">{item.ticket_id}</Badge>}
          <Badge variant="secondary" className="text-[10px]">{item.required_capability || "approval"}</Badge>
          {item.status === "requested" && (
            <>
              <Button size="sm" variant="outline" className="ml-auto h-6 px-2 text-[10px]" disabled={approving} onClick={() => onRuntimeReview(item, "approved")}>
                <Check className="h-3 w-3" />Approve
              </Button>
              <Button size="sm" variant="outline" className="h-6 px-2 text-[10px]" disabled={approving} onClick={() => onRuntimeReview(item, "rejected")}>
                <X className="h-3 w-3" />Reject
              </Button>
            </>
          )}
          {item.status === "approved" && (
            <Button size="sm" variant="outline" className="ml-auto h-6 px-2 text-[10px]" disabled={approving} onClick={() => onRuntimeRun(item)}>
              <Check className="h-3 w-3" />Run
            </Button>
          )}
        </div>
        {lastResult && <div className="line-clamp-2 rounded-md bg-muted/40 px-2 py-1 text-xs text-muted-foreground">{lastResult}</div>}
      </div>
    );
  })}</div>;
}

/* ── Main Page ─────────────────────────────────────────────────────────────── */

const DRAWER_W = "34rem";

function ContentSkeleton() {
  return (
    <div className="space-y-3 p-4">
      {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-14 w-full" />)}
    </div>
  );
}

export function AssetsPage({ selectedArea, selectedDetail }: { selectedArea?: string | null; selectedDetail?: string | null }) {
  const area = areaFromRoute(selectedArea);
  const routeTarget = routeTargetFromDetail(area, selectedArea, selectedDetail);
  const [allAssets, setAllAssets] = useState<AssetRecord[]>([]);
  const [knowledgeStatus, setKnowledgeStatus] = useState<KnowledgeStatusResponse | null>(null);
  const [docs, setDocs] = useState<KnowledgeDocSummary[]>([]);
  const [memories, setMemories] = useState<MemoryCandidate[]>([]);
  const [decisions, setDecisions] = useState<DecisionRecord[]>([]);
  const [reviewItems, setReviewItems] = useState<ReviewQueueItem[]>([]);
  const [assetCandidates, setAssetCandidates] = useState<AssetCandidateRecord[]>([]);
  const [runtimeApprovals, setRuntimeApprovals] = useState<RuntimeApprovalRecord[]>([]);
  const [planV8Artifacts, setPlanV8Artifacts] = useState<PlanV8ArtifactSummary | null>(null);
  const [skills, setSkills] = useState<ChatSkillSummary[]>([]);
  const [capRegistry, setCapRegistry] = useState<CapabilityRegistryResponse | null>(null);
  const [drawerId, setDrawerId] = useState("");
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [assetReviewTargetId, setAssetReviewTargetId] = useState("");
  const [assetReviewRelationshipType, setAssetReviewRelationshipType] = useState("derived_from");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [approving, setApproving] = useState(false);
  const [fullText, setFullText] = useState<FullTextPayload | null>(null);

  const searching = Boolean(submittedQuery.trim());

  // Sub-tab for knowledge & capabilities (auto-select first when entering area)
  const kTab: KnowledgeTab | null = area === "knowledge"
    ? (selectedDetail && KNOWLEDGE_TAB_KEYS.has(selectedDetail) ? selectedDetail as KnowledgeTab : routeTarget ? knowledgeTabFromRouteTarget(routeTarget) : "docs")
    : null;
  const cTab: CapabilityTab | null = area === "capabilities"
    ? (selectedDetail && CAPABILITY_TAB_KEYS.has(selectedDetail) ? selectedDetail as CapabilityTab : "skills")
    : null;
  const rTab: ReviewTab | null = area === "review"
    ? (selectedDetail && REVIEW_TAB_KEYS.has(selectedDetail) ? selectedDetail as ReviewTab : null)
    : null;
  const assetListDetail = area === "knowledge" ? kTab : area === "capabilities" ? cTab : area === "review" ? rTab : null;

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const assetQuery = submittedQuery.trim();
      const [a, ac, ks, d, m, dec, rev, sk, cap, system] = await Promise.all([
        listAssets(assetQuery ? null : area, assetQuery ? null : assetListDetail, assetQuery).catch(() => []),
        listAssetCandidates({ status: "proposed" }).catch(() => []),
        getKnowledgeStatus().catch(() => null),
        listKnowledgeDocs().catch(() => []),
        listApprovedMemory().catch(() => []),
        listKnowledgeDecisions().catch(() => []),
        listKnowledgeReviewQueue().catch(() => []),
        listChatSkills().catch(() => []),
        getCapabilities().catch(() => null),
        getSystemStatus().catch(() => null),
      ]);
      const executorIds = Array.from(new Set((system?.runtime_executors ?? []).map((executor) => executor.executor_id).filter(Boolean)));
      const approvalLists = await Promise.all(
        executorIds.map((executorId) => listRuntimeExecutorApprovals(executorId).catch(() => [])),
      );
      const approvals = approvalLists.flat().sort((left, right) => {
        const dl = new Date(left.updated_at || left.created_at).getTime();
        const dr = new Date(right.updated_at || right.created_at).getTime();
        return dr - dl;
      });
      setAllAssets(a); setAssetCandidates(ac); setKnowledgeStatus(ks); setDocs(d); setMemories(m);
      setDecisions(dec); setReviewItems(rev); setRuntimeApprovals(approvals); setSkills(sk); setCapRegistry(cap);
      setPlanV8Artifacts(system?.plan_v8_artifacts ?? null);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to load assets"); }
    finally { setLoading(false); }
  }, [area, assetListDetail, submittedQuery]);

  useEffect(() => { void load(); }, [load]);

  // Close drawer when switching asset scopes, including sibling sub-tabs.
  useEffect(() => {
    setDrawerId("");
    setFullText(null);
  }, [area, selectedDetail, submittedQuery]);

  useEffect(() => {
    if (!routeTarget || loading) return;
    const resolved = resolveRouteDrawerId({
      allAssets,
      area,
      assetCandidates,
      decisions,
      docs,
      memories,
      reviewItems,
      runtimeApprovals,
      selectedArea,
      skills,
      target: routeTarget,
    });
    if (resolved) setDrawerId(resolved);
  }, [
    allAssets,
    area,
    assetCandidates,
    decisions,
    docs,
    loading,
    memories,
    reviewItems,
    routeTarget,
    runtimeApprovals,
    selectedArea,
    skills,
  ]);

  useEffect(() => {
    setAssetReviewTargetId("");
    setAssetReviewRelationshipType("derived_from");
  }, [drawerId]);

  function submitSearch(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setSubmittedQuery(query.trim());
  }

  function handleApprove(id: string) {
    setApproving(true);
    approveMemoryCandidate(id).then(() => load()).catch((err) => setError(err.message)).finally(() => setApproving(false));
  }

  function handleReview(id: string, status: "rejected" | "stale", reason: string) {
    setApproving(true);
    reviewMemoryCandidate(id, { status, reason, actor_employee_id: "clara" })
      .then(() => {
        setDrawerId("");
        return load();
      })
      .catch((err) => setError(err.message))
      .finally(() => setApproving(false));
  }

  function handleUsageReview(id: string, usageId: string, usefulnessStatus: "used" | "irrelevant" | "harmful" | "promoted", reason: string) {
    setApproving(true);
    reviewMemoryRecallUsage(id, usageId, { usefulness_status: usefulnessStatus, reviewer_employee_id: "clara", reason })
      .then(() => load())
      .catch((err) => setError(err.message))
      .finally(() => setApproving(false));
  }

  function handleAssetCandidateReview(
    item: AssetCandidateRecord,
    status: AssetCandidateReviewStatus,
    options: { targetAssetId?: string; relationshipType?: string } = {},
  ) {
    const targetAssetId = (options.targetAssetId ?? "").trim();
    const relationshipType = (options.relationshipType ?? "derived_from").trim() || "derived_from";
    if ((status === "merged" || status === "linked") && !targetAssetId) {
      setError("Target Asset ID is required to merge or link an Asset candidate.");
      return;
    }
    setApproving(true);
    reviewAssetCandidate(item.id, {
      status,
      reviewer_employee_id: "clara",
      reason: `${status === "approved" ? "Approved" : status === "rejected" ? "Rejected" : status === "merged" ? "Merged" : "Linked"} from Assets review queue.`,
      merge_target_asset_id: status === "merged" || status === "linked" ? targetAssetId : "",
      link_relationships: status === "approved" && targetAssetId ? [
        {
          type: relationshipType,
          target_kind: "asset",
          target_ref: targetAssetId,
          reason: `Approved from Assets review queue with ${relationshipType} relationship.`,
        },
      ] : [],
    })
      .then((response) => {
        setAssetCandidates((current) => current.map((candidate) => candidate.id === response.candidate.id ? response.candidate : candidate));
        setDrawerId(assetCandidateDrawerId(response.candidate));
        setAssetReviewTargetId("");
        setAssetReviewRelationshipType("derived_from");
        return load();
      })
      .catch((err) => setError(err.message))
      .finally(() => setApproving(false));
  }

  function handleAssetCandidateBatchReview(
    items: AssetCandidateRecord[],
    status: "approved" | "rejected",
  ) {
    const candidateIds = items.filter((item) => item.status === "proposed").map((item) => item.id);
    if (!candidateIds.length) return;
    setApproving(true);
    reviewAssetCandidatesBatch({
      candidate_ids: candidateIds,
      status,
      reviewer_employee_id: "clara",
      reason: `Batch ${status === "approved" ? "approved" : "rejected"} from Assets review queue.`,
    })
      .then((response) => {
        const reviewed = response.results
          .map((item) => item.response?.candidate)
          .filter((candidate): candidate is AssetCandidateRecord => Boolean(candidate));
        setAssetCandidates((current) => current.map((candidate) => reviewed.find((item) => item.id === candidate.id) ?? candidate));
        if (response.failed_count > 0) {
          setError(`${response.failed_count} Asset candidate batch review item failed.`);
        } else {
          setError(null);
        }
        return load();
      })
      .catch((err) => setError(err.message))
      .finally(() => setApproving(false));
  }

  function handleRuntimeApprovalReview(item: RuntimeApprovalRecord, status: "approved" | "rejected") {
    setApproving(true);
    reviewRuntimeExecutorApproval(item.executor_id, item.id, {
      status,
      reviewer_employee_id: "clara",
      reason: `${status === "approved" ? "Approved" : "Rejected"} from Assets review queue.`,
    })
      .then((updated) => {
        setRuntimeApprovals((current) => current.map((candidate) => candidate.id === updated.id ? updated : candidate));
        setDrawerId(runtimeApprovalDrawerId(updated));
      })
      .catch((err) => setError(err.message))
      .finally(() => setApproving(false));
  }

  function handleRuntimeApprovalRun(item: RuntimeApprovalRecord) {
    setApproving(true);
    runRuntimeExecutorApproval(item.executor_id, item.id, { employee_id: item.employee_id || "clara", ingest_result: true })
      .then((response) => {
        const updated = asRecord(response.approval) as RuntimeApprovalRecord | null;
        if (updated?.id) {
          setRuntimeApprovals((current) => current.map((candidate) => candidate.id === updated.id ? updated : candidate));
          setDrawerId(runtimeApprovalDrawerId(updated));
        }
      })
      .catch((err) => setError(err.message))
      .finally(() => setApproving(false));
  }

  function handleProjectAssetToGraphiti(asset: AssetRecord) {
    const registryId = assetRegistryId(asset);
    if (!registryId) {
      setError("Asset registry ID is required to project an Asset to Graphiti.");
      return;
    }
    setApproving(true);
    projectAssetRecordToGraphiti(registryId)
      .then(() => load())
      .catch((err) => setError(err.message))
      .finally(() => setApproving(false));
  }

  function handleProjectAssetRelationshipsToGraphiti(asset: AssetRecord) {
    const registryId = assetRegistryId(asset);
    if (!registryId) {
      setError("Asset registry ID is required to project Asset relationships to Graphiti.");
      return;
    }
    setApproving(true);
    projectAssetRecordRelationshipsToGraphiti(registryId)
      .then(() => load())
      .catch((err) => setError(err.message))
      .finally(() => setApproving(false));
  }

  function handleApplyEmployeeImprovement(asset: AssetRecord) {
    const registryId = assetRegistryId(asset);
    const employeeId = employeeImprovementTarget(asset);
    if (!registryId || !employeeId) {
      setError("Approved Employee improvement Asset and target Employee are required.");
      return;
    }
    setApproving(true);
    applyEmployeeImprovementAsset(employeeId, registryId, {
      actor_employee_id: "clara",
      reason: "Applied from Assets approved Employee improvement drawer.",
    })
      .then(() => load())
      .catch((err) => setError(err.message))
      .finally(() => setApproving(false));
  }

  // Breadcrumb
  const areaLabel = area ? AREA_TABS.find((t) => t.key === area)?.label ?? area : "Overview";
  const detailLabel = area === "knowledge" ? (kTab ? KNOWLEDGE_TABS.find((t) => t.key === kTab)?.label : null)
    : area === "capabilities" ? (cTab ? CAPABILITY_TABS.find((t) => t.key === cTab)?.label : null)
    : null;
  const breadcrumbSegments: Array<{ label: string; onClick?: () => void }> = searching
    ? [{ label: "Search Results" }]
    : [
        { label: "Assets", onClick: area ? () => navigateTo("assets") : undefined },
        ...(area ? [{ label: areaLabel, onClick: detailLabel ? () => navigateTo("assets", area) : undefined }] : []),
        ...(detailLabel ? [{ label: detailLabel }] : []),
      ];

  // Resolve drawer content
  const drawerOpen = Boolean(drawerId);
  let drawerContent: React.ReactNode = null;
  if (drawerOpen) {
    if (searching) {
      const asset = allAssets.find((a) => a.id === drawerId);
      if (asset) {
        const registryId = assetRegistryId(asset);
        const graphiti = assetGraphitiStatus(asset);
        const relationships = assetRelationships(asset);
        const relationshipGraphiti = assetGraphitiRelationshipStatus(asset);
        const improvementTarget = employeeImprovementTarget(asset);
        const improvementStatus = employeeImprovementApplicationStatus(asset);
        drawerContent = (
          <div className="space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0"><h3 className="truncate text-lg font-semibold">{asset.title}</h3><div className="mt-1 flex flex-wrap gap-1.5"><Badge variant="outline">{asset.kind}</Badge><Badge variant={statusVar(asset.status)}>{asset.status}</Badge></div></div>
              <Button variant="ghost" size="icon" onClick={() => setDrawerId("")}><X className="h-4 w-4" /></Button>
            </div>
            {metaStr(asset, "description") && <p className="text-sm leading-6 text-muted-foreground">{metaStr(asset, "description")}</p>}
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => setFullText({ title: asset.title, source: metaStr(asset, "saved_path") || asset.source_ticket || asset.id, content: assetFullText(asset) })}>
                <FileText className="h-4 w-4" />Open Full Text
              </Button>
              {registryId && asset.status === "approved" && (
                <Button variant="outline" size="sm" disabled={approving || graphiti.status === "ingested"} onClick={() => handleProjectAssetToGraphiti(asset)}>
                  <Link2 className="h-4 w-4" />Project Graphiti
                </Button>
              )}
              {registryId && asset.status === "approved" && relationships.length > 0 && (
                <Button variant="outline" size="sm" disabled={approving || relationshipGraphiti.status === "projected"} onClick={() => handleProjectAssetRelationshipsToGraphiti(asset)}>
                  <Link2 className="h-4 w-4" />Project Relationships
                </Button>
              )}
              {registryId && improvementTarget && asset.status === "approved" && (
                <Button variant="outline" size="sm" disabled={approving || improvementStatus === "applied"} onClick={() => handleApplyEmployeeImprovement(asset)}>
                  <Sparkles className="h-4 w-4" />Apply Improvement
                </Button>
              )}
            </div>
            <div className="rounded-md border bg-muted/30 p-3">
              <div className="mb-2 text-xs font-medium uppercase text-muted-foreground">Provenance</div>
              <div className="space-y-3"><Status label="Domain" value={assetDomain(asset) || "-"} /><Status label="Source" value={asset.source_ticket || "-"} /><Status label="Employee" value={asset.source_employee || "-"} /><Status label="Updated" value={fmtTime(asset.updated_at)} /></div>
            </div>
            {registryId && (
              <div className="rounded-md border bg-muted/30 p-3">
                <div className="mb-2 text-xs font-medium uppercase text-muted-foreground">Provider Projection</div>
                <div className="space-y-3">
                  <Status label="Asset" value={registryId} />
                  <Status label="Graphiti" value={graphiti.status || "not projected"} />
                  <Status label="Episode" value={graphiti.episodeId || "-"} />
                  <Status label="Relationships" value={`${relationshipGraphiti.projected}/${relationshipGraphiti.total} ${relationshipGraphiti.status}`} />
                </div>
                {relationships.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {relationships.slice(0, 4).map((relationship, index) => (
                      <Badge key={`asset-relationship-${index}`} variant="outline" className="text-[10px]">
                        {provenanceText(relationship, ["type", "relationship_type"]) || "relationship"}:{provenanceText(relationship, ["target_ref", "target_asset_id"]) || "-"}
                      </Badge>
                    ))}
                    {relationshipGraphiti.relationshipIds.slice(0, 3).map((id) => (
                      <Badge key={`asset-graphiti-relationship-${id}`} variant="secondary" className="text-[10px]">{id}</Badge>
                    ))}
                  </div>
                )}
              </div>
            )}
            {registryId && improvementTarget && (
              <div className="rounded-md border bg-muted/30 p-3">
                <div className="mb-2 text-xs font-medium uppercase text-muted-foreground">Employee Improvement</div>
                <div className="space-y-3">
                  <Status label="Employee" value={improvementTarget} />
                  <Status label="Application" value={improvementStatus || "not applied"} />
                </div>
              </div>
            )}
          </div>
        );
      }
    } else if (area === "knowledge") {
      const doc = docs.find((d) => d.id === drawerId);
      const mem = memories.find((m) => m.id === drawerId);
      const dec = decisions.find((d) => d.id === drawerId);
      if (doc) drawerContent = (
        <div className="space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0"><h3 className="truncate text-lg font-semibold">{doc.title}</h3><p className="truncate text-xs text-muted-foreground">{doc.path}</p></div>
            <Button variant="ghost" size="icon" onClick={() => setDrawerId("")}><X className="h-4 w-4" /></Button>
          </div>
          <div className="flex flex-wrap gap-2"><Badge variant={doc.source === "plane" ? "secondary" : "outline"}>{doc.source}</Badge>{doc.tags.map((t) => <Badge key={t} variant="outline">{t}</Badge>)}</div>
          <p className="text-sm leading-6 text-muted-foreground">{doc.excerpt}</p>
          <Button variant="outline" size="sm" onClick={() => setFullText({ title: doc.title, source: doc.path, content: doc.content || doc.excerpt })}>
            <FileText className="h-4 w-4" />Open Full Text
          </Button>
          <Status label="Updated" value={fmtTime(doc.updated_at)} />
        </div>
      );
      else if (mem) {
        const usageSummary = memoryUsageSummary(mem);
        const usageHistory = memoryUsageHistory(mem);
        const latestUsage = latestMemoryUsage(mem);
        const latestUsageId = typeof latestUsage?.usage_id === "string" ? latestUsage.usage_id : "";
        const latestUsefulness = typeof latestUsage?.usefulness_status === "string" ? latestUsage.usefulness_status : "";
        const relatedTicketIds = memoryRelatedTicketIds(mem);
        const sourceTicketId = provenanceText(mem.provenance, ["source_ticket_id"]) || (mem.scope_kind === "ticket" ? mem.scope_ref : "");
        const sourceRunId = provenanceText(mem.provenance, ["source_run_id"]) || provenanceText(asRecord(mem.provenance.usage_summary) ?? {}, ["last_recalled_run_id"]);
        const sourceReportId = provenanceText(mem.provenance, ["source_report_id"]);
        const evidenceId = provenanceText(mem.provenance, ["evidence_id"]);
        const versionHash = provenanceText(mem.provenance, ["version_hash", "content_hash", "hash", "version"]);
        const providerRefs = provenanceText(mem.provenance, ["provider_refs", "provider_ref"]);
        drawerContent = (
          <div className="space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0"><h3 className="truncate text-lg font-semibold">{mem.scope_kind}:{mem.scope_ref}</h3><p className="truncate text-xs text-muted-foreground">{mem.source_kind}:{mem.source_ref || "-"}</p></div>
              <Button variant="ghost" size="icon" onClick={() => setDrawerId("")}><X className="h-4 w-4" /></Button>
            </div>
            <div className="flex flex-wrap gap-2"><Badge variant={statusVar(mem.status)}>{mem.status}</Badge>{mem.tags.map((t) => <Badge key={t} variant="outline">{t}</Badge>)}</div>
            <p className="text-sm leading-6">{mem.content}</p>
            <div className="rounded-md border bg-muted/30 p-3">
              <div className="mb-2 text-xs font-medium uppercase text-muted-foreground">Graphiti Provenance</div>
              <div className="space-y-2">
                <ProvenanceRow label="Episode" title={mem.graphiti_episode_id || "-"}>{mem.graphiti_episode_id || "-"}</ProvenanceRow>
                <ProvenanceRow label="Status" title={graphitiStatusText(mem)}>{graphitiStatusText(mem)}</ProvenanceRow>
                <ProvenanceRow label="Asset" title={`${mem.id} / ${mem.memory_type}`}>{mem.id} / {mem.memory_type}</ProvenanceRow>
                <ProvenanceRow label="Scope" title={`${mem.scope_kind}:${mem.scope_ref}`}>{mem.scope_kind}:{mem.scope_ref}</ProvenanceRow>
                <ProvenanceRow label="Ticket" title={sourceTicketId || "-"}>{sourceTicketId ? (
                  <button type="button" onClick={() => navigateTo("tickets", sourceTicketId)} className="text-primary hover:underline">{sourceTicketId}</button>
                ) : "-"}</ProvenanceRow>
                <ProvenanceRow label="Employee" title={mem.employee_ids.join(", ") || "-"}>{mem.employee_ids.join(", ") || "-"}</ProvenanceRow>
                <ProvenanceRow label="Run" title={sourceRunId || "-"}>{sourceRunId || "-"}</ProvenanceRow>
                <ProvenanceRow label="Report" title={sourceReportId || "-"}>{sourceReportId || "-"}</ProvenanceRow>
                <ProvenanceRow label="Evidence" title={evidenceId || "-"}>{evidenceId || "-"}</ProvenanceRow>
                <ProvenanceRow label="Version" title={versionHash || "-"}>{versionHash || "-"}</ProvenanceRow>
                <ProvenanceRow label="Provider" title={providerRefs || "-"}>{providerRefs || "-"}</ProvenanceRow>
                <ProvenanceRow label="Source" title={`${mem.source_kind}:${mem.source_ref || "-"}`}>{mem.source_kind}:{mem.source_ref || "-"}</ProvenanceRow>
              </div>
            </div>
            {usageSummary && (
              <div className="rounded-md border bg-muted/30 p-3">
                <div className="mb-2 text-xs font-medium uppercase text-muted-foreground">Usage</div>
                <div className="space-y-3">
                  <Status label="Recall count" value={String(usageSummary.recall_count ?? 0)} />
                  <Status label="Used" value={String(usageSummary.used_count ?? usageSummary.useful_count ?? 0)} />
                  <Status label="Irrelevant" value={String(usageSummary.irrelevant_count ?? usageSummary.not_useful_count ?? 0)} />
                  <Status label="Harmful" value={String(usageSummary.harmful_count ?? 0)} />
                  <Status label="Promoted" value={String(usageSummary.promoted_count ?? 0)} />
                  <Status label="Latest status" value={String((usageSummary.last_usefulness_status ?? latestUsefulness) || "-")} />
                  <Status label="Last recalled" value={fmtTime(typeof usageSummary.last_recalled_at === "string" ? usageSummary.last_recalled_at : "")} />
                </div>
              </div>
            )}
            {relatedTicketIds.length > 0 && (
              <div>
                <h4 className="mb-2 text-sm font-semibold">Related Tickets</h4>
                <div className="flex flex-wrap gap-2">
                  {relatedTicketIds.map((ticketId) => (
                    <button key={ticketId} type="button" onClick={() => navigateTo("tickets", ticketId)}>
                      <Badge variant="secondary">{ticketId}</Badge>
                    </button>
                  ))}
                </div>
              </div>
            )}
            {usageHistory.length > 0 && (
              <div>
                <h4 className="mb-2 text-sm font-semibold">Usage History</h4>
                <div className="space-y-2">
                  {usageHistory.slice().reverse().slice(0, 5).map((usage, index) => {
                    const usageId = typeof usage.usage_id === "string" ? usage.usage_id : `usage-${index + 1}`;
                    const usageTickets = asStringArray(usage.source_ticket_ids);
                    const sourceRunId = typeof usage.source_run_id === "string" ? usage.source_run_id : "";
                    const sourceTracePath = typeof usage.source_trace_path === "string" ? usage.source_trace_path : "";
                    const usefulnessStatus = typeof usage.usefulness_status === "string" ? usage.usefulness_status : "unreviewed";
                    return (
                      <div key={`${usageId}-${index}`} className="rounded-md border bg-muted/30 px-3 py-2 text-xs">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-medium text-foreground">{usageId}</span>
                          <Badge variant={statusVar(usefulnessStatus)} className="text-[10px]">{usefulnessStatus}</Badge>
                        </div>
                        <div className="mt-1 flex flex-wrap gap-1.5">
                          {usageTickets.map((ticketId) => (
                            <button key={ticketId} type="button" onClick={() => navigateTo("tickets", ticketId)}>
                              <Badge variant="outline" className="text-[10px]">{ticketId}</Badge>
                            </button>
                          ))}
                        </div>
                        <div className="mt-1 space-y-0.5 text-muted-foreground">
                          <div>Run: {sourceRunId || "-"}</div>
                          <div>Trace: {sourceTracePath || "-"}</div>
                          <div>Recalled: {fmtTime(typeof usage.at === "string" ? usage.at : "")}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
            <Button variant="outline" size="sm" onClick={() => setFullText({ title: `${mem.scope_kind}:${mem.scope_ref}`, source: `${mem.source_kind}:${mem.source_ref || "-"}`, content: mem.content })}>
              <FileText className="h-4 w-4" />Open Full Text
            </Button>
            {mem.status === "proposed" && <Button size="sm" variant="outline" disabled={approving} onClick={() => handleApprove(mem.id)}><Check className="h-3 w-3" />Approve</Button>}
            {mem.status === "approved" && (
              <Button size="sm" variant="outline" disabled={approving} onClick={() => handleReview(mem.id, "stale", "Marked stale from Assets memory detail.")}>
                <Archive className="h-3 w-3" />Mark Stale
              </Button>
            )}
            {mem.status === "approved" && latestUsageId && latestUsefulness === "unreviewed" && (
              <>
                <Button size="sm" variant="outline" disabled={approving} onClick={() => handleUsageReview(mem.id, latestUsageId, "used", "Marked used from Assets memory detail.")}>
                  <Check className="h-3 w-3" />Mark Used
                </Button>
                <Button size="sm" variant="outline" disabled={approving} onClick={() => handleUsageReview(mem.id, latestUsageId, "irrelevant", "Marked irrelevant from Assets memory detail.")}>
                  <X className="h-3 w-3" />Mark Irrelevant
                </Button>
                <Button size="sm" variant="outline" disabled={approving} onClick={() => handleUsageReview(mem.id, latestUsageId, "harmful", "Marked harmful from Assets memory detail.")}>
                  <Archive className="h-3 w-3" />Mark Harmful
                </Button>
                <Button size="sm" variant="outline" disabled={approving} onClick={() => handleUsageReview(mem.id, latestUsageId, "promoted", "Promoted from Assets memory detail.")}>
                  <Check className="h-3 w-3" />Promote
                </Button>
              </>
            )}
          </div>
        );
      }
      else if (dec) drawerContent = (
        <div className="space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0"><h3 className="truncate text-lg font-semibold">{dec.title}</h3><p className="truncate text-xs text-muted-foreground">{dec.saved_path}</p></div>
            <Button variant="ghost" size="icon" onClick={() => setDrawerId("")}><X className="h-4 w-4" /></Button>
          </div>
          <Badge variant={statusVar(dec.status)}>{dec.status}</Badge>
          <p className="text-sm leading-6">{dec.decision}</p>
          {dec.consequences && <div><div className="text-xs font-medium uppercase text-muted-foreground">Consequences</div><p className="text-sm leading-6 text-muted-foreground">{dec.consequences}</p></div>}
          <Button variant="outline" size="sm" onClick={() => setFullText({ title: dec.title, source: dec.saved_path, content: decisionText(dec) })}>
            <FileText className="h-4 w-4" />Open Full Text
          </Button>
        </div>
      );
    } else if (area === "capabilities" && cTab === "skills") {
      const skill = skills.find((s) => s.id === drawerId);
      if (skill) drawerContent = (
        <div className="space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0"><h3 className="truncate text-lg font-semibold">{skill.title}</h3><p className="truncate text-xs text-muted-foreground">{skill.id}</p></div>
            <Button variant="ghost" size="icon" onClick={() => setDrawerId("")}><X className="h-4 w-4" /></Button>
          </div>
          <div className="space-y-3">
            <Status label="Uses" value={skill.usage_count ?? 0} />
            <Status label="Last used" value={fmtTime(skill.last_used_at)} />
            <Status label="Last employee" value={skill.last_used_by_employee_id || "-"} />
            <Status label="Latest ticket" value={skill.last_used_ticket_id || "-"} />
            <Status label="Employees" value={skill.assigned_employees.length} />
            <Status label="Files" value={skill.resources.length + 1} />
          </div>
          {Object.keys(asRecord(skill.usefulness_stats) ?? {}).length > 0 && (
            <div><h4 className="mb-2 text-sm font-semibold">Usefulness</h4><div className="flex flex-wrap gap-2">
              {Object.entries(asRecord(skill.usefulness_stats) ?? {}).map(([status, count]) => (
                <Badge key={status} variant="outline">{status}: {String(count)}</Badge>
              ))}
            </div></div>
          )}
          <div><h4 className="mb-2 text-sm font-semibold">Description</h4><p className="text-sm leading-6 text-muted-foreground">{skill.description || "No description configured."}</p></div>
          <Button variant="outline" size="sm" onClick={() => setFullText({ title: skill.title, source: skill.saved_path, content: skill.content || skill.description || "No SKILL.md content available." })}>
            <FileText className="h-4 w-4" />Open SKILL.md
          </Button>
          {skill.assigned_employees.length > 0 && (
            <div><h4 className="mb-2 text-sm font-semibold">Employees</h4><div className="flex flex-wrap gap-2">{skill.assigned_employees.map((eid) => (
              <button key={eid} type="button" onClick={() => navigateTo("employees", eid)}><Badge variant="secondary">{eid}</Badge></button>
            ))}</div></div>
          )}
          <div><h4 className="mb-2 text-sm font-semibold">Files</h4><div className="space-y-2 text-sm">
            <button type="button" onClick={() => setFullText({ title: skill.title, source: skill.saved_path, content: skill.content || skill.description || "No SKILL.md content available." })} className="w-full rounded-md border bg-muted/30 px-3 py-2 text-left transition-colors hover:bg-muted">
              {skill.saved_path}
            </button>
            {skill.resources.map((r) => <div key={r} className="rounded-md border bg-muted/30 px-3 py-2">{r}</div>)}
          </div></div>
        </div>
      );
    } else if (area === "review") {
      const item = reviewItems.find((i) => i.id === drawerId);
      if (item) drawerContent = (
        <div className="space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0"><h3 className="truncate text-lg font-semibold">{item.title}</h3><p className="truncate text-xs text-muted-foreground">{item.kind} · {item.source_ref}</p></div>
            <Button variant="ghost" size="icon" onClick={() => setDrawerId("")}><X className="h-4 w-4" /></Button>
          </div>
          <div className="space-y-3"><Status label="Kind" value={item.kind} /><Status label="Status" value={item.status} /><Status label="Source" value={item.source_ref || "-"} /><Status label="Created" value={fmtTime(item.created_at)} /><Status label="Updated" value={fmtTime(item.updated_at)} /></div>
          <div><h4 className="mb-2 text-sm font-semibold">Content</h4><p className="whitespace-pre-wrap text-sm leading-6">{item.content}</p></div>
          {metadataBlock(item.metadata) && (
            <div>
              <h4 className="mb-2 text-sm font-semibold">Metadata</h4>
              <pre className="max-h-56 overflow-auto rounded-md border bg-muted/30 p-3 text-xs leading-5">{metadataBlock(item.metadata)}</pre>
            </div>
          )}
          <Button variant="outline" size="sm" onClick={() => setFullText({ title: item.title, source: item.source_ref, content: reviewText(item) })}>
            <FileText className="h-4 w-4" />Open Full Text
          </Button>
          {item.kind === "memory" && item.status === "proposed" && (
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" disabled={approving} onClick={() => handleApprove(item.id)}><Check className="h-3 w-3" />Approve</Button>
              <Button size="sm" variant="outline" disabled={approving} onClick={() => handleReview(item.id, "rejected", "Rejected from Assets review queue.")}><X className="h-3 w-3" />Reject</Button>
            </div>
          )}
        </div>
      );
      else {
        const assetCandidate = assetCandidates.find((candidate) => assetCandidateDrawerId(candidate) === drawerId);
        if (assetCandidate) {
          drawerContent = (
            <div className="space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="truncate text-lg font-semibold">{assetCandidateTitle(assetCandidate)}</h3>
                  <p className="truncate text-xs text-muted-foreground">asset candidate · {assetCandidate.id}</p>
                </div>
                <Button variant="ghost" size="icon" onClick={() => setDrawerId("")}><X className="h-4 w-4" /></Button>
              </div>
              <div className="space-y-3">
                <Status label="Status" value={assetCandidate.status} />
                <Status label="Review state" value={assetCandidate.review_state} />
                <Status label="Asset type" value={assetCandidate.asset_type} />
                <Status label="Scope" value={`${assetCandidate.scope_kind}:${assetCandidate.scope_ref}`} />
                <Status label="Owner" value={assetCandidate.owner_employee_id || "-"} />
                <Status label="Source" value={`${assetCandidate.source_kind}:${assetCandidate.source_ref || "-"}`} />
              </div>
              <ToolCallCandidateDetails item={assetCandidate} />
              <div><h4 className="mb-2 text-sm font-semibold">Content</h4><p className="whitespace-pre-wrap text-sm leading-6">{assetCandidate.content || "-"}</p></div>
              <div className="rounded-md border bg-muted/30 p-3">
                <div className="mb-2 text-xs font-medium uppercase text-muted-foreground">Provenance</div>
                <pre className="max-h-48 overflow-auto text-xs leading-5">{prettyJson(assetCandidate.provenance) || "-"}</pre>
              </div>
              <Button variant="outline" size="sm" onClick={() => setFullText({ title: assetCandidateTitle(assetCandidate), source: assetCandidate.id, content: assetCandidateText(assetCandidate) })}>
                <FileText className="h-4 w-4" />Open Full Text
              </Button>
              {assetCandidate.status === "proposed" && (
                <>
                  <div className="grid gap-3 rounded-md border bg-muted/30 p-3 sm:grid-cols-[minmax(0,1fr)_12rem]">
                    <label className="grid gap-1.5 text-xs font-medium uppercase text-muted-foreground">
                      Target Asset ID
                      <Input
                        aria-label="Target Asset ID"
                        value={assetReviewTargetId}
                        onChange={(event) => setAssetReviewTargetId(event.target.value)}
                        placeholder="asset-id"
                      />
                    </label>
                    <label className="grid gap-1.5 text-xs font-medium uppercase text-muted-foreground">
                      Relationship
                      <Select
                        aria-label="Relationship type"
                        value={assetReviewRelationshipType}
                        onChange={(event) => setAssetReviewRelationshipType(event.target.value)}
                      >
                        <option value="derived_from">derived_from</option>
                        <option value="supersedes">supersedes</option>
                        <option value="conflicts_with">conflicts_with</option>
                        <option value="used_by">used_by</option>
                        <option value="validated_by">validated_by</option>
                      </Select>
                    </label>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={approving}
                      onClick={() => handleAssetCandidateReview(assetCandidate, "approved", {
                        targetAssetId: assetReviewTargetId,
                        relationshipType: assetReviewRelationshipType,
                      })}
                    >
                      <Check className="h-3 w-3" />Approve
                    </Button>
                    <Button size="sm" variant="outline" disabled={approving || !assetReviewTargetId.trim()} onClick={() => handleAssetCandidateReview(assetCandidate, "linked", { targetAssetId: assetReviewTargetId })}>
                      <Link2 className="h-3 w-3" />Link
                    </Button>
                    <Button size="sm" variant="outline" disabled={approving || !assetReviewTargetId.trim()} onClick={() => handleAssetCandidateReview(assetCandidate, "merged", { targetAssetId: assetReviewTargetId })}>
                      <Layers3 className="h-3 w-3" />Merge
                    </Button>
                    <Button size="sm" variant="outline" disabled={approving} onClick={() => handleAssetCandidateReview(assetCandidate, "rejected")}><X className="h-3 w-3" />Reject</Button>
                  </div>
                </>
              )}
            </div>
          );
        } else {
        const approval = runtimeApprovals.find((candidate) => runtimeApprovalDrawerId(candidate) === drawerId);
        if (approval) {
          const lastResult = runtimeApprovalLastResultDetail(approval);
          const result = asRecord(approval.last_result);
          const lastRunReport = typeof result?.report === "string" ? result.report : "";
          const runHistory = runtimeApprovalRunHistory(approval);
          drawerContent = (
            <div className="space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="truncate text-lg font-semibold">{runtimeApprovalTitle(approval)}</h3>
                  <p className="truncate text-xs text-muted-foreground">runtime approval · {approval.executor_id} · {approval.id}</p>
                </div>
                <Button variant="ghost" size="icon" onClick={() => setDrawerId("")}><X className="h-4 w-4" /></Button>
              </div>
              <div className="space-y-3">
                <Status label="Status" value={approval.status} />
                <Status label="Executor" value={approval.executor_id || "-"} />
                <Status label="Capability" value={approval.required_capability || "-"} />
                <Status label="Ticket" value={approval.ticket_id || "-"} />
                <Status label="Employee" value={approval.employee_id || "-"} />
                <Status label="Updated" value={fmtTime(approval.updated_at)} />
                {approval.reviewed_at && <Status label="Reviewed" value={`${fmtTime(approval.reviewed_at)} by ${approval.reviewer_employee_id || "-"}`} />}
                {approval.last_run_request_id && <Status label="Last run" value={`${approval.last_run_request_id} (${approval.last_run_status || "-"})`} />}
                {approval.last_ingestion_blocker && <Status label="Ingestion blocker" value={approval.last_ingestion_blocker} />}
              </div>
              <div><h4 className="mb-2 text-sm font-semibold">Reason</h4><p className="whitespace-pre-wrap text-sm leading-6">{approval.reason || "-"}</p></div>
              {approval.review_reason && <div><h4 className="mb-2 text-sm font-semibold">Review Reason</h4><p className="whitespace-pre-wrap text-sm leading-6 text-muted-foreground">{approval.review_reason}</p></div>}
              {lastRunReport && <div><h4 className="mb-2 text-sm font-semibold">Last Result</h4><p className="whitespace-pre-wrap text-sm leading-6 text-muted-foreground">{lastRunReport}</p></div>}
              {lastResult && !lastRunReport && <div className="rounded-md border bg-muted/30 p-3 text-sm text-muted-foreground">{lastResult}</div>}
              {runHistory.length > 0 && (
                <div>
                  <h4 className="mb-2 text-sm font-semibold">Run History</h4>
                  <div className="space-y-2">
                    {runHistory.map((entry, index) => {
                      const runRequestId = String(entry.run_request_id ?? `attempt-${index + 1}`);
                      const traceRef = String(entry.trace_ref ?? "");
                      const blocker = typeof entry.ingestion_blocker === "string" ? entry.ingestion_blocker : "";
                      return (
                        <div key={`${runRequestId}-${index}`} className="rounded-md border bg-muted/30 p-3 text-xs">
                          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                            <div className="min-w-0 font-medium">
                              <span className="text-muted-foreground">Attempt {index + 1}</span>
                              <span className="ml-2 break-all text-foreground">{runRequestId}</span>
                            </div>
                            <Badge variant={statusVar(String(entry.status ?? ""))}>{String(entry.status ?? "-")}</Badge>
                          </div>
                          <div className="grid gap-2 sm:grid-cols-2">
                            <Status label="Ingested" value={String(entry.ingested ?? "-")} />
                            <Status label="Trace" value={traceRef || "-"} />
                            <Status label="Artifacts" value={String(entry.artifact_count ?? 0)} />
                            <Status label="Evidence" value={String(entry.evidence_count ?? 0)} />
                            <Status label="Errors" value={String(entry.error_count ?? 0)} />
                            <Status label="Capabilities" value={asStringArray(entry.approved_capabilities).join(", ") || "-"} />
                          </div>
                          {blocker && <div className="mt-2 rounded border border-destructive/30 bg-destructive/10 px-2 py-1 text-destructive">Ingestion blocker: {blocker}</div>}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
              <div className="rounded-md border bg-muted/30 p-3">
                <div className="mb-2 text-xs font-medium uppercase text-muted-foreground">Approval Request</div>
                <pre className="max-h-48 overflow-auto text-xs leading-5">{prettyJson(approval.approval_request) || "-"}</pre>
              </div>
              <Button variant="outline" size="sm" onClick={() => setFullText({ title: runtimeApprovalTitle(approval), source: approval.id, content: runtimeApprovalText(approval) })}>
                <FileText className="h-4 w-4" />Open Full Text
              </Button>
              {approval.status === "requested" && (
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" disabled={approving} onClick={() => handleRuntimeApprovalReview(approval, "approved")}><Check className="h-3 w-3" />Approve</Button>
                  <Button size="sm" variant="outline" disabled={approving} onClick={() => handleRuntimeApprovalReview(approval, "rejected")}><X className="h-3 w-3" />Reject</Button>
                </div>
              )}
              {approval.status === "approved" && (
                <Button size="sm" variant="outline" disabled={approving} onClick={() => handleRuntimeApprovalRun(approval)}><Check className="h-3 w-3" />Run</Button>
              )}
            </div>
          );
        }
        }
      }
    } else {
      const asset = allAssets.find((a) => a.id === drawerId);
      if (asset) {
        const registryId = assetRegistryId(asset);
        const graphiti = assetGraphitiStatus(asset);
        const relationships = assetRelationships(asset);
        const relationshipGraphiti = assetGraphitiRelationshipStatus(asset);
        const improvementTarget = employeeImprovementTarget(asset);
        const improvementStatus = employeeImprovementApplicationStatus(asset);
        drawerContent = (
          <div className="space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0"><h3 className="truncate text-lg font-semibold">{asset.title}</h3><div className="mt-1 flex flex-wrap gap-1.5"><Badge variant="outline">{asset.kind}</Badge><Badge variant={statusVar(asset.status)}>{asset.status}</Badge></div></div>
              <Button variant="ghost" size="icon" onClick={() => setDrawerId("")}><X className="h-4 w-4" /></Button>
            </div>
            {metaStr(asset, "description") && <p className="text-sm leading-6 text-muted-foreground">{metaStr(asset, "description")}</p>}
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => setFullText({ title: asset.title, source: metaStr(asset, "saved_path") || asset.source_ticket || asset.id, content: assetFullText(asset) })}>
                <FileText className="h-4 w-4" />Open Full Text
              </Button>
              {registryId && asset.status === "approved" && (
                <Button variant="outline" size="sm" disabled={approving || graphiti.status === "ingested"} onClick={() => handleProjectAssetToGraphiti(asset)}>
                  <Link2 className="h-4 w-4" />Project Graphiti
                </Button>
              )}
              {registryId && asset.status === "approved" && relationships.length > 0 && (
                <Button variant="outline" size="sm" disabled={approving || relationshipGraphiti.status === "projected"} onClick={() => handleProjectAssetRelationshipsToGraphiti(asset)}>
                  <Link2 className="h-4 w-4" />Project Relationships
                </Button>
              )}
              {registryId && improvementTarget && asset.status === "approved" && (
                <Button variant="outline" size="sm" disabled={approving || improvementStatus === "applied"} onClick={() => handleApplyEmployeeImprovement(asset)}>
                  <Sparkles className="h-4 w-4" />Apply Improvement
                </Button>
              )}
            </div>
            <div className="rounded-md border bg-muted/30 p-3">
              <div className="mb-2 text-xs font-medium uppercase text-muted-foreground">Provenance</div>
              <div className="space-y-3"><Status label="Domain" value={assetDomain(asset) || "-"} /><Status label="Source" value={asset.source_ticket || "-"} /><Status label="Employee" value={asset.source_employee || "-"} /><Status label="Updated" value={fmtTime(asset.updated_at)} /></div>
            </div>
            {registryId && (
              <div className="rounded-md border bg-muted/30 p-3">
                <div className="mb-2 text-xs font-medium uppercase text-muted-foreground">Provider Projection</div>
                <div className="space-y-3">
                  <Status label="Asset" value={registryId} />
                  <Status label="Graphiti" value={graphiti.status || "not projected"} />
                  <Status label="Episode" value={graphiti.episodeId || "-"} />
                  <Status label="Relationships" value={`${relationshipGraphiti.projected}/${relationshipGraphiti.total} ${relationshipGraphiti.status}`} />
                </div>
                {relationships.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {relationships.slice(0, 4).map((relationship, index) => (
                      <Badge key={`asset-relationship-${index}`} variant="outline" className="text-[10px]">
                        {provenanceText(relationship, ["type", "relationship_type"]) || "relationship"}:{provenanceText(relationship, ["target_ref", "target_asset_id"]) || "-"}
                      </Badge>
                    ))}
                    {relationshipGraphiti.relationshipIds.slice(0, 3).map((id) => (
                      <Badge key={`asset-graphiti-relationship-${id}`} variant="secondary" className="text-[10px]">{id}</Badge>
                    ))}
                  </div>
                )}
              </div>
            )}
            {registryId && improvementTarget && (
              <div className="rounded-md border bg-muted/30 p-3">
                <div className="mb-2 text-xs font-medium uppercase text-muted-foreground">Employee Improvement</div>
                <div className="space-y-3">
                  <Status label="Employee" value={improvementTarget} />
                  <Status label="Application" value={improvementStatus || "not applied"} />
                </div>
              </div>
            )}
          </div>
        );
      }
    }
  }

  // Render main content based on area (no embedded tabs — tabs are in the unified bar above)
  let mainContent: React.ReactNode;
  if (loading) {
    mainContent = <ContentSkeleton />;
  } else if (searching) {
    mainContent = (
      <section className="rounded-md border bg-background">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <div className="flex items-center gap-2">
            <Search className="h-4 w-4 text-muted-foreground" />
            <div><h3 className="text-sm font-semibold">Search Results</h3><p className="text-xs text-muted-foreground">{`Results for "${submittedQuery}"`}</p></div>
          </div>
          <Badge variant="secondary">{allAssets.length}</Badge>
        </div>
        {allAssets.length === 0 ? (
          <EmptyState title="No matching results" description={`No assets match "${submittedQuery}". Try a different search term.`} action={<Button variant="outline" size="sm" onClick={() => { setQuery(""); setSubmittedQuery(""); }}>Clear search</Button>} />
        ) : allAssets.map((a) => (
          <AssetRow key={`${a.kind}-${a.id}`} asset={a} active={drawerId === a.id} onSelect={() => setDrawerId(a.id)} />
        ))}
      </section>
    );
  } else if (!area) {
    mainContent = <AssetOverview allAssets={allAssets} assetCandidates={assetCandidates} knowledgeStatus={knowledgeStatus} reviewItems={reviewItems} runtimeApprovals={runtimeApprovals} skills={skills} capRegistry={capRegistry} planV8Artifacts={planV8Artifacts} />;
  } else if (area === "knowledge") {
    mainContent = (
      <section className="rounded-md border bg-background">
        {kTab === "docs" ? <KnowledgeDocsList docs={docs} selectedId={drawerId} onSelect={setDrawerId} /> : null}
        {kTab === "memories" && <KnowledgeMemoriesList memories={memories} selectedId={drawerId} onSelect={setDrawerId} onApprove={handleApprove} approving={approving} />}
        {kTab === "decisions" && <KnowledgeDecisionsList decisions={decisions} selectedId={drawerId} onSelect={setDrawerId} />}
      </section>
    );
  } else if (area === "capabilities") {
    mainContent = cTab === "skills" ? (
      <section className="rounded-md border bg-background">
        <SkillsTableView skills={skills} selectedId={drawerId} onSelect={setDrawerId} />
      </section>
    ) : (capRegistry ? (
      <CapabilitiesGroupedView
        registry={capRegistry}
        tab={cTab}
        selectedId={drawerId}
        onSelect={setDrawerId}
      />
    ) : <ContentSkeleton />);
  } else if (area === "review") {
    mainContent = (
      <section className="rounded-md border bg-background">
        <ReviewQueueList
          assetCandidates={assetCandidates}
          items={reviewItems}
          runtimeApprovals={runtimeApprovals}
          selectedId={drawerId}
          onSelect={setDrawerId}
          onApprove={handleApprove}
          onAssetCandidateReview={handleAssetCandidateReview}
          onAssetCandidateBatchReview={handleAssetCandidateBatchReview}
          onRuntimeReview={handleRuntimeApprovalReview}
          onRuntimeRun={handleRuntimeApprovalRun}
          approving={approving}
          tab={rTab}
        />
      </section>
    );
  } else {
    mainContent = (
      <section className="rounded-md border bg-background">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <div className="flex items-center gap-2">
            {searching ? <Search className="h-4 w-4 text-muted-foreground" /> : <Archive className="h-4 w-4 text-muted-foreground" />}
            <div><h3 className="text-sm font-semibold">{searching ? "Search Results" : areaLabel}</h3><p className="text-xs text-muted-foreground">{searching ? `Results for "${submittedQuery}"` : "All traceable team assets."}</p></div>
          </div>
          <Badge variant="secondary">{allAssets.length}</Badge>
        </div>
        {allAssets.length === 0 ? (
          <EmptyState title={searching ? "No matching results" : "No assets found"} description={searching ? `No assets match "${submittedQuery}". Try a different search term.` : "Assets are traceable team resources. Add knowledge docs, configure skills, or connect tools to populate this view."} action={searching ? <Button variant="outline" size="sm" onClick={() => { setQuery(""); setSubmittedQuery(""); }}>Clear search</Button> : <Button variant="outline" size="sm" onClick={() => navigateTo("chat")}>Ask in Chat</Button>} />
        ) : allAssets.map((a) => (
          <AssetRow key={`${a.kind}-${a.id}`} asset={a} active={drawerId === a.id} onSelect={() => setDrawerId(a.id)} />
        ))}
      </section>
    );
  }

  // Unified tab bar: area tabs + contextual sub-tabs in one row
  const tabBtnCls = "flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2 text-xs font-medium transition-colors";

  return (
    <div className="space-y-3">
      {/* Compact stable header */}
      <section className="rounded-md border bg-background">
        <div className="flex items-center justify-between gap-3 px-4 py-2.5">
          <div className="flex items-center gap-1 text-sm font-semibold">
            {breadcrumbSegments.map((seg, i) => (
              <span key={i} className="flex items-center gap-1">
                {i > 0 && <span className="text-muted-foreground">/</span>}
                {seg.onClick ? (
                  <button type="button" onClick={seg.onClick} className="text-muted-foreground hover:text-foreground transition-colors">{seg.label}</button>
                ) : <span>{seg.label}</span>}
              </span>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <form onSubmit={submitSearch} className="flex items-center gap-1.5">
              <div className="relative">
                <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <input aria-label="Search assets" value={query}
                  onChange={(e) => { setQuery(e.target.value); if (!e.target.value.trim()) setSubmittedQuery(""); }}
                  placeholder="Search assets…"
                  className="h-7 w-48 rounded border border-input bg-background pl-7 pr-2 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
              </div>
              {submittedQuery && <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => { setQuery(""); setSubmittedQuery(""); }}><X className="h-3 w-3" /></Button>}
            </form>
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => void load()} title="Refresh"><RefreshCw className="h-3.5 w-3.5" /></Button>
          </div>
        </div>
        {error && <div className="border-t px-4 py-2"><ErrorState message={error} onRetry={load} /></div>}
      </section>

      {/* Area tabs — always stable, never re-rendered on content load */}
      <nav className="flex items-center gap-0 overflow-x-auto border-b">
        <button type="button" onClick={() => navigateTo("assets")} className={cn(
          tabBtnCls,
          !area && !searching ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
        )}>
          <Layers3 className="h-3.5 w-3.5" />Overview
        </button>
        {AREA_TABS.map((tab) => {
          const Icon = tab.icon;
          return (
            <button key={tab.key} type="button" onClick={() => navigateTo("assets", tab.key)} className={cn(
              tabBtnCls,
              area === tab.key && !searching ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
            )}>
              <Icon className="h-3.5 w-3.5" />{tab.label}
            </button>
          );
        })}
      </nav>

      {/* Contextual sub-tabs — second row, only when area is active */}
      {area && !searching && (area === "knowledge" || area === "capabilities" || area === "review") && (
        <nav className="flex items-center gap-0 overflow-x-auto border-b pl-1">
          {area === "knowledge" && KNOWLEDGE_TABS.map((t) => (
            <button key={t.key} type="button" onClick={() => navigateTo("assets", "knowledge", t.key)} className={cn(
              tabBtnCls, "text-[11px] px-2.5",
              kTab === t.key ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
            )}>{t.label}</button>
          ))}
          {area === "capabilities" && CAPABILITY_TABS.map((t) => (
            <button key={t.key} type="button" onClick={() => navigateTo("assets", "capabilities", t.key)} className={cn(
              tabBtnCls, "text-[11px] px-2.5",
              cTab === t.key ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
            )}>{t.label}</button>
          ))}
          {area === "review" && (
            <>
              <button type="button" onClick={() => navigateTo("assets", "review")} className={cn(
                tabBtnCls, "text-[11px] px-2.5",
                !rTab ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
              )}>All</button>
              {(["memories", "decisions", "skills", "tools"] as const).map((t) => (
                <button key={t} type="button" onClick={() => navigateTo("assets", "review", t)} className={cn(
                  tabBtnCls, "text-[11px] px-2.5 capitalize",
                  rTab === t ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
                )}>{t}</button>
              ))}
            </>
          )}
        </nav>
      )}

      {/* Content area with drawer overlay */}
      <div className="relative">
        <section className={cn("transition-[padding] duration-200", drawerOpen && `pr-[${DRAWER_W}]`)} style={drawerOpen ? { paddingRight: DRAWER_W } : undefined}>
          {mainContent}
        </section>

        {/* Slide-over detail drawer */}
        {drawerOpen && drawerContent && (
          <aside className="absolute inset-y-0 right-0 z-20 flex flex-col overflow-y-auto border-l bg-background p-6 shadow-xl" style={{ width: DRAWER_W }}>
            {drawerContent}
          </aside>
        )}
      </div>

      <Dialog open={Boolean(fullText)} onOpenChange={(open) => { if (!open) setFullText(null); }}>
        <DialogContent className="max-h-[86vh] max-w-4xl grid-rows-[auto_minmax(0,1fr)]">
          <DialogHeader>
            <DialogTitle className="pr-8">{fullText?.title ?? "Asset full text"}</DialogTitle>
            <DialogDescription>{fullText?.source || "Read-only asset content"}</DialogDescription>
          </DialogHeader>
          <Textarea
            aria-label="Asset full text"
            readOnly
            value={fullText?.content ?? ""}
            className="min-h-[60vh] resize-none overflow-auto whitespace-pre font-mono text-xs leading-5"
          />
        </DialogContent>
      </Dialog>
    </div>
  );
}
