import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EmployeesPage } from "../pages/employees";

const employees = [
  {
    id: "clara",
    display_name: "Clara",
    kind: "ai",
    role: "AI Team OS Manager",
    summary: "Coordinator",
    skills: ["ticket-specification"],
    skill_refs: ["ticket-specification"],
    capability_tags: ["ticket-specification"],
    personality_tags: ["calm"],
    memory_scopes: ["aiteamos", "employee:clara"],
    preferred_runtime: "universal_employee_agent",
    permission_policy: { permissions: ["chat", "manage_tickets"] },
    handoff_policy: { can_receive_handoffs: true, escalate_to: "clara", accepts_lanes: ["ops"], max_risk_level: "high" },
    current_load: {
      active_ticket_count: 0,
      assigned_ticket_count: 0,
      validation_ticket_count: 0,
      active_run_count: 0,
      needs_approval_run_count: 0,
      status: "available",
      active_ticket_ids: [],
      active_run_ids: [],
    },
    ai_engine_mode: "deepseek_chat_or_file_stub",
    default_ai_engine: "system",
    preserve_engine_thread: true,
    default_thread_id: "employee-clara-default",
  },
  {
    id: "alex",
    display_name: "Alex",
    kind: "ai",
    role: "AI RD / Implementer",
    summary: "Implementer",
    skills: ["test-engineering"],
    skill_refs: ["test-engineering"],
    capability_tags: ["backend-api-implementation", "test-engineering"],
    personality_tags: ["direct"],
    memory_scopes: ["aiteamos", "employee:alex"],
    preferred_runtime: "universal_employee_agent",
    permission_policy: { permissions: ["chat", "manage_tickets"] },
    handoff_policy: {
      can_receive_handoffs: true,
      escalate_to: "clara",
      accepts_lanes: ["rd"],
      preferred_lanes: ["rd"],
      max_risk_level: "critical",
      max_active_tickets: 3,
    },
    current_load: {
      active_ticket_count: 1,
      assigned_ticket_count: 1,
      validation_ticket_count: 0,
      active_run_count: 1,
      needs_approval_run_count: 1,
      status: "needs_attention",
      active_ticket_ids: ["rd-0001"],
      active_run_ids: ["run-load-needs-approval"],
    },
    ai_engine_mode: "external_or_file_stub",
    default_ai_engine: "system",
    preserve_engine_thread: true,
    default_thread_id: "employee-alex-default",
  },
];

const threadsByEmployee = {
  clara: {
    employee_id: "clara",
    active_thread_id: "employee-clara-default",
    threads: [
      {
        id: "employee-clara-default",
        employee_id: "clara",
        title: "Coordinate tickets",
        created_at: "2026-06-01T00:00:00Z",
        updated_at: "2026-06-01T00:05:00Z",
        last_message_at: "2026-06-01T00:05:00Z",
        message_count: 2,
        archived: false,
        saved_path: ".aiteamos/conversations/employee-clara-default.jsonl",
      },
    ],
  },
  alex: {
    employee_id: "alex",
    active_thread_id: "employee-alex-default",
    threads: [
      {
        id: "employee-alex-default",
        employee_id: "alex",
        title: "Implement ticket flow",
        created_at: "2026-06-01T00:00:00Z",
        updated_at: "2026-06-01T00:10:00Z",
        last_message_at: "2026-06-01T00:10:00Z",
        message_count: 4,
        archived: false,
        saved_path: ".aiteamos/conversations/employee-alex-default.jsonl",
      },
    ],
  },
};

