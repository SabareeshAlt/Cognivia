import { resolveFeatureFlags } from "@/lib/feature-flags";

const LOCAL_BACKEND_PORTS = [8000, 8001, 8002, 8003, 8004, 8005];

function optionalEnv(name: string): string | null {
  const value = import.meta.env[name];
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

function stripTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

function boolEnvWithDefault(name: string, fallback: boolean): boolean {
  const raw = optionalEnv(name);
  if (!raw) {
    return fallback;
  }
  const value = raw.toLowerCase();
  if (!["true", "false", "1", "0", "yes", "no", "on", "off"].includes(value)) {
    console.warn(`[config] Invalid boolean environment variable: ${name}. Using fallback: ${fallback}`);
    return fallback;
  }
  return ["true", "1", "yes", "on"].includes(value);
}

function intEnvWithDefault(name: string, fallback: number): number {
  const raw = optionalEnv(name);
  if (!raw) {
    return fallback;
  }
  const value = Number.parseInt(raw, 10);
  if (Number.isNaN(value)) {
    console.warn(`[config] Invalid integer environment variable: ${name}. Using fallback: ${fallback}`);
    return fallback;
  }
  return value;
}

function resolveApiBaseUrl(): string {
  const explicit = optionalEnv("VITE_API_BASE_URL");
  if (explicit) {
    return stripTrailingSlash(explicit);
  }

  if (typeof window !== "undefined") {
    const runtimeUrl = (window as Window & { __ACADEMERAG_API_BASE_URL__?: unknown }).__ACADEMERAG_API_BASE_URL__;
    if (typeof runtimeUrl === "string" && runtimeUrl.trim()) {
      return stripTrailingSlash(runtimeUrl.trim());
    }

    return stripTrailingSlash(window.location.origin);
  }

  return "http://localhost:5173";
}

const apiBaseUrl = resolveApiBaseUrl();
const chatDisabled = boolEnvWithDefault("VITE_CHAT_DISABLED", false);
const canaryPercent = Math.max(0, Math.min(100, intEnvWithDefault("VITE_CANARY_PERCENT", 100)));
const requestTimeoutMs = Math.max(intEnvWithDefault("VITE_API_TIMEOUT_MS", 30_000), 1_000);
const maxJsBundleKb = Math.max(intEnvWithDefault("VITE_MAX_JS_BUNDLE_KB", 600), 100);

export const config = {
  apiBaseUrl,
  chatDisabled,
  requestTimeoutMs,
  maxJsBundleKb,
  featureFlags: resolveFeatureFlags({
    chatDisabled,
    canaryPercent,
    enhancedStreaming: optionalEnv("VITE_FEATURE_ENHANCED_STREAMING") ?? "true",
    diagnosticsPanel: optionalEnv("VITE_FEATURE_DIAGNOSTICS_PANEL") ?? "false",
  }),
};