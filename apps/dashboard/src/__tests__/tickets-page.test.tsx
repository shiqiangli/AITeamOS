import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TicketsPage } from "../pages/tickets";

const tickets = [
  {
    id: "ticket-implement-plane-sync-123abc",
    title: "Implement Plane sync",
    description: "Connect local Tickets to the Plane Ticket Backend boundary.",
    status: "reported",
    assigned_employee_id: "alex",
    assigned_role: "",
    validation_employee_id: "peter",
    validation_role: "",
    knowledge_refs: ["doc:product-direction"],
    code_repository_ids: ["repo-aiteamos"],
    source_thread_id: "employee-clara-default",
    source_run_id: "run-1",
    reports: [
      {
        id: "report-1",
        reporter_employee_id: "peter",
        reporter_role: "AI PV",
        content: "Validation passed.",
        evidence: ["npm test passed"],
        report_type: "validation",
        created_at: "2026-06-03T08:30:00Z",
      },
    ],
    created_at: "2026-06-03T08:00:00Z",
    updated_at: "2026-06-03T08:30:00Z",
    saved_path: ".aiteamos/tickets/index.json",
  },
  {
    id: "rd-0009",
    title: "Inspect recalled Memory usage",
    description: "Selected from related Memory asset.",
    status: "assigned",
    assigned_employee_id: "clara",
    assigned_role: "",
    validation_employee_id: "",
    validation_role: "",
    knowledge_refs: [],
    code_repository_ids: [],
    source_thread_id: "thread-memory",
    source_run_id: "run-memory",
    reports: [],
    created_at: "2026-06-03T08:10:00Z",
    updated_at: "2026-06-03T08:20:00Z",
    saved_path: ".aiteamos/tickets/index.json",
  },
];

const supportedModes = [
  {
    id: "local_file",
    label: "Local file",
    status: "legacy",
    description: "Legacy projection for explicit migration checks.",
  },
  {
    id: "plane",
    label: "Plane",
    status: "ready",
    description: "Plane-backed Ticket fact source.",
  },
];

const backendSettings = {
  mode: "plane",
  local_file_path: ".aiteamos/tickets/index.json",
  saved_paths: {
    settings: ".aiteamos/tickets/backend.json",
    plane_projection: ".aiteamos/tickets/plane",
  },
  supported_modes: supportedModes,
};

const backendStatus = {
  mode: "plane",
  status: "ready",
  detail: "Plane Ticket Backend is active.",
  ticket_count: 1,
  local_file_path: ".aiteamos/tickets/index.json",
  provider: "plane",
  provider_ref_count: 1,
  setup_required: [],
  capabilities: ["create_ticket", "append_report_comment"],
  mapping: { Ticket: "provider record" },
  saved_paths: backendSettings.saved_paths,
  supported_modes: supportedModes,
};

const ticketAssets = [
  {
    id: "mem-candidate-1:candidate",
    kind: "memory_candidate",
    title: "Memory candidate from ticket-implement-plane-sync-123abc",
    status: "proposed",
    source_ticket_id: "ticket-implement-plane-sync-123abc",
    source_employee_id: "clara",
    assigned_employees: ["clara"],
    scopes: ["ticket:ticket-implement-plane-sync-123abc"],
    created_at: "2026-06-03T08:10:00Z",
    updated_at: "2026-06-03T08:10:00Z",
    metadata: {
      memory_id: "mem-candidate-1",
      source_trace_path: ".aiteamos/traces/run-candidate.jsonl",
    },
  },
  {
    id: "mem-1:usage-run-1:ticket-implement-plane-sync-123abc",
    kind: "memory",
    title: "Approved Memory reused by ticket-implement-plane-sync-123abc",
    status: "approved",
    source_ticket_id: "ticket-implement-plane-sync-123abc",
    source_employee_id: "alex",
    assigned_employees: ["clara"],
    scopes: ["ticket:rd-0001", "graphiti"],
    created_at: "2026-06-03T08:15:00Z",
    updated_at: "2026-06-03T08:30:00Z",
    metadata: {
      memory_id: "mem-1",
      derived_from_ticket_id: "rd-0001",
      usefulness_status: "useful",
      graphiti_episode_id: "episode-1",
    },
  },
];

