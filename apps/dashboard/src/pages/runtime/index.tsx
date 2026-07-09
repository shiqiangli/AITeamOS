import { useEffect, useMemo, useState } from "react";
import { Activity, Database, RefreshCw } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { EmptyState, ErrorState, LoadingState, Status, navigateTo } from "../../components/shared";
import { RuntimeSessionReplayDetail } from "../../components/runtimeReplay";
import {
  getRuntimeExecutionSessionReplay,
  listRuntimeExecutors,
  listRuntimeExecutionSessions,
  type RuntimeExecutionReplayResponse,
  type RuntimeExecutionSessionRecord,
  type RuntimeExecutorRegistryResponse,
} from "../../api/runtimeExecutors";
import { cn } from "@/lib/utils";

function statusVariant(status: string): "default" | "secondary" | "warning" | "success" | "danger" | "outline" {
  const normalized = status.trim().toLowerCase();
  if (["completed", "ready", "running"].includes(normalized)) return "success";
  if (["needs_approval", "paused", "queued"].includes(normalized)) return "warning";
  if (["failed", "blocked", "cancelled"].includes(normalized)) return "danger";
  return "secondary";
}

function shortRef(value?: string | null, fallback = "-"): string {
  const text = String(value ?? "").trim();
  if (!text) return fallback;
  return text.length > 44 ? `${text.slice(0, 20)}...${text.slice(-18)}` : text;
}

function sessionTitle(session: RuntimeExecutionSessionRecord): string {
  return session.last_request_id || session.session_key;
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function recordArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(recordValue).filter((item) => Object.keys(item).length > 0) : [];
}

function textValue(value: unknown, fallback = ""): string {
  if (value === null || value === undefined || value === "") return fallback;
  return typeof value === "string" ? value : String(value);
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => textValue(item)).filter(Boolean) : [];
}

