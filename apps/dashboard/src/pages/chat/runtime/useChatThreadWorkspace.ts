import { useCallback, useMemo, useState } from "react";
import {
  activateChatThread,
  createChatThread,
  deleteChatThread,
  listChatThreads,
  type ChatEmployeeSummary,
  type ChatThreadSummary,
} from "../../../api/chat";

function safeThreadComponent(value: string): string {
  return value.replace(/[^A-Za-z0-9_.:-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80) || "employee";
}

export function defaultThreadIdForEmployee(employee: ChatEmployeeSummary | null): string {
  if (!employee) return "employee-clara-default";
  return employee.default_thread_id || `employee-${safeThreadComponent(employee.id)}-default`;
}

export function useChatThreadWorkspace({
  clearPendingApproval,
  clearRunState,
  onError,
  selectedEmployee,
}: {
  clearPendingApproval: () => void;
  clearRunState: () => void;
  onError: (message: string | null) => void;
  selectedEmployee: ChatEmployeeSummary | null;
}) {
  const [threads, setThreads] = useState<ChatThreadSummary[]>([]);
  const [threadId, setThreadId] = useState("");
  const [openThreadIds, setOpenThreadIds] = useState<string[]>([]);
  const [threadHistoryOpen, setThreadHistoryOpen] = useState(false);
  const [threadQuery, setThreadQuery] = useState("");
  const [threadsLoading, setThreadsLoading] = useState(false);
  const [deletingThreadId, setDeletingThreadId] = useState<string | null>(null);

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
      const ids = new Set(response.threads.map((thread) => thread.id));
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
    } finally {
      setThreadsLoading(false);
    }
  }, []);

  const registerResponseThread = useCallback((employee: ChatEmployeeSummary, nextThreadId: string) => {
    setThreadId(nextThreadId);
    void loadThreadsForEmployee(employee, nextThreadId).catch((err) => {
      onError(err instanceof Error ? err.message : "Failed to reload threads");
    });
  }, [loadThreadsForEmployee, onError]);

  const prepareEmployeeThreadWorkspace = useCallback(async (employee: ChatEmployeeSummary | null) => {
    onError(null);
    setThreadId(defaultThreadIdForEmployee(employee));
    clearPendingApproval();
    clearRunState();
    setOpenThreadIds([]);
    setThreadQuery("");
    try {
      await loadThreadsForEmployee(employee);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to load employee threads");
    }
  }, [clearPendingApproval, clearRunState, loadThreadsForEmployee, onError]);

  const resetThread = useCallback(async () => {
    if (!selectedEmployee) return;
    onError(null);
    try {
      const thread = await createChatThread(selectedEmployee.id);
      setThreads((current) => [thread, ...current.filter((item) => item.id !== thread.id)]);
      setThreadId(thread.id);
      clearPendingApproval();
      clearRunState();
      setOpenThreadIds((current) => current.includes(thread.id) ? current : [...current, thread.id]);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to create thread");
    }
  }, [clearPendingApproval, clearRunState, onError, selectedEmployee]);

  const switchThread = useCallback(async (nextThread: ChatThreadSummary) => {
    if (!selectedEmployee) return;
    setOpenThreadIds((current) => current.includes(nextThread.id) ? current : [...current, nextThread.id]);
    if (nextThread.id === activeThreadId) return;
    onError(null);
    const previousThreadId = activeThreadId;
    setThreadId(nextThread.id);
    clearPendingApproval();
    clearRunState();
    try {
      await activateChatThread(nextThread.id, selectedEmployee.id);
    } catch (err) {
      setThreadId(previousThreadId);
      onError(err instanceof Error ? err.message : "Failed to switch thread");
    }
  }, [activeThreadId, clearPendingApproval, clearRunState, onError, selectedEmployee]);

  const closeWorkspaceThread = useCallback(async (thread: ChatThreadSummary) => {
    const currentOpenIds = openThreads.map((item) => item.id);
    if (currentOpenIds.length <= 1) return;

    const nextOpenIds = currentOpenIds.filter((id) => id !== thread.id);
    setOpenThreadIds(nextOpenIds);

    if (thread.id !== activeThreadId) return;
    const closedIndex = currentOpenIds.indexOf(thread.id);
    const nextThreadId = nextOpenIds[Math.min(closedIndex, nextOpenIds.length - 1)] ?? nextOpenIds[0];
    const nextThread = threads.find((item) => item.id === nextThreadId);
    if (nextThread) await switchThread(nextThread);
  }, [activeThreadId, openThreads, switchThread, threads]);

  const deleteThread = useCallback(async (thread: ChatThreadSummary) => {
    if (!selectedEmployee) return;
    if (!window.confirm(`Delete thread "${thread.title || thread.id}"?`)) return;
    setDeletingThreadId(thread.id);
    try {
      await deleteChatThread(thread.id);
      const remaining = threads.filter((item) => item.id !== thread.id);
      setThreads(remaining);
      setOpenThreadIds((current) => current.filter((id) => id !== thread.id));
      if (thread.id === activeThreadId) {
        const fallback = remaining[0] ?? null;
        if (fallback) {
          await switchThread(fallback);
        } else {
          await resetThread();
        }
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to delete thread");
    } finally {
      setDeletingThreadId(null);
    }
  }, [activeThreadId, onError, resetThread, selectedEmployee, switchThread, threads]);

  return {
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
  };
}
