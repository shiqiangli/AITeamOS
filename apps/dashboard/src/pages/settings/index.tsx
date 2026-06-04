import { FormEvent, type Dispatch, type ReactNode, type SetStateAction, useEffect, useMemo, useState } from "react";
import {
  Activity,
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
  SlidersHorizontal,
  Trash2,
} from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Select } from "../../components/ui/select";
import { ErrorState, LoadingState, Status } from "../../components/shared";
import { ResizableDetailLayout } from "../../components/resizable-layout";
import { getCapabilities, type CapabilityRegistryResponse } from "../../api/capabilities";
import {
  getChatAiEngines,
  listChatEmployees,
  updateChatAiEngine,
  updateChatAiEngines,
  type ChatEmployeeSummary,
  type ChatAiEngineSettings,
  type ChatAiEngineUpdateRequest,
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
  getToolConnectorStatus,
  listToolConnectors,
  type ToolConnector,
  type ToolConnectorRegistryStatus,
} from "../../api/toolConnectors";
import { getSecretsHealth, type SecretsHealthResponse } from "../../api/settings";
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

type SettingsSection = "ai-engines" | "tool-connectors" | "code-repositories" | "ticket-backend" | "memory-backend" | "secrets-health";

type AiEngineForm = {
  activeEngine: string;
  deepseekModel: string;
  deepseekThinking: string;
  openaiModel: string;
  fallbackOnError: boolean;
};

type GraphitiForm = {
  enabled: boolean;
  graphDatabase: string;
  uri: string;
  user: string;
  groupId: string;
  llmProvider: string;
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
}

const SECTION_GROUPS: SettingsGroup[] = [
  { key: "ai-engines", label: "AI Engines", icon: SlidersHorizontal },
  { key: "tool-connectors", label: "Tool Connectors", icon: Plug },
  { key: "code-repositories", label: "Code Repositories", icon: FolderGit2 },
  { key: "ticket-backend", label: "Ticket Backend", icon: ClipboardList },
  { key: "memory-backend", label: "Memory Backend", icon: Database },
  { key: "secrets-health", label: "Secrets & Health", icon: KeyRound },
];

const SECTION_DESCRIPTIONS: Record<SettingsSection, string> = {
  "ai-engines": "Model and agent backends that Clara and Employees use to think and execute.",
  "tool-connectors": "External tool sources, including MCP servers and adapter-backed integrations.",
  "code-repositories": "Product and regression repositories that ground code-aware work.",
  "ticket-backend": "Ticket source of truth and adapter targets for work ledgers.",
  "memory-backend": "Long-term memory backend configuration for approved memory assets.",
  "secrets-health": "Read-only environment variable checks and runtime health signals.",
};

const PROVIDERS = [
  { id: "stub", name: "File stub", kind: "local", description: "Offline deterministic fallback for development." },
  { id: "deepseek", name: "DeepSeek", kind: "llm_api", description: "Chat Completions engine used for low-cost AI Employee testing." },
  { id: "openai", name: "OpenAI / ChatGPT", kind: "llm_api", description: "Responses API engine for OpenAI-backed employees." },
];

function sectionFromRoute(value?: string | null): SettingsSection {
  return SECTION_GROUPS.some((g) => g.key === value) ? (value as SettingsSection) : "ai-engines";
}

function aiEnginesToForm(aiEngines: ChatAiEngineSettings): AiEngineForm {
  return {
    activeEngine: aiEngines.active_engine,
    deepseekModel: aiEngines.deepseek_model,
    deepseekThinking: aiEngines.deepseek_thinking,
    openaiModel: aiEngines.openai_model,
    fallbackOnError: aiEngines.fallback_on_error,
  };
}

