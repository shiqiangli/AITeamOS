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
import { Activity, Bot, GitBranch, KeyRound, MessageSquare, Plus, Send, User } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Select } from "../../components/ui/select";
import { ErrorState, LoadingState, Status, navigateTo } from "../../components/shared";
import {
  activateChatThread,
  createChatThread,
  getChatThread,
  getChatRuntime,
  listChatThreads,
  listChatMembers,
  type ConversationMessage,
  type ChatMemberSummary,
  type ChatMessageResponse,
  type ChatRuntimeSettings,
  type ChatThreadSummary,
  type ChatTraceEvent,
} from "../../api/chat";
import { cn } from "@/lib/utils";

function hasMemberProfileMutation(events: ChatTraceEvent[]): boolean {
  return events.some((event) => (
    event.event === "tool.create_member.completed"
    || event.event === "tool.edit_member_profile.completed"
    || event.event === "tool.delete_member.completed"
    || event.event === "tool.assign_skill_to_member.completed"
    || event.event === "tool.delete_skill.completed"
  ));
}

const ACTIVE_MEMBER_STORAGE_KEY = "aiteamos.chat.activeMemberId";

function readTextStorage(key: string): string {
  try {
    return globalThis.localStorage?.getItem(key) ?? "";
  } catch {
    return "";
  }
}

function writeTextStorage(key: string, value: string): void {
  try {
    globalThis.localStorage?.setItem(key, value);
  } catch {
    // Local storage is optional; file-backed backend history remains canonical.
  }
}

function safeThreadComponent(value: string): string {
  return value.replace(/[^A-Za-z0-9_.:-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80) || "member";
}

function defaultThreadIdForMember(member: ChatMemberSummary | null): string {
  if (!member) return "member-clara-default";
  return member.default_thread_id || `member-${safeThreadComponent(member.id)}-default`;
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
  const common = {
    id: messageIdForConversation(message, index),
    createdAt: parseConversationDate(message.timestamp),
    content: [{ type: "text" as const, text: message.content }],
    metadata: {
      custom: {
        aiteamos: {
          member_id: message.member_id,
          run_id: message.run_id,
        },
      },
    },
  };

  if (message.role === "user") {
    return {
      ...common,
      role: "user",
      attachments: [],
    };
  }

  return {
    ...common,
    role: "assistant",
    status: { type: "complete", reason: "stop" },
    metadata: {
      unstable_state: null,
      unstable_annotations: [],
      unstable_data: [],
      steps: [],
      custom: common.metadata.custom,
    },
  };
}

function conversationToHistory(messages: ConversationMessage[]): Awaited<ReturnType<ThreadHistoryAdapter["load"]>> {
  const threadMessages = messages
    .map(toThreadMessage)
    .filter((message): message is ThreadMessage => Boolean(message));

  return {
    headId: threadMessages.length > 0 ? threadMessages[threadMessages.length - 1]!.id : null,
    messages: threadMessages.map((message, index) => ({
      parentId: index > 0 ? threadMessages[index - 1]!.id : null,
      message,
    })),
  };
}

function buildAgentUrl(targetMemberId: string, jiraKey: string): string {
  const params = new URLSearchParams();
  if (targetMemberId) params.set("target_member_id", targetMemberId);
  const trimmedJiraKey = jiraKey.trim();
  if (trimmedJiraKey) params.set("jira_key", trimmedJiraKey);

  const query = params.toString();
  return `/api/v1/chat/agent${query ? `?${query}` : ""}`;
}

function isChatMessageResponse(value: unknown): value is ChatMessageResponse {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.thread_id === "string"
    && typeof record.run_id === "string"
    && typeof record.provider_thread_id === "string"
    && Array.isArray(record.trace_events)
    && !!record.saved_paths
    && typeof record.saved_paths === "object"
  );
}

function extractAiteamosResponse(state: unknown): ChatMessageResponse | null {
  if (!state || typeof state !== "object") return null;
  const response = (state as Record<string, unknown>).aiteamos_chat_response;
  return isChatMessageResponse(response) ? response : null;
}

