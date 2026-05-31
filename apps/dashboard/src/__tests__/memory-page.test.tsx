/**
 * AITeamOS Dashboard - Memory Page Component Tests
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryPage } from "../pages/memory";

vi.mock("../api/client", () => ({
  listMemories: vi.fn(),
  getMemoryDetail: vi.fn(),
  getMemoryVersions: vi.fn(),
  createMemory: vi.fn(),
  changeMemoryLifecycle: vi.fn(),
  deleteMemory: vi.fn(),
  getReviewsByTarget: vi.fn(),
  createReview: vi.fn(),
  decideReview: vi.fn(),
  listMembers: vi.fn(),
  listUnresolvedConflicts: vi.fn(),
  reportConflict: vi.fn(),
  resolveConflict: vi.fn(),
  listPendingProposals: vi.fn(),
}));

import {
  listMemories,
  getMemoryDetail,
  getMemoryVersions,
  changeMemoryLifecycle,
  getReviewsByTarget,
  createReview,
  decideReview,
  listMembers,
  listUnresolvedConflicts,
  listPendingProposals,
} from "../api/client";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("MemoryPage", () => {
  beforeEach(() => {
    (listMemories as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: "memory-1",
        title: "Compiler pass workflow",
        tier: "patterns",
        lifecycle_state: "candidate",
        confidence_value: 0.72,
        scope_kind: "project",
        tags: [],
        current_version: 1,
        created_at: "2026-05-01T00:00:00Z",
      },
      {
        id: "memory-2",
        title: "Legacy pass workflow",
        tier: "patterns",
        lifecycle_state: "active",
        confidence_value: 0.81,
        scope_kind: "project",
        tags: [],
        current_version: 1,
        created_at: "2026-05-02T00:00:00Z",
      },
    ]);
    (getMemoryDetail as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: "memory-1",
      title: "Compiler pass workflow",
      tier: "patterns",
      statement: "Add optimization passes through a reviewed pipeline.",
      lifecycle_state: "candidate",
      confidence_value: 0.72,
      versions: 1,
      created_at: "2026-05-01T00:00:00Z",
    });
    (getMemoryVersions as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        version_no: 1,
        diff: { statement: "Add optimization passes through a reviewed pipeline." },
        reason: "Initial candidate",
        author_member_id: "member-1",
        created_at: "2026-05-01T00:00:00Z",
      },
    ]);
    (listMembers as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: "member-1",
        kind: "human",
        display_name: "Reviewer Ada",
        department_id: null,
        concurrency_limit: 1,
        is_archived: false,
        created_at: null,
      },
    ]);
    (getReviewsByTarget as ReturnType<typeof vi.fn>).mockImplementation((targetKind: string) => (
      targetKind === "memory_candidate"
        ? Promise.resolve([
          {
            id: "review-1",
            target_kind: "memory_candidate",
            target_id: "memory-1",
            reviewer_member_id: "member-1",
            status: "pending",
            verdict: null,
            reason: null,
            correction: null,
            decision_at: null,
            created_at: "2026-05-03T00:00:00Z",
          },
        ])
        : Promise.resolve([])
    ));
    (listUnresolvedConflicts as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: "conflict-1",
        memory_a_id: "memory-1",
        memory_b_id: "memory-2",
        conflict_kind: "semantic",
        detected_by: "manual",
        status: "open",
        resolution: null,
        winner_id: null,
        resolved_by: null,
        detected_at: "2026-05-04T00:00:00Z",
      },
    ]);
    (listPendingProposals as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: "memory-1",
        title: "Compiler pass workflow",
        tier: "patterns",
        lifecycle_state: "candidate",
        confidence_value: 0.72,
        scope_kind: "project",
        tags: [],
        current_version: 1,
        created_at: "2026-05-01T00:00:00Z",
      },
    ]);
    (decideReview as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: "review-1",
      status: "decided",
      verdict: "approve",
    });
    (createReview as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: "review-new",
      status: "created",
    });
    (changeMemoryLifecycle as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: "memory-1",
      lifecycle_state: "active",
    });
  });

  it("loads governance data inside the memory detail dialog", async () => {
    const user = userEvent.setup();
    render(<MemoryPage selectedId="memory-1" />);

    await waitFor(() => {
      expect(getReviewsByTarget).toHaveBeenCalledWith("memory_candidate", "memory-1");
      expect(getReviewsByTarget).toHaveBeenCalledWith("memory_modification", "memory-1");
      expect(getReviewsByTarget).toHaveBeenCalledWith("memory_promotion", "memory-1");
    });

    await user.click(screen.getByRole("tab", { name: "Review" }));

    expect(await screen.findByText("Review Settlement")).toBeDefined();
    expect(screen.getByText("Review Cases")).toBeDefined();
    expect(screen.getAllByText("Conflicts").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Legacy pass workflow")).toBeDefined();

    await user.click(screen.getByRole("tab", { name: "Versions" }));
    expect(await screen.findByText("Initial candidate")).toBeDefined();
  });

  it("settles a pending memory review from the detail dialog", async () => {
    const user = userEvent.setup();
    render(<MemoryPage selectedId="memory-1" />);

    await user.click(await screen.findByRole("tab", { name: "Review" }));
    const approveButtons = await screen.findAllByRole("button", { name: /Approve/ });
    await user.click(approveButtons[1]);

    await waitFor(() => {
      expect(decideReview).toHaveBeenCalledWith(
        "review-1",
        expect.objectContaining({ verdict: "approve" }),
      );
      expect(changeMemoryLifecycle).toHaveBeenCalledWith(
        "memory-1",
        "active",
        expect.any(String),
      );
    });
  });

  it("creates and decides a memory review when no review case exists", async () => {
    const user = userEvent.setup();
    (getReviewsByTarget as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    render(<MemoryPage selectedId="memory-1" />);

    await user.click(await screen.findByRole("tab", { name: "Review" }));
    const approveButtons = await screen.findAllByRole("button", { name: /Approve/ });
    await user.click(approveButtons[0]);

    await waitFor(() => {
      expect(createReview).toHaveBeenCalledWith({
        target_kind: "memory_candidate",
        target_id: "memory-1",
        reviewer_member_id: "member-1",
      });
      expect(decideReview).toHaveBeenCalledWith(
        "review-new",
        expect.objectContaining({ verdict: "approve" }),
      );
    });
  });
});