function graphitiToForm(settings: GraphitiSettingsResponse): GraphitiForm {
  return {
    enabled: settings.enabled,
    graphDatabase: settings.graph_database || "neo4j",
    uri: settings.uri || "bolt://localhost:7687",
    user: settings.user || "neo4j",
    groupId: settings.group_id || "aiteamos",
    llmProvider: settings.llm_provider || "openai",
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

function DetailPanel({
  children,
  icon: Icon,
  title,
}: {
  children: ReactNode;
  icon: typeof Settings;
  title: string;
}) {
  return (
    <section className="rounded-md border bg-background p-4">
      <div className="mb-3 flex items-center gap-2">
        <Icon className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold">{title}</h3>
      </div>
      {children}
    </section>
  );
}

function DetailPaths({ paths }: { paths?: Record<string, string> | null }) {
  const entries = Object.entries(paths ?? {});
  if (entries.length === 0) {
    return <div className="text-sm text-muted-foreground">No saved files recorded.</div>;
  }

  return (
    <div className="space-y-3">
      {entries.map(([key, value]) => (
        <div key={key} className="min-w-0">
          <div className="text-xs uppercase text-muted-foreground">{key.replace(/_/g, " ")}</div>
          <div className="truncate text-sm font-medium" title={value}>{value}</div>
        </div>
      ))}
    </div>
  );
}

function EmptyDetail({ children }: { children: ReactNode }) {
  return <div className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">{children}</div>;
}

function AiEnginesSection({
  form,
  aiEngines,
  saving,
  setForm,
  onPolicySubmit,
  onEngineSubmit,
}: {
  form: AiEngineForm;
  aiEngines: ChatAiEngineSettings | null;
  saving: boolean;
  setForm: Dispatch<SetStateAction<AiEngineForm>>;
  onPolicySubmit: (event: FormEvent<HTMLFormElement>) => void;
  onEngineSubmit: (engineId: string, payload: ChatAiEngineUpdateRequest) => void;
}) {
  const deepseek = aiEngines?.engines?.deepseek;
  const openai = aiEngines?.engines?.openai;
  const stub = aiEngines?.engines?.stub;

  return (
    <div className="space-y-4">
      <section className="rounded-md border bg-background">
        <div className="border-b px-4 py-3">
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold">AI Engine Policy</h3>
          </div>
        </div>
        <form onSubmit={onPolicySubmit} className="grid gap-4 p-4 xl:grid-cols-[minmax(0,1fr)_18rem]">
          <div className="grid gap-4 md:grid-cols-2">
          <label className="block space-y-1">
            <span className="text-xs uppercase text-muted-foreground">Active engine</span>
            <Select
              aria-label="Active AI Engine"
              value={form.activeEngine}
              onChange={(event) => setForm((current) => ({ ...current, activeEngine: event.target.value }))}
            >
              <option value="stub">File stub</option>
              <option value="deepseek">DeepSeek</option>
              <option value="openai">OpenAI</option>
            </Select>
          </label>

            <label className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm">
              <span>Fallback on engine error</span>
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
            <Status label="Active" value={aiEngines?.active_engine ?? "-"} />
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
            onClick={() => onEngineSubmit("stub", { activate: true })}
          >
            {stub?.active ? "Active" : "Set active"}
          </Button>
        </section>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            onEngineSubmit("deepseek", {
              model: form.deepseekModel,
              thinking: form.deepseekThinking,
            });
          }}
          className={cn("rounded-md border bg-background p-4", deepseek?.active && "border-primary bg-primary/10")}
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold">DeepSeek</h3>
              <p className="mt-1 text-sm text-muted-foreground">Low-cost LLM API engine for development and Clara chat testing.</p>
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
            <Status label="DEEPSEEK_API_KEY" value={deepseek?.api_key_configured ? "configured" : "missing"} tone={deepseek?.api_key_configured ? "ok" : "warn"} />
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
              onClick={() => onEngineSubmit("deepseek", { activate: true })}
            >
              {deepseek?.active ? "Active" : "Set active"}
            </Button>
          </div>
        </form>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            onEngineSubmit("openai", {
              model: form.openaiModel,
            });
          }}
          className={cn("rounded-md border bg-background p-4", openai?.active && "border-primary bg-primary/10")}
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold">OpenAI / ChatGPT</h3>
              <p className="mt-1 text-sm text-muted-foreground">OpenAI-backed AI Engine for ChatGPT/OpenAI execution.</p>
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
            <Status label="OPENAI_API_KEY" value={openai?.api_key_configured ? "configured" : "missing"} tone={openai?.api_key_configured ? "ok" : "warn"} />
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
              onClick={() => onEngineSubmit("openai", { activate: true })}
            >
              {openai?.active ? "Active" : "Set active"}
            </Button>
          </div>
        </form>
      </div>
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
      <form onSubmit={onSubmit} className="space-y-4 p-4">
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

      </form>
    </section>
  );
}

