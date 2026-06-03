import { apiRequest } from "./client";

export interface CapabilityRecord {
  id: string;
  name: string;
  kind: string;
  domain: string;
  source: string;
  status: string;
  enabled: boolean;
  configured: boolean;
  description: string;
  owner_scope: string;
  permissions: string[];
  required_settings: string[];
  arguments: string[];
  produces: string[];
  boundary: string;
  deep_link: string;
  connector_id: string;
}

export interface CapabilityRegistryStatus {
  capability_count: number;
  enabled_count: number;
  configured_count: number;
  ready_count: number;
  local_tool_count: number;
  mcp_capability_count: number;
  agent_executor_count: number;
  saved_paths: Record<string, string>;
}

export interface CapabilityRegistryResponse {
  status: CapabilityRegistryStatus;
  capabilities: CapabilityRecord[];
  model: Record<string, string>;
}

export function getCapabilities(): Promise<CapabilityRegistryResponse> {
  return apiRequest<CapabilityRegistryResponse>("/capabilities");
}

export function getCapabilityStatus(): Promise<CapabilityRegistryStatus> {
  return apiRequest<CapabilityRegistryStatus>("/capabilities/status");
}
