import { useCallback, useEffect, useMemo, useState } from "react";
import { Panel, Group, Separator } from "react-resizable-panels";
import { ErrorState, LoadingState } from "../../components/shared";
import {
  getChatAiEngines,
  listChatEmployees,
  updateChatAiEngine,
  type ChatEmployeeSummary,
  type ChatMessageResponse,
  type ChatAiEngineRecord,
  type ChatAiEngineSettings,
  type ChatAiEngineUpdateRequest,
  type ChatTraceEvent,
} from "../../api/chat";
import {
  getCapabilities,
  type CapabilityRecord,
  type CapabilityRegistryResponse,
} from "../../api/capabilities";
import { cn } from "@/lib/utils";
import {
  AiteamosWorkbenchRuntimeProvider,
  WorkbenchErrorBridge,
  WorkbenchInterruptBridge,
  WorkbenchRunConfigBridge,
  WorkbenchStateBridge,
} from "./runtime/LangGraphWorkbenchProvider";
import {
  hasWorkbenchSnapshot,
  readCurrentLangGraphThreadId,
  responseFromValues,
  type WorkbenchSnapshot,
  workbenchSnapshotFromValues,
} from "./runtime/workbenchState";
import { createWorkbenchRunViewModel } from "./runtime/workbenchRunViewModel";
import { useChatThreadWorkspace } from "./runtime/useChatThreadWorkspace";
import { ApprovalPanel } from "./panels/ApprovalPanel";
import { AssetCandidatesPanel } from "./panels/AssetCandidatesPanel";
import { CurrentEmployeePanel } from "./panels/CurrentEmployeePanel";
import { LatestRunPanel } from "./panels/LatestRunPanel";
import { RunProvenancePanel } from "./panels/RunProvenancePanel";
import { ScopedContextPanel } from "./panels/ScopedContextPanel";
import { TicketLoopPolicyPanel } from "./panels/TicketLoopPolicyPanel";
import { TicketLoopResumePanel } from "./panels/TicketLoopResumePanel";
import { TracePanel } from "./panels/TracePanel";
import { ThreadHistoryPanel } from "./panels/ThreadHistoryPanel";
import { WorkbenchDetailsPanel } from "./panels/WorkbenchDetailsPanel";
import { WorkbenchSnapshotPanel } from "./panels/WorkbenchSnapshotPanel";
import { WorkbenchThreadPanel } from "./panels/WorkbenchThreadPanel";
import { ThreadWorkspaceTabsPanel } from "./panels/ThreadWorkspaceTabsPanel";

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

