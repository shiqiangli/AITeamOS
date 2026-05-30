import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

const apiProxyTarget = process.env.AITEAMOS_API_PROXY_TARGET ?? "http://127.0.0.1:8000";
const httpsKey = process.env.AITEAMOS_DASHBOARD_HTTPS_KEY;
const httpsCert = process.env.AITEAMOS_DASHBOARD_HTTPS_CERT;

function dashboardHttpsConfig() {
  if (!httpsKey && !httpsCert) {
    return undefined;
  }
  if (!httpsKey || !httpsCert || !existsSync(httpsKey) || !existsSync(httpsCert)) {
    throw new Error("AITEAMOS_DASHBOARD_HTTPS_KEY and AITEAMOS_DASHBOARD_HTTPS_CERT must point to existing files.");
  }
  return {
    key: readFileSync(httpsKey),
    cert: readFileSync(httpsCert),
  };
}

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/__tests__/**/*.test.{ts,tsx}"],
    exclude: ["e2e/**"],
  },
  server: {
    https: dashboardHttpsConfig(),
    proxy: {
      "/api": apiProxyTarget,
      "/health": apiProxyTarget,
    }
  }
});
