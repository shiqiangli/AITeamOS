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

export interface EmployeeWorkLedger {
  employee_id: string;
  current_tickets: TicketWorkItem[];
  historical_tickets: TicketWorkItem[];
  reports: EmployeeTicketReportRecord[];
  validations: EmployeeTicketReportRecord[];
  blocked_records: EmployeeTicketReportRecord[];
  handoffs: Record<string, unknown>[];
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
  capabilities: string[];
  mapping: Record<string, string>;
  saved_paths: Record<string, string>;
  supported_modes: TicketBackendMode[];
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

export function getTicketEvidenceRequirements(ticketId: string): Promise<TicketEvidenceRequirements> {
  return apiRequest<TicketEvidenceRequirements>(`/tickets/${encodeURIComponent(ticketId)}/evidence-requirements`);
}

export function getSelfBootstrapSummary(): Promise<SelfBootstrapLearningSummary> {
  return apiRequest<SelfBootstrapLearningSummary>("/tickets/self-bootstrap/summary");
}

export function getTicketBackendSettings(): Promise<TicketBackendSettings> {
  return apiRequest<TicketBackendSettings>("/tickets/backend");
}

export function updateTicketBackendSettings(
  payload: TicketBackendSettingsUpdateRequest,
): Promise<TicketBackendSettings> {
  return apiRequest<TicketBackendSettings>("/tickets/backend", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getTicketBackendStatus(): Promise<TicketBackendStatus> {
  return apiRequest<TicketBackendStatus>("/tickets/status");
}
