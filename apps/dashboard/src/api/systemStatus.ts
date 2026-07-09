import { apiRequest } from "./client";
import type { GraphitiBackendStatus } from "./memory";
import type { TicketBackendStatus } from "./tickets";

export interface SystemStatusSecretItem {
  id: string;
  scope: string;
  purpose: string;
  env_vars: string[];
  required_for: string;
  configured: boolean;
  how_to_configure: string;
}

export interface RuntimeExecutorStatus {
  executor_id: string;
  status: string;
  detail: string;
  capabilities: string[];
  supported_actions?: string[];
  missing_env?: string[];
  setup_url?: string;
  configured?: Record<string, boolean>;
  config?: Record<string, string | number | boolean | null | undefined>;
  config_env?: Record<string, string>;
  delivery?: {
    configured_mode?: string;
    supported_modes?: string[];
    prompt_delivery?: string;
    default_mode?: string;
    non_destructive_default?: boolean;
  };
  expected_output_schema?: Record<string, string>;
  safety_policy?: {
    default_mode?: string;
    repo_mutation_guard?: string[];
    completion_policy?: string;
  };
  diagnostics?: {
    smoke?: {
      endpoint?: string;
      method?: string;
      default_ingest_result?: boolean;
      ingest_requires_ticket?: boolean;
      mode?: string;
      dispatch_boundary?: string;
    };
    dogfood?: {
      endpoint?: string;
      method?: string;
      creates_ticket_if_missing?: boolean;
      approval_required?: boolean;
      ingest_requires_ticket?: boolean;
      repo_mutation_guard?: string[];
      dispatch_boundary?: string;
    };
  };
}

export interface LiveProviderDogfoodReadiness {
  status: string;
  profile?: string;
  selected_executor_id: string;
  require_repo_write_executor: boolean;
  mutation_gate: Record<string, unknown>;
  selected_executor_preflight: Record<string, unknown>;
  repo_write_executor_candidates: Array<{
    executor_id: string;
    display_name: string;
    status: string;
    detail: string;
    capabilities: string[];
    setup_required: string[];
    ready: boolean;
    health: Record<string, unknown>;
  }>;
  provider_prerequisites: {
    ticket_backend?: Record<string, unknown>;
    memory_backend?: Record<string, unknown>;
    provider_smoke?: Record<string, unknown>;
  };
  blockers: Array<Record<string, unknown>>;
  warnings: Array<Record<string, unknown>>;
  summary: Record<string, unknown>;
}

export interface LiveProviderSoakScenario {
  id: string;
  title: string;
  expected_state: string;
  status: string;
  detail: string;
  command: string;
  required_evidence: string[];
  ui_surfaces: string[];
  blockers: string[];
}

export interface LiveProviderSoakPlanResponse {
  contract_version: string;
  status: string;
  detail: string;
  summary: {
    scenario_count: number;
    ready_scenario_count: number;
    blocked_scenario_count: number;
    expected_state_count: number;
    expected_states: string[];
    mutation_gate_open: boolean;
    ticket_backend_status: string;
    ticket_backend_mode?: string;
    ticket_backend_provider?: string;
    plane_ticket_backend_selected?: boolean;
    plane_ticket_backend_setup_status?: string;
    plane_ticket_backend_setup_required?: string[];
    plane_ticket_scope_status?: string;
    plane_ticket_scope_candidate_count?: number;
    plane_ticket_scope_missing_count?: number;
    plane_ticket_scope_setup_action?: string;
    memory_backend_status: string;
    selected_executor_id: string;
    ready_to_execute: boolean;
    contract_version: string;
  };
  blockers: string[];
  scenarios: LiveProviderSoakScenario[];
  commands: string[];
  evidence_refs: string[];
}

export interface LiveProviderSoakEvidenceScenario {
  id: string;
  title: string;
  expected_state: string;
  status: string;
  detail: string;
  command: string;
  execution_kind: string;
  operator_action: string;
  artifact_name: string;
  artifact_path: string;
  artifact_schema: string;
  artifact_status: string;
  generated_at: string;
  required_evidence: string[];
  observed_evidence: string[];
  missing_evidence: string[];
  blockers: string[];
  ui_surfaces: string[];
}

export interface LiveProviderSoakEvidenceResponse {
  contract_version: string;
  status: string;
  detail: string;
  summary: {
    scenario_count: number;
    passed_scenario_count: number;
    blocked_scenario_count: number;
    failed_scenario_count: number;
    missing_scenario_count: number;
    warning_scenario_count: number;
    latest_generated_at: string;
    mutation_gate_open: boolean;
    ready_to_execute: boolean;
    ready_for_release: boolean;
    live_write_scenario_count: number;
    remaining_live_write_scenario_count: number;
    passed_non_mutating_scenario_count: number;
    operator_action_required: boolean;
    operator_action: string;
    mutation_gate_env_var: string;
    live_write_targets: string[];
    contract_version: string;
  };
  blockers: string[];
  scenarios: LiveProviderSoakEvidenceScenario[];
  commands: string[];
  evidence_refs: string[];
}

