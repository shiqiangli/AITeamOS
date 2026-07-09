import { FormEvent, type Dispatch, type ReactNode, type SetStateAction, useEffect, useMemo, useState } from "react";
import {
  Activity,
  Check,
  ClipboardList,
  Copy,
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
import { ErrorState, LoadingState, Status, navigateTo } from "../../components/shared";
import { ResizableDetailLayout } from "../../components/resizable-layout";
import { RuntimeSessionReplayDetail } from "../../components/runtimeReplay";
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
  discoverTicketBackendPlaneScope,
  getTicketBackendSettings,
  getTicketBackendStatus,
  updateTicketBackendSettings,
  type TicketBackendPlaneScopeDiscovery,
  type TicketBackendSettings,
  type TicketBackendStatus,
} from "../../api/tickets";
import {
  getRuntimeExecutionSessionReplay,
  listRuntimeApprovals,
  listRuntimeExecutionSessions,
  listRuntimeExecutorConfigs,
  listRuntimeExecutors,
  reviewRuntimeExecutorApproval,
  runRuntimeExecutorApproval,
  updateRuntimeExecutorConfig,
  type RuntimeApprovalRecord,
  type RuntimeExecutionReplayResponse,
  type RuntimeExecutionSessionRecord,
  type RuntimeExecutorConfigListResponse,
  type RuntimeExecutorConfigRecord,
  type RuntimeExecutorRegistryItem,
  type RuntimeExecutorRegistryResponse,
} from "../../api/runtimeExecutors";
import { cn } from "@/lib/utils";

type SettingsSection = "ai-engines" | "runtime-executors" | "tool-connectors" | "code-repositories" | "ticket-backend" | "memory-backend";

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
  planeApiBaseUrl: string;
  planeWebBaseUrl: string;
  planeWorkspaceSlug: string;
  planeProjectId: string;
  planeApiKeyEnv: string;
  planeNamespaceStrategy: string;
  planeNamespaceLabelIds: string;
  planeStateIds: string;
  planeEmployeeAssigneeIds: string;
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

type RuntimeExecutorForm = {
  enabled: boolean;
  binary_path: string;
  working_dir: string;
  command_template: string;
  model: string;
  api_base_url: string;
  api_key_env: string;
  http_endpoint_path: string;
  mode: string;
  timeout_seconds: string;
};

interface SettingsGroup {
  key: SettingsSection;
  label: string;
  icon: typeof Settings;
}

const SECTION_GROUPS: SettingsGroup[] = [
  { key: "ai-engines", label: "AI Engines", icon: SlidersHorizontal },
  { key: "runtime-executors", label: "Runtime Executors", icon: GitBranch },
  { key: "tool-connectors", label: "Tool Connectors", icon: Plug },
  { key: "code-repositories", label: "Code Repositories", icon: FolderGit2 },
  { key: "ticket-backend", label: "Ticket Backend", icon: ClipboardList },
  { key: "memory-backend", label: "Memory Backend", icon: Database },
];

const SECTION_DESCRIPTIONS: Record<SettingsSection, string> = {
  "ai-engines": "Model and agent backends that Clara and Employees use to think and execute.",
  "runtime-executors": "Agent runtime adapters used through ExecutionRequest and ExecutionResult governance boundaries.",
  "tool-connectors": "External tool sources, including MCP servers and adapter-backed integrations.",
  "code-repositories": "Product and regression repositories that ground code-aware work.",
  "ticket-backend": "Ticket source of truth and adapter targets for work ledgers.",
  "memory-backend": "Long-term memory backend configuration for approved memory assets.",
};

const LIVE_PROVIDER_READINESS_SMOKE_COMMAND = "python scripts/live_provider_readiness_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-readiness-smoke.json";
const PLANE_ACTION_SMOKE_COMMAND = "python scripts/plane_ticket_action_smoke.py --workspace-dir . --source-run-id plan-v8-plane-action-smoke --output .aiteamos/artifacts/plan_v8/track-c-plane-ticket-action-smoke.json";
const LIVE_DOGFOOD_SOAK_COMMAND = "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --output .aiteamos/artifacts/plan_v8/track-c-live-soak-completed.json";

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
    planeApiBaseUrl: settings.plane_api_base_url || "https://api.plane.so",
    planeWebBaseUrl: settings.plane_web_base_url || "https://app.plane.so",
    planeWorkspaceSlug: settings.plane_workspace_slug || "",
    planeProjectId: settings.plane_project_id || "",
    planeApiKeyEnv: settings.plane_api_key_env || "PLANE_API_KEY",
    planeNamespaceStrategy: settings.plane_namespace_strategy || "label",
    planeNamespaceLabelIds: JSON.stringify(settings.plane_namespace_label_ids ?? {}, null, 2),
    planeStateIds: JSON.stringify(settings.plane_state_ids ?? {}, null, 2),
    planeEmployeeAssigneeIds: JSON.stringify(settings.plane_employee_assignee_ids ?? {}, null, 2),
  };
}

