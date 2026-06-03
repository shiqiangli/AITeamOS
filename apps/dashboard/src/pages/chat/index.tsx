import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { HttpAgent } from "@ag-ui/client";
import {
  AssistantRuntimeProvider,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useAuiState,
} from "@assistant-ui/react";
import { useAgUiRuntime } from "@assistant-ui/react-ag-ui";
import { Activity, Bot, FileText, GitBranch, KeyRound, RefreshCcw, Save, Send, User } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Select } from "../../components/ui/select";
import { ErrorState, LoadingState, Status } from "../../components/shared";
import {
  getChatRuntime,
  listChatMembers,
  updateChatRuntime,
  type ChatMemberSummary,
  type ChatMessageResponse,
  type ChatRuntimeSettings,
  type ChatTraceEvent,
} from "../../api/chat";
import { cn } from "@/lib/utils";

type RuntimeForm = {
  provider: string;
  deepseekModel: string;
  deepseekThinking: string;
  openaiModel: string;
  fallbackOnError: boolean;
  deepseekApiKey: string;
  openaiApiKey: string;
};

function runtimeToForm(runtime: ChatRuntimeSettings): RuntimeForm {
  return {
    provider: runtime.provider,
    deepseekModel: runtime.deepseek_model,
    deepseekThinking: runtime.deepseek_thinking,
    openaiModel: runtime.openai_model,
    fallbackOnError: runtime.fallback_on_error,
    deepseekApiKey: "",
    openaiApiKey: "",
  };
}

function hasMemberProfileMutation(events: ChatTraceEvent[]): boolean {
  return events.some((event) => (
    event.event === "tool.create_member.completed"
    || event.event === "tool.edit_member_profile.completed"
    || event.event === "tool.delete_member.completed"
    || event.event === "tool.assign_skill_to_member.completed"
    || event.event === "tool.delete_skill.completed"
  ));
}

