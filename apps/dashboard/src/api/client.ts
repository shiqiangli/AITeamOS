/**
 * AITeamOS Dashboard — API Client (plan.md §1.6.1)
 *
 * Typed REST client for the new API Gateway at /api/v1.
 * Uses fetch with Bearer token auth and JSON content type.
 */

const API_BASE = "/api/v1";

let _authToken: string | null = null;

export function setAuthToken(token: string | null): void {
  _authToken = token;
}

export function getAuthToken(): string | null {
  return _authToken;
}

// ─── Generic fetch wrapper ───────────────────────────────────────────────────

export class ApiClientError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public body: unknown,
  ) {
    super(formatApiErrorMessage(status, statusText, body));
    this.name = "ApiClientError";
  }
}

function formatApiErrorMessage(status: number, statusText: string, body: unknown): string {
  const detail = extractApiErrorDetail(body);
  return detail ? `API ${status}: ${detail}` : `API ${status}: ${statusText}`;
}

function extractApiErrorDetail(body: unknown): string | null {
  if (!body) return null;
  if (typeof body === "string") return body || null;
  if (typeof body !== "object") return null;

  const record = body as Record<string, unknown>;
  if (typeof record.detail === "string") return record.detail;
  if (Array.isArray(record.detail)) return record.detail.map(String).join("; ");

  const error = record.error;
  if (error && typeof error === "object") {
    const errorRecord = error as Record<string, unknown>;
    if (typeof errorRecord.message === "string") return errorRecord.message;
  }

  if (typeof record.message === "string") return record.message;
  return null;
}

