import { defineConfig, devices } from "@playwright/test";

const noProxyLaunchOptions = {
  args: ["--no-proxy-server", "--proxy-server=direct://", "--proxy-bypass-list=*"],
};

const browserProjectNames = (process.env.AITEAMOS_E2E_BROWSER_PROJECTS ?? "chromium")
  .split(",")
  .map((name) => name.trim())
  .filter(Boolean);

const browserProjects = {
  chromium: {
    name: "chromium",
    use: { ...devices["Desktop Chrome"], launchOptions: noProxyLaunchOptions },
  },
  firefox: {
    name: "firefox",
    use: { ...devices["Desktop Firefox"], launchOptions: noProxyLaunchOptions },
  },
  webkit: {
    name: "webkit",
    use: { ...devices["Desktop Safari"], launchOptions: noProxyLaunchOptions },
  },
};

const selectedBrowserProjects = browserProjectNames.map((name) => {
  if (!(name in browserProjects)) {
    throw new Error(`Unknown AITEAMOS_E2E_BROWSER_PROJECTS entry: ${name}`);
  }
  return browserProjects[name as keyof typeof browserProjects];
});

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: {
    timeout: 20_000,
  },
  fullyParallel: false,
  retries: 0,
  use: {
    baseURL: process.env.AITEAMOS_E2E_DASHBOARD_URL ?? "http://127.0.0.1:15173",
    ignoreHTTPSErrors: true,
    launchOptions: noProxyLaunchOptions,
    trace: "retain-on-failure",
  },
  projects: selectedBrowserProjects,
});
