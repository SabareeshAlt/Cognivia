import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command:
      "VITE_API_BASE_URL=http://127.0.0.1:8000 VITE_CHAT_DISABLED=false VITE_CANARY_PERCENT=100 VITE_API_TIMEOUT_MS=10000 VITE_MAX_JS_BUNDLE_KB=550 VITE_FEATURE_ENHANCED_STREAMING=true VITE_FEATURE_DIAGNOSTICS_PANEL=false npm run dev -- --host 127.0.0.1 --port 4173",
    port: 4173,
    timeout: 120000,
    reuseExistingServer: !process.env.CI,
  },
});
