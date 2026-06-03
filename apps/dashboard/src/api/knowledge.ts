import { apiRequest } from "./client";

export interface KnowledgeDocSummary {
  id: string;
  title: string;
  source: string;
  path: string;
  excerpt: string;
  updated_at: string;
  tags: string[];
}

export interface DecisionRecord {
  id: string;
  title: string;
  status: string;
  context: string;
  decision: string;
  consequences: string;
  linked_work_items: string[];
  linked_memories: string[];
  created_at: string;
  updated_at: string;
  saved_path: string;
}

export interface KnowledgeSearchResult {
  id: string;
  title: string;
  content: string;
  source_type: string;
  source_ref: string;
  score: number;
  metadata: Record<string, unknown>;
}

export interface KnowledgeSearchResponse {
  query: string;
  results: KnowledgeSearchResult[];
}

export interface ReviewQueueItem {
  id: string;
  kind: string;
  title: string;
  content: string;
  status: string;
  source_ref: string;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
}

export interface KnowledgeStatusResponse {
  docs_count: number;
  memories_count: number;
  decisions_count: number;
  review_queue_count: number;
  saved_paths: Record<string, string>;
}

export function getKnowledgeStatus(): Promise<KnowledgeStatusResponse> {
  return apiRequest<KnowledgeStatusResponse>("/knowledge/status");
}

export function listKnowledgeDocs(): Promise<KnowledgeDocSummary[]> {
  return apiRequest<KnowledgeDocSummary[]>("/knowledge/docs");
}

export function listKnowledgeDecisions(): Promise<DecisionRecord[]> {
  return apiRequest<DecisionRecord[]>("/knowledge/decisions");
}

export function listKnowledgeReviewQueue(): Promise<ReviewQueueItem[]> {
  return apiRequest<ReviewQueueItem[]>("/knowledge/review-queue");
}

export function searchKnowledge(query: string): Promise<KnowledgeSearchResponse> {
  return apiRequest<KnowledgeSearchResponse>(`/knowledge/search?q=${encodeURIComponent(query)}&limit=12`);
}
