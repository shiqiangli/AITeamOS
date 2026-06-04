import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EmployeesPage } from "../pages/employees";

const employees = [
  {
    id: "clara",
    display_name: "Clara",
    kind: "ai",
    role: "AI Team OS Manager",
    summary: "Coordinator",
    skills: ["task-specification"],
    ai_engine_mode: "deepseek_chat_or_file_stub",
    default_ai_engine: "system",
    preserve_provider_thread: true,
    default_thread_id: "employee-clara-default",
  },
  {
    id: "alex",
    display_name: "Alex",
    kind: "ai",
    role: "AI RD / Implementer",
    summary: "Implementer",
    skills: ["test-engineering"],
    ai_engine_mode: "external_or_file_stub",
    default_ai_engine: "system",
    preserve_provider_thread: true,
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
    contribution: {
      ticket_count: 0,
      current_ticket_count: 0,
      report_count: 0,
      validation_count: 0,
      blocked_count: 0,
      handoff_count: 0,
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
    handoffs: [],
    contribution: {
      ticket_count: 1,
      current_ticket_count: 1,
      report_count: 0,
      validation_count: 0,
      blocked_count: 0,
      handoff_count: 0,
    },
  },
};

const capabilities = {
  status: {
    capability_count: 2,
    enabled_count: 2,
    configured_count: 2,
    ready_count: 2,
    tool_count: 1,
    built_in_tool_count: 1,
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
      source_kind: "built_in",
      domain: "knowledge",
      source: "file",
      status: "ready",
      enabled: true,
      configured: true,
      description: "Search project knowledge",
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
      const body = url.includes("/tickets/employees/")
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
