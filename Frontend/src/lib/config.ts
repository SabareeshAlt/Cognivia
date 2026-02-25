import { resolveFeatureFlags } from "@/lib/feature-flags";

function requiredEnv(name: string): string {
  const value = import.meta.env[name];
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value.trim();
}

function requiredBooleanEnv(name: string): boolean {
  const value = requiredEnv(name).toLowerCase();
  if (!["true", "false", "1", "0", "yes", "no", "on", "off"].includes(value)) {
    throw new Error(`Invalid boolean environment variable: ${name}`);
  }
  return ["true", "1", "yes", "on"].includes(value);
}

function requiredIntEnv(name: string): number {
  const value = Number.parseInt(requiredEnv(name), 10);
  if (Number.isNaN(value)) {
    throw new Error(`Invalid integer environment variable: ${name}`);
  }
  return value;
}

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

    const { protocol, hostname, origin, port } = window.location;
    if ((hostname === "127.0.0.1" || hostname === "localhost") && (port === "5173" || port === "4173")) {
      return `${protocol}//${hostname}:8000`;
    }
    return stripTrailingSlash(origin);
  }

  return "http://127.0.0.1:8000";
}

function intEnvWithDefault(name: string, fallback: number): number {
  const raw = optionalEnv(name);
  if (!raw) {
    return fallback;
  }
  const value = Number.parseInt(raw, 10);
  if (Number.isNaN(value)) {
    throw new Error(`Invalid integer environment variable: ${name}`);
  }
  return value;
}

const apiBaseUrl = resolveApiBaseUrl();
const chatDisabled = requiredBooleanEnv("VITE_CHAT_DISABLED");
const canaryPercent = requiredIntEnv("VITE_CANARY_PERCENT");
const requestTimeoutMs = Math.max(intEnvWithDefault("VITE_API_TIMEOUT_MS", 30_000), 1_000);
const maxJsBundleKb = requiredIntEnv("VITE_MAX_JS_BUNDLE_KB");

export const config = {
  apiBaseUrl,
  chatDisabled,
  requestTimeoutMs,
  maxJsBundleKb,
  featureFlags: resolveFeatureFlags({
    chatDisabled,
    canaryPercent,
    enhancedStreaming: requiredEnv("VITE_FEATURE_ENHANCED_STREAMING"),
    diagnosticsPanel: requiredEnv("VITE_FEATURE_DIAGNOSTICS_PANEL"),
  }),
};
