import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SystemStatusPage } from "../pages/system-status";

let clipboardWrite: ReturnType<typeof vi.fn>;

const aiEngines = {
  active_engine: "openai",
  deepseek_model: "deepseek-v4-flash",
  deepseek_thinking: "disabled",
  openai_model: "gpt-5-nano",
  fallback_on_error: true,
  engines: {
    openai: {
      id: "openai",
      display_name: "ChatGPT / OpenAI API",
      kind: "llm_api",
      description: "OpenAI Responses API engine.",
      support_status: "supported",
      config_status: "configured",
      auth_kind: "bearer",
      enabled: true,
      editable: true,
      active: true,
      api_key_configured: true,
      status: "configured",
      secret_env_vars: ["OPENAI_API_KEY"],
      capabilities: ["chat", "responses", "graphiti_llm"],
      model_options: ["gpt-5-nano"],
      thinking_options: [],
      config_fields: [],
      chat_options: [],
      health_detail: "Ready for Chat selection.",
    },
  },
  api_keys_configured: { openai: true },
  catalog_order: ["openai"],
  saved_paths: { ai_engines: ".aiteamos/ai_engines.json" },
};

const capabilities = {
  status: {
    capability_count: 3,
    enabled_count: 2,
    configured_count: 2,
    ready_count: 2,
    tool_count: 3,
    kernel_command_count: 1,
    mcp_tool_count: 2,
    native_api_tool_count: 0,
    cli_tool_count: 0,
    ci_tool_count: 0,
    saved_paths: {},
  },
  capabilities: [],
  categories: {},
};

const employees = [
  {
    id: "clara",
    display_name: "Clara",
    kind: "ai",
    role: "AI Team OS Manager",
    summary: "Coordinator",
    skills: [],
    ai_engine_mode: "external_or_file_stub",
    preserve_engine_thread: true,
    default_thread_id: "employee-clara-default",
  },
];

const knowledge = {
  docs_count: 3,
  memories_count: 1,
  decisions_count: 0,
  review_queue_count: 2,
  asset_count: 6,
  saved_paths: {},
};

const memory = {
  backend: {
    backend: "graphiti",
    enabled: true,
    configured: true,
    graph_configured: true,
    llm_configured: true,
    package_installed: true,
    status: "ready",
    detail: "Graphiti is configured.",
    group_id: "aiteamos",
    graph_database: "neo4j",
    uri: "bolt://localhost:7687",
    user: "neo4j",
    llm_ai_engine: "openai",
    llm_ai_engine_name: "ChatGPT / OpenAI API",
    llm_api_key_env: "OPENAI_API_KEY",
    password_configured: true,
    llm_api_key_configured: true,
  },
  candidate_count: 2,
  approved_count: 1,
  pending_graphiti_count: 0,
  saved_paths: {},
};

const codeRepositoryStatus = {
  repository_count: 1,
  enabled_count: 1,
  ready_count: 1,
  local_count: 1,
  remote_count: 0,
  saved_paths: {},
};

const ticketBackendStatus = {
  mode: "plane",
  status: "setup_blocked",
  ticket_count: 0,
  local_file_path: "",
  provider: "plane",
  provider_ref_count: 0,
  setup_required: ["plane_workspace_slug", "plane_project_id", "PLANE_API_KEY"],
  release_target: {
    status: "blocked",
    ready: false,
    detail: "Plan v8 release requires Plane as the active Ticket Backend, complete Plane workspace/project/API setup, and an available Code Repository Plane scope.",
    active_mode: "plane",
    required_mode: "plane",
    required_scope_status: "available",
    code_repository_scope_status: "available",
    blockers: ["plane_api_key_missing"],
    setup_required: ["PLANE_API_KEY"],
    setup_action: "configure_plane_ticket_backend",
  },
  capabilities: ["setup_blocker"],
  mapping: { Ticket: "provider record" },
  detail: "Plane Ticket Backend is selected but setup is incomplete.",
  supported_modes: [],
  saved_paths: { plane_projection: ".aiteamos/tickets/plane" },
};

const toolConnectorStatus = {
  connector_count: 2,
  enabled_count: 2,
  configured_count: 1,
  ready_count: 1,
  saved_paths: {},
};

