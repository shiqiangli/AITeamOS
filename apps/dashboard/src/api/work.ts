import { apiRequest } from "./client";

export interface WorkItemReport {
  id: string;
  reporter_member_id: string;
  reporter_role: string;
  content: string;
  evidence: string[];
  report_type: string;
  created_at: string;
}

export interface WorkItem {
  id: string;
  title: string;
  description: string;
  status: string;
  assigned_member_id: string;
  assigned_role: string;
  validation_member_id: string;
  validation_role: string;
  knowledge_refs: string[];
  code_repository_ids: string[];
  source_thread_id: string;
  source_run_id: string;
  reports: WorkItemReport[];
  created_at: string;
  updated_at: string;
  saved_path: string;
}

export function listWorkItems(): Promise<WorkItem[]> {
  return apiRequest<WorkItem[]>("/work-items");
}
