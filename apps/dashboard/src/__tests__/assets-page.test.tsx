import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AssetsPage } from "../pages/assets";

const status = {
  docs_count: 1,
  memories_count: 0,
  decisions_count: 0,
  review_queue_count: 0,
  asset_count: 1,
  saved_paths: {},
};

const assets = [
  {
    id: "report-1:evidence:0",
    kind: "evidence",
    title: "pytest passed",
    status: "approved",
    source_ticket: "rd-0001",
    source_employee: "peter",
    assigned_employees: ["alex", "peter"],
    scopes: ["rd", "doc:product-direction"],
    created_at: "2026-06-03T08:30:00Z",
    updated_at: "2026-06-03T08:30:00Z",
    metadata: { asset_domain: "work", asset_type: "evidence" },
  },
  {
    id: "product-model",
    kind: "doc",
    title: "Product Model",
    status: "approved",
    source_ticket: "",
    source_employee: "",
    assigned_employees: [],
    scopes: ["knowledge", "docs"],
    created_at: "2026-06-03T08:30:00Z",
    updated_at: "2026-06-03T08:30:00Z",
    metadata: { asset_domain: "knowledge", asset_type: "docs" },
  },
  {
    id: "list_employees",
    kind: "tool",
    title: "List employees",
    status: "ready",
    source_ticket: "",
    source_employee: "",
    assigned_employees: [],
    scopes: ["capabilities", "kernel-commands", "employees"],
    created_at: "2026-06-03T08:30:00Z",
    updated_at: "2026-06-03T08:30:00Z",
    metadata: {
      asset_domain: "capabilities",
      asset_type: "kernel-commands",
      source_kind: "kernel_command",
      description: "List file-backed employees.",
    },
  },
  {
    id: "mcp:github:repo.search",
    kind: "tool",
    title: "repo.search",
    status: "planned",
    source_ticket: "",
    source_employee: "",
    assigned_employees: [],
    scopes: ["capabilities", "mcp-tools", "repo"],
    created_at: "2026-06-03T08:30:00Z",
    updated_at: "2026-06-03T08:30:00Z",
    metadata: {
      asset_domain: "capabilities",
      asset_type: "mcp-tools",
      source_kind: "mcp_server",
      description: "GitHub exposes repo.search.",
    },
  },
];

const skills = [
  {
    id: "test-engineering",
    title: "Test Engineering",
    description: "Test execution.",
    content: "# Test Engineering\n\nRun tests and report evidence.",
    assigned_employees: ["alex"],
    resources: [],
    saved_path: ".aiteamos/skills/test-engineering/SKILL.md",
  },
];

const docs = [
  {
    id: "product-model",
    title: "Product Model",
    path: ".aiteamos/knowledge/docs/PRODUCT_MODEL.md",
    excerpt: "Core product direction.",
    content: "# Product Model\n\nFull body for review.",
    source: "local",
    tags: ["product"],
    updated_at: "2026-06-03T08:30:00Z",
  },
];

const reviewItems = [
  {
    id: "mem-1",
    kind: "memory",
    title: "Memory candidate from ticket",
    content: "Remember the ticket asset review flow.",
    status: "proposed",
    source_ref: "rd-0001",
    created_at: "2026-06-03T08:30:00Z",
    updated_at: "2026-06-03T08:30:00Z",
    metadata: { scope_kind: "ticket", scope_ref: "rd-0001" },
  },
];