const systemStatus = {
  secrets: [
    {
      id: "deepseek_api_key",
      scope: "AI Engines",
      purpose: "DeepSeek LLM API key.",
      env_vars: ["DEEPSEEK_API_KEY"],
      required_for: "DeepSeek AI Engine execution.",
      configured: false,
      how_to_configure: "Set DEEPSEEK_API_KEY in the server environment before starting AITeamOS.",
    },
    {
      id: "openai_api_key",
      scope: "AI Engines / Memory Backend",
      purpose: "OpenAI API key.",
      env_vars: ["OPENAI_API_KEY"],
      required_for: "OpenAI AI Engine execution.",
      configured: true,
      how_to_configure: "Set OPENAI_API_KEY in the server environment before starting AITeamOS.",
    },
    {
      id: "anthropic_api_key",
      scope: "Runtime Executors",
      purpose: "Anthropic API key for Claude Agent SDK handoff.",
      env_vars: ["ANTHROPIC_API_KEY"],
      required_for: "Claude Agent SDK runtime adapter.",
      configured: false,
      how_to_configure: "Set ANTHROPIC_API_KEY in the server environment before starting AITeamOS.",
    },
    {
      id: "claude_code_bin",
      scope: "Runtime Executors",
      purpose: "Local Claude Code-compatible CLI binary path.",
      env_vars: ["CLAUDE_CODE_BIN"],
      required_for: "Claude Code-compatible local RuntimeExecutor handoff.",
      configured: false,
      how_to_configure: "Set CLAUDE_CODE_BIN in the server environment before starting AITeamOS.",
    },
    {
      id: "cursor_api_key",
      scope: "Runtime Executors",
      purpose: "Cursor commercial agent backend API key.",
      env_vars: ["CURSOR_API_KEY"],
      required_for: "Cursor RuntimeExecutor handoff.",
      configured: false,
      how_to_configure: "Set CURSOR_API_KEY in the server environment before starting AITeamOS.",
    },
  ],
  runtime_executors: [
    {
      executor_id: "langgraph",
      status: "ready",
      detail: "LangGraph executor is available for runtime-first dispatch.",
      capabilities: ["answer_only", "create_ticket", "append_report", "stream"],
      supported_actions: ["answer_only", "create_ticket", "append_report"],
      diagnostics: {
        smoke: {
          endpoint: "/api/v1/runtime-executors/langgraph/smoke",
          method: "POST",
          default_ingest_result: false,
          ingest_requires_ticket: true,
          mode: "non_destructive_inspect_and_report",
          dispatch_boundary: "RuntimeExecutor",
        },
      },
    },
    {
      executor_id: "claude_code",
      status: "setup_blocked",
      detail: "Claude Code-compatible Local CLI Executor is not configured.",
      capabilities: ["agent_loop", "repo:read", "repo:write", "compatible_local_cli", "deepseek_backend"],
      supported_actions: ["answer_only", "inspect_code_repository", "append_report"],
      missing_env: ["CLAUDE_CODE_BIN"],
      delivery: {
        configured_mode: "handoff",
        supported_modes: ["local_cli"],
        prompt_delivery: "artifact_handoff",
        default_mode: "non_destructive_inspect_and_report",
        non_destructive_default: true,
      },
      config: {
        mode: "non_destructive_inspect_and_report",
        api_key_env: "DEEPSEEK_API_KEY",
        model: "deepseek-reasoner",
      },
      config_env: {
        binary_path: "CLAUDE_CODE_BIN",
        command_template: "CLAUDE_CODE_COMMAND_TEMPLATE",
        model: "CLAUDE_CODE_MODEL",
        api_base_url: "CLAUDE_CODE_API_BASE_URL",
        api_key_env: "CLAUDE_CODE_API_KEY_ENV",
        working_dir: "CLAUDE_CODE_WORKING_DIR",
        mode: "CLAUDE_CODE_MODE",
        timeout_seconds: "CLAUDE_CODE_TIMEOUT_SECONDS",
      },
      expected_output_schema: {
        status: "completed | failed | blocked | needs_approval | partial | cancelled",
        report: "string",
        evidence: "list[dict]",
        artifacts: "list[dict]",
        approval_requests: "list[dict]",
        errors: "list[dict]",
        memory_candidates: "list[dict]",
        tool_events: "list[dict]",
        learning_delta: "dict",
        usage: "dict",
      },
      configured: { binary: false, command_template: true, model: true, api_key_env: true },
      safety_policy: {
        default_mode: "non_destructive_inspect_and_report",
        repo_mutation_guard: ["ticket_bound", "approval_bound", "evidence_bound", "repo_write_capability_required"],
        completion_policy: "external_runtime_completion_must_not_be_faked",
      },
      diagnostics: {
        smoke: {
          endpoint: "/api/v1/runtime-executors/claude_code/smoke",
          method: "POST",
          default_ingest_result: false,
          ingest_requires_ticket: true,
          mode: "non_destructive_inspect_and_report",
          dispatch_boundary: "RuntimeExecutor",
        },
        dogfood: {
          endpoint: "/api/v1/runtime-executors/dogfood",
          method: "POST",
          creates_ticket_if_missing: true,
          approval_required: true,
          ingest_requires_ticket: true,
          repo_mutation_guard: ["ticket_bound", "approval_bound", "evidence_bound"],
          dispatch_boundary: "RuntimeExecutor",
        },
      },
    },
    {
      executor_id: "cursor",
      status: "setup_blocked",
      detail: "Cursor Executor is not configured.",
      capabilities: ["agent_loop", "repo:read", "repo:write", "commercial_agent_backend"],
      supported_actions: ["answer_only", "inspect_code_repository", "append_report"],
      missing_env: ["CURSOR_API_KEY"],
      setup_url: "https://cursor.com/",
      delivery: {
        configured_mode: "http",
        supported_modes: ["http"],
        prompt_delivery: "http_json",
        default_mode: "non_destructive_inspect_and_report",
        non_destructive_default: true,
      },
      config_env: {
        model: "CURSOR_MODEL",
        api_base_url: "CURSOR_API_BASE_URL",
        api_key_env: "CURSOR_API_KEY_ENV",
        http_endpoint_path: "CURSOR_INSPECT_ENDPOINT",
      },
      expected_output_schema: {
        status: "completed | failed | blocked | needs_approval | partial | cancelled",
        report: "string",
        evidence: "list[dict]",
        artifacts: "list[dict]",
      },
      safety_policy: {
        default_mode: "non_destructive_inspect_and_report",
        repo_mutation_guard: ["ticket_bound", "approval_bound", "evidence_bound", "repo_write_capability_required"],
        completion_policy: "external_runtime_completion_must_not_be_faked",
      },
      diagnostics: {
        smoke: {
          endpoint: "/api/v1/runtime-executors/cursor/smoke",
          method: "POST",
          default_ingest_result: false,
          ingest_requires_ticket: true,
          mode: "non_destructive_inspect_and_report",
          dispatch_boundary: "RuntimeExecutor",
        },
        dogfood: {
          endpoint: "/api/v1/runtime-executors/dogfood",
          method: "POST",
          creates_ticket_if_missing: true,
          approval_required: true,
          ingest_requires_ticket: true,
          repo_mutation_guard: ["ticket_bound", "approval_bound", "evidence_bound"],
          dispatch_boundary: "RuntimeExecutor",
        },
      },
    },
  ],
  live_provider_dogfood: {
    status: "blocked",
    selected_executor_id: "local_tool",
    require_repo_write_executor: true,
    mutation_gate: {
      open: false,
      execute_flag: true,
      confirm_env_var: "AITEAMOS_LIVE_PROVIDER_DOGFOOD",
      confirm_env_configured: false,
      blocker: {
        reason: "live_provider_dogfood_not_confirmed",
        detail: "Pass --execute and set AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 to mutate live Plane / Graphiti provider state.",
        setup_required: ["--execute", "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1"],
      },
    },
    selected_executor_preflight: {
      executor_id: "local_tool",
      status: "blocked",
      capabilities: ["local_tools", "repo:read"],
      health: { status: "not_checked", reason: "repo_write_capability_missing" },
      blockers: [
        {
          reason: "runtime_executor_lacks_repo_write",
          detail: "Live provider dogfood requires a repo:write RuntimeExecutor; local_tool capabilities do not include repo:write.",
          setup_required: ["select a ready RuntimeExecutor with repo:write"],
        },
      ],
    },
    repo_write_executor_candidates: [
      {
        executor_id: "claude_code",
        display_name: "Claude Code",
        status: "setup_blocked",
        detail: "Claude Code-compatible Local CLI Executor is not configured.",
        capabilities: ["agent_loop", "repo:read", "repo:write", "compatible_local_cli"],
        setup_required: ["CLAUDE_CODE_BIN"],
        ready: false,
        health: { status: "setup_blocked" },
      },
      {
        executor_id: "codex_cli",
        display_name: "OpenAI Codex CLI Executor",
        status: "ready",
        detail: "OpenAI Codex CLI Executor is configured for non-destructive inspect-and-report execution.",
        capabilities: ["agent_loop", "repo:read", "repo:write", "commercial_agent_backend", "compatible_local_cli"],
        setup_required: [],
        ready: true,
        health: { status: "ready" },
      },
      {
        executor_id: "cursor",
        display_name: "Cursor",
        status: "setup_blocked",
        detail: "Cursor Executor is not configured.",
        capabilities: ["agent_loop", "repo:read", "repo:write", "commercial_agent_backend"],
        setup_required: ["CURSOR_API_KEY"],
        ready: false,
        health: { status: "setup_blocked" },
      },
    ],
    provider_prerequisites: {
      ticket_backend: {
        status: "setup_blocked",
        mode: "plane",
        provider: "plane",
        detail: "Plane Ticket Backend is selected but setup is incomplete.",
      },
      plane_ticket_backend_setup: {
        status: "setup_blocked",
        selected: true,
        configured: false,
        active_mode: "plane",
        active_provider: "plane",
        required_mode: "plane",
        workspace_configured: true,
        project_configured: true,
        api_key_env: "PLANE_API_KEY",
        api_key_configured: false,
        setup_required: ["PLANE_API_KEY"],
        settings_path: ".aiteamos/tickets/backend.json",
        setup_endpoint: "/api/v1/tickets/backend",
        code_repository_scope_status: "available",
        code_repository_scope_detail: "Code Repository registry has Plane workspace/project scope candidates.",
        code_repository_scope_candidate_count: 1,
        code_repository_scope_missing_count: 0,
        code_repository_scope_setup_action: "apply_code_repository_plane_scope_to_ticket_backend",
        code_repository_scope_candidates: [
          {
            source: "code_repository",
            repository_id: "repo-aiteamos-afc617",
            repository_name: "AITeamOS",
            provider: "local",
            status: "ready",
            workspace_configured: true,
            project_configured: true,
            plane_workspace_slug: "ait",
            plane_project_id: "plane-project-1",
            deep_link: "#/settings/code-repositories",
          },
        ],
        code_repository_scope_missing: [] as Record<string, unknown>[],
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
        reason: "runtime_executor_lacks_repo_write",
        scope: "selected_runtime_executor",
        detail: "Live provider dogfood requires a repo:write RuntimeExecutor; local_tool capabilities do not include repo:write.",
        setup_required: ["select a ready RuntimeExecutor with repo:write"],
      },
      {
        reason: "ticket_provider_not_ready",
        scope: "ticket_backend",
        status: "setup_blocked",
        detail: "Plane Ticket Backend is selected but setup is incomplete.",
        setup_required: ["PLANE_API_KEY"],
      },
      {
        reason: "memory_provider_not_ready",
        scope: "memory_backend",
        status: "disabled",
        detail: "Graphiti is not enabled.",
        setup_required: ["Graphiti URI/user", "Graphiti Neo4j password", "OPENAI_API_KEY"],
      },
      {
        reason: "live_provider_dogfood_not_confirmed",
        scope: "mutation_gate",
        status: "confirmation_required",
        detail: "Pass --execute and set AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 to mutate live Plane / Graphiti provider state.",
        setup_required: ["--execute", "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1"],
      },
    ],
    warnings: [],
    summary: {
      blocker_count: 4,
      repo_write_candidate_count: 3,
      repo_write_ready_count: 1,
      ticket_backend_status: "setup_blocked",
      ticket_backend_mode: "plane",
      ticket_backend_provider: "plane",
      plane_ticket_backend_selected: true,
      plane_ticket_backend_setup_status: "setup_blocked",
      plane_ticket_backend_setup_required: ["PLANE_API_KEY"],
      plane_ticket_backend_configured: false,
      plane_ticket_workspace_configured: true,
      plane_ticket_project_configured: true,
      plane_ticket_api_key_configured: false,
      plane_ticket_scope_status: "available",
      plane_ticket_scope_candidate_count: 1,
      plane_ticket_scope_missing_count: 0,
      plane_ticket_scope_setup_action: "apply_code_repository_plane_scope_to_ticket_backend",
      ticket_backend_release_target_status: "blocked",
      ticket_backend_release_target_ready: false,
      ticket_backend_release_target_blockers: ["plane_api_key_missing"],
      ticket_backend_release_target_setup_action: "configure_plane_ticket_backend",
      memory_backend_status: "disabled",
      anti_wheel_boundary: "readiness reuses RuntimeExecutor health plus Ticket and Graphiti provider status",
    },
  },
  live_provider_soak_plan: {
    contract_version: "aiteamos_live_provider_soak_plan.v1",
    status: "blocked",
    detail: "Live provider soak plan is prepared, but live writes are blocked until the mutation gate is explicitly opened.",
    summary: {
      scenario_count: 6,
      ready_scenario_count: 0,
      blocked_scenario_count: 6,
      expected_state_count: 6,
      expected_states: ["completed", "handoff", "approval", "blocked", "preflight", "retry"],
      mutation_gate_open: false,
      ticket_backend_status: "setup_blocked",
      ticket_backend_mode: "plane",
      ticket_backend_provider: "plane",
      plane_ticket_backend_selected: true,
      plane_ticket_backend_setup_status: "setup_blocked",
      plane_ticket_backend_setup_required: ["PLANE_API_KEY"],
      plane_ticket_scope_status: "available",
      plane_ticket_scope_candidate_count: 1,
      plane_ticket_scope_missing_count: 0,
      plane_ticket_scope_setup_action: "apply_code_repository_plane_scope_to_ticket_backend",
      memory_backend_status: "disabled",
      selected_executor_id: "local_tool",
      ready_to_execute: false,
      contract_version: "aiteamos_live_provider_soak_plan.v1",
    },
    blockers: [
      "runtime_executor_lacks_repo_write",
      "ticket_provider_not_ready",
      "memory_provider_not_ready",
      "live_provider_dogfood_not_confirmed",
    ],
    scenarios: [
      {
        id: "core_loop_completed_closeout_asset",
        title: "Completed closeout with Asset proposal",
        expected_state: "completed",
        status: "blocked",
        detail: "Fresh Agent Server core loop creates or advances a Ticket, writes report/evidence, promotes governed Asset evidence, projects to Graphiti, and recalls it.",
        command: "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --output .aiteamos/artifacts/plan_v8/track-c-live-soak-completed.json",
        required_evidence: ["fresh_agent_server", "ticket_report", "memory_candidate_ids", "asset_record_ids", "graphiti_projection_statuses"],
        ui_surfaces: ["Chat", "Tickets", "Assets", "Runtime Replay", "System Status"],
        blockers: ["live_provider_dogfood_not_confirmed"],
      },
      {
        id: "natural_handoff",
        title: "Natural Employee handoff",
        expected_state: "handoff",
        status: "blocked",
        detail: "Core loop records a durable Ticket-backed handoff from Clara to the worker Employee and exposes the handoff in Chat/Ticket/Employee state.",
        command: "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --require-natural-handoff --expected-handoff-target alex --output .aiteamos/artifacts/plan_v8/track-c-live-soak-handoff.json",
        required_evidence: ["handoff_summary", "ticket_handoff_refs", "natural_handoff", "handoff_target_employee_id"],
        ui_surfaces: ["Chat", "Tickets", "Employees", "Runtime Replay"],
        blockers: ["live_provider_dogfood_not_confirmed"],
      },
      {
        id: "approval_and_asset_governance",
        title: "Approval and Asset governance",
        expected_state: "approval",
        status: "blocked",
        detail: "Runtime execution remains approval-bound, evidence-bound, and review-bound before durable Asset/Memory promotion.",
        command: "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --output .aiteamos/artifacts/plan_v8/track-c-live-soak-approval-assets.json",
        required_evidence: ["approval_id", "approved_run", "summary_report", "asset_reviews", "approved_memory"],
        ui_surfaces: ["Chat", "Assets", "Runtime Replay", "System Status"],
        blockers: ["live_provider_dogfood_not_confirmed"],
      },
      {
        id: "provider_blocker_visibility",
        title: "Provider blocker visibility",
        expected_state: "blocked",
        status: "blocked",
        detail: "Provider failure must surface as a governed blocker instead of being hidden by answer-only summaries, repo-write adapters, or direct LLM fallback.",
        command: "python scripts/live_provider_readiness_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-readiness-smoke.json",
        required_evidence: ["blocker_reasons", "blocker_scopes", "ticket_backend_status", "memory_backend_status"],
        ui_surfaces: ["Chat", "Tickets", "System Status"],
        blockers: ["live_provider_dogfood_not_confirmed"],
      },
      {
        id: "plane_ticket_action_preflight",
        title: "Plane Ticket action-smoke preflight",
        expected_state: "preflight",
        status: "blocked",
        detail: "Gated Ticket provider action smoke verifies the Plane handoff/report write path is explicit and mutation-gated before full live dogfood.",
        command: "python scripts/plane_ticket_action_smoke.py --workspace-dir . --source-run-id plan-v8-plane-action-smoke --output .aiteamos/artifacts/plan_v8/track-c-plane-ticket-action-smoke.json",
        required_evidence: ["ticket_backend_status", "plane_action_smoke_guard", "confirm_env_var"],
        ui_surfaces: ["Tickets", "System Status"],
        blockers: ["live_provider_dogfood_not_confirmed"],
      },
      {
        id: "retry_resume_closeout",
        title: "Retry, resume, and closeout settlement",
        expected_state: "retry",
        status: "blocked",
        detail: "Deterministic queue-worker soak preserves retry causes, Ticket refs, queue reliability, failure-retrospective Asset candidates, and daemon settlement while live provider closeout remains covered by the live dogfood artifacts.",
        command: "python scripts/ticket_loop_queue_worker_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-ticket-loop-worker-soak.json",
        required_evidence: ["retry_cause", "ticket_report", "queue_reliability", "failure_retrospective_candidate", "daemon_resume_settlement"],
        ui_surfaces: ["Chat", "Tickets", "Runtime Replay", "System Status"],
        blockers: ["live_provider_dogfood_not_confirmed"],
      },
    ],
    commands: [
      "python scripts/live_provider_soak_plan.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-soak-plan.json",
      "python scripts/live_provider_readiness_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-readiness-smoke.json",
      "python scripts/plane_ticket_action_smoke.py --workspace-dir . --source-run-id plan-v8-plane-action-smoke --output .aiteamos/artifacts/plan_v8/track-c-plane-ticket-action-smoke.json",
      "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --output .aiteamos/artifacts/plan_v8/track-c-live-soak-completed.json",
      "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --require-natural-handoff --expected-handoff-target alex --output .aiteamos/artifacts/plan_v8/track-c-live-soak-handoff.json",
      "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --output .aiteamos/artifacts/plan_v8/track-c-live-soak-approval-assets.json",
      "python scripts/ticket_loop_queue_worker_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-ticket-loop-worker-soak.json",
    ],
    evidence_refs: ["track-c-agent-server-smoke.json", "track-c-live-provider-readiness.json"],
  },
  live_provider_soak_evidence: {
    contract_version: "aiteamos_live_provider_soak_evidence.v1",
    status: "blocked",
    detail: "Repeated live-provider soak evidence is blocked by 1 readiness signal(s).",
    summary: {
      scenario_count: 6,
      passed_scenario_count: 3,
      blocked_scenario_count: 3,
      failed_scenario_count: 0,
      missing_scenario_count: 0,
      warning_scenario_count: 0,
      latest_generated_at: "",
      mutation_gate_open: false,
      ready_to_execute: false,
      ready_for_release: false,
      live_write_scenario_count: 3,
      remaining_live_write_scenario_count: 3,
      passed_non_mutating_scenario_count: 3,
      operator_action_required: true,
      operator_action: "Explicitly set AITEAMOS_LIVE_PROVIDER_DOGFOOD=1, then run the remaining 3 live provider soak command(s).",
      mutation_gate_env_var: "AITEAMOS_LIVE_PROVIDER_DOGFOOD",
      live_write_targets: [
        "Plane Ticket reports / comments",
        "LangGraph Agent Server thread / run state",
        "Runtime approval records",
        "Asset reviews and approved records",
        "Graphiti projection / recall",
      ],
      contract_version: "aiteamos_live_provider_soak_evidence.v1",
    },
    blockers: ["live_provider_dogfood_not_confirmed"],
    scenarios: [
      {
        id: "core_loop_completed_closeout_asset",
        title: "Completed closeout with Asset proposal",
        expected_state: "completed",
        status: "blocked",
        detail: "Execution evidence is waiting on the live mutation gate.",
        command: "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --output .aiteamos/artifacts/plan_v8/track-c-live-soak-completed.json",
        execution_kind: "live_provider_write",
        operator_action: "open_live_mutation_gate_and_run_command",
        artifact_name: "track-c-live-soak-completed.json",
        artifact_path: "",
        artifact_schema: "",
        artifact_status: "",
        generated_at: "",
        required_evidence: ["fresh_agent_server", "ticket_report", "memory_candidate_ids", "asset_record_ids"],
        observed_evidence: [],
        missing_evidence: ["fresh_agent_server", "ticket_report", "memory_candidate_ids", "asset_record_ids"],
        blockers: ["live_provider_dogfood_not_confirmed"],
        ui_surfaces: ["Chat", "Tickets", "Assets", "Runtime Replay", "System Status"],
      },
      {
        id: "natural_handoff",
        title: "Natural Employee handoff",
        expected_state: "handoff",
        status: "blocked",
        detail: "Execution evidence is waiting on the live mutation gate.",
        command: "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --require-natural-handoff --expected-handoff-target alex --output .aiteamos/artifacts/plan_v8/track-c-live-soak-handoff.json",
        execution_kind: "live_provider_write",
        operator_action: "open_live_mutation_gate_and_run_command",
        artifact_name: "track-c-live-soak-handoff.json",
        artifact_path: "",
        artifact_schema: "",
        artifact_status: "",
        generated_at: "",
        required_evidence: ["handoff_summary", "ticket_handoff_refs", "natural_handoff", "handoff_target_employee_id"],
        observed_evidence: [],
        missing_evidence: ["handoff_summary", "ticket_handoff_refs", "natural_handoff", "handoff_target_employee_id"],
        blockers: ["live_provider_dogfood_not_confirmed"],
        ui_surfaces: ["Chat", "Tickets", "Employees", "Runtime Replay"],
      },
      {
        id: "approval_and_asset_governance",
        title: "Approval and Asset governance",
        expected_state: "approval",
        status: "blocked",
        detail: "Execution evidence is waiting on the live mutation gate.",
        command: "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --output .aiteamos/artifacts/plan_v8/track-c-live-soak-approval-assets.json",
        execution_kind: "live_provider_write",
        operator_action: "open_live_mutation_gate_and_run_command",
        artifact_name: "track-c-live-soak-approval-assets.json",
        artifact_path: "",
        artifact_schema: "",
        artifact_status: "",
        generated_at: "",
        required_evidence: ["approval_id", "approved_run", "summary_report", "asset_reviews", "approved_memory"],
        observed_evidence: [],
        missing_evidence: ["approval_id", "approved_run", "summary_report", "asset_reviews", "approved_memory"],
        blockers: ["live_provider_dogfood_not_confirmed"],
        ui_surfaces: ["Chat", "Assets", "Runtime Replay", "System Status"],
      },
      {
        id: "provider_blocker_visibility",
        title: "Provider blocker visibility",
        expected_state: "blocked",
        status: "passed",
        detail: "Soak artifact satisfies the expected governed blocker evidence for this scenario.",
        command: "python scripts/live_provider_readiness_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-readiness-smoke.json",
        execution_kind: "read_only_provider_blocker_smoke",
        operator_action: "covered",
        artifact_name: "track-c-live-provider-readiness-smoke.json",
        artifact_path: ".aiteamos/artifacts/plan_v8/track-c-live-provider-readiness-smoke.json",
        artifact_schema: "aiteamos.live_provider_readiness_smoke.v1",
        artifact_status: "blocked",
        generated_at: "2026-06-21T03:22:59Z",
        required_evidence: ["blocker_reasons", "blocker_scopes", "ticket_backend_status", "memory_backend_status", "provider_smoke_status"],
        observed_evidence: ["blocker_reasons", "blocker_scopes", "ticket_backend_status", "memory_backend_status", "provider_smoke_status"],
        missing_evidence: [],
        blockers: ["live_provider_dogfood_not_confirmed"],
        ui_surfaces: ["Chat", "Tickets", "System Status"],
      },
      {
        id: "plane_ticket_action_preflight",
        title: "Plane Ticket action-smoke preflight",
        expected_state: "preflight",
        status: "passed",
        detail: "Soak artifact proves the provider action path is present and mutation-gated.",
        command: "python scripts/plane_ticket_action_smoke.py --workspace-dir . --source-run-id plan-v8-plane-action-smoke --output .aiteamos/artifacts/plan_v8/track-c-plane-ticket-action-smoke.json",
        execution_kind: "gated_provider_action_smoke",
        operator_action: "covered",
        artifact_name: "track-c-plane-ticket-action-smoke.json",
        artifact_path: ".aiteamos/artifacts/plan_v8/track-c-plane-ticket-action-smoke.json",
        artifact_schema: "aiteamos.plane_ticket_action_smoke.v1",
        artifact_status: "dry_run",
        generated_at: "2026-06-21T03:23:30Z",
        required_evidence: ["ticket_backend_status", "plane_action_smoke_guard", "confirm_env_var"],
        observed_evidence: ["ticket_backend_status", "plane_action_smoke_guard", "confirm_env_var"],
        missing_evidence: [],
        blockers: ["plane_action_smoke_not_confirmed"],
        ui_surfaces: ["Tickets", "System Status"],
      },
      {
        id: "retry_resume_closeout",
        title: "Retry, resume, and closeout settlement",
        expected_state: "retry",
        status: "passed",
        detail: "Soak artifact satisfies the required evidence for this scenario.",
        command: "python scripts/ticket_loop_queue_worker_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-ticket-loop-worker-soak.json",
        execution_kind: "local_queue_worker",
        operator_action: "covered",
        artifact_name: "track-c-ticket-loop-worker-soak.json",
        artifact_path: ".aiteamos/artifacts/plan_v8/track-c-ticket-loop-worker-soak.json",
        artifact_schema: "aiteamos.ticket_loop_queue_worker_smoke.v2",
        artifact_status: "passed",
        generated_at: "2026-06-21T15:22:34Z",
        required_evidence: ["retry_cause", "ticket_report", "queue_reliability", "failure_retrospective_candidate", "daemon_resume_settlement"],
        observed_evidence: ["retry_cause", "ticket_report", "queue_reliability", "failure_retrospective_candidate", "daemon_resume_settlement"],
        missing_evidence: [],
        blockers: [],
        ui_surfaces: ["Chat", "Tickets", "Runtime Replay", "System Status"],
      },
    ],
    commands: [
      "python scripts/live_provider_soak_evidence.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-soak-evidence.json",
      "python scripts/live_provider_soak_plan.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-soak-plan.json",
      "python scripts/plane_ticket_action_smoke.py --workspace-dir . --source-run-id plan-v8-plane-action-smoke --output .aiteamos/artifacts/plan_v8/track-c-plane-ticket-action-smoke.json",
      "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --output .aiteamos/artifacts/plan_v8/track-c-live-soak-completed.json",
      "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --require-natural-handoff --expected-handoff-target alex --output .aiteamos/artifacts/plan_v8/track-c-live-soak-handoff.json",
      "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --output .aiteamos/artifacts/plan_v8/track-c-live-soak-approval-assets.json",
      "python scripts/ticket_loop_queue_worker_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-ticket-loop-worker-soak.json",
    ],
    evidence_refs: ["track-c-live-provider-readiness-smoke.json", "track-c-plane-ticket-action-smoke.json", "track-c-ticket-loop-worker-soak.json"],
  },
  provider_conformance: {
    contract_version: "provider_conformance.v1",
    summary: {
      provider_count: 6,
      ready_count: 3,
      blocked_count: 3,
      selected_provider_count: 6,
      core_required_count: 5,
      production_ready_count: 2,
      core_blocked_count: 3,
      optional_warning_count: 1,
      runtime_boundary_status: "passed",
      runtime_boundary_checks: [
        "chat_route_transport_adapter",
        "chat_runtime_factory_route_free",
        "chat_execution_service_contract_boundary",
        "workbench_runtime_context_contract_boundary",
        "workbench_context_node_route_free_services",
        "workbench_governance_node_route_free_services",
        "graphiti_memory_provider_langchain_boundary",
      ],
      runtime_boundary_warnings: [],
      runtime_boundary_blockers: [],
      contract_version: "provider_conformance.v1",
      core_model_boundary: "Ticket / Employee / Asset models remain AITeamOS-owned; providers are projections or execution adapters.",
    },
    providers: [
      {
        provider_id: "ticket:plane",
        provider_kind: "ticket",
        implementation: "plane",
        display_name: "Plane Ticket Provider",
        selected: true,
        status: "setup_blocked",
        detail: "Plane Ticket Backend is selected but setup is incomplete.",
        setup_blockers: [
          {
            id: "ticket:plane:setup",
            status: "setup_blocked",
            detail: "Plane Ticket Backend is selected but setup is incomplete.",
            setup_required: ["plane_workspace_slug", "plane_project_id", "PLANE_API_KEY"],
          },
        ],
        capabilities: ["setup_blocker", "create_ticket", "append_report", "handoff", "validation_projection"],
        conformance_smoke: {
          kind: "status_check",
          endpoint: "/api/v1/tickets/status",
          method: "GET",
          write_policy: "ticket_writes_must_use_ticket_service_adapter",
          non_destructive: true,
        },
        projection_direction: [
          "AITeamOS Ticket -> provider issue/task",
          "AITeamOS Ticket report -> provider comment",
        ],
        failure_semantics: [
          "missing_config_reports_setup_blocker",
          "provider_error_must_not_mark_ticket_completed",
        ],
        domain_boundary: ["provider_ref is a projection pointer, not the domain object"],
        contract_expectations: [
          {
            id: "ticket.required_capabilities",
            category: "capabilities",
            required: ["create_ticket", "append_report", "handoff", "validation_projection"],
            satisfied: ["create_ticket", "append_report", "handoff", "validation_projection"],
            missing: [],
            status: "passed",
          },
        ],
        production_evaluation: {
          schema_version: "provider_conformance.v1",
          migration_status: "schema_current",
          required_for_core: true,
          production_ready: false,
          readiness_level: "degraded_with_fallback",
          blockers: ["ticket:plane:setup"],
          warnings: [],
        },
        fallback_provider: "ticket:local_file",
        provider_ref: { provider: "plane" },
      },
      {
        provider_id: "asset:local_registry",
        provider_kind: "asset",
        implementation: "local_registry",
        display_name: "Local Asset Registry",
        selected: true,
        status: "ready",
        detail: "Local Asset Candidate registry is available.",
        setup_blockers: [],
        capabilities: ["asset_candidate_registry", "review_state_tracking", "local_fallback"],
        conformance_smoke: {
          kind: "status_check",
          endpoint: "/api/v1/assets/candidates",
          method: "GET",
        },
        projection_direction: ["governed artifact -> AssetCandidate"],
        failure_semantics: ["external_asset_graph_disabled_keeps_local_registry_available"],
        domain_boundary: ["Assets are AITeamOS-owned long-term records"],
        production_evaluation: {
          schema_version: "provider_conformance.v1",
          migration_status: "schema_current",
          required_for_core: true,
          production_ready: true,
          readiness_level: "production_ready",
          blockers: [],
          warnings: [],
        },
        fallback_provider: "",
        provider_ref: { provider: "local_file" },
      },
      {
        provider_id: "employee:local_profiles",
        provider_kind: "employee",
        implementation: "local_profiles",
        display_name: "Local Employee Profiles",
        selected: true,
        status: "ready",
        detail: "Employee identities are local AITeamOS records.",
        setup_blockers: [],
        capabilities: ["fixed_employee_identity", "permission_policy", "memory_scopes"],
        conformance_smoke: {
          kind: "status_check",
          endpoint: "/api/v1/chat/employees",
          method: "GET",
        },
        projection_direction: ["Employee profile -> runtime context"],
        failure_semantics: ["permission_policy_controls_tool_and_runtime_access"],
        domain_boundary: ["Employee is a fixed AITeamOS identity"],
        fallback_provider: "",
        provider_ref: { provider: "local_file" },
      },
      {
        provider_id: "memory:graphiti",
        provider_kind: "memory",
        implementation: "graphiti",
        display_name: "Graphiti Memory / Asset Graph Provider",
        selected: true,
        status: "disabled",
        detail: "Graphiti is not enabled.",
        setup_blockers: [
          {
            id: "memory:graphiti:setup",
            status: "disabled",
            detail: "Graphiti is not enabled.",
            setup_required: ["Graphiti enabled", "AITEAMOS_GRAPHITI_PASSWORD, NEO4J_PASSWORD, or AITEAMOS_NEO4J_PASSWORD"],
          },
        ],
        capabilities: ["approved_asset_projection", "memory_recall", "relationship_search"],
        conformance_smoke: {
          kind: "status_check",
          endpoint: "/api/v1/memory/status",
          method: "GET",
          projection_endpoints: ["/api/v1/memory/graphiti/durable-assets"],
        },
        projection_direction: ["approved AITeamOS Asset/Memory -> Graphiti episode"],
        failure_semantics: ["disabled_graphiti_keeps_local_asset_and_memory_registry_available"],
        domain_boundary: ["Graphiti is a projection/search provider, not the source of truth"],
        fallback_provider: "asset:local_registry",
        provider_ref: { provider: "graphiti" },
      },
      {
        provider_id: "runtime:claude_code",
        provider_kind: "runtime",
        implementation: "claude_code",
        display_name: "Claude Code Runtime Provider",
        selected: true,
        status: "setup_blocked",
        detail: "Claude Code-compatible Local CLI Executor is not configured.",
        setup_blockers: [
          {
            id: "runtime:claude_code:setup",
            status: "setup_blocked",
            detail: "Set CLAUDE_CODE_BIN.",
            setup_required: ["CLAUDE_CODE_BIN"],
          },
        ],
        capabilities: ["agent_loop", "repo:read", "repo:write", "compatible_local_cli"],
        conformance_smoke: {
          kind: "runtime_executor_smoke",
          endpoint: "/api/v1/runtime-executors/claude_code/smoke",
          method: "POST",
          batch_endpoint: "/api/v1/runtime-executors/smoke-batch",
        },
        projection_direction: [
          "ExecutionRequest -> RuntimeProvider",
          "RuntimeProvider result -> ExecutionResult",
          "ExecutionResult -> Ticket report / evidence / Asset candidates through ingestion",
        ],
        failure_semantics: [
          "setup_blocked_returns_blocked_execution_result",
          "external_runtime_completion_must_not_be_faked",
          "repo_write_requires_approval",
        ],
        domain_boundary: ["Chat route remains entry/bridge, not an agent loop"],
        fallback_provider: "runtime:universal_employee_agent",
        provider_ref: { executor_id: "claude_code" },
      },
      {
        provider_id: "runtime:langgraph",
        provider_kind: "runtime",
        implementation: "langgraph",
        display_name: "LangGraph Runtime Provider",
        selected: true,
        status: "ready",
        detail: "LangGraph core runtime is configured.",
        setup_blockers: [],
        capabilities: ["answer_only", "create_ticket", "append_report"],
        conformance_smoke: {
          kind: "runtime_executor_smoke",
          endpoint: "/api/v1/runtime-executors/langgraph/smoke",
          method: "POST",
        },
        projection_direction: ["ExecutionRequest -> RuntimeProvider"],
        failure_semantics: ["setup_blocked_returns_blocked_execution_result"],
        domain_boundary: ["RuntimeProvider executes behind ExecutionRequest/ExecutionResult"],
        fallback_provider: "runtime:universal_employee_agent",
        provider_ref: { executor_id: "langgraph" },
      },
    ],
  },
  schema_registry: {
    contract_version: "aiteamos_schema_registry.v1",
    status: "warning",
    summary: {
      store_count: 4,
      current_count: 3,
      missing_count: 1,
      legacy_count: 0,
      invalid_count: 0,
      migration_required_count: 0,
      contract_version: "aiteamos_schema_registry.v1",
      covered_domains: ["assets", "employees", "runtime", "tickets"],
    },
    stores: [
      {
        id: "execution.sessions",
        domain: "runtime",
        display_name: "Execution Sessions",
        provider: "local_file",
        schema_version: "execution_sessions.v1",
        expected_shape: "object map keyed by employee_id::thread_id::ticket_id",
        actual_shape: "object_map",
        path: ".aiteamos/execution_sessions.json",
        status: "current",
        migration_status: "schema_current",
        migration_required: false,
        item_count: 2,
        exists: true,
        checks: ["schema:execution_sessions.v1", "path_exists", "json_loaded", "shape:object_map"],
        warnings: [],
        blockers: [],
        provenance_boundary: "Runtime sessions correlate Employee, Ticket, checkpoint, approval, tool events, and replay refs.",
        migration_strategy: "read-compatible; migrate by explicit future writer, not implicit status read",
      },
      {
        id: "assets.candidates",
        domain: "assets",
        display_name: "Asset Candidates",
        provider: "local_file",
        schema_version: "asset_candidates.v1",
        expected_shape: "list[AssetCandidateRecord]",
        actual_shape: "missing",
        path: ".aiteamos/assets/candidates.json",
        status: "missing",
        migration_status: "not_created_yet",
        migration_required: false,
        item_count: 0,
        exists: false,
        checks: ["schema:asset_candidates.v1", "path_missing_allowed"],
        warnings: [],
        blockers: [],
        provenance_boundary: "Governed runtime artifacts enter long-term Assets through candidate review.",
        migration_strategy: "read-compatible; migrate by explicit future writer, not implicit status read",
      },
      {
        id: "employees.local_profiles",
        domain: "employees",
        display_name: "Local Employee Profiles",
        provider: "local_file",
        schema_version: "employee_profiles.v1",
        expected_shape: "directory of YAML Employee profiles",
        actual_shape: "directory",
        path: ".aiteamos/employees",
        status: "current",
        migration_status: "schema_current",
        migration_required: false,
        item_count: 1,
        exists: true,
        checks: ["schema:employee_profiles.v1", "path_exists", "shape:directory"],
        warnings: [],
        blockers: [],
        provenance_boundary: "Employees remain fixed AITeamOS identities; providers may execute for them but cannot redefine them.",
        migration_strategy: "file-backed YAML profiles; future provider adapters project from this source of truth",
      },
      {
        id: "tickets.projection",
        domain: "tickets",
        display_name: "Ticket Projection Index",
        provider: "local_file",
        schema_version: "ticket_projection.v1",
        expected_shape: "list[Ticket]",
        actual_shape: "list",
        path: ".aiteamos/tickets/index.json",
        status: "current",
        migration_status: "schema_current",
        migration_required: false,
        item_count: 0,
        exists: true,
        checks: ["schema:ticket_projection.v1", "path_exists", "json_loaded", "shape:list"],
        warnings: [],
        blockers: [],
        provenance_boundary: "Tickets are the collaboration, handoff, report, validation, and closeout channel.",
        migration_strategy: "read-compatible; migrate by explicit future writer, not implicit status read",
      },
    ],
    saved_paths: { workspace: ".aiteamos" },
  },
  plan_v8_artifacts: {
    artifact_dir: ".aiteamos/artifacts/plan_v8",
    status: "warning",
    artifact_count: 8,
    agent_server_smoke_count: 1,
    chat_visible_response_matrix_count: 1,
    live_provider_readiness_count: 1,
    live_provider_soak_plan_count: 0,
    live_provider_soak_evidence_count: 1,
    plane_scope_discovery_smoke_count: 1,
    plane_ticket_action_smoke_count: 1,
    ticket_loop_worker_soak_count: 1,
    context_retrieval_eval_count: 0,
    asset_provenance_eval_count: 0,
    plan_v8_readiness_count: 1,
    employee_growth_eval_count: 1,
    latest_generated_at: "2026-06-21T03:25:00Z",
    latest_agent_server_smoke: {
      name: "track-c-agent-server-smoke.json",
      path: ".aiteamos/artifacts/plan_v8/track-c-agent-server-smoke.json",
      kind: "agent_server_smoke",
      status: "passed",
      generated_at: "2026-06-21T03:20:00Z",
      summary: {
        assistant_id: "aiteamos_workbench",
        runtime_status: "completed",
        current_node: "final_response",
        visible_response_version: "chat_visible_response.v1",
        visible_display_state: "completed",
        provider_blocker_count: 0,
        provider_blocker_reasons: [],
      },
    },
    latest_chat_visible_response_matrix: {
      name: "track-a-chat-visible-response-matrix.json",
      path: ".aiteamos/artifacts/plan_v8/track-a-chat-visible-response-matrix.json",
      kind: "chat_visible_response_matrix",
      status: "passed",
      generated_at: "2026-06-21T03:20:30Z",
      summary: {
        case_count: 5,
        passed_case_count: 5,
        failed_case_count: 0,
        required_states: ["completed", "blocked", "needs_approval", "handoff", "provider_blocker"],
        observed_states: ["completed", "blocked", "needs_approval", "handoff", "provider_blocker"],
        missing_states: [],
        assistant_reply_visible_count: 5,
        runtime_status_visible_count: 5,
        blocked_reason_visible_count: 2,
        retry_cause_visible_count: 1,
        approval_request_visible_count: 1,
        handoff_visible_count: 1,
        provider_blocker_visible_count: 1,
      },
    },
    latest_live_provider_readiness: {
      name: "track-c-live-provider-readiness.json",
      path: ".aiteamos/artifacts/plan_v8/track-c-live-provider-readiness.json",
      kind: "live_provider_readiness",
      status: "passed",
      generated_at: "2026-06-21T03:19:00Z",
      summary: {
        readiness_status: "blocked",
        profile: "core_loop",
        selected_executor_id: "langgraph",
        repo_write_ready_count: 1,
        repo_write_candidate_count: 3,
        ticket_backend_status: "setup_blocked",
        ticket_backend_release_target_status: "blocked",
        ticket_backend_release_target_ready: false,
        ticket_backend_release_target_blockers: ["plane_api_key_missing"],
        ticket_backend_release_target_setup_action: "configure_plane_ticket_backend",
        memory_backend_status: "disabled",
        provider_smoke_status: "not_run",
        mutation_gate_open: false,
        blocker_count: 2,
        blocker_reasons: ["ticket_provider_not_ready", "memory_provider_not_ready"],
        blocker_scopes: ["ticket_backend", "memory_backend"],
      },
    },
    latest_live_provider_soak_evidence: {
      name: "track-c-live-provider-soak-evidence.json",
      path: ".aiteamos/artifacts/plan_v8/track-c-live-provider-soak-evidence.json",
      kind: "live_provider_soak_evidence",
      status: "blocked",
      generated_at: "2026-06-21T03:23:00Z",
      summary: {
        ready_for_release: false,
        scenario_count: 6,
        passed_scenario_count: 3,
        blocked_scenario_count: 3,
        failed_scenario_count: 0,
        missing_scenario_count: 0,
        warning_scenario_count: 0,
        mutation_gate_open: false,
        live_write_scenario_count: 3,
        remaining_live_write_scenario_count: 3,
        passed_non_mutating_scenario_count: 3,
        operator_action_required: true,
        latest_generated_at: "",
        blockers: ["live_provider_dogfood_not_confirmed"],
      },
    },
    latest_plane_scope_discovery_smoke: {
      name: "track-c-plane-scope-discovery-smoke.json",
      path: ".aiteamos/artifacts/plan_v8/track-c-plane-scope-discovery-smoke.json",
      kind: "plane_scope_discovery_smoke",
      status: "passed",
      generated_at: "2026-06-21T03:23:20Z",
      summary: {
        discovery_status: "ready",
        detail: "Plane scope discovery found workspace/project candidates.",
        api_key_env: "PLANE_API_KEY",
        api_key_configured: true,
        external_calls: true,
        external_mutation: false,
        workspace_count: 1,
        project_count: 1,
        suggestion_count: 1,
        first_workspace_slug: "ait",
        first_project_id: "plane-project-1",
        first_workspace_name: "AITeamOS",
        first_project_name: "Core Loop",
        checks: ["plane_workspace_list_requested", "plane_project_list_requested"],
        setup_required: [],
      },
    },
    latest_plane_ticket_action_smoke: {
      name: "track-c-plane-ticket-action-smoke.json",
      path: ".aiteamos/artifacts/plan_v8/track-c-plane-ticket-action-smoke.json",
      kind: "plane_ticket_action_smoke",
      status: "dry_run",
      generated_at: "2026-06-21T03:23:30Z",
      summary: {
        provider: "plane",
        ticket_backend_status: "ready",
        mutation_gate_open: false,
        confirm_env_var: "AITEAMOS_LIVE_PROVIDER_DOGFOOD",
        confirm_env_configured: false,
        ticket_id: "",
        provider_record_id: "",
        handoff_recorded: false,
        handoff_report_recorded: false,
        report_id: "",
        blocker_stage: "",
        blocker_reasons: ["plane_action_smoke_not_confirmed"],
        warnings: [],
        checks: ["plane_action_smoke_requested", "plane_action_smoke_mutation_gate_checked"],
        external_calls: false,
        mutating: false,
      },
    },
    latest_ticket_loop_worker_soak: {
      name: "track-c-ticket-loop-worker-soak.json",
      path: ".aiteamos/artifacts/plan_v8/track-c-ticket-loop-worker-soak.json",
      kind: "ticket_loop_worker_soak",
      status: "passed",
      generated_at: "2026-06-21T03:24:00Z",
      summary: {
        ticket_id: "ops-worker-soak",
        processed_statuses: ["blocked", "blocked"],
        queue_ids: ["queue-worker-1", "queue-worker-2"],
        asset_candidate_ids: ["asset-candidate-ticket-loop-failure-retrospective-ops-worker-soak"],
        asset_candidate_count: 1,
        timeline_statuses: ["assigned", "loop_queued", "blocked", "proposed"],
        after_reliability_status: "error",
        after_reliability_detail: "At least one queued loop item failed.",
        worker_status: "completed",
        worker_processed_delta: 2,
        worker_policy_action_delta: 1,
        failed_delta: 2,
        daemon_status: "passed",
        daemon_processed_delta: 2,
        daemon_tick_delta: 6,
        daemon_run_statuses: ["completed", "completed"],
        daemon_queue_statuses: ["completed", "completed"],
      },
    },
    latest_plan_v8_readiness: {
      name: "track-g-plan-v8-readiness.json",
      path: ".aiteamos/artifacts/plan_v8/track-g-plan-v8-readiness.json",
      kind: "plan_v8_readiness",
      status: "blocked",
      generated_at: "2026-06-21T03:25:00Z",
      summary: {
        ready_for_release: false,
        check_count: 6,
        passed_count: 3,
        warning_count: 2,
        blocked_count: 1,
        failed_count: 0,
        next_action: "Open the live mutation gate explicitly, then run the live provider dogfood soak against Plane and Graphiti.",
        blockers: ["live_provider_dogfood_not_confirmed"],
        evidence_refs: [
          "track-c-agent-server-smoke.json",
          "track-a-chat-visible-response-matrix.json",
          "track-c-ticket-loop-worker-soak.json",
        ],
      },
    },
    latest_employee_growth_eval: {
      name: "track-e-employee-growth-eval-smoke.json",
      path: ".aiteamos/artifacts/plan_v8/track-e-employee-growth-eval-smoke.json",
      kind: "employee_growth_eval",
      status: "passed",
      generated_at: "2026-06-21T03:24:30Z",
      summary: {
        employee_id: "alex",
        current_load_status: "needs_attention",
        active_ticket_count: 1,
        active_run_count: 1,
        current_ticket_count: 1,
        historical_ticket_count: 1,
        report_count: 2,
        handoff_count: 1,
        asset_candidate_count: 2,
        approved_asset_count: 1,
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
        provider_projection_status: "not_projected",
        graph_node_count: 4,
        graph_edge_count: 3,
        warnings: [],
        blockers: [],
      },
    },
    evidence_gaps: [],
    evidence_warnings: [],
    provider_blockers: ["ticket_provider_not_ready", "memory_provider_not_ready", "live_provider_dogfood_not_confirmed"],
    records: [
      {
        name: "track-g-plan-v8-readiness.json",
        path: ".aiteamos/artifacts/plan_v8/track-g-plan-v8-readiness.json",
        kind: "plan_v8_readiness",
        status: "blocked",
        generated_at: "2026-06-21T03:25:00Z",
        summary: {},
      },
      {
        name: "track-e-employee-growth-eval-smoke.json",
        path: ".aiteamos/artifacts/plan_v8/track-e-employee-growth-eval-smoke.json",
        kind: "employee_growth_eval",
        status: "warning",
        generated_at: "2026-06-21T03:24:30Z",
        summary: {},
      },
      {
        name: "track-c-agent-server-smoke.json",
        path: ".aiteamos/artifacts/plan_v8/track-c-agent-server-smoke.json",
        kind: "agent_server_smoke",
        status: "passed",
        generated_at: "2026-06-21T03:20:00Z",
        summary: {},
      },
      {
        name: "track-a-chat-visible-response-matrix.json",
        path: ".aiteamos/artifacts/plan_v8/track-a-chat-visible-response-matrix.json",
        kind: "chat_visible_response_matrix",
        status: "passed",
        generated_at: "2026-06-21T03:20:30Z",
        summary: {},
      },
      {
        name: "track-c-live-provider-readiness.json",
        path: ".aiteamos/artifacts/plan_v8/track-c-live-provider-readiness.json",
        kind: "live_provider_readiness",
        status: "passed",
        generated_at: "2026-06-21T03:19:00Z",
        summary: {},
      },
      {
        name: "track-c-live-provider-soak-evidence.json",
        path: ".aiteamos/artifacts/plan_v8/track-c-live-provider-soak-evidence.json",
        kind: "live_provider_soak_evidence",
        status: "blocked",
        generated_at: "2026-06-21T03:23:00Z",
        summary: {},
      },
      {
        name: "track-c-plane-ticket-action-smoke.json",
        path: ".aiteamos/artifacts/plan_v8/track-c-plane-ticket-action-smoke.json",
        kind: "plane_ticket_action_smoke",
        status: "dry_run",
        generated_at: "2026-06-21T03:23:30Z",
        summary: {},
      },
      {
        name: "track-c-ticket-loop-worker-soak.json",
        path: ".aiteamos/artifacts/plan_v8/track-c-ticket-loop-worker-soak.json",
        kind: "ticket_loop_worker_soak",
        status: "passed",
        generated_at: "2026-06-21T03:24:00Z",
        summary: {},
      },
    ],
  },
  plan_v8_readiness: {
    contract_version: "aiteamos_plan_v8_readiness.v1",
    status: "blocked",
    detail: "Plan v8 readiness is blocked by 4 signal(s).",
    summary: {
      check_count: 6,
      passed_count: 2,
      warning_count: 2,
      blocked_count: 2,
      failed_count: 0,
      ready_for_release: false,
      contract_version: "aiteamos_plan_v8_readiness.v1",
      next_action: "Complete the Code Repository Plane workspace/project scope, switch the Ticket backend to Plane, rerun the Plane action smoke, then reopen the live mutation gate for Plane / Graphiti dogfood.",
      next_steps: [
        "Open Settings -> Code Repositories and complete the AITeamOS repository Plane workspace/project scope.",
        "Open Settings -> Ticket Backend and use Apply scope or save the form with mode=plane.",
        "Run python scripts/live_provider_readiness_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-readiness-smoke.json before any provider mutation.",
        "Run python scripts/plane_ticket_action_smoke.py --workspace-dir . --source-run-id plan-v8-plane-action-smoke --output .aiteamos/artifacts/plan_v8/track-c-plane-ticket-action-smoke.json.",
        "When ready, run AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --output .aiteamos/artifacts/plan_v8/track-c-live-soak-completed.json.",
      ],
      next_step_actions: [
        {
          id: "complete_code_repository_plane_scope",
          label: "Code Repository scope",
          detail: "Open Settings -> Code Repositories, use Discover Plane scope to read workspace/project candidates without mutation, then complete the AITeamOS repository Plane scope.",
          kind: "settings",
          status: "incomplete",
          href: "#/settings/code-repositories",
          command: "",
          mutation_gate_required: false,
          evidence: {
            scope_candidates: 0,
            scope_missing: 1,
            setup_action: "add_plane_scope_to_code_repository_or_ticket_backend",
            discovery_ui_action: "Discover Plane scope",
            discovery_endpoint: "/api/v1/tickets/backend/plane-scope/discovery",
            api_key_configured: true,
            external_mutation: false,
          },
        },
        {
          id: "apply_plane_ticket_backend",
          label: "Ticket Backend Plane mode",
          detail: "Open Settings -> Ticket Backend and use Apply scope or save the form with mode=plane.",
          kind: "settings",
          status: "setup_blocked",
          href: "#/settings/ticket-backend",
          command: "",
          mutation_gate_required: false,
          evidence: {
            current_mode: "local_file",
            release_target_status: "blocked",
            release_target_ready: false,
            release_target_setup_action: "select_plane_ticket_backend",
            release_target_blockers: ["plane_ticket_backend_not_selected", "plane_workspace_slug_missing", "plane_project_id_missing"],
            current_provider: "",
            plane_selected: false,
            workspace_configured: false,
            project_configured: false,
            api_key_configured: true,
          },
        },
        {
          id: "run_live_provider_readiness_smoke",
          label: "Provider readiness smoke",
          detail: "Run python scripts/live_provider_readiness_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-readiness-smoke.json before any provider mutation.",
          kind: "command",
          status: "ready_to_run",
          href: "",
          command: "python scripts/live_provider_readiness_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-readiness-smoke.json",
          mutation_gate_required: false,
          evidence: {
            external_mutation: false,
            provider_smoke_status: "read_only",
          },
        },
        {
          id: "run_plane_action_smoke",
          label: "Plane action smoke",
          detail: "Run python scripts/plane_ticket_action_smoke.py --workspace-dir . --source-run-id plan-v8-plane-action-smoke --output .aiteamos/artifacts/plan_v8/track-c-plane-ticket-action-smoke.json.",
          kind: "command",
          status: "blocked",
          href: "",
          command: "python scripts/plane_ticket_action_smoke.py --workspace-dir . --source-run-id plan-v8-plane-action-smoke --output .aiteamos/artifacts/plan_v8/track-c-plane-ticket-action-smoke.json",
          mutation_gate_required: false,
          evidence: {
            requires_ticket_backend_mode: "plane",
            current_mode: "local_file",
          },
        },
        {
          id: "keep_mutation_gate_closed",
          label: "Mutation gate",
          detail: "Keep AITEAMOS_LIVE_PROVIDER_DOGFOOD unset until Plane and Graphiti setup evidence is ready.",
          kind: "guard",
          status: "closed",
          href: "",
          command: "unset AITEAMOS_LIVE_PROVIDER_DOGFOOD",
          mutation_gate_required: true,
          evidence: {
            gate_open: false,
            confirm_env_var: "AITEAMOS_LIVE_PROVIDER_DOGFOOD",
          },
        },
        {
          id: "run_live_provider_dogfood",
          label: "Live dogfood soak",
          detail: "When ready, run AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --output .aiteamos/artifacts/plan_v8/track-c-live-soak-completed.json.",
          kind: "command",
          status: "blocked",
          href: "",
          command: "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --output .aiteamos/artifacts/plan_v8/track-c-live-soak-completed.json",
          mutation_gate_required: true,
          evidence: {
            requires_gate_open: true,
            gate_open: false,
          },
        },
      ],
    },
    checks: [
      {
        id: "chat_visible_response",
        scope: "Track A",
        status: "passed",
        detail: "Chat main-thread visible response contract from fresh Agent Server evidence plus the five-state visible-response matrix.",
        blockers: [],
        evidence: {
          visible_response_version: "chat_visible_response.v1",
          visible_display_state: "completed",
          matrix_artifact: "track-a-chat-visible-response-matrix.json",
          matrix_passed_case_count: 5,
          matrix_observed_states: ["completed", "blocked", "needs_approval", "handoff", "provider_blocker"],
        },
      },
      {
        id: "plan_v8_artifact_evidence",
        scope: "Track C/F/G",
        status: "warning",
        detail: "Latest plan_v8 artifact summary for Agent Server, live readiness, context retrieval, and Asset provenance.",
        blockers: ["ticket_provider_not_ready", "memory_provider_not_ready"],
        evidence: {
          artifact_count: 2,
          plane_scope_discovery_smoke_count: 1,
          plane_scope_discovery_smoke_status: "passed",
          plane_scope_discovery_status: "ready",
          plane_scope_discovery_suggestion_count: 1,
          plane_scope_discovery_external_mutation: false,
          plane_ticket_action_smoke_count: 1,
          plane_ticket_action_smoke_status: "dry_run",
          plane_ticket_action_smoke_provider: "plane",
          employee_growth_eval_count: 1,
          employee_growth_warning_count: 0,
          employee_growth_improvement_loop_proof_status: "passed",
          employee_growth_improvement_loop_application_status: "applied",
        },
      },
      {
        id: "live_provider_dogfood",
        scope: "Track C",
        status: "blocked",
        detail: "Readiness for the live Plane / Graphiti Ticket-loop dogfood gate.",
        blockers: ["ticket_provider_not_ready", "memory_provider_not_ready", "live_provider_dogfood_not_confirmed"],
        evidence: { selected_executor_id: "langgraph", mutation_gate_open: false },
      },
      {
        id: "provider_boundary",
        scope: "Track B/C",
        status: "blocked",
        detail: "Provider conformance keeps Ticket / Employee / Asset facts AITeamOS-owned and runtime behind LangGraph/RuntimeExecutor boundaries.",
        blockers: ["core_provider_not_production_ready"],
        evidence: {
          direct_llm_provider_count: 0,
          runtime_boundary_status: "passed",
          runtime_boundary_checks: [
            "chat_route_transport_adapter",
            "chat_runtime_factory_route_free",
            "chat_execution_service_contract_boundary",
            "workbench_runtime_context_contract_boundary",
            "workbench_context_node_route_free_services",
            "workbench_governance_node_route_free_services",
            "graphiti_memory_provider_langchain_boundary",
          ],
          runtime_boundary_warnings: [],
          runtime_boundary_blocker_count: 0,
        },
      },
      {
        id: "schema_registry",
        scope: "Track G",
        status: "passed",
        detail: "Local Ticket, Employee, Asset, and runtime ledgers are on expected schema boundaries.",
        blockers: [],
        evidence: { store_count: 8, migration_required_count: 0 },
      },
      {
        id: "release_hygiene",
        scope: "Track G",
        status: "warning",
        detail: "Source files, generated artifacts, local projections, and test outputs are classified for release review.",
        blockers: [],
        evidence: { total_changed: 5, unknown_count: 0 },
      },
    ],
    blockers: [
      "ticket_provider_not_ready",
      "memory_provider_not_ready",
      "live_provider_dogfood_not_confirmed",
      "core_provider_not_production_ready",
    ],
    commands: [
      "python scripts/plan_v8_readiness.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-g-plan-v8-readiness.json",
      "python scripts/chat_visible_response_matrix.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-a-chat-visible-response-matrix.json",
      "python scripts/live_provider_soak_plan.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-soak-plan.json",
      "python scripts/live_provider_soak_evidence.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-soak-evidence.json",
      "python scripts/live_provider_readiness_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-readiness-smoke.json",
      "python scripts/plane_scope_discovery_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-plane-scope-discovery-smoke.json",
      "python scripts/plane_ticket_action_smoke.py --workspace-dir . --source-run-id plan-v8-plane-action-smoke --output .aiteamos/artifacts/plan_v8/track-c-plane-ticket-action-smoke.json",
      "python scripts/employee_growth_eval_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-e-employee-growth-eval-smoke.json",
      "python scripts/environment_smoke.py --workspace-dir .",
    ],
    evidence_refs: [
      "track-c-agent-server-smoke.json",
      "track-a-chat-visible-response-matrix.json",
      "track-c-live-provider-readiness.json",
      "track-c-plane-scope-discovery-smoke.json",
      "track-c-plane-ticket-action-smoke.json",
      "track-c-ticket-loop-worker-soak.json",
      "track-g-plan-v8-readiness.json",
      "track-e-employee-growth-eval-smoke.json",
    ],
  },
  release_hygiene: {
    contract_version: "aiteamos_release_hygiene.v1",
    status: "warning",
    detail: "Worktree has changed files; review source changes separately from generated artifacts and local provider projections.",
    git_root: "/home/shiqiangli/projects/AITeamOS",
    summary: {
      total_changed: 5,
      source_count: 2,
      generated_artifact_count: 1,
      local_projection_count: 1,
      test_output_count: 0,
      unknown_count: 0,
      untracked_count: 2,
      modified_count: 3,
      deleted_count: 0,
    },
    review_commands: [
      "git status --short",
      "git diff --stat",
      "python scripts/plan_v8_artifact_summary.py --workspace-dir .",
    ],
    boundary_notes: [
      "Source files are reviewed as implementation changes.",
      "Generated artifacts under .aiteamos/artifacts are evidence, not durable product truth.",
      "Local provider projections under .aiteamos are runtime state unless explicitly promoted.",
      "plan_v8.md is the stable baseline; progress belongs in plan_v8_progress.md.",
    ],
    category_samples: {
      source: [
        {
          path: "services/api/aiteamos_api/read/system_status_routes.py",
          status_code: " M",
          category: "source",
          review_action: "review_in_code_diff",
          detail: "Source/config/test/docs change that belongs in normal code review.",
        },
      ],
      generated_artifact: [
        {
          path: ".aiteamos/artifacts/plan_v8/track-f-context-retrieval-eval-smoke.json",
          status_code: "??",
          category: "generated_artifact",
          review_action: "retain_as_evidence_or_archive",
          detail: "Generated evidence or progress artifact; review as proof, not as product source.",
        },
      ],
      local_projection: [
        {
          path: ".aiteamos/tickets/index.json",
          status_code: "??",
          category: "local_projection",
          review_action: "do_not_treat_as_source_without_explicit_decision",
          detail: "Local provider projection or runtime state; preserve only when intentionally promoted.",
        },
      ],
    },
    items: [
      {
        path: "services/api/aiteamos_api/read/system_status_routes.py",
        status_code: " M",
        category: "source",
        review_action: "review_in_code_diff",
        detail: "Source/config/test/docs change that belongs in normal code review.",
      },
      {
        path: ".aiteamos/artifacts/plan_v8/track-f-context-retrieval-eval-smoke.json",
        status_code: "??",
        category: "generated_artifact",
        review_action: "retain_as_evidence_or_archive",
        detail: "Generated evidence or progress artifact; review as proof, not as product source.",
      },
      {
        path: ".aiteamos/tickets/index.json",
        status_code: "??",
        category: "local_projection",
        review_action: "do_not_treat_as_source_without_explicit_decision",
        detail: "Local provider projection or runtime state; preserve only when intentionally promoted.",
      },
    ],
  },
  blockers: [
    {
      id: "ticket_backend",
      scope: "Ticket Backend",
      status: "setup_blocked",
      detail: "Plane Ticket Backend is selected but setup is incomplete.",
      setup_required: ["plane_workspace_slug", "plane_project_id", "PLANE_API_KEY"],
    },
    {
      id: "memory_asset_graph_backend",
      scope: "Memory / Asset Graph Backend",
      status: "disabled",
      detail: "Graphiti is not enabled.",
      setup_required: ["Graphiti URI/user", "AITEAMOS_GRAPHITI_PASSWORD, NEO4J_PASSWORD, or AITEAMOS_NEO4J_PASSWORD"],
    },
    {
      id: "runtime_executor:claude_code",
      scope: "Runtime Executor: claude code",
      status: "setup_blocked",
      detail: "Claude Code-compatible Local CLI Executor is not configured.",
      setup_required: ["CLAUDE_CODE_BIN"],
    },
    {
      id: "live_provider_dogfood",
      scope: "Live Provider Dogfood",
      status: "blocked",
      detail: "The full Chat -> Employee -> Ticket -> Approval -> Assets -> Graphiti -> Recall loop is not executable yet (4 blockers).",
      setup_required: ["select a ready RuntimeExecutor with repo:write", "PLANE_API_KEY", "Graphiti URI/user", "--execute", "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1"],
      reasons: [
        "runtime_executor_lacks_repo_write",
        "ticket_provider_not_ready",
        "memory_provider_not_ready",
        "live_provider_dogfood_not_confirmed",
      ],
      related_blockers: [
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
      related_candidates: [
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
        selected_executor_id: "local_tool",
        repo_write_ready_count: 1,
        repo_write_candidate_count: 3,
        mutation_gate_open: false,
        provider_smoke_status: "not_run",
      },
    },
  ],
};

describe("SystemStatusPage", () => {
  beforeEach(() => {
    clipboardWrite = vi.fn(async () => undefined);
    Object.defineProperty(window.navigator, "clipboard", {
      configurable: true,
      value: { writeText: clipboardWrite },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/chat/ai-engines")) {
          return new Response(JSON.stringify(aiEngines), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/capabilities")) {
          return new Response(JSON.stringify(capabilities), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/code-repositories/status")) {
          return new Response(JSON.stringify(codeRepositoryStatus), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/chat/employees")) {
          return new Response(JSON.stringify(employees), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/knowledge/status")) {
          return new Response(JSON.stringify(knowledge), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/memory/status")) {
          return new Response(JSON.stringify(memory), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.includes("/system-status/environment-smoke")) {
          const includeExternal = url.includes("include_external=true");
          return new Response(JSON.stringify({
            contract_version: "provider_conformance.v1",
            status: includeExternal ? "warning" : "setup_blocked",
            checks: [
              {
                id: "ai_engine:deepseek",
                scope: "AI Engines",
                status: "setup_blocked",
                detail: "Read-only DeepSeek LangChain model-provider readiness check. No model API call is made by this smoke.",
                checks: ["langchain_model_provider_config_inspected", "deepseek_configuration_inspected", "no_external_llm_call"],
                warnings: ["openai_api_key_not_configured"],
                failures: [],
                blockers: [{ id: "ai_engine:deepseek:setup", status: "setup_blocked", setup_required: ["DEEPSEEK_API_KEY"] }],
                evidence: { langchain_model_provider: { selected_provider: "deepseek", config_inspected: true, no_external_llm_call: true } },
                external_calls: false,
              },
              {
                id: "providers:core",
                scope: "Provider Adapters",
                status: includeExternal ? "warning" : "setup_blocked",
                detail: "Aggregates provider adapter smoke while treating optional commercial runtimes as warnings.",
                checks: includeExternal
                  ? ["provider_conformance_smoke_run", "external_provider_smoke_requested", "provider:ticket:plane:passed", "provider:memory:graphiti:passed"]
                  : ["provider_conformance_smoke_run", "external_provider_smoke_not_requested", "provider:ticket:plane:setup_blocked"],
                warnings: ["optional_provider_setup_blocked:runtime:claude_code"],
                failures: [],
                blockers: includeExternal ? [] : [{ id: "ticket:plane:setup", status: "setup_blocked", setup_required: ["PLANE_API_KEY"], provider_id: "ticket:plane" }],
                evidence: { provider_summary: { provider_count: 2, external_calls: includeExternal } },
                external_calls: includeExternal,
              },
              {
                id: "fallback:local",
                scope: "Local Fallback",
                status: "passed",
                detail: "Verifies local AITeamOS-owned Ticket/Employee/Asset fallback paths remain available.",
                checks: ["local_asset_registry_ready", "local_employee_profiles_ready", "ticket_local_file_fallback_declared"],
                warnings: [],
                failures: [],
                blockers: [],
                evidence: { asset_provider: "asset:local_registry" },
                external_calls: false,
              },
              {
                id: "runtime:agent_loop",
                scope: "LangGraph Agent Loop",
                status: "passed",
                detail: "Verifies the core agent loop remains behind RuntimeExecutor/LangGraph instead of Chat route logic.",
                checks: [
                  "runtime_provider_contract_read",
                  "chat_route_bridge_boundary",
                  "runtime_boundary_source_audited",
                  "chat_route_transport_adapter",
                  "chat_runtime_factory_route_free",
                  "chat_execution_service_contract_boundary",
                  "workbench_runtime_context_contract_boundary",
                  "workbench_context_node_route_free_services",
                  "workbench_governance_node_route_free_services",
                  "graphiti_memory_provider_langchain_boundary",
                  "runtime:universal_employee_agent_ready",
                ],
                warnings: [],
                failures: [],
                blockers: [],
                evidence: {
                  universal_employee_agent: { status: "ready" },
                  runtime_boundary_audit: {
                    contract_version: "aiteamos_runtime_boundary_audit.v1",
                    status: "passed",
                    summary: {
                      check_count: 7,
                      passed_count: 7,
                      warning_count: 0,
                      blocked_count: 0,
                      chat_route_line_count: 170,
                      workbench_context_line_count: 232,
                      workbench_context_node_line_count: 405,
                      workbench_governance_node_line_count: 404,
                      passed_checks: [
                        "chat_route_transport_adapter",
                        "chat_runtime_factory_route_free",
                        "chat_execution_service_contract_boundary",
                        "workbench_runtime_context_contract_boundary",
                        "workbench_context_node_route_free_services",
                        "workbench_governance_node_route_free_services",
                        "graphiti_memory_provider_langchain_boundary",
                      ],
                      warnings: [],
                      blockers: [],
                    },
                  },
                },
                external_calls: false,
              },
            ],
            provider_smoke: null,
            summary: {
              check_count: 4,
              passed_count: 2,
              blocked_count: includeExternal ? 1 : 2,
              warning_count: 2,
              failed_count: 0,
              contract_version: "provider_conformance.v1",
              external_calls: includeExternal,
              include_external: includeExternal,
              evaluation_scope: "environment_readiness_with_provider_smoke",
              non_destructive: true,
              core_boundary: "DeepSeek/direct LLM, Ticket provider, Memory provider, local fallback, and LangGraph runtime readiness.",
            },
          }), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.includes("/system-status/providers/smoke")) {
          const includeExternal = url.includes("include_external=true");
          return new Response(JSON.stringify({
            contract_version: "provider_conformance.v1",
            status: "passed",
            results: [
              {
                provider_id: "ticket:plane",
                provider_kind: "ticket",
                implementation: "plane",
                status: "setup_blocked",
                detail: "Plane Ticket Backend is selected but setup is incomplete.",
                smoke_kind: "ticket_backend_status",
                checks: includeExternal
                  ? ["ticket_backend_status_read", "external_smoke_requested", "plane_project_work_items_read"]
                  : ["ticket_backend_status_read", "no_fake_success_for_blocked_provider"],
                warnings: includeExternal ? [] : ["external_provider_smoke_skipped"],
                failures: [],
                blockers: [{ id: "ticket:plane:setup", status: "setup_blocked", setup_required: ["PLANE_API_KEY"] }],
                evidence: includeExternal
                  ? { external_smoke: { response_keys: ["results", "total_count"] } }
                  : { ticket_backend_status: { status: "setup_blocked" } },
                external_calls: includeExternal,
              },
              {
                provider_id: "asset:local_registry",
                provider_kind: "asset",
                implementation: "local_registry",
                status: "passed",
                detail: "Local Asset Candidate registry is available.",
                smoke_kind: "asset_registry_contract",
                checks: ["asset_registry_contract_read"],
                warnings: [],
                failures: [],
                blockers: [],
                evidence: { asset_registry: { provider: "local_file" } },
                external_calls: false,
              },
            ],
            summary: {
              provider_count: 2,
              passed_count: 1,
              blocked_count: 1,
              warning_count: 1,
              failed_count: 0,
              contract_version: "provider_conformance.v1",
              external_calls: includeExternal,
              include_external: includeExternal,
              evaluation_scope: "provider_status_and_adapter_health",
              non_destructive: true,
            },
          }), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/system-status")) {
          return new Response(JSON.stringify(systemStatus), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/runtime-executors/claude_code/smoke")) {
          return new Response(JSON.stringify({
            executor_id: "claude_code",
            request: { request_id: "smoke-claude_code" },
            result: {
              request_id: "smoke-claude_code",
              executor_id: "claude_code",
              status: "blocked",
              report: "Claude Code-compatible Local CLI Executor is not configured.",
              errors: [{ reason: "runtime_setup_blocked", detail: "Set CLAUDE_CODE_BIN." }],
            },
            ingested: false,
            ingestion_blocker: "",
          }), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/runtime-executors/smoke-batch")) {
          return new Response(JSON.stringify({
            status: "blocked",
            results: [
              {
                executor_id: "claude_code",
                request: { request_id: "smoke-claude_code" },
                result: {
                  request_id: "smoke-claude_code",
                  executor_id: "claude_code",
                  status: "blocked",
                  report: "Claude Code-compatible Local CLI Executor is not configured.",
                  errors: [{ reason: "executor_setup_blocker", detail: "Set CLAUDE_CODE_BIN." }],
                },
                ingested: false,
                ingestion_blocker: "",
              },
              {
                executor_id: "langgraph",
                request: { request_id: "smoke-langgraph" },
                result: {
                  request_id: "smoke-langgraph",
                  executor_id: "langgraph",
                  status: "completed",
                  report: "LangGraph smoke completed.",
                  errors: [],
                },
                ingested: false,
                ingestion_blocker: "",
              },
            ],
            summary: {
              executor_count: 2,
              completed_count: 1,
              blocked_count: 1,
              failed_count: 0,
              ingested_count: 0,
              ingestion_blocker_count: 0,
            },
            learning_delta: { action: "runtime_executor_smoke_batch" },
            ingestion_blocker: "",
          }), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/runtime-executors/dogfood")) {
          return new Response(JSON.stringify({
            status: "completed",
            ticket: { id: "ops-42", title: "RuntimeExecutor dogfood: claude_code" },
            smoke_batch: {
              status: "completed",
              summary: { executor_count: 1, completed_count: 1, blocked_count: 0 },
            },
            approval: { id: "approval-runtime-42", status: "approved", ticket_id: "ops-42" },
            approved_run: {
              ingested: true,
              result: {
                status: "completed",
                report: "Approved runtime mutation executed.",
              },
            },
            summary_report: {
              report_type: "runtime_dogfood_summary",
              evidence: ["smoke://system-status/dogfood", "pytest::system-status-dogfood::passed"],
            },
            learning_delta: {
              action: "runtime_executor_dogfood",
              memory_candidate_ids: ["mem-candidate-dogfood-1"],
              memory_candidate_count: 1,
            },
            blockers: [],
          }), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/tickets/status")) {
          return new Response(JSON.stringify(ticketBackendStatus), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/tool-connectors/status")) {
          return new Response(JSON.stringify(toolConnectorStatus), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        return new Response("not found", { status: 404 });
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders system summary and secret health checks", async () => {
    render(<SystemStatusPage />);

    expect(await screen.findByRole("heading", { name: "System Status" })).toBeTruthy();
    expect(screen.getByText("System Summary")).toBeTruthy();
    expect(screen.getByText("Release Target")).toBeTruthy();
    expect(screen.getByText("release target status blocked")).toBeTruthy();
    expect(screen.getByText("Operating Blockers")).toBeTruthy();
    expect(screen.getAllByText("Runtime Executors").length).toBeGreaterThan(0);
    expect(screen.getAllByText("langgraph").length).toBeGreaterThan(0);
    expect(screen.getAllByText("claude code").length).toBeGreaterThan(0);
    expect(screen.getAllByText("cursor").length).toBeGreaterThan(0);
    expect(screen.getAllByText("inspect_code_repository").length).toBeGreaterThan(0);
    expect(screen.getAllByText("compatible_local_cli").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Delivery").length).toBeGreaterThan(0);
    expect(screen.getByText("artifact_handoff")).toBeTruthy();
    expect(screen.getByText("http_json")).toBeTruthy();
    expect(screen.getByText("local_cli")).toBeTruthy();
    expect(screen.getAllByText("CLAUDE_CODE_BIN").length).toBeGreaterThan(0);
    expect(screen.getByText("CLAUDE_CODE_COMMAND_TEMPLATE")).toBeTruthy();
    expect(screen.getByText("CURSOR_INSPECT_ENDPOINT")).toBeTruthy();
    expect(screen.getAllByText("Result Schema").length).toBeGreaterThan(0);
    expect(screen.getAllByText("approval_requests").length).toBeGreaterThan(0);
    expect(screen.getAllByText("tool_events").length).toBeGreaterThan(0);
    expect(screen.getByText("deepseek-reasoner")).toBeTruthy();
    expect(screen.getAllByText("DEEPSEEK_API_KEY").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Governance Guard").length).toBeGreaterThan(0);
    expect(screen.getAllByText("ticket_bound").length).toBeGreaterThan(0);
    expect(screen.getAllByText("approval_bound").length).toBeGreaterThan(0);
    expect(screen.getAllByText("evidence_bound").length).toBeGreaterThan(0);
    expect(screen.getAllByText("external_runtime_completion_must_not_be_faked").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Diagnostics").length).toBeGreaterThan(0);
    expect(screen.getAllByText("/api/v1/runtime-executors/claude_code/smoke").length).toBeGreaterThan(0);
    expect(screen.getAllByText("/api/v1/runtime-executors/dogfood").length).toBeGreaterThan(0);
    expect(screen.getAllByText("dogfood creates Ticket").length).toBeGreaterThan(0);
    expect(screen.getAllByText("dogfood approval").length).toBeGreaterThan(0);
    expect(screen.getAllByText("RuntimeExecutor").length).toBeGreaterThan(0);
    expect(screen.getAllByText("no default ingest").length).toBeGreaterThan(0);
    expect(screen.getAllByText("ticket-bound ingest").length).toBeGreaterThan(0);
    expect(screen.getAllByText("CURSOR_API_KEY").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Environment Smoke" })).toBeTruthy();
    expect(screen.getByText("Provider Adapter Conformance")).toBeTruthy();
    expect(screen.getByText("provider_conformance.v1")).toBeTruthy();
    expect(screen.getByText("2 production-ready")).toBeTruthy();
    expect(screen.getByText("Ticket / Employee / Asset models remain AITeamOS-owned; providers are projections or execution adapters.")).toBeTruthy();
    expect(screen.getByText("Runtime Boundary")).toBeTruthy();
    expect(screen.getByText("Chat route and runtime contract audit")).toBeTruthy();
    expect(screen.getByText("0 runtime blockers")).toBeTruthy();
    expect(screen.getAllByText("chat_route_transport_adapter").length).toBeGreaterThan(0);
    expect(screen.getAllByText("chat_runtime_factory_route_free").length).toBeGreaterThan(0);
    expect(screen.getAllByText("chat_execution_service_contract_boundary").length).toBeGreaterThan(0);
    expect(screen.getAllByText("workbench_runtime_context_contract_boundary").length).toBeGreaterThan(0);
    expect(screen.getAllByText("workbench_context_node_route_free_services").length).toBeGreaterThan(0);
    expect(screen.getAllByText("workbench_governance_node_route_free_services").length).toBeGreaterThan(0);
    expect(screen.getAllByText("graphiti_memory_provider_langchain_boundary").length).toBeGreaterThan(0);
    expect(screen.getByText("Plane Ticket Provider")).toBeTruthy();
    expect(screen.getByText("Local Asset Registry")).toBeTruthy();
    expect(screen.getAllByText("Local Employee Profiles").length).toBeGreaterThan(0);
    expect(screen.getByText("Graphiti Memory / Asset Graph Provider")).toBeTruthy();
    expect(screen.getByText("ticket:local_file")).toBeTruthy();
    expect(screen.getByText("asset:local_registry")).toBeTruthy();
    expect(screen.getByText("Contract Guards")).toBeTruthy();
    expect(screen.getByText("ticket.required_capabilities")).toBeTruthy();
    expect(screen.getByText("degraded_with_fallback")).toBeTruthy();
    expect(screen.getAllByText("schema_current").length).toBeGreaterThan(0);
    expect(screen.getByText("Plan v8 Readiness")).toBeTruthy();
    expect(screen.getByText("aiteamos_plan_v8_readiness.v1")).toBeTruthy();
    expect(screen.getAllByText("not release ready").length).toBeGreaterThan(0);
    expect(screen.getByText("Readiness Checklist")).toBeTruthy();
    expect(screen.getByText("Next Steps")).toBeTruthy();
    expect(screen.getByText(/Complete the Code Repository Plane workspace\/project scope/)).toBeTruthy();
    expect(screen.getByText(/Settings -> Code Repositories/)).toBeTruthy();
    expect(screen.getByText("Code Repository scope")).toBeTruthy();
    expect(screen.getAllByText("incomplete").length).toBeGreaterThan(0);
    expect(screen.getByText("scope candidates 0")).toBeTruthy();
    expect(screen.getByText("scope missing 1")).toBeTruthy();
    expect(screen.getByText("discovery ui action Discover Plane scope")).toBeTruthy();
    expect(screen.getByText("discovery endpoint /api/v1/tickets/backend/plane-scope/discovery")).toBeTruthy();
    expect(screen.getByText("api key configured yes")).toBeTruthy();
    expect(screen.getAllByText("external mutation no").length).toBeGreaterThan(0);
    expect(screen.getByText(/Settings -> Ticket Backend/)).toBeTruthy();
    expect(screen.getByText("Ticket Backend Plane mode")).toBeTruthy();
    expect(screen.getAllByText("setup blocked").length).toBeGreaterThan(0);
    expect(screen.getAllByText("current mode local file").length).toBeGreaterThan(0);
    expect(screen.getByText("release target ready no")).toBeTruthy();
    expect(screen.getByText("release target setup action select plane ticket backend")).toBeTruthy();
    expect(screen.getByText("release target blockers plane ticket backend not selected, plane workspace slug missing, plane project id missing")).toBeTruthy();
    expect(screen.getByText("plane selected no")).toBeTruthy();
    expect(screen.getAllByText("command").length).toBeGreaterThan(0);
    const liveProviderReadinessSmokeCommand = "python scripts/live_provider_readiness_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-readiness-smoke.json";
    expect(screen.getAllByText(liveProviderReadinessSmokeCommand).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Copy Provider readiness smoke command" }));
    await waitFor(() => expect(clipboardWrite).toHaveBeenCalledWith(liveProviderReadinessSmokeCommand));
    expect(screen.getByRole("button", { name: "Provider readiness smoke command copied" })).toBeTruthy();
    const planeActionSmokeCommand = "python scripts/plane_ticket_action_smoke.py --workspace-dir . --source-run-id plan-v8-plane-action-smoke --output .aiteamos/artifacts/plan_v8/track-c-plane-ticket-action-smoke.json";
    fireEvent.click(screen.getByRole("button", { name: "Copy Plane action smoke command" }));
    await waitFor(() => expect(clipboardWrite).toHaveBeenCalledWith(planeActionSmokeCommand));
    expect(screen.getByRole("button", { name: "Plane action smoke command copied" })).toBeTruthy();
    const mutationGateGuardCommand = "unset AITEAMOS_LIVE_PROVIDER_DOGFOOD";
    expect(screen.getByText(mutationGateGuardCommand)).toBeTruthy();
    expect(screen.getAllByText("closed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("gate open no").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Copy Mutation gate command" }));
    await waitFor(() => expect(clipboardWrite).toHaveBeenCalledWith(mutationGateGuardCommand));
    expect(screen.getByRole("button", { name: "Mutation gate command copied" })).toBeTruthy();
    window.location.hash = "";
    fireEvent.click(screen.getByRole("button", { name: "Open Code Repository scope" }));
    expect(window.location.hash).toBe("#/settings/code-repositories");
    window.location.hash = "";
    fireEvent.click(screen.getByRole("button", { name: "Open Ticket Backend Plane mode" }));
    expect(window.location.hash).toBe("#/settings/ticket-backend");
    expect(screen.getByText("Local Readiness Command")).toBeTruthy();
    const planReadinessCommand = "python scripts/plan_v8_readiness.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-g-plan-v8-readiness.json";
    expect(screen.getByText(planReadinessCommand)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Copy Local readiness command 1 command" }));
    await waitFor(() => expect(clipboardWrite).toHaveBeenCalledWith(planReadinessCommand));
    expect(screen.getByRole("button", { name: "Local readiness command 1 command copied" })).toBeTruthy();
    expect(screen.getByText("chat_visible_response")).toBeTruthy();
    expect(screen.getAllByText("live provider dogfood not confirmed").length).toBeGreaterThan(0);
    expect(screen.getByText("Schema / Migration Readiness")).toBeTruthy();
    expect(screen.getByText("aiteamos_schema_registry.v1")).toBeTruthy();
    expect(screen.getByText("3 current")).toBeTruthy();
    expect(screen.getByText("0 migration required")).toBeTruthy();
    expect(screen.getByText("Execution Sessions")).toBeTruthy();
    expect(screen.getByText("execution_sessions.v1")).toBeTruthy();
    expect(screen.getByText(".aiteamos/execution_sessions.json")).toBeTruthy();
    expect(screen.getByText("object_map / object map keyed by employee_id::thread_id::ticket_id")).toBeTruthy();
    expect(screen.getByText("Asset Candidates")).toBeTruthy();
    expect(screen.getByText("not_created_yet")).toBeTruthy();
    expect(screen.getAllByText("Local Employee Profiles").length).toBeGreaterThan(1);
    expect(screen.getByText("employee_profiles.v1")).toBeTruthy();
    expect(screen.getByText("Ticket Projection Index")).toBeTruthy();
    expect(screen.getByText("ticket_projection.v1")).toBeTruthy();
    expect(screen.getByText("Plan v8 Artifact Evidence")).toBeTruthy();
    expect(screen.getByText(".aiteamos/artifacts/plan_v8")).toBeTruthy();
    const artifactEvidencePanel = screen.getByText("Plan v8 Artifact Evidence").closest("section");
    expect(artifactEvidencePanel).toBeTruthy();
    expect(within(artifactEvidencePanel as HTMLElement).getByText("Latest evidence")).toBeTruthy();
    expect(within(artifactEvidencePanel as HTMLElement).getByText("Release readiness")).toBeTruthy();
    expect(within(artifactEvidencePanel as HTMLElement).getAllByText("2026-06-21T03:25:00Z").length).toBeGreaterThan(0);
    expect(within(artifactEvidencePanel as HTMLElement).getByText("Provider blockers")).toBeTruthy();
    expect(within(artifactEvidencePanel as HTMLElement).getByText("Warnings / gaps")).toBeTruthy();
    expect(within(artifactEvidencePanel as HTMLElement).getAllByText("3").length).toBeGreaterThan(0);
    expect(within(artifactEvidencePanel as HTMLElement).getByText("0 / 0")).toBeTruthy();
    expect(screen.getByText("1 Agent Server")).toBeTruthy();
    expect(screen.getByText("1 matrix")).toBeTruthy();
    expect(screen.getByText("1 readiness")).toBeTruthy();
    expect(screen.getByText("1 soak evidence")).toBeTruthy();
    expect(screen.getByText("1 Plane discovery")).toBeTruthy();
    expect(screen.getByText("1 Plane action")).toBeTruthy();
    expect(screen.getByText("1 worker soak")).toBeTruthy();
    expect(screen.getByText("1 release review")).toBeTruthy();
    expect(screen.getByText("1 employee growth")).toBeTruthy();
    expect(screen.getByText("Fresh Agent Server Smoke")).toBeTruthy();
    expect(screen.getByText("Chat Visible Response Matrix")).toBeTruthy();
    expect(screen.getByText("5/5 cases")).toBeTruthy();
    expect(screen.getAllByText("provider blocker").length).toBeGreaterThan(0);
    expect(screen.getAllByText("track-a-chat-visible-response-matrix.json").length).toBeGreaterThan(0);
    expect(screen.getByText("Live Provider Readiness Artifact")).toBeTruthy();
    expect(screen.getByText("release target blocked")).toBeTruthy();
    expect(screen.getByText("configure plane ticket backend")).toBeTruthy();
    expect(screen.getByText("plane api key missing")).toBeTruthy();
    expect(screen.getByText("Live Provider Soak Evidence Artifact")).toBeTruthy();
    expect(screen.getAllByText("track-c-live-provider-soak-evidence.json").length).toBeGreaterThan(0);
    expect(screen.getByText("Plane Scope Discovery Artifact")).toBeTruthy();
    expect(screen.getByText("discovery ready")).toBeTruthy();
    expect(screen.getByText("API key ready")).toBeTruthy();
    expect(screen.getByText("external read")).toBeTruthy();
    expect(screen.getAllByText("non-mutating").length).toBeGreaterThan(0);
    expect(screen.getByText("1 suggestions")).toBeTruthy();
    expect(screen.getByText("1 workspaces")).toBeTruthy();
    expect(screen.getByText("1 projects")).toBeTruthy();
    expect(screen.getAllByText("ait").length).toBeGreaterThan(0);
    expect(screen.getAllByText("plane-project-1").length).toBeGreaterThan(0);
    expect(screen.getByText("Plane scope discovery found workspace/project candidates.")).toBeTruthy();
    expect(screen.getAllByText("track-c-plane-scope-discovery-smoke.json").length).toBeGreaterThan(0);
    expect(screen.getByText("Plane Ticket Action Smoke Artifact")).toBeTruthy();
    expect(screen.getAllByText("track-c-plane-ticket-action-smoke.json").length).toBeGreaterThan(0);
    expect(screen.getAllByText("dry run").length).toBeGreaterThan(0);
    expect(screen.getAllByText("AITEAMOS_LIVE_PROVIDER_DOGFOOD").length).toBeGreaterThan(0);
    expect(screen.getByText("Ticket Loop Worker Soak Artifact")).toBeTruthy();
    expect(screen.getByText("ops-worker-soak")).toBeTruthy();
    expect(screen.getByText("2 processed")).toBeTruthy();
    expect(screen.getByText("1 policy actions")).toBeTruthy();
    expect(screen.getByText("1 retrospective assets")).toBeTruthy();
    expect(screen.getByText("daemon passed")).toBeTruthy();
    expect(screen.getAllByText("track-c-ticket-loop-worker-soak.json").length).toBeGreaterThan(0);
    expect(screen.getByText("Employee Growth Eval Artifact")).toBeTruthy();
    expect(screen.getAllByText("track-e-employee-growth-eval-smoke.json").length).toBeGreaterThan(0);
    expect(screen.getByText("2 quality feedback")).toBeTruthy();
    expect(screen.getByText("work history score 3")).toBeTruthy();
    expect(screen.getByText("0 applied improvements")).toBeTruthy();
    expect(screen.getByText("proof passed")).toBeTruthy();
    expect(screen.getByText("application applied")).toBeTruthy();
    expect(screen.getByText("4 proof changes")).toBeTruthy();
    expect(screen.getByText("report-employee-growth-proof")).toBeTruthy();
    expect(screen.getByText("Plan v8 Release Readiness Artifact")).toBeTruthy();
    expect(screen.getAllByText("track-g-plan-v8-readiness.json").length).toBeGreaterThan(0);
    expect(screen.getAllByText("not release ready").length).toBeGreaterThan(0);
    expect(screen.getByText("chat_visible_response.v1")).toBeTruthy();
    expect(screen.getByText("final_response")).toBeTruthy();
    expect(screen.getAllByText("1/3 repo-write ready").length).toBeGreaterThan(0);
    expect(screen.getByText("Gaps, Warnings, and Provider Blockers")).toBeTruthy();
    expect(screen.getAllByText("ticket provider not ready").length).toBeGreaterThan(0);
    expect(screen.getAllByText("memory provider not ready").length).toBeGreaterThan(0);
    expect(screen.getByText("Recent Evidence")).toBeTruthy();
    expect(screen.getAllByText("track-c-agent-server-smoke.json").length).toBeGreaterThan(0);
    expect(screen.getAllByText("track-c-live-provider-readiness.json").length).toBeGreaterThan(0);
    expect(screen.getByText("Release Hygiene")).toBeTruthy();
    expect(screen.getByText("aiteamos_release_hygiene.v1")).toBeTruthy();
    expect(screen.getByText("Change Boundaries")).toBeTruthy();
    expect(screen.getByText("Review Commands")).toBeTruthy();
    expect(screen.getByText("Category Samples")).toBeTruthy();
    expect(screen.getByText("Changed Path Samples")).toBeTruthy();
    expect(screen.getByText("git status --short")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Copy Release review command 1 command" }));
    await waitFor(() => expect(clipboardWrite).toHaveBeenCalledWith("git status --short"));
    expect(screen.getByRole("button", { name: "Release review command 1 command copied" })).toBeTruthy();
    expect(screen.getAllByText("services/api/aiteamos_api/read/system_status_routes.py").length).toBeGreaterThan(0);
    expect(screen.getAllByText(".aiteamos/artifacts/plan_v8/track-f-context-retrieval-eval-smoke.json").length).toBeGreaterThan(0);
    expect(screen.getAllByText(".aiteamos/tickets/index.json").length).toBeGreaterThan(0);
    expect(screen.getByText("Live Provider Dogfood Readiness")).toBeTruthy();
    expect(screen.getByText("readiness reuses RuntimeExecutor health plus Ticket and Graphiti provider status")).toBeTruthy();
    expect(screen.getAllByText("1/3 repo-write ready").length).toBeGreaterThan(0);
    expect(screen.getAllByText("gate closed").length).toBeGreaterThan(0);
    expect(screen.getByText("Selected Runtime")).toBeTruthy();
    expect(screen.getByText("Provider Preconditions")).toBeTruthy();
    window.location.hash = "";
    fireEvent.click(screen.getByRole("button", { name: "Code Repositories" }));
    expect(window.location.hash).toBe("#/settings/code-repositories");
    window.location.hash = "";
    fireEvent.click(screen.getByRole("button", { name: "Ticket Backend" }));
    expect(window.location.hash).toBe("#/settings/ticket-backend");
    window.location.hash = "";
    fireEvent.click(screen.getByRole("button", { name: "Memory Backend" }));
    expect(window.location.hash).toBe("#/settings/memory-backend");
    expect(screen.getByText("Repo-Write Candidates")).toBeTruthy();
    expect(screen.getByText("codex cli")).toBeTruthy();
    expect(screen.getByText("Readiness Blockers")).toBeTruthy();
    expect(screen.getByText("repo:write required")).toBeTruthy();
    expect(screen.getAllByText("Ticket setup blocked").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Memory disabled").length).toBeGreaterThan(0);
    expect(screen.getByText("readiness is read-only and does not call external provider smoke")).toBeTruthy();
    expect(screen.getAllByText("runtime executor lacks repo write").length).toBeGreaterThan(0);
    expect(screen.getAllByText("select a ready RuntimeExecutor with repo:write").length).toBeGreaterThan(0);
    expect(screen.getByText("Live Provider Soak Plan")).toBeTruthy();
    expect(screen.getByText("aiteamos_live_provider_soak_plan.v1")).toBeTruthy();
    expect(screen.getAllByText("6 scenarios").length).toBeGreaterThan(0);
    expect(screen.getByText("Repeated Soak Matrix")).toBeTruthy();
    expect(screen.getAllByText("Completed closeout with Asset proposal").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Natural Employee handoff").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Plane Ticket action-smoke preflight").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Retry, resume, and closeout settlement").length).toBeGreaterThan(0);
    expect(screen.getByText("Soak Commands")).toBeTruthy();
    const liveProviderSoakPlanCommand = "python scripts/live_provider_soak_plan.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-soak-plan.json";
    expect(screen.getAllByText(liveProviderSoakPlanCommand).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Copy Soak command 1 command" }));
    await waitFor(() => expect(clipboardWrite).toHaveBeenCalledWith(liveProviderSoakPlanCommand));
    expect(screen.getByRole("button", { name: "Soak command 1 command copied" })).toBeTruthy();
    expect(screen.getAllByText("python scripts/plane_ticket_action_smoke.py --workspace-dir . --source-run-id plan-v8-plane-action-smoke --output .aiteamos/artifacts/plan_v8/track-c-plane-ticket-action-smoke.json").length).toBeGreaterThan(0);
    expect(screen.getAllByText("python scripts/ticket_loop_queue_worker_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-ticket-loop-worker-soak.json").length).toBeGreaterThan(0);
    expect(screen.getByText("Live Provider Soak Evidence")).toBeTruthy();
    expect(screen.getByText("aiteamos_live_provider_soak_evidence.v1")).toBeTruthy();
    expect(screen.getAllByText("3 passed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("3 blocked").length).toBeGreaterThan(0);
    expect(screen.getAllByText("3 live remaining").length).toBeGreaterThan(0);
    expect(screen.getByText("operator action required")).toBeTruthy();
    expect(screen.getByText("Explicitly set AITEAMOS_LIVE_PROVIDER_DOGFOOD=1, then run the remaining 3 live provider soak command(s).")).toBeTruthy();
    expect(screen.getByText("Scenario Evidence")).toBeTruthy();
    expect(screen.getByText("track-c-live-soak-completed.json")).toBeTruthy();
    expect(screen.getByText("track-c-live-soak-handoff.json")).toBeTruthy();
    const liveProviderDogfoodCommand = "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --output .aiteamos/artifacts/plan_v8/track-c-live-soak-completed.json";
    fireEvent.click(screen.getByRole("button", { name: "Copy Completed closeout with Asset proposal scenario command" }));
    await waitFor(() => expect(clipboardWrite).toHaveBeenCalledWith(liveProviderDogfoodCommand));
    expect(screen.getByRole("button", { name: "Completed closeout with Asset proposal scenario command copied" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Copy Evidence command 1 command" }));
    await waitFor(() => expect(clipboardWrite).toHaveBeenCalledWith(liveProviderDogfoodCommand));
    expect(screen.getByRole("button", { name: "Evidence command 1 command copied" })).toBeTruthy();
    expect(screen.getByText("Live Mutation Handoff")).toBeTruthy();
    expect(screen.getByText("3 live-write scenarios")).toBeTruthy();
    expect(screen.getByText("3 non-mutating passed")).toBeTruthy();
    expect(screen.getByText("Plane Ticket reports / comments")).toBeTruthy();
    expect(screen.getByText("Graphiti projection / recall")).toBeTruthy();
    expect(screen.getAllByText("live provider write").length).toBeGreaterThan(0);
    expect(screen.getAllByText("gated provider action smoke").length).toBeGreaterThan(0);
    expect(screen.getAllByText("open live mutation gate and run command").length).toBeGreaterThan(0);
    expect(screen.getAllByText("track-c-plane-ticket-action-smoke.json").length).toBeGreaterThan(0);
    expect(screen.getAllByText("track-c-live-provider-readiness-smoke.json").length).toBeGreaterThan(0);
    expect(screen.getByText("Evidence Commands")).toBeTruthy();
    expect(screen.getAllByText("python scripts/live_provider_soak_evidence.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-soak-evidence.json").length).toBeGreaterThan(0);
    expect(screen.getByText("release proof incomplete")).toBeTruthy();
    expect(screen.getByText("/api/v1/tickets/status")).toBeTruthy();
    expect(screen.getByText("/api/v1/assets/candidates")).toBeTruthy();
    expect(screen.getByText("/api/v1/chat/employees")).toBeTruthy();
    expect(screen.getByText("/api/v1/memory/graphiti/durable-assets")).toBeTruthy();
    expect(screen.getAllByText("append_report").length).toBeGreaterThan(0);
    expect(screen.getByText("provider_error_must_not_mark_ticket_completed")).toBeTruthy();
    expect(screen.getByText("disabled_graphiti_keeps_local_asset_and_memory_registry_available")).toBeTruthy();
    expect(screen.getByText("repo_write_requires_approval")).toBeTruthy();
    expect(screen.getByText("Memory / Asset Graph Backend")).toBeTruthy();
    expect(screen.getByText("Runtime Executor: claude code")).toBeTruthy();
    expect(screen.getAllByText("AITEAMOS_GRAPHITI_PASSWORD, NEO4J_PASSWORD, or AITEAMOS_NEO4J_PASSWORD").length).toBeGreaterThan(0);
    const operatingBlockersPanel = screen.getByRole("heading", { name: "Operating Blockers" }).closest("section");
    expect(operatingBlockersPanel).toBeTruthy();
    expect(within(operatingBlockersPanel as HTMLElement).getByText("Live Provider Dogfood")).toBeTruthy();
    expect(within(operatingBlockersPanel as HTMLElement).getAllByText("live provider dogfood not confirmed").length).toBeGreaterThan(0);
    expect(within(operatingBlockersPanel as HTMLElement).getByText("Readiness Details")).toBeTruthy();
    expect(within(operatingBlockersPanel as HTMLElement).getByText("Runtime Candidates")).toBeTruthy();
    expect(within(operatingBlockersPanel as HTMLElement).getByText("OpenAI Codex CLI Executor")).toBeTruthy();
    expect(within(operatingBlockersPanel as HTMLElement).getByText("smoke not run")).toBeTruthy();
    expect(screen.getByText("Secrets Health")).toBeTruthy();
    expect(screen.getByText("ChatGPT / OpenAI API")).toBeTruthy();
    expect(screen.getAllByText("DEEPSEEK_API_KEY").length).toBeGreaterThan(0);
    expect(screen.getAllByText("OPENAI_API_KEY").length).toBeGreaterThan(0);
    expect(screen.getAllByText("ANTHROPIC_API_KEY").length).toBeGreaterThan(0);
  });

  it("surfaces local-file Ticket mode as a Plane live-dogfood blocker", async () => {
    const originalDogfood = systemStatus.live_provider_dogfood;
    systemStatus.live_provider_dogfood = {
      ...originalDogfood,
      selected_executor_id: "langgraph",
      require_repo_write_executor: false,
      provider_prerequisites: {
        ...originalDogfood.provider_prerequisites,
        ticket_backend: {
          status: "ready",
          mode: "local_file",
          provider: "",
          detail: "Local append-only Ticket backend is active.",
        },
        plane_ticket_backend_setup: {
          status: "setup_blocked",
          selected: false,
          configured: false,
          active_mode: "local_file",
          active_provider: "",
          required_mode: "plane",
          workspace_configured: false,
          project_configured: false,
          api_key_env: "PLANE_API_KEY",
          api_key_configured: true,
          setup_required: ["PUT /api/v1/tickets/backend mode=plane", ".aiteamos/tickets/backend.json mode=plane", "plane_workspace_slug", "plane_project_id"],
          settings_path: ".aiteamos/tickets/backend.json",
          setup_endpoint: "/api/v1/tickets/backend",
          code_repository_scope_status: "incomplete",
          code_repository_scope_detail: "Code Repository registry has repositories, but none has both Plane workspace and project configured.",
          code_repository_scope_candidate_count: 0,
          code_repository_scope_missing_count: 1,
          code_repository_scope_setup_action: "add_plane_scope_to_code_repository_or_ticket_backend",
          code_repository_scope_candidates: [],
          code_repository_scope_missing: [
            {
              source: "code_repository",
              repository_id: "repo-aiteamos-afc617",
              repository_name: "AITeamOS",
              provider: "local",
              status: "ready",
              workspace_configured: false,
              project_configured: false,
              deep_link: "#/settings/code-repositories",
            },
          ],
        },
      },
      blockers: [
        {
          reason: "plane_ticket_backend_not_selected",
          scope: "ticket_backend",
          status: "setup_blocked",
          detail: "Live Plane / Graphiti dogfood requires the Plane Ticket backend, but the selected Ticket backend mode is local_file.",
          setup_required: ["PUT /api/v1/tickets/backend mode=plane", ".aiteamos/tickets/backend.json mode=plane", "plane_workspace_slug", "plane_project_id"],
        },
        ...originalDogfood.blockers.filter((blocker) => blocker.reason !== "ticket_provider_not_ready"),
      ],
      summary: {
        ...originalDogfood.summary,
        blocker_count: originalDogfood.summary.blocker_count,
        ticket_backend_status: "ready",
        ticket_backend_mode: "local_file",
        ticket_backend_provider: "",
        plane_ticket_backend_selected: false,
        plane_ticket_backend_setup_status: "setup_blocked",
        plane_ticket_backend_setup_required: ["PUT /api/v1/tickets/backend mode=plane", ".aiteamos/tickets/backend.json mode=plane", "plane_workspace_slug", "plane_project_id"],
        plane_ticket_backend_configured: false,
        plane_ticket_workspace_configured: false,
        plane_ticket_project_configured: false,
        plane_ticket_api_key_configured: true,
        plane_ticket_scope_status: "incomplete",
        plane_ticket_scope_candidate_count: 0,
        plane_ticket_scope_missing_count: 1,
        plane_ticket_scope_setup_action: "add_plane_scope_to_code_repository_or_ticket_backend",
      },
    };

    try {
      render(<SystemStatusPage />);

      expect(await screen.findByText("Live Provider Dogfood Readiness")).toBeTruthy();
      expect(screen.getAllByText("Ticket ready").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Ticket mode local file").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Plane config setup blocked").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Plane scope incomplete").length).toBeGreaterThan(0);
      expect(screen.getAllByText("0/1 scope candidates").length).toBeGreaterThan(0);
      expect(screen.getAllByText("scope incomplete").length).toBeGreaterThan(0);
      expect(screen.getAllByText("workspace missing").length).toBeGreaterThan(0);
      expect(screen.getAllByText("project missing").length).toBeGreaterThan(0);
      expect(screen.getAllByText("plane_workspace_slug").length).toBeGreaterThan(0);
      expect(screen.getAllByText("plane_project_id").length).toBeGreaterThan(0);
      expect(screen.getAllByText("plane ticket backend not selected").length).toBeGreaterThan(0);
      expect(screen.getAllByText("PUT /api/v1/tickets/backend mode=plane").length).toBeGreaterThan(0);
    } finally {
      systemStatus.live_provider_dogfood = originalDogfood;
    }
  });

  it("can run a non-destructive runtime smoke diagnostic from system status", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SystemStatusPage />);

    expect((await screen.findAllByText("claude code")).length).toBeGreaterThan(0);
    const smokeButtons = await screen.findAllByRole("button", { name: "Smoke" });
    fireEvent.click(smokeButtons[1]);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/runtime-executors/claude_code/smoke",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("non-destructive RuntimeExecutor smoke"),
        }),
      );
    });
    expect(await screen.findByText("Runtime Smoke")).toBeTruthy();
    expect(screen.getAllByText("runtime setup blocked").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Claude Code-compatible Local CLI Executor is not configured.").length).toBeGreaterThan(0);
  });

  it("can run a non-destructive runtime smoke batch from system status", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SystemStatusPage />);

    expect(await screen.findByRole("button", { name: /Smoke All/i })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Smoke All/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/runtime-executors/smoke-batch",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("non-destructive RuntimeExecutor smoke batch"),
        }),
      );
    });
    expect(await screen.findByText("2 executors")).toBeTruthy();
    expect(screen.getAllByText("1 completed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("1 blocked").length).toBeGreaterThan(0);
    expect(screen.getAllByText("LangGraph smoke completed.").length).toBeGreaterThan(0);
  });

  it("can run provider conformance smoke from system status", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SystemStatusPage />);

    const heading = await screen.findByText("Provider Adapter Conformance");
    const panel = heading.closest("section");
    expect(panel).toBeTruthy();
    fireEvent.click(within(panel as HTMLElement).getByRole("button", { name: "Smoke" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/system-status/providers/smoke",
        expect.objectContaining({ method: "GET" }),
      );
    });
    expect(await screen.findByText("provider_status_and_adapter_health")).toBeTruthy();
    expect(screen.getAllByText("Provider Smoke").length).toBeGreaterThan(0);
    expect(screen.getByText("ticket_backend_status")).toBeTruthy();
    expect(screen.getByText("asset_registry_contract")).toBeTruthy();
    expect(screen.getAllByText("local only").length).toBeGreaterThan(0);
    expect(screen.getByText("external_provider_smoke_skipped")).toBeTruthy();
  });

  it("can run environment smoke from system status", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SystemStatusPage />);

    const heading = await screen.findByRole("heading", { name: "Environment Smoke" });
    const panel = heading.closest("section");
    expect(panel).toBeTruthy();
    fireEvent.click(within(panel as HTMLElement).getByRole("button", { name: "Environment Smoke" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/system-status/environment-smoke",
        expect.objectContaining({ method: "GET" }),
      );
    });
    expect(await screen.findByText("environment_readiness_with_provider_smoke")).toBeTruthy();
    expect(screen.getAllByText("AI Engines").length).toBeGreaterThan(0);
    expect(screen.getByText("Provider Adapters")).toBeTruthy();
    expect(screen.getByText("LangGraph Agent Loop")).toBeTruthy();
    expect(screen.getAllByText("DEEPSEEK_API_KEY").length).toBeGreaterThan(0);
    expect(screen.getByText("chat_route_bridge_boundary")).toBeTruthy();
    expect(screen.getByText("runtime_boundary_source_audited")).toBeTruthy();
    expect(screen.getAllByText("chat_route_transport_adapter").length).toBeGreaterThan(0);
    expect(screen.getAllByText("chat_runtime_factory_route_free").length).toBeGreaterThan(0);
    expect(screen.getAllByText("workbench_runtime_context_contract_boundary").length).toBeGreaterThan(0);
    expect(screen.getAllByText("workbench_context_node_route_free_services").length).toBeGreaterThan(0);
    expect(screen.getAllByText("workbench_governance_node_route_free_services").length).toBeGreaterThan(0);
    expect(screen.getAllByText("graphiti_memory_provider_langchain_boundary").length).toBeGreaterThan(0);
    expect(screen.queryByText("chat_route_helper_surface_large")).toBeNull();
    expect(screen.getAllByText("no external calls").length).toBeGreaterThan(0);
  });

  it("can explicitly run external environment smoke", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SystemStatusPage />);

    const heading = await screen.findByRole("heading", { name: "Environment Smoke" });
    const panel = heading.closest("section");
    expect(panel).toBeTruthy();
    fireEvent.click(within(panel as HTMLElement).getByRole("button", { name: "External Environment Smoke" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/system-status/environment-smoke?include_external=true",
        expect.objectContaining({ method: "GET" }),
      );
    });
    await screen.findByText("external_provider_smoke_requested");
    expect(screen.getAllByText("external calls").length).toBeGreaterThan(0);
    expect(screen.getByText("provider:ticket:plane:passed")).toBeTruthy();
    expect(screen.getByText("provider:memory:graphiti:passed")).toBeTruthy();
  });

  it("can explicitly run external provider conformance smoke", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SystemStatusPage />);

    const heading = await screen.findByText("Provider Adapter Conformance");
    const panel = heading.closest("section");
    expect(panel).toBeTruthy();
    fireEvent.click(within(panel as HTMLElement).getByRole("button", { name: "External Smoke" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/system-status/providers/smoke?include_external=true",
        expect.objectContaining({ method: "GET" }),
      );
    });
    await screen.findByText("provider_status_and_adapter_health");
    expect(screen.getAllByText("external calls").length).toBeGreaterThan(0);
    expect(screen.getByText("plane_project_work_items_read")).toBeTruthy();
  });

  it("can run a Ticket-bound runtime dogfood harness from system status", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SystemStatusPage />);

    expect((await screen.findAllByText("claude code")).length).toBeGreaterThan(0);
    const dogfoodButtons = await screen.findAllByRole("button", { name: "Dogfood" });
    fireEvent.click(dogfoodButtons[0]);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/runtime-executors/dogfood",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("Dogfood approved external runtime mutation"),
        }),
      );
    });
    expect(await screen.findByText("dogfood completed")).toBeTruthy();
    expect(screen.getByText("Ticket ops-42")).toBeTruthy();
    expect(screen.getByText("Approval approval-runtime-42")).toBeTruthy();
    expect(screen.getByText("Run completed")).toBeTruthy();
    expect(screen.getByText("ingested")).toBeTruthy();
    expect(screen.getByText("1 candidates")).toBeTruthy();
    expect(screen.getByText("Candidate mem-candidate-dogfood-1")).toBeTruthy();
    expect(screen.getByText("pytest::system-status-dogfood::passed")).toBeTruthy();
  });
});
