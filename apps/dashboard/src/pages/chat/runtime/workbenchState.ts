import { Client as LangGraphClient } from "@langchain/langgraph-sdk";
import type { ChatMessageResponse } from "../../../api/chat";

export interface WorkbenchInitialState {
  messages: unknown[];
  thread_id: string;
  employee_id: string;
  ticket_key: string;
  approval_ref: string;
}

export interface WorkbenchSnapshot {
  activeTicket: Record<string, unknown>;
  selectedEmployee: Record<string, unknown>;
  employeeIdentity: Record<string, unknown>;
  ticketBinding: Record<string, unknown>;
  linkedAssets: Record<string, unknown>[];
  recalledMemoryRefs: Record<string, unknown>[];
  approvalRequests: Record<string, unknown>[];
  approvalRecords: Record<string, unknown>[];
  assetCandidates: Record<string, unknown>[];
  provenanceEvents: Record<string, unknown>[];
  providerBlockers: Record<string, unknown>[];
  handoffDecision: Record<string, unknown>;
  handoffSummary: Record<string, unknown>;
  ticketHandoffRefs: Record<string, unknown>[];
  ticketLoopDecision: Record<string, unknown>;
  ticketLoopPolicyActions: Record<string, unknown>[];
  runtimeStatus: Record<string, unknown>;
  workbenchPanels: Record<string, unknown>;
}

export interface PendingInterrupt {
  id: string;
  namespace: string[];
  value: Record<string, unknown>;
}

const LANGGRAPH_THREAD_MAP_STORAGE_KEY = "aiteamos.chat.langGraphThreadMap.v1";
const LANGGRAPH_CURRENT_THREAD_STORAGE_KEY = "aiteamos.chat.currentLangGraphThreadId";

function viteEnv(key: string): string {
  const env = (import.meta as unknown as { env?: Record<string, string | undefined> }).env;
  return env?.[key] ?? "";
}

function readTextStorage(key: string): string {
  try { return globalThis.localStorage?.getItem(key) ?? ""; } catch { return ""; }
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function asRecordArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(asRecord).filter((item) => Object.keys(item).length > 0) : [];
}

function metadataText(value: unknown): string {
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  return typeof value === "string" && value.trim() ? value : "-";
}

export function langGraphApiUrl(): string {
  return viteEnv("VITE_LANGGRAPH_API_URL") || "http://127.0.0.1:2024";
}

export function langGraphAssistantId(): string {
  return viteEnv("VITE_LANGGRAPH_ASSISTANT_ID") || "aiteamos_workbench";
}

export function normalizeUrl(value: string): string {
  return value.replace(/\/+$/, "");
}

function langGraphThreadMapKey(apiUrl: string, assistantId: string, aiteamosThreadId: string): string {
  return [normalizeUrl(apiUrl), assistantId, aiteamosThreadId].join("|");
}

function readLangGraphThreadMap(): Record<string, string> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(LANGGRAPH_THREAD_MAP_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed as Record<string, string>
      : {};
  } catch {
    return {};
  }
}

export function readLangGraphExternalThreadId(apiUrl: string, assistantId: string, aiteamosThreadId: string): string {
  const key = langGraphThreadMapKey(apiUrl, assistantId, aiteamosThreadId);
  const value = readLangGraphThreadMap()[key];
  return typeof value === "string" ? value : "";
}

export function readLatestLangGraphExternalThreadId(apiUrl: string, assistantId: string): string {
  const prefix = `${normalizeUrl(apiUrl)}|${assistantId}|`;
  const entries = Object.entries(readLangGraphThreadMap()).filter(([key]) => key.startsWith(prefix));
  const latest = entries[entries.length - 1]?.[1];
  return typeof latest === "string" ? latest : "";
}

export function writeLangGraphExternalThreadId(
  apiUrl: string,
  assistantId: string,
  aiteamosThreadId: string,
  langGraphThreadId: string,
) {
  if (typeof window === "undefined") return;
  const map = readLangGraphThreadMap();
  map[langGraphThreadMapKey(apiUrl, assistantId, aiteamosThreadId)] = langGraphThreadId;
  window.localStorage.setItem(LANGGRAPH_THREAD_MAP_STORAGE_KEY, JSON.stringify(map));
  window.localStorage.setItem(LANGGRAPH_CURRENT_THREAD_STORAGE_KEY, langGraphThreadId);
}

export function readCurrentLangGraphThreadId(): string {
  return readTextStorage(LANGGRAPH_CURRENT_THREAD_STORAGE_KEY);
}