const approvedMemory = {
  id: "mem-approved-1",
  content: "Approved memory that can become stale.",
  status: "approved",
  source_kind: "ticket_summary",
  source_ref: "traces/run-approved",
  scope_kind: "ticket",
  scope_ref: "rd-0009",
  memory_type: "lesson",
  confidence: 0.88,
  employee_ids: ["clara"],
  tags: ["validation"],
  provenance: {
    source_ticket_id: "rd-0009",
    source_run_id: "run-approved-source",
    source_report_id: "report-approved-1",
    evidence_id: "evidence-approved-1",
    version_hash: "hash-approved-1",
    provider_refs: { graphiti_episode_id: "episode-approved-1" },
    usage_history: [
      {
        usage_id: "usage-approved-1",
        at: "2026-06-03T08:40:00Z",
        source_run_id: "run-approved-usage",
        source_trace_path: ".aiteamos/traces/run-approved-usage.jsonl",
        source_ticket_ids: ["rd-0009"],
        usefulness_status: "unreviewed",
      },
    ],
    usage_summary: {
      recall_count: 1,
      useful_count: 0,
      not_useful_count: 0,
      last_recalled_at: "2026-06-03T08:40:00Z",
      last_recalled_ticket_id: "rd-0009",
      last_recalled_run_id: "run-approved-usage",
      last_usefulness_status: "unreviewed",
    },
  },
  created_at: "2026-06-03T08:30:00Z",
  updated_at: "2026-06-03T08:30:00Z",
  approved_at: "2026-06-03T08:31:00Z",
  graphiti_episode_id: "episode-approved-1",
  graphiti_status: { status: "ingested" },
};

