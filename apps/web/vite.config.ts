import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const apiTarget = env.VITE_API_PROXY_TARGET || "http://localhost:8000";

  return {
    plugins: [react()],
    server: {
      proxy: {
        "/api": apiTarget,
        "/healthz": apiTarget,
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: "./src/test/setup.ts",
    },
  };
});