const workByEmployee = {
  clara: {
    employee_id: "clara",
    current_tickets: [],
    historical_tickets: [],
    reports: [],
    validations: [],
    blocked_records: [],
    handoffs: [],
    asset_candidates: [],
    approved_assets: [],
    asset_reviews: [],
    runtime_runs: [],
    quality_feedback: [],
    contribution: {
      ticket_count: 0,
      current_ticket_count: 0,
      report_count: 0,
      validation_count: 0,
      blocked_count: 0,
      handoff_count: 0,
      asset_candidate_count: 0,
      approved_asset_count: 0,
      asset_review_count: 0,
      runtime_run_count: 0,
      quality_feedback_count: 0,
      tool_event_count: 0,
    },
  },
  alex: {
    employee_id: "alex",
    current_tickets: [
      {
        ticket_id: "rd-0001",
        title: "Implement ticket flow",
        status: "assigned",
        role: "owner",
        updated_at: "2026-06-01T00:10:00Z",
        next_action: "alex investigates and reports",
      },
    ],
    historical_tickets: [
      {
        ticket_id: "rd-0001",
        title: "Implement ticket flow",
        status: "assigned",
        role: "owner",
        updated_at: "2026-06-01T00:10:00Z",
        next_action: "alex investigates and reports",
      },
    ],
    reports: [],
    validations: [],
    blocked_records: [],
    handoffs: [
      {
        ticket_id: "rd-0001",
        title: "Implement ticket flow",
        relation: "target",
        event: {
          type: "handoff_requested",
          at: "2026-06-01T00:09:00Z",
          data: {
            from_employee_id: "clara",
            from_role: "AI Team OS Manager",
            to_employee_id: "alex",
            to_role: "AI RD / Implementer",
            content: "RD ownership required for runtime implementation.",
            source_run_id: "run-handoff-policy",
          },
        },
      },
    ],
    asset_candidates: [
      {
        asset_id: "asset-load-candidate",
        candidate_id: "asset-candidate-load",
        asset_type: "tool_call",
        title: "Reusable terminal evidence command",
        status: "proposed",
        review_state: "proposed",
        scope_kind: "ticket",
        scope_ref: "rd-0001",
        source_ticket_id: "rd-0001",
        source_run_id: "run-load-needs-approval",
        source_ref: "external-runtime:run-load-needs-approval",
        created_at: "2026-06-01T00:11:00Z",
        updated_at: "2026-06-01T00:11:00Z",
      },
      {
        asset_id: "asset-employee-improvement-alex",
        candidate_id: "employee-improvement-alex-runtime-feedback-run-load-needs-approval",
        asset_type: "employee_improvement",
        title: "Runtime blocker triage improvement",
        status: "proposed",
        review_state: "proposed",
        scope_kind: "employee",
        scope_ref: "alex",
        source_ticket_id: "rd-0001",
        source_run_id: "run-load-needs-approval",
        source_ref: "runtime-feedback:run-load-needs-approval",
        created_at: "2026-06-01T00:13:00Z",
        updated_at: "2026-06-01T00:13:00Z",
      },
    ],
    approved_assets: [
      {
        asset_id: "asset-approved-load",
        candidate_id: "asset-candidate-load",
        asset_type: "tool_call",
        title: "Reusable terminal evidence command",
        status: "approved",
        review_state: "approved",
        scope_kind: "ticket",
        scope_ref: "rd-0001",
        source_ticket_id: "rd-0001",
        source_run_id: "run-load-needs-approval",
        source_ref: "external-runtime:run-load-needs-approval",
        created_at: "2026-06-01T00:12:00Z",
        updated_at: "2026-06-01T00:12:00Z",
      },
      {
        asset_id: "asset-improvement-alex",
        candidate_id: "employee-improvement-alex-runtime-feedback-run-load-needs-approval",
        asset_type: "employee_improvement",
        title: "Runtime blocker triage improvement",
        status: "approved",
        review_state: "approved",
        scope_kind: "employee",
        scope_ref: "alex",
        source_ticket_id: "rd-0001",
        source_run_id: "run-load-needs-approval",
        source_ref: "runtime-feedback:run-load-needs-approval",
        application_status: "",
        application_report_id: "",
        application_employee_id: "",
        created_at: "2026-06-01T00:14:00Z",
        updated_at: "2026-06-01T00:14:00Z",
      },
    ],
    asset_reviews: [
      {
        review_id: "asset-review-load-1",
        candidate_id: "asset-candidate-load",
        asset_id: "asset-approved-load",
        status: "approved",
        reviewer_employee_id: "clara",
        reason: "Useful reusable command.",
        relation_to_employee: "asset_owner",
        created_at: "2026-06-01T00:12:00Z",
        updated_at: "2026-06-01T00:12:00Z",
      },
    ],
    runtime_runs: [
      {
        request_id: "run-load-needs-approval",
        run_id: "run-load-needs-approval",
        session_key: "alex::employee-alex-default::rd-0001",
        ticket_id: "rd-0001",
        action: "terminal_run",
        executor_id: "local_tool",
        status: "blocked",
        trace_ref: ".aiteamos/traces/run-load-needs-approval.jsonl",
        artifact_count: 1,
        evidence_count: 1,
        tool_event_count: 2,
        memory_candidate_count: 1,
        latency_ms: 1250,
        total_cost: 0.0123,
        started_at: "2026-06-01T00:10:00Z",
        finished_at: "2026-06-01T00:10:02Z",
      },
    ],
    quality_feedback: [
      {
        id: "asset-review-load-1",
        kind: "asset_review",
        status: "approved",
        summary: "Useful reusable command.",
        source_ref: "asset-candidate-load",
        reviewer_employee_id: "clara",
        ticket_id: "rd-0001",
        created_at: "2026-06-01T00:12:00Z",
      },
      {
        id: "runtime-feedback:run-load-needs-approval",
        kind: "runtime_result",
        status: "blocked",
        summary: "Runtime run run-load-needs-approval ended with status=blocked.",
        source_ref: "run-load-needs-approval",
        reviewer_employee_id: "",
        ticket_id: "rd-0001",
        created_at: "2026-06-01T00:10:02Z",
      },
    ],
    contribution: {
      ticket_count: 1,
      current_ticket_count: 1,
      report_count: 0,
      validation_count: 0,
      blocked_count: 0,
      handoff_count: 1,
      asset_candidate_count: 2,
      approved_asset_count: 2,
      asset_review_count: 1,
      runtime_run_count: 1,
      quality_feedback_count: 2,
      tool_event_count: 2,
    },
  },
};