const capabilities = {
  status: {
    capability_count: 2,
    enabled_count: 1,
    configured_count: 1,
    ready_count: 1,
    tool_count: 2,
    kernel_command_count: 1,
    mcp_tool_count: 1,
    native_api_tool_count: 0,
    cli_tool_count: 0,
    ci_tool_count: 0,
    saved_paths: {},
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
  model: {},
};

describe("AssetsPage", () => {
  let approvedMemories: unknown[] = [];

  beforeEach(() => {
    approvedMemories = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        let body: unknown = [];
        if (url.includes("/memory/candidates/") && url.includes("/usage/") && url.includes("/review")) {
          const review = JSON.parse(String(init?.body ?? "{}")) as { usefulness_status?: string };
          body = {
            ...approvedMemory,
            provenance: {
              ...approvedMemory.provenance,
              usage_history: [
                {
                  usage_id: "usage-approved-1",
                  at: "2026-06-03T08:40:00Z",
                  source_run_id: "run-approved-usage",
                  source_trace_path: ".aiteamos/traces/run-approved-usage.jsonl",
                  source_ticket_ids: ["rd-0009"],
                  usefulness_status: review.usefulness_status ?? "useful",
                },
              ],
              usage_summary: {
                recall_count: 1,
                useful_count: 1,
                not_useful_count: 0,
                last_recalled_at: "2026-06-03T08:40:00Z",
                last_recalled_ticket_id: "rd-0009",
                last_recalled_run_id: "run-approved-usage",
                last_usefulness_status: review.usefulness_status ?? "useful",
              },
            },
          };
        } else if (url.includes("/memory/candidates/") && url.includes("/review")) {
          const review = JSON.parse(String(init?.body ?? "{}")) as { status?: string };
          if (review.status === "stale") approvedMemories = [];
          body = { ...approvedMemory, id: url.split("/memory/candidates/")[1].split("/review")[0], status: review.status ?? "rejected" };
        }
        if (url.includes("/knowledge/status")) body = status;
        if (url.includes("/chat/skills")) body = skills;
        if (url.includes("/knowledge/docs")) body = docs;
        if (url.includes("/memory/approved")) body = approvedMemories;
        if (url.includes("/knowledge/decisions")) body = [];
        if (url.includes("/knowledge/review-queue")) body = reviewItems;
        if (url.includes("/capabilities")) body = capabilities;
        if (url.includes("/assets")) body = assets;
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders Overview with recent changes when no area selected", async () => {
    render(<AssetsPage selectedArea={null} selectedDetail={null} />);

    expect(await screen.findByText("Recent Changes")).toBeTruthy();
    expect((await screen.findAllByText("pytest passed")).length).toBeGreaterThan(0);
  });

  it("renders Knowledge Docs with breadcrumb and doc list", async () => {
    render(<AssetsPage selectedArea="knowledge" selectedDetail="docs" />);

    expect((await screen.findAllByText("Knowledge")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("Docs")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("Product Model")).length).toBeGreaterThan(0);
  });

  it("opens a read-only full text dialog from doc detail", async () => {
    render(<AssetsPage selectedArea="knowledge" selectedDetail="docs" />);

    fireEvent.click((await screen.findAllByText("Product Model"))[0]);
    fireEvent.click(await screen.findByText("Open Full Text"));

    await waitFor(() => {
      expect((screen.getByLabelText("Asset full text") as HTMLTextAreaElement).value).toContain("Full body for review.");
    });
  });

  it("closes the current detail drawer when switching knowledge sub-tabs", async () => {
    const { rerender } = render(<AssetsPage selectedArea="knowledge" selectedDetail="docs" />);

    fireEvent.click((await screen.findAllByText("Product Model"))[0]);
    expect(await screen.findByText("Open Full Text")).toBeTruthy();

    rerender(<AssetsPage selectedArea="knowledge" selectedDetail="memories" />);
    await waitFor(() => expect(screen.queryByText("Open Full Text")).toBeNull());
  });

  it("shows review item details and opens review full text", async () => {
    render(<AssetsPage selectedArea="review" selectedDetail={null} />);

    fireEvent.click(await screen.findByText("Memory candidate from ticket"));
    expect((await screen.findAllByText("Remember the ticket asset review flow.")).length).toBeGreaterThan(0);

    fireEvent.click(await screen.findByText("Open Full Text"));
    await waitFor(() => {
      expect((screen.getByLabelText("Asset full text") as HTMLTextAreaElement).value).toContain("Remember the ticket asset review flow.");
    });
  });

  it("can reject a proposed memory from the review queue", async () => {
    render(<AssetsPage selectedArea="review" selectedDetail={null} />);

    fireEvent.click(await screen.findByText("Memory candidate from ticket"));
    fireEvent.click(await screen.findByText("Reject"));

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/memory/candidates/mem-1/review",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"status":"rejected"'),
        }),
      );
    });
  });

  it("can mark an approved memory stale from the memory detail", async () => {
    approvedMemories = [approvedMemory];

    render(<AssetsPage selectedArea="knowledge" selectedDetail="memories" />);

    fireEvent.click(await screen.findByText("ticket:rd-0009"));
    fireEvent.click(await screen.findByText("Mark Stale"));

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/memory/candidates/mem-approved-1/review",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"status":"stale"'),
        }),
      );
    });
  });

  it("can mark the latest memory recall useful from the memory detail", async () => {
    approvedMemories = [approvedMemory];

    render(<AssetsPage selectedArea="knowledge" selectedDetail="memories" />);

    fireEvent.click(await screen.findByText("ticket:rd-0009"));
    expect(await screen.findByText("Recall count")).toBeTruthy();
    expect(await screen.findByText("Graphiti Provenance")).toBeTruthy();
    expect(await screen.findByText("episode-approved-1")).toBeTruthy();
    expect(await screen.findByText("mem-approved-1 / lesson")).toBeTruthy();
    expect(await screen.findByText("run-approved-source")).toBeTruthy();
    expect(await screen.findByText("report-approved-1")).toBeTruthy();
    expect(await screen.findByText("evidence-approved-1")).toBeTruthy();
    expect(await screen.findByText("hash-approved-1")).toBeTruthy();
    expect(await screen.findByText("Related Tickets")).toBeTruthy();
    expect(await screen.findByText("Usage History")).toBeTruthy();
    expect(await screen.findByText("usage-approved-1")).toBeTruthy();
    expect(await screen.findByText("Run: run-approved-usage")).toBeTruthy();
    expect(await screen.findByText("Trace: .aiteamos/traces/run-approved-usage.jsonl")).toBeTruthy();
    fireEvent.click(await screen.findByText("Mark Useful"));

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/memory/candidates/mem-approved-1/usage/usage-approved-1/review",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"usefulness_status":"useful"'),
        }),
      );
    });
  });

  it("renders flattened capability tool tabs", async () => {
    const { rerender } = render(<AssetsPage selectedArea="capabilities" selectedDetail="kernel-commands" />);

    expect((await screen.findAllByText("Kernel Commands")).length).toBeGreaterThan(0);
    expect(await screen.findByText("List employees")).toBeTruthy();

    rerender(<AssetsPage selectedArea="capabilities" selectedDetail="mcp-tools" />);

    expect((await screen.findAllByText("MCP Tools")).length).toBeGreaterThan(0);
    expect(await screen.findByText("repo.search")).toBeTruthy();
  });
});
