import { authStorage } from "@/lib/auth";

export interface FeatureFlags {
  chatEnabled: boolean;
  enhancedStreaming: boolean;
  diagnosticsPanel: boolean;
  canaryUser: boolean;
}

function parseBool(value: string, fallback: boolean): boolean {
  const normalized = value.trim().toLowerCase();
  if (!["true", "false", "1", "0", "yes", "no", "on", "off"].includes(normalized)) {
    console.warn(`[feature-flags] Invalid boolean flag value: ${value}. Using fallback: ${fallback}`);
    return fallback;
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

function readOverrides(): Partial<FeatureFlags> {
  const overrideRaw = localStorage.getItem("rag_feature_overrides");
  if (!overrideRaw) {
    return {};
  }

  try {
    const parsed = JSON.parse(overrideRaw) as unknown;
    if (parsed && typeof parsed === "object") {
      return parsed as Partial<FeatureFlags>;
    }
  } catch {
    console.warn("[feature-flags] Ignoring invalid localStorage override payload");
  }

  return {};
}

export function resolveFeatureFlags(config: {
  chatDisabled: boolean;
  canaryPercent: number;
  enhancedStreaming: string;
  diagnosticsPanel: string;
}): FeatureFlags {
  const override = readOverrides();

  const computed: FeatureFlags = {
    chatEnabled: !config.chatDisabled,
    enhancedStreaming: parseBool(config.enhancedStreaming, true),
    diagnosticsPanel: parseBool(config.diagnosticsPanel, false),
    canaryUser: canaryEnabled(config.canaryPercent),
  };

  return {
    ...computed,
    ...override,
  };
}