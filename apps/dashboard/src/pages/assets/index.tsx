import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  Archive, BookOpen, Brain, Check, ClipboardCheck, Layers3,
  FileText, RefreshCw, Search,
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
import { Textarea } from "../../components/ui/textarea";
import { ErrorState, EmptyState, Status, navigateTo } from "../../components/shared";
import { Skeleton } from "../../components/ui/skeleton";
import { listAssets, type AssetRecord } from "../../api/assets";
import {
  getKnowledgeStatus, listKnowledgeDocs, listKnowledgeDecisions,
  listKnowledgeReviewQueue,
  type DecisionRecord, type KnowledgeDocSummary,
  type KnowledgeStatusResponse, type ReviewQueueItem,
} from "../../api/knowledge";
import {
  approveMemoryCandidate, listApprovedMemory, type MemoryCandidate,
} from "../../api/memory";
import {
  getCapabilities, type CapabilityRecord, type CapabilityRegistryResponse,
} from "../../api/capabilities";
import { listChatSkills, type ChatSkillSummary } from "../../api/chat";
import { cn } from "@/lib/utils";

/* ── types & constants ─────────────────────────────────────────────────────── */

type AssetArea = "knowledge" | "capabilities" | "review";
type KnowledgeTab = "docs" | "memories" | "decisions";
type CapabilityTab = "skills" | "kernel-commands" | "mcp-tools";
type ReviewTab = "memories" | "decisions" | "skills" | "tools";

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

const CAPABILITY_TABS: Array<{ key: CapabilityTab; label: string }> = [
  { key: "skills", label: "Skills" },
  { key: "kernel-commands", label: "Kernel Commands" },
  { key: "mcp-tools", label: "MCP Tools" },
];

/* ── helpers ───────────────────────────────────────────────────────────────── */

function areaFromRoute(v?: string | null): AssetArea | null {
  if (!v || v === "all") return null;
  if (v === "skills" || v === "kernel-commands" || v === "mcp-tools") return "capabilities";
  return AREA_TABS.some((t) => t.key === v) ? (v as AssetArea) : null;
}

