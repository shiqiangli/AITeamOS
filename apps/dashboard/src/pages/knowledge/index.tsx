import { FormEvent, useEffect, useMemo, useState } from "react";
import { Brain, Check, ExternalLink, FileText, MessageSquare, Plug, RefreshCw, Search } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { ErrorState, LoadingState, navigateTo, Status } from "../../components/shared";
import { getMcpConnectorSettings, type McpConnectorSettingsResponse } from "../../api/mcp";
import {
  getKnowledgeStatus,
  listKnowledgeDecisions,
  listKnowledgeDocs,
  listKnowledgeReviewQueue,
  searchKnowledge,
  type DecisionRecord,
  type KnowledgeDocSummary,
  type KnowledgeSearchResult,
  type KnowledgeStatusResponse,
  type ReviewQueueItem,
} from "../../api/knowledge";
import {
  approveMemoryCandidate,
  listApprovedMemory,
  type MemoryCandidate,
} from "../../api/memory";
import { cn } from "@/lib/utils";

type KnowledgeSection = "docs" | "memories" | "decisions" | "review";
type KnowledgeItem =
  | { kind: "doc"; id: string; title: string; subtitle: string; content: string; metadata: KnowledgeDocSummary }
  | { kind: "memory"; id: string; title: string; subtitle: string; content: string; metadata: MemoryCandidate }
  | { kind: "decision"; id: string; title: string; subtitle: string; content: string; metadata: DecisionRecord }
  | { kind: "review"; id: string; title: string; subtitle: string; content: string; metadata: ReviewQueueItem }
  | { kind: "search"; id: string; title: string; subtitle: string; content: string; metadata: KnowledgeSearchResult };

const SECTIONS: { key: KnowledgeSection; label: string }[] = [
  { key: "docs", label: "Docs" },
  { key: "memories", label: "Memories" },
  { key: "decisions", label: "Decisions" },
  { key: "review", label: "Review Queue" },
];

function sectionFromRoute(value?: string | null): KnowledgeSection {
  return SECTIONS.some((section) => section.key === value) ? value as KnowledgeSection : "docs";
}

