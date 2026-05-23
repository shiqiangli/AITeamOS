import { expect, test } from "@playwright/test";
import { execFile } from "node:child_process";
import { spawn, type ChildProcess, type SpawnOptions } from "node:child_process";
import { cp, mkdtemp, rm } from "node:fs/promises";
import https from "node:https";
import { tmpdir } from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

const execFileAsync = promisify(execFile);
const filename = fileURLToPath(import.meta.url);
const dirname = path.dirname(filename);
const dashboardRoot = path.resolve(dirname, "..");
const repoRoot = path.resolve(dashboardRoot, "../..");
const apiPort = Number(process.env.AITEAMOS_HTTPS_E2E_API_PORT ?? "18768");
const dashboardPort = Number(process.env.AITEAMOS_HTTPS_E2E_DASHBOARD_PORT ?? "15175");
const apiBase = `http://127.0.0.1:${apiPort}`;
const dashboardBase = `https://127.0.0.1:${dashboardPort}`;
const adminProductUser = "https-admin";
const adminProductUserToken = "https-admin-token";
const serverLogs: string[] = [];

let tempRoot = "";
let apiProcess: ChildProcess | undefined;
let dashboardProcess: ChildProcess | undefined;

function spawnManaged(label: string, command: string, args: string[], options: SpawnOptions): ChildProcess {
  const child = spawn(command, args, { ...options, stdio: ["ignore", "pipe", "pipe"] });
  child.stdout?.on("data", (chunk: Buffer) => serverLogs.push(`[${label}] ${chunk.toString()}`));
  child.stderr?.on("data", (chunk: Buffer) => serverLogs.push(`[${label}] ${chunk.toString()}`));
  return child;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function workspacePythonPath(): string {
  return [
    path.join(repoRoot, "packages/schema"),
    path.join(repoRoot, "packages/workspace"),
    path.join(repoRoot, "services/api"),
    repoRoot,
    process.env.PYTHONPATH ?? "",
  ]
    .filter(Boolean)
    .join(":");
}

function localServerEnv(): NodeJS.ProcessEnv {
  return {
    ...process.env,
    HTTP_PROXY: "",
    HTTPS_PROXY: "",
    http_proxy: "",
    https_proxy: "",
    NO_PROXY: "*",
    no_proxy: "*",
  };
}

async function waitForHttp(url: string, label: string): Promise<void> {
  const deadline = Date.now() + 40_000;
  let lastError = "";
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return;
      }
      lastError = `${response.status} ${response.statusText}`;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await sleep(300);
  }
  throw new Error(`${label} did not become ready at ${url}: ${lastError}\n${serverLogs.slice(-40).join("")}`);
}

async function waitForHttps(url: string, label: string): Promise<void> {
  const deadline = Date.now() + 40_000;
  let lastError = "";
  while (Date.now() < deadline) {
    try {
      const ready = await new Promise<boolean>((resolve, reject) => {
        const request = https.get(url, { rejectUnauthorized: false }, (response) => {
          const ok = Boolean(response.statusCode && response.statusCode >= 200 && response.statusCode < 500);
          lastError = `${response.statusCode ?? "unknown"} ${response.statusMessage ?? ""}`.trim();
          response.resume();
          resolve(ok);
        });
        request.on("error", reject);
        request.setTimeout(5_000, () => {
          request.destroy(new Error("timeout"));
        });
      });
      if (ready) {
        return;
      }
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await sleep(300);
  }
  throw new Error(`${label} did not become ready at ${url}: ${lastError}\n${serverLogs.slice(-40).join("")}`);
}

async function stopProcess(child: ChildProcess | undefined): Promise<void> {
  if (!child || child.exitCode !== null || child.signalCode !== null) {
    return;
  }
  child.kill();
  await new Promise<void>((resolve) => {
    const timer = setTimeout(() => {
      if (child.exitCode === null && child.signalCode === null) {
        child.kill("SIGKILL");
      }
      resolve();
    }, 1_000);
    child.once("exit", () => {
      clearTimeout(timer);
      resolve();
    });
  });
}

async function createSelfSignedCertificate(directory: string): Promise<{ key: string; cert: string }> {
  const key = path.join(directory, "dashboard.key.pem");
  const cert = path.join(directory, "dashboard.cert.pem");
  await execFileAsync("openssl", [
    "req",
    "-x509",
    "-newkey",
    "rsa:2048",
    "-nodes",
    "-keyout",
    key,
    "-out",
    cert,
    "-days",
    "1",
    "-subj",
    "/CN=127.0.0.1",
    "-addext",
    "subjectAltName=IP:127.0.0.1,DNS:localhost",
  ]);
  return { key, cert };
}

async function createProductUser(): Promise<void> {
  const response = await fetch(`${apiBase}/product-users`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: adminProductUser,
      actorMember: "frontend-human",
      displayName: "HTTPS Admin",
      member: "frontend-human",
      status: "active",
      roles: ["admin", "viewer"],
      sessionTokenEnv: "AITEAMOS_HTTPS_E2E_ADMIN_TOKEN",
      governanceScopes: ["memory", "skills", "permissions", "project", "employee", "assignment"],
      reason: "Create HTTPS browser ProductUser session fixture.",
    }),
  });
  if (!response.ok) {
    throw new Error(`ProductUser HTTPS fixture creation failed: ${response.status} ${await response.text()}`);
  }
}

