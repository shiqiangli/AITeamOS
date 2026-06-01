/**
 * AITeamOS Dashboard — API Client Tests (plan.md §1.6)
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  apiRequest,
  setAuthToken,
  getAuthToken,
  listMemories,
  listSkills,
  listMembers,
  getMemberProfileView,
  listDepartments,
  listProjects,
  getMemoryDetail,
  getMemoryVersions,
  getSkillDetail,
  getMemberDetail,
  getProjectDetail,
  createMemory,
  registerSkill,
  createMember,
  createDepartment,
  createProject,
  publishSkill,
  deprecateSkill,
  listLlmModels,
  getLlmModelDetail,
  createLlmModel,
  listAgentProfiles,
  getAgentProfileDetail,
  createAgentProfile,
  changeMemoryLifecycle,
  assignSkillToMember,
  assignMemberToProject,
  searchMemories,
  listPendingReviews,
  getReviewsByTarget,
  createReview,
  decideReview,
  listUnresolvedConflicts,
  reportConflict,
  resolveConflict,
  ApiClientError,
  fetchHealth,
  fetchValueMetrics,
  fetchSystemHealth,
} from "../api/client";

describe("API Client", () => {
  beforeEach(() => {
    setAuthToken(null);
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function mockFetchResponse(data: unknown, status = 200) {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: status >= 200 && status < 300,
      status,
      statusText: status === 200 ? "OK" : "Error",
      json: () => Promise.resolve(data),
      text: () => Promise.resolve(JSON.stringify(data)),
    });
  }

  describe("Auth Token", () => {
    it("should set and get auth token", () => {
      expect(getAuthToken()).toBeNull();
      setAuthToken("test-token");
      expect(getAuthToken()).toBe("test-token");
    });

    it("should include Authorization header when token is set", async () => {
      setAuthToken("my-token");
      mockFetchResponse([]);
      await apiRequest("/test");
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/test",
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: "Bearer my-token",
          }),
        }),
      );
    });

    it("should not include Authorization header when no token", async () => {
      mockFetchResponse([]);
      await apiRequest("/test");
      const callArgs = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(callArgs[1].headers.Authorization).toBeUndefined();
    });
  });

  describe("Error handling", () => {
    it("should throw ApiClientError on non-ok response", async () => {
      (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: "Not Found",
        json: () => Promise.resolve({ detail: "not found" }),
        text: () => Promise.resolve("not found"),
      });
      await expect(apiRequest("/missing")).rejects.toThrow(ApiClientError);
    });

    it("should include API detail text in error messages", async () => {
      (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        ok: false,
        status: 409,
        statusText: "Conflict",
        json: () => Promise.resolve({ detail: "Cannot delete: department has 1 member(s)." }),
        text: () => Promise.resolve("conflict"),
      });
      await expect(apiRequest("/conflict")).rejects.toThrow("API 409: Cannot delete: department has 1 member(s).");
    });

    it("should handle 204 No Content", async () => {
      (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        ok: true,
        status: 204,
        statusText: "No Content",
        json: () => Promise.resolve(undefined),
      });
      const result = await apiRequest<void>("/action", { method: "POST" });
      expect(result).toBeUndefined();
    });
  });

  describe("Health", () => {
    it("should fetch health status", async () => {
      (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ status: "ok" }),
      });
      const result = await fetchHealth();
      expect(result.status).toBe("ok");
      expect(fetch).toHaveBeenCalledWith("/health");
    });
  });

  describe("Memory API", () => {
    it("should list memories with default params", async () => {
      const data = [{ id: "m1", title: "Test", tier: "core" }];
      mockFetchResponse(data);
      const result = await listMemories();
      expect(result).toEqual(data);
      expect(fetch).toHaveBeenCalledWith("/api/v1/memories", expect.anything());
    });

    it("should list memories with filters", async () => {
      mockFetchResponse([]);
      await listMemories({ tier: "core", limit: 10 });
      const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0];
      expect(url).toContain("tier=core");
      expect(url).toContain("limit=10");
    });

    it("should search memories", async () => {
      mockFetchResponse([]);
      await searchMemories("test", "tag1,tag2");
      const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0];
      expect(url).toContain("keyword=test");
      expect(url).toContain("tags=tag1%2Ctag2");
    });

    it("should get memory detail", async () => {
      const data = { id: "m1", title: "Detail", tier: "core" };
      mockFetchResponse(data);
      const result = await getMemoryDetail("m1");
      expect(result).toEqual(data);
      expect(fetch).toHaveBeenCalledWith("/api/v1/memories/m1", expect.anything());
    });

    it("should get memory versions", async () => {
      const data = [
        {
          version_no: 1,
          diff: { statement: "Initial" },
          reason: "Created",
          author_member_id: "member-uuid",
          created_at: "2026-05-01T00:00:00Z",
        },
      ];
      mockFetchResponse(data);
      const result = await getMemoryVersions("m1");
      expect(result[0].version_no).toBe(1);
      expect(fetch).toHaveBeenCalledWith("/api/v1/memories/m1/versions", expect.anything());
    });

    it("should create memory", async () => {
      const payload = {
        tier: "core",
        title: "New",
        statement: "Statement",
        scope_kind: "domain",
        scope_id: "global",
        source_kind: "manual_input",
      };
      mockFetchResponse({ id: "new-id", ...payload }, 201);
      const result = await createMemory(payload);
      expect(result.id).toBe("new-id");
    });

    it("should change memory lifecycle", async () => {
      mockFetchResponse({ id: "m1", lifecycle_state: "archived" });
      await changeMemoryLifecycle("m1", "archived", "done");
      const callArgs = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(callArgs[0]).toContain("/memories/m1/lifecycle");
      expect(callArgs[1].method).toBe("PATCH");
      expect(JSON.parse(callArgs[1].body)).toEqual({
        new_state: "archived",
        reason: "done",
      });
    });
  });

  describe("Skill API", () => {
    it("should list skills", async () => {
      mockFetchResponse([{ id: "s1", name: "TestSkill" }]);
      const result = await listSkills();
      expect(result).toHaveLength(1);
    });

    it("should get skill detail", async () => {
      mockFetchResponse({ id: "s1", name: "Detail" });
      const result = await getSkillDetail("s1");
      expect(result.name).toBe("Detail");
    });

    it("should register skill", async () => {
      mockFetchResponse({ id: "new", name: "my-skill" }, 201);
      const result = await registerSkill({
        name: "my-skill",
        domain: "compiler",
        capability_tags: ["compiler"],
      });
      expect(result.name).toBe("my-skill");
      const callArgs = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      const body = JSON.parse(callArgs[1].body);
      expect(body.domain).toBe("compiler");
      expect(body.entry_point).toBeUndefined();
    });

    it("should publish skill", async () => {
      mockFetchResponse({ id: "s1", status: "published" });
      await publishSkill("s1");
      const callArgs = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(callArgs[0]).toContain("/skills/s1/publish");
      expect(callArgs[1].method).toBe("PATCH");
    });

    it("should deprecate skill", async () => {
      mockFetchResponse({ id: "s1", status: "deprecated" });
      await deprecateSkill("s1", "no longer needed");
      const callArgs = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(callArgs[0]).toContain("/skills/s1/deprecate");
    });
  });

  describe("Member API", () => {
    it("should list members", async () => {
      mockFetchResponse([{ id: "mem1", display_name: "Alice" }]);
      const result = await listMembers();
      expect(result).toHaveLength(1);
    });

    it("should get member detail", async () => {
      mockFetchResponse({ id: "mem1", display_name: "Alice", kind: "human" });
      const result = await getMemberDetail("mem1");
      expect(result.display_name).toBe("Alice");
    });

    it("should get member profile view", async () => {
      mockFetchResponse({
        member: { id: "mem1", display_name: "Alice", kind: "human" },
        stats: { task_count: 0 },
        skills: [],
        memories: [],
        projects: [],
        tasks: [],
        activities: [],
        capability_changes: [],
      });
      const result = await getMemberProfileView("mem1");
      expect(result.member.display_name).toBe("Alice");
      expect(fetch).toHaveBeenCalledWith("/api/v1/members/mem1/profile", expect.anything());
    });

    it("should create member", async () => {
      mockFetchResponse({ id: "new", display_name: "Bob" }, 201);
      const result = await createMember({ kind: "human", display_name: "Bob" });
      expect(result.display_name).toBe("Bob");
    });

    it("should assign skill to member", async () => {
      (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        ok: true,
        status: 204,
        json: () => Promise.resolve(undefined),
      });
      await assignSkillToMember("mem1", "sv-elaboration");
      const callArgs = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(callArgs[0]).toContain("/members/mem1/skills");
      const body = JSON.parse(callArgs[1].body);
      expect(body.skill_name).toBe("sv-elaboration");
      expect(body.skill_id).toBeUndefined();
    });
  });

  describe("Department API", () => {
    it("should list departments", async () => {
      mockFetchResponse([{ id: "d1", name: "Engineering" }]);
      const result = await listDepartments();
      expect(result).toHaveLength(1);
    });

    it("should create department", async () => {
      mockFetchResponse({ id: "new", name: "HR" }, 201);
      const result = await createDepartment({ name: "HR" });
      expect(result.name).toBe("HR");
    });
  });

  describe("Project API", () => {
    it("should list projects", async () => {
      mockFetchResponse([{ id: "p1", name: "Alpha" }]);
      const result = await listProjects();
      expect(result).toHaveLength(1);
    });

    it("should get project detail", async () => {
      mockFetchResponse({ id: "p1", name: "Alpha", status: "active" });
      const result = await getProjectDetail("p1");
      expect(result.name).toBe("Alpha");
    });

    it("should create project", async () => {
      mockFetchResponse({ id: "new", name: "Beta" }, 201);
      const result = await createProject({ name: "Beta" });
      expect(result.name).toBe("Beta");
    });

    it("should create project with repository_refs", async () => {
      mockFetchResponse({ id: "new", name: "Gamma", repository_refs: ["https://github.com/org/repo"] }, 201);
      const result = await createProject({ name: "Gamma", repository_refs: ["https://github.com/org/repo"] });
      expect(result.name).toBe("Gamma");
      const callArgs = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      const body = JSON.parse(callArgs[1].body);
      expect(body.repository_refs).toEqual(["https://github.com/org/repo"]);
    });

    it("should assign member to project", async () => {
      (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        ok: true,
        status: 204,
        json: () => Promise.resolve(undefined),
      });
      await assignMemberToProject("p1", "mem1");
      const callArgs = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(callArgs[0]).toContain("/projects/p1/members");
    });
  });

  describe("Runtime Resource API", () => {
    it("should list LLM models with filters", async () => {
      mockFetchResponse([{ id: "llm1", name: "gpt-compiler", provider: "openai" }]);
      const result = await listLlmModels({ status: "active", limit: 10 });
      expect(result).toHaveLength(1);
      const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0];
      expect(url).toContain("/llm-models");
      expect(url).toContain("status=active");
      expect(url).toContain("limit=10");
    });

    it("should get LLM model detail", async () => {
      mockFetchResponse({ id: "llm1", name: "gpt-compiler", provider: "openai" });
      const result = await getLlmModelDetail("llm1");
      expect(result.name).toBe("gpt-compiler");
      expect(fetch).toHaveBeenCalledWith("/api/v1/llm-models/llm1", expect.anything());
    });

    it("should create LLM model", async () => {
      mockFetchResponse({ id: "llm-new", name: "local-code", provider: "local" }, 201);
      const result = await createLlmModel({
        name: "local-code",
        provider: "local",
        model_id: "codestral-local",
        supports_tools: true,
        capability_tags: ["code"],
      });
      expect(result.id).toBe("llm-new");
      const callArgs = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(callArgs[0]).toContain("/llm-models");
      expect(callArgs[1].method).toBe("POST");
      const body = JSON.parse(callArgs[1].body);
      expect(body.model_id).toBe("codestral-local");
      expect(body.supports_tools).toBe(true);
    });

    it("should list agent profiles", async () => {
      mockFetchResponse([{ id: "agent1", name: "compiler-agent" }]);
      const result = await listAgentProfiles({ name_filter: "compiler" });
      expect(result).toHaveLength(1);
      const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0];
      expect(url).toContain("/agent-profiles");
      expect(url).toContain("name_filter=compiler");
    });

    it("should get agent profile detail", async () => {
      mockFetchResponse({ id: "agent1", name: "compiler-agent", default_llm_model_id: "llm1" });
      const result = await getAgentProfileDetail("agent1");
      expect(result.default_llm_model_id).toBe("llm1");
      expect(fetch).toHaveBeenCalledWith("/api/v1/agent-profiles/agent1", expect.anything());
    });

    it("should create agent profile", async () => {
      mockFetchResponse({ id: "agent-new", name: "compiler-agent" }, 201);
      const result = await createAgentProfile({
        name: "compiler-agent",
        default_llm_model_id: "llm1",
        tool_names: ["repo.search"],
        memory_policy: { recall: "task_scoped" },
      });
      expect(result.id).toBe("agent-new");
      const callArgs = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(callArgs[0]).toContain("/agent-profiles");
      expect(callArgs[1].method).toBe("POST");
      const body = JSON.parse(callArgs[1].body);
      expect(body.default_llm_model_id).toBe("llm1");
      expect(body.tool_names).toEqual(["repo.search"]);
    });

  });

  describe("Governance API — Reviews", () => {
    it("should list pending reviews", async () => {
      const data = [
        {
          id: "r1",
          target_kind: "memory_candidate",
          target_id: "t1",
          reviewer_member_id: "m1",
          verdict: null,
          reason: null,
          decision_at: null,
          created_at: "2026-01-01T00:00:00Z",
        },
      ];
      mockFetchResponse(data);
      const result = await listPendingReviews();
      expect(result).toHaveLength(1);
      expect(result[0].target_kind).toBe("memory_candidate");
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/reviews/pending",
        expect.anything(),
      );
    });

    it("should get reviews by target", async () => {
      mockFetchResponse([]);
      const result = await getReviewsByTarget("memory_candidate", "target-uuid");
      expect(result).toEqual([]);
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/reviews/by-target/memory_candidate/target-uuid",
        expect.anything(),
      );
    });

    it("should create review", async () => {
      const payload = {
        target_kind: "memory_candidate",
        target_id: "target-uuid",
        reviewer_member_id: "reviewer-uuid",
      };
      mockFetchResponse(
        {
          id: "r-new",
          ...payload,
          verdict: null,
          reason: null,
          decision_at: null,
          created_at: "2026-01-01T00:00:00Z",
        },
        201,
      );
      const result = await createReview(payload);
      expect(result.id).toBe("r-new");
      const callArgs = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(callArgs[0]).toContain("/reviews");
      expect(callArgs[1].method).toBe("POST");
    });

    it("should decide review", async () => {
      mockFetchResponse({
        id: "r1",
        target_kind: "memory_candidate",
        target_id: "t1",
        reviewer_member_id: "m1",
        verdict: "approve",
        reason: "Looks good",
        decision_at: "2026-01-02T00:00:00Z",
        created_at: "2026-01-01T00:00:00Z",
      });
      const result = await decideReview("r1", {
        verdict: "approve",
        reason: "Looks good",
      });
      expect(result.verdict).toBe("approve");
      const callArgs = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(callArgs[0]).toContain("/reviews/r1/decide");
      expect(callArgs[1].method).toBe("POST");
    });

    it("should decide review with correction", async () => {
      mockFetchResponse({
        id: "r1",
        verdict: "revise",
        reason: "Needs work",
        correction: "Fix the typo",
      });
      const result = await decideReview("r1", {
        verdict: "revise",
        reason: "Needs work",
        correction: "Fix the typo",
      });
      expect(result.verdict).toBe("revise");
    });
  });

  describe("Governance API — Conflicts", () => {
    it("should list unresolved conflicts", async () => {
      const data = [
        {
          id: "c1",
          memory_a_id: "ma1",
          memory_b_id: "mb1",
          conflict_kind: "semantic",
          detected_by: "embedding_similarity",
          resolution: null,
          winner_id: null,
          resolved_by: null,
          created_at: "2026-01-01T00:00:00Z",
        },
      ];
      mockFetchResponse(data);
      const result = await listUnresolvedConflicts();
      expect(result).toHaveLength(1);
      expect(result[0].conflict_kind).toBe("semantic");
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/conflicts/unresolved",
        expect.anything(),
      );
    });

    it("should report conflict", async () => {
      const payload = {
        memory_a_id: "ma-uuid",
        memory_b_id: "mb-uuid",
        conflict_kind: "semantic",
        detected_by: "embedding_similarity",
      };
      mockFetchResponse(
        {
          id: "c-new",
          ...payload,
          resolution: null,
          winner_id: null,
          resolved_by: null,
          created_at: "2026-01-01T00:00:00Z",
        },
        201,
      );
      const result = await reportConflict(payload);
      expect(result.id).toBe("c-new");
      const callArgs = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(callArgs[0]).toContain("/conflicts");
      expect(callArgs[1].method).toBe("POST");
    });

    it("should resolve conflict", async () => {
      mockFetchResponse({
        id: "c1",
        memory_a_id: "ma1",
        memory_b_id: "mb1",
        conflict_kind: "semantic",
        detected_by: "embedding_similarity",
        resolution: "keep_a",
        winner_id: "ma1",
        resolved_by: "resolver-uuid",
        created_at: "2026-01-01T00:00:00Z",
      });
      const result = await resolveConflict("c1", {
        resolution: "keep_a",
        winner_id: "ma1",
        resolved_by: "resolver-uuid",
      });
      expect(result.resolution).toBe("keep_a");
      const callArgs = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(callArgs[0]).toContain("/conflicts/c1/resolve");
      expect(callArgs[1].method).toBe("POST");
    });

    it("should resolve conflict with deprecate_both", async () => {
      mockFetchResponse({
        id: "c2",
        resolution: "deprecate_both",
        winner_id: null,
        resolved_by: "resolver-uuid",
      });
      const result = await resolveConflict("c2", {
        resolution: "deprecate_both",
        resolved_by: "resolver-uuid",
      });
      expect(result.resolution).toBe("deprecate_both");
      expect(result.winner_id).toBeNull();
    });
  });

  describe("Metrics API", () => {
    it("should fetch value metrics with default period", async () => {
      const data = {
        memory_total: 10,
        memory_active: 7,
        memory_candidates: 2,
        memory_deprecated: 1,
        skill_count: 5,
        member_count: 3,
        task_count: 12,
        recall_count: 8,
        memory_active_rate: 0.7,
      };
      mockFetchResponse(data);
      const result = await fetchValueMetrics();
      expect(result.memory_total).toBe(10);
      expect(result.memory_active_rate).toBe(0.7);
      const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0];
      expect(url).toContain("/metrics/value");
    });

    it("should fetch value metrics with custom period", async () => {
      mockFetchResponse({
        memory_total: 5,
        memory_active: 3,
        memory_candidates: 1,
        memory_deprecated: 1,
        skill_count: 2,
        member_count: 1,
        task_count: 4,
        recall_count: 2,
        memory_active_rate: 0.6,
      });
      const result = await fetchValueMetrics("daily");
      expect(result.memory_active_rate).toBe(0.6);
      const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0];
      expect(url).toContain("period=daily");
    });

    it("should fetch system health", async () => {
      const data = {
        database: "connected",
        memory_total: 10,
        conflicts_open: 2,
        reviews_pending: 3,
        task_first_pass_rate: 0.85,
        status: "healthy",
      };
      mockFetchResponse(data);
      const result = await fetchSystemHealth();
      expect(result.task_first_pass_rate).toBe(0.85);
      expect(result.conflicts_open).toBe(2);
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/metrics/system-health",
        expect.anything(),
      );
    });

    it("should handle empty system health", async () => {
      mockFetchResponse({
        database: "connected",
        memory_total: 0,
        conflicts_open: 0,
        reviews_pending: 0,
        task_first_pass_rate: 0.0,
        status: "unknown",
      });
      const result = await fetchSystemHealth();
      expect(result.status).toBe("unknown");
      expect(result.memory_total).toBe(0);
    });
  });
});
