/**
 * AITeamOS Dashboard - Agent / LLM Runtime Catalog
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Bot, Cpu, Plus } from "lucide-react";
import {
  Panel,
  DataTable,
  Definition,
  FormField,
  LoadingState,
  ErrorState,
  navigateTo,
  Status,
  ComboInput,
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
  listAgentProfiles,
  getAgentProfileDetail,
  createAgentProfile,
  type LlmModelSummary,
  type LlmModelDetail,
  type AgentProfileSummary,
  type AgentProfileDetail,
} from "../../api/client";

type CatalogTab = "agents" | "llms";
type SelectedRuntime = { kind: "agent" | "llm"; id: string } | null;

function parseSelected(value: string | null): SelectedRuntime {
  if (!value) return null;
  if (value.startsWith("agent:")) return { kind: "agent", id: value.slice("agent:".length) };
  if (value.startsWith("llm:")) return { kind: "llm", id: value.slice("llm:".length) };
  return null;
}

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

function parseJsonObject(value: string, fallback: Record<string, unknown>): Record<string, unknown> {
  const trimmed = value.trim();
  if (!trimmed) return fallback;
  const parsed = JSON.parse(trimmed);
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error("JSON fields must be objects");
  }
  return parsed as Record<string, unknown>;
}

function formatJson(value: Record<string, unknown> | null | undefined): string {
  if (!value || Object.keys(value).length === 0) return "{}";
  return JSON.stringify(value, null, 2);
}

function formatList(values: string[] | null | undefined): string {
  return values?.length ? values.join(", ") : "-";
}

export function AgentPage({ selectedId }: { selectedId: string | null }) {
  const selected = parseSelected(selectedId);
  const [activeTab, setActiveTab] = useState<CatalogTab>(selected?.kind === "llm" ? "llms" : "agents");
  const [llms, setLlms] = useState<LlmModelSummary[]>([]);
  const [agents, setAgents] = useState<AgentProfileSummary[]>([]);
  const [llmDetail, setLlmDetail] = useState<LlmModelDetail | null>(null);
  const [agentDetail, setAgentDetail] = useState<AgentProfileDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [showCreateLlm, setShowCreateLlm] = useState(false);
  const [showCreateAgent, setShowCreateAgent] = useState(false);

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

  const [agentName, setAgentName] = useState("");
  const [agentDescription, setAgentDescription] = useState("");
  const [agentRuntimeKind, setAgentRuntimeKind] = useState("llm_agent");
  const [agentDefaultLlm, setAgentDefaultLlm] = useState("");
  const [agentPrompt, setAgentPrompt] = useState("");
  const [agentTools, setAgentTools] = useState("");
  const [agentMemoryPolicy, setAgentMemoryPolicy] = useState("{}");
  const [agentSafetyPolicy, setAgentSafetyPolicy] = useState("{}");
  const [agentStatus, setAgentStatus] = useState("active");

  useEffect(() => {
    if (selected?.kind === "llm") setActiveTab("llms");
    if (selected?.kind === "agent") setActiveTab("agents");
  }, [selected?.kind]);

  const llmNameById = useCallback((id: string | null) => {
    if (!id) return "-";
    const model = llms.find((item) => item.id === id);
    return model ? model.name : id.length > 8 ? `${id.slice(0, 8)}...` : id;
  }, [llms]);

  const selectedLlmId = selected?.kind === "llm" ? selected.id : undefined;
  const selectedAgentId = selected?.kind === "agent" ? selected.id : undefined;

  const llmOptions = useMemo(
    () => llms.map((model) => ({ value: model.name, label: `${model.name} (${model.provider})` })),
    [llms],
  );

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

  const filteredAgents = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return agents.filter((agent) => {
      const matchesSearch = !needle
        || agent.name.toLowerCase().includes(needle)
        || agent.runtime_kind.toLowerCase().includes(needle)
        || agent.description.toLowerCase().includes(needle);
      const matchesStatus = !filterStatus || agent.status === filterStatus;
      return matchesSearch && matchesStatus;
    });
  }, [agents, filterStatus, search]);

  const llmColumns: Column<LlmModelSummary>[] = [
    { key: "name", label: "Name" },
    { key: "provider", label: "Provider" },
    { key: "model_id", label: "Model" },
    { key: "endpoint_type", label: "Endpoint" },
    { key: "context_window", label: "Context" },
    { key: "supports_tools", label: "Tools", render: (row) => row.supports_tools ? "Yes" : "No" },
    { key: "status", label: "Status", render: (row) => <Badge variant={statusVariant(row.status)}>{row.status}</Badge> },
  ];

  const agentColumns: Column<AgentProfileSummary>[] = [
    { key: "name", label: "Name" },
    { key: "runtime_kind", label: "Runtime" },
    { key: "default_llm_model_id", label: "Default LLM", render: (row) => llmNameById(row.default_llm_model_id) },
    { key: "tool_names", label: "Tools", render: (row) => formatList(row.tool_names) },
    { key: "status", label: "Status", render: (row) => <Badge variant={statusVariant(row.status)}>{row.status}</Badge> },
    { key: "created_at", label: "Created", render: (row) => formatDate(row.created_at) },
  ];

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [models, profiles] = await Promise.all([
        listLlmModels({ limit: 100 }),
        listAgentProfiles({ limit: 100 }),
      ]);
      setLlms(models);
      setAgents(profiles);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load runtime catalog");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDetail = useCallback(async (target: SelectedRuntime) => {
    setLlmDetail(null);
    setAgentDetail(null);
    setDetailError(null);
    if (!target) return;
    try {
      if (target.kind === "llm") {
        setLlmDetail(await getLlmModelDetail(target.id));
      } else {
        setAgentDetail(await getAgentProfileDetail(target.id));
      }
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : "Failed to load runtime detail");
    }
  }, []);

  useEffect(() => { loadList(); }, [loadList]);
  useEffect(() => { loadDetail(selected); }, [selected?.kind, selected?.id, loadDetail]);

  function resolveLlmId(value: string): string | undefined {
    const trimmed = value.trim();
    if (!trimmed) return undefined;
    return llms.find((model) => model.name === trimmed || model.id === trimmed)?.id;
  }

  function resetLlmForm() {
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

  function resetAgentForm() {
    setAgentName("");
    setAgentDescription("");
    setAgentRuntimeKind("llm_agent");
    setAgentDefaultLlm("");
    setAgentPrompt("");
    setAgentTools("");
    setAgentMemoryPolicy("{}");
    setAgentSafetyPolicy("{}");
    setAgentStatus("active");
  }

  async function handleCreateLlm() {
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
      setShowCreateLlm(false);
      resetLlmForm();
      await loadList();
      navigateTo("agents", `llm:${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create LLM failed");
    }
  }

  async function handleCreateAgent() {
    if (!agentName.trim()) return;
    const defaultLlmId = resolveLlmId(agentDefaultLlm);
    if (agentDefaultLlm.trim() && !defaultLlmId) {
      setError("Default LLM not found");
      return;
    }
    try {
      const created = await createAgentProfile({
        name: agentName.trim(),
        description: agentDescription.trim() || undefined,
        runtime_kind: agentRuntimeKind.trim() || "llm_agent",
        default_llm_model_id: defaultLlmId,
        system_prompt: agentPrompt,
        tool_names: parseList(agentTools),
        memory_policy: parseJsonObject(agentMemoryPolicy, {}),
        safety_policy: parseJsonObject(agentSafetyPolicy, {}),
        status: agentStatus,
      });
      setShowCreateAgent(false);
      resetAgentForm();
      await loadList();
      navigateTo("agents", `agent:${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create agent failed");
    }
  }

  const activeLlmCount = llms.filter((model) => model.status === "active").length;
  const activeAgentCount = agents.filter((agent) => agent.status === "active").length;

  return (
    <div className="space-y-6">
      <Panel title="Agent / LLM Catalog">
        <div className="mb-4 flex flex-wrap items-center gap-4">
          <Status label="Active Agents" value={activeAgentCount} tone="ok" />
          <Status label="Active LLMs" value={activeLlmCount} tone="ok" />
          <Status label="Visible" value={activeTab === "agents" ? filteredAgents.length : filteredLlms.length} />
        </div>

        <div className="mb-4 grid gap-3 lg:grid-cols-[minmax(16rem,1fr)_12rem_auto_auto]">
          <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search runtime resources" />
          <Select value={filterStatus} onChange={(event) => setFilterStatus(event.target.value)}>
            <option value="">All Status</option>
            <option value="active">Active</option>
            <option value="draft">Draft</option>
            <option value="paused">Paused</option>
            <option value="retired">Retired</option>
          </Select>
          <Button variant="recommended" onClick={() => { setActiveTab("agents"); setShowCreateAgent(!showCreateAgent); }}>
            {showCreateAgent ? "Cancel" : <><Plus className="h-4 w-4" />Create Agent</>}
          </Button>
          <Button variant="outline" onClick={() => { setActiveTab("llms"); setShowCreateLlm(!showCreateLlm); }}>
            {showCreateLlm ? "Cancel" : <><Plus className="h-4 w-4" />Create LLM</>}
          </Button>
        </div>

        {error && <ErrorState message={error} />}

        {showCreateAgent && (
          <div className="mb-4 grid gap-4 rounded-md border p-4 lg:grid-cols-2">
            <FormField label="Agent Name">
              <Input value={agentName} onChange={(event) => setAgentName(event.target.value)} placeholder="Unique agent name" />
            </FormField>
            <FormField label="Runtime Kind">
              <Input value={agentRuntimeKind} onChange={(event) => setAgentRuntimeKind(event.target.value)} placeholder="llm_agent" />
            </FormField>
            <FormField label="Default LLM">
              <ComboInput
                value={agentDefaultLlm}
                onChange={setAgentDefaultLlm}
                options={llmOptions}
                placeholder="Select or type LLM name"
              />
            </FormField>
            <FormField label="Status">
              <Select value={agentStatus} onChange={(event) => setAgentStatus(event.target.value)}>
                <option value="active">Active</option>
                <option value="draft">Draft</option>
                <option value="paused">Paused</option>
                <option value="retired">Retired</option>
              </Select>
            </FormField>
            <FormField label="Description" wide>
              <Textarea value={agentDescription} onChange={(event) => setAgentDescription(event.target.value)} placeholder="Neutral purpose and operating mode" />
            </FormField>
            <FormField label="System Prompt" wide>
              <Textarea value={agentPrompt} onChange={(event) => setAgentPrompt(event.target.value)} placeholder="Instruction template for this agent profile" />
            </FormField>
            <FormField label="Tool Names">
              <Textarea value={agentTools} onChange={(event) => setAgentTools(event.target.value)} placeholder="One per line or comma separated" />
            </FormField>
            <FormField label="Memory Policy">
              <Textarea value={agentMemoryPolicy} onChange={(event) => setAgentMemoryPolicy(event.target.value)} className="font-mono" />
            </FormField>
            <FormField label="Safety Policy" wide>
              <Textarea value={agentSafetyPolicy} onChange={(event) => setAgentSafetyPolicy(event.target.value)} className="font-mono" />
            </FormField>
            <div className="col-span-full flex items-center gap-2">
              <Button variant="recommended" disabled={!agentName.trim()} onClick={handleCreateAgent}>
                <Plus className="h-4 w-4" />Create
              </Button>
            </div>
          </div>
        )}

        {showCreateLlm && (
          <div className="mb-4 grid gap-4 rounded-md border p-4 lg:grid-cols-3">
            <FormField label="LLM Name">
              <Input value={llmName} onChange={(event) => setLlmName(event.target.value)} placeholder="Unique model name" />
            </FormField>
            <FormField label="Provider">
              <Input value={llmProvider} onChange={(event) => setLlmProvider(event.target.value)} placeholder="openai, anthropic, local" />
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
              <Button variant="recommended" disabled={!llmName.trim() || !llmProvider.trim() || !llmModelId.trim()} onClick={handleCreateLlm}>
                <Plus className="h-4 w-4" />Create
              </Button>
            </div>
          </div>
        )}

        <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as CatalogTab)} className="space-y-4">
          <TabsList>
            <TabsTrigger value="agents">Agents</TabsTrigger>
            <TabsTrigger value="llms">LLMs</TabsTrigger>
          </TabsList>
          <TabsContent value="agents">
            {loading ? (
              <LoadingState />
            ) : (
              <DataTable
                data={filteredAgents}
                columns={agentColumns}
                selectedId={selectedAgentId}
                onSelect={(row) => navigateTo("agents", `agent:${row.id}`)}
              />
            )}
          </TabsContent>
          <TabsContent value="llms">
            {loading ? (
              <LoadingState />
            ) : (
              <DataTable
                data={filteredLlms}
                columns={llmColumns}
                selectedId={selectedLlmId}
                onSelect={(row) => navigateTo("agents", `llm:${row.id}`)}
              />
            )}
          </TabsContent>
        </Tabs>
      </Panel>

      <Dialog open={Boolean(selected)} onOpenChange={(open) => { if (!open) navigateTo("agents"); }}>
        <DialogContent className="block max-h-[calc(100vh-2rem)] w-[calc(100vw-2rem)] max-w-5xl overflow-hidden p-0">
          {detailError && (
            <div className="space-y-4 p-6">
              <DialogHeader>
                <DialogTitle>Runtime Details</DialogTitle>
                <DialogDescription>Runtime detail could not be loaded.</DialogDescription>
              </DialogHeader>
              <ErrorState message={detailError} />
            </div>
          )}
          {selected?.kind === "agent" && !agentDetail && !detailError && (
            <div className="space-y-4 p-6">
              <DialogHeader>
                <DialogTitle>Agent Details</DialogTitle>
                <DialogDescription>Loading agent profile.</DialogDescription>
              </DialogHeader>
              <LoadingState />
            </div>
          )}
          {selected?.kind === "llm" && !llmDetail && !detailError && (
            <div className="space-y-4 p-6">
              <DialogHeader>
                <DialogTitle>LLM Details</DialogTitle>
                <DialogDescription>Loading LLM model.</DialogDescription>
              </DialogHeader>
              <LoadingState />
            </div>
          )}
          {selected?.kind === "agent" && agentDetail && (
            <RuntimeAgentDialog agent={agentDetail} llmNameById={llmNameById} />
          )}
          {selected?.kind === "llm" && llmDetail && (
            <RuntimeLlmDialog model={llmDetail} />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function RuntimeAgentDialog({
  agent,
  llmNameById,
}: {
  agent: AgentProfileDetail;
  llmNameById: (id: string | null) => string;
}) {
  return (
    <div className="flex max-h-[calc(100vh-2rem)] flex-col">
      <div className="border-b px-6 py-5">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-3 text-xl">
            <Bot className="h-5 w-5 text-muted-foreground" />
            <span>{agent.name}</span>
            <Badge variant={statusVariant(agent.status)}>{agent.status}</Badge>
          </DialogTitle>
          <DialogDescription>{agent.runtime_kind}</DialogDescription>
        </DialogHeader>
      </div>
      <div className="overflow-y-auto px-6 py-5">
        <Tabs defaultValue="overview" className="space-y-5">
          <TabsList className="flex h-auto flex-wrap justify-start">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="prompt">Prompt</TabsTrigger>
            <TabsTrigger value="policies">Policies</TabsTrigger>
          </TabsList>
          <TabsContent value="overview">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <Definition label="Name" value={agent.name} />
              <Definition label="Runtime" value={agent.runtime_kind} />
              <Definition label="Default LLM" value={llmNameById(agent.default_llm_model_id)} />
              <Definition label="Tools" value={formatList(agent.tool_names)} />
              <Definition label="Created" value={formatDate(agent.created_at)} />
              <Definition label="Agent ID" value={agent.id} />
            </div>
            <div className="mt-5 rounded-md border border-dashed px-4 py-3 text-sm text-muted-foreground">
              {agent.description || "No description"}
            </div>
          </TabsContent>
          <TabsContent value="prompt">
            <pre className="whitespace-pre-wrap rounded-md bg-muted p-4 font-mono text-sm">{agent.system_prompt || "-"}</pre>
          </TabsContent>
          <TabsContent value="policies">
            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <h3 className="mb-2 text-sm font-semibold">Memory Policy</h3>
                <pre className="whitespace-pre-wrap rounded-md bg-muted p-4 font-mono text-sm">{formatJson(agent.memory_policy)}</pre>
              </div>
              <div>
                <h3 className="mb-2 text-sm font-semibold">Safety Policy</h3>
                <pre className="whitespace-pre-wrap rounded-md bg-muted p-4 font-mono text-sm">{formatJson(agent.safety_policy)}</pre>
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

function RuntimeLlmDialog({ model }: { model: LlmModelDetail }) {
  return (
    <div className="flex max-h-[calc(100vh-2rem)] flex-col">
      <div className="border-b px-6 py-5">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-3 text-xl">
            <Cpu className="h-5 w-5 text-muted-foreground" />
            <span>{model.name}</span>
            <Badge variant={statusVariant(model.status)}>{model.status}</Badge>
          </DialogTitle>
          <DialogDescription>{model.provider} / {model.model_id}</DialogDescription>
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
              <Definition label="Name" value={model.name} />
              <Definition label="Provider" value={model.provider} />
              <Definition label="Model ID" value={model.model_id} />
              <Definition label="Endpoint" value={model.endpoint_type} />
              <Definition label="Context Window" value={model.context_window ?? "-"} />
              <Definition label="Max Output" value={model.max_output_tokens ?? "-"} />
              <Definition label="Tools" value={model.supports_tools ? "Yes" : "No"} />
              <Definition label="JSON" value={model.supports_json ? "Yes" : "No"} />
              <Definition label="Tags" value={formatList(model.capability_tags)} />
              <Definition label="Created" value={formatDate(model.created_at)} />
              <Definition label="LLM ID" value={model.id} />
            </div>
          </TabsContent>
          <TabsContent value="costs">
            <div className="grid gap-4 sm:grid-cols-2">
              <Definition label="Input Cost / 1M" value={model.input_cost_per_1m ?? "-"} />
              <Definition label="Output Cost / 1M" value={model.output_cost_per_1m ?? "-"} />
            </div>
          </TabsContent>
          <TabsContent value="notes">
            <pre className="whitespace-pre-wrap rounded-md bg-muted p-4 font-mono text-sm">{model.notes || "-"}</pre>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
