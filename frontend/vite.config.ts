/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiProxyTarget = env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000";

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    test: {
      environment: "node",
      globals: true,
      include: ["src/**/*.test.ts", "tests/**/*.test.ts", "tests/**/*.test.mjs"],
      coverage: {
        provider: "v8",
        reportsDirectory: "./coverage",
        reporter: ["text-summary", "json-summary"],
        include: [
          "src/App.vue",
          "src/app/**/*.ts",
          "src/api/**/*.ts",
          "src/pages/SearchPage.vue",
          "src/composables/useApiCache.ts",
          "src/lib/**/*.ts",
          "src/shared/lib/**/*.ts",
          "src/utils/**/*.ts",
        ],
        exclude: ["src/**/*.d.ts", "src/**/__tests__/**"],
        thresholds: {
          branches: 60,
          functions: 45,
          lines: 50,
          statements: 50,
        },
      },
    },
    server: {
      host: "0.0.0.0",
      port: 5173,
      proxy: {
        "/api": {
          target: apiProxyTarget,
          changeOrigin: true,
        },
      },
    },
  };
});
