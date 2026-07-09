import { ReactNode, useCallback, useEffect, useMemo, useRef } from "react";
import { AssistantRuntimeProvider, useComposerRuntime } from "@assistant-ui/react";
import { InMemoryThreadListAdapter } from "@assistant-ui/core";
import {
  useLangChainError,
  useLangChainInterruptState,
  useLangChainState,
  useStreamRuntime,
} from "@assistant-ui/react-langchain";
import type { ChatMessageResponse } from "../../../api/chat";
import {
  delay,
  fetchLangGraphThreadValues,
  hasWorkbenchSnapshot,
  langGraphApiUrl,
  langGraphAssistantId,
  readLangGraphExternalThreadId,
  responseFromValues,
  type WorkbenchInitialState,
  type WorkbenchSnapshot,
  workbenchSnapshotFromValues,
  workbenchSnapshotSignature,
  writeLangGraphExternalThreadId,
} from "./workbenchState";

const EMPTY_WORKBENCH_ARRAY: Record<string, unknown>[] = [];
const EMPTY_INTERRUPT_NAMESPACE: string[] = [];

function metadataText(value: unknown): string {
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  return typeof value === "string" && value.trim() ? value : "-";
}

export interface WorkbenchInterruptInfo {
  approvalRef: string;
  interruptId: string;
  namespace: string[];
}

export function AiteamosWorkbenchRuntimeProvider({
  approvalRef, children, ticketKey, onError, onResponse, onRuntimeThreadId, onSnapshot, selectedEmployeeId, threadId,
}: {
  approvalRef: string;
  children: ReactNode; ticketKey: string; onError: (e: Error) => void;
  onResponse: (response: ChatMessageResponse) => void;
  onRuntimeThreadId: (threadId: string) => void;
  onSnapshot: (snapshot: WorkbenchSnapshot) => void;
  selectedEmployeeId: string; threadId: string;
}) {
  const apiUrl = langGraphApiUrl();
  const assistantId = langGraphAssistantId();
  const contextRef = useRef({ apiUrl, assistantId, onError, onResponse, onSnapshot, threadId });
  useEffect(() => {
    contextRef.current = { apiUrl, assistantId, onError, onResponse, onSnapshot, threadId };
  }, [apiUrl, assistantId, onError, onResponse, onSnapshot, threadId]);

  const ensureExternalThreadId = useCallback(async () => {
    return readLangGraphExternalThreadId(apiUrl, assistantId, threadId) || undefined;
  }, [apiUrl, assistantId, threadId]);

  const threadListAdapter = useMemo(() => {
    const adapter = new InMemoryThreadListAdapter();
    adapter.initialize = async (runtimeThreadId: string) => ({
      remoteId: runtimeThreadId,
      externalId: await ensureExternalThreadId(),
    });
    return adapter;
  }, [ensureExternalThreadId]);

  const hydrateCompletedState = useCallback(async (retry = false) => {
    const context = contextRef.current;
    const langGraphThreadId = readLangGraphExternalThreadId(context.apiUrl, context.assistantId, context.threadId);
    if (!langGraphThreadId) return;
    const attempts = retry ? [600, 1200, 2400, 4800, 8000, 12000, 16000] : [0];
    let lastError: unknown = null;
    for (const waitMs of attempts) {
      if (waitMs > 0) await delay(waitMs);
      try {
        const values = await fetchLangGraphThreadValues(context.apiUrl, langGraphThreadId);
        const response = responseFromValues(values);
        if (response) context.onResponse(response);
        const snapshot = workbenchSnapshotFromValues(values);
        if (hasWorkbenchSnapshot(snapshot)) context.onSnapshot(snapshot);
        if (response || hasWorkbenchSnapshot(snapshot)) return;
      } catch (error) {
        lastError = error;
      }
    }
    if (lastError) {
      context.onError(lastError instanceof Error ? lastError : new Error(String(lastError)));
    }
  }, []);

  const runtimeOptions = useMemo(() => ({
    apiUrl,
    assistantId,
    messagesKey: "messages",
    threadId: threadId || null,
    initialValues: {
      messages: [],
      thread_id: threadId,
      employee_id: selectedEmployeeId,
      ticket_key: ticketKey,
      approval_ref: approvalRef,
    } satisfies WorkbenchInitialState,
    create: async () => ({ externalId: await ensureExternalThreadId() }),
    onThreadId: (langGraphThreadId: string) => {
      const context = contextRef.current;
      writeLangGraphExternalThreadId(context.apiUrl, context.assistantId, context.threadId, langGraphThreadId);
      onRuntimeThreadId(langGraphThreadId);
    },
    onCreated: () => { void hydrateCompletedState(true); },
    onCompleted: () => { void hydrateCompletedState(); },
    optimistic: true,
    unstable_threadListAdapter: threadListAdapter,
  }), [
    apiUrl,
    approvalRef,
    assistantId,
    ensureExternalThreadId,
    hydrateCompletedState,
    onRuntimeThreadId,
    selectedEmployeeId,
    threadId,
    threadListAdapter,
    ticketKey,
  ]);
  const assistantRuntime = useStreamRuntime(runtimeOptions);
  return <AssistantRuntimeProvider runtime={assistantRuntime}>{children}</AssistantRuntimeProvider>;
}

