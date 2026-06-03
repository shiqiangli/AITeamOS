import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CapabilitiesPage } from "../pages/capabilities";
import { SettingsPage } from "../pages/settings";

const runtime = {
  provider: "deepseek",
  deepseek_model: "deepseek-v4-flash",
  deepseek_thinking: "disabled",
  openai_model: "gpt-5-nano",
  fallback_on_error: true,
  providers: {
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
  saved_paths: {
    runtime: ".aiteamos/runtime.json",
    secrets: ".aiteamos/secrets.local.json",
  },
};

const employees = [
  {
    id: "clara",
    display_name: "Clara",
    kind: "ai",
    role: "AI Team OS Manager",
    summary: "Coordinator",
    skills: [],
    runtime_mode: "deepseek_chat_or_file_stub",
    preserve_provider_thread: true,
    default_thread_id: "employee-clara-default",
  },
];

const knowledge = {
  docs_count: 3,
  memories_count: 1,
  decisions_count: 0,
  review_queue_count: 2,
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
    llm_provider: "openai",
    password_configured: false,
    openai_api_key_configured: false,
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
  llm_provider: "openai",
  password_configured: false,
  openai_api_key_configured: false,
  uses_runtime_openai_key: false,
  saved_paths: {
    settings: ".aiteamos/graphiti.json",
    secrets: ".aiteamos/secrets.local.json",
  },
  backend: memory.backend,
};

const mcpConnectors = [
  {
    id: "plane",
    name: "Plane",
    status: "planned",
    transport: "rest",
    enabled: false,
    configured: false,
    description: "Default Ticket/Docs backend.",
    capabilities: ["tickets.search", "knowledge.docs.search"],
    permissions: ["tickets:read", "docs:read"],
    required_settings: ["base_url", "api_token", "workspace_slug"],
    server: {},
    updated_at: "2026-06-03T00:00:00Z",
  },
];

const mcpStatus = {
  connector_count: 1,
  enabled_count: 0,
  configured_count: 0,
  ready_count: 0,
  saved_paths: { registry: ".aiteamos/mcp_connectors.json" },
};

const capabilityRegistry = {
  status: {
    capability_count: 6,
    enabled_count: 3,
    configured_count: 3,
    ready_count: 3,
    local_tool_count: 2,
    mcp_capability_count: 2,
    agent_executor_count: 1,
    saved_paths: { registry: ".aiteamos/mcp_connectors.json" },
  },
  capabilities: [
    {
      id: "list_employees",
      name: "List employees",
      kind: "local_tool",
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
      id: "create_ticket",
      name: "Create ticket",
      kind: "local_tool",
      domain: "tickets",
      source: "AITeamOS Kernel",
      status: "ready",
      enabled: true,
      configured: true,
      description: "Create a local ticket.",
      owner_scope: "Clara",
      permissions: ["tickets:write"],
      required_settings: [],
      arguments: ["title"],
      produces: ["ticket"],
      boundary: "Local P0 ticket.",
      deep_link: "#/tickets/tickets",
      connector_id: "",
    },
    {
      id: "mcp:plane",
      name: "Plane",
      kind: "mcp_connector",
      domain: "external",
      source: "MCP Registry",
      status: "planned",
      enabled: false,
      configured: false,
      description: "Plane connector.",
      owner_scope: "Connector adapter",
      permissions: ["tickets:read"],
      required_settings: ["base_url"],
      arguments: [],
      produces: ["external_capabilities"],
      boundary: "Connector exposes external capabilities.",
      deep_link: "#/settings/mcp-connectors",
      connector_id: "plane",
    },
    {
      id: "mcp:plane:tickets.search",
      name: "tickets.search",
      kind: "mcp_capability",
      domain: "tickets",
      source: "MCP connector: Plane",
      status: "planned",
      enabled: false,
      configured: false,
      description: "Plane exposes tickets.search.",
      owner_scope: "Authorized employees through connector adapter",
      permissions: ["tickets:read"],
      required_settings: ["base_url"],
      arguments: [],
      produces: ["external_result"],
      boundary: "External semantics stay behind the adapter.",
      deep_link: "#/settings/mcp-connectors",
      connector_id: "plane",
    },
    {
      id: "mcp:plane:knowledge.docs.search",
      name: "knowledge.docs.search",
      kind: "mcp_capability",
      domain: "knowledge",
      source: "MCP connector: Plane",
      status: "planned",
      enabled: false,
      configured: false,
      description: "Plane exposes knowledge.docs.search.",
      owner_scope: "Authorized employees through connector adapter",
      permissions: ["docs:read"],
      required_settings: ["base_url"],
      arguments: [],
      produces: ["external_result"],
      boundary: "External semantics stay behind the adapter.",
      deep_link: "#/settings/mcp-connectors",
      connector_id: "plane",
    },
    {
      id: "executor:codex",
      name: "Codex",
      kind: "agent_executor",
      domain: "runtime",
      source: "AITeamOS Settings",
      status: "planned",
      enabled: false,
      configured: false,
      description: "Planned coding executor.",
      owner_scope: "RD/PV/Architect employees",
      permissions: ["repo:read"],
      required_settings: ["executor_profile"],
      arguments: [],
      produces: ["ticket_report"],
      boundary: "Reuse mature agent behavior.",
      deep_link: "#/settings/agent-executors",
      connector_id: "",
    },
  ],
  model: {
    knowledge: "Facts and history that ground reasoning.",
    skill: "Method and workflow assigned to employees.",
    tool: "Deterministic executable action.",
    mcp: "External tool and resource connector layer.",
    executor: "Mature agent runtime.",
  },
};

const planeSettings = {
  connector_id: "plane",
  enabled: false,
  configured: false,
  base_url: "",
  email: "",
  space_key: "",
  workspace_slug: "",
  project_id: "",
  api_token_configured: false,
  saved_paths: {
    settings: ".aiteamos/connectors/plane.json",
    secrets: ".aiteamos/secrets.local.json",
  },
  connector: mcpConnectors[0],
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
        if (url.endsWith("/chat/runtime")) {
          return new Response(JSON.stringify(runtime), { status: 200, headers: { "Content-Type": "application/json" } });
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
        if (url.endsWith("/mcp/connectors")) {
          return new Response(JSON.stringify(mcpConnectors), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/mcp/connectors/plane/settings")) {
          return new Response(JSON.stringify(planeSettings), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.endsWith("/mcp/status")) {
          return new Response(JSON.stringify(mcpStatus), { status: 200, headers: { "Content-Type": "application/json" } });
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

  it("renders runtime settings and configured secret state", async () => {
    render(<SettingsPage selectedSection="runtimes" />);

    expect(await screen.findByText("Runtime Policy")).toBeTruthy();
    expect(screen.getByLabelText("Runtime provider")).toBeTruthy();
    expect(screen.getAllByText("DeepSeek").length).toBeGreaterThan(0);
    expect(screen.getByText("Save DeepSeek")).toBeTruthy();
  });

  it("renders MCP connector section", async () => {
    render(<SettingsPage selectedSection="mcp-connectors" />);

    expect((await screen.findAllByText("Integrations")).length).toBeGreaterThan(0);
    expect(screen.getByText("Ticket Backend")).toBeTruthy();
    expect(screen.getByLabelText("Local Ticket file")).toBeTruthy();
    expect(screen.getByText("Plane Connector")).toBeTruthy();
    expect(screen.getAllByText("Plane").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Plane API base URL")).toBeTruthy();
  });

  it("renders Capability registry page", async () => {
    render(<CapabilitiesPage />);

    expect((await screen.findAllByText("Capabilities")).length).toBeGreaterThan(0);
    expect(screen.getByText("Capability Model")).toBeTruthy();
    expect(screen.getByText("Local Tools")).toBeTruthy();
    expect(screen.getByText("List employees")).toBeTruthy();
    expect(screen.getByText("MCP Capabilities")).toBeTruthy();
  });

  it("renders Code Repositories settings", async () => {
    render(<SettingsPage selectedSection="code-repositories" />);

    expect(await screen.findByLabelText("Repository location")).toBeTruthy();
    expect(screen.getAllByText("Code Repositories").length).toBeGreaterThan(0);
    expect(screen.getAllByText("AITeamOS").length).toBeGreaterThan(0);
    expect(screen.getByText("Add repository")).toBeTruthy();
  });

  it("renders Knowledge Backend settings", async () => {
    render(<SettingsPage selectedSection="knowledge-backend" />);

    expect((await screen.findAllByText("Knowledge Backend")).length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Neo4j URI")).toBeTruthy();
    expect(screen.getByText("Save backend")).toBeTruthy();
  });
});
