import { apiRequest } from "./client";

export interface CodeRepository {
  id: string;
  name: string;
  provider: string;
  location: string;
  default_branch: string;
  plane_workspace_slug: string;
  plane_project_id: string;
  description: string;
  enabled: boolean;
  status: string;
  detail: string;
  git_detected: boolean;
  current_branch: string;
  created_at: string;
  updated_at: string;
  saved_path: string;
}

export interface CodeRepositoryUpsertRequest {
  id?: string;
  name: string;
  provider: string;
  location: string;
  default_branch?: string;
  plane_workspace_slug?: string;
  plane_project_id?: string;
  description?: string;
  enabled?: boolean;
}

export interface CodeRepositoryStatus {
  repository_count: number;
  enabled_count: number;
  ready_count: number;
  local_count: number;
  remote_count: number;
  saved_paths: Record<string, string>;
}

export function listCodeRepositories(): Promise<CodeRepository[]> {
  return apiRequest<CodeRepository[]>("/code-repositories");
}

export function getCodeRepositoryStatus(): Promise<CodeRepositoryStatus> {
  return apiRequest<CodeRepositoryStatus>("/code-repositories/status");
}

export function createCodeRepository(payload: CodeRepositoryUpsertRequest): Promise<CodeRepository> {
  return apiRequest<CodeRepository>("/code-repositories", {
    method: "POST",
    body: payload,
  });
}

export function updateCodeRepository(repoId: string, payload: CodeRepositoryUpsertRequest): Promise<CodeRepository> {
  return apiRequest<CodeRepository>(`/code-repositories/${encodeURIComponent(repoId)}`, {
    method: "PUT",
    body: payload,
  });
}

export function deleteCodeRepository(repoId: string): Promise<void> {
  return apiRequest<void>(`/code-repositories/${encodeURIComponent(repoId)}`, {
    method: "DELETE",
  });
}
