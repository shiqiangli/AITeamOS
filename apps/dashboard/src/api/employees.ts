import { apiRequest } from "./client";
import type { EmployeeQualityFeedbackRecord, TicketGraphEdge, TicketGraphNode } from "./tickets";

export interface EmployeeAnalytics {
  employee_id: string;
  assigned_ticket_count: number;
  completed_ticket_count: number;
  validation_pass_rate: number;
  candidates_produced: number;
  recalled_asset_count: number;
  blocker_count: number;
  validation_failure_count: number;
  stale_asset_count: number;
  useful_recall_count: number;
  execution_run_count: number;
  total_cost: number;
  average_latency_ms: number;
  source_counts: Record<string, number>;
}

export interface EmployeeAnalyticsSummary {
  employees: EmployeeAnalytics[];
  source_counts: Record<string, number>;
}

export interface EmployeeGraphProjection {
  employee_id: string;
  nodes: TicketGraphNode[];
  edges: TicketGraphEdge[];
  grouped_edges: Record<string, TicketGraphEdge[]>;
  source_counts: Record<string, number>;
  provider_projection: Record<string, Record<string, unknown>>;
}

export interface EmployeeGrowthEvalCheck {
  id: string;
  status: string;
  detail: string;
  evidence: Record<string, unknown>;
}

export interface EmployeeGrowthEvalSummary {
  employee_id: string;
  current_load_status: string;
  active_ticket_count: number;
  active_run_count: number;
  current_ticket_count: number;
  historical_ticket_count: number;
  report_count: number;
  handoff_count: number;
  asset_candidate_count: number;
  approved_asset_count: number;
  asset_review_count: number;
  runtime_run_count: number;
  quality_feedback_count: number;
  improvement_candidate_count: number;
  approved_improvement_count: number;
  applied_improvement_count: number;
  improvement_loop_proof_status: string;
  improvement_loop_candidate_id: string;
  improvement_loop_asset_id: string;
  improvement_loop_application_status: string;
  improvement_loop_ticket_report_id: string;
  improvement_loop_applied_change_count: number;
  improvement_loop_workspace: string;
  handoff_target_employee_id: string;
  handoff_work_history_score: number;
  provider_projection_status: string;
  graph_node_count: number;
  graph_edge_count: number;
  source_counts: Record<string, number>;
}

export interface EmployeeGrowthEvalResponse {
  contract_version: string;
  status: string;
  detail: string;
  summary: EmployeeGrowthEvalSummary;
  checks: EmployeeGrowthEvalCheck[];
  blockers: string[];
  warnings: string[];
  commands: string[];
}

export interface EmployeeImprovementCandidateResponse {
  employee_id: string;
  feedback: EmployeeQualityFeedbackRecord;
  candidate: Record<string, unknown> & {
    id?: string;
    asset_type?: string;
    title?: string;
  };
  saved_paths: Record<string, string>;
}

export interface EmployeeImprovementApplyResponse {
  employee_id: string;
  asset_id: string;
  status: string;
  detail: string;
  applied_changes: Record<string, string[]>;
  profile: Record<string, unknown>;
  asset: Record<string, unknown>;
  ticket_report_id: string;
  saved_paths: Record<string, string>;
}

export function getEmployeeAnalytics(employeeId: string): Promise<EmployeeAnalytics> {
  return apiRequest<EmployeeAnalytics>(`/employees/${encodeURIComponent(employeeId)}/analytics`);
}

export function getEmployeeAnalyticsSummary(): Promise<EmployeeAnalyticsSummary> {
  return apiRequest<EmployeeAnalyticsSummary>("/employees/analytics/summary");
}

export function getEmployeeGraph(employeeId: string): Promise<EmployeeGraphProjection> {
  return apiRequest<EmployeeGraphProjection>(`/employees/${encodeURIComponent(employeeId)}/graph`);
}

export function getEmployeeGrowthEval(employeeId: string): Promise<EmployeeGrowthEvalResponse> {
  return apiRequest<EmployeeGrowthEvalResponse>(`/employees/${encodeURIComponent(employeeId)}/growth-eval`);
}

export function proposeEmployeeImprovementCandidate(
  employeeId: string,
  feedbackId: string,
  payload: {
    actor_employee_id?: string;
    reason?: string;
    title?: string;
    content?: string;
    proposed_skill_refs?: string[];
    proposed_memory_scopes?: string[];
    proposed_capability_tags?: string[];
    proposed_personality_tags?: string[];
  } = {},
): Promise<EmployeeImprovementCandidateResponse> {
  return apiRequest<EmployeeImprovementCandidateResponse>(
    `/employees/${encodeURIComponent(employeeId)}/quality-feedback/${encodeURIComponent(feedbackId)}/improvement-candidate`,
    {
      method: "POST",
      body: payload,
    },
  );
}

export function applyEmployeeImprovementAsset(
  employeeId: string,
  assetId: string,
  payload: { actor_employee_id?: string; reason?: string; application_note?: string } = {},
): Promise<EmployeeImprovementApplyResponse> {
  return apiRequest<EmployeeImprovementApplyResponse>(
    `/employees/${encodeURIComponent(employeeId)}/improvement-assets/${encodeURIComponent(assetId)}/apply`,
    {
      method: "POST",
      body: payload,
    },
  );
}
