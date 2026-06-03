import { apiRequest } from "./client";

export interface ChatMemberSummary {
  id: string;
  display_name: string;
  kind: string;
  role: string;
  summary: string;
  skills: string[];
  runtime_mode: string;
  preserve_provider_thread: boolean;
}

export interface ChatSkillSummary {
  id: string;
  title: string;
  description: string;
  assigned_members: string[];
  resources: string[];
  saved_path: string;
}

export interface ChatTraceEvent {
  event: string;
  detail: string;
  data: Record<string, unknown>;
}

export interface ChatMessageRequest {
  message: string;
  target_member_id?: string;
  thread_id?: string;
  jira_key?: string;
}

export interface ChatMessageResponse {
  thread_id: string;
  run_id: string;
  target_member: ChatMemberSummary;
  provider_thread_id: string;
  jira_keys: string[];
  reply: string;
  trace_events: ChatTraceEvent[];
  saved_paths: Record<string, string>;
}

export interface ChatRuntimeSettings {
  provider: string;
  deepseek_model: string;
  deepseek_thinking: string;
  openai_model: string;
  fallback_on_error: boolean;
  api_keys_configured: Record<string, boolean>;
  saved_paths: Record<string, string>;
}

export interface ChatRuntimeSettingsRequest {
  provider: string;
  deepseek_model: string;
  deepseek_thinking: string;
  openai_model: string;
  fallback_on_error: boolean;
  deepseek_api_key?: string;
  openai_api_key?: string;
}

export function listChatMembers(): Promise<ChatMemberSummary[]> {
  return apiRequest<ChatMemberSummary[]>("/chat/members");
}

export function listChatSkills(): Promise<ChatSkillSummary[]> {
  return apiRequest<ChatSkillSummary[]>("/chat/skills");
}

export function getChatRuntime(): Promise<ChatRuntimeSettings> {
  return apiRequest<ChatRuntimeSettings>("/chat/runtime");
}

export function updateChatRuntime(payload: ChatRuntimeSettingsRequest): Promise<ChatRuntimeSettings> {
  return apiRequest<ChatRuntimeSettings>("/chat/runtime", {
    method: "PUT",
    body: payload,
  });
}

export function sendChatMessage(payload: ChatMessageRequest): Promise<ChatMessageResponse> {
  return apiRequest<ChatMessageResponse>("/chat/messages", {
    method: "POST",
    body: payload,
  });
}
