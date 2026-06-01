/**
 * AITeamOS Dashboard - Department Page Component Tests
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DepartmentPage } from "../pages/manager";

vi.mock("../api/client", () => ({
  listDepartments: vi.fn(),
  listMembers: vi.fn(),
  listProjects: vi.fn(),
  createDepartment: vi.fn(),
  deleteDepartment: vi.fn(),
}));

import {
  listDepartments,
  listMembers,
  listProjects,
  deleteDepartment,
} from "../api/client";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("DepartmentPage", () => {
  beforeEach(() => {
    (listDepartments as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: "dept-1",
        name: "Compiler",
        leader_member_id: null,
        created_at: "2026-05-01T00:00:00Z",
      },
    ]);
    (listMembers as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (listProjects as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (deleteDepartment as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("blocks department deletion in the UI when members or projects still reference it", async () => {
    (listMembers as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: "member-1",
        kind: "ai",
        display_name: "Agent Ada",
        department_id: "dept-1",
        concurrency_limit: 2,
        is_archived: false,
        created_at: null,
      },
    ]);
    (listProjects as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: "project-1",
        name: "Compiler Core",
        department_id: "dept-1",
        status: "active",
        member_count: 1,
        created_at: null,
      },
    ]);

    const user = userEvent.setup();
    render(<DepartmentPage selectedId="dept-1" />);

    await waitFor(() => {
      expect(listDepartments).toHaveBeenCalled();
    });
    await user.click(screen.getByRole("tab", { name: "Actions" }));

    expect(screen.getByText(/Cannot delete while this department has 1 member\(s\) and 1 project\(s\)/)).toBeDefined();
    expect((screen.getByRole("button", { name: /Delete/ }) as HTMLButtonElement).disabled).toBe(true);
    expect(deleteDepartment).not.toHaveBeenCalled();
  });

  it("deletes a department when there are no local references", async () => {
    const user = userEvent.setup();
    render(<DepartmentPage selectedId="dept-1" />);

    await waitFor(() => {
      expect(listDepartments).toHaveBeenCalled();
    });
    await user.click(screen.getByRole("tab", { name: "Actions" }));
    await user.click(screen.getByRole("button", { name: /Delete/ }));

    await waitFor(() => {
      expect(deleteDepartment).toHaveBeenCalledWith("dept-1");
    });
  });
});
