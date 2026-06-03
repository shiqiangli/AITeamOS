import { FormEvent, type Dispatch, type ReactNode, type SetStateAction, useEffect, useMemo, useState } from "react";
import {
  Activity,
  Bot,
  CheckCircle2,
  ClipboardList,
  Database,
  FolderGit2,
  GitBranch,
  KeyRound,
  Plug,
  Plus,
  RefreshCw,
  Save,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
  Wrench,
} from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Select } from "../../components/ui/select";
import { ErrorState, LoadingState, Status, navigateTo } from "../../components/shared";
import { ResizableDetailLayout } from "../../components/resizable-layout";
import { getCapabilities, type CapabilityRecord, type CapabilityRegistryResponse } from "../../api/capabilities";
import {
  getChatRuntime,
  listChatEmployees,
  updateChatRuntime,
  updateChatRuntimeProvider,
  type ChatEmployeeSummary,
  type ChatRuntimeProviderUpdateRequest,
  type ChatRuntimeSettings,
} from "../../api/chat";
import { getKnowledgeStatus, type KnowledgeStatusResponse } from "../../api/knowledge";
import {
  getGraphitiSettings,
  getMemoryStatus,
  updateGraphitiSettings,
  type GraphitiSettingsResponse,
  type GraphitiSettingsUpdateRequest,
  type MemoryStatusResponse,
} from "../../api/memory";
import {
  checkMcpConnectorHealth,
  getMcpConnectorSettings,
  getMcpStatus,
  listMcpConnectors,
  updateMcpConnectorSettings,
  type McpConnector,
  type McpConnectorHealthResponse,
  type McpConnectorSettingsResponse,
  type McpRegistryStatus,
} from "../../api/mcp";
import {
  createCodeRepository,
  deleteCodeRepository,
  getCodeRepositoryStatus,
  listCodeRepositories,
  updateCodeRepository,
  type CodeRepository,
  type CodeRepositoryStatus,
} from "../../api/repositories";
import {
  getTicketBackendSettings,
  getTicketBackendStatus,
  updateTicketBackendSettings,
  type TicketBackendSettings,
  type TicketBackendStatus,
} from "../../api/tickets";
import { cn } from "@/lib/utils";

type SettingsSection = "runtime" | "integrations" | "system";

type RuntimeForm = {
  provider: string;
  deepseekModel: string;
  deepseekThinking: string;
  openaiModel: string;
  fallbackOnError: boolean;
  deepseekApiKey: string;
  openaiApiKey: string;
};

type GraphitiForm = {
  enabled: boolean;
  graphDatabase: string;
  uri: string;
  user: string;
  password: string;
  groupId: string;
  llmProvider: string;
  openaiApiKey: string;
};

type PlaneForm = {
  enabled: boolean;
  baseUrl: string;
  workspaceSlug: string;
  projectId: string;
  apiToken: string;
};

type TicketBackendForm = {
  mode: string;
  localFilePath: string;
};

type RepositoryForm = {
  name: string;
  provider: string;
  location: string;
  defaultBranch: string;
  planeWorkspaceSlug: string;
  planeProjectId: string;
  description: string;
  enabled: boolean;
};

interface SettingsGroup {
  key: SettingsSection;
  label: string;
  icon: typeof Settings;
  subsections: { key: string; label: string }[];
}

const SECTION_GROUPS: SettingsGroup[] = [
  {
    key: "runtime",
    label: "Runtime",
    icon: SlidersHorizontal,
    subsections: [
      { key: "runtimes", label: "LLM Providers" },
      { key: "agent-executors", label: "Agent Executors" },
    ],
  },
  {
    key: "integrations",
    label: "Integrations",
    icon: Plug,
    subsections: [
      { key: "ticket-backend", label: "Ticket Backend" },
      { key: "mcp-connectors", label: "MCP Connectors" },
      { key: "code-repositories", label: "Code Repositories" },
      { key: "knowledge-backend", label: "Knowledge Backend" },
    ],
  },
  {
    key: "system",
    label: "System",
    icon: Activity,
    subsections: [
      { key: "secrets", label: "Secrets" },
      { key: "defaults", label: "Employee Defaults" },
      { key: "health", label: "Health" },
    ],
  },
];

const PROVIDERS = [
  { id: "stub", name: "File stub", kind: "local", description: "Offline deterministic fallback for development." },
  { id: "deepseek", name: "DeepSeek", kind: "llm_api", description: "Chat Completions provider used for low-cost runtime testing." },
  { id: "openai", name: "OpenAI / ChatGPT", kind: "llm_api", description: "Responses API runtime for ChatGPT/OpenAI-backed employees." },
];

const AGENT_EXECUTORS = [
  { id: "codex", name: "Codex", status: "planned", description: "Bounded coding executor for repo edits, tests, and reports." },
  { id: "cursor", name: "Cursor", status: "planned", description: "IDE agent executor when an external API/CLI is available." },
  { id: "qoder", name: "Qoder", status: "planned", description: "External coding-agent runtime candidate." },
  { id: "claude-code", name: "Claude Code", status: "planned", description: "CLI coding executor candidate." },
];

function sectionFromRoute(value?: string | null): SettingsSection {
  // Map old subsection keys to their parent group for backward compatibility
  const legacyMap: Record<string, SettingsSection> = {
    runtimes: "runtime", providers: "runtime", "agent-executors": "runtime",
    "ticket-backend": "integrations", "mcp-connectors": "integrations", "code-repositories": "integrations",
    "knowledge-backend": "integrations", capabilities: "integrations",
    knowledge: "integrations",
    secrets: "system", defaults: "system", health: "system",
  };
  if (value && legacyMap[value]) return legacyMap[value];
  return SECTION_GROUPS.some((g) => g.key === value) ? (value as SettingsSection) : "runtime";
}

function runtimeToForm(runtime: ChatRuntimeSettings): RuntimeForm {
  return {
    provider: runtime.provider,
    deepseekModel: runtime.deepseek_model,
    deepseekThinking: runtime.deepseek_thinking,
    openaiModel: runtime.openai_model,
    fallbackOnError: runtime.fallback_on_error,
    deepseekApiKey: "",
    openaiApiKey: "",
  };
}

function graphitiToForm(settings: GraphitiSettingsResponse): GraphitiForm {
  return {
    enabled: settings.enabled,
    graphDatabase: settings.graph_database || "neo4j",
    uri: settings.uri || "bolt://localhost:7687",
    user: settings.user || "neo4j",
    password: "",
    groupId: settings.group_id || "aiteamos",
    llmProvider: settings.llm_provider || "openai",
    openaiApiKey: "",
  };
}

function planeToForm(settings: McpConnectorSettingsResponse): PlaneForm {
  return {
    enabled: settings.enabled,
    baseUrl: settings.base_url,
    workspaceSlug: settings.workspace_slug,
    projectId: settings.project_id,
    apiToken: "",
  };
}

function ticketBackendToForm(settings: TicketBackendSettings): TicketBackendForm {
  return {
    mode: settings.mode,
    localFilePath: settings.local_file_path,
  };
}

function emptyRepositoryForm(): RepositoryForm {
  return {
    name: "",
    provider: "local",
    location: "",
    defaultBranch: "main",
    planeWorkspaceSlug: "",
    planeProjectId: "",
    description: "",
    enabled: true,
  };
}

