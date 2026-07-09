import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AssetsPage } from "../pages/assets";
import type { RuntimeApprovalRecord } from "../api/runtimeExecutors";

const status = {
  docs_count: 1,
  memories_count: 0,
  decisions_count: 0,
  review_queue_count: 0,
  asset_count: 1,
  saved_paths: {},
};

const assets = [
  {
    id: "report-1:evidence:0",
    kind: "evidence",
    title: "pytest passed",
    status: "approved",
    source_ticket: "rd-0001",
    source_employee: "peter",
    assigned_employees: ["alex", "peter"],
    scopes: ["rd", "doc:product-direction"],
    created_at: "2026-06-03T08:30:00Z",
    updated_at: "2026-06-03T08:30:00Z",
    metadata: { asset_domain: "work", asset_type: "evidence" },
  },
  {
    id: "product-model",
    kind: "doc",
    title: "Product Model",
    status: "approved",
    source_ticket: "",
    source_employee: "",
    assigned_employees: [],
    scopes: ["knowledge", "docs"],
    created_at: "2026-06-03T08:30:00Z",
    updated_at: "2026-06-03T08:30:00Z",
    metadata: { asset_domain: "knowledge", asset_type: "docs" },
  },
  {
    id: "list_employees",
    kind: "tool",
    title: "List employees",
    status: "ready",
    source_ticket: "",
    source_employee: "",
    assigned_employees: [],
    scopes: ["capabilities", "kernel-commands", "employees"],
    created_at: "2026-06-03T08:30:00Z",
    updated_at: "2026-06-03T08:30:00Z",
    metadata: {
      asset_domain: "capabilities",
      asset_type: "kernel-commands",
      source_kind: "kernel_command",
      description: "List file-backed employees.",
    },
  },
  {
    id: "mcp:github:repo.search",
    kind: "tool",
    title: "repo.search",
    status: "planned",
    source_ticket: "",
    source_employee: "",
    assigned_employees: [],
    scopes: ["capabilities", "mcp-tools", "repo"],
    created_at: "2026-06-03T08:30:00Z",
    updated_at: "2026-06-03T08:30:00Z",
    metadata: {
      asset_domain: "capabilities",
      asset_type: "mcp-tools",
      source_kind: "mcp_server",
      description: "GitHub exposes repo.search.",
    },
  },
  {
    id: "asset-registry:asset-closeout-ui",
    kind: "solution",
    title: "Closeout solution for Graphiti projection",
    status: "approved",
    source_ticket: "rd-0020",
    source_employee: "alex",
    assigned_employees: ["alex"],
    scopes: ["ticket:rd-0020", "solution"],
    created_at: "2026-06-03T08:35:00Z",
    updated_at: "2026-06-03T08:35:00Z",
    metadata: {
      asset_domain: "assets",
      asset_type: "solution",
      asset_registry_id: "asset-closeout-ui",
      content: "Closeout solution should project through Graphiti from the Assets page.",
      relationships: [{ type: "supersedes", target_kind: "asset", target_ref: "asset-closeout-v1" }],
      provenance: {},
    },
  },
  {
    id: "asset-registry:asset-improvement-ui",
    kind: "employee_improvement",
    title: "Runtime blocker triage improvement",
    status: "approved",
    source_ticket: "",
    source_employee: "alex",
    assigned_employees: ["alex"],
    scopes: ["employee:alex", "employee_improvement"],
    created_at: "2026-06-03T08:36:00Z",
    updated_at: "2026-06-03T08:36:00Z",
    metadata: {
      asset_domain: "assets",
      asset_type: "employee_improvement",
      asset_registry_id: "asset-improvement-ui",
      content: "Apply runtime blocker triage as governed Employee improvement.",
      provenance: {},
    },
  },
];

const skills = [
  {
    id: "test-engineering",
    title: "Test Engineering",
    description: "Test execution.",
    content: "# Test Engineering\n\nRun tests and report evidence.",
    assigned_employees: ["alex"],
    resources: [],
    saved_path: ".aiteamos/skills/test-engineering/SKILL.md",
  },
];

const docs = [
  {
    id: "product-model",
    title: "Product Model",
    path: ".aiteamos/knowledge/docs/PRODUCT_MODEL.md",
    excerpt: "Core product direction.",
    content: "# Product Model\n\nFull body for review.",
    source: "local",
    tags: ["product"],
    updated_at: "2026-06-03T08:30:00Z",
  },
];

const reviewItems = [
  {
    id: "mem-1",
    kind: "memory",
    title: "Memory candidate from ticket",
    content: "Remember the ticket asset review flow.",
    status: "proposed",
    source_ref: "rd-0001",
    created_at: "2026-06-03T08:30:00Z",
    updated_at: "2026-06-03T08:30:00Z",
    metadata: { scope_kind: "ticket", scope_ref: "rd-0001" },
  },
];

