import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RuntimePage } from "../pages/runtime";

const runtimeExecutionSessions = [
  {
    session_key: "alex::thread-runtime::rd-9999",
    employee_id: "alex",
    thread_id: "thread-runtime",
    ticket_id: "rd-9999",
    executor_id: "claude_code",
    executor_session_ref: "claude_code-exec-chat-runtime-mutation",
    checkpoint_ref: "claude_code:exec-chat-runtime-mutation",
    last_request_id: "exec-chat-runtime-mutation",
    status: "needs_approval",
    trace_ref: ".aiteamos/traces/exec-chat-runtime-mutation.jsonl",
    current_graph_node: "governance_gate",
    source_state_ref: "state://universal_employee_agent/exec-chat-runtime-mutation/governance_gate",
    tool_event_count: 2,
    tool_events: [
      { event: "runtime.load_request", tool_name: "runtime.load_request" },
      { event: "universal_agent.tool.completed", tool_name: "search_tickets" },
    ],
    ticket_refs: ["rd-9999"],
    memory_refs: ["mem-runtime"],
    context_refs: [{ source_kind: "aiteamos_service", source_ref: "list_tickets" }],
    approval_refs: ["approval-exec-chat-runtime-mutation-1"],
    updated_at: "2026-06-18T00:00:00Z",
  },
];

const runtimeExecutorRegistry = {
  executors: [
    {
      executor_id: "claude_code",
      display_name: "Claude Code",
      status: "setup_blocked",
      detail: "Claude Code-compatible Local CLI Executor is not configured.",
      capabilities: ["agent_loop", "repo:read", "repo:write"],
      setup_required: ["CLAUDE_CODE_BIN"],
      diagnostics: {},
      health: { status: "setup_blocked" },
    },
    {
      executor_id: "codex_cli",
      display_name: "OpenAI Codex CLI Executor",
      status: "ready",
      detail: "OpenAI Codex CLI Executor is configured.",
      capabilities: ["agent_loop", "repo:read", "repo:write"],
      setup_required: [],
      diagnostics: {},
      health: { status: "ready" },
    },
  ],
  summary: {
    executor_count: 2,
    ready_count: 1,
    blocked_count: 1,
    runtime_boundary: "RuntimeExecutor",
    live_provider_status: "blocked",
    live_provider_blocker_count: 4,
  },
  blockers: [
    {
      executor_id: "claude_code",
      status: "setup_blocked",
      detail: "Claude Code-compatible Local CLI Executor is not configured.",
      setup_required: ["CLAUDE_CODE_BIN"],
    },
  ],
  live_provider_readiness: {
    status: "blocked",
    selected_executor_id: "local_tool",
    require_repo_write_executor: true,
    mutation_gate: {
      open: false,
      confirm_env_var: "AITEAMOS_LIVE_PROVIDER_DOGFOOD",
      confirm_env_configured: false,
    },
    provider_prerequisites: {
      ticket_backend_status: "setup_blocked",
      memory_backend_status: "disabled",
      provider_smoke_status: "not_run",
    },
    reasons: [
      "runtime_executor_lacks_repo_write",
      "ticket_provider_not_ready",
      "memory_provider_not_ready",
      "live_provider_dogfood_not_confirmed",
    ],
    setup_required: ["select a ready RuntimeExecutor with repo:write", "PLANE_API_KEY", "Graphiti URI/user", "--execute", "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1"],
    blockers: [
      {
        reason: "runtime_executor_lacks_repo_write",
        scope: "selected_runtime_executor",
        status: "blocked",
        detail: "Live provider dogfood requires a repo:write RuntimeExecutor; local_tool capabilities do not include repo:write.",
        setup_required: ["select a ready RuntimeExecutor with repo:write"],
      },
      {
        reason: "live_provider_dogfood_not_confirmed",
        scope: "mutation_gate",
        status: "confirmation_required",
        detail: "Pass --execute and set AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 to mutate live Plane / Graphiti provider state.",
        setup_required: ["--execute", "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1"],
      },
    ],
    repo_write_candidates: [
      {
        executor_id: "claude_code",
        display_name: "Claude Code",
        status: "setup_blocked",
        ready: false,
        setup_required: ["CLAUDE_CODE_BIN"],
      },
      {
        executor_id: "codex_cli",
        display_name: "OpenAI Codex CLI Executor",
        status: "ready",
        ready: true,
        setup_required: [],
      },
    ],
    summary: {
      blocker_count: 4,
      repo_write_ready_count: 1,
      repo_write_candidate_count: 2,
      ticket_backend_status: "setup_blocked",
      memory_backend_status: "disabled",
      anti_wheel_boundary: "readiness reuses RuntimeExecutor health plus Ticket and Graphiti provider status",
    },
  },
};

