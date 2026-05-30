/**
 * AITeamOS Dashboard - Memory Management Page
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Archive, Brain, FileText, Plus, Trash2 } from "lucide-react";
import { Panel, DataTable, Definition, FormField, LoadingState, ErrorState, navigateTo, Status, type Column } from "../../components/shared";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import { Textarea } from "../../components/ui/textarea";
import { Badge } from "../../components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../../components/ui/tabs";
import {
  listMemories,
  getMemoryDetail,
  createMemory,
  changeMemoryLifecycle,
  deleteMemory,
  type MemorySummary,
  type MemoryDetail,
} from "../../api/client";
import { useToast } from "../../components/ui/use-toast";

function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

function lifecycleVariant(state: string): "success" | "warning" | "secondary" | "danger" {
  switch (state) {
    case "active": return "success";
    case "draft": return "warning";
    case "deprecated": return "danger";
    default: return "secondary";
  }
}

export function MemoryPage({ selectedId }: { selectedId: string | null }) {
  const [memories, setMemories] = useState<MemorySummary[]>([]);
  const [detail, setDetail] = useState<MemoryDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filterLifecycle, setFilterLifecycle] = useState("");

  const [formTier, setFormTier] = useState("facts");
  const [formTitle, setFormTitle] = useState("");
  const [formStatement, setFormStatement] = useState("");
  const [formScopeKind, setFormScopeKind] = useState("global");
  const [formScopeId, setFormScopeId] = useState("");
  const [formSourceKind, setFormSourceKind] = useState("manual_input");

  const columns: Column<MemorySummary>[] = [
    { key: "title", label: "Name" },
    { key: "tier", label: "Tier" },
    { key: "lifecycle_state", label: "Lifecycle", render: (r) => <Badge variant={lifecycleVariant(r.lifecycle_state)}>{r.lifecycle_state}</Badge> },
    { key: "confidence_value", label: "Confidence", render: (r) => r.confidence_value?.toFixed(2) ?? "-" },
    { key: "scope_kind", label: "Scope" },
    { key: "created_at", label: "Created", render: (r) => formatDate(r.created_at) },
  ];

  const filteredMemories = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return memories.filter((memory) => {
      const matchesSearch = !needle
        || memory.title.toLowerCase().includes(needle)
        || memory.id.toLowerCase().includes(needle);
      const matchesLifecycle = !filterLifecycle || memory.lifecycle_state === filterLifecycle;
      return matchesSearch && matchesLifecycle;
    });
  }, [filterLifecycle, memories, search]);

  const activeCount = memories.filter((m) => m.lifecycle_state === "active").length;
  const draftCount = memories.filter((m) => m.lifecycle_state === "draft").length;
  const deprecatedCount = memories.filter((m) => m.lifecycle_state === "deprecated").length;

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setMemories(await listMemories({ limit: 100 }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load memories");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDetail = useCallback(async (id: string) => {
    setDetail(null);
    setDetailError(null);
    try {
      setDetail(await getMemoryDetail(id));
    } catch (err) {
      setDetail(null);
      setDetailError(err instanceof Error ? err.message : "Failed to load memory detail");
    }
  }, []);

  useEffect(() => { loadList(); }, [loadList]);
  useEffect(() => {
    if (selectedId) {
      loadDetail(selectedId);
    } else {
      setDetail(null);
      setDetailError(null);
    }
  }, [selectedId, loadDetail]);

  function handleSelect(row: MemorySummary) {
    navigateTo("memories", row.id);
  }

  async function handleCreate() {
    if (!formTitle.trim() || !formStatement.trim()) return;
    try {
      const created = await createMemory({
        tier: formTier,
        title: formTitle.trim(),
        statement: formStatement.trim(),
        scope_kind: formScopeKind,
        scope_id: formScopeId.trim() || "global",
        source_kind: formSourceKind,
      });
      setShowCreate(false);
      setFormTitle("");
      setFormStatement("");
      await loadList();
      navigateTo("memories", created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    }
  }

  const { toast } = useToast();

  async function handleDelete() {
    if (!detail) return;
    if (!confirm(`Delete memory "${detail.title}"? This cannot be undone.`)) return;
    try {
      await deleteMemory(detail.id);
      setDetail(null);
      navigateTo("memories");
      toast({ title: "Memory deleted" });
      await loadList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  async function handleLifecycle(action: string) {
    if (!detail) return;
    try {
      await changeMemoryLifecycle(detail.id, action, "Changed via dashboard");
      await loadList();
      await loadDetail(detail.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lifecycle change failed");
    }
  }

  return (
    <div className="space-y-6">
      <Panel title="Memories">
        <div className="mb-4 flex flex-wrap items-center gap-4">
          <Status label="Active" value={activeCount} tone={activeCount > 0 ? "ok" : undefined} />
          <Status label="Draft" value={draftCount} tone={draftCount > 0 ? "warn" : undefined} />
          <Status label="Deprecated" value={deprecatedCount} />
          <Status label="Visible" value={filteredMemories.length} />
        </div>

        <div className="mb-4 grid gap-3 lg:grid-cols-[minmax(16rem,1fr)_12rem_auto]">
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search memories" />
          <Select value={filterLifecycle} onChange={(e) => setFilterLifecycle(e.target.value)}>
            <option value="">All Lifecycles</option>
            <option value="draft">Draft</option>
            <option value="active">Active</option>
            <option value="deprecated">Deprecated</option>
            <option value="archived">Archived</option>
          </Select>
          <Button variant="recommended" onClick={() => setShowCreate(!showCreate)}>
            {showCreate ? "Cancel" : <><Plus className="h-4 w-4" />Create Memory</>}
          </Button>
        </div>

        {error && <ErrorState message={error} />}

        {showCreate && (
          <div className="mb-4 grid gap-4 rounded-md border p-4 lg:grid-cols-2">
            <FormField label="Tier">
              <Select value={formTier} onChange={(e) => setFormTier(e.target.value)}>
                <option value="facts">Facts</option>
                <option value="patterns">Patterns</option>
                <option value="principles">Principles</option>
              </Select>
            </FormField>
            <FormField label="Scope Kind">
              <Select value={formScopeKind} onChange={(e) => setFormScopeKind(e.target.value)}>
                <option value="project">Project</option>
                <option value="tech_stack">Tech Stack</option>
                <option value="department">Department</option>
                <option value="global">Global</option>
              </Select>
            </FormField>
            <FormField label="Source Kind">
              <Select value={formSourceKind} onChange={(e) => setFormSourceKind(e.target.value)}>
                <option value="manual_input">Manual Input</option>
                <option value="task_execution">Task Execution</option>
                <option value="review">Review</option>
                <option value="bulk_import">Bulk Import</option>
              </Select>
            </FormField>
            <FormField label="Scope ID">
              <Input value={formScopeId} onChange={(e) => setFormScopeId(e.target.value)} placeholder="global" />
            </FormField>
            <FormField label="Memory Name" wide>
              <Input value={formTitle} onChange={(e) => setFormTitle(e.target.value)} placeholder="Unique memory name" />
            </FormField>
            <FormField label="Statement" wide>
              <Textarea value={formStatement} onChange={(e) => setFormStatement(e.target.value)} placeholder="Memory statement..." />
            </FormField>
            <div className="col-span-full flex items-center gap-2">
              <Button variant="recommended" disabled={!formTitle.trim() || !formStatement.trim()} onClick={handleCreate}>
                <Plus className="h-4 w-4" />Create
              </Button>
            </div>
          </div>
        )}

        {loading ? (
          <LoadingState />
        ) : (
          <DataTable data={filteredMemories} columns={columns} selectedId={selectedId ?? undefined} onSelect={handleSelect} />
        )}
      </Panel>

      <Dialog open={Boolean(selectedId)} onOpenChange={(open) => { if (!open) navigateTo("memories"); }}>
        <DialogContent className="block max-h-[calc(100vh-2rem)] w-[calc(100vw-2rem)] max-w-5xl overflow-hidden p-0">
          {detailError && (
            <div className="space-y-4 p-6">
              <DialogHeader>
                <DialogTitle>Memory Details</DialogTitle>
                <DialogDescription>Memory detail could not be loaded.</DialogDescription>
              </DialogHeader>
              <ErrorState message={detailError} />
            </div>
          )}
          {!detail && !detailError && (
            <div className="space-y-4 p-6">
              <DialogHeader>
                <DialogTitle>Memory Details</DialogTitle>
                <DialogDescription>Loading memory detail.</DialogDescription>
              </DialogHeader>
              <LoadingState />
            </div>
          )}
          {detail && (
            <div className="flex max-h-[calc(100vh-2rem)] flex-col">
              <div className="border-b px-6 py-5">
                <DialogHeader>
                  <DialogTitle className="flex flex-wrap items-center gap-3 text-xl">
                    <Brain className="h-5 w-5 text-muted-foreground" />
                    <span>{detail.title}</span>
                    <Badge variant={lifecycleVariant(detail.lifecycle_state)}>{detail.lifecycle_state}</Badge>
                  </DialogTitle>
                  <DialogDescription>{detail.tier} memory</DialogDescription>
                </DialogHeader>
              </div>
              <div className="overflow-y-auto px-6 py-5">
                <Tabs defaultValue="overview" className="space-y-5">
                  <TabsList className="flex h-auto flex-wrap justify-start">
                    <TabsTrigger value="overview">Overview</TabsTrigger>
                    <TabsTrigger value="statement">Statement</TabsTrigger>
                    <TabsTrigger value="versions">Versions</TabsTrigger>
                    <TabsTrigger value="actions">Actions</TabsTrigger>
                  </TabsList>
                  <TabsContent value="overview">
                    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                      <Definition label="Name" value={detail.title} />
                      <Definition label="Tier" value={detail.tier} />
                      <Definition label="Lifecycle" value={<Badge variant={lifecycleVariant(detail.lifecycle_state)}>{detail.lifecycle_state}</Badge>} />
                      <Definition label="Confidence" value={detail.confidence_value?.toFixed(2)} />
                      <Definition label="Versions" value={detail.versions} />
                      <Definition label="Created" value={formatDate(detail.created_at)} />
                    </div>
                  </TabsContent>
                  <TabsContent value="statement">
                    <pre className="whitespace-pre-wrap rounded-md bg-muted p-4 font-mono text-sm">{detail.statement}</pre>
                  </TabsContent>
                  <TabsContent value="versions">
                    <div className="rounded-md border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
                      Version history endpoint is available for future expansion.
                    </div>
                  </TabsContent>
                  <TabsContent value="actions">
                    <div className="flex flex-wrap items-center gap-2">
                      {detail.lifecycle_state === "active" && (
                        <>
                          <Button variant="outline" onClick={() => handleLifecycle("archive")}><Archive className="h-4 w-4" />Archive</Button>
                          <Button variant="outline" onClick={() => handleLifecycle("deprecate")}>Deprecate</Button>
                        </>
                      )}
                      {detail.lifecycle_state === "draft" && (
                        <Button variant="recommended" onClick={() => handleLifecycle("activate")}><FileText className="h-4 w-4" />Activate</Button>
                      )}
                      <Button variant="outline" onClick={handleDelete} className="border-destructive text-destructive">
                        <Trash2 className="h-4 w-4" />Delete
                      </Button>
                    </div>
                  </TabsContent>
                </Tabs>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
