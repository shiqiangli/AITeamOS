import { apiRequest } from "./client";

export interface ChatEmployeeSummary {
  id: string;
  display_name: string;
  kind: string;
  role: string;
  summary: string;
  skills: string[];
  ai_engine_mode: string;
  preserve_provider_thread: boolean;
  default_thread_id: string;
}

export interface ChatSkillSummary {
  id: string;
  title: string;
  description: string;
  content: string;
  assigned_employees: string[];
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
  target_employee_id?: string;
  thread_id?: string;
  ticket_key?: string;
}

export interface ChatMessageResponse {
  thread_id: string;
  run_id: string;
  target_employee: ChatEmployeeSummary;
  provider_thread_id: string;
  ticket_keys: string[];
  reply: string;
  trace_events: ChatTraceEvent[];
  run_metadata: Record<string, unknown>;
  saved_paths: Record<string, string>;
}

export interface ConversationMessage {
  timestamp: string;
  role: string;
  content: string;
  employee_id?: string | null;
  run_id?: string | null;
  metadata?: Record<string, unknown>;
}

export interface ConversationResponse {
  thread_id: string;
  messages: ConversationMessage[];
  thread?: ChatThreadSummary | null;
}

export interface ChatThreadSummary {
  id: string;
  employee_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  last_message_at?: string | null;
  message_count: number;
  archived: boolean;
  saved_path: string;
}

export interface ChatThreadListResponse {
  employee_id: string;
  active_thread_id: string;
  threads: ChatThreadSummary[];
}

export interface ChatAiEngineSettings {
  active_engine: string;
  deepseek_model: string;
  deepseek_thinking: string;
  openai_model: string;
  fallback_on_error: boolean;
  engines: Record<string, ChatAiEngineRecord>;
  api_keys_configured: Record<string, boolean>;
  saved_paths: Record<string, string>;
}

export interface ChatAiEngineRecord {
  id: string;
  display_name: string;
  kind: string;
  model?: string | null;
  thinking?: string | null;
  active: boolean;
  api_key_configured: boolean;
  status: string;
}

export interface ChatAiEngineSettingsRequest {
  active_engine: string;
  deepseek_model: string;
  deepseek_thinking: string;
  openai_model: string;
  fallback_on_error: boolean;
}

export interface ChatAiEngineUpdateRequest {
  model?: string | null;
  thinking?: string | null;
  activate?: boolean;
}

export function listChatEmployees(): Promise<ChatEmployeeSummary[]> {
  return apiRequest<ChatEmployeeSummary[]>("/chat/employees");
}

export function listChatSkills(): Promise<ChatSkillSummary[]> {
  return apiRequest<ChatSkillSummary[]>("/chat/skills");
}

export function getChatAiEngines(): Promise<ChatAiEngineSettings> {
  return apiRequest<ChatAiEngineSettings>("/chat/ai-engines");
}

export function updateChatAiEngines(payload: ChatAiEngineSettingsRequest): Promise<ChatAiEngineSettings> {
  return apiRequest<ChatAiEngineSettings>("/chat/ai-engines", {
    method: "PUT",
    body: payload,
  });
}

export function updateChatAiEngine(
  engineId: string,
  payload: ChatAiEngineUpdateRequest,
): Promise<ChatAiEngineSettings> {
  return apiRequest<ChatAiEngineSettings>(`/chat/ai-engines/${encodeURIComponent(engineId)}`, {
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

export function listChatThreads(employeeId: string): Promise<ChatThreadListResponse> {
  return apiRequest<ChatThreadListResponse>(`/chat/threads?employee_id=${encodeURIComponent(employeeId)}`);
}

export function createChatThread(employeeId: string, title?: string): Promise<ChatThreadSummary> {
  return apiRequest<ChatThreadSummary>("/chat/threads", {
    method: "POST",
    body: {
      employee_id: employeeId,
      ...(title ? { title } : {}),
    },
  });
}

export function activateChatThread(threadId: string, employeeId: string): Promise<ChatThreadSummary> {
  return apiRequest<ChatThreadSummary>(`/chat/threads/${encodeURIComponent(threadId)}/activate`, {
    method: "POST",
    body: { employee_id: employeeId },
  });
}

export function deleteChatThread(threadId: string): Promise<void> {
  return apiRequest<void>(`/chat/threads/${encodeURIComponent(threadId)}`, {
    method: "DELETE",
  });
}
