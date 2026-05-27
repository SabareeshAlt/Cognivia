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

const LOCAL_BACKEND_SCAN_PORTS = [8000, 8001, 8002, 8003, 8004, 8005];
let activeApiBaseUrl = config.apiBaseUrl;

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
  const useTimeout = timeoutMs > 0;
  const controller = useTimeout ? new AbortController() : null;
  const externalSignal = init.signal;
  let onExternalAbort: (() => void) | null = null;
  const timeout = useTimeout ? setTimeout(() => controller?.abort(), timeoutMs) : null;
  const signal = useTimeout ? controller?.signal : externalSignal;

  if (useTimeout && controller && externalSignal) {
    if (externalSignal.aborted) {
      controller.abort();
    } else {
      onExternalAbort = () => controller.abort();
      externalSignal.addEventListener("abort", onExternalAbort, { once: true });
    }
  }

  try {
    return await fetch(input, { ...init, signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      if (externalSignal?.aborted) {
        throw new ApiError("Request aborted", 499, "REQUEST_ABORTED");
      }
      throw new ApiError("Request timed out", 408, "TIMEOUT");
    }
    if (error instanceof TypeError) {
      throw new ApiError("Cannot reach API. Check server/CORS/network.", 503, "NETWORK_ERROR");
    }
    const message = error instanceof Error ? error.message : "Unexpected network failure";
    throw new ApiError(sanitizeText(message), 500, "REQUEST_FAILED");
  } finally {
    if (timeout) {
      clearTimeout(timeout);
    }
    if (externalSignal && onExternalAbort) {
      externalSignal.removeEventListener("abort", onExternalAbort);
    }
  }
}

function isLocalHostname(hostname: string): boolean {
  return hostname === "127.0.0.1" || hostname === "localhost";
}

function buildApiUrl(path: string): string {
  return `${activeApiBaseUrl}${path}`;
}

function candidateApiBaseUrls(): string[] {
  const candidates = new Set<string>([activeApiBaseUrl]);
  try {
    const current = new URL(activeApiBaseUrl);
    if (isLocalHostname(current.hostname)) {
      const protocol = current.protocol;
      const hostname = current.hostname;
      for (const port of LOCAL_BACKEND_SCAN_PORTS) {
        candidates.add(`${protocol}//${hostname}:${port}`);
      }
    }
  } catch {
    // Keep explicit value only
  }
  return [...candidates];
}

async function probeApi(baseUrl: string): Promise<boolean> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 1_500);
  try {
    const response = await fetch(`${baseUrl}/api/health/live/`, {
      method: "GET",
      signal: controller.signal,
    });
    return response.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timeout);
  }
}

async function resolveReachableApiBaseUrl(): Promise<string | null> {
  const candidates = candidateApiBaseUrls();
  for (const candidate of candidates) {
    if (await probeApi(candidate)) {
      return candidate;
    }
  }
  return null;
}

function formatConnectivityMessage(error: ApiError, timeoutMs: number): ApiError {
  if (error.code !== "TIMEOUT" && error.code !== "NETWORK_ERROR") {
    return error;
  }
  const detail =
    error.code === "TIMEOUT"
      ? `Request to API timed out after ${timeoutMs}ms.`
      : "Cannot reach API.";
  return new ApiError(
    `${detail} Active base URL: ${activeApiBaseUrl}. Verify /api/health/live/ responds.`,
    error.status,
    error.code,
    error.traceId,
  );
}

async function fetchApi(path: string, init: RequestInit = {}, timeoutMs = config.requestTimeoutMs): Promise<Response> {
  try {
    return await fetchWithTimeout(buildApiUrl(path), init, timeoutMs);
  } catch (error) {
    const apiError = error instanceof ApiError ? error : new ApiError("Unexpected API error");
    if (apiError.code === "TIMEOUT" || apiError.code === "NETWORK_ERROR") {
      const discoveredBaseUrl = await resolveReachableApiBaseUrl();
      if (discoveredBaseUrl && discoveredBaseUrl !== activeApiBaseUrl) {
        logTelemetry("api.base_url_failover", {
          from: activeApiBaseUrl,
          to: discoveredBaseUrl,
          reason: apiError.code,
        });
        activeApiBaseUrl = discoveredBaseUrl;
        return fetchWithTimeout(buildApiUrl(path), init, timeoutMs);
      }
    }
    throw formatConnectivityMessage(apiError, timeoutMs);
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
    const response = await fetchApi(url, init);
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
  getActiveBaseUrl(): string {
    return activeApiBaseUrl;
  },

  async login(email: string, password: string): Promise<AuthResponse> {
    const payload = await requestWithRetry<AuthResponse>("/api/auth/login/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });

    authStorage.setUser(payload.user);
    authStorage.setTokens(payload.tokens);
    return payload;
  },

  async register(name: string, email: string, password: string): Promise<AuthResponse> {
    const payload = await requestWithRetry<AuthResponse>("/api/auth/register/", {
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

    const payload = await requestWithRetry<{ success: boolean; tokens: AuthTokens }>("/api/auth/refresh/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh: tokens.refresh }),
    });

    authStorage.setTokens(payload.tokens);
    return payload.tokens;
  },

  async askStream(question: string, options?: { signal?: AbortSignal }): Promise<Response> {
    const streamOpenTimeoutMs = 20000;
    let response = await fetchApi(
      "/api/ask/stream/",
      {
        method: "POST",
        headers: buildHeaders(),
        body: JSON.stringify({ question }),
        signal: options?.signal,
      },
      streamOpenTimeoutMs,
    );

    if (response.status === 401) {
      await this.refresh();
      response = await fetchApi(
        "/api/ask/stream/",
        {
          method: "POST",
          headers: buildHeaders(),
          body: JSON.stringify({ question }),
          signal: options?.signal,
        },
        streamOpenTimeoutMs,
      );
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
