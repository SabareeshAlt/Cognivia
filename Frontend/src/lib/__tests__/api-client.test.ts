import { beforeEach, describe, expect, it, vi } from "vitest";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

describe("apiClient", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    localStorage.clear();
    sessionStorage.clear();

    vi.stubEnv("VITE_API_BASE_URL", "http://api.test");
    vi.stubEnv("VITE_CHAT_DISABLED", "false");
    vi.stubEnv("VITE_CANARY_PERCENT", "100");
    vi.stubEnv("VITE_API_TIMEOUT_MS", "1000");
    vi.stubEnv("VITE_MAX_JS_BUNDLE_KB", "550");
    vi.stubEnv("VITE_FEATURE_ENHANCED_STREAMING", "true");
    vi.stubEnv("VITE_FEATURE_DIAGNOSTICS_PANEL", "false");
  });

  it("logs in and persists user/tokens", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          success: true,
          user: { id: 1, email: "a@b.com", name: "A" },
          tokens: { access: "access", refresh: "refresh" },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const { apiClient } = await import("@/lib/api-client");
    await apiClient.login("a@b.com", "password123");

    expect(localStorage.getItem("rag_user")).toContain("a@b.com");
    expect(sessionStorage.getItem("rag_tokens")).toContain("access");
  });

  it("retries stream call after 401 using refresh", async () => {
    sessionStorage.setItem("rag_tokens", JSON.stringify({ access: "old", refresh: "refresh-token" }));

    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ error: "expired" }), { status: 401, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ success: true, tokens: { access: "new", refresh: "newr" } }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(new Response("stream", { status: 200 }));

    const { apiClient } = await import("@/lib/api-client");
    const response = await apiClient.askStream("hello");

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("surfaces timeout as ApiError", async () => {
    fetchMock.mockImplementation(
      () =>
        new Promise((_, reject) => {
          setTimeout(() => reject(new DOMException("timeout", "AbortError")), 0);
        }),
    );

    const { apiClient, ApiError } = await import("@/lib/api-client");
    await expect(apiClient.login("a@b.com", "password123")).rejects.toBeInstanceOf(ApiError);
  });
});
