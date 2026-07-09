import { apiRequest } from "./client";

export interface TicketReport {
  id: string;
  reporter_employee_id: string;
  reporter_role: string;
  content: string;
  evidence: string[];
  report_type: string;
  created_at: string;
  source_event_id?: string;
}

export interface TicketEvent {
  event_id: string;
  ticket_id: string;
  type: string;
  at: string;
  actor: Record<string, string>;
  data: Record<string, unknown>;
}

export interface ProviderTicketRef {
  provider: string;
  provider_record_id: string;
  provider_project_id: string;
  provider_url: string;
  synced_at: string;
}

export interface Ticket {
  id: string;
  title: string;
  description: string;
  status: string;
  ticket_type?: string;
  assigned_employee_id: string;
  assigned_role: string;
  validation_employee_id: string;
  validation_role: string;
  knowledge_refs: string[];
  code_repository_ids: string[];
  source_thread_id: string;
  source_run_id: string;
  reports: TicketReport[];
  events?: TicketEvent[];
  provider_ref?: ProviderTicketRef | null;
  external_url?: string;
  provider_metadata?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  saved_path: string;
}

export interface TicketWorkItem {
  ticket_id: string;
  title: string;
  status: string;
  role: string;
  updated_at: string;
  next_action: string;
}

export interface EmployeeTicketReportRecord {
  ticket_id: string;
  ticket_title: string;
  report_id: string;
  report_type: string;
  content: string;
  evidence: string[];
  created_at: string;
}

export interface EmployeeAssetWorkRecord {
  asset_id: string;
  candidate_id: string;
  asset_type: string;
  title: string;
  status: string;
  review_state: string;
  scope_kind: string;
  scope_ref: string;
  source_ticket_id: string;
  source_run_id: string;
  source_ref: string;
  application_status: string;
  application_report_id: string;
  application_employee_id: string;
  created_at: string;
  updated_at: string;
}

export interface EmployeeAssetReviewRecord {
  review_id: string;
  candidate_id: string;
  asset_id: string;
  status: string;
  reviewer_employee_id: string;
  reason: string;
  relation_to_employee: string;
  created_at: string;
  updated_at: string;
}

export interface EmployeeRuntimeRunRecord {
  request_id: string;
  run_id: string;
  session_key: string;
  ticket_id: string;
  action: string;
  executor_id: string;
  status: string;
  trace_ref: string;
  artifact_count: number;
  evidence_count: number;
  tool_event_count: number;
  memory_candidate_count: number;
  latency_ms: number;
  total_cost: number;
  started_at: string;
  finished_at: string;
}

export interface EmployeeQualityFeedbackRecord {
  id: string;
  kind: string;
  status: string;
  summary: string;
  source_ref: string;
  reviewer_employee_id: string;
  ticket_id: string;
  created_at: string;
}

export interface EmployeeWorkLedger {
  employee_id: string;
  current_tickets: TicketWorkItem[];
  historical_tickets: TicketWorkItem[];
  reports: EmployeeTicketReportRecord[];
  validations: EmployeeTicketReportRecord[];
  blocked_records: EmployeeTicketReportRecord[];
  handoffs: Record<string, unknown>[];
  asset_candidates: EmployeeAssetWorkRecord[];
  approved_assets: EmployeeAssetWorkRecord[];
  asset_reviews: EmployeeAssetReviewRecord[];
  runtime_runs: EmployeeRuntimeRunRecord[];
  quality_feedback: EmployeeQualityFeedbackRecord[];
  contribution: Record<string, number>;
}

export interface TicketAssetRecord {
  id: string;
  kind: string;
  title: string;
  status: string;
  source_ticket_id: string;
  source_employee_id: string;
  assigned_employees: string[];
  scopes: string[];
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
}

export interface TicketGraphNode {
  id: string;
  kind: string;
  label: string;
  status: string;
  ref: string;
  metadata: Record<string, unknown>;
}

export interface TicketGraphEdge {
  id: string;
  type: string;
  source_id: string;
  target_id: string;
  label: string;
  evidence_refs: string[];
  metadata: Record<string, unknown>;
}

export interface TicketGraphProjection {
  ticket_id: string;
  nodes: TicketGraphNode[];
  edges: TicketGraphEdge[];
  grouped_edges: Record<string, TicketGraphEdge[]>;
  source_counts: Record<string, number>;
}

