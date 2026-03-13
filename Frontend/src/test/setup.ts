import "@testing-library/jest-dom";
import { expect, vi } from "vitest";
import { toHaveNoViolations } from "jest-axe";

expect.extend(toHaveNoViolations);

vi.stubEnv("VITE_API_BASE_URL", "http://127.0.0.1:8000");
vi.stubEnv("VITE_CHAT_DISABLED", "false");
vi.stubEnv("VITE_CANARY_PERCENT", "100");
vi.stubEnv("VITE_API_TIMEOUT_MS", "10000");
vi.stubEnv("VITE_MAX_JS_BUNDLE_KB", "550");
vi.stubEnv("VITE_FEATURE_ENHANCED_STREAMING", "true");
vi.stubEnv("VITE_FEATURE_DIAGNOSTICS_PANEL", "false");

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => {},
  }),
});

Object.defineProperty(HTMLElement.prototype, "scrollTo", {
  writable: true,
  value: () => {},
});
