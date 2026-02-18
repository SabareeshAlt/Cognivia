import { beforeEach, describe, expect, it, vi } from "vitest";

import { resolveFeatureFlags } from "@/lib/feature-flags";

vi.mock("@/lib/auth", () => ({
  authStorage: {
    getUser: () => ({ id: 1, email: "canary@example.com", name: "Canary" }),
  },
}));

describe("resolveFeatureFlags", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("resolves deterministic canary and defaults", () => {
    const flags = resolveFeatureFlags({
      chatDisabled: false,
      canaryPercent: 100,
      enhancedStreaming: "true",
      diagnosticsPanel: "false",
    });

    expect(flags.chatEnabled).toBe(true);
    expect(flags.enhancedStreaming).toBe(true);
    expect(flags.diagnosticsPanel).toBe(false);
    expect(flags.canaryUser).toBe(true);
  });

  it("applies local override", () => {
    localStorage.setItem("rag_feature_overrides", JSON.stringify({ diagnosticsPanel: true }));

    const flags = resolveFeatureFlags({
      chatDisabled: false,
      canaryPercent: 0,
      enhancedStreaming: "false",
      diagnosticsPanel: "false",
    });

    expect(flags.diagnosticsPanel).toBe(true);
  });
});
