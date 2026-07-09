import { Badge } from "./ui/badge";
import { Status, navigateTo } from "./shared";
import type { RuntimeExecutionReplayResponse } from "../api/runtimeExecutors";

function shortRef(value?: string | null, fallback = "-"): string {
  const text = String(value ?? "").trim();
  if (!text) return fallback;
  return text.length > 44 ? `${text.slice(0, 20)}...${text.slice(-18)}` : text;
}

function runtimeRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function runtimeArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function runtimeText(value: unknown, fallback = "-"): string {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return fallback;
  }
}

function runtimeStringList(value: unknown): string[] {
  return runtimeArray(value).map((item) => runtimeText(item, "")).filter(Boolean);
}

function runtimeRefsLabel(value: unknown): string {
  const refs = runtimeArray(value).map((item) => {
    if (typeof item === "string") return item;
    const record = runtimeRecord(item);
    return [record.kind, record.ref].map((part) => runtimeText(part, "")).filter(Boolean).join(":");
  }).filter(Boolean);
  return refs.length > 0 ? refs.slice(0, 4).join(", ") : "-";
}

function runtimeRefRecord(item: unknown): { kind: string; ref: string } | null {
  if (typeof item === "string") return { kind: "ref", ref: item };
  const record = runtimeRecord(item);
  const kind = runtimeText(record.kind || record.source_kind || record.target_kind, "").trim().toLowerCase();
  const ref = runtimeText(record.ref || record.source_ref || record.target_ref || record.id, "").trim();
  return ref ? { kind, ref } : null;
}

function navigateRuntimeRef(kind: string, ref: string): void {
  const normalizedKind = kind.trim().toLowerCase();
  const normalizedRef = ref.trim();
  if (!normalizedRef) return;
  if (normalizedKind.includes("approval")) navigateTo("assets", "review", `approval:${normalizedRef}`);
  else if (normalizedKind.includes("ticket")) navigateTo("tickets", normalizedRef);
  else if (normalizedKind.includes("employee")) navigateTo("employees", normalizedRef);
  else if (normalizedKind.includes("memory")) navigateTo("assets", "knowledge", `memory:${normalizedRef}`);
  else if (normalizedKind.includes("asset") || normalizedKind.includes("artifact") || normalizedKind.includes("evidence")) navigateTo("assets", "asset", normalizedRef);
}

function hasRuntimeRefRoute(kind: string, ref: string): boolean {
  const normalizedKind = kind.trim().toLowerCase();
  return Boolean(
      ref.trim()
      && (
      normalizedKind.includes("approval")
      || normalizedKind.includes("ticket")
      || normalizedKind.includes("employee")
      || normalizedKind.includes("memory")
      || normalizedKind.includes("asset")
      || normalizedKind.includes("artifact")
      || normalizedKind.includes("evidence")
    )
  );
}

function RuntimeRefButton({ kind, ref }: { kind: string; ref: string }) {
  if (!hasRuntimeRefRoute(kind, ref)) {
    return <Badge variant="outline">{kind || "ref"}:{shortRef(ref)}</Badge>;
  }
  return (
    <button
      type="button"
      onClick={() => navigateRuntimeRef(kind, ref)}
      className="inline-flex max-w-full items-center rounded-full border bg-background px-2 py-0.5 text-[10px] font-medium text-muted-foreground transition-colors hover:border-primary hover:text-foreground"
      aria-label={`Open ${kind || "ref"} ${ref}`}
      title={`${kind || "ref"}:${ref}`}
    >
      <span className="truncate">{kind || "ref"}:{shortRef(ref)}</span>
    </button>
  );
}

function RuntimeRefs({ refs }: { refs: unknown }) {
  const records = runtimeArray(refs).map(runtimeRefRecord).filter((item): item is { kind: string; ref: string } => Boolean(item));
  if (records.length === 0) return <span>Refs: -</span>;
  return (
    <div className="flex min-w-0 flex-wrap gap-1">
      <span className="text-muted-foreground">Refs:</span>
      {records.slice(0, 4).map((item, index) => (
        <RuntimeRefButton key={`${item.kind}-${item.ref}-${index}`} kind={item.kind} ref={item.ref} />
      ))}
    </div>
  );
}