export async function apiRequest<T>(
  path: string,
  options: { method?: string; body?: unknown } = {},
): Promise<T> {
  const { method = "GET", body } = options;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };
  if (_authToken) {
    headers["Authorization"] = `Bearer ${_authToken}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    let errorBody: unknown;
    try {
      errorBody = await res.json();
    } catch {
      errorBody = await res.text().catch(() => null);
    }
    throw new ApiClientError(res.status, res.statusText, errorBody);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ─── Health ──────────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch("/health");
  if (!res.ok) throw new ApiClientError(res.status, res.statusText, null);
  return res.json() as Promise<HealthResponse>;
}

// ─── Memory types ────────────────────────────────────────────────────────────

export interface MemorySummary {
  id: string;
  tier: string;
  title: string;
  lifecycle_state: string;
  confidence_value: number;
  scope_kind: string;
  tags: string[];
  current_version: number;
  created_at: string | null;
}

export interface MemoryDetail {
  id: string;
  tier: string;
  title: string;
  statement: string;
  lifecycle_state: string;
  confidence_value: number;
  versions: number;
  created_at: string;
}

export interface MemoryLifecycleResponse {
  id: string;
  lifecycle_state: string;
}

export interface MemoryVersion {
  version_no: number;
  diff: unknown;
  reason: string | null;
  author_member_id: string | null;
  created_at: string | null;
}

export interface CreateMemoryPayload {
  tier: string;
  title: string;
  statement: string;
  scope_kind: string;
  scope_id: string;
  source_kind: string;
  confidence?: number;
  tags?: string[];
  created_by?: string;
}

export interface UpdateMemoryPayload {
  title?: string;
  statement?: string;
  tags?: string[];
  edit_reason?: string;
}

export interface CreateMemoryEdgePayload {
  source_id: string;
  target_id: string;
  relation_type: string;
  weight?: number;
  created_by?: string;
}

// ─── Memory API ──────────────────────────────────────────────────────────────

export interface ListMemoriesParams {
  tier?: string;
  scope_kind?: string;
  lifecycle?: string;
  offset?: number;
  limit?: number;
}

export function listMemories(params: ListMemoriesParams = {}): Promise<MemorySummary[]> {
  const qs = buildQueryString(params);
  return apiRequest<MemorySummary[]>(`/memories${qs}`);
}

export function searchMemories(keyword?: string, tags?: string, limit = 20): Promise<MemorySummary[]> {
  const qs = buildQueryString({ keyword, tags, limit });
  return apiRequest<MemorySummary[]>(`/memories/search${qs}`);
}

export function getMemoryDetail(id: string): Promise<MemoryDetail> {
  return apiRequest<MemoryDetail>(`/memories/${encodeURIComponent(id)}`);
}

export function getMemoryVersions(id: string): Promise<MemoryVersion[]> {
  return apiRequest<MemoryVersion[]>(`/memories/${encodeURIComponent(id)}/versions`);
}

export function createMemory(payload: CreateMemoryPayload): Promise<MemoryDetail> {
  return apiRequest<MemoryDetail>("/memories", { method: "POST", body: payload });
}

export function updateMemory(id: string, payload: UpdateMemoryPayload): Promise<MemoryDetail> {
  return apiRequest<MemoryDetail>(`/memories/${encodeURIComponent(id)}`, { method: "PUT", body: payload });
}

export function changeMemoryLifecycle(
  id: string,
  newState: string,
  reason?: string,
): Promise<MemoryLifecycleResponse> {
  return apiRequest<MemoryLifecycleResponse>(`/memories/${encodeURIComponent(id)}/lifecycle`, {
    method: "PATCH",
    body: { new_state: newState, reason },
  });
}

export function createMemoryEdge(payload: CreateMemoryEdgePayload): Promise<{ id: string }> {
  return apiRequest<{ id: string }>("/memories/edges", { method: "POST", body: payload });
}

// ─── Skill types ─────────────────────────────────────────────────────────────

export interface SkillSummary {
  id: string;
  name: string;
  version: string;
  description: string;
  domain: string;
  status: string;
  capability_tags: string[];
  created_at: string | null;
}

export interface SkillDetail {
  id: string;
  name: string;
  version: string;
  description: string;
  domain: string;
  status: string;
  capability_tags: string[];
  created_at: string | null;
}

export interface RegisterSkillPayload {
  name: string;
  version?: string;
  description?: string;
  domain?: string;
  capability_tags?: string[];
}

// ─── Skill API ───────────────────────────────────────────────────────────────

export interface ListSkillsParams {
  status?: string;
  name_filter?: string;
  offset?: number;
  limit?: number;
}

export function listSkills(params: ListSkillsParams = {}): Promise<SkillSummary[]> {
  const qs = buildQueryString(params);
  return apiRequest<SkillSummary[]>(`/skills${qs}`);
}

export function getSkillDetail(id: string): Promise<SkillDetail> {
  return apiRequest<SkillDetail>(`/skills/${encodeURIComponent(id)}`);
}

export function registerSkill(payload: RegisterSkillPayload): Promise<SkillDetail> {
  return apiRequest<SkillDetail>("/skills", { method: "POST", body: payload });
}

export function publishSkill(id: string, approvedBy?: string): Promise<SkillDetail> {
  return apiRequest<SkillDetail>(`/skills/${encodeURIComponent(id)}/publish`, {
    method: "PATCH",
    body: { approved_by: approvedBy },
  });
}

export function deprecateSkill(id: string, reason?: string): Promise<SkillDetail> {
  return apiRequest<SkillDetail>(`/skills/${encodeURIComponent(id)}/deprecate`, {
    method: "PATCH",
    body: { reason },
  });
}

export function updateSkill(id: string, payload: { description?: string; domain?: string; capability_tags?: string[] }): Promise<SkillDetail> {
  return apiRequest<SkillDetail>(`/skills/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: payload,
  });
}

export interface SkillFileResponse {
  skill_id: string;
  skill_name: string;
  file_path: string;
  content: string;
  exists: boolean;
}

export function fetchSkillFile(id: string): Promise<SkillFileResponse> {
  return apiRequest<SkillFileResponse>(`/skills/${encodeURIComponent(id)}/file`);
}

// ─── Member types ────────────────────────────────────────────────────────────

export interface MemberSummary {
  id: string;
  kind: string;
  display_name: string;
  role: string | null;
  department_id: string | null;
  concurrency_limit: number;
  is_archived: boolean;
  created_at: string | null;
}

