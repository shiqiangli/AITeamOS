/**
 * AITeamOS Dashboard - Member Page Component Tests
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemberPage } from "../pages/members";

vi.mock("../api/client", () => ({
  listMembers: vi.fn(),
  listDepartments: vi.fn(),
  listSkills: vi.fn(),
  listTasks: vi.fn(),
  getMemberDetail: vi.fn(),
  getMemberProfileView: vi.fn(),
  createMember: vi.fn(),
  assignSkillToMember: vi.fn(),
  deleteMember: vi.fn(),
}));

import {
  listMembers,
  listDepartments,
  listSkills,
  listTasks,
  getMemberDetail,
  getMemberProfileView,
} from "../api/client";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("MemberPage", () => {
  beforeEach(() => {
    (listMembers as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: "member-1",
        kind: "ai",
        display_name: "Agent Ada",
        department_id: "dept-1",
        concurrency_limit: 2,
        is_archived: false,
        created_at: "2026-05-01T00:00:00Z",
      },
    ]);
    (listDepartments as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: "dept-1",
        name: "Compiler",
        leader_member_id: null,
        created_at: null,
      },
    ]);
    (listSkills as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: "skill-1234567890",
        name: "sv-elaboration",
        version: "1.0.0",
        description: "SystemVerilog elaboration capability",
        domain: "compiler",
        status: "published",
        circuit_state: "closed",
        capability_tags: ["compiler"],
        created_at: null,
      },
    ]);
    (getMemberDetail as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: "member-1",
      kind: "ai",
      display_name: "Agent Ada",
      role: "developer",
      department_id: "dept-1",
      concurrency_limit: 2,
      base_skill_set: ["skill-1234567890"],
      assigned_memories: ["memory-1234567890"],
      is_archived: false,
      created_at: "2026-05-01T00:00:00Z",
    });
    const tasks = [
      {
        id: "task-1",
        title: "Improve parser diagnostics",
        state: "running",
        priority: "P1",
        assigned_member_id: "member-1",
        department_id: "dept-1",
        retry_count: 0,
        review_round: 0,
        created_at: "2026-05-02T00:00:00Z",
      },
    ];
    (listTasks as ReturnType<typeof vi.fn>).mockResolvedValue(tasks);
    (getMemberProfileView as ReturnType<typeof vi.fn>).mockResolvedValue({
      member: {
        id: "member-1",
        kind: "ai",
        display_name: "Agent Ada",
        role: "developer",
        department_id: "dept-1",
        concurrency_limit: 2,
        base_skill_set: ["skill-1234567890"],
        assigned_memories: ["memory-1234567890"],
        is_archived: false,
        created_at: "2026-05-01T00:00:00Z",
      },
      stats: {
        skill_count: 1,
        memory_count: 1,
        project_count: 1,
        task_count: 1,
        active_task_count: 1,
        done_task_count: 0,
        failed_task_count: 0,
        done_rate: 0,
        activity_count: 1,
        last_activity_at: "2026-05-02T00:00:00Z",
      },
      skills: [
        {
          id: "skill-1234567890",
          name: "sv-elaboration",
          version: "1.0.0",
          description: "SystemVerilog elaboration capability",
          domain: "compiler",
          status: "published",
          circuit_state: "closed",
          capability_tags: ["compiler"],
          is_base: true,
          assigned_at: "2026-05-02T00:00:00Z",
          created_at: "2026-05-01T00:00:00Z",
        },
      ],
      memories: [
        {
          id: "memory-1234567890",
          title: "Elaboration boundary",
          tier: "principles",
          lifecycle_state: "active",
          confidence_value: 0.9,
          scope_kind: "project",
          current_version: 1,
          weight: 1,
          assigned_at: "2026-05-02T00:00:00Z",
          created_at: "2026-05-01T00:00:00Z",
        },
      ],
      projects: [
        {
          id: "project-1",
          name: "Compiler Core",
          description: null,
          department_id: "dept-1",
          status: "active",
          role: "contributor",
          assigned_at: "2026-05-02T00:00:00Z",
          created_at: "2026-05-01T00:00:00Z",
        },
      ],
      tasks,
      activities: [
        {
          id: "activity-1",
          kind: "task_completed",
          label: "Completed parser diagnostics",
          occurred_at: "2026-05-02T00:00:00Z",
          target_kind: "task",
          target_id: "task-1",
          payload: {},
        },
      ],
      capability_changes: [
        {
          id: "skill:skill-1234567890",
          kind: "skill_assigned",
          target_kind: "skill",
          target_id: "skill-1234567890",
          label: "sv-elaboration",
          occurred_at: "2026-05-02T00:00:00Z",
        },
      ],
    });
  });

  it("renders the member list as the primary surface", async () => {
    render(<MemberPage selectedId={null} />);

    await waitFor(() => {
      expect(screen.getByText("Agent Ada")).toBeDefined();
    });

    expect(screen.getByText("Visible")).toBeDefined();
    expect(screen.queryByText("Member Detail")).toBeNull();
  });

  it("opens selected member details with tabs and assigned tasks", async () => {
    const user = userEvent.setup();
    render(<MemberPage selectedId="member-1" />);

    await waitFor(() => {
      expect(getMemberProfileView).toHaveBeenCalledWith("member-1");
      expect(getMemberDetail).not.toHaveBeenCalled();
      expect(listTasks).not.toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.getAllByText("Agent Ada").length).toBeGreaterThan(0);
      expect(screen.getByText("Overview")).toBeDefined();
      expect(screen.getByText("Knowledge & Skills")).toBeDefined();
      expect(screen.getByText("Work")).toBeDefined();
      expect(screen.getByText("Change Log")).toBeDefined();
      expect(screen.getByText("Profile")).toBeDefined();
    });

    await user.click(screen.getByText("Work"));
    expect(screen.getByText("Improve parser diagnostics")).toBeDefined();
  });
});