const runtimeExecutionReplay = {
  session: runtimeExecutionSessions[0],
  execution_artifacts: {
    request_id: "exec-chat-runtime-mutation",
    artifacts: [{ kind: "runtime_session_artifact", ref: "artifact://runtime-session", api_key: "[redacted]" }],
    evidence: [{ kind: "test_evidence", ref: "pytest::runtime-session::passed" }],
  },
  approvals: [
    {
      id: "approval-exec-chat-runtime-mutation-1",
      status: "requested",
      ticket_id: "rd-9999",
      employee_id: "alex",
      executor_id: "claude_code",
      required_capability: "repo:write",
      reason: "Runtime mutation needs governed approval before writing repository files.",
      checkpoint_ref: "langgraph:exec-chat-runtime-mutation",
      source_state_ref: "state://universal_employee_agent/exec-chat-runtime-mutation/governance_gate",
      last_run_request_id: "exec-chat-runtime-mutation-approved",
      last_run_status: "blocked",
      last_ingestion_blocker: "approval_run_waiting_for_fresh_evidence",
    },
  ],
  state_snapshots: [
    {
      approval_id: "approval-exec-chat-runtime-mutation-1",
      source_state_snapshot_ref: ".aiteamos/execution_state_snapshots/exec-chat-runtime-mutation.json",
      state_summary: { request_id: "exec-chat-runtime-mutation", current_step: "governance_gate" },
      state_delta: { from: "execution_request", to: "governance_gate" },
    },
  ],
  native_checkpoint_history: [
    {
      index: 0,
      thread_id: "exec-chat-runtime-mutation",
      checkpoint_id: "checkpoint-native-1",
      metadata: { step: 5 },
      next: ["request_approval_interrupt"],
      state_summary: { request_id: "exec-chat-runtime-mutation", current_step: "request_approval_interrupt" },
      state_delta: {
        from: "governance_gate",
        to: "request_approval_interrupt",
        changed_keys: ["approval_interrupt"],
      },
    },
  ],
  state_transitions: [
    {
      index: 0,
      event: "execution.state_transition",
      source_kind: "state_snapshot",
      from: "execution_request",
      to: "governance_gate",
      changed_keys: ["approval_interrupt"],
      checkpoint_ref: "langgraph:exec-chat-runtime-mutation",
      source_state_ref: "state://universal_employee_agent/exec-chat-runtime-mutation/governance_gate",
      source_state_snapshot_ref: ".aiteamos/execution_state_snapshots/exec-chat-runtime-mutation.json",
    },
  ],
  trace_events: [{ event: "trace.step", authorization: "[redacted]" }],
  handoff_summary: {
    schema: "execution_replay_handoff_policy.v1",
    status: "durable_handoff_recorded",
    source_kind: "execution_artifact",
    ticket_id: "rd-9999",
    source_employee_id: "clara",
    source_role: "AI Team OS Manager",
    target_employee_id: "victor",
    target_role: "AI Runtime Owner",
    lane: "rd",
    confidence: 0.91,
    reason: "Selected under handoff_policy. memory_scope matched. risk_boundary=critical.",
    policy: {
      policy_aware: true,
      required_memory_scopes: ["employee:victor"],
      matched_memory_scopes: ["employee:victor"],
      available_memory_scopes: ["aiteamos", "employee:victor"],
      memory_scope_match: "matched",
      risk_level: "critical",
      max_risk_level: "critical",
      risk_allowed: true,
    },
    required_memory_scopes: ["employee:victor"],
    matched_memory_scopes: ["employee:victor"],
    available_memory_scopes: ["aiteamos", "employee:victor"],
    memory_scope_match: "matched",
    risk_level: "critical",
    max_risk_level: "critical",
    risk_allowed: true,
    policy_aware: true,
    provenance: { source_kind: "langgraph_handoff_decision", source_ref: "exec-chat-runtime-mutation" },
    refs: [
      { kind: "ticket", ref: "rd-9999" },
      { kind: "employee", ref: "clara" },
      { kind: "employee", ref: "victor" },
      { kind: "request", ref: "exec-chat-runtime-mutation" },
    ],
  },
  coverage_summary: {
    schema: "execution_replay_coverage.v1",
    required_chain_complete: true,
    gaps: [],
    coverage: {
      ticket: true,
      employee: true,
      runtime: true,
      evidence: true,
      trace: true,
      state: true,
      checkpoint: true,
      approval: true,
      asset_or_memory: true,
      handoff: true,
      handoff_policy: true,
    },
    counts: {
      timeline_event_count: 6,
      artifact_count: 1,
      evidence_count: 1,
      approval_count: 1,
      state_snapshot_count: 1,
      native_checkpoint_count: 1,
      state_transition_count: 1,
      trace_event_count: 1,
      handoff_ref_count: 4,
    },
    refs: {
      ticket_refs: ["rd-9999"],
      employee_refs: ["alex"],
      memory_refs: ["mem-runtime"],
      asset_refs: ["asset-closeout-ui"],
      evidence_refs: ["pytest::runtime-session::passed"],
    },
  },
  timeline: [
    { index: 0, kind: "session", event: "execution.session", title: "Execution session needs_approval", refs: [] },
    { index: 1, kind: "tool_event", event: "universal_agent.tool.completed", title: "search_tickets", refs: [{ kind: "ticket", ref: "rd-9999" }] },
    { index: 2, kind: "approval_run", event: "approval.run.completed", title: "approval run completed", refs: [{ kind: "approval", ref: "approval-exec-chat-runtime-mutation-1" }] },
    { index: 3, kind: "state_snapshot", event: "execution.state_snapshot", title: "State snapshot governance_gate", refs: [] },
    { index: 4, kind: "state_transition", event: "execution.state_transition", title: "execution_request -> governance_gate", refs: [] },
    { index: 5, kind: "asset_candidate", event: "asset.candidate.proposed", title: "Proposed memory and asset refs", refs: [{ kind: "memory", ref: "mem-runtime" }, { kind: "asset", ref: "asset-closeout-ui" }] },
  ],
};

