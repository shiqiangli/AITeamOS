import { apiRequest } from "./client";

export interface TicketReport {
  id: string;
  reporter_employee_id: string;
  reporter_role: string;
  content: string;
  evidence: string[];
  report_type: string;
  created_at: string;
}

export interface Ticket {
  id: string;
  title: string;
  description: string;
  status: string;
  assigned_employee_id: string;
  assigned_role: string;
  validation_employee_id: string;
  validation_role: string;
  knowledge_refs: string[];
  code_repository_ids: string[];
  source_thread_id: string;
  source_run_id: string;
  reports: TicketReport[];
  created_at: string;
  updated_at: string;
  saved_path: string;
}

export function listTickets(): Promise<Ticket[]> {
  return apiRequest<Ticket[]>("/tickets");
}