export interface MemberDetail {
  id: string;
  kind: string;
  display_name: string;
  role: string | null;
  department_id: string;
  concurrency_limit: number;
  base_skill_set: string[];
  assigned_memories: string[];
  prompt_template: string;
  is_archived: boolean;
  created_at: string;
}

export interface MemberProfileStats {
  skill_count: number;
  memory_count: number;
  project_count: number;
  task_count: number;
  active_task_count: number;
  done_task_count: number;
  failed_task_count: number;
  done_rate: number | null;
  activity_count: number;
  last_activity_at: string | null;
}

export interface MemberSkillRecord {
  id: string;
  name: string;
  version: string | null;
  description: string | null;
  domain: string | null;
  status: string | null;
  capability_tags: string[];
  is_base: boolean;
  assigned_at: string | null;
  created_at: string | null;
}

export interface MemberMemoryRecord {
  id: string;
  title: string;
  tier: string | null;
  lifecycle_state: string | null;
  confidence_value: number | null;
  scope_kind: string | null;
  current_version: number | null;
  weight: number;
  assigned_at: string | null;
  created_at: string | null;
}

export interface MemberProjectRecord {
  id: string;
  name: string;
  description: string | null;
  department_id: string | null;
  status: string | null;
  role: string | null;
  assigned_at: string | null;
  created_at: string | null;
}

export interface MemberActivityRecord {
  id: string;
  kind: string;
  label: string;
  occurred_at: string | null;
  target_kind: string | null;
  target_id: string | null;
  payload: Record<string, unknown>;
}

export interface MemberCapabilityChangeRecord {
  id: string;
  kind: string;
  target_kind: string;
  target_id: string;
  label: string;
  occurred_at: string | null;
}

export interface MemberProfileView {
  member: MemberDetail;
  stats: MemberProfileStats;
  skills: MemberSkillRecord[];
  memories: MemberMemoryRecord[];
  projects: MemberProjectRecord[];
  tasks: TaskSummary[];
  activities: MemberActivityRecord[];
  capability_changes: MemberCapabilityChangeRecord[];
}

export interface CreateMemberPayload {
  kind: string;
  display_name: string;
  department_id?: string;
  role?: string;
  concurrency_limit?: number;
  base_skill_set?: string[];
  created_by?: string;
}

// ─── Member API ──────────────────────────────────────────────────────────────

export interface ListMembersParams {
  department_id?: string;
  kind?: string;
  offset?: number;
  limit?: number;
}

export function listMembers(params: ListMembersParams = {}): Promise<MemberSummary[]> {
  const qs = buildQueryString(params);
  return apiRequest<MemberSummary[]>(`/members${qs}`);
}

export function getMemberDetail(id: string): Promise<MemberDetail> {
  return apiRequest<MemberDetail>(`/members/${encodeURIComponent(id)}`);
}

export function getMemberProfileView(id: string): Promise<MemberProfileView> {
  return apiRequest<MemberProfileView>(`/members/${encodeURIComponent(id)}/profile`);
}

export function createMember(payload: CreateMemberPayload): Promise<MemberDetail> {
  return apiRequest<MemberDetail>("/members", { method: "POST", body: payload });
}

export function assignSkillToMember(memberId: string, skillName: string, assignedBy?: string): Promise<void> {
  return apiRequest<void>(`/members/${encodeURIComponent(memberId)}/skills`, {
    method: "POST",
    body: { skill_name: skillName, assigned_by: assignedBy },
  });
}

export function assignMemoryToMember(memberId: string, memoryId: string, assignedBy?: string): Promise<void> {
  return apiRequest<void>(`/members/${encodeURIComponent(memberId)}/memories`, {
    method: "POST",
    body: { memory_id: memoryId, assigned_by: assignedBy },
  });
}

export function updateMemberPromptTemplate(memberId: string, promptTemplate: string): Promise<{ id: string; status: string }> {
  return apiRequest<{ id: string; status: string }>(`/members/${encodeURIComponent(memberId)}/prompt-template`, {
    method: "PUT",
    body: { prompt_template: promptTemplate },
  });
}

