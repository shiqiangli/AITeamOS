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

export type AssetArea = "knowledge" | "capabilities" | "review";
export type AssetDetail =
  | "docs"
  | "memories"
  | "decisions"
  | "skills"
  | "built-in-tools"
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

export function listAllAssets(): Promise<AssetRecord[]> {
  return apiRequest<AssetRecord[]>("/assets");
}
