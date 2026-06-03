import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TicketsPage } from "../pages/tickets";

const tickets = [
  {
    id: "ticket-implement-plane-sync-123abc",
    title: "Implement Plane sync",
    description: "Connect local Tickets to the Plane connector boundary.",
    status: "reported",
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
];

const supportedModes = [
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

const backendSettings = {
  mode: "local_file",
  local_file_path: ".aiteamos/tickets/index.json",
  saved_paths: {
    settings: ".aiteamos/tickets/backend.json",
    local_file: ".aiteamos/tickets/index.json",
  },
  supported_modes: supportedModes,
};

const backendStatus = {
  mode: "local_file",
  status: "ready",
  detail: "Local file Ticket backend is active.",
  ticket_count: 1,
  local_file_path: ".aiteamos/tickets/index.json",
  saved_paths: backendSettings.saved_paths,
  supported_modes: supportedModes,
};

describe("TicketsPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
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
    expect(screen.getByText("Ticket Backend")).toBeTruthy();
    expect(screen.getAllByText("local_file").length).toBeGreaterThan(0);
  });

  it("renders report view from Ticket reports", async () => {
    render(<TicketsPage selectedSection="reports" />);

    expect(await screen.findByText("Validation passed.")).toBeTruthy();
    expect(screen.getByText("npm test passed")).toBeTruthy();
  });
});
