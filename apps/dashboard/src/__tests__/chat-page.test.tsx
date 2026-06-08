import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatPage } from "../pages/chat";

const runtimeState = vi.hoisted(() => ({
  response: null as Record<string, unknown> | null,
}));

vi.mock("@ag-ui/client", () => ({
  HttpAgent: class HttpAgent {
    constructor() {
      // Runtime transport is not exercised in this inspector test.
    }
  },
}));

vi.mock("@assistant-ui/react-ag-ui", () => ({
  useAgUiRuntime: () => ({}),
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
    useAuiState: (selector: (state: unknown) => unknown) => selector({
      thread: {
        state: runtimeState.response ? { aiteamos_chat_response: runtimeState.response } : {},
      },
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
    commands: [],
    trace: { path: ".aiteamos/traces/run-chat-provenance.jsonl" },
  },
  saved_paths: { trace: ".aiteamos/traces/run-chat-provenance.jsonl" },
};

describe("ChatPage", () => {
  beforeEach(() => {
    runtimeState.response = chatResponse;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      let body: unknown;
      if (url.endsWith("/chat/employees")) body = [clara];
      else if (url.endsWith("/chat/ai-engines")) body = aiEngines;
      else if (url.endsWith("/capabilities")) body = { capabilities: [] };
      else if (url.includes("/chat/threads?")) body = threadList;
      else body = { detail: `Unhandled URL ${url}` };
      const status = "detail" in (body as Record<string, unknown>) ? 404 : 200;
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
  });

  it("shows run provenance for action plan, recalled memory, Graphiti, provider, and trace", async () => {
    render(<ChatPage />);

    expect(await screen.findByText("Latest Run")).toBeTruthy();
    expect(screen.getByText("Trace path")).toBeTruthy();
    expect(screen.getAllByText(".aiteamos/traces/run-chat-provenance.jsonl").length).toBeGreaterThan(0);
    expect(screen.getByText("Action Plan")).toBeTruthy();
    expect(screen.getByText("append_report:deepseek")).toBeTruthy();
    expect(screen.getByText("Recalled Memories")).toBeTruthy();
    expect(screen.getByText("mem-approved-1")).toBeTruthy();
    expect(screen.getByText("Graphiti: yes")).toBeTruthy();
    expect(screen.getByText("Source: rd-0000")).toBeTruthy();
    expect(screen.getByText("Graphiti Episodes")).toBeTruthy();
    expect(screen.getByText("episode-approved-1")).toBeTruthy();
    expect(screen.getByText("Provider Refs")).toBeTruthy();
    expect(screen.getByText("plane")).toBeTruthy();
  });
});
