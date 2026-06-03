import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MembersPage } from "../pages/members";

const members = [
  {
    id: "clara",
    display_name: "Clara",
    kind: "ai",
    role: "AI Team Lead",
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

describe("MembersPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(members), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders file-backed members and selected detail", async () => {
    render(<MembersPage selectedId="alex" />);

    expect(await screen.findByText("Clara")).toBeTruthy();
    expect(screen.getAllByText("Alex").length).toBeGreaterThan(0);
    expect(screen.getAllByText("AI RD / Implementer").length).toBeGreaterThan(0);
    expect(screen.getAllByText("external_or_file_stub").length).toBeGreaterThan(0);
  });
});