export interface ProviderSetupBlocker {
  id: string;
  status: string;
  detail: string;
  setup_required: string[];
}

export interface ProviderContractExpectation {
  id: string;
  category: string;
  required: string[];
  satisfied: string[];
  missing: string[];
  status: string;
}

export interface ProviderProductionEvaluation {
  schema_version: string;
  migration_status: string;
  required_for_core: boolean;
  production_ready: boolean;
  readiness_level: string;
  blockers: string[];
  warnings: string[];
}

export interface ProviderConformanceRecord {
  provider_id: string;
  provider_kind: string;
  implementation: string;
  display_name: string;
  selected: boolean;
  status: string;
  detail: string;
  setup_blockers: ProviderSetupBlocker[];
  capabilities: string[];
  conformance_smoke: Record<string, unknown>;
  projection_direction: string[];
  failure_semantics: string[];
  domain_boundary: string[];
  contract_expectations?: ProviderContractExpectation[];
  production_evaluation?: ProviderProductionEvaluation;
  fallback_provider: string;
  provider_ref: Record<string, unknown>;
}

export interface ProviderConformanceResponse {
  contract_version: string;
  providers: ProviderConformanceRecord[];
  summary: {
    provider_count: number;
    ready_count: number;
    blocked_count: number;
    selected_provider_count: number;
    core_required_count?: number;
    production_ready_count?: number;
    core_blocked_count?: number;
    optional_warning_count?: number;
    runtime_boundary_status?: string;
    runtime_boundary_checks?: string[];
    runtime_boundary_warnings?: string[];
    runtime_boundary_blockers?: string[];
    contract_version: string;
    core_model_boundary: string;
  };
}

export interface ProviderConformanceSmokeRecord {
  provider_id: string;
  provider_kind: string;
  implementation: string;
  status: string;
  detail: string;
  smoke_kind: string;
  checks: string[];
  warnings: string[];
  failures: string[];
  blockers: Array<Record<string, unknown>>;
  evidence: Record<string, unknown>;
  external_calls: boolean;
}

export interface ProviderConformanceSmokeResponse {
  contract_version: string;
  status: string;
  results: ProviderConformanceSmokeRecord[];
  summary: {
    provider_count: number;
    passed_count: number;
    blocked_count: number;
    warning_count: number;
    failed_count: number;
    contract_version: string;
    external_calls: boolean;
    include_external: boolean;
    evaluation_scope: string;
    non_destructive: boolean;
  };
}

export interface EnvironmentSmokeCheckRecord {
  id: string;
  scope: string;
  status: string;
  detail: string;
  checks: string[];
  warnings: string[];
  failures: string[];
  blockers: Array<Record<string, unknown>>;
  evidence: Record<string, unknown>;
  external_calls: boolean;
}

export interface EnvironmentSmokeResponse {
  contract_version: string;
  status: string;
  checks: EnvironmentSmokeCheckRecord[];
  provider_smoke?: ProviderConformanceSmokeResponse | null;
  summary: {
    check_count: number;
    passed_count: number;
    blocked_count: number;
    warning_count: number;
    failed_count: number;
    contract_version: string;
    external_calls: boolean;
    include_external: boolean;
    evaluation_scope: string;
    non_destructive: boolean;
    core_boundary: string;
  };
}

export interface SchemaStoreRecord {
  id: string;
  domain: string;
  display_name: string;
  provider: string;
  schema_version: string;
  expected_shape: string;
  actual_shape: string;
  path: string;
  status: string;
  migration_status: string;
  migration_required: boolean;
  item_count: number;
  exists: boolean;
  checks: string[];
  warnings: string[];
  blockers: string[];
  provenance_boundary: string;
  migration_strategy: string;
}

export interface SchemaRegistryResponse {
  contract_version: string;
  status: string;
  summary: {
    store_count: number;
    current_count: number;
    missing_count: number;
    legacy_count: number;
    invalid_count: number;
    migration_required_count: number;
    contract_version: string;
    covered_domains: string[];
  };
  stores: SchemaStoreRecord[];
  saved_paths: Record<string, string>;
}

export interface PlanV8ArtifactRecord {
  name: string;
  path: string;
  kind: string;
  status: string;
  generated_at: string;
  summary: Record<string, unknown>;
}

