import { beforeEach, describe, expect, it, vi } from "vitest";

describe("config", () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.clear();
    sessionStorage.clear();
  });

  it("loads required values", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "http://api.test");
    vi.stubEnv("VITE_CHAT_DISABLED", "false");
    vi.stubEnv("VITE_CANARY_PERCENT", "50");
    vi.stubEnv("VITE_API_TIMEOUT_MS", "10000");
    vi.stubEnv("VITE_MAX_JS_BUNDLE_KB", "550");
    vi.stubEnv("VITE_FEATURE_ENHANCED_STREAMING", "true");
    vi.stubEnv("VITE_FEATURE_DIAGNOSTICS_PANEL", "false");

    const { config } = await import("@/lib/config");
    expect(config.apiBaseUrl).toBe("http://api.test");
    expect(config.featureFlags.chatEnabled).toBe(true);
  });

  it("falls back to runtime origin when base URL env is missing", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "");
    vi.stubEnv("VITE_CHAT_DISABLED", "false");
    vi.stubEnv("VITE_CANARY_PERCENT", "50");
    vi.stubEnv("VITE_API_TIMEOUT_MS", "30000");
    vi.stubEnv("VITE_MAX_JS_BUNDLE_KB", "550");
    vi.stubEnv("VITE_FEATURE_ENHANCED_STREAMING", "true");
    vi.stubEnv("VITE_FEATURE_DIAGNOSTICS_PANEL", "false");

    const { config } = await import("@/lib/config");
    expect(config.apiBaseUrl).toBe("http://localhost:8000");
  });
});