describe("RuntimePage", () => {
  beforeEach(() => {
    window.location.hash = "";
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/runtime-executors/sessions")) {
          return new Response(JSON.stringify(runtimeExecutionSessions), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/runtime-executors")) {
          return new Response(JSON.stringify(runtimeExecutorRegistry), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/runtime-executors/sessions/alex%3A%3Athread-runtime%3A%3Ard-9999")) {
          return new Response(JSON.stringify(runtimeExecutionReplay), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        return new Response("not found", { status: 404 });
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders runtime sessions and opens replay detail", async () => {
    render(<RuntimePage selectedSessionKey={null} />);

    expect(await screen.findByText("Runtime Replay")).toBeTruthy();
    expect(await screen.findByText("Runtime Provider Readiness")).toBeTruthy();
    expect(screen.getByText("1/2 repo-write ready")).toBeTruthy();
    expect(screen.getByText("gate closed")).toBeTruthy();
    expect(screen.getByText("runtime executor lacks repo write")).toBeTruthy();
    expect(screen.getByText("live provider dogfood not confirmed")).toBeTruthy();
    expect(screen.getByText("selected local_tool")).toBeTruthy();
    expect(screen.getByText("Ticket setup blocked")).toBeTruthy();
    expect(screen.getByText("Memory disabled")).toBeTruthy();
    expect(screen.getByText("smoke not run")).toBeTruthy();
    expect(screen.getByText("OpenAI Codex CLI Executor")).toBeTruthy();
    expect(await screen.findByText("exec-chat-runtime-mutation")).toBeTruthy();
    fireEvent.click(await screen.findByText("exec-chat-runtime-mutation"));

    expect(await screen.findByText("Replay Detail")).toBeTruthy();
    expect(screen.getByText("execution.state_snapshot")).toBeTruthy();
    expect(screen.getByText("1 state snapshots")).toBeTruthy();
    expect(screen.getByText("1 native checkpoints")).toBeTruthy();
    expect(screen.getByText("Native Checkpoints")).toBeTruthy();
    expect(screen.getByText("checkpoint-native-1")).toBeTruthy();
    expect(screen.getByText("1 state transitions")).toBeTruthy();
    expect(screen.getByText("State Transitions")).toBeTruthy();
    expect(screen.getByText("Replay Coverage")).toBeTruthy();
    expect(screen.getByText("complete")).toBeTruthy();
    expect(screen.getByText("Assets/Memory: yes")).toBeTruthy();
    expect(screen.getByText("Handoff Policy")).toBeTruthy();
    expect(screen.getByText("durable handoff recorded")).toBeTruthy();
    expect(screen.getByText("risk critical")).toBeTruthy();
    expect(screen.getByText("victor")).toBeTruthy();
    expect(screen.getAllByText("employee:victor").length).toBeGreaterThan(0);
    expect(screen.getByText("Risk boundary")).toBeTruthy();
    expect(screen.getByText("matched")).toBeTruthy();
    expect(screen.getAllByText("execution_request -> governance_gate").length).toBeGreaterThan(0);
    expect(screen.getByText("Session Refs")).toBeTruthy();
    expect(screen.getByText("Runtime Approvals")).toBeTruthy();
    expect(screen.getByText("Runtime mutation needs governed approval before writing repository files.")).toBeTruthy();
    expect(screen.getAllByText(/approval_run_waiting_for_fresh_evidence/).length).toBeGreaterThan(0);
    expect(screen.getByText(/state_summary/)).toBeTruthy();
    expect(screen.getByText(/native_checkpoint_history/)).toBeTruthy();
    expect(screen.getByText(/state_transitions/)).toBeTruthy();
    expect(screen.getByText(/\[redacted\]/)).toBeTruthy();
    await waitFor(() => {
      expect(window.location.hash).toBe("#/runtime/alex%3A%3Athread-runtime%3A%3Ard-9999");
    });
  });

  it("links replay refs to Ticket, Employee, Memory, and Asset surfaces", async () => {
    render(<RuntimePage selectedSessionKey="alex::thread-runtime::rd-9999" />);

    expect(await screen.findByText("Replay Detail")).toBeTruthy();

    fireEvent.click(screen.getAllByRole("button", { name: "Open employee alex" })[0]);
    expect(window.location.hash).toBe("#/employees/alex");

    fireEvent.click(screen.getAllByRole("button", { name: "Open ticket rd-9999" })[0]);
    expect(window.location.hash).toBe("#/tickets/rd-9999");

    fireEvent.click(screen.getAllByRole("button", { name: "Open memory mem-runtime" })[0]);
    expect(window.location.hash).toBe("#/assets/knowledge/memory%3Amem-runtime");

    fireEvent.click(screen.getByRole("button", { name: "Open asset asset-closeout-ui" }));
    expect(window.location.hash).toBe("#/assets/asset/asset-closeout-ui");

    fireEvent.click(screen.getAllByRole("button", { name: "Open approval approval-exec-chat-runtime-mutation-1" })[0]);
    expect(window.location.hash).toBe("#/assets/review/approval%3Aapproval-exec-chat-runtime-mutation-1");
  });

  it("opens a route-backed replay from the session key", async () => {
    render(<RuntimePage selectedSessionKey="alex::thread-runtime::rd-9999" />);

    expect(await screen.findByText("Replay Detail")).toBeTruthy();
    expect(screen.getByText("approval.run.completed")).toBeTruthy();
    expect(vi.mocked(fetch).mock.calls.some(([input]) => String(input).endsWith("/runtime-executors/sessions/alex%3A%3Athread-runtime%3A%3Ard-9999"))).toBe(true);
  });
});