const analyticsByEmployee = {
  clara: {
    employee_id: "clara",
    assigned_ticket_count: 0,
    completed_ticket_count: 0,
    validation_pass_rate: 0,
    candidates_produced: 1,
    recalled_asset_count: 0,
    blocker_count: 0,
    validation_failure_count: 0,
    stale_asset_count: 0,
    useful_recall_count: 0,
    execution_run_count: 0,
    total_cost: 0,
    average_latency_ms: 0,
    source_counts: {
      tickets: 0,
      reports: 0,
      events: 1,
      assets: 1,
      execution_runs: 0,
    },
  },
  alex: {
    employee_id: "alex",
    assigned_ticket_count: 1,
    completed_ticket_count: 0,
    validation_pass_rate: 0.75,
    candidates_produced: 0,
    recalled_asset_count: 1,
    blocker_count: 1,
    validation_failure_count: 1,
    stale_asset_count: 1,
    useful_recall_count: 1,
    execution_run_count: 2,
    total_cost: 0.1234,
    average_latency_ms: 1250,
    source_counts: {
      tickets: 1,
      reports: 0,
      events: 2,
      assets: 1,
      execution_runs: 2,
    },
  },
};

const graphByEmployee = {
  clara: {
    employee_id: "clara",
    nodes: [
      { id: "employee:clara", kind: "employee", label: "Clara", status: "active", ref: "clara", metadata: {} },
    ],
    edges: [],
    grouped_edges: {},
    source_counts: {
      tickets: 0,
      reports: 0,
      events: 1,
      assets: 1,
    },
    provider_projection: {
      employee_profile: {
        provider: "graphiti",
        asset_id: "employee-profile-clara",
        asset_type: "employee_profile_summary",
        status: "not_projected",
        backend_status: "setup_blocked",
        detail: "Employee profile summary has not been projected to Graphiti.",
        episode_id: "",
        ingested_at: "",
      },
    },
  },
  alex: {
    employee_id: "alex",
    nodes: [
      { id: "employee:alex", kind: "employee", label: "Alex", status: "active", ref: "alex", metadata: {} },
      { id: "ticket:rd-0001", kind: "ticket", label: "Implement ticket flow", status: "assigned", ref: "rd-0001", metadata: {} },
      { id: "asset:mem-approved-1", kind: "memory", label: "Approved Memory", status: "approved", ref: "mem-approved-1", metadata: {} },
    ],
    edges: [
      {
        id: "edge-alex-ticket-1",
        type: "employee.assigned_ticket",
        source_id: "employee:alex",
        target_id: "ticket:rd-0001",
        label: "assigned Ticket",
        evidence_refs: ["event-assigned-1"],
        metadata: {},
      },
      {
        id: "edge-alex-memory-1",
        type: "employee.recalled_asset",
        source_id: "employee:alex",
        target_id: "asset:mem-approved-1",
        label: "recalled asset",
        evidence_refs: ["usage-approved-1"],
        metadata: {},
      },
    ],
    grouped_edges: {
      "employee.assigned_ticket": [
        {
          id: "edge-alex-ticket-1",
          type: "employee.assigned_ticket",
          source_id: "employee:alex",
          target_id: "ticket:rd-0001",
          label: "assigned Ticket",
          evidence_refs: ["event-assigned-1"],
          metadata: {},
        },
      ],
      "employee.recalled_asset": [
        {
          id: "edge-alex-memory-1",
          type: "employee.recalled_asset",
          source_id: "employee:alex",
          target_id: "asset:mem-approved-1",
          label: "recalled asset",
          evidence_refs: ["usage-approved-1"],
          metadata: {},
        },
      ],
    },
    source_counts: {
      tickets: 1,
      reports: 0,
      events: 2,
      assets: 1,
    },
    provider_projection: {
      employee_profile: {
        provider: "graphiti",
        asset_id: "employee-profile-alex",
        asset_type: "employee_profile_summary",
        status: "ingested",
        backend_status: "ready",
        detail: "Employee profile summary is projected to Graphiti.",
        episode_id: "episode-employee-profile-alex",
        ingested_at: "2026-06-01T00:00:00Z",
      },
    },
  },
};

