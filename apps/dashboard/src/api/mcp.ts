import { apiRequest } from "./client";

export interface McpConnector {
  id: string;
  name: string;
  status: string;
  transport: string;
  enabled: boolean;
  configured: boolean;
  description: string;
  capabilities: string[];
  permissions: string[];
  required_settings: string[];
  server: Record<string, unknown>;
  updated_at: string;
}

export interface McpRegistryStatus {
  connector_count: number;
  enabled_count: number;
  configured_count: number;
  ready_count: number;
  saved_paths: Record<string, string>;
}

export interface McpConnectorSettingsResponse {
  connector_id: string;
  enabled: boolean;
  configured: boolean;
  base_url: string;
  email: string;
  space_key: string;
  workspace_slug: string;
  project_id: string;
  api_token_configured: boolean;
  saved_paths: Record<string, string>;
  connector: McpConnector;
}

export interface McpConnectorSettingsUpdateRequest {
  enabled: boolean;
  base_url: string;
  email: string;
  space_key?: string;
  workspace_slug?: string;
  project_id?: string;
  api_token?: string;
}

export interface McpConnectorHealthResponse {
  connector_id: string;
  status: string;
  detail: string;
  checked_at: string;
  configured: boolean;
  data: Record<string, unknown>;
}

export function listMcpConnectors(): Promise<McpConnector[]> {
  return apiRequest<McpConnector[]>("/mcp/connectors");
}

export function getMcpStatus(): Promise<McpRegistryStatus> {
  return apiRequest<McpRegistryStatus>("/mcp/status");
}

export function getMcpConnectorSettings(connectorId: string): Promise<McpConnectorSettingsResponse> {
  return apiRequest<McpConnectorSettingsResponse>(`/mcp/connectors/${encodeURIComponent(connectorId)}/settings`);
}

export function updateMcpConnectorSettings(
  connectorId: string,
  payload: McpConnectorSettingsUpdateRequest,
): Promise<McpConnectorSettingsResponse> {
  return apiRequest<McpConnectorSettingsResponse>(`/mcp/connectors/${encodeURIComponent(connectorId)}/settings`, {
    method: "PUT",
    body: payload,
  });
}

export function checkMcpConnectorHealth(connectorId: string): Promise<McpConnectorHealthResponse> {
  return apiRequest<McpConnectorHealthResponse>(`/mcp/connectors/${encodeURIComponent(connectorId)}/health`, {
    method: "POST",
  });
}