function sessionRefItems(session: Record<string, unknown>): Array<{ kind: string; ref: string }> {
  const refs: Array<{ kind: string; ref: string }> = [];
  const employeeId = runtimeText(session.employee_id, "").trim();
  const ticketId = runtimeText(session.ticket_id, "").trim();
  if (employeeId) refs.push({ kind: "employee", ref: employeeId });
  if (ticketId) refs.push({ kind: "ticket", ref: ticketId });
  for (const ref of runtimeArray(session.ticket_refs)) {
    const text = runtimeText(ref, "").trim();
    if (text) refs.push({ kind: "ticket", ref: text });
  }
  for (const ref of runtimeArray(session.memory_refs)) {
    const text = runtimeText(ref, "").trim();
    if (text) refs.push({ kind: "memory", ref: text });
  }
  for (const ref of runtimeArray(session.approval_refs)) {
    const text = runtimeText(ref, "").trim();
    if (text) refs.push({ kind: "approval", ref: text });
  }
  const seen = new Set<string>();
  return refs.filter((item) => {
    const key = `${item.kind}:${item.ref}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function EmptyReplayDetail({ children }: { children: string }) {
  return (
    <div className="rounded-md border bg-muted/30 p-4 text-sm text-muted-foreground">
      {children}
    </div>
  );
}

function approvalStatusVariant(status: string): "success" | "warning" | "danger" | "secondary" | "outline" {
  const normalized = status.trim().toLowerCase();
  if (["approved", "completed", "already_approved"].includes(normalized)) return "success";
  if (["requested", "needs_approval", "changes_requested", "evidence_requested", "pending"].includes(normalized)) return "warning";
  if (["rejected", "failed", "blocked", "cancelled"].includes(normalized)) return "danger";
  return normalized ? "secondary" : "outline";
}

function RuntimeApprovalsSection({ approvals }: { approvals: unknown[] }) {
  const records = approvals.map(runtimeRecord).filter((item) => Object.keys(item).length > 0);
  return (
    <div className="rounded-md border bg-background px-3 py-2">
      <div className="mb-2 flex min-w-0 items-center justify-between gap-2">
        <div className="text-[10px] font-medium uppercase text-muted-foreground">Runtime Approvals</div>
        <Badge variant="outline">{records.length}</Badge>
      </div>
      {records.length === 0 ? (
        <div className="text-sm text-muted-foreground">No runtime approval records captured for this replay.</div>
      ) : (
        <div className="grid gap-2">
          {records.slice(0, 4).map((approval, index) => {
            const approvalId = runtimeText(approval.id || approval.approval_id || approval.approval_ref, `approval-${index + 1}`);
            const status = runtimeText(approval.status, "unknown");
            const ticketId = runtimeText(approval.ticket_id, "");
            const employeeId = runtimeText(approval.employee_id, "");
            const checkpointRef = runtimeText(approval.checkpoint_ref, "");
            const stateRef = runtimeText(approval.source_state_ref, "");
            const lastRun = runtimeText(approval.last_run_request_id, "");
            const lastRunStatus = runtimeText(approval.last_run_status, "");
            const ingestionBlocker = runtimeText(approval.last_ingestion_blocker, "");
            return (
              <div key={`${approvalId}-${index}`} className="grid gap-2 rounded-md border px-2 py-1.5 text-xs">
                <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
                  <RuntimeRefButton kind="approval" ref={approvalId} />
                  <Badge variant={approvalStatusVariant(status)}>{status.replace(/_/g, " ")}</Badge>
                </div>
                <div className="flex min-w-0 flex-wrap gap-1.5">
                  {ticketId ? <RuntimeRefButton kind="ticket" ref={ticketId} /> : null}
                  {employeeId ? <RuntimeRefButton kind="employee" ref={employeeId} /> : null}
                  {runtimeText(approval.executor_id, "") ? (
                    <Badge variant="outline">{runtimeText(approval.executor_id, "")}</Badge>
                  ) : null}
                  {runtimeText(approval.required_capability, "") ? (
                    <Badge variant="secondary">{runtimeText(approval.required_capability, "")}</Badge>
                  ) : null}
                </div>
                {runtimeText(approval.reason, "") ? (
                  <div className="line-clamp-2 text-muted-foreground" title={runtimeText(approval.reason, "")}>
                    {runtimeText(approval.reason, "")}
                  </div>
                ) : null}
                <div className="grid gap-1 text-muted-foreground">
                  {checkpointRef ? (
                    <div className="line-clamp-1" title={checkpointRef}>Checkpoint: {shortRef(checkpointRef)}</div>
                  ) : null}
                  {stateRef ? (
                    <div className="line-clamp-1" title={stateRef}>State: {shortRef(stateRef)}</div>
                  ) : null}
                  {lastRun ? (
                    <div className="line-clamp-1" title={`${lastRun} ${lastRunStatus}`}>
                      Last run: {lastRun}{lastRunStatus ? ` (${lastRunStatus})` : ""}
                    </div>
                  ) : null}
                </div>
                {ingestionBlocker ? (
                  <div className="rounded border border-warning/40 bg-warning/10 px-2 py-1 text-[10px] text-warning-foreground">
                    Ingestion blocker: {ingestionBlocker}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function RuntimeSessionReplayDetail({
  error,
  loading,
  replay,
}: {
  error: string;
  loading: boolean;
  replay: RuntimeExecutionReplayResponse | null;
}) {
  if (loading) {
    return <EmptyReplayDetail>Loading replay.</EmptyReplayDetail>;
  }
  if (error) {
    return <EmptyReplayDetail>{error}</EmptyReplayDetail>;
  }
  if (!replay) return null;

  const session = runtimeRecord(replay.session);
  const executionArtifacts = runtimeRecord(replay.execution_artifacts);
  const artifacts = runtimeArray(executionArtifacts.artifacts);
  const evidence = runtimeArray(executionArtifacts.evidence);
  const timeline = runtimeArray(replay.timeline).map(runtimeRecord);
  const traceEvents = runtimeArray(replay.trace_events);
  const coverageSummary = runtimeRecord(replay.coverage_summary);
  const coverage = runtimeRecord(coverageSummary.coverage);
  const coverageCounts = runtimeRecord(coverageSummary.counts);
  const coverageGaps = runtimeArray(coverageSummary.gaps).map((item) => runtimeText(item, "")).filter(Boolean);
  const approvals = runtimeArray(replay.approvals);
  const stateSnapshots = runtimeArray(replay.state_snapshots);
  const nativeCheckpoints = runtimeArray(replay.native_checkpoint_history).map(runtimeRecord);
  const stateTransitions = runtimeArray(replay.state_transitions).map(runtimeRecord);
  const handoffSummary = runtimeRecord(replay.handoff_summary);
  const handoffPolicy = runtimeRecord(handoffSummary.policy);
  const handoffStatus = runtimeText(handoffSummary.status, "");
  const showHandoffSummary = Boolean(handoffStatus && handoffStatus !== "not_applicable");
  const requiredMemoryScopes = runtimeStringList(handoffSummary.required_memory_scopes);
  const matchedMemoryScopes = runtimeStringList(handoffSummary.matched_memory_scopes);
  const availableMemoryScopes = runtimeStringList(handoffSummary.available_memory_scopes);
  const payloadPreview = JSON.stringify(
    {
      artifacts,
      evidence,
      approvals,
      state_snapshots: stateSnapshots,
      native_checkpoint_history: nativeCheckpoints,
      state_transitions: stateTransitions,
      handoff_summary: handoffSummary,
      trace_events: traceEvents.slice(0, 5),
    },
    null,
    2,
  );

  return (
    <div className="space-y-3 rounded-md border bg-muted/30 p-3">
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm font-semibold">Replay Detail</div>
          <div className="mt-1 truncate text-xs text-muted-foreground" title={runtimeText(session.session_key)}>
            {runtimeText(session.session_key)}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline">{timeline.length} events</Badge>
          <Badge variant="secondary">{artifacts.length} artifacts</Badge>
          <Badge variant="secondary">{evidence.length} evidence</Badge>
          <Badge variant="secondary">{stateSnapshots.length} state snapshots</Badge>
          <Badge variant="secondary">{nativeCheckpoints.length} native checkpoints</Badge>
          <Badge variant="secondary">{stateTransitions.length} state transitions</Badge>
        </div>
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        <Status label="Checkpoint" value={shortRef(runtimeText(session.checkpoint_ref, ""))} />
        <Status label="Graph node" value={runtimeText(session.current_graph_node)} />
        <Status label="Trace" value={shortRef(runtimeText(session.trace_ref, ""))} />
        <Status label="Approvals" value={runtimeArray(session.approval_refs).length} />
      </div>

      {Object.keys(coverageSummary).length > 0 && (
        <div className="rounded-md border bg-background px-3 py-2">
          <div className="mb-2 flex min-w-0 items-center justify-between gap-2">
            <div className="text-[10px] font-medium uppercase text-muted-foreground">Replay Coverage</div>
            <Badge variant={coverageSummary.required_chain_complete ? "success" : "warning"}>
              {coverageSummary.required_chain_complete ? "complete" : "gaps"}
            </Badge>
          </div>
          <div className="grid gap-2 sm:grid-cols-4">
            <Status label="Ticket" value={coverage.ticket ? "yes" : "missing"} tone={coverage.ticket ? "ok" : "warn"} />
            <Status label="Runtime" value={coverage.runtime ? "yes" : "missing"} tone={coverage.runtime ? "ok" : "warn"} />
            <Status label="Evidence" value={coverage.evidence ? "yes" : "missing"} tone={coverage.evidence ? "ok" : "warn"} />
            <Status label="Trace" value={coverage.trace ? "yes" : "missing"} tone={coverage.trace ? "ok" : "warn"} />
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Badge variant="outline">{runtimeText(coverageCounts.timeline_event_count, "0")} events</Badge>
            <Badge variant="outline">{runtimeText(coverageCounts.state_transition_count, "0")} transitions</Badge>
            <Badge variant="outline">{runtimeText(coverageCounts.trace_event_count, "0")} trace</Badge>
            <Badge variant={coverage.asset_or_memory ? "secondary" : "outline"}>
              Assets/Memory: {coverage.asset_or_memory ? "yes" : "none"}
            </Badge>
          </div>
          {coverageGaps.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {coverageGaps.slice(0, 6).map((gap) => <Badge key={gap} variant="warning">{gap}</Badge>)}
            </div>
          )}
        </div>
      )}

      {showHandoffSummary && (
        <div className="rounded-md border bg-background px-3 py-2">
          <div className="mb-2 flex min-w-0 flex-wrap items-center justify-between gap-2">
            <div className="text-[10px] font-medium uppercase text-muted-foreground">Handoff Policy</div>
            <div className="flex flex-wrap gap-1.5">
              <Badge variant="outline">{handoffStatus.replace(/_/g, " ")}</Badge>
              <Badge variant={handoffSummary.risk_allowed ? "success" : "warning"}>
                risk {runtimeText(handoffSummary.risk_level, "unknown")}
              </Badge>
            </div>
          </div>
          <div className="grid gap-2 sm:grid-cols-4">
            <Status label="From" value={runtimeText(handoffSummary.source_employee_id)} />
            <Status label="Target" value={runtimeText(handoffSummary.target_employee_id)} />
            <Status label="Scope match" value={runtimeText(handoffSummary.memory_scope_match, "unknown")} />
            <Status label="Risk boundary" value={runtimeText(handoffSummary.max_risk_level, "unknown")} />
          </div>
          <div className="mt-2 grid gap-2 text-xs text-muted-foreground">
            <div className="flex min-w-0 flex-wrap gap-1.5">
              <span className="text-muted-foreground">Matched scopes:</span>
              {matchedMemoryScopes.length ? matchedMemoryScopes.slice(0, 6).map((scope) => (
                <Badge key={`matched-${scope}`} variant="secondary">{scope}</Badge>
              )) : <Badge variant="outline">none</Badge>}
            </div>
            <div className="flex min-w-0 flex-wrap gap-1.5">
              <span className="text-muted-foreground">Required scopes:</span>
              {requiredMemoryScopes.length ? requiredMemoryScopes.slice(0, 6).map((scope) => (
                <Badge key={`required-${scope}`} variant="outline">{scope}</Badge>
              )) : <Badge variant="outline">none</Badge>}
            </div>
            {availableMemoryScopes.length ? (
              <div className="line-clamp-1" title={availableMemoryScopes.join(", ")}>
                Available: {availableMemoryScopes.join(", ")}
              </div>
            ) : null}
            {runtimeText(handoffSummary.reason, "") ? (
              <div className="line-clamp-2" title={runtimeText(handoffSummary.reason)}>
                {runtimeText(handoffSummary.reason)}
              </div>
            ) : null}
            {Object.keys(handoffPolicy).length > 0 ? (
              <div className="line-clamp-1" title={runtimeText(handoffPolicy)}>
                Policy: {runtimeText(handoffPolicy)}
              </div>
            ) : null}
            <RuntimeRefs refs={handoffSummary.refs} />
          </div>
        </div>
      )}

      <div className="rounded-md border bg-background px-3 py-2">
        <div className="mb-1 text-[10px] font-medium uppercase text-muted-foreground">Session Refs</div>
        <div className="flex flex-wrap gap-1.5">
          {sessionRefItems(session).length > 0 ? sessionRefItems(session).map((item) => (
            <RuntimeRefButton key={`${item.kind}-${item.ref}`} kind={item.kind} ref={item.ref} />
          )) : (
            <Badge variant="outline">none</Badge>
          )}
        </div>
      </div>

      <RuntimeApprovalsSection approvals={approvals} />

      <div className="rounded-md border bg-background px-3 py-2">
        <div className="mb-2 flex min-w-0 items-center justify-between gap-2">
          <div className="text-[10px] font-medium uppercase text-muted-foreground">Native Checkpoints</div>
          <Badge variant="outline">{nativeCheckpoints.length}</Badge>
        </div>
        {nativeCheckpoints.length === 0 ? (
          <div className="text-sm text-muted-foreground">No LangGraph checkpoint history recorded.</div>
        ) : (
          <div className="grid gap-2">
            {nativeCheckpoints.slice(0, 4).map((checkpoint, index) => {
              const summary = runtimeRecord(checkpoint.state_summary);
              const delta = runtimeRecord(checkpoint.state_delta);
              return (
                <div key={`${runtimeText(checkpoint.checkpoint_id)}-${index}`} className="grid gap-1 rounded-md border px-2 py-1.5 text-xs">
                  <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
                    <span className="truncate font-medium" title={runtimeText(checkpoint.checkpoint_id)}>
                      {shortRef(runtimeText(checkpoint.checkpoint_id, `checkpoint-${index + 1}`))}
                    </span>
                    <Badge variant="outline">step {runtimeText(runtimeRecord(checkpoint.metadata).step)}</Badge>
                  </div>
                  <div className="line-clamp-1 text-muted-foreground" title={`${runtimeText(delta.from)} -> ${runtimeText(delta.to)}`}>
                    {runtimeText(delta.from)} -&gt; {runtimeText(delta.to)}
                  </div>
                  <div className="line-clamp-1 text-muted-foreground" title={runtimeRefsLabel(delta.changed_keys)}>
                    Changed: {runtimeRefsLabel(delta.changed_keys)}
                  </div>
                  <div className="line-clamp-1 text-muted-foreground" title={runtimeRefsLabel(checkpoint.next)}>
                    Next: {runtimeRefsLabel(checkpoint.next)}
                  </div>
                  <div className="line-clamp-1 text-muted-foreground" title={runtimeText(summary.current_step)}>
                    Current: {runtimeText(summary.current_step)}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="rounded-md border bg-background px-3 py-2">
        <div className="mb-2 flex min-w-0 items-center justify-between gap-2">
          <div className="text-[10px] font-medium uppercase text-muted-foreground">State Transitions</div>
          <Badge variant="outline">{stateTransitions.length}</Badge>
        </div>
        {stateTransitions.length === 0 ? (
          <div className="text-sm text-muted-foreground">No state transitions recorded.</div>
        ) : (
          <div className="grid gap-2">
            {stateTransitions.slice(0, 4).map((transition, index) => (
              <div key={`${runtimeText(transition.source_kind)}-${index}`} className="grid gap-1 rounded-md border px-2 py-1.5 text-xs">
                <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
                  <span className="truncate font-medium" title={`${runtimeText(transition.from)} -> ${runtimeText(transition.to)}`}>
                    {runtimeText(transition.from)} -&gt; {runtimeText(transition.to)}
                  </span>
                  <Badge variant="outline">{runtimeText(transition.source_kind)}</Badge>
                </div>
                <div className="line-clamp-1 text-muted-foreground" title={runtimeRefsLabel(transition.changed_keys)}>
                  Changed: {runtimeRefsLabel(transition.changed_keys)}
                </div>
                <div className="min-w-0 text-muted-foreground">
                  <RuntimeRefs refs={[
                    { kind: "checkpoint", ref: runtimeText(transition.checkpoint_ref, "") },
                    { kind: "state", ref: runtimeText(transition.source_state_ref, "") },
                    { kind: "state_snapshot", ref: runtimeText(transition.source_state_snapshot_ref, "") },
                  ].filter((item) => item.ref)} />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="max-h-72 divide-y overflow-y-auto rounded-md border bg-background">
        {timeline.length === 0 ? (
          <div className="px-3 py-2 text-sm text-muted-foreground">No timeline events recorded.</div>
        ) : timeline.slice(0, 24).map((item, index) => (
          <div key={`${runtimeText(item.event)}-${index}`} className="grid gap-1 px-3 py-2 text-sm">
            <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
              <span className="truncate font-medium" title={runtimeText(item.event)}>{runtimeText(item.event)}</span>
              <Badge variant="outline">{runtimeText(item.kind)}</Badge>
            </div>
            <div className="line-clamp-2 text-xs text-muted-foreground">{runtimeText(item.title)}</div>
            <div className="min-w-0 text-xs" title={runtimeRefsLabel(item.refs)}>
              <RuntimeRefs refs={item.refs} />
            </div>
          </div>
        ))}
      </div>

      <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-md bg-background p-3 text-xs text-muted-foreground">
        {payloadPreview}
      </pre>
    </div>
  );
}