test.beforeAll(async () => {
  tempRoot = await mkdtemp(path.join(tmpdir(), "aiteamos-dashboard-https-e2e-"));
  const tempWorkspace = path.join(tempRoot, ".aiteamos");
  await cp(path.join(repoRoot, ".aiteamos"), tempWorkspace, { recursive: true });
  const certs = await createSelfSignedCertificate(tempRoot);
  const pythonPath = workspacePythonPath();
  const apiEnv = {
    ...localServerEnv(),
    PYTHONPATH: pythonPath,
    AITEAMOS_API_TOKEN: "",
    AITEAMOS_VIEWER_TOKEN_MAP: "",
    AITEAMOS_MCP_READ_TOKEN: "",
    AITEAMOS_MCP_WRITE_TOKEN: "",
    AITEAMOS_ENV: "production",
    AITEAMOS_PUBLIC_URL: dashboardBase,
    AITEAMOS_SESSION_COOKIE_SAMESITE: "none",
    AITEAMOS_SESSION_COOKIE_SECURE: "",
    AITEAMOS_HTTPS_E2E_ADMIN_TOKEN: adminProductUserToken,
  };
  apiProcess = spawnManaged(
    "api",
    path.join(repoRoot, "aiteamos"),
    ["serve", "--workspace", tempWorkspace, "--host", "127.0.0.1", "--port", String(apiPort)],
    { cwd: repoRoot, env: apiEnv },
  );
  await waitForHttp(`${apiBase}/session`, "AITEAMOS API");
  await createProductUser();

  dashboardProcess = spawnManaged(
    "dashboard-https",
    "npm",
    ["exec", "--", "vite", "--host", "127.0.0.1", "--port", String(dashboardPort), "--strictPort"],
    {
      cwd: dashboardRoot,
      env: {
        ...localServerEnv(),
        AITEAMOS_API_PROXY_TARGET: apiBase,
        AITEAMOS_DASHBOARD_HTTPS_KEY: certs.key,
        AITEAMOS_DASHBOARD_HTTPS_CERT: certs.cert,
      },
    },
  );
  await waitForHttps(dashboardBase, "HTTPS dashboard");
});

test.afterAll(async () => {
  await stopProcess(dashboardProcess);
  await stopProcess(apiProcess);
  if (tempRoot) {
    await rm(tempRoot, { recursive: true, force: true });
  }
});

