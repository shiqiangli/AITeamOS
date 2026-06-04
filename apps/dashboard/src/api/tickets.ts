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

export interface TicketBackendMode {
  id: string;
  label: string;
  status: string;
  description: string;
}

export interface TicketBackendSettings {
  mode: string;
  local_file_path: string;
  saved_paths: Record<string, string>;
  supported_modes: TicketBackendMode[];
}

export interface TicketBackendSettingsUpdateRequest {
  mode: string;
  local_file_path: string;
}

export interface TicketBackendStatus {
  mode: string;
  status: string;
  detail: string;
  ticket_count: number;
  local_file_path: string;
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
