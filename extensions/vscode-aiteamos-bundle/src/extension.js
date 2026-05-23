"use strict";

const fs = require("fs/promises");
const vscode = require("vscode");

const BUNDLE_KEY = "aiteamos.bundle.v1";

function activate(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand("aiteamosBundle.import", () => importBundle(context)),
    vscode.commands.registerCommand("aiteamosBundle.writeIngest", () => writeIngest(context))
  );
}

function deactivate() {}

async function importBundle(context) {
  const selected = await vscode.window.showOpenDialog({
    canSelectFiles: true,
    canSelectFolders: false,
    canSelectMany: false,
    filters: { "AITEAMOS bundle": ["json"] },
    title: "Import aiteamos-bundle.json"
  });
  if (!selected || selected.length === 0) {
    return;
  }

  const text = await fs.readFile(selected[0].fsPath, "utf8");
  const bundle = JSON.parse(text);
  validateBundle(bundle);
  await context.workspaceState.update(BUNDLE_KEY, bundle);
  vscode.window.showInformationMessage(`Imported AITEAMOS bundle for ${bundle.run}.`);
}

async function writeIngest(context) {
  const bundle = context.workspaceState.get(BUNDLE_KEY);
  if (!bundle) {
    throw new Error("Import aiteamos-bundle.json before submitting assisted ingest.");
  }
  validateBundle(bundle);

  const journal = await vscode.window.showInputBox({
    prompt: "Assisted ingest journal",
    placeHolder: "Summarize the changes, verification, and residual risk."
  });
  if (!journal) {
    return;
  }

  const testLog = await vscode.window.showInputBox({
    prompt: "Optional test evidence",
    placeHolder: "Example: python -m unittest tests.test_example -q passed"
  });

  const payload = {
    journal,
    testLog: testLog || undefined,
    reviewTarget: {
      type: "external_review",
      description: `Submitted from AITEAMOS Bundle reference extension for ${bundle.run}`
    }
  };

  await postAssistedIngest(bundle, payload);
  vscode.window.showInformationMessage(`Submitted RunAssistedIngestInput for ${bundle.run}.`);
}

function validateBundle(bundle) {
  if (!bundle || bundle.kind !== "AiteamosBundle" || bundle.schemaVersion !== "aiteamos-bundle.v1") {
    throw new Error("Expected an AiteamosBundle with schemaVersion aiteamos-bundle.v1.");
  }
  if (bundle.ingestInputSchema !== "RunAssistedIngestInput") {
    throw new Error("Expected bundle.ingestInputSchema to be RunAssistedIngestInput.");
  }
  const boundary = bundle.package && bundle.package.ingestContract && bundle.package.ingestContract.durableMutationBoundary;
  if (!boundary || !boundary.endsWith("/assisted-ingest")) {
    throw new Error("AITEAMOS bundle is missing the assisted ingest boundary.");
  }
  if (bundle.secretHandling !== "references-only-no-secret-values") {
    throw new Error("AITEAMOS bundle must declare references-only-no-secret-values secret handling.");
  }
}

async function postAssistedIngest(bundle, payload) {
  if (typeof fetch !== "function") {
    throw new Error("This extension host does not provide fetch; run on a VSCode/Cursor build with Node fetch support.");
  }
  const url = ingestUrl(bundle);
  const headers = { "content-type": "application/json" };
  const bearer = process.env.AITEAMOS_API_TOKEN;
  if (bearer) {
    headers.authorization = `Bearer ${bearer}`;
  }

  const response = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`AITEAMOS assisted ingest failed: ${response.status} ${text}`);
  }
}

function ingestUrl(bundle) {
  const boundary = bundle.package.ingestContract.durableMutationBoundary;
  const envBase = process.env.AITEAMOS_API_BASE_URL || "";
  const base = (envBase || bundle.apiBaseUrl || "http://127.0.0.1:8765").replace(/\/+$/, "");
  if (boundary.startsWith("http://") || boundary.startsWith("https://")) {
    return boundary;
  }
  if (base.endsWith("/api") && boundary.startsWith("/api/")) {
    return `${base.slice(0, -4)}${boundary}`;
  }
  return `${base}${boundary.startsWith("/") ? boundary : `/${boundary}`}`;
}

module.exports = { activate, deactivate, validateBundle, ingestUrl };
