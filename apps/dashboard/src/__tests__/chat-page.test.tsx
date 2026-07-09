import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatPage } from "../pages/chat";

const runtimeState = vi.hoisted(() => ({
  response: null as Record<string, unknown> | null,
  state: {} as Record<string, unknown>,
  runtimeOptions: [] as Record<string, unknown>[],
  runConfigs: [] as Record<string, unknown>[],
  protocolCommands: [] as Record<string, unknown>[],
  assetReviews: [] as Record<string, unknown>[],
  assetProjections: [] as string[],
  approvalReviews: [] as Record<string, unknown>[],
  loopResumes: [] as Record<string, unknown>[],
  interrupt: null as Record<string, unknown> | null,
}));

vi.mock("@assistant-ui/react-langchain", () => ({
  useStreamRuntime: (options: Record<string, unknown>) => {
    runtimeState.runtimeOptions.push(options);
    return {};
  },
  useLangChainState: (key: string, defaultValue: unknown) => (
    key === "aiteamos_chat_response"
      ? runtimeState.response
      : key in runtimeState.state
        ? runtimeState.state[key]
        : defaultValue
  ),
  useLangChainError: () => null,
  useLangChainInterruptState: () => runtimeState.interrupt,
}));

vi.mock("@assistant-ui/react", () => {
  const Passthrough = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>;
  return {
    AssistantRuntimeProvider: Passthrough,
    ComposerPrimitive: {
      Root: Passthrough,
      Input: ({ submitMode: _submitMode, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement> & { submitMode?: string }) => <textarea {...props} />,
      Send: ({ children }: { children?: React.ReactNode }) => <button type="button">{children}</button>,
    },
    MessagePrimitive: {
      Root: Passthrough,
      Parts: () => null,
    },
    ThreadPrimitive: {
      Root: Passthrough,
      Viewport: Passthrough,
      Empty: Passthrough,
      Messages: () => <div />,
      ViewportFooter: Passthrough,
    },
    useComposerRuntime: () => ({
      setRunConfig: (config: Record<string, unknown>) => runtimeState.runConfigs.push(config),
    }),
  };
});

vi.mock("react-resizable-panels", () => ({
  Panel: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  Group: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  Separator: () => <div />,
}));

const clara = {
  id: "clara",
  display_name: "Clara",
  kind: "ai",
  role: "AI Team OS Manager",
  summary: "Coordinator",
  skills: ["ticket-specification"],
  ai_engine_mode: "deepseek_chat_or_file_stub",
  default_ai_engine: "system",
  preserve_engine_thread: true,
  default_thread_id: "employee-clara-default",
};

const aiEngines = {
  active_engine: "deepseek",
  deepseek_model: "deepseek-v4-flash",
  deepseek_thinking: "enabled",
  openai_model: "gpt-5.5",
  fallback_on_error: true,
  engines: {
    deepseek: {
      id: "deepseek",
      display_name: "DeepSeek",
      kind: "llm_api",
      description: "DeepSeek remote engine",
      support_status: "supported",
      config_status: "configured",
      auth_kind: "bearer",
      base_url: "https://api.deepseek.com",
      api_key_env: "DEEPSEEK_API_KEY",
      model: "deepseek-v4-flash",
      thinking: "enabled",
      context_window: 1000000,
      max_tokens: 384000,
      enabled: true,
      editable: true,
      active: true,
      api_key_configured: true,
      status: "configured",
      secret_env_vars: ["DEEPSEEK_API_KEY"],
      capabilities: ["chat", "reasoning"],
      model_options: ["deepseek-v4-flash"],
      thinking_options: ["enabled", "disabled"],
      config_fields: [],
      chat_options: [],
      health_detail: "Ready for Chat selection.",
    },
  },
  api_keys_configured: { deepseek: true },
  catalog_order: ["deepseek"],
  saved_paths: { ai_engines: ".aiteamos/ai_engines.json" },
};

const threadList = {
  employee_id: "clara",
  active_thread_id: "employee-clara-default",
  threads: [
    {
      id: "employee-clara-default",
      employee_id: "clara",
      title: "Self-bootstrap recall",
      created_at: "2026-06-07T00:00:00Z",
      updated_at: "2026-06-07T00:01:00Z",
      last_message_at: "2026-06-07T00:01:00Z",
      message_count: 2,
      archived: false,
      saved_path: ".aiteamos/conversations/employee-clara-default.jsonl",
    },
  ],
};

const approvalRecord = {
  id: "approval-runtime-1",
  status: "requested",
  kind: "runtime_approval",
  ticket_id: "rd-0001",
  employee_id: "clara",
  executor_id: "claude_code",
  required_capability: "repo:write",
  risk_level: "high",
  reason: "External runtime repo mutation requires approval before execution.",
  proposed_action: { action: "implement_ticket", ticket_id: "rd-0001", executor_id: "claude_code" },
  source_state_ref: "state-runtime-1",
  source_state_snapshot_ref: "snapshot-runtime-1",
  current_graph_node: "governance_gate",
  checkpoint_ref: "checkpoint-runtime-1",
  executor_session_ref: "session-runtime-1",
  approval_request: {},
  source_request: {
    request_id: "run-chat-provenance",
    action_plan: { action: "implement_ticket", arguments: { ticket_id: "rd-0001" } },
  },
  source_result: { status: "needs_approval" },
  created_at: "2026-06-19T00:00:00Z",
  updated_at: "2026-06-19T00:01:00Z",
  reviewed_at: "2026-06-19T00:01:00Z",
  reviewer_employee_id: "clara",
  review_reason: "Initial governance review reason.",
  last_run_request_id: "run-chat-provenance-approved-attempt-1",
  last_run_status: "blocked",
  last_ingestion_blocker: "test evidence is required before ingestion.",
  last_result: { status: "blocked", report: "test evidence is required before ingestion." },
  resume_result: {},
  run_history: [
    {
      run_request_id: "run-chat-provenance-approved-attempt-1",
      status: "blocked",
      ingested: false,
      ingestion_blocker: "test evidence is required before ingestion.",
      artifact_count: 0,
      evidence_count: 0,
      error_count: 1,
      trace_ref: ".aiteamos/traces/run-chat-provenance-approved.jsonl",
      created_at: "2026-06-19T00:01:00Z",
    },
  ],
};

const ticketLoopTimeline = {
  ticket_id: "rd-0001",
  summary: {
    ticket_id: "rd-0001",
    status: "waiting_evidence",
    waiting_reason: "A reviewer requested more evidence before this Ticket loop can retry.",
    next_action: "Attach evidence, then retry the governed loop.",
    can_run: false,
    can_resume: true,
    can_retry: true,
    latest_at: "2026-06-19T00:01:00Z",
    counts: { ticket_report: 1, approval: 1 },
    provider_blockers: [],
    retry_requirements: [
      {
        id: "new_evidence_after_review",
        label: "New evidence after review",
        satisfied: true,
        detail: "Evidence was attached after the reviewer asked for it.",
        target_route: "tickets/reports/rd-0001",
      },
    ],
    approval_resume: [],
    queue_reliability: null,
  },
  items: [],
  saved_paths: { timeline: ".aiteamos/ticket_loop_runs.json" },
};

const ticketLoopResumeResponse = {
  ticket_id: "rd-0001",
  status: "in_progress",
  previous_status: "waiting_evidence",
  detail: "Ticket loop resume queued from waiting_evidence status.",
  queue_item: {
    queue_id: "ticket-loop-queue-rd-0001-retry",
    run_id: "ticket-loop-run-rd-0001-retry",
    ticket_id: "rd-0001",
    status: "queued",
    priority: 50,
    request: { action: "retry_after_evidence", max_steps: 2 },
    response: {},
    error: "",
    actor_employee_id: "clara",
    actor_role: "AI Team OS Manager",
    reason: "Chat Workbench requested governed Ticket loop retry_after_evidence.",
    report_id: "report-loop-resume-rd-0001",
    enqueued_at: "2026-06-19T00:02:00Z",
    started_at: "",
    finished_at: "",
    updated_at: "2026-06-19T00:02:00Z",
    saved_path: ".aiteamos/ticket_loop_queue.json",
  },
  saved_paths: { loop_queue: ".aiteamos/ticket_loop_queue.json" },
};

const chatResponse = {
  thread_id: "employee-clara-default",
  run_id: "run-chat-provenance",
  target_employee: clara,
  engine_thread_id: "engine-thread-1",
  ticket_keys: ["rd-0001"],
  reply: "Recorded report with recalled memory context.",
  trace_events: [
    {
      event: "chat.action_plan.completed",
      detail: "Planned ChatActionPlan action: append_report.",
      data: {
        action: "append_report",
        source: "deepseek",
        reason: "User asked to append a report to the Ticket.",
      },
    },
    {
      event: "ai_engine.deepseek.completed",
      detail: "Generated response through DeepSeek Chat Completions API.",
      data: { ai_engine: "deepseek_chat_completions", model: "deepseek-v4-flash" },
    },
  ],
  run_metadata: {
    run_id: "run-chat-provenance",
    thread_id: "employee-clara-default",
    employee: { id: "clara", display_name: "Clara", role: "AI Team OS Manager" },
    ticket_keys: ["rd-0001"],
    provider_refs: [{ provider: "plane", provider_ref: "plane-ticket-1" }],
    graphiti_episode_refs: [{ graphiti_episode_id: "episode-approved-1", memory_id: "mem-approved-1" }],
    recalled_memory_refs: [
      {
        memory_id: "mem-approved-1",
        graphiti_recalled: true,
        graphiti_episode_id: "episode-approved-1",
        source_ticket_id: "rd-0000",
      },
    ],
    ai_engine: {
      selected_ai_engine: "deepseek",
      actual_ai_engine: "deepseek_chat_completions",
      model: "deepseek-v4-flash",
      engine_thread_id: "engine-thread-1",
      event: "ai_engine.deepseek.completed",
    },
    execution: {
      request_id: "run-chat-provenance",
      executor_id: "langgraph",
      status: "completed",
      action: "append_report",
      ticket_binding: { mode: "existing", ticket_id: "rd-0001", required: true },
      capability_grants: ["tickets:read", "tickets:write", "memory:recall"],
      trace: {
        trace_ref: ".aiteamos/traces/run-chat-provenance.jsonl",
        executor_session_ref: "lg-run-chat-provenance",
        checkpoint_ref: "langgraph:run-chat-provenance",
      },
      result: {
        output_ticket_id: "rd-0001",
        artifact_count: 1,
        artifact_refs: [{ kind: "external_runtime_cli_execution", ref: "external-runtime:claude_code:cli" }],
        tool_event_count: 2,
        memory_candidate_count: 1,
        evidence_count: 1,
        evidence_refs: [{ kind: "runtime_report", ref: "runtime-report-ref" }],
        ticket_report_count: 1,
        ticket_report_refs: [{ kind: "external_runtime_repo_mutation", ref: "report-runtime-1", evidence_count: "2" }],
        error_count: 0,
        errors: [{ reason: "repo_mutation_approval_required", detail: "repo:write requires approval" }],
      },
      governance: {
        approval_refs: ["approval-runtime-1"],
        approved_capabilities: ["repo:write"],
        ticket_report_refs: [{ kind: "external_runtime_repo_mutation", ref: "report-runtime-1", evidence_count: "2" }],
      },
    },
    scoped_context: {
      relevant_asset_count: 2,
      recalled_memory_count: 1,
      prior_evidence_count: 1,
      setup_blocker_count: 1,
      setup_blockers: [{ reason: "graphiti_setup_blocker", detail: "Graphiti is not configured." }],
      exclusions: ["raw secrets", "raw terminal logs"],
      universal_context: {
        version: "universal_context.v1",
        employee_id: "clara",
        ticket_id: "rd-0001",
        selected_ai_engine: "deepseek",
        related_ticket_count: 1,
        relevant_asset_count: 2,
        recalled_memory_count: 1,
        prior_evidence_count: 1,
        setup_blocker_count: 1,
        ticket_backend_status: "configured",
        summary: {
          task_summary: "Recorded report with recalled memory context.",
          employee_id: "clara",
          selected_ai_engine: "deepseek",
          ticket_id: "rd-0001",
          related_ticket_count: 1,
          relevant_asset_count: 2,
          asset_relationship_hint_count: 2,
          recalled_memory_count: 1,
          prior_evidence_count: 1,
          setup_blocker_count: 1,
        },
        employee_context: {
          selected_employee: {
            employee_id: "clara",
            display_name: "Clara",
            work_history_summary: {
              source: "employee_work_ledger",
              current_ticket_count: 1,
              report_count: 2,
              runtime_run_count: 1,
              quality_feedback_count: 1,
            },
          },
          work_history: {
            summary: {
              source: "employee_work_ledger",
              current_ticket_count: 1,
              historical_ticket_count: 4,
              report_count: 2,
              runtime_run_count: 1,
              quality_feedback_count: 1,
            },
          },
        },
        asset_context: {
          relevant_assets: [
            {
              asset_id: "asset-runtime-new-guidance",
              title: "New runtime guidance",
              source_kind: "asset_record",
              source_ref: "asset-runtime-new-guidance",
            },
          ],
          relationship_hints: [
            {
              asset_id: "asset-runtime-old-guidance",
              target_asset_id: "asset-runtime-old-guidance",
              source_asset_id: "asset-runtime-new-guidance",
              relationship_type: "supersedes",
              status: "superseded",
              title: "Old runtime guidance",
              exclusion_reason: "Approved Asset relationship marks asset-runtime-old-guidance as superseded: New governed runtime guidance supersedes older runtime guidance.",
              superseded_by_asset_id: "asset-runtime-new-guidance",
              conflicted_by_asset_id: "",
              source_confidence: 0.94,
              provenance: {
                source_kind: "asset_relationship",
                source_ref: "asset-runtime-new-guidance",
                scope_kind: "asset",
                scope_ref: "asset-runtime-old-guidance",
              },
            },
            {
              asset_id: "asset-runtime-conflicting-guidance",
              target_asset_id: "asset-runtime-conflicting-guidance",
              source_asset_id: "asset-runtime-new-guidance",
              relationship_type: "conflicts_with",
              status: "conflicted",
              title: "Conflicting runtime guidance",
              exclusion_reason: "Approved Asset relationship marks asset-runtime-conflicting-guidance as conflicted: New governed runtime guidance conflicts with prior risky guidance.",
              superseded_by_asset_id: "",
              conflicted_by_asset_id: "asset-runtime-new-guidance",
              source_confidence: 0.88,
              provenance: {
                source_kind: "asset_relationship",
                source_ref: "asset-runtime-new-guidance",
                scope_kind: "asset",
                scope_ref: "asset-runtime-conflicting-guidance",
              },
            },
          ],
        },
        backend_context: {
          ticket_backend: { status: "configured" },
        },
        provenance_summary: [
          {
            kind: "employee",
            source_kind: "employee_profile",
            source_ref: "clara",
            scope_kind: "employee",
            scope_ref: "clara",
            source_confidence: "1.0",
          },
          {
            kind: "employee_work_history",
            source_kind: "employee_work_ledger",
            source_ref: "clara",
            scope_kind: "employee",
            scope_ref: "clara",
            source_confidence: "0.85",
          },
          {
            kind: "ticket",
            source_kind: "ticket_service",
            source_ref: "rd-0001",
            scope_kind: "ticket",
            scope_ref: "rd-0001",
            source_confidence: "0.9",
          },
          {
            kind: "memory",
            source_kind: "memory",
            source_ref: "mem-approved-1",
            scope_kind: "ticket",
            scope_ref: "rd-0001",
            source_confidence: "0.8",
          },
        ],
      },
    },
    approval: {
      require_approval_for: ["repo:write", "memory_approve"],
      on_missing_approval: "return_needs_approval",
      approval_refs: ["approval-runtime-1"],
      approved_capabilities: ["repo:write"],
      approval_records: [approvalRecord],
      approval_requests: [
        {
          kind: "repo_mutation",
          ticket_id: "rd-0001",
          executor_id: "claude_code",
          required_capability: "repo:write",
          approval_ref: "approval-runtime-1",
          reason: "External runtime repo mutation requires approval before execution.",
        },
      ],
    },
    visible_response: {
      version: "chat_visible_response.v1",
      assistant_message: {
        role: "assistant",
        content: "Recorded report with recalled memory context.",
      },
      display_state: "provider_blocker",
      runtime_status: {
        status: "completed",
        display_state: "provider_blocker",
        run_id: "run-chat-provenance",
        request_id: "run-chat-provenance",
        executor_id: "langgraph",
        current_node: "final_response",
      },
      blocked_reason: "Graphiti is not configured.",
      retry_cause: "repo:write requires approval",
      approval_request: {
        kind: "repo_mutation",
        ticket_id: "rd-0001",
        executor_id: "claude_code",
        required_capability: "repo:write",
        approval_ref: "approval-runtime-1",
        reason: "External runtime repo mutation requires approval before execution.",
      },
      approval_requests: [
        {
          kind: "repo_mutation",
          ticket_id: "rd-0001",
          executor_id: "claude_code",
          required_capability: "repo:write",
          approval_ref: "approval-runtime-1",
          reason: "External runtime repo mutation requires approval before execution.",
        },
      ],
      approval_records: [approvalRecord],
      handoff_summary: {
        status: "durable_handoff_recorded",
        ticket_id: "rd-0001",
        from_employee_id: "clara",
        to_employee_id: "alex",
      },
      ticket_handoff_refs: [{ kind: "ticket_handoff", ref: "report-handoff-1", to_employee_id: "alex" }],
      ticket_refs: [{ kind: "ticket", ref: "rd-0001" }],
      asset_refs: [{ kind: "memory_candidate", ref: "asset-candidate-1" }],
      memory_refs: [{ kind: "memory", ref: "mem-approved-1" }],
      provider_blockers: [{ reason: "graphiti_setup_blocker", detail: "Graphiti is not configured." }],
    },
    commands: [],
    trace: { path: ".aiteamos/traces/run-chat-provenance.jsonl" },
  },
  saved_paths: { trace: ".aiteamos/traces/run-chat-provenance.jsonl" },
};

describe("ChatPage", () => {
  beforeEach(() => {
    window.location.hash = "";
    runtimeState.response = chatResponse;
    runtimeState.state = {
      active_ticket: { id: "rd-0001", source: "aiteamos_chat_response", ticket_keys: ["rd-0001"] },
      employee_identity: { id: "clara", display_name: "Clara", role: "AI Team OS Manager" },
      ticket_binding: { mode: "existing", ticket_id: "rd-0001", required: true },
      linked_assets: [{ kind: "external_runtime_cli_execution", ref: "external-runtime:claude_code:cli" }],
      recalled_memory_refs: [
        {
          memory_id: "mem-approved-1",
          graphiti_recalled: true,
          graphiti_episode_id: "episode-approved-1",
          source_ticket_id: "rd-0000",
        },
      ],
      approval_requests: [
        {
          kind: "repo_mutation",
          ticket_id: "rd-0001",
          executor_id: "claude_code",
          required_capability: "repo:write",
          approval_ref: "approval-runtime-1",
          reason: "External runtime repo mutation requires approval before execution.",
        },
      ],
      approval_records: [approvalRecord],
      asset_candidates: [
        {
          id: "asset-candidate-1",
          kind: "memory_candidate",
          candidate_id: "mem-candidate-1",
          source_candidate_id: "mem-candidate-1",
          asset_id: "mem-candidate-1",
          asset_type: "memory",
          status: "proposed",
          review_state: "proposed",
          source_ticket_id: "rd-0001",
          source_report_id: "report-runtime-1",
          provider: "aiteamos",
          provider_ref: ".aiteamos/assets/candidates.json#asset-candidate-1",
        },
      ],
      provider_blockers: [{ reason: "graphiti_setup_blocker", detail: "Graphiti is not configured." }],
      handoff_decision: {
        should_handoff: true,
        source: "execution_result_artifact",
        target_employee_id: "alex",
        reason: "Goal asks for backend runtime implementation.",
      },
      handoff_summary: {
        node: "maybe_handoff_employee",
        status: "durable_handoff_recorded",
        ticket_id: "rd-0001",
        from_employee_id: "clara",
        to_employee_id: "alex",
        to_role: "AI RD / Implementer",
      },
      ticket_handoff_refs: [
        {
          kind: "ticket_handoff",
          ticket_id: "rd-0001",
          report_id: "report-handoff-1",
          to_employee_id: "alex",
          to_role: "AI RD / Implementer",
        },
      ],
      ticket_loop_policy_actions: [
        {
          kind: "sla_escalation_handoff",
          ticket_id: "rd-0001",
          status: "escalated",
          detail: "SLA response breach escalated through existing Ticket handoff.",
          candidate_ids: [],
          queue_ids: [],
          run_ids: [],
          handoff_refs: [
            {
              kind: "handoff_requested",
              ticket_id: "rd-0001",
              event_id: "event-sla-handoff-1",
              to_employee_id: "alex",
              to_role: "AI RD / Implementer",
            },
          ],
          report_id: "report-sla-1",
        },
        {
          kind: "recurrence_auto_enqueued",
          ticket_id: "rd-0001",
          status: "queued",
          detail: "Recurring Ticket loop work was enqueued by the queue worker.",
          candidate_ids: [],
          queue_ids: ["ticket-loop-queue-rd-0001-recur"],
          run_ids: ["ticket-loop-run-rd-0001-recur"],
          handoff_refs: [],
          report_id: "report-recur-1",
        },
      ],
      ticket_loop_decision: {
        ticket_id: "rd-0001",
        policy_action_count: 2,
        policy_action_kinds: ["sla_escalation_handoff", "recurrence_auto_enqueued"],
        policy_action_refs: [
          {
            kind: "ticket_handoff",
            action_kind: "sla_escalation_handoff",
            ticket_id: "rd-0001",
            event_id: "event-sla-handoff-1",
            to_employee_id: "alex",
            to_role: "AI RD / Implementer",
          },
          {
            kind: "ticket_loop_queue",
            action_kind: "recurrence_auto_enqueued",
            ticket_id: "rd-0001",
            queue_id: "ticket-loop-queue-rd-0001-recur",
          },
          {
            kind: "ticket_loop_run",
            action_kind: "recurrence_auto_enqueued",
            ticket_id: "rd-0001",
            run_id: "ticket-loop-run-rd-0001-recur",
          },
          {
            kind: "ticket_report",
            action_kind: "sla_escalation_handoff",
            ticket_id: "rd-0001",
            report_id: "report-sla-1",
          },
        ],
      },
      runtime_status: {
        graph: "aiteamos_workbench",
        current_node: "update_workbench_state",
        status: "completed",
        ticket_loop_policy_action_count: 2,
        ticket_loop_policy_action_kinds: ["sla_escalation_handoff", "recurrence_auto_enqueued"],
      },
      workbench_panels: {
        active_ticket: true,
        employee: true,
        assets: true,
        approval: true,
        provider_blockers: true,
        handoff: true,
        ticket_loop_policy: true,
      },
    };
    runtimeState.runtimeOptions = [];
    runtimeState.runConfigs = [];
    runtimeState.protocolCommands = [];
    runtimeState.assetReviews = [];
    runtimeState.assetProjections = [];
    runtimeState.approvalReviews = [];
    runtimeState.loopResumes = [];
    runtimeState.interrupt = null;
    window.localStorage.removeItem("aiteamos.chat.langGraphThreadMap.v1");
    window.localStorage.removeItem("aiteamos.chat.currentLangGraphThreadId");
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      let body: unknown;
      if (url.includes("/api/v1/assets/candidates/asset-candidate-1/review")) {
        const review = JSON.parse(String(init?.body || "{}")) as Record<string, unknown>;
        runtimeState.assetReviews.push(review);
        body = {
          candidate: {
            id: "asset-candidate-1",
            source_candidate_id: "mem-candidate-1",
            asset_id: "mem-candidate-1",
            asset_type: "memory",
            title: "Fixture approval memory",
            content: "Approved fixture resume completed.",
            content_ref: "memory_candidate://mem-candidate-1",
            status: "approved",
            scope_kind: "ticket",
            scope_ref: "rd-0001",
            owner_employee_id: "clara",
            source_kind: "memory_candidate",
            source_ref: "mem-candidate-1",
            provenance: { source_ticket_id: "rd-0001", source_report_id: "report-runtime-1" },
            provider: "aiteamos",
            provider_ref: ".aiteamos/assets/candidates.json#asset-candidate-1",
            relationships: [],
            review_state: "approved",
            usefulness_stats: {},
            created_at: "2026-06-19T00:00:00Z",
            updated_at: "2026-06-19T00:01:00Z",
          },
          review: {
            id: "asset-review-asset-candidate-1",
            candidate_id: "asset-candidate-1",
            asset_id: "mem-candidate-1",
            status: "approved",
            reviewer_employee_id: "clara",
            reason: String(review.reason || ""),
            merge_target_asset_id: "",
            link_relationships: [],
            created_at: "2026-06-19T00:01:00Z",
            updated_at: "2026-06-19T00:01:00Z",
          },
          asset: {
            id: "mem-candidate-1",
            asset_type: "memory",
            title: "Fixture approval memory",
            content: "Approved fixture resume completed.",
            content_ref: "memory_candidate://mem-candidate-1",
            status: "approved",
            scope_kind: "ticket",
            scope_ref: "rd-0001",
            owner_employee_id: "clara",
            source_kind: "memory_candidate",
            source_ref: "mem-candidate-1",
            provenance: { source_ticket_id: "rd-0001", source_report_id: "report-runtime-1" },
            provider: "aiteamos",
            provider_ref: ".aiteamos/assets/registry.json#mem-candidate-1",
            relationships: [],
            review_state: "approved",
            usefulness_stats: {},
            created_at: "2026-06-19T00:01:00Z",
            updated_at: "2026-06-19T00:01:00Z",
          },
          saved_paths: {},
        };
      } else if (url.includes("/api/v1/assets/records/mem-candidate-1/project/graphiti")) {
        runtimeState.assetProjections.push("mem-candidate-1");
        body = {
          asset_id: "mem-candidate-1",
          status: "ingested",
          detail: "Projected to Graphiti.",
          ingested_asset: { episode_id: "episode-fixture-dogfood-2" },
          skipped_asset: null,
          saved_paths: {},
        };
      } else if (url.includes("/api/v1/runtime-executors/claude_code/approvals/approval-runtime-1/review")) {
        const review = JSON.parse(String(init?.body || "{}")) as Record<string, unknown>;
        runtimeState.approvalReviews.push(review);
        body = {
          ...approvalRecord,
          status: String(review.status || "approved"),
          updated_at: "2026-06-19T00:01:00Z",
          reviewed_at: "2026-06-19T00:01:00Z",
          reviewer_employee_id: String(review.reviewer_employee_id || "clara"),
          review_reason: String(review.reason || ""),
        };
      } else if (url.includes("/api/v1/tickets/rd-0001/loop/resume")) {
        const resume = JSON.parse(String(init?.body || "{}")) as Record<string, unknown>;
        runtimeState.loopResumes.push(resume);
        body = ticketLoopResumeResponse;
      } else if (url.includes("/api/v1/tickets/rd-0001/loop/timeline")) {
        body = ticketLoopTimeline;
      } else if (url.includes(":2024/threads/runtime-thread-1/commands")) {
        runtimeState.protocolCommands.push(JSON.parse(String(init?.body || "{}")));
        return new Response(JSON.stringify({ type: "success", id: 2, result: {} }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      else if (url.includes(":2024/threads/runtime-thread-1/state")) {
        body = {
          interrupts: runtimeState.interrupt
            ? [
                {
                  id: runtimeState.interrupt.id,
                  ns: runtimeState.interrupt.ns,
                  value: runtimeState.interrupt.value,
                },
              ]
            : [],
          values: {
            ...runtimeState.state,
            aiteamos_chat_response: {
              ...chatResponse,
              run_id: "run-resumed-approval",
              run_metadata: {
                ...chatResponse.run_metadata,
                execution: {
                  ...(chatResponse.run_metadata.execution as Record<string, unknown>),
                  status: "completed",
                },
              },
            },
            runtime_status: { graph: "aiteamos_workbench", current_node: "final_response", status: "completed" },
          },
        };
      } else if (url.endsWith(":2024/threads")) body = { thread_id: "019ede34-a8c3-7a19-a1a8-0df675ac55f8" };
      else if (url.endsWith("/chat/employees")) body = [clara];
      else if (url.endsWith("/chat/ai-engines")) body = aiEngines;
      else if (url.endsWith("/capabilities")) body = { capabilities: [] };
      else if (url.includes("/chat/threads?")) body = threadList;
      else body = { detail: `Unhandled URL ${url}` };
      const bodyRecord = body as Record<string, unknown>;
      const status = "detail" in bodyRecord && Object.keys(bodyRecord).length === 1 ? 404 : 200;
      return new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    }));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    runtimeState.response = null;
    runtimeState.state = {};
    runtimeState.runtimeOptions = [];
    runtimeState.runConfigs = [];
    runtimeState.protocolCommands = [];
    runtimeState.assetReviews = [];
    runtimeState.assetProjections = [];
    runtimeState.approvalReviews = [];
    runtimeState.loopResumes = [];
    runtimeState.interrupt = null;
  });

  it("uses the LangChain Workbench runtime instead of the AG-UI main path", async () => {
    render(<ChatPage />);

    expect(await screen.findByText("Latest Run")).toBeTruthy();
    expect(screen.getByText("Workbench State")).toBeTruthy();
    expect(screen.getByText("update_workbench_state")).toBeTruthy();
    expect(screen.getByText("Employee Handoff")).toBeTruthy();
    expect(screen.getAllByText("durable_handoff_recorded").length).toBeGreaterThan(0);
    expect(screen.getAllByText("clara -> alex").length).toBeGreaterThan(0);
    expect(screen.getByText("report-handoff-1")).toBeTruthy();
    expect(screen.getByText("Ticket Loop Policy")).toBeTruthy();
    expect(screen.getByText("sla_escalation_handoff")).toBeTruthy();
    expect(screen.getByText("recurrence_auto_enqueued")).toBeTruthy();
    expect(screen.getAllByText("handoff:alex").length).toBeGreaterThan(0);
    expect(screen.getAllByText("queue:ticket-loop-queue-rd-0001-recur").length).toBeGreaterThan(0);
    expect(screen.getAllByText("run:ticket-loop-run-rd-0001-recur").length).toBeGreaterThan(0);
    expect(runtimeState.runtimeOptions.length).toBeGreaterThan(0);
    expect(runtimeState.runtimeOptions[0]).toMatchObject({
      assistantId: "aiteamos_workbench",
      messagesKey: "messages",
      threadId: "employee-clara-default",
      initialValues: {
        thread_id: "employee-clara-default",
      },
    });
    await expect((runtimeState.runtimeOptions[0].create as () => Promise<{ externalId?: string }> )()).resolves.toEqual({
      externalId: undefined,
    });
    (runtimeState.runtimeOptions[0].onThreadId as (threadId: string) => void)("019ede34-a8c3-7a19-a1a8-0df675ac55f8");
    expect(window.localStorage.getItem("aiteamos.chat.langGraphThreadMap.v1")).toContain("019ede34-a8c3-7a19-a1a8-0df675ac55f8");
    expect(runtimeState.runConfigs.length).toBeGreaterThan(0);
    expect(runtimeState.runConfigs[runtimeState.runConfigs.length - 1]).toMatchObject({
      custom: {
        target_employee_id: "clara",
        employee_id: "clara",
        thread_id: "employee-clara-default",
      },
    });
  });

  it("renders the backend visible response contract in the main Chat thread", async () => {
    render(<ChatPage />);

    expect((await screen.findAllByText("Recorded report with recalled memory context.")).length).toBeGreaterThan(0);
    expect(screen.getByText("provider_blocker")).toBeTruthy();
    expect(screen.getAllByText("Graphiti is not configured.").length).toBeGreaterThan(0);
    expect(screen.getAllByText("repo:write requires approval").length).toBeGreaterThan(0);
    expect(screen.getAllByText("approval-runtime-1: External runtime repo mutation requires approval before execution.").length).toBeGreaterThan(0);
    expect(screen.getAllByText("clara -> alex").length).toBeGreaterThan(0);
    expect(screen.getAllByText("memory:mem-approved-1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("asset-candidate-1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("rd-0001").length).toBeGreaterThan(0);
  });

  it("links visible response actions to domain pages and Chat details", async () => {
    render(<ChatPage />);

    expect(await screen.findByText("provider_blocker")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Open visible Ticket rd-0001" }));
    expect(window.location.hash).toBe("#/tickets/rd-0001");

    fireEvent.click(screen.getByRole("button", { name: "Open visible Employee alex" }));
    expect(window.location.hash).toBe("#/employees/alex/work");

    fireEvent.click(screen.getByRole("button", { name: "Open visible Asset Asset Review" }));
    expect(window.location.hash).toBe("#/assets/review/memories");

    fireEvent.click(screen.getByRole("button", { name: "Open visible Runtime Replay clara::employee-clara-default::rd-0001" }));
    expect(window.location.hash).toBe("#/runtime/clara%3A%3Aemployee-clara-default%3A%3Ard-0001");

    fireEvent.click(screen.getByRole("button", { name: "Open provider blocker status" }));
    expect(window.location.hash).toBe("#/system-status");

    fireEvent.click(screen.getAllByTitle("Hide trace")[0]);
    expect(screen.queryByText("Approval Policy")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Open approval panel approval-runtime-1" }));
    expect(screen.getByText("Approval Policy")).toBeTruthy();
  });

  it("maps completed, blocked, approval, handoff, and provider states from visible response", async () => {
    const cases: Array<{
      state: string;
      reply: string;
      detail: string;
      blocked_reason?: string;
      retry_cause?: string;
      approval_requests?: Record<string, unknown>[];
      provider_blockers?: Record<string, unknown>[];
      handoff_summary?: Record<string, unknown>;
    }> = [
      {
        state: "completed",
        reply: "Completed visible reply.",
        detail: "completed-ticket",
      },
      {
        state: "blocked",
        reply: "Blocked visible reply.",
        detail: "Plane write failed.",
        blocked_reason: "Plane write failed.",
        retry_cause: "Retry after Plane provider health recovers.",
      },
      {
        state: "needs_approval",
        reply: "Approval visible reply.",
        detail: "approval-visible-1: Approval required for repo:write.",
        approval_requests: [{ approval_ref: "approval-visible-1", reason: "Approval required for repo:write." }],
      },
      {
        state: "handoff",
        reply: "Handoff visible reply.",
        detail: "clara -> alex",
        handoff_summary: { from_employee_id: "clara", to_employee_id: "alex" },
      },
      {
        state: "provider_blocker",
        reply: "Provider visible reply.",
        detail: "Graphiti setup is missing.",
        blocked_reason: "Graphiti setup is missing.",
        provider_blockers: [{ reason: "graphiti_setup_blocker", detail: "Graphiti setup is missing." }],
      },
    ];

    for (const item of cases) {
      cleanup();
      runtimeState.response = {
        ...chatResponse,
        reply: item.reply,
        run_metadata: {
          ...chatResponse.run_metadata,
          visible_response: {
            version: "chat_visible_response.v1",
            assistant_message: { role: "assistant", content: item.reply },
            display_state: item.state,
            runtime_status: {
              status: item.state === "provider_blocker" ? "completed" : item.state,
              display_state: item.state,
              run_id: `run-${item.state}`,
              executor_id: "langgraph",
              current_node: "final_response",
            },
            blocked_reason: item.blocked_reason || "",
            retry_cause: item.retry_cause || "",
            approval_requests: item.approval_requests || [],
            provider_blockers: item.provider_blockers || [],
            handoff_summary: item.handoff_summary || {},
            ticket_refs: [{ kind: "ticket", ref: item.detail === "completed-ticket" ? item.detail : "rd-0001" }],
            asset_refs: [],
            memory_refs: [],
            ticket_handoff_refs: [],
          },
        },
      };

      render(<ChatPage />);
      expect((await screen.findAllByText(item.reply)).length).toBeGreaterThan(0);
      expect(screen.getAllByText(item.state).length).toBeGreaterThan(0);
      expect(screen.getAllByText(item.detail).length).toBeGreaterThan(0);
    }
  });

  it("shows run provenance for action plan, recalled memory, Graphiti, provider, and trace", async () => {
    render(<ChatPage />);

    expect(await screen.findByText("Latest Run")).toBeTruthy();
    expect(screen.getByText("Trace path")).toBeTruthy();
    expect(screen.getAllByText(".aiteamos/traces/run-chat-provenance.jsonl").length).toBeGreaterThan(0);
    expect(screen.getByText("Action Plan")).toBeTruthy();
    expect(screen.getByText("append_report:deepseek")).toBeTruthy();
    expect(screen.getByText("Runtime Dispatch")).toBeTruthy();
    expect(screen.getByText("langgraph")).toBeTruthy();
    expect(screen.getByText("existing:rd-0001")).toBeTruthy();
    expect(screen.getByText("lg-run-chat-provenance")).toBeTruthy();
    expect(screen.getAllByText("Artifacts").length).toBeGreaterThan(0);
    expect(screen.getByText("external-runtime:claude_code:cli")).toBeTruthy();
    expect(screen.getAllByText("Evidence").length).toBeGreaterThan(0);
    expect(screen.getByText("runtime-report-ref")).toBeTruthy();
    expect(screen.getByText("Ticket Reports")).toBeTruthy();
    expect(screen.getAllByText("report-runtime-1").length).toBeGreaterThan(0);
    expect(screen.getByText("external_runtime_repo_mutation · 2 evidence")).toBeTruthy();
    expect(screen.getByText("Governance Refs")).toBeTruthy();
    expect(screen.getByText("approval approval-runtime-1")).toBeTruthy();
    expect(screen.getByText("approved repo:write")).toBeTruthy();
    expect(screen.getByText("Execution Errors")).toBeTruthy();
    expect(screen.getByText("repo_mutation_approval_required")).toBeTruthy();
    expect(screen.getByText("tickets:write")).toBeTruthy();
    expect(screen.getByText("Scoped Context")).toBeTruthy();
    expect(screen.getByText("Setup blockers")).toBeTruthy();
    expect(screen.getByText("Universal Context")).toBeTruthy();
    expect(screen.getByText("universal_context.v1")).toBeTruthy();
    expect(screen.getByText("Related tickets")).toBeTruthy();
    expect(screen.getByText("Work History")).toBeTruthy();
    expect(screen.getByText("Current tickets")).toBeTruthy();
    expect(screen.getAllByText("employee_work_ledger").length).toBeGreaterThan(0);
    expect(screen.getByText("Runtime runs")).toBeTruthy();
    expect(screen.getByText("Asset Relationship Hints")).toBeTruthy();
    expect(screen.getByText("asset-runtime-old-guidance")).toBeTruthy();
    expect(screen.getByText("asset-runtime-conflicting-guidance")).toBeTruthy();
    expect(screen.getAllByText("By: asset-runtime-new-guidance").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("supersedes")).toBeTruthy();
    expect(screen.getByText("conflicts_with")).toBeTruthy();
    expect(screen.getByText("Approved Asset relationship marks asset-runtime-old-guidance as superseded: New governed runtime guidance supersedes older runtime guidance.")).toBeTruthy();
    expect(screen.getByText("Context Provenance")).toBeTruthy();
    expect(screen.getByText("employee_profile:clara")).toBeTruthy();
    expect(screen.getAllByText("ticket_service:rd-0001").length).toBeGreaterThan(0);
    expect(screen.getAllByText("memory:mem-approved-1").length).toBeGreaterThan(0);
    expect(screen.getByText("graphiti_setup_blocker")).toBeTruthy();
    expect(screen.getAllByText("Graphiti is not configured.").length).toBeGreaterThan(0);
    expect(screen.getByText("raw secrets")).toBeTruthy();
    expect(screen.getByText("Approval Policy")).toBeTruthy();
    expect(screen.getAllByText("repo:write").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Requests: 1 · Records: 1")).toBeTruthy();
    expect(screen.getAllByText("Ref: approval-runtime-1").length).toBeGreaterThan(0);
    expect(screen.getByText("Approved: repo:write")).toBeTruthy();
    expect(screen.getByText("repo_mutation")).toBeTruthy();
    expect(screen.getAllByText("External runtime repo mutation requires approval before execution.").length).toBeGreaterThan(0);
    expect(screen.getByText("Executor: claude_code")).toBeTruthy();
    expect(screen.getByText("Ticket: rd-0001")).toBeTruthy();
    expect(screen.getByText("Risk: high")).toBeTruthy();
    expect(screen.getByText("Run History")).toBeTruthy();
    expect(screen.getAllByText("test evidence is required before ingestion.").length).toBeGreaterThan(0);
    expect(screen.getByDisplayValue("Initial governance review reason.")).toBeTruthy();
    expect(screen.getAllByText("Ref: approval-runtime-1").length).toBeGreaterThan(0);
    window.localStorage.setItem("aiteamos.chat.currentLangGraphThreadId", "runtime-thread-1");
    runtimeState.interrupt = {
      id: "interrupt-runtime-1",
      value: { approval_ref: "approval-runtime-1" },
    };
    fireEvent.click(screen.getByRole("button", { name: "Resume approval approval-runtime-1" }));
    expect(await screen.findByText("approval-runtime-1")).toBeTruthy();
    await waitFor(() => {
      expect(runtimeState.approvalReviews).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            status: "approved",
            reviewer_employee_id: "clara",
          }),
        ]),
      );
    });
    await waitFor(() => {
      expect(runtimeState.protocolCommands).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            id: expect.any(Number),
            method: "input.respond",
            params: expect.objectContaining({
              interrupt_id: "interrupt-runtime-1",
              response: expect.objectContaining({
                approval_ref: "approval-runtime-1",
                approval_refs: ["approval-runtime-1"],
                approved_capabilities: ["repo:write"],
                action: "resume_after_approval",
              }),
            }),
          }),
        ]),
      );
    });
    expect(screen.getByText("Recalled Memories")).toBeTruthy();
    expect(screen.getByText("mem-approved-1")).toBeTruthy();
    expect(screen.getByText("Graphiti: yes")).toBeTruthy();
    expect(screen.getByText("Source: rd-0000")).toBeTruthy();
    expect(screen.getByText("Graphiti Episodes")).toBeTruthy();
    expect(screen.getByText("episode-approved-1")).toBeTruthy();
    expect(screen.getByText("Provider Refs")).toBeTruthy();
    expect(screen.getByText("plane")).toBeTruthy();
  });

  it("reviews runtime approvals with reject, changes, and evidence actions", async () => {
    render(<ChatPage />);

    expect(await screen.findByText("Approval Policy")).toBeTruthy();
    const reasonBox = screen.getByLabelText("Review reason approval-runtime-1");

    fireEvent.change(reasonBox, { target: { value: "Please narrow the patch and add approval tests." } });
    fireEvent.click(screen.getByRole("button", { name: "Request changes approval approval-runtime-1" }));
    await waitFor(() => {
      expect(runtimeState.approvalReviews).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            status: "changes_requested",
            reason: "Please narrow the patch and add approval tests.",
          }),
        ]),
      );
    });
    expect(await screen.findByText("changes requested")).toBeTruthy();
    expect((await screen.findAllByText("Please narrow the patch and add approval tests.")).length).toBeGreaterThan(0);

    fireEvent.change(reasonBox, { target: { value: "Attach pytest output and changed-file evidence before approval." } });
    fireEvent.click(screen.getByRole("button", { name: "Ask evidence approval approval-runtime-1" }));
    await waitFor(() => {
      expect(runtimeState.approvalReviews).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            status: "evidence_requested",
            reason: "Attach pytest output and changed-file evidence before approval.",
          }),
        ]),
      );
    });
    expect(await screen.findByText("evidence requested")).toBeTruthy();

    fireEvent.change(reasonBox, { target: { value: "Risk remains too high for this runtime mutation." } });
    fireEvent.click(screen.getByRole("button", { name: "Reject approval approval-runtime-1" }));
    await waitFor(() => {
      expect(runtimeState.approvalReviews).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            status: "rejected",
            reason: "Risk remains too high for this runtime mutation.",
          }),
        ]),
      );
    });
    expect(await screen.findByText("rejected")).toBeTruthy();
  });

  it("queues governed Ticket loop retries from the Chat Workbench timeline", async () => {
    render(<ChatPage />);

    expect(await screen.findByText("Ticket Loop")).toBeTruthy();
    expect(screen.getByText("waiting_evidence")).toBeTruthy();
    expect(screen.getByText("Retry Preflight")).toBeTruthy();
    expect(screen.getByText("1/1")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Retry after evidence rd-0001" }));

    await waitFor(() => {
      expect(runtimeState.loopResumes).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            action: "retry_after_evidence",
            employee_id: "clara",
            selected_executor: "universal_employee_agent",
          }),
        ]),
      );
    });
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/tickets/rd-0001/loop/resume",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("\"action\":\"retry_after_evidence\""),
        }),
      );
    });
    expect(await screen.findByText("Ticket loop resume queued from waiting_evidence status.")).toBeTruthy();
    expect(screen.getByText("Queued ticket-loop-run-rd-0001-retry")).toBeTruthy();
  });

  it("can approve and project Workbench Asset candidates through Assets APIs", async () => {
    render(<ChatPage />);

    expect(await screen.findByText("Asset Candidates")).toBeTruthy();
    expect(screen.getByText("asset-candidate-1")).toBeTruthy();
    expect(screen.getAllByText("mem-candidate-1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("report-runtime-1").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Approve Asset candidate asset-candidate-1" }));
    await waitFor(() => {
      expect(runtimeState.assetReviews).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            status: "approved",
            reviewer_employee_id: "clara",
          }),
        ]),
      );
    });
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/assets/candidates/asset-candidate-1/review",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"status":"approved"'),
        }),
      );
    });
    await waitFor(() => {
      expect((screen.getByRole("button", { name: "Project Asset mem-candidate-1 to Graphiti" }) as HTMLButtonElement).disabled).toBe(false);
    });
    const projectButton = screen.getByRole("button", { name: "Project Asset mem-candidate-1 to Graphiti" });
    fireEvent.click(projectButton);
    await waitFor(() => {
      expect(runtimeState.assetProjections).toContain("mem-candidate-1");
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/assets/records/mem-candidate-1/project/graphiti",
        expect.objectContaining({ method: "POST" }),
      );
    });
    expect(await screen.findByText("ingested:episode-fixture-dogfood-2")).toBeTruthy();
  });

  it("links latest run provenance to Ticket, Runtime Replay, and Assets", async () => {
    render(<ChatPage />);

    expect(await screen.findByText("Provenance Links")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Open Ticket rd-0001" }));
    expect(window.location.hash).toBe("#/tickets/rd-0001");

    fireEvent.click(screen.getByRole("button", { name: "Open Employee clara" }));
    expect(window.location.hash).toBe("#/employees/clara/work");

    fireEvent.click(screen.getByRole("button", { name: "Open Runtime Replay clara::employee-clara-default::rd-0001" }));
    expect(window.location.hash).toBe("#/runtime/clara%3A%3Aemployee-clara-default%3A%3Ard-0001");

    fireEvent.click(screen.getByRole("button", { name: "Open Asset Review" }));
    expect(window.location.hash).toBe("#/assets/review/memories");
  });
});
