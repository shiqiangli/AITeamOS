import { useEffect, useMemo, useRef, useState } from "react";
import { Check, SlidersHorizontal, X } from "lucide-react";
import { Button } from "../../../components/ui/button";
import { Select } from "../../../components/ui/select";
import {
  type ChatAiEngineConfigField,
  type ChatAiEngineRecord,
  type ChatAiEngineSettings,
  type ChatAiEngineUpdateRequest,
} from "../../../api/chat";
import { cn } from "@/lib/utils";

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

export function AiEngineControlPanel({
  aiEngines,
  aiEngineRecords,
  aiEngineReady,
  aiEngineSaving,
  onAiEngineChange,
  onAiEngineConfigChange,
}: {
  aiEngines: ChatAiEngineSettings | null;
  aiEngineRecords: ChatAiEngineRecord[];
  aiEngineReady: boolean;
  aiEngineSaving: boolean;
  onAiEngineChange: (engineId: string) => void;
  onAiEngineConfigChange: (engineId: string, payload: ChatAiEngineUpdateRequest) => Promise<void>;
}) {
  const activeAiEngine = aiEngineRecords.find((engine) => engine.id === aiEngines?.active_engine) ?? aiEngineRecords[0] ?? null;
  return (
    <div className="min-w-0 flex-[1_1_10rem]">
      <span className="mb-1 block text-[10px] font-medium uppercase leading-none text-muted-foreground">AI Engine</span>
      <div className="flex items-center gap-1.5">
        <div className={cn("h-2 w-2 shrink-0 rounded-full", aiEngineReady ? "bg-green-500" : "bg-orange-400")} />
        <Select
          aria-label="AI Engine for next reply"
          value={aiEngines?.active_engine ?? "deepseek"}
          onChange={(event) => onAiEngineChange(event.target.value)}
          disabled={aiEngineSaving}
          className="h-9 min-w-0 flex-1 text-xs"
        >
          {aiEngineRecords.length > 0 ? aiEngineRecords.map((engine) => (
            <option key={engine.id} value={engine.id}>
              {engine.display_name}
            </option>
          )) : (
            <option value="deepseek">DeepSeek</option>
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
  );
}
