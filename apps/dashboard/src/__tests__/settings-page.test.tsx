import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsPage } from "../pages/settings";

let clipboardWrite: ReturnType<typeof vi.fn>;

const liveProviderReadinessSmokeCommand = "python scripts/live_provider_readiness_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-readiness-smoke.json";
const planeActionSmokeCommand = "python scripts/plane_ticket_action_smoke.py --workspace-dir . --source-run-id plan-v8-plane-action-smoke --output .aiteamos/artifacts/plan_v8/track-c-plane-ticket-action-smoke.json";
const liveDogfoodSoakCommand = "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --output .aiteamos/artifacts/plan_v8/track-c-live-soak-completed.json";

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
      kind: "local_model",
      description: "Local deterministic fallback.",
      support_status: "supported",
      config_status: "configured",
      auth_kind: "none",
      enabled: true,
      editable: true,
      active: false,
      api_key_configured: true,
      status: "configured",
      secret_env_vars: [],
      capabilities: ["offline"],
      model_options: [],
      thinking_options: [],
      config_fields: [],
      chat_options: [],
      health_detail: "Ready for Chat selection.",
    },
    deepseek: {
      id: "deepseek",
      display_name: "DeepSeek",
      kind: "llm_api",
      description: "Low-cost LLM API engine.",
      support_status: "supported",
      config_status: "configured",
      auth_kind: "bearer",
      base_url: "https://api.deepseek.com",
      api_key_env: "DEEPSEEK_API_KEY",
      model: "deepseek-v4-flash",
      thinking: "disabled",
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
      thinking_options: ["disabled", "enabled"],
      config_fields: [
        { id: "model", label: "Default model", kind: "text", value: "deepseek-v4-flash", placeholder: "", options: [], required: true, secret: false, read_only: false, help: "" },
        { id: "thinking", label: "Thinking", kind: "select", value: "disabled", placeholder: "", options: ["disabled", "enabled"], required: false, secret: false, read_only: false, help: "" },
        { id: "context_window", label: "Context window", kind: "number", value: 1000000, placeholder: "1000000", options: [], required: false, secret: false, read_only: false, help: "Model context length used by AITeamOS context loading; DeepSeek V4 supports 1M." },
        { id: "max_tokens", label: "Max output tokens", kind: "number", value: 384000, placeholder: "384000", options: [], required: false, secret: false, read_only: false, help: "Sent as DeepSeek max_tokens. DeepSeek V4 max output is 384K." },
        { id: "base_url", label: "Base URL", kind: "text", value: "https://api.deepseek.com", placeholder: "", options: [], required: true, secret: false, read_only: false, help: "" },
        { id: "api_key_env", label: "API key env", kind: "text", value: "DEEPSEEK_API_KEY", placeholder: "", options: [], required: true, secret: true, read_only: false, help: "" },
      ],
      chat_options: [
        { id: "thinking", label: "Reasoning", kind: "select", value: "disabled", placeholder: "", options: ["disabled", "enabled"], required: false, secret: false, read_only: false, help: "" },
      ],
      health_detail: "Ready for Chat selection.",
    },
    openai: {
      id: "openai",
      display_name: "ChatGPT / OpenAI API",
      kind: "llm_api",
      description: "OpenAI Responses API engine.",
      support_status: "supported",
      config_status: "missing_secret",
      auth_kind: "bearer",
      base_url: "https://api.openai.com/v1",
      api_key_env: "OPENAI_API_KEY",
      model: "gpt-5-nano",
      enabled: true,
      editable: true,
      active: false,
      api_key_configured: false,
      status: "missing_secret",
      secret_env_vars: ["OPENAI_API_KEY"],
      capabilities: ["chat", "responses", "graphiti_llm"],
      model_options: ["gpt-5-nano"],
      thinking_options: [],
      config_fields: [
        { id: "model", label: "Default model", kind: "text", value: "gpt-5-nano", placeholder: "", options: [], required: true, secret: false, read_only: false, help: "" },
        { id: "base_url", label: "Base URL", kind: "text", value: "https://api.openai.com/v1", placeholder: "", options: [], required: true, secret: false, read_only: false, help: "" },
        { id: "api_key_env", label: "API key env", kind: "text", value: "OPENAI_API_KEY", placeholder: "", options: [], required: true, secret: true, read_only: false, help: "" },
      ],
      chat_options: [],
      health_detail: "Configuration is saved, but the referenced API key environment variable is missing.",
    },
  },
  api_keys_configured: { deepseek: true, openai: false },
  catalog_order: ["stub", "deepseek", "openai"],
  saved_paths: { ai_engines: ".aiteamos/ai_engines.json" },
};

const employees = [
  {
    id: "clara",
    display_name: "Clara",
    kind: "ai",
    role: "AI Team OS Manager",
    summary: "Coordinator",
    skills: [],
    ai_engine_mode: "deepseek_chat_or_file_stub",
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
    enabled: false,
    configured: false,
    graph_configured: false,
    llm_configured: false,
    package_installed: true,
    status: "disabled",
    detail: "Graphiti is not enabled.",
    group_id: "aiteamos",
    graph_database: "neo4j",
    uri: "",
    user: "neo4j",
    llm_ai_engine: "openai",
    llm_ai_engine_name: "ChatGPT / OpenAI API",
    llm_api_key_env: "OPENAI_API_KEY",
    password_configured: false,
    llm_api_key_configured: false,
  },
  candidate_count: 2,
  approved_count: 1,
  pending_graphiti_count: 0,
  saved_paths: {},
};

