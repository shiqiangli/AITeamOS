import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WorkPage } from "../pages/work";

const workItems = [
  {
    id: "work-implement-plane-sync-123abc",
    title: "Implement Plane sync",
    description: "Connect local WorkItems to the Plane connector boundary.",
    status: "reported",
    assigned_member_id: "alex",
    assigned_role: "",
    validation_member_id: "peter",
    validation_role: "",
    knowledge_refs: ["doc:product-direction"],
    code_repository_ids: ["repo-aiteamos"],
    source_thread_id: "member-clara-default",
    source_run_id: "run-1",
    reports: [
      {
        id: "report-1",
        reporter_member_id: "peter",
        reporter_role: "AI PV",
        content: "Validation passed.",
        evidence: ["npm test passed"],
        report_type: "validation",
        created_at: "2026-06-03T08:30:00Z",
      },
    ],
    created_at: "2026-06-03T08:00:00Z",
    updated_at: "2026-06-03T08:30:00Z",
    saved_path: ".aiteamos/work_items/index.json",
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
    description: "Default WorkItem/Docs backend.",
    capabilities: ["work_items.search", "knowledge.docs.search"],
    permissions: ["work_items:read", "docs:read"],
    required_settings: ["base_url", "api_token", "workspace_slug"],
    server: {},
    updated_at: "2026-06-03T08:00:00Z",
  },
};

describe("WorkPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/work-items")) {
          return new Response(JSON.stringify(workItems), {
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

  it("renders Plane readiness and local WorkItems", async () => {
    render(<WorkPage selectedSection="tickets" />);

    expect(await screen.findByText("Plane Connector")).toBeTruthy();
    expect(screen.getAllByText("Implement Plane sync").length).toBeGreaterThan(0);
    expect(screen.getAllByText("alex").length).toBeGreaterThan(0);
    expect(screen.getAllByText("peter").length).toBeGreaterThan(0);
    expect(screen.getAllByText("repo-aiteamos").length).toBeGreaterThan(0);
    expect(screen.getByText("Open Plane")).toBeTruthy();
  });

  it("renders report view from WorkItem reports", async () => {
    render(<WorkPage selectedSection="reports" />);

    expect(await screen.findByText("Validation passed.")).toBeTruthy();
    expect(screen.getByText("npm test passed")).toBeTruthy();
  });
});