export interface PromptPreviewResponse {
  template: string;
  rendered: string;
  variables_used: string[];
  token_estimate: number;
}

export function getMemberPromptPreview(memberId: string): Promise<PromptPreviewResponse> {
  return apiRequest<PromptPreviewResponse>(`/members/${encodeURIComponent(memberId)}/prompt/preview`);
}

// ─── Department types ────────────────────────────────────────────────────────

export interface DepartmentSummary {
  id: string;
  name: string;
  leader_member_id: string | null;
  created_at: string | null;
}

export interface CreateDepartmentPayload {
  name: string;
  leader_member_id?: string;
  created_by?: string;
}

// ─── Department API ──────────────────────────────────────────────────────────

export function listDepartments(offset = 0, limit = 50): Promise<DepartmentSummary[]> {
  const qs = buildQueryString({ offset, limit });
  return apiRequest<DepartmentSummary[]>(`/departments${qs}`);
}

export function createDepartment(payload: CreateDepartmentPayload): Promise<DepartmentSummary> {
  return apiRequest<DepartmentSummary>("/departments", { method: "POST", body: payload });
}

// ─── Project types ───────────────────────────────────────────────────────────

export interface ProjectSummary {
  id: string;
  name: string;
  department_id: string | null;
  status: string;
  member_count: number;
  created_at: string | null;
}

export interface ProjectDetail {
  id: string;
  name: string;
  description: string | null;
  department_id: string;
  repository_refs: string[];
  harness_config: Record<string, unknown> | null;
  status: string;
  member_ids: string[];
  created_at: string;
  archived_at: string | null;
}

export interface CreateProjectPayload {
  name: string;
  department_id?: string;
  description?: string;
  repository_refs?: string[];
}

// ─── Project API ─────────────────────────────────────────────────────────────

export interface ListProjectsParams {
  department_id?: string;
  status?: string;
  offset?: number;
  limit?: number;
}

export function listProjects(params: ListProjectsParams = {}): Promise<ProjectSummary[]> {
  const qs = buildQueryString(params);
  return apiRequest<ProjectSummary[]>(`/projects${qs}`);
}

export function getProjectDetail(id: string): Promise<ProjectDetail> {
  return apiRequest<ProjectDetail>(`/projects/${encodeURIComponent(id)}`);
}

export function createProject(payload: CreateProjectPayload): Promise<ProjectDetail> {
  return apiRequest<ProjectDetail>("/projects", { method: "POST", body: payload });
}

export function assignMemberToProject(projectId: string, memberId: string, role?: string): Promise<void> {
  return apiRequest<void>(`/projects/${encodeURIComponent(projectId)}/members`, {
    method: "POST",
    body: { member_id: memberId, role },
  });
}

// ─── Runtime Resource types ─────────────────────────────────────────────────

