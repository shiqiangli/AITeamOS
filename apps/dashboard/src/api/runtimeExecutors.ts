import { apiRequest } from "./client";

export interface RuntimeApprovalRecord {
  id: string;
  status: string;
  kind: string;
  ticket_id: string;
  employee_id: string;
  executor_id: string;
  required_capability: string;
  risk_level: string;
  reason: string;
  proposed_action: Record<string, unknown>;
  source_state_ref: string;
  source_state_snapshot_ref: string;
  current_graph_node: string;
  checkpoint_ref: string;
  executor_session_ref: string;
  approval_request: Record<string, unknown>;
  source_request: Record<string, unknown>;
  source_result: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  reviewed_at: string;
  reviewer_employee_id: string;
  review_reason: string;
  last_run_request_id: string;
  last_run_status: string;
  last_ingestion_blocker: string;
  last_result: Record<string, unknown>;
  resume_result: Record<string, unknown>;
  run_history: Array<Record<string, unknown>>;
}

export interface RuntimeApprovalRunResponse {
  approval: RuntimeApprovalRecord | Record<string, unknown>;
  request: Record<string, unknown>;
  result: Record<string, unknown>;
  ingested: boolean;
  ingestion_blocker: string;
}

export type RuntimeApprovalReviewStatus = "approved" | "rejected" | "changes_requested" | "evidence_requested";

export interface RuntimeExecutionSessionRecord {
  session_key: string;
  employee_id: string;
  thread_id: string;
  ticket_id: string;
  executor_id: string;
  executor_session_ref: string;
  checkpoint_ref: string;
  last_request_id: string;
  status: string;
  trace_ref: string;
  current_graph_node: string;
  source_state_ref: string;
  tool_event_count: number;
  tool_events: Array<Record<string, unknown>>;
  ticket_refs: string[];
  memory_refs: string[];
  context_refs: Array<Record<string, unknown>>;
  approval_refs: string[];
  updated_at: string;
}

export interface RuntimeExecutionReplayResponse {
  session: Record<string, unknown>;
  execution_artifacts: Record<string, unknown>;
  approvals: Array<Record<string, unknown>>;
  state_snapshots: Array<Record<string, unknown>>;
  native_checkpoint_history: Array<Record<string, unknown>>;
  state_transitions: Array<Record<string, unknown>>;
  trace_events: Array<Record<string, unknown>>;
  handoff_summary: Record<string, unknown>;
  coverage_summary: Record<string, unknown>;
  timeline: Array<Record<string, unknown>>;
}

export interface RuntimeExecutionTimelineResponse {
  session: Record<string, unknown>;
  timeline: Array<Record<string, unknown>>;
}

export interface RuntimeExecutorSmokeResponse {
  executor_id: string;
  request: Record<string, unknown>;
  result: Record<string, unknown>;
  ingested: boolean;
  ingestion_blocker: string;
}

export interface RuntimeExecutorSmokeBatchResponse {
  status: string;
  results: RuntimeExecutorSmokeResponse[];
  summary: Record<string, unknown>;
  learning_delta: Record<string, unknown>;
  ingestion_blocker: string;
}

export interface RuntimeExecutorDogfoodResponse {
  status: string;
  ticket: Record<string, unknown>;
  smoke_batch: Record<string, unknown>;
  approval: Record<string, unknown>;
  approved_run: Record<string, unknown>;
  summary_report: Record<string, unknown>;
  learning_delta: Record<string, unknown>;
  blockers: Array<Record<string, unknown>>;
}

export interface RuntimeExecutorRegistryItem {
  executor_id: string;
  display_name: string;
  status: string;
  detail: string;
  capabilities: string[];
  setup_required: string[];
  diagnostics: Record<string, unknown>;
  health: Record<string, unknown>;
}

export interface RuntimeExecutorRegistryResponse {
  executors: RuntimeExecutorRegistryItem[];
  summary: Record<string, unknown>;
  blockers: Array<Record<string, unknown>>;
  live_provider_readiness?: Record<string, unknown>;
}

export interface RuntimeExecutorConfigRecord {
  executor_id: string;
  enabled: boolean;
  binary_path: string;
  working_dir: string;
  command_template: string;
  model: string;
  api_base_url: string;
  api_key_env: string;
  http_endpoint_path: string;
  mode: string;
  timeout_seconds: number | null;
  saved_path: string;
}

export interface RuntimeExecutorConfigListResponse {
  executors: Record<string, RuntimeExecutorConfigRecord>;
  saved_paths: Record<string, string>;
}

export function listRuntimeExecutors(): Promise<RuntimeExecutorRegistryResponse> {
  return apiRequest<RuntimeExecutorRegistryResponse>("/runtime-executors");
}

export function listRuntimeExecutorConfigs(): Promise<RuntimeExecutorConfigListResponse> {
  return apiRequest<RuntimeExecutorConfigListResponse>("/runtime-executors/config");
}