function CodeRepositoriesSection({
  form,
  repositories,
  saving,
  selectedId,
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

      </aside>
    </div>
  );
}

function MemoryBackendSection({
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
          <h3 className="text-sm font-semibold">Memory Backend</h3>
        </div>
      </div>
      <form onSubmit={onSubmit} className="space-y-4 p-4">
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
              <span className="text-xs uppercase text-muted-foreground">Graphiti LLM</span>
              <Select
                aria-label="Graphiti LLM provider"
                value={form.llmProvider}
                onChange={(event) => setForm((current) => ({ ...current, llmProvider: event.target.value }))}
              >
                <option value="openai">OpenAI</option>
              </Select>
            </label>
            <Status label="Graphiti password env" value={graphiti?.password_configured ? "configured" : "missing"} tone={graphiti?.password_configured ? "ok" : "warn"} />
            <Status label="Graphiti LLM key env" value={graphiti?.openai_api_key_configured ? "configured" : "missing"} tone={graphiti?.openai_api_key_configured ? "ok" : "warn"} />
          </div>

          <Button type="submit" disabled={saving}>
            <Save className="h-4 w-4" />
            {saving ? "Saving" : "Save backend"}
          </Button>
        </div>

      </form>
    </section>
  );
}

export function SettingsPage({ selectedSection }: { selectedSection?: string | null }) {
  const [section, setSection] = useState<SettingsSection>(() => sectionFromRoute(selectedSection));
  const [aiEngines, setAiEngines] = useState<ChatAiEngineSettings | null>(null);
  const [form, setForm] = useState<AiEngineForm>({
    activeEngine: "stub",
    deepseekModel: "deepseek-v4-flash",
    deepseekThinking: "disabled",
    openaiModel: "gpt-5-nano",
    fallbackOnError: true,
  });
  const [graphitiForm, setGraphitiForm] = useState<GraphitiForm>({
    enabled: false,
    graphDatabase: "neo4j",
    uri: "bolt://localhost:7687",
    user: "neo4j",
    groupId: "aiteamos",
    llmProvider: "openai",
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
  const [toolConnectors, setToolConnectors] = useState<ToolConnector[]>([]);
  const [selectedConnectorId, setSelectedConnectorId] = useState("");
  const [toolConnectorStatus, setToolConnectorStatus] = useState<ToolConnectorRegistryStatus | null>(null);
  const [secretsHealth, setSecretsHealth] = useState<SecretsHealthResponse | null>(null);
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
  const selectedRepository = useMemo(
    () => repositories.find((repository) => repository.id === selectedRepositoryId) ?? null,
    [repositories, selectedRepositoryId],
  );
  const selectedConnector = useMemo(
    () => toolConnectors.find((connector) => connector.id === selectedConnectorId) ?? toolConnectors[0] ?? null,
    [toolConnectors, selectedConnectorId],
  );

  async function loadSettings() {
    setLoading(true);
    setError(null);
    try {
      const [
        loadedAiEngines,
        loadedEmployees,
        loadedKnowledge,
        loadedMemory,
        loadedGraphiti,
        loadedCapabilityRegistry,
        loadedTicketBackend,
        loadedTicketBackendStatus,
        loadedRepositories,
        loadedRepositoryStatus,
        loadedToolConnectors,
        loadedToolConnectorStatus,
        loadedSecretsHealth,
      ] = await Promise.all([
        getChatAiEngines(),
        listChatEmployees(),
        getKnowledgeStatus(),
        getMemoryStatus(),
        getGraphitiSettings(),
        getCapabilities(),
        getTicketBackendSettings(),
        getTicketBackendStatus(),
        listCodeRepositories(),
        getCodeRepositoryStatus(),
        listToolConnectors(),
        getToolConnectorStatus(),
        getSecretsHealth(),
      ]);
      setAiEngines(loadedAiEngines);
      setForm(aiEnginesToForm(loadedAiEngines));
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
      setToolConnectors(loadedToolConnectors);
      const selectedConnector = loadedToolConnectors.find((connector) => connector.id === selectedConnectorId) ?? loadedToolConnectors[0] ?? null;
      setSelectedConnectorId(selectedConnector?.id ?? "");
      setToolConnectorStatus(loadedToolConnectorStatus);
      setSecretsHealth(loadedSecretsHealth);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadSettings();
  }, []);

  async function handleAiEnginePolicySubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateChatAiEngines({
        active_engine: form.activeEngine,
        deepseek_model: form.deepseekModel,
        deepseek_thinking: form.deepseekThinking,
        openai_model: form.openaiModel,
        fallback_on_error: form.fallbackOnError,
      });
      setAiEngines(updated);
      setForm(aiEnginesToForm(updated));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save AI Engine settings");
    } finally {
      setSaving(false);
    }
  }

  async function handleAiEngineSubmit(engineId: string, payload: ChatAiEngineUpdateRequest) {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateChatAiEngine(engineId, payload);
      setAiEngines(updated);
      setForm(aiEnginesToForm(updated));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save AI Engine settings");
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
    };
    try {
      const updated = await updateGraphitiSettings(payload);
      const updatedMemory = await getMemoryStatus();
      setGraphiti(updated);
      setGraphitiForm(graphitiToForm(updated));
      setMemory(updatedMemory);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save memory backend settings");
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

  function renderSettingsDetail(): ReactNode {
    if (section === "ai-engines") {
      const engines = Object.values(aiEngines?.engines ?? {});

      return (
        <aside className="space-y-4">
          <DetailPanel title="AI Engine Detail" icon={SlidersHorizontal}>
            <div className="space-y-3">
              <Status label="Active" value={aiEngines?.active_engine ?? "-"} tone={aiEngines?.active_engine === "stub" ? "warn" : "ok"} />
              <Status label="Fallback" value={aiEngines?.fallback_on_error ? "enabled" : "disabled"} />
              {engines.map((engine) => (
                <div key={engine.id} className="rounded-md border px-3 py-2 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-medium">{engine.display_name}</span>
                    <div className="flex flex-wrap gap-2">
                      {engine.active && <Badge variant="success">active</Badge>}
                      <Badge variant={statusVariant(engine.status)}>{engine.status}</Badge>
                    </div>
                  </div>
                  <div className="mt-2 grid gap-2 text-xs text-muted-foreground">
                    <span>Kind: {engine.kind}</span>
                    {engine.model && <span>Model: {engine.model}</span>}
                    {engine.thinking && <span>Thinking: {engine.thinking}</span>}
                    <span>Secret: {engine.api_key_configured ? "configured" : "missing"}</span>
                  </div>
                </div>
              ))}
            </div>
          </DetailPanel>

          <DetailPanel title="Saved Files" icon={Settings}>
            <DetailPaths paths={aiEngines?.saved_paths} />
          </DetailPanel>
        </aside>
      );
    }

    if (section === "tool-connectors") {
      const connectorStatus = selectedConnector
        ? selectedConnector.enabled && selectedConnector.configured ? "ready" : selectedConnector.status
        : "-";

      return (
        <aside className="space-y-4">
          <DetailPanel title="Connector Detail" icon={Plug}>
            {selectedConnector ? (
              <div className="space-y-3">
                <div>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="text-sm font-semibold">{selectedConnector.name}</h3>
                    <Badge variant={statusVariant(connectorStatus)}>{connectorStatus}</Badge>
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">{selectedConnector.description}</p>
                </div>
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
                  <Status label="Transport" value={selectedConnector.transport} />
                  <Status label="Enabled" value={selectedConnector.enabled ? "yes" : "no"} tone={selectedConnector.enabled ? "ok" : "warn"} />
                  <Status label="Configured" value={selectedConnector.configured ? "yes" : "no"} tone={selectedConnector.configured ? "ok" : "warn"} />
                  <Status label="Updated" value={selectedConnector.updated_at || "-"} />
                </div>
                <div>
                  <div className="mb-2 text-xs uppercase text-muted-foreground">Capabilities</div>
                  <div className="flex flex-wrap gap-2">
                    {selectedConnector.capabilities.length === 0 ? (
                      <Badge variant="secondary">none</Badge>
                    ) : selectedConnector.capabilities.map((capability) => (
                      <Badge key={capability} variant="outline">{capability}</Badge>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="mb-2 text-xs uppercase text-muted-foreground">Required settings</div>
                  <div className="flex flex-wrap gap-2">
                    {selectedConnector.required_settings.length === 0 ? (
                      <Badge variant="secondary">none</Badge>
                    ) : selectedConnector.required_settings.map((setting) => (
                      <Badge key={setting} variant="secondary">{setting}</Badge>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="mb-2 text-xs uppercase text-muted-foreground">Permissions</div>
                  <div className="flex flex-wrap gap-2">
                    {selectedConnector.permissions.length === 0 ? (
                      <Badge variant="secondary">none</Badge>
                    ) : selectedConnector.permissions.map((permission) => (
                      <Badge key={permission} variant="outline">{permission}</Badge>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <EmptyDetail>No connector selected.</EmptyDetail>
            )}
          </DetailPanel>

          <DetailPanel title="Connector Registry" icon={Settings}>
            <div className="space-y-3">
              <Status label="Connectors" value={toolConnectorStatus?.connector_count ?? toolConnectors.length} />
              <Status label="Enabled" value={toolConnectorStatus?.enabled_count ?? 0} />
              <Status label="Configured" value={toolConnectorStatus?.configured_count ?? 0} />
              <Status label="Ready" value={toolConnectorStatus?.ready_count ?? 0} tone={(toolConnectorStatus?.ready_count ?? 0) > 0 ? "ok" : "warn"} />
              <DetailPaths paths={toolConnectorStatus?.saved_paths} />
            </div>
          </DetailPanel>
        </aside>
      );
    }

    if (section === "code-repositories") {
      return (
        <aside className="space-y-4">
          <DetailPanel title="Repository Detail" icon={FolderGit2}>
            {selectedRepository ? (
              <div className="space-y-3">
                <div>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="text-sm font-semibold">{selectedRepository.name}</h3>
                    <Badge variant={statusVariant(selectedRepository.status)}>{selectedRepository.status}</Badge>
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">{selectedRepository.detail || selectedRepository.description || "No detail recorded."}</p>
                </div>
                <Status label="Provider" value={selectedRepository.provider} />
                <Status label="Branch" value={selectedRepository.current_branch || selectedRepository.default_branch || "-"} />
                <Status label="Git detected" value={selectedRepository.git_detected ? "yes" : "no"} tone={selectedRepository.git_detected ? "ok" : "warn"} />
                <Status label="Enabled" value={selectedRepository.enabled ? "yes" : "no"} tone={selectedRepository.enabled ? "ok" : "warn"} />
                <div className="min-w-0">
                  <div className="text-xs uppercase text-muted-foreground">Location</div>
                  <div className="truncate text-sm font-medium" title={selectedRepository.location}>{selectedRepository.location}</div>
                </div>
                <div className="grid gap-2 text-xs text-muted-foreground">
                  <span>Plane workspace: {selectedRepository.plane_workspace_slug || "-"}</span>
                  <span>Plane project: {selectedRepository.plane_project_id || "-"}</span>
                </div>
              </div>
            ) : (
              <EmptyDetail>Select a repository to inspect its status and source mapping.</EmptyDetail>
            )}
          </DetailPanel>

          <DetailPanel title="Repository Registry" icon={GitBranch}>
            <div className="space-y-3">
              <Status label="Repositories" value={repositoryStatus?.repository_count ?? repositories.length} />
              <Status label="Enabled" value={repositoryStatus?.enabled_count ?? 0} />
              <Status label="Ready" value={repositoryStatus?.ready_count ?? 0} />
              <Status label="Remote" value={repositoryStatus?.remote_count ?? 0} />
              <DetailPaths paths={repositoryStatus?.saved_paths} />
            </div>
          </DetailPanel>
        </aside>
      );
    }

    if (section === "ticket-backend") {
      return (
        <aside className="space-y-4">
          <DetailPanel title="Ticket Backend Status" icon={ClipboardList}>
            <div className="space-y-3">
              <Status label="Mode" value={ticketBackendStatus?.mode ?? ticketBackend?.mode ?? "-"} />
              <Status label="Status" value={compactStatus(ticketBackendStatus?.status)} tone={ticketBackendStatus?.status === "ready" ? "ok" : "warn"} />
              <Status label="Tickets" value={ticketBackendStatus?.ticket_count ?? 0} />
              <div className="min-w-0">
                <div className="text-xs uppercase text-muted-foreground">Local file</div>
                <div className="truncate text-sm font-medium" title={ticketBackendStatus?.local_file_path ?? ticketBackend?.local_file_path}>
                  {ticketBackendStatus?.local_file_path ?? ticketBackend?.local_file_path ?? "-"}
                </div>
              </div>
              <div className="rounded-md bg-muted px-3 py-2 text-xs leading-5 text-muted-foreground">
                {ticketBackendStatus?.detail ?? "Local file is the active P0 backend. Plane/Jira are adapter targets, not separate product models."}
              </div>
            </div>
          </DetailPanel>

          <DetailPanel title="Saved Files" icon={Settings}>
            <DetailPaths paths={ticketBackendStatus?.saved_paths ?? ticketBackend?.saved_paths} />
          </DetailPanel>
        </aside>
      );
    }

    if (section === "memory-backend") {
      const savedPaths = {
        ...(memory?.saved_paths ?? {}),
        ...(graphiti?.saved_paths ?? {}),
      };

      return (
        <aside className="space-y-4">
          <DetailPanel title="Memory Backend Status" icon={Database}>
            <div className="space-y-3">
              <Status label="Graphiti" value={compactStatus(graphiti?.backend.status ?? memory?.backend.status)} tone={(graphiti?.backend.status ?? memory?.backend.status) === "ready" ? "ok" : "warn"} />
              <Status label="Graph DB" value={(graphiti?.backend.graph_configured ?? memory?.backend.graph_configured) ? "set" : "missing"} tone={(graphiti?.backend.graph_configured ?? memory?.backend.graph_configured) ? "ok" : "warn"} />
              <Status label="LLM key" value={(graphiti?.backend.llm_configured ?? memory?.backend.llm_configured) ? "set" : "missing"} tone={(graphiti?.backend.llm_configured ?? memory?.backend.llm_configured) ? "ok" : "warn"} />
              <Status label="Approved memories" value={memory?.approved_count ?? 0} />
              <Status label="Pending graphiti" value={memory?.pending_graphiti_count ?? 0} />
              <Status label="Shared OpenAI key" value={graphiti?.uses_shared_openai_key ? "used" : "optional"} />
              <div className="rounded-md bg-muted px-3 py-2 text-xs leading-5 text-muted-foreground">
                {graphiti?.backend.detail ?? memory?.backend.detail ?? "Memory backend health has not been checked yet."}
              </div>
            </div>
          </DetailPanel>

          <DetailPanel title="Saved Files" icon={Settings}>
            <DetailPaths paths={savedPaths} />
          </DetailPanel>
        </aside>
      );
    }

    const secretItems = secretsHealth?.items ?? [];
    const configuredSecrets = secretItems.filter((item) => item.configured).length;

    return (
      <aside className="space-y-4">
        <DetailPanel title="System Health" icon={Activity}>
          <div className="grid gap-3">
            <Status label="AI Engine" value={aiEngines?.active_engine ?? "-"} tone={aiEngines?.active_engine === "stub" ? "warn" : "ok"} />
            <Status label="Employees" value={employees.length} />
            <Status label="Knowledge docs" value={knowledge?.docs_count ?? 0} />
            <Status label="Review items" value={knowledge?.review_queue_count ?? 0} />
            <Status label="Tools" value={capabilityRegistry?.status.tool_count ?? 0} />
            <Status label="Tools ready" value={capabilityRegistry?.status.ready_count ?? 0} tone={(capabilityRegistry?.status.ready_count ?? 0) > 0 ? "ok" : "warn"} />
            <Status label="Ticket backend" value={compactStatus(ticketBackendStatus?.status)} tone={ticketBackendStatus?.status === "ready" ? "ok" : "warn"} />
            <Status label="Tickets" value={ticketBackendStatus?.ticket_count ?? 0} />
            <Status label="Tool connectors ready" value={toolConnectorStatus?.ready_count ?? 0} tone={(toolConnectorStatus?.ready_count ?? 0) > 0 ? "ok" : "warn"} />
            <Status label="Code repositories" value={repositoryStatus?.repository_count ?? repositories.length} />
            <Status label="Repos ready" value={repositoryStatus?.ready_count ?? 0} tone={(repositoryStatus?.ready_count ?? 0) > 0 ? "ok" : "warn"} />
            <Status label="Approved memories" value={memory?.approved_count ?? 0} />
          </div>
        </DetailPanel>

        <DetailPanel title="Secret Coverage" icon={KeyRound}>
          <div className="space-y-3">
            <Status label="Configured" value={configuredSecrets} tone={configuredSecrets === secretItems.length ? "ok" : "warn"} />
            <Status label="Missing" value={secretItems.length - configuredSecrets} tone={configuredSecrets === secretItems.length ? "ok" : "warn"} />
            <Status label="Required vars" value={secretItems.reduce((count, item) => count + item.env_vars.length, 0)} />
          </div>
        </DetailPanel>
      </aside>
    );
  }

  if (loading) return <LoadingState />;
  const ActiveIcon = activeGroup.icon;

  return (
    <ResizableDetailLayout
      id="aiteamos-settings-layout"
	      main={(
	        <section className="space-y-4">
	        <div className="rounded-md border bg-background">
	          <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
	            <div>
	              <div className="flex items-center gap-2">
	                <ActiveIcon className="h-4 w-4 text-muted-foreground" />
	                <h3 className="text-sm font-semibold">{activeGroup.label}</h3>
	              </div>
	              <p className="mt-1 text-sm text-muted-foreground">{SECTION_DESCRIPTIONS[section]}</p>
	            </div>
	            <Button type="button" variant="outline" size="sm" onClick={() => void loadSettings()}>
	              <RefreshCw className="h-4 w-4" />
	              Refresh
	            </Button>
	          </div>

	          {error && (
	            <div className="border-t p-4">
	              <ErrorState message={error} onRetry={loadSettings} />
	            </div>
	          )}
        </div>

        {section === "ai-engines" && (
          <AiEnginesSection
            form={form}
            aiEngines={aiEngines}
            saving={saving}
            setForm={setForm}
            onPolicySubmit={handleAiEnginePolicySubmit}
            onEngineSubmit={(engineId, payload) => void handleAiEngineSubmit(engineId, payload)}
          />
        )}

        {section === "ticket-backend" && (
          <TicketBackendSection
            form={ticketBackendForm}
            saving={saving}
            settings={ticketBackend}
            status={ticketBackendStatus}
            setForm={setTicketBackendForm}
            onSubmit={(event) => void handleTicketBackendSubmit(event)}
          />
        )}

	        {section === "tool-connectors" && (
	          <section className="rounded-md border bg-background">
	            <div className="border-b px-4 py-3">
	              <div className="flex items-center gap-2">
	                <Plug className="h-4 w-4 text-muted-foreground" />
	                <h3 className="text-sm font-semibold">Tool Connectors</h3>
	              </div>
	            </div>
	            <div className="grid gap-3 p-4">
	              {toolConnectors.length === 0 ? (
	                <EmptyDetail>No tool connectors configured.</EmptyDetail>
	              ) : toolConnectors.map((connector) => {
	                const connectorStatus = connector.enabled && connector.configured ? "ready" : connector.status;
	                return (
	                  <button
	                    key={connector.id}
	                    type="button"
	                    onClick={() => setSelectedConnectorId(connector.id)}
	                    className={cn(
	                      "rounded-md border px-4 py-3 text-left transition-colors",
	                      selectedConnector?.id === connector.id ? "border-primary bg-primary/10" : "bg-background hover:bg-muted/60",
	                    )}
	                  >
	                    <div className="flex flex-wrap items-start justify-between gap-3">
	                      <div className="min-w-0">
	                        <div className="font-medium">{connector.name}</div>
	                        <div className="mt-1 text-sm text-muted-foreground">{connector.description}</div>
	                      </div>
	                      <div className="flex shrink-0 flex-wrap gap-2">
	                        <Badge variant="outline">{connector.transport}</Badge>
	                        <Badge variant={statusVariant(connectorStatus)}>{connectorStatus}</Badge>
	                      </div>
	                    </div>
	                    <div className="mt-3 flex flex-wrap gap-2">
	                      {connector.capabilities.slice(0, 4).map((capability) => (
	                        <Badge key={capability} variant="outline">{capability}</Badge>
	                      ))}
	                      {connector.capabilities.length === 0 && <Badge variant="secondary">no tools</Badge>}
	                      {connector.capabilities.length > 4 && (
	                        <Badge variant="secondary">+{connector.capabilities.length - 4}</Badge>
	                      )}
	                    </div>
	                  </button>
	                );
	              })}
	            </div>
	          </section>
	        )}

        {section === "code-repositories" && (
          <CodeRepositoriesSection
            form={repositoryForm}
	            repositories={repositories}
	            saving={saving}
	            selectedId={selectedRepositoryId}
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
        )}

        {section === "memory-backend" && (
          <MemoryBackendSection
            form={graphitiForm}
            graphiti={graphiti}
            saving={saving}
            setForm={setGraphitiForm}
            onSubmit={handleGraphitiSubmit}
          />
        )}

	        {section === "secrets-health" && (
	          <section className="rounded-md border bg-background">
	            <div className="border-b px-4 py-3">
	              <div className="flex items-center gap-2">
	                <KeyRound className="h-4 w-4 text-muted-foreground" />
	                <h3 className="text-sm font-semibold">Secrets & Health</h3>
	              </div>
	            </div>
	            <div className="grid gap-3 p-4">
	              {(secretsHealth?.items ?? []).map((item) => (
	                <ConfigRow
	                  key={item.id}
	                  name={item.env_vars.join(" / ")}
	                  kind={item.scope}
	                  status={item.configured ? "configured" : "missing"}
	                  description={`${item.purpose} ${item.how_to_configure}`}
	                />
	              ))}
	            </div>
	          </section>
	        )}
        </section>
      )}

	      detail={renderSettingsDetail()}
	    />
	  );
	}
