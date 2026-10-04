import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { componentTagger } from "lovable-tagger";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const esbuildNodeWritePlugin = {
  name: "esbuild-node-write",
  setup(build) {
    build.initialOptions.write = false;
    build.onEnd((result) => {
      if (result?.outputFiles) {
        for (const file of result.outputFiles) {
          if (file.path && !file.path.endsWith("<stdout>")) {
            fs.mkdirSync(path.dirname(file.path), { recursive: true });
            fs.writeFileSync(file.path, file.contents);
          }
        }
      }
    });
  },
};

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  root: __dirname,
  optimizeDeps: {
    esbuildOptions: {
      plugins: [esbuildNodeWritePlugin],
    },
  },
  server: {
    host: "localhost",
    port: 5173,
    strictPort: true,
    hmr: {
      overlay: false,
    },
    proxy: {
      "/api": {
        target: process.env.VITE_PROXY_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  plugins: [react(), mode === "development" && componentTagger()].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
}));
