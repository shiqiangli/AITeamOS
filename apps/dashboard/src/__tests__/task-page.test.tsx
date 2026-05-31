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
  listAgentProfiles: vi.fn(),
  getTaskDetail: vi.fn(),
  createTask: vi.fn(),
  assignTask: vi.fn(),
  assignTaskRuntime: vi.fn(),
  startTaskRun: vi.fn(),
  cancelTask: vi.fn(),
  requeueTask: vi.fn(),
  deleteTask: vi.fn(),
}));

import {
  listTasks,
  listDepartments,
  listMembers,
  listLlmModels,
  listAgentProfiles,
  createTask,
  assignTaskRuntime,
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
    (listMembers as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (listLlmModels as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: "llm-1",
        name: "GPT Compiler",
        provider: "openai",
        model_id: "gpt-compiler",
        status: "active",
      },
    ]);
    (listAgentProfiles as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: "agent-1",
        name: "Compiler Agent",
        default_llm_model_id: "llm-1",
        runtime_kind: "llm_agent",
        description: "",
        tool_names: [],
        status: "active",
      },
    ]);
    (createTask as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: "task-1",
      state: "draft",
    });
    (assignTaskRuntime as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: "task-1",
      assigned_llm_model_id: "llm-1",
      assigned_agent_profile_id: "agent-1",
      status: "runtime_assigned",
    });
  });

  it("assigns the selected agent and its default LLM when creating a task", async () => {
    const user = userEvent.setup();
    render(<TaskPage selectedId={null} />);

    await screen.findByText("No records");
    await user.click(await screen.findByRole("button", { name: /Create Task/ }));
    await user.type(screen.getByLabelText("Task Name"), "Add LICM pass");
    await user.type(screen.getByPlaceholderText("Select or type department name"), "Compiler");
    await user.type(screen.getByPlaceholderText("Select or type agent name"), "Compiler Agent");
    await user.click(screen.getByRole("button", { name: /^Create$/ }));

    await waitFor(() => {
      expect(createTask).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Add LICM pass",
          department_id: "dept-1",
        }),
      );
      expect(assignTaskRuntime).toHaveBeenCalledWith("task-1", {
        agent_profile_id: "agent-1",
        llm_model_id: "llm-1",
      });
    });
  });
});
