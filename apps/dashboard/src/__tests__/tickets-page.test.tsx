import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TicketsPage } from "../pages/tickets";

const tickets = [
  {
    id: "ticket-implement-plane-sync-123abc",
    title: "Implement Plane sync",
    description: "Connect local Tickets to the Plane Ticket Backend boundary.",
    status: "ready_to_resume",
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
    status: "waiting_evidence",
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

const systemStatus = {
  secrets: [],
  ticket_backend: backendStatus,
  memory_backend: {
    backend: "graphiti",
    enabled: true,
    configured: false,
    graph_configured: true,
    llm_configured: true,
    package_installed: true,
    status: "disabled",
    detail: "Graphiti is not enabled.",
    group_id: "aiteamos",
    graph_database: "neo4j",
    uri: "bolt://localhost:7687",
    user: "neo4j",
    llm_ai_engine: "openai",
    llm_ai_engine_name: "ChatGPT / OpenAI API",
    llm_api_key_env: "OPENAI_API_KEY",
    password_configured: false,
    llm_api_key_configured: true,
  },
  runtime_executors: [],
  live_provider_dogfood: {
    status: "blocked",
    profile: "core_loop",
    selected_executor_id: "langgraph",
    require_repo_write_executor: false,
    mutation_gate: {
      open: false,
      confirm_env_var: "AITEAMOS_LIVE_PROVIDER_DOGFOOD",
      confirm_env_configured: false,
    },
    selected_executor_preflight: {
      executor_id: "langgraph",
      status: "passed",
      capabilities: ["answer_only", "create_ticket", "append_report"],
      blockers: [],
    },
    repo_write_executor_candidates: [
      {
        executor_id: "codex_cli",
        display_name: "OpenAI Codex CLI Executor",
        status: "ready",
        detail: "OpenAI Codex CLI Executor is configured.",
        capabilities: ["agent_loop", "repo:read", "repo:write"],
        setup_required: [],
        ready: true,
        health: { status: "ready" },
      },
      {
        executor_id: "claude_code",
        display_name: "Claude Code",
        status: "setup_blocked",
        detail: "Claude Code-compatible Local CLI Executor is not configured.",
        capabilities: ["agent_loop", "repo:read", "repo:write"],
        setup_required: ["CLAUDE_CODE_BIN"],
        ready: false,
        health: { status: "setup_blocked" },
      },
    ],
    provider_prerequisites: {
      ticket_backend: {
        status: "ready",
        provider: "plane",
        detail: "Plane Ticket Backend is active.",
      },
      memory_backend: {
        status: "disabled",
        backend: "graphiti",
        detail: "Graphiti is not enabled.",
      },
      provider_smoke: {
        status: "not_run",
        reason: "readiness is read-only and does not call external provider smoke",
      },
    },
    blockers: [
      {
        reason: "memory_provider_not_ready",
        scope: "memory_backend",
        status: "disabled",
        detail: "Graphiti is not enabled.",
        setup_required: ["Graphiti URI/user"],
      },
      {
        reason: "live_provider_dogfood_not_confirmed",
        scope: "mutation_gate",
        status: "confirmation_required",
        detail: "Set AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 before live Plane / Graphiti writes.",
        setup_required: ["AITEAMOS_LIVE_PROVIDER_DOGFOOD=1"],
      },
    ],
    warnings: [],
    summary: {
      profile: "core_loop",
      blocker_count: 2,
      repo_write_candidate_count: 2,
      repo_write_ready_count: 1,
      ticket_backend_status: "ready",
      memory_backend_status: "disabled",
      anti_wheel_boundary: "readiness reuses RuntimeExecutor health plus Ticket and Graphiti provider status",
    },
  },
  provider_conformance: null,
  schema_registry: null,
  blockers: [],
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

const ticketRuntimeEvidence = {
  ticket_id: "ticket-implement-plane-sync-123abc",
  status: "ready_to_resume",
  source_counts: {
    events: 3,
    reports: 1,
    evidence: 1,
    assets: 2,
    memory_candidates: 1,
    approved_memories: 1,
    graph_nodes: 3,
    graph_edges: 2,
    loop_runs: 2,
    runtime_artifact_runs: 1,
    handoffs: 1,
    approval_resume: 1,
    retry_requirements: 0,
    provider_blockers: 0,
  },
  provider_state: {
    mode: "plane",
    status: "ready",
    provider: "plane",
    provider_ref_recorded: true,
    provider_record_id: "plane-ticket-1",
    provider_project_id: "plane-project-1",
    provider_url: "https://app.plane.test/ait/projects/plane-project-1/work-items/plane-ticket-1",
    external_url: "https://app.plane.test/ait/projects/plane-project-1/work-items/plane-ticket-1",
    synced_at: "2026-06-18T00:00:00Z",
    detail: "Plane Ticket Backend is active.",
    setup_required: [],
  },
  governance_state: {
    timeline_status: "ready_to_resume",
    next_action: "Resume the governed Ticket loop.",
    waiting_reason: "Approval was granted; the Ticket loop can be resumed through the governed queue.",
    can_run: true,
    can_resume: true,
    can_retry: false,
    approval_resume_count: 1,
    retry_requirement_count: 0,
    provider_blocker_count: 0,
    queue_reliability_status: "waiting_worker",
    queue_reliability: {
      status: "waiting_worker",
      detail: "This Ticket has queued loop work but the queue worker is not running.",
    },
  },
  latest_loop_run: {
    run_id: "ticket-loop-run-ticket-implement-plane-sync-123abc-001",
    status: "completed",
    stop_reason: "max_steps_reached",
    active: false,
    session_key: "alex::ticket-loop-ticket-implement-plane-sync-123abc-step-1::ticket-implement-plane-sync-123abc",
    step_count: 1,
    queued_at: "2026-06-18T00:00:00Z",
    started_at: "2026-06-18T00:00:00Z",
    finished_at: "2026-06-18T00:00:01Z",
    updated_at: "2026-06-18T00:00:01Z",
    saved_path: ".aiteamos/ticket_loop_runs.json",
  },
  blockers: [],
  gaps: [
    {
      reason: "queue_reliability_attention",
      detail: "This Ticket has queued loop work but the queue worker is not running.",
      scope: "loop_queue",
      status: "waiting_worker",
    },
  ],
  links: {
    ticket: "tickets/overview/ticket-implement-plane-sync-123abc",
    runtime: "runtime/alex::ticket-loop-ticket-implement-plane-sync-123abc-step-1::ticket-implement-plane-sync-123abc",
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

const closeoutCandidateResponse = {
  ticket_id: "ticket-implement-plane-sync-123abc",
  status: "proposed",
  detail: "Ticket closeout Asset candidates were proposed for review.",
  report_id: "report-closeout-candidates",
  saved_paths: { asset_candidates: ".aiteamos/assets/candidates.json" },
  candidates: [
    {
      id: "asset-candidate-ticket-closeout-ticket-implement-plane-sync-123abc",
      source_candidate_id: "",
      asset_id: "ticket-closeout-ticket-implement-plane-sync-123abc",
      asset_type: "ticket_closeout",
      title: "Ticket closeout: Implement Plane sync",
      content: "Ticket closeout content.",
      content_ref: "ticket://ticket-implement-plane-sync-123abc#closeout",
      status: "proposed",
      scope_kind: "ticket",
      scope_ref: "ticket-implement-plane-sync-123abc",
      owner_employee_id: "alex",
      source_kind: "ticket_closeout",
      source_ref: "tickets/ticket-implement-plane-sync-123abc",
      provenance: { source_ticket_id: "ticket-implement-plane-sync-123abc" },
      provider: "local_file",
      provider_ref: ".aiteamos/assets/candidates.json#asset-candidate-ticket-closeout-ticket-implement-plane-sync-123abc",
      relationships: [{ type: "derived_from_ticket", target_ref: "ticket-implement-plane-sync-123abc" }],
      review_state: "proposed",
      usefulness_stats: {},
      created_at: "2026-06-03T08:45:00Z",
      updated_at: "2026-06-03T08:45:00Z",
    },
    {
      id: "asset-candidate-ticket-solution-ticket-implement-plane-sync-123abc",
      source_candidate_id: "",
      asset_id: "ticket-solution-ticket-implement-plane-sync-123abc",
      asset_type: "solution",
      title: "Validated solution: Implement Plane sync",
      content: "Validated solution content.",
      content_ref: "ticket://ticket-implement-plane-sync-123abc#solution",
      status: "proposed",
      scope_kind: "ticket",
      scope_ref: "ticket-implement-plane-sync-123abc",
      owner_employee_id: "alex",
      source_kind: "ticket_closeout",
      source_ref: "tickets/ticket-implement-plane-sync-123abc",
      provenance: { source_ticket_id: "ticket-implement-plane-sync-123abc" },
      provider: "local_file",
      provider_ref: ".aiteamos/assets/candidates.json#asset-candidate-ticket-solution-ticket-implement-plane-sync-123abc",
      relationships: [{ type: "derived_from_ticket", target_ref: "ticket-implement-plane-sync-123abc" }],
      review_state: "proposed",
      usefulness_stats: {},
      created_at: "2026-06-03T08:45:00Z",
      updated_at: "2026-06-03T08:45:00Z",
    },
    {
      id: "asset-candidate-ticket-validation-ticket-implement-plane-sync-123abc",
      source_candidate_id: "",
      asset_id: "ticket-validation-ticket-implement-plane-sync-123abc",
      asset_type: "validation_result",
      title: "Validation result: Implement Plane sync",
      content: "Validation result content.",
      content_ref: "ticket://ticket-implement-plane-sync-123abc#validation",
      status: "proposed",
      scope_kind: "ticket",
      scope_ref: "ticket-implement-plane-sync-123abc",
      owner_employee_id: "peter",
      source_kind: "ticket_closeout",
      source_ref: "tickets/ticket-implement-plane-sync-123abc",
      provenance: { source_ticket_id: "ticket-implement-plane-sync-123abc" },
      provider: "local_file",
      provider_ref: ".aiteamos/assets/candidates.json#asset-candidate-ticket-validation-ticket-implement-plane-sync-123abc",
      relationships: [{ type: "derived_from_ticket", target_ref: "ticket-implement-plane-sync-123abc" }],
      review_state: "proposed",
      usefulness_stats: {},
      created_at: "2026-06-03T08:45:00Z",
      updated_at: "2026-06-03T08:45:00Z",
    },
  ],
};

const closeoutSettlementResponse = {
  ticket_id: "ticket-implement-plane-sync-123abc",
  status: "blocked",
  detail: "Ticket closeout settlement hit one or more provider blockers.",
  proposal: closeoutCandidateResponse,
  review: {
    status: "completed",
    requested_count: 3,
    reviewed_count: 3,
    failed_count: 0,
    results: [],
    saved_paths: {
      asset_candidates: ".aiteamos/assets/candidates.json",
      asset_records: ".aiteamos/assets/index.json",
      asset_reviews: ".aiteamos/assets/reviews.json",
    },
  },
  candidates: closeoutCandidateResponse.candidates.map((candidate) => ({
    ...candidate,
    status: "approved",
    review_state: "approved",
  })),
  asset_ids: [
    "ticket-closeout-ticket-implement-plane-sync-123abc",
    "ticket-solution-ticket-implement-plane-sync-123abc",
    "ticket-validation-ticket-implement-plane-sync-123abc",
  ],
  projections: [
    {
      asset_id: "ticket-closeout-ticket-implement-plane-sync-123abc",
      status: "ingested",
      projection: { status: "ingested", ingested_asset: { episode_id: "episode-ticket-closeout" } },
      relationship_projection: null,
      error: "",
    },
    {
      asset_id: "ticket-solution-ticket-implement-plane-sync-123abc",
      status: "blocked",
      projection: null,
      relationship_projection: null,
      error: "Graphiti provider is not configured.",
    },
    {
      asset_id: "ticket-validation-ticket-implement-plane-sync-123abc",
      status: "skipped",
      projection: { status: "skipped", ingested_asset: null },
      relationship_projection: null,
      error: "",
    },
  ],
  report_id: "report-closeout-settlement",
  saved_paths: {
    asset_candidates: ".aiteamos/assets/candidates.json",
    asset_records: ".aiteamos/assets/index.json",
    asset_reviews: ".aiteamos/assets/reviews.json",
    graphiti_state: ".aiteamos/memory/graphiti_state.json",
  },
};

const failureRetrospectiveCandidateResponse = {
  ticket_id: "ticket-implement-plane-sync-123abc",
  status: "proposed",
  detail: "Ticket loop failure retrospective Asset candidate was proposed for review.",
  report_id: "report-failure-retrospective",
  failed_item_count: 2,
  saved_paths: { asset_candidates: ".aiteamos/assets/candidates.json" },
  candidates: [
    {
      id: "asset-candidate-ticket-loop-failure-retrospective-ticket-implement-plane-sync-123abc",
      source_candidate_id: "",
      asset_id: "ticket-loop-failure-retrospective-ticket-implement-plane-sync-123abc",
      asset_type: "failure_retrospective",
      title: "Failure retrospective: Implement Plane sync",
      content: "Repeated loop queue failures should be reviewed.",
      content_ref: "ticket://ticket-implement-plane-sync-123abc#loop-failure-retrospective",
      status: "proposed",
      scope_kind: "ticket",
      scope_ref: "ticket-implement-plane-sync-123abc",
      owner_employee_id: "alex",
      source_kind: "ticket_loop_failure_retrospective",
      source_ref: "tickets/ticket-implement-plane-sync-123abc/loop/queue",
      provenance: { source_ticket_id: "ticket-implement-plane-sync-123abc", failed_item_count: 2 },
      provider: "local_file",
      provider_ref: ".aiteamos/assets/candidates.json#asset-candidate-ticket-loop-failure-retrospective-ticket-implement-plane-sync-123abc",
      relationships: [{ type: "derived_from_ticket", target_ref: "ticket-implement-plane-sync-123abc" }],
      review_state: "proposed",
      usefulness_stats: {},
      created_at: "2026-06-18T00:05:00Z",
      updated_at: "2026-06-18T00:05:00Z",
    },
  ],
};

const loopRunResponse = {
  ticket_id: "ticket-implement-plane-sync-123abc",
  status: "completed",
  stop_reason: "max_steps_reached",
  steps: [
    {
      ticket_id: "ticket-implement-plane-sync-123abc",
      status: "completed",
      stop_reason: "single_step_completed",
      request: {
        ticket_id: "ticket-implement-plane-sync-123abc",
        employee_id: "alex",
      },
      result: {
        executor_id: "universal_employee_agent",
        status: "completed",
      },
      ingested: true,
      ingestion_blocker: "",
      loop_state: {
        step_count: 1,
        max_steps: 1,
      },
    },
  ],
  loop_state: {
    step_count: 1,
    max_steps: 2,
  },
};

const loopRunRecords = [
  {
    run_id: "ticket-loop-run-ticket-implement-plane-sync-123abc-queued",
    ticket_id: "ticket-implement-plane-sync-123abc",
    status: "queued",
    stop_reason: "",
    active: true,
    session_key: "",
    request: { max_steps: 2 },
    response: {},
    step_count: 0,
    policy: { max_steps: 3 },
    control: {},
    queued_at: "2026-06-18T00:01:00Z",
    started_at: "",
    finished_at: "",
    updated_at: "2026-06-18T00:01:00Z",
    saved_path: ".aiteamos/ticket_loop_runs.json",
  },
  {
    run_id: "ticket-loop-run-ticket-implement-plane-sync-123abc-001",
    ticket_id: "ticket-implement-plane-sync-123abc",
    status: "completed",
    stop_reason: "max_steps_reached",
    active: false,
    session_key: "alex::ticket-loop-ticket-implement-plane-sync-123abc-step-1::ticket-implement-plane-sync-123abc",
    request: { max_steps: 2 },
    response: loopRunResponse,
    step_count: 1,
    policy: { max_steps: 3 },
    control: {},
    queued_at: "2026-06-18T00:00:00Z",
    started_at: "2026-06-18T00:00:00Z",
    finished_at: "2026-06-18T00:00:01Z",
    updated_at: "2026-06-18T00:00:01Z",
    saved_path: ".aiteamos/ticket_loop_runs.json",
  },
];

const ticketLoopTimeline = {
  ticket_id: "ticket-implement-plane-sync-123abc",
  summary: {
    ticket_id: "ticket-implement-plane-sync-123abc",
    status: "ready_to_resume",
    waiting_reason: "Approval was granted; the Ticket loop can be resumed through the governed queue.",
    next_action: "Resume the governed Ticket loop.",
    can_run: true,
    can_resume: true,
    can_retry: false,
    latest_at: "2026-06-18T00:02:00Z",
    counts: {
      approval: 1,
      ticket_event: 2,
      ticket_report: 1,
      runtime_session: 1,
      loop_run: 2,
      loop_queue: 1,
      asset: 2,
    },
    provider_blockers: [],
    retry_requirements: [],
    approval_resume: [
      {
        approval_id: "approval-ticket-implement-plane-sync-1",
        executor_id: "claude_code",
        status: "approved",
        required_capability: "repo:write",
        ready_to_run: true,
        needs_review: false,
        blocked: false,
        reviewed_at: "2026-06-18T00:02:00Z",
        last_run_request_id: "",
        last_run_status: "",
        last_ingestion_blocker: "",
        attempt_count: 0,
        target_route: "assets/review/runtime-approval:claude_code:approval-ticket-implement-plane-sync-1",
        detail: "Runtime approval is ready to run from the approval review surface.",
      },
    ],
    queue_reliability: {
      ticket_id: "ticket-implement-plane-sync-123abc",
      status: "waiting_worker",
      detail: "This Ticket has queued loop work but the queue worker is not running.",
      queued_count: 1,
      duplicate_queued_count: 0,
      running_count: 0,
      stale_running_count: 0,
      stale_running_after_seconds: 900,
      completed_count: 1,
      failed_count: 0,
      active_count: 1,
      total_count: 2,
      latest_activity_at: "2026-06-18T00:01:00Z",
      worker_status: "stopped",
      worker_running: false,
      worker_last_error: "",
    },
  },
  items: [
    {
      timeline_id: "approval:approval-ticket-implement-plane-sync-1",
      ticket_id: "ticket-implement-plane-sync-123abc",
      kind: "approval",
      status: "approved",
      title: "Runtime approval approved",
      detail: "Approved for governed resume.",
      at: "2026-06-18T00:02:00Z",
      actor_employee_id: "clara",
      actor_role: "AI Team OS Manager",
      source_kind: "execution_approval",
      source_ref: "approval-ticket-implement-plane-sync-1",
      target_route: "assets/review/runtime-approval:claude_code:approval-ticket-implement-plane-sync-1",
      refs: [{ kind: "checkpoint", ref: "langgraph:approval-ticket-implement-plane-sync-1", target_route: "" }],
      data: {},
    },
    {
      timeline_id: "runtime_session:alex::ticket-loop-ticket-implement-plane-sync-123abc::ticket-implement-plane-sync-123abc",
      ticket_id: "ticket-implement-plane-sync-123abc",
      kind: "runtime_session",
      status: "needs_approval",
      title: "Runtime session needs_approval",
      detail: "ticket-loop-run-ticket-implement-plane-sync-123abc-001",
      at: "2026-06-18T00:01:00Z",
      actor_employee_id: "alex",
      actor_role: "",
      source_kind: "execution_session",
      source_ref: "alex::ticket-loop-ticket-implement-plane-sync-123abc::ticket-implement-plane-sync-123abc",
      target_route: "runtime/alex::ticket-loop-ticket-implement-plane-sync-123abc::ticket-implement-plane-sync-123abc",
      refs: [{ kind: "trace", ref: ".aiteamos/traces/ticket-loop.jsonl", target_route: "" }],
      data: {},
    },
    {
      timeline_id: "asset:mem-candidate-1:candidate",
      ticket_id: "ticket-implement-plane-sync-123abc",
      kind: "asset",
      status: "proposed",
      title: "Memory candidate from ticket-implement-plane-sync-123abc",
      detail: "memory_candidate",
      at: "2026-06-03T08:10:00Z",
      actor_employee_id: "clara",
      actor_role: "",
      source_kind: "asset",
      source_ref: "mem-candidate-1:candidate",
      target_route: "assets/asset/mem-candidate-1:candidate",
      refs: [{ kind: "asset", ref: "mem-candidate-1:candidate", target_route: "assets/asset/mem-candidate-1:candidate" }],
      data: {},
    },
    {
      timeline_id: "report:report-1",
      ticket_id: "ticket-implement-plane-sync-123abc",
      kind: "ticket_report",
      status: "validation",
      title: "Report: validation",
      detail: "Validation passed.",
      at: "2026-06-03T08:30:00Z",
      actor_employee_id: "peter",
      actor_role: "AI PV",
      source_kind: "ticket_report",
      source_ref: "report-1",
      target_route: "tickets/reports/ticket-implement-plane-sync-123abc::report::report-1",
      refs: [{ kind: "evidence", ref: "npm test passed", target_route: "tickets/reports/ticket-implement-plane-sync-123abc::evidence::report-1::0" }],
      data: {},
    },
  ],
  saved_paths: {
    loop_runs: ".aiteamos/ticket_loop_runs.json",
    loop_queue: ".aiteamos/ticket_loop_queue.json",
    loop_controls: ".aiteamos/ticket_loop_controls.json",
  },
};

const failureRetrospectiveTimeline = {
  ...ticketLoopTimeline,
  summary: {
    ...ticketLoopTimeline.summary,
    queue_reliability: {
      ...ticketLoopTimeline.summary.queue_reliability,
      status: "error",
      detail: "At least one queued loop item failed.",
      queued_count: 0,
      failed_count: 2,
      active_count: 0,
      total_count: 2,
    },
  },
};

let activeTicketLoopTimeline = ticketLoopTimeline;

const waitingEvidenceTimeline = {
  ticket_id: "rd-0009",
  summary: {
    ticket_id: "rd-0009",
    status: "waiting_evidence",
    waiting_reason: "A reviewer requested more evidence before this Ticket loop can retry.",
    next_action: "Attach evidence, then retry the governed Ticket loop.",
    can_run: true,
    can_resume: true,
    can_retry: true,
    latest_at: "2026-06-18T00:04:00Z",
    counts: {
      approval: 1,
      ticket_report: 1,
    },
    provider_blockers: [],
    retry_requirements: [
      {
        id: "latest_evidence_requested_review",
        label: "Review recorded",
        satisfied: true,
        detail: "Latest runtime approval review status: evidence_requested.",
        target_route: "assets/review/runtime-approval:claude_code:approval-rd-0009-1",
      },
      {
        id: "new_evidence_after_review",
        label: "New evidence after review",
        satisfied: false,
        detail: "A non-approval Ticket evidence ref was attached after the reviewer requested more evidence.",
        target_route: "tickets/reports/rd-0009",
      },
    ],
    approval_resume: [
      {
        approval_id: "approval-rd-0009-1",
        executor_id: "claude_code",
        status: "evidence_requested",
        required_capability: "repo:write",
        ready_to_run: false,
        needs_review: false,
        blocked: false,
        reviewed_at: "2026-06-18T00:04:00Z",
        last_run_request_id: "",
        last_run_status: "",
        last_ingestion_blocker: "",
        attempt_count: 0,
        target_route: "assets/review/runtime-approval:claude_code:approval-rd-0009-1",
        detail: "Runtime approval review status is evidence_requested; follow the Ticket next action before runtime resume.",
      },
    ],
    queue_reliability: {
      ticket_id: "rd-0009",
      status: "idle",
      detail: "No queued loop work is currently attached to this Ticket.",
      queued_count: 0,
      duplicate_queued_count: 0,
      running_count: 0,
      stale_running_count: 0,
      stale_running_after_seconds: 900,
      completed_count: 0,
      failed_count: 0,
      active_count: 0,
      total_count: 0,
      latest_activity_at: "",
      worker_status: "stopped",
      worker_running: false,
      worker_last_error: "",
    },
  },
  items: [
    {
      timeline_id: "approval:approval-rd-0009-1",
      ticket_id: "rd-0009",
      kind: "approval",
      status: "evidence_requested",
      title: "Runtime approval evidence_requested",
      detail: "Attach more evidence.",
      at: "2026-06-18T00:04:00Z",
      actor_employee_id: "clara",
      actor_role: "AI Team OS Manager",
      source_kind: "execution_approval",
      source_ref: "approval-rd-0009-1",
      target_route: "assets/review/runtime-approval:claude_code:approval-rd-0009-1",
      refs: [],
      data: {},
    },
  ],
  saved_paths: {
    loop_runs: ".aiteamos/ticket_loop_runs.json",
    loop_queue: ".aiteamos/ticket_loop_queue.json",
    loop_controls: ".aiteamos/ticket_loop_controls.json",
  },
};

const ticketLoopResumeResponse = {
  ticket_id: "ticket-implement-plane-sync-123abc",
  status: "in_progress",
  previous_status: "ready_to_resume",
  detail: "Ticket loop resume queued from ready_to_resume status.",
  queue_item: {
    queue_id: "ticket-loop-queue-ticket-implement-plane-sync-123abc-resume",
    run_id: "ticket-loop-run-ticket-implement-plane-sync-123abc-resume",
    ticket_id: "ticket-implement-plane-sync-123abc",
    status: "queued",
    priority: 50,
    request: { max_steps: 2 },
    response: {},
    error: "",
    actor_employee_id: "clara",
    actor_role: "AI Team OS Manager",
    reason: "Dashboard requested governed Ticket loop resume.",
    report_id: "report-loop-resume",
    enqueued_at: "2026-06-18T00:03:00Z",
    started_at: "",
    finished_at: "",
    updated_at: "2026-06-18T00:03:00Z",
    saved_path: ".aiteamos/ticket_loop_queue.json",
  },
  saved_paths: {
    loop_queue: ".aiteamos/ticket_loop_queue.json",
    loop_runs: ".aiteamos/ticket_loop_runs.json",
  },
};

const loopQueueStatus = {
  status: "queued",
  queued_count: 1,
  running_count: 0,
  completed_count: 1,
  failed_count: 0,
  active_count: 1,
  total_count: 2,
  oldest_queued_at: "2026-06-18T00:01:00Z",
  latest_activity_at: "2026-06-18T00:01:00Z",
  next_queue_id: "ticket-loop-queue-ticket-implement-plane-sync-123abc-queued",
  next_ticket_id: "ticket-implement-plane-sync-123abc",
  next_run_id: "ticket-loop-run-ticket-implement-plane-sync-123abc-queued",
  saved_paths: {
    loop_queue: ".aiteamos/ticket_loop_queue.json",
    loop_runs: ".aiteamos/ticket_loop_runs.json",
  },
};

const loopQueuePumpResponse = {
  status: "completed",
  processed: [
    {
      queue_id: "ticket-loop-queue-ticket-implement-plane-sync-123abc-queued",
      run_id: "ticket-loop-run-ticket-implement-plane-sync-123abc-queued",
      ticket_id: "ticket-implement-plane-sync-123abc",
      status: "completed",
    },
  ],
  policy_actions: [],
  remaining_queued: 0,
  saved_paths: {
    loop_queue: ".aiteamos/ticket_loop_queue.json",
  },
};

const loopQueueItems = [
  {
    queue_id: "ticket-loop-queue-ticket-implement-plane-sync-123abc-queued",
    run_id: "ticket-loop-run-ticket-implement-plane-sync-123abc-queued",
    ticket_id: "ticket-implement-plane-sync-123abc",
    status: "queued",
    priority: 10,
    request: { max_steps: 2 },
    response: {},
    error: "",
    actor_employee_id: "clara",
    actor_role: "AI Team OS Manager",
    reason: "Queue this Ticket loop from Clara.",
    report_id: "report-loop-queued",
    enqueued_at: "2026-06-18T00:01:00Z",
    started_at: "",
    finished_at: "",
    updated_at: "2026-06-18T00:01:00Z",
    saved_path: ".aiteamos/ticket_loop_queue.json",
  },
  {
    queue_id: "ticket-loop-queue-ticket-implement-plane-sync-123abc-done",
    run_id: "ticket-loop-run-ticket-implement-plane-sync-123abc-001",
    ticket_id: "ticket-implement-plane-sync-123abc",
    status: "completed",
    priority: 100,
    request: { max_steps: 1 },
    response: loopRunResponse,
    error: "",
    actor_employee_id: "clara",
    actor_role: "AI Team OS Manager",
    reason: "Completed queue item.",
    report_id: "report-loop-queued-done",
    enqueued_at: "2026-06-18T00:00:00Z",
    started_at: "2026-06-18T00:00:00Z",
    finished_at: "2026-06-18T00:00:01Z",
    updated_at: "2026-06-18T00:00:01Z",
    saved_path: ".aiteamos/ticket_loop_queue.json",
  },
];

const loopQueueWorkerStatus = {
  worker_id: "ticket-loop-queue-worker",
  status: "stopped",
  running: false,
  interval_seconds: 5,
  max_items: 1,
  started_at: "",
  stopped_at: "2026-06-18T00:02:00Z",
  last_tick_at: "2026-06-18T00:01:00Z",
  last_tick_status: "idle",
  last_error: "",
  total_ticks: 2,
  total_processed: 1,
  total_policy_actions: 1,
  recent_policy_actions: [
    {
      kind: "failure_retrospective_candidate",
      ticket_id: "ticket-implement-plane-sync-123abc",
      status: "proposed",
      detail: "Ticket loop failure retrospective Asset candidate was proposed for review.",
      candidate_ids: ["asset-candidate-ticket-loop-failure-retrospective-ticket-implement-plane-sync-123abc"],
      report_id: "report-failure-retrospective",
    },
  ],
  last_control_reason: "Worker stopped.",
  saved_path: ".aiteamos/ticket_loop_queue_worker.json",
};

const loopQueueWorkerTickResponse = {
  status: {
    ...loopQueueWorkerStatus,
    status: "completed",
    last_tick_status: "completed",
    total_ticks: 3,
    total_processed: 2,
    last_control_reason: "Dashboard requested a governed Ticket loop queue worker tick.",
  },
  pump: loopQueuePumpResponse,
};

function loopControlResponse(action: "stop" | "pause" | "continue" | "cancel") {
  const statusByAction = {
    cancel: "cancelled",
    continue: "ready_to_continue",
    pause: "paused",
    stop: "stopped",
  };
  return {
    ticket_id: "ticket-implement-plane-sync-123abc",
    state: {
      control_id: `ticket-loop-control-ticket-implement-plane-sync-123abc-${action}`,
      ticket_id: "ticket-implement-plane-sync-123abc",
      action,
      status: statusByAction[action],
      active: action !== "continue",
      actor_employee_id: "clara",
      actor_role: "AI Team OS Manager",
      reason: `Dashboard requested a governed Ticket loop ${action}.`,
      session_key: "",
      updated_session_count: 1,
      updated_at: "2026-06-18T00:00:00Z",
      saved_path: ".aiteamos/ticket_loop_controls.json",
    },
    report_id: `report-loop-control-${action}`,
    updated_sessions: [
      {
        session_key: "alex::ticket-loop-ticket-implement-plane-sync-123abc-step-1::ticket-implement-plane-sync-123abc",
        status: statusByAction[action],
      },
    ],
    saved_paths: {
      loop_controls: ".aiteamos/ticket_loop_controls.json",
    },
  };
}

describe("TicketsPage", () => {
  beforeEach(() => {
    window.location.hash = "";
    activeTicketLoopTimeline = ticketLoopTimeline;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/system-status")) {
          return new Response(JSON.stringify(systemStatus), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/tickets/self-bootstrap/summary")) {
          return new Response(JSON.stringify(selfBootstrapSummary), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/tickets/ticket-implement-plane-sync-123abc/closeout-candidates")) {
          return new Response(JSON.stringify(closeoutCandidateResponse), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/tickets/ticket-implement-plane-sync-123abc/closeout-settlement")) {
          return new Response(JSON.stringify(closeoutSettlementResponse), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/tickets/ticket-implement-plane-sync-123abc/failure-retrospective-candidates")) {
          return new Response(JSON.stringify(failureRetrospectiveCandidateResponse), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/tickets/ticket-implement-plane-sync-123abc/loop/run")) {
          return new Response(JSON.stringify(loopRunResponse), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/tickets/ticket-implement-plane-sync-123abc/loop/resume")) {
          return new Response(JSON.stringify(ticketLoopResumeResponse), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/tickets/ticket-implement-plane-sync-123abc/loop/timeline")) {
          return new Response(JSON.stringify(activeTicketLoopTimeline), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/tickets/rd-0009/loop/timeline")) {
          return new Response(JSON.stringify(waitingEvidenceTimeline), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/tickets/rd-0009/loop/runs")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/tickets/ticket-implement-plane-sync-123abc/loop/runs/ticket-loop-run-ticket-implement-plane-sync-123abc-001")) {
          return new Response(JSON.stringify(loopRunRecords[1]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/tickets/ticket-implement-plane-sync-123abc/loop/runs")) {
          return new Response(JSON.stringify(loopRunRecords), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/tickets/loop/queue/status")) {
          return new Response(JSON.stringify(loopQueueStatus), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/tickets/loop/queue/worker/status")) {
          return new Response(JSON.stringify(loopQueueWorkerStatus), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/tickets/loop/queue/worker/start")) {
          return new Response(JSON.stringify({ ...loopQueueWorkerStatus, status: "running", running: true }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/tickets/loop/queue/worker/stop")) {
          return new Response(JSON.stringify(loopQueueWorkerStatus), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/tickets/loop/queue/worker/tick")) {
          return new Response(JSON.stringify(loopQueueWorkerTickResponse), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/tickets/loop/queue/pump")) {
          return new Response(JSON.stringify(loopQueuePumpResponse), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/tickets/loop/queue")) {
          return new Response(JSON.stringify(loopQueueItems), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/tickets/ticket-implement-plane-sync-123abc/loop/control")) {
          const body = typeof init?.body === "string" ? init.body : "";
          const action = body.includes("\"action\":\"pause\"")
            ? "pause"
            : body.includes("\"action\":\"continue\"")
              ? "continue"
              : body.includes("\"action\":\"cancel\"")
                ? "cancel"
                : "stop";
          return new Response(JSON.stringify(loopControlResponse(action)), {
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
        if (url.includes("/tickets/") && url.endsWith("/runtime-evidence")) {
          return new Response(JSON.stringify(ticketRuntimeEvidence), {
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
    cleanup();
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
    expect(screen.getAllByText("Ticket Backend").length).toBeGreaterThan(0);
    expect(screen.getAllByText("plane").length).toBeGreaterThan(0);
    expect(screen.getByText("Projection mirror")).toBeTruthy();
    window.location.hash = "";
    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    expect(window.location.hash).toBe("#/settings/ticket-backend");
    expect(screen.getByText("Live Provider Loop")).toBeTruthy();
    expect(screen.getByText("core_loop")).toBeTruthy();
    expect(screen.getByText("repo:write optional")).toBeTruthy();
    expect(screen.getByText("1/2 repo-write ready")).toBeTruthy();
    expect(screen.getByText("gate closed")).toBeTruthy();
    expect(screen.getByText("Ticket provider")).toBeTruthy();
    expect(screen.getByText("Memory provider")).toBeTruthy();
    expect(screen.getByText("Provider smoke")).toBeTruthy();
    expect(screen.getByText("Live Blockers")).toBeTruthy();
    expect(screen.getByText("memory provider not ready")).toBeTruthy();
    expect(screen.getByText("live provider dogfood not confirmed")).toBeTruthy();
    expect(screen.getByText("AITEAMOS_LIVE_PROVIDER_DOGFOOD=1")).toBeTruthy();
    expect(screen.getByText("OpenAI Codex CLI Executor")).toBeTruthy();
    window.location.hash = "";
    fireEvent.click(screen.getByRole("button", { name: "Ticket Backend" }));
    expect(window.location.hash).toBe("#/settings/ticket-backend");
    window.location.hash = "";
    fireEvent.click(screen.getByRole("button", { name: "Memory Backend" }));
    expect(window.location.hash).toBe("#/settings/memory-backend");
    expect(screen.getByRole("button", { name: "System Status" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Runtime Replay" })).toBeTruthy();
    expect(screen.getByText("Self-Bootstrap")).toBeTruthy();
    expect(screen.getByText(selfBootstrapSummary.summary)).toBeTruthy();
    expect(screen.getByText("Graphiti recall: 1")).toBeTruthy();
    expect(screen.getByText("Needs evidence")).toBeTruthy();
    expect(screen.getByText("rd-0009")).toBeTruthy();
    expect(screen.getByText("Attach validation evidence before marking this Ticket validated.")).toBeTruthy();
    expect(screen.getByText("Memory candidates")).toBeTruthy();
    expect(screen.getAllByText("Memory candidate from ticket-implement-plane-sync-123abc").length).toBeGreaterThan(0);
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
    expect(await screen.findByText("Runtime Evidence")).toBeTruthy();
    expect(screen.getByText("Latest run: completed")).toBeTruthy();
    expect(screen.getByText("Provider: plane ready")).toBeTruthy();
    expect(screen.getByText("Queue waiting_worker")).toBeTruthy();
    expect(screen.getByText("Runtime Gaps")).toBeTruthy();
    expect(screen.getByText("queue reliability attention")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Latest Replay" })).toBeTruthy();
    expect(await screen.findByText("Loop Runs")).toBeTruthy();
    expect(screen.getByText("Loop Queue")).toBeTruthy();
    expect(screen.getAllByText("ticket-loop-run-ticket-implement-plane-sync-123abc-queued").length).toBeGreaterThan(0);
    expect(screen.getByText("ticket-loop-run-ticket-implement-plane-sync-123abc-001")).toBeTruthy();
    expect(screen.getByText("2 recorded")).toBeTruthy();
    expect(screen.getByText("Timeline Next Action")).toBeTruthy();
    expect(screen.getAllByText("Resume the governed Ticket loop.").length).toBeGreaterThan(0);
    expect(screen.getByText("Approval was granted; the Ticket loop can be resumed through the governed queue.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Resume Loop" })).toBeTruthy();
    expect(screen.getAllByText("queued").length).toBeGreaterThan(0);
    expect(screen.getByText("1 active")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Pump Queue" })).toBeTruthy();
    expect(screen.getByText("max_steps_reached")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Continue Loop" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Pause Loop" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Stop Loop" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Cancel Loop" })).toBeTruthy();
    expect(screen.getByText("Assignee: yes")).toBeTruthy();
    expect(screen.getByText("Graphiti Recall: yes")).toBeTruthy();
    expect(await screen.findByText("Grouped Edges")).toBeTruthy();
    expect(screen.getByText("ticket.assigned_to.employee")).toBeTruthy();
    expect(screen.getByText("ticket:ticket-implement-plane-sync-123abc -> employee:alex")).toBeTruthy();
  });

  it("renders the Ticket team timeline projection", async () => {
    render(<TicketsPage selectedSection="flow/ticket-implement-plane-sync-123abc" />);

    expect(await screen.findByText("Team Timeline")).toBeTruthy();
    expect(screen.getByText("Runtime approval approved")).toBeTruthy();
    expect(screen.getByText("Runtime session needs_approval")).toBeTruthy();
    expect(screen.getAllByText("Memory candidate from ticket-implement-plane-sync-123abc").length).toBeGreaterThan(0);
    expect(screen.getByText("Report: validation")).toBeTruthy();
    expect(screen.getByText("Approval: 1")).toBeTruthy();
    expect(screen.getByText("Runtime: 1")).toBeTruthy();
    expect(screen.getByText("checkpoint: langgraph:approval-ticket-implement-plane-sync-1")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Open Report" }));
    expect(window.location.hash).toBe("#/tickets/reports/ticket-implement-plane-sync-123abc%3A%3Areport%3A%3Areport-1");

    fireEvent.click(screen.getByRole("button", { name: "evidence: npm test passed" }));
    expect(window.location.hash).toBe("#/tickets/reports/ticket-implement-plane-sync-123abc%3A%3Aevidence%3A%3Areport-1%3A%3A0");

    fireEvent.click(screen.getByRole("button", { name: "Open Approval" }));
    expect(window.location.hash).toBe("#/assets/review/runtime-approval%3Aclaude_code%3Aapproval-ticket-implement-plane-sync-1");

    fireEvent.click(screen.getByRole("button", { name: "Open Runtime" }));
    expect(window.location.hash).toBe("#/runtime/alex%3A%3Aticket-loop-ticket-implement-plane-sync-123abc%3A%3Aticket-implement-plane-sync-123abc");

    fireEvent.click(screen.getByRole("button", { name: "Open Asset" }));
    expect(window.location.hash).toBe("#/assets/asset/mem-candidate-1%3Acandidate");
  });

  it("opens Ticket reports with focused evidence from timeline routes", async () => {
    render(<TicketsPage selectedSection="reports/ticket-implement-plane-sync-123abc::evidence::report-1::0" />);

    expect(await screen.findByText("Ticket Cockpit")).toBeTruthy();
    expect(screen.getByText("Validation passed.")).toBeTruthy();
    expect(screen.getByText("selected")).toBeTruthy();
    expect(screen.getByText("npm test passed")).toBeTruthy();
  });

  it("shows runtime approval resume visibility and queue reliability in Ticket detail", async () => {
    render(<TicketsPage selectedSection="overview/ticket-implement-plane-sync-123abc" />);

    expect(await screen.findByText("Runtime Approval Resume")).toBeTruthy();
    expect(screen.getByText("approval-ticket-implement-plane-sync-1")).toBeTruthy();
    expect(screen.getByText("Runtime approval is ready to run from the approval review surface.")).toBeTruthy();
    expect(screen.getByText("Queue Reliability")).toBeTruthy();
    expect(screen.getByText("waiting_worker")).toBeTruthy();
    expect(screen.getByText("Worker stopped")).toBeTruthy();
    expect(screen.getByText("This Ticket has queued loop work but the queue worker is not running.")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Open Approval" }));
    expect(window.location.hash).toBe("#/assets/review/runtime-approval%3Aclaude_code%3Aapproval-ticket-implement-plane-sync-1");
  });

  it("renders retry preflight requirements before retrying waiting evidence Tickets", async () => {
    render(<TicketsPage selectedSection="overview/rd-0009" />);

    expect(await screen.findByText("Retry Preflight")).toBeTruthy();
    expect(screen.getByText("1/2")).toBeTruthy();
    expect(screen.getByText("Review recorded")).toBeTruthy();
    expect(screen.getByText("New evidence after review")).toBeTruthy();
    expect(screen.getByText("needed")).toBeTruthy();

    const openButtons = screen.getAllByRole("button", { name: "Open" });
    fireEvent.click(openButtons[0]);
    expect(window.location.hash).toBe("#/assets/review/runtime-approval%3Aclaude_code%3Aapproval-rd-0009-1");
    fireEvent.click(openButtons[1]);
    expect(window.location.hash).toBe("#/tickets/reports/rd-0009");
  });

  it("can resume a ready Ticket loop from the Ticket detail", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<TicketsPage selectedSection="tickets" />);

    expect(await screen.findByText("Ticket Cockpit")).toBeTruthy();
    expect(await screen.findByText("Timeline Next Action")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Resume Loop" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/tickets/ticket-implement-plane-sync-123abc/loop/resume",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("\"action\":\"resume\""),
        }),
      );
    });
    expect(await screen.findByText("Loop Resume")).toBeTruthy();
    expect(screen.getByText("Ticket loop resume queued from ready_to_resume status.")).toBeTruthy();
    expect(screen.getByText("Queued ticket-loop-run-ticket-implement-plane-sync-123abc-resume")).toBeTruthy();
  });

  it("can propose Ticket closeout Asset candidates from the Ticket detail", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<TicketsPage selectedSection="tickets" />);

    expect(await screen.findByText("Ticket Cockpit")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Closeout Assets" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/tickets/ticket-implement-plane-sync-123abc/closeout-candidates",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("Dashboard Ticket detail closeout proposal"),
        }),
      );
    });
    expect(await screen.findByText("Ticket closeout Asset candidates were proposed for review.")).toBeTruthy();
    expect(screen.getByText("ticket_closeout")).toBeTruthy();
    expect(screen.getByText("solution")).toBeTruthy();
    expect(screen.getByText("validation_result")).toBeTruthy();
    expect(screen.getByText("Report report-closeout-candidates")).toBeTruthy();
  });

  it("can settle Ticket closeout Assets and surface Graphiti blockers", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<TicketsPage selectedSection="tickets" />);

    expect(await screen.findByText("Ticket Cockpit")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Settle Closeout" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/tickets/ticket-implement-plane-sync-123abc/closeout-settlement",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("\"approve_candidates\":true"),
        }),
      );
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/tickets/ticket-implement-plane-sync-123abc/closeout-settlement",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("\"project_graphiti\":true"),
        }),
      );
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/tickets/ticket-implement-plane-sync-123abc/closeout-settlement",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("\"project_relationships\":true"),
        }),
      );
    });
    expect(await screen.findByText("Closeout Settlement")).toBeTruthy();
    expect(screen.getByText("Ticket closeout settlement hit one or more provider blockers.")).toBeTruthy();
    expect(screen.getByText("Reviewed 3/3")).toBeTruthy();
    expect(screen.getByText("3 AssetRecords")).toBeTruthy();
    expect(screen.getByText("3 Graphiti projections")).toBeTruthy();
    expect(screen.getByText("Report report-closeout-settlement")).toBeTruthy();
    expect(screen.getAllByText("ticket-solution-ticket-implement-plane-sync-123abc").length).toBeGreaterThan(0);
    expect(screen.getByText("Graphiti provider is not configured.")).toBeTruthy();
    expect(screen.getByText("Graphiti .aiteamos/memory/graphiti_state.json")).toBeTruthy();
  });

  it("can propose failure retrospective Asset candidates from queue reliability", async () => {
    activeTicketLoopTimeline = failureRetrospectiveTimeline;
    const fetchMock = vi.mocked(fetch);
    render(<TicketsPage selectedSection="overview/ticket-implement-plane-sync-123abc" />);

    expect(await screen.findByText("Queue Reliability")).toBeTruthy();
    expect(screen.getByText("error")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Failure Retrospective" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/tickets/ticket-implement-plane-sync-123abc/failure-retrospective-candidates",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("Dashboard Ticket queue reliability failure retrospective proposal"),
        }),
      );
    });
    expect(await screen.findByText("Ticket loop failure retrospective Asset candidate was proposed for review.")).toBeTruthy();
    expect(screen.getByText("2 failed items")).toBeTruthy();
    expect(screen.getByText("failure_retrospective")).toBeTruthy();
    expect(screen.getByText("Report report-failure-retrospective")).toBeTruthy();
  });

  it("can run a bounded Ticket-native autonomous loop from the Ticket detail", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<TicketsPage selectedSection="tickets" />);

    expect(await screen.findByText("Ticket Cockpit")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Run Loop" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/tickets/ticket-implement-plane-sync-123abc/loop/run",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("\"max_steps\":2"),
        }),
      );
    });
    expect(await screen.findByText("Autonomous Loop")).toBeTruthy();
    expect(screen.getByText("Stop max_steps_reached")).toBeTruthy();
    expect(screen.getAllByText("1 steps").length).toBeGreaterThan(0);
    expect(screen.getByText("Step 1")).toBeTruthy();
    expect(screen.getByText("single_step_completed")).toBeTruthy();
  });

  it("can stop a Ticket-native autonomous loop from the Ticket detail", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<TicketsPage selectedSection="tickets" />);

    expect(await screen.findByText("Ticket Cockpit")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Stop Loop" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/tickets/ticket-implement-plane-sync-123abc/loop/control",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("\"action\":\"stop\""),
        }),
      );
    });
    expect(await screen.findByText("Loop Control")).toBeTruthy();
    expect(screen.getByText("stopped")).toBeTruthy();
    expect(screen.getByText("Dashboard requested a governed Ticket loop stop.")).toBeTruthy();
    expect(screen.getByText("1 sessions")).toBeTruthy();
    expect(screen.getByText("Report report-loop-control-stop")).toBeTruthy();
  });

  it("can pause a Ticket-native autonomous loop from the Ticket detail", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<TicketsPage selectedSection="tickets" />);

    expect(await screen.findByText("Ticket Cockpit")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Pause Loop" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/tickets/ticket-implement-plane-sync-123abc/loop/control",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("\"action\":\"pause\""),
        }),
      );
    });
    expect(await screen.findByText("Loop Control")).toBeTruthy();
    expect(screen.getByText("paused")).toBeTruthy();
    expect(screen.getByText("Dashboard requested a governed Ticket loop pause.")).toBeTruthy();
    expect(screen.getByText("Report report-loop-control-pause")).toBeTruthy();
  });

  it("can pump the cross-Ticket loop queue from the Ticket cockpit", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<TicketsPage selectedSection="tickets" />);

    expect(await screen.findByText("Ticket Cockpit")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Pump Queue" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/tickets/loop/queue/pump",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("\"max_items\":1"),
        }),
      );
    });
    expect(await screen.findByText("Pump completed: 1 processed, 0 queued")).toBeTruthy();
  });

  it("can drill into a Ticket loop run detail from the Ticket workspace", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<TicketsPage selectedSection="tickets" />);

    expect(await screen.findByText("Loop Runs")).toBeTruthy();
    const detailButtons = await screen.findAllByRole("button", { name: "Details" });
    fireEvent.click(detailButtons[1]);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/tickets/ticket-implement-plane-sync-123abc/loop/runs/ticket-loop-run-ticket-implement-plane-sync-123abc-001",
        expect.objectContaining({ method: "GET" }),
      );
    });
    expect(await screen.findByText("Loop Run Detail")).toBeTruthy();
    expect(screen.getAllByText("ticket-loop-run-ticket-implement-plane-sync-123abc-001").length).toBeGreaterThan(0);
    expect(screen.getByText("Saved .aiteamos/ticket_loop_runs.json")).toBeTruthy();
    expect(screen.getByText("Request")).toBeTruthy();
    expect(screen.getByText("Response")).toBeTruthy();
    expect(screen.getByText("Policy")).toBeTruthy();
    expect(screen.getByText("Control")).toBeTruthy();
    expect(screen.getAllByText((content) => content.includes("\"max_steps\": 2")).length).toBeGreaterThan(0);
    expect(screen.getAllByText((content) => content.includes("\"executor_id\": \"universal_employee_agent\"")).length).toBeGreaterThan(0);
  });

  it("links Ticket loop runs to the Runtime Replay surface", async () => {
    render(<TicketsPage selectedSection="tickets" />);

    expect(await screen.findByText("Loop Runs")).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: "Replay" }));

    expect(window.location.hash).toBe("#/runtime/alex%3A%3Aticket-loop-ticket-implement-plane-sync-123abc-step-1%3A%3Aticket-implement-plane-sync-123abc");
  });

  it("renders the cross-Ticket loop queue tab", async () => {
    render(<TicketsPage selectedSection="queue" />);

    expect((await screen.findAllByText("Loop Queue")).length).toBeGreaterThan(0);
    expect(screen.getByText("Cross-Ticket queue for governed autonomous loop runs.")).toBeTruthy();
    expect(screen.getByText("ticket-loop-queue-ticket-implement-plane-sync-123abc-queued")).toBeTruthy();
    expect(screen.getByText("Queue this Ticket loop from Clara.")).toBeTruthy();
    expect(screen.getByText("Priority 10")).toBeTruthy();
    expect(screen.getByText("Completed queue item.")).toBeTruthy();
    expect(screen.getByText("Worker Daemon")).toBeTruthy();
    expect(screen.getByText("State .aiteamos/ticket_loop_queue_worker.json")).toBeTruthy();
    expect(screen.getByText("Worker ticks")).toBeTruthy();
    expect(screen.getByText("Worker processed")).toBeTruthy();
    expect(screen.getByText("Policy actions")).toBeTruthy();
    expect(screen.getByText("Recent policy action proposed: failure_retrospective_candidate, report report-failure-retrospective")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Report" }));
    expect(window.location.hash).toBe("#/tickets/reports/ticket-implement-plane-sync-123abc%3A%3Areport%3A%3Areport-failure-retrospective");
    fireEvent.click(screen.getByRole("button", { name: "Review Asset" }));
    expect(window.location.hash).toBe("#/assets/review/asset-candidate-ticket-loop-failure-retrospective-ticket-implement-plane-sync-123abc");
    expect(screen.getByRole("button", { name: "Start Worker" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Tick Worker" })).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Ticket" }).length).toBeGreaterThan(0);
  });

  it("can tick the Ticket loop queue worker from the Queue tab", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<TicketsPage selectedSection="queue" />);

    expect(await screen.findByText("Worker Daemon")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Tick Worker" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/tickets/loop/queue/worker/tick",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("Dashboard requested a governed Ticket loop queue worker tick."),
        }),
      );
    });
    expect(await screen.findByText("Worker tick completed: 1 processed, 0 queued")).toBeTruthy();
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

  it("selects a Ticket from executor deep links with overview and Ticket id", async () => {
    render(<TicketsPage selectedSection="tickets/rd-0009" />);

    expect(await screen.findByText("Selected from related Memory asset.")).toBeTruthy();
    expect(screen.getAllByText("rd-0009").length).toBeGreaterThan(0);
  });
});
