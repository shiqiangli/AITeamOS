/**
 * AITeamOS Dashboard — Metrics Page Component Tests
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/react";
import { MetricsPage } from "../pages/metrics";

// Mock the API client
vi.mock("../api/client", () => ({
  fetchValueMetrics: vi.fn(),
  fetchSystemHealth: vi.fn(),
  fetchMemoryHealth: vi.fn(),
}));

import { fetchValueMetrics, fetchSystemHealth, fetchMemoryHealth } from "../api/client";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("MetricsPage", () => {
  beforeEach(() => {
    (fetchValueMetrics as ReturnType<typeof vi.fn>).mockResolvedValue({
      memory_total: 10,
      memory_active: 7,
      memory_candidates: 2,
      memory_deprecated: 1,
      skill_count: 5,
      member_count: 3,
      task_count: 12,
      recall_count: 8,
      memory_active_rate: 0.72,
    });
    (fetchSystemHealth as ReturnType<typeof vi.fn>).mockResolvedValue({
      database: "connected",
      memory_total: 10,
      conflicts_open: 2,
      reviews_pending: 3,
      task_first_pass_rate: 0.85,
      status: "healthy",
    });
    (fetchMemoryHealth as ReturnType<typeof vi.fn>).mockResolvedValue({
      active: 150,
      candidate: 23,
      deprecated: 12,
      needs_verify: 8,
      total: 193,
      candidate_ratio: 0.119,
      deprecated_ratio: 0.062,
      needs_verify_ratio: 0.041,
    });
  });

  describe("System Overview", () => {
    it("should render system overview panel", async () => {
      render(<MetricsPage />);
      await waitFor(() => {
        expect(screen.getByText("System Overview")).toBeDefined();
      });
    });

    it("should display memory counts", async () => {
      render(<MetricsPage />);
      await waitFor(() => {
        expect(screen.getByText("Memories")).toBeDefined();
        expect(screen.getAllByText("10").length).toBeGreaterThanOrEqual(1);
      });
    });

    it("should display memory active rate as percentage", async () => {
      render(<MetricsPage />);
      await waitFor(() => {
        expect(screen.getByText("Active Rate")).toBeDefined();
        expect(screen.getByText("72.0%")).toBeDefined();
      });
    });

    it("should display skill and member counts", async () => {
      render(<MetricsPage />);
      await waitFor(() => {
        expect(screen.getByText("Skills")).toBeDefined();
        expect(screen.getAllByText("5").length).toBeGreaterThanOrEqual(1);
        expect(screen.getByText("Members")).toBeDefined();
        expect(screen.getAllByText("3").length).toBeGreaterThanOrEqual(1);
      });
    });

    it("should call fetchValueMetrics on mount", async () => {
      render(<MetricsPage />);
      await waitFor(() => {
        expect(fetchValueMetrics).toHaveBeenCalled();
      });
    });
  });

  describe("System Health", () => {
    it("should render system health panel", async () => {
      render(<MetricsPage />);
      await waitFor(() => {
        expect(screen.getByText("System Health")).toBeDefined();
      });
    });

    it("should display first pass rate", async () => {
      render(<MetricsPage />);
      await waitFor(() => {
        expect(screen.getByText("First Pass Rate")).toBeDefined();
        expect(screen.getByText("85.0%")).toBeDefined();
      });
    });

    it("should display open conflicts", async () => {
      render(<MetricsPage />);
      await waitFor(() => {
        expect(screen.getByText("Open Conflicts")).toBeDefined();
      });
    });

    it("should display database status", async () => {
      render(<MetricsPage />);
      await waitFor(() => {
        expect(screen.getByText("Database")).toBeDefined();
        expect(screen.getByText("connected")).toBeDefined();
      });
    });

    it("should call fetchSystemHealth on mount", async () => {
      render(<MetricsPage />);
      await waitFor(() => {
        expect(fetchSystemHealth).toHaveBeenCalled();
      });
    });
  });

  describe("Memory Health", () => {
    it("should render memory health panel", async () => {
      render(<MetricsPage />);
      await waitFor(() => {
        expect(screen.getByText("Memory Health")).toBeDefined();
      });
    });

    it("should display active and candidate counts", async () => {
      render(<MetricsPage />);
      await waitFor(() => {
        expect(screen.getAllByText("Active").length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText("150").length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText("Candidate").length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText("23").length).toBeGreaterThanOrEqual(1);
      });
    });

    it("should call fetchMemoryHealth on mount", async () => {
      render(<MetricsPage />);
      await waitFor(() => {
        expect(fetchMemoryHealth).toHaveBeenCalled();
      });
    });
  });

  describe("Error Handling", () => {
    it("should display error when metrics fetch fails", async () => {
      (fetchValueMetrics as ReturnType<typeof vi.fn>).mockRejectedValue(
        new Error("Metrics unavailable"),
      );
      render(<MetricsPage />);
      await waitFor(() => {
        expect(screen.getByText("Metrics unavailable")).toBeDefined();
      });
    });
  });
});