function formatTime(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function planeHref(settings: McpConnectorSettingsResponse | null): string {
  return settings?.base_url?.trim() || "http://localhost:8082";
}

function DocsSourcePanel({ settings }: { settings: McpConnectorSettingsResponse | null }) {
  const configured = Boolean(settings?.configured);
  return (
    <section className="rounded-md border bg-background p-4">
      <div className="mb-3 flex items-center gap-2">
        <Plug className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold">Doc Sources</h3>
      </div>
      <div className="space-y-3 text-sm">
        <div className="rounded-md border bg-muted/30 p-3">
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium">Local Markdown</span>
            <Badge variant="success">active</Badge>
          </div>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            AITeamOS direction, interaction design, architecture principles, and local process docs.
          </p>
        </div>
        <div className="rounded-md border bg-muted/30 p-3">
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium">Plane Pages</span>
            <Badge variant={configured ? "success" : "warning"}>{configured ? "configured" : "not configured"}</Badge>
          </div>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            Project pages, proposals, postmortems, and long-form docs linked to WorkItems.
          </p>
          <a
            className="mt-3 inline-flex h-8 items-center justify-center gap-2 rounded-md border border-input bg-background px-3 text-xs font-medium hover:bg-accent hover:text-accent-foreground"
            href={planeHref(settings)}
            target="_blank"
            rel="noreferrer"
          >
            <ExternalLink className="h-4 w-4" />
            Open Plane
          </a>
        </div>
      </div>
    </section>
  );
}

function docsToItems(docs: KnowledgeDocSummary[]): KnowledgeItem[] {
  return docs.map((doc) => ({
    kind: "doc",
    id: doc.id,
    title: doc.title,
    subtitle: doc.path,
    content: doc.excerpt,
    metadata: doc,
  }));
}

function memoriesToItems(memories: MemoryCandidate[]): KnowledgeItem[] {
  return memories.map((memory) => ({
    kind: "memory",
    id: memory.id,
    title: `${memory.scope_kind}:${memory.scope_ref}`,
    subtitle: `${memory.source_kind}:${memory.source_ref || "-"}`,
    content: memory.content,
    metadata: memory,
  }));
}

function decisionsToItems(decisions: DecisionRecord[]): KnowledgeItem[] {
  return decisions.map((decision) => ({
    kind: "decision",
    id: decision.id,
    title: decision.title,
    subtitle: `${decision.status} · ${decision.saved_path}`,
    content: decision.decision,
    metadata: decision,
  }));
}

function reviewToItems(items: ReviewQueueItem[]): KnowledgeItem[] {
  return items.map((item) => ({
    kind: "review",
    id: item.id,
    title: item.title,
    subtitle: `${item.kind} · ${item.status}`,
    content: item.content,
    metadata: item,
  }));
}

function searchToItems(results: KnowledgeSearchResult[]): KnowledgeItem[] {
  return results.map((result) => ({
    kind: "search",
    id: result.id,
    title: result.title,
    subtitle: `${result.source_type} · ${result.source_ref}`,
    content: result.content,
    metadata: result,
  }));
}

function KnowledgeRow({
  active,
  item,
  onSelect,
}: {
  active: boolean;
  item: KnowledgeItem;
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
          <div className="mt-1 truncate text-xs text-muted-foreground">{item.subtitle}</div>
        </div>
        <Badge variant={item.kind === "review" ? "warning" : "secondary"}>{item.kind}</Badge>
      </div>
      <div className="line-clamp-2 text-xs leading-5 text-muted-foreground">{item.content}</div>
    </button>
  );
}

function DetailPanel({
  approving,
  item,
  onApprove,
}: {
  approving: boolean;
  item: KnowledgeItem | null;
  onApprove: (item: KnowledgeItem) => void;
}) {
  if (!item) {
    return (
      <section className="rounded-md border bg-background p-4">
        <div className="mb-3 flex items-center gap-2">
          <FileText className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Detail</h3>
        </div>
        <p className="text-sm text-muted-foreground">No knowledge selected.</p>
      </section>
    );
  }

  const canApprove = item.kind === "review" && item.metadata.kind === "memory";
  return (
    <section className="rounded-md border bg-background p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
          <h3 className="truncate text-sm font-semibold">{item.title}</h3>
        </div>
        {canApprove && (
          <Button type="button" size="sm" onClick={() => onApprove(item)} disabled={approving}>
            <Check className="h-4 w-4" />
            {approving ? "Approving" : "Approve"}
          </Button>
        )}
      </div>
      <div className="space-y-4 text-sm">
        <p className="whitespace-pre-wrap leading-6">{item.content}</p>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
          <Status label="Type" value={item.kind} />
          <Status label="Source" value={item.subtitle || "-"} />
          {"updated_at" in item.metadata && <Status label="Updated" value={formatTime(item.metadata.updated_at)} />}
        </div>
        {item.kind === "memory" && item.metadata.tags.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {item.metadata.tags.map((tag) => <Badge key={tag} variant="outline">{tag}</Badge>)}
          </div>
        )}
        {item.kind === "decision" && item.metadata.consequences && (
          <div>
            <div className="text-xs uppercase text-muted-foreground">Consequences</div>
            <p className="mt-1 leading-6">{item.metadata.consequences}</p>
          </div>
        )}
      </div>
    </section>
  );
}

