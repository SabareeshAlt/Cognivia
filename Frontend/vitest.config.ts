import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react-swc";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: [path.resolve(__dirname, "src/test/setup.ts")],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    coverage: {
      reporter: ["text", "html", "json-summary"],
      include: [
        "src/lib/**/*.{ts,tsx}",
        "src/store/**/*.{ts,tsx}",
        "src/pages/AuthPage.tsx",
      ],
      exclude: [
        "src/lib/**/__tests__/**",
      ],
      lines: 70,
      functions: 70,
      branches: 60,
      statements: 70,
    },
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
});