export interface TicketEmployeeContribution {
  employee_id: string;
  role: string;
  assigned: boolean;
  validator: boolean;
  reporter: boolean;
  event_actor: boolean;
  asset_source: boolean;
  asset_assigned: boolean;
  report_count: number;
  validation_report_count: number;
  blocked_report_count: number;
  evidence_count: number;
  event_count: number;
  candidate_count: number;
  recalled_asset_count: number;
  linked_asset_count: number;
}

export interface TicketPerformance {
  ticket_id: string;
  status: string;
  contribution: TicketEmployeeContribution[];
  quality_signals: Record<string, boolean | number | string>;
  source_counts: Record<string, number>;
}

export interface TicketRuntimeProviderEvidence {
  mode: string;
  status: string;
  provider: string;
  provider_ref_recorded: boolean;
  provider_record_id: string;
  provider_project_id: string;
  provider_url: string;
  external_url: string;
  synced_at: string;
  detail: string;
  setup_required: string[];
}

export interface TicketRuntimeLoopRunEvidence {
  run_id: string;
  status: string;
  stop_reason: string;
  active: boolean;
  session_key: string;
  step_count: number;
  queued_at: string;
  started_at: string;
  finished_at: string;
  updated_at: string;
  saved_path: string;
}

export interface TicketRuntimeEvidenceIssue {
  reason: string;
  detail: string;
  scope?: string;
  status?: string;
  setup_required?: string[];
  [key: string]: unknown;
}

export interface TicketRuntimeEvidence {
  ticket_id: string;
  status: string;
  source_counts: Record<string, number>;
  provider_state: TicketRuntimeProviderEvidence;
  governance_state: Record<string, unknown>;
  latest_loop_run: TicketRuntimeLoopRunEvidence | null;
  blockers: TicketRuntimeEvidenceIssue[];
  gaps: TicketRuntimeEvidenceIssue[];
  links: Record<string, string>;
}

export interface TicketEvidenceRequirement {
  id: string;
  label: string;
  required: boolean;
  satisfied: boolean;
  evidence_refs: string[];
  recommended_commands: string[];
  detail: string;
}

export interface TicketEvidenceRequirements {
  ticket_id: string;
  ticket_type: string;
  profile: string;
  satisfied: boolean;
  missing_required: string[];
  evidence_refs: string[];
  requirements: TicketEvidenceRequirement[];
}

export interface SelfBootstrapTicketLearningRecord {
  ticket_id: string;
  title: string;
  status: string;
  assigned_employee_id: string;
  validation_employee_id: string;
  evidence_count: number;
  missing_required_evidence: number;
  validation_passed: boolean;
  blocked_or_failed: boolean;
  memory_candidates: number;
  approved_memory_candidates: number;
  approved_memories_recalled: number;
  graphiti_memories_recalled: number;
  useful_memory_recalls: number;
  provider_ref_recorded: boolean;
  next_learning_action: string;
}

export interface SelfBootstrapLearningSummary {
  ticket_count: number;
  validated_ticket_count: number;
  blocked_ticket_count: number;
  tickets_with_evidence: number;
  tickets_missing_required_evidence: number;
  memory_candidates_produced: number;
  approved_memory_candidates: number;
  approved_memories_recalled: number;
  graphiti_memories_recalled: number;
  useful_memory_recalls: number;
  stale_or_superseded_assets: number;
  summary: string;
  learning_delta: Record<string, number | string | boolean>;
  tickets: SelfBootstrapTicketLearningRecord[];
  source_counts: Record<string, number>;
}

export interface TicketBackendMode {
  id: string;
  label: string;
  status: string;
  description: string;
}

export interface TicketBackendSettings {
  mode: string;
  local_file_path: string;
  plane_api_base_url: string;
  plane_web_base_url: string;
  plane_workspace_slug: string;
  plane_project_id: string;
  plane_api_key_env: string;
  plane_namespace_strategy: string;
  plane_namespace_label_ids: Record<string, string>;
  plane_state_ids: Record<string, string>;
  plane_employee_assignee_ids: Record<string, string>;
  saved_paths: Record<string, string>;
  supported_modes: TicketBackendMode[];
}