function repositoryToForm(repository: CodeRepository): RepositoryForm {
  return {
    name: repository.name,
    provider: repository.provider,
    location: repository.location,
    defaultBranch: repository.default_branch,
    planeWorkspaceSlug: repository.plane_workspace_slug,
    planeProjectId: repository.plane_project_id,
    description: repository.description,
    enabled: repository.enabled,
  };
}

function statusVariant(status: string): "default" | "secondary" | "warning" | "success" | "danger" | "outline" {
  if (status === "ready" || status === "configured" || status === "active" || status === "available" || status === "local") {
    return "success";
  }
  if (status === "planned" || status === "held") return "warning";
  if (status === "missing" || status === "failed" || status === "invalid") return "danger";
  return "secondary";
}

function compactStatus(status?: string | null): string {
  if (!status) return "-";
  if (status === "llm_not_configured") return "llm missing";
  if (status === "not_configured") return "missing";
  if (status === "package_missing") return "pkg missing";
  return status;
}

function ConfigRow({
  active,
  children,
  description,
  kind,
  name,
  status,
}: {
  active?: boolean;
  children?: ReactNode;
  description: string;
  kind?: string;
  name: string;
  status: string;
}) {
  return (
    <div className={cn("rounded-md border px-4 py-3", active ? "border-primary bg-primary/10" : "bg-background")}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-medium">{name}</div>
          <div className="mt-1 text-sm text-muted-foreground">{description}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          {kind && <Badge variant="outline">{kind}</Badge>}
          <Badge variant={statusVariant(status)}>{status}</Badge>
        </div>
      </div>
      {children && <div className="mt-3">{children}</div>}
    </div>
  );
}