export interface PlanV8ArtifactSummary {
  artifact_dir: string;
  status: string;
  artifact_count: number;
  agent_server_smoke_count: number;
  chat_visible_response_matrix_count?: number;
  live_provider_readiness_count: number;
  live_provider_soak_plan_count?: number;
  live_provider_soak_evidence_count?: number;
  plane_scope_discovery_smoke_count?: number;
  plane_ticket_action_smoke_count?: number;
  ticket_loop_worker_soak_count?: number;
  context_retrieval_eval_count: number;
  asset_provenance_eval_count: number;
  plan_v8_readiness_count?: number;
  employee_growth_eval_count?: number;
  latest_generated_at: string;
  latest_agent_server_smoke?: PlanV8ArtifactRecord | null;
  latest_chat_visible_response_matrix?: PlanV8ArtifactRecord | null;
  latest_live_provider_readiness?: PlanV8ArtifactRecord | null;
  latest_live_provider_soak_plan?: PlanV8ArtifactRecord | null;
  latest_live_provider_soak_evidence?: PlanV8ArtifactRecord | null;
  latest_plane_scope_discovery_smoke?: PlanV8ArtifactRecord | null;
  latest_plane_ticket_action_smoke?: PlanV8ArtifactRecord | null;
  latest_ticket_loop_worker_soak?: PlanV8ArtifactRecord | null;
  latest_context_retrieval_eval?: PlanV8ArtifactRecord | null;
  latest_asset_provenance_eval?: PlanV8ArtifactRecord | null;
  latest_plan_v8_readiness?: PlanV8ArtifactRecord | null;
  latest_employee_growth_eval?: PlanV8ArtifactRecord | null;
  evidence_gaps: string[];
  evidence_warnings?: string[];
  provider_blockers: string[];
  records: PlanV8ArtifactRecord[];
}

export interface ReleaseHygieneItem {
  path: string;
  status_code: string;
  category: string;
  review_action: string;
  detail: string;
}

export interface ReleaseHygieneSummary {
  total_changed: number;
  source_count: number;
  generated_artifact_count: number;
  local_projection_count: number;
  test_output_count: number;
  unknown_count: number;
  untracked_count: number;
  modified_count: number;
  deleted_count: number;
}

export interface ReleaseHygieneResponse {
  contract_version: string;
  status: string;
  detail: string;
  git_root: string;
  summary: ReleaseHygieneSummary;
  review_commands: string[];
  boundary_notes: string[];
  category_samples?: Record<string, ReleaseHygieneItem[]>;
  items: ReleaseHygieneItem[];
}

export interface PlanV8ReadinessCheck {
  id: string;
  scope: string;
  status: string;
  detail: string;
  blockers: string[];
  evidence: Record<string, unknown>;
}

export interface PlanV8ReadinessNextStep {
  id: string;
  label: string;
  detail: string;
  kind: string;
  status?: string;
  href?: string;
  command?: string;
  mutation_gate_required?: boolean;
  evidence?: Record<string, unknown>;
}

export interface PlanV8ReadinessResponse {
  contract_version: string;
  status: string;
  detail: string;
  summary: {
    check_count: number;
    passed_count: number;
    warning_count: number;
    blocked_count: number;
    failed_count: number;
    ready_for_release: boolean;
    contract_version: string;
    next_action: string;
    next_steps?: string[];
    next_step_actions?: PlanV8ReadinessNextStep[];
  };
  checks: PlanV8ReadinessCheck[];
  blockers: string[];
  commands: string[];
  evidence_refs: string[];
}

export interface SystemStatusResponse {
  secrets: SystemStatusSecretItem[];
  ticket_backend?: TicketBackendStatus | null;
  memory_backend?: GraphitiBackendStatus | null;
  runtime_executors?: RuntimeExecutorStatus[];
  live_provider_dogfood?: LiveProviderDogfoodReadiness | null;
  live_provider_soak_plan?: LiveProviderSoakPlanResponse | null;
  live_provider_soak_evidence?: LiveProviderSoakEvidenceResponse | null;
  provider_conformance?: ProviderConformanceResponse | null;
  schema_registry?: SchemaRegistryResponse | null;
  plan_v8_artifacts?: PlanV8ArtifactSummary | null;
  plan_v8_readiness?: PlanV8ReadinessResponse | null;
  release_hygiene?: ReleaseHygieneResponse | null;
  blockers?: Array<{
    id: string;
    scope: string;
    status: string;
    detail: string;
    setup_required: string[];
    reasons?: string[];
    related_blockers?: Array<Record<string, unknown>>;
    related_candidates?: Array<Record<string, unknown>>;
    summary?: Record<string, unknown>;
  }>;
}

export function getSystemStatus(): Promise<SystemStatusResponse> {
  return apiRequest<SystemStatusResponse>("/system-status");
}

export function getProviderConformanceSmoke(includeExternal = false): Promise<ProviderConformanceSmokeResponse> {
  const query = includeExternal ? "?include_external=true" : "";
  return apiRequest<ProviderConformanceSmokeResponse>(`/system-status/providers/smoke${query}`);
}

export function getEnvironmentSmoke(includeExternal = false): Promise<EnvironmentSmokeResponse> {
  const query = includeExternal ? "?include_external=true" : "";
  return apiRequest<EnvironmentSmokeResponse>(`/system-status/environment-smoke${query}`);
}