export interface LlmModelSummary {
  id: string;
  name: string;
  provider: string;
  model_id: string;
  endpoint_type: string;
  context_window: number | null;
  max_output_tokens: number | null;
  supports_tools: boolean;
  supports_json: boolean;
  input_cost_per_1m: number | null;
  output_cost_per_1m: number | null;
  capability_tags: string[];
  status: string;
  notes: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export type LlmModelDetail = LlmModelSummary;

export interface CreateLlmModelPayload {
  name: string;
  provider: string;
  model_id: string;
  endpoint_type?: string;
  context_window?: number;
  max_output_tokens?: number;
  supports_tools?: boolean;
  supports_json?: boolean;
  input_cost_per_1m?: number;
  output_cost_per_1m?: number;
  capability_tags?: string[];
  status?: string;
  notes?: string;
}

export interface AgentProfileSummary {
  id: string;
  name: string;
  description: string;
  runtime_kind: string;
  default_llm_model_id: string | null;
  system_prompt: string;
  tool_names: string[];
  memory_policy: Record<string, unknown>;
  safety_policy: Record<string, unknown>;
  status: string;
  created_at: string | null;
  updated_at: string | null;
}

export type AgentProfileDetail = AgentProfileSummary;

export interface CreateAgentProfilePayload {
  name: string;
  description?: string;
  runtime_kind?: string;
  default_llm_model_id?: string;
  system_prompt?: string;
  tool_names?: string[];
  memory_policy?: Record<string, unknown>;
  safety_policy?: Record<string, unknown>;
  status?: string;
}

export interface ListRuntimeResourcesParams {
  status?: string;
  name_filter?: string;
  offset?: number;
  limit?: number;
}

export interface AssignTaskRuntimePayload {
  llm_model_id?: string | null;
  agent_profile_id?: string | null;
}

export interface AssignTaskRuntimeResponse {
  id: string;
  assigned_llm_model_id: string | null;
  assigned_agent_profile_id: string | null;
  status: string;
}

// ─── Runtime Resource API ───────────────────────────────────────────────────

export function listLlmModels(params: ListRuntimeResourcesParams = {}): Promise<LlmModelSummary[]> {
  const qs = buildQueryString(params);
  return apiRequest<LlmModelSummary[]>(`/llm-models${qs}`);
}

export function getLlmModelDetail(id: string): Promise<LlmModelDetail> {
  return apiRequest<LlmModelDetail>(`/llm-models/${encodeURIComponent(id)}`);
}

export function createLlmModel(payload: CreateLlmModelPayload): Promise<LlmModelDetail> {
  return apiRequest<LlmModelDetail>("/llm-models", { method: "POST", body: payload });
}

export function listAgentProfiles(params: ListRuntimeResourcesParams = {}): Promise<AgentProfileSummary[]> {
  const qs = buildQueryString(params);
  return apiRequest<AgentProfileSummary[]>(`/agent-profiles${qs}`);
}

export function getAgentProfileDetail(id: string): Promise<AgentProfileDetail> {
  return apiRequest<AgentProfileDetail>(`/agent-profiles/${encodeURIComponent(id)}`);
}

export function createAgentProfile(payload: CreateAgentProfilePayload): Promise<AgentProfileDetail> {
  return apiRequest<AgentProfileDetail>("/agent-profiles", { method: "POST", body: payload });
}

// ─── Job types ──────────────────────────────────────────────────────────────

export interface Job {
  job_id: string;
  task_id: string;
  member_id: string | null;
  llm_model_id: string | null;
  rendered_prompt: string | null;
  context_snapshot: Record<string, unknown>;
  phase: string;
  phase_entered_at: string | null;
  error: string | null;
  result_report: Record<string, unknown>;
  cost: Record<string, unknown>;
  state: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string | null;
}

export interface JobSummary {
  job_id: string;
  task_id: string;
  member_id: string | null;
  llm_model_id: string | null;
  phase: string;
  state: string;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string | null;
}

export interface CreateJobPayload {
  task_id: string;
  member_id?: string | null;
  llm_model_id?: string | null;
}

// ─── Job API ───────────────────────────────────────────────────────────────

export function createJob(payload: CreateJobPayload): Promise<JobSummary> {
  return apiRequest<JobSummary>("/jobs", { method: "POST", body: payload });
}

export function listJobs(taskId?: string): Promise<JobSummary[]> {
  const qs = taskId ? `?task_id=${encodeURIComponent(taskId)}` : "";
  return apiRequest<JobSummary[]>(`/jobs${qs}`);
}

export function getJobDetail(jobId: string): Promise<Job> {
  return apiRequest<Job>(`/jobs/${encodeURIComponent(jobId)}`);
}

// ─── Governance types ────────────────────────────────────────────────────────

export interface ReviewCaseSummary {
  id: string;
  target_kind: string;
  target_id: string;
  reviewer_member_id: string;
  status?: string;
  verdict: string | null;
  reason: string | null;
  correction?: string | null;
  decision_at: string | null;
  created_at: string | null;
}

export interface CreateReviewPayload {
  target_kind: string;
  target_id: string;
  reviewer_member_id: string;
}

export interface CreateReviewResponse {
  id: string;
  status: string;
}

export interface DecideReviewPayload {
  verdict: string;
  reason?: string;
  correction?: string;
}

export interface ConflictCaseSummary {
  id: string;
  memory_a_id: string;
  memory_b_id: string;
  conflict_kind: string;
  detected_by: string;
  status?: string;
  resolution: string | null;
  winner_id: string | null;
  resolved_by: string | null;
  created_at?: string | null;
  detected_at?: string | null;
  resolved_at?: string | null;
}

export interface ReportConflictPayload {
  memory_a_id: string;
  memory_b_id: string;
  conflict_kind: string;
  detected_by: string;
}

export interface ResolveConflictPayload {
  resolution: string;
  winner_id?: string;
  resolved_by?: string;
}

// ─── Governance API ──────────────────────────────────────────────────────────

export function listPendingReviews(): Promise<ReviewCaseSummary[]> {
  return apiRequest<ReviewCaseSummary[]>("/reviews/pending");
}

export function getReviewsByTarget(targetKind: string, targetId: string): Promise<ReviewCaseSummary[]> {
  return apiRequest<ReviewCaseSummary[]>(
    `/reviews/by-target/${encodeURIComponent(targetKind)}/${encodeURIComponent(targetId)}`,
  );
}

export function createReview(payload: CreateReviewPayload): Promise<CreateReviewResponse> {
  return apiRequest<CreateReviewResponse>("/reviews", { method: "POST", body: payload });
}

export function decideReview(id: string, payload: DecideReviewPayload): Promise<ReviewCaseSummary> {
  return apiRequest<ReviewCaseSummary>(`/reviews/${encodeURIComponent(id)}/decide`, {
    method: "POST",
    body: payload,
  });
}

export function listUnresolvedConflicts(): Promise<ConflictCaseSummary[]> {
  return apiRequest<ConflictCaseSummary[]>("/conflicts/unresolved");
}

export function reportConflict(payload: ReportConflictPayload): Promise<ConflictCaseSummary> {
  return apiRequest<ConflictCaseSummary>("/conflicts", { method: "POST", body: payload });
}

export function resolveConflict(id: string, payload: ResolveConflictPayload): Promise<ConflictCaseSummary> {
  return apiRequest<ConflictCaseSummary>(`/conflicts/${encodeURIComponent(id)}/resolve`, {
    method: "POST",
    body: payload,
  });
}

// ─── Metrics types ───────────────────────────────────────────────────────────

export interface ValueMetricsResponse {
  memory_total: number;
  memory_active: number;
  memory_candidates: number;
  memory_deprecated: number;
  skill_count: number;
  member_count: number;
  task_count: number;
  recall_count: number;
  memory_active_rate: number;
}

export interface SystemHealthResponse {
  database: string;
  memory_total: number;
  conflicts_open: number;
  reviews_pending: number;
  task_first_pass_rate: number;
  status: string;
}

export interface MemoryHealthResponse {
  active: number;
  candidate: number;
  deprecated: number;
  needs_verify: number;
  total: number;
  candidate_ratio: number;
  deprecated_ratio: number;
  needs_verify_ratio: number;
}

// ─── Metrics API ─────────────────────────────────────────────────────────────

export function fetchValueMetrics(period = "monthly"): Promise<ValueMetricsResponse> {
  const qs = buildQueryString({ period });
  return apiRequest<ValueMetricsResponse>(`/metrics/value${qs}`);
}

export function fetchSystemHealth(): Promise<SystemHealthResponse> {
  return apiRequest<SystemHealthResponse>("/metrics/system-health");
}

// ─── Memory Proposals & Health API ───────────────────────────────────────────

export function listPendingProposals(offset = 0, limit = 50): Promise<MemorySummary[]> {
  const qs = buildQueryString({ offset, limit });
  return apiRequest<MemorySummary[]>(`/memories/proposals/pending${qs}`);
}

export function fetchMemoryHealth(): Promise<MemoryHealthResponse> {
  return apiRequest<MemoryHealthResponse>("/memories/health");
}

// ─── Task types ──────────────────────────────────────────────────────────────

export interface TaskSummary {
  id: string;
  title: string;
  state: string;
  priority: string;
  department_id: string | null;
  retry_count: number;
  review_round: number;
  created_at: string | null;
}

export interface TaskDetail {
  id: string;
  title: string;
  description: string;
  state: string;
  priority: string;
  department_id: string;
  project_ids: string[];
  parent_task_id: string | null;
  declared_skills: string[];
  deliverable_kind: string;
  acceptance_criteria: string[];
  max_retry_count: number;
  max_review_rounds: number;
  retry_count: number;
  review_round: number;
  runs: TaskRun[];
  created_at: string;
}

export interface TaskRun {
  id: string;
  state: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface CreateTaskPayload {
  department_id: string;
  title: string;
  description?: string;
  priority?: string;
  project_ids?: string[];
  parent_task_id?: string;
  declared_skills?: string[];
  deliverable_kind?: string;
  acceptance_criteria?: string[];
  max_retry_count?: number;
  max_review_rounds?: number;
}

// ─── Task API ────────────────────────────────────────────────────────────────

export interface ListTasksParams {
  department_id?: string;
  state?: string;
  offset?: number;
  limit?: number;
}

export function listTasks(params: ListTasksParams = {}): Promise<TaskSummary[]> {
  const qs = buildQueryString(params);
  return apiRequest<TaskSummary[]>(`/tasks${qs}`);
}

export function getTaskDetail(id: string): Promise<TaskDetail> {
  return apiRequest<TaskDetail>(`/tasks/${encodeURIComponent(id)}`);
}

export function createTask(payload: CreateTaskPayload): Promise<{ id: string; state: string }> {
  return apiRequest<{ id: string; state: string }>("/tasks", { method: "POST", body: payload });
}

export interface UpdateTaskPayload {
  title?: string;
  description?: string;
  priority?: string;
  deliverable_kind?: string;
  max_retry_count?: number;
  max_review_rounds?: number;
}

export function updateTask(taskId: string, payload: UpdateTaskPayload): Promise<{ id: string; status: string }> {
  return apiRequest<{ id: string; status: string }>(`/tasks/${encodeURIComponent(taskId)}`, { method: "PUT", body: payload });
}

export function assignTask(taskId: string, memberId: string): Promise<{ id: string; state: string }> {
  return apiRequest<{ id: string; state: string }>(`/tasks/${encodeURIComponent(taskId)}/assign`, {
    method: "POST",
    body: { member_id: memberId },
  });
}

export function startTaskRun(taskId: string, memberId?: string): Promise<{ id: string; state: string }> {
  return apiRequest<{ id: string; state: string }>(`/tasks/${encodeURIComponent(taskId)}/start`, {
    method: "POST",
    body: { member_id: memberId },
  });
}

export function cancelTask(taskId: string): Promise<{ id: string; state: string }> {
  return apiRequest<{ id: string; state: string }>(`/tasks/${encodeURIComponent(taskId)}/cancel`, {
    method: "POST",
  });
}

export function requeueTask(taskId: string): Promise<{ id: string; state: string }> {
  return apiRequest<{ id: string; state: string }>(`/tasks/${encodeURIComponent(taskId)}/requeue`, {
    method: "POST",
  });
}

// ─── Delete API ──────────────────────────────────────────────────────────────

export function deleteMemory(id: string): Promise<void> {
  return apiRequest<void>(`/memories/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function deleteSkill(id: string): Promise<void> {
  return apiRequest<void>(`/skills/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function deleteMember(id: string): Promise<void> {
  return apiRequest<void>(`/members/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function deleteDepartment(id: string): Promise<void> {
  return apiRequest<void>(`/departments/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function deleteProject(id: string): Promise<void> {
  return apiRequest<void>(`/projects/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function deleteTask(id: string): Promise<void> {
  return apiRequest<void>(`/tasks/${encodeURIComponent(id)}`, { method: "DELETE" });
}

// ─── Utilities ───────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function buildQueryString(params: Record<string, any>): string {
  const entries: string[] = [];
  for (const [key, val] of Object.entries(params)) {
    if (val !== undefined && val !== null && val !== "") {
      entries.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(val))}`);
    }
  }
  return entries.length > 0 ? `?${entries.join("&")}` : "";
}