const graphitiSettings = {
  enabled: false,
  graph_database: "neo4j",
  uri: "bolt://localhost:7687",
  user: "neo4j",
  group_id: "aiteamos",
  llm_ai_engine: "openai",
  llm_ai_engine_name: "ChatGPT / OpenAI API",
  llm_api_key_env: "OPENAI_API_KEY",
  password_configured: false,
  llm_api_key_configured: false,
  saved_paths: { settings: ".aiteamos/graphiti.json" },
  backend: memory.backend,
};

const capabilityRegistry = {
  status: {
    capability_count: 3,
    enabled_count: 1,
    configured_count: 1,
    ready_count: 1,
    tool_count: 3,
    kernel_command_count: 1,
    mcp_tool_count: 2,
    native_api_tool_count: 0,
    cli_tool_count: 0,
    ci_tool_count: 0,
    saved_paths: { registry: ".aiteamos/tool_connectors.json" },
  },
  capabilities: [
    {
      id: "list_employees",
      name: "List employees",
      kind: "tool",
      source_kind: "kernel_command",
      domain: "employees",
      source: "AITeamOS Kernel",
      status: "ready",
      enabled: true,
      configured: true,
      description: "List file-backed employees.",
      owner_scope: "Clara and authorized employees",
      permissions: ["employees:read"],
      required_settings: [],
      arguments: [],
      produces: ["chat_result"],
      boundary: "Read-only employee inventory.",
      deep_link: "#/employees",
      connector_id: "",
    },
    {
      id: "mcp:github:repo.search",
      name: "repo.search",
      kind: "tool",
      source_kind: "mcp_server",
      domain: "repo",
      source: "MCP server: GitHub",
      status: "planned",
      enabled: false,
      configured: false,
      description: "GitHub exposes repo.search.",
      owner_scope: "Authorized employees through connector adapter",
      permissions: ["repo:read"],
      required_settings: ["owner", "repo"],
      arguments: [],
      produces: ["external_result"],
      boundary: "External system semantics stay behind the connector adapter.",
      deep_link: "#/settings/tool-connectors",
      connector_id: "github",
    },
  ],
  model: {
    tool: "executable action exposed through Kernel commands, MCP servers, native APIs, CLIs, CI, or AI engine bridges",
    connector: "settings-side external capability source",
  },
};

const ticketBackendModes = [
  {
    id: "local_file",
    label: "Local file",
    status: "legacy",
    description: "Legacy local projection.",
  },
  {
    id: "plane",
    label: "Plane",
    status: "ready",
    description: "Plane-backed Ticket fact source.",
  },
];

const ticketBackendSettings = {
  mode: "plane",
  local_file_path: ".aiteamos/tickets/index.json",
  plane_api_base_url: "https://api.plane.so",
  plane_web_base_url: "https://app.plane.so",
  plane_workspace_slug: "ait",
  plane_project_id: "plane-project-1",
  plane_api_key_env: "PLANE_API_KEY",
  plane_namespace_strategy: "label",
  plane_namespace_label_ids: { rd: "label-rd" },
  plane_state_ids: { assigned: "state-assigned" },
  plane_employee_assignee_ids: { alex: "plane-user-alex" },
  saved_paths: {
    settings: ".aiteamos/tickets/backend.json",
    plane_projection: ".aiteamos/tickets/plane",
  },
  supported_modes: ticketBackendModes,
};

let activeTicketBackendSettings: Record<string, unknown> = ticketBackendSettings;

const ticketBackendStatus = {
  mode: "plane",
  status: "ready",
  detail: "Plane Ticket Backend is active.",
  ticket_count: 2,
  local_file_path: ".aiteamos/tickets/index.json",
  provider: "plane",
  provider_ref_count: 2,
  setup_required: [],
  plane_setup: {
    status: "ready",
    detail: "Plane Ticket Backend is selected and configured.",
    selected: true,
    configured: true,
    active_mode: "plane",
    active_provider: "plane",
    required_mode: "plane",
    workspace_configured: true,
    project_configured: true,
    api_key_env: "PLANE_API_KEY",
    api_key_configured: true,
    setup_required: [],
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
        repository_id: "repo-aiteamos",
        repository_name: "AITeamOS",
        provider: "local",
        status: "ready",
        workspace_configured: true,
        project_configured: true,
        plane_workspace_slug: "ait",
        plane_project_id: "aiteamos",
        deep_link: "#/settings/code-repositories",
      },
    ],
    code_repository_scope_missing: [] as Record<string, unknown>[],
  },
  release_target: {
    status: "ready",
    ready: true,
    detail: "Plan v8 release target is ready: Plane is active, configured, and backed by an available Code Repository Plane scope.",
    active_mode: "plane",
    required_mode: "plane",
    required_scope_status: "available",
    code_repository_scope_status: "available",
    blockers: [] as string[],
    setup_required: [] as string[],
    setup_action: "none",
  },
  capabilities: ["create_ticket", "append_report_comment"],
  mapping: {
    Ticket: "provider record",
    report: "Plane comment with AITeamOS metadata",
  },
  saved_paths: ticketBackendSettings.saved_paths,
  supported_modes: ticketBackendModes,
};

let activeTicketBackendStatus: Record<string, unknown> = ticketBackendStatus;

const toolConnectors = [
  {
    id: "mcp-server",
    name: "MCP Server",
    status: "planned",
    transport: "mcp",
    enabled: false,
    configured: false,
    description: "Generic MCP server entry point.",
    capabilities: [],
    permissions: [],
    required_settings: ["server_command_or_url"],
    server: {},
    updated_at: "2026-06-03T00:00:00Z",
  },
  {
    id: "github",
    name: "GitHub",
    status: "planned",
    transport: "mcp",
    enabled: false,
    configured: false,
    description: "Repository, pull request, and issue connector.",
    capabilities: ["repo.search", "pull_requests.read"],
    permissions: ["repo:read"],
    required_settings: ["owner", "repo"],
    server: {},
    updated_at: "2026-06-03T00:00:00Z",
  },
];

