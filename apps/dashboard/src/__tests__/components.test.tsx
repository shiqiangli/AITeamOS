/**
 * AITeamOS Dashboard — Component Rendering Tests (plan.md §1.6)
 */

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { Panel, Status, Definition, DataTable, parseHash, NAV_ITEMS } from "../components/shared";

afterEach(() => {
  cleanup();
});

describe("Shared Components", () => {
  describe("Panel", () => {
    it("should render with title", () => {
      render(<Panel title="Test Panel"><p>Content</p></Panel>);
      expect(screen.getByText("Test Panel")).toBeTruthy();
      expect(screen.getByText("Content")).toBeTruthy();
    });

    it("should render without title", () => {
      const { container } = render(<Panel><p>No Title</p></Panel>);
      expect(container.querySelector("[class*='rounded']")).not.toBeNull();
      expect(screen.getByText("No Title")).toBeTruthy();
    });
  });

  describe("Status", () => {
    it("should render label and value", () => {
      render(<Status label="Count" value={42} />);
      expect(screen.getByText("Count")).toBeTruthy();
      expect(screen.getByText("42")).toBeTruthy();
    });

    it("should apply warn tone", () => {
      render(<Status label="Errors" value={5} tone="warn" />);
      expect(screen.getByText("Errors")).toBeTruthy();
      expect(screen.getByText("5")).toBeTruthy();
    });

    it("should apply ok tone", () => {
      render(<Status label="OK" value={0} tone="ok" />);
      expect(screen.getByText("OK")).toBeTruthy();
      expect(screen.getByText("0")).toBeTruthy();
    });
  });

  describe("Definition", () => {
    it("should render label and value", () => {
      render(<Definition label="Name" value="Alice" />);
      expect(screen.getByText("Name")).toBeTruthy();
      expect(screen.getByText("Alice")).toBeTruthy();
    });

    it("should show dash for null value", () => {
      render(<Definition label="Empty" value={null} />);
      expect(screen.getByText("\u2014")).toBeTruthy();
    });
  });

  describe("DataTable", () => {
    it("should render empty state", () => {
      render(<DataTable data={[]} columns={[{ key: "name" }]} />);
      expect(screen.getByText("No records")).toBeTruthy();
    });

    it("should render table with data", () => {
      const data = [
        { id: "1", name: "Alice", role: "dev" },
        { id: "2", name: "Bob", role: "qa" },
      ];
      const columns = [
        { key: "name", label: "Name" },
        { key: "role", label: "Role" },
      ];
      render(<DataTable data={data} columns={columns} />);
      expect(screen.getByText("Alice")).toBeTruthy();
      expect(screen.getByText("Bob")).toBeTruthy();
      expect(screen.getByText("Name")).toBeTruthy();
      expect(screen.getByText("Role")).toBeTruthy();
    });

    it("should highlight selected row", () => {
      const data = [
        { id: "1", name: "Alice" },
        { id: "2", name: "Bob" },
      ];
      const { container } = render(
        <DataTable data={data} columns={[{ key: "name" }]} selectedId="2" />,
      );
      expect(container.querySelector(".bg-muted")).not.toBeNull();
    });

    it("should call onSelect when row is clicked", () => {
      const onSelect = vi.fn();
      const data = [{ id: "1", name: "Alice" }];
      render(
        <DataTable data={data} columns={[{ key: "name" }]} onSelect={onSelect} />,
      );
      screen.getByText("Alice").closest("tr")?.click();
      expect(onSelect).toHaveBeenCalledWith(data[0]);
    });

    it("should render array values as comma-separated", () => {
      const data = [{ id: "1", tags: ["python", "testing"] }];
      render(<DataTable data={data} columns={[{ key: "tags", label: "Tags" }]} />);
      expect(screen.getByText("python, testing")).toBeTruthy();
    });
  });

  describe("parseHash", () => {
    it("should parse empty hash as home", () => {
      Object.defineProperty(window, "location", {
        value: { hash: "" },
        writable: true,
      });
      const result = parseHash();
      expect(result.page).toBe("home");
      expect(result.id).toBeNull();
    });

    it("should parse page from hash", () => {
      Object.defineProperty(window, "location", {
        value: { hash: "#/memories" },
        writable: true,
      });
      const result = parseHash();
      expect(result.page).toBe("memories");
      expect(result.id).toBeNull();
    });

    it("should parse page and id from hash", () => {
      Object.defineProperty(window, "location", {
        value: { hash: "#/skills/skill-123" },
        writable: true,
      });
      const result = parseHash();
      expect(result.page).toBe("skills");
      expect(result.id).toBe("skill-123");
    });

    it("should decode URI components in id", () => {
      Object.defineProperty(window, "location", {
        value: { hash: "#/members/uuid%20with%20spaces" },
        writable: true,
      });
      const result = parseHash();
      expect(result.id).toBe("uuid with spaces");
    });
  });

  describe("NAV_ITEMS", () => {
    it("should have all required navigation items", () => {
      const keys = NAV_ITEMS.map((item) => item.key);
      expect(keys).toContain("home");
      expect(keys).toContain("memories");
      expect(keys).toContain("skills");
      expect(keys).toContain("agents");
      expect(keys).toContain("members");
      expect(keys).toContain("departments");
      expect(keys).toContain("projects");
      expect(keys).toContain("tasks");
      expect(keys).toContain("metrics");
      expect(keys).not.toContain("reviews");
    });

    it("should have labels for all items", () => {
      for (const item of NAV_ITEMS) {
        expect(item.label).toBeTruthy();
      }
    });
  });
});