export interface TicketBackendSettingsUpdateRequest {
  mode: string;
  local_file_path: string;
  plane_api_base_url: string;
  plane_web_base_url: string;
  plane_workspace_slug: string;
  plane_project_id: string;
  plane_api_key_env: string;
  plane_namespace_strategy: string;
  plane_namespace_label_ids: Record<string, string>;
  plane_state_ids: Record<string, string>;
  plane_employee_assignee_ids: Record<string, string>;
}

export interface TicketBackendStatus {
  mode: string;
  status: string;
  detail: string;
  ticket_count: number;
  local_file_path: string;
  provider: string;
  provider_ref_count: number;
  setup_required: string[];
  plane_setup?: Record<string, unknown>;
  release_target?: Record<string, unknown>;
  capabilities: string[];
  mapping: Record<string, string>;
  saved_paths: Record<string, string>;
  supported_modes: TicketBackendMode[];
}

export interface TicketBackendPlaneScopeDiscovery {
  status: string;
  detail: string;
  api_key_env: string;
  api_key_configured: boolean;
  external_calls: boolean;
  checks: string[];
  setup_required: string[];
  suggestions: Array<Record<string, unknown>>;
  evidence: Record<string, unknown>;
}

export interface TicketCloseoutAssetCandidate {
  id: string;
  source_candidate_id: string;
  asset_id: string;
  asset_type: string;
  title: string;
  content: string;
  content_ref: string;
  status: string;
  scope_kind: string;
  scope_ref: string;
  owner_employee_id: string;
  source_kind: string;
  source_ref: string;
  provenance: Record<string, unknown>;
  provider: string;
  provider_ref: string;
  relationships: Record<string, unknown>[];
  review_state: string;
  usefulness_stats: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface TicketCloseoutAssetCandidateResponse {
  ticket_id: string;
  status: string;
  detail: string;
  candidates: TicketCloseoutAssetCandidate[];
  report_id: string;
  saved_paths: Record<string, string>;
}

export interface TicketCloseoutSettlementReview {
  status: string;
  requested_count: number;
  reviewed_count: number;
  failed_count: number;
  results: Record<string, unknown>[];
  saved_paths: Record<string, string>;
}

export interface TicketCloseoutSettlementProjection {
  asset_id: string;
  status: string;
  projection: Record<string, unknown> | null;
  relationship_projection: Record<string, unknown> | null;
  error: string;
}

export interface TicketCloseoutSettlementResponse {
  ticket_id: string;
  status: string;
  detail: string;
  proposal: TicketCloseoutAssetCandidateResponse;
  review: TicketCloseoutSettlementReview | null;
  candidates: TicketCloseoutAssetCandidate[];
  asset_ids: string[];
  projections: TicketCloseoutSettlementProjection[];
  report_id: string;
  saved_paths: Record<string, string>;
}

export interface TicketFailureRetrospectiveAssetCandidateResponse {
  ticket_id: string;
  status: string;
  detail: string;
  candidates: TicketCloseoutAssetCandidate[];
  report_id: string;
  failed_item_count: number;
  saved_paths: Record<string, string>;
}

export interface TicketLoopStepResponse {
  ticket_id: string;
  status: string;
  stop_reason: string;
  request: Record<string, unknown>;
  result: Record<string, unknown>;
  ingested: boolean;
  ingestion_blocker: string;
  loop_state: Record<string, unknown>;
}

export interface TicketLoopRunResponse {
  ticket_id: string;
  status: string;
  stop_reason: string;
  steps: TicketLoopStepResponse[];
  loop_state: Record<string, unknown>;
}

export interface TicketLoopRunRecord {
  run_id: string;
  ticket_id: string;
  status: string;
  stop_reason: string;
  active: boolean;
  session_key: string;
  request: Record<string, unknown>;
  response: Record<string, unknown>;
  step_count: number;
  policy: Record<string, unknown>;
  control: Record<string, unknown>;
  queued_at: string;
  started_at: string;
  finished_at: string;
  updated_at: string;
  saved_path: string;
}

export interface TicketLoopControlState {
  control_id: string;
  ticket_id: string;
  action: string;
  status: string;
  active: boolean;
  actor_employee_id: string;
  actor_role: string;
  reason: string;
  session_key: string;
  updated_session_count: number;
  updated_at: string;
  saved_path: string;
}

export interface TicketLoopControlResponse {
  ticket_id: string;
  state: TicketLoopControlState;
  report_id: string;
  updated_sessions: Record<string, unknown>[];
  saved_paths: Record<string, string>;
}

export interface TicketLoopTimelineRef {
  kind: string;
  ref: string;
  target_route: string;
}

export interface TicketLoopTimelineItem {
  timeline_id: string;
  ticket_id: string;
  kind: string;
  status: string;
  title: string;
  detail: string;
  at: string;
  actor_employee_id: string;
  actor_role: string;
  source_kind: string;
  source_ref: string;
  target_route: string;
  refs: TicketLoopTimelineRef[];
  data: Record<string, unknown>;
}

export interface TicketLoopRetryRequirement {
  id: string;
  label: string;
  satisfied: boolean;
  detail: string;
  target_route: string;
}

export interface TicketLoopApprovalResumeState {
  approval_id: string;
  executor_id: string;
  status: string;
  required_capability: string;
  ready_to_run: boolean;
  needs_review: boolean;
  blocked: boolean;
  reviewed_at: string;
  last_run_request_id: string;
  last_run_status: string;
  last_ingestion_blocker: string;
  attempt_count: number;
  target_route: string;
  detail: string;
}

export interface TicketLoopQueueReliability {
  ticket_id: string;
  status: string;
  detail: string;
  queued_count: number;
  duplicate_queued_count: number;
  running_count: number;
  stale_running_count: number;
  stale_running_after_seconds: number;
  completed_count: number;
  failed_count: number;
  active_count: number;
  total_count: number;
  latest_activity_at: string;
  worker_status: string;
  worker_running: boolean;
  worker_last_error: string;
}

export interface TicketLoopTimelineSummary {
  ticket_id: string;
  status: string;
  waiting_reason: string;
  next_action: string;
  can_run: boolean;
  can_resume: boolean;
  can_retry: boolean;
  latest_at: string;
  counts: Record<string, number>;
  provider_blockers: Record<string, unknown>[];
  retry_requirements: TicketLoopRetryRequirement[];
  approval_resume: TicketLoopApprovalResumeState[];
  queue_reliability: TicketLoopQueueReliability | null;
}

export interface TicketLoopTimelineResponse {
  ticket_id: string;
  summary: TicketLoopTimelineSummary;
  items: TicketLoopTimelineItem[];
  saved_paths: Record<string, string>;
}

export interface TicketLoopResumeResponse {
  ticket_id: string;
  status: string;
  previous_status: string;
  detail: string;
  queue_item: TicketLoopQueueItem;
  saved_paths: Record<string, string>;
}

export interface TicketLoopQueueStatus {
  status: string;
  queued_count: number;
  running_count: number;
  completed_count: number;
  failed_count: number;
  active_count: number;
  total_count: number;
  oldest_queued_at: string;
  latest_activity_at: string;
  next_queue_id: string;
  next_ticket_id: string;
  next_run_id: string;
  saved_paths: Record<string, string>;
}

export interface TicketLoopQueuePumpResponse {
  status: string;
  processed: Record<string, unknown>[];
  policy_actions: TicketLoopPolicyAction[];
  remaining_queued: number;
  saved_paths: Record<string, string>;
}

export interface TicketLoopPolicyAction {
  kind: string;
  ticket_id: string;
  status: string;
  detail: string;
  candidate_ids: string[];
  queue_ids: string[];
  run_ids: string[];
  handoff_refs: Record<string, string>[];
  report_id: string;
}

export interface TicketLoopQueueItem {
  queue_id: string;
  run_id: string;
  ticket_id: string;
  status: string;
  priority: number;
  request: Record<string, unknown>;
  response: Record<string, unknown>;
  error: string;
  actor_employee_id: string;
  actor_role: string;
  reason: string;
  report_id: string;
  enqueued_at: string;
  started_at: string;
  finished_at: string;
  updated_at: string;
  saved_path: string;
}

export interface TicketLoopQueueWorkerStatus {
  worker_id: string;
  status: string;
  running: boolean;
  interval_seconds: number;
  max_items: number;
  started_at: string;
  stopped_at: string;
  last_tick_at: string;
  last_tick_status: string;
  last_error: string;
  total_ticks: number;
  total_processed: number;
  total_policy_actions: number;
  recent_policy_actions: TicketLoopPolicyAction[];
  last_control_reason: string;
  saved_path: string;
}

export interface TicketLoopQueueWorkerTickResponse {
  status: TicketLoopQueueWorkerStatus;
  pump: TicketLoopQueuePumpResponse;
}

export function listTickets(): Promise<Ticket[]> {
  return apiRequest<Ticket[]>("/tickets");
}

export function listTicketEvents(ticketId: string): Promise<TicketEvent[]> {
  return apiRequest<TicketEvent[]>(`/tickets/${encodeURIComponent(ticketId)}/events`);
}

export function getEmployeeWorkLedger(employeeId: string): Promise<EmployeeWorkLedger> {
  return apiRequest<EmployeeWorkLedger>(`/tickets/employees/${encodeURIComponent(employeeId)}/work`);
}

export function listTicketAssets(): Promise<TicketAssetRecord[]> {
  return apiRequest<TicketAssetRecord[]>("/tickets/assets");
}

export function getTicketGraph(ticketId: string): Promise<TicketGraphProjection> {
  return apiRequest<TicketGraphProjection>(`/tickets/${encodeURIComponent(ticketId)}/graph`);
}

export function getTicketPerformance(ticketId: string): Promise<TicketPerformance> {
  return apiRequest<TicketPerformance>(`/tickets/${encodeURIComponent(ticketId)}/performance`);
}

export function getTicketRuntimeEvidence(ticketId: string): Promise<TicketRuntimeEvidence> {
  return apiRequest<TicketRuntimeEvidence>(`/tickets/${encodeURIComponent(ticketId)}/runtime-evidence`);
}

export function getTicketEvidenceRequirements(ticketId: string): Promise<TicketEvidenceRequirements> {
  return apiRequest<TicketEvidenceRequirements>(`/tickets/${encodeURIComponent(ticketId)}/evidence-requirements`);
}

export function getSelfBootstrapSummary(): Promise<SelfBootstrapLearningSummary> {
  return apiRequest<SelfBootstrapLearningSummary>("/tickets/self-bootstrap/summary");
}

export function proposeTicketCloseoutCandidates(
  ticketId: string,
  body: { actor_employee_id?: string; actor_role?: string; reason?: string } = {},
): Promise<TicketCloseoutAssetCandidateResponse> {
  return apiRequest<TicketCloseoutAssetCandidateResponse>(`/tickets/${encodeURIComponent(ticketId)}/closeout-candidates`, {
    method: "POST",
    body,
  });
}

export function settleTicketCloseout(
  ticketId: string,
  body: {
    actor_employee_id?: string;
    actor_role?: string;
    reviewer_employee_id?: string;
    reason?: string;
    approve_candidates?: boolean;
    project_graphiti?: boolean;
    project_relationships?: boolean;
    asset_types?: string[];
  } = {},
): Promise<TicketCloseoutSettlementResponse> {
  return apiRequest<TicketCloseoutSettlementResponse>(`/tickets/${encodeURIComponent(ticketId)}/closeout-settlement`, {
    method: "POST",
    body,
  });
}

export function proposeTicketFailureRetrospectiveCandidates(
  ticketId: string,
  body: { actor_employee_id?: string; actor_role?: string; reason?: string; min_failed_items?: number } = {},
): Promise<TicketFailureRetrospectiveAssetCandidateResponse> {
  return apiRequest<TicketFailureRetrospectiveAssetCandidateResponse>(`/tickets/${encodeURIComponent(ticketId)}/failure-retrospective-candidates`, {
    method: "POST",
    body,
  });
}

export function runTicketLoop(
  ticketId: string,
  body: { employee_id?: string; message?: string; max_steps?: number; selected_executor?: string; selected_ai_engine?: string } = {},
): Promise<TicketLoopRunResponse> {
  return apiRequest<TicketLoopRunResponse>(`/tickets/${encodeURIComponent(ticketId)}/loop/run`, {
    method: "POST",
    body,
  });
}

export function listTicketLoopRuns(ticketId: string): Promise<TicketLoopRunRecord[]> {
  return apiRequest<TicketLoopRunRecord[]>(`/tickets/${encodeURIComponent(ticketId)}/loop/runs`);
}

export function getTicketLoopRun(ticketId: string, runId: string): Promise<TicketLoopRunRecord> {
  return apiRequest<TicketLoopRunRecord>(`/tickets/${encodeURIComponent(ticketId)}/loop/runs/${encodeURIComponent(runId)}`);
}

export function getTicketLoopTimeline(ticketId: string): Promise<TicketLoopTimelineResponse> {
  return apiRequest<TicketLoopTimelineResponse>(`/tickets/${encodeURIComponent(ticketId)}/loop/timeline`);
}

export function resumeTicketLoop(
  ticketId: string,
  body: {
    action?: "resume" | "retry_after_changes" | "retry_after_evidence";
    employee_id?: string;
    message?: string;
    max_steps?: number;
    selected_executor?: string;
    selected_ai_engine?: string;
    reason?: string;
  } = {},
): Promise<TicketLoopResumeResponse> {
  return apiRequest<TicketLoopResumeResponse>(`/tickets/${encodeURIComponent(ticketId)}/loop/resume`, {
    method: "POST",
    body,
  });
}

export function getTicketLoopQueueStatus(): Promise<TicketLoopQueueStatus> {
  return apiRequest<TicketLoopQueueStatus>("/tickets/loop/queue/status");
}

export function listTicketLoopQueue(status = ""): Promise<TicketLoopQueueItem[]> {
  const suffix = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiRequest<TicketLoopQueueItem[]>(`/tickets/loop/queue${suffix}`);
}

export function pumpTicketLoopQueue(body: { max_items?: number } = {}): Promise<TicketLoopQueuePumpResponse> {
  return apiRequest<TicketLoopQueuePumpResponse>("/tickets/loop/queue/pump", {
    method: "POST",
    body,
  });
}

export function getTicketLoopQueueWorkerStatus(): Promise<TicketLoopQueueWorkerStatus> {
  return apiRequest<TicketLoopQueueWorkerStatus>("/tickets/loop/queue/worker/status");
}

export function startTicketLoopQueueWorker(
  body: { interval_seconds?: number; max_items?: number; reason?: string } = {},
): Promise<TicketLoopQueueWorkerStatus> {
  return apiRequest<TicketLoopQueueWorkerStatus>("/tickets/loop/queue/worker/start", {
    method: "POST",
    body,
  });
}

export function stopTicketLoopQueueWorker(): Promise<TicketLoopQueueWorkerStatus> {
  return apiRequest<TicketLoopQueueWorkerStatus>("/tickets/loop/queue/worker/stop", {
    method: "POST",
  });
}

export function tickTicketLoopQueueWorker(
  body: { interval_seconds?: number; max_items?: number; reason?: string } = {},
): Promise<TicketLoopQueueWorkerTickResponse> {
  return apiRequest<TicketLoopQueueWorkerTickResponse>("/tickets/loop/queue/worker/tick", {
    method: "POST",
    body,
  });
}

export function controlTicketLoop(
  ticketId: string,
  body: { action: "stop" | "pause" | "continue" | "cancel"; actor_employee_id?: string; actor_role?: string; reason?: string; session_key?: string },
): Promise<TicketLoopControlResponse> {
  return apiRequest<TicketLoopControlResponse>(`/tickets/${encodeURIComponent(ticketId)}/loop/control`, {
    method: "POST",
    body,
  });
}

export function getTicketBackendSettings(): Promise<TicketBackendSettings> {
  return apiRequest<TicketBackendSettings>("/tickets/backend");
}

export function updateTicketBackendSettings(
  payload: TicketBackendSettingsUpdateRequest,
): Promise<TicketBackendSettings> {
  return apiRequest<TicketBackendSettings>("/tickets/backend", {
    method: "PUT",
    body: payload,
  });
}

export function getTicketBackendStatus(): Promise<TicketBackendStatus> {
  return apiRequest<TicketBackendStatus>("/tickets/status");
}

export function discoverTicketBackendPlaneScope(): Promise<TicketBackendPlaneScopeDiscovery> {
  return apiRequest<TicketBackendPlaneScopeDiscovery>("/tickets/backend/plane-scope/discovery");
}