const ticketGraph = {
  ticket_id: "ticket-implement-plane-sync-123abc",
  nodes: [
    { id: "ticket:ticket-implement-plane-sync-123abc", kind: "ticket", label: "Implement Plane sync", status: "reported", ref: "ticket-implement-plane-sync-123abc", metadata: {} },
    { id: "employee:alex", kind: "employee", label: "alex", status: "AI RD / Implementer", ref: "alex", metadata: { role: "AI RD / Implementer" } },
    { id: "report:report-1", kind: "report", label: "validation report", status: "validation", ref: "report-1", metadata: {} },
  ],
  edges: [
    {
      id: "ticket.assigned_to.employee:ticket:ticket-implement-plane-sync-123abc->employee:alex",
      type: "ticket.assigned_to.employee",
      source_id: "ticket:ticket-implement-plane-sync-123abc",
      target_id: "employee:alex",
      label: "assigned to",
      evidence_refs: [],
      metadata: {},
    },
    {
      id: "employee.produced.report:employee:alex->report:report-1",
      type: "employee.produced.report",
      source_id: "employee:alex",
      target_id: "report:report-1",
      label: "produced",
      evidence_refs: ["npm test passed"],
      metadata: {},
    },
  ],
  grouped_edges: {
    "ticket.assigned_to.employee": [
      {
        id: "ticket.assigned_to.employee:ticket:ticket-implement-plane-sync-123abc->employee:alex",
        type: "ticket.assigned_to.employee",
        source_id: "ticket:ticket-implement-plane-sync-123abc",
        target_id: "employee:alex",
        label: "assigned to",
        evidence_refs: [],
        metadata: {},
      },
    ],
    "employee.produced.report": [
      {
        id: "employee.produced.report:employee:alex->report:report-1",
        type: "employee.produced.report",
        source_id: "employee:alex",
        target_id: "report:report-1",
        label: "produced",
        evidence_refs: ["npm test passed"],
        metadata: {},
      },
    ],
  },
  source_counts: { events: 3, reports: 1, assets: 2, evidence: 1 },
};

const ticketPerformance = {
  ticket_id: "ticket-implement-plane-sync-123abc",
  status: "reported",
  contribution: [
    {
      employee_id: "alex",
      role: "AI RD / Implementer",
      assigned: true,
      validator: false,
      reporter: false,
      event_actor: true,
      asset_source: true,
      asset_assigned: false,
      report_count: 0,
      validation_report_count: 0,
      blocked_report_count: 0,
      evidence_count: 0,
      event_count: 2,
      candidate_count: 0,
      recalled_asset_count: 1,
      linked_asset_count: 1,
    },
    {
      employee_id: "peter",
      role: "AI PV",
      assigned: false,
      validator: true,
      reporter: true,
      event_actor: true,
      asset_source: true,
      asset_assigned: false,
      report_count: 1,
      validation_report_count: 1,
      blocked_report_count: 0,
      evidence_count: 1,
      event_count: 1,
      candidate_count: 0,
      recalled_asset_count: 0,
      linked_asset_count: 1,
    },
  ],
  quality_signals: {
    has_assignee: true,
    has_report: true,
    has_evidence: true,
    validation_requested: true,
    has_validation_report: true,
    has_blocker: false,
    candidate_produced: true,
    used_recalled_asset: true,
    graphiti_recall_recorded: true,
    provider_ref_recorded: true,
    missing_evidence: false,
    waiting_report: false,
    waiting_validation: false,
    blocked_or_failed: false,
  },
  source_counts: {
    events: 3,
    reports: 1,
    evidence: 1,
    assets: 2,
    memory_candidates: 1,
    recalled_assets: 1,
    graphiti_recalled_assets: 1,
    graph_nodes: 3,
    graph_edges: 2,
  },
};

const ticketEvidenceRequirements = {
  ticket_id: "ticket-implement-plane-sync-123abc",
  ticket_type: "rd",
  profile: "backend_change",
  satisfied: true,
  missing_required: [],
  evidence_refs: ["npm test passed"],
  requirements: [
    {
      id: "backend_change:validation_evidence",
      label: "Validation evidence recorded",
      required: true,
      satisfied: true,
      evidence_refs: ["npm test passed"],
      recommended_commands: ["pytest"],
      detail: "This Ticket profile requires at least one evidence ref before it can be marked validated.",
    },
  ],
};

const selfBootstrapSummary = {
  ticket_count: 2,
  validated_ticket_count: 1,
  blocked_ticket_count: 0,
  tickets_with_evidence: 1,
  tickets_missing_required_evidence: 1,
  memory_candidates_produced: 1,
  approved_memory_candidates: 1,
  approved_memories_recalled: 1,
  graphiti_memories_recalled: 1,
  useful_memory_recalls: 1,
  stale_or_superseded_assets: 0,
  summary: "2 self-bootstrap Tickets, 1 validated, 1 candidates produced, 1 approved assets recalled.",
  learning_delta: {
    new_candidates: 1,
    approved_candidates: 1,
    reused_prior_assets: 1,
    graphiti_reused_assets: 1,
    useful_recalls: 1,
    needs_validation_evidence: 1,
    blocked_or_failed_tickets: 0,
    stale_or_superseded_assets: 0,
  },
  tickets: [
    {
      ticket_id: "ticket-implement-plane-sync-123abc",
      title: "Implement Plane sync",
      status: "reported",
      assigned_employee_id: "alex",
      validation_employee_id: "peter",
      evidence_count: 1,
      missing_required_evidence: 0,
      validation_passed: true,
      blocked_or_failed: false,
      memory_candidates: 1,
      approved_memory_candidates: 1,
      approved_memories_recalled: 1,
      graphiti_memories_recalled: 1,
      useful_memory_recalls: 1,
      provider_ref_recorded: true,
      next_learning_action: "Post Clara learning summary and use this Ticket as prior evidence for the next batch.",
    },
    {
      ticket_id: "rd-0009",
      title: "Inspect recalled Memory usage",
      status: "assigned",
      assigned_employee_id: "clara",
      validation_employee_id: "",
      evidence_count: 0,
      missing_required_evidence: 1,
      validation_passed: false,
      blocked_or_failed: false,
      memory_candidates: 0,
      approved_memory_candidates: 0,
      approved_memories_recalled: 0,
      graphiti_memories_recalled: 0,
      useful_memory_recalls: 0,
      provider_ref_recorded: false,
      next_learning_action: "Attach validation evidence before marking this Ticket validated.",
    },
  ],
  source_counts: {
    tickets: 2,
    assets: 2,
    reports: 1,
    evidence: 1,
    memory_candidates: 1,
    memory_recall_usages: 1,
  },
};