function createThreadId(): string {
  const random = globalThis.crypto?.randomUUID?.() ?? Math.random().toString(16).slice(2);
  return `thread-${random}`;
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
  const runtime = useAgUiRuntime({
    agent,
    showThinking: false,
    onError,
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
  const [selectedMemberId, setSelectedMemberId] = useState("");
  const [jiraKey, setJiraKey] = useState("");
  const [threadId, setThreadId] = useState(createThreadId);
  const [providerThreadId, setProviderThreadId] = useState<string | null>(null);
  const [traceEvents, setTraceEvents] = useState<ChatTraceEvent[]>([]);
  const [savedPaths, setSavedPaths] = useState<Record<string, string>>({});
  const [runtime, setRuntime] = useState<ChatRuntimeSettings | null>(null);
  const [runtimeForm, setRuntimeForm] = useState<RuntimeForm>({
    provider: "stub",
    deepseekModel: "deepseek-v4-flash",
    deepseekThinking: "disabled",
    openaiModel: "gpt-5-nano",
    fallbackOnError: true,
    deepseekApiKey: "",
    openaiApiKey: "",
  });
  const [loading, setLoading] = useState(true);
  const [savingRuntime, setSavingRuntime] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedMember = useMemo(
    () => members.find((member) => member.id === selectedMemberId) ?? members[0] ?? null,
    [members, selectedMemberId],
  );

  const loadWorkbench = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [loaded, loadedRuntime] = await Promise.all([listChatMembers(), getChatRuntime()]);
      setMembers(loaded);
      setRuntime(loadedRuntime);
      setRuntimeForm(runtimeToForm(loadedRuntime));
      const preferred = loaded.find((member) => member.id === "clara") ?? loaded[0];
      setSelectedMemberId((current) => current || preferred?.id || "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load chat workbench");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadWorkbench();
  }, [loadWorkbench]);

  const handleAgentResponse = useCallback((response: ChatMessageResponse) => {
    setThreadId(response.thread_id);
    setProviderThreadId(response.provider_thread_id);
    setTraceEvents(response.trace_events);
    setSavedPaths(response.saved_paths);

    if (hasMemberProfileMutation(response.trace_events)) {
      void listChatMembers()
        .then(setMembers)
        .catch((err) => {
          setError(err instanceof Error ? err.message : "Failed to reload members");
        });
    }
  }, []);

  function resetThread() {
    setThreadId(createThreadId());
    setProviderThreadId(null);
    setTraceEvents([]);
    setSavedPaths({});
  }

  async function handleRuntimeSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (savingRuntime) return;

    setSavingRuntime(true);
    setError(null);
    try {
      const updated = await updateChatRuntime({
        provider: runtimeForm.provider,
        deepseek_model: runtimeForm.deepseekModel,
        deepseek_thinking: runtimeForm.deepseekThinking,
        openai_model: runtimeForm.openaiModel,
        fallback_on_error: runtimeForm.fallbackOnError,
        deepseek_api_key: runtimeForm.deepseekApiKey.trim() || undefined,
        openai_api_key: runtimeForm.openaiApiKey.trim() || undefined,
      });
      setRuntime(updated);
      setRuntimeForm(runtimeToForm(updated));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save runtime settings");
    } finally {
      setSavingRuntime(false);
    }
  }

  if (loading) return <LoadingState />;

  return (
    <AiteamosAgUiRuntimeProvider
      key={threadId}
      jiraKey={jiraKey}
      onError={(err) => setError(err.message)}
      selectedMemberId={selectedMember?.id ?? ""}
      threadId={threadId}
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
                onChange={(event) => setSelectedMemberId(event.target.value)}
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
            <Button type="button" variant="outline" size="icon" onClick={resetThread} title="New thread">
              <RefreshCcw className="h-4 w-4" />
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
            <div className="mb-3 flex items-center gap-2">
              <KeyRound className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold">Runtime</h3>
            </div>
            <form onSubmit={handleRuntimeSubmit} className="space-y-3">
              <label className="block space-y-1">
                <span className="text-xs uppercase text-muted-foreground">Provider</span>
                <Select
                  aria-label="Runtime provider"
                  value={runtimeForm.provider}
                  onChange={(event) => setRuntimeForm((current) => ({ ...current, provider: event.target.value }))}
                >
                  <option value="stub">File stub</option>
                  <option value="deepseek">DeepSeek</option>
                  <option value="openai">OpenAI</option>
                </Select>
              </label>

              {runtimeForm.provider === "deepseek" && (
                <>
                  <label className="block space-y-1">
                    <span className="text-xs uppercase text-muted-foreground">DeepSeek model</span>
                    <input
                      aria-label="DeepSeek model"
                      value={runtimeForm.deepseekModel}
                      onChange={(event) => setRuntimeForm((current) => ({ ...current, deepseekModel: event.target.value }))}
                      className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  </label>
                  <label className="block space-y-1">
                    <span className="text-xs uppercase text-muted-foreground">Thinking</span>
                    <Select
                      aria-label="DeepSeek thinking"
                      value={runtimeForm.deepseekThinking}
                      onChange={(event) => setRuntimeForm((current) => ({ ...current, deepseekThinking: event.target.value }))}
                    >
                      <option value="disabled">Disabled</option>
                      <option value="enabled">Enabled</option>
                    </Select>
                  </label>
                  <label className="block space-y-1">
                    <span className="text-xs uppercase text-muted-foreground">DeepSeek API key</span>
                    <input
                      aria-label="DeepSeek API key"
                      type="password"
                      value={runtimeForm.deepseekApiKey}
                      onChange={(event) => setRuntimeForm((current) => ({ ...current, deepseekApiKey: event.target.value }))}
                      placeholder={runtime?.api_keys_configured.deepseek ? "Configured" : "Not configured"}
                      className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  </label>
                </>
              )}

              {runtimeForm.provider === "openai" && (
                <>
                  <label className="block space-y-1">
                    <span className="text-xs uppercase text-muted-foreground">OpenAI model</span>
                    <input
                      aria-label="OpenAI model"
                      value={runtimeForm.openaiModel}
                      onChange={(event) => setRuntimeForm((current) => ({ ...current, openaiModel: event.target.value }))}
                      className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  </label>
                  <label className="block space-y-1">
                    <span className="text-xs uppercase text-muted-foreground">OpenAI API key</span>
                    <input
                      aria-label="OpenAI API key"
                      type="password"
                      value={runtimeForm.openaiApiKey}
                      onChange={(event) => setRuntimeForm((current) => ({ ...current, openaiApiKey: event.target.value }))}
                      placeholder={runtime?.api_keys_configured.openai ? "Configured" : "Not configured"}
                      className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  </label>
                </>
              )}

              <label className="flex items-center justify-between gap-3 text-sm">
                <span>Fallback</span>
                <input
                  aria-label="Fallback on error"
                  type="checkbox"
                  checked={runtimeForm.fallbackOnError}
                  onChange={(event) => setRuntimeForm((current) => ({ ...current, fallbackOnError: event.target.checked }))}
                  className="h-4 w-4"
                />
              </label>

              <Button type="submit" className="w-full" disabled={savingRuntime}>
                <Save className="h-4 w-4" />
                {savingRuntime ? "Saving" : "Save runtime"}
              </Button>
            </form>
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
              <FileText className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold">Thread</h3>
            </div>
            <div className="space-y-3">
              <Status label="Thread" value={threadId} />
              <Status label="Provider" value={providerThreadId ?? "-"} />
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
