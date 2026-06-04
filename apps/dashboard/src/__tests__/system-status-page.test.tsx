import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SystemStatusPage } from "../pages/system-status";

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
    built_in_tool_count: 1,
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
  mode: "local_file",
  status: "ready",
  ticket_count: 4,
  local_file_path: ".aiteamos/tickets/index.json",
  detail: "Local file backend is ready.",
  supported_modes: ["local_file"],
  saved_paths: {},
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
  ],
};

describe("SystemStatusPage", () => {
  beforeEach(() => {
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
        if (url.endsWith("/system-status")) {
          return new Response(JSON.stringify(systemStatus), { status: 200, headers: { "Content-Type": "application/json" } });
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

    expect(await screen.findByText("System Status")).toBeTruthy();
    expect(screen.getByText("System Summary")).toBeTruthy();
    expect(screen.getByText("Secrets Health")).toBeTruthy();
    expect(screen.getByText("ChatGPT / OpenAI API")).toBeTruthy();
    expect(screen.getByText("DEEPSEEK_API_KEY")).toBeTruthy();
    expect(screen.getByText("OPENAI_API_KEY")).toBeTruthy();
  });
});
