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

const apiBaseUrl = requiredEnv("VITE_API_BASE_URL");
const chatDisabled = requiredBooleanEnv("VITE_CHAT_DISABLED");
const canaryPercent = requiredIntEnv("VITE_CANARY_PERCENT");
const requestTimeoutMs = requiredIntEnv("VITE_API_TIMEOUT_MS");
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