const toolConnectorStatus = {
  connector_count: 2,
  enabled_count: 0,
  configured_count: 0,
  ready_count: 0,
  saved_paths: { registry: ".aiteamos/tool_connectors.json" },
};

const codeRepositories = [
  {
    id: "repo-aiteamos",
    name: "AITeamOS",
    provider: "local",
    location: "/home/shiqiangli/projects/AITeamOS",
    default_branch: "main",
    plane_workspace_slug: "ait",
    plane_project_id: "aiteamos",
    description: "Main local checkout.",
    enabled: true,
    status: "ready",
    detail: "Local Git repository is available.",
    git_detected: true,
    current_branch: "main",
    created_at: "2026-06-03T00:00:00Z",
    updated_at: "2026-06-03T00:00:00Z",
    saved_path: ".aiteamos/code_repositories.json",
  },
];

let activeCodeRepositories = codeRepositories;

const planeScopeDiscovery = {
  status: "ready",
  detail: "Plane scope discovery found workspace/project candidates.",
  api_key_env: "PLANE_API_KEY",
  api_key_configured: true,
  external_calls: true,
  checks: ["plane_workspace_list_requested", "plane_project_list_requested"],
  setup_required: [] as string[],
  suggestions: [
    {
      source: "plane_discovery",
      plane_workspace_slug: "ait",
      plane_project_id: "plane-project-1",
      workspace_name: "AITeamOS",
      project_name: "Core Loop",
      status: "available",
      deep_link: "#/settings/code-repositories",
    },
  ],
  evidence: {
    workspace_count: 1,
    project_count: 1,
  },
};

let activePlaneScopeDiscovery: Record<string, unknown> = planeScopeDiscovery;

function codeRepositoryStatus() {
  const enabledRepositories = activeCodeRepositories.filter((repository) => repository.enabled);
  const candidates = enabledRepositories
    .filter((repository) => repository.plane_workspace_slug && repository.plane_project_id)
    .map((repository) => ({
      source: "code_repository",
      repository_id: repository.id,
      repository_name: repository.name,
      provider: repository.provider,
      status: repository.status,
      plane_workspace_slug: repository.plane_workspace_slug,
      plane_project_id: repository.plane_project_id,
      deep_link: "#/settings/code-repositories",
    }));
  const missing = enabledRepositories
    .filter((repository) => !repository.plane_workspace_slug || !repository.plane_project_id)
    .map((repository) => ({
      source: "code_repository",
      repository_id: repository.id,
      repository_name: repository.name,
      provider: repository.provider,
      status: repository.status,
      workspace_configured: Boolean(repository.plane_workspace_slug),
      project_configured: Boolean(repository.plane_project_id),
      deep_link: "#/settings/code-repositories",
    }));
  const backendWorkspace = String(activeTicketBackendSettings.plane_workspace_slug ?? "");
  const backendProject = String(activeTicketBackendSettings.plane_project_id ?? "");
  const suggestions = backendWorkspace && backendProject
    ? [
      {
        source: "ticket_backend",
        mode: String(activeTicketBackendSettings.mode ?? ""),
        plane_workspace_slug: backendWorkspace,
        plane_project_id: backendProject,
        settings_path: ".aiteamos/tickets/backend.json",
        deep_link: "#/settings/ticket-backend",
        status: "available",
      },
    ]
    : [];
  const planeScopeStatus = candidates.length ? "available" : missing.length ? "incomplete" : "missing";
  return {
    repository_count: activeCodeRepositories.length,
    enabled_count: enabledRepositories.length,
    ready_count: activeCodeRepositories.filter((repository) => ["ready", "configured"].includes(repository.status)).length,
    local_count: activeCodeRepositories.filter((repository) => repository.provider === "local").length,
    remote_count: activeCodeRepositories.filter((repository) => repository.provider !== "local").length,
    plane_scope_status: planeScopeStatus,
    plane_scope_detail: candidates.length
      ? "Code Repository registry has Plane workspace/project scope candidates."
      : suggestions.length && missing.length
      ? "Code Repository registry has no ready Plane scope, but Ticket Backend has Plane workspace/project values."
      : missing.length
      ? "Code Repository registry has repositories, but none has both Plane workspace and project configured."
      : "No enabled Code Repository can provide a Plane workspace/project scope candidate.",
    plane_scope_candidate_count: candidates.length,
    plane_scope_missing_count: missing.length,
    plane_scope_setup_action: candidates.length
      ? "apply_code_repository_plane_scope_to_ticket_backend"
      : suggestions.length && missing.length
      ? "copy_ticket_backend_plane_scope_to_code_repository"
      : missing.length
      ? "add_plane_scope_to_code_repository_or_ticket_backend"
      : "configure_plane_scope_in_ticket_backend",
    plane_scope_candidates: candidates,
    plane_scope_missing: missing,
    plane_scope_suggestions: suggestions,
    saved_paths: { registry: ".aiteamos/code_repositories.json" },
  };
}

