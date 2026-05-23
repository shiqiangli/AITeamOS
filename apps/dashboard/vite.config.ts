import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { existsSync, readFileSync } from "node:fs";

const apiProxyTarget = process.env.AITEAMOS_API_PROXY_TARGET ?? "http://127.0.0.1:8765";
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
  server: {
    https: dashboardHttpsConfig(),
    proxy: {
      "/session": apiProxyTarget,
      "/workspaces": apiProxyTarget
    }
  }
});