const growthEvalByEmployee = {
  clara: {
    contract_version: "aiteamos_employee_growth_eval.v1",
    status: "warning",
    detail: "Employee growth evidence for clara has 1 warning signal(s).",
    summary: {
      employee_id: "clara",
      current_load_status: "available",
      active_ticket_count: 0,
      active_run_count: 0,
      current_ticket_count: 0,
      historical_ticket_count: 0,
      report_count: 0,
      handoff_count: 0,
      asset_candidate_count: 0,
      approved_asset_count: 0,
      asset_review_count: 0,
      runtime_run_count: 0,
      quality_feedback_count: 0,
      improvement_candidate_count: 0,
      approved_improvement_count: 0,
      applied_improvement_count: 0,
      improvement_loop_proof_status: "passed",
      improvement_loop_candidate_id: "employee-improvement-clara-runtime-feedback:employee-growth-proof-request",
      improvement_loop_asset_id: "asset-employee-improvement-clara-runtime-feedback:employee-growth-proof-request",
      improvement_loop_application_status: "applied",
      improvement_loop_ticket_report_id: "report-employee-growth-proof-clara",
      improvement_loop_applied_change_count: 4,
      improvement_loop_workspace: "temporary",
      handoff_target_employee_id: "",
      handoff_work_history_score: 0,
      provider_projection_status: "not_projected",
      graph_node_count: 1,
      graph_edge_count: 0,
      source_counts: {},
    },
    checks: [
      {
        id: "quality_feedback",
        status: "warning",
        detail: "No quality feedback has been recorded for Clara yet.",
        evidence: { quality_feedback_count: 0 },
      },
    ],
    blockers: [],
    warnings: ["quality_feedback_missing"],
    commands: [],
  },
  alex: {
    contract_version: "aiteamos_employee_growth_eval.v1",
    status: "passed",
    detail: "Employee growth evidence is passing for alex.",
    summary: {
      employee_id: "alex",
      current_load_status: "needs_attention",
      active_ticket_count: 1,
      active_run_count: 1,
      current_ticket_count: 1,
      historical_ticket_count: 1,
      report_count: 0,
      handoff_count: 1,
      asset_candidate_count: 2,
      approved_asset_count: 2,
      asset_review_count: 1,
      runtime_run_count: 1,
      quality_feedback_count: 2,
      improvement_candidate_count: 1,
      approved_improvement_count: 1,
      applied_improvement_count: 0,
      improvement_loop_proof_status: "passed",
      improvement_loop_candidate_id: "employee-improvement-alex-runtime-feedback:employee-growth-proof-request",
      improvement_loop_asset_id: "asset-employee-improvement-alex-runtime-feedback:employee-growth-proof-request",
      improvement_loop_application_status: "applied",
      improvement_loop_ticket_report_id: "report-employee-growth-proof",
      improvement_loop_applied_change_count: 4,
      improvement_loop_workspace: "temporary",
      handoff_target_employee_id: "alex",
      handoff_work_history_score: 3,
      provider_projection_status: "ingested",
      graph_node_count: 3,
      graph_edge_count: 2,
      source_counts: {
        tickets: 1,
        events: 2,
        assets: 1,
        execution_runs: 1,
      },
    },
    checks: [
      {
        id: "current_load",
        status: "passed",
        detail: "Current load is projected from Ticket and runtime facts.",
        evidence: { active_ticket_count: 1, active_run_count: 1 },
      },
      {
        id: "work_history",
        status: "passed",
        detail: "Work history is populated for handoff decisions.",
        evidence: { handoff_work_history_score: 3 },
      },
      {
        id: "improvement_loop",
        status: "passed",
        detail: "Quality feedback can become an approved Employee improvement asset.",
        evidence: { ticket_report_id: "report-employee-growth-proof" },
      },
    ],
    blockers: [],
    warnings: [],
    commands: [
      "python scripts/employee_growth_eval_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-e-employee-growth-eval-smoke.json",
    ],
  },
};