test("ProductUser Secure cookie session works through an HTTPS dashboard proxy", async ({ page }) => {
  await page.goto(`${dashboardBase}/?page=Settings`);
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.isSecureContext)).toBe(true);

  await page.getByLabel("Product Session Token").fill(adminProductUserToken);
  const loginResponsePromise = page.waitForResponse(
    (response) => response.url().includes("/session/login") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Login Product Session" }).click();
  const loginResponse = await loginResponsePromise;
  expect(loginResponse.ok()).toBe(true);
  const setCookie = (await loginResponse.headerValue("set-cookie")) ?? "";
  expect(setCookie).toContain("aiteamos_session=");
  expect(setCookie).toContain("Secure");
  expect(setCookie.toLowerCase()).toContain("samesite=none");
  expect(setCookie).not.toContain(adminProductUserToken);

  await expect(page.getByText("product-user-token")).toBeVisible();
  await expect(page.getByLabel("Session Projection").getByText(adminProductUser)).toBeVisible();
  await expect(page.getByLabel("Projection Viewer")).toBeEnabled();
  await expect.poll(() => page.evaluate(() => window.localStorage.getItem("aiteamos.apiToken"))).toBeNull();
  await expect.poll(() => page.evaluate(() => window.localStorage.getItem("aiteamos.cookieSession"))).toBe("1");
  const initialCsrf = await page.evaluate(() => window.localStorage.getItem("aiteamos.csrfToken"));
  expect(initialCsrf).toBeTruthy();

  await page.getByLabel("ProductUser Name").fill("HTTPS Managed User");
  await page.getByLabel("ProductUser Display Name").fill("HTTPS Managed User");
  await page.getByLabel("ProductUser Member").selectOption("frontend-human");
  await page.getByLabel("ProductUser Roles").fill("viewer, auditor");
  await page.getByLabel("ProductUser Token Env").fill("AITEAMOS_HTTPS_E2E_MANAGED_TOKEN");
  await page.getByLabel("ProductUser Governance Scopes").fill("memory, permissions");
  await page.getByLabel("ProductUser Actor Member").selectOption("frontend-human");
  await page.getByLabel("ProductUser Reason").fill("Create via HTTPS secure cookie session.");
  const createResponsePromise = page.waitForResponse(
    (response) => response.url().includes("/product-users") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Create Product User" }).click();
  const createResponse = await createResponsePromise;
  expect(createResponse.ok()).toBe(true);
  const createHeaders = createResponse.request().headers();
  expect(createHeaders.authorization).toBeUndefined();
  expect(createHeaders["x-aiteamos-csrf"]).toBe(initialCsrf);

  await expect.poll(async () => {
    const response = await fetch(`${apiBase}/product-users/https-managed-user`, {
      headers: { Authorization: `Bearer ${adminProductUserToken}` },
    });
    return response.ok;
  }).toBe(true);

  const renewResponsePromise = page.waitForResponse(
    (response) => response.url().includes("/session/renew") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Renew Product Session" }).click();
  const renewResponse = await renewResponsePromise;
  expect(renewResponse.ok()).toBe(true);
  expect(renewResponse.request().headers()["x-aiteamos-csrf"]).toBe(initialCsrf);
  const renewedSetCookie = (await renewResponse.headerValue("set-cookie")) ?? "";
  expect(renewedSetCookie).toContain("aiteamos_session=");
  expect(renewedSetCookie).toContain("Secure");
  expect(renewedSetCookie.toLowerCase()).toContain("samesite=none");
  expect(renewedSetCookie).not.toContain(adminProductUserToken);
  expect(renewedSetCookie).not.toBe(setCookie);
  const renewedPayload = (await renewResponse.json()) as { csrfToken?: string };
  expect(renewedPayload.csrfToken).toBeTruthy();
  expect(renewedPayload.csrfToken).not.toBe(initialCsrf);
  await expect.poll(() => page.evaluate(() => window.localStorage.getItem("aiteamos.csrfToken"))).toBe(renewedPayload.csrfToken);

  await page.getByLabel("ProductUser Name").fill("HTTPS Renewed User");
  await page.getByLabel("ProductUser Display Name").fill("HTTPS Renewed User");
  await page.getByLabel("ProductUser Member").selectOption("frontend-human");
  await page.getByLabel("ProductUser Roles").fill("viewer, auditor");
  await page.getByLabel("ProductUser Token Env").fill("AITEAMOS_HTTPS_E2E_RENEWED_TOKEN");
  await page.getByLabel("ProductUser Governance Scopes").fill("memory, permissions");
  await page.getByLabel("ProductUser Actor Member").selectOption("frontend-human");
  await page.getByLabel("ProductUser Reason").fill("Create via renewed HTTPS CSRF session.");
  const renewedCreateResponsePromise = page.waitForResponse(
    (response) => response.url().includes("/product-users") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Create Product User" }).click();
  const renewedCreateResponse = await renewedCreateResponsePromise;
  expect(renewedCreateResponse.ok(), `${renewedCreateResponse.status()} ${await renewedCreateResponse.text()}`).toBeTruthy();
  const renewedCreateHeaders = renewedCreateResponse.request().headers();
  expect(renewedCreateHeaders.authorization).toBeUndefined();
  expect(renewedCreateHeaders["x-aiteamos-csrf"]).toBe(renewedPayload.csrfToken);

  await expect.poll(async () => {
    const response = await fetch(`${apiBase}/product-users/https-renewed-user`, {
      headers: { Authorization: `Bearer ${adminProductUserToken}` },
    });
    if (!response.ok) {
      return "";
    }
    const payload = (await response.json()) as { spec?: { roles?: string[] } };
    return (payload.spec?.roles ?? []).join(",");
  }).toBe("viewer,auditor");

  const logoutResponsePromise = page.waitForResponse(
    (response) => response.url().includes("/session/logout") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Logout Product Session" }).click();
  const logoutResponse = await logoutResponsePromise;
  expect(logoutResponse.ok()).toBe(true);
  const logoutSetCookie = (await logoutResponse.headerValue("set-cookie")) ?? "";
  expect(logoutSetCookie).toContain("aiteamos_session=");
  expect(logoutSetCookie).toContain("Secure");
  expect(logoutSetCookie.toLowerCase()).toContain("samesite=none");
  await expect.poll(() => page.evaluate(() => window.localStorage.getItem("aiteamos.cookieSession"))).toBeNull();
  await expect.poll(() => page.evaluate(() => window.localStorage.getItem("aiteamos.csrfToken"))).toBeNull();
  await expect.poll(() =>
    page.evaluate(async () => {
      const response = await fetch("/session", { credentials: "same-origin" });
      return response.status;
    }),
  ).toBe(401);
});
