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
  default_thread_id: string;
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

export interface ConversationMessage {
  timestamp: string;
  role: string;
  content: string;
  member_id?: string | null;
  run_id?: string | null;
}

export interface ConversationResponse {
  thread_id: string;
  messages: ConversationMessage[];
  thread?: ChatThreadSummary | null;
}

export interface ChatThreadSummary {
  id: string;
  member_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  last_message_at?: string | null;
  message_count: number;
  archived: boolean;
  saved_path: string;
}

export interface ChatThreadListResponse {
  member_id: string;
  active_thread_id: string;
  threads: ChatThreadSummary[];
}

export interface ChatRuntimeSettings {
  provider: string;
  deepseek_model: string;
  deepseek_thinking: string;
  openai_model: string;
  fallback_on_error: boolean;
  providers: Record<string, ChatRuntimeProviderSettings>;
  api_keys_configured: Record<string, boolean>;
  saved_paths: Record<string, string>;
}

export interface ChatRuntimeProviderSettings {
  id: string;
  display_name: string;
  kind: string;
  model?: string | null;
  thinking?: string | null;
  active: boolean;
  api_key_configured: boolean;
  status: string;
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

export interface ChatRuntimeProviderUpdateRequest {
  model?: string | null;
  thinking?: string | null;
  api_key?: string;
  activate?: boolean;
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

export function updateChatRuntimeProvider(
  providerId: string,
  payload: ChatRuntimeProviderUpdateRequest,
): Promise<ChatRuntimeSettings> {
  return apiRequest<ChatRuntimeSettings>(`/chat/runtime/providers/${encodeURIComponent(providerId)}`, {
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

export function getChatThread(threadId: string): Promise<ConversationResponse> {
  return apiRequest<ConversationResponse>(`/chat/threads/${encodeURIComponent(threadId)}`);
}

export function listChatThreads(memberId: string): Promise<ChatThreadListResponse> {
  return apiRequest<ChatThreadListResponse>(`/chat/threads?member_id=${encodeURIComponent(memberId)}`);
}

export function createChatThread(memberId: string, title?: string): Promise<ChatThreadSummary> {
  return apiRequest<ChatThreadSummary>("/chat/threads", {
    method: "POST",
    body: {
      member_id: memberId,
      ...(title ? { title } : {}),
    },
  });
}

export function activateChatThread(threadId: string, memberId: string): Promise<ChatThreadSummary> {
  return apiRequest<ChatThreadSummary>(`/chat/threads/${encodeURIComponent(threadId)}/activate`, {
    method: "POST",
    body: { member_id: memberId },
  });
}