function fmtTime(v?: string | null): string {
  if (!v) return "-";
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? "-" : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function statusVar(s: string): "default" | "secondary" | "warning" | "success" | "danger" | "outline" {
  if (["approved", "accepted", "ready", "configured", "active", "local", "available"].includes(s)) return "success";
  if (["proposed", "candidate", "planned", "pending", "held"].includes(s)) return "warning";
  if (["failed", "blocked", "invalid", "missing"].includes(s)) return "danger";
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

const REVIEW_TABS = new Set(["memories", "decisions", "skills", "tools"]);

function AssetOverview({
  allAssets, knowledgeStatus, reviewItems, skills, capRegistry,
}: {
  allAssets: AssetRecord[]; knowledgeStatus: KnowledgeStatusResponse | null;
  reviewItems: ReviewQueueItem[]; skills: ChatSkillSummary[];
  capRegistry: CapabilityRegistryResponse | null;
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
  const revTools = reviewItems.filter((i) => i.kind === "tool" || i.kind === "capability").length;

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
      area: "review" as AssetArea, total: reviewItems.length,
      subs: [
        { label: "Memories", count: revMemories, detail: "memories" },
        { label: "Decisions", count: revDecisions, detail: "decisions" },
        { label: "Skills", count: revSkills, detail: "skills" },
        { label: "Tools", count: revTools, detail: "tools" },
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
        {reviewItems.length > 0 && (
          <section className="rounded-md border bg-background p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold">Pending Review</h3>
              <Button variant="outline" size="sm" onClick={() => navigateTo("assets", "review")}>View all</Button>
            </div>
            <div className="space-y-2">
              {reviewItems.slice(0, 3).map((item) => (
                <button key={item.id} type="button"
                  onClick={() => navigateTo("assets", "review", REVIEW_TABS.has(item.kind) ? item.kind : undefined)}
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
      <TableHeader><TableRow><TableHead>Name</TableHead><TableHead>Description</TableHead><TableHead className="text-right">Employees</TableHead><TableHead className="text-right">Files</TableHead></TableRow></TableHeader>
      <TableBody>{skills.map((skill) => (
        <TableRow key={skill.id} className={cn("cursor-pointer", selectedId === skill.id && "bg-muted/60")} onClick={() => onSelect(skill.id)}>
          <TableCell><div className="flex items-center gap-2"><BookOpen className="h-4 w-4 text-muted-foreground" /><div><div className="font-medium">{skill.title}</div><div className="text-xs text-muted-foreground">{skill.id}</div></div></div></TableCell>
          <TableCell className="max-w-[32rem] truncate text-muted-foreground">{skill.description || "No description configured."}</TableCell>
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
  items, selectedId, onSelect, onApprove, approving, tab,
}: {
  items: ReviewQueueItem[]; selectedId: string; onSelect: (id: string) => void;
  onApprove: (id: string) => void; approving: boolean; tab: ReviewTab | null;
}) {
  const filtered = tab ? items.filter((i) => {
    if (tab === "memories") return i.kind === "memory";
    if (tab === "decisions") return i.kind === "decision";
    if (tab === "skills") return i.kind === "skill";
    if (tab === "tools") return i.kind === "tool" || i.kind === "capability";
    return true;
  }) : items;
  if (filtered.length === 0) return <EmptyState title="No review items" description={tab ? `No pending ${tab} reviews. Items will appear here when candidates are proposed.` : "Review queue is clear. Proposed memories, decisions, skills, and tool changes will appear here for approval."} />;
  return <div>{filtered.map((item) => (
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
  ))}</div>;
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
  const [allAssets, setAllAssets] = useState<AssetRecord[]>([]);
  const [knowledgeStatus, setKnowledgeStatus] = useState<KnowledgeStatusResponse | null>(null);
  const [docs, setDocs] = useState<KnowledgeDocSummary[]>([]);
  const [memories, setMemories] = useState<MemoryCandidate[]>([]);
  const [decisions, setDecisions] = useState<DecisionRecord[]>([]);
  const [reviewItems, setReviewItems] = useState<ReviewQueueItem[]>([]);
  const [skills, setSkills] = useState<ChatSkillSummary[]>([]);
  const [capRegistry, setCapRegistry] = useState<CapabilityRegistryResponse | null>(null);
  const [drawerId, setDrawerId] = useState("");
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [approving, setApproving] = useState(false);
  const [fullText, setFullText] = useState<FullTextPayload | null>(null);

  const searching = Boolean(submittedQuery.trim());

  // Sub-tab for knowledge & capabilities (auto-select first when entering area)
  const kTab: KnowledgeTab | null = area === "knowledge"
    ? (selectedDetail && ["docs", "memories", "decisions"].includes(selectedDetail) ? selectedDetail as KnowledgeTab : "docs")
    : null;
  const cTab: CapabilityTab | null = area === "capabilities"
    ? (selectedDetail && ["skills", "kernel-commands", "mcp-tools"].includes(selectedDetail) ? selectedDetail as CapabilityTab : "skills")
    : null;
  const rTab: ReviewTab | null = area === "review"
    ? (selectedDetail && ["memories", "decisions", "skills", "tools"].includes(selectedDetail) ? selectedDetail as ReviewTab : null)
    : null;

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const assetQuery = submittedQuery.trim();
      const [a, ks, d, m, dec, rev, sk, cap] = await Promise.all([
        listAssets(assetQuery ? null : area, assetQuery ? null : selectedDetail, assetQuery).catch(() => []),
        getKnowledgeStatus().catch(() => null),
        listKnowledgeDocs().catch(() => []),
        listApprovedMemory().catch(() => []),
        listKnowledgeDecisions().catch(() => []),
        listKnowledgeReviewQueue().catch(() => []),
        listChatSkills().catch(() => []),
        getCapabilities().catch(() => null),
      ]);
      setAllAssets(a); setKnowledgeStatus(ks); setDocs(d); setMemories(m);
      setDecisions(dec); setReviewItems(rev); setSkills(sk); setCapRegistry(cap);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to load assets"); }
    finally { setLoading(false); }
  }, [area, selectedDetail, submittedQuery]);

  useEffect(() => { void load(); }, [load]);

  // Close drawer when switching asset scopes, including sibling sub-tabs.
  useEffect(() => {
    setDrawerId("");
    setFullText(null);
  }, [area, selectedDetail, submittedQuery]);

  function submitSearch(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setSubmittedQuery(query.trim());
  }

  function handleApprove(id: string) {
    setApproving(true);
    approveMemoryCandidate(id).then(() => load()).catch((err) => setError(err.message)).finally(() => setApproving(false));
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
      if (asset) drawerContent = (
        <div className="space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0"><h3 className="truncate text-lg font-semibold">{asset.title}</h3><div className="mt-1 flex flex-wrap gap-1.5"><Badge variant="outline">{asset.kind}</Badge><Badge variant={statusVar(asset.status)}>{asset.status}</Badge></div></div>
            <Button variant="ghost" size="icon" onClick={() => setDrawerId("")}><X className="h-4 w-4" /></Button>
          </div>
          {metaStr(asset, "description") && <p className="text-sm leading-6 text-muted-foreground">{metaStr(asset, "description")}</p>}
          <Button variant="outline" size="sm" onClick={() => setFullText({ title: asset.title, source: metaStr(asset, "saved_path") || asset.source_ticket || asset.id, content: assetFullText(asset) })}>
            <FileText className="h-4 w-4" />Open Full Text
          </Button>
          <div className="rounded-md border bg-muted/30 p-3">
            <div className="mb-2 text-xs font-medium uppercase text-muted-foreground">Provenance</div>
            <div className="space-y-3"><Status label="Domain" value={assetDomain(asset) || "-"} /><Status label="Source" value={asset.source_ticket || "-"} /><Status label="Employee" value={asset.source_employee || "-"} /><Status label="Updated" value={fmtTime(asset.updated_at)} /></div>
          </div>
        </div>
      );
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
      else if (mem) drawerContent = (
        <div className="space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0"><h3 className="truncate text-lg font-semibold">{mem.scope_kind}:{mem.scope_ref}</h3><p className="truncate text-xs text-muted-foreground">{mem.source_kind}:{mem.source_ref || "-"}</p></div>
            <Button variant="ghost" size="icon" onClick={() => setDrawerId("")}><X className="h-4 w-4" /></Button>
          </div>
          <div className="flex flex-wrap gap-2"><Badge variant={statusVar(mem.status)}>{mem.status}</Badge>{mem.tags.map((t) => <Badge key={t} variant="outline">{t}</Badge>)}</div>
          <p className="text-sm leading-6">{mem.content}</p>
          <Button variant="outline" size="sm" onClick={() => setFullText({ title: `${mem.scope_kind}:${mem.scope_ref}`, source: `${mem.source_kind}:${mem.source_ref || "-"}`, content: mem.content })}>
            <FileText className="h-4 w-4" />Open Full Text
          </Button>
          {mem.status === "proposed" && <Button size="sm" variant="outline" disabled={approving} onClick={() => handleApprove(mem.id)}><Check className="h-3 w-3" />Approve</Button>}
        </div>
      );
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
          <div className="space-y-3"><Status label="Employees" value={skill.assigned_employees.length} /><Status label="Files" value={skill.resources.length + 1} /></div>
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
          {item.kind === "memory" && item.status === "proposed" && <Button size="sm" variant="outline" disabled={approving} onClick={() => handleApprove(item.id)}><Check className="h-3 w-3" />Approve</Button>}
        </div>
      );
    } else {
      const asset = allAssets.find((a) => a.id === drawerId);
      if (asset) drawerContent = (
        <div className="space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0"><h3 className="truncate text-lg font-semibold">{asset.title}</h3><div className="mt-1 flex flex-wrap gap-1.5"><Badge variant="outline">{asset.kind}</Badge><Badge variant={statusVar(asset.status)}>{asset.status}</Badge></div></div>
            <Button variant="ghost" size="icon" onClick={() => setDrawerId("")}><X className="h-4 w-4" /></Button>
          </div>
          {metaStr(asset, "description") && <p className="text-sm leading-6 text-muted-foreground">{metaStr(asset, "description")}</p>}
          <Button variant="outline" size="sm" onClick={() => setFullText({ title: asset.title, source: metaStr(asset, "saved_path") || asset.source_ticket || asset.id, content: assetFullText(asset) })}>
            <FileText className="h-4 w-4" />Open Full Text
          </Button>
          <div className="rounded-md border bg-muted/30 p-3">
            <div className="mb-2 text-xs font-medium uppercase text-muted-foreground">Provenance</div>
            <div className="space-y-3"><Status label="Domain" value={assetDomain(asset) || "-"} /><Status label="Source" value={asset.source_ticket || "-"} /><Status label="Employee" value={asset.source_employee || "-"} /><Status label="Updated" value={fmtTime(asset.updated_at)} /></div>
          </div>
        </div>
      );
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
    mainContent = <AssetOverview allAssets={allAssets} knowledgeStatus={knowledgeStatus} reviewItems={reviewItems} skills={skills} capRegistry={capRegistry} />;
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
        <ReviewQueueList items={reviewItems} selectedId={drawerId} onSelect={setDrawerId} onApprove={handleApprove} approving={approving} tab={rTab} />
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