function isSelectableAiEngine(engine: ChatAiEngineRecord): boolean {
  return (engine.support_status ?? "supported") === "supported";
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

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function metadataText(value: unknown): string {
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  return typeof value === "string" && value.trim() ? value : "-";
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
  const [pendingApprovalRef, setPendingApprovalRef] = useState("");
  const [pendingInterruptId, setPendingInterruptId] = useState("");
  const [pendingInterruptNamespace, setPendingInterruptNamespace] = useState<string[]>([]);
  const [langGraphRuntimeThreadId, setLangGraphRuntimeThreadId] = useState(() => readCurrentLangGraphThreadId());
  const [engineThreadId, setEngineThreadId] = useState<string | null>(null);
  const [traceEvents, setTraceEvents] = useState<ChatTraceEvent[]>([]);
  const [runMetadata, setRunMetadata] = useState<Record<string, unknown> | null>(null);
  const [latestReply, setLatestReply] = useState("");
  const [workbenchSnapshot, setWorkbenchSnapshot] = useState<WorkbenchSnapshot | null>(null);
  const [savedPaths, setSavedPaths] = useState<Record<string, string>>({});
  const [aiEngines, setAiEngines] = useState<ChatAiEngineSettings | null>(null);
  const [capabilityRegistry, setCapabilityRegistry] = useState<CapabilityRegistryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
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

  const clearPendingApproval = useCallback(() => {
    setPendingApprovalRef("");
    setPendingInterruptId("");
    setPendingInterruptNamespace([]);
  }, []);

  const clearRunState = useCallback(() => {
    setEngineThreadId(null);
    setTraceEvents([]);
    setRunMetadata(null);
    setLatestReply("");
    setWorkbenchSnapshot(null);
    setSavedPaths({});
  }, []);

  const {
    activeThread,
    activeThreadId,
    closeWorkspaceThread,
    deletingThreadId,
    deleteThread,
    loadThreadsForEmployee,
    openThreadIds,
    openThreads,
    prepareEmployeeThreadWorkspace,
    registerResponseThread,
    resetThread,
    setThreadHistoryOpen,
    setThreadQuery,
    switchThread,
    threadHistoryOpen,
    threadQuery,
    threads,
    threadsLoading,
  } = useChatThreadWorkspace({
    clearPendingApproval,
    clearRunState,
    onError: setError,
    selectedEmployee,
  });

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
    setPendingApprovalRef("");
    setPendingInterruptId("");
    setPendingInterruptNamespace([]);
    setEngineThreadId(response.engine_thread_id);
    setTraceEvents(response.trace_events);
    setRunMetadata(response.run_metadata ?? null);
    setLatestReply(response.reply);
    setSavedPaths(response.saved_paths);
    writeTextStorage(ACTIVE_EMPLOYEE_STORAGE_KEY, response.target_employee.id);
    registerResponseThread(response.target_employee, response.thread_id);
    if (hasEmployeeProfileMutation(response.trace_events)) {
      void listChatEmployees().then(setEmployees).catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to reload employees");
      });
    }
  }, [registerResponseThread]);

  const handleWorkbenchSnapshot = useCallback((snapshot: WorkbenchSnapshot) => {
    setWorkbenchSnapshot(snapshot);
  }, []);

  const handleWorkbenchValues = useCallback((values: Record<string, unknown>) => {
    const response = responseFromValues(values);
    if (response) handleAgentResponse(response);
    const snapshot = workbenchSnapshotFromValues(values);
    if (hasWorkbenchSnapshot(snapshot)) handleWorkbenchSnapshot(snapshot);
  }, [handleAgentResponse, handleWorkbenchSnapshot]);

  async function selectEmployee(nextEmployeeId: string) {
    const next = employees.find((m) => m.id === nextEmployeeId) ?? null;
    setSelectedEmployeeId(nextEmployeeId);
    writeTextStorage(ACTIVE_EMPLOYEE_STORAGE_KEY, nextEmployeeId);
    setError(null);
    await prepareEmployeeThreadWorkspace(next);
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

  const runViewModel = useMemo(() => createWorkbenchRunViewModel({
    engineThreadId,
    latestReply,
    runMetadata,
    savedPaths,
    traceEvents,
    workbenchSnapshot,
  }), [engineThreadId, latestReply, runMetadata, savedPaths, traceEvents, workbenchSnapshot]);
  if (loading) return <LoadingState />;
  const aiEngineReady = Boolean(
    aiEngines?.active_engine
    && aiEngines.active_engine !== "stub"
    && (activeAiEngineRecord?.config_status ?? activeAiEngineRecord?.status) === "configured",
  );

  return (
    <AiteamosWorkbenchRuntimeProvider
      key={activeThreadId} approvalRef={pendingApprovalRef} ticketKey={ticketKey}
      onError={(err) => setError(err.message)}
      onResponse={handleAgentResponse}
      onRuntimeThreadId={setLangGraphRuntimeThreadId}
      onSnapshot={handleWorkbenchSnapshot}
      selectedEmployeeId={selectedEmployee?.id ?? ""} threadId={activeThreadId}
    >
      <WorkbenchRunConfigBridge
        approvalRef={pendingApprovalRef}
        selectedEmployeeId={selectedEmployee?.id ?? ""}
        ticketKey={ticketKey}
        threadId={activeThreadId}
      />
      <WorkbenchStateBridge onResponse={handleAgentResponse} onSnapshot={handleWorkbenchSnapshot} />
      <WorkbenchErrorBridge onError={(err) => setError(err.message)} />
      <WorkbenchInterruptBridge
        onInterrupt={(interrupt) => {
          setPendingApprovalRef(interrupt.approvalRef);
          setPendingInterruptId(interrupt.interruptId);
          setPendingInterruptNamespace(interrupt.namespace);
        }}
      />
      <div className="h-[calc(100vh-8rem)] overflow-hidden rounded-md border bg-background">
        <Group orientation="horizontal" id="aiteamos-chat-layout">
          {threadHistoryOpen && (
            <>
              <Panel defaultSize="18rem" minSize="14rem" maxSize="28rem">
                <ThreadHistoryPanel
                  activeThreadId={activeThreadId}
                  deletingThreadId={deletingThreadId}
                  openThreadIds={openThreadIds}
                  query={threadQuery}
                  threads={threads}
                  threadsLoading={threadsLoading}
                  onClose={() => setThreadHistoryOpen(false)}
                  onCreateThread={() => void resetThread()}
                  onDeleteThread={(thread) => void deleteThread(thread)}
                  onOpenThread={(thread) => void switchThread(thread)}
                  onQueryChange={setThreadQuery}
                />
              </Panel>
              <ResizeHandle />
            </>
          )}

          <Panel defaultSize={detailsPanelOpen ? 70 : 100} minSize="32rem">
            <section className="flex h-full min-w-0 flex-col">
              <ThreadWorkspaceTabsPanel
                activeThreadId={activeThreadId}
                detailsPanelOpen={detailsPanelOpen}
                openThreads={openThreads}
                threadHistoryOpen={threadHistoryOpen}
                threadsLoading={threadsLoading}
                onCloseThread={(thread) => void closeWorkspaceThread(thread)}
                onCreateThread={() => void resetThread()}
                onOpenThread={(thread) => void switchThread(thread)}
                onToggleDetailsPanel={() => setDetailsPanelOpen((open) => !open)}
                onToggleThreadHistory={() => setThreadHistoryOpen((open) => !open)}
              />

              {error && (
                <div className="border-b p-3">
                  <ErrorState message={error} onRetry={loadChatSurface} />
                </div>
              )}

              <WorkbenchThreadPanel
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
                pendingApprovalRef={pendingApprovalRef}
                onClearApprovalRef={clearPendingApproval}
                visibleResponse={runViewModel.visibleResponse}
                onOpenDetails={() => setDetailsPanelOpen(true)}
              />
            </section>
          </Panel>

          {detailsPanelOpen && <ResizeHandle />}

          {detailsPanelOpen && (
            <Panel defaultSize="24rem" minSize="18rem" maxSize="42rem">
              <WorkbenchDetailsPanel activeThread={activeThread} onClose={() => setDetailsPanelOpen(false)}>
                <WorkbenchSnapshotPanel snapshot={workbenchSnapshot} />
                <TicketLoopResumePanel
                  employeeId={runViewModel.employeeId || selectedEmployee?.id || ""}
                  selectedAiEngine={aiEngines?.active_engine ?? ""}
                  ticketId={runViewModel.primaryTicketId}
                />
                <TicketLoopPolicyPanel {...runViewModel.ticketLoopPolicyProps} />

                <section className="border-b p-3">
                  {runMetadata ? (
                    <div className="space-y-1.5 text-xs">
                      <LatestRunPanel {...runViewModel.latestRunProps} />
                      <ScopedContextPanel {...runViewModel.scopedContextProps} />
                      <ApprovalPanel
                        {...runViewModel.approvalProps}
                        pendingInterruptId={pendingInterruptId}
                        pendingInterruptNamespace={pendingInterruptNamespace}
                        langGraphThreadId={langGraphRuntimeThreadId}
                        onRuntimeValues={handleWorkbenchValues}
                        onResumeIntent={(approvalRef, nextTicketId) => {
                          setPendingApprovalRef(approvalRef);
                          if (nextTicketId) setTicketKey(nextTicketId);
                        }}
                        onError={setError}
                      />
                      <AssetCandidatesPanel candidates={runViewModel.assetCandidates} onError={setError} />
                      <RunProvenancePanel {...runViewModel.provenanceProps} />
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground">No run selected yet.</p>
                  )}
                </section>

                <CurrentEmployeePanel
                  capabilities={capabilities}
                  employee={selectedEmployee}
                  threadCount={threads.length}
                />
                <TracePanel savedPaths={savedPaths} traceEvents={traceEvents} />
              </WorkbenchDetailsPanel>
            </Panel>
          )}
        </Group>
      </div>
    </AiteamosWorkbenchRuntimeProvider>
  );
}