export function WorkbenchRunConfigBridge({
  approvalRef,
  selectedEmployeeId,
  ticketKey,
  threadId,
}: {
  approvalRef: string;
  selectedEmployeeId: string;
  ticketKey: string;
  threadId: string;
}) {
  const composer = useComposerRuntime({ optional: true });
  useEffect(() => {
    composer?.setRunConfig({
      custom: {
        target_employee_id: selectedEmployeeId,
        employee_id: selectedEmployeeId,
        ticket_key: ticketKey.trim(),
        approval_ref: approvalRef.trim(),
        thread_id: threadId,
        runtime_config: { source: "aiteamos_chat_workbench" },
      },
    });
  }, [approvalRef, composer, selectedEmployeeId, threadId, ticketKey]);
  return null;
}

export function WorkbenchStateBridge({
  onResponse,
  onSnapshot,
}: {
  onResponse: (r: ChatMessageResponse) => void;
  onSnapshot: (snapshot: WorkbenchSnapshot) => void;
}) {
  const response = useLangChainState<ChatMessageResponse | null>("aiteamos_chat_response", null);
  const activeTicket = useLangChainState<unknown>("active_ticket", null);
  const selectedEmployee = useLangChainState<unknown>("selected_employee", null);
  const employeeIdentity = useLangChainState<unknown>("employee_identity", null);
  const ticketBinding = useLangChainState<unknown>("ticket_binding", null);
  const linkedAssets = useLangChainState<unknown>("linked_assets", EMPTY_WORKBENCH_ARRAY);
  const recalledMemoryRefs = useLangChainState<unknown>("recalled_memory_refs", EMPTY_WORKBENCH_ARRAY);
  const approvalRequests = useLangChainState<unknown>("approval_requests", EMPTY_WORKBENCH_ARRAY);
  const approvalRecords = useLangChainState<unknown>("approval_records", EMPTY_WORKBENCH_ARRAY);
  const assetCandidates = useLangChainState<unknown>("asset_candidates", EMPTY_WORKBENCH_ARRAY);
  const provenanceEvents = useLangChainState<unknown>("provenance_events", EMPTY_WORKBENCH_ARRAY);
  const providerBlockers = useLangChainState<unknown>("provider_blockers", EMPTY_WORKBENCH_ARRAY);
  const handoffDecision = useLangChainState<unknown>("handoff_decision", null);
  const handoffSummary = useLangChainState<unknown>("handoff_summary", null);
  const ticketHandoffRefs = useLangChainState<unknown>("ticket_handoff_refs", EMPTY_WORKBENCH_ARRAY);
  const ticketLoopDecision = useLangChainState<unknown>("ticket_loop_decision", null);
  const ticketLoopPolicyActions = useLangChainState<unknown>("ticket_loop_policy_actions", EMPTY_WORKBENCH_ARRAY);
  const runtimeStatus = useLangChainState<unknown>("runtime_status", null);
  const workbenchPanels = useLangChainState<unknown>("workbench_panels", null);
  const lastRunIdRef = useRef<string | null>(null);
  const lastSnapshotRef = useRef<string | null>(null);
  const snapshot = useMemo<WorkbenchSnapshot>(() => workbenchSnapshotFromValues({
    active_ticket: activeTicket,
    selected_employee: selectedEmployee,
    employee_identity: employeeIdentity,
    ticket_binding: ticketBinding,
    linked_assets: linkedAssets,
    recalled_memory_refs: recalledMemoryRefs,
    approval_requests: approvalRequests,
    approval_records: approvalRecords,
    asset_candidates: assetCandidates,
    provenance_events: provenanceEvents,
    provider_blockers: providerBlockers,
    handoff_decision: handoffDecision,
    handoff_summary: handoffSummary,
    ticket_handoff_refs: ticketHandoffRefs,
    ticket_loop_decision: ticketLoopDecision,
    ticket_loop_policy_actions: ticketLoopPolicyActions,
    runtime_status: runtimeStatus,
    workbench_panels: workbenchPanels,
  }), [
    activeTicket,
    approvalRecords,
    approvalRequests,
    assetCandidates,
    employeeIdentity,
    handoffDecision,
    handoffSummary,
    linkedAssets,
    provenanceEvents,
    providerBlockers,
    recalledMemoryRefs,
    runtimeStatus,
    selectedEmployee,
    ticketHandoffRefs,
    ticketBinding,
    ticketLoopDecision,
    ticketLoopPolicyActions,
    workbenchPanels,
  ]);
  useEffect(() => {
    if (!response || response.run_id === lastRunIdRef.current) return;
    lastRunIdRef.current = response.run_id;
    onResponse(response);
  }, [onResponse, response]);
  useEffect(() => {
    if (!hasWorkbenchSnapshot(snapshot)) return;
    const signature = workbenchSnapshotSignature(snapshot);
    if (signature === lastSnapshotRef.current) return;
    lastSnapshotRef.current = signature;
    onSnapshot(snapshot);
  }, [onSnapshot, snapshot]);
  return null;
}

