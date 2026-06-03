import { render, screen } from "@testing-library/react";
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
    runtime_mode: "deepseek_chat_or_file_stub",
    preserve_provider_thread: true,
  },
  {
    id: "alex",
    display_name: "Alex",
    kind: "ai",
    role: "AI RD / Implementer",
    summary: "Implementer",
    skills: ["test-engineering"],
    runtime_mode: "external_or_file_stub",
    preserve_provider_thread: true,
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

const capabilities = {
  status: {
    capability_count: 2,
    enabled_count: 2,
    configured_count: 2,
    ready_count: 2,
    local_tool_count: 1,
    mcp_capability_count: 0,
    agent_executor_count: 1,
    saved_paths: {},
  },
  capabilities: [
    {
      id: "search_knowledge",
      name: "Search Knowledge",
      kind: "local_tool",
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

describe("EmployeesPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        const body = url.includes("/chat/threads")
          ? threadsByEmployee[url.includes("alex") ? "alex" : "clara"]
          : url.includes("/capabilities")
            ? capabilities
            : employees;
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
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
    expect(screen.getAllByText("Implement ticket flow").length).toBeGreaterThan(0);
    expect(screen.getAllByText("1 skills").length).toBeGreaterThan(0);
  });
});