const approvedMemory = {
  id: "mem-approved-1",
  content: "Approved memory that can become stale.",
  status: "approved",
  source_kind: "ticket_summary",
  source_ref: "traces/run-approved",
  scope_kind: "ticket",
  scope_ref: "rd-0009",
  memory_type: "lesson",
  confidence: 0.88,
  employee_ids: ["clara"],
  tags: ["validation"],
  provenance: {
    source_ticket_id: "rd-0009",
    source_run_id: "run-approved-source",
    source_report_id: "report-approved-1",
    evidence_id: "evidence-approved-1",
    version_hash: "hash-approved-1",
    provider_refs: { graphiti_episode_id: "episode-approved-1" },
    usage_history: [
      {
        usage_id: "usage-approved-1",
        at: "2026-06-03T08:40:00Z",
        source_run_id: "run-approved-usage",
        source_trace_path: ".aiteamos/traces/run-approved-usage.jsonl",
        source_ticket_ids: ["rd-0009"],
        usefulness_status: "unreviewed",
      },
    ],
    usage_summary: {
      recall_count: 1,
      used_count: 0,
      irrelevant_count: 0,
      harmful_count: 0,
      promoted_count: 0,
      useful_count: 0,
      not_useful_count: 0,
      last_recalled_at: "2026-06-03T08:40:00Z",
      last_recalled_ticket_id: "rd-0009",
      last_recalled_run_id: "run-approved-usage",
      last_usefulness_status: "unreviewed",
    },
  },
  created_at: "2026-06-03T08:30:00Z",
  updated_at: "2026-06-03T08:30:00Z",
  approved_at: "2026-06-03T08:31:00Z",
  graphiti_episode_id: "episode-approved-1",
  graphiti_status: { status: "ingested" },
};

const capabilities = {
  status: {
    capability_count: 2,
    enabled_count: 1,
    configured_count: 1,
    ready_count: 1,
    tool_count: 2,
    kernel_command_count: 1,
    mcp_tool_count: 1,
    native_api_tool_count: 0,
    cli_tool_count: 0,
    ci_tool_count: 0,
    saved_paths: {},
  },
  capabilities: [
    {
      id: "list_employees",
      name: "List employees",
      kind: "tool",
      source_kind: "kernel_command",
      domain: "employees",
      source: "AITeamOS Kernel",
      status: "ready",
      enabled: true,
      configured: true,
      description: "List file-backed employees.",
      owner_scope: "Clara and authorized employees",
      permissions: ["employees:read"],
      required_settings: [],
      arguments: [],
      produces: ["chat_result"],
      boundary: "Read-only employee inventory.",
      deep_link: "#/employees",
      connector_id: "",
    },
    {
      id: "mcp:github:repo.search",
      name: "repo.search",
      kind: "tool",
      source_kind: "mcp_server",
      domain: "repo",
      source: "MCP server: GitHub",
      status: "planned",
      enabled: false,
      configured: false,
      description: "GitHub exposes repo.search.",
      owner_scope: "Authorized employees through connector adapter",
      permissions: ["repo:read"],
      required_settings: ["owner", "repo"],
      arguments: [],
      produces: ["external_result"],
      boundary: "External system semantics stay behind the connector adapter.",
      deep_link: "#/settings/tool-connectors",
      connector_id: "github",
    },
  ],
  model: {},
};

const systemStatus = {
  secrets: [],
  plan_v8_artifacts: {
    artifact_dir: ".aiteamos/artifacts/plan_v8",
    status: "ready",
    artifact_count: 4,
    agent_server_smoke_count: 1,
    live_provider_readiness_count: 1,
    context_retrieval_eval_count: 1,
    asset_provenance_eval_count: 1,
    latest_generated_at: "2026-06-21T03:45:00Z",
    latest_context_retrieval_eval: {
      name: "track-f-context-retrieval-eval-smoke.json",
      path: ".aiteamos/artifacts/plan_v8/track-f-context-retrieval-eval-smoke.json",
      kind: "context_retrieval_eval",
      status: "passed",
      generated_at: "2026-06-21T03:44:00Z",
      summary: {
        query: "Graphiti context Neo4j password provider dogfood",
        ticket_id: "rd-context-retrieval",
        graphiti_result_count: 1,
        graphiti_excluded_result_count: 2,
        active_asset_ids: ["asset-graphiti-context-solution"],
        recalled_memory_ids: ["mem-context-retrieval-note"],
        stale_hint_asset_ids: ["asset-graphiti-stale-solution", "asset-graphiti-conflicted-solution"],
        excluded_asset_ids: ["asset-graphiti-stale-solution"],
        wrong_ticket_filtered: true,
        work_history_eval_recall: 1,
        work_history_eval_precision_like: 1,
        work_history_missing_ref_count: 0,
        work_history_matched_ref_count: 3,
        provider_blocker_count: 0,
      },
    },
    latest_asset_provenance_eval: {
      name: "track-f-asset-provenance-eval-smoke.json",
      path: ".aiteamos/artifacts/plan_v8/track-f-asset-provenance-eval-smoke.json",
      kind: "asset_provenance_eval",
      status: "passed",
      generated_at: "2026-06-21T03:45:00Z",
      summary: {
        source_asset_id: "asset-provenance-new-guidance",
        target_asset_id: "asset-provenance-old-guidance",
        relationship_id: "asset-relationship-asset-provenance-new-guidance-supersedes-asset-provenance-old-guidance",
        relationship_projection_status: "ingested",
        relationship_ingested_count: 1,
        relationship_search_result_count: 1,
        stale_memory_id: "mem-stale-provenance",
        stale_review_status: "stale",
        stale_after_excluded_count: 1,
        stale_active_filtered: true,
      },
    },
    latest_agent_server_smoke: null,
    latest_live_provider_readiness: null,
    evidence_gaps: [],
    provider_blockers: [],
    records: [],
  },
  runtime_executors: [
    {
      executor_id: "claude_code",
      status: "setup_blocked",
      detail: "Claude Code-compatible Local CLI Executor is not configured.",
      capabilities: ["agent_loop", "repo:read", "repo:write", "compatible_local_cli"],
      supported_actions: ["inspect_code_repository", "implement_ticket"],
    },
  ],
  blockers: [],
};

