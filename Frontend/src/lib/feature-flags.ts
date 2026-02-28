import { authStorage } from "@/lib/auth";

export interface FeatureFlags {
  chatEnabled: boolean;
  enhancedStreaming: boolean;
  diagnosticsPanel: boolean;
  canaryUser: boolean;
}

function parseBool(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  if (!["true", "false", "1", "0", "yes", "no", "on", "off"].includes(normalized)) {
    throw new Error(`Invalid boolean flag value: ${value}`);
  }
  return ["true", "1", "yes", "on"].includes(normalized);
}

function deterministicBucket(seed: string): number {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash << 5) - hash + seed.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash) % 100;
}

function canaryEnabled(canaryPercent: number): boolean {
  const user = authStorage.getUser();
  const seed = user?.email || "anonymous";
  return deterministicBucket(seed) < canaryPercent;
}

export function resolveFeatureFlags(config: {
  chatDisabled: boolean;
  canaryPercent: number;
  enhancedStreaming: string;
  diagnosticsPanel: string;
}): FeatureFlags {
  const overrideRaw = localStorage.getItem("rag_feature_overrides");
  const override = overrideRaw ? (JSON.parse(overrideRaw) as Partial<FeatureFlags>) : {};

  const computed: FeatureFlags = {
    chatEnabled: !config.chatDisabled,
    enhancedStreaming: parseBool(config.enhancedStreaming),
    diagnosticsPanel: parseBool(config.diagnosticsPanel),
    canaryUser: canaryEnabled(config.canaryPercent),
  };

  return {
    ...computed,
    ...override,
  };
}
