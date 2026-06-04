import { apiRequest } from "./client";

export interface SystemStatusSecretItem {
  id: string;
  scope: string;
  purpose: string;
  env_vars: string[];
  required_for: string;
  configured: boolean;
  how_to_configure: string;
}

export interface SystemStatusResponse {
  secrets: SystemStatusSecretItem[];
}

export function getSystemStatus(): Promise<SystemStatusResponse> {
  return apiRequest<SystemStatusResponse>("/system-status");
}
