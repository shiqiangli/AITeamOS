/**
 * AITeamOS Dashboard - API Page Component Tests (LLM Catalog only)
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiPage } from "../pages/agents";

vi.mock("../api/client", () => ({
  listLlmModels: vi.fn(),
  getLlmModelDetail: vi.fn(),
  createLlmModel: vi.fn(),
}));

import {
  listLlmModels,
  getLlmModelDetail,
  createLlmModel,
} from "../api/client";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ApiPage", () => {
  beforeEach(() => {
    (listLlmModels as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: "llm-1",
        name: "GPT Compiler",
        provider: "openai",
        model_id: "gpt-compiler",
        endpoint_type: "chat",
        context_window: 128000,
        max_output_tokens: 8192,
        supports_tools: true,
        supports_json: true,
        input_cost_per_1m: 1.25,
        output_cost_per_1m: 10,
        capability_tags: ["code"],
        status: "active",
        notes: null,
        created_at: "2026-05-01T00:00:00Z",
        updated_at: null,
      },
    ]);
    (getLlmModelDetail as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: "llm-1",
      name: "GPT Compiler",
      provider: "openai",
      model_id: "gpt-compiler",
      endpoint_type: "chat",
      context_window: 128000,
      max_output_tokens: 8192,
      supports_tools: true,
      supports_json: true,
      input_cost_per_1m: 1.25,
      output_cost_per_1m: 10,
      capability_tags: ["code"],
      status: "active",
      notes: "Use for compiler tasks.",
      created_at: "2026-05-01T00:00:00Z",
      updated_at: null,
    });
    (createLlmModel as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: "llm-new",
      name: "Local Code",
    });
  });

  it("lists LLM models", async () => {
    render(<ApiPage selectedId={null} />);
    expect(await screen.findByText("GPT Compiler")).toBeDefined();
    expect(await screen.findByText("openai")).toBeDefined();
  });

  it("creates an LLM model", async () => {
    const user = userEvent.setup();
    render(<ApiPage selectedId={null} />);

    await screen.findByText("GPT Compiler");
    await user.click(screen.getByRole("button", { name: /Create LLM/ }));
    await user.type(screen.getByLabelText("LLM Name"), "Local Code");
    await user.type(screen.getByLabelText("Provider"), "local");
    await user.type(screen.getByLabelText("Provider Model ID"), "llama-3");
    await user.click(screen.getByRole("button", { name: /^Create$/ }));

    await waitFor(() => {
      expect(createLlmModel).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "Local Code",
          provider: "local",
          model_id: "llama-3",
        }),
      );
    });
  });
});