export function workbenchSnapshotFromValues(values: Record<string, unknown>): WorkbenchSnapshot {
  return {
    activeTicket: asRecord(values.active_ticket),
    selectedEmployee: asRecord(values.selected_employee),
    employeeIdentity: asRecord(values.employee_identity),
    ticketBinding: asRecord(values.ticket_binding),
    linkedAssets: asRecordArray(values.linked_assets),
    recalledMemoryRefs: asRecordArray(values.recalled_memory_refs),
    approvalRequests: asRecordArray(values.approval_requests),
    approvalRecords: asRecordArray(values.approval_records),
    assetCandidates: asRecordArray(values.asset_candidates),
    provenanceEvents: asRecordArray(values.provenance_events),
    providerBlockers: asRecordArray(values.provider_blockers),
    handoffDecision: asRecord(values.handoff_decision),
    handoffSummary: asRecord(values.handoff_summary),
    ticketHandoffRefs: asRecordArray(values.ticket_handoff_refs),
    ticketLoopDecision: asRecord(values.ticket_loop_decision),
    ticketLoopPolicyActions: asRecordArray(values.ticket_loop_policy_actions),
    runtimeStatus: asRecord(values.runtime_status),
    workbenchPanels: asRecord(values.workbench_panels),
  };
}

export function responseFromValues(values: Record<string, unknown>): ChatMessageResponse | null {
  const response = values.aiteamos_chat_response;
  return response && typeof response === "object" && !Array.isArray(response)
    ? response as ChatMessageResponse
    : null;
}

export function hasWorkbenchSnapshot(snapshot: WorkbenchSnapshot | null): snapshot is WorkbenchSnapshot {
  if (!snapshot) return false;
  return (
    Object.keys(snapshot.activeTicket).length > 0
    || Object.keys(snapshot.employeeIdentity).length > 0
    || Object.keys(snapshot.ticketBinding).length > 0
    || snapshot.linkedAssets.length > 0
    || snapshot.recalledMemoryRefs.length > 0
    || snapshot.approvalRequests.length > 0
    || snapshot.approvalRecords.length > 0
    || snapshot.assetCandidates.length > 0
    || snapshot.providerBlockers.length > 0
    || Object.keys(snapshot.handoffDecision).length > 0
    || Object.keys(snapshot.handoffSummary).length > 0
    || snapshot.ticketHandoffRefs.length > 0
    || Object.keys(snapshot.ticketLoopDecision).length > 0
    || snapshot.ticketLoopPolicyActions.length > 0
    || Object.keys(snapshot.runtimeStatus).length > 0
  );
}

export function workbenchSnapshotSignature(snapshot: WorkbenchSnapshot): string {
  return JSON.stringify(snapshot);
}

export async function fetchLangGraphThreadValues(apiUrl: string, threadId: string): Promise<Record<string, unknown>> {
  const client = new LangGraphClient<Record<string, unknown>>({ apiUrl: normalizeUrl(apiUrl) });
  const state = await client.threads.getState<Record<string, unknown>>(threadId);
  return asRecord(state.values);
}

function pendingInterruptsFromState(state: unknown): PendingInterrupt[] {
  const record = asRecord(state);
  const rawInterrupts = Array.isArray(record.interrupts) ? record.interrupts : [];
  return rawInterrupts.map((item) => {
    const interrupt = asRecord(item);
    return {
      id: metadataText(interrupt.id) !== "-" ? metadataText(interrupt.id) : "",
      namespace: asStringArray(interrupt.ns ?? interrupt.namespace),
      value: asRecord(interrupt.value),
    };
  }).filter((item) => item.id);
}

export async function fetchLangGraphPendingInterrupt(
  apiUrl: string,
  threadId: string,
  approvalRef: string,
): Promise<PendingInterrupt | null> {
  const client = new LangGraphClient<Record<string, unknown>>({ apiUrl: normalizeUrl(apiUrl) });
  const state = await client.threads.getState<Record<string, unknown>>(threadId);
  const interrupts = pendingInterruptsFromState(state);
  return interrupts.find((item) => metadataText(item.value.approval_ref) === approvalRef) ?? interrupts[0] ?? null;
}

export async function sendLangGraphInputRespond({
  apiUrl,
  interruptId,
  namespace,
  response,
  threadId,
}: {
  apiUrl: string;
  interruptId: string;
  namespace: string[];
  response: Record<string, unknown>;
  threadId: string;
}) {
  const commandResponse = await fetch(`${normalizeUrl(apiUrl)}/threads/${encodeURIComponent(threadId)}/commands`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      id: Date.now(),
      method: "input.respond",
      params: {
        namespace,
        interrupt_id: interruptId,
        response,
      },
    }),
  });
  if (!commandResponse.ok) {
    const text = await commandResponse.text().catch(() => "");
    throw new Error(text || `LangGraph resume failed with HTTP ${commandResponse.status}`);
  }
}

export function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    globalThis.setTimeout(resolve, ms);
  });
}
