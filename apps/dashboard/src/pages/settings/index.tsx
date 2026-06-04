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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";
import { ErrorState, LoadingState, Status } from "../../components/shared";
import { ResizableDetailLayout } from "../../components/resizable-layout";
import {
  getChatAiEngines,
  updateChatAiEngine,
  updateChatAiEngines,
  type ChatAiEngineConfigField,
  type ChatAiEngineRecord,
  type ChatAiEngineSettings,
  type ChatAiEngineUpdateRequest,
} from "../../api/chat";
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

type SettingsSection = "ai-engines" | "tool-connectors" | "code-repositories" | "ticket-backend" | "memory-backend";

type AiEngineForm = {
  activeEngine: string;
  fallbackOnError: boolean;
};

type AiEngineDraft = {
  model: string;
  thinking: string;
  speed: string;
  context_window: string;
  max_tokens: string;
  base_url: string;
  api_key_env: string;
  enabled: boolean;
};

type GraphitiForm = {
  enabled: boolean;
  graphDatabase: string;
  uri: string;
  user: string;
  groupId: string;
  llmAiEngine: string;
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
];

const SECTION_DESCRIPTIONS: Record<SettingsSection, string> = {
  "ai-engines": "Model and agent backends that Clara and Employees use to think and execute.",
  "tool-connectors": "External tool sources, including MCP servers and adapter-backed integrations.",
  "code-repositories": "Product and regression repositories that ground code-aware work.",
  "ticket-backend": "Ticket source of truth and adapter targets for work ledgers.",
  "memory-backend": "Long-term memory backend configuration for approved memory assets.",
};

function sectionFromRoute(value?: string | null): SettingsSection {
  return SECTION_GROUPS.some((g) => g.key === value) ? (value as SettingsSection) : "ai-engines";
}

function aiEnginesToForm(aiEngines: ChatAiEngineSettings): AiEngineForm {
  return {
    activeEngine: aiEngines.active_engine,
    fallbackOnError: aiEngines.fallback_on_error,
  };
}

function aiEngineFieldValue(engine: ChatAiEngineRecord, fieldId: keyof AiEngineDraft): string | boolean {
  if (fieldId === "enabled") return engine.enabled;
  const field = engine.config_fields?.find((item) => item.id === fieldId);
  const value = field?.value ?? engine[fieldId] ?? "";
  return typeof value === "boolean" ? value : String(value);
}

function aiEnginesToDrafts(aiEngines: ChatAiEngineSettings): Record<string, AiEngineDraft> {
  return Object.fromEntries(
    orderedAiEngineRecords(aiEngines).map((engine) => [
      engine.id,
      {
        model: String(aiEngineFieldValue(engine, "model")),
        thinking: String(aiEngineFieldValue(engine, "thinking")),
        speed: String(aiEngineFieldValue(engine, "speed")),
        context_window: String(aiEngineFieldValue(engine, "context_window")),
        max_tokens: String(aiEngineFieldValue(engine, "max_tokens")),
        base_url: String(aiEngineFieldValue(engine, "base_url")),
        api_key_env: String(aiEngineFieldValue(engine, "api_key_env")),
        enabled: Boolean(aiEngineFieldValue(engine, "enabled")),
      },
    ]),
  );
}

function orderedAiEngineRecords(aiEngines: ChatAiEngineSettings | null): ChatAiEngineRecord[] {
  const engines = aiEngines?.engines ?? {};
  const ordered = (aiEngines?.catalog_order ?? [])
    .map((engineId) => engines[engineId])
    .filter((engine): engine is ChatAiEngineRecord => Boolean(engine));
  const seen = new Set(ordered.map((engine) => engine.id));
  return [
    ...ordered,
    ...Object.values(engines).filter((engine) => !seen.has(engine.id)),
  ];
}

function graphitiCompatibleAiEngines(aiEngines: ChatAiEngineSettings | null): ChatAiEngineRecord[] {
  return orderedAiEngineRecords(aiEngines).filter((engine) => (
    engine.support_status === "supported"
    && engine.capabilities.includes("graphiti_llm")
  ));
}

