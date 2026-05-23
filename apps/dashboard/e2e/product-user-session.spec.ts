import { expect, test, type Page } from "@playwright/test";
import { spawn, type ChildProcess, type SpawnOptions } from "node:child_process";
import { createHmac } from "node:crypto";
import { cp, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const filename = fileURLToPath(import.meta.url);
const dirname = path.dirname(filename);
const dashboardRoot = path.resolve(dirname, "..");
const repoRoot = path.resolve(dashboardRoot, "../..");
const apiPort = Number(process.env.AITEAMOS_E2E_API_PORT ?? "18765");
const dashboardPort = Number(process.env.AITEAMOS_E2E_DASHBOARD_PORT ?? "15173");
const apiBase = `http://127.0.0.1:${apiPort}`;
const dashboardBase = `http://127.0.0.1:${dashboardPort}`;
const viewerProductUser = "frontend-viewer";
const adminProductUser = "frontend-admin";
const viewerProductUserToken = "frontend-viewer-token";
const adminProductUserToken = "frontend-admin-token";
const forgejoWebhookSecret = "forgejo-webhook-secret";
const giteaWebhookSecret = "gitea-webhook-secret";
const gitlabWebhookSecret = "gitlab-webhook-secret";
const githubWebhookSecret = "github-webhook-secret";
const projectId = "aiteamos";
const memberId = "frontend-human";
const assignmentId = "aiteamos-dashboard";
const serverLogs: string[] = [];

let tempRoot = "";
let humanAssistedRunId = "";
let browserWorkerRunId = "";
let forgejoProviderDeliveryId = "";
let giteaProviderDeliveryId = "";
let gitlabProviderDeliveryId = "";
let githubProviderDeliveryId = "";
let githubInstallationProviderDeliveryId = "";
let githubStaleProviderDeliveryId = "";
let githubDuplicateProviderDeliveryId = "";
let githubChangedPayloadProviderDeliveryId = "";
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

async function runWorkspacePython(script: string, env: NodeJS.ProcessEnv): Promise<string> {
  const child = spawn("python", ["-c", script], { cwd: repoRoot, env, stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "";
  let stderr = "";
  child.stdout?.on("data", (chunk: Buffer) => {
    const text = chunk.toString();
    stdout += text;
    serverLogs.push(`[fixture] ${text}`);
  });
  child.stderr?.on("data", (chunk: Buffer) => {
    const text = chunk.toString();
    stderr += text;
    serverLogs.push(`[fixture] ${text}`);
  });
  const exitCode = await new Promise<number | null>((resolve) => child.once("exit", (code) => resolve(code)));
  if (exitCode !== 0) {
    throw new Error(`workspace fixture failed with ${exitCode}: ${stderr || stdout}`);
  }
  return stdout.trim();
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

async function createProductUser({
  name,
  displayName,
  roles,
  sessionTokenEnv,
  authorizationToken,
}: {
  name: string;
  displayName: string;
  roles: string[];
  sessionTokenEnv: string;
  authorizationToken?: string;
}): Promise<void> {
  const response = await fetch(`${apiBase}/product-users`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(authorizationToken ? { Authorization: `Bearer ${authorizationToken}` } : {}),
    },
    body: JSON.stringify({
      name,
      actorMember: "frontend-human",
      displayName,
      member: "frontend-human",
      status: "active",
      roles,
      sessionTokenEnv,
      governanceScopes: ["memory", "skills", "permissions", "project", "employee", "assignment"],
      reason: `Create browser E2E ProductUser session fixture for ${name}.`,
    }),
  });
  if (!response.ok) {
    throw new Error(`ProductUser fixture ${name} creation failed: ${response.status} ${await response.text()}`);
  }
}

async function getJson(pathname: string): Promise<unknown> {
  const response = await fetch(`${apiBase}${pathname}`);
  if (!response.ok) {
    throw new Error(`${pathname} failed: ${response.status} ${await response.text()}`);
  }
  return response.json();
}

function collectApiRequests(page: Page): string[] {
  const apiRequests: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.origin === dashboardBase && url.pathname.startsWith("/")) {
      apiRequests.push(`${url.pathname}${url.search}`);
    }
  });
  return apiRequests;
}

async function useWorkspaceApiBase(page: Page): Promise<void> {
  await page.addInitScript((base) => {
    window.localStorage.setItem("aiteamos.apiBaseUrl", base);
  }, apiBase);
}

async function loginProductSession(
  page: Page,
  token: string,
  productUser: string,
  canSelectViewer: boolean,
): Promise<void> {
  await expect.poll(async () => {
    try {
      const response = await fetch(`${apiBase}/session`);
      return response.ok;
    } catch {
      return false;
    }
  }).toBe(true);
  await page.getByLabel("Product Session Token").fill(token);
  const loginResponsePromise = page.waitForResponse((response) => response.url().includes("/session/login") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Login Product Session" }).click();
  const loginResponse = await loginResponsePromise;
  expect(loginResponse.ok()).toBe(true);
  await expect(page.getByText("product-user-token")).toBeVisible();
  await expect(page.getByText(productUser)).toBeVisible();
  const projectionViewer = page.getByLabel("Projection Viewer");
  if (canSelectViewer) {
    await expect(projectionViewer).toBeEnabled();
  } else {
    await expect(projectionViewer).toBeDisabled();
  }
}

async function expectDashboardDataReady(page: Page, timeoutMs = 40_000): Promise<void> {
  await expect(page.getByText("Loading workspace data...")).toHaveCount(0, { timeout: timeoutMs });
}

async function waitForDashboardWorkspaceReload(page: Page, timeoutMs = 90_000): Promise<void> {
  await page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.origin === apiBase && url.pathname === "/runs" && response.request().method() === "GET" && response.ok();
  }, { timeout: timeoutMs });
  await expectDashboardDataReady(page, timeoutMs);
}

async function expectScopedRequestsWithoutStaleViewer(apiRequests: string[], expectedRequests: string[]): Promise<void> {
  for (const expectedRequest of expectedRequests) {
    await expect.poll(() => apiRequests.some((request) => request === expectedRequest)).toBe(true);
  }
  expect(apiRequests.some((request) => request.includes("viewerMember=architect"))).toBe(false);
}

async function expectScopedRequestsWithViewer(apiRequests: string[], expectedRequests: string[], viewer: string): Promise<void> {
  for (const expectedRequest of expectedRequests) {
    await expect.poll(() => apiRequests.some((request) => request === `${expectedRequest}?viewerMember=${viewer}`)).toBe(true);
  }
}