function AiteamosAgUiRuntimeProvider({
  children,
  jiraKey,
  onError,
  selectedMemberId,
  threadId,
}: {
  children: ReactNode;
  jiraKey: string;
  onError: (error: Error) => void;
  selectedMemberId: string;
  threadId: string;
}) {
  const agent = useMemo(
    () => new HttpAgent({
      url: buildAgentUrl(selectedMemberId, jiraKey),
      threadId,
      fetch: (url, requestInit) => globalThis.fetch(url, requestInit),
    }),
    [jiraKey, selectedMemberId, threadId],
  );
  const history = useMemo<ThreadHistoryAdapter>(() => ({
    async load() {
      const thread = await getChatThread(threadId);
      return conversationToHistory(thread.messages);
    },
    async append() {
      // The FastAPI AG-UI endpoint persists the canonical file-backed transcript.
    },
  }), [threadId]);
  const runtime = useAgUiRuntime({
    agent,
    showThinking: false,
    onError,
    adapters: {
      history,
      threadList: {
        threadId,
        async onSwitchToThread(nextThreadId) {
          const thread = await getChatThread(nextThreadId);
          return {
            messages: conversationToHistory(thread.messages).messages.map((item) => item.message),
          };
        },
      },
    },
  });

  return <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>;
}

function ChatStateBridge({ onResponse }: { onResponse: (response: ChatMessageResponse) => void }) {
  const threadState = useAuiState((state) => state.thread.state as unknown);
  const response = useMemo(() => extractAiteamosResponse(threadState), [threadState]);
  const lastRunIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!response || response.run_id === lastRunIdRef.current) return;
    lastRunIdRef.current = response.run_id;
    onResponse(response);
  }, [onResponse, response]);

  return null;
}

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

