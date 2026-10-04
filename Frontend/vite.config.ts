import { defineConfig, PluginOption } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import fs from "fs";
import { componentTagger } from "lovable-tagger";

interface EsbuildOutputFile {
  path: string;
  contents: Uint8Array;
}

interface EsbuildBuildResult {
  outputFiles?: EsbuildOutputFile[];
}

interface EsbuildPluginBuild {
  initialOptions: { write?: boolean };
  onEnd: (callback: (result: EsbuildBuildResult) => Promise<void> | void) => void;
}

const esbuildNodeWritePlugin = {
  name: "esbuild-node-write",
  setup(build: EsbuildPluginBuild) {
    build.initialOptions.write = false;
    build.onEnd((result: EsbuildBuildResult) => {
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
  plugins: [react(), mode === "development" && componentTagger()].filter(Boolean) as PluginOption[],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
}));