export function WorkbenchErrorBridge({ onError }: { onError: (e: Error) => void }) {
  const runtimeError = useLangChainError();
  useEffect(() => {
    if (!runtimeError) return;
    onError(runtimeError instanceof Error ? runtimeError : new Error(String(runtimeError)));
  }, [onError, runtimeError]);
  return null;
}

export function WorkbenchInterruptBridge({ onInterrupt }: { onInterrupt: (value: WorkbenchInterruptInfo) => void }) {
  const interrupt = useLangChainInterruptState() as { id?: string; ns?: string[]; value?: unknown } | undefined;
  const lastInterruptSignatureRef = useRef("");
  useEffect(() => {
    const value = interrupt?.value;
    if (!value || typeof value !== "object" || Array.isArray(value)) return;
    const record = value as Record<string, unknown>;
    const approvalRef = metadataText(record.approval_ref || record.approval_id || interrupt?.id);
    if (approvalRef !== "-") {
      const namespace = Array.isArray(interrupt?.ns) ? interrupt.ns : EMPTY_INTERRUPT_NAMESPACE;
      const signature = JSON.stringify({ approvalRef, interruptId: interrupt?.id ?? "", namespace });
      if (signature === lastInterruptSignatureRef.current) return;
      lastInterruptSignatureRef.current = signature;
      onInterrupt({
        approvalRef,
        interruptId: interrupt?.id ?? "",
        namespace,
      });
    }
  }, [interrupt, onInterrupt]);
  return null;
}