const runtimeExecutors = {
  executors: [
    {
      executor_id: "claude_code",
      display_name: "Claude Code-compatible Local CLI Executor",
      status: "setup_blocked",
      detail: "Claude Code-compatible Local CLI Executor is not configured.",
      capabilities: ["agent_loop", "repo:read", "repo:write", "compatible_local_cli"],
      setup_required: ["CLAUDE_CODE_BIN"],
      diagnostics: {
        smoke: { endpoint: "/api/v1/runtime-executors/claude_code/smoke", method: "POST" },
        mutation_guard: { required: ["ticket_bound", "approval_bound", "evidence_bound"] },
      },
      health: {
        config: {
          model: "deepseek-coder",
          api_key_env: "DEEPSEEK_API_KEY",
        },
      },
    },
    {
      executor_id: "cursor",
      display_name: "Cursor Executor",
      status: "setup_blocked",
      detail: "Cursor Executor is not configured.",
      capabilities: ["agent_loop", "repo:read", "repo:write", "commercial_agent_backend"],
      setup_required: ["CURSOR_API_KEY"],
      diagnostics: {},
      health: {},
    },
  ],
  summary: { executor_count: 2, ready_count: 0, blocked_count: 2, runtime_boundary: "RuntimeExecutor" },
  blockers: [{ executor_id: "claude_code", status: "setup_blocked" }],
};

const runtimeExecutorConfigs = {
  executors: {
    claude_code: {
      executor_id: "claude_code",
      enabled: true,
      binary_path: "/tmp/claude-code-compatible",
      working_dir: "/home/shiqiangli/projects/AITeamOS",
      command_template: "{binary}",
      model: "deepseek-coder",
      api_base_url: "https://api.deepseek.com",
      api_key_env: "DEEPSEEK_API_KEY",
      http_endpoint_path: "",
      mode: "non_destructive_inspect_and_report",
      timeout_seconds: 120,
      saved_path: ".aiteamos/runtime_executors.json",
    },
  },
  saved_paths: { runtime_executors: ".aiteamos/runtime_executors.json" },
};

const runtimeApprovals = [
  {
    id: "approval-exec-chat-runtime-mutation-1",
    status: "requested",
    kind: "runtime_approval",
    ticket_id: "rd-9999",
    employee_id: "alex",
    executor_id: "claude_code",
    required_capability: "repo:write",
    risk_level: "high",
    reason: "External runtime repo mutation requires approval before execution.",
    proposed_action: { action: "implement_ticket", executor_id: "claude_code" },
    source_state_ref: "state://universal_employee_agent/exec-chat-runtime-mutation/governance_gate",
    source_state_snapshot_ref: ".aiteamos/execution_state_snapshots/exec-chat-runtime-mutation.json",
    current_graph_node: "governance_gate",
    checkpoint_ref: "langgraph:exec-chat-runtime-mutation",
    executor_session_ref: "lg-exec-chat-runtime-mutation",
    approval_request: {},
    source_request: {},
    source_result: {},
    created_at: "2026-06-18T00:00:00Z",
    updated_at: "2026-06-18T00:00:00Z",
    reviewed_at: "",
    reviewer_employee_id: "",
    review_reason: "",
    last_run_request_id: "",
    last_run_status: "",
    last_ingestion_blocker: "",
    last_result: {},
    resume_result: {},
    run_history: [
      {
        run_request_id: "exec-chat-runtime-mutation-approved-approval-exec-chat-runtime-mutation-1-attempt-1",
        status: "completed",
        resume_source: "checkpoint_state",
        resume_source_state_snapshot_ref: ".aiteamos/execution_state_snapshots/exec-chat-runtime-mutation.json",
      },
    ],
  },
];

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