const runtimeApproval: RuntimeApprovalRecord = {
  id: "approval-run-1",
  status: "requested",
  kind: "runtime_approval",
  ticket_id: "rd-0020",
  employee_id: "alex",
  executor_id: "claude_code",
  required_capability: "repo:write",
  risk_level: "high",
  reason: "Repo mutation requires approval before dispatch.",
  proposed_action: { action: "implement_ticket", ticket_id: "rd-0020", executor_id: "claude_code" },
  source_state_ref: "state://universal_employee_agent/run-1/governance_gate",
  source_state_snapshot_ref: ".aiteamos/execution_state_snapshots/run-1.json",
  current_graph_node: "governance_gate",
  checkpoint_ref: "langgraph:run-1",
  executor_session_ref: "lg-run-1",
  approval_request: {
    kind: "repo_mutation",
    ticket_id: "rd-0020",
    required_capability: "repo:write",
    executor_id: "claude_code",
  },
  source_request: {
    request_id: "run-1",
    employee_id: "alex",
    action_plan: { action: "implement_ticket", arguments: { ticket_id: "rd-0020" } },
  },
  source_result: { status: "needs_approval", report: "Approval required." },
  created_at: "2026-06-03T08:30:00Z",
  updated_at: "2026-06-03T08:30:00Z",
  reviewed_at: "",
  reviewer_employee_id: "",
  review_reason: "",
  last_run_request_id: "",
  last_run_status: "",
  last_ingestion_blocker: "",
  last_result: {},
  resume_result: {},
  run_history: [],
};

const assetCandidate = {
  id: "asset-candidate-skill-1",
  source_candidate_id: "mem-skill-1",
  asset_id: "asset-skill-1",
  asset_type: "skill",
  title: "Normalize external runtime outputs",
  content: "Preserve Ticket provenance before promoting external runtime knowledge.",
  content_ref: "memory_candidate://mem-skill-1",
  status: "proposed",
  scope_kind: "ticket",
  scope_ref: "rd-0020",
  owner_employee_id: "alex",
  source_kind: "external_runtime_skill_candidate",
  source_ref: ".aiteamos/traces/run-1.jsonl",
  provenance: { source_ticket_id: "rd-0020", source_employee_id: "alex" },
  provider: "local_file",
  provider_ref: ".aiteamos/assets/candidates.json#asset-candidate-skill-1",
  relationships: [{ type: "derived_from_ticket", target_kind: "ticket", target_ref: "rd-0020" }],
  review_state: "proposed",
  usefulness_stats: {},
  created_at: "2026-06-03T08:30:00Z",
  updated_at: "2026-06-03T08:30:00Z",
};

const toolCallAssetCandidate = {
  id: "asset-candidate-tool-call-1",
  source_candidate_id: "mem-tool-call-1",
  asset_id: "asset-tool-call-1",
  asset_type: "tool_call",
  title: "Tool call terminal.run:run",
  content: "Tool call: terminal.run:run Event: command.completed Status: completed",
  content_ref: "memory_candidate://mem-tool-call-1",
  status: "proposed",
  scope_kind: "ticket",
  scope_ref: "rd-0020",
  owner_employee_id: "alex",
  source_kind: "execution_tool_event",
  source_ref: ".aiteamos/traces/run-tool-call.jsonl#tool-event-0",
  provenance: {
    source_ticket_id: "rd-0020",
    source_employee_id: "alex",
    source_run_id: "run-tool-call",
    source_trace_path: ".aiteamos/traces/run-tool-call.jsonl",
    tool_event_index: 0,
    tool_event_name: "command.completed",
    command_id: "terminal.run:run",
    executor_id: "local_tool",
  },
  provider: "local_file",
  provider_ref: ".aiteamos/assets/candidates.json#asset-candidate-tool-call-1",
  relationships: [{ type: "derived_from_ticket", target_kind: "ticket", target_ref: "rd-0020" }],
  review_state: "proposed",
  usefulness_stats: {},
  created_at: "2026-06-03T08:32:00Z",
  updated_at: "2026-06-03T08:32:00Z",
};

