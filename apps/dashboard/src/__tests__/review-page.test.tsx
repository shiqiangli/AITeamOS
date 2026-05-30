/**
 * AITeamOS Dashboard — Review Page Component Tests (plan.md §3.4)
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReviewPage } from "../pages/reviews";

// Mock the API client
vi.mock("../api/client", () => ({
  listPendingReviews: vi.fn(),
  createReview: vi.fn(),
  decideReview: vi.fn(),
  listUnresolvedConflicts: vi.fn(),
  reportConflict: vi.fn(),
  resolveConflict: vi.fn(),
  listPendingProposals: vi.fn(),
  listMembers: vi.fn(),
  listMemories: vi.fn(),
}));

import {
  listPendingReviews,
  createReview,
  decideReview,
  listUnresolvedConflicts,
  reportConflict,
  resolveConflict,
  listPendingProposals,
  listMembers,
  listMemories,
} from "../api/client";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ReviewPage", () => {
  beforeEach(() => {
    (listPendingProposals as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (listMembers as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: "mem-1", display_name: "reviewer-uuid", kind: "ai", department_id: "d1", concurrency_limit: 1, is_archived: false, created_at: null },
    ]);
    (listMemories as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: "some-uuid", title: "some-uuid", tier: "facts", lifecycle_state: "active", confidence_value: 0.5, scope_kind: "global", tags: [], current_version: 1, created_at: null },
    ]);
    (listPendingReviews as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: "r1",
        target_kind: "memory_candidate",
        target_id: "target-uuid-1234-5678-9012",
        reviewer_member_id: "mem-1",
        verdict: null,
        reason: null,
        decision_at: null,
        created_at: "2026-01-01T00:00:00Z",
      },
      {
        id: "r2",
        target_kind: "task_deliverable",
        target_id: "task-uuid-1234-5678-9012",
        reviewer_member_id: "reviewer-uuid-2",
        verdict: "approve",
        reason: "Looks good",
        decision_at: "2026-01-02T00:00:00Z",
        created_at: "2026-01-01T00:00:00Z",
      },
    ]);
    (listUnresolvedConflicts as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: "c1",
        memory_a_id: "mem-a-uuid-1234-5678-9012",
        memory_b_id: "mem-b-uuid-1234-5678-9012",
        conflict_kind: "semantic",
        detected_by: "embedding_similarity",
        resolution: null,
        winner_id: null,
        resolved_by: null,
        created_at: "2026-01-01T00:00:00Z",
      },
    ]);
  });

  describe("Reviews Tab", () => {
    it("should render reviews tab by default", async () => {
      render(<ReviewPage selectedId={null} />);
      await waitFor(() => {
        const elements = screen.getAllByText("Reviews");
        expect(elements.length).toBeGreaterThanOrEqual(1);
      });
    });

    it("should load and display pending reviews", async () => {
      render(<ReviewPage selectedId={null} />);
      await waitFor(() => {
        expect(listPendingReviews).toHaveBeenCalled();
      });
      await waitFor(() => {
        expect(screen.getByText("memory_candidate")).toBeDefined();
      });
    });

    it("should show pending count", async () => {
      render(<ReviewPage selectedId={null} />);
      await waitFor(() => {
        expect(screen.getByText("Pending")).toBeDefined();
      });
    });

    it("should show create review button", async () => {
      render(<ReviewPage selectedId={null} />);
      await waitFor(() => {
        expect(screen.getByText("Create Review")).toBeDefined();
      });
    });

    it("should toggle create review form", async () => {
      const user = userEvent.setup();
      render(<ReviewPage selectedId={null} />);
      await waitFor(() => {
        expect(screen.getByText("Create Review")).toBeDefined();
      });
      await user.click(screen.getByText("Create Review"));
      await waitFor(() => {
        expect(screen.getAllByText("Target Kind").length).toBeGreaterThanOrEqual(2);
        expect(screen.getByPlaceholderText("Select memory or type title")).toBeDefined();
        expect(screen.getByPlaceholderText("Select member or type name")).toBeDefined();
      });
    });

    it("should show review detail when selected", async () => {
      render(<ReviewPage selectedId="r1" />);
      await waitFor(() => {
        expect(screen.getByText("Review Detail")).toBeDefined();
      });
    });

    it("should display verdict as pending for undecided reviews", async () => {
      render(<ReviewPage selectedId={null} />);
      await waitFor(() => {
        const pendingCells = screen.getAllByText("pending");
        expect(pendingCells.length).toBeGreaterThan(0);
      });
    });

    it("should display approved verdict", async () => {
      render(<ReviewPage selectedId={null} />);
      await waitFor(() => {
        expect(screen.getByText("approve")).toBeDefined();
      });
    });
  });

  describe("Conflicts Tab", () => {
    it("should switch to conflicts tab", async () => {
      const user = userEvent.setup();
      render(<ReviewPage selectedId={null} />);
      await waitFor(() => {
        expect(screen.getByText("Conflicts")).toBeDefined();
      });
      await user.click(screen.getByText("Conflicts"));
      await waitFor(() => {
        expect(listUnresolvedConflicts).toHaveBeenCalled();
      });
    });

    it("should show unresolved conflict count", async () => {
      const user = userEvent.setup();
      render(<ReviewPage selectedId={null} />);
      await waitFor(() => {
        expect(screen.getByText("Conflicts")).toBeDefined();
      });
      await user.click(screen.getByText("Conflicts"));
      await waitFor(() => {
        expect(screen.getByText("Unresolved")).toBeDefined();
      });
    });

    it("should show report conflict button on conflicts tab", async () => {
      const user = userEvent.setup();
      render(<ReviewPage selectedId={null} />);
      await waitFor(() => {
        expect(screen.getByText("Conflicts")).toBeDefined();
      });
      await user.click(screen.getByText("Conflicts"));
      await waitFor(() => {
        expect(screen.getByText("Report Conflict")).toBeDefined();
      });
    });

    it("should toggle report conflict form", async () => {
      const user = userEvent.setup();
      render(<ReviewPage selectedId={null} />);
      await waitFor(() => {
        expect(screen.getByText("Conflicts")).toBeDefined();
      });
      await user.click(screen.getByText("Conflicts"));
      await waitFor(() => {
        expect(screen.getByText("Report Conflict")).toBeDefined();
      });
      await user.click(screen.getByText("Report Conflict"));
      await waitFor(() => {
        expect(screen.getAllByText("Memory A")[0]).toBeDefined();
        expect(screen.getAllByText("Memory B")[0]).toBeDefined();
      });
    });

    it("should load conflicts when switching tabs", async () => {
      const user = userEvent.setup();
      render(<ReviewPage selectedId={null} />);
      await waitFor(() => {
        expect(screen.getByText("Conflicts")).toBeDefined();
      });
      await user.click(screen.getByText("Conflicts"));
      await waitFor(() => {
        expect(listUnresolvedConflicts).toHaveBeenCalledTimes(1);
      });
    });
  });

  describe("Create Review Form", () => {
    it("should submit create review form", async () => {
      (createReview as ReturnType<typeof vi.fn>).mockResolvedValue({
        id: "r-new",
        target_kind: "memory_candidate",
        target_id: "some-uuid",
        reviewer_member_id: "mem-1",
        verdict: null,
        reason: null,
        decision_at: null,
        created_at: "2026-01-01T00:00:00Z",
      });

      const user = userEvent.setup();
      render(<ReviewPage selectedId={null} />);
      await waitFor(() => {
        expect(screen.getByText("Create Review")).toBeDefined();
      });
      await user.click(screen.getByText("Create Review"));

      await waitFor(() => {
        expect(screen.getByPlaceholderText("Select memory or type title")).toBeDefined();
      });

      await user.type(screen.getByPlaceholderText("Select memory or type title"), "some-uuid");
      await user.type(screen.getByPlaceholderText("Select member or type name"), "reviewer-uuid");

      await user.click(screen.getByText("Create"));

      await waitFor(() => {
        expect(createReview).toHaveBeenCalledWith({
          target_kind: "memory_candidate",
          target_id: "some-uuid",
          reviewer_member_id: "mem-1",
        });
      });
    });
  });

  describe("Error Handling", () => {
    it("should display error when loading reviews fails", async () => {
      (listPendingReviews as ReturnType<typeof vi.fn>).mockRejectedValue(
        new Error("Network error"),
      );
      render(<ReviewPage selectedId={null} />);
      await waitFor(() => {
        expect(screen.getByText("Network error")).toBeDefined();
      });
    });

    it("should display error when loading conflicts fails", async () => {
      const user = userEvent.setup();
      (listUnresolvedConflicts as ReturnType<typeof vi.fn>).mockRejectedValue(
        new Error("Conflict load error"),
      );
      render(<ReviewPage selectedId={null} />);
      await waitFor(() => {
        expect(screen.getByText("Conflicts")).toBeDefined();
      });
      await user.click(screen.getByText("Conflicts"));
      await waitFor(() => {
        expect(screen.getByText("Conflict load error")).toBeDefined();
      });
    });
  });
});