function RuntimesSection({
  form,
  runtime,
  saving,
  setForm,
  onPolicySubmit,
  onProviderSubmit,
}: {
  form: RuntimeForm;
  runtime: ChatRuntimeSettings | null;
  saving: boolean;
  setForm: Dispatch<SetStateAction<RuntimeForm>>;
  onPolicySubmit: (event: FormEvent<HTMLFormElement>) => void;
  onProviderSubmit: (providerId: string, payload: ChatRuntimeProviderUpdateRequest) => void;
}) {
  const deepseek = runtime?.providers?.deepseek;
  const openai = runtime?.providers?.openai;
  const stub = runtime?.providers?.stub;

  return (
    <div className="space-y-4">
      <section className="rounded-md border bg-background">
        <div className="border-b px-4 py-3">
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold">Runtime Policy</h3>
          </div>
        </div>
        <form onSubmit={onPolicySubmit} className="grid gap-4 p-4 xl:grid-cols-[minmax(0,1fr)_18rem]">
          <div className="grid gap-4 md:grid-cols-2">
          <label className="block space-y-1">
            <span className="text-xs uppercase text-muted-foreground">Default provider</span>
            <Select
              aria-label="Runtime provider"
              value={form.provider}
              onChange={(event) => setForm((current) => ({ ...current, provider: event.target.value }))}
            >
              <option value="stub">File stub</option>
              <option value="deepseek">DeepSeek</option>
              <option value="openai">OpenAI</option>
            </Select>
          </label>

            <label className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm">
              <span>Fallback on provider error</span>
              <input
                aria-label="Fallback on error"
                type="checkbox"
                checked={form.fallbackOnError}
                onChange={(event) => setForm((current) => ({ ...current, fallbackOnError: event.target.checked }))}
                className="h-4 w-4"
              />
            </label>
          </div>
          <aside className="space-y-3">
            <Status label="Active" value={runtime?.provider ?? "-"} />
            <Button type="submit" disabled={saving} className="w-full">
              <Save className="h-4 w-4" />
              {saving ? "Saving" : "Save policy"}
            </Button>
          </aside>
        </form>
      </section>

      <div className="grid gap-4 xl:grid-cols-3">
        <section className={cn("rounded-md border bg-background p-4", stub?.active && "border-primary bg-primary/10")}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold">File stub</h3>
              <p className="mt-1 text-sm text-muted-foreground">Local deterministic fallback for offline development.</p>
            </div>
            <Badge variant={statusVariant(stub?.active ? "active" : "available")}>{stub?.active ? "active" : "available"}</Badge>
          </div>
          <Button
            type="button"
            variant={stub?.active ? "secondary" : "outline"}
            disabled={saving || stub?.active}
            className="mt-4 w-full"
            onClick={() => onProviderSubmit("stub", { activate: true })}
          >
            {stub?.active ? "Active" : "Set active"}
          </Button>
        </section>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            onProviderSubmit("deepseek", {
              model: form.deepseekModel,
              thinking: form.deepseekThinking,
              api_key: form.deepseekApiKey.trim() || undefined,
            });
          }}
          className={cn("rounded-md border bg-background p-4", deepseek?.active && "border-primary bg-primary/10")}
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold">DeepSeek</h3>
              <p className="mt-1 text-sm text-muted-foreground">Low-cost API provider for development and Clara chat testing.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {deepseek?.active && <Badge variant="success">active</Badge>}
              <Badge variant={statusVariant(deepseek?.status ?? "missing")}>{deepseek?.status ?? "missing"}</Badge>
            </div>
          </div>
          <div className="mt-4 space-y-3">
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">Model</span>
              <input
                aria-label="DeepSeek model"
                value={form.deepseekModel}
                onChange={(event) => setForm((current) => ({ ...current, deepseekModel: event.target.value }))}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">Thinking</span>
              <Select
                aria-label="DeepSeek thinking"
                value={form.deepseekThinking}
                onChange={(event) => setForm((current) => ({ ...current, deepseekThinking: event.target.value }))}
              >
                <option value="disabled">Disabled</option>
                <option value="enabled">Enabled</option>
              </Select>
            </label>
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">API key</span>
              <input
                aria-label="DeepSeek API key"
                type="password"
                value={form.deepseekApiKey}
                onChange={(event) => setForm((current) => ({ ...current, deepseekApiKey: event.target.value }))}
                placeholder={deepseek?.api_key_configured ? "Configured" : "Not configured"}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button type="submit" disabled={saving}>
              <Save className="h-4 w-4" />
              Save DeepSeek
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={saving || deepseek?.active}
              onClick={() => onProviderSubmit("deepseek", { activate: true })}
            >
              {deepseek?.active ? "Active" : "Set active"}
            </Button>
          </div>
        </form>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            onProviderSubmit("openai", {
              model: form.openaiModel,
              api_key: form.openaiApiKey.trim() || undefined,
            });
          }}
          className={cn("rounded-md border bg-background p-4", openai?.active && "border-primary bg-primary/10")}
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold">OpenAI / ChatGPT</h3>
              <p className="mt-1 text-sm text-muted-foreground">OpenAI-backed employee runtime for later ChatGPT integration.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {openai?.active && <Badge variant="success">active</Badge>}
              <Badge variant={statusVariant(openai?.status ?? "missing")}>{openai?.status ?? "missing"}</Badge>
            </div>
          </div>
          <div className="mt-4 space-y-3">
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">Model</span>
              <input
                aria-label="OpenAI model"
                value={form.openaiModel}
                onChange={(event) => setForm((current) => ({ ...current, openaiModel: event.target.value }))}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">API key</span>
              <input
                aria-label="OpenAI API key"
                type="password"
                value={form.openaiApiKey}
                onChange={(event) => setForm((current) => ({ ...current, openaiApiKey: event.target.value }))}
                placeholder={openai?.api_key_configured ? "Configured" : "Not configured"}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button type="submit" disabled={saving}>
              <Save className="h-4 w-4" />
              Save OpenAI
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={saving || openai?.active}
              onClick={() => onProviderSubmit("openai", { activate: true })}
            >
              {openai?.active ? "Active" : "Set active"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function capabilityGroupLabel(kind: string): string {
  if (kind === "local_tool") return "Local Tools";
  if (kind === "mcp_connector") return "MCP Connectors";
  if (kind === "mcp_capability") return "MCP Capabilities";
  if (kind === "agent_executor") return "Agent Executors";
  return kind;
}

function groupedCapabilities(capabilities: CapabilityRecord[]): [string, CapabilityRecord[]][] {
  const order = ["local_tool", "mcp_connector", "mcp_capability", "agent_executor"];
  const groups = new Map<string, CapabilityRecord[]>();
  for (const capability of capabilities) {
    groups.set(capability.kind, [...(groups.get(capability.kind) ?? []), capability]);
  }
  return order
    .filter((kind) => groups.has(kind))
    .map((kind) => [kind, groups.get(kind) ?? []]);
}

function CapabilitiesSection({ registry }: { registry: CapabilityRegistryResponse | null }) {
  const capabilities = registry?.capabilities ?? [];
  const groups = groupedCapabilities(capabilities);
  const modelEntries = [
    ["Knowledge", registry?.model.knowledge ?? "Facts and history that ground reasoning."],
    ["Skill", registry?.model.skill ?? "Employee methods and workflows."],
    ["Tool", registry?.model.tool ?? "Executable deterministic actions."],
    ["MCP", registry?.model.mcp ?? "External tool and resource connector layer."],
    ["Executor", registry?.model.executor ?? "Mature agent runtime used by employees."],
  ];

  return (
    <div className="space-y-4">
      <section className="rounded-md border bg-background">
        <div className="border-b px-4 py-3">
          <div className="flex items-center gap-2">
            <Wrench className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold">Capability Model</h3>
          </div>
        </div>
        <div className="grid gap-3 p-4 md:grid-cols-5">
          {modelEntries.map(([name, description]) => (
            <div key={name} className="rounded-md border px-3 py-3">
              <div className="text-sm font-semibold">{name}</div>
              <div className="mt-1 text-xs leading-5 text-muted-foreground">{description}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-md border bg-background">
        <div className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-4">
          <Status label="Capabilities" value={registry?.status.capability_count ?? capabilities.length} />
          <Status label="Ready" value={registry?.status.ready_count ?? 0} tone={(registry?.status.ready_count ?? 0) > 0 ? "ok" : "warn"} />
          <Status label="Local tools" value={registry?.status.local_tool_count ?? 0} />
          <Status label="MCP capabilities" value={registry?.status.mcp_capability_count ?? 0} />
        </div>
      </section>

      {groups.map(([kind, items]) => (
        <section key={kind} className="rounded-md border bg-background">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
            <h3 className="text-sm font-semibold">{capabilityGroupLabel(kind)}</h3>
            <Badge variant="secondary">{items.length}</Badge>
          </div>
          <div className="divide-y">
            {items.map((capability) => (
              <div key={capability.id} className="grid gap-3 px-4 py-3 text-sm xl:grid-cols-[minmax(0,1fr)_14rem]">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{capability.name}</span>
                    <Badge variant="outline">{capability.domain}</Badge>
                    <Badge variant={statusVariant(capability.status)}>{capability.status}</Badge>
                    {!capability.enabled && capability.kind !== "agent_executor" && <Badge variant="secondary">disabled</Badge>}
                  </div>
                  <div className="mt-1 text-muted-foreground">{capability.description}</div>
                  {capability.boundary && (
                    <div className="mt-2 rounded-md bg-muted px-3 py-2 text-xs leading-5 text-muted-foreground">
                      {capability.boundary}
                    </div>
                  )}
                  <div className="mt-2 flex flex-wrap gap-2">
                    {capability.permissions.slice(0, 5).map((permission) => (
                      <Badge key={permission} variant="outline">{permission}</Badge>
                    ))}
                    {capability.required_settings.slice(0, 4).map((setting) => (
                      <Badge key={setting} variant="secondary">{setting}</Badge>
                    ))}
                  </div>
                </div>
                <aside className="min-w-0 space-y-2 text-xs text-muted-foreground">
                  <div>
                    <div className="uppercase">Source</div>
                    <div className="truncate font-medium text-foreground" title={capability.source}>{capability.source}</div>
                  </div>
                  <div>
                    <div className="uppercase">Owner scope</div>
                    <div className="truncate font-medium text-foreground" title={capability.owner_scope}>{capability.owner_scope || "-"}</div>
                  </div>
                  {capability.deep_link && (
                    <a className="inline-flex text-sm font-medium text-primary hover:underline" href={capability.deep_link}>
                      Open surface
                    </a>
                  )}
                </aside>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function TicketBackendSection({
  form,
  saving,
  settings,
  status,
  setForm,
  onSubmit,
}: {
  form: TicketBackendForm;
  saving: boolean;
  settings: TicketBackendSettings | null;
  status: TicketBackendStatus | null;
  setForm: Dispatch<SetStateAction<TicketBackendForm>>;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const supportedModes = settings?.supported_modes ?? status?.supported_modes ?? [
    {
      id: "local_file",
      label: "Local file",
      status: "ready",
      description: "File-backed Tickets for fast local dogfooding.",
    },
  ];

  return (
    <section className="rounded-md border bg-background">
      <div className="border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <ClipboardList className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Ticket Backend</h3>
        </div>
      </div>
      <form onSubmit={onSubmit} className="grid gap-4 p-4 xl:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">Source of truth</span>
              <Select
                aria-label="Ticket backend mode"
                value={form.mode}
                onChange={(event) => setForm((current) => ({ ...current, mode: event.target.value }))}
              >
                {supportedModes.map((mode) => (
                  <option key={mode.id} value={mode.id} disabled={mode.status !== "ready"}>
                    {mode.label}{mode.status !== "ready" ? ` (${mode.status})` : ""}
                  </option>
                ))}
              </Select>
            </label>
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">Local Ticket file</span>
              <input
                aria-label="Local Ticket file"
                value={form.localFilePath}
                onChange={(event) => setForm((current) => ({ ...current, localFilePath: event.target.value }))}
                placeholder=".aiteamos/tickets/index.json"
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>
          </div>

          <div className="grid gap-3">
            {supportedModes.map((mode) => (
              <ConfigRow
                key={mode.id}
                active={form.mode === mode.id}
                name={mode.label}
                status={mode.status}
                description={mode.description}
              />
            ))}
          </div>

          <Button type="submit" disabled={saving}>
            <Save className="h-4 w-4" />
            {saving ? "Saving" : "Save Ticket backend"}
          </Button>
        </div>

        <aside className="space-y-3">
          <Status label="Mode" value={status?.mode ?? settings?.mode ?? "-"} />
          <Status label="Status" value={compactStatus(status?.status)} tone={status?.status === "ready" ? "ok" : "warn"} />
          <Status label="Tickets" value={status?.ticket_count ?? 0} />
          <div className="rounded-md border bg-card p-3 text-xs leading-5 text-muted-foreground">
            {status?.detail ?? "Local file is the active P0 backend. Plane/Jira are Adapter targets, not separate product models."}
          </div>
        </aside>
      </form>
    </section>
  );
}

function CodeRepositoriesSection({
  form,
  repositories,
  saving,
  selectedId,
  status,
  setForm,
  onDelete,
  onNew,
  onSelect,
  onSubmit,
}: {
  form: RepositoryForm;
  repositories: CodeRepository[];
  saving: boolean;
  selectedId: string;
  status: CodeRepositoryStatus | null;
  setForm: Dispatch<SetStateAction<RepositoryForm>>;
  onDelete: (repoId: string) => void;
  onNew: () => void;
  onSelect: (repository: CodeRepository) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_24rem]">
      <section className="rounded-md border bg-background">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
          <div className="flex items-center gap-2">
            <FolderGit2 className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold">Code Repositories</h3>
          </div>
          <Button type="button" size="sm" variant="outline" onClick={onNew}>
            <Plus className="h-4 w-4" />
            New
          </Button>
        </div>

        {repositories.length === 0 ? (
          <div className="px-4 py-10 text-center text-sm text-muted-foreground">
            No repositories configured. Add the local path or Git URL for a Plane project.
          </div>
        ) : (
          <div className="divide-y">
            {repositories.map((repository) => (
              <button
                key={repository.id}
                type="button"
                onClick={() => onSelect(repository)}
                className={cn(
                  "grid w-full gap-2 px-4 py-3 text-left text-sm transition-colors",
                  selectedId === repository.id ? "bg-primary/10" : "hover:bg-muted/60",
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="font-medium">{repository.name}</div>
                    <div className="mt-1 truncate text-xs text-muted-foreground">{repository.location}</div>
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2">
                    <Badge variant="outline">{repository.provider}</Badge>
                    <Badge variant={statusVariant(repository.status)}>{repository.status}</Badge>
                  </div>
                </div>
                <div className="grid gap-2 text-xs text-muted-foreground sm:grid-cols-3">
                  <span className="truncate">Branch: {repository.current_branch || repository.default_branch || "-"}</span>
                  <span className="truncate">Workspace: {repository.plane_workspace_slug || "-"}</span>
                  <span className="truncate">Project: {repository.plane_project_id || "-"}</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </section>

      <aside className="space-y-4">
        <section className="rounded-md border bg-background p-4">
          <div className="mb-3 flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold">{selectedId ? "Edit Repository" : "Add Repository"}</h3>
          </div>
          <form onSubmit={onSubmit} className="space-y-3">
            <label className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm">
              <span>Enabled</span>
              <input
                aria-label="Repository enabled"
                type="checkbox"
                checked={form.enabled}
                onChange={(event) => setForm((current) => ({ ...current, enabled: event.target.checked }))}
                className="h-4 w-4"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">Name</span>
              <input
                aria-label="Repository name"
                value={form.name}
                onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                placeholder="AITeamOS"
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">Provider</span>
              <Select
                aria-label="Repository provider"
                value={form.provider}
                onChange={(event) => setForm((current) => ({ ...current, provider: event.target.value }))}
              >
                <option value="local">Local path</option>
                <option value="github">GitHub</option>
                <option value="gitea">Gitea</option>
                <option value="gitlab">GitLab</option>
                <option value="generic_git">Generic Git</option>
              </Select>
            </label>
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">URL or local path</span>
              <input
                aria-label="Repository location"
                value={form.location}
                onChange={(event) => setForm((current) => ({ ...current, location: event.target.value }))}
                placeholder="/home/me/project or https://github.com/org/repo.git"
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">Default branch</span>
              <input
                aria-label="Repository default branch"
                value={form.defaultBranch}
                onChange={(event) => setForm((current) => ({ ...current, defaultBranch: event.target.value }))}
                placeholder="main"
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
              <label className="block space-y-1">
                <span className="text-xs uppercase text-muted-foreground">Plane workspace</span>
                <input
                  aria-label="Repository Plane workspace"
                  value={form.planeWorkspaceSlug}
                  onChange={(event) => setForm((current) => ({ ...current, planeWorkspaceSlug: event.target.value }))}
                  placeholder="optional"
                  className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </label>
              <label className="block space-y-1">
                <span className="text-xs uppercase text-muted-foreground">Plane project</span>
                <input
                  aria-label="Repository Plane project"
                  value={form.planeProjectId}
                  onChange={(event) => setForm((current) => ({ ...current, planeProjectId: event.target.value }))}
                  placeholder="optional"
                  className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </label>
            </div>
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">Description</span>
              <textarea
                aria-label="Repository description"
                value={form.description}
                onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
                rows={3}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={saving}>
                <Save className="h-4 w-4" />
                {saving ? "Saving" : selectedId ? "Save repository" : "Add repository"}
              </Button>
              {selectedId && (
                <Button type="button" variant="danger" disabled={saving} onClick={() => onDelete(selectedId)}>
                  <Trash2 className="h-4 w-4" />
                  Delete
                </Button>
              )}
            </div>
          </form>
        </section>

        <section className="rounded-md border bg-background p-4">
          <div className="mb-3 text-sm font-semibold">Repository Status</div>
          <div className="space-y-3">
            <Status label="Repositories" value={status?.repository_count ?? repositories.length} />
            <Status label="Enabled" value={status?.enabled_count ?? 0} />
            <Status label="Ready" value={status?.ready_count ?? 0} />
            <Status label="Remote" value={status?.remote_count ?? 0} />
          </div>
        </section>
      </aside>
    </div>
  );
}

function PlaneConnectorSection({
  form,
  health,
  saving,
  settings,
  setForm,
  onHealth,
  onSubmit,
}: {
  form: PlaneForm;
  health: McpConnectorHealthResponse | null;
  saving: boolean;
  settings: McpConnectorSettingsResponse | null;
  setForm: Dispatch<SetStateAction<PlaneForm>>;
  onHealth: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <section className="rounded-md border bg-background">
      <div className="border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Plug className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Plane Connector</h3>
        </div>
      </div>
      <div className="grid gap-4 p-4 xl:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="space-y-4">
          <form onSubmit={onSubmit} className="space-y-4">
            <label className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm">
              <span>Enabled</span>
              <input
                aria-label="Plane enabled"
                type="checkbox"
                checked={form.enabled}
                onChange={(event) => setForm((current) => ({ ...current, enabled: event.target.checked }))}
                className="h-4 w-4"
              />
            </label>
            <div className="grid gap-4 md:grid-cols-2">
              <label className="block space-y-1 md:col-span-2">
                <span className="text-xs uppercase text-muted-foreground">API base URL</span>
                <input
                  aria-label="Plane API base URL"
                  value={form.baseUrl}
                  onChange={(event) => setForm((current) => ({ ...current, baseUrl: event.target.value }))}
                  placeholder="http://localhost:8082 or https://plane.example.com"
                  className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </label>
              <label className="block space-y-1">
                <span className="text-xs uppercase text-muted-foreground">Workspace slug</span>
                <input
                  aria-label="Plane workspace slug"
                  value={form.workspaceSlug}
                  onChange={(event) => setForm((current) => ({ ...current, workspaceSlug: event.target.value }))}
                  placeholder="my-team"
                  className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </label>
              <label className="block space-y-1">
                <span className="text-xs uppercase text-muted-foreground">Default project id</span>
                <input
                  aria-label="Plane default project id"
                  value={form.projectId}
                  onChange={(event) => setForm((current) => ({ ...current, projectId: event.target.value }))}
                  placeholder="optional"
                  className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </label>
              <label className="block space-y-1 md:col-span-2">
                <span className="text-xs uppercase text-muted-foreground">API token</span>
                <input
                  aria-label="Plane API token"
                  type="password"
                  value={form.apiToken}
                  onChange={(event) => setForm((current) => ({ ...current, apiToken: event.target.value }))}
                  placeholder={settings?.api_token_configured ? "Configured" : "Not configured"}
                  className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </label>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={saving}>
                <Save className="h-4 w-4" />
                {saving ? "Saving" : "Save Plane"}
              </Button>
              <Button type="button" variant="outline" disabled={saving} onClick={onHealth}>
                <RefreshCw className="h-4 w-4" />
                Check
              </Button>
            </div>
          </form>
        </div>

        <aside className="space-y-3">
          <Status label="Configured" value={settings?.configured ? "yes" : "no"} tone={settings?.configured ? "ok" : "warn"} />
          <Status label="Token" value={settings?.api_token_configured ? "set" : "missing"} tone={settings?.api_token_configured ? "ok" : "warn"} />
          <Status label="Health" value={compactStatus(health?.status ?? settings?.connector.status)} tone={health?.status === "ready" ? "ok" : "warn"} />
          <Status label="Transport" value={settings?.connector.transport ?? "-"} />
          {health?.detail && (
            <div className="rounded-md border bg-card p-3 text-xs leading-5 text-muted-foreground">{health.detail}</div>
          )}
        </aside>
      </div>
    </section>
  );
}

function KnowledgeBackendSection({
  form,
  graphiti,
  saving,
  setForm,
  onSubmit,
}: {
  form: GraphitiForm;
  graphiti: GraphitiSettingsResponse | null;
  saving: boolean;
  setForm: Dispatch<SetStateAction<GraphitiForm>>;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <section className="rounded-md border bg-background">
      <div className="border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Knowledge Backend</h3>
        </div>
      </div>
      <form onSubmit={onSubmit} className="grid gap-4 p-4 xl:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="space-y-4">
          <label className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm">
            <span>Graphiti enabled</span>
            <input
              aria-label="Graphiti enabled"
              type="checkbox"
              checked={form.enabled}
              onChange={(event) => setForm((current) => ({ ...current, enabled: event.target.checked }))}
              className="h-4 w-4"
            />
          </label>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">Graph database</span>
              <Select
                aria-label="Graph database"
                value={form.graphDatabase}
                onChange={(event) => setForm((current) => ({ ...current, graphDatabase: event.target.value }))}
              >
                <option value="neo4j">Neo4j</option>
              </Select>
            </label>
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">Group id</span>
              <input
                aria-label="Graphiti group id"
                value={form.groupId}
                onChange={(event) => setForm((current) => ({ ...current, groupId: event.target.value }))}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>
            <label className="block space-y-1 md:col-span-2">
              <span className="text-xs uppercase text-muted-foreground">Neo4j URI</span>
              <input
                aria-label="Neo4j URI"
                value={form.uri}
                onChange={(event) => setForm((current) => ({ ...current, uri: event.target.value }))}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">Neo4j user</span>
              <input
                aria-label="Neo4j user"
                value={form.user}
                onChange={(event) => setForm((current) => ({ ...current, user: event.target.value }))}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">Neo4j password</span>
              <input
                aria-label="Neo4j password"
                type="password"
                value={form.password}
                onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))}
                placeholder={graphiti?.password_configured ? "Configured" : "Not configured"}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">Graphiti LLM</span>
              <Select
                aria-label="Graphiti LLM provider"
                value={form.llmProvider}
                onChange={(event) => setForm((current) => ({ ...current, llmProvider: event.target.value }))}
              >
                <option value="openai">OpenAI</option>
              </Select>
            </label>
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">OpenAI API key</span>
              <input
                aria-label="Graphiti OpenAI API key"
                type="password"
                value={form.openaiApiKey}
                onChange={(event) => setForm((current) => ({ ...current, openaiApiKey: event.target.value }))}
                placeholder={graphiti?.openai_api_key_configured ? "Configured" : "Not configured"}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>
          </div>

          <Button type="submit" disabled={saving}>
            <Save className="h-4 w-4" />
            {saving ? "Saving" : "Save backend"}
          </Button>
        </div>

        <aside className="space-y-3">
          <Status label="Graphiti" value={compactStatus(graphiti?.backend.status)} tone={graphiti?.backend.status === "ready" ? "ok" : "warn"} />
          <Status label="Graph DB" value={graphiti?.backend.graph_configured ? "set" : "missing"} tone={graphiti?.backend.graph_configured ? "ok" : "warn"} />
          <Status label="LLM key" value={graphiti?.backend.llm_configured ? "set" : "missing"} tone={graphiti?.backend.llm_configured ? "ok" : "warn"} />
          <Status label="Runtime key" value={graphiti?.uses_runtime_openai_key ? "used" : "optional"} />
        </aside>
      </form>
    </section>
  );
}

export function SettingsPage({ selectedSection }: { selectedSection?: string | null }) {
  const [section, setSection] = useState<SettingsSection>(() => sectionFromRoute(selectedSection));
  const [runtime, setRuntime] = useState<ChatRuntimeSettings | null>(null);
  const [form, setForm] = useState<RuntimeForm>({
    provider: "stub",
    deepseekModel: "deepseek-v4-flash",
    deepseekThinking: "disabled",
    openaiModel: "gpt-5-nano",
    fallbackOnError: true,
    deepseekApiKey: "",
    openaiApiKey: "",
  });
  const [graphitiForm, setGraphitiForm] = useState<GraphitiForm>({
    enabled: false,
    graphDatabase: "neo4j",
    uri: "bolt://localhost:7687",
    user: "neo4j",
    password: "",
    groupId: "aiteamos",
    llmProvider: "openai",
    openaiApiKey: "",
  });
  const [planeForm, setPlaneForm] = useState<PlaneForm>({
    enabled: false,
    baseUrl: "",
    workspaceSlug: "",
    projectId: "",
    apiToken: "",
  });
  const [ticketBackendForm, setTicketBackendForm] = useState<TicketBackendForm>({
    mode: "local_file",
    localFilePath: ".aiteamos/tickets/index.json",
  });
  const [repositoryForm, setRepositoryForm] = useState<RepositoryForm>(emptyRepositoryForm);
  const [repositories, setRepositories] = useState<CodeRepository[]>([]);
  const [repositoryStatus, setRepositoryStatus] = useState<CodeRepositoryStatus | null>(null);
  const [selectedRepositoryId, setSelectedRepositoryId] = useState("");
  const [capabilityRegistry, setCapabilityRegistry] = useState<CapabilityRegistryResponse | null>(null);
  const [employees, setEmployees] = useState<ChatEmployeeSummary[]>([]);
  const [knowledge, setKnowledge] = useState<KnowledgeStatusResponse | null>(null);
  const [memory, setMemory] = useState<MemoryStatusResponse | null>(null);
  const [graphiti, setGraphiti] = useState<GraphitiSettingsResponse | null>(null);
  const [ticketBackend, setTicketBackend] = useState<TicketBackendSettings | null>(null);
  const [ticketBackendStatus, setTicketBackendStatus] = useState<TicketBackendStatus | null>(null);
  const [mcpConnectors, setMcpConnectors] = useState<McpConnector[]>([]);
  const [planeSettings, setPlaneSettings] = useState<McpConnectorSettingsResponse | null>(null);
  const [planeHealth, setPlaneHealth] = useState<McpConnectorHealthResponse | null>(null);
  const [mcpStatus, setMcpStatus] = useState<McpRegistryStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSection(sectionFromRoute(selectedSection));
  }, [selectedSection]);

  const activeGroup = useMemo(
    () => SECTION_GROUPS.find((g) => g.key === section) ?? SECTION_GROUPS[0]!,
    [section],
  );

  async function loadSettings() {
    setLoading(true);
    setError(null);
    try {
      const [
        loadedRuntime,
        loadedEmployees,
        loadedKnowledge,
        loadedMemory,
        loadedGraphiti,
        loadedCapabilityRegistry,
        loadedTicketBackend,
        loadedTicketBackendStatus,
        loadedRepositories,
        loadedRepositoryStatus,
        loadedMcpConnectors,
        loadedPlaneSettings,
        loadedMcpStatus,
      ] = await Promise.all([
        getChatRuntime(),
        listChatEmployees(),
        getKnowledgeStatus(),
        getMemoryStatus(),
        getGraphitiSettings(),
        getCapabilities(),
        getTicketBackendSettings(),
        getTicketBackendStatus(),
        listCodeRepositories(),
        getCodeRepositoryStatus(),
        listMcpConnectors(),
        getMcpConnectorSettings("plane"),
        getMcpStatus(),
      ]);
      setRuntime(loadedRuntime);
      setForm(runtimeToForm(loadedRuntime));
      setEmployees(loadedEmployees);
      setKnowledge(loadedKnowledge);
      setMemory(loadedMemory);
      setGraphiti(loadedGraphiti);
      setGraphitiForm(graphitiToForm(loadedGraphiti));
      setCapabilityRegistry(loadedCapabilityRegistry);
      setTicketBackend(loadedTicketBackend);
      setTicketBackendStatus(loadedTicketBackendStatus);
      setTicketBackendForm(ticketBackendToForm(loadedTicketBackend));
      setRepositories(loadedRepositories);
      setRepositoryStatus(loadedRepositoryStatus);
      const selectedRepository = loadedRepositories.find((repo) => repo.id === selectedRepositoryId) ?? null;
      setSelectedRepositoryId(selectedRepository?.id ?? "");
      setRepositoryForm(selectedRepository ? repositoryToForm(selectedRepository) : emptyRepositoryForm());
      setMcpConnectors(loadedMcpConnectors);
      setPlaneSettings(loadedPlaneSettings);
      setPlaneForm(planeToForm(loadedPlaneSettings));
      setMcpStatus(loadedMcpStatus);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadSettings();
  }, []);

  async function handleRuntimePolicySubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateChatRuntime({
        provider: form.provider,
        deepseek_model: form.deepseekModel,
        deepseek_thinking: form.deepseekThinking,
        openai_model: form.openaiModel,
        fallback_on_error: form.fallbackOnError,
        deepseek_api_key: form.deepseekApiKey.trim() || undefined,
        openai_api_key: form.openaiApiKey.trim() || undefined,
      });
      setRuntime(updated);
      setForm(runtimeToForm(updated));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save runtime settings");
    } finally {
      setSaving(false);
    }
  }

  async function handleRuntimeProviderSubmit(providerId: string, payload: ChatRuntimeProviderUpdateRequest) {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateChatRuntimeProvider(providerId, payload);
      setRuntime(updated);
      setForm(runtimeToForm(updated));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save provider settings");
    } finally {
      setSaving(false);
    }
  }

  async function handleGraphitiSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setError(null);
    const payload: GraphitiSettingsUpdateRequest = {
      enabled: graphitiForm.enabled,
      graph_database: graphitiForm.graphDatabase,
      uri: graphitiForm.uri,
      user: graphitiForm.user,
      group_id: graphitiForm.groupId,
      llm_provider: graphitiForm.llmProvider,
      password: graphitiForm.password.trim() || undefined,
      openai_api_key: graphitiForm.openaiApiKey.trim() || undefined,
    };
    try {
      const updated = await updateGraphitiSettings(payload);
      const updatedMemory = await getMemoryStatus();
      setGraphiti(updated);
      setGraphitiForm(graphitiToForm(updated));
      setMemory(updatedMemory);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save Knowledge backend settings");
    } finally {
      setSaving(false);
    }
  }

  async function handleTicketBackendSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateTicketBackendSettings({
        mode: ticketBackendForm.mode,
        local_file_path: ticketBackendForm.localFilePath,
      });
      const updatedStatus = await getTicketBackendStatus();
      setTicketBackend(updated);
      setTicketBackendForm(ticketBackendToForm(updated));
      setTicketBackendStatus(updatedStatus);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save Ticket backend settings");
    } finally {
      setSaving(false);
    }
  }

  async function handlePlaneSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateMcpConnectorSettings("plane", {
        enabled: planeForm.enabled,
        base_url: planeForm.baseUrl,
        email: "",
        workspace_slug: planeForm.workspaceSlug,
        project_id: planeForm.projectId,
        api_token: planeForm.apiToken.trim() || undefined,
      });
      const [updatedConnectors, updatedStatus] = await Promise.all([
        listMcpConnectors(),
        getMcpStatus(),
      ]);
      setPlaneSettings(updated);
      setPlaneForm(planeToForm(updated));
      setMcpConnectors(updatedConnectors);
      setMcpStatus(updatedStatus);
      setPlaneHealth(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save Plane connector");
    } finally {
      setSaving(false);
    }
  }

  async function handlePlaneHealth() {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      const health = await checkMcpConnectorHealth("plane");
      setPlaneHealth(health);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to check Plane connector");
    } finally {
      setSaving(false);
    }
  }

  async function reloadRepositories(nextSelectedId = selectedRepositoryId) {
    const [loadedRepositories, loadedStatus] = await Promise.all([
      listCodeRepositories(),
      getCodeRepositoryStatus(),
    ]);
    setRepositories(loadedRepositories);
    setRepositoryStatus(loadedStatus);
    const selected = loadedRepositories.find((repository) => repository.id === nextSelectedId) ?? null;
    setSelectedRepositoryId(selected?.id ?? "");
    setRepositoryForm(selected ? repositoryToForm(selected) : emptyRepositoryForm());
  }

  function repositoryPayload() {
    return {
      name: repositoryForm.name,
      provider: repositoryForm.provider,
      location: repositoryForm.location,
      default_branch: repositoryForm.defaultBranch,
      plane_workspace_slug: repositoryForm.planeWorkspaceSlug,
      plane_project_id: repositoryForm.planeProjectId,
      description: repositoryForm.description,
      enabled: repositoryForm.enabled,
    };
  }

  async function handleRepositorySubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      const updated = selectedRepositoryId
        ? await updateCodeRepository(selectedRepositoryId, repositoryPayload())
        : await createCodeRepository(repositoryPayload());
      await reloadRepositories(updated.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save code repository");
    } finally {
      setSaving(false);
    }
  }

  async function handleRepositoryDelete(repoId: string) {
    if (saving) return;
    if (!window.confirm("Delete this repository mapping?")) return;
    setSaving(true);
    setError(null);
    try {
      await deleteCodeRepository(repoId);
      await reloadRepositories("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete code repository");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <LoadingState />;
  const ActiveIcon = activeGroup.icon;

  return (
    <ResizableDetailLayout
      id="aiteamos-settings-layout"
      main={(
        <section className="space-y-4">
        {/* Group header with refresh */}
        <div className="rounded-md border bg-background">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
            <div className="flex items-center gap-2">
              <ActiveIcon className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold">{activeGroup.label}</h3>
            </div>
            <Button type="button" variant="outline" size="sm" onClick={() => void loadSettings()}>
              <RefreshCw className="h-4 w-4" />
              Refresh
            </Button>
          </div>

          {/* Grouped tab navigation */}
          <div className="flex flex-wrap gap-2 border-b px-4 py-3">
            {SECTION_GROUPS.map((group) => {
              const GIcon = group.icon;
              return (
                <Button
                  key={group.key}
                  type="button"
                  variant={section === group.key ? "default" : "outline"}
                  size="sm"
                  onClick={() => navigateTo("settings", group.key)}
                >
                  <GIcon className="h-3.5 w-3.5" />
                  {group.label}
                </Button>
              );
            })}
          </div>

          {error && (
            <div className="border-b p-4">
              <ErrorState message={error} onRetry={loadSettings} />
            </div>
          )}
        </div>

        {/* ─── Runtime Group ─── */}
        {section === "runtime" && (
          <>
            <RuntimesSection
              form={form}
              runtime={runtime}
              saving={saving}
              setForm={setForm}
              onPolicySubmit={handleRuntimePolicySubmit}
              onProviderSubmit={(providerId, payload) => void handleRuntimeProviderSubmit(providerId, payload)}
            />
            <section className="rounded-md border bg-background">
              <div className="border-b px-4 py-3">
                <div className="flex items-center gap-2">
                  <Bot className="h-4 w-4 text-muted-foreground" />
                  <h3 className="text-sm font-semibold">Agent Executors</h3>
                </div>
              </div>
              <div className="grid gap-3 p-4">
                {AGENT_EXECUTORS.map((executor) => (
                  <ConfigRow
                    key={executor.id}
                    name={executor.name}
                    status={executor.status}
                    description={executor.description}
                  />
                ))}
              </div>
            </section>
          </>
        )}

        {/* ─── Integrations Group ─── */}
        {section === "integrations" && (
          <>
            <TicketBackendSection
              form={ticketBackendForm}
              saving={saving}
              settings={ticketBackend}
              status={ticketBackendStatus}
              setForm={setTicketBackendForm}
              onSubmit={(event) => void handleTicketBackendSubmit(event)}
            />
            <div className="grid gap-3">
              {mcpConnectors.map((connector) => (
                <ConfigRow
                  key={connector.id}
                  name={connector.name}
                  kind={connector.transport}
                  status={connector.enabled && connector.configured ? "ready" : connector.status}
                  description={connector.description}
                >
                  <div className="flex flex-wrap gap-2">
                    {connector.capabilities.slice(0, 4).map((capability) => (
                      <Badge key={capability} variant="outline">{capability}</Badge>
                    ))}
                    {connector.capabilities.length > 4 && (
                      <Badge variant="secondary">+{connector.capabilities.length - 4}</Badge>
                    )}
                  </div>
                </ConfigRow>
              ))}
              <PlaneConnectorSection
                form={planeForm}
                health={planeHealth}
                saving={saving}
                settings={planeSettings}
                setForm={setPlaneForm}
                onHealth={() => void handlePlaneHealth()}
                onSubmit={(event) => void handlePlaneSubmit(event)}
              />
            </div>
            <CodeRepositoriesSection
              form={repositoryForm}
              repositories={repositories}
              saving={saving}
              selectedId={selectedRepositoryId}
              status={repositoryStatus}
              setForm={setRepositoryForm}
              onDelete={(repoId) => void handleRepositoryDelete(repoId)}
              onNew={() => {
                setSelectedRepositoryId("");
                setRepositoryForm(emptyRepositoryForm());
              }}
              onSelect={(repository) => {
                setSelectedRepositoryId(repository.id);
                setRepositoryForm(repositoryToForm(repository));
              }}
              onSubmit={(event) => void handleRepositorySubmit(event)}
            />
            <KnowledgeBackendSection
              form={graphitiForm}
              graphiti={graphiti}
              saving={saving}
              setForm={setGraphitiForm}
              onSubmit={handleGraphitiSubmit}
            />
          </>
        )}

        {/* ─── System Group ─── */}
        {section === "system" && (
          <div className="space-y-4">
            {/* Secrets */}
            <section className="rounded-md border bg-background">
              <div className="border-b px-4 py-3">
                <div className="flex items-center gap-2">
                  <KeyRound className="h-4 w-4 text-muted-foreground" />
                  <h3 className="text-sm font-semibold">Secrets</h3>
                </div>
              </div>
              <div className="grid gap-3 p-4">
                <ConfigRow
                  name="DeepSeek API key"
                  status={runtime?.api_keys_configured.deepseek ? "configured" : "missing"}
                  description="Stored in the local ignored secrets file through the Runtime form."
                />
                <ConfigRow
                  name="OpenAI API key"
                  status={runtime?.api_keys_configured.openai ? "configured" : "missing"}
                  description="Stored in the local ignored secrets file through the Runtime form."
                />
                <ConfigRow
                  name="Graphiti Neo4j password"
                  status={graphiti?.password_configured ? "configured" : "missing"}
                  description="Stored in the local ignored secrets file through the Knowledge Backend form."
                />
                <ConfigRow
                  name="Graphiti OpenAI API key"
                  status={graphiti?.openai_api_key_configured ? "configured" : "missing"}
                  description={graphiti?.uses_runtime_openai_key ? "Using the Runtime OpenAI key." : "Optional dedicated key for Graphiti ingestion."}
                />
                <ConfigRow
                  name="Plane API token"
                  status={planeSettings?.api_token_configured ? "configured" : "missing"}
                  description="Stored in the local ignored secrets file through the MCP Connectors form."
                />
              </div>
            </section>

            {/* Employee Defaults */}
            <section className="rounded-md border bg-background">
              <div className="border-b px-4 py-3">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4 text-muted-foreground" />
                  <h3 className="text-sm font-semibold">Employee Defaults</h3>
                </div>
              </div>
              <div>
                {employees.length === 0 ? (
                  <p className="px-4 py-6 text-center text-sm text-muted-foreground">No employees configured.</p>
                ) : (
                  employees.map((employee) => (
                    <div key={employee.id} className="grid gap-2 border-b px-4 py-3 text-sm last:border-b-0 md:grid-cols-[minmax(0,1fr)_12rem_10rem]">
                      <div>
                        <div className="font-medium">{employee.display_name}</div>
                        <div className="text-muted-foreground">{employee.role}</div>
                      </div>
                      <div>
                        <div className="text-xs uppercase text-muted-foreground">Runtime mode</div>
                        <div className="font-medium">{employee.runtime_mode}</div>
                      </div>
                      <div>
                        <div className="text-xs uppercase text-muted-foreground">Thread</div>
                        <div className="truncate font-medium" title={employee.default_thread_id}>{employee.default_thread_id}</div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </section>

            {/* Health */}
            <section className="rounded-md border bg-background">
              <div className="border-b px-4 py-3">
                <div className="flex items-center gap-2">
                  <Activity className="h-4 w-4 text-muted-foreground" />
                  <h3 className="text-sm font-semibold">System Health</h3>
                </div>
              </div>
              <div className="grid gap-3 p-4 md:grid-cols-2">
                <Status label="Runtime" value={runtime?.provider ?? "-"} tone={runtime?.provider === "stub" ? "warn" : "ok"} />
                <Status label="Employees" value={employees.length} />
                <Status label="Knowledge docs" value={knowledge?.docs_count ?? 0} />
                <Status label="Review items" value={knowledge?.review_queue_count ?? 0} />
                <Status label="Capabilities" value={capabilityRegistry?.status.capability_count ?? 0} />
                <Status label="Capability ready" value={capabilityRegistry?.status.ready_count ?? 0} tone={(capabilityRegistry?.status.ready_count ?? 0) > 0 ? "ok" : "warn"} />
                <Status label="Ticket backend" value={compactStatus(ticketBackendStatus?.status)} tone={ticketBackendStatus?.status === "ready" ? "ok" : "warn"} />
                <Status label="Tickets" value={ticketBackendStatus?.ticket_count ?? 0} />
                <Status label="MCP ready" value={mcpStatus?.ready_count ?? 0} tone={(mcpStatus?.ready_count ?? 0) > 0 ? "ok" : "warn"} />
                <Status label="Code repositories" value={repositoryStatus?.repository_count ?? repositories.length} />
                <Status label="Repos ready" value={repositoryStatus?.ready_count ?? 0} tone={(repositoryStatus?.ready_count ?? 0) > 0 ? "ok" : "warn"} />
                <Status label="Approved memories" value={memory?.approved_count ?? 0} />
                <section className="rounded-md border bg-background p-4 md:col-span-2">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h3 className="text-sm font-semibold">Graphiti Memory Backend</h3>
                      <p className="mt-1 text-sm text-muted-foreground">
                        {graphiti?.backend.detail ?? memory?.backend.detail ?? "Memory backend status is unavailable."}
                      </p>
                    </div>
                    <Badge variant={statusVariant(graphiti?.backend.status ?? memory?.backend.status ?? "missing")}>
                      {graphiti?.backend.status ?? memory?.backend.status ?? "-"}
                    </Badge>
                  </div>
                  <div className="mt-4 grid gap-3 md:grid-cols-4">
                    <Status
                      label="Package"
                      value={(graphiti?.backend.package_installed ?? memory?.backend.package_installed) ? "installed" : "missing"}
                      tone={(graphiti?.backend.package_installed ?? memory?.backend.package_installed) ? "ok" : "warn"}
                    />
                    <Status
                      label="Enabled"
                      value={(graphiti?.backend.enabled ?? memory?.backend.enabled) ? "yes" : "no"}
                      tone={(graphiti?.backend.enabled ?? memory?.backend.enabled) ? "ok" : "warn"}
                    />
                    <Status
                      label="Neo4j config"
                      value={(graphiti?.backend.graph_configured ?? memory?.backend.graph_configured) ? "set" : "missing"}
                      tone={(graphiti?.backend.graph_configured ?? memory?.backend.graph_configured) ? "ok" : "warn"}
                    />
                    <Status
                      label="LLM key"
                      value={(graphiti?.backend.llm_configured ?? memory?.backend.llm_configured) ? "set" : "missing"}
                      tone={(graphiti?.backend.llm_configured ?? memory?.backend.llm_configured) ? "ok" : "warn"}
                    />
                  </div>
                </section>
              </div>
            </section>
          </div>
        )}
        </section>
      )}

      detail={(
        <aside className="space-y-4">
        <section className="rounded-md border bg-background p-4">
          <div className="mb-3 flex items-center gap-2">
            <Settings className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold">Overview</h3>
          </div>
          <div className="space-y-3">
            <Status label="Provider" value={runtime?.provider ?? "-"} />
            <Status label="Employees" value={employees.length} />
            <Status label="Docs" value={knowledge?.docs_count ?? 0} />
            <Status label="Tickets" value={ticketBackendStatus?.ticket_count ?? 0} />
            <Status label="Capabilities" value={capabilityRegistry?.status.capability_count ?? 0} />
            <Status label="Repos" value={repositoryStatus?.repository_count ?? repositories.length} />
            <Status label="MCP" value={mcpStatus?.connector_count ?? 0} />
            <Status label="Graphiti" value={compactStatus(graphiti?.backend.status ?? memory?.backend.status)} />
          </div>
        </section>

        <section className="rounded-md border bg-background p-4">
          <div className="mb-3 flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold">Files</h3>
          </div>
          <div className="space-y-3">
            {Object.entries(runtime?.saved_paths ?? {}).map(([key, value]) => (
              <div key={key} className="min-w-0">
                <div className="text-xs uppercase text-muted-foreground">{key}</div>
                <div className="truncate text-sm font-medium" title={value}>{value}</div>
              </div>
            ))}
            {Object.entries(mcpStatus?.saved_paths ?? {}).map(([key, value]) => (
              <div key={`mcp-${key}`} className="min-w-0">
                <div className="text-xs uppercase text-muted-foreground">mcp {key}</div>
                <div className="truncate text-sm font-medium" title={value}>{value}</div>
              </div>
            ))}
            {Object.entries(capabilityRegistry?.status.saved_paths ?? {}).map(([key, value]) => (
              <div key={`capability-${key}`} className="min-w-0">
                <div className="text-xs uppercase text-muted-foreground">capability {key}</div>
                <div className="truncate text-sm font-medium" title={value}>{value}</div>
              </div>
            ))}
            {Object.entries(ticketBackendStatus?.saved_paths ?? ticketBackend?.saved_paths ?? {}).map(([key, value]) => (
              <div key={`ticket-${key}`} className="min-w-0">
                <div className="text-xs uppercase text-muted-foreground">ticket {key}</div>
                <div className="truncate text-sm font-medium" title={value}>{value}</div>
              </div>
            ))}
            {Object.entries(repositoryStatus?.saved_paths ?? {}).map(([key, value]) => (
              <div key={`repo-${key}`} className="min-w-0">
                <div className="text-xs uppercase text-muted-foreground">repo {key}</div>
                <div className="truncate text-sm font-medium" title={value}>{value}</div>
              </div>
            ))}
            {Object.entries(planeSettings?.saved_paths ?? {}).map(([key, value]) => (
              <div key={`plane-${key}`} className="min-w-0">
                <div className="text-xs uppercase text-muted-foreground">plane {key}</div>
                <div className="truncate text-sm font-medium" title={value}>{value}</div>
              </div>
            ))}
            {Object.entries(graphiti?.saved_paths ?? {}).map(([key, value]) => (
              <div key={`graphiti-${key}`} className="min-w-0">
                <div className="text-xs uppercase text-muted-foreground">graphiti {key}</div>
                <div className="truncate text-sm font-medium" title={value}>{value}</div>
              </div>
            ))}
          </div>
        </section>
        </aside>
      )}
    />
  );
}
