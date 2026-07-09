import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../state/App";

vi.mock("../pages/chat", () => ({
  ChatPage: ({ routeTarget }: { routeTarget: string | null }) => <div>Chat route {routeTarget || "default"}</div>,
}));

vi.mock("../pages/tickets", () => ({
  TicketsPage: ({ selectedSection }: { selectedSection: string | null }) => <div>Tickets route {selectedSection || "default"}</div>,
}));

vi.mock("../pages/employees", () => ({
  EmployeesPage: ({ selectedDetail, selectedId }: { selectedDetail: string | null; selectedId: string | null }) => (
    <div>Employees route {selectedId || "default"} {selectedDetail || "none"}</div>
  ),
}));

vi.mock("../pages/assets", () => ({
  AssetsPage: ({ selectedArea, selectedDetail }: { selectedArea: string | null; selectedDetail: string | null }) => (
    <div>Assets route {selectedArea || "default"} {selectedDetail || "none"}</div>
  ),
}));

vi.mock("../pages/runtime", () => ({
  RuntimePage: ({ selectedSessionKey }: { selectedSessionKey: string | null }) => <div>Runtime route {selectedSessionKey || "default"}</div>,
}));

vi.mock("../pages/settings", () => ({
  SettingsPage: ({ selectedSection }: { selectedSection: string | null }) => <div>Settings route {selectedSection || "default"}</div>,
}));

vi.mock("../pages/system-status", () => ({
  SystemStatusPage: () => <div>System status route</div>,
}));

describe("App shell", () => {
  beforeEach(() => {
    window.location.hash = "";
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({}), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    })));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("loads route pages lazily and preserves nested route props", async () => {
    window.location.hash = "#/tickets/reports/rd-0001";

    render(<App />);

    expect(await screen.findByText("Tickets route reports/rd-0001")).toBeTruthy();
  });

  it("defaults to Chat when no route is present", async () => {
    render(<App />);

    expect(await screen.findByText("Chat route default")).toBeTruthy();
  });

  it("passes Settings section deep links to the Settings page", async () => {
    window.location.hash = "#/settings/ticket-backend";

    render(<App />);

    expect(await screen.findByText("Settings route ticket-backend")).toBeTruthy();

    window.location.hash = "#/settings/code-repositories";
    window.dispatchEvent(new Event("hashchange"));

    expect(await screen.findByText("Settings route code-repositories")).toBeTruthy();
  });
});
