/**
 * AITeamOS Dashboard - API Catalog (LLM Configuration)
 *
 * Manages LLM API endpoints that tasks can bind to for execution.
 * Agent profiles have been removed — role identity lives in Member.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Cpu, Plus } from "lucide-react";
import {
  Panel,
  DataTable,
  Definition,
  FormField,
  LoadingState,
  ErrorState,
  navigateTo,
  Status,
  type Column,
} from "../../components/shared";
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
  listLlmModels,
  getLlmModelDetail,
  createLlmModel,
  type LlmModelSummary,
  type LlmModelDetail,
} from "../../api/client";

function statusVariant(status: string): "success" | "warning" | "secondary" | "danger" {
  switch (status) {
    case "active": return "success";
    case "draft":
    case "paused":
      return "warning";
    case "retired":
    case "disabled":
      return "danger";
    default:
      return "secondary";
  }
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

function parseList(value: string): string[] {
  return value
    .split(/\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function formatList(values: string[] | null | undefined): string {
  return values?.length ? values.join(", ") : "-";
}

export function ApiPage({ selectedId }: { selectedId: string | null }) {
  const parsedId = selectedId?.startsWith("llm:") ? selectedId.slice("llm:".length) : (selectedId ?? undefined);
  const [llms, setLlms] = useState<LlmModelSummary[]>([]);
  const [llmDetail, setLlmDetail] = useState<LlmModelDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [showCreate, setShowCreate] = useState(false);

  const [llmName, setLlmName] = useState("");
  const [llmProvider, setLlmProvider] = useState("");
  const [llmModelId, setLlmModelId] = useState("");
  const [llmEndpoint, setLlmEndpoint] = useState("chat");
  const [llmContext, setLlmContext] = useState("");
  const [llmOutput, setLlmOutput] = useState("");
  const [llmTools, setLlmTools] = useState(false);
  const [llmJson, setLlmJson] = useState(false);
  const [llmInputCost, setLlmInputCost] = useState("");
  const [llmOutputCost, setLlmOutputCost] = useState("");
  const [llmTags, setLlmTags] = useState("");
  const [llmStatus, setLlmStatus] = useState("active");
  const [llmNotes, setLlmNotes] = useState("");

  const filteredLlms = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return llms.filter((model) => {
      const matchesSearch = !needle
        || model.name.toLowerCase().includes(needle)
        || model.provider.toLowerCase().includes(needle)
        || model.model_id.toLowerCase().includes(needle);
      const matchesStatus = !filterStatus || model.status === filterStatus;
      return matchesSearch && matchesStatus;
    });
  }, [filterStatus, llms, search]);

  const llmColumns: Column<LlmModelSummary>[] = [
    { key: "name", label: "Name" },
    { key: "provider", label: "Provider" },
    { key: "model_id", label: "Model" },
    { key: "endpoint_type", label: "Endpoint" },
    { key: "context_window", label: "Context" },
    { key: "supports_tools", label: "Tools", render: (row) => row.supports_tools ? "Yes" : "No" },
    { key: "status", label: "Status", render: (row) => <Badge variant={statusVariant(row.status)}>{row.status}</Badge> },
  ];

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const models = await listLlmModels({ limit: 100 });
      setLlms(models);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load LLM catalog");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDetail = useCallback(async (id: string | null) => {
    setLlmDetail(null);
    setDetailError(null);
    if (!id) return;
    try {
      setLlmDetail(await getLlmModelDetail(id));
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : "Failed to load LLM detail");
    }
  }, []);

  useEffect(() => { loadList(); }, [loadList]);
  useEffect(() => { loadDetail(parsedId ?? null); }, [parsedId]);

  function resetForm() {
    setLlmName("");
    setLlmProvider("");
    setLlmModelId("");
    setLlmEndpoint("chat");
    setLlmContext("");
    setLlmOutput("");
    setLlmTools(false);
    setLlmJson(false);
    setLlmInputCost("");
    setLlmOutputCost("");
    setLlmTags("");
    setLlmStatus("active");
    setLlmNotes("");
  }

  async function handleCreate() {
    if (!llmName.trim() || !llmProvider.trim() || !llmModelId.trim()) return;
    try {
      const created = await createLlmModel({
        name: llmName.trim(),
        provider: llmProvider.trim(),
        model_id: llmModelId.trim(),
        endpoint_type: llmEndpoint,
        context_window: llmContext ? Number(llmContext) : undefined,
        max_output_tokens: llmOutput ? Number(llmOutput) : undefined,
        supports_tools: llmTools,
        supports_json: llmJson,
        input_cost_per_1m: llmInputCost ? Number(llmInputCost) : undefined,
        output_cost_per_1m: llmOutputCost ? Number(llmOutputCost) : undefined,
        capability_tags: parseList(llmTags),
        status: llmStatus,
        notes: llmNotes.trim() || undefined,
      });
      setShowCreate(false);
      resetForm();
      await loadList();
      navigateTo("agents", `llm:${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create LLM failed");
    }
  }

  const activeLlmCount = llms.filter((model) => model.status === "active").length;

  return (
    <div className="space-y-6">
      <Panel title="API Catalog">
        <div className="mb-4 flex flex-wrap items-center gap-4">
          <Status label="Active LLMs" value={activeLlmCount} tone="ok" />
          <Status label="Visible" value={filteredLlms.length} />
        </div>

        <div className="mb-4 grid gap-3 lg:grid-cols-[minmax(16rem,1fr)_12rem_auto]">
          <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search LLM models" />
          <Select value={filterStatus} onChange={(event) => setFilterStatus(event.target.value)}>
            <option value="">All Status</option>
            <option value="active">Active</option>
            <option value="draft">Draft</option>
            <option value="paused">Paused</option>
            <option value="retired">Retired</option>
          </Select>
          <Button variant="recommended" onClick={() => setShowCreate(!showCreate)}>
            {showCreate ? "Cancel" : <><Plus className="h-4 w-4" />Create LLM</>}
          </Button>
        </div>

        {error && <ErrorState message={error} />}

        {showCreate && (
          <div className="mb-4 grid gap-4 rounded-md border p-4 lg:grid-cols-3">
            <FormField label="LLM Name">
              <Input value={llmName} onChange={(event) => setLlmName(event.target.value)} placeholder="Unique model name" />
            </FormField>
            <FormField label="Provider">
              <Input value={llmProvider} onChange={(event) => setLlmProvider(event.target.value)} placeholder="openai, anthropic, qoder" />
            </FormField>
            <FormField label="Provider Model ID">
              <Input value={llmModelId} onChange={(event) => setLlmModelId(event.target.value)} placeholder="Provider-specific model id" />
            </FormField>
            <FormField label="Endpoint">
              <Select value={llmEndpoint} onChange={(event) => setLlmEndpoint(event.target.value)}>
                <option value="chat">Chat</option>
                <option value="responses">Responses</option>
                <option value="completion">Completion</option>
                <option value="embedding">Embedding</option>
              </Select>
            </FormField>
            <FormField label="Context Window">
              <Input type="number" min="0" value={llmContext} onChange={(event) => setLlmContext(event.target.value)} />
            </FormField>
            <FormField label="Max Output Tokens">
              <Input type="number" min="0" value={llmOutput} onChange={(event) => setLlmOutput(event.target.value)} />
            </FormField>
            <FormField label="Input Cost / 1M">
              <Input type="number" min="0" step="0.000001" value={llmInputCost} onChange={(event) => setLlmInputCost(event.target.value)} />
            </FormField>
            <FormField label="Output Cost / 1M">
              <Input type="number" min="0" step="0.000001" value={llmOutputCost} onChange={(event) => setLlmOutputCost(event.target.value)} />
            </FormField>
            <FormField label="Status">
              <Select value={llmStatus} onChange={(event) => setLlmStatus(event.target.value)}>
                <option value="active">Active</option>
                <option value="draft">Draft</option>
                <option value="paused">Paused</option>
                <option value="retired">Retired</option>
              </Select>
            </FormField>
            <label className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <input type="checkbox" checked={llmTools} onChange={(event) => setLlmTools(event.target.checked)} />
              Supports tools
            </label>
            <label className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <input type="checkbox" checked={llmJson} onChange={(event) => setLlmJson(event.target.checked)} />
              Supports JSON
            </label>
            <FormField label="Capability Tags">
              <Textarea value={llmTags} onChange={(event) => setLlmTags(event.target.value)} placeholder="reasoning, code, fast" />
            </FormField>
            <FormField label="Notes" wide>
              <Textarea value={llmNotes} onChange={(event) => setLlmNotes(event.target.value)} />
            </FormField>
            <div className="col-span-full flex items-center gap-2">
              <Button variant="recommended" disabled={!llmName.trim() || !llmProvider.trim() || !llmModelId.trim()} onClick={handleCreate}>
                <Plus className="h-4 w-4" />Create
              </Button>
            </div>
          </div>
        )}

        {loading ? (
          <LoadingState />
        ) : (
          <DataTable
            data={filteredLlms}
            columns={llmColumns}
            selectedId={parsedId}
            onSelect={(row) => navigateTo("agents", `llm:${row.id}`)}
          />
        )}
      </Panel>

      <Dialog open={Boolean(parsedId)} onOpenChange={(open) => { if (!open) navigateTo("agents"); }}>
        <DialogContent className="block max-h-[calc(100vh-2rem)] w-[calc(100vw-2rem)] max-w-5xl overflow-hidden p-0">
          {detailError && (
            <div className="space-y-4 p-6">
              <DialogHeader>
                <DialogTitle>LLM Details</DialogTitle>
                <DialogDescription>LLM detail could not be loaded.</DialogDescription>
              </DialogHeader>
              <ErrorState message={detailError} />
            </div>
          )}
          {!llmDetail && !detailError && parsedId && (
            <div className="space-y-4 p-6">
              <DialogHeader>
                <DialogTitle>LLM Details</DialogTitle>
                <DialogDescription>Loading LLM model.</DialogDescription>
              </DialogHeader>
              <LoadingState />
            </div>
          )}
          {llmDetail && (
            <div className="flex max-h-[calc(100vh-2rem)] flex-col">
              <div className="border-b px-6 py-5">
                <DialogHeader>
                  <DialogTitle className="flex flex-wrap items-center gap-3 text-xl">
                    <Cpu className="h-5 w-5 text-muted-foreground" />
                    <span>{llmDetail.name}</span>
                    <Badge variant={statusVariant(llmDetail.status)}>{llmDetail.status}</Badge>
                  </DialogTitle>
                  <DialogDescription>{llmDetail.provider} / {llmDetail.model_id}</DialogDescription>
                </DialogHeader>
              </div>
              <div className="overflow-y-auto px-6 py-5">
                <Tabs defaultValue="overview" className="space-y-5">
                  <TabsList className="flex h-auto flex-wrap justify-start">
                    <TabsTrigger value="overview">Overview</TabsTrigger>
                    <TabsTrigger value="costs">Costs</TabsTrigger>
                    <TabsTrigger value="notes">Notes</TabsTrigger>
                  </TabsList>
                  <TabsContent value="overview">
                    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                      <Definition label="Name" value={llmDetail.name} />
                      <Definition label="Provider" value={llmDetail.provider} />
                      <Definition label="Model ID" value={llmDetail.model_id} />
                      <Definition label="Endpoint" value={llmDetail.endpoint_type} />
                      <Definition label="Context Window" value={llmDetail.context_window ?? "-"} />
                      <Definition label="Max Output" value={llmDetail.max_output_tokens ?? "-"} />
                      <Definition label="Tools" value={llmDetail.supports_tools ? "Yes" : "No"} />
                      <Definition label="JSON" value={llmDetail.supports_json ? "Yes" : "No"} />
                      <Definition label="Tags" value={formatList(llmDetail.capability_tags)} />
                      <Definition label="Created" value={formatDate(llmDetail.created_at)} />
                      <Definition label="LLM ID" value={llmDetail.id} />
                    </div>
                  </TabsContent>
                  <TabsContent value="costs">
                    <div className="grid gap-4 sm:grid-cols-2">
                      <Definition label="Input Cost / 1M" value={llmDetail.input_cost_per_1m ?? "-"} />
                      <Definition label="Output Cost / 1M" value={llmDetail.output_cost_per_1m ?? "-"} />
                    </div>
                  </TabsContent>
                  <TabsContent value="notes">
                    <pre className="whitespace-pre-wrap rounded-md bg-muted p-4 font-mono text-sm">{llmDetail.notes || "-"}</pre>
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
