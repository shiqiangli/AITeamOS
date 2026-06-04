import { apiRequest } from "./client";

export interface SecretHealthItem {
  id: string;
  scope: string;
  purpose: string;
  env_vars: string[];
  required_for: string;
  configured: boolean;
  how_to_configure: string;
}

export interface SecretsHealthResponse {
  items: SecretHealthItem[];
}

export function getSecretsHealth(): Promise<SecretsHealthResponse> {
  return apiRequest<SecretsHealthResponse>("/settings/secrets-health");
}
