import { apiRequest } from "./client";

export interface ToolConnector {
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

export interface ToolConnectorRegistryStatus {
  connector_count: number;
  enabled_count: number;
  configured_count: number;
  ready_count: number;
  saved_paths: Record<string, string>;
}

export interface ToolConnectorSettingsResponse {
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
  connector: ToolConnector;
}

export interface ToolConnectorSettingsUpdateRequest {
  enabled: boolean;
  base_url: string;
  email: string;
  space_key?: string;
  workspace_slug?: string;
  project_id?: string;
}

export interface ToolConnectorHealthResponse {
  connector_id: string;
  status: string;
  detail: string;
  checked_at: string;
  configured: boolean;
  data: Record<string, unknown>;
}

export function listToolConnectors(): Promise<ToolConnector[]> {
  return apiRequest<ToolConnector[]>("/tool-connectors/connectors");
}

export function getToolConnectorStatus(): Promise<ToolConnectorRegistryStatus> {
  return apiRequest<ToolConnectorRegistryStatus>("/tool-connectors/status");
}

export function getToolConnectorSettings(connectorId: string): Promise<ToolConnectorSettingsResponse> {
  return apiRequest<ToolConnectorSettingsResponse>(`/tool-connectors/connectors/${encodeURIComponent(connectorId)}/settings`);
}

export function updateToolConnectorSettings(
  connectorId: string,
  payload: ToolConnectorSettingsUpdateRequest,
): Promise<ToolConnectorSettingsResponse> {
  return apiRequest<ToolConnectorSettingsResponse>(`/tool-connectors/connectors/${encodeURIComponent(connectorId)}/settings`, {
    method: "PUT",
    body: payload,
  });
}

export function checkToolConnectorHealth(connectorId: string): Promise<ToolConnectorHealthResponse> {
  return apiRequest<ToolConnectorHealthResponse>(`/tool-connectors/connectors/${encodeURIComponent(connectorId)}/health`, {
    method: "POST",
  });
}