export function updateRuntimeExecutorConfig(
  executorId: string,
  payload: Partial<Omit<RuntimeExecutorConfigRecord, "executor_id" | "saved_path">>,
): Promise<RuntimeExecutorConfigRecord> {
  return apiRequest<RuntimeExecutorConfigRecord>(
    `/runtime-executors/${encodeURIComponent(executorId)}/config`,
    { method: "PUT", body: payload },
  );
}

export function runRuntimeExecutorSmoke(
  executorId: string,
  payload: {
    message?: string;
    employee_id?: string;
    workspace_id?: string;
    ticket_id?: string;
    repository_ids?: string[];
    runtime_config?: Record<string, unknown>;
    ingest_result?: boolean;
  } = {},
): Promise<RuntimeExecutorSmokeResponse> {
  return apiRequest<RuntimeExecutorSmokeResponse>(
    `/runtime-executors/${encodeURIComponent(executorId)}/smoke`,
    { method: "POST", body: payload },
  );
}

export function runRuntimeExecutorSmokeBatch(
  payload: {
    message?: string;
    employee_id?: string;
    workspace_id?: string;
    ticket_id?: string;
    executor_ids?: string[];
    repository_ids?: string[];
    runtime_config?: Record<string, unknown>;
    runtime_config_by_executor?: Record<string, Record<string, unknown>>;
    ingest_result?: boolean;
  } = {},
): Promise<RuntimeExecutorSmokeBatchResponse> {
  return apiRequest<RuntimeExecutorSmokeBatchResponse>(
    "/runtime-executors/smoke-batch",
    { method: "POST", body: payload },
  );
}

export function runRuntimeExecutorDogfood(
  payload: {
    executor_id?: string;
    message?: string;
    employee_id?: string;
    reviewer_employee_id?: string;
    workspace_id?: string;
    ticket_id?: string;
    create_ticket_if_missing?: boolean;
    repository_ids?: string[];
    smoke_executor_ids?: string[];
    runtime_config?: Record<string, unknown>;
    runtime_config_by_executor?: Record<string, Record<string, unknown>>;
  } = {},
): Promise<RuntimeExecutorDogfoodResponse> {
  return apiRequest<RuntimeExecutorDogfoodResponse>(
    "/runtime-executors/dogfood",
    { method: "POST", body: payload },
  );
}

export function listRuntimeExecutorApprovals(executorId: string, status = ""): Promise<RuntimeApprovalRecord[]> {
  const query = status.trim() ? `?status=${encodeURIComponent(status.trim())}` : "";
  return apiRequest<RuntimeApprovalRecord[]>(`/runtime-executors/${encodeURIComponent(executorId)}/approvals${query}`);
}

export function listRuntimeApprovals(status = ""): Promise<RuntimeApprovalRecord[]> {
  const query = status.trim() ? `?status=${encodeURIComponent(status.trim())}` : "";
  return apiRequest<RuntimeApprovalRecord[]>(`/runtime-executors/approvals${query}`);
}

export function listRuntimeExecutionSessions(params: { executor_id?: string; status?: string } = {}): Promise<RuntimeExecutionSessionRecord[]> {
  const query = new URLSearchParams();
  if (params.executor_id?.trim()) query.set("executor_id", params.executor_id.trim());
  if (params.status?.trim()) query.set("status", params.status.trim());
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiRequest<RuntimeExecutionSessionRecord[]>(`/runtime-executors/sessions${suffix}`);
}

export function getRuntimeExecutionSessionReplay(sessionKey: string): Promise<RuntimeExecutionReplayResponse> {
  return apiRequest<RuntimeExecutionReplayResponse>(`/runtime-executors/sessions/${encodeURIComponent(sessionKey)}`);
}

export function getRuntimeExecutionSessionTimeline(sessionKey: string): Promise<RuntimeExecutionTimelineResponse> {
  return apiRequest<RuntimeExecutionTimelineResponse>(`/runtime-executors/sessions/${encodeURIComponent(sessionKey)}/timeline`);
}

export function reviewRuntimeExecutorApproval(
  executorId: string,
  approvalId: string,
  payload: { status: RuntimeApprovalReviewStatus; reviewer_employee_id?: string; reason?: string },
): Promise<RuntimeApprovalRecord> {
  return apiRequest<RuntimeApprovalRecord>(
    `/runtime-executors/${encodeURIComponent(executorId)}/approvals/${encodeURIComponent(approvalId)}/review`,
    { method: "POST", body: payload },
  );
}

export function runRuntimeExecutorApproval(
  executorId: string,
  approvalId: string,
  payload: {
    employee_id?: string;
    workspace_id?: string;
    message?: string;
    runtime_config?: Record<string, unknown>;
    ingest_result?: boolean;
  } = {},
): Promise<RuntimeApprovalRunResponse> {
  return apiRequest<RuntimeApprovalRunResponse>(
    `/runtime-executors/${encodeURIComponent(executorId)}/approvals/${encodeURIComponent(approvalId)}/run`,
    { method: "POST", body: payload },
  );
}