test.beforeAll(async () => {
  tempRoot = await mkdtemp(path.join(tmpdir(), "aiteamos-dashboard-e2e-"));
  const tempWorkspace = path.join(tempRoot, ".aiteamos");
  await cp(path.join(repoRoot, ".aiteamos"), tempWorkspace, { recursive: true });
  const pythonPath = workspacePythonPath();
  const fixtureOutput = await runWorkspacePython(
    `
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import yaml
from aiteamos_workspace import admit_external_automation_event, create_automation, create_model_profile, create_run, create_task, load_workspace

workspace = ${JSON.stringify(tempWorkspace)}
source = Path(${JSON.stringify(tempWorkspace)}).parent / "worker-source"
source.mkdir(parents=True, exist_ok=True)
(source / "packages" / "workspace").mkdir(parents=True, exist_ok=True)
(source / "packages" / "workspace" / "browser_worker_fixture.txt").write_text("browser worker fixture\\n", encoding="utf-8")
init = subprocess.run(["git", "init", "-b", "main"], cwd=source, check=False, capture_output=True, text=True)
if init.returncode != 0:
    subprocess.run(["git", "init"], cwd=source, check=True, capture_output=True, text=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=source, check=True, capture_output=True, text=True)
subprocess.run(["git", "config", "user.email", "aiteamos@example.invalid"], cwd=source, check=True)
subprocess.run(["git", "config", "user.name", "AITEAMOS Browser Worker"], cwd=source, check=True)
subprocess.run(["git", "add", "."], cwd=source, check=True)
subprocess.run(["git", "commit", "-m", "initial browser worker fixture"], cwd=source, check=True, capture_output=True, text=True)
repo_manifest = Path(workspace) / "repositories" / "aiteamos.yaml"
repo_data = yaml.safe_load(repo_manifest.read_text(encoding="utf-8"))
repo_data.setdefault("spec", {})["localPath"] = str(source)
repo_data["spec"]["url"] = source.as_uri()
repo_data["spec"]["defaultBranch"] = "main"
repo_manifest.write_text(yaml.safe_dump(repo_data, sort_keys=False), encoding="utf-8")
profile_manifest = Path(workspace) / "execution_profiles" / "digital" / "backend-digital.yaml"
profile_data = yaml.safe_load(profile_manifest.read_text(encoding="utf-8"))
allowed = profile_data.setdefault("spec", {}).setdefault("allowedModelProfiles", [])
if "local-manual-browser-worker" not in allowed:
    allowed.append("local-manual-browser-worker")
profile_manifest.write_text(yaml.safe_dump(profile_data, sort_keys=False), encoding="utf-8")
create_model_profile(
    workspace,
    name="local-manual-browser-worker",
    provider="local",
    model="manual",
    gateway="manual",
    capabilities=["managed_llm"],
)
task = create_task(
    workspace,
    title="Browser human assisted ingest fixture",
    project="aiteamos",
    assigned_member="frontend-human",
    assignment="aiteamos-dashboard",
    priority="high",
    status="TODO",
    risk_class="dashboard-browser",
    execution_mode="assisted",
    acceptance=[
        "Browser Run Detail submits assisted journal and review target.",
        "Ingest creates a pending MemoryProposal with TeamMember, Assignment, Task, and Run lineage.",
    ],
    markdown="# Browser human assisted ingest fixture\\n\\nTemporary E2E fixture generated from the copied workspace.\\n",
)
run = create_run(
    workspace,
    task_id=task.metadata.id,
    member="frontend-human",
    assignment="aiteamos-dashboard",
    mode="assisted",
    status="READY",
)
worker_task = create_task(
    workspace,
    title="Browser managed worker start fixture",
    project="aiteamos",
    assigned_member="backend-digital",
    assignment="aiteamos-backend-runtime",
    priority="normal",
    status="TODO",
    risk_class="browser-worker",
    execution_mode="managed_llm",
    acceptance=[
        "Browser Run Detail starts a governed managed worker.",
        "Worker result enters review without approving memory or bypassing permission gates.",
    ],
    markdown="# Browser managed worker start fixture\\n\\nTemporary E2E fixture generated from the copied workspace.\\n",
)
worker_run = create_run(
    workspace,
    task_id=worker_task.metadata.id,
    member="backend-digital",
    assignment="aiteamos-backend-runtime",
    model_profile="local-manual-browser-worker",
    mode="managed_llm",
    status="READY",
)

connectors_dir = Path(workspace) / "connectors"
connectors_dir.mkdir(parents=True, exist_ok=True)
(connectors_dir / "forgejo-main.yaml").write_text(
    yaml.safe_dump(
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "Connector",
            "metadata": {"name": "forgejo-main"},
            "spec": {
                "provider": "forgejo",
                "connectorType": "git",
                "ownerMember": "memory-service",
                "projects": ["aiteamos"],
                "config": {"allowedRepositories": ["example/aiteamos"]},
                "secretRefs": {"webhookSecretEnv": "AITEAMOS_E2E_FORGEJO_SECRET"},
                "permissionPolicies": ["service-memory-default"],
            },
        },
        sort_keys=False,
    ),
    encoding="utf-8",
)
(connectors_dir / "gitea-main.yaml").write_text(
    yaml.safe_dump(
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "Connector",
            "metadata": {"name": "gitea-main"},
            "spec": {
                "provider": "gitea",
                "connectorType": "issue",
                "ownerMember": "memory-service",
                "projects": ["aiteamos"],
                "config": {"allowedRepositories": ["example/aiteamos"]},
                "secretRefs": {"webhookSecretEnv": "AITEAMOS_E2E_GITEA_SECRET"},
                "permissionPolicies": ["service-memory-default"],
            },
        },
        sort_keys=False,
    ),
    encoding="utf-8",
)
(connectors_dir / "gitlab-main.yaml").write_text(
    yaml.safe_dump(
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "Connector",
            "metadata": {"name": "gitlab-main"},
            "spec": {
                "provider": "gitlab",
                "connectorType": "git",
                "ownerMember": "memory-service",
                "projects": ["aiteamos"],
                "config": {"allowedRepositories": ["example/aiteamos"]},
                "secretRefs": {"webhookSecretEnv": "AITEAMOS_E2E_GITLAB_SECRET"},
                "permissionPolicies": ["service-memory-default"],
            },
        },
        sort_keys=False,
    ),
    encoding="utf-8",
)
(connectors_dir / "github-main.yaml").write_text(
    yaml.safe_dump(
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "Connector",
            "metadata": {"name": "github-main"},
            "spec": {
                "provider": "github",
                "connectorType": "issue",
                "ownerMember": "memory-service",
                "projects": ["aiteamos"],
                "config": {
                    "allowedRepositories": ["example/aiteamos"],
                    "allowedInstallationIds": ["12345"],
                },
                "secretRefs": {"webhookSecretEnv": "AITEAMOS_E2E_GITHUB_SECRET"},
                "permissionPolicies": ["service-memory-default"],
            },
        },
        sort_keys=False,
    ),
    encoding="utf-8",
)
(connectors_dir / "github-stale-main.yaml").write_text(
    yaml.safe_dump(
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "Connector",
            "metadata": {"name": "github-stale-main"},
            "spec": {
                "provider": "github",
                "connectorType": "issue",
                "ownerMember": "memory-service",
                "projects": ["aiteamos"],
                "config": {
                    "allowedRepositories": ["example/aiteamos"],
                    "allowedInstallationIds": ["12345"],
                    "timestampHeader": "X-AITEAMOS-Timestamp",
                    "replayWindowSeconds": 60,
                },
                "secretRefs": {"webhookSecretEnv": "AITEAMOS_E2E_GITHUB_SECRET"},
                "permissionPolicies": ["service-memory-default"],
            },
        },
        sort_keys=False,
    ),
    encoding="utf-8",
)
create_automation(
    workspace,
    name="forgejo-provider-retry-browser",
    target_type="human_reminder",
    target={"toMembers": ["frontend-human"], "body": "Review Forgejo provider retry evidence."},
    owner_member="frontend-human",
    service_member="memory-service",
    project="aiteamos",
    triggers=[{"triggerType": "pr_event", "config": {"provider": "forgejo", "connector": "forgejo-main"}}],
)
create_automation(
    workspace,
    name="gitea-provider-retry-browser",
    target_type="human_reminder",
    target={"toMembers": ["frontend-human"], "body": "Review Gitea provider retry evidence."},
    owner_member="frontend-human",
    service_member="memory-service",
    project="aiteamos",
    triggers=[{"triggerType": "issue_task_event", "config": {"provider": "gitea", "connector": "gitea-main"}}],
)
create_automation(
    workspace,
    name="gitlab-provider-retry-browser",
    target_type="human_reminder",
    target={"toMembers": ["frontend-human"], "body": "Review GitLab provider retry evidence."},
    owner_member="frontend-human",
    service_member="memory-service",
    project="aiteamos",
    triggers=[{"triggerType": "pr_event", "config": {"provider": "gitlab", "connector": "gitlab-main"}}],
)
create_automation(
    workspace,
    name="github-provider-retry-browser",
    target_type="human_reminder",
    target={"toMembers": ["frontend-human"], "body": "Review GitHub provider retry evidence."},
    owner_member="frontend-human",
    service_member="memory-service",
    project="aiteamos",
    triggers=[{"triggerType": "issue_task_event", "config": {"provider": "github", "connector": "github-main"}}],
)
create_automation(
    workspace,
    name="github-stale-provider-retry-browser",
    target_type="human_reminder",
    target={"toMembers": ["frontend-human"], "body": "Review GitHub stale provider delivery evidence."},
    owner_member="frontend-human",
    service_member="memory-service",
    project="aiteamos",
    triggers=[{"triggerType": "issue_task_event", "config": {"provider": "github", "connector": "github-stale-main"}}],
)
blocked_payload = {
    "action": "opened",
    "repository": {"full_name": "evil/repo"},
    "pull_request": {
        "number": 77,
        "title": "Blocked Forgejo PR",
        "head": {"ref": "feature/replay"},
        "base": {"ref": "main"},
    },
}
blocked_raw = json.dumps(blocked_payload, sort_keys=True, separators=(",", ":"))
os.environ["AITEAMOS_E2E_FORGEJO_SECRET"] = ${JSON.stringify(forgejoWebhookSecret)}
blocked_signature = __import__("hmac").new(
    ${JSON.stringify(forgejoWebhookSecret)}.encode("utf-8"),
    blocked_raw.encode("utf-8"),
    __import__("hashlib").sha256,
).hexdigest()
try:
    admit_external_automation_event(
        workspace,
        "forgejo-provider-retry-browser",
        provider="forgejo",
        event_type="pull_request",
        connector="forgejo-main",
        headers={
            "X-Forgejo-Event": "pull_request",
            "X-Forgejo-Delivery": "forgejo-browser-delivery-blocked",
            "X-Forgejo-Signature": blocked_signature,
        },
        payload=blocked_payload,
        raw_body=blocked_raw,
    )
except ValueError:
    pass
gitea_blocked_payload = {
    "action": "opened",
    "repository": {"full_name": "evil/repo"},
    "issue": {
        "number": 88,
        "title": "Blocked Gitea issue",
        "html_url": "https://gitea.example/evil/repo/issues/88",
    },
}
gitea_blocked_raw = json.dumps(gitea_blocked_payload, sort_keys=True, separators=(",", ":"))
os.environ["AITEAMOS_E2E_GITEA_SECRET"] = ${JSON.stringify(giteaWebhookSecret)}
gitea_blocked_signature = __import__("hmac").new(
    ${JSON.stringify(giteaWebhookSecret)}.encode("utf-8"),
    gitea_blocked_raw.encode("utf-8"),
    __import__("hashlib").sha256,
).hexdigest()
try:
    admit_external_automation_event(
        workspace,
        "gitea-provider-retry-browser",
        provider="gitea",
        event_type="issues",
        connector="gitea-main",
        headers={
            "X-Gitea-Event": "issues",
            "X-Gitea-Delivery": "gitea-browser-delivery-blocked",
            "X-Gitea-Signature": gitea_blocked_signature,
        },
        payload=gitea_blocked_payload,
        raw_body=gitea_blocked_raw,
    )
except ValueError:
    pass
gitlab_blocked_payload = {
    "event_name": "merge_request",
    "project": {"path_with_namespace": "evil/repo"},
    "object_attributes": {
        "iid": 21,
        "title": "Blocked GitLab MR",
        "action": "open",
        "source_branch": "feature/replay",
        "target_branch": "main",
        "url": "https://gitlab.example/evil/repo/-/merge_requests/21",
    },
}
gitlab_blocked_raw = json.dumps(gitlab_blocked_payload, sort_keys=True, separators=(",", ":"))
os.environ["AITEAMOS_E2E_GITLAB_SECRET"] = ${JSON.stringify(gitlabWebhookSecret)}
gitlab_blocked_signature = __import__("hmac").new(
    ${JSON.stringify(gitlabWebhookSecret)}.encode("utf-8"),
    gitlab_blocked_raw.encode("utf-8"),
    __import__("hashlib").sha256,
).hexdigest()
try:
    admit_external_automation_event(
        workspace,
        "gitlab-provider-retry-browser",
        provider="gitlab",
        event_type="merge_request",
        connector="gitlab-main",
        headers={
            "X-Gitlab-Event": "merge_request",
            "X-Gitlab-Event-UUID": "gitlab-browser-delivery-blocked",
            "X-AITEAMOS-Signature": f"sha256={gitlab_blocked_signature}",
        },
        payload=gitlab_blocked_payload,
        raw_body=gitlab_blocked_raw,
    )
except ValueError:
    pass
github_blocked_payload = {
    "action": "opened",
    "repository": {"full_name": "evil/repo"},
    "installation": {"id": 12345},
    "issue": {
        "number": 16,
        "title": "Blocked GitHub issue",
        "html_url": "https://github.example/evil/repo/issues/16",
    },
}
github_blocked_raw = json.dumps(github_blocked_payload, sort_keys=True, separators=(",", ":"))
os.environ["AITEAMOS_E2E_GITHUB_SECRET"] = ${JSON.stringify(githubWebhookSecret)}
github_blocked_signature = __import__("hmac").new(
    ${JSON.stringify(githubWebhookSecret)}.encode("utf-8"),
    github_blocked_raw.encode("utf-8"),
    __import__("hashlib").sha256,
).hexdigest()
try:
    admit_external_automation_event(
        workspace,
        "github-provider-retry-browser",
        provider="github",
        event_type="issues",
        connector="github-main",
        headers={
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "github-browser-delivery-blocked",
            "X-Hub-Signature-256": f"sha256={github_blocked_signature}",
        },
        payload=github_blocked_payload,
        raw_body=github_blocked_raw,
    )
except ValueError:
    pass
github_installation_blocked_payload = {
    "action": "opened",
    "repository": {"full_name": "example/aiteamos"},
    "installation": {"id": 999},
    "issue": {
        "number": 17,
        "title": "Blocked GitHub installation",
        "html_url": "https://github.example/example/aiteamos/issues/17",
    },
}
github_installation_blocked_raw = json.dumps(github_installation_blocked_payload, sort_keys=True, separators=(",", ":"))
github_installation_blocked_signature = __import__("hmac").new(
    ${JSON.stringify(githubWebhookSecret)}.encode("utf-8"),
    github_installation_blocked_raw.encode("utf-8"),
    __import__("hashlib").sha256,
).hexdigest()
try:
    admit_external_automation_event(
        workspace,
        "github-provider-retry-browser",
        provider="github",
        event_type="issues",
        connector="github-main",
        headers={
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "github-browser-installation-blocked",
            "X-Hub-Signature-256": f"sha256={github_installation_blocked_signature}",
        },
        payload=github_installation_blocked_payload,
        raw_body=github_installation_blocked_raw,
    )
except ValueError:
    pass
github_stale_payload = {
    "action": "opened",
    "repository": {"full_name": "example/aiteamos"},
    "installation": {"id": 12345},
    "issue": {
        "number": 18,
        "title": "Stale GitHub delivery",
        "html_url": "https://github.example/example/aiteamos/issues/18",
    },
}
github_stale_raw = json.dumps(github_stale_payload, sort_keys=True, separators=(",", ":"))
github_stale_signature = __import__("hmac").new(
    ${JSON.stringify(githubWebhookSecret)}.encode("utf-8"),
    github_stale_raw.encode("utf-8"),
    __import__("hashlib").sha256,
).hexdigest()
github_stale_event_time = (datetime.now().astimezone() - timedelta(minutes=10)).isoformat(timespec="milliseconds")
github_stale_received_at = datetime.now().astimezone().isoformat(timespec="milliseconds")
try:
    admit_external_automation_event(
        workspace,
        "github-stale-provider-retry-browser",
        provider="github",
        event_type="issues",
        connector="github-stale-main",
        headers={
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "github-browser-stale-delivery-blocked",
            "X-Hub-Signature-256": f"sha256={github_stale_signature}",
            "X-AITEAMOS-Timestamp": github_stale_event_time,
        },
        payload=github_stale_payload,
        raw_body=github_stale_raw,
        received_at=github_stale_received_at,
    )
except ValueError:
    pass
github_duplicate_payload = {
    "action": "opened",
    "repository": {"full_name": "example/aiteamos"},
    "installation": {"id": 12345},
    "issue": {
        "number": 19,
        "title": "Duplicate GitHub admission",
        "html_url": "https://github.example/example/aiteamos/issues/19",
    },
}
github_duplicate_raw = json.dumps(github_duplicate_payload, sort_keys=True, separators=(",", ":"))
github_duplicate_signature = __import__("hmac").new(
    ${JSON.stringify(githubWebhookSecret)}.encode("utf-8"),
    github_duplicate_raw.encode("utf-8"),
    __import__("hashlib").sha256,
).hexdigest()
admit_external_automation_event(
    workspace,
    "github-provider-retry-browser",
    provider="github",
    event_type="issues",
    connector="github-main",
    headers={
        "X-GitHub-Event": "issues",
        "X-GitHub-Delivery": "github-browser-duplicate-delivery",
        "X-Hub-Signature-256": f"sha256={github_duplicate_signature}",
    },
    payload=github_duplicate_payload,
    raw_body=github_duplicate_raw,
)
github_changed_payload = {
    "action": "opened",
    "repository": {"full_name": "example/aiteamos"},
    "installation": {"id": 12345},
    "issue": {
        "number": 20,
        "title": "Original GitHub changed-payload admission",
        "html_url": "https://github.example/example/aiteamos/issues/20",
    },
}
github_changed_raw = json.dumps(github_changed_payload, sort_keys=True, separators=(",", ":"))
github_changed_signature = __import__("hmac").new(
    ${JSON.stringify(githubWebhookSecret)}.encode("utf-8"),
    github_changed_raw.encode("utf-8"),
    __import__("hashlib").sha256,
).hexdigest()
admit_external_automation_event(
    workspace,
    "github-provider-retry-browser",
    provider="github",
    event_type="issues",
    connector="github-main",
    headers={
        "X-GitHub-Event": "issues",
        "X-GitHub-Delivery": "github-browser-changed-payload-delivery",
        "X-Hub-Signature-256": f"sha256={github_changed_signature}",
    },
    payload=github_changed_payload,
    raw_body=github_changed_raw,
)
index = load_workspace(workspace)
forgejo_delivery = next(
    delivery
    for delivery in index.automation_provider_deliveries.values()
    if delivery.spec.provider == "forgejo" and delivery.spec.deliveryId == "forgejo-browser-delivery-blocked"
)
gitea_delivery = next(
    delivery
    for delivery in index.automation_provider_deliveries.values()
    if delivery.spec.provider == "gitea" and delivery.spec.deliveryId == "gitea-browser-delivery-blocked"
)
gitlab_delivery = next(
    delivery
    for delivery in index.automation_provider_deliveries.values()
    if delivery.spec.provider == "gitlab" and delivery.spec.deliveryId == "gitlab-browser-delivery-blocked"
)
github_delivery = next(
    delivery
    for delivery in index.automation_provider_deliveries.values()
    if delivery.spec.provider == "github" and delivery.spec.deliveryId == "github-browser-delivery-blocked"
)
github_installation_delivery = next(
    delivery
    for delivery in index.automation_provider_deliveries.values()
    if delivery.spec.provider == "github" and delivery.spec.deliveryId == "github-browser-installation-blocked"
)
github_stale_delivery = next(
    delivery
    for delivery in index.automation_provider_deliveries.values()
    if delivery.spec.provider == "github" and delivery.spec.deliveryId == "github-browser-stale-delivery-blocked"
)
github_duplicate_delivery = next(
    delivery
    for delivery in index.automation_provider_deliveries.values()
    if delivery.spec.provider == "github" and delivery.spec.deliveryId == "github-browser-duplicate-delivery"
)
github_changed_delivery = next(
    delivery
    for delivery in index.automation_provider_deliveries.values()
    if delivery.spec.provider == "github" and delivery.spec.deliveryId == "github-browser-changed-payload-delivery"
)
print(json.dumps({"task": task.metadata.id, "run": run.metadata.id, "workerRun": worker_run.metadata.id, "forgejoProviderDelivery": forgejo_delivery.object_id, "giteaProviderDelivery": gitea_delivery.object_id, "gitlabProviderDelivery": gitlab_delivery.object_id, "githubProviderDelivery": github_delivery.object_id, "githubInstallationProviderDelivery": github_installation_delivery.object_id, "githubStaleProviderDelivery": github_stale_delivery.object_id, "githubDuplicateProviderDelivery": github_duplicate_delivery.object_id, "githubChangedPayloadProviderDelivery": github_changed_delivery.object_id}))
`,
    { ...process.env, PYTHONPATH: pythonPath, AITEAMOS_E2E_FORGEJO_SECRET: forgejoWebhookSecret, AITEAMOS_E2E_GITEA_SECRET: giteaWebhookSecret, AITEAMOS_E2E_GITLAB_SECRET: gitlabWebhookSecret, AITEAMOS_E2E_GITHUB_SECRET: githubWebhookSecret },
  );
  const fixture = JSON.parse(fixtureOutput.split(/\r?\n/).at(-1) ?? "{}") as {
    run?: string;
    workerRun?: string;
    forgejoProviderDelivery?: string;
    giteaProviderDelivery?: string;
    gitlabProviderDelivery?: string;
    githubProviderDelivery?: string;
    githubInstallationProviderDelivery?: string;
    githubStaleProviderDelivery?: string;
    githubDuplicateProviderDelivery?: string;
    githubChangedPayloadProviderDelivery?: string;
  };
  if (!fixture.run || !fixture.workerRun || !fixture.forgejoProviderDelivery || !fixture.giteaProviderDelivery || !fixture.gitlabProviderDelivery || !fixture.githubProviderDelivery || !fixture.githubInstallationProviderDelivery || !fixture.githubStaleProviderDelivery || !fixture.githubDuplicateProviderDelivery || !fixture.githubChangedPayloadProviderDelivery) {
    throw new Error(`browser Run fixtures did not return run ids: ${fixtureOutput}`);
  }
  humanAssistedRunId = fixture.run;
  browserWorkerRunId = fixture.workerRun;
  forgejoProviderDeliveryId = fixture.forgejoProviderDelivery;
  giteaProviderDeliveryId = fixture.giteaProviderDelivery;
  gitlabProviderDeliveryId = fixture.gitlabProviderDelivery;
  githubProviderDeliveryId = fixture.githubProviderDelivery;
  githubInstallationProviderDeliveryId = fixture.githubInstallationProviderDelivery;
  githubStaleProviderDeliveryId = fixture.githubStaleProviderDelivery;
  githubDuplicateProviderDeliveryId = fixture.githubDuplicateProviderDelivery;
  githubChangedPayloadProviderDeliveryId = fixture.githubChangedPayloadProviderDelivery;

  const apiEnv = {
    ...process.env,
    PYTHONPATH: pythonPath,
    AITEAMOS_API_TOKEN: "",
    AITEAMOS_VIEWER_TOKEN_MAP: "",
    AITEAMOS_MCP_READ_TOKEN: "",
    AITEAMOS_MCP_WRITE_TOKEN: "",
    AITEAMOS_E2E_VIEWER_TOKEN: viewerProductUserToken,
    AITEAMOS_E2E_ADMIN_TOKEN: adminProductUserToken,
    AITEAMOS_E2E_FORGEJO_SECRET: forgejoWebhookSecret,
    AITEAMOS_E2E_GITEA_SECRET: giteaWebhookSecret,
    AITEAMOS_E2E_GITLAB_SECRET: gitlabWebhookSecret,
    AITEAMOS_E2E_GITHUB_SECRET: githubWebhookSecret,
    AITEAMOS_SESSION_COOKIE_SECURE: "",
    AITEAMOS_SESSION_COOKIE_SAMESITE: "",
  };
  apiProcess = spawnManaged(
    "api",
    path.join(repoRoot, "aiteamos"),
    ["serve", "--workspace", tempWorkspace, "--host", "127.0.0.1", "--port", String(apiPort)],
    { cwd: repoRoot, env: apiEnv },
  );
  await waitForHttp(`${apiBase}/session`, "AITEAMOS API");
  await createProductUser({
    name: adminProductUser,
    displayName: "Frontend Admin",
    roles: ["admin", "viewer"],
    sessionTokenEnv: "AITEAMOS_E2E_ADMIN_TOKEN",
  });
  await createProductUser({
    name: viewerProductUser,
    displayName: "Frontend Viewer",
    roles: ["viewer"],
    sessionTokenEnv: "AITEAMOS_E2E_VIEWER_TOKEN",
    authorizationToken: adminProductUserToken,
  });

  dashboardProcess = spawnManaged(
    "dashboard",
    "npm",
    ["exec", "--", "vite", "--host", "127.0.0.1", "--port", String(dashboardPort), "--strictPort"],
    {
      cwd: dashboardRoot,
      env: {
        ...process.env,
        AITEAMOS_API_PROXY_TARGET: apiBase,
      },
    },
  );
  await waitForHttp(dashboardBase, "dashboard");
});

