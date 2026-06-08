import { apiRequest } from "./client";

export interface ChatEmployeeSummary {
  id: string;
  display_name: string;
  kind: string;
  role: string;
  summary: string;
  skills: string[];
  ai_engine_mode: string;
  default_ai_engine: string;
  preserve_engine_thread: boolean;
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
  source?: string;
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
  engine_thread_id: string;
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
  catalog_order: string[];
  saved_paths: Record<string, string>;
}

export interface ChatAiEngineConfigField {
  id: string;
  label: string;
  kind: string;
  value?: string | boolean | number | null;
  placeholder: string;
  options: string[];
  required: boolean;
  secret: boolean;
  read_only: boolean;
  help: string;
}

export interface ChatAiEngineRecord {
  id: string;
  display_name: string;
  kind: string;
  description: string;
  support_status: string;
  config_status: string;
  auth_kind: string;
  base_url?: string | null;
  api_key_env?: string | null;
  model?: string | null;
  thinking?: string | null;
  speed?: string | null;
  context_window?: number | null;
  max_tokens?: number | null;
  enabled: boolean;
  editable: boolean;
  active: boolean;
  api_key_configured: boolean;
  status: string;
  secret_env_vars: string[];
  capabilities: string[];
  model_options: string[];
  thinking_options: string[];
  config_fields: ChatAiEngineConfigField[];
  chat_options: ChatAiEngineConfigField[];
  health_detail: string;
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
  speed?: string | null;
  context_window?: number | null;
  max_tokens?: number | null;
  base_url?: string | null;
  api_key_env?: string | null;
  enabled?: boolean | null;
  activate?: boolean;
}

export interface ChatEmployeeAiEngineUpdateRequest {
  default_ai_engine: string;
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

export function updateChatEmployeeAiEngine(
  employeeId: string,
  payload: ChatEmployeeAiEngineUpdateRequest,
): Promise<ChatEmployeeSummary> {
  return apiRequest<ChatEmployeeSummary>(`/chat/employees/${encodeURIComponent(employeeId)}/ai-engine`, {
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
