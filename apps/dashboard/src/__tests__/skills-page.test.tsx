import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AssetsPage } from "../pages/assets";

const skills = [
  {
    id: "test-engineering",
    title: "Test Engineering",
    description: "Test execution and validation evidence.",
    assigned_employees: ["alex"],
    resources: [],
    saved_path: ".aiteamos/skills/test-engineering/SKILL.md",
  },
  {
    id: "technical-decision",
    title: "Technical Decision",
    description: "ADR and technical option analysis.",
    assigned_employees: ["clara"],
    resources: ["references/options.md"],
    saved_path: ".aiteamos/skills/technical-decision/SKILL.md",
  },
];

describe("AssetsPage — Skills view", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/chat/skills")) {
          return new Response(JSON.stringify(skills), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/assets")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/knowledge/status")) {
          return new Response(JSON.stringify({ docs_count: 0, memories_count: 0, decisions_count: 0, review_queue_count: 0, saved_paths: {} }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/knowledge/docs")) {
          return new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.includes("/memory/approved")) {
          return new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.includes("/knowledge/decisions")) {
          return new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.includes("/knowledge/review-queue")) {
          return new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.includes("/capabilities")) {
          return new Response(JSON.stringify({
            status: {
              capability_count: 0,
              enabled_count: 0,
              configured_count: 0,
              ready_count: 0,
              tool_count: 0,
              built_in_tool_count: 0,
              mcp_tool_count: 0,
              native_api_tool_count: 0,
              cli_tool_count: 0,
              ci_tool_count: 0,
              saved_paths: {},
            },
            capabilities: [],
            model: {},
          }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        return new Response("not found", { status: 404 });
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders skills table with skills data", async () => {
    render(<AssetsPage selectedArea="capabilities" selectedDetail="skills" />);

    expect((await screen.findAllByText("Test Engineering")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Technical Decision").length).toBeGreaterThan(0);
  });
});
