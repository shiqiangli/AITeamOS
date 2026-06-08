import { apiRequest } from "./client";
import type { TicketGraphEdge, TicketGraphNode } from "./tickets";

export interface EmployeeAnalytics {
  employee_id: string;
  assigned_ticket_count: number;
  completed_ticket_count: number;
  validation_pass_rate: number;
  candidates_produced: number;
  recalled_asset_count: number;
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