describe("TicketsPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/tickets/self-bootstrap/summary")) {
          return new Response(JSON.stringify(selfBootstrapSummary), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/tickets/") && url.endsWith("/evidence-requirements")) {
          return new Response(JSON.stringify(ticketEvidenceRequirements), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/tickets/") && url.endsWith("/performance")) {
          return new Response(JSON.stringify(ticketPerformance), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/tickets/") && url.endsWith("/graph")) {
          return new Response(JSON.stringify(ticketGraph), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/tickets/assets")) {
          return new Response(JSON.stringify(ticketAssets), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/tickets")) {
          return new Response(JSON.stringify(tickets), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/tickets/backend")) {
          return new Response(JSON.stringify(backendSettings), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/tickets/status")) {
          return new Response(JSON.stringify(backendStatus), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        return new Response(JSON.stringify({ detail: `Unhandled URL ${url}` }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders local Tickets with status filters and backend source", async () => {
    render(<TicketsPage selectedSection="tickets" />);

    expect(await screen.findByText("Ticket Cockpit")).toBeTruthy();
    expect((await screen.findAllByText("Implement Plane sync")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("All").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Active").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Review").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Blocked").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Done").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Implement Plane sync").length).toBeGreaterThan(0);
    expect(screen.getAllByText("alex").length).toBeGreaterThan(0);
    expect(screen.getAllByText("peter").length).toBeGreaterThan(0);
    expect(screen.getAllByText("repo-aiteamos").length).toBeGreaterThan(0);
    expect(screen.getByText("Ticket Backend")).toBeTruthy();
    expect(screen.getAllByText("plane").length).toBeGreaterThan(0);
    expect(screen.getByText("Projection mirror")).toBeTruthy();
    expect(screen.getByText("Self-Bootstrap")).toBeTruthy();
    expect(screen.getByText(selfBootstrapSummary.summary)).toBeTruthy();
    expect(screen.getByText("Graphiti recall: 1")).toBeTruthy();
    expect(screen.getByText("Needs evidence")).toBeTruthy();
    expect(screen.getByText("rd-0009")).toBeTruthy();
    expect(screen.getByText("Attach validation evidence before marking this Ticket validated.")).toBeTruthy();
    expect(screen.getByText("Memory candidates")).toBeTruthy();
    expect(screen.getByText("Memory candidate from ticket-implement-plane-sync-123abc")).toBeTruthy();
    expect(screen.getByText("Trace: .aiteamos/traces/run-candidate.jsonl")).toBeTruthy();
    expect(screen.getByText("Approved memories used")).toBeTruthy();
    expect(screen.getByText("Approved Memory reused by ticket-implement-plane-sync-123abc")).toBeTruthy();
    expect(screen.getByText("Source: rd-0001")).toBeTruthy();
    expect(await screen.findByText("Evidence Requirements")).toBeTruthy();
    expect(screen.getByText("backend_change")).toBeTruthy();
    expect(screen.getByText("Validation evidence recorded")).toBeTruthy();
    expect(screen.getByText("pytest")).toBeTruthy();
    expect(await screen.findByText("Performance")).toBeTruthy();
    expect(screen.getByText("Quality Signals")).toBeTruthy();
    expect(screen.getByText("Recalled Assets")).toBeTruthy();
    expect(screen.getByText("Contributors")).toBeTruthy();
    expect(screen.getByText("Assignee: yes")).toBeTruthy();
    expect(screen.getByText("Graphiti Recall: yes")).toBeTruthy();
    expect(await screen.findByText("Grouped Edges")).toBeTruthy();
    expect(screen.getByText("ticket.assigned_to.employee")).toBeTruthy();
    expect(screen.getByText("ticket:ticket-implement-plane-sync-123abc -> employee:alex")).toBeTruthy();
  });

  it("renders report view from Ticket reports", async () => {
    render(<TicketsPage selectedSection="reports" />);

    expect(await screen.findByText("Validation passed.")).toBeTruthy();
    expect(screen.getByText("npm test passed")).toBeTruthy();
  });

  it("selects a Ticket when the route segment is a Ticket id", async () => {
    render(<TicketsPage selectedSection="rd-0009" />);

    expect(await screen.findByText("Selected from related Memory asset.")).toBeTruthy();
    expect(screen.getAllByText("rd-0009").length).toBeGreaterThan(0);
  });
});
