import { apiRequest } from "./client";
import type { GraphitiBackendStatus } from "./memory";
import type { TicketBackendStatus } from "./tickets";

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
  ticket_backend?: TicketBackendStatus | null;
  memory_backend?: GraphitiBackendStatus | null;
  blockers?: Array<{
    id: string;
    scope: string;
    status: string;
    detail: string;
    setup_required: string[];
  }>;
}

export function getSystemStatus(): Promise<SystemStatusResponse> {
  return apiRequest<SystemStatusResponse>("/system-status");
}
