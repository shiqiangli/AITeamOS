/**
 * AITeamOS Dashboard - Agent Page Component Tests
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AgentPage } from "../pages/agents";

vi.mock("../api/client", () => ({
  listLlmModels: vi.fn(),
  getLlmModelDetail: vi.fn(),
  createLlmModel: vi.fn(),
  listAgentProfiles: vi.fn(),
  getAgentProfileDetail: vi.fn(),
  createAgentProfile: vi.fn(),
}));

import {
  listLlmModels,
  getLlmModelDetail,
  createLlmModel,
  listAgentProfiles,
  getAgentProfileDetail,
  createAgentProfile,
} from "../api/client";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("AgentPage", () => {
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
    (listAgentProfiles as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: "agent-1",
        name: "Compiler Agent",
        description: "Compiler work profile",
        runtime_kind: "llm_agent",
        default_llm_model_id: "llm-1",
        system_prompt: "Be precise.",
        tool_names: ["repo.search"],
        memory_policy: {},
        safety_policy: {},
        status: "active",
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
    (getAgentProfileDetail as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: "agent-1",
      name: "Compiler Agent",
      description: "Compiler work profile",
      runtime_kind: "llm_agent",
      default_llm_model_id: "llm-1",
      system_prompt: "Be precise.",
      tool_names: ["repo.search"],
      memory_policy: {},
      safety_policy: {},
      status: "active",
      created_at: "2026-05-01T00:00:00Z",
      updated_at: null,
    });
    (createAgentProfile as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: "agent-new",
      name: "Optimization Agent",
    });
    (createLlmModel as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: "llm-new",
      name: "Local Code",
    });
  });

  it("lists agents and LLM models in tabs", async () => {
    const user = userEvent.setup();
    render(<AgentPage selectedId={null} />);

    expect(await screen.findByText("Compiler Agent")).toBeDefined();
    await user.click(screen.getByRole("tab", { name: "LLMs" }));
    expect(await screen.findByText("GPT Compiler")).toBeDefined();
  });

  it("creates an agent profile with a default LLM selected by name", async () => {
    const user = userEvent.setup();
    render(<AgentPage selectedId={null} />);

    await screen.findByText("Compiler Agent");
    await user.click(await screen.findByRole("button", { name: /Create Agent/ }));
    await user.type(screen.getByLabelText("Agent Name"), "Optimization Agent");
    await user.type(screen.getByPlaceholderText("Select or type LLM name"), "GPT Compiler");
    await user.click(screen.getByRole("button", { name: /^Create$/ }));

    await waitFor(() => {
      expect(createAgentProfile).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "Optimization Agent",
          default_llm_model_id: "llm-1",
        }),
      );
    });
  });
});
