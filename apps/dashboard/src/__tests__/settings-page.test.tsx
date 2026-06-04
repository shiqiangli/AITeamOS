import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsPage } from "../pages/settings";

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
      runtime_options: [],
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
        { id: "base_url", label: "Base URL", kind: "text", value: "https://api.deepseek.com", placeholder: "", options: [], required: true, secret: false, read_only: false, help: "" },
        { id: "api_key_env", label: "API key env", kind: "text", value: "DEEPSEEK_API_KEY", placeholder: "", options: [], required: true, secret: true, read_only: false, help: "" },
      ],
      runtime_options: [
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
      runtime_options: [],
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
    preserve_provider_thread: true,
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
    built_in_tool_count: 1,
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
      source_kind: "built_in",
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
    tool: "executable action normalized from built-in code, MCP servers, native APIs, CLIs, CI, or AI engine bridges",
    connector: "settings-side external capability source",
  },
};

const ticketBackendModes = [
  {
    id: "local_file",
    label: "Local file",
    status: "ready",
    description: "File-backed Tickets for fast local dogfooding.",
  },
  {
    id: "plane",
    label: "Plane",
    status: "planned",
    description: "Future Plane-backed source of truth.",
  },
];

const ticketBackendSettings = {
  mode: "local_file",
  local_file_path: ".aiteamos/tickets/index.json",
  saved_paths: {
    settings: ".aiteamos/tickets/backend.json",
    local_file: ".aiteamos/tickets/index.json",
  },
  supported_modes: ticketBackendModes,
};

const ticketBackendStatus = {
  mode: "local_file",
  status: "ready",
  detail: "Local file Ticket backend is active.",
  ticket_count: 2,
  local_file_path: ".aiteamos/tickets/index.json",
  saved_paths: ticketBackendSettings.saved_paths,
  supported_modes: ticketBackendModes,
};

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

const codeRepositoryStatus = {
  repository_count: 1,
  enabled_count: 1,
  ready_count: 1,
  local_count: 1,
  remote_count: 0,
  saved_paths: { registry: ".aiteamos/code_repositories.json" },
};

describe("SettingsPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
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
        if (url.endsWith("/tickets/backend")) {
          return new Response(JSON.stringify(ticketBackendSettings), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/tickets/status")) {
          return new Response(JSON.stringify(ticketBackendStatus), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/tool-connectors/connectors")) {
          return new Response(JSON.stringify(toolConnectors), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/tool-connectors/status")) {
          return new Response(JSON.stringify(toolConnectorStatus), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/code-repositories")) {
          return new Response(JSON.stringify(codeRepositories), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/code-repositories/status")) {
          return new Response(JSON.stringify(codeRepositoryStatus), { status: 200, headers: { "Content-Type": "application/json" } });
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
    expect(screen.getByLabelText("API key env")).toBeTruthy();
  });

  it("renders Ticket Backend settings", async () => {
    render(<SettingsPage selectedSection="ticket-backend" />);

    expect((await screen.findAllByText("Ticket Backend")).length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Ticket backend mode")).toBeTruthy();
    expect(screen.getByLabelText("Local Ticket file")).toBeTruthy();
    expect(screen.getByText("Save Ticket backend")).toBeTruthy();
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
    expect(screen.getAllByText("Code Repositories").length).toBeGreaterThan(0);
    expect(screen.getAllByText("AITeamOS").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "Add" }).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Config" }));

    expect(await screen.findByLabelText("Repository location")).toBeTruthy();
    expect(screen.getByText("Configure Repository")).toBeTruthy();
  });

  it("renders Memory Backend settings", async () => {
    render(<SettingsPage selectedSection="memory-backend" />);

    expect((await screen.findAllByText("Memory Backend")).length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Neo4j URI")).toBeTruthy();
    expect(screen.getByText("Save backend")).toBeTruthy();
  });

});