const capabilities = {
  status: {
    capability_count: 2,
    enabled_count: 2,
    configured_count: 2,
    ready_count: 2,
    tool_count: 1,
    kernel_command_count: 1,
    mcp_tool_count: 0,
    native_api_tool_count: 0,
    cli_tool_count: 0,
    ci_tool_count: 0,
    saved_paths: {},
  },
  capabilities: [
    {
      id: "search_knowledge",
      name: "Search Knowledge",
      kind: "tool",
      source_kind: "kernel_command",
      domain: "knowledge",
      source: "file",
      status: "ready",
      enabled: true,
      configured: true,
      description: "Search team knowledge",
      owner_scope: "system",
      permissions: [],
      required_settings: [],
      arguments: [],
      produces: [],
      boundary: "",
      deep_link: "",
      connector_id: "",
    },
  ],
  model: {},
};

const aiEngines = {
  active_engine: "deepseek",
  deepseek_model: "deepseek-v4-flash",
  deepseek_thinking: "disabled",
  openai_model: "gpt-5-nano",
  fallback_on_error: true,
  engines: {
    stub: {
      id: "stub",
      display_name: "File stub",
      kind: "local",
      active: false,
      api_key_configured: true,
      status: "available",
    },
    deepseek: {
      id: "deepseek",
      display_name: "DeepSeek",
      kind: "llm_api",
      model: "deepseek-v4-flash",
      thinking: "disabled",
      active: true,
      api_key_configured: true,
      status: "configured",
    },
    openai: {
      id: "openai",
      display_name: "OpenAI / ChatGPT",
      kind: "llm_api",
      model: "gpt-5-nano",
      active: false,
      api_key_configured: false,
      status: "missing",
    },
  },
  api_keys_configured: { deepseek: true, openai: false },
  saved_paths: { ai_engines: ".aiteamos/ai_engines.json" },
};