function RuntimeReadinessPanel({ registry }: { registry: RuntimeExecutorRegistryResponse | null }) {
  const readiness = recordValue(registry?.live_provider_readiness);
  const summary = recordValue(readiness.summary);
  const mutationGate = recordValue(readiness.mutation_gate);
  const providerPrerequisites = recordValue(readiness.provider_prerequisites);
  const blockers = recordArray(readiness.blockers);
  const candidates = recordArray(readiness.repo_write_candidates);
  const readyCandidateCount = Number(summary.repo_write_ready_count ?? candidates.filter((item) => item.ready === true).length);
  const candidateCount = Number(summary.repo_write_candidate_count ?? candidates.length);
  const status = textValue(readiness.status, "unknown");

  return (
    <section className="rounded-md border bg-background p-4">
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-semibold">Runtime Provider Readiness</div>
          <p className="mt-1 text-sm text-muted-foreground">Live mutation readiness stays behind RuntimeExecutor capability, Ticket, Graphiti, and approval boundaries.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant={statusVariant(status)}>{status.replace(/_/g, " ")}</Badge>
          <Badge variant={readyCandidateCount > 0 ? "success" : "warning"}>{readyCandidateCount}/{candidateCount || "?"} repo-write ready</Badge>
          <Badge variant={mutationGate.open ? "success" : "warning"}>{mutationGate.open ? "gate open" : "gate closed"}</Badge>
        </div>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="rounded-md border bg-card px-3 py-2">
          <div className="mb-2 text-[10px] font-medium uppercase text-muted-foreground">Blockers</div>
          {blockers.length === 0 ? (
            <div className="text-sm text-muted-foreground">No live provider readiness blockers reported.</div>
          ) : (
            <div className="grid gap-2">
              {blockers.slice(0, 4).map((blocker, index) => {
                const reason = textValue(blocker.reason, `blocker-${index + 1}`);
                const setupRequired = stringArray(blocker.setup_required);
                return (
                  <div key={`${reason}-${index}`} className="rounded-md border bg-background px-3 py-2">
                    <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium" title={reason}>{reason.replace(/_/g, " ")}</span>
                      <Badge variant={statusVariant(textValue(blocker.status, "blocked"))}>{textValue(blocker.status, "blocked").replace(/_/g, " ")}</Badge>
                    </div>
                    {textValue(blocker.scope) ? <div className="mt-1 text-xs text-muted-foreground">{textValue(blocker.scope).replace(/_/g, " ")}</div> : null}
                    {setupRequired.length ? (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {setupRequired.slice(0, 4).map((item) => <Badge key={`${reason}-${item}`} variant="outline">{item}</Badge>)}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="rounded-md border bg-card px-3 py-2">
          <div className="mb-2 text-[10px] font-medium uppercase text-muted-foreground">Provider Evidence</div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline">selected {textValue(readiness.selected_executor_id, "-")}</Badge>
            <Badge variant={statusVariant(textValue(providerPrerequisites.ticket_backend_status, "unknown"))}>
              Ticket {textValue(providerPrerequisites.ticket_backend_status, "unknown").replace(/_/g, " ")}
            </Badge>
            <Badge variant={statusVariant(textValue(providerPrerequisites.memory_backend_status, "unknown"))}>
              Memory {textValue(providerPrerequisites.memory_backend_status, "unknown").replace(/_/g, " ")}
            </Badge>
            <Badge variant="secondary">smoke {textValue(providerPrerequisites.provider_smoke_status, "unknown").replace(/_/g, " ")}</Badge>
          </div>
          <div className="mt-3 grid gap-2">
            {candidates.length === 0 ? (
              <div className="text-sm text-muted-foreground">No repo-write RuntimeExecutor candidates reported.</div>
            ) : candidates.slice(0, 4).map((candidate, index) => {
              const executorId = textValue(candidate.executor_id, `candidate-${index + 1}`);
              const displayName = textValue(candidate.display_name, executorId.replace(/_/g, " "));
              const setupRequired = stringArray(candidate.setup_required);
              return (
                <div key={`${executorId}-${index}`} className="rounded-md border bg-background px-3 py-2">
                  <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
                    <span className="truncate text-sm font-medium" title={displayName}>{displayName}</span>
                    <Badge variant={candidate.ready === true ? "success" : "warning"}>{textValue(candidate.status, "unknown").replace(/_/g, " ")}</Badge>
                  </div>
                  {setupRequired.length ? (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {setupRequired.slice(0, 4).map((item) => <Badge key={`${executorId}-${item}`} variant="outline">{item}</Badge>)}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}

export function RuntimePage({ selectedSessionKey }: { selectedSessionKey?: string | null }) {
  const [sessions, setSessions] = useState<RuntimeExecutionSessionRecord[]>([]);
  const [registry, setRegistry] = useState<RuntimeExecutorRegistryResponse | null>(null);
  const [selectedKey, setSelectedKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [replay, setReplay] = useState<RuntimeExecutionReplayResponse | null>(null);
  const [replayLoading, setReplayLoading] = useState(false);
  const [replayError, setReplayError] = useState("");
  const routeKey = selectedSessionKey && selectedSessionKey !== "sessions" ? selectedSessionKey : "";

  async function loadSessions() {
    setLoading(true);
    setError("");
    try {
      const [loaded, loadedRegistry] = await Promise.all([
        listRuntimeExecutionSessions(),
        listRuntimeExecutors(),
      ]);
      setSessions(loaded);
      setRegistry(loadedRegistry);
      const nextKey = routeKey || selectedKey || loaded[0]?.session_key || "";
      setSelectedKey(nextKey);
      if (nextKey) await loadReplay(nextKey, false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load runtime sessions");
    } finally {
      setLoading(false);
    }
  }

  async function loadReplay(sessionKey: string, updateRoute = true) {
    if (!sessionKey) return;
    setSelectedKey(sessionKey);
    if (updateRoute) navigateTo("runtime", sessionKey);
    setReplayLoading(true);
    setReplayError("");
    try {
      setReplay(await getRuntimeExecutionSessionReplay(sessionKey));
    } catch (err) {
      setReplay(null);
      setReplayError(err instanceof Error ? err.message : "Failed to load execution replay");
    } finally {
      setReplayLoading(false);
    }
  }

  useEffect(() => {
    void loadSessions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeKey]);

  const selectedSession = useMemo(
    () => sessions.find((session) => session.session_key === selectedKey) ?? sessions[0] ?? null,
    [selectedKey, sessions],
  );
  const needsAttention = sessions.filter((session) => ["needs_approval", "blocked", "failed", "paused"].includes(session.status)).length;

  if (loading) return <LoadingState message="Loading runtime sessions." />;
  if (error) return <ErrorState message={error} onRetry={() => void loadSessions()} />;

  return (
    <div className="space-y-4">
      <section className="rounded-md border bg-background p-4">
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-muted-foreground" />
              <h2 className="text-lg font-semibold">Runtime Replay</h2>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">Execution sessions, approvals, tool events, artifacts, evidence, and state snapshots.</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => void loadSessions()}>
            <RefreshCw className="h-4 w-4" />Refresh
          </Button>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <Status label="Sessions" value={sessions.length} />
          <Status label="Needs attention" value={needsAttention} tone={needsAttention ? "warn" : "ok"} />
          <Status label="Selected" value={selectedSession?.executor_id || "-"} />
        </div>
      </section>

      <RuntimeReadinessPanel registry={registry} />

      <div className="grid min-h-[32rem] gap-4 xl:grid-cols-[minmax(22rem,0.85fr)_minmax(30rem,1.15fr)]">
        <section className="min-h-0 rounded-md border bg-background">
          <div className="flex items-center justify-between border-b px-4 py-3">
            <div className="flex items-center gap-2">
              <Database className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold">Execution Sessions</h3>
            </div>
            <Badge variant="secondary">{sessions.length}</Badge>
          </div>
          {sessions.length === 0 ? (
            <EmptyState title="No execution sessions" description="Runtime sessions will appear after a governed Employee run is dispatched." />
          ) : (
            <div className="max-h-[calc(100vh-18rem)] divide-y overflow-y-auto">
              {sessions.map((session) => {
                const selected = session.session_key === selectedKey;
                return (
                  <button
                    key={session.session_key}
                    type="button"
                    onClick={() => void loadReplay(session.session_key)}
                    className={cn("grid w-full gap-2 px-4 py-3 text-left text-sm transition-colors hover:bg-muted/60", selected ? "bg-primary/10" : "")}
                  >
                    <div className="flex min-w-0 items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="truncate font-medium" title={sessionTitle(session)}>{sessionTitle(session)}</div>
                        <div className="mt-0.5 truncate text-xs text-muted-foreground" title={session.session_key}>{session.session_key}</div>
                      </div>
                      <Badge variant={statusVariant(session.status)}>{session.status || "unknown"}</Badge>
                    </div>
                    <div className="grid gap-1 text-xs text-muted-foreground">
                      <span className="truncate" title={session.ticket_id}>Ticket: {session.ticket_id || "-"}</span>
                      <span className="truncate" title={session.checkpoint_ref}>Checkpoint: {shortRef(session.checkpoint_ref)}</span>
                      <span className="truncate" title={session.trace_ref}>Trace: {shortRef(session.trace_ref)}</span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      <Badge variant="outline">{session.tool_event_count} tool events</Badge>
                      <Badge variant="secondary">{session.employee_id || "employee"}</Badge>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </section>

        <section className="min-h-0 rounded-md border bg-background p-4">
          <RuntimeSessionReplayDetail error={replayError} loading={replayLoading} replay={replay} />
          {!replay && !replayLoading && !replayError && (
            <EmptyState title="No replay selected" description="Select an execution session to inspect its timeline, artifacts, evidence, approvals, and state snapshots." />
          )}
        </section>
      </div>
    </div>
  );
}