export function KnowledgePage({ selectedSection }: { selectedSection?: string | null }) {
  const [section, setSection] = useState<KnowledgeSection>(() => sectionFromRoute(selectedSection));
  const [status, setStatus] = useState<KnowledgeStatusResponse | null>(null);
  const [docs, setDocs] = useState<KnowledgeDocSummary[]>([]);
  const [memories, setMemories] = useState<MemoryCandidate[]>([]);
  const [decisions, setDecisions] = useState<DecisionRecord[]>([]);
  const [reviewItems, setReviewItems] = useState<ReviewQueueItem[]>([]);
  const [searchResults, setSearchResults] = useState<KnowledgeSearchResult[]>([]);
  const [planeSettings, setPlaneSettings] = useState<McpConnectorSettingsResponse | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [approving, setApproving] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSection(sectionFromRoute(selectedSection));
    setSelectedId("");
  }, [selectedSection]);

  const sectionItems = useMemo(() => {
    if (query.trim() && searchResults.length > 0) return searchToItems(searchResults);
    if (section === "docs") return docsToItems(docs);
    if (section === "memories") return memoriesToItems(memories);
    if (section === "decisions") return decisionsToItems(decisions);
    return reviewToItems(reviewItems);
  }, [decisions, docs, memories, query, reviewItems, searchResults, section]);

  const selected = sectionItems.find((item) => item.id === selectedId) ?? sectionItems[0] ?? null;

  async function loadKnowledge() {
    setLoading(true);
    setError(null);
    try {
      const [loadedStatus, loadedDocs, loadedMemories, loadedDecisions, loadedReview] = await Promise.all([
        getKnowledgeStatus(),
        listKnowledgeDocs(),
        listApprovedMemory(),
        listKnowledgeDecisions(),
        listKnowledgeReviewQueue(),
      ]);
      setStatus(loadedStatus);
      setDocs(loadedDocs);
      setMemories(loadedMemories);
      setDecisions(loadedDecisions);
      setReviewItems(loadedReview);
      try {
        setPlaneSettings(await getMcpConnectorSettings("plane"));
      } catch {
        setPlaneSettings(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load knowledge");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadKnowledge();
  }, []);

  async function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) {
      setSearchResults([]);
      return;
    }
    setSearching(true);
    setError(null);
    try {
      const response = await searchKnowledge(trimmed);
      setSearchResults(response.results);
      setSelectedId(response.results[0]?.id ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to search knowledge");
    } finally {
      setSearching(false);
    }
  }

  async function approve(item: KnowledgeItem) {
    if (item.kind !== "review" || item.metadata.kind !== "memory") return;
    setApproving(true);
    setError(null);
    try {
      await approveMemoryCandidate(item.id);
      await loadKnowledge();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to approve review item");
    } finally {
      setApproving(false);
    }
  }

  if (loading) return <LoadingState />;

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <section className="rounded-md border bg-background">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
          <div className="flex items-center gap-2">
            <Brain className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold">Knowledge</h3>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => void loadKnowledge()}>
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
            <ErrorState message={error} onRetry={loadKnowledge} />
          </div>
        )}

        <div className="border-b p-4">
          <form onSubmit={submitSearch} className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                aria-label="Search knowledge"
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  if (!event.target.value.trim()) setSearchResults([]);
                }}
                placeholder="Search docs, memories, decisions"
                className="h-10 w-full rounded-md border border-input bg-background pl-9 pr-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            <Button type="submit" disabled={searching}>
              <Search className="h-4 w-4" />
              {searching ? "Searching" : "Search"}
            </Button>
          </form>
        </div>

        <div className="flex flex-wrap gap-2 border-b px-4 py-3">
          {SECTIONS.map((entry) => (
            <Button
              key={entry.key}
              type="button"
              variant={section === entry.key ? "default" : "outline"}
              size="sm"
              onClick={() => navigateTo("knowledge", entry.key)}
            >
              {entry.label}
            </Button>
          ))}
        </div>

        {sectionItems.length === 0 ? (
          <div className="px-4 py-10 text-center text-sm text-muted-foreground">
            No knowledge items.
          </div>
        ) : (
          <div>
            {sectionItems.map((item) => (
              <KnowledgeRow
                key={`${item.kind}-${item.id}`}
                item={item}
                active={selected?.id === item.id}
                onSelect={() => setSelectedId(item.id)}
              />
            ))}
          </div>
        )}
      </section>

      <aside className="space-y-4">
        <section className="rounded-md border bg-background p-4">
          <div className="mb-3 flex items-center gap-2">
            <Brain className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold">Status</h3>
          </div>
          <div className="space-y-3">
            <Status label="Docs" value={status?.docs_count ?? docs.length} />
            <Status label="Memories" value={status?.memories_count ?? memories.length} />
            <Status label="Decisions" value={status?.decisions_count ?? decisions.length} />
            <Status label="Review" value={status?.review_queue_count ?? reviewItems.length} />
          </div>
        </section>

        <section className="rounded-md border bg-background p-4">
          <div className="mb-3 text-sm font-semibold">Files</div>
          <div className="space-y-3">
            {Object.entries(status?.saved_paths ?? {}).map(([key, value]) => (
              <div key={key} className="min-w-0">
                <div className="text-xs uppercase text-muted-foreground">{key}</div>
                <div className="truncate text-sm font-medium" title={value}>{value}</div>
              </div>
            ))}
          </div>
        </section>

        <DocsSourcePanel settings={planeSettings} />

        <DetailPanel item={selected} approving={approving} onApprove={(item) => void approve(item)} />
      </aside>
    </div>
  );
}
