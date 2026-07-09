import { expect, test, type APIRequestContext } from "@playwright/test";

const langGraphApiUrl = process.env.AITEAMOS_E2E_LANGGRAPH_URL ?? "http://127.0.0.1:2024";
const langGraphOrigin = new URL(langGraphApiUrl).origin;
const dashboardUrl = process.env.AITEAMOS_E2E_DASHBOARD_URL ?? "http://127.0.0.1:5173";
const dashboardOrigin = new URL(dashboardUrl).origin;
const approvalFixtureEnabled = process.env.AITEAMOS_E2E_APPROVAL_FIXTURE === "1";

async function createApprovalFixtureTicket(request: APIRequestContext): Promise<string> {
  const backendResponse = await request.put(`${dashboardOrigin}/api/v1/tickets/backend`, {
    data: { mode: "local_file", local_file_path: ".aiteamos/tickets/index.json" },
  });
  expect(backendResponse.ok()).toBe(true);

  const createResponse = await request.post(`${dashboardOrigin}/api/v1/tickets`, {
    data: {
      title: "Approval fixture dogfood Ticket",
      description: "Deterministic LangGraph approval fixture for AITeamOS Workbench dogfood.",
      ticket_type: "rd",
      assigned_employee_id: "clara",
      assigned_role: "AI Team OS Manager",
      source_thread_id: "employee-clara-approval-fixture",
      source_run_id: "fixture-needs-approval",
      actor_employee_id: "clara",
      actor_role: "AI Team OS Manager",
    },
  });
  expect(createResponse.ok()).toBe(true);

  const ticket = await createResponse.json();
  expect(typeof ticket.id).toBe("string");
  expect(ticket.id).toMatch(/^rd-\d{4,}$/);
  return ticket.id;
}

test("Chat Workbench runs through the LangGraph Agent Server from the browser", async ({ page }) => {
  test.skip(approvalFixtureEnabled, "Approval fixture mode runs the dedicated interrupt/resume browser spec.");

  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.addInitScript(() => {
    window.localStorage.setItem("aiteamos.chat.activeEmployeeId", "clara");
  });

  await page.goto("/#/chat");
  await expect(page.getByLabel("Chat message")).toBeVisible();

  const graphRunResponse = page.waitForResponse(
    (response) => response.url().startsWith(`${langGraphOrigin}/`) && response.url().includes("/commands") && response.request().method() === "POST",
    { timeout: 90_000 },
  );

  await page.getByLabel("Chat message").fill(
    "Workbench browser smoke test: 用一句话说明 AITeamOS 的核心价值。",
  );
  await page.getByRole("button", { name: "Send" }).click();

  const response = await graphRunResponse;
  expect(response.ok()).toBe(true);

  await expect(page.getByText("Workbench State")).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText("Latest Run")).toBeVisible();
  await expect(page.getByText("aiteamos_workbench")).toBeVisible();
  await expect(page.getByText("Clara").first()).toBeVisible();
  const visibleResponse = page.getByLabel("Visible assistant response");
  await expect(visibleResponse).toBeVisible({ timeout: 90_000 });
  await expect(visibleResponse.getByText("Assistant")).toBeVisible();
  await expect(visibleResponse.getByText(/completed|handoff|provider_blocker|needs_approval|blocked/)).toBeVisible();

  expect(pageErrors).toEqual([]);
});