function AiteamosThread({ selectedMember }: { selectedMember: ChatMemberSummary | null }) {
  return (
    <ThreadPrimitive.Root className="flex min-h-0 flex-1 flex-col">
      <ThreadPrimitive.Viewport className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4">
        <ThreadPrimitive.Empty>
          <div className="flex h-full min-h-[18rem] items-center justify-center text-sm text-muted-foreground">
            {selectedMember ? `${selectedMember.display_name} is ready.` : "No members loaded."}
          </div>
        </ThreadPrimitive.Empty>
        <div className="space-y-4">
          <ThreadPrimitive.Messages
            components={{
              UserMessage,
              AssistantMessage,
            }}
          />
        </div>
        <ThreadPrimitive.ViewportFooter className="sticky bottom-0 mt-auto bg-background pt-4">
          <ComposerPrimitive.Root className="grid gap-3 border-t bg-background pt-4 sm:grid-cols-[minmax(0,1fr)_auto]">
            <ComposerPrimitive.Input
              aria-label="Chat message"
              placeholder={selectedMember ? `Message ${selectedMember.display_name}` : "Message"}
              submitMode="enter"
              className="min-h-[5.5rem] resize-none rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            <ComposerPrimitive.Send className={cn(
              "inline-flex h-full min-h-[5.5rem] items-center justify-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm transition-colors",
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

export function ChatPage() {
  const [members, setMembers] = useState<ChatMemberSummary[]>([]);
  const [selectedMemberId, setSelectedMemberId] = useState(() => readTextStorage(ACTIVE_MEMBER_STORAGE_KEY));
  const [jiraKey, setJiraKey] = useState("");
  const [threads, setThreads] = useState<ChatThreadSummary[]>([]);
  const [threadId, setThreadId] = useState("");
  const [providerThreadId, setProviderThreadId] = useState<string | null>(null);
  const [traceEvents, setTraceEvents] = useState<ChatTraceEvent[]>([]);
  const [savedPaths, setSavedPaths] = useState<Record<string, string>>({});
  const [runtime, setRuntime] = useState<ChatRuntimeSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [threadsLoading, setThreadsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedMember = useMemo(
    () => members.find((member) => member.id === selectedMemberId) ?? members[0] ?? null,
    [members, selectedMemberId],
  );
  const activeThreadId = threadId || defaultThreadIdForMember(selectedMember);

  const loadThreadsForMember = useCallback(async (
    member: ChatMemberSummary | null,
    preferredThreadId?: string,
  ) => {
    if (!member) return "";
    setThreadsLoading(true);
    try {
      const response = await listChatThreads(member.id);
      setThreads(response.threads);
      const availableIds = new Set(response.threads.map((thread) => thread.id));
      const nextThreadId = (
        preferredThreadId && availableIds.has(preferredThreadId)
          ? preferredThreadId
          : response.active_thread_id || response.threads[0]?.id || defaultThreadIdForMember(member)
      );
      setThreadId(nextThreadId);
      return nextThreadId;
    } finally {
      setThreadsLoading(false);
    }
  }, []);

  const loadWorkbench = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [loaded, loadedRuntime] = await Promise.all([listChatMembers(), getChatRuntime()]);
      setMembers(loaded);
      setRuntime(loadedRuntime);
      const storedMemberId = readTextStorage(ACTIVE_MEMBER_STORAGE_KEY);
      const preferred = (
        loaded.find((member) => member.id === storedMemberId)
        ?? loaded.find((member) => member.id === "clara")
        ?? loaded[0]
        ?? null
      );
      const nextMemberId = preferred?.id ?? "";
      setSelectedMemberId(nextMemberId);
      if (nextMemberId) writeTextStorage(ACTIVE_MEMBER_STORAGE_KEY, nextMemberId);
      await loadThreadsForMember(preferred);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load chat workbench");
    } finally {
      setLoading(false);
    }
  }, [loadThreadsForMember]);

  useEffect(() => {
    loadWorkbench();
  }, [loadWorkbench]);

  const handleAgentResponse = useCallback((response: ChatMessageResponse) => {
    setThreadId(response.thread_id);
    setProviderThreadId(response.provider_thread_id);
    setTraceEvents(response.trace_events);
    setSavedPaths(response.saved_paths);
    writeTextStorage(ACTIVE_MEMBER_STORAGE_KEY, response.target_member.id);
    void loadThreadsForMember(response.target_member, response.thread_id)
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to reload threads");
      });

    if (hasMemberProfileMutation(response.trace_events)) {
      void listChatMembers()
        .then(setMembers)
        .catch((err) => {
          setError(err instanceof Error ? err.message : "Failed to reload members");
        });
    }
  }, [loadThreadsForMember]);

  async function resetThread() {
    if (!selectedMember) return;
    setError(null);
    try {
      const thread = await createChatThread(selectedMember.id);
      await loadThreadsForMember(selectedMember, thread.id);
      setProviderThreadId(null);
      setTraceEvents([]);
      setSavedPaths({});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create thread");
    }
  }

  async function selectMember(nextMemberId: string) {
    const nextMember = members.find((member) => member.id === nextMemberId) ?? null;
    setSelectedMemberId(nextMemberId);
    writeTextStorage(ACTIVE_MEMBER_STORAGE_KEY, nextMemberId);
    setThreadId(defaultThreadIdForMember(nextMember));
    setProviderThreadId(null);
    setTraceEvents([]);
    setSavedPaths({});
    setError(null);
    try {
      await loadThreadsForMember(nextMember);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load member threads");
    }
  }

  async function switchThread(nextThread: ChatThreadSummary) {
    if (!selectedMember || nextThread.id === activeThreadId) return;
    setError(null);
    try {
      await activateChatThread(nextThread.id, selectedMember.id);
      await loadThreadsForMember(selectedMember, nextThread.id);
      setProviderThreadId(null);
      setTraceEvents([]);
      setSavedPaths({});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to switch thread");
    }
  }

  if (loading) return <LoadingState />;

  return (
    <AiteamosAgUiRuntimeProvider
      key={activeThreadId}
      jiraKey={jiraKey}
      onError={(err) => setError(err.message)}
      selectedMemberId={selectedMember?.id ?? ""}
      threadId={activeThreadId}
    >
      <ChatStateBridge onResponse={handleAgentResponse} />
      <div className="grid min-h-[calc(100vh-11rem)] gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <section className="flex min-h-[36rem] flex-col overflow-hidden rounded-md border bg-background">
          <div className="flex flex-wrap items-center gap-3 border-b px-4 py-3">
            <div className="flex min-w-[14rem] flex-1 items-center gap-2">
              <Bot className="h-4 w-4 text-muted-foreground" />
              <Select
                aria-label="Target member"
                value={selectedMember?.id ?? ""}
                onChange={(event) => void selectMember(event.target.value)}
              >
                {members.map((member) => (
                  <option key={member.id} value={member.id}>
                    {member.display_name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="flex min-w-[11rem] items-center gap-2">
              <GitBranch className="h-4 w-4 text-muted-foreground" />
              <input
                aria-label="Jira key"
                value={jiraKey}
                onChange={(event) => setJiraKey(event.target.value)}
                placeholder="Jira"
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            <Button type="button" variant="outline" size="icon" onClick={() => void resetThread()} title="New thread">
              <Plus className="h-4 w-4" />
            </Button>
          </div>

          {error && (
            <div className="border-b p-4">
              <ErrorState message={error} onRetry={loadWorkbench} />
            </div>
          )}

          <AiteamosThread selectedMember={selectedMember} />
        </section>

        <aside className="space-y-4">
          <section className="rounded-md border bg-background p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <KeyRound className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-sm font-semibold">Runtime</h3>
              </div>
              <Button type="button" variant="outline" size="sm" onClick={() => navigateTo("settings", "runtimes")}>
                Settings
              </Button>
            </div>
            <div className="space-y-3">
              <Status label="Provider" value={runtime?.provider ?? "-"} />
              <Status label="Fallback" value={runtime?.fallback_on_error ? "on" : "off"} />
              <div className="flex flex-wrap gap-2">
                <Badge variant={runtime?.api_keys_configured.deepseek ? "success" : "outline"}>
                  DeepSeek {runtime?.api_keys_configured.deepseek ? "key set" : "missing"}
                </Badge>
                <Badge variant={runtime?.api_keys_configured.openai ? "success" : "outline"}>
                  OpenAI {runtime?.api_keys_configured.openai ? "key set" : "missing"}
                </Badge>
              </div>
            </div>
          </section>

          <section className="rounded-md border bg-background p-4">
            <div className="mb-3 flex items-center gap-2">
              <Bot className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold">Member</h3>
            </div>
            {selectedMember ? (
              <div className="space-y-3">
                <Status label="Role" value={selectedMember.role} />
                <Status label="Runtime" value={selectedMember.runtime_mode} />
                <Status label="Skills" value={selectedMember.skills.length} />
                <p className="text-sm text-muted-foreground">{selectedMember.summary}</p>
                <div className="flex flex-wrap gap-2">
                  {selectedMember.skills.map((skill) => (
                    <Badge key={skill} variant="secondary">{skill}</Badge>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No member selected.</p>
            )}
          </section>

          <section className="rounded-md border bg-background p-4">
            <div className="mb-3 flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold">Threads</h3>
            </div>
            <div className="space-y-3">
              <Status label="Thread" value={activeThreadId} />
              <Status label="Provider" value={providerThreadId ?? "-"} />
              {threadsLoading ? (
                <p className="text-sm text-muted-foreground">Loading threads...</p>
              ) : threads.length === 0 ? (
                <p className="text-sm text-muted-foreground">No threads.</p>
              ) : (
                <div className="space-y-2">
                  {threads.map((thread) => {
                    const isActive = thread.id === activeThreadId;
                    const updated = new Date(thread.last_message_at ?? thread.updated_at);
                    const updatedLabel = Number.isNaN(updated.getTime())
                      ? ""
                      : updated.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
                    return (
                      <button
                        key={thread.id}
                        type="button"
                        onClick={() => void switchThread(thread)}
                        className={cn(
                          "w-full rounded-md border px-3 py-2 text-left text-sm transition-colors",
                          isActive ? "border-primary bg-primary/10" : "hover:bg-muted",
                        )}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <span className="line-clamp-2 font-medium">{thread.title}</span>
                          {isActive && <Badge variant="secondary">Active</Badge>}
                        </div>
                        <div className="mt-1 flex items-center justify-between gap-2 text-xs text-muted-foreground">
                          <span>{thread.message_count} messages</span>
                          <span>{updatedLabel}</span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
              {Object.entries(savedPaths).map(([key, value]) => (
                <div key={key} className="min-w-0">
                  <div className="text-xs uppercase text-muted-foreground">{key}</div>
                  <div className="truncate text-sm font-medium" title={value}>{value}</div>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-md border bg-background p-4">
            <div className="mb-3 flex items-center gap-2">
              <Activity className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold">Trace</h3>
            </div>
            {traceEvents.length === 0 ? (
              <p className="text-sm text-muted-foreground">No trace events.</p>
            ) : (
              <ol className="space-y-3">
                {traceEvents.map((event, index) => (
                  <li key={`${event.event}-${index}`} className="rounded-md border px-3 py-2">
                    <div className="text-xs font-medium text-muted-foreground">{event.event}</div>
                    <div className="mt-1 text-sm">{event.detail}</div>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </aside>
      </div>
    </AiteamosAgUiRuntimeProvider>
  );
}
