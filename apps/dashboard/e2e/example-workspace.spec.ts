import { expect, test, type Page } from "@playwright/test";
import { execFileSync, spawn, type ChildProcess, type SpawnOptions } from "node:child_process";
import { cp, mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const filename = fileURLToPath(import.meta.url);
const dirname = path.dirname(filename);
const dashboardRoot = path.resolve(dirname, "..");
const repoRoot = path.resolve(dashboardRoot, "../..");
const apiPort = Number(process.env.AITEAMOS_EXAMPLE_E2E_API_PORT ?? "18766");
const rootApiPort = Number(process.env.AITEAMOS_EXAMPLE_E2E_ROOT_API_PORT ?? "18767");
const dashboardPort = Number(process.env.AITEAMOS_EXAMPLE_E2E_DASHBOARD_PORT ?? "15174");
const apiBase = `http://127.0.0.1:${apiPort}`;
const rootApiBase = `http://127.0.0.1:${rootApiPort}`;
const dashboardBase = `http://127.0.0.1:${dashboardPort}`;
const dashboardApiToken = "example-dashboard-e2e-token";
const sourceWorkspace = path.join(repoRoot, "examples/protocol-fixture/.aiteamos");
const sourceRootWorkspace = path.join(repoRoot, ".aiteamos");
const serverLogs: string[] = [];

let tempRoot = "";
let apiProcess: ChildProcess | undefined;
let rootApiProcess: ChildProcess | undefined;
let dashboardProcess: ChildProcess | undefined;
let demoWorkerRunId = "";
let demoFollowupRunId = "";

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

async function expectDashboardDataReady(page: Page): Promise<void> {
  await expect(page.getByText("Loading workspace data...")).toHaveCount(0, { timeout: 40_000 });
}

async function getJson(pathname: string): Promise<unknown> {
  const response = await fetch(`${apiBase}${pathname}`);
  if (!response.ok) {
    throw new Error(`${pathname} failed: ${response.status} ${response.statusText} ${await response.text()}`);
  }
  return response.json();
}

test.beforeAll(async () => {
  tempRoot = await mkdtemp(path.join(tmpdir(), "aiteamos-example-dashboard-e2e-"));
  const tempWorkspace = path.join(tempRoot, ".aiteamos");
  const tempRootWorkspace = path.join(tempRoot, "root.aiteamos");
  await cp(sourceWorkspace, tempWorkspace, { recursive: true });
  await cp(sourceRootWorkspace, tempRootWorkspace, { recursive: true });
  const fixtureOutput = execFileSync(
    "python",
    [
      "-c",
      `
from pathlib import Path
import json
import shutil
import subprocess
import yaml

from aiteamos_workspace import (
    approve_permission_request,
    create_model_profile,
    create_permission_request,
    create_run,
    create_task,
    explain_effective_permissions,
    load_workspace,
)

workspace = Path(${JSON.stringify(tempWorkspace)})
repo_root = Path(${JSON.stringify(repoRoot)})
source = Path(${JSON.stringify(tempRoot)}) / "protocol-demo-source"
shutil.copytree(
    repo_root / "examples" / "protocol-fixture",
    source,
    ignore=shutil.ignore_patterns(".aiteamos", "__pycache__", "artifacts", "indexes"),
)
init = subprocess.run(["git", "init", "-b", "main"], cwd=source, check=False, capture_output=True, text=True)
if init.returncode != 0:
    subprocess.run(["git", "init"], cwd=source, check=True, capture_output=True, text=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=source, check=True, capture_output=True, text=True)
subprocess.run(["git", "config", "user.email", "aiteamos@example.invalid"], cwd=source, check=True)
subprocess.run(["git", "config", "user.name", "AITEAMOS Example Browser Worker"], cwd=source, check=True)
subprocess.run(["git", "add", "."], cwd=source, check=True)
subprocess.run(["git", "commit", "-m", "initial protocol browser worker fixture"], cwd=source, check=True, capture_output=True, text=True)

repo_manifest = workspace / "repositories" / "protocol-fixture.yaml"
repo_data = yaml.safe_load(repo_manifest.read_text(encoding="utf-8"))
repo_data.setdefault("spec", {})["localPath"] = str(source)
repo_data["spec"]["url"] = source.as_uri()
repo_data["spec"]["defaultBranch"] = "main"
repo_manifest.write_text(yaml.safe_dump(repo_data, sort_keys=False), encoding="utf-8")

profile_manifest = workspace / "execution_profiles" / "digital" / "protocol-runtime-bot.yaml"
profile_data = yaml.safe_load(profile_manifest.read_text(encoding="utf-8"))
allowed = profile_data.setdefault("spec", {}).setdefault("allowedModelProfiles", [])
if "manual-demo-browser-worker" not in allowed:
    allowed.append("manual-demo-browser-worker")
profile_manifest.write_text(yaml.safe_dump(profile_data, sort_keys=False), encoding="utf-8")

fixture_response = """## Summary
Prepared a bounded browser replay change for the public Protocol demo.

\`\`\`diff
diff --git a/src/pure_function.py b/src/pure_function.py
index 505b52d..54a6549 100644
--- a/src/pure_function.py
+++ b/src/pure_function.py
@@ -1,2 +1,3 @@
 def add_i32(lhs: str, rhs: str) -> str:
-    return f"runtime.add_i32({lhs}, {rhs})"
+    callee = "runtime.add_i32"
+    return f"{callee}({lhs}, {rhs})"
\`\`\`

Memory proposal: Public Protocol browser worker replays should prove diff, test log, command log, review target, and pending memory proposal artifacts from Run Detail.
"""

create_model_profile(
    workspace,
    name="manual-demo-browser-worker",
    provider="local",
    model="manual",
    gateway="manual",
    invocation={"fixtureResponse": fixture_response},
    capabilities=["managed_llm"],
)
task = create_task(
    workspace,
    title="Browser replay Protocol digital worker",
    project="protocol-fixture",
    assigned_member="protocol-runtime-bot",
    assignment="conversion-runtime",
    priority="high",
    status="TODO",
    risk_class="public-demo-browser-worker",
    execution_mode="managed_llm",
    acceptance=[
        "Run Detail starts the public demo digital worker from the browser.",
        "Worker artifacts include diff patch, test log, command log, review target, and pending memory proposal.",
    ],
    markdown="# Browser replay Protocol digital worker\\n\\nTemporary E2E fixture generated from the public demo workspace.\\n",
)
verify_command = (
    "python -c \\"from src.pure_function import add_i32; "
    "assert add_i32('lhs', 'rhs') == 'runtime.add_i32(lhs, rhs)'\\""
)
run = create_run(
    workspace,
    task_id=task.object_id,
    member="protocol-runtime-bot",
    assignment="conversion-runtime",
    model_profile="manual-demo-browser-worker",
    mode="managed_llm",
    status="READY",
    extra_spec={"worker": {"verificationCommands": [verify_command], "commandTimeoutSeconds": 30}},
)
followup_task = create_task(
    workspace,
    title="Use reviewed public Protocol worker learning",
    project="protocol-fixture",
    assigned_member="protocol-runtime-bot",
    assignment="conversion-runtime",
    priority="normal",
    status="TODO",
    risk_class="public-demo-memory-reuse",
    execution_mode="managed_llm",
    acceptance=[
        "Follow-up context preview includes the approved worker-created memory.",
    ],
    markdown="# Use reviewed public Protocol worker learning\\n\\nTemporary E2E fixture for memory approval and reuse.\\n",
)
followup_run = create_run(
    workspace,
    task_id=followup_task.object_id,
    member="protocol-runtime-bot",
    assignment="conversion-runtime",
    model_profile="manual-demo-browser-worker",
    mode="managed_llm",
    status="READY",
)
index = load_workspace(workspace)
decision = explain_effective_permissions(
    index,
    member="protocol-runtime-bot",
    project="protocol-fixture",
    assignment="conversion-runtime",
    action={"tool": "Bash", "command": verify_command},
    non_interactive=True,
)
request = create_permission_request(
    workspace,
    member="protocol-runtime-bot",
    project="protocol-fixture",
    assignment="conversion-runtime",
    task=task.object_id,
    run=run.object_id,
    requester_member="protocol-reviewer-human",
    action={"tool": "Bash", "command": verify_command},
    current_decision=decision,
    reason="Approve deterministic public demo browser worker verification in a temporary workspace.",
    source="protocol-demo-browser-worker-replay",
)
approve_permission_request(
    workspace,
    request.object_id,
    reviewer_member="protocol-reviewer-human",
    reason="Approved for public demo browser worker replay E2E.",
)
print(json.dumps({"run": run.object_id, "followupRun": followup_run.object_id}))
`,
    ],
    {
      cwd: repoRoot,
      env: { ...localServerEnv(), PYTHONPATH: workspacePythonPath() },
      encoding: "utf8",
    },
  );
  const fixtureJson = fixtureOutput.split(/\r?\n/).filter((line) => line.trim()).at(-1) ?? "{}";
  const fixture = JSON.parse(fixtureJson) as { run?: string };
  if (!fixture.run) {
    throw new Error(`Protocol browser worker fixture did not return a run id: ${fixtureOutput}`);
  }
  demoWorkerRunId = fixture.run;
  demoFollowupRunId = fixture.followupRun ?? "";
  if (!demoFollowupRunId) {
    throw new Error(`Protocol browser worker fixture did not return a follow-up run id: ${fixtureOutput}`);
  }

  apiProcess = spawnManaged(
    "api",
    path.join(repoRoot, "aiteamos"),
    ["serve", "--workspace", tempWorkspace, "--host", "127.0.0.1", "--port", String(apiPort)],
    {
      cwd: repoRoot,
      env: {
        ...localServerEnv(),
        PYTHONPATH: workspacePythonPath(),
        AITEAMOS_API_TOKEN: "",
        AITEAMOS_VIEWER_TOKEN_MAP: "",
        AITEAMOS_MCP_READ_TOKEN: "",
        AITEAMOS_MCP_WRITE_TOKEN: "",
      },
    },
  );
  await waitForHttp(`${apiBase}/session`, "AITEAMOS API");

  rootApiProcess = spawnManaged(
    "root-api",
    path.join(repoRoot, "aiteamos"),
    ["serve", "--workspace", tempRootWorkspace, "--host", "127.0.0.1", "--port", String(rootApiPort)],
    {
      cwd: repoRoot,
      env: {
        ...localServerEnv(),
        PYTHONPATH: workspacePythonPath(),
        AITEAMOS_API_TOKEN: dashboardApiToken,
        AITEAMOS_VIEWER_TOKEN_MAP: "",
        AITEAMOS_MCP_READ_TOKEN: "",
        AITEAMOS_MCP_WRITE_TOKEN: "",
      },
    },
  );
  await waitForHttp(`${rootApiBase}/session`, "AITEAMOS root API");

  dashboardProcess = spawnManaged(
    "dashboard",
    "npm",
    ["exec", "--", "vite", "--host", "127.0.0.1", "--port", String(dashboardPort), "--strictPort"],
    {
      cwd: dashboardRoot,
      env: {
        ...localServerEnv(),
        AITEAMOS_API_PROXY_TARGET: apiBase,
      },
    },
  );
  await waitForHttp(dashboardBase, "dashboard");
});

test.afterAll(async () => {
  await stopProcess(dashboardProcess);
  await stopProcess(rootApiProcess);
  await stopProcess(apiProcess);
  if (tempRoot) {
    await rm(tempRoot, { recursive: true, force: true });
  }
});

test("walks the public Protocol demo through Project, Employee, Run, Memory, and Automation details", async ({ page }) => {
  await page.addInitScript((token) => window.localStorage.setItem("aiteamos.apiToken", token), dashboardApiToken);
  await page.goto(`${dashboardBase}/?page=Projects&project=protocol-fixture&assignment=conversion-runtime`);
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByText("A neutral compiler demo project").first()).toBeVisible();
  await expect(page.getByRole("cell", { name: "protocol-runtime-bot" }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Assignments / Ownership Map" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "conversion-runtime" }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Project Memory", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "MEM-protocol-runtime-contract" }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Project Automation Schedule / Status" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "protocol-memory-health-demo" }).first()).toBeVisible();

  await page.goto(`${dashboardBase}/?page=Employees&member=protocol-release-hybrid&assignment=release-handoff`);
  await expect(page.getByRole("heading", { name: "Employees" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByText("Assisted release and handoff owner").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Assignment Detail" }).first()).toBeVisible();
  await expect(page.getByRole("cell", { name: "release-handoff" }).first()).toBeVisible();
  await expect(page.getByRole("cell", { name: "RUN-20260521T083000000" }).first()).toBeVisible();
  await expect(page.getByRole("cell", { name: "HANDOFF-20260521T083000000" }).first()).toBeVisible();

  await page.goto(`${dashboardBase}/?page=Runs&run=RUN-20260521T083000000`);
  await expect(page.getByRole("heading", { name: "Runs" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByRole("heading", { name: "Run Detail" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "protocol-release-hybrid" }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Assisted Ingest Workbench" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Selected Run Context Memory Injection" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Context Manifest Explorer" })).toBeVisible();
  await expect(page.getByText("Context Source Decisions")).toBeVisible();
  await expect(page.getByText("Context Source Detail")).toBeVisible();
  await expect(page.getByRole("cell", { name: "MEM-protocol-runtime-contract" }).first()).toBeVisible();
  await expect(page.getByRole("cell", { name: "memory:MEM-protocol-runtime-contract" }).first()).toBeVisible();
  await page.getByRole("cell", { name: "memory:MEM-protocol-runtime-contract" }).first().click();
  await expect(page.getByText("Open Memory Detail")).toBeVisible();

  await page.goto(`${dashboardBase}/?page=Memory&memory=MEM-protocol-runtime-contract&viewer=protocol-release-hybrid`);
  await expect(page.getByRole("heading", { name: "Memory" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByLabel("Projection Viewer")).toHaveValue("protocol-release-hybrid");
  await expect(page.getByRole("heading", { name: "Selected Memory Resource" })).toBeVisible();
  await expect(page.getByText("The reviewed runtime contract for").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Selected Memory Context Injection" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "RUN-20260521T083000000" }).first()).toBeVisible();

  await page.goto(`${dashboardBase}/?page=Automations&automation=protocol-memory-health-demo&project=protocol-fixture`);
  await expect(page.getByRole("heading", { name: "Automations" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByRole("heading", { name: "Automation Control Plane" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Selected Automation" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "protocol-memory-health-demo" }).first()).toBeVisible();
  await expect(page.getByRole("cell", { name: "ARUN-20260521T090000000" }).first()).toBeVisible();
  await expect(page.getByText("Pending proposal MP-20260521T083000000 still needs human memory review.").first()).toBeVisible();
});

test("starts the public Protocol demo digital worker and exposes rich review artifacts", async ({ page }) => {
  test.slow();

  await page.addInitScript((token) => window.localStorage.setItem("aiteamos.apiToken", token), dashboardApiToken);
  await page.goto(`${dashboardBase}/?page=Runs&run=${demoWorkerRunId}`);
  await expect(page.getByRole("heading", { name: "Runs" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByRole("heading", { name: "Managed Worker Start Console" })).toBeVisible();
  await expect(page.getByText("Worker can be started.").first()).toBeVisible();
  await expect(page.getByText(demoWorkerRunId).first()).toBeVisible();

  const startResponsePromise = page.waitForResponse(
    (response) => response.url().includes(`/runs/${demoWorkerRunId}/worker/start`) && response.request().method() === "POST",
    { timeout: 120_000 },
  );
  await page.getByRole("button", { name: "Start Managed Worker" }).click();
  const startResponse = await startResponsePromise;
  expect(startResponse.ok(), `${startResponse.status()} ${await startResponse.text()}\n${serverLogs.slice(-80).join("")}`).toBeTruthy();

  await expect.poll(async () => {
    const run = (await getJson(`/runs/${demoWorkerRunId}`)) as {
      spec?: {
        status?: string;
        reviewTarget?: { type?: string };
        outputs?: Array<{ type?: string }>;
        memoryProposals?: string[];
        worker?: { stage?: string; attemptId?: string };
      };
    };
    const outputTypes = new Set((run.spec?.outputs ?? []).map((item) => item.type));
    return [
      run.spec?.status ?? "",
      run.spec?.worker?.stage ?? "",
      run.spec?.reviewTarget?.type ?? "",
      outputTypes.has("worker_output"),
      outputTypes.has("diff_patch"),
      outputTypes.has("test_log"),
      outputTypes.has("command_log"),
      outputTypes.has("review_target"),
      (run.spec?.memoryProposals ?? []).length > 0,
    ].join(":");
  }, { timeout: 120_000 }).toBe("REVIEW:review:branch:true:true:true:true:true:true");

  const proposals = (await getJson("/memory/proposals")) as Array<{ id?: string; spec?: { sourceRun?: string; status?: string; member?: string; assignment?: string } }>;
  const proposal = proposals.find((item) => item.spec?.sourceRun === demoWorkerRunId);
  expect(proposal?.spec).toMatchObject({
    status: "pending-review",
    member: "protocol-runtime-bot",
    assignment: "conversion-runtime",
  });
  const proposalId = proposal?.id ?? "";
  expect(proposalId).toMatch(/^MP-/);

  await page.getByRole("button", { name: "Refresh" }).click();
  await expectDashboardDataReady(page);
  await expect(page.getByText("worker_output").first()).toBeVisible();
  await expect(page.getByText("diff_patch").first()).toBeVisible();
  await expect(page.getByText("test_log").first()).toBeVisible();
  await expect(page.getByText("command_log").first()).toBeVisible();
  await expect(page.getByText("review_target").first()).toBeVisible();
  await expect(page.getByText("pending-review").first()).toBeVisible();
  await expect(page.getByText(proposalId).first()).toBeVisible();

  await expect(page.getByRole("heading", { name: "Run Review Console" })).toBeVisible();
  const reviewResponsePromise = page.waitForResponse(
    (response) => response.url().includes(`/runs/${demoWorkerRunId}/reviews`) && response.request().method() === "POST",
    { timeout: 40_000 },
  );
  await page.getByLabel("Human Reviewer Member").fill("protocol-reviewer-human");
  await page.getByLabel("Run Review Verdict").selectOption("approved");
  await page.getByLabel("Run Review Summary").fill("Reviewed the isolated demo worker branch and approved the bounded runtime contract change.");
  await page.getByRole("button", { name: "Record Run Review" }).click();
  const reviewResponse = await reviewResponsePromise;
  expect(reviewResponse.ok(), `${reviewResponse.status()} ${await reviewResponse.text()}`).toBeTruthy();
  const reviewPayload = (await reviewResponse.json()) as { id?: string; spec?: { reviewerMember?: string; reviewerKind?: string; verdict?: string; target?: { type?: string } } };
  const reviewId = reviewPayload.id ?? "";
  expect(reviewId).toMatch(/^REVIEW-/);
  expect(reviewPayload.spec).toMatchObject({
    reviewerMember: "protocol-reviewer-human",
    reviewerKind: "human",
    verdict: "approved",
    target: { type: "branch" },
  });
  await expect.poll(async () => {
    const reviews = (await getJson("/reviews")) as Array<{ id?: string; spec?: { run?: string; reviewerMember?: string; verdict?: string } }>;
    const review = reviews.find((item) => item.id === reviewId && item.spec?.run === demoWorkerRunId);
    return `${review?.spec?.reviewerMember ?? ""}:${review?.spec?.verdict ?? ""}`;
  }).toBe("protocol-reviewer-human:approved");
  await page.goto(`${dashboardBase}/?page=Runs&run=${demoWorkerRunId}`);
  await expect(page.getByRole("heading", { name: "Runs" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByRole("cell", { name: "protocol-reviewer-human" }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Run Closeout Console" })).toBeVisible();
  const closeoutResponsePromise = page.waitForResponse(
    (response) => response.url().includes(`/runs/${demoWorkerRunId}/closeout`) && response.request().method() === "POST",
    { timeout: 40_000 },
  );
  await page.getByLabel("Closeout Actor Member").fill("protocol-reviewer-human");
  await page.getByLabel("Closeout Reason").fill("Approved branch review and worker evidence in the public demo.");
  await page.getByRole("button", { name: "Close Reviewed Run" }).click();
  const closeoutResponse = await closeoutResponsePromise;
  expect(closeoutResponse.ok(), `${closeoutResponse.status()} ${await closeoutResponse.text()}`).toBeTruthy();
  const closeoutPayload = (await closeoutResponse.json()) as {
    spec?: { status?: string; closeout?: { latestReview?: string; decisionAudit?: Array<{ decisionKind?: string }> } };
  };
  expect(closeoutPayload.spec?.status).toBe("DONE");
  expect(closeoutPayload.spec?.closeout?.latestReview).toBe(reviewId);
  expect(closeoutPayload.spec?.closeout?.decisionAudit?.[0]?.decisionKind).toBe("human_approval");
  await expect.poll(async () => {
    const closedRun = (await getJson(`/runs/${demoWorkerRunId}`)) as { spec?: { status?: string; closeout?: { closedByMember?: string } } };
    return `${closedRun.spec?.status ?? ""}:${closedRun.spec?.closeout?.closedByMember ?? ""}`;
  }).toBe("DONE:protocol-reviewer-human");
  const sourceFile = path.join(tempRoot, "protocol-demo-source", "src", "pure_function.py");
  expect(await readFile(sourceFile, "utf-8")).not.toContain('callee = "runtime.add_i32"');

  await page.goto(`${dashboardBase}/?page=Runs&run=${demoWorkerRunId}`);
  await expect(page.getByRole("heading", { name: "Runs" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByRole("heading", { name: "Run Source Integration Console" })).toBeVisible();
  await expect.poll(async () => {
    const gate = (await getJson(`/runs/${demoWorkerRunId}/source-integration-gate?actorMember=protocol-reviewer-human`)) as {
      readyForSourceIntegration?: boolean;
      changedPaths?: string[];
    };
    return `${gate.readyForSourceIntegration === true}:${gate.changedPaths?.includes("src/pure_function.py") === true}`;
  }, { timeout: 40_000 }).toBe("true:true");
  await expect(page.getByText("READY_FOR_SOURCE_INTEGRATION").first()).toBeVisible();
  const integrationResponsePromise = page.waitForResponse(
    (response) => response.url().includes(`/runs/${demoWorkerRunId}/source-integration`) && response.request().method() === "POST",
    { timeout: 40_000 },
  );
  await page.getByLabel("Source Integration Actor Member").fill("protocol-reviewer-human");
  await page.getByLabel("Source Integration Reason").fill("Integrate the reviewed public demo branch after closeout.");
  await page.getByRole("button", { name: "Integrate Reviewed Source" }).click();
  const integrationResponse = await integrationResponsePromise;
  expect(integrationResponse.ok(), `${integrationResponse.status()} ${await integrationResponse.text()}`).toBeTruthy();
  const integrationPayload = (await integrationResponse.json()) as {
    spec?: { sourceIntegration?: { status?: string; sourceBranch?: string; decisionAudit?: Array<{ decisionKind?: string }> } };
  };
  expect(integrationPayload.spec?.sourceIntegration?.status).toBe("integrated");
  expect(integrationPayload.spec?.sourceIntegration?.sourceBranch).toBe("main");
  expect(integrationPayload.spec?.sourceIntegration?.decisionAudit?.[0]?.decisionKind).toBe("human_approval");
  await expect.poll(async () => (await readFile(sourceFile, "utf-8")).includes('callee = "runtime.add_i32"')).toBe(true);

  await page.goto(`${dashboardBase}/?page=Reviews&review=${proposalId}`);
  await expect(page.getByRole("heading", { name: "Reviews" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByText(proposalId).first()).toBeVisible();
  await expect(page.getByText("pending-review").first()).toBeVisible();

  const repairResponsePromise = page.waitForResponse(
    (response) => response.url().includes(`/memory/proposals/${proposalId}/repair`) && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Repair Proposal" }).click();
  const repairResponse = await repairResponsePromise;
  expect(repairResponse.ok(), `${repairResponse.status()} ${await repairResponse.text()}`).toBeTruthy();
  await expectDashboardDataReady(page);

  const approvalResponsePromise = page.waitForResponse(
    (response) => response.url().includes(`/memory/proposals/${proposalId}/approve`) && response.request().method() === "POST",
  );
  await page.getByLabel("Memory Approval Reason").fill("E2E approved repaired proposal");
  await page.getByRole("button", { name: "Approve Proposal With Review" }).click();
  const approvalResponse = await approvalResponsePromise;
  expect(approvalResponse.ok(), `${approvalResponse.status()} ${await approvalResponse.text()}`).toBeTruthy();
  const approvalPayload = (await approvalResponse.json()) as { memory?: { id?: string }; proposal?: { spec?: { approvedMemory?: string } } };
  const approvedMemoryId = approvalPayload.memory?.id ?? approvalPayload.proposal?.spec?.approvedMemory ?? "";
  expect(approvedMemoryId).toMatch(/^MEM-/);

  await expect.poll(async () => {
    const entries = (await getJson("/memory/entries")) as Array<{ id?: string; spec?: { lifecycle?: string } }>;
    const entry = entries.find((item) => item.id === approvedMemoryId);
    return `${entry?.id ?? ""}:${entry?.spec?.lifecycle ?? ""}`;
  }).toBe(`${approvedMemoryId}:active`);

  await expect.poll(async () => {
    const preview = (await getJson(`/runs/${demoFollowupRunId}/context-preview`)) as {
      manifest?: {
        sources?: { selectedMemory?: Array<{ memory?: string }> };
        sourceDecisions?: Array<{ sourceRef?: string; outcome?: string }>;
      };
      capsule?: string;
    };
    const selected = new Set((preview.manifest?.sources?.selectedMemory ?? []).map((item) => item.memory ?? ""));
    const included = new Set(
      (preview.manifest?.sourceDecisions ?? [])
        .filter((item) => item.outcome === "included")
        .map((item) => item.sourceRef ?? ""),
    );
    return selected.has(approvedMemoryId) && included.has(approvedMemoryId) && String(preview.capsule ?? "").includes(approvedMemoryId);
  }, { timeout: 40_000 }).toBe(true);

  await page.goto(`${dashboardBase}/?page=Runs&run=${demoFollowupRunId}`);
  await expect(page.getByRole("heading", { name: "Runs" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByRole("heading", { name: "Selected Run Context Memory Injection" })).toBeVisible();
  await expect(page.getByText(approvedMemoryId).first()).toBeVisible();
  await expect(page.getByText(`memory:${approvedMemoryId}`).first()).toBeVisible();
});

test("switches one dashboard session between two running workspace APIs", async ({ page }) => {
  await page.goto(dashboardBase);
  await page.evaluate((token) => window.localStorage.setItem("aiteamos.apiToken", token), dashboardApiToken);
  await page.goto(`${dashboardBase}/?page=Projects&project=protocol-fixture`);
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByText("A neutral compiler demo project").first()).toBeVisible();

  await page.goto(`${dashboardBase}/?page=Settings`);
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expectDashboardDataReady(page);
  await page.evaluate(() => window.localStorage.removeItem("aiteamos.apiToken"));
  await page.getByLabel("Workspace API Base").fill(rootApiBase);
  await page.getByRole("button", { name: "Apply API Base" }).click();
  await expectDashboardDataReady(page);
  await expect(page.getByText(rootApiBase).first()).toBeVisible();
  expect(rootApiProcess?.exitCode, serverLogs.slice(-80).join("")).toBeNull();
  const rootApiCheck = await page.request.get(`${rootApiBase}/session`);
  expect(rootApiCheck.ok(), `${rootApiCheck.status()} ${await rootApiCheck.text()}\n${serverLogs.slice(-80).join("")}`).toBeTruthy();

  await page.goto(`${dashboardBase}/?page=Projects&project=aiteamos`);
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  await expectDashboardDataReady(page);
  await expect(page.getByText("A model-agnostic AI team management system").first()).toBeVisible();
  await expect(page.getByRole("cell", { name: "aiteamos-dashboard" }).first()).toBeVisible();
});