test("Chat Workbench resumes a LangGraph approval interrupt through the input.respond protocol command", async ({ page, request }) => {
  test.skip(!approvalFixtureEnabled, "Set AITEAMOS_E2E_APPROVAL_FIXTURE=1 and VITE_LANGGRAPH_ASSISTANT_ID=aiteamos_workbench_approval_fixture.");

  const fixtureTicketId = await createApprovalFixtureTicket(request);
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.addInitScript(() => {
    window.localStorage.setItem("aiteamos.chat.activeEmployeeId", "clara");
    window.localStorage.removeItem("aiteamos.chat.langGraphThreadMap.v1");
    window.localStorage.removeItem("aiteamos.chat.currentLangGraphThreadId");
  });

  await page.goto("/#/chat");
  await expect(page.getByLabel("Chat message")).toBeVisible();
  const newThreadResponse = page.waitForResponse(
    (response) => response.url().includes("/api/v1/chat/threads") && response.request().method() === "POST",
    { timeout: 20_000 },
  );
  await page.getByRole("button", { name: "New thread" }).click();
  expect((await newThreadResponse).ok()).toBe(true);
  await page.getByLabel("Ticket key").fill(fixtureTicketId);

  const interruptedRunResponse = page.waitForResponse(
    (response) => response.url().startsWith(`${langGraphOrigin}/`) && response.url().includes("/commands") && response.request().method() === "POST",
    { timeout: 90_000 },
  );

  await page.getByLabel("Chat message").fill("Trigger approval fixture.");
  await page.getByRole("button", { name: "Send" }).click();

  expect((await interruptedRunResponse).ok()).toBe(true);
  await expect(page.getByText("Approval Policy")).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText("approval-fixture-1").first()).toBeVisible();

  const resumeResponse = page.waitForResponse(
    (response) => {
      const request = response.request();
      return (
        response.url().startsWith(`${langGraphOrigin}/`)
        && response.url().includes("/commands")
        && request.method() === "POST"
        && (request.postData() ?? "").includes("\"method\":\"input.respond\"")
      );
    },
    { timeout: 90_000 },
  );
  await page.getByRole("button", { name: "Resume approval approval-fixture-1" }).click();

  expect((await resumeResponse).ok()).toBe(true);
  await expect(page.getByText("Approved fixture resume completed.")).toBeVisible({ timeout: 90_000 });
  const visibleResponse = page.getByLabel("Visible assistant response");
  await expect(visibleResponse).toBeVisible();
  await expect(visibleResponse).toContainText("Approved fixture resume completed.");
  await expect(visibleResponse.getByRole("button", { name: "Open Chat run details" })).toBeVisible();
  await expect(page.getByText("artifact-approved-fixture")).toBeVisible();
  await expect(page.getByText("aiteamos_workbench_approval_fixture")).toBeVisible();
  await expect(page.getByText("Asset Candidates")).toBeVisible({ timeout: 90_000 });

  const approveCandidateButton = page.getByRole("button", { name: /Approve Asset candidate asset-candidate-/ }).first();
  await expect(approveCandidateButton).toBeVisible();
  if (await approveCandidateButton.isEnabled()) {
    const reviewResponse = page.waitForResponse(
      (response) => (
        response.url().includes("/api/v1/assets/candidates/")
        && response.url().includes("/review")
        && response.request().method() === "POST"
      ),
      { timeout: 90_000 },
    );
    await approveCandidateButton.click();
    expect((await reviewResponse).ok()).toBe(true);
  }

  const projectGraphitiButton = page.getByRole("button", { name: /Project Asset .* to Graphiti/ }).first();
  await expect(projectGraphitiButton).toBeVisible();
  await expect(projectGraphitiButton).toBeEnabled({ timeout: 20_000 });
  const projectionResponse = page.waitForResponse(
    (response) => (
      response.url().includes("/api/v1/assets/records/")
      && response.url().includes("/project/graphiti")
      && response.request().method() === "POST"
    ),
    { timeout: 90_000 },
  );
  await projectGraphitiButton.click();
  const projection = await projectionResponse;
  if (projection.ok()) {
    await expect(page.getByText(/ingested|skipped/).first()).toBeVisible({ timeout: 20_000 });
  } else {
    const body = await projection.text().catch(() => "");
    expect(body).toContain("Graphiti");
    await expect(page.getByText(/Graphiti/).first()).toBeVisible();
  }

  const recallResponse = page.waitForResponse(
    (response) => {
      const request = response.request();
      return (
        response.url().startsWith(`${langGraphOrigin}/`)
        && response.url().includes("/commands")
        && request.method() === "POST"
        && (request.postData() ?? "").includes("Recall approved asset fixture")
      );
    },
    { timeout: 90_000 },
  );
  await page.getByLabel("Chat message").fill("Recall approved asset fixture");
  await page.getByRole("button", { name: "Send" }).click();

  expect((await recallResponse).ok()).toBe(true);
  await expect(page.getByText("Recalled approved fixture Asset from Assets registry.")).toBeVisible({ timeout: 90_000 });
  await expect(page.getByLabel("Visible assistant response")).toContainText(
    "Recalled approved fixture Asset from Assets registry.",
  );
  await expect(page.getByText("fixture-asset-recall").first()).toBeVisible();
  await expect(page.getByText(`Source: ${fixtureTicketId}`).first()).toBeVisible();
  await expect(page.getByText(/Graphiti: (yes|no)/).first()).toBeVisible();

  expect(pageErrors).toEqual([]);
});
