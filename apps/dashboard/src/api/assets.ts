import { apiRequest } from "./client";

export interface AssetRecord {
  id: string;
  kind: string;
  title: string;
  status: string;
  source_ticket: string;
  source_employee: string;
  assigned_employees: string[];
  scopes: string[];
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
}

export interface AssetCandidateRecord {
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
  relationships: Array<Record<string, unknown>>;
  review_state: string;
  usefulness_stats: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AssetReviewRecord {
  id: string;
  candidate_id: string;
  asset_id: string;
  status: string;
  reviewer_employee_id: string;
  reason: string;
  merge_target_asset_id: string;
  link_relationships: Array<Record<string, unknown>>;
  created_at: string;
  updated_at: string;
}

export interface AssetRegistryRecord {
  id: string;
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
  relationships: Array<Record<string, unknown>>;
  review_state: string;
  usefulness_stats: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AssetCandidateReviewResponse {
  candidate: AssetCandidateRecord;
  review: AssetReviewRecord;
  asset: AssetRegistryRecord | null;
  saved_paths: Record<string, string>;
}

export interface AssetCandidateBatchReviewItem {
  candidate_id: string;
  status: string;
  response: AssetCandidateReviewResponse | null;
  error: string;
}

export interface AssetCandidateBatchReviewResponse {
  status: string;
  requested_count: number;
  reviewed_count: number;
  failed_count: number;
  results: AssetCandidateBatchReviewItem[];
  saved_paths: Record<string, string>;
}

export interface AssetRecordProjectionResponse {
  asset_id: string;
  status: string;
  detail: string;
  ingested_asset: Record<string, unknown> | null;
  skipped_asset: Record<string, string> | null;
  saved_paths: Record<string, string>;
}

export interface AssetRecordRelationshipProjectionResponse {
  asset_id: string;
  status: string;
  detail: string;
  ingested_relationships: Array<Record<string, unknown>>;
  skipped_relationships: Array<Record<string, string>>;
  unsupported_relationships: Array<Record<string, string>>;
  saved_paths: Record<string, string>;
}

export type AssetArea = "knowledge" | "capabilities" | "review";
export type AssetDetail =
  | "docs"
  | "memories"
  | "decisions"
  | "skills"
  | "kernel-commands"
  | "mcp-tools"
  | "tools";

function assetPath(area?: string | null, detail?: string | null): string {
  if (!area) return "/assets";
  const parts = ["/assets", area, detail].filter(Boolean);
  return parts.join("/");
}

function withQuery(path: string, query?: string): string {
  const trimmed = query?.trim() ?? "";
  return trimmed ? `${path}?q=${encodeURIComponent(trimmed)}` : path;
}

export function listAssets(area?: string | null, detail?: string | null, query?: string): Promise<AssetRecord[]> {
  return apiRequest<AssetRecord[]>(withQuery(assetPath(area, detail), query));
}

export function searchAssets(query: string): Promise<AssetRecord[]> {
  return apiRequest<AssetRecord[]>(withQuery("/assets/search", query));
}

export function listAssetCandidates(params: { status?: string; asset_type?: string; q?: string } = {}): Promise<AssetCandidateRecord[]> {
  const query = new URLSearchParams();
  if (params.status?.trim()) query.set("status", params.status.trim());
  if (params.asset_type?.trim()) query.set("asset_type", params.asset_type.trim());
  if (params.q?.trim()) query.set("q", params.q.trim());
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiRequest<AssetCandidateRecord[]>(`/assets/candidates${suffix}`);
}

export function reviewAssetCandidate(
  candidateId: string,
  payload: {
    status: "approved" | "rejected" | "merged" | "linked";
    reviewer_employee_id?: string;
    reason?: string;
    merge_target_asset_id?: string;
    link_relationships?: Array<Record<string, unknown>>;
  },
): Promise<AssetCandidateReviewResponse> {
  return apiRequest<AssetCandidateReviewResponse>(
    `/assets/candidates/${encodeURIComponent(candidateId)}/review`,
    { method: "POST", body: payload },
  );
}

export function reviewAssetCandidatesBatch(payload: {
  candidate_ids: string[];
  status: "approved" | "rejected" | "merged" | "linked";
  reviewer_employee_id?: string;
  reason?: string;
  merge_target_asset_id?: string;
  link_relationships?: Array<Record<string, unknown>>;
}): Promise<AssetCandidateBatchReviewResponse> {
  return apiRequest<AssetCandidateBatchReviewResponse>(
    "/assets/candidates/review-batch",
    { method: "POST", body: payload },
  );
}

export function projectAssetRecordToGraphiti(assetId: string): Promise<AssetRecordProjectionResponse> {
  return apiRequest<AssetRecordProjectionResponse>(
    `/assets/records/${encodeURIComponent(assetId)}/project/graphiti`,
    { method: "POST" },
  );
}

export function projectAssetRecordRelationshipsToGraphiti(assetId: string): Promise<AssetRecordRelationshipProjectionResponse> {
  return apiRequest<AssetRecordRelationshipProjectionResponse>(
    `/assets/records/${encodeURIComponent(assetId)}/relationships/project/graphiti`,
    { method: "POST" },
  );
}

export function listAllAssets(): Promise<AssetRecord[]> {
  return apiRequest<AssetRecord[]>("/assets");
}
