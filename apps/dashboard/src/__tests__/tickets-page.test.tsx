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

const planeSettings = {
  connector_id: "plane",
  enabled: true,
  configured: true,
  base_url: "http://localhost:8082",
  email: "",
  space_key: "",
  workspace_slug: "aiteamos",
  project_id: "ait",
  api_token_configured: true,
  saved_paths: {
    settings: ".aiteamos/connectors/plane.json",
    secrets: ".aiteamos/secrets.local.json",
  },
  connector: {
    id: "plane",
    name: "Plane",
    status: "ready",
    transport: "rest",
    enabled: true,
    configured: true,
    description: "Default Ticket/Docs backend.",
    capabilities: ["tickets.search", "knowledge.docs.search"],
    permissions: ["tickets:read", "docs:read"],
    required_settings: ["base_url", "api_token", "workspace_slug"],
    server: {},
    updated_at: "2026-06-03T08:00:00Z",
  },
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
        if (url.endsWith("/mcp/connectors/plane/settings")) {
          return new Response(JSON.stringify(planeSettings), {
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

  it("renders local Tickets with status filters and Plane source", async () => {
    render(<TicketsPage selectedSection="tickets" />);

    expect((await screen.findAllByText("Implement Plane sync")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("All").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Active").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Review").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Done").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Implement Plane sync").length).toBeGreaterThan(0);
    expect(screen.getAllByText("alex").length).toBeGreaterThan(0);
    expect(screen.getAllByText("peter").length).toBeGreaterThan(0);
    expect(screen.getAllByText("repo-aiteamos").length).toBeGreaterThan(0);
    expect(screen.getByText(/Plane source:/)).toBeTruthy();
  });

  it("renders report view from Ticket reports", async () => {
    render(<TicketsPage selectedSection="reports" />);

    expect(await screen.findByText("Validation passed.")).toBeTruthy();
    expect(screen.getByText("npm test passed")).toBeTruthy();
  });
});
