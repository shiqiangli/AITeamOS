import { ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { HttpAgent } from "@ag-ui/client";
import {
  AssistantRuntimeProvider,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  type ThreadHistoryAdapter,
  type ThreadMessage,
  useAuiState,
} from "@assistant-ui/react";
import { useAgUiRuntime } from "@assistant-ui/react-ag-ui";
import { Panel, Group, Separator } from "react-resizable-panels";
import {
  Activity,
  Bot,
  Check,
  ChevronDown,
  GitBranch,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  Search,
  Send,
  SlidersHorizontal,
  Trash2,
  User,
  X,
} from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Select } from "../../components/ui/select";
import { ErrorState, LoadingState } from "../../components/shared";
import {
  activateChatThread,
  createChatThread,
  deleteChatThread,
  getChatThread,
  getChatAiEngines,
  listChatThreads,
  listChatEmployees,
  updateChatAiEngine,
  type ConversationMessage,
  type ChatEmployeeSummary,
  type ChatAiEngineConfigField,
  type ChatMessageResponse,
  type ChatAiEngineRecord,
  type ChatAiEngineSettings,
  type ChatAiEngineUpdateRequest,
  type ChatThreadSummary,
  type ChatTraceEvent,
} from "../../api/chat";
import {
  getCapabilities,
  type CapabilityRecord,
  type CapabilityRegistryResponse,
} from "../../api/capabilities";
import { cn } from "@/lib/utils";

/* ─── helpers ─────────────────────────────────────────────────────────────── */

function hasEmployeeProfileMutation(events: ChatTraceEvent[]): boolean {
  const mutationCommands = new Set([
    "employees.manage:create",
    "employees.manage:update",
    "employees.manage:delete",
    "assets.manage:assign_skill",
    "assets.manage:delete_skill",
  ]);
  return events.some((event) => (
    event.event === "command.completed"
    && mutationCommands.has(metadataText(asRecord(asRecord(event.data).command).id))
  ));
}

const ACTIVE_EMPLOYEE_STORAGE_KEY = "aiteamos.chat.activeEmployeeId";

function readTextStorage(key: string): string {
  try { return globalThis.localStorage?.getItem(key) ?? ""; } catch { return ""; }
}
function writeTextStorage(key: string, value: string): void {
  try { globalThis.localStorage?.setItem(key, value); } catch { /* optional */ }
}