const runtimeExecutionReplay = {
  session: runtimeExecutionSessions[0],
  execution_artifacts: {
    request_id: "exec-chat-runtime-mutation",
    artifacts: [{ kind: "runtime_session_artifact", ref: "artifact://runtime-session", api_key: "[redacted]" }],
    evidence: [{ kind: "test_evidence", ref: "pytest::runtime-session::passed" }],
  },
  approvals: runtimeApprovals,
  state_snapshots: [
    {
      approval_id: "approval-exec-chat-runtime-mutation-1",
      source_state_ref: "state://universal_employee_agent/exec-chat-runtime-mutation/governance_gate",
      source_state_snapshot_ref: ".aiteamos/execution_state_snapshots/exec-chat-runtime-mutation.json",
      snapshot_schema: "execution_state_snapshot.v1",
      checkpoint_ref: "langgraph:exec-chat-runtime-mutation",
      current_graph_node: "governance_gate",
      state_summary: {
        request_id: "exec-chat-runtime-mutation",
        action: "implement_ticket",
        current_step: "governance_gate",
        error_count: 1,
      },
      state_delta: {
        from: "execution_request",
        to: "governance_gate",
        changed_keys: ["approval_interrupt", "errors"],
      },
      graph_state: { execution_request: { request_id: "exec-chat-runtime-mutation" }, api_key: "[redacted]" },
    },
  ],
  native_checkpoint_history: [
    {
      index: 0,
      thread_id: "exec-chat-runtime-mutation",
      checkpoint_id: "checkpoint-native-1",
      metadata: { step: 5 },
      next: ["request_approval_interrupt"],
      state_summary: {
        request_id: "exec-chat-runtime-mutation",
        action: "implement_ticket",
        current_step: "request_approval_interrupt",
      },
      state_delta: {
        from: "governance_gate",
        to: "request_approval_interrupt",
        changed_keys: ["approval_interrupt", "errors"],
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
      changed_keys: ["approval_interrupt", "errors"],
      checkpoint_ref: "langgraph:exec-chat-runtime-mutation",
      source_state_ref: "state://universal_employee_agent/exec-chat-runtime-mutation/governance_gate",
      source_state_snapshot_ref: ".aiteamos/execution_state_snapshots/exec-chat-runtime-mutation.json",
    },
  ],
  trace_events: [
    { event: "trace.step", authorization: "[redacted]", data: { token: "[redacted]", visible: "yes" } },
  ],
  timeline: [
    { index: 0, kind: "session", event: "execution.session", title: "Execution session needs_approval", refs: [] },
    { index: 1, kind: "tool_event", event: "universal_agent.tool.completed", title: "search_tickets", refs: [{ kind: "ticket", ref: "rd-9999" }] },
    { index: 2, kind: "artifact", event: "runtime_session_artifact", title: "runtime_session_artifact", refs: [{ kind: "artifact", ref: "artifact://runtime-session" }] },
    { index: 3, kind: "evidence", event: "test_evidence", title: "test_evidence", refs: [{ kind: "evidence", ref: "pytest::runtime-session::passed" }] },
    { index: 4, kind: "approval_run", event: "approval.run.completed", title: "approval run completed", refs: [{ kind: "approval", ref: "approval-exec-chat-runtime-mutation-1" }] },
    { index: 5, kind: "state_snapshot", event: "execution.state_snapshot", title: "State snapshot governance_gate", refs: [{ kind: "state", ref: "state://universal_employee_agent/exec-chat-runtime-mutation/governance_gate" }] },
    { index: 6, kind: "state_transition", event: "execution.state_transition", title: "execution_request -> governance_gate", refs: [] },
    { index: 7, kind: "trace", event: "trace.step", title: "trace.step", refs: [] },
  ],
};

describe("SettingsPage", () => {
  beforeEach(() => {
    activeTicketBackendSettings = ticketBackendSettings;
    activeTicketBackendStatus = ticketBackendStatus;
    activeCodeRepositories = codeRepositories;
    activePlaneScopeDiscovery = planeScopeDiscovery;
    clipboardWrite = vi.fn(async () => undefined);
    Object.defineProperty(window.navigator, "clipboard", {
      configurable: true,
      value: { writeText: clipboardWrite },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/chat/ai-engines")) {
          return new Response(JSON.stringify(aiEngines), { status: 200, headers: { "Content-Type": "application/json" } });
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
        if (url.endsWith("/memory/graphiti/settings")) {
          return new Response(JSON.stringify(graphitiSettings), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/capabilities")) {
          return new Response(JSON.stringify(capabilityRegistry), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/tickets/backend") && init?.method === "PUT") {
          const payload = JSON.parse(String(init.body ?? "{}"));
          activeTicketBackendSettings = {
            ...ticketBackendSettings,
            ...payload,
            saved_paths: ticketBackendSettings.saved_paths,
            supported_modes: ticketBackendModes,
          };
          return new Response(JSON.stringify(activeTicketBackendSettings), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/tickets/backend")) {
          return new Response(JSON.stringify(activeTicketBackendSettings), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/tickets/status")) {
          return new Response(JSON.stringify(activeTicketBackendStatus), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/tickets/backend/plane-scope/discovery")) {
          return new Response(JSON.stringify(activePlaneScopeDiscovery), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/tool-connectors/connectors")) {
          return new Response(JSON.stringify(toolConnectors), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/tool-connectors/status")) {
          return new Response(JSON.stringify(toolConnectorStatus), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.includes("/code-repositories/") && init?.method === "PUT") {
          const repositoryId = url.split("/").pop() ?? "";
          const payload = JSON.parse(String(init.body ?? "{}"));
          const existing = activeCodeRepositories.find((repository) => repository.id === repositoryId) ?? activeCodeRepositories[0]!;
          const updated = { ...existing, ...payload, id: repositoryId, status: "ready" };
          activeCodeRepositories = activeCodeRepositories.map((repository) => (repository.id === repositoryId ? updated : repository));
          return new Response(JSON.stringify(updated), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/code-repositories")) {
          return new Response(JSON.stringify(activeCodeRepositories), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/code-repositories/status")) {
          return new Response(JSON.stringify(codeRepositoryStatus()), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/runtime-executors")) {
          return new Response(JSON.stringify(runtimeExecutors), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/runtime-executors/config")) {
          return new Response(JSON.stringify(runtimeExecutorConfigs), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/runtime-executors/approvals")) {
          return new Response(JSON.stringify(runtimeApprovals), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/runtime-executors/sessions")) {
          return new Response(JSON.stringify(runtimeExecutionSessions), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/runtime-executors/sessions/alex%3A%3Athread-runtime%3A%3Ard-9999")) {
          return new Response(JSON.stringify(runtimeExecutionReplay), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/runtime-executors/claude_code/config")) {
          return new Response(JSON.stringify(runtimeExecutorConfigs.executors.claude_code), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        return new Response("not found", { status: 404 });
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders AI Engine settings and configured secret state", async () => {
    render(<SettingsPage selectedSection="ai-engines" />);

    expect(await screen.findByText("AI Engines")).toBeTruthy();
    expect(screen.getByText("Missing secrets")).toBeTruthy();
    expect(screen.getByText("Engine Catalog")).toBeTruthy();
    expect(screen.getAllByText("DeepSeek").length).toBeGreaterThan(0);
    expect(screen.getByText("Save engine")).toBeTruthy();
    expect(screen.getByLabelText("Context window")).toBeTruthy();
    expect(screen.getByLabelText("Max output tokens")).toBeTruthy();
    expect(screen.getByLabelText("API key env")).toBeTruthy();
  });

  it("renders Ticket Backend settings", async () => {
    render(<SettingsPage selectedSection="ticket-backend" />);

    expect((await screen.findAllByText("Ticket Backend")).length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Ticket backend mode")).toBeTruthy();
    expect(screen.getByLabelText("Legacy projection file")).toBeTruthy();
    expect(screen.getByLabelText("Plane API base URL")).toBeTruthy();
    expect(screen.getByLabelText("Plane workspace slug")).toBeTruthy();
    expect(screen.getByText("Plan v8 release target")).toBeTruthy();
    expect(screen.getByText("Plan v8 release target is ready: Plane is active, configured, and backed by an available Code Repository Plane scope.")).toBeTruthy();
    expect(screen.getByText("Plane setup preflight")).toBeTruthy();
    expect(screen.getAllByText("scope available").length).toBeGreaterThan(0);
    expect(screen.getAllByText("1/1 scope candidates").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Use scope" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Apply scope" })).toBeTruthy();
    expect(screen.getByText("Provider readiness smoke")).toBeTruthy();
    expect(screen.getByText(liveProviderReadinessSmokeCommand)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Copy Provider readiness smoke command" }));
    await waitFor(() => expect(clipboardWrite).toHaveBeenCalledWith(liveProviderReadinessSmokeCommand));
    expect(screen.getByRole("button", { name: "Provider readiness smoke command copied" })).toBeTruthy();
    expect(screen.getByText("Plane action smoke")).toBeTruthy();
    expect(screen.getByText(planeActionSmokeCommand)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Copy Plane action smoke command" }));
    await waitFor(() => expect(clipboardWrite).toHaveBeenCalledWith(planeActionSmokeCommand));
    expect(screen.getByRole("button", { name: "Plane action smoke command copied" })).toBeTruthy();
    expect(screen.getByText("Live dogfood gate")).toBeTruthy();
    expect(screen.getByText("mutation gate")).toBeTruthy();
    expect(screen.getByText(liveDogfoodSoakCommand)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Copy Live dogfood soak command" }));
    await waitFor(() => expect(clipboardWrite).toHaveBeenCalledWith(liveDogfoodSoakCommand));
    expect(screen.getByRole("button", { name: "Live dogfood soak command copied" })).toBeTruthy();
    expect(screen.getByLabelText("Plane namespace label mapping")).toBeTruthy();
    expect(screen.getByText("Plane mapping")).toBeTruthy();
    expect(screen.getByText("Save Ticket backend")).toBeTruthy();
  });

  it("applies complete repository scope to Ticket Backend", async () => {
    render(<SettingsPage selectedSection="ticket-backend" />);

    expect(await screen.findByText("Plane setup preflight")).toBeTruthy();
    const statusCallCount = vi.mocked(fetch).mock.calls.filter(([input]) => String(input).endsWith("/tickets/status")).length;
    fireEvent.click(screen.getByRole("button", { name: "Apply scope" }));

    await waitFor(() => {
      expect(
        vi.mocked(fetch).mock.calls.some(([input, init]) => String(input).endsWith("/tickets/backend") && init?.method === "PUT"),
      ).toBe(true);
    });
    const saveCall = vi.mocked(fetch).mock.calls.find(([input, init]) => String(input).endsWith("/tickets/backend") && init?.method === "PUT");
    expect(JSON.parse(String(saveCall?.[1]?.body))).toMatchObject({
      mode: "plane",
      plane_workspace_slug: "ait",
      plane_project_id: "aiteamos",
    });
    await waitFor(() => {
      expect(vi.mocked(fetch).mock.calls.filter(([input]) => String(input).endsWith("/tickets/status")).length).toBeGreaterThan(statusCallCount);
    });
  });

  it("opens incomplete repository scope config from Ticket Backend preflight", async () => {
    window.location.hash = "#/settings/ticket-backend";
    activeCodeRepositories = codeRepositories.map((repository) => ({
      ...repository,
      plane_workspace_slug: "",
      plane_project_id: "",
    }));
    activeTicketBackendStatus = {
      ...ticketBackendStatus,
      mode: "local_file",
      provider: "",
      release_target: {
        status: "blocked",
        ready: false,
        detail: "Plan v8 release requires Plane as the active Ticket Backend, complete Plane workspace/project/API setup, and an available Code Repository Plane scope.",
        active_mode: "local_file",
        required_mode: "plane",
        required_scope_status: "available",
        code_repository_scope_status: "incomplete",
        blockers: ["plane_ticket_backend_not_selected", "plane_workspace_slug_missing", "plane_project_id_missing", "code_repository_plane_scope_incomplete"],
        setup_required: ["PUT /api/v1/tickets/backend mode=plane", "plane_workspace_slug", "plane_project_id"],
        setup_action: "select_plane_ticket_backend",
      },
      plane_setup: {
        ...ticketBackendStatus.plane_setup,
        status: "setup_blocked",
        detail: "Plane Ticket backend is not selected and Plane workspace/project setup is incomplete.",
        selected: false,
        configured: false,
        active_mode: "local_file",
        active_provider: "",
        workspace_configured: false,
        project_configured: false,
        setup_required: ["PUT /api/v1/tickets/backend mode=plane", "plane_workspace_slug", "plane_project_id"],
        code_repository_scope_status: "incomplete",
        code_repository_scope_detail: "Code Repository registry has repositories, but none has both Plane workspace and project configured.",
        code_repository_scope_candidate_count: 0,
        code_repository_scope_missing_count: 1,
        code_repository_scope_candidates: [],
        code_repository_scope_missing: [
          {
            source: "code_repository",
            repository_id: "repo-aiteamos",
            repository_name: "AITeamOS",
            provider: "local",
            status: "ready",
            workspace_configured: false,
            project_configured: false,
            deep_link: "#/settings/code-repositories",
          },
        ],
      },
    };

    render(<SettingsPage selectedSection="ticket-backend" />);

    expect(await screen.findByText("Plane setup preflight")).toBeTruthy();
    expect(screen.getByText("plane_ticket_backend_not_selected")).toBeTruthy();
    expect(screen.getByText(/Release blockers:/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Edit scope" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Edit scope" }));

    expect(window.location.hash).toBe("#/settings/code-repositories");
    expect(await screen.findByText("Configure Repository")).toBeTruthy();
    expect(screen.getByLabelText("Repository Plane workspace")).toBeTruthy();
    expect(screen.getByLabelText("Repository Plane project")).toBeTruthy();

    const statusCallCount = vi.mocked(fetch).mock.calls.filter(([input]) => String(input).endsWith("/tickets/status")).length;
    fireEvent.change(screen.getByLabelText("Repository Plane workspace"), { target: { value: "ait" } });
    fireEvent.change(screen.getByLabelText("Repository Plane project"), { target: { value: "aiteamos" } });
    fireEvent.click(screen.getByRole("button", { name: "Save repository" }));

    await waitFor(() => {
      expect(
        vi.mocked(fetch).mock.calls.some(([input, init]) => String(input).endsWith("/code-repositories/repo-aiteamos") && init?.method === "PUT"),
      ).toBe(true);
    });
    await waitFor(() => {
      expect(vi.mocked(fetch).mock.calls.filter(([input]) => String(input).endsWith("/tickets/status")).length).toBeGreaterThan(statusCallCount);
    });
  });

  it("renders Tool Connectors section", async () => {
    render(<SettingsPage selectedSection="tool-connectors" />);

    expect((await screen.findAllByText("Tool Connectors")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("MCP Server").length).toBeGreaterThan(0);
    expect(screen.getByText("GitHub")).toBeTruthy();
    expect(screen.getByText("repo.search")).toBeTruthy();
  });

  it("renders Code Repositories settings", async () => {
    render(<SettingsPage selectedSection="code-repositories" />);

    expect(await screen.findByText("Repository List")).toBeTruthy();
    expect(screen.getByText("Plane Scope Preflight")).toBeTruthy();
    expect(screen.getByText("Code Repository registry has Plane workspace/project scope candidates.")).toBeTruthy();
    expect(screen.getAllByText("scope available").length).toBeGreaterThan(0);
    expect(screen.getByText("1/1 scope candidates")).toBeTruthy();
    expect(screen.getAllByText("Workspace: ait").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Project: aiteamos").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Code Repositories").length).toBeGreaterThan(0);
    expect(screen.getAllByText("AITeamOS").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "Add" }).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Config" }));

    expect(await screen.findByLabelText("Repository location")).toBeTruthy();
    expect(screen.getByText("Configure Repository")).toBeTruthy();
  });

  it("opens repository scope config from Code Repositories Plane preflight", async () => {
    activeCodeRepositories = codeRepositories.map((repository) => ({
      ...repository,
      plane_workspace_slug: "",
      plane_project_id: "",
    }));

    render(<SettingsPage selectedSection="code-repositories" />);

    expect(await screen.findByText("Plane Scope Preflight")).toBeTruthy();
    expect(screen.getByText("Code Repository registry has no ready Plane scope, but Ticket Backend has Plane workspace/project values.")).toBeTruthy();
    expect(screen.getByText("Ticket Backend scope")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Use Ticket Backend scope" })).toBeTruthy();
    expect(screen.getAllByText("scope incomplete").length).toBeGreaterThan(0);
    expect(screen.getByText("0/1 scope candidates")).toBeTruthy();
    expect(screen.getByText("Workspace: missing")).toBeTruthy();
    expect(screen.getByText("Project: missing")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Edit scope" }));

    expect(await screen.findByText("Configure Repository")).toBeTruthy();
    expect(screen.getByLabelText("Repository Plane workspace")).toBeTruthy();
    expect(screen.getByLabelText("Repository Plane project")).toBeTruthy();
  });

  it("prefills repository Plane scope from Ticket Backend suggestion", async () => {
    activeCodeRepositories = codeRepositories.map((repository) => ({
      ...repository,
      plane_workspace_slug: "",
      plane_project_id: "",
    }));

    render(<SettingsPage selectedSection="code-repositories" />);

    expect(await screen.findByText("Plane Scope Preflight")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Use Ticket Backend scope" }));

    expect(await screen.findByText("Configure Repository")).toBeTruthy();
    expect((screen.getByLabelText("Repository Plane workspace") as HTMLInputElement).value).toBe("ait");
    expect((screen.getByLabelText("Repository Plane project") as HTMLInputElement).value).toBe("plane-project-1");

    fireEvent.click(screen.getByRole("button", { name: "Save repository" }));
    await waitFor(() => {
      expect(
        vi.mocked(fetch).mock.calls.some(([input, init]) => String(input).endsWith("/code-repositories/repo-aiteamos") && init?.method === "PUT"),
      ).toBe(true);
    });
    const saveCall = vi.mocked(fetch).mock.calls.find(([input, init]) => String(input).endsWith("/code-repositories/repo-aiteamos") && init?.method === "PUT");
    expect(JSON.parse(String(saveCall?.[1]?.body))).toMatchObject({
      plane_workspace_slug: "ait",
      plane_project_id: "plane-project-1",
    });
  });

  it("discovers Plane scope candidates and prefills repository scope", async () => {
    activeTicketBackendSettings = {
      ...ticketBackendSettings,
      plane_workspace_slug: "",
      plane_project_id: "",
    };
    activeCodeRepositories = codeRepositories.map((repository) => ({
      ...repository,
      plane_workspace_slug: "",
      plane_project_id: "",
    }));

    render(<SettingsPage selectedSection="code-repositories" />);

    expect(await screen.findByText("Plane Scope Preflight")).toBeTruthy();
    expect(screen.queryByText("Plane discovery scope")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Discover Plane scope" }));

    await waitFor(() => {
      expect(vi.mocked(fetch).mock.calls.some(([input]) => String(input).endsWith("/tickets/backend/plane-scope/discovery"))).toBe(true);
    });
    expect(await screen.findByText("Plane discovery scope")).toBeTruthy();
    expect(screen.getByText("Workspace: ait")).toBeTruthy();
    expect(screen.getByText("Project: plane-project-1")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Use discovered scope" }));

    expect(await screen.findByText("Configure Repository")).toBeTruthy();
    expect((screen.getByLabelText("Repository Plane workspace") as HTMLInputElement).value).toBe("ait");
    expect((screen.getByLabelText("Repository Plane project") as HTMLInputElement).value).toBe("plane-project-1");
  });

  it("opens Ticket Backend from Code Repositories Plane preflight", async () => {
    window.location.hash = "";
    render(<SettingsPage selectedSection="code-repositories" />);

    expect(await screen.findByText("Plane Scope Preflight")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Ticket Backend" }));

    expect(window.location.hash).toBe("#/settings/ticket-backend");
    expect(await screen.findByLabelText("Ticket backend mode")).toBeTruthy();
    expect(screen.getByText("Plane setup preflight")).toBeTruthy();
  });

  it("updates the visible Settings section when the route section prop changes", async () => {
    const view = render(<SettingsPage selectedSection="code-repositories" />);

    expect(await screen.findByText("Repository List")).toBeTruthy();
    expect(screen.getByText("Plane Scope Preflight")).toBeTruthy();

    view.rerender(<SettingsPage selectedSection="ticket-backend" />);

    await waitFor(() => expect(screen.getByLabelText("Ticket backend mode")).toBeTruthy());
    expect(screen.getByText("Plane setup preflight")).toBeTruthy();
    expect(screen.queryByText("Repository List")).toBeNull();
  });

  it("renders and saves Runtime Executor settings", async () => {
    render(<SettingsPage selectedSection="runtime-executors" />);

    expect(await screen.findByText("Runtime Executors")).toBeTruthy();
    expect(screen.getAllByText("Claude Code-compatible Local CLI Executor").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Runtime binary path")).toBeTruthy();
    expect(screen.getByLabelText("Runtime model")).toBeTruthy();
    expect(screen.getByLabelText("Runtime API key env")).toBeTruthy();
    expect(screen.getByText("CLAUDE_CODE_BIN")).toBeTruthy();
    expect(screen.getByText("Review Queue")).toBeTruthy();
    expect(screen.getByText("approval-exec-chat-runtime-mutation-1")).toBeTruthy();
    expect(screen.getByText("Risk: high")).toBeTruthy();
    expect(screen.getByText("Checkpoint: langgraph:exec-chat-runtime-mutation")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Approve" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reject" })).toBeTruthy();
    expect(screen.getByText("Execution Sessions")).toBeTruthy();
    expect(screen.getByText("exec-chat-runtime-mutation")).toBeTruthy();
    expect(screen.getByText("Checkpoint: claude_code:exec-chat-runtime-mutation")).toBeTruthy();
    expect(screen.getByText("search_tickets")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Replay" }));

    expect(await screen.findByText("Replay Detail")).toBeTruthy();
    expect(screen.getAllByText("runtime_session_artifact").length).toBeGreaterThan(0);
    expect(screen.getAllByText("test_evidence").length).toBeGreaterThan(0);
    expect(screen.getAllByText("approval.run.completed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("execution.state_snapshot").length).toBeGreaterThan(0);
    expect(screen.getByText("1 state snapshots")).toBeTruthy();
    expect(screen.getByText("1 native checkpoints")).toBeTruthy();
    expect(screen.getByText("Native Checkpoints")).toBeTruthy();
    expect(screen.getByText("checkpoint-native-1")).toBeTruthy();
    expect(screen.getByText("1 state transitions")).toBeTruthy();
    expect(screen.getAllByText("execution_request -> governance_gate").length).toBeGreaterThan(0);
    expect(screen.getByText(/state_summary/)).toBeTruthy();
    expect(screen.getByText(/state_delta/)).toBeTruthy();
    expect(screen.getByText(/native_checkpoint_history/)).toBeTruthy();
    expect(screen.getByText(/state_transitions/)).toBeTruthy();
    expect(screen.getAllByText("trace.step").length).toBeGreaterThan(0);
    expect(screen.getByText(/\[redacted\]/)).toBeTruthy();
    expect(vi.mocked(fetch).mock.calls.some(([input]) => String(input).endsWith("/runtime-executors/sessions/alex%3A%3Athread-runtime%3A%3Ard-9999"))).toBe(true);

    fireEvent.change(screen.getByLabelText("Runtime model"), { target: { value: "deepseek-chat" } });
    fireEvent.click(screen.getByRole("button", { name: "Save runtime executor" }));

    await waitFor(() => {
      expect(vi.mocked(fetch).mock.calls.some(([input, init]) => String(input).endsWith("/runtime-executors/claude_code/config") && init?.method === "PUT")).toBe(true);
    });
    const calls = vi.mocked(fetch).mock.calls.map(([input, init]) => ({ url: String(input), init }));
    const saveCall = calls.find((call) => call.url.endsWith("/runtime-executors/claude_code/config") && call.init?.method === "PUT");
    expect(saveCall).toBeTruthy();
    expect(JSON.parse(String(saveCall?.init?.body))).toMatchObject({
      model: "deepseek-chat",
      api_key_env: "DEEPSEEK_API_KEY",
    });
  });

  it("renders Memory Backend settings", async () => {
    render(<SettingsPage selectedSection="memory-backend" />);

    expect((await screen.findAllByText("Memory Backend")).length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Neo4j URI")).toBeTruthy();
    expect(screen.getByText("Save backend")).toBeTruthy();
  });

});