test.afterAll(async () => {
  await stopProcess(dashboardProcess);
  await stopProcess(apiProcess);
  if (tempRoot) {
    await rm(tempRoot, { recursive: true, force: true });
  }
});

test("non-admin ProductUser cookie session suppresses stale URL viewers across scoped routes", async ({ page }) => {
  const apiRequests = collectApiRequests(page);

  await page.goto(`${dashboardBase}/?page=Projects&project=${projectId}&viewer=architect`);
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  apiRequests.length = 0;

  await loginProductSession(page, viewerProductUserToken, viewerProductUser, false);
  await expectScopedRequestsWithoutStaleViewer(apiRequests, [`/projects/${projectId}/skills`, `/projects/${projectId}/permissions`]);

  apiRequests.length = 0;
  await page.goto(`${dashboardBase}/?page=Employees&member=${memberId}&assignment=${assignmentId}&viewer=architect`);
  await expect(page.getByRole("heading", { name: "Employees" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByText("Assignment Detail").first()).toBeVisible();
  await expectScopedRequestsWithoutStaleViewer(apiRequests, [
    `/members/${memberId}/skills`,
    `/members/${memberId}/permissions`,
    `/assignments/${assignmentId}/skills`,
    `/assignments/${assignmentId}/permissions`,
  ]);

  apiRequests.length = 0;
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${dashboardBase}/?page=Employees&member=${memberId}&assignment=${assignmentId}&viewer=architect`);
  await expect(page.getByRole("heading", { name: "Employees" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByLabel("Projection Viewer")).toBeDisabled();
  await expectScopedRequestsWithoutStaleViewer(apiRequests, [
    `/members/${memberId}/skills`,
    `/members/${memberId}/permissions`,
    `/assignments/${assignmentId}/skills`,
    `/assignments/${assignmentId}/permissions`,
  ]);

  expect(page.url()).toContain("viewer=architect");
});

test("admin ProductUser cookie session preserves selected viewers across scoped routes", async ({ page }) => {
  const apiRequests = collectApiRequests(page);

  await page.goto(`${dashboardBase}/?page=Projects&project=${projectId}&viewer=architect`);
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  apiRequests.length = 0;

  await loginProductSession(page, adminProductUserToken, adminProductUser, true);
  await expect(page.getByText("admin-selected-viewer")).toBeVisible();
  await expect(page.getByLabel("Projection Viewer")).toHaveValue("architect");
  await expectScopedRequestsWithViewer(
    apiRequests,
    [
      "/memory/entries",
      "/skills",
      "/permissions",
      `/projects/${projectId}/skills`,
      `/projects/${projectId}/permissions`,
    ],
    "architect",
  );

  apiRequests.length = 0;
  await page.goto(`${dashboardBase}/?page=Employees&member=${memberId}&assignment=${assignmentId}&viewer=architect`);
  await expect(page.getByRole("heading", { name: "Employees" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByText("Assignment Detail").first()).toBeVisible();
  await expect(page.getByLabel("Projection Viewer")).toBeEnabled();
  await expectScopedRequestsWithViewer(
    apiRequests,
    [
      `/members/${memberId}/skills`,
      `/members/${memberId}/permissions`,
      `/assignments/${assignmentId}/skills`,
      `/assignments/${assignmentId}/permissions`,
    ],
    "architect",
  );
});

test("human Run Detail assisted ingest promotes reviewed memory into context in the browser", async ({ page }) => {
  const proposalTitle = `Browser assisted ingest discipline ${Date.now()}`;
  const reviewTargetUrl = `https://example.invalid/aiteamos/${humanAssistedRunId}`;

  await page.goto(`${dashboardBase}/?page=Runs&run=${humanAssistedRunId}`);
  await expect(page.getByRole("heading", { name: "Runs" })).toBeVisible();
  await loginProductSession(page, adminProductUserToken, adminProductUser, true);
  await expectDashboardDataReady(page);
  await expect(page.getByText("Assisted Ingest Workbench")).toBeVisible();
  await expect(page.getByText("frontend-human").first()).toBeVisible();
  await expect(page.getByText("human").first()).toBeVisible();

  const submit = page.getByRole("button", { name: "Ingest Assisted Output" });
  await expect(submit).toBeDisabled();
  await page.getByLabel("Journal").fill("Human browser assisted result from the IDE workbench.");
  await page.getByLabel("Review Target URL").fill(reviewTargetUrl);
  await page.getByLabel("Test Log").fill("browser assisted ingest e2e passed");
  await page.getByLabel("Memory Title").fill(proposalTitle);
  await page.getByLabel("Memory Content").fill("Human assisted browser results must return through Run Detail before review.");
  await expect(submit).toBeEnabled();

  const ingestResponsePromise = page.waitForResponse(
    (response) => response.url().includes(`/runs/${humanAssistedRunId}/assisted-ingest`) && response.request().method() === "POST",
  );
  await submit.click();
  const ingestResponse = await ingestResponsePromise;
  expect(ingestResponse.ok()).toBe(true);

  await expect.poll(async () => {
    const run = (await getJson(`/runs/${humanAssistedRunId}`)) as { spec?: { status?: string; ingest?: { memoryProposal?: string } } };
    return `${run.spec?.status ?? ""}:${run.spec?.ingest?.memoryProposal ?? ""}`;
  }).toMatch(/^REVIEW:MP-/);

  await expect.poll(async () => {
    const proposals = (await getJson("/memory/proposals")) as Array<{ id?: string; spec?: { title?: string; member?: string; assignment?: string; sourceRun?: string; status?: string } }>;
    const proposal = proposals.find((item) => item.spec?.title === proposalTitle);
    return proposal && proposal.spec?.member === memberId && proposal.spec?.assignment === assignmentId && proposal.spec?.sourceRun === humanAssistedRunId && proposal.spec?.status === "pending-review"
      ? proposal.id ?? ""
      : "";
  }).not.toBe("");
  const proposals = (await getJson("/memory/proposals")) as Array<{ id?: string; spec?: { title?: string } }>;
  const proposalId = proposals.find((item) => item.spec?.title === proposalTitle)?.id ?? "";
  expect(proposalId).not.toBe("");

  await page.goto(`${dashboardBase}/?page=Memory&memory=${proposalId}`);
  await expect(page.getByRole("heading", { name: "Memory" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByText(proposalTitle)).toBeVisible();
  await expect(page.getByText("pending-review").first()).toBeVisible();

  const approvalResponsePromise = page.waitForResponse(
    (response) => response.url().includes(`/memory/proposals/${proposalId}/approve`) && response.request().method() === "POST",
  );
  await page.getByLabel("Memory Approval Reason").fill("E2E approved assisted ingest memory");
  await page.getByRole("button", { name: "Approve Proposal With Review" }).click();
  const approvalResponse = await approvalResponsePromise;
  expect(approvalResponse.ok()).toBe(true);
  const approvalPayload = (await approvalResponse.json()) as { spec?: { approvedMemory?: string }; memory?: { id?: string } };
  const approvedMemoryId = approvalPayload.memory?.id ?? approvalPayload.spec?.approvedMemory ?? "";
  expect(approvedMemoryId).toMatch(/^MEM-/);

  await expect.poll(async () => {
    const entries = (await getJson("/memory/entries")) as Array<{ id?: string; spec?: { lifecycle?: string; title?: string } }>;
    const entry = entries.find((item) => item.id === approvedMemoryId);
    return `${entry?.id ?? ""}:${entry?.spec?.lifecycle ?? ""}`;
  }).toBe(`${approvedMemoryId}:active`);

  await expect.poll(async () => {
    const preview = (await getJson(`/runs/${humanAssistedRunId}/context-preview`)) as unknown;
    return JSON.stringify(preview).includes(approvedMemoryId);
  }).toBe(true);

  await page.goto(`${dashboardBase}/?page=Memory&memory=${approvedMemoryId}&viewer=${memberId}`);
  await expect(page.getByRole("heading", { name: "Memory" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByLabel("Projection Viewer")).toHaveValue(memberId);
  await expect(page.getByText(proposalTitle)).toBeVisible();
  await expect(page.getByText("Selected Memory Context Injection")).toBeVisible();
  await expect(page.getByText(approvedMemoryId).first()).toBeVisible();
});

test("Run Detail starts a ready managed worker in the browser without bypassing review", async ({ page }) => {
  test.slow();

  await useWorkspaceApiBase(page);
  await page.goto(`${dashboardBase}/?page=Runs&run=${browserWorkerRunId}`);
  await expect(page.getByRole("heading", { name: "Runs" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByRole("heading", { name: "Managed Worker Start Console" })).toBeVisible();
  await expect(page.getByText("Worker can be started.").first()).toBeVisible();
  await expect(page.getByText(browserWorkerRunId).first()).toBeVisible();

  const startResponsePromise = page.waitForResponse(
    (response) => response.url().includes(`/runs/${browserWorkerRunId}/worker/start`) && response.request().method() === "POST",
    { timeout: 90_000 },
  );
  const dashboardReloadPromise = waitForDashboardWorkspaceReload(page, 120_000);
  await page.getByRole("button", { name: "Start Managed Worker" }).click();
  const startResponse = await startResponsePromise;
  expect(startResponse.ok(), `${startResponse.status()} ${await startResponse.text()}\n${serverLogs.slice(-80).join("")}`).toBeTruthy();

  await expect.poll(async () => {
    const run = (await getJson(`/runs/${browserWorkerRunId}`)) as {
      spec?: { status?: string; worker?: { stage?: string; attemptId?: string }; reviewTarget?: { type?: string }; outputs?: Array<{ type?: string }> };
    };
    const outputTypes = new Set((run.spec?.outputs ?? []).map((item) => item.type));
    return `${run.spec?.status ?? ""}:${run.spec?.worker?.stage ?? ""}:${run.spec?.reviewTarget?.type ?? ""}:${outputTypes.has("worker_output")}:${outputTypes.has("review_target")}`;
  }, { timeout: 90_000 }).toBe("REVIEW:review:external_review:true:true");

  await dashboardReloadPromise;
  await expectDashboardDataReady(page, 120_000);
  await expect(page.getByText("external_review").first()).toBeVisible();
  await expect(page.getByText("worker_output").first()).toBeVisible();
  await expect(page.getByText(/ATTEMPT/).first()).toBeVisible();
});

test("automation control plane creates a draft task plan and opens TaskPlan detail in the browser", async ({ page }) => {
  test.slow();
  const automationId = "demo-task-planning";

  await useWorkspaceApiBase(page);
  await page.goto(`${dashboardBase}/?page=Automations&automation=${automationId}&project=${projectId}`);
  await expect(page.getByRole("heading", { name: "Automations" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByRole("heading", { name: "Automation Control Plane" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Automation Action Console" })).toBeVisible();
  await expect(page.getByText(automationId).first()).toBeVisible();

  await page.getByLabel("Automation Actor Member").fill("manager");
  await page.getByLabel("Automation Trigger Type").fill("manual");
  await page.getByLabel("Automation Source").fill("browser-task-plan-e2e");

  const triggerResponsePromise = page.waitForResponse(
    (response) => response.url().includes(`/automations/${automationId}/trigger`) && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: /^Trigger$/ }).click();
  const triggerResponse = await triggerResponsePromise;
  expect(triggerResponse.ok()).toBe(true);
  const triggerPayload = (await triggerResponse.json()) as { id?: string; spec?: { status?: string } };
  const automationRunId = triggerPayload.id ?? "";
  expect(automationRunId).toMatch(/^ARUN-/);
  expect(triggerPayload.spec?.status).toBe("queued");

  await expect.poll(async () => {
    const automationRuns = (await getJson("/automations/runs")) as Array<{ id?: string; spec?: { status?: string } }>;
    return automationRuns.find((record) => record.id === automationRunId)?.spec?.status ?? "";
  }).toBe("queued");
  await page.getByRole("button", { name: "Refresh" }).click();
  await expectDashboardDataReady(page);
  await expect(page.getByText(automationRunId).first()).toBeVisible();
  await page.getByLabel("Queued Automation Run").selectOption(automationRunId);
  await page.getByLabel("Executor Member").fill("team-execution-service");

  const executeResponsePromise = page.waitForResponse(
    (response) => response.url().includes(`/automations/runs/${automationRunId}/execute`) && response.request().method() === "POST",
  );
  const dashboardReloadPromise = waitForDashboardWorkspaceReload(page);
  await page.getByRole("button", { name: "Execute Automation Run" }).click();
  const executeResponse = await executeResponsePromise;
  expect(executeResponse.ok()).toBe(true);
  const executePayload = (await executeResponse.json()) as { spec?: { status?: string; createdTaskPlan?: string; createdTask?: string; createdRun?: string } };
  const createdTaskPlanId = executePayload.spec?.createdTaskPlan ?? "";
  expect(executePayload.spec?.status).toBe("succeeded");
  expect(createdTaskPlanId).toMatch(/^PLAN-/);
  expect(executePayload.spec?.createdTask ?? "").toBe("");
  expect(executePayload.spec?.createdRun ?? "").toBe("");

  await expect.poll(async () => {
    const taskPlans = (await getJson("/task-plans")) as Array<{ id?: string; spec?: { status?: string; subtasks?: unknown[] } }>;
    const taskPlan = taskPlans.find((record) => record.id === createdTaskPlanId);
    return `${taskPlan?.spec?.status ?? ""}:${taskPlan?.spec?.subtasks?.length ?? 0}`;
  }).toBe("draft:2");

  await dashboardReloadPromise;
  await page.goto(`${dashboardBase}/?page=Tasks&taskPlan=${createdTaskPlanId}`);
  await expectDashboardDataReady(page, 90_000);
  await expect(page).toHaveURL(new RegExp(`page=Tasks.*taskPlan=${createdTaskPlanId}`));
  await expect(page.getByRole("heading", { name: "Tasks", level: 2 })).toBeVisible();
  await expect(page.getByText(createdTaskPlanId).first()).toBeVisible();
  await expect(page.getByText("TaskPlan Detail")).toBeVisible();
  await expect(page.getByText("TaskPlan Main Path")).toBeVisible();
  await expect(page.getByText("Automation must not start worker execution or approve memory.").first()).toBeVisible();
});

test("automation control plane creates an assisted hybrid run and opens assisted ingest gates in the browser", async ({ page }) => {
  test.slow();
  const automationId = "demo-hybrid-assist-run";

  await useWorkspaceApiBase(page);
  await page.goto(`${dashboardBase}/?page=Automations&automation=${automationId}&project=${projectId}`);
  await expect(page.getByRole("heading", { name: "Automations" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByRole("heading", { name: "Automation Control Plane" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Automation Action Console" })).toBeVisible();
  await expect(page.getByText(automationId).first()).toBeVisible();

  await page.getByLabel("Automation Actor Member").fill("frontend-human");
  await page.getByLabel("Automation Trigger Type").fill("manual");
  await page.getByLabel("Automation Source").fill("browser-hybrid-e2e");

  const triggerResponsePromise = page.waitForResponse(
    (response) => response.url().includes(`/automations/${automationId}/trigger`) && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: /^Trigger$/ }).click();
  const triggerResponse = await triggerResponsePromise;
  expect(triggerResponse.ok()).toBe(true);
  const triggerPayload = (await triggerResponse.json()) as { id?: string; spec?: { status?: string } };
  const automationRunId = triggerPayload.id ?? "";
  expect(automationRunId).toMatch(/^ARUN-/);
  expect(triggerPayload.spec?.status).toBe("queued");

  await expect.poll(async () => {
    const automationRuns = (await getJson("/automations/runs")) as Array<{ id?: string; spec?: { status?: string } }>;
    return automationRuns.find((record) => record.id === automationRunId)?.spec?.status ?? "";
  }).toBe("queued");
  await page.getByRole("button", { name: "Refresh" }).click();
  await expectDashboardDataReady(page);
  await expect(page.getByText(automationRunId).first()).toBeVisible();
  await page.getByLabel("Queued Automation Run").selectOption(automationRunId);
  await page.getByLabel("Executor Member").fill("team-execution-service");

  const executeResponsePromise = page.waitForResponse(
    (response) => response.url().includes(`/automations/runs/${automationRunId}/execute`) && response.request().method() === "POST",
  );
  const dashboardReloadPromise = waitForDashboardWorkspaceReload(page);
  await page.getByRole("button", { name: "Execute Automation Run" }).click();
  const executeResponse = await executeResponsePromise;
  expect(executeResponse.ok()).toBe(true);
  const executePayload = (await executeResponse.json()) as { spec?: { status?: string; createdTask?: string; createdRun?: string; createdTaskPlan?: string } };
  const createdRunId = executePayload.spec?.createdRun ?? "";
  expect(executePayload.spec?.status).toBe("succeeded");
  expect(executePayload.spec?.createdTask ?? "").toMatch(/^TASK-/);
  expect(createdRunId).toMatch(/^RUN-/);
  expect(executePayload.spec?.createdTaskPlan ?? "").toBe("");

  await expect.poll(async () => {
    const run = (await getJson(`/runs/${createdRunId}`)) as { spec?: { member?: string; assignment?: string; mode?: string; status?: string; worker?: unknown } };
    return `${run.spec?.member ?? ""}:${run.spec?.assignment ?? ""}:${run.spec?.mode ?? ""}:${run.spec?.status ?? ""}:${run.spec?.worker ? "worker-started" : "worker-gated"}`;
  }).toBe("frontend-human:aiteamos-dashboard:assisted:READY:worker-gated");

  await dashboardReloadPromise;
  await expect.poll(async () => {
    const runs = (await getJson("/runs")) as Array<{ id?: string }>;
    return runs.some((record) => record.id === createdRunId);
  }).toBe(true);
  await page.goto(`${dashboardBase}/?page=Runs&run=${createdRunId}`);
  await expectDashboardDataReady(page, 90_000);
  await expect(page).toHaveURL(new RegExp(`page=Runs.*run=${createdRunId}`));
  await expect(page.getByRole("heading", { name: "Runs", level: 2 })).toBeVisible();
  await expect(page.getByText(createdRunId).first()).toBeVisible();
  await expect(page.getByText("Assisted Ingest Workbench")).toBeVisible();
  await expect(page.getByText("Selected Run Worker Readiness")).toBeVisible();
  await expect(page.getByText("Run mode assisted is not a managed worker mode; use assisted/manual ingest instead.").first()).toBeVisible();
  await expect(page.getByText("Selected Run Permission Outcome")).toBeVisible();
});

test("automation control plane creates a managed digital run and opens worker gates in the browser", async ({ page }) => {
  test.slow();
  const automationId = "demo-digital-execution-run";

  await useWorkspaceApiBase(page);
  await page.goto(`${dashboardBase}/?page=Automations&automation=${automationId}&project=${projectId}`);
  await expect(page.getByRole("heading", { name: "Automations" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByRole("heading", { name: "Automation Control Plane" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Automation Action Console" })).toBeVisible();
  await expect(page.getByText(automationId).first()).toBeVisible();

  await page.getByLabel("Automation Actor Member").fill("manager");
  await page.getByLabel("Automation Trigger Type").fill("manual");
  await page.getByLabel("Automation Source").fill("browser-e2e");

  const triggerResponsePromise = page.waitForResponse(
    (response) => response.url().includes(`/automations/${automationId}/trigger`) && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: /^Trigger$/ }).click();
  const triggerResponse = await triggerResponsePromise;
  expect(triggerResponse.ok()).toBe(true);
  const triggerPayload = (await triggerResponse.json()) as { id?: string; spec?: { status?: string } };
  const automationRunId = triggerPayload.id ?? "";
  expect(automationRunId).toMatch(/^ARUN-/);
  expect(triggerPayload.spec?.status).toBe("queued");

  await expect.poll(async () => {
    const automationRuns = (await getJson("/automations/runs")) as Array<{ id?: string; spec?: { status?: string } }>;
    return automationRuns.find((record) => record.id === automationRunId)?.spec?.status ?? "";
  }).toBe("queued");
  await page.getByRole("button", { name: "Refresh" }).click();
  await expectDashboardDataReady(page);
  await expect(page.getByText(automationRunId).first()).toBeVisible();
  await page.getByLabel("Queued Automation Run").selectOption(automationRunId);
  await page.getByLabel("Executor Member").fill("team-execution-service");

  const executeResponsePromise = page.waitForResponse(
    (response) => response.url().includes(`/automations/runs/${automationRunId}/execute`) && response.request().method() === "POST",
  );
  const dashboardReloadPromise = waitForDashboardWorkspaceReload(page);
  await page.getByRole("button", { name: "Execute Automation Run" }).click();
  const executeResponse = await executeResponsePromise;
  expect(executeResponse.ok()).toBe(true);
  const executePayload = (await executeResponse.json()) as { spec?: { status?: string; createdTask?: string; createdRun?: string } };
  const createdRunId = executePayload.spec?.createdRun ?? "";
  expect(executePayload.spec?.status).toBe("succeeded");
  expect(executePayload.spec?.createdTask ?? "").toMatch(/^TASK-/);
  expect(createdRunId).toMatch(/^RUN-/);

  await expect.poll(async () => {
    const run = (await getJson(`/runs/${createdRunId}`)) as { spec?: { member?: string; assignment?: string; mode?: string; status?: string; worker?: unknown } };
    return `${run.spec?.member ?? ""}:${run.spec?.assignment ?? ""}:${run.spec?.mode ?? ""}:${run.spec?.status ?? ""}:${run.spec?.worker ? "worker-started" : "worker-gated"}`;
  }).toBe("backend-digital:aiteamos-backend-runtime:managed_llm:READY:worker-gated");

  await dashboardReloadPromise;
  await page.goto(`${dashboardBase}/?page=Runs&run=${createdRunId}`);
  await expectDashboardDataReady(page, 90_000);
  await expect(page).toHaveURL(new RegExp(`page=Runs.*run=${createdRunId}`));
  await expect(page.getByRole("heading", { name: "Runs", level: 2 })).toBeVisible();
  await expect(page.getByText(createdRunId).first()).toBeVisible();
  await expect(page.getByText("Selected Run Worker Readiness")).toBeVisible();
  await expect(page.getByText("Selected Run Permission Outcome")).toBeVisible();
  await expect(page.getByText("Required provider secret env OPENAI_API_KEY is missing.").first()).toBeVisible();
});

test("Forgejo provider delivery retry opens replay lineage in the browser", async ({ page }) => {
  test.slow();
  const redeliveryId = `forgejo-browser-delivery-retry-${Date.now()}`;
  const rawBody = JSON.stringify({
    action: "opened",
    repository: { full_name: "example/aiteamos" },
    pull_request: {
      number: 77,
      title: "Allowed Forgejo browser PR",
      head: { ref: "feature/replay" },
      base: { ref: "main" },
      html_url: "https://forgejo.example/example/aiteamos/pulls/77",
    },
  });
  const signature = createHmac("sha256", forgejoWebhookSecret).update(rawBody).digest("hex");

  await useWorkspaceApiBase(page);
  await page.goto(`${dashboardBase}/?page=Automations&automation=forgejo-provider-retry-browser&delivery=${forgejoProviderDeliveryId}`);
  await expect(page.getByRole("heading", { name: "Automations" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByRole("heading", { name: "Provider Delivery Detail" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Provider Delivery Retry" })).toBeVisible();
  const retryPanel = page.locator(".panel").filter({ has: page.getByRole("heading", { name: "Provider Delivery Retry" }) });
  await expect(page.getByText("X-Forgejo-Event + X-Forgejo-Delivery").first()).toBeVisible();
  await expect(page.getByText(forgejoProviderDeliveryId).first()).toBeVisible();
  await expect(page.getByText("forgejo-browser-delivery-blocked").first()).toBeVisible();

  await retryPanel.locator("select").first().selectOption(forgejoProviderDeliveryId);
  await retryPanel.getByLabel("Retry Actor").fill("frontend-human");
  await retryPanel.getByLabel("Retry Reason").fill("Reviewed Forgejo browser delivery and requested a provider redelivery.");
  await retryPanel.getByLabel("Redelivery ID Header").fill(redeliveryId);
  await retryPanel.getByLabel("Retry Signature").fill(signature);
  await retryPanel.getByLabel("Retry Raw Body").fill(rawBody);

  const retryResponsePromise = page.waitForResponse(
    (response) => response.url().includes(`/automations/provider-deliveries/${forgejoProviderDeliveryId}/retry`) && response.request().method() === "POST",
    { timeout: 60_000 },
  );
  await retryPanel.getByRole("button", { name: "Request Provider Delivery Retry" }).click();
  const retryResponse = await retryResponsePromise;
  expect(retryResponse.ok(), `${retryResponse.status()} ${await retryResponse.text()}`).toBeTruthy();
  const retryPayload = (await retryResponse.json()) as {
    delivery?: { spec?: { retryDelivery?: string; retryAutomationTriggerEvent?: string; retryStatus?: string } };
    retryDelivery?: { id?: string; spec?: { deliveryId?: string; provider?: string; safeHeaders?: Record<string, string> } };
    event?: { id?: string; spec?: { triggerType?: string; source?: string } };
  };
  const retryDeliveryId = retryPayload.retryDelivery?.id ?? retryPayload.delivery?.spec?.retryDelivery ?? "";
  expect(retryDeliveryId).toMatch(/^ADELIVERY-/);
  expect(retryPayload.delivery?.spec?.retryStatus).toBe("admitted");
  expect(retryPayload.retryDelivery?.spec?.provider).toBe("forgejo");
  expect(retryPayload.retryDelivery?.spec?.deliveryId).toBe(redeliveryId);
  expect(retryPayload.retryDelivery?.spec?.safeHeaders?.["x-forgejo-event"]).toBe("pull_request");
  expect(retryPayload.retryDelivery?.spec?.safeHeaders?.["x-forgejo-delivery"]).toBe(redeliveryId);
  expect(retryPayload.event?.spec?.triggerType).toBe("pr_event");
  expect(retryPayload.event?.spec?.source).toBe("git_provider");

  await page.goto(`${dashboardBase}/?page=Automations&automation=forgejo-provider-retry-browser&delivery=${forgejoProviderDeliveryId}`);
  await expectDashboardDataReady(page, 90_000);
  await expect(page.getByRole("heading", { name: "Provider Delivery Detail" })).toBeVisible();
  await expect(page.getByText(forgejoProviderDeliveryId).first()).toBeVisible();
  await expect(page.getByText(retryDeliveryId).first()).toBeVisible();
  await expect(page.getByText(redeliveryId).first()).toBeVisible();
  await expect(page.getByText("retry-admitted").first()).toBeVisible();
  const decisionAuditPanel = page.locator(".subpanel").filter({ has: page.getByRole("heading", { name: "Decision Audit" }) });
  await expect(decisionAuditPanel.getByText("frontend-human").first()).toBeVisible();
});

test("Gitea provider issue delivery retry opens replay lineage in the browser", async ({ page }) => {
  test.slow();
  const redeliveryId = `gitea-browser-delivery-retry-${Date.now()}`;
  const rawBody = JSON.stringify({
    action: "opened",
    repository: { full_name: "example/aiteamos" },
    issue: {
      number: 88,
      title: "Allowed Gitea browser issue",
      html_url: "https://gitea.example/example/aiteamos/issues/88",
    },
  });
  const signature = createHmac("sha256", giteaWebhookSecret).update(rawBody).digest("hex");

  await useWorkspaceApiBase(page);
  await page.goto(`${dashboardBase}/?page=Automations&automation=gitea-provider-retry-browser&delivery=${giteaProviderDeliveryId}`);
  await expect(page.getByRole("heading", { name: "Automations" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByRole("heading", { name: "Provider Delivery Detail" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Provider Delivery Retry" })).toBeVisible();
  const retryPanel = page.locator(".panel").filter({ has: page.getByRole("heading", { name: "Provider Delivery Retry" }) });
  await expect(page.getByText("X-Gitea-Event + X-Gitea-Delivery").first()).toBeVisible();
  await expect(page.getByText(giteaProviderDeliveryId).first()).toBeVisible();
  await expect(page.getByText("gitea-browser-delivery-blocked").first()).toBeVisible();

  await retryPanel.locator("select").first().selectOption(giteaProviderDeliveryId);
  await retryPanel.getByLabel("Retry Actor").fill("frontend-human");
  await retryPanel.getByLabel("Retry Reason").fill("Reviewed Gitea browser delivery and requested a provider redelivery.");
  await retryPanel.getByLabel("Redelivery ID Header").fill(redeliveryId);
  await retryPanel.getByLabel("Retry Signature").fill(signature);
  await retryPanel.getByLabel("Retry Raw Body").fill(rawBody);

  const retryResponsePromise = page.waitForResponse(
    (response) => response.url().includes(`/automations/provider-deliveries/${giteaProviderDeliveryId}/retry`) && response.request().method() === "POST",
    { timeout: 60_000 },
  );
  await retryPanel.getByRole("button", { name: "Request Provider Delivery Retry" }).click();
  const retryResponse = await retryResponsePromise;
  expect(retryResponse.ok(), `${retryResponse.status()} ${await retryResponse.text()}`).toBeTruthy();
  const retryPayload = (await retryResponse.json()) as {
    delivery?: { spec?: { retryDelivery?: string; retryAutomationTriggerEvent?: string; retryStatus?: string } };
    retryDelivery?: { id?: string; spec?: { deliveryId?: string; provider?: string; safeHeaders?: Record<string, string> } };
    event?: { id?: string; spec?: { triggerType?: string; source?: string; payload?: { normalized?: Record<string, string> } } };
  };
  const retryDeliveryId = retryPayload.retryDelivery?.id ?? retryPayload.delivery?.spec?.retryDelivery ?? "";
  expect(retryDeliveryId).toMatch(/^ADELIVERY-/);
  expect(retryPayload.delivery?.spec?.retryStatus).toBe("admitted");
  expect(retryPayload.retryDelivery?.spec?.provider).toBe("gitea");
  expect(retryPayload.retryDelivery?.spec?.deliveryId).toBe(redeliveryId);
  expect(retryPayload.retryDelivery?.spec?.safeHeaders?.["x-gitea-event"]).toBe("issues");
  expect(retryPayload.retryDelivery?.spec?.safeHeaders?.["x-gitea-delivery"]).toBe(redeliveryId);
  expect(retryPayload.event?.spec?.triggerType).toBe("issue_task_event");
  expect(retryPayload.event?.spec?.source).toBe("git_provider");
  expect(retryPayload.event?.spec?.payload?.normalized?.repository).toBe("example/aiteamos");
  expect(retryPayload.event?.spec?.payload?.normalized?.number).toBe("88");

  await page.goto(`${dashboardBase}/?page=Automations&automation=gitea-provider-retry-browser&delivery=${giteaProviderDeliveryId}`);
  await expectDashboardDataReady(page, 90_000);
  await expect(page.getByRole("heading", { name: "Provider Delivery Detail" })).toBeVisible();
  await expect(page.getByText(giteaProviderDeliveryId).first()).toBeVisible();
  await expect(page.getByText(retryDeliveryId).first()).toBeVisible();
  await expect(page.getByText(redeliveryId).first()).toBeVisible();
  await expect(page.getByText("retry-admitted").first()).toBeVisible();
  const decisionAuditPanel = page.locator(".subpanel").filter({ has: page.getByRole("heading", { name: "Decision Audit" }) });
  await expect(decisionAuditPanel.getByText("frontend-human").first()).toBeVisible();
});

test("Gitea bad-signature webhook admission rejects without delivery event or run side effects in the browser", async ({ page }) => {
  test.slow();
  const badDeliveryId = "gitea-browser-bad-signature-delivery";
  const rawBody = JSON.stringify({
    action: "opened",
    repository: { full_name: "example/aiteamos" },
    issue: {
      number: 89,
      title: "Bad signature Gitea admission",
      html_url: "https://gitea.example/example/aiteamos/issues/89",
    },
  });

  const deliveriesBefore = (await getJson("/automations/gitea-provider-retry-browser/provider-deliveries")) as Array<{
    id?: string;
    spec?: { deliveryId?: string; automationTriggerEvent?: string; automationRun?: string };
  }>;
  const eventsBefore = (await getJson("/automations/gitea-provider-retry-browser/events")) as Array<{
    id?: string;
    spec?: { dedupeKey?: string; payload?: { deliveryId?: string } };
  }>;
  const runsBefore = (await getJson("/automations/gitea-provider-retry-browser/runs")) as Array<{
    id?: string;
    spec?: { sourceEvent?: { dedupeKey?: string } };
  }>;
  expect(deliveriesBefore.some((record) => record.spec?.deliveryId === badDeliveryId)).toBeFalsy();
  expect(eventsBefore.some((record) => record.spec?.dedupeKey === `gitea:issues:${badDeliveryId}`)).toBeFalsy();
  expect(runsBefore.some((record) => record.spec?.sourceEvent?.dedupeKey === `gitea:issues:${badDeliveryId}`)).toBeFalsy();

  await useWorkspaceApiBase(page);
  await page.goto(`${dashboardBase}/?page=Automations&automation=gitea-provider-retry-browser`);
  await expect(page.getByRole("heading", { name: "Automations" })).toBeVisible();
  await expectDashboardDataReady(page);
  const webhookPanel = page.locator(".panel").filter({ has: page.getByRole("heading", { name: "Webhook Admission Console" }) });

  await webhookPanel.getByLabel("Webhook Automation Target").selectOption("gitea-provider-retry-browser");
  await webhookPanel.getByLabel("Webhook Provider").fill("gitea");
  await webhookPanel.getByLabel("Webhook Connector").fill("gitea-main");
  await webhookPanel.getByLabel("Webhook Event Type").fill("issues");
  await webhookPanel.getByLabel("Webhook Delivery ID").fill(badDeliveryId);
  await webhookPanel.getByLabel("Webhook Signature").fill("bad-signature");
  await webhookPanel.getByLabel("Webhook Raw Body").fill(rawBody);

  const dialogPromise = page.waitForEvent("dialog", { timeout: 60_000 }).then(async (dialog) => {
    const message = dialog.message();
    await dialog.dismiss();
    return message;
  });
  const admissionResponsePromise = page.waitForResponse(
    (response) => response.url().includes("/automations/gitea-provider-retry-browser/admit-webhook") && response.request().method() === "POST",
    { timeout: 60_000 },
  );
  await webhookPanel.getByRole("button", { name: "Admit Webhook Delivery" }).click();
  const admissionResponse = await admissionResponsePromise;
  expect(admissionResponse.status()).toBe(400);
  await expect(dialogPromise).resolves.toContain("webhook signature verification failed");
  await expect(webhookPanel.getByText(/Webhook admission failed:/)).toBeVisible();
  await expect(webhookPanel.getByText("blocked").first()).toBeVisible();
  await expect(webhookPanel.getByText(badDeliveryId).first()).toBeVisible();

  const deliveriesAfter = (await getJson("/automations/gitea-provider-retry-browser/provider-deliveries")) as Array<{
    id?: string;
    spec?: { deliveryId?: string; automationTriggerEvent?: string; automationRun?: string };
  }>;
  const eventsAfter = (await getJson("/automations/gitea-provider-retry-browser/events")) as Array<{
    id?: string;
    spec?: { dedupeKey?: string; payload?: { deliveryId?: string } };
  }>;
  const runsAfter = (await getJson("/automations/gitea-provider-retry-browser/runs")) as Array<{
    id?: string;
    spec?: { sourceEvent?: { dedupeKey?: string } };
  }>;
  expect(deliveriesAfter.map((record) => record.id).sort()).toEqual(deliveriesBefore.map((record) => record.id).sort());
  expect(eventsAfter.map((record) => record.id).sort()).toEqual(eventsBefore.map((record) => record.id).sort());
  expect(runsAfter.map((record) => record.id).sort()).toEqual(runsBefore.map((record) => record.id).sort());
  expect(deliveriesAfter.some((record) => record.spec?.deliveryId === badDeliveryId)).toBeFalsy();
  expect(eventsAfter.some((record) => record.spec?.dedupeKey === `gitea:issues:${badDeliveryId}`)).toBeFalsy();
  expect(runsAfter.some((record) => record.spec?.sourceEvent?.dedupeKey === `gitea:issues:${badDeliveryId}`)).toBeFalsy();
});

test("GitLab provider merge request delivery retry opens replay lineage in the browser", async ({ page }) => {
  test.slow();
  const redeliveryId = `gitlab-browser-delivery-retry-${Date.now()}`;
  const rawBody = JSON.stringify({
    event_name: "merge_request",
    project: { path_with_namespace: "example/aiteamos" },
    object_attributes: {
      iid: 21,
      title: "Allowed GitLab browser MR",
      action: "open",
      source_branch: "feature/replay",
      target_branch: "main",
      url: "https://gitlab.example/example/aiteamos/-/merge_requests/21",
    },
  });
  const signature = `sha256=${createHmac("sha256", gitlabWebhookSecret).update(rawBody).digest("hex")}`;

  await useWorkspaceApiBase(page);
  await page.goto(`${dashboardBase}/?page=Automations&automation=gitlab-provider-retry-browser&delivery=${gitlabProviderDeliveryId}`);
  await expect(page.getByRole("heading", { name: "Automations" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByRole("heading", { name: "Provider Delivery Detail" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Provider Delivery Retry" })).toBeVisible();
  const retryPanel = page.locator(".panel").filter({ has: page.getByRole("heading", { name: "Provider Delivery Retry" }) });
  await expect(page.getByText("X-Gitlab-Event + X-Gitlab-Event-UUID").first()).toBeVisible();
  await expect(page.getByText(gitlabProviderDeliveryId).first()).toBeVisible();
  await expect(page.getByText("gitlab-browser-delivery-blocked").first()).toBeVisible();

  await retryPanel.locator("select").first().selectOption(gitlabProviderDeliveryId);
  await retryPanel.getByLabel("Retry Actor").fill("frontend-human");
  await retryPanel.getByLabel("Retry Reason").fill("Reviewed GitLab browser delivery and requested a provider redelivery.");
  await retryPanel.getByLabel("Redelivery ID Header").fill(redeliveryId);
  await retryPanel.getByLabel("Retry Signature").fill(signature);
  await retryPanel.getByLabel("Retry Raw Body").fill(rawBody);

  const retryResponsePromise = page.waitForResponse(
    (response) => response.url().includes(`/automations/provider-deliveries/${gitlabProviderDeliveryId}/retry`) && response.request().method() === "POST",
    { timeout: 60_000 },
  );
  await retryPanel.getByRole("button", { name: "Request Provider Delivery Retry" }).click();
  const retryResponse = await retryResponsePromise;
  expect(retryResponse.ok(), `${retryResponse.status()} ${await retryResponse.text()}`).toBeTruthy();
  const retryPayload = (await retryResponse.json()) as {
    delivery?: { spec?: { retryDelivery?: string; retryAutomationTriggerEvent?: string; retryStatus?: string } };
    retryDelivery?: { id?: string; spec?: { deliveryId?: string; provider?: string; safeHeaders?: Record<string, string> } };
    event?: { id?: string; spec?: { triggerType?: string; source?: string; payload?: { normalized?: Record<string, string> } } };
  };
  const retryDeliveryId = retryPayload.retryDelivery?.id ?? retryPayload.delivery?.spec?.retryDelivery ?? "";
  expect(retryDeliveryId).toMatch(/^ADELIVERY-/);
  expect(retryPayload.delivery?.spec?.retryStatus).toBe("admitted");
  expect(retryPayload.retryDelivery?.spec?.provider).toBe("gitlab");
  expect(retryPayload.retryDelivery?.spec?.deliveryId).toBe(redeliveryId);
  expect(retryPayload.retryDelivery?.spec?.safeHeaders?.["x-gitlab-event"]).toBe("merge_request");
  expect(retryPayload.retryDelivery?.spec?.safeHeaders?.["x-gitlab-event-uuid"]).toBe(redeliveryId);
  expect(retryPayload.event?.spec?.triggerType).toBe("pr_event");
  expect(retryPayload.event?.spec?.source).toBe("git_provider");
  expect(retryPayload.event?.spec?.payload?.normalized?.repository).toBe("example/aiteamos");
  expect(retryPayload.event?.spec?.payload?.normalized?.number).toBe("21");
  expect(retryPayload.event?.spec?.payload?.normalized?.headRef).toBe("feature/replay");
  expect(retryPayload.event?.spec?.payload?.normalized?.baseRef).toBe("main");

  await page.goto(`${dashboardBase}/?page=Automations&automation=gitlab-provider-retry-browser&delivery=${gitlabProviderDeliveryId}`);
  await expectDashboardDataReady(page, 90_000);
  await expect(page.getByRole("heading", { name: "Provider Delivery Detail" })).toBeVisible();
  await expect(page.getByText(gitlabProviderDeliveryId).first()).toBeVisible();
  await expect(page.getByText(retryDeliveryId).first()).toBeVisible();
  await expect(page.getByText(redeliveryId).first()).toBeVisible();
  await expect(page.getByText("retry-admitted").first()).toBeVisible();
  const decisionAuditPanel = page.locator(".subpanel").filter({ has: page.getByRole("heading", { name: "Decision Audit" }) });
  await expect(decisionAuditPanel.getByText("frontend-human").first()).toBeVisible();
});

test("GitLab bad-signature webhook admission rejects without delivery event or run side effects in the browser", async ({ page }) => {
  test.slow();
  const badDeliveryId = "gitlab-browser-bad-signature-delivery";
  const rawBody = JSON.stringify({
    event_name: "merge_request",
    object_attributes: {
      action: "open",
      iid: 22,
      source_branch: "feature/bad-signature",
      target_branch: "main",
      title: "Bad signature GitLab MR",
      url: "https://gitlab.example/example/aiteamos/-/merge_requests/22",
    },
    project: { path_with_namespace: "example/aiteamos" },
  });

  const deliveriesBefore = (await getJson("/automations/gitlab-provider-retry-browser/provider-deliveries")) as Array<{
    id?: string;
    spec?: { deliveryId?: string; automationTriggerEvent?: string; automationRun?: string };
  }>;
  const eventsBefore = (await getJson("/automations/gitlab-provider-retry-browser/events")) as Array<{
    id?: string;
    spec?: { dedupeKey?: string; payload?: { deliveryId?: string } };
  }>;
  const runsBefore = (await getJson("/automations/gitlab-provider-retry-browser/runs")) as Array<{
    id?: string;
    spec?: { sourceEvent?: { dedupeKey?: string } };
  }>;
  expect(deliveriesBefore.some((record) => record.spec?.deliveryId === badDeliveryId)).toBeFalsy();
  expect(eventsBefore.some((record) => record.spec?.dedupeKey === `gitlab:merge_request:${badDeliveryId}`)).toBeFalsy();
  expect(runsBefore.some((record) => record.spec?.sourceEvent?.dedupeKey === `gitlab:merge_request:${badDeliveryId}`)).toBeFalsy();

  await useWorkspaceApiBase(page);
  await page.goto(`${dashboardBase}/?page=Automations&automation=gitlab-provider-retry-browser`);
  await expect(page.getByRole("heading", { name: "Automations" })).toBeVisible();
  await expectDashboardDataReady(page);
  const webhookPanel = page.locator(".panel").filter({ has: page.getByRole("heading", { name: "Webhook Admission Console" }) });

  await webhookPanel.getByLabel("Webhook Automation Target").selectOption("gitlab-provider-retry-browser");
  await webhookPanel.getByLabel("Webhook Provider").fill("gitlab");
  await webhookPanel.getByLabel("Webhook Connector").fill("gitlab-main");
  await webhookPanel.getByLabel("Webhook Event Type").fill("merge_request");
  await webhookPanel.getByLabel("Webhook Delivery ID").fill(badDeliveryId);
  await webhookPanel.getByLabel("Webhook Signature").fill("sha256=bad-signature");
  await webhookPanel.getByLabel("Webhook Raw Body").fill(rawBody);

  const dialogPromise = page.waitForEvent("dialog", { timeout: 60_000 }).then(async (dialog) => {
    const message = dialog.message();
    await dialog.dismiss();
    return message;
  });
  const admissionResponsePromise = page.waitForResponse(
    (response) => response.url().includes("/automations/gitlab-provider-retry-browser/admit-webhook") && response.request().method() === "POST",
    { timeout: 60_000 },
  );
  await webhookPanel.getByRole("button", { name: "Admit Webhook Delivery" }).click();
  const admissionResponse = await admissionResponsePromise;
  expect(admissionResponse.status()).toBe(400);
  await expect(dialogPromise).resolves.toContain("webhook signature verification failed");

  const deliveriesAfter = (await getJson("/automations/gitlab-provider-retry-browser/provider-deliveries")) as Array<{
    id?: string;
    spec?: { deliveryId?: string; automationTriggerEvent?: string; automationRun?: string };
  }>;
  const eventsAfter = (await getJson("/automations/gitlab-provider-retry-browser/events")) as Array<{
    id?: string;
    spec?: { dedupeKey?: string; payload?: { deliveryId?: string } };
  }>;
  const runsAfter = (await getJson("/automations/gitlab-provider-retry-browser/runs")) as Array<{
    id?: string;
    spec?: { sourceEvent?: { dedupeKey?: string } };
  }>;
  expect(deliveriesAfter.map((record) => record.id).sort()).toEqual(deliveriesBefore.map((record) => record.id).sort());
  expect(eventsAfter.map((record) => record.id).sort()).toEqual(eventsBefore.map((record) => record.id).sort());
  expect(runsAfter.map((record) => record.id).sort()).toEqual(runsBefore.map((record) => record.id).sort());
  expect(deliveriesAfter.some((record) => record.spec?.deliveryId === badDeliveryId)).toBeFalsy();
  expect(eventsAfter.some((record) => record.spec?.dedupeKey === `gitlab:merge_request:${badDeliveryId}`)).toBeFalsy();
  expect(runsAfter.some((record) => record.spec?.sourceEvent?.dedupeKey === `gitlab:merge_request:${badDeliveryId}`)).toBeFalsy();
});

test("GitHub provider issue delivery retry opens replay lineage in the browser", async ({ page }) => {
  test.slow();
  const redeliveryId = `github-browser-delivery-retry-${Date.now()}`;
  const rawBody = JSON.stringify({
    action: "opened",
    repository: { full_name: "example/aiteamos" },
    installation: { id: 12345 },
    issue: {
      number: 16,
      title: "Allowed GitHub browser issue",
      html_url: "https://github.example/example/aiteamos/issues/16",
    },
  });
  const signature = `sha256=${createHmac("sha256", githubWebhookSecret).update(rawBody).digest("hex")}`;

  await useWorkspaceApiBase(page);
  await page.goto(`${dashboardBase}/?page=Automations&automation=github-provider-retry-browser&delivery=${githubProviderDeliveryId}`);
  await expect(page.getByRole("heading", { name: "Automations" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByRole("heading", { name: "Provider Delivery Detail" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Provider Delivery Retry" })).toBeVisible();
  const retryPanel = page.locator(".panel").filter({ has: page.getByRole("heading", { name: "Provider Delivery Retry" }) });
  await expect(page.getByText("X-GitHub-Event + X-GitHub-Delivery").first()).toBeVisible();
  await expect(page.getByText(githubProviderDeliveryId).first()).toBeVisible();
  await expect(page.getByText("github-browser-delivery-blocked").first()).toBeVisible();

  await retryPanel.locator("select").first().selectOption(githubProviderDeliveryId);
  await retryPanel.getByLabel("Retry Actor").fill("frontend-human");
  await retryPanel.getByLabel("Retry Reason").fill("Reviewed GitHub browser delivery and requested a provider redelivery.");
  await retryPanel.getByLabel("Redelivery ID Header").fill(redeliveryId);
  await retryPanel.getByLabel("Retry Signature").fill(signature);
  await retryPanel.getByLabel("Retry Raw Body").fill(rawBody);

  const retryResponsePromise = page.waitForResponse(
    (response) => response.url().includes(`/automations/provider-deliveries/${githubProviderDeliveryId}/retry`) && response.request().method() === "POST",
    { timeout: 60_000 },
  );
  await retryPanel.getByRole("button", { name: "Request Provider Delivery Retry" }).click();
  const retryResponse = await retryResponsePromise;
  expect(retryResponse.ok(), `${retryResponse.status()} ${await retryResponse.text()}`).toBeTruthy();
  const retryPayload = (await retryResponse.json()) as {
    delivery?: { spec?: { retryDelivery?: string; retryAutomationTriggerEvent?: string; retryStatus?: string } };
    retryDelivery?: { id?: string; spec?: { deliveryId?: string; provider?: string; safeHeaders?: Record<string, string> } };
    event?: { id?: string; spec?: { triggerType?: string; source?: string; payload?: { normalized?: Record<string, string> } } };
  };
  const retryDeliveryId = retryPayload.retryDelivery?.id ?? retryPayload.delivery?.spec?.retryDelivery ?? "";
  expect(retryDeliveryId).toMatch(/^ADELIVERY-/);
  expect(retryPayload.delivery?.spec?.retryStatus).toBe("admitted");
  expect(retryPayload.retryDelivery?.spec?.provider).toBe("github");
  expect(retryPayload.retryDelivery?.spec?.deliveryId).toBe(redeliveryId);
  expect(retryPayload.retryDelivery?.spec?.safeHeaders?.["x-github-event"]).toBe("issues");
  expect(retryPayload.retryDelivery?.spec?.safeHeaders?.["x-github-delivery"]).toBe(redeliveryId);
  expect(retryPayload.event?.spec?.triggerType).toBe("issue_task_event");
  expect(retryPayload.event?.spec?.source).toBe("git_provider");
  expect(retryPayload.event?.spec?.payload?.normalized?.repository).toBe("example/aiteamos");
  expect(retryPayload.event?.spec?.payload?.normalized?.number).toBe("16");
  expect(retryPayload.event?.spec?.payload?.normalized?.title).toBe("Allowed GitHub browser issue");

  await page.goto(`${dashboardBase}/?page=Automations&automation=github-provider-retry-browser&delivery=${githubProviderDeliveryId}`);
  await expectDashboardDataReady(page, 90_000);
  await expect(page.getByRole("heading", { name: "Provider Delivery Detail" })).toBeVisible();
  await expect(page.getByText(githubProviderDeliveryId).first()).toBeVisible();
  await expect(page.getByText(retryDeliveryId).first()).toBeVisible();
  await expect(page.getByText(redeliveryId).first()).toBeVisible();
  await expect(page.getByText("retry-admitted").first()).toBeVisible();
  const decisionAuditPanel = page.locator(".subpanel").filter({ has: page.getByRole("heading", { name: "Decision Audit" }) });
  await expect(decisionAuditPanel.getByText("frontend-human").first()).toBeVisible();
});

test("GitHub provider delivery retry keeps blocked installation evidence in the browser", async ({ page }) => {
  test.slow();
  const redeliveryId = `github-browser-installation-retry-${Date.now()}`;
  const rawBody = JSON.stringify({
    action: "opened",
    repository: { full_name: "example/aiteamos" },
    installation: { id: 999 },
    issue: {
      number: 17,
      title: "Still blocked GitHub installation",
      html_url: "https://github.example/example/aiteamos/issues/17",
    },
  });
  const signature = `sha256=${createHmac("sha256", githubWebhookSecret).update(rawBody).digest("hex")}`;

  await useWorkspaceApiBase(page);
  await page.goto(`${dashboardBase}/?page=Automations&automation=github-provider-retry-browser&delivery=${githubInstallationProviderDeliveryId}`);
  await expect(page.getByRole("heading", { name: "Automations" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByRole("heading", { name: "Provider Delivery Detail" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Provider Delivery Retry" })).toBeVisible();
  const retryPanel = page.locator(".panel").filter({ has: page.getByRole("heading", { name: "Provider Delivery Retry" }) });
  await expect(page.getByText("github-browser-installation-blocked").first()).toBeVisible();
  await expect(page.getByText("does not allow installation 999").first()).toBeVisible();

  await retryPanel.locator("select").first().selectOption(githubInstallationProviderDeliveryId);
  await retryPanel.getByLabel("Retry Actor").fill("frontend-human");
  await retryPanel.getByLabel("Retry Reason").fill("Reviewed GitHub installation evidence and kept the redelivery blocked.");
  await retryPanel.getByLabel("Redelivery ID Header").fill(redeliveryId);
  await retryPanel.getByLabel("Retry Signature").fill(signature);
  await retryPanel.getByLabel("Retry Raw Body").fill(rawBody);

  const retryResponsePromise = page.waitForResponse(
    (response) => response.url().includes(`/automations/provider-deliveries/${githubInstallationProviderDeliveryId}/retry`) && response.request().method() === "POST",
    { timeout: 60_000 },
  );
  await retryPanel.getByRole("button", { name: "Request Provider Delivery Retry" }).click();
  const retryResponse = await retryResponsePromise;
  expect(retryResponse.ok(), `${retryResponse.status()} ${await retryResponse.text()}`).toBeTruthy();
  const retryPayload = (await retryResponse.json()) as {
    admitted?: boolean;
    requested?: boolean;
    blockers?: string[];
    delivery?: { spec?: { retryStatus?: string; retryDelivery?: string; retryAutomationTriggerEvent?: string; retryAttempts?: Array<{ outcome?: string; blockers?: string[] }> } };
    retryDelivery?: unknown;
    event?: unknown;
    run?: unknown;
  };
  expect(retryPayload.admitted).toBe(false);
  expect(retryPayload.requested).toBe(true);
  expect(retryPayload.retryDelivery ?? null).toBeNull();
  expect(retryPayload.event ?? null).toBeNull();
  expect(retryPayload.run ?? null).toBeNull();
  expect(retryPayload.delivery?.spec?.retryStatus).toBe("blocked");
  expect(retryPayload.delivery?.spec?.retryDelivery ?? "").toBe("");
  expect(retryPayload.delivery?.spec?.retryAutomationTriggerEvent ?? "").toBe("");
  expect(retryPayload.delivery?.spec?.retryAttempts?.at(-1)?.outcome).toBe("blocked");
  expect(retryPayload.blockers?.join(" ")).toContain("does not allow installation 999");
  expect((retryPayload.delivery?.spec?.retryAttempts?.at(-1)?.blockers ?? []).join(" ")).toContain("does not allow installation 999");

  await page.goto(`${dashboardBase}/?page=Automations&automation=github-provider-retry-browser&delivery=${githubInstallationProviderDeliveryId}`);
  await expectDashboardDataReady(page, 90_000);
  await expect(page.getByRole("heading", { name: "Provider Delivery Detail" })).toBeVisible();
  await expect(page.getByText(githubInstallationProviderDeliveryId).first()).toBeVisible();
  await expect(page.getByText("retry-blocked").first()).toBeVisible();
  await expect(page.getByText("does not allow installation 999").first()).toBeVisible();
  await expect(page.getByText("No retry delivery linked.")).toBeVisible();
  await expect(page.getByText("No retry trigger event linked.")).toBeVisible();
  await expect(page.getByText("No retry automation run linked.")).toBeVisible();
  const decisionAuditPanel = page.locator(".subpanel").filter({ has: page.getByRole("heading", { name: "Decision Audit" }) });
  await expect(decisionAuditPanel.getByText("frontend-human").first()).toBeVisible();
});

test("GitHub stale provider delivery retry refreshes timestamp evidence in the browser", async ({ page }) => {
  test.slow();
  const redeliveryId = `github-browser-stale-retry-${Date.now()}`;
  const freshTimestamp = new Date().toISOString();
  const rawBody = JSON.stringify({
    action: "opened",
    repository: { full_name: "example/aiteamos" },
    installation: { id: 12345 },
    issue: {
      number: 18,
      title: "Fresh GitHub timestamp retry",
      html_url: "https://github.example/example/aiteamos/issues/18",
    },
  });
  const signature = `sha256=${createHmac("sha256", githubWebhookSecret).update(rawBody).digest("hex")}`;

  await useWorkspaceApiBase(page);
  await page.goto(`${dashboardBase}/?page=Automations&automation=github-stale-provider-retry-browser&delivery=${githubStaleProviderDeliveryId}`);
  await expect(page.getByRole("heading", { name: "Automations" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByRole("heading", { name: "Provider Delivery Detail" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Provider Delivery Retry" })).toBeVisible();
  const retryPanel = page.locator(".panel").filter({ has: page.getByRole("heading", { name: "Provider Delivery Retry" }) });
  await expect(page.getByText("github-browser-stale-delivery-blocked").first()).toBeVisible();
  await expect(page.getByText("stale").first()).toBeVisible();
  await expect(page.getByText("outside replay window of 60 seconds").first()).toBeVisible();

  await retryPanel.locator("select").first().selectOption(githubStaleProviderDeliveryId);
  await retryPanel.getByLabel("Retry Actor").fill("frontend-human");
  await retryPanel.getByLabel("Retry Reason").fill("Reviewed stale GitHub delivery and requested a fresh provider timestamp redelivery.");
  await retryPanel.getByLabel("Redelivery ID Header").fill(redeliveryId);
  await retryPanel.getByLabel("Retry Timestamp Header").fill("X-AITEAMOS-Timestamp");
  await retryPanel.getByLabel("Retry Timestamp", { exact: true }).fill(freshTimestamp);
  await retryPanel.getByLabel("Retry Signature").fill(signature);
  await retryPanel.getByLabel("Retry Raw Body").fill(rawBody);

  const retryResponsePromise = page.waitForResponse(
    (response) => response.url().includes(`/automations/provider-deliveries/${githubStaleProviderDeliveryId}/retry`) && response.request().method() === "POST",
    { timeout: 60_000 },
  );
  await retryPanel.getByRole("button", { name: "Request Provider Delivery Retry" }).click();
  const retryResponse = await retryResponsePromise;
  expect(retryResponse.ok(), `${retryResponse.status()} ${await retryResponse.text()}`).toBeTruthy();
  const retryPayload = (await retryResponse.json()) as {
    admitted?: boolean;
    requested?: boolean;
    delivery?: { spec?: { retryStatus?: string; retryDelivery?: string; retryAutomationTriggerEvent?: string; retryAttempts?: Array<{ outcome?: string; payloadDigest?: string }> } };
    retryDelivery?: { id?: string; spec?: { deliveryId?: string; replayStatus?: string; admissionStatus?: string; safeHeaders?: Record<string, string> } };
    event?: { id?: string; spec?: { triggerType?: string; source?: string; payload?: { normalized?: Record<string, string> } } };
    run?: { id?: string };
  };
  const retryDeliveryId = retryPayload.retryDelivery?.id ?? retryPayload.delivery?.spec?.retryDelivery ?? "";
  expect(retryPayload.admitted).toBe(true);
  expect(retryPayload.requested).toBe(true);
  expect(retryDeliveryId).toMatch(/^ADELIVERY-/);
  expect(retryPayload.delivery?.spec?.retryStatus).toBe("admitted");
  expect(retryPayload.delivery?.spec?.retryAttempts?.at(-1)?.outcome).toBe("admitted");
  expect(retryPayload.retryDelivery?.spec?.deliveryId).toBe(redeliveryId);
  expect(retryPayload.retryDelivery?.spec?.replayStatus).toBe("accepted");
  expect(retryPayload.retryDelivery?.spec?.admissionStatus).toBe("accepted");
  expect(retryPayload.retryDelivery?.spec?.safeHeaders?.["x-aiteamos-timestamp"]).toBe(freshTimestamp);
  expect(retryPayload.event?.spec?.triggerType).toBe("issue_task_event");
  expect(retryPayload.event?.spec?.source).toBe("git_provider");
  expect(retryPayload.event?.spec?.payload?.normalized?.repository).toBe("example/aiteamos");
  expect(retryPayload.event?.spec?.payload?.normalized?.number).toBe("18");
  expect(retryPayload.event?.spec?.payload?.normalized?.title).toBe("Fresh GitHub timestamp retry");
  expect(retryPayload.run?.id ?? "").toMatch(/^ARUN-/);

  await page.goto(`${dashboardBase}/?page=Automations&automation=github-stale-provider-retry-browser&delivery=${githubStaleProviderDeliveryId}`);
  await expectDashboardDataReady(page, 90_000);
  await expect(page.getByRole("heading", { name: "Provider Delivery Detail" })).toBeVisible();
  await expect(page.getByText(githubStaleProviderDeliveryId).first()).toBeVisible();
  await expect(page.getByText("github-browser-stale-delivery-blocked").first()).toBeVisible();
  await expect(page.getByText("outside replay window of 60 seconds").first()).toBeVisible();
  await expect(page.getByText("retry-admitted").first()).toBeVisible();
  await expect(page.getByText(retryDeliveryId).first()).toBeVisible();
  await expect(page.getByText(redeliveryId).first()).toBeVisible();
  await expect(page.getByText(freshTimestamp).first()).toBeVisible();
  const decisionAuditPanel = page.locator(".subpanel").filter({ has: page.getByRole("heading", { name: "Decision Audit" }) });
  await expect(decisionAuditPanel.getByText("frontend-human").first()).toBeVisible();
});

test("GitHub duplicate webhook admission keeps original event and run lineage in the browser", async ({ page }) => {
  test.slow();
  const rawBody = JSON.stringify({
    action: "opened",
    installation: { id: 12345 },
    issue: {
      html_url: "https://github.example/example/aiteamos/issues/19",
      number: 19,
      title: "Duplicate GitHub admission",
    },
    repository: { full_name: "example/aiteamos" },
  });
  const signature = `sha256=${createHmac("sha256", githubWebhookSecret).update(rawBody).digest("hex")}`;

  const deliveriesBefore = (await getJson("/automations/github-provider-retry-browser/provider-deliveries")) as Array<{
    id?: string;
    spec?: {
      admissionStatus?: string;
      replayStatus?: string;
      automationTriggerEvent?: string;
      automationRun?: string;
      attemptCount?: number;
    };
  }>;
  const originalDelivery = deliveriesBefore.find((record) => record.id === githubDuplicateProviderDeliveryId);
  expect(originalDelivery?.spec?.admissionStatus).toBe("accepted");
  expect(originalDelivery?.spec?.replayStatus).toBe("accepted");
  const originalEventId = originalDelivery?.spec?.automationTriggerEvent ?? "";
  const originalRunId = originalDelivery?.spec?.automationRun ?? "";
  expect(originalEventId).toMatch(/^AEVENT-/);
  expect(originalRunId).toMatch(/^ARUN-/);

  await useWorkspaceApiBase(page);
  await page.goto(`${dashboardBase}/?page=Automations&automation=github-provider-retry-browser&delivery=${githubDuplicateProviderDeliveryId}`);
  await expect(page.getByRole("heading", { name: "Automations" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByRole("heading", { name: "Provider Delivery Detail" })).toBeVisible();
  await expect(page.getByText("github-browser-duplicate-delivery").first()).toBeVisible();
  const webhookPanel = page.locator(".panel").filter({ has: page.getByRole("heading", { name: "Webhook Admission Console" }) });

  await webhookPanel.getByLabel("Webhook Automation Target").selectOption("github-provider-retry-browser");
  await webhookPanel.getByLabel("Webhook Provider").fill("github");
  await webhookPanel.getByLabel("Webhook Connector").fill("github-main");
  await webhookPanel.getByLabel("Webhook Event Type").fill("issues");
  await webhookPanel.getByLabel("Webhook Delivery ID").fill("github-browser-duplicate-delivery");
  await webhookPanel.getByLabel("Webhook Signature").fill(signature);
  await webhookPanel.getByLabel("Webhook Raw Body").fill(rawBody);

  const admissionResponsePromise = page.waitForResponse(
    (response) => response.url().includes("/automations/github-provider-retry-browser/admit-webhook") && response.request().method() === "POST",
    { timeout: 60_000 },
  );
  await webhookPanel.getByRole("button", { name: "Admit Webhook Delivery" }).click();
  const admissionResponse = await admissionResponsePromise;
  expect(admissionResponse.ok(), `${admissionResponse.status()} ${await admissionResponse.text()}`).toBeTruthy();
  const duplicatePayload = (await admissionResponse.json()) as {
    delivery?: {
      spec?: {
        admissionStatus?: string;
        replayStatus?: string;
        automationTriggerEvent?: string;
        automationRun?: string;
        attemptCount?: number;
        summary?: string;
      };
    };
    event?: { id?: string };
    run?: { id?: string };
  };
  expect(duplicatePayload.delivery?.spec?.admissionStatus).toBe("duplicate");
  expect(duplicatePayload.delivery?.spec?.replayStatus).toBe("duplicate");
  expect(duplicatePayload.delivery?.spec?.automationTriggerEvent).toBe(originalEventId);
  expect(duplicatePayload.delivery?.spec?.automationRun).toBe(originalRunId);
  expect(duplicatePayload.delivery?.spec?.attemptCount).toBe((originalDelivery?.spec?.attemptCount ?? 1) + 1);
  expect(duplicatePayload.delivery?.spec?.summary).toContain("existing AutomationTriggerEvent");
  expect(duplicatePayload.event?.id).toBe(originalEventId);
  expect(duplicatePayload.run?.id).toBe(originalRunId);

  await page.goto(`${dashboardBase}/?page=Automations&automation=github-provider-retry-browser&delivery=${githubDuplicateProviderDeliveryId}`);
  await expectDashboardDataReady(page, 90_000);
  await expect(page.getByRole("heading", { name: "Provider Delivery Detail" })).toBeVisible();
  await expect(page.getByText(githubDuplicateProviderDeliveryId).first()).toBeVisible();
  await expect(page.getByText("github-browser-duplicate-delivery").first()).toBeVisible();
  await expect(page.getByText("duplicate").first()).toBeVisible();
  await expect(page.getByText("Provider delivery replay returned the existing AutomationTriggerEvent.").first()).toBeVisible();
  await expect(page.getByText(originalEventId).first()).toBeVisible();
  await expect(page.getByText(originalRunId).first()).toBeVisible();
});

test("GitHub changed-payload webhook replay blocks without creating a new run in the browser", async ({ page }) => {
  test.slow();
  const changedRawBody = JSON.stringify({
    action: "opened",
    installation: { id: 12345 },
    issue: {
      html_url: "https://github.example/example/aiteamos/issues/20",
      number: 20,
      title: "Tampered GitHub changed-payload admission",
    },
    repository: { full_name: "example/aiteamos" },
  });
  const changedSignature = `sha256=${createHmac("sha256", githubWebhookSecret).update(changedRawBody).digest("hex")}`;

  const deliveriesBefore = (await getJson("/automations/github-provider-retry-browser/provider-deliveries")) as Array<{
    id?: string;
    spec?: {
      admissionStatus?: string;
      replayStatus?: string;
      automationTriggerEvent?: string;
      automationRun?: string;
      attemptCount?: number;
      payloadDigest?: string;
    };
  }>;
  const originalDelivery = deliveriesBefore.find((record) => record.id === githubChangedPayloadProviderDeliveryId);
  expect(originalDelivery?.spec?.admissionStatus).toBe("accepted");
  expect(originalDelivery?.spec?.replayStatus).toBe("accepted");
  const originalEventId = originalDelivery?.spec?.automationTriggerEvent ?? "";
  const originalRunId = originalDelivery?.spec?.automationRun ?? "";
  const originalPayloadDigest = originalDelivery?.spec?.payloadDigest ?? "";
  expect(originalEventId).toMatch(/^AEVENT-/);
  expect(originalRunId).toMatch(/^ARUN-/);
  expect(originalPayloadDigest).toMatch(/^[a-f0-9]{64}$/);
  const runIdsBefore = new Set(deliveriesBefore.map((record) => record.spec?.automationRun).filter(Boolean));

  await useWorkspaceApiBase(page);
  await page.goto(`${dashboardBase}/?page=Automations&automation=github-provider-retry-browser&delivery=${githubChangedPayloadProviderDeliveryId}`);
  await expect(page.getByRole("heading", { name: "Automations" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByRole("heading", { name: "Provider Delivery Detail" })).toBeVisible();
  await expect(page.getByText("github-browser-changed-payload-delivery").first()).toBeVisible();
  const webhookPanel = page.locator(".panel").filter({ has: page.getByRole("heading", { name: "Webhook Admission Console" }) });

  await webhookPanel.getByLabel("Webhook Automation Target").selectOption("github-provider-retry-browser");
  await webhookPanel.getByLabel("Webhook Provider").fill("github");
  await webhookPanel.getByLabel("Webhook Connector").fill("github-main");
  await webhookPanel.getByLabel("Webhook Event Type").fill("issues");
  await webhookPanel.getByLabel("Webhook Delivery ID").fill("github-browser-changed-payload-delivery");
  await webhookPanel.getByLabel("Webhook Signature").fill(changedSignature);
  await webhookPanel.getByLabel("Webhook Raw Body").fill(changedRawBody);

  const dialogPromise = page.waitForEvent("dialog", { timeout: 60_000 }).then(async (dialog) => {
    const message = dialog.message();
    await dialog.dismiss();
    return message;
  });
  const admissionResponsePromise = page.waitForResponse(
    (response) => response.url().includes("/automations/github-provider-retry-browser/admit-webhook") && response.request().method() === "POST",
    { timeout: 60_000 },
  );
  await webhookPanel.getByRole("button", { name: "Admit Webhook Delivery" }).click();
  const admissionResponse = await admissionResponsePromise;
  expect(admissionResponse.status()).toBe(400);
  await expect(dialogPromise).resolves.toContain("replay changed payload digest");

  await page.goto(`${dashboardBase}/?page=Automations&automation=github-provider-retry-browser&delivery=${githubChangedPayloadProviderDeliveryId}`);
  await expectDashboardDataReady(page, 90_000);
  await expect(page.getByRole("heading", { name: "Provider Delivery Detail" })).toBeVisible();
  await expect(page.getByText(githubChangedPayloadProviderDeliveryId).first()).toBeVisible();
  await expect(page.getByText("github-browser-changed-payload-delivery").first()).toBeVisible();
  await expect(page.getByText("Provider delivery id replay used a different payload digest.").first()).toBeVisible();
  await expect(page.getByText("Provider delivery blocked because delivery id replay changed payload digest.").first()).toBeVisible();
  await expect(page.getByText(originalEventId).first()).toBeVisible();
  await expect(page.getByText(originalRunId).first()).toBeVisible();

  const deliveriesAfter = (await getJson("/automations/github-provider-retry-browser/provider-deliveries")) as Array<{
    id?: string;
    spec?: {
      admissionStatus?: string;
      replayStatus?: string;
      automationTriggerEvent?: string;
      automationRun?: string;
      attemptCount?: number;
      payloadDigest?: string;
      blockers?: string[];
    };
  }>;
  const blockedDelivery = deliveriesAfter.find((record) => record.id === githubChangedPayloadProviderDeliveryId);
  expect(blockedDelivery?.spec?.admissionStatus).toBe("blocked");
  expect(blockedDelivery?.spec?.replayStatus).toBe("blocked");
  expect(blockedDelivery?.spec?.automationTriggerEvent).toBe(originalEventId);
  expect(blockedDelivery?.spec?.automationRun).toBe(originalRunId);
  expect(blockedDelivery?.spec?.attemptCount).toBe((originalDelivery?.spec?.attemptCount ?? 1) + 1);
  expect(blockedDelivery?.spec?.payloadDigest).not.toBe(originalPayloadDigest);
  expect((blockedDelivery?.spec?.blockers ?? []).join(" ")).toContain("different payload digest");
  const runIdsAfter = new Set(deliveriesAfter.map((record) => record.spec?.automationRun).filter(Boolean));
  expect(runIdsAfter).toEqual(runIdsBefore);
});

test("GitHub bad-signature webhook admission rejects without delivery event or run side effects in the browser", async ({ page }) => {
  test.slow();
  const badDeliveryId = "github-browser-bad-signature-delivery";
  const rawBody = JSON.stringify({
    action: "opened",
    installation: { id: 12345 },
    issue: {
      html_url: "https://github.example/example/aiteamos/issues/21",
      number: 21,
      title: "Bad signature GitHub admission",
    },
    repository: { full_name: "example/aiteamos" },
  });

  const deliveriesBefore = (await getJson("/automations/github-provider-retry-browser/provider-deliveries")) as Array<{
    id?: string;
    spec?: { deliveryId?: string; automationTriggerEvent?: string; automationRun?: string };
  }>;
  const eventsBefore = (await getJson("/automations/github-provider-retry-browser/events")) as Array<{
    id?: string;
    spec?: { dedupeKey?: string; payload?: { deliveryId?: string } };
  }>;
  const runsBefore = (await getJson("/automations/github-provider-retry-browser/runs")) as Array<{
    id?: string;
    spec?: { sourceEvent?: { dedupeKey?: string } };
  }>;
  expect(deliveriesBefore.some((record) => record.spec?.deliveryId === badDeliveryId)).toBeFalsy();
  expect(eventsBefore.some((record) => record.spec?.dedupeKey === `github:issues:${badDeliveryId}`)).toBeFalsy();
  expect(runsBefore.some((record) => record.spec?.sourceEvent?.dedupeKey === `github:issues:${badDeliveryId}`)).toBeFalsy();

  await useWorkspaceApiBase(page);
  await page.goto(`${dashboardBase}/?page=Automations&automation=github-provider-retry-browser`);
  await expect(page.getByRole("heading", { name: "Automations" })).toBeVisible();
  await expectDashboardDataReady(page);
  const webhookPanel = page.locator(".panel").filter({ has: page.getByRole("heading", { name: "Webhook Admission Console" }) });

  await webhookPanel.getByLabel("Webhook Automation Target").selectOption("github-provider-retry-browser");
  await webhookPanel.getByLabel("Webhook Provider").fill("github");
  await webhookPanel.getByLabel("Webhook Connector").fill("github-main");
  await webhookPanel.getByLabel("Webhook Event Type").fill("issues");
  await webhookPanel.getByLabel("Webhook Delivery ID").fill(badDeliveryId);
  await webhookPanel.getByLabel("Webhook Signature").fill("sha256=bad-signature");
  await webhookPanel.getByLabel("Webhook Raw Body").fill(rawBody);

  const dialogPromise = page.waitForEvent("dialog", { timeout: 60_000 }).then(async (dialog) => {
    const message = dialog.message();
    await dialog.dismiss();
    return message;
  });
  const admissionResponsePromise = page.waitForResponse(
    (response) => response.url().includes("/automations/github-provider-retry-browser/admit-webhook") && response.request().method() === "POST",
    { timeout: 60_000 },
  );
  await webhookPanel.getByRole("button", { name: "Admit Webhook Delivery" }).click();
  const admissionResponse = await admissionResponsePromise;
  expect(admissionResponse.status()).toBe(400);
  await expect(dialogPromise).resolves.toContain("webhook signature verification failed");

  const deliveriesAfter = (await getJson("/automations/github-provider-retry-browser/provider-deliveries")) as Array<{
    id?: string;
    spec?: { deliveryId?: string; automationTriggerEvent?: string; automationRun?: string };
  }>;
  const eventsAfter = (await getJson("/automations/github-provider-retry-browser/events")) as Array<{
    id?: string;
    spec?: { dedupeKey?: string; payload?: { deliveryId?: string } };
  }>;
  const runsAfter = (await getJson("/automations/github-provider-retry-browser/runs")) as Array<{
    id?: string;
    spec?: { sourceEvent?: { dedupeKey?: string } };
  }>;
  expect(deliveriesAfter.map((record) => record.id).sort()).toEqual(deliveriesBefore.map((record) => record.id).sort());
  expect(eventsAfter.map((record) => record.id).sort()).toEqual(eventsBefore.map((record) => record.id).sort());
  expect(runsAfter.map((record) => record.id).sort()).toEqual(runsBefore.map((record) => record.id).sort());
  expect(deliveriesAfter.some((record) => record.spec?.deliveryId === badDeliveryId)).toBeFalsy();
  expect(eventsAfter.some((record) => record.spec?.dedupeKey === `github:issues:${badDeliveryId}`)).toBeFalsy();
  expect(runsAfter.some((record) => record.spec?.sourceEvent?.dedupeKey === `github:issues:${badDeliveryId}`)).toBeFalsy();
});