function graphitiToForm(settings: GraphitiSettingsResponse): GraphitiForm {
  return {
    enabled: settings.enabled,
    graphDatabase: settings.graph_database || "neo4j",
    uri: settings.uri || "bolt://localhost:7687",
    user: settings.user || "neo4j",
    groupId: settings.group_id || "aiteamos",
    llmAiEngine: settings.llm_ai_engine || "openai",
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
  if (status === "missing" || status === "missing_secret" || status === "failed" || status === "invalid") return "danger";
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

function SummaryMetric({
  label,
  tone,
  value,
}: {
  label: string;
  tone?: "ok" | "warn";
  value: ReactNode;
}) {
  const toneClass =
    tone === "ok"
      ? "text-green-600"
      : tone === "warn"
      ? "text-orange-500"
      : "text-foreground";
  return (
    <div className="min-w-0 rounded-md border bg-card px-3 py-2">
      <div className="text-[10px] font-medium uppercase text-muted-foreground">{label}</div>
      <div className={cn("mt-0.5 truncate text-sm font-semibold", toneClass)}>{value}</div>
    </div>
  );
}

function updateAiEngineDraft(
  setDrafts: Dispatch<SetStateAction<Record<string, AiEngineDraft>>>,
  engineId: string,
  fieldId: keyof AiEngineDraft,
  value: string | boolean,
) {
  setDrafts((current) => {
    const currentDraft = current[engineId] ?? {
      model: "",
      thinking: "",
      speed: "",
      context_window: "",
      max_tokens: "",
      base_url: "",
      api_key_env: "",
      enabled: true,
    };
    return {
      ...current,
      [engineId]: {
        ...currentDraft,
        [fieldId]: value,
      },
    };
  });
}

function aiEngineUpdatePayload(draft: AiEngineDraft | undefined): ChatAiEngineUpdateRequest {
  return {
    model: draft?.model ?? "",
    thinking: draft?.thinking ?? "",
    speed: draft?.speed ?? "",
    context_window: draft?.context_window ? Number(draft.context_window) : null,
    max_tokens: draft?.max_tokens ? Number(draft.max_tokens) : null,
    base_url: draft?.base_url ?? "",
    api_key_env: draft?.api_key_env ?? "",
    enabled: draft?.enabled ?? true,
  };
}

function AiEngineFieldControl({
  draft,
  engine,
  field,
  onChange,
}: {
  draft: AiEngineDraft;
  engine: ChatAiEngineRecord;
  field: ChatAiEngineConfigField;
  onChange: (fieldId: keyof AiEngineDraft, value: string | boolean) => void;
}) {
  const fieldId = field.id as keyof AiEngineDraft;
  const disabled = field.read_only || !engine.editable;
  const value = field.id in draft ? draft[fieldId] : field.value;

  if (field.kind === "select") {
    return (
      <label className="block space-y-1">
        <span className="text-xs uppercase text-muted-foreground">{field.label}</span>
        <Select
          aria-label={field.label}
          value={String(value ?? "")}
          disabled={disabled}
          onChange={(event) => onChange(fieldId, event.target.value)}
        >
          {(field.options ?? []).map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </Select>
      </label>
    );
  }

  if (field.kind === "toggle") {
    return (
      <label className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm">
        <span>{field.label}</span>
        <input
          aria-label={field.label}
          type="checkbox"
          checked={Boolean(value)}
          disabled={disabled}
          onChange={(event) => onChange(fieldId, event.target.checked)}
          className="h-4 w-4"
        />
      </label>
    );
  }

  return (
    <label className="block space-y-1">
      <span className="text-xs uppercase text-muted-foreground">{field.label}</span>
      <input
        aria-label={field.label}
        type={field.kind === "number" ? "number" : "text"}
        value={String(value ?? "")}
        disabled={disabled}
        onChange={(event) => onChange(fieldId, event.target.value)}
        placeholder={field.placeholder}
        className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm disabled:bg-muted disabled:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
      {field.help && <span className="text-xs text-muted-foreground">{field.help}</span>}
    </label>
  );
}

function AiEngineDetailPanel({
  draft,
  engine,
  saving,
  setDrafts,
  onActivate,
  onSave,
}: {
  draft: AiEngineDraft;
  engine: ChatAiEngineRecord | null;
  saving: boolean;
  setDrafts: Dispatch<SetStateAction<Record<string, AiEngineDraft>>>;
  onActivate: (engineId: string) => void;
  onSave: (engineId: string) => void;
}) {
  if (!engine) return <EmptyDetail>Select an AI Engine to inspect its configuration.</EmptyDetail>;
  const supportStatus = engine.support_status ?? "supported";
  const configStatus = engine.config_status ?? engine.status;
  const editable = (engine.editable ?? true) && supportStatus === "supported";
  const configFields = engine.config_fields ?? [];
  const capabilities = engine.capabilities ?? [];
  const secretEnvVars = engine.secret_env_vars ?? (engine.api_key_env ? [engine.api_key_env] : []);

  return (
    <div className="space-y-4">
      <DetailPanel title="Engine Configuration" icon={SlidersHorizontal}>
        <div className="space-y-4">
          <div>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="text-sm font-semibold">{engine.display_name}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{engine.description}</p>
              </div>
              <div className="flex shrink-0 flex-wrap gap-2">
                {engine.active && <Badge variant="success">active</Badge>}
                <Badge variant="outline">{engine.kind}</Badge>
                <Badge variant={statusVariant(supportStatus)}>{supportStatus}</Badge>
                <Badge variant={statusVariant(configStatus)}>{configStatus.replace(/_/g, " ")}</Badge>
              </div>
            </div>
            <div className="mt-3 rounded-md bg-muted px-3 py-2 text-xs leading-5 text-muted-foreground">
              {engine.health_detail || "Status has not been checked yet."}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
            <Status label="Auth" value={engine.auth_kind} />
            <Status label="Secret" value={engine.api_key_configured ? "configured" : "missing"} tone={engine.api_key_configured ? "ok" : "warn"} />
          </div>

          {configFields.length > 0 ? (
            <form
              className="space-y-3"
              onSubmit={(event) => {
                event.preventDefault();
                if (editable) onSave(engine.id);
              }}
            >
              {configFields.map((field) => (
                <AiEngineFieldControl
                  key={field.id}
                  draft={draft}
                  engine={engine}
                  field={field}
                  onChange={(fieldId, value) => updateAiEngineDraft(setDrafts, engine.id, fieldId, value)}
                />
              ))}
              <div className="flex flex-wrap gap-2 pt-1">
                <Button type="submit" disabled={saving || !editable}>
                  <Save className="h-4 w-4" />
                  Save engine
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  disabled={saving || !editable || engine.active}
                  onClick={() => onActivate(engine.id)}
                >
                  {engine.active ? "Active" : "Set active"}
                </Button>
              </div>
            </form>
          ) : (
            <div className="space-y-3">
              <EmptyDetail>This engine does not need API configuration.</EmptyDetail>
              <Button
                type="button"
                variant="outline"
                disabled={saving || !editable || engine.active}
                onClick={() => onActivate(engine.id)}
              >
                {engine.active ? "Active" : "Set active"}
              </Button>
            </div>
          )}
        </div>
      </DetailPanel>

      <DetailPanel title="Capabilities" icon={Activity}>
        <div className="flex flex-wrap gap-2">
          {capabilities.length === 0 ? (
            <Badge variant="secondary">none</Badge>
          ) : capabilities.map((capability) => (
            <Badge key={capability} variant="outline">{capability}</Badge>
          ))}
        </div>
      </DetailPanel>

      <DetailPanel title="Secret Reference" icon={KeyRound}>
        <div className="space-y-3">
          {secretEnvVars.length === 0 ? (
            <EmptyDetail>No API key environment variable is required.</EmptyDetail>
          ) : secretEnvVars.map((envVar) => (
            <Status key={envVar} label={envVar} value={engine.api_key_configured ? "configured" : "missing"} tone={engine.api_key_configured ? "ok" : "warn"} />
          ))}
        </div>
      </DetailPanel>
    </div>
  );
}

function AiEnginesSection({
  detail,
  form,
  aiEngines,
  selectedId,
  saving,
  setForm,
  onSelect,
  onPolicySubmit,
  onActivate,
}: {
  detail: ReactNode;
  form: AiEngineForm;
  aiEngines: ChatAiEngineSettings | null;
  selectedId: string;
  saving: boolean;
  setForm: Dispatch<SetStateAction<AiEngineForm>>;
  onPolicySubmit: (event: FormEvent<HTMLFormElement>) => void;
  onSelect: (engineId: string) => void;
  onActivate: (engineId: string) => void;
}) {
  const engines = orderedAiEngineRecords(aiEngines);
  const configuredCount = engines.filter((engine) => engine.config_status === "configured").length;
  const missingSecretCount = engines.filter((engine) => (engine.config_status ?? engine.status) === "missing_secret").length;
  const plannedCount = engines.filter((engine) => engine.support_status === "planned").length;
  const activeEngineName = aiEngines?.engines?.[form.activeEngine]?.display_name ?? form.activeEngine;

  return (
    <div className="space-y-3">
      <section className="sticky top-0 z-20 rounded-md border bg-background/95 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-background/85">
        <form onSubmit={onPolicySubmit} className="grid gap-3 p-3 xl:grid-cols-[minmax(0,1fr)_auto]">
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
            <SummaryMetric label="Active" value={activeEngineName} tone={form.activeEngine === "stub" ? "warn" : "ok"} />
            <SummaryMetric label="Configured" value={configuredCount} tone={configuredCount > 1 ? "ok" : "warn"} />
            <SummaryMetric label="Missing secrets" value={missingSecretCount} tone={missingSecretCount === 0 ? "ok" : "warn"} />
            <SummaryMetric label="Planned" value={plannedCount} />
            <SummaryMetric label="Fallback" value={form.fallbackOnError ? "enabled" : "disabled"} />
          </div>
          <div className="flex min-w-[13rem] flex-wrap items-center gap-2 xl:justify-end">
            <label className="flex h-9 items-center justify-between gap-3 rounded-md border px-3 text-sm">
              <span>Fallback on engine error</span>
              <input
                aria-label="Fallback on error"
                type="checkbox"
                checked={form.fallbackOnError}
                onChange={(event) => setForm((current) => ({ ...current, fallbackOnError: event.target.checked }))}
                className="h-4 w-4"
              />
            </label>
            <Button type="submit" size="sm" disabled={saving}>
              <Save className="h-4 w-4" />
              Save policy
            </Button>
          </div>
        </form>
      </section>

      <div className="grid min-h-[26rem] gap-3 xl:h-[calc(100vh-20rem)] xl:grid-cols-[minmax(20rem,0.95fr)_minmax(24rem,1.05fr)]">
        <section className="flex min-h-0 min-w-0 flex-col rounded-md border bg-background">
          <div className="shrink-0 border-b px-3 py-2">
            <h3 className="text-sm font-semibold">Engine Catalog</h3>
          </div>
          <div className="min-h-0 flex-1 divide-y overflow-y-auto">
            {engines.map((engine) => {
              const selected = selectedId === engine.id;
              const supportStatus = engine.support_status ?? "supported";
              const disabled = supportStatus !== "supported";
              const capabilities = engine.capabilities ?? [];
              return (
                <div
                  key={engine.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => onSelect(engine.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") onSelect(engine.id);
                  }}
                  className={cn(
                    "grid w-full cursor-pointer gap-2 px-3 py-2.5 text-left transition-colors",
                    selected ? "bg-primary/10" : "hover:bg-muted/60",
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{engine.display_name}</span>
                        {engine.active && <Badge variant="success">active</Badge>}
                      </div>
                      <div className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{engine.description}</div>
                    </div>
                    <div className="flex shrink-0 flex-wrap justify-end gap-1.5">
                      <Badge variant="outline">{engine.kind}</Badge>
                      <Badge variant={statusVariant(supportStatus)}>{supportStatus}</Badge>
                      <Badge variant={statusVariant(engine.config_status ?? engine.status)}>{(engine.config_status ?? engine.status).replace(/_/g, " ")}</Badge>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    {capabilities.slice(0, 3).map((capability) => (
                      <Badge key={capability} variant="secondary">{capability}</Badge>
                    ))}
                    {capabilities.length > 3 && <Badge variant="secondary">+{capabilities.length - 3}</Badge>}
                    <div className="ml-auto">
                      {supportStatus === "supported" && (
                        <Button
                          type="button"
                          size="sm"
                          variant={engine.active ? "secondary" : "outline"}
                          disabled={saving || engine.active}
                          onClick={(event) => {
                            event.stopPropagation();
                            onActivate(engine.id);
                          }}
                        >
                          {engine.active ? "Active" : "Set active"}
                        </Button>
                      )}
                      {disabled && <Badge variant="outline">read only</Badge>}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        <aside className="min-h-0 min-w-0 space-y-3 overflow-y-auto pr-1">
          {detail}
        </aside>
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
  dialogOpen,
  form,
  repositories,
  repositoryStatus,
  saving,
  selectedId,
  setDialogOpen,
  setForm,
  onDelete,
  onNew,
  onSelect,
  onSubmit,
}: {
  dialogOpen: boolean;
  form: RepositoryForm;
  repositories: CodeRepository[];
  repositoryStatus: CodeRepositoryStatus | null;
  saving: boolean;
  selectedId: string;
  setDialogOpen: Dispatch<SetStateAction<boolean>>;
  setForm: Dispatch<SetStateAction<RepositoryForm>>;
  onDelete: (repoId: string) => void;
  onNew: () => void;
  onSelect: (repository: CodeRepository) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const selectedRepository = repositories.find((repository) => repository.id === selectedId) ?? null;
  const enabledCount = repositoryStatus?.enabled_count ?? repositories.filter((repository) => repository.enabled).length;
  const readyCount = repositoryStatus?.ready_count ?? repositories.filter((repository) => repository.status === "ready").length;
  const localCount = repositoryStatus?.local_count ?? repositories.filter((repository) => repository.provider === "local").length;
  const remoteCount = repositoryStatus?.remote_count ?? Math.max(repositories.length - localCount, 0);

  function openNewRepository() {
    onNew();
    setDialogOpen(true);
  }

  function openRepositoryConfig(repository: CodeRepository) {
    onSelect(repository);
    setDialogOpen(true);
  }

  return (
    <div className="space-y-3">
      <section className="sticky top-0 z-20 rounded-md border bg-background/95 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-background/85">
        <div className="grid gap-3 p-3 xl:grid-cols-[minmax(0,1fr)_auto]">
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
            <SummaryMetric label="Repositories" value={repositoryStatus?.repository_count ?? repositories.length} />
            <SummaryMetric label="Enabled" value={enabledCount} tone={enabledCount > 0 ? "ok" : "warn"} />
            <SummaryMetric label="Ready" value={readyCount} tone={readyCount > 0 ? "ok" : "warn"} />
            <SummaryMetric label="Local" value={localCount} />
            <SummaryMetric label="Remote" value={remoteCount} />
          </div>
          <div className="flex items-center justify-end">
            <Button type="button" size="sm" onClick={openNewRepository}>
              <Plus className="h-4 w-4" />
              Add
            </Button>
          </div>
        </div>
      </section>

      <section className="rounded-md border bg-background">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
          <div>
            <div className="flex items-center gap-2">
              <FolderGit2 className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold">Repository List</h3>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">Code context mappings used by Clara and Employees when creating or executing Tickets.</p>
          </div>
          <Button type="button" size="sm" variant="outline" onClick={openNewRepository}>
            <Plus className="h-4 w-4" />
            Add
          </Button>
        </div>

        {repositories.length === 0 ? (
          <div className="px-4 py-10 text-center text-sm text-muted-foreground">
            No repositories configured. Add the local path or Git URL for Ticket evidence.
          </div>
        ) : (
          <div className="divide-y">
            {repositories.map((repository) => (
              <div
                key={repository.id}
                className={cn(
                  "grid gap-3 px-4 py-3 text-sm transition-colors",
                  selectedId === repository.id ? "bg-primary/10" : "hover:bg-muted/60",
                )}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
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
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                    <span>Git: {repository.git_detected ? "detected" : "not detected"}</span>
                    <span>Enabled: {repository.enabled ? "yes" : "no"}</span>
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2">
                    <Button type="button" size="sm" variant="outline" onClick={() => openRepositoryConfig(repository)}>
                      <Settings className="h-4 w-4" />
                      Config
                    </Button>
                    <Button type="button" size="sm" variant="danger" disabled={saving} onClick={() => onDelete(repository.id)}>
                      <Trash2 className="h-4 w-4" />
                      Delete
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-h-[88vh] max-w-2xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{selectedId ? "Configure Repository" : "Add Repository"}</DialogTitle>
            <DialogDescription>
              {selectedRepository
                ? "Update the code context mapping used by Tickets and Employee repo tools."
                : "Add a local path or Git URL that AITeamOS can attach to Ticket flow."}
            </DialogDescription>
          </DialogHeader>
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
              <span className="text-xs uppercase text-muted-foreground">Source</span>
              <Select
                aria-label="Repository source"
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
              <Button type="button" variant="outline" disabled={saving} onClick={() => setDialogOpen(false)}>
                Cancel
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function MemoryBackendSection({
  form,
  graphiti,
  aiEngines,
  memory,
  saving,
  setForm,
  onSubmit,
}: {
  form: GraphitiForm;
  graphiti: GraphitiSettingsResponse | null;
  aiEngines: ChatAiEngineSettings | null;
  memory: MemoryStatusResponse | null;
  saving: boolean;
  setForm: Dispatch<SetStateAction<GraphitiForm>>;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const backendStatus = graphiti?.backend.status ?? memory?.backend.status ?? "unknown";
  const graphConfigured = graphiti?.backend.graph_configured ?? memory?.backend.graph_configured ?? false;
  const llmConfigured = graphiti?.backend.llm_configured ?? memory?.backend.llm_configured ?? false;
  const compatibleEngines = graphitiCompatibleAiEngines(aiEngines);
  const selectedCompatibleEngine = compatibleEngines.find((engine) => engine.id === form.llmAiEngine) ?? null;
  const selectedEngineLabel = selectedCompatibleEngine?.display_name ?? graphiti?.llm_ai_engine_name ?? form.llmAiEngine;
  const selectedEngineMissing = form.llmAiEngine && compatibleEngines.length > 0 && !selectedCompatibleEngine;
  const savedPaths = {
    ...(memory?.saved_paths ?? {}),
    ...(graphiti?.saved_paths ?? {}),
  };

  return (
    <div className="space-y-3">
      <section className="rounded-md border bg-background">
        <div className="grid gap-3 p-3 md:grid-cols-2 xl:grid-cols-5">
          <SummaryMetric label="Graphiti" value={compactStatus(backendStatus)} tone={backendStatus === "ready" ? "ok" : "warn"} />
          <SummaryMetric label="Graph DB" value={graphConfigured ? "set" : "missing"} tone={graphConfigured ? "ok" : "warn"} />
          <SummaryMetric label="AI key" value={llmConfigured ? "set" : "missing"} tone={llmConfigured ? "ok" : "warn"} />
          <SummaryMetric label="Approved memories" value={memory?.approved_count ?? 0} />
          <SummaryMetric label="Pending graphiti" value={memory?.pending_graphiti_count ?? 0} />
        </div>
      </section>

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
                <span className="text-xs uppercase text-muted-foreground">Graphiti AI Engine</span>
                <Select
                  aria-label="Graphiti AI Engine"
                  value={form.llmAiEngine}
                  onChange={(event) => setForm((current) => ({ ...current, llmAiEngine: event.target.value }))}
                >
                  {selectedEngineMissing && (
                    <option value={form.llmAiEngine}>{selectedEngineLabel}</option>
                  )}
                  {compatibleEngines.length === 0 ? (
                    <option value={form.llmAiEngine}>No compatible AI Engine</option>
                  ) : compatibleEngines.map((engine) => (
                    <option key={engine.id} value={engine.id}>
                      {engine.display_name}
                    </option>
                  ))}
                </Select>
              </label>
              <Status label="Graphiti password env" value={graphiti?.password_configured ? "configured" : "missing"} tone={graphiti?.password_configured ? "ok" : "warn"} />
              <Status label="Graphiti AI key env" value={graphiti?.llm_api_key_configured ? "configured" : "missing"} tone={graphiti?.llm_api_key_configured ? "ok" : "warn"} />
            </div>

            <Button type="submit" disabled={saving}>
              <Save className="h-4 w-4" />
              {saving ? "Saving" : "Save backend"}
            </Button>
          </div>
        </form>
      </section>

      <section className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.7fr)]">
        <DetailPanel title="Backend Health" icon={Activity}>
          <div className="space-y-3">
            <div className="grid gap-3 md:grid-cols-3">
              <Status label="AI Engine" value={selectedEngineLabel} />
              <Status label="API key env" value={graphiti?.llm_api_key_env || "-"} tone={llmConfigured ? "ok" : "warn"} />
              <Status label="Candidates" value={memory?.candidate_count ?? 0} />
              <Status label="Approved" value={memory?.approved_count ?? 0} />
            </div>
            <div className="rounded-md bg-muted px-3 py-2 text-xs leading-5 text-muted-foreground">
              {graphiti?.backend.detail ?? memory?.backend.detail ?? "Memory backend health has not been checked yet."}
            </div>
          </div>
        </DetailPanel>

        <DetailPanel title="Saved Files" icon={Settings}>
          <DetailPaths paths={savedPaths} />
        </DetailPanel>
      </section>
    </div>
  );
}

export function SettingsPage({ selectedSection }: { selectedSection?: string | null }) {
  const [section, setSection] = useState<SettingsSection>(() => sectionFromRoute(selectedSection));
  const [aiEngines, setAiEngines] = useState<ChatAiEngineSettings | null>(null);
  const [form, setForm] = useState<AiEngineForm>({
    activeEngine: "stub",
    fallbackOnError: true,
  });
  const [selectedAiEngineId, setSelectedAiEngineId] = useState("deepseek");
  const [aiEngineDrafts, setAiEngineDrafts] = useState<Record<string, AiEngineDraft>>({});
  const [graphitiForm, setGraphitiForm] = useState<GraphitiForm>({
    enabled: false,
    graphDatabase: "neo4j",
    uri: "bolt://localhost:7687",
    user: "neo4j",
    groupId: "aiteamos",
    llmAiEngine: "openai",
  });
  const [ticketBackendForm, setTicketBackendForm] = useState<TicketBackendForm>({
    mode: "local_file",
    localFilePath: ".aiteamos/tickets/index.json",
  });
  const [repositoryForm, setRepositoryForm] = useState<RepositoryForm>(emptyRepositoryForm);
  const [repositories, setRepositories] = useState<CodeRepository[]>([]);
  const [repositoryStatus, setRepositoryStatus] = useState<CodeRepositoryStatus | null>(null);
  const [selectedRepositoryId, setSelectedRepositoryId] = useState("");
  const [repositoryDialogOpen, setRepositoryDialogOpen] = useState(false);
  const [memory, setMemory] = useState<MemoryStatusResponse | null>(null);
  const [graphiti, setGraphiti] = useState<GraphitiSettingsResponse | null>(null);
  const [ticketBackend, setTicketBackend] = useState<TicketBackendSettings | null>(null);
  const [ticketBackendStatus, setTicketBackendStatus] = useState<TicketBackendStatus | null>(null);
  const [toolConnectors, setToolConnectors] = useState<ToolConnector[]>([]);
  const [selectedConnectorId, setSelectedConnectorId] = useState("");
  const [toolConnectorStatus, setToolConnectorStatus] = useState<ToolConnectorRegistryStatus | null>(null);
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
  const selectedAiEngine = useMemo(
    () => aiEngines?.engines?.[selectedAiEngineId] ?? orderedAiEngineRecords(aiEngines)[0] ?? null,
    [aiEngines, selectedAiEngineId],
  );

  async function loadSettings() {
    setLoading(true);
    setError(null);
    try {
      const [
        loadedAiEngines,
        loadedMemory,
        loadedGraphiti,
        loadedTicketBackend,
        loadedTicketBackendStatus,
        loadedRepositories,
        loadedRepositoryStatus,
        loadedToolConnectors,
        loadedToolConnectorStatus,
      ] = await Promise.all([
        getChatAiEngines(),
        getMemoryStatus(),
        getGraphitiSettings(),
        getTicketBackendSettings(),
        getTicketBackendStatus(),
        listCodeRepositories(),
        getCodeRepositoryStatus(),
        listToolConnectors(),
        getToolConnectorStatus(),
      ]);
      setAiEngines(loadedAiEngines);
      setForm(aiEnginesToForm(loadedAiEngines));
      setAiEngineDrafts(aiEnginesToDrafts(loadedAiEngines));
      setSelectedAiEngineId((current) => {
        const engines = loadedAiEngines.engines ?? {};
        if (current && engines[current]) return current;
        return loadedAiEngines.active_engine || loadedAiEngines.catalog_order?.[0] || Object.keys(engines)[0] || "";
      });
      setMemory(loadedMemory);
      setGraphiti(loadedGraphiti);
      setGraphitiForm(graphitiToForm(loadedGraphiti));
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
      const deepseekDraft = aiEngineDrafts.deepseek;
      const openaiDraft = aiEngineDrafts.openai;
      const updated = await updateChatAiEngines({
        active_engine: form.activeEngine,
        deepseek_model: deepseekDraft?.model || aiEngines?.deepseek_model || "deepseek-v4-flash",
        deepseek_thinking: deepseekDraft?.thinking || aiEngines?.deepseek_thinking || "disabled",
        openai_model: openaiDraft?.model || aiEngines?.openai_model || "gpt-5-nano",
        fallback_on_error: form.fallbackOnError,
      });
      setAiEngines(updated);
      setForm(aiEnginesToForm(updated));
      setAiEngineDrafts(aiEnginesToDrafts(updated));
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
      setAiEngineDrafts(aiEnginesToDrafts(updated));
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
      llm_ai_engine: graphitiForm.llmAiEngine,
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
      setRepositoryDialogOpen(false);
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

  function renderAiEngineDetail(): ReactNode {
    const draft = selectedAiEngine ? aiEngineDrafts[selectedAiEngine.id] ?? {
      model: selectedAiEngine.model ?? "",
      thinking: selectedAiEngine.thinking ?? "",
      speed: selectedAiEngine.speed ?? "",
      context_window: selectedAiEngine.context_window ? String(selectedAiEngine.context_window) : "",
      max_tokens: selectedAiEngine.max_tokens ? String(selectedAiEngine.max_tokens) : "",
      base_url: selectedAiEngine.base_url ?? "",
      api_key_env: selectedAiEngine.api_key_env ?? "",
      enabled: selectedAiEngine.enabled,
    } : {
      model: "",
      thinking: "",
      speed: "",
      context_window: "",
      max_tokens: "",
      base_url: "",
      api_key_env: "",
      enabled: true,
    };

    return (
      <>
        <AiEngineDetailPanel
          draft={draft}
          engine={selectedAiEngine}
          saving={saving}
          setDrafts={setAiEngineDrafts}
          onActivate={(engineId) => void handleAiEngineSubmit(engineId, { activate: true })}
          onSave={(engineId) => void handleAiEngineSubmit(engineId, aiEngineUpdatePayload(aiEngineDrafts[engineId] ?? draft))}
        />

        <DetailPanel title="Saved Files" icon={Settings}>
          <DetailPaths paths={aiEngines?.saved_paths} />
        </DetailPanel>
      </>
    );
  }

  function renderSettingsDetail(): ReactNode {
    if (section === "ai-engines") {
      return (
        <aside className="space-y-4">
          {renderAiEngineDetail()}
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
                <Status label="Source" value={selectedRepository.provider} />
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

    return (
      <aside className="space-y-4">
        <EmptyDetail>Select an item to inspect its settings.</EmptyDetail>
      </aside>
    );
  }

  if (loading) return <LoadingState />;
  const ActiveIcon = activeGroup.icon;

  if (section === "ai-engines") {
    return (
      <section className="space-y-3">
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

        <AiEnginesSection
          detail={renderAiEngineDetail()}
          form={form}
          aiEngines={aiEngines}
          selectedId={selectedAiEngine?.id ?? selectedAiEngineId}
          saving={saving}
          setForm={setForm}
          onPolicySubmit={handleAiEnginePolicySubmit}
          onSelect={setSelectedAiEngineId}
          onActivate={(engineId) => void handleAiEngineSubmit(engineId, { activate: true })}
        />
      </section>
    );
  }

  if (section === "code-repositories") {
    return (
      <section className="space-y-3">
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

        <CodeRepositoriesSection
          dialogOpen={repositoryDialogOpen}
          form={repositoryForm}
          repositories={repositories}
          repositoryStatus={repositoryStatus}
          saving={saving}
          selectedId={selectedRepositoryId}
          setDialogOpen={setRepositoryDialogOpen}
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
      </section>
    );
  }

  if (section === "memory-backend") {
    return (
      <section className="space-y-3">
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

        <MemoryBackendSection
          form={graphitiForm}
          graphiti={graphiti}
          aiEngines={aiEngines}
          memory={memory}
          saving={saving}
          setForm={setGraphitiForm}
          onSubmit={handleGraphitiSubmit}
        />
      </section>
    );
  }

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

        </section>
      )}

	      detail={renderSettingsDetail()}
	    />
	  );
	}
