import { apiRequest } from "./client";

export interface GraphitiBackendStatus {
  backend: string;
  enabled: boolean;
  configured: boolean;
  graph_configured: boolean;
  llm_configured: boolean;
  package_installed: boolean;
  status: string;
  detail: string;
  group_id: string;
  graph_database: string;
  uri: string;
  user: string;
  llm_provider: string;
  password_configured: boolean;
  openai_api_key_configured: boolean;
}

export interface GraphitiSettingsResponse {
  enabled: boolean;
  graph_database: string;
  uri: string;
  user: string;
  group_id: string;
  llm_provider: string;
  password_configured: boolean;
  openai_api_key_configured: boolean;
  uses_runtime_openai_key: boolean;
  saved_paths: Record<string, string>;
  backend: GraphitiBackendStatus;
}

export interface GraphitiSettingsUpdateRequest {
  enabled: boolean;
  graph_database: string;
  uri: string;
  user: string;
  password?: string;
  group_id: string;
  llm_provider: string;
  openai_api_key?: string;
}

export interface MemoryCandidate {
  id: string;
  content: string;
  status: string;
  source_kind: string;
  source_ref: string;
  scope_kind: string;
  scope_ref: string;
  memory_type: string;
  confidence: number;
  employee_ids: string[];
  tags: string[];
  provenance: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  approved_at?: string | null;
  graphiti_episode_id?: string | null;
  graphiti_status: Record<string, unknown>;
}

export interface MemoryCandidateCreateRequest {
  content: string;
  source_kind?: string;
  source_ref?: string;
  scope_kind?: string;
  scope_ref?: string;
  memory_type?: string;
  confidence?: number;
  employee_ids?: string[];
  tags?: string[];
  provenance?: Record<string, unknown>;
}

export interface MemoryStatusResponse {
  backend: GraphitiBackendStatus;
  candidate_count: number;
  approved_count: number;
  pending_graphiti_count: number;
  saved_paths: Record<string, string>;
}

export interface MemorySearchResult {
  id: string;
  content: string;
  source: string;
  score?: number | null;
  source_kind: string;
  source_ref: string;
  scope_kind: string;
  scope_ref: string;
  memory_type: string;
  employee_ids: string[];
  tags: string[];
  provenance: Record<string, unknown>;
}

export interface MemorySearchResponse {
  query: string;
  results: MemorySearchResult[];
  backend: GraphitiBackendStatus;
}

export function getMemoryStatus(): Promise<MemoryStatusResponse> {
  return apiRequest<MemoryStatusResponse>("/memory/status");
}

export function getGraphitiSettings(): Promise<GraphitiSettingsResponse> {
  return apiRequest<GraphitiSettingsResponse>("/memory/graphiti/settings");
}

export function updateGraphitiSettings(payload: GraphitiSettingsUpdateRequest): Promise<GraphitiSettingsResponse> {
  return apiRequest<GraphitiSettingsResponse>("/memory/graphiti/settings", {
    method: "PUT",
    body: payload,
  });
}

export function listMemoryCandidates(status?: string): Promise<MemoryCandidate[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiRequest<MemoryCandidate[]>(`/memory/candidates${query}`);
}

export function createMemoryCandidate(payload: MemoryCandidateCreateRequest): Promise<MemoryCandidate> {
  return apiRequest<MemoryCandidate>("/memory/candidates", {
    method: "POST",
    body: payload,
  });
}

export function approveMemoryCandidate(candidateId: string): Promise<MemoryCandidate> {
  return apiRequest<MemoryCandidate>(`/memory/candidates/${encodeURIComponent(candidateId)}/approve`, {
    method: "POST",
  });
}

export function listApprovedMemory(): Promise<MemoryCandidate[]> {
  return apiRequest<MemoryCandidate[]>("/memory/approved");
}

export function searchMemory(query: string): Promise<MemorySearchResponse> {
  return apiRequest<MemorySearchResponse>(`/memory/search?q=${encodeURIComponent(query)}&limit=12`);
}
