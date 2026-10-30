import type { ApiErrorBody, AuthResponse, AuthTokens, ClientConfig, ConnectionState, ConnectPayload } from "@/types";

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: string,
  ) {
    super(message);
  }
}

let sessionId = "";
export function setSessionId(id: string) {
  sessionId = id;
}

// --- Auth tokens: kept by the useAuth store, read here for every request ---
let tokens: AuthTokens | null = null;
let onTokensChanged: (t: AuthTokens | null) => void = () => {};

export function setTokens(t: AuthTokens | null) {
  tokens = t;
}
export function onAuthChange(fn: (t: AuthTokens | null) => void) {
  onTokensChanged = fn;
}

function headers(extra?: HeadersInit): HeadersInit {
  return {
    "Content-Type": "application/json",
    "X-Session-Id": sessionId,
    ...(tokens ? { Authorization: `Bearer ${tokens.access_token}` } : {}),
    ...extra,
  };
}

/** Swap the refresh token for a new pair. Shared, so parallel 401s refresh only once. */
let refreshing: Promise<boolean> | null = null;
function refreshTokens(): Promise<boolean> {
  refreshing ??= (async () => {
    try {
      const res = await fetch(`${BASE_URL}/api/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: tokens?.refresh_token }),
      });
      if (!res.ok) throw new Error();
      const data = (await res.json()) as AuthResponse;
      tokens = { access_token: data.access_token, refresh_token: data.refresh_token };
      onTokensChanged(tokens);
      return true;
    } catch {
      tokens = null;
      onTokensChanged(null); // refresh token expired or revoked: back to the login page
      return false;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

/** fetch() with the access token; on 401 it refreshes the tokens once and retries. */
async function authedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const send = () => fetch(`${BASE_URL}${path}`, { ...init, headers: headers(init.headers) });
  let res = await send();
  if (res.status === 401 && tokens && !path.startsWith("/api/auth/") && (await refreshTokens())) res = await send();
  return res;
}

async function toApiError(res: Response): Promise<ApiError> {
  let body: Partial<ApiErrorBody> = {};
  try {
    body = await res.json();
  } catch {
    /* non-JSON error */
  }
  const message = body.error?.message ?? (res.status === 429 ? "Too many requests, slow down a little." : `Request failed (${res.status})`);
  return new ApiError(message, res.status, body.error?.code ?? "http_error");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await authedFetch(path, init);
  } catch {
    throw new ApiError("Cannot reach the DataPilot server. Is the backend running?", 0, "network_error");
  }
  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  login: (email: string, password: string) =>
    request<AuthResponse>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  signup: (email: string, password: string) =>
    request<AuthResponse>("/api/auth/signup", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: (refresh_token: string) =>
    request<void>("/api/auth/logout", { method: "POST", body: JSON.stringify({ refresh_token }) }),
  config: () => request<ClientConfig>("/api/config"),
  currentConnection: () => request<ConnectionState>("/api/connections/current"),
  connect: (payload: ConnectPayload) =>
    request<ConnectionState>("/api/connections", { method: "POST", body: JSON.stringify(payload) }),
  disconnect: () => request<void>("/api/connections/current", { method: "DELETE" }),
  refreshSchema: () => request<ConnectionState>("/api/schema/refresh", { method: "POST" }),
};

export interface StreamEvent {
  event: string;
  data: unknown;
}

/** POST + Server-Sent Events (EventSource only supports GET). */
export async function* streamChat(
  body: { message: string; history: { role: string; content: string; sql?: string | null }[]; model: string | null },
  signal: AbortSignal,
): AsyncGenerator<StreamEvent> {
  let res: Response;
  try {
    res = await authedFetch("/api/chat", {
      method: "POST",
      headers: { Accept: "text/event-stream" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError("Cannot reach the DataPilot server. Is the backend running?", 0, "network_error");
  }
  if (!res.ok || !res.body) throw await toApiError(res);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of raw.split("\n")) {
        if (line.startsWith(":")) continue;
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      if (data.length) yield { event, data: JSON.parse(data.join("\n")) };
    }
  }
}