describe("EmployeesPage", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/chat/employees/alex/ai-engine") && init?.method === "PUT") {
        const payload = JSON.parse(String(init.body ?? "{}"));
        return new Response(JSON.stringify({ ...employees[1], default_ai_engine: payload.default_ai_engine }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes("/employees/alex/quality-feedback/") && url.endsWith("/improvement-candidate")) {
        return new Response(JSON.stringify({
          employee_id: "alex",
          feedback: workByEmployee.alex.quality_feedback[1],
          candidate: {
            id: "employee-improvement-alex-runtime-feedback-run-load-needs-approval",
            asset_type: "employee_improvement",
            title: "Improve alex from runtime feedback",
          },
          saved_paths: { asset_candidates: ".aiteamos/assets/candidates.json" },
        }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.endsWith("/employees/alex/improvement-assets/asset-improvement-alex/apply")) {
        return new Response(JSON.stringify({
          employee_id: "alex",
          asset_id: "asset-improvement-alex",
          status: "applied",
          detail: "Employee improvement Asset applied.",
          applied_changes: {
            skill_refs: ["runtime-blocker-triage"],
            memory_scopes: ["employee:alex:runtime-blockers"],
            capability_tags: ["runtime-debugging"],
            personality_tags: ["evidence-driven"],
          },
          profile: {},
          asset: {
            id: "asset-improvement-alex",
            asset_type: "employee_improvement",
            title: "Runtime blocker triage improvement",
          },
          ticket_report_id: "ticket-report-employee-improvement-applied",
          saved_paths: { employee_profile: ".aiteamos/employees/alex.yaml" },
        }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      const body = url.includes("/employees/") && url.includes("/analytics")
        ? analyticsByEmployee[url.includes("alex") ? "alex" : "clara"]
        : url.includes("/employees/") && url.includes("/graph")
        ? graphByEmployee[url.includes("alex") ? "alex" : "clara"]
        : url.includes("/employees/") && url.includes("/growth-eval")
        ? growthEvalByEmployee[url.includes("alex") ? "alex" : "clara"]
        : url.includes("/tickets/employees/")
        ? workByEmployee[url.includes("alex") ? "alex" : "clara"]
        : url.includes("/chat/threads")
        ? threadsByEmployee[url.includes("alex") ? "alex" : "clara"]
        : url.includes("/capabilities")
          ? capabilities
          : url.includes("/chat/ai-engines")
            ? aiEngines
            : employees;
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal(
      "fetch",
      fetchMock,
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders file-backed employees and selected detail", async () => {
    render(<EmployeesPage selectedId="alex" />);

    expect(await screen.findByText("AI Employee Directory")).toBeTruthy();
    expect(await screen.findByText("Clara")).toBeTruthy();
    expect(screen.getAllByText("Alex").length).toBeGreaterThan(0);
    expect(screen.getAllByText("AI RD / Implementer").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Implement ticket flow/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("1 skills").length).toBeGreaterThan(0);
    expect(screen.queryByText("Ready Tools")).toBeNull();
    expect(screen.getByText("Workforce Record")).toBeTruthy();
    expect(screen.getByText("Load Snapshot")).toBeTruthy();
    expect(await screen.findByText("Growth Evidence")).toBeTruthy();
    expect(screen.getByText("Employee growth evidence is passing for alex.")).toBeTruthy();
    expect(screen.getByText("proof passed")).toBeTruthy();
    expect(screen.getByText("application applied")).toBeTruthy();
    expect(screen.getByText("4 proof changes")).toBeTruthy();
    expect(screen.getByText("report-employee-growth-proof")).toBeTruthy();
    expect(screen.getByText("Growth Checks")).toBeTruthy();
    expect(screen.getByText("current_load")).toBeTruthy();
    expect(screen.getByText("Work history is populated for handoff decisions.")).toBeTruthy();
    expect(screen.getByText("Evidence Commands")).toBeTruthy();
    expect(screen.getByText(/employee_growth_eval_smoke\.py/)).toBeTruthy();
    expect(screen.getByText("Memory & Handoff Boundary")).toBeTruthy();
    expect(screen.getAllByText("employee:alex").length).toBeGreaterThan(0);
    expect(screen.getByText("Risk boundary")).toBeTruthy();
    expect(screen.getByText("critical")).toBeTruthy();
    expect(screen.getAllByText("Runtime Runs").length).toBeGreaterThan(0);
    expect(screen.getByText("Waiting Approval")).toBeTruthy();
    expect(screen.getByText("Runs: run-load-needs-approval")).toBeTruthy();
    expect(screen.getByText("Provider Projection")).toBeTruthy();
    expect(screen.getByText("employee-profile-alex")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Work Ledger" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Analytics" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Governance" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Work Ledger" }));
    expect(window.location.hash).toBe("#/employees/alex/work");
    expect(screen.getAllByText("Current Tickets").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Historical Tickets").length).toBeGreaterThan(0);
    expect(screen.getByText("Asset Contributions")).toBeTruthy();
    expect(screen.getByText("Handoffs")).toBeTruthy();
    expect(screen.getByText("clara -> alex")).toBeTruthy();
    expect(screen.getByText("Run: run-handoff-policy")).toBeTruthy();
    expect(screen.getAllByText("Reusable terminal evidence command").length).toBeGreaterThan(0);
    expect(screen.getByText("Runtime Run Ledger")).toBeTruthy();
    expect(screen.getAllByText("run-load-needs-approval").length).toBeGreaterThan(0);
    expect(screen.getByText("Quality Feedback")).toBeTruthy();
    expect(screen.getByText("Useful reusable command.")).toBeTruthy();
    expect(screen.getByText("Improvement Path")).toBeTruthy();
    expect(screen.getByText("Candidate Review")).toBeTruthy();
    expect(screen.getByText("Approved Assets")).toBeTruthy();
    expect(screen.getAllByText("Runtime blocker triage improvement").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Analytics" }));
    expect(screen.getByText("Phase 4a Core Metrics")).toBeTruthy();
    expect(screen.getByText("Assigned Tickets")).toBeTruthy();
    expect(screen.getByText("Validation Pass Rate")).toBeTruthy();
    expect(screen.getByText("75%")).toBeTruthy();
    expect(screen.getByText("Recalled Assets")).toBeTruthy();
    expect(screen.getByText("Phase 4b Quality Signals")).toBeTruthy();
    expect(screen.getByText("Blockers")).toBeTruthy();
    expect(screen.getByText("Validation Failures")).toBeTruthy();
    expect(screen.getByText("Useful Recalls")).toBeTruthy();
    expect(screen.getByText("Avg Latency")).toBeTruthy();
    expect(screen.getByText("1.3 s")).toBeTruthy();
    expect(screen.getByText("$0.1234")).toBeTruthy();
    expect(screen.getByText("Evidence Sources")).toBeTruthy();
    expect(screen.getByText("Graph Provenance")).toBeTruthy();
    expect(screen.getByText("Graph Nodes")).toBeTruthy();
    expect(screen.getByText("Graph Edges")).toBeTruthy();
    expect(screen.getByText("employee.assigned_ticket")).toBeTruthy();
    expect(screen.getByText("employee:alex -> ticket:rd-0001")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Capabilities" }));
    expect(screen.getByText("Assigned Skills")).toBeTruthy();
    expect(screen.getByText("Kernel Commands")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Governance" }));
    expect(screen.getByText("Memory & Handoff Boundary")).toBeTruthy();
    expect(screen.getByText("Permissions")).toBeTruthy();
  });

  it("opens route-backed work ledger provenance links", async () => {
    render(<EmployeesPage selectedId="alex" selectedDetail="work" />);

    expect(await screen.findByText("Runtime Run Ledger")).toBeTruthy();

    fireEvent.click(screen.getAllByRole("button", { name: "Open Ticket rd-0001" })[0]);
    expect(window.location.hash).toBe("#/tickets/rd-0001");

    fireEvent.click(screen.getByRole("button", { name: "Open Runtime Replay alex::employee-alex-default::rd-0001" }));
    expect(window.location.hash).toBe("#/runtime/alex%3A%3Aemployee-alex-default%3A%3Ard-0001");

    fireEvent.click(screen.getByRole("button", { name: "Open Asset asset-candidate-load" }));
    expect(window.location.hash).toBe("#/assets/review/candidate%3Aasset-candidate-load");

    fireEvent.click(screen.getByRole("button", { name: "Open Asset asset-approved-load" }));
    expect(window.location.hash).toBe("#/assets/asset/asset-approved-load");
  });

  it("proposes Employee improvement candidates from quality feedback", async () => {
    render(<EmployeesPage selectedId="alex" selectedDetail="work" />);

    expect(await screen.findByText("Quality Feedback")).toBeTruthy();
    const buttons = await screen.findAllByRole("button", { name: "Propose Improvement" });
    fireEvent.click(buttons[1]);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/employees/alex/quality-feedback/runtime-feedback%3Arun-load-needs-approval/improvement-candidate",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            actor_employee_id: "clara",
            reason: "Proposed from Employee work ledger feedback runtime-feedback:run-load-needs-approval.",
          }),
        }),
      );
    });
    const candidateButton = await screen.findByRole("button", {
      name: "employee-improvement-alex-runtime-feedback-run-load-needs-approval",
    });
    fireEvent.click(candidateButton);
    expect(window.location.hash).toBe("#/assets/review/candidate%3Aemployee-improvement-alex-runtime-feedback-run-load-needs-approval");
  });

  it("applies approved Employee improvement assets from the work ledger", async () => {
    render(<EmployeesPage selectedId="alex" selectedDetail="work" />);

    expect(await screen.findByText("Improvement Path")).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: "Apply Improvement" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/employees/alex/improvement-assets/asset-improvement-alex/apply",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            actor_employee_id: "clara",
            reason: "Applied from Employee work ledger improvement path.",
          }),
        }),
      );
    });
    expect(await screen.findByText("applied")).toBeTruthy();
  });

  it("updates the selected employee default AI Engine", async () => {
    render(<EmployeesPage selectedId="alex" />);

    fireEvent.click(await screen.findByRole("button", { name: "AI Engine" }));
    const input = screen.getByLabelText("Default AI Engine");
    fireEvent.change(input, { target: { value: "openai" } });
    fireEvent.click(screen.getByRole("button", { name: "Save default engine" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/chat/employees/alex/ai-engine",
        expect.objectContaining({
          method: "PUT",
          body: JSON.stringify({ default_ai_engine: "openai" }),
        }),
      );
    });
    expect(await screen.findByDisplayValue("openai")).toBeTruthy();
  });
});
