import { authStorage, type AuthTokens, type AuthUser } from "@/lib/auth";
import { config } from "@/lib/config";
import { sanitizeText } from "@/lib/sanitize";
import { logTelemetry } from "@/lib/telemetry";

interface AuthResponse {
  success: boolean;
  user: AuthUser;
  tokens: AuthTokens;
  error?: string;
}

export class ApiError extends Error {
  status: number;
  code: string;
  traceId?: string;

  constructor(message: string, status = 500, code = "API_ERROR", traceId?: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.traceId = traceId;
  }
}

function buildHeaders(): HeadersInit {
  const headers: HeadersInit = { "Content-Type": "application/json", "X-Client-Version": "enterprise-v1" };
  const tokens = authStorage.getTokens();
  if (tokens?.access) {
    headers.Authorization = `Bearer ${tokens.access}`;
  }
  return headers;
}

async function fetchWithTimeout(
  input: RequestInfo | URL,
  init: RequestInit = {},
  timeoutMs = config.requestTimeoutMs,
): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("Request timed out", 408, "TIMEOUT");
    }
    if (error instanceof TypeError) {
      throw new ApiError(
        `Cannot reach API at ${config.apiBaseUrl}. Check server/CORS/network.`,
        503,
        "NETWORK_ERROR",
      );
    }
    const message = error instanceof Error ? error.message : "Unexpected network failure";
    throw new ApiError(sanitizeText(message), 500, "REQUEST_FAILED");
  } finally {
    clearTimeout(timeout);
  }
}

async function parseJson<T>(response: Response): Promise<T> {
  let data: (T & { error?: string; trace_id?: string }) | null = null;
  try {
    data = (await response.json()) as T & { error?: string; trace_id?: string };
  } catch {
    data = null;
  }

  if (!response.ok) {
    const message = data?.error || `Request failed with status ${response.status}`;
    const traceId = data?.trace_id || response.headers.get("X-Request-ID") || undefined;
    throw new ApiError(sanitizeText(message), response.status, "HTTP_ERROR", traceId);
  }

  return (data ?? ({} as T)) as T;
}

async function requestWithRetry<T>(url: string, init: RequestInit, retries = 1): Promise<T> {
  try {
    const response = await fetchWithTimeout(url, init);
    return await parseJson<T>(response);
  } catch (error) {
    const isTransient = error instanceof ApiError && [408, 429, 500, 502, 503, 504].includes(error.status);
    if (retries > 0 && isTransient) {
      logTelemetry("api.retry", { url, status: error.status });
      return requestWithRetry<T>(url, init, retries - 1);
    }
    throw error;
  }
}

export const apiClient = {
  async login(email: string, password: string): Promise<AuthResponse> {
    const payload = await requestWithRetry<AuthResponse>(`${config.apiBaseUrl}/api/auth/login/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });

    authStorage.setUser(payload.user);
    authStorage.setTokens(payload.tokens);
    return payload;
  },

  async register(name: string, email: string, password: string): Promise<AuthResponse> {
    const payload = await requestWithRetry<AuthResponse>(`${config.apiBaseUrl}/api/auth/register/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, email, password }),
    });

    authStorage.setUser(payload.user);
    authStorage.setTokens(payload.tokens);
    return payload;
  },

  async refresh(): Promise<AuthTokens> {
    const tokens = authStorage.getTokens();
    if (!tokens?.refresh) {
      throw new ApiError("No refresh token available", 401, "NO_REFRESH_TOKEN");
    }

    const payload = await requestWithRetry<{ success: boolean; tokens: AuthTokens }>(
      `${config.apiBaseUrl}/api/auth/refresh/`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh: tokens.refresh }),
      },
    );

    authStorage.setTokens(payload.tokens);
    return payload.tokens;
  },

  async askStream(question: string): Promise<Response> {
    const streamOpenTimeoutMs = Math.max(config.requestTimeoutMs, 60_000);
    let response = await fetchWithTimeout(`${config.apiBaseUrl}/api/ask/stream/`, {
      method: "POST",
      headers: buildHeaders(),
      body: JSON.stringify({ question }),
    }, streamOpenTimeoutMs);

    if (response.status === 401) {
      await this.refresh();
      response = await fetchWithTimeout(`${config.apiBaseUrl}/api/ask/stream/`, {
        method: "POST",
        headers: buildHeaders(),
        body: JSON.stringify({ question }),
      }, streamOpenTimeoutMs);
    }

    if (!response.ok) {
      let errorMessage = `Streaming request failed (${response.status})`;
      let traceId: string | undefined;
      try {
        const payload = (await response.json()) as { error?: string; trace_id?: string };
        if (payload.error) {
          errorMessage = sanitizeText(payload.error);
        }
        traceId = payload.trace_id;
      } catch {
        // Keep fallback message
      }
      throw new ApiError(errorMessage, response.status, "STREAM_ERROR", traceId);
    }

    logTelemetry("api.stream_open", { route: "/api/ask/stream/" });
    return response;
  },
};
