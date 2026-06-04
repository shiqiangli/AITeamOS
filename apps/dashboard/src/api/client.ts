/**
 * AITeamOS Dashboard — API Client (file-first P0)
 *
 * Generic typed REST client for the AITeamOS API at /api/v1.
 */

const API_BASE = "/api/v1";

let _authToken: string | null = null;

export function setAuthToken(token: string | null): void {
  _authToken = token;
}

export function getAuthToken(): string | null {
  return _authToken;
}

// ─── Generic fetch wrapper ───────────────────────────────────────────────────

export class ApiClientError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public body: unknown,
  ) {
    super(formatApiErrorMessage(status, statusText, body));
    this.name = "ApiClientError";
  }
}

function formatApiErrorMessage(status: number, statusText: string, body: unknown): string {
  const detail = extractApiErrorDetail(body);
  return detail ? `API ${status}: ${detail}` : `API ${status}: ${statusText}`;
}

function extractApiErrorDetail(body: unknown): string | null {
  if (!body) return null;
  if (typeof body === "string") return body || null;
  if (typeof body !== "object") return null;

  const record = body as Record<string, unknown>;
  if (typeof record.detail === "string") return record.detail;
  if (Array.isArray(record.detail)) return record.detail.map(String).join("; ");

  const error = record.error;
  if (error && typeof error === "object") {
    const errorRecord = error as Record<string, unknown>;
    if (typeof errorRecord.message === "string") return errorRecord.message;
  }

  if (typeof record.message === "string") return record.message;
  return null;
}

export async function apiRequest<T>(
  path: string,
  options: { method?: string; body?: unknown } = {},
): Promise<T> {
  const { method = "GET", body } = options;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };
  if (_authToken) {
    headers["Authorization"] = `Bearer ${_authToken}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    let errorBody: unknown;
    try {
      errorBody = await res.json();
    } catch {
      errorBody = await res.text().catch(() => null);
    }
    throw new ApiClientError(res.status, res.statusText, errorBody);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}
