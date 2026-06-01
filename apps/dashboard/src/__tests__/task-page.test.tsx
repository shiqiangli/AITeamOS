/**
 * AITeamOS Dashboard - Task Page Component Tests
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TaskPage } from "../pages/tasks";

vi.mock("../api/client", () => ({
  listTasks: vi.fn(),
  listDepartments: vi.fn(),
  listMembers: vi.fn(),
  listLlmModels: vi.fn(),
  getTaskDetail: vi.fn(),
  createTask: vi.fn(),
  createJob: vi.fn(),
  listJobs: vi.fn(),
  startTaskRun: vi.fn(),
  cancelTask: vi.fn(),
  requeueTask: vi.fn(),
  deleteTask: vi.fn(),
  updateTask: vi.fn(),
}));

import {
  listTasks,
  listDepartments,
  listMembers,
  listLlmModels,
  createTask,
} from "../api/client";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("TaskPage", () => {
  beforeEach(() => {
    (listTasks as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (listDepartments as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: "dept-1", name: "Compiler" },
    ]);
    (listMembers as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: "mem-1", display_name: "Owen", kind: "ai", role: "PV" },
    ]);
    (listLlmModels as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: "llm-1",
        name: "GPT Compiler",
        provider: "openai",
        model_id: "gpt-compiler",
        status: "active",
      },
    ]);
    (createTask as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: "task-1",
      state: "draft",
    });
  });

  it("creates a task with department and priority", async () => {
    const user = userEvent.setup();
    render(<TaskPage selectedId={null} />);

    await screen.findByText("No records");
    await user.click(await screen.findByRole("button", { name: /Create Task/ }));
    await user.type(screen.getByLabelText("Task Name"), "Add LICM pass");
    await user.type(screen.getByPlaceholderText("Select or type department name"), "Compiler");
    await user.click(screen.getByRole("button", { name: /^Create$/ }));

    await waitFor(() => {
      expect(createTask).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Add LICM pass",
          department_id: "dept-1",
        }),
      );
    });
  });
});