describe("AssetsPage", () => {
  let approvedMemories: unknown[] = [];
  let runtimeApprovals: RuntimeApprovalRecord[] = [];
  let assetCandidates: Array<typeof assetCandidate | typeof toolCallAssetCandidate> = [];

  beforeEach(() => {
    approvedMemories = [];
    runtimeApprovals = [{ ...runtimeApproval }];
    assetCandidates = [{ ...assetCandidate }, { ...toolCallAssetCandidate }];
    assets[4].metadata.provenance = {};
    assets[5].metadata.provenance = {};
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        let body: unknown = [];
        if (url.includes("/memory/candidates/") && url.includes("/usage/") && url.includes("/review")) {
          const review = JSON.parse(String(init?.body ?? "{}")) as { usefulness_status?: string };
          body = {
            ...approvedMemory,
            provenance: {
              ...approvedMemory.provenance,
              usage_history: [
                {
                  usage_id: "usage-approved-1",
                  at: "2026-06-03T08:40:00Z",
                  source_run_id: "run-approved-usage",
                  source_trace_path: ".aiteamos/traces/run-approved-usage.jsonl",
                  source_ticket_ids: ["rd-0009"],
                  usefulness_status: review.usefulness_status ?? "used",
                },
              ],
              usage_summary: {
                recall_count: 1,
                used_count: 1,
                irrelevant_count: 0,
                harmful_count: 0,
                promoted_count: 0,
                useful_count: 1,
                not_useful_count: 0,
                last_recalled_at: "2026-06-03T08:40:00Z",
                last_recalled_ticket_id: "rd-0009",
                last_recalled_run_id: "run-approved-usage",
                last_usefulness_status: review.usefulness_status ?? "used",
              },
            },
          };
        } else if (url.includes("/memory/candidates/") && url.includes("/review")) {
          const review = JSON.parse(String(init?.body ?? "{}")) as { status?: string };
          if (review.status === "stale") approvedMemories = [];
          body = { ...approvedMemory, id: url.split("/memory/candidates/")[1].split("/review")[0], status: review.status ?? "rejected" };
        }
        if (url.includes("/runtime-executors/claude_code/approvals/") && url.includes("/review")) {
          const review = JSON.parse(String(init?.body ?? "{}")) as { status?: string; reason?: string };
          runtimeApprovals = runtimeApprovals.map((item) => item.id === "approval-run-1"
            ? {
                ...item,
                status: review.status ?? "approved",
                reviewed_at: "2026-06-03T08:41:00Z",
                reviewer_employee_id: "clara",
                review_reason: review.reason ?? "",
                updated_at: "2026-06-03T08:41:00Z",
              }
            : item);
          body = runtimeApprovals[0];
        } else if (url.includes("/runtime-executors/claude_code/approvals/") && url.includes("/run")) {
          runtimeApprovals = runtimeApprovals.map((item) => item.id === "approval-run-1"
            ? {
                ...item,
                status: "approved",
                last_run_request_id: "run-1-approved-approval-run-1-attempt-1",
                last_run_status: "blocked",
                last_ingestion_blocker: "Claude Code-compatible Local CLI Executor is not configured.",
                last_result: {
                  status: "blocked",
                  report: "Claude Code-compatible Local CLI Executor is not configured.",
                  errors: [{ reason: "runtime_setup_blocked", detail: "Set CLAUDE_CODE_BIN." }],
                },
                run_history: [
                  ...item.run_history,
                  {
                    run_request_id: "run-1-approved-approval-run-1-attempt-1",
                    status: "blocked",
                    ingested: false,
                    ingestion_blocker: "Claude Code-compatible Local CLI Executor is not configured.",
                    executor_id: "claude_code",
                    trace_ref: ".aiteamos/traces/run-1-approved-approval-run-1-attempt-1.jsonl",
                    approval_refs: ["approval-run-1"],
                    approved_capabilities: ["repo:write"],
                    artifact_count: 0,
                    evidence_count: 0,
                    error_count: 1,
                    created_at: "2026-06-03T08:42:00Z",
                  },
                ],
                updated_at: "2026-06-03T08:42:00Z",
              }
            : item);
          body = {
            approval: runtimeApprovals[0],
            request: { request_id: "run-1-approved-approval-run-1-attempt-1" },
            result: runtimeApprovals[0].last_result,
            ingested: false,
            ingestion_blocker: "Claude Code-compatible Local CLI Executor is not configured.",
          };
        } else if (url.includes("/runtime-executors/claude_code/approvals")) {
          body = runtimeApprovals;
        }
        if (url.includes("/assets/records/asset-closeout-ui/relationships/project/graphiti")) {
          assets[4].metadata.provenance = {
            ...(assets[4].metadata.provenance as Record<string, unknown>),
            graphiti_relationships: [
              {
                relationship_id: "asset-relationship-asset-closeout-ui-supersedes-asset-closeout-v1",
                relationship_type: "supersedes",
                source_asset_id: "asset-closeout-ui",
                target_asset_id: "asset-closeout-v1",
                status: "ingested",
                episode_id: "episode-asset-closeout-ui-relationship",
              },
            ],
          };
          body = {
            asset_id: "asset-closeout-ui",
            status: "ingested",
            detail: "Approved AssetRecord relationships were projected to Graphiti.",
            ingested_relationships: [
              {
                relationship_id: "asset-relationship-asset-closeout-ui-supersedes-asset-closeout-v1",
                relationship_type: "supersedes",
                source_asset_id: "asset-closeout-ui",
                target_asset_id: "asset-closeout-v1",
                status: "ingested",
                ingested_asset: { episode_id: "episode-asset-closeout-ui-relationship" },
              },
            ],
            skipped_relationships: [],
            unsupported_relationships: [],
            saved_paths: {},
          };
        } else if (url.includes("/assets/records/asset-closeout-ui/project/graphiti")) {
          assets[4].metadata.provenance = {
            graphiti_status: {
              status: "ingested",
              episode_id: "episode-asset-closeout-ui",
            },
          };
          body = {
            asset_id: "asset-closeout-ui",
            status: "ingested",
            detail: "Approved AssetRecord was projected to Graphiti.",
            ingested_asset: { episode_id: "episode-asset-closeout-ui" },
            skipped_asset: null,
            saved_paths: {},
          };
        } else if (url.includes("/employees/alex/improvement-assets/asset-improvement-ui/apply")) {
          assets[5].metadata.provenance = {
            employee_improvement_application: {
              status: "applied",
              employee_id: "alex",
              applied_by_employee_id: "clara",
            },
          };
          body = {
            employee_id: "alex",
            asset_id: "asset-improvement-ui",
            status: "applied",
            detail: "Approved Employee improvement Asset was applied.",
            applied_changes: {
              skill_refs: ["runtime-blocker-triage"],
              memory_scopes: ["employee:alex:runtime-blockers"],
              capability_tags: ["runtime-debugging"],
              personality_tags: ["evidence-driven"],
            },
            profile: {},
            asset: {},
            ticket_report_id: "report-improvement-applied",
            saved_paths: {},
          };
        } else if (url.includes("/assets/candidates/review-batch")) {
          const review = JSON.parse(String(init?.body ?? "{}")) as {
            candidate_ids?: string[];
            status?: string;
            reason?: string;
          };
          const ids = review.candidate_ids ?? [];
          assetCandidates = assetCandidates.map((item) => ids.includes(item.id)
            ? {
                ...item,
                status: review.status ?? "approved",
                review_state: review.status ?? "approved",
                updated_at: "2026-06-03T08:46:00Z",
                provenance: {
                  ...item.provenance,
                  last_review_reason: review.reason ?? "",
                },
              }
            : item);
          body = {
            status: "completed",
            requested_count: ids.length,
            reviewed_count: ids.length,
            failed_count: 0,
            results: ids.map((id) => {
              const candidate = assetCandidates.find((item) => item.id === id);
              return {
                candidate_id: id,
                status: "reviewed",
                response: {
                  candidate,
                  review: {
                    id: `asset-review-${id}-batch`,
                    candidate_id: id,
                    asset_id: `asset-${id}`,
                    status: review.status ?? "approved",
                    reviewer_employee_id: "clara",
                    reason: review.reason ?? "",
                    merge_target_asset_id: "",
                    link_relationships: [],
                    created_at: "2026-06-03T08:46:00Z",
                    updated_at: "2026-06-03T08:46:00Z",
                  },
                  asset: review.status === "approved" ? {
                    id: `asset-${id}`,
                    asset_type: candidate?.asset_type ?? "asset",
                    title: candidate?.title ?? id,
                    content: candidate?.content ?? "",
                    status: "approved",
                  } : null,
                  saved_paths: {},
                },
                error: "",
              };
            }),
            saved_paths: {},
          };
        } else if (url.includes("/assets/candidates/") && url.includes("/review")) {
          const review = JSON.parse(String(init?.body ?? "{}")) as {
            status?: string;
            reason?: string;
            merge_target_asset_id?: string;
            link_relationships?: Array<Record<string, unknown>>;
          };
          assetCandidates = assetCandidates.map((item) => item.id === "asset-candidate-skill-1"
            ? {
                ...item,
                status: review.status ?? "approved",
                review_state: review.status ?? "approved",
                updated_at: "2026-06-03T08:45:00Z",
                provenance: {
                  ...item.provenance,
                  last_review_reason: review.reason ?? "",
                },
              }
            : item);
          body = {
            candidate: assetCandidates[0],
            review: {
              id: "asset-review-asset-candidate-skill-1-1",
              candidate_id: "asset-candidate-skill-1",
              asset_id: "asset-skill-1",
              status: review.status ?? "approved",
              reviewer_employee_id: "clara",
              reason: review.reason ?? "",
              merge_target_asset_id: review.merge_target_asset_id ?? "",
              link_relationships: review.link_relationships ?? [],
              created_at: "2026-06-03T08:45:00Z",
              updated_at: "2026-06-03T08:45:00Z",
            },
            asset: review.status === "approved" ? {
              id: "asset-skill-1",
              asset_type: "skill",
              title: "Normalize external runtime outputs",
              content: "Preserve Ticket provenance before promoting external runtime knowledge.",
              status: "approved",
            } : null,
            saved_paths: {},
          };
        } else if (url.includes("/assets/candidates")) {
          body = assetCandidates;
        }
        if (url.includes("/system-status")) body = systemStatus;
        if (url.includes("/knowledge/status")) body = status;
        if (url.includes("/chat/skills")) body = skills;
        if (url.includes("/knowledge/docs")) body = docs;
        if (url.includes("/memory/approved")) body = approvedMemories;
        if (url.includes("/knowledge/decisions")) body = [];
        if (url.includes("/knowledge/review-queue")) body = reviewItems;
        if (url.includes("/capabilities")) body = capabilities;
        if (url.includes("/assets") && !url.includes("/assets/candidates") && !url.includes("/assets/records/")) body = assets;
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders Overview with recent changes when no area selected", async () => {
    render(<AssetsPage selectedArea={null} selectedDetail={null} />);

    expect(await screen.findByText("Recent Changes")).toBeTruthy();
    expect((await screen.findAllByText("pytest passed")).length).toBeGreaterThan(0);
    expect(await screen.findByText("Recall Quality Evidence")).toBeTruthy();
    expect(screen.getByText("Scoped Retrieval")).toBeTruthy();
    expect(screen.getByText("Provenance Exclusion")).toBeTruthy();
    expect(screen.getByText("asset-graphiti-context-solution")).toBeTruthy();
    expect(screen.getByText("mem-context-retrieval-note")).toBeTruthy();
    expect(screen.getAllByText("asset-graphiti-stale-solution").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("asset-provenance-new-guidance")).toBeTruthy();
    expect(screen.getAllByText("filtered").length).toBeGreaterThanOrEqual(2);
  });

  it("renders Knowledge Docs with breadcrumb and doc list", async () => {
    render(<AssetsPage selectedArea="knowledge" selectedDetail="docs" />);

    expect((await screen.findAllByText("Knowledge")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("Docs")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("Product Model")).length).toBeGreaterThan(0);
  });

  it("opens a read-only full text dialog from doc detail", async () => {
    render(<AssetsPage selectedArea="knowledge" selectedDetail="docs" />);

    fireEvent.click((await screen.findAllByText("Product Model"))[0]);
    fireEvent.click(await screen.findByText("Open Full Text"));

    await waitFor(() => {
      expect((screen.getByLabelText("Asset full text") as HTMLTextAreaElement).value).toContain("Full body for review.");
    });
  });

  it("opens a route-backed memory drawer from an Assets deep link", async () => {
    approvedMemories = [approvedMemory];
    render(<AssetsPage selectedArea="knowledge" selectedDetail="memory:mem-approved-1" />);

    expect(await screen.findByText("Graphiti Provenance")).toBeTruthy();
    expect(screen.getAllByText("Approved memory that can become stale.").length).toBeGreaterThan(1);
    expect(screen.getByText("mem-approved-1 / lesson")).toBeTruthy();
  });

  it("opens a route-backed asset candidate drawer from an Assets deep link", async () => {
    render(<AssetsPage selectedArea="review" selectedDetail="candidate:asset-candidate-skill-1" />);

    expect((await screen.findAllByText("skill · Normalize external runtime outputs")).length).toBeGreaterThan(1);
    expect(screen.getByText("asset candidate · asset-candidate-skill-1")).toBeTruthy();
    expect(screen.getByLabelText("Target Asset ID")).toBeTruthy();
  });

  it("opens a route-backed AssetRecord drawer from an Assets deep link", async () => {
    render(<AssetsPage selectedArea="asset" selectedDetail="asset-registry:asset-closeout-ui" />);

    expect((await screen.findAllByText("Closeout solution for Graphiti projection")).length).toBeGreaterThan(1);
    expect(screen.getByText("Provider Projection")).toBeTruthy();
    expect(screen.getByText("asset-closeout-ui")).toBeTruthy();
  });

  it("closes the current detail drawer when switching knowledge sub-tabs", async () => {
    const { rerender } = render(<AssetsPage selectedArea="knowledge" selectedDetail="docs" />);

    fireEvent.click((await screen.findAllByText("Product Model"))[0]);
    expect(await screen.findByText("Open Full Text")).toBeTruthy();

    rerender(<AssetsPage selectedArea="knowledge" selectedDetail="memories" />);
    await waitFor(() => expect(screen.queryByText("Open Full Text")).toBeNull());
  });

  it("can project an approved AssetRecord to Graphiti from the asset drawer", async () => {
    render(<AssetsPage selectedArea={null} selectedDetail={null} />);

    fireEvent.change(await screen.findByLabelText("Search assets"), { target: { value: "Closeout solution" } });
    fireEvent.submit(screen.getByLabelText("Search assets").closest("form") as HTMLFormElement);
    fireEvent.click(await screen.findByText("Closeout solution for Graphiti projection"));

    expect(await screen.findByText("Provider Projection")).toBeTruthy();
    expect(await screen.findByText("not projected")).toBeTruthy();
    fireEvent.click(await screen.findByText("Project Graphiti"));

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/assets/records/asset-closeout-ui/project/graphiti",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  it("can project approved AssetRecord relationships to Graphiti from the asset drawer", async () => {
    render(<AssetsPage selectedArea={null} selectedDetail={null} />);

    fireEvent.change(await screen.findByLabelText("Search assets"), { target: { value: "Closeout solution" } });
    fireEvent.submit(screen.getByLabelText("Search assets").closest("form") as HTMLFormElement);
    fireEvent.click(await screen.findByText("Closeout solution for Graphiti projection"));

    expect(await screen.findByText("Provider Projection")).toBeTruthy();
    expect(await screen.findByText("0/1 not projected")).toBeTruthy();
    expect(screen.getByText("supersedes:asset-closeout-v1")).toBeTruthy();
    fireEvent.click(await screen.findByText("Project Relationships"));

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/assets/records/asset-closeout-ui/relationships/project/graphiti",
        expect.objectContaining({ method: "POST" }),
      );
    });
    expect(await screen.findByText("1/1 projected")).toBeTruthy();
    expect(screen.getByText("asset-relationship-asset-closeout-ui-supersedes-asset-closeout-v1")).toBeTruthy();
  });

  it("can apply an approved Employee improvement AssetRecord from the asset drawer", async () => {
    render(<AssetsPage selectedArea={null} selectedDetail={null} />);

    fireEvent.change(await screen.findByLabelText("Search assets"), { target: { value: "Runtime blocker triage" } });
    fireEvent.submit(screen.getByLabelText("Search assets").closest("form") as HTMLFormElement);
    fireEvent.click(await screen.findByText("Runtime blocker triage improvement"));

    expect(await screen.findByText("Employee Improvement")).toBeTruthy();
    expect(await screen.findByText("not applied")).toBeTruthy();
    fireEvent.click(await screen.findByText("Apply Improvement"));

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/employees/alex/improvement-assets/asset-improvement-ui/apply",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"actor_employee_id":"clara"'),
        }),
      );
    });
  });

  it("shows review item details and opens review full text", async () => {
    render(<AssetsPage selectedArea="review" selectedDetail={null} />);

    fireEvent.click(await screen.findByText("Memory candidate from ticket"));
    expect((await screen.findAllByText("Remember the ticket asset review flow.")).length).toBeGreaterThan(0);

    fireEvent.click(await screen.findByText("Open Full Text"));
    await waitFor(() => {
      expect((screen.getByLabelText("Asset full text") as HTMLTextAreaElement).value).toContain("Remember the ticket asset review flow.");
    });
  });

  it("can reject a proposed memory from the review queue", async () => {
    render(<AssetsPage selectedArea="review" selectedDetail={null} />);

    fireEvent.click(await screen.findByText("Memory candidate from ticket"));
    const rejectButtons = await screen.findAllByText("Reject");
    fireEvent.click(rejectButtons[rejectButtons.length - 1]);

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/memory/candidates/mem-1/review",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"status":"rejected"'),
        }),
      );
    });
  });

  it("shows asset candidates in review queue and can approve them", async () => {
    render(<AssetsPage selectedArea="review" selectedDetail="skills" />);

    expect(await screen.findByText(/skill · Normalize external runtime outputs/)).toBeTruthy();
    expect(await screen.findByText(/Preserve Ticket provenance/)).toBeTruthy();

    fireEvent.click(await screen.findByText(/skill · Normalize external runtime outputs/));
    expect(await screen.findByText("Asset type")).toBeTruthy();
    expect(await screen.findByText("Open Full Text")).toBeTruthy();

    fireEvent.click((await screen.findAllByText("Approve"))[0]);
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/assets/candidates/asset-candidate-skill-1/review",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"status":"approved"'),
        }),
      );
    });
  });

  it("can approve an asset candidate with a relationship target", async () => {
    render(<AssetsPage selectedArea="review" selectedDetail="skills" />);

    fireEvent.click(await screen.findByText(/skill · Normalize external runtime outputs/));
    fireEvent.change(await screen.findByLabelText("Target Asset ID"), { target: { value: "asset-skill-old" } });
    fireEvent.change(await screen.findByLabelText("Relationship type"), { target: { value: "supersedes" } });

    const approveButtons = await screen.findAllByText("Approve");
    fireEvent.click(approveButtons[approveButtons.length - 1]);

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/assets/candidates/asset-candidate-skill-1/review",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"type":"supersedes"'),
        }),
      );
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/assets/candidates/asset-candidate-skill-1/review",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"target_ref":"asset-skill-old"'),
        }),
      );
    });
  });

  it("can link an asset candidate to an existing asset without promotion", async () => {
    render(<AssetsPage selectedArea="review" selectedDetail="skills" />);

    fireEvent.click(await screen.findByText(/skill · Normalize external runtime outputs/));
    fireEvent.change(await screen.findByLabelText("Target Asset ID"), { target: { value: "asset-skill-existing" } });
    fireEvent.click(await screen.findByText("Link"));

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/assets/candidates/asset-candidate-skill-1/review",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"status":"linked"'),
        }),
      );
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/assets/candidates/asset-candidate-skill-1/review",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"merge_target_asset_id":"asset-skill-existing"'),
        }),
      );
    });
  });

  it("can batch approve visible asset candidates from the review queue", async () => {
    render(<AssetsPage selectedArea="review" selectedDetail={null} />);

    fireEvent.click(await screen.findByText("Approve All"));

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/assets/candidates/review-batch",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"candidate_ids":["asset-candidate-skill-1","asset-candidate-tool-call-1"]'),
        }),
      );
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/assets/candidates/review-batch",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"status":"approved"'),
        }),
      );
    });
  });

  it("shows typed tool call details for tool_call asset candidates", async () => {
    render(<AssetsPage selectedArea="review" selectedDetail="tools" />);

    expect(await screen.findByText(/tool call · Tool call terminal.run:run/)).toBeTruthy();
    fireEvent.click(await screen.findByText(/tool call · Tool call terminal.run:run/));

    expect(await screen.findByText("Tool Call")).toBeTruthy();
    expect(screen.getByText("Command")).toBeTruthy();
    expect(screen.getAllByText("terminal.run:run").length).toBeGreaterThan(0);
    expect(screen.getByText("Event")).toBeTruthy();
    expect(screen.getAllByText("command.completed").length).toBeGreaterThan(0);
    expect(screen.getByText("Run")).toBeTruthy();
    expect(screen.getAllByText("run-tool-call").length).toBeGreaterThan(0);
    expect(screen.getByText("Executor")).toBeTruthy();
    expect(screen.getAllByText("local_tool").length).toBeGreaterThan(0);
  });

  it("shows runtime approval records in review tools and can approve and run them", async () => {
    render(<AssetsPage selectedArea="review" selectedDetail="tools" />);

    expect(await screen.findByText(/claude_code repo:write/)).toBeTruthy();
    expect(await screen.findByText("Repo mutation requires approval before dispatch.")).toBeTruthy();

    const approveButtons = await screen.findAllByText("Approve");
    fireEvent.click(approveButtons[approveButtons.length - 1]);
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/runtime-executors/claude_code/approvals/approval-run-1/review",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"status":"approved"'),
        }),
      );
    });

    fireEvent.click((await screen.findAllByText("Run"))[0]);
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/runtime-executors/claude_code/approvals/approval-run-1/run",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"ingest_result":true'),
        }),
      );
    });
    expect((await screen.findAllByText(/Claude Code-compatible Local CLI Executor is not configured/)).length).toBeGreaterThan(0);
    expect(await screen.findByText("Ingestion blocker")).toBeTruthy();
    expect(await screen.findByText("Run History")).toBeTruthy();
    expect(await screen.findByText("Attempt 1")).toBeTruthy();
    expect((await screen.findAllByText(/run-1-approved-approval-run-1-attempt-1/)).length).toBeGreaterThan(0);
  });

  it("can mark an approved memory stale from the memory detail", async () => {
    approvedMemories = [approvedMemory];

    render(<AssetsPage selectedArea="knowledge" selectedDetail="memories" />);

    fireEvent.click(await screen.findByText("ticket:rd-0009"));
    fireEvent.click(await screen.findByText("Mark Stale"));

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/memory/candidates/mem-approved-1/review",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"status":"stale"'),
        }),
      );
    });
  });

  it("can mark the latest memory recall used from the memory detail", async () => {
    approvedMemories = [approvedMemory];

    render(<AssetsPage selectedArea="knowledge" selectedDetail="memories" />);

    fireEvent.click(await screen.findByText("ticket:rd-0009"));
    expect(await screen.findByText("Recall count")).toBeTruthy();
    expect(await screen.findByText("Graphiti Provenance")).toBeTruthy();
    expect(await screen.findByText("episode-approved-1")).toBeTruthy();
    expect(await screen.findByText("mem-approved-1 / lesson")).toBeTruthy();
    expect(await screen.findByText("run-approved-source")).toBeTruthy();
    expect(await screen.findByText("report-approved-1")).toBeTruthy();
    expect(await screen.findByText("evidence-approved-1")).toBeTruthy();
    expect(await screen.findByText("hash-approved-1")).toBeTruthy();
    expect(await screen.findByText("Related Tickets")).toBeTruthy();
    expect(await screen.findByText("Usage History")).toBeTruthy();
    expect(await screen.findByText("usage-approved-1")).toBeTruthy();
    expect(await screen.findByText("Run: run-approved-usage")).toBeTruthy();
    expect(await screen.findByText("Trace: .aiteamos/traces/run-approved-usage.jsonl")).toBeTruthy();
    fireEvent.click(await screen.findByText("Mark Used"));

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        "/api/v1/memory/candidates/mem-approved-1/usage/usage-approved-1/review",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"usefulness_status":"used"'),
        }),
      );
    });
    expect(screen.getByText("Mark Irrelevant")).toBeTruthy();
    expect(screen.getByText("Mark Harmful")).toBeTruthy();
    expect(screen.getByText("Promote")).toBeTruthy();
  });

  it("renders flattened capability tool tabs", async () => {
    const { rerender } = render(<AssetsPage selectedArea="capabilities" selectedDetail="kernel-commands" />);

    expect((await screen.findAllByText("Kernel Commands")).length).toBeGreaterThan(0);
    expect(await screen.findByText("List employees")).toBeTruthy();

    rerender(<AssetsPage selectedArea="capabilities" selectedDetail="mcp-tools" />);

    expect((await screen.findAllByText("MCP Tools")).length).toBeGreaterThan(0);
    expect(await screen.findByText("repo.search")).toBeTruthy();
  });
});