function safeThreadComponent(value: string): string {
  return value.replace(/[^A-Za-z0-9_.:-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80) || "employee";
}

function defaultThreadIdForEmployee(employee: ChatEmployeeSummary | null): string {
  if (!employee) return "employee-clara-default";
  return employee.default_thread_id || `employee-${safeThreadComponent(employee.id)}-default`;
}

function isSelectableAiEngine(engine: ChatAiEngineRecord): boolean {
  return (engine.support_status ?? "supported") === "supported";
}

function messageIdForConversation(message: ConversationMessage, index: number): string {
  return safeThreadComponent(`${message.run_id || "message"}-${message.role}-${index}`);
}

function parseConversationDate(value: string): Date {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? new Date() : date;
}

function toThreadMessage(message: ConversationMessage, index: number): ThreadMessage | null {
  if (message.role !== "user" && message.role !== "assistant") return null;
  const messageMetadata = message.metadata ?? {};
  const aiteamosMetadata = (
    messageMetadata.aiteamos && typeof messageMetadata.aiteamos === "object" && !Array.isArray(messageMetadata.aiteamos)
      ? messageMetadata.aiteamos as Record<string, unknown>
      : {}
  );
  const common = {
    id: messageIdForConversation(message, index),
    createdAt: parseConversationDate(message.timestamp),
    content: [{ type: "text" as const, text: message.content }],
    metadata: {
      custom: {
        aiteamos: {
          ...aiteamosMetadata,
          employee_id: message.employee_id,
          run_id: message.run_id,
        },
      },
    },
  };
  if (message.role === "user") {
    return { ...common, role: "user", attachments: [] };
  }
  return {
    ...common,
    role: "assistant",
    status: { type: "complete", reason: "stop" },
    metadata: {
      unstable_state: null, unstable_annotations: [], unstable_data: [], steps: [],
      custom: common.metadata.custom,
    },
  };
}

function conversationToHistory(messages: ConversationMessage[]): Awaited<ReturnType<ThreadHistoryAdapter["load"]>> {
  const threadMessages = messages.map(toThreadMessage).filter((m): m is ThreadMessage => Boolean(m));
  return {
    headId: threadMessages.length > 0 ? threadMessages[threadMessages.length - 1]!.id : null,
    messages: threadMessages.map((message, index) => ({
      parentId: index > 0 ? threadMessages[index - 1]!.id : null,
      message,
    })),
  };
}

function buildAgentUrl(targetEmployeeId: string, ticketKey: string): string {
  const params = new URLSearchParams();
  if (targetEmployeeId) params.set("target_employee_id", targetEmployeeId);
  const trimmed = ticketKey.trim();
  if (trimmed) params.set("ticket_key", trimmed);
  const query = params.toString();
  return `/api/v1/chat/agent${query ? `?${query}` : ""}`;
}

function isChatMessageResponse(value: unknown): value is ChatMessageResponse {
  if (!value || typeof value !== "object") return false;
  const r = value as Record<string, unknown>;
  return typeof r.thread_id === "string" && typeof r.run_id === "string"
    && typeof r.engine_thread_id === "string" && Array.isArray(r.trace_events)
    && (r.run_metadata === undefined || (!!r.run_metadata && typeof r.run_metadata === "object"))
    && !!r.saved_paths && typeof r.saved_paths === "object";
}

function extractAiteamosResponse(state: unknown): ChatMessageResponse | null {
  if (!state || typeof state !== "object") return null;
  const response = (state as Record<string, unknown>).aiteamos_chat_response;
  return isChatMessageResponse(response) ? response : null;
}

function employeeCapabilities(employee: ChatEmployeeSummary | null, registry: CapabilityRegistryResponse | null): CapabilityRecord[] {
  if (!employee) return [];
  const capabilities = registry?.capabilities ?? [];
  const isClara = employee.id === "clara";
  return capabilities.filter((capability) => {
    if (!capability.enabled) return false;
    if (capability.kind !== "tool") return false;
    if (isClara) return true;
    if (capability.source_kind === "mcp_server") return capability.configured;
    return [
      "search_knowledge",
      "list_tickets",
      "record_ticket_report",
      "list_code_repositories",
      "inspect_code_repository",
    ].includes(capability.id);
  });
}

function capabilityVariant(capability: CapabilityRecord): "success" | "warning" | "secondary" | "outline" {
  if (!capability.configured) return "outline";
  if (capability.status === "ready") return "success";
  if (capability.status === "planned") return "warning";
  return "secondary";
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function metadataText(value: unknown): string {
  return typeof value === "string" && value.trim() ? value : "-";
}

const DEEPSEEK_CONTEXT_PRESETS = [200000, 400000, 1000000];
const DEEPSEEK_MAX_OUTPUT_PRESETS = [64000, 128000, 384000];

function compactTokens(value?: number | string | null): string {
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) return "-";
  if (parsed >= 1000000 && parsed % 1000000 === 0) return `${parsed / 1000000}M`;
  if (parsed >= 1000 && parsed % 1000 === 0) return `${parsed / 1000}K`;
  return parsed.toLocaleString();
}

function aiEngineNumberDraft(value?: number | null, fallback = 0): string {
  return String(value || fallback || "");
}

function draftNumber(value: string, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function draftNumberOrNull(value: string): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

const QUICK_ENGINE_FIELD_IDS = ["model", "thinking", "speed", "context_window", "max_tokens"] as const;
type QuickEngineFieldId = typeof QUICK_ENGINE_FIELD_IDS[number];
type QuickEngineDraft = Record<QuickEngineFieldId, string>;

function isQuickEngineFieldId(value: string): value is QuickEngineFieldId {
  return (QUICK_ENGINE_FIELD_IDS as readonly string[]).includes(value);
}

function engineFieldTextValue(engine: ChatAiEngineRecord, fieldId: QuickEngineFieldId): string {
  if (fieldId === "context_window") return aiEngineNumberDraft(engine.context_window);
  if (fieldId === "max_tokens") return aiEngineNumberDraft(engine.max_tokens);
  const value = engine[fieldId];
  return value === undefined || value === null ? "" : String(value);
}

function quickEngineFields(engine: ChatAiEngineRecord): ChatAiEngineConfigField[] {
  const fieldsById = new Map<QuickEngineFieldId, ChatAiEngineConfigField>();
  const fields = [
    ...(engine.config_fields ?? []),
    ...(engine.chat_options ?? []),
  ];
  for (const field of fields) {
    if (isQuickEngineFieldId(field.id) && !field.secret && !field.read_only) {
      fieldsById.set(field.id, field);
    }
  }
  return QUICK_ENGINE_FIELD_IDS
    .map((fieldId) => fieldsById.get(fieldId))
    .filter((field): field is ChatAiEngineConfigField => Boolean(field));
}

function quickDraftFromEngine(engine: ChatAiEngineRecord): QuickEngineDraft {
  const draft = {
    model: "",
    thinking: "",
    speed: "",
    context_window: "",
    max_tokens: "",
  };
  for (const field of quickEngineFields(engine)) {
    const fieldId = field.id as QuickEngineFieldId;
    const value = field.value ?? engineFieldTextValue(engine, fieldId);
    draft[fieldId] = value === undefined || value === null ? "" : String(value);
  }
  return draft;
}

function quickFieldOptions(engine: ChatAiEngineRecord, field: ChatAiEngineConfigField): string[] {
  const fieldOptions = field.options ?? [];
  if (fieldOptions.length > 0) return fieldOptions;
  if (field.id === "model") return engine.model_options ?? [];
  if (field.id === "thinking") return engine.thinking_options ?? [];
  return [];
}

function quickPresets(engine: ChatAiEngineRecord, fieldId: string): number[] {
  if (engine.id === "deepseek" && fieldId === "context_window") return DEEPSEEK_CONTEXT_PRESETS;
  if (engine.id === "deepseek" && fieldId === "max_tokens") return DEEPSEEK_MAX_OUTPUT_PRESETS;
  return [];
}

function quickFieldMax(engine: ChatAiEngineRecord, fieldId: string): number | undefined {
  if (fieldId === "context_window") return engine.context_window ?? undefined;
  if (fieldId === "max_tokens") return engine.context_window ?? engine.max_tokens ?? undefined;
  return undefined;
}

function quickPayloadFromDraft(engine: ChatAiEngineRecord, draft: QuickEngineDraft): ChatAiEngineUpdateRequest {
  const fieldIds = new Set(quickEngineFields(engine).map((field) => field.id));
  const payload: ChatAiEngineUpdateRequest = {};
  if (fieldIds.has("model")) payload.model = draft.model;
  if (fieldIds.has("thinking")) payload.thinking = draft.thinking;
  if (fieldIds.has("speed")) payload.speed = draft.speed;
  if (fieldIds.has("context_window")) payload.context_window = draftNumberOrNull(draft.context_window);
  if (fieldIds.has("max_tokens")) {
    const maxTokens = draftNumberOrNull(draft.max_tokens);
    const contextWindow = draftNumberOrNull(draft.context_window);
    payload.max_tokens = maxTokens && contextWindow ? Math.min(maxTokens, contextWindow) : maxTokens;
  }
  return payload;
}

function quickEngineSummary(draft: QuickEngineDraft): string {
  const parts = [
    draft.model,
    draft.thinking ? `reasoning ${draft.thinking}` : "",
    draft.speed ? `speed ${draft.speed}` : "",
    draft.context_window ? `${compactTokens(draft.context_window)} ctx` : "",
    draft.max_tokens ? `${compactTokens(draft.max_tokens)} out` : "",
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(" · ") : "No runtime fields";
}

function dataPreview(value: unknown): string {
  if (!value || typeof value !== "object") return "";
  const json = JSON.stringify(value);
  return json.length > 360 ? `${json.slice(0, 357)}...` : json;
}

function formatThreadTime(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

/* ─── AG-UI Provider ──────────────────────────────────────────────────────── */

function AiteamosAgUiRuntimeProvider({
  children, ticketKey, onError, selectedEmployeeId, threadId,
}: {
  children: ReactNode; ticketKey: string; onError: (e: Error) => void;
  selectedEmployeeId: string; threadId: string;
}) {
  const agent = useMemo(
    () => new HttpAgent({
      url: buildAgentUrl(selectedEmployeeId, ticketKey), threadId,
      fetch: (url, init) => globalThis.fetch(url, init),
    }),
    [ticketKey, selectedEmployeeId, threadId],
  );
  const history = useMemo<ThreadHistoryAdapter>(() => ({
    async load() { const t = await getChatThread(threadId); return conversationToHistory(t.messages); },
    async append() { /* backend persists */ },
  }), [threadId]);
  const assistantRuntime = useAgUiRuntime({
    agent, showThinking: false, onError,
    adapters: {
      history,
      threadList: {
        threadId,
        async onSwitchToThread(nextId) {
          const t = await getChatThread(nextId);
          return { messages: conversationToHistory(t.messages).messages.map((i) => i.message) };
        },
      },
    },
  });
  return <AssistantRuntimeProvider runtime={assistantRuntime}>{children}</AssistantRuntimeProvider>;
}

function ChatStateBridge({ onResponse }: { onResponse: (r: ChatMessageResponse) => void }) {
  const threadState = useAuiState((s) => s.thread.state as unknown);
  const response = useMemo(() => extractAiteamosResponse(threadState), [threadState]);
  const lastRunIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (!response || response.run_id === lastRunIdRef.current) return;
    lastRunIdRef.current = response.run_id;
    onResponse(response);
  }, [onResponse, response]);
  return null;
}

/* ─── Message Components ──────────────────────────────────────────────────── */

function UserMessage() {
  return (
    <MessagePrimitive.Root className="ml-auto max-w-[78ch] rounded-md border bg-primary px-4 py-3 text-sm text-primary-foreground shadow-sm">
      <div className="mb-2 flex items-center gap-2 text-xs opacity-80">
        <User className="h-3.5 w-3.5" />
        <span>You</span>
      </div>
      <MessagePrimitive.Parts />
    </MessagePrimitive.Root>
  );
}

function AssistantMessage() {
  return (
    <MessagePrimitive.Root className="mr-auto max-w-[78ch] rounded-md border bg-card px-4 py-3 text-sm shadow-sm">
      <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
        <Bot className="h-3.5 w-3.5" />
        <span>Assistant</span>
      </div>
      <div className="whitespace-pre-wrap leading-6">
        <MessagePrimitive.Parts />
      </div>
    </MessagePrimitive.Root>
  );
}

function EngineQuickConfig({
  engine,
  saving,
  onSave,
}: {
  engine: ChatAiEngineRecord;
  saving: boolean;
  onSave: (payload: ChatAiEngineUpdateRequest) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(() => quickDraftFromEngine(engine));
  const ref = useRef<HTMLDivElement>(null);
  const fields = useMemo(() => quickEngineFields(engine), [engine]);

  useEffect(() => {
    setDraft(quickDraftFromEngine(engine));
  }, [engine]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  if (fields.length === 0) return null;

  function setDraftField(fieldId: QuickEngineFieldId, value: string) {
    setDraft((current) => {
      const next = { ...current, [fieldId]: value };
      const contextWindow = draftNumberOrNull(next.context_window) ?? engine.context_window ?? null;
      const maxTokens = draftNumberOrNull(next.max_tokens);
      if (contextWindow && maxTokens && maxTokens > contextWindow) {
        next.max_tokens = String(contextWindow);
      }
      return next;
    });
  }

  async function save() {
    await onSave(quickPayloadFromDraft(engine, draft));
    setOpen(false);
  }

  return (
    <div ref={ref} className="relative shrink-0">
      <Button
        type="button"
        variant="outline"
        size="icon"
        className="h-9 w-9"
        aria-label={`${engine.display_name} settings`}
        title={`${engine.display_name} settings`}
        onClick={() => setOpen((value) => !value)}
        disabled={saving}
      >
        <SlidersHorizontal className="h-4 w-4" />
      </Button>

      {open && (
        <div className="absolute bottom-full right-0 z-50 mb-2 w-[20rem] max-w-[calc(100vw-2rem)] rounded-md border bg-popover p-3 text-sm shadow-xl">
          <div className="mb-3 flex min-w-0 items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="truncate font-semibold">{engine.display_name}</div>
              <div className="mt-0.5 truncate text-xs text-muted-foreground">{quickEngineSummary(draft)}</div>
            </div>
            <Button type="button" variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={() => setOpen(false)} title="Close">
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>

          <div className="space-y-3">
            {fields.map((field) => {
              const fieldId = field.id as QuickEngineFieldId;
              const options = quickFieldOptions(engine, field);
              const presets = quickPresets(engine, field.id);
              const numericValue = draftNumber(draft[fieldId], 0);
              const max = quickFieldMax(engine, field.id);
              return (
                <label key={field.id} className="block space-y-1">
                  <span className="text-[10px] font-medium uppercase text-muted-foreground">{field.label}</span>
                  {presets.length > 0 && (
                    <div className="grid grid-cols-3 gap-1">
                      {presets.map((preset) => {
                        const selected = preset === numericValue;
                        return (
                          <button
                            key={preset}
                            type="button"
                            onClick={() => setDraftField(fieldId, String(preset))}
                            disabled={saving}
                            className={cn(
                              "flex h-8 items-center justify-center gap-1 rounded-md border px-2 text-xs transition-colors",
                              selected ? "border-primary bg-primary/10 text-foreground" : "bg-background text-muted-foreground hover:bg-muted hover:text-foreground",
                            )}
                          >
                            <span>{compactTokens(preset)}</span>
                            {selected && <Check className="h-3 w-3" />}
                          </button>
                        );
                      })}
                    </div>
                  )}
                  {options.length > 0 ? (
                    <Select
                      aria-label={`${engine.display_name} ${field.label}`}
                      value={draft[fieldId]}
                      onChange={(event) => setDraftField(fieldId, event.target.value)}
                      disabled={saving}
                      className="h-8 text-xs"
                    >
                      {options.map((option) => (
                        <option key={option} value={option}>{option}</option>
                      ))}
                    </Select>
                  ) : (
                    <input
                      aria-label={`${engine.display_name} ${field.label}`}
                      type={field.kind === "number" ? "number" : "text"}
                      value={draft[fieldId]}
                      min={field.kind === "number" ? (field.id === "context_window" ? 1024 : 64) : undefined}
                      max={field.kind === "number" ? max : undefined}
                      onChange={(event) => setDraftField(fieldId, event.target.value)}
                      disabled={saving}
                      placeholder={field.placeholder}
                      className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  )}
                  {field.help && <span className="block text-[11px] leading-4 text-muted-foreground">{field.help}</span>}
                </label>
              );
            })}

            <div className="flex justify-end gap-2 pt-1">
              <Button type="button" variant="outline" size="sm" onClick={() => setDraft(quickDraftFromEngine(engine))} disabled={saving}>
                Reset
              </Button>
              <Button type="button" size="sm" onClick={() => void save()} disabled={saving}>
                Save
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function AiteamosThread({
  employees,
  selectedEmployee,
  onSelectEmployee,
  aiEngines,
  aiEngineRecords,
  aiEngineReady,
  aiEngineSaving,
  onAiEngineChange,
  onAiEngineConfigChange,
  ticketKey,
  onTicketKeyChange,
}: {
  employees: ChatEmployeeSummary[];
  selectedEmployee: ChatEmployeeSummary | null;
  onSelectEmployee: (employeeId: string) => void;
  aiEngines: ChatAiEngineSettings | null;
  aiEngineRecords: ChatAiEngineRecord[];
  aiEngineReady: boolean;
  aiEngineSaving: boolean;
  onAiEngineChange: (engineId: string) => void;
  onAiEngineConfigChange: (engineId: string, payload: ChatAiEngineUpdateRequest) => Promise<void>;
  ticketKey: string;
  onTicketKeyChange: (value: string) => void;
}) {
  const activeAiEngine = aiEngineRecords.find((engine) => engine.id === aiEngines?.active_engine) ?? aiEngineRecords[0] ?? null;

  return (
    <ThreadPrimitive.Root className="flex min-h-0 flex-1 flex-col">
      <ThreadPrimitive.Viewport className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4">
        <ThreadPrimitive.Empty>
          <div className="flex h-full min-h-[18rem] items-center justify-center text-sm text-muted-foreground">
            {selectedEmployee ? `${selectedEmployee.display_name} is ready.` : "No employees loaded."}
          </div>
        </ThreadPrimitive.Empty>
        <div className="space-y-4">
          <ThreadPrimitive.Messages components={{ UserMessage, AssistantMessage }} />
        </div>
        <ThreadPrimitive.ViewportFooter className="sticky bottom-0 mt-auto border-t bg-background px-4 pb-4 pt-3">
          <div className="mb-2 flex flex-wrap items-end gap-2 rounded-md border bg-muted/20 p-2">
            <div className="min-w-0 flex-[1_1_11rem]">
              <div className="mb-1 text-[10px] font-medium uppercase text-muted-foreground">Employee</div>
              <EmployeeSelect
                employees={employees}
                selectedEmployee={selectedEmployee}
                onSelect={onSelectEmployee}
                className="h-9 rounded-md border bg-background"
              />
            </div>

            <div className="min-w-0 flex-[1_1_10rem]">
              <span className="mb-1 block text-[10px] font-medium uppercase leading-none text-muted-foreground">AI Engine</span>
              <div className="flex items-center gap-1.5">
                <div className={cn("h-2 w-2 shrink-0 rounded-full", aiEngineReady ? "bg-green-500" : "bg-orange-400")} />
                <Select
                  aria-label="AI Engine for next reply"
                  value={aiEngines?.active_engine ?? "stub"}
                  onChange={(event) => onAiEngineChange(event.target.value)}
                  disabled={aiEngineSaving}
                  className="h-9 min-w-0 flex-1 text-xs"
                >
                  {aiEngineRecords.length > 0 ? aiEngineRecords.map((engine) => (
                    <option key={engine.id} value={engine.id}>
                      {engine.display_name}
                    </option>
                  )) : (
                    <option value="stub">File stub</option>
                  )}
                </Select>
                {activeAiEngine && (
                  <EngineQuickConfig
                    engine={activeAiEngine}
                    saving={aiEngineSaving}
                    onSave={(payload) => onAiEngineConfigChange(activeAiEngine.id, payload)}
                  />
                )}
              </div>
            </div>

            <label className="min-w-0 flex-[1_1_9rem]">
              <span className="mb-1 block text-[10px] font-medium uppercase leading-none text-muted-foreground">Ticket</span>
              <div className="flex h-9 items-center gap-1 rounded-md border border-input bg-background px-2 shadow-sm">
                <GitBranch className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <input
                  aria-label="Ticket key"
                  value={ticketKey}
                  onChange={(event) => onTicketKeyChange(event.target.value)}
                  placeholder="Ticket key"
                  className="h-full min-w-0 flex-1 bg-transparent text-xs outline-none placeholder:text-muted-foreground"
                />
              </div>
            </label>
          </div>

          <ComposerPrimitive.Root className="grid gap-2 bg-background sm:grid-cols-[minmax(0,1fr)_auto]">
            <ComposerPrimitive.Input
              aria-label="Chat message"
              placeholder={selectedEmployee ? `Message ${selectedEmployee.display_name}` : "Message"}
              submitMode="enter"
              style={{ height: 44 }}
              className="h-[2.75rem] min-h-[2.75rem] max-h-32 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            <ComposerPrimitive.Send className={cn(
              "inline-flex h-[2.75rem] min-h-[2.75rem] items-center justify-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm transition-colors",
              "hover:bg-primary/90 disabled:pointer-events-none disabled:opacity-50",
            )}>
              <Send className="h-4 w-4" />
              Send
            </ComposerPrimitive.Send>
          </ComposerPrimitive.Root>
        </ThreadPrimitive.ViewportFooter>
      </ThreadPrimitive.Viewport>
    </ThreadPrimitive.Root>
  );
}

/* ─── Employee Select (Combobox) ────────────────────────────────────────────── */

function EmployeeSelect({
  employees, selectedEmployee, onSelect, className,
}: {
  employees: ChatEmployeeSummary[]; selectedEmployee: ChatEmployeeSummary | null;
  onSelect: (employeeId: string) => void;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => {
    if (!query.trim()) return employees;
    const q = query.toLowerCase();
    return employees.filter(
      (m) => m.display_name.toLowerCase().includes(q) || m.id.toLowerCase().includes(q) || m.role.toLowerCase().includes(q),
    );
  }, [employees, query]);

  // Close on outside click
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const initial = selectedEmployee?.display_name.charAt(0) ?? "?";

  return (
    <div ref={ref} className={cn("relative", className ?? "px-3 py-2 border-b")}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex h-full min-h-9 w-full items-center gap-2 rounded-md px-2 text-sm transition-colors hover:bg-muted"
      >
        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
          {initial}
        </div>
        <div className="min-w-0 flex-1 text-left">
          <div className="truncate text-xs font-medium">{selectedEmployee?.display_name ?? "Select employee"}</div>
        </div>
        <ChevronDown className={cn("h-3.5 w-3.5 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="absolute left-2 right-2 top-full z-50 mt-1 rounded-md border bg-popover shadow-md">
          <div className="flex items-center gap-2 border-b px-2 py-1.5">
            <Search className="h-3.5 w-3.5 text-muted-foreground" />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search employees..."
              className="h-6 w-full bg-transparent text-xs outline-none placeholder:text-muted-foreground"
            />
          </div>
          <div className="max-h-48 overflow-y-auto py-1">
            {filtered.length === 0 ? (
              <p className="px-3 py-2 text-xs text-muted-foreground">No employees found.</p>
            ) : (
              filtered.map((employee) => {
                const isActive = employee.id === selectedEmployee?.id;
                return (
                  <button
                    key={employee.id}
                    type="button"
                    onClick={() => { onSelect(employee.id); setOpen(false); setQuery(""); }}
                    className={cn(
                      "flex w-full items-center gap-2 px-3 py-1.5 text-sm transition-colors",
                      isActive ? "bg-primary/10 text-foreground font-medium" : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    <div className={cn(
                      "flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold",
                      isActive ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
                    )}>
                      {employee.display_name.charAt(0)}
                    </div>
                    <div className="min-w-0 flex-1 text-left">
                      <span className="truncate block">{employee.display_name}</span>
                    </div>
                    <span className="text-[10px] text-muted-foreground shrink-0">{employee.role}</span>
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Thread History ──────────────────────────────────────────────────────── */

function ThreadHistory({
  activeThreadId,
  deletingThreadId,
  openThreadIds,
  query,
  threads,
  threadsLoading,
  onClose,
  onCreateThread,
  onDeleteThread,
  onOpenThread,
  onQueryChange,
}: {
  activeThreadId: string;
  deletingThreadId: string | null;
  openThreadIds: string[];
  query: string;
  threads: ChatThreadSummary[];
  threadsLoading: boolean;
  onClose: () => void;
  onCreateThread: () => void;
  onDeleteThread: (thread: ChatThreadSummary) => void;
  onOpenThread: (thread: ChatThreadSummary) => void;
  onQueryChange: (value: string) => void;
}) {
  const openSet = useMemo(() => new Set(openThreadIds), [openThreadIds]);
  const filteredThreads = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return threads;
    return threads.filter((thread) => (
      thread.title.toLowerCase().includes(normalized)
      || thread.id.toLowerCase().includes(normalized)
      || thread.employee_id.toLowerCase().includes(normalized)
    ));
  }, [query, threads]);

  return (
    <aside className="flex h-full min-w-0 flex-col bg-sidebar">
      <div className="border-b p-3">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold">Thread History</h3>
            <p className="text-xs text-muted-foreground">All history, recent first</p>
          </div>
          <Button type="button" variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={onClose} title="Collapse thread history">
            <PanelLeftClose className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex items-center gap-2 rounded-md border bg-background px-2">
          <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <input
            aria-label="Search threads"
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="Search threads"
            className="h-9 min-w-0 flex-1 bg-transparent text-xs outline-none placeholder:text-muted-foreground"
          />
        </div>
        <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
          <span>{filteredThreads.length} of {threads.length}</span>
          <Button type="button" variant="outline" size="sm" className="h-7 gap-1.5 px-2 text-xs" onClick={onCreateThread}>
            <Plus className="h-3.5 w-3.5" />
            New
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {threadsLoading ? (
          <div className="p-3 text-xs text-muted-foreground">Loading threads...</div>
        ) : filteredThreads.length === 0 ? (
          <div className="p-3 text-xs text-muted-foreground">No threads found.</div>
        ) : (
          <div className="divide-y">
            {filteredThreads.map((thread) => {
              const isActive = thread.id === activeThreadId;
              const isOpen = openSet.has(thread.id);
              const isDeleting = deletingThreadId === thread.id;
              return (
                <div
                  key={thread.id}
                  className={cn(
                    "group grid grid-cols-[minmax(0,1fr)_auto] gap-1 px-2.5 py-1.5 text-left transition-colors",
                    isActive ? "bg-primary/10" : "hover:bg-muted/70",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => onOpenThread(thread)}
                    className="min-w-0 text-left"
                    title={thread.title || thread.id}
                  >
                    <div className="flex min-w-0 items-center gap-1.5">
                      <span className="truncate text-xs font-medium">{thread.title || thread.id}</span>
                      {isOpen && <Badge variant="secondary" className="shrink-0 px-1 py-0 text-[9px] leading-3">open</Badge>}
                    </div>
                    <div className="mt-0.5 flex min-w-0 items-center gap-2 text-[10px] text-muted-foreground">
                      <span className="shrink-0">{thread.message_count} msgs</span>
                      <span className="truncate">last {formatThreadTime(thread.last_message_at || thread.updated_at)}</span>
                    </div>
                  </button>
                  <button
                    type="button"
                    onClick={() => onDeleteThread(thread)}
                    disabled={isDeleting}
                    className="self-center rounded p-1 text-muted-foreground opacity-60 transition-colors hover:bg-background hover:text-destructive group-hover:opacity-100"
                    title="Delete thread"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </aside>
  );
}

/* ─── Resize Handle ───────────────────────────────────────────────────────── */

function ResizeHandle({ className }: { className?: string }) {
  return (
    <Separator
      className={cn(
        "relative w-0.5 bg-border transition-colors hover:bg-primary/40",
        className,
      )}
    />
  );
}

/* ─── Main Chat Page ──────────────────────────────────────────────────────── */

export function ChatPage({ routeTarget = null }: { routeTarget?: string | null }) {
  const normalizedRouteTarget = routeTarget?.trim() ?? "";
  const [employees, setEmployees] = useState<ChatEmployeeSummary[]>([]);
  const [selectedEmployeeId, setSelectedEmployeeId] = useState(() => readTextStorage(ACTIVE_EMPLOYEE_STORAGE_KEY));
  const [ticketKey, setTicketKey] = useState("");
  const [threads, setThreads] = useState<ChatThreadSummary[]>([]);
  const [threadId, setThreadId] = useState("");
  const [openThreadIds, setOpenThreadIds] = useState<string[]>([]);
  const [threadHistoryOpen, setThreadHistoryOpen] = useState(false);
  const [threadQuery, setThreadQuery] = useState("");
  const [engineThreadId, setEngineThreadId] = useState<string | null>(null);
  const [traceEvents, setTraceEvents] = useState<ChatTraceEvent[]>([]);
  const [runMetadata, setRunMetadata] = useState<Record<string, unknown> | null>(null);
  const [savedPaths, setSavedPaths] = useState<Record<string, string>>({});
  const [aiEngines, setAiEngines] = useState<ChatAiEngineSettings | null>(null);
  const [capabilityRegistry, setCapabilityRegistry] = useState<CapabilityRegistryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [threadsLoading, setThreadsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingThreadId, setDeletingThreadId] = useState<string | null>(null);
  const [aiEngineSaving, setAiEngineSaving] = useState(false);
  const [detailsPanelOpen, setDetailsPanelOpen] = useState(true);

  const selectedEmployee = useMemo(
    () => employees.find((m) => m.id === selectedEmployeeId) ?? employees[0] ?? null,
    [employees, selectedEmployeeId],
  );
  const capabilities = useMemo(
    () => employeeCapabilities(selectedEmployee, capabilityRegistry),
    [capabilityRegistry, selectedEmployee],
  );
  const aiEngineRecords = useMemo(
    () => Object.values(aiEngines?.engines ?? {}).filter(isSelectableAiEngine),
    [aiEngines],
  );
  const activeAiEngineRecord = useMemo(
    () => aiEngineRecords.find((engine) => engine.id === aiEngines?.active_engine) ?? null,
    [aiEngineRecords, aiEngines],
  );
  const activeThreadId = threadId || defaultThreadIdForEmployee(selectedEmployee);
  const activeThread = useMemo(
    () => threads.find((thread) => thread.id === activeThreadId) ?? null,
    [activeThreadId, threads],
  );
  const openThreads = useMemo(() => {
    const byId = new Map(threads.map((thread) => [thread.id, thread]));
    return openThreadIds.map((id) => byId.get(id)).filter((thread): thread is ChatThreadSummary => Boolean(thread));
  }, [openThreadIds, threads]);

  const loadThreadsForEmployee = useCallback(async (employee: ChatEmployeeSummary | null, preferredThreadId?: string) => {
    if (!employee) return "";
    setThreadsLoading(true);
    try {
      const response = await listChatThreads(employee.id);
      setThreads(response.threads);
      const ids = new Set(response.threads.map((t) => t.id));
      const nextId = (
        preferredThreadId && ids.has(preferredThreadId) ? preferredThreadId
        : response.active_thread_id || response.threads[0]?.id || defaultThreadIdForEmployee(employee)
      );
      setThreadId(nextId);
      setOpenThreadIds((current) => {
        const valid = current.filter((id) => ids.has(id));
        return nextId && !valid.includes(nextId) ? [...valid, nextId] : valid;
      });
      return nextId;
    } finally { setThreadsLoading(false); }
  }, []);

  const loadChatSurface = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [loaded, loadedAiEngines, loadedCapabilities] = await Promise.all([
        listChatEmployees(),
        getChatAiEngines(),
        getCapabilities().catch(() => null),
      ]);
      setEmployees(loaded);
      setAiEngines(loadedAiEngines);
      setCapabilityRegistry(loadedCapabilities);
      const routeEmployee = normalizedRouteTarget ? loaded.find((m) => m.id === normalizedRouteTarget) : undefined;
      const routeTicketKey = normalizedRouteTarget && !routeEmployee ? normalizedRouteTarget : "";
      const clara = loaded.find((m) => m.id === "clara") ?? null;
      const storedId = readTextStorage(ACTIVE_EMPLOYEE_STORAGE_KEY);
      const preferred = (
        routeEmployee
        ?? (routeTicketKey ? (clara ?? loaded[0]) : undefined)
        ?? (storedId ? loaded.find((m) => m.id === storedId) : undefined)
        ?? clara
        ?? loaded[0] ?? null
      );
      setTicketKey(routeTicketKey);
      const nextId = preferred?.id ?? "";
      setSelectedEmployeeId(nextId);
      if (nextId) writeTextStorage(ACTIVE_EMPLOYEE_STORAGE_KEY, nextId);
      await loadThreadsForEmployee(preferred);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load Chat");
    } finally { setLoading(false); }
  }, [loadThreadsForEmployee, normalizedRouteTarget]);

  useEffect(() => { loadChatSurface(); }, [loadChatSurface]);

  const handleAgentResponse = useCallback((response: ChatMessageResponse) => {
    setThreadId(response.thread_id);
    setEngineThreadId(response.engine_thread_id);
    setTraceEvents(response.trace_events);
    setRunMetadata(response.run_metadata ?? null);
    setSavedPaths(response.saved_paths);
    writeTextStorage(ACTIVE_EMPLOYEE_STORAGE_KEY, response.target_employee.id);
    void loadThreadsForEmployee(response.target_employee, response.thread_id).catch((err) => {
      setError(err instanceof Error ? err.message : "Failed to reload threads");
    });
    if (hasEmployeeProfileMutation(response.trace_events)) {
      void listChatEmployees().then(setEmployees).catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to reload employees");
      });
    }
  }, [loadThreadsForEmployee]);

  async function resetThread() {
    if (!selectedEmployee) return;
    setError(null);
    try {
      const thread = await createChatThread(selectedEmployee.id);
      setThreads((current) => [thread, ...current.filter((item) => item.id !== thread.id)]);
      setThreadId(thread.id);
      setOpenThreadIds((current) => current.includes(thread.id) ? current : [...current, thread.id]);
      setEngineThreadId(null); setTraceEvents([]); setRunMetadata(null); setSavedPaths({});
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to create thread"); }
  }

  async function selectEmployee(nextEmployeeId: string) {
    const next = employees.find((m) => m.id === nextEmployeeId) ?? null;
    setSelectedEmployeeId(nextEmployeeId);
    writeTextStorage(ACTIVE_EMPLOYEE_STORAGE_KEY, nextEmployeeId);
    setThreadId(defaultThreadIdForEmployee(next));
    setOpenThreadIds([]);
    setThreadQuery("");
    setEngineThreadId(null); setTraceEvents([]); setRunMetadata(null); setSavedPaths({}); setError(null);
    try { await loadThreadsForEmployee(next); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed to load employee threads"); }
  }

  async function switchThread(nextThread: ChatThreadSummary) {
    if (!selectedEmployee) return;
    setOpenThreadIds((current) => current.includes(nextThread.id) ? current : [...current, nextThread.id]);
    if (nextThread.id === activeThreadId) return;
    setError(null);
    const previousThreadId = activeThreadId;
    setThreadId(nextThread.id);
    setEngineThreadId(null); setTraceEvents([]); setRunMetadata(null); setSavedPaths({});
    try {
      await activateChatThread(nextThread.id, selectedEmployee.id);
    } catch (err) {
      setThreadId(previousThreadId);
      setError(err instanceof Error ? err.message : "Failed to switch thread");
    }
  }

  async function closeWorkspaceThread(thread: ChatThreadSummary) {
    const currentOpenIds = openThreads.map((item) => item.id);
    if (currentOpenIds.length <= 1) return;

    const nextOpenIds = currentOpenIds.filter((id) => id !== thread.id);
    setOpenThreadIds(nextOpenIds);

    if (thread.id !== activeThreadId) return;
    const closedIndex = currentOpenIds.indexOf(thread.id);
    const nextThreadId = nextOpenIds[Math.min(closedIndex, nextOpenIds.length - 1)] ?? nextOpenIds[0];
    const nextThread = threads.find((item) => item.id === nextThreadId);
    if (nextThread) {
      await switchThread(nextThread);
    }
  }

  async function handleDeleteThread(thread: ChatThreadSummary) {
    if (!selectedEmployee) return;
    if (!window.confirm(`Delete thread "${thread.title || thread.id}"?`)) return;
    setDeletingThreadId(thread.id);
    try {
      await deleteChatThread(thread.id);
      const remaining = threads.filter((t) => t.id !== thread.id);
      setThreads(remaining);
      setOpenThreadIds((current) => current.filter((id) => id !== thread.id));
      // If deleting the active thread, switch to another
      if (thread.id === activeThreadId) {
        const fallback = remaining[0] ?? null;
        if (fallback) {
          await switchThread(fallback);
        } else {
          await resetThread();
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete thread");
    } finally { setDeletingThreadId(null); }
  }

  async function switchAiEngine(nextEngine: string) {
    if (!nextEngine || nextEngine === aiEngines?.active_engine || aiEngineSaving) return;
    setAiEngineSaving(true);
    setError(null);
    try {
      setAiEngines(await updateChatAiEngine(nextEngine, { activate: true }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to switch AI Engine");
    } finally {
      setAiEngineSaving(false);
    }
  }

  async function updateAiEngineConfig(engineId: string, payload: ChatAiEngineUpdateRequest) {
    if (!engineId || aiEngineSaving) return;
    setAiEngineSaving(true);
    setError(null);
    try {
      setAiEngines(await updateChatAiEngine(engineId, payload));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update AI Engine settings");
      throw err;
    } finally {
      setAiEngineSaving(false);
    }
  }

  if (loading) return <LoadingState />;
  const aiEngineReady = Boolean(
    aiEngines?.active_engine
    && aiEngines.active_engine !== "stub"
    && (activeAiEngineRecord?.config_status ?? activeAiEngineRecord?.status) === "configured",
  );
  const runMetadataRecord = asRecord(runMetadata);
  const runAiEngine = asRecord(runMetadataRecord.ai_engine);
  const runEmployee = asRecord(runMetadataRecord.employee);
  const runTicketKeys = asStringArray(runMetadataRecord.ticket_keys);
  const runCommands = Array.isArray(runMetadataRecord.commands) ? runMetadataRecord.commands.map(asRecord) : [];

  return (
    <AiteamosAgUiRuntimeProvider
      key={activeThreadId} ticketKey={ticketKey}
      onError={(err) => setError(err.message)}
      selectedEmployeeId={selectedEmployee?.id ?? ""} threadId={activeThreadId}
    >
      <ChatStateBridge onResponse={handleAgentResponse} />
      <div className="h-[calc(100vh-8rem)] overflow-hidden rounded-md border bg-background">
        <Group orientation="horizontal" id="aiteamos-chat-layout">
          {threadHistoryOpen && (
            <>
              <Panel defaultSize="18rem" minSize="14rem" maxSize="28rem">
                <ThreadHistory
                  activeThreadId={activeThreadId}
                  deletingThreadId={deletingThreadId}
                  openThreadIds={openThreadIds}
                  query={threadQuery}
                  threads={threads}
                  threadsLoading={threadsLoading}
                  onClose={() => setThreadHistoryOpen(false)}
                  onCreateThread={() => void resetThread()}
                  onDeleteThread={(thread) => void handleDeleteThread(thread)}
                  onOpenThread={(thread) => void switchThread(thread)}
                  onQueryChange={setThreadQuery}
                />
              </Panel>
              <ResizeHandle />
            </>
          )}

          <Panel defaultSize={detailsPanelOpen ? 70 : 100} minSize="32rem">
            <section className="flex h-full min-w-0 flex-col">
              <div className="flex h-12 shrink-0 items-center gap-2 border-b px-3">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 shrink-0"
                  onClick={() => setThreadHistoryOpen((open) => !open)}
                  title={threadHistoryOpen ? "Hide thread history" : "Show thread history"}
                >
                  {threadHistoryOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
                </Button>
                <div className="flex h-full min-w-0 flex-1 flex-nowrap items-center gap-1 overflow-hidden" role="tablist" aria-label="Chat threads">
                  {threadsLoading && openThreads.length === 0 ? (
                    <span className="px-2 text-xs text-muted-foreground">Loading...</span>
                  ) : openThreads.length === 0 ? (
                    <span className="px-2 text-xs text-muted-foreground">Open a thread from history.</span>
                  ) : (
                    openThreads.map((thread) => {
                      const isActive = thread.id === activeThreadId;
                      return (
                        <div
                          key={thread.id}
                          className={cn(
                            "group flex h-8 min-w-0 max-w-[14rem] flex-1 basis-0 items-center rounded-md border text-xs transition-colors",
                            isActive ? "border-primary/30 bg-primary/10 text-foreground" : "bg-background text-muted-foreground hover:bg-muted hover:text-foreground",
                          )}
                        >
                          <button
                            type="button"
                            role="tab"
                            aria-selected={isActive}
                            onClick={() => void switchThread(thread)}
                            className="min-w-0 flex-1 px-2 text-left"
                            title={thread.title || thread.id}
                          >
                            <span className="block truncate font-medium">{thread.title || thread.id}</span>
                          </button>
                          <button
                            type="button"
                            onClick={(event) => { event.stopPropagation(); void closeWorkspaceThread(thread); }}
                            disabled={openThreads.length <= 1}
                            className="mr-1 shrink-0 rounded p-1 text-muted-foreground opacity-60 transition-colors hover:bg-background hover:text-foreground disabled:pointer-events-none disabled:opacity-25 group-hover:opacity-100"
                            title={openThreads.length <= 1 ? "Keep one thread open" : "Close tab"}
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </div>
                      );
                    })
                  )}
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 shrink-0"
                  onClick={() => void resetThread()}
                  title="New thread"
                >
                  <Plus className="h-4 w-4" />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 shrink-0"
                  onClick={() => setDetailsPanelOpen((open) => !open)}
                  title={detailsPanelOpen ? "Hide trace" : "Show trace"}
                >
                  {detailsPanelOpen ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}
                </Button>
              </div>

              {error && (
                <div className="border-b p-3">
                  <ErrorState message={error} onRetry={loadChatSurface} />
                </div>
              )}

              <AiteamosThread
                employees={employees}
                selectedEmployee={selectedEmployee}
                onSelectEmployee={selectEmployee}
                aiEngines={aiEngines}
                aiEngineRecords={aiEngineRecords}
                aiEngineReady={aiEngineReady}
                aiEngineSaving={aiEngineSaving}
                onAiEngineChange={(engineId) => void switchAiEngine(engineId)}
                onAiEngineConfigChange={updateAiEngineConfig}
                ticketKey={ticketKey}
                onTicketKeyChange={setTicketKey}
              />
            </section>
          </Panel>

          {detailsPanelOpen && <ResizeHandle />}

          {detailsPanelOpen && (
            <Panel defaultSize="24rem" minSize="18rem" maxSize="42rem">
              <aside className="flex h-full flex-col overflow-y-auto bg-sidebar">
                <section className="border-b p-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5">
                      <Activity className="h-3.5 w-3.5 text-muted-foreground" />
                      <h3 className="text-xs font-semibold">Thread Context</h3>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 shrink-0"
                      onClick={() => setDetailsPanelOpen(false)}
                      title="Hide trace"
                    >
                      <PanelRightClose className="h-4 w-4" />
                    </Button>
                  </div>
                  {activeThread && (
                    <div className="mt-1 min-w-0 text-xs">
                      <div className="truncate font-medium" title={activeThread.title}>{activeThread.title}</div>
                      <div className="mt-0.5 flex min-w-0 items-center gap-2 text-[10px] text-muted-foreground">
                        <span className="shrink-0">{activeThread.message_count} msgs</span>
                        <span className="truncate">last {formatThreadTime(activeThread.last_message_at || activeThread.updated_at)}</span>
                      </div>
                    </div>
                  )}
                </section>

                <section className="border-b p-3">
                  {runMetadata ? (
                    <div className="space-y-1.5 text-xs">
                      <div className="text-[10px] font-medium uppercase text-muted-foreground">Latest Run</div>
                      <div className="flex justify-between gap-2">
                        <span className="text-muted-foreground">Run</span>
                        <span className="truncate font-medium" title={metadataText(runMetadataRecord.run_id)}>
                          {metadataText(runMetadataRecord.run_id)}
                        </span>
                      </div>
                      <div className="flex justify-between gap-2">
                        <span className="text-muted-foreground">Employee</span>
                        <span className="truncate text-right font-medium" title={metadataText(runEmployee.role)}>
                          {metadataText(runEmployee.display_name)}
                        </span>
                      </div>
                      <div className="flex justify-between gap-2">
                        <span className="text-muted-foreground">AI Engine</span>
                        <span className="truncate text-right font-medium">
                          {metadataText(runAiEngine.actual_ai_engine)}
                        </span>
                      </div>
                      <div className="flex justify-between gap-2">
                        <span className="text-muted-foreground">Model</span>
                        <span className="truncate text-right">{metadataText(runAiEngine.model)}</span>
                      </div>
                      <div className="flex justify-between gap-2">
                        <span className="text-muted-foreground">Engine thread</span>
                        <span className="truncate text-right" title={metadataText(runAiEngine.engine_thread_id || engineThreadId)}>
                          {metadataText(runAiEngine.engine_thread_id || engineThreadId)}
                        </span>
                      </div>
                      <div>
                        <div className="mb-1 text-[10px] uppercase text-muted-foreground">Tickets</div>
                        <div className="flex flex-wrap gap-1">
                          {runTicketKeys.length ? runTicketKeys.map((key) => (
                            <Badge key={key} variant="secondary" className="px-1.5 text-[10px]">{key}</Badge>
                          )) : (
                            <Badge variant="outline" className="px-1.5 text-[10px]">none</Badge>
                          )}
                        </div>
                      </div>
                      <div>
                        <div className="mb-1 text-[10px] uppercase text-muted-foreground">Commands</div>
                        <div className="flex flex-wrap gap-1">
                          {runCommands.length ? runCommands.map((command, index) => (
                            <Badge
                              key={`${metadataText(command.id)}-${index}`}
                              variant={metadataText(command.status) === "completed" ? "success" : metadataText(command.status) === "blocked" ? "warning" : "outline"}
                              className="max-w-full px-1.5 text-[10px]"
                              title={metadataText(command.id)}
                            >
                              <span className="truncate">{metadataText(command.id)}:{metadataText(command.status)}</span>
                            </Badge>
                          )) : (
                            <Badge variant="outline" className="px-1.5 text-[10px]">none</Badge>
                          )}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground">No run selected yet.</p>
                  )}
                </section>

                {selectedEmployee && (
                  <section className="border-b p-3">
                    <div className="mb-2 flex items-center gap-1.5">
                      <Bot className="h-3.5 w-3.5 text-muted-foreground" />
                      <h3 className="text-xs font-semibold">Current Employee</h3>
                    </div>
                    <div className="space-y-1.5 text-xs">
                      <div className="flex justify-between gap-2">
                        <span className="text-muted-foreground">Role</span>
                        <span className="truncate text-right font-medium">{selectedEmployee.role}</span>
                      </div>
                      <div className="flex justify-between gap-2">
                        <span className="text-muted-foreground">Threads</span>
                        <span>{threads.length}</span>
                      </div>
                      {capabilities.length > 0 && (
                        <div>
                          <div className="mb-1 mt-2 text-[10px] uppercase text-muted-foreground">Capabilities</div>
                          <div className="flex flex-wrap gap-1">
                            {capabilities.slice(0, 8).map((capability) => (
                              <Badge
                                key={capability.id}
                                variant={capabilityVariant(capability)}
                                className="max-w-full px-1.5 text-[10px]"
                                title={capability.description || capability.id}
                              >
                                <span className="truncate">{capability.name}</span>
                              </Badge>
                            ))}
                            {capabilities.length > 8 && (
                              <Badge variant="outline" className="px-1.5 text-[10px]">+{capabilities.length - 8}</Badge>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  </section>
                )}

                <section className="p-3">
                  <div className="mb-2 flex items-center gap-1.5">
                    <Activity className="h-3.5 w-3.5 text-muted-foreground" />
                    <h3 className="text-xs font-semibold">Trace</h3>
                  </div>
                  {traceEvents.length === 0 ? (
                    <p className="text-xs text-muted-foreground">No trace events.</p>
                  ) : (
                    <ol className="space-y-1.5">
                      {traceEvents.map((event, index) => {
                        const preview = event.event.startsWith("command.") ? dataPreview(event.data) : "";
                        return (
                          <li key={`${event.event}-${index}`} className="rounded border px-2 py-1.5">
                            <div className="text-[10px] font-medium text-muted-foreground">{event.event}</div>
                            <div className="text-xs">{event.detail}</div>
                            {preview && (
                              <pre className="mt-1 max-h-28 overflow-auto rounded bg-muted p-1 text-[10px] leading-4 text-muted-foreground">
                                {preview}
                              </pre>
                            )}
                          </li>
                        );
                      })}
                    </ol>
                  )}
                  {Object.entries(savedPaths).length > 0 && (
                    <div className="mt-3 space-y-1">
                      {Object.entries(savedPaths).map(([key, value]) => (
                        <div key={key} className="min-w-0">
                          <div className="text-[10px] uppercase text-muted-foreground">{key}</div>
                          <div className="truncate text-xs font-medium" title={value}>{value}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </section>
              </aside>
            </Panel>
          )}
        </Group>
      </div>
    </AiteamosAgUiRuntimeProvider>
  );
}
