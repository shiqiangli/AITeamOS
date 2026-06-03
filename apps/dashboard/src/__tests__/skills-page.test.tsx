import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SkillsPage } from "../pages/skills";

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

describe("SkillsPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(skills), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders file-backed skills and selected detail", async () => {
    render(<SkillsPage selectedId="technical-decision" />);

    expect(await screen.findByText("Test Engineering")).toBeTruthy();
    expect(screen.getAllByText("Technical Decision").length).toBeGreaterThan(0);
    expect(screen.getAllByText("ADR and technical option analysis.").length).toBeGreaterThan(0);
    expect(screen.getByText(".aiteamos/skills/technical-decision/SKILL.md")).toBeTruthy();
  });
});