function parseRecordDraft(value: string, label: string): Record<string, string> {
  const trimmed = value.trim();
  if (!trimmed) return {};
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    throw new Error(`${label} must be valid JSON.`);
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON object.`);
  }
  return Object.fromEntries(
    Object.entries(parsed).map(([key, entry]) => [key, String(entry)]).filter(([key, entry]) => key && entry),
  );
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

function runtimeExecutorToForm(record?: RuntimeExecutorConfigRecord | null): RuntimeExecutorForm {
  return {
    enabled: record?.enabled ?? true,
    binary_path: record?.binary_path ?? "",
    working_dir: record?.working_dir ?? "",
    command_template: record?.command_template ?? "",
    model: record?.model ?? "",
    api_base_url: record?.api_base_url ?? "",
    api_key_env: record?.api_key_env ?? "",
    http_endpoint_path: record?.http_endpoint_path ?? "",
    mode: record?.mode ?? "",
    timeout_seconds: record?.timeout_seconds ? String(record.timeout_seconds) : "",
  };
}

function runtimeExecutorPayload(form: RuntimeExecutorForm) {
  return {
    enabled: form.enabled,
    binary_path: form.binary_path,
    working_dir: form.working_dir,
    command_template: form.command_template,
    model: form.model,
    api_base_url: form.api_base_url,
    api_key_env: form.api_key_env,
    http_endpoint_path: form.http_endpoint_path,
    mode: form.mode,
    timeout_seconds: form.timeout_seconds ? Number(form.timeout_seconds) : null,
  };
}

function statusVariant(status: string): "default" | "secondary" | "warning" | "success" | "danger" | "outline" {
  if (status === "ready" || status === "configured" || status === "active" || status === "available" || status === "local") {
    return "success";
  }
  if (status === "planned" || status === "held" || status === "setup_blocked" || status === "incomplete") return "warning";
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

function shortRef(value?: string | null, fallback = "-"): string {
  const text = String(value ?? "").trim();
  if (!text) return fallback;
  return text.length > 44 ? `${text.slice(0, 20)}...${text.slice(-18)}` : text;
}

async function copyTextToClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function asRecordArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(asRecord).filter((item) => Object.keys(item).length > 0) : [];
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function numberValue(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function runtimeRefCount(session: RuntimeExecutionSessionRecord): string {
  return [
    `${session.ticket_refs.length} ticket`,
    `${session.memory_refs.length} memory`,
    `${session.context_refs.length} context`,
    `${session.approval_refs.length} approval`,
  ].join(" / ");
}

function runtimeToolEventLabel(event: Record<string, unknown>): string {
  return String(event.tool_name || event.event || "tool_event");
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

function SettingsCommandRow({
  command,
  copied,
  label,
  onCopy,
}: {
  command: string;
  copied: boolean;
  label: string;
  onCopy: () => void;
}) {
  return (
    <div className="flex min-w-0 items-center gap-2 rounded-md border bg-background px-3 py-2">
      <code className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap font-mono text-xs" title={command}>{command}</code>
      <Button
        type="button"
        size="icon"
        variant="outline"
        className="h-7 w-7 shrink-0"
        aria-label={copied ? `${label} command copied` : `Copy ${label} command`}
        title="Copy command"
        onClick={onCopy}
      >
        {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      </Button>
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

function RuntimeExecutorsSection({
  approvals,
  configs,
  executors,
  form,
  sessions,
  saving,
  selectedId,
  setForm,
  onSelect,
  onReviewApproval,
  onRunApproval,
  onSubmit,
}: {
  approvals: RuntimeApprovalRecord[];
  configs: RuntimeExecutorConfigListResponse | null;
  executors: RuntimeExecutorRegistryResponse | null;
  form: RuntimeExecutorForm;
  sessions: RuntimeExecutionSessionRecord[];
  saving: boolean;
  selectedId: string;
  setForm: Dispatch<SetStateAction<RuntimeExecutorForm>>;
  onSelect: (executorId: string) => void;
  onReviewApproval: (approval: RuntimeApprovalRecord, status: "approved" | "rejected") => void;
  onRunApproval: (approval: RuntimeApprovalRecord) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const items = executors?.executors ?? [];
  const selected = items.find((item) => item.executor_id === selectedId) ?? items[0] ?? null;
  const readyCount = items.filter((item) => item.status === "ready").length;
  const blockedCount = executors?.blockers?.length ?? items.filter((item) => item.status === "setup_blocked").length;
  const savedPaths = configs?.saved_paths ?? {};
  const selectedApprovals = selected ? approvals.filter((approval) => approval.executor_id === selected.executor_id).slice(0, 6) : [];
  const selectedSessions = selected ? sessions.filter((session) => session.executor_id === selected.executor_id).slice(0, 6) : [];
  const pendingApprovalCount = approvals.filter((approval) => approval.status === "requested").length;
  const [sessionReplay, setSessionReplay] = useState<RuntimeExecutionReplayResponse | null>(null);
  const [sessionReplayKey, setSessionReplayKey] = useState("");
  const [sessionReplayLoading, setSessionReplayLoading] = useState(false);
  const [sessionReplayError, setSessionReplayError] = useState("");

  useEffect(() => {
    setSessionReplay(null);
    setSessionReplayKey("");
    setSessionReplayError("");
  }, [selected?.executor_id]);

  async function openSessionReplay(sessionKey: string) {
    if (!sessionKey || sessionReplayLoading) return;
    setSessionReplayKey(sessionKey);
    setSessionReplayLoading(true);
    setSessionReplayError("");
    try {
      const replay = await getRuntimeExecutionSessionReplay(sessionKey);
      setSessionReplay(replay);
    } catch (err) {
      setSessionReplay(null);
      setSessionReplayError(err instanceof Error ? err.message : "Failed to load execution replay");
    } finally {
      setSessionReplayLoading(false);
    }
  }

  return (
    <div className="grid min-h-[28rem] gap-3 xl:h-[calc(100vh-20rem)] xl:grid-cols-[minmax(20rem,0.9fr)_minmax(26rem,1.1fr)]">
      <section className="flex min-h-0 min-w-0 flex-col rounded-md border bg-background">
        <div className="grid gap-2 border-b p-3 sm:grid-cols-4">
          <SummaryMetric label="Executors" value={items.length} />
          <SummaryMetric label="Ready" value={readyCount} tone={readyCount > 0 ? "ok" : "warn"} />
          <SummaryMetric label="Blockers" value={blockedCount} tone={blockedCount === 0 ? "ok" : "warn"} />
          <SummaryMetric label="Approvals" value={pendingApprovalCount} tone={pendingApprovalCount === 0 ? "ok" : "warn"} />
        </div>
        <div className="min-h-0 flex-1 divide-y overflow-y-auto">
          {items.length === 0 ? (
            <div className="p-4 text-sm text-muted-foreground">No runtime executors are registered.</div>
          ) : items.map((executor) => {
            const selectedRow = selected?.executor_id === executor.executor_id;
            return (
              <button
                key={executor.executor_id}
                type="button"
                onClick={() => onSelect(executor.executor_id)}
                className={cn(
                  "grid w-full gap-2 px-3 py-2.5 text-left transition-colors",
                  selectedRow ? "bg-primary/10" : "hover:bg-muted/60",
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate font-medium">{executor.display_name}</div>
                    <div className="mt-1 truncate text-xs text-muted-foreground">{executor.detail || executor.executor_id}</div>
                  </div>
                  <Badge variant={statusVariant(executor.status)}>{executor.status.replace(/_/g, " ")}</Badge>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {executor.capabilities.slice(0, 4).map((capability) => (
                    <Badge key={`${executor.executor_id}-${capability}`} variant="secondary">{capability}</Badge>
                  ))}
                  {executor.capabilities.length > 4 && <Badge variant="secondary">+{executor.capabilities.length - 4}</Badge>}
                </div>
              </button>
            );
          })}
        </div>
      </section>

      <aside className="min-h-0 min-w-0 space-y-3 overflow-y-auto pr-1">
        <DetailPanel title="Runtime Executor Config" icon={GitBranch}>
          {selected ? (
            <form onSubmit={onSubmit} className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h3 className="text-sm font-semibold">{selected.display_name}</h3>
                  <p className="mt-1 text-xs text-muted-foreground">{selected.executor_id}</p>
                </div>
                <Badge variant={statusVariant(selected.status)}>{selected.status.replace(/_/g, " ")}</Badge>
              </div>
              <label className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm">
                <span>Enabled</span>
                <input
                  aria-label="Runtime executor enabled"
                  type="checkbox"
                  checked={form.enabled}
                  onChange={(event) => setForm((current) => ({ ...current, enabled: event.target.checked }))}
                  className="h-4 w-4"
                />
              </label>
              <div className="grid gap-3 md:grid-cols-2">
                <label className="block space-y-1">
                  <span className="text-xs uppercase text-muted-foreground">Binary path</span>
                  <input
                    aria-label="Runtime binary path"
                    value={form.binary_path}
                    onChange={(event) => setForm((current) => ({ ...current, binary_path: event.target.value }))}
                    placeholder="/usr/local/bin/claude-code-compatible"
                    className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  />
                </label>
                <label className="block space-y-1">
                  <span className="text-xs uppercase text-muted-foreground">Working dir</span>
                  <input
                    aria-label="Runtime working dir"
                    value={form.working_dir}
                    onChange={(event) => setForm((current) => ({ ...current, working_dir: event.target.value }))}
                    placeholder="/home/me/project"
                    className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  />
                </label>
                <label className="block space-y-1">
                  <span className="text-xs uppercase text-muted-foreground">Model</span>
                  <input
                    aria-label="Runtime model"
                    value={form.model}
                    onChange={(event) => setForm((current) => ({ ...current, model: event.target.value }))}
                    placeholder="deepseek-chat or gpt-5-nano"
                    className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  />
                </label>
                <label className="block space-y-1">
                  <span className="text-xs uppercase text-muted-foreground">API base URL</span>
                  <input
                    aria-label="Runtime API base URL"
                    value={form.api_base_url}
                    onChange={(event) => setForm((current) => ({ ...current, api_base_url: event.target.value }))}
                    placeholder="https://api.deepseek.com"
                    className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  />
                </label>
                <label className="block space-y-1">
                  <span className="text-xs uppercase text-muted-foreground">API key env</span>
                  <input
                    aria-label="Runtime API key env"
                    value={form.api_key_env}
                    onChange={(event) => setForm((current) => ({ ...current, api_key_env: event.target.value }))}
                    placeholder="DEEPSEEK_API_KEY"
                    className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  />
                </label>
                <label className="block space-y-1">
                  <span className="text-xs uppercase text-muted-foreground">HTTP endpoint path</span>
                  <input
                    aria-label="Runtime HTTP endpoint path"
                    value={form.http_endpoint_path}
                    onChange={(event) => setForm((current) => ({ ...current, http_endpoint_path: event.target.value }))}
                    placeholder="/agent/inspect"
                    className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  />
                </label>
                <label className="block space-y-1 md:col-span-2">
                  <span className="text-xs uppercase text-muted-foreground">Command template</span>
                  <input
                    aria-label="Runtime command template"
                    value={form.command_template}
                    onChange={(event) => setForm((current) => ({ ...current, command_template: event.target.value }))}
                    placeholder="{binary}"
                    className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  />
                </label>
                <label className="block space-y-1">
                  <span className="text-xs uppercase text-muted-foreground">Mode</span>
                  <input
                    aria-label="Runtime mode"
                    value={form.mode}
                    onChange={(event) => setForm((current) => ({ ...current, mode: event.target.value }))}
                    placeholder="non_destructive_inspect_and_report"
                    className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  />
                </label>
                <label className="block space-y-1">
                  <span className="text-xs uppercase text-muted-foreground">Timeout seconds</span>
                  <input
                    aria-label="Runtime timeout seconds"
                    type="number"
                    value={form.timeout_seconds}
                    onChange={(event) => setForm((current) => ({ ...current, timeout_seconds: event.target.value }))}
                    placeholder="120"
                    className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  />
                </label>
              </div>
              <Button type="submit" disabled={saving}>
                <Save className="h-4 w-4" />
                {saving ? "Saving" : "Save runtime executor"}
              </Button>
            </form>
          ) : (
            <EmptyDetail>Select a runtime executor to configure.</EmptyDetail>
          )}
        </DetailPanel>

        <DetailPanel title="Governance Boundary" icon={Activity}>
          {selected ? (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-2">
                {selected.setup_required.length ? selected.setup_required.map((item) => (
                  <Badge key={`${selected.executor_id}-setup-${item}`} variant="warning">{item}</Badge>
                )) : <Badge variant="success">setup clear</Badge>}
              </div>
              <div className="flex flex-wrap gap-2">
                {selected.capabilities.map((capability) => (
                  <Badge key={`${selected.executor_id}-cap-${capability}`} variant="outline">{capability}</Badge>
                ))}
              </div>
              <DetailPaths paths={savedPaths} />
            </div>
          ) : (
            <EmptyDetail>No runtime executor selected.</EmptyDetail>
          )}
        </DetailPanel>

        <DetailPanel title="Review Queue" icon={KeyRound}>
          {selected ? (
            <div className="space-y-3">
              {selectedApprovals.length === 0 ? (
                <EmptyDetail>No approval records for this executor.</EmptyDetail>
              ) : (
                <div className="divide-y rounded-md border">
                  {selectedApprovals.map((approval) => (
                    <div key={approval.id} className="space-y-2 px-3 py-2 text-sm">
                      <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
                        <span className="truncate font-medium" title={approval.id}>{approval.id}</span>
                        <Badge variant={statusVariant(approval.status)}>{approval.status}</Badge>
                      </div>
                      <div className="grid gap-1 text-xs text-muted-foreground">
                        <span className="truncate">Ticket: {approval.ticket_id || "-"}</span>
                        <span className="truncate">Capability: {approval.required_capability || "-"}</span>
                        <span className="truncate">Risk: {approval.risk_level || "-"}</span>
                        <span className="truncate" title={approval.checkpoint_ref}>Checkpoint: {shortRef(approval.checkpoint_ref)}</span>
                        <span className="truncate" title={approval.source_state_ref}>State: {shortRef(approval.source_state_ref)}</span>
                        <span className="line-clamp-2">Reason: {approval.reason || "-"}</span>
                      </div>
                      <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                        <span>Last run: {approval.last_run_status || "-"}</span>
                        <span>Runs: {approval.run_history.length}</span>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {approval.status === "requested" && (
                          <>
                            <Button
                              type="button"
                              size="sm"
                              disabled={saving}
                              onClick={() => onReviewApproval(approval, "approved")}
                            >
                              Approve
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              disabled={saving}
                              onClick={() => onReviewApproval(approval, "rejected")}
                            >
                              Reject
                            </Button>
                          </>
                        )}
                        {approval.status === "approved" && (
                          <Button
                            type="button"
                            size="sm"
                            disabled={saving}
                            onClick={() => onRunApproval(approval)}
                          >
                            Resume
                          </Button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <EmptyDetail>No runtime executor selected.</EmptyDetail>
          )}
        </DetailPanel>

        <DetailPanel title="Execution Sessions" icon={Database}>
          {selected ? (
            <div className="space-y-3">
              {selectedSessions.length === 0 ? (
                <EmptyDetail>No execution sessions recorded for this executor.</EmptyDetail>
              ) : (
                <div className="divide-y rounded-md border">
                  {selectedSessions.map((session) => (
                    <div key={session.session_key} className="space-y-2 px-3 py-2 text-sm">
                      <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
                        <span className="truncate font-medium" title={session.last_request_id}>{session.last_request_id || session.session_key}</span>
                        <Badge variant={statusVariant(session.status)}>{session.status || "unknown"}</Badge>
                      </div>
                      <div className="grid gap-1 text-xs text-muted-foreground">
                        <span className="truncate" title={session.checkpoint_ref}>Checkpoint: {shortRef(session.checkpoint_ref)}</span>
                        <span className="truncate" title={session.trace_ref}>Trace: {shortRef(session.trace_ref)}</span>
                        <span className="truncate">Ticket: {session.ticket_id || "-"}</span>
                        <span>{runtimeRefCount(session)}</span>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Badge variant="outline">{session.tool_event_count} tool events</Badge>
                        <Badge variant="secondary">{session.employee_id || "employee"} / {session.thread_id || "runtime"}</Badge>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          disabled={sessionReplayLoading && sessionReplayKey === session.session_key}
                          onClick={() => void openSessionReplay(session.session_key)}
                        >
                          <Activity className="h-4 w-4" />
                          Replay
                        </Button>
                      </div>
                      {session.tool_events.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                          {session.tool_events.slice(0, 4).map((event, index) => (
                            <Badge key={`${session.session_key}-event-${index}`} variant="outline">
                              {runtimeToolEventLabel(event)}
                            </Badge>
                          ))}
                          {session.tool_events.length > 4 && <Badge variant="secondary">+{session.tool_events.length - 4}</Badge>}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {(sessionReplay || sessionReplayLoading || sessionReplayError) && (
                <RuntimeSessionReplayDetail
                  error={sessionReplayError}
                  loading={sessionReplayLoading}
                  replay={sessionReplay}
                />
              )}
            </div>
          ) : (
            <EmptyDetail>No runtime executor selected.</EmptyDetail>
          )}
        </DetailPanel>
      </aside>
    </div>
  );
}

function TicketBackendSection({
  form,
  saving,
  settings,
  status,
  setForm,
  onApplyRepositoryScope,
  onConfigureRepositoryScope,
  onSubmit,
}: {
  form: TicketBackendForm;
  saving: boolean;
  settings: TicketBackendSettings | null;
  status: TicketBackendStatus | null;
  setForm: Dispatch<SetStateAction<TicketBackendForm>>;
  onApplyRepositoryScope: (candidate: Record<string, unknown>) => void;
  onConfigureRepositoryScope: (repositoryId: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const supportedModes = settings?.supported_modes ?? status?.supported_modes ?? [
    {
      id: "plane",
      label: "Plane",
      status: "ready",
      description: "Plane-backed Ticket fact source.",
    },
  ];
  const planeSetup = asRecord(status?.plane_setup);
  const releaseTarget = asRecord(status?.release_target);
  const releaseTargetBlockers = Array.isArray(releaseTarget.blockers) ? releaseTarget.blockers.map(String).filter(Boolean) : [];
  const releaseTargetSetupRequired = Array.isArray(releaseTarget.setup_required) ? releaseTarget.setup_required.map(String).filter(Boolean) : [];
  const setupRequired = Array.isArray(planeSetup.setup_required) ? planeSetup.setup_required.map(String).filter(Boolean) : [];
  const planeScopeCandidates = asRecordArray(planeSetup.code_repository_scope_candidates);
  const planeScopeMissing = asRecordArray(planeSetup.code_repository_scope_missing);
  const planeScopeCandidateCount = numberValue(planeSetup.code_repository_scope_candidate_count, planeScopeCandidates.length);
  const planeScopeMissingCount = numberValue(planeSetup.code_repository_scope_missing_count, planeScopeMissing.length);
  const planeScopeTotal = planeScopeCandidateCount + planeScopeMissingCount;
  const planeSelected = Boolean(planeSetup.selected);
  const planeWorkspaceConfigured = Boolean(planeSetup.workspace_configured);
  const planeProjectConfigured = Boolean(planeSetup.project_configured);
  const planeApiKeyConfigured = Boolean(planeSetup.api_key_configured);
  const [copiedCommandKey, setCopiedCommandKey] = useState("");

  function applyRepositoryScope(candidate: Record<string, unknown>) {
    const workspace = stringValue(candidate.plane_workspace_slug);
    const project = stringValue(candidate.plane_project_id);
    if (!workspace || !project) return;
    setForm((current) => ({
      ...current,
      mode: "plane",
      planeWorkspaceSlug: workspace,
      planeProjectId: project,
    }));
  }

  async function handleCopyCommand(key: string, command: string) {
    await copyTextToClipboard(command);
    setCopiedCommandKey(key);
  }

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
              <span className="text-xs uppercase text-muted-foreground">Legacy projection file</span>
              <input
                aria-label="Legacy projection file"
                value={form.localFilePath}
                onChange={(event) => setForm((current) => ({ ...current, localFilePath: event.target.value }))}
                placeholder=".aiteamos/tickets/index.json"
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>
          </div>

          {Object.keys(releaseTarget).length ? (
            <div className="rounded-md border bg-muted/20 px-3 py-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div className="text-xs font-medium uppercase text-muted-foreground">Plan v8 release target</div>
                <Badge variant={stringValue(releaseTarget.status) === "ready" ? "success" : "warning"}>
                  {compactStatus(stringValue(releaseTarget.status))}
                </Badge>
              </div>
              <div className="text-xs leading-5 text-muted-foreground">
                {stringValue(releaseTarget.detail)}
              </div>
              {releaseTargetBlockers.length ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {releaseTargetBlockers.slice(0, 8).map((blocker) => (
                    <Badge key={`ticket-backend-release-target-${blocker}`} variant="outline">
                      {blocker}
                    </Badge>
                  ))}
                </div>
              ) : null}
              {releaseTargetSetupRequired.length ? (
                <div className="mt-2 text-xs leading-5 text-muted-foreground">
                  Setup required: {releaseTargetSetupRequired.slice(0, 6).join(", ")}
                </div>
              ) : null}
            </div>
          ) : null}

          <div className="rounded-md border bg-muted/20 px-3 py-3">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div className="text-xs font-medium uppercase text-muted-foreground">Plane setup preflight</div>
              <div className="flex flex-wrap gap-2">
                <Badge variant={statusVariant(stringValue(planeSetup.status))}>{compactStatus(stringValue(planeSetup.status))}</Badge>
                <Badge variant={planeScopeCandidateCount ? "success" : statusVariant(stringValue(planeSetup.code_repository_scope_status))}>
                  scope {compactStatus(stringValue(planeSetup.code_repository_scope_status))}
                </Badge>
                {planeScopeTotal ? <Badge variant="outline">{planeScopeCandidateCount}/{planeScopeTotal} scope candidates</Badge> : null}
              </div>
            </div>

            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              <SummaryMetric label="Mode" value={stringValue(planeSetup.active_mode) || form.mode} tone={planeSelected ? "ok" : "warn"} />
              <SummaryMetric label="Workspace" value={planeWorkspaceConfigured ? "set" : "missing"} tone={planeWorkspaceConfigured ? "ok" : "warn"} />
              <SummaryMetric label="Project" value={planeProjectConfigured ? "set" : "missing"} tone={planeProjectConfigured ? "ok" : "warn"} />
              <SummaryMetric label="API key" value={planeApiKeyConfigured ? "set" : "missing"} tone={planeApiKeyConfigured ? "ok" : "warn"} />
            </div>

            {setupRequired.length ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {setupRequired.slice(0, 6).map((item) => (
                  <Badge key={`ticket-backend-plane-setup-${item}`} variant="outline">{item}</Badge>
                ))}
              </div>
            ) : null}

            {planeScopeCandidates.length ? (
              <div className="mt-3 grid gap-2">
                {planeScopeCandidates.slice(0, 3).map((candidate) => {
                  const repositoryId = stringValue(candidate.repository_id) || stringValue(candidate.repository_name);
                  return (
                    <div key={`ticket-backend-plane-candidate-${repositoryId}`} className="flex flex-wrap items-center justify-between gap-2 rounded-md border bg-background px-3 py-2">
                      <div className="min-w-0">
                        <div className="text-sm font-medium">{stringValue(candidate.repository_name) || repositoryId}</div>
                        <div className="mt-1 flex flex-wrap gap-2">
                          <Badge variant="outline">{stringValue(candidate.plane_workspace_slug)}</Badge>
                          <Badge variant="outline">{stringValue(candidate.plane_project_id)}</Badge>
                          <Badge variant={statusVariant(stringValue(candidate.status))}>{compactStatus(stringValue(candidate.status))}</Badge>
                        </div>
                      </div>
                      <Button type="button" size="sm" variant="outline" onClick={() => applyRepositoryScope(candidate)}>
                        Use scope
                      </Button>
                      <Button type="button" size="sm" disabled={saving} onClick={() => onApplyRepositoryScope(candidate)}>
                        <Save className="h-4 w-4" />
                        Apply scope
                      </Button>
                    </div>
                  );
                })}
              </div>
            ) : planeScopeMissing.length ? (
              <div className="mt-3 grid gap-2">
                {planeScopeMissing.slice(0, 3).map((candidate) => {
                  const repositoryId = stringValue(candidate.repository_id) || stringValue(candidate.repository_name);
                  const workspaceConfigured = Boolean(candidate.workspace_configured);
                  const projectConfigured = Boolean(candidate.project_configured);
                  return (
                    <div key={`ticket-backend-plane-missing-${repositoryId}`} className="rounded-md border bg-background px-3 py-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="text-sm font-medium">{stringValue(candidate.repository_name) || repositoryId}</div>
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="warning">scope incomplete</Badge>
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            disabled={!repositoryId}
                            onClick={() => onConfigureRepositoryScope(repositoryId)}
                          >
                            <Settings className="h-4 w-4" />
                            Edit scope
                          </Button>
                        </div>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <Badge variant={workspaceConfigured ? "success" : "warning"}>workspace {workspaceConfigured ? "set" : "missing"}</Badge>
                        <Badge variant={projectConfigured ? "success" : "warning"}>project {projectConfigured ? "set" : "missing"}</Badge>
                        <Badge variant={statusVariant(stringValue(candidate.status))}>{compactStatus(stringValue(candidate.status))}</Badge>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : null}

            <div className="mt-3 border-t pt-3">
              <div className="mb-2 text-[10px] font-medium uppercase text-muted-foreground">Provider readiness smoke</div>
              <SettingsCommandRow
                command={LIVE_PROVIDER_READINESS_SMOKE_COMMAND}
                copied={copiedCommandKey === "live-provider-readiness-smoke"}
                label="Provider readiness smoke"
                onCopy={() => void handleCopyCommand("live-provider-readiness-smoke", LIVE_PROVIDER_READINESS_SMOKE_COMMAND)}
              />
            </div>
            <div className="mt-3 border-t pt-3">
              <div className="mb-2 text-[10px] font-medium uppercase text-muted-foreground">Plane action smoke</div>
              <SettingsCommandRow
                command={PLANE_ACTION_SMOKE_COMMAND}
                copied={copiedCommandKey === "plane-action-smoke"}
                label="Plane action smoke"
                onCopy={() => void handleCopyCommand("plane-action-smoke", PLANE_ACTION_SMOKE_COMMAND)}
              />
            </div>
            <div className="mt-3 border-t pt-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div className="text-[10px] font-medium uppercase text-muted-foreground">Live dogfood gate</div>
                <Badge variant="warning">mutation gate</Badge>
              </div>
              <SettingsCommandRow
                command={LIVE_DOGFOOD_SOAK_COMMAND}
                copied={copiedCommandKey === "live-dogfood-soak"}
                label="Live dogfood soak"
                onCopy={() => void handleCopyCommand("live-dogfood-soak", LIVE_DOGFOOD_SOAK_COMMAND)}
              />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">Plane API base URL</span>
              <input
                aria-label="Plane API base URL"
                value={form.planeApiBaseUrl}
                onChange={(event) => setForm((current) => ({ ...current, planeApiBaseUrl: event.target.value }))}
                placeholder="https://api.plane.so"
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">Plane web base URL</span>
              <input
                aria-label="Plane web base URL"
                value={form.planeWebBaseUrl}
                onChange={(event) => setForm((current) => ({ ...current, planeWebBaseUrl: event.target.value }))}
                placeholder="https://app.plane.so"
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">Plane workspace slug</span>
              <input
                aria-label="Plane workspace slug"
                value={form.planeWorkspaceSlug}
                onChange={(event) => setForm((current) => ({ ...current, planeWorkspaceSlug: event.target.value }))}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">Plane project id</span>
              <input
                aria-label="Plane project id"
                value={form.planeProjectId}
                onChange={(event) => setForm((current) => ({ ...current, planeProjectId: event.target.value }))}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">Plane API key env</span>
              <input
                aria-label="Plane API key env"
                value={form.planeApiKeyEnv}
                onChange={(event) => setForm((current) => ({ ...current, planeApiKeyEnv: event.target.value }))}
                placeholder="PLANE_API_KEY"
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">Plane namespace strategy</span>
              <Select
                aria-label="Plane namespace strategy"
                value={form.planeNamespaceStrategy}
                onChange={(event) => setForm((current) => ({ ...current, planeNamespaceStrategy: event.target.value }))}
              >
                <option value="label">Label</option>
              </Select>
            </label>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">Namespace labels</span>
              <textarea
                aria-label="Plane namespace label mapping"
                value={form.planeNamespaceLabelIds}
                onChange={(event) => setForm((current) => ({ ...current, planeNamespaceLabelIds: event.target.value }))}
                className="min-h-24 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">State mapping</span>
              <textarea
                aria-label="Plane state mapping"
                value={form.planeStateIds}
                onChange={(event) => setForm((current) => ({ ...current, planeStateIds: event.target.value }))}
                className="min-h-24 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs uppercase text-muted-foreground">Employee assignees</span>
              <textarea
                aria-label="Plane Employee assignee mapping"
                value={form.planeEmployeeAssigneeIds}
                onChange={(event) => setForm((current) => ({ ...current, planeEmployeeAssigneeIds: event.target.value }))}
                className="min-h-24 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
  planeScopeDiscovery,
  planeScopeDiscoveryLoading,
  repositories,
  repositoryStatus,
  saving,
  selectedId,
  setDialogOpen,
  setForm,
  onDelete,
  onDiscoverPlaneScope,
  onNew,
  onOpenTicketBackend,
  onSelect,
  onSubmit,
}: {
  dialogOpen: boolean;
  form: RepositoryForm;
  planeScopeDiscovery: TicketBackendPlaneScopeDiscovery | null;
  planeScopeDiscoveryLoading: boolean;
  repositories: CodeRepository[];
  repositoryStatus: CodeRepositoryStatus | null;
  saving: boolean;
  selectedId: string;
  setDialogOpen: Dispatch<SetStateAction<boolean>>;
  setForm: Dispatch<SetStateAction<RepositoryForm>>;
  onDelete: (repoId: string) => void;
  onDiscoverPlaneScope: () => void;
  onNew: () => void;
  onOpenTicketBackend: () => void;
  onSelect: (repository: CodeRepository) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const selectedRepository = repositories.find((repository) => repository.id === selectedId) ?? null;
  const enabledCount = repositoryStatus?.enabled_count ?? repositories.filter((repository) => repository.enabled).length;
  const readyCount = repositoryStatus?.ready_count ?? repositories.filter((repository) => repository.status === "ready").length;
  const localCount = repositoryStatus?.local_count ?? repositories.filter((repository) => repository.provider === "local").length;
  const remoteCount = repositoryStatus?.remote_count ?? Math.max(repositories.length - localCount, 0);
  const enabledRepositories = repositories.filter((repository) => repository.enabled);
  const fallbackPlaneScopeCandidates = enabledRepositories.filter((repository) => repository.plane_workspace_slug && repository.plane_project_id);
  const fallbackPlaneScopeMissing = enabledRepositories.filter((repository) => !repository.plane_workspace_slug || !repository.plane_project_id);
  const hasPlaneScopeContract = Boolean(repositoryStatus?.plane_scope_status);
  const planeScopeCandidates: Record<string, unknown>[] = hasPlaneScopeContract
    ? asRecordArray(repositoryStatus?.plane_scope_candidates)
    : fallbackPlaneScopeCandidates.map((repository) => ({
      repository_id: repository.id,
      repository_name: repository.name,
      provider: repository.provider,
      status: repository.status,
      plane_workspace_slug: repository.plane_workspace_slug,
      plane_project_id: repository.plane_project_id,
    }));
  const planeScopeMissing: Record<string, unknown>[] = hasPlaneScopeContract
    ? asRecordArray(repositoryStatus?.plane_scope_missing)
    : fallbackPlaneScopeMissing.map((repository) => ({
      repository_id: repository.id,
      repository_name: repository.name,
      provider: repository.provider,
      status: repository.status,
      workspace_configured: Boolean(repository.plane_workspace_slug),
      project_configured: Boolean(repository.plane_project_id),
    }));
  const planeScopeSuggestions = asRecordArray(repositoryStatus?.plane_scope_suggestions);
  const primaryPlaneScopeSuggestion = planeScopeSuggestions[0] ?? null;
  const discoveredPlaneScopeSuggestions = asRecordArray(planeScopeDiscovery?.suggestions);
  const primaryDiscoveredPlaneScopeSuggestion = discoveredPlaneScopeSuggestions[0] ?? null;
  const primaryPrefillScopeSuggestion = primaryPlaneScopeSuggestion ?? primaryDiscoveredPlaneScopeSuggestion;
  const primaryPrefillScopeLabel = primaryPlaneScopeSuggestion ? "Ticket Backend scope" : "Plane discovery scope";
  const planeScopeCandidateCount = repositoryStatus?.plane_scope_candidate_count ?? fallbackPlaneScopeCandidates.length;
  const planeScopeMissingCount = repositoryStatus?.plane_scope_missing_count ?? fallbackPlaneScopeMissing.length;
  const planeScopeStatus = repositoryStatus?.plane_scope_status || (fallbackPlaneScopeCandidates.length ? "available" : fallbackPlaneScopeMissing.length ? "incomplete" : "missing");
  const planeScopeDetail = repositoryStatus?.plane_scope_detail || "Plane workspace/project scope decides whether the Ticket Backend can be switched to Plane safely.";
  const planeScopeTotal = planeScopeCandidateCount + planeScopeMissingCount || enabledRepositories.length;
  const planeScopeRows = planeScopeCandidates.length ? planeScopeCandidates : planeScopeMissing;

  function openNewRepository() {
    onNew();
    setDialogOpen(true);
  }

  function openRepositoryConfig(repository: CodeRepository) {
    onSelect(repository);
    setDialogOpen(true);
  }

  function usePlaneScopeSuggestion(suggestion: Record<string, unknown>, repository?: CodeRepository | null) {
    const workspace = stringValue(suggestion.plane_workspace_slug);
    const project = stringValue(suggestion.plane_project_id);
    if (!workspace || !project) return;
    const target = repository ?? selectedRepository ?? repositories.find((item) => item.enabled) ?? null;
    if (target) {
      onSelect(target);
    } else {
      onNew();
    }
    setForm((current) => ({
      ...current,
      planeWorkspaceSlug: workspace,
      planeProjectId: project,
    }));
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
          <div className="flex items-center gap-2">
            <ClipboardList className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold">Plane Scope Preflight</h3>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{planeScopeDetail}</p>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex flex-wrap gap-2">
              <Badge variant={planeScopeCandidateCount ? "success" : planeScopeMissingCount ? "warning" : "danger"}>
                scope {compactStatus(planeScopeStatus)}
              </Badge>
              <Badge variant="outline">{planeScopeCandidateCount}/{planeScopeTotal} scope candidates</Badge>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="button" size="sm" variant="outline" disabled={planeScopeDiscoveryLoading} onClick={onDiscoverPlaneScope}>
                <RefreshCw className="h-4 w-4" />
                {planeScopeDiscoveryLoading ? "Discovering" : "Discover Plane scope"}
              </Button>
              <Button type="button" size="sm" variant="outline" onClick={onOpenTicketBackend}>
                <ClipboardList className="h-4 w-4" />
                Ticket Backend
              </Button>
            </div>
          </div>
        </div>
        <div className="grid gap-3 p-4 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
          <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-1">
            <SummaryMetric label="Scope" value={compactStatus(planeScopeStatus)} tone={planeScopeCandidateCount ? "ok" : "warn"} />
            <SummaryMetric label="Ready Scope" value={planeScopeCandidateCount} tone={planeScopeCandidateCount ? "ok" : "warn"} />
            <SummaryMetric label="Missing Scope" value={planeScopeMissingCount} tone={planeScopeMissingCount ? "warn" : "ok"} />
          </div>
          <div className="grid gap-2">
            {primaryPrefillScopeSuggestion && !planeScopeCandidateCount ? (
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border bg-muted/20 px-3 py-2">
                <div className="min-w-0">
                  <div className="text-sm font-medium">{primaryPrefillScopeLabel}</div>
                  <div className="mt-1 flex flex-wrap gap-2">
                    <Badge variant="outline">Workspace: {stringValue(primaryPrefillScopeSuggestion.plane_workspace_slug)}</Badge>
                    <Badge variant="outline">Project: {stringValue(primaryPrefillScopeSuggestion.plane_project_id)}</Badge>
                    <Badge variant={statusVariant(stringValue(primaryPrefillScopeSuggestion.status))}>
                      {compactStatus(stringValue(primaryPrefillScopeSuggestion.status))}
                    </Badge>
                  </div>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => usePlaneScopeSuggestion(primaryPrefillScopeSuggestion)}
                >
                  <Settings className="h-4 w-4" />
                  {primaryPlaneScopeSuggestion ? "Use Ticket Backend scope" : "Use discovered scope"}
                </Button>
              </div>
            ) : null}
            {planeScopeDiscovery && !primaryDiscoveredPlaneScopeSuggestion ? (
              <div className="rounded-md border bg-muted/20 px-3 py-2 text-xs leading-5 text-muted-foreground">
                Plane discovery {compactStatus(planeScopeDiscovery.status)}: {planeScopeDiscovery.detail}
              </div>
            ) : null}
            {planeScopeRows.length ? (
              planeScopeRows.slice(0, 4).map((row) => {
                const repositoryId = stringValue(row.repository_id) || stringValue(row.id);
                const repository = repositories.find((item) => item.id === repositoryId);
                const workspace = stringValue(row.plane_workspace_slug) || repository?.plane_workspace_slug || "";
                const project = stringValue(row.plane_project_id) || repository?.plane_project_id || "";
                const workspaceConfigured = "workspace_configured" in row ? Boolean(row.workspace_configured) : Boolean(workspace);
                const projectConfigured = "project_configured" in row ? Boolean(row.project_configured) : Boolean(project);
                const repositoryName = stringValue(row.repository_name) || repository?.name || repositoryId || "Repository";
                const repositoryStatusValue = stringValue(row.status) || repository?.status || "unknown";
                return (
                  <div key={`plane-scope-preflight-${repositoryId || repositoryName}`} className="flex flex-wrap items-center justify-between gap-2 rounded-md border bg-muted/20 px-3 py-2">
                    <div className="min-w-0">
                      <div className="text-sm font-medium">{repositoryName}</div>
                      <div className="mt-1 flex flex-wrap gap-2">
                        <Badge variant={workspaceConfigured ? "success" : "warning"}>
                          Workspace: {workspace || "missing"}
                        </Badge>
                        <Badge variant={projectConfigured ? "success" : "warning"}>
                          Project: {project || "missing"}
                        </Badge>
                        <Badge variant={statusVariant(repositoryStatusValue)}>{compactStatus(repositoryStatusValue)}</Badge>
                      </div>
                    </div>
                    <Button type="button" size="sm" variant="outline" disabled={!repository} onClick={() => repository && openRepositoryConfig(repository)}>
                      <Settings className="h-4 w-4" />
                      Edit scope
                    </Button>
                  </div>
                );
              })
            ) : (
              <EmptyDetail>No enabled repositories are available for Plane scope.</EmptyDetail>
            )}
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
              {primaryPrefillScopeSuggestion ? (
                <div className="rounded-md border bg-muted/20 px-3 py-2 sm:col-span-2 xl:col-span-1">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-xs font-medium uppercase text-muted-foreground">{primaryPrefillScopeLabel}</div>
                      <div className="mt-1 flex flex-wrap gap-2">
                        <Badge variant="outline">Workspace: {stringValue(primaryPrefillScopeSuggestion.plane_workspace_slug)}</Badge>
                        <Badge variant="outline">Project: {stringValue(primaryPrefillScopeSuggestion.plane_project_id)}</Badge>
                      </div>
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => usePlaneScopeSuggestion(primaryPrefillScopeSuggestion, selectedRepository)}
                    >
                      {primaryPlaneScopeSuggestion ? "Use Ticket Backend scope" : "Use discovered scope"}
                    </Button>
                  </div>
                </div>
              ) : null}
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
  const [runtimeExecutors, setRuntimeExecutors] = useState<RuntimeExecutorRegistryResponse | null>(null);
  const [runtimeExecutorConfigs, setRuntimeExecutorConfigs] = useState<RuntimeExecutorConfigListResponse | null>(null);
  const [runtimeApprovals, setRuntimeApprovals] = useState<RuntimeApprovalRecord[]>([]);
  const [runtimeExecutionSessions, setRuntimeExecutionSessions] = useState<RuntimeExecutionSessionRecord[]>([]);
  const [selectedRuntimeExecutorId, setSelectedRuntimeExecutorId] = useState("claude_code");
  const [runtimeExecutorForm, setRuntimeExecutorForm] = useState<RuntimeExecutorForm>(runtimeExecutorToForm(null));
  const [graphitiForm, setGraphitiForm] = useState<GraphitiForm>({
    enabled: false,
    graphDatabase: "neo4j",
    uri: "bolt://localhost:7687",
    user: "neo4j",
    groupId: "aiteamos",
    llmAiEngine: "openai",
  });
  const [ticketBackendForm, setTicketBackendForm] = useState<TicketBackendForm>({
    mode: "plane",
    localFilePath: ".aiteamos/tickets/index.json",
    planeApiBaseUrl: "https://api.plane.so",
    planeWebBaseUrl: "https://app.plane.so",
    planeWorkspaceSlug: "",
    planeProjectId: "",
    planeApiKeyEnv: "PLANE_API_KEY",
    planeNamespaceStrategy: "label",
    planeNamespaceLabelIds: "{}",
    planeStateIds: "{}",
    planeEmployeeAssigneeIds: "{}",
  });
  const [repositoryForm, setRepositoryForm] = useState<RepositoryForm>(emptyRepositoryForm);
  const [repositories, setRepositories] = useState<CodeRepository[]>([]);
  const [repositoryStatus, setRepositoryStatus] = useState<CodeRepositoryStatus | null>(null);
  const [planeScopeDiscovery, setPlaneScopeDiscovery] = useState<TicketBackendPlaneScopeDiscovery | null>(null);
  const [planeScopeDiscoveryLoading, setPlaneScopeDiscoveryLoading] = useState(false);
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
        loadedRuntimeExecutors,
        loadedRuntimeExecutorConfigs,
        loadedRuntimeApprovals,
        loadedRuntimeExecutionSessions,
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
        listRuntimeExecutors(),
        listRuntimeExecutorConfigs(),
        listRuntimeApprovals(),
        listRuntimeExecutionSessions(),
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
      setRuntimeExecutors(loadedRuntimeExecutors);
      setRuntimeExecutorConfigs(loadedRuntimeExecutorConfigs);
      setRuntimeApprovals(loadedRuntimeApprovals);
      setRuntimeExecutionSessions(loadedRuntimeExecutionSessions);
      setSelectedRuntimeExecutorId((current) => {
        const selected = loadedRuntimeExecutors.executors.find((executor) => executor.executor_id === current) ?? loadedRuntimeExecutors.executors[0] ?? null;
        setRuntimeExecutorForm(runtimeExecutorToForm(selected ? loadedRuntimeExecutorConfigs.executors[selected.executor_id] : null));
        return selected?.executor_id ?? "";
      });
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
        plane_api_base_url: ticketBackendForm.planeApiBaseUrl,
        plane_web_base_url: ticketBackendForm.planeWebBaseUrl,
        plane_workspace_slug: ticketBackendForm.planeWorkspaceSlug,
        plane_project_id: ticketBackendForm.planeProjectId,
        plane_api_key_env: ticketBackendForm.planeApiKeyEnv,
        plane_namespace_strategy: ticketBackendForm.planeNamespaceStrategy,
        plane_namespace_label_ids: parseRecordDraft(ticketBackendForm.planeNamespaceLabelIds, "Plane namespace labels"),
        plane_state_ids: parseRecordDraft(ticketBackendForm.planeStateIds, "Plane state mapping"),
        plane_employee_assignee_ids: parseRecordDraft(ticketBackendForm.planeEmployeeAssigneeIds, "Plane Employee assignee mapping"),
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

  async function handleApplyTicketBackendScope(candidate: Record<string, unknown>) {
    if (saving) return;
    const workspace = stringValue(candidate.plane_workspace_slug);
    const project = stringValue(candidate.plane_project_id);
    if (!workspace || !project) return;
    setSaving(true);
    setError(null);
    const nextForm: TicketBackendForm = {
      ...ticketBackendForm,
      mode: "plane",
      planeWorkspaceSlug: workspace,
      planeProjectId: project,
    };
    try {
      const updated = await updateTicketBackendSettings({
        mode: nextForm.mode,
        local_file_path: nextForm.localFilePath,
        plane_api_base_url: nextForm.planeApiBaseUrl,
        plane_web_base_url: nextForm.planeWebBaseUrl,
        plane_workspace_slug: nextForm.planeWorkspaceSlug,
        plane_project_id: nextForm.planeProjectId,
        plane_api_key_env: nextForm.planeApiKeyEnv,
        plane_namespace_strategy: nextForm.planeNamespaceStrategy,
        plane_namespace_label_ids: parseRecordDraft(nextForm.planeNamespaceLabelIds, "Plane namespace labels"),
        plane_state_ids: parseRecordDraft(nextForm.planeStateIds, "Plane state mapping"),
        plane_employee_assignee_ids: parseRecordDraft(nextForm.planeEmployeeAssigneeIds, "Plane Employee assignee mapping"),
      });
      const updatedStatus = await getTicketBackendStatus();
      setTicketBackend(updated);
      setTicketBackendForm(ticketBackendToForm(updated));
      setTicketBackendStatus(updatedStatus);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to apply repository Plane scope");
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

  async function handleDiscoverPlaneScope() {
    if (planeScopeDiscoveryLoading) return;
    setPlaneScopeDiscoveryLoading(true);
    setError(null);
    try {
      setPlaneScopeDiscovery(await discoverTicketBackendPlaneScope());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to discover Plane scope");
    } finally {
      setPlaneScopeDiscoveryLoading(false);
    }
  }

  function openRepositoryScopeConfig(repositoryId: string) {
    setSection("code-repositories");
    navigateTo("settings", "code-repositories");
    const repository = repositories.find((item) => item.id === repositoryId) ?? null;
    if (!repository) {
      setSelectedRepositoryId("");
      setRepositoryForm(emptyRepositoryForm());
      setRepositoryDialogOpen(false);
      return;
    }
    setSelectedRepositoryId(repository.id);
    setRepositoryForm(repositoryToForm(repository));
    setRepositoryDialogOpen(true);
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
      setTicketBackendStatus(await getTicketBackendStatus());
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
      setTicketBackendStatus(await getTicketBackendStatus());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete code repository");
    } finally {
      setSaving(false);
    }
  }

  async function reloadRuntimeExecutors(nextSelectedId = selectedRuntimeExecutorId) {
    const [loadedExecutors, loadedConfigs, loadedApprovals, loadedSessions] = await Promise.all([
      listRuntimeExecutors(),
      listRuntimeExecutorConfigs(),
      listRuntimeApprovals(),
      listRuntimeExecutionSessions(),
    ]);
    setRuntimeExecutors(loadedExecutors);
    setRuntimeExecutorConfigs(loadedConfigs);
    setRuntimeApprovals(loadedApprovals);
    setRuntimeExecutionSessions(loadedSessions);
    const selected = loadedExecutors.executors.find((executor) => executor.executor_id === nextSelectedId) ?? loadedExecutors.executors[0] ?? null;
    setSelectedRuntimeExecutorId(selected?.executor_id ?? "");
    setRuntimeExecutorForm(runtimeExecutorToForm(selected ? loadedConfigs.executors[selected.executor_id] : null));
  }

  function selectRuntimeExecutor(executorId: string) {
    setSelectedRuntimeExecutorId(executorId);
    setRuntimeExecutorForm(runtimeExecutorToForm(runtimeExecutorConfigs?.executors?.[executorId] ?? null));
  }

  async function handleRuntimeExecutorSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving || !selectedRuntimeExecutorId) return;
    setSaving(true);
    setError(null);
    try {
      await updateRuntimeExecutorConfig(selectedRuntimeExecutorId, runtimeExecutorPayload(runtimeExecutorForm));
      await reloadRuntimeExecutors(selectedRuntimeExecutorId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save RuntimeExecutor settings");
    } finally {
      setSaving(false);
    }
  }

  async function handleRuntimeApprovalReview(approval: RuntimeApprovalRecord, status: "approved" | "rejected") {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      await reviewRuntimeExecutorApproval(approval.executor_id, approval.id, {
        status,
        reviewer_employee_id: "clara",
        reason: status === "approved" ? "Approved from Runtime Review Queue." : "Rejected from Runtime Review Queue.",
      });
      await reloadRuntimeExecutors(selectedRuntimeExecutorId);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to ${status} runtime approval`);
    } finally {
      setSaving(false);
    }
  }

  async function handleRuntimeApprovalRun(approval: RuntimeApprovalRecord) {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      await runRuntimeExecutorApproval(approval.executor_id, approval.id, { ingest_result: true });
      await reloadRuntimeExecutors(selectedRuntimeExecutorId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to resume runtime approval");
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
      const ticketReleaseTarget = asRecord(ticketBackendStatus?.release_target);
      const ticketReleaseTargetBlockers = Array.isArray(ticketReleaseTarget.blockers) ? ticketReleaseTarget.blockers.map(String).filter(Boolean) : [];
      const projectionPath =
        ticketBackendStatus?.saved_paths?.plane_projection
        ?? ticketBackend?.saved_paths?.plane_projection
        ?? ticketBackendStatus?.local_file_path
        ?? ticketBackend?.local_file_path;
      return (
        <aside className="space-y-4">
          <DetailPanel title="Ticket Backend Status" icon={ClipboardList}>
            <div className="space-y-3">
              <Status label="Mode" value={ticketBackendStatus?.mode ?? ticketBackend?.mode ?? "-"} />
              <Status label="Status" value={compactStatus(ticketBackendStatus?.status)} tone={ticketBackendStatus?.status === "ready" ? "ok" : "warn"} />
              <Status label="Tickets" value={ticketBackendStatus?.ticket_count ?? 0} />
              <Status label="Provider" value={ticketBackendStatus?.provider || "-"} />
              <Status label="Provider refs" value={ticketBackendStatus?.provider_ref_count ?? 0} />
              {Object.keys(ticketReleaseTarget).length ? (
                <Status
                  label="Release target"
                  value={compactStatus(stringValue(ticketReleaseTarget.status))}
                  tone={stringValue(ticketReleaseTarget.status) === "ready" ? "ok" : "warn"}
                />
              ) : null}
              <div className="min-w-0">
                <div className="text-xs uppercase text-muted-foreground">Projection mirror</div>
                <div className="truncate text-sm font-medium" title={projectionPath}>
                  {projectionPath ?? "-"}
                </div>
              </div>
              {ticketBackendStatus?.setup_required?.length ? (
                <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
                  Missing setup: {ticketBackendStatus.setup_required.join(", ")}
                </div>
              ) : null}
              {ticketReleaseTargetBlockers.length ? (
                <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
                  Release blockers: {ticketReleaseTargetBlockers.join(", ")}
                </div>
              ) : null}
              {ticketBackendStatus?.mapping && Object.keys(ticketBackendStatus.mapping).length ? (
                <div className="space-y-1">
                  <div className="text-xs uppercase text-muted-foreground">Plane mapping</div>
                  <div className="space-y-1 text-xs text-muted-foreground">
                    {Object.entries(ticketBackendStatus.mapping).map(([key, value]) => (
                      <div key={key} className="flex min-w-0 justify-between gap-3 rounded-md bg-muted px-2 py-1">
                        <span className="font-medium text-foreground">{key}</span>
                        <span className="truncate" title={value}>{value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
              <div className="rounded-md bg-muted px-3 py-2 text-xs leading-5 text-muted-foreground">
                {ticketBackendStatus?.detail ?? "Plane is the target Ticket Backend. AITeamOS keeps only configuration, trace, and audit projection locally."}
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
          planeScopeDiscovery={planeScopeDiscovery}
          planeScopeDiscoveryLoading={planeScopeDiscoveryLoading}
          repositories={repositories}
          repositoryStatus={repositoryStatus}
          saving={saving}
          selectedId={selectedRepositoryId}
          setDialogOpen={setRepositoryDialogOpen}
          setForm={setRepositoryForm}
          onDelete={(repoId) => void handleRepositoryDelete(repoId)}
          onDiscoverPlaneScope={() => void handleDiscoverPlaneScope()}
          onNew={() => {
            setSelectedRepositoryId("");
            setRepositoryForm(emptyRepositoryForm());
          }}
          onOpenTicketBackend={() => {
            setSection("ticket-backend");
            navigateTo("settings", "ticket-backend");
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

  if (section === "runtime-executors") {
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

        <RuntimeExecutorsSection
          approvals={runtimeApprovals}
          configs={runtimeExecutorConfigs}
          executors={runtimeExecutors}
          form={runtimeExecutorForm}
          sessions={runtimeExecutionSessions}
          saving={saving}
          selectedId={selectedRuntimeExecutorId}
          setForm={setRuntimeExecutorForm}
          onSelect={selectRuntimeExecutor}
          onReviewApproval={(approval, status) => void handleRuntimeApprovalReview(approval, status)}
          onRunApproval={(approval) => void handleRuntimeApprovalRun(approval)}
          onSubmit={(event) => void handleRuntimeExecutorSubmit(event)}
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
            onApplyRepositoryScope={(candidate) => void handleApplyTicketBackendScope(candidate)}
            onConfigureRepositoryScope={openRepositoryScopeConfig}
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
