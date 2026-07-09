import { type ReactNode, useEffect, useState } from "react";
import { Activity, Check, ClipboardList, Copy, Cpu, Database, FolderGit2, PlayCircle, RefreshCw, KeyRound, Plug } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { ErrorState, LoadingState, navigateTo } from "../../components/shared";
import { getCapabilities, type CapabilityRegistryResponse } from "../../api/capabilities";
import { getChatAiEngines, listChatEmployees, type ChatAiEngineSettings, type ChatEmployeeSummary } from "../../api/chat";
import { getKnowledgeStatus, type KnowledgeStatusResponse } from "../../api/knowledge";
import { getMemoryStatus, type MemoryStatusResponse } from "../../api/memory";
import { getCodeRepositoryStatus, type CodeRepositoryStatus } from "../../api/repositories";
import {
  runRuntimeExecutorDogfood,
  runRuntimeExecutorSmoke,
  runRuntimeExecutorSmokeBatch,
  type RuntimeExecutorDogfoodResponse,
  type RuntimeExecutorSmokeBatchResponse,
  type RuntimeExecutorSmokeResponse,
} from "../../api/runtimeExecutors";
import {
  getEnvironmentSmoke,
  getProviderConformanceSmoke,
  getSystemStatus,
  type LiveProviderSoakEvidenceScenario,
  type EnvironmentSmokeResponse,
  type LiveProviderSoakScenario,
  type PlanV8ReadinessNextStep,
  type PlanV8ReadinessCheck,
  type ProviderConformanceRecord,
  type ProviderConformanceSmokeResponse,
  type ReleaseHygieneItem,
  type RuntimeExecutorStatus,
  type SchemaStoreRecord,
  type SystemStatusResponse,
  type SystemStatusSecretItem,
} from "../../api/systemStatus";
import { getTicketBackendStatus, type TicketBackendStatus } from "../../api/tickets";
import { getToolConnectorStatus, type ToolConnectorRegistryStatus } from "../../api/toolConnectors";
import { cn } from "@/lib/utils";

function compactStatus(status?: string | null): string {
  if (!status) return "-";
  if (status === "llm_not_configured") return "llm missing";
  if (status === "not_configured") return "missing";
  return status.replace(/_/g, " ");
}

function SummaryMetric({
  label,
  tone,
  value,
}: {
  label: string;
  tone?: "ok" | "warn";
  value: ReactNode;
}) {
  const toneClass =
    tone === "ok"
      ? "text-green-600"
      : tone === "warn"
      ? "text-orange-500"
      : "text-foreground";
  return (
    <div className="min-w-0 rounded-md border bg-card px-3 py-2">
      <div className="text-[10px] font-medium uppercase text-muted-foreground">{label}</div>
      <div className={cn("mt-0.5 truncate text-sm font-semibold", toneClass)}>{value}</div>
    </div>
  );
}

function EmptyDetail({ children }: { children: ReactNode }) {
  return <div className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">{children}</div>;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function asRecordArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(asRecord).filter((item) => Object.keys(item).length > 0) : [];
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function stringArrayValue(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function numberValue(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function readinessStepBadgeVariant(status: string): "success" | "warning" | "danger" | "secondary" | "outline" {
  if (status === "passed" || status === "ready" || status === "ready_to_run" || status === "open") return "success";
  if (status === "warning" || status === "blocked" || status === "setup_blocked" || status === "incomplete" || status === "closed") return "warning";
  if (status === "failed" || status === "error") return "danger";
  return status ? "secondary" : "outline";
}

function compactEvidenceKey(key: string): string {
  return key.replace(/^plane_ticket_/, "").replace(/_/g, " ");
}

function compactEvidenceValue(value: unknown): string {
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return value.replace(/_/g, " ");
  if (Array.isArray(value)) return value.map(compactEvidenceValue).filter(Boolean).join(", ");
  return "";
}

function SystemSummary({
  aiEngines,
  capabilityRegistry,
  codeRepositoryStatus,
  employees,
  knowledge,
  memory,
  systemStatus,
  ticketBackendStatus,
  toolConnectorStatus,
}: {
  aiEngines: ChatAiEngineSettings | null;
  capabilityRegistry: CapabilityRegistryResponse | null;
  codeRepositoryStatus: CodeRepositoryStatus | null;
  employees: ChatEmployeeSummary[];
  knowledge: KnowledgeStatusResponse | null;
  memory: MemoryStatusResponse | null;
  systemStatus: SystemStatusResponse | null;
  ticketBackendStatus: TicketBackendStatus | null;
  toolConnectorStatus: ToolConnectorRegistryStatus | null;
}) {
  const secretItems = systemStatus?.secrets ?? [];
  const configuredSecrets = secretItems.filter((item) => item.configured).length;
  const missingSecrets = secretItems.length - configuredSecrets;
  const activeEngine = aiEngines?.engines?.[aiEngines.active_engine];
  const activeEngineLabel = activeEngine?.display_name ?? aiEngines?.active_engine ?? "-";
  const releaseTarget = asRecord(ticketBackendStatus?.release_target);
  const releaseTargetStatus = stringValue(releaseTarget.status);
  const readyTools = toolConnectorStatus?.ready_count ?? capabilityRegistry?.status.ready_count ?? 0;

  return (
    <section className="rounded-md border bg-background">
      <div className="border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">System Summary</h3>
        </div>
      </div>
      <div className="grid gap-3 p-3 md:grid-cols-2 xl:grid-cols-4">
        <SummaryMetric label="AI Engine" value={activeEngineLabel} tone={aiEngines?.active_engine === "stub" ? "warn" : "ok"} />
        <SummaryMetric label="Employees" value={employees.length} />
        <SummaryMetric label="Ticket Backend" value={compactStatus(ticketBackendStatus?.status)} tone={ticketBackendStatus?.status === "ready" ? "ok" : "warn"} />
        <SummaryMetric label="Release Target" value={compactStatus(releaseTargetStatus)} tone={releaseTargetStatus === "ready" ? "ok" : "warn"} />
        <SummaryMetric label="Memory Backend" value={compactStatus(memory?.backend.status)} tone={memory?.backend.status === "ready" ? "ok" : "warn"} />
        <SummaryMetric label="Tools Ready" value={readyTools} tone={readyTools > 0 ? "ok" : "warn"} />
        <SummaryMetric label="Repos Ready" value={`${codeRepositoryStatus?.ready_count ?? 0}/${codeRepositoryStatus?.repository_count ?? 0}`} tone={(codeRepositoryStatus?.ready_count ?? 0) > 0 ? "ok" : "warn"} />
        <SummaryMetric label="Review Queue" value={knowledge?.review_queue_count ?? 0} tone={(knowledge?.review_queue_count ?? 0) > 0 ? "warn" : undefined} />
        <SummaryMetric label="Secrets" value={`${configuredSecrets}/${secretItems.length}`} tone={missingSecrets === 0 ? "ok" : "warn"} />
      </div>
    </section>
  );
}

function PlanV8ReadinessPanel({ systemStatus }: { systemStatus: SystemStatusResponse | null }) {
  const readiness = systemStatus?.plan_v8_readiness ?? null;
  const checks = readiness?.checks ?? [];
  const nextStepActions = readiness?.summary.next_step_actions ?? [];
  const nextSteps = readiness?.summary.next_steps ?? [];
  const [copiedCommandKey, setCopiedCommandKey] = useState("");

  function badgeVariant(status: string): "success" | "warning" | "danger" | "secondary" | "outline" {
    if (status === "passed" || status === "ready") return "success";
    if (status === "warning" || status === "blocked") return "warning";
    if (status === "failed" || status === "error") return "danger";
    return status ? "secondary" : "outline";
  }

  async function handleCopyCommand(key: string, command: string) {
    await copyTextToClipboard(command);
    setCopiedCommandKey(key);
  }

  return (
    <section className="rounded-md border bg-background">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Plan v8 Readiness</h3>
        </div>
        <div className="flex flex-wrap gap-2">
          {readiness?.contract_version ? <Badge variant="outline">{readiness.contract_version}</Badge> : null}
          <Badge variant={badgeVariant(readiness?.status ?? "")}>{compactStatus(readiness?.status)}</Badge>
          <Badge variant="secondary">{readiness?.summary.check_count ?? 0} checks</Badge>
          <Badge variant={(readiness?.summary.blocked_count ?? 0) ? "warning" : "success"}>{readiness?.summary.blocked_count ?? 0} blocked</Badge>
          <Badge variant={readiness?.summary.ready_for_release ? "success" : "warning"}>
            {readiness?.summary.ready_for_release ? "release ready" : "not release ready"}
          </Badge>
        </div>
      </div>
      {!readiness ? (
        <div className="p-4">
          <EmptyDetail>No plan_v8 readiness checklist is available.</EmptyDetail>
        </div>
      ) : (
        <>
          <div className="border-b bg-muted/40 px-4 py-2">
            <div className="text-xs text-muted-foreground">{readiness.detail}</div>
            {readiness.summary.next_action ? (
              <div className="mt-1 text-xs text-muted-foreground">{readiness.summary.next_action}</div>
            ) : null}
          </div>
          <div className="grid gap-3 p-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
            <div className="rounded-md border bg-card px-4 py-3">
              <div className="mb-3 text-[10px] font-medium uppercase text-muted-foreground">Readiness Checklist</div>
              {checks.length ? (
                <div className="grid gap-2">
                  {checks.map((check: PlanV8ReadinessCheck) => (
                    <div key={check.id} className="rounded-md border bg-background px-3 py-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="min-w-0">
                          <div className="text-sm font-medium">{check.scope}</div>
                          <div className="mt-0.5 text-xs text-muted-foreground">{check.detail}</div>
                        </div>
                        <Badge variant={badgeVariant(check.status)}>{compactStatus(check.status)}</Badge>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <Badge variant="outline">{check.id}</Badge>
                        {check.blockers.slice(0, 4).map((blocker) => (
                          <Badge key={`${check.id}-${blocker}`} variant="warning">{compactStatus(blocker)}</Badge>
                        ))}
                        {check.blockers.length > 4 ? <Badge variant="secondary">+{check.blockers.length - 4}</Badge> : null}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyDetail>No readiness checks were reported.</EmptyDetail>
              )}
            </div>

            <div className="grid gap-3">
              <div className="rounded-md border bg-card px-4 py-3">
                <div className="mb-3 text-[10px] font-medium uppercase text-muted-foreground">Next Steps</div>
                {nextStepActions.length ? (
                  <div className="space-y-2">
                    {nextStepActions.slice(0, 6).map((step, index) => (
                      <ReadinessNextStepRow
                        key={step.id || `${index}-${step.detail}`}
                        copiedCommandKey={copiedCommandKey}
                        index={index}
                        onCopyCommand={(key, command) => void handleCopyCommand(key, command)}
                        step={step}
                      />
                    ))}
                  </div>
                ) : nextSteps.length ? (
                  <div className="space-y-2">
                    {nextSteps.slice(0, 5).map((step, index) => (
                      <div key={`${index}-${step}`} className="rounded-md border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">{index + 1}. {step}</div>
                    ))}
                  </div>
                ) : (
                  <EmptyDetail>No next steps are available.</EmptyDetail>
                )}
              </div>

              <div className="rounded-md border bg-card px-4 py-3">
                <div className="mb-3 text-[10px] font-medium uppercase text-muted-foreground">Local Readiness Command</div>
                {readiness.commands.length ? (
                  <div className="space-y-2">
                    {readiness.commands.slice(0, 4).map((command, index) => (
                      <CommandRow
                        key={command}
                        command={command}
                        copied={copiedCommandKey === `local-readiness-${index}`}
                        label={`Local readiness command ${index + 1}`}
                        onCopy={() => void handleCopyCommand(`local-readiness-${index}`, command)}
                      />
                    ))}
                  </div>
                ) : (
                  <EmptyDetail>No readiness commands are available.</EmptyDetail>
                )}
              </div>

              <div className="rounded-md border bg-card px-4 py-3">
                <div className="mb-3 text-[10px] font-medium uppercase text-muted-foreground">Evidence and Blockers</div>
                <div className="flex flex-wrap gap-2">
                  {readiness.evidence_refs.map((ref) => <Badge key={`evidence-${ref}`} variant="outline">{ref}</Badge>)}
                  {readiness.blockers.map((blocker) => <Badge key={`blocker-${blocker}`} variant="warning">{compactStatus(blocker)}</Badge>)}
                  {!readiness.evidence_refs.length && !readiness.blockers.length ? <Badge variant="success">clear</Badge> : null}
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function ReadinessNextStepRow({
  copiedCommandKey,
  index,
  onCopyCommand,
  step,
}: {
  copiedCommandKey: string;
  index: number;
  onCopyCommand: (key: string, command: string) => void;
  step: PlanV8ReadinessNextStep;
}) {
  const href = typeof step.href === "string" ? step.href : "";
  const command = typeof step.command === "string" ? step.command : "";
  const canOpen = href.startsWith("#/");
  const commandKey = `next-step-${step.id || index}`;
  const label = step.label || step.id || `Next step ${index + 1}`;
  const status = typeof step.status === "string" ? step.status : "";
  const evidence = step.evidence && typeof step.evidence === "object" && !Array.isArray(step.evidence) ? step.evidence : {};
  const evidenceEntries = Object.entries(evidence)
    .map(([key, value]) => [key, compactEvidenceValue(value)] as const)
    .filter(([, value]) => value)
    .slice(0, 8);

  return (
    <div className="rounded-md border bg-muted/30 px-3 py-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">{index + 1}</Badge>
            <span className="text-xs font-medium">{step.label || step.id || "Next step"}</span>
            {step.kind ? <Badge variant={step.kind === "guard" ? "warning" : "secondary"}>{compactStatus(step.kind)}</Badge> : null}
            {status ? <Badge variant={readinessStepBadgeVariant(status)}>{compactStatus(status)}</Badge> : null}
            {step.mutation_gate_required ? <Badge variant="warning">mutation gate</Badge> : null}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">{step.detail || "-"}</div>
          {evidenceEntries.length ? (
            <div className="mt-2 flex flex-wrap gap-2">
              {evidenceEntries.map(([key, value]) => (
                <Badge key={`${step.id || index}-evidence-${key}`} variant="outline">
                  {compactEvidenceKey(key)} {value}
                </Badge>
              ))}
            </div>
          ) : null}
        </div>
        {canOpen ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            aria-label={`Open ${label}`}
            onClick={() => navigateToHashHref(href)}
          >
            <Activity className="h-4 w-4" />
            Open
          </Button>
        ) : null}
      </div>
      {command ? (
        <CommandRow
          className="mt-2"
          command={command}
          copied={copiedCommandKey === commandKey}
          label={label}
          onCopy={() => onCopyCommand(commandKey, command)}
        />
      ) : null}
    </div>
  );
}

function CommandRow({
  className,
  command,
  copied,
  label,
  onCopy,
}: {
  className?: string;
  command: string;
  copied: boolean;
  label: string;
  onCopy: () => void;
}) {
  return (
    <div className={cn("flex min-w-0 items-center gap-2 rounded-md border bg-background px-3 py-2", className)}>
      <code className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap font-mono text-xs" title={command}>{command}</code>
      <Button
        type="button"
        size="icon"
        variant="outline"
        className="h-7 w-7 shrink-0"
        aria-label={copied ? `${label} command copied` : `Copy ${label} command`}
        title="Copy command"
        onClick={onCopy}
      >
        {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      </Button>
    </div>
  );
}

async function copyTextToClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
}

function navigateToHashHref(href: string): void {
  const parts = href.replace(/^#\/?/, "").split("/").filter(Boolean).map((part) => {
    try {
      return decodeURIComponent(part);
    } catch {
      return part;
    }
  });
  const [page, id, detail] = parts;
  if (!page) return;
  navigateTo(page, id ?? null, detail ?? null);
}

function SchemaRegistryPanel({ systemStatus }: { systemStatus: SystemStatusResponse | null }) {
  const registry = systemStatus?.schema_registry;
  const stores = [...(registry?.stores ?? [])].sort((left, right) => {
    if (left.domain !== right.domain) return left.domain.localeCompare(right.domain);
    return left.id.localeCompare(right.id);
  });

  function badgeVariant(status: string): "success" | "warning" | "danger" | "secondary" {
    if (status === "current" || status === "passed") return "success";
    if (status === "missing" || status === "legacy" || status === "warning") return "warning";
    if (status === "invalid" || status === "failed") return "danger";
    return "secondary";
  }

  return (
    <section className="rounded-md border bg-background">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Schema / Migration Readiness</h3>
        </div>
        <div className="flex flex-wrap gap-2">
          {registry?.contract_version ? <Badge variant="outline">{registry.contract_version}</Badge> : null}
          <Badge variant={badgeVariant(registry?.status ?? "missing")}>{compactStatus(registry?.status)}</Badge>
          <Badge variant="secondary">{registry?.summary.store_count ?? 0} stores</Badge>
          <Badge variant={(registry?.summary.current_count ?? 0) === (registry?.summary.store_count ?? 0) ? "success" : "warning"}>
            {registry?.summary.current_count ?? 0} current
          </Badge>
          <Badge variant={(registry?.summary.migration_required_count ?? 0) ? "danger" : "success"}>
            {registry?.summary.migration_required_count ?? 0} migration required
          </Badge>
        </div>
      </div>
      {registry?.summary.covered_domains.length ? (
        <div className="border-b bg-muted/40 px-4 py-2">
          <div className="flex flex-wrap gap-2">
            {registry.summary.covered_domains.map((domain) => (
              <Badge key={domain} variant="outline">{domain}</Badge>
            ))}
            {registry.summary.missing_count ? <Badge variant="warning">{registry.summary.missing_count} missing</Badge> : null}
            {registry.summary.legacy_count ? <Badge variant="warning">{registry.summary.legacy_count} legacy</Badge> : null}
            {registry.summary.invalid_count ? <Badge variant="danger">{registry.summary.invalid_count} invalid</Badge> : null}
          </div>
        </div>
      ) : null}
      <div className="grid gap-3 p-4 lg:grid-cols-2">
        {stores.length === 0 ? (
          <EmptyDetail>No schema registry records are available.</EmptyDetail>
        ) : stores.map((store: SchemaStoreRecord) => {
          const visibleChecks = store.checks.slice(0, 5);
          const visibleWarnings = store.warnings.slice(0, 3);
          const visibleBlockers = store.blockers.slice(0, 3);
          return (
            <div key={store.id} className="rounded-md border bg-card px-4 py-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="text-sm font-semibold">{store.display_name}</div>
                    <Badge variant="outline">{store.domain}</Badge>
                    <Badge variant="secondary">{store.schema_version}</Badge>
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">{store.provenance_boundary}</p>
                </div>
                <Badge variant={badgeVariant(store.status)}>{compactStatus(store.status)}</Badge>
              </div>

              <div className="mt-3 grid gap-3 text-xs text-muted-foreground md:grid-cols-2">
                <div>
                  <div className="font-medium uppercase">Path</div>
                  <div className="mt-1 truncate text-foreground" title={store.path}>{store.path}</div>
                </div>
                <div>
                  <div className="font-medium uppercase">Shape</div>
                  <div className="mt-1 truncate text-foreground" title={`${store.actual_shape} / ${store.expected_shape}`}>
                    {store.actual_shape || "-"} / {store.expected_shape}
                  </div>
                </div>
                <div>
                  <div className="font-medium uppercase">Items</div>
                  <div className="mt-1 text-foreground">{store.item_count}</div>
                </div>
                <div>
                  <div className="font-medium uppercase">Migration</div>
                  <div className="mt-1 truncate text-foreground" title={store.migration_status}>{store.migration_status}</div>
                </div>
              </div>

              <div className="mt-3 flex flex-wrap gap-2">
                {visibleChecks.map((check) => (
                  <Badge key={`${store.id}-check-${check}`} variant="outline">{check}</Badge>
                ))}
                {visibleWarnings.map((warning) => (
                  <Badge key={`${store.id}-warning-${warning}`} variant="secondary">{warning}</Badge>
                ))}
                {visibleBlockers.map((blocker) => (
                  <Badge key={`${store.id}-blocker-${blocker}`} variant="danger">{blocker}</Badge>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function PlanV8ArtifactEvidencePanel({ systemStatus }: { systemStatus: SystemStatusResponse | null }) {
  const artifacts = systemStatus?.plan_v8_artifacts;
  const latestAgent = artifacts?.latest_agent_server_smoke ?? null;
  const latestMatrix = artifacts?.latest_chat_visible_response_matrix ?? null;
  const latestReadiness = artifacts?.latest_live_provider_readiness ?? null;
  const latestSoakEvidence = artifacts?.latest_live_provider_soak_evidence ?? null;
  const latestPlaneScopeDiscovery = artifacts?.latest_plane_scope_discovery_smoke ?? null;
  const latestPlaneAction = artifacts?.latest_plane_ticket_action_smoke ?? null;
  const latestWorkerSoak = artifacts?.latest_ticket_loop_worker_soak ?? null;
  const latestPlanV8Readiness = artifacts?.latest_plan_v8_readiness ?? null;
  const latestEmployeeGrowth = artifacts?.latest_employee_growth_eval ?? null;
  const agentSummary = asRecord(latestAgent?.summary);
  const matrixSummary = asRecord(latestMatrix?.summary);
  const readinessSummary = asRecord(latestReadiness?.summary);
  const soakEvidenceSummary = asRecord(latestSoakEvidence?.summary);
  const planeScopeDiscoverySummary = asRecord(latestPlaneScopeDiscovery?.summary);
  const planeActionSummary = asRecord(latestPlaneAction?.summary);
  const workerSoakSummary = asRecord(latestWorkerSoak?.summary);
  const planV8ReadinessSummary = asRecord(latestPlanV8Readiness?.summary);
  const employeeGrowthSummary = asRecord(latestEmployeeGrowth?.summary);
  const evidenceGaps = artifacts?.evidence_gaps ?? [];
  const evidenceWarnings = artifacts?.evidence_warnings ?? [];
  const providerBlockers = artifacts?.provider_blockers ?? [];
  const recentRecords = artifacts?.records ?? [];

  function badgeVariant(status: string): "success" | "warning" | "danger" | "secondary" | "outline" {
    if (status === "ready" || status === "passed" || status === "dry_run") return "success";
    if (status === "warning" || status === "blocked" || status === "setup_blocked" || status === "disabled" || status === "skipped") return "warning";
    if (status === "failed" || status === "error") return "danger";
    return status ? "secondary" : "outline";
  }

  return (
    <section className="rounded-md border bg-background">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Plan v8 Artifact Evidence</h3>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant={badgeVariant(artifacts?.status ?? "")}>{compactStatus(artifacts?.status)}</Badge>
          <Badge variant="secondary">{artifacts?.artifact_count ?? 0} artifacts</Badge>
          <Badge variant={(artifacts?.agent_server_smoke_count ?? 0) ? "success" : "warning"}>
            {artifacts?.agent_server_smoke_count ?? 0} Agent Server
          </Badge>
          <Badge variant={(artifacts?.chat_visible_response_matrix_count ?? 0) ? "success" : "warning"}>
            {artifacts?.chat_visible_response_matrix_count ?? 0} matrix
          </Badge>
          <Badge variant={(artifacts?.live_provider_readiness_count ?? 0) ? "success" : "warning"}>
            {artifacts?.live_provider_readiness_count ?? 0} readiness
          </Badge>
          <Badge variant={(artifacts?.live_provider_soak_evidence_count ?? 0) ? "success" : "warning"}>
            {artifacts?.live_provider_soak_evidence_count ?? 0} soak evidence
          </Badge>
          <Badge variant={(artifacts?.plane_scope_discovery_smoke_count ?? 0) ? "success" : "warning"}>
            {artifacts?.plane_scope_discovery_smoke_count ?? 0} Plane discovery
          </Badge>
          <Badge variant={(artifacts?.plane_ticket_action_smoke_count ?? 0) ? "success" : "warning"}>
            {artifacts?.plane_ticket_action_smoke_count ?? 0} Plane action
          </Badge>
          <Badge variant={(artifacts?.ticket_loop_worker_soak_count ?? 0) ? "success" : "warning"}>
            {artifacts?.ticket_loop_worker_soak_count ?? 0} worker soak
          </Badge>
          <Badge variant={(artifacts?.plan_v8_readiness_count ?? 0) ? "success" : "warning"}>
            {artifacts?.plan_v8_readiness_count ?? 0} release review
          </Badge>
          <Badge variant={(artifacts?.employee_growth_eval_count ?? 0) ? "success" : "warning"}>
            {artifacts?.employee_growth_eval_count ?? 0} employee growth
          </Badge>
        </div>
      </div>
      {!artifacts ? (
        <div className="p-4">
          <EmptyDetail>No plan_v8 artifact summary is available.</EmptyDetail>
        </div>
      ) : (
        <>
          <div className="border-b bg-muted/40 px-4 py-2">
            <div className="truncate text-xs text-muted-foreground" title={artifacts.artifact_dir}>
              {artifacts.artifact_dir}
            </div>
          </div>
          <div className="grid gap-3 border-b p-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="min-w-0 rounded-md border bg-card px-3 py-2">
              <div className="text-[10px] font-medium uppercase text-muted-foreground">Latest evidence</div>
              <div className="mt-0.5 truncate text-sm font-semibold" title={artifacts.latest_generated_at || "-"}>
                {artifacts.latest_generated_at || "-"}
              </div>
            </div>
            <div className="min-w-0 rounded-md border bg-card px-3 py-2">
              <div className="text-[10px] font-medium uppercase text-muted-foreground">Release readiness</div>
              <div className="mt-0.5 truncate text-sm font-semibold" title={latestPlanV8Readiness?.generated_at || "-"}>
                {latestPlanV8Readiness?.generated_at || "-"}
              </div>
            </div>
            <div className="min-w-0 rounded-md border bg-card px-3 py-2">
              <div className="text-[10px] font-medium uppercase text-muted-foreground">Provider blockers</div>
              <div className={`mt-0.5 truncate text-sm font-semibold ${providerBlockers.length ? "text-orange-500" : "text-green-600"}`}>
                {providerBlockers.length}
              </div>
            </div>
            <div className="min-w-0 rounded-md border bg-card px-3 py-2">
              <div className="text-[10px] font-medium uppercase text-muted-foreground">Warnings / gaps</div>
              <div className={`mt-0.5 truncate text-sm font-semibold ${evidenceWarnings.length || evidenceGaps.length ? "text-orange-500" : "text-green-600"}`}>
                {evidenceWarnings.length} / {evidenceGaps.length}
              </div>
            </div>
          </div>
          <div className="grid gap-3 p-4 lg:grid-cols-2">
            <div className="rounded-md border bg-card px-4 py-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-semibold">Fresh Agent Server Smoke</div>
                  <p className="mt-1 text-sm text-muted-foreground">Current-code Agent Server proof for the Chat visible-response contract.</p>
                </div>
                <Badge variant={badgeVariant(latestAgent?.status ?? "")}>{compactStatus(latestAgent?.status)}</Badge>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge variant="outline">{stringValue(agentSummary.visible_response_version) || "-"}</Badge>
                <Badge variant={badgeVariant(stringValue(agentSummary.visible_display_state))}>
                  {compactStatus(stringValue(agentSummary.visible_display_state))}
                </Badge>
                <Badge variant="secondary">{compactStatus(stringValue(agentSummary.runtime_status))}</Badge>
                {stringValue(agentSummary.current_node) ? <Badge variant="outline">{stringValue(agentSummary.current_node)}</Badge> : null}
              </div>
              {latestAgent?.name ? <div className="mt-3 truncate text-xs text-muted-foreground" title={latestAgent.name}>{latestAgent.name}</div> : null}
            </div>

            <div className="rounded-md border bg-card px-4 py-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-semibold">Plane Scope Discovery Artifact</div>
                  <p className="mt-1 text-sm text-muted-foreground">Read-only Plane workspace/project discovery evidence before Code Repository scope or Ticket Backend mutation.</p>
                </div>
                <Badge variant={badgeVariant(latestPlaneScopeDiscovery?.status ?? "")}>{compactStatus(latestPlaneScopeDiscovery?.status)}</Badge>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge variant={badgeVariant(stringValue(planeScopeDiscoverySummary.discovery_status))}>
                  discovery {compactStatus(stringValue(planeScopeDiscoverySummary.discovery_status))}
                </Badge>
                <Badge variant={planeScopeDiscoverySummary.api_key_configured ? "success" : "warning"}>
                  API key {planeScopeDiscoverySummary.api_key_configured ? "ready" : "missing"}
                </Badge>
                <Badge variant={planeScopeDiscoverySummary.external_calls ? "warning" : "success"}>
                  {planeScopeDiscoverySummary.external_calls ? "external read" : "local only"}
                </Badge>
                <Badge variant={planeScopeDiscoverySummary.external_mutation ? "warning" : "success"}>
                  {planeScopeDiscoverySummary.external_mutation ? "mutating" : "non-mutating"}
                </Badge>
                <Badge variant={Number(planeScopeDiscoverySummary.suggestion_count ?? 0) ? "success" : "warning"}>
                  {String(planeScopeDiscoverySummary.suggestion_count ?? 0)} suggestions
                </Badge>
                <Badge variant="outline">
                  {String(planeScopeDiscoverySummary.workspace_count ?? 0)} workspaces
                </Badge>
                <Badge variant="outline">
                  {String(planeScopeDiscoverySummary.project_count ?? 0)} projects
                </Badge>
              </div>
              {stringValue(planeScopeDiscoverySummary.first_workspace_slug) || stringValue(planeScopeDiscoverySummary.first_project_id) ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {stringValue(planeScopeDiscoverySummary.first_workspace_slug) ? (
                    <Badge variant="outline">{stringValue(planeScopeDiscoverySummary.first_workspace_slug)}</Badge>
                  ) : null}
                  {stringValue(planeScopeDiscoverySummary.first_project_id) ? (
                    <Badge variant="outline">{stringValue(planeScopeDiscoverySummary.first_project_id)}</Badge>
                  ) : null}
                </div>
              ) : null}
              {stringValue(planeScopeDiscoverySummary.detail) ? (
                <div className="mt-3 rounded-md border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                  {stringValue(planeScopeDiscoverySummary.detail)}
                </div>
              ) : null}
              {latestPlaneScopeDiscovery?.name ? (
                <div className="mt-3 truncate text-xs text-muted-foreground" title={latestPlaneScopeDiscovery.name}>{latestPlaneScopeDiscovery.name}</div>
              ) : null}
            </div>

            <div className="rounded-md border bg-card px-4 py-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-semibold">Chat Visible Response Matrix</div>
                  <p className="mt-1 text-sm text-muted-foreground">Backend contract proof for completed, blocked, approval, handoff, and provider-blocker Chat states.</p>
                </div>
                <Badge variant={badgeVariant(latestMatrix?.status ?? "")}>{compactStatus(latestMatrix?.status)}</Badge>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge variant={Number(matrixSummary.passed_case_count ?? 0) ? "success" : "warning"}>
                  {String(matrixSummary.passed_case_count ?? 0)}/{String(matrixSummary.case_count ?? 0)} cases
                </Badge>
                {stringArrayValue(matrixSummary.observed_states).map((state) => (
                  <Badge key={`matrix-state-${state}`} variant={badgeVariant(state)}>{compactStatus(state)}</Badge>
                ))}
              </div>
              {latestMatrix?.name ? <div className="mt-3 truncate text-xs text-muted-foreground" title={latestMatrix.name}>{latestMatrix.name}</div> : null}
            </div>

            <div className="rounded-md border bg-card px-4 py-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-semibold">Live Provider Readiness Artifact</div>
                  <p className="mt-1 text-sm text-muted-foreground">Read-only provider readiness evidence for Plane, Graphiti, mutation gate, and RuntimeExecutor candidates.</p>
                </div>
                <Badge variant={badgeVariant(stringValue(readinessSummary.readiness_status) || latestReadiness?.status || "")}>
                  {compactStatus(stringValue(readinessSummary.readiness_status) || latestReadiness?.status)}
                </Badge>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge variant="outline">{stringValue(readinessSummary.profile) || "-"}</Badge>
                <Badge variant="secondary">{stringValue(readinessSummary.selected_executor_id) || "-"}</Badge>
                <Badge variant={Number(readinessSummary.repo_write_ready_count ?? 0) > 0 ? "success" : "warning"}>
                  {String(readinessSummary.repo_write_ready_count ?? 0)}/{String(readinessSummary.repo_write_candidate_count ?? 0)} repo-write ready
                </Badge>
                <Badge variant={readinessSummary.mutation_gate_open ? "success" : "warning"}>
                  {readinessSummary.mutation_gate_open ? "gate open" : "gate closed"}
                </Badge>
                {stringValue(readinessSummary.ticket_backend_release_target_status) ? (
                  <Badge variant={stringValue(readinessSummary.ticket_backend_release_target_status) === "ready" ? "success" : "warning"}>
                    release target {compactStatus(stringValue(readinessSummary.ticket_backend_release_target_status))}
                  </Badge>
                ) : null}
                {stringValue(readinessSummary.ticket_backend_release_target_setup_action) ? (
                  <Badge variant="outline">
                    {compactStatus(stringValue(readinessSummary.ticket_backend_release_target_setup_action))}
                  </Badge>
                ) : null}
              </div>
              {stringArrayValue(readinessSummary.ticket_backend_release_target_blockers).length ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {stringArrayValue(readinessSummary.ticket_backend_release_target_blockers).slice(0, 4).map((blocker) => (
                    <Badge key={`live-readiness-release-target-${blocker}`} variant="warning">
                      {compactStatus(blocker)}
                    </Badge>
                  ))}
                </div>
              ) : null}
              {latestReadiness?.name ? <div className="mt-3 truncate text-xs text-muted-foreground" title={latestReadiness.name}>{latestReadiness.name}</div> : null}
            </div>

            <div className="rounded-md border bg-card px-4 py-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-semibold">Plane Ticket Action Smoke Artifact</div>
                  <p className="mt-1 text-sm text-muted-foreground">Gated provider-action proof for the Plane Ticket handoff/report write path before full live dogfood.</p>
                </div>
                <Badge variant={badgeVariant(latestPlaneAction?.status ?? "")}>{compactStatus(latestPlaneAction?.status)}</Badge>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge variant="outline">{stringValue(planeActionSummary.provider) || "-"}</Badge>
                <Badge variant={badgeVariant(stringValue(planeActionSummary.ticket_backend_status))}>
                  Ticket {compactStatus(stringValue(planeActionSummary.ticket_backend_status))}
                </Badge>
                <Badge variant={planeActionSummary.mutation_gate_open ? "success" : "warning"}>
                  {planeActionSummary.mutation_gate_open ? "gate open" : "gate closed"}
                </Badge>
                <Badge variant={planeActionSummary.external_calls ? "warning" : "success"}>
                  {planeActionSummary.external_calls ? "external" : "no external call"}
                </Badge>
                <Badge variant={planeActionSummary.mutating ? "warning" : "success"}>
                  {planeActionSummary.mutating ? "mutating" : "non-mutating"}
                </Badge>
              </div>
              {stringValue(planeActionSummary.confirm_env_var) ? (
                <div className="mt-3 truncate text-xs text-muted-foreground" title={stringValue(planeActionSummary.confirm_env_var)}>
                  {stringValue(planeActionSummary.confirm_env_var)}
                </div>
              ) : null}
              {latestPlaneAction?.name ? <div className="mt-3 truncate text-xs text-muted-foreground" title={latestPlaneAction.name}>{latestPlaneAction.name}</div> : null}
            </div>

            <div className="rounded-md border bg-card px-4 py-3 lg:col-span-2">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-semibold">Live Provider Soak Evidence Artifact</div>
                  <p className="mt-1 text-sm text-muted-foreground">Scenario-level proof coverage for repeated fresh Agent Server / live-provider Ticket-loop soak.</p>
                </div>
                <Badge variant={badgeVariant(latestSoakEvidence?.status ?? "")}>{compactStatus(latestSoakEvidence?.status)}</Badge>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge variant="secondary">{String(soakEvidenceSummary.scenario_count ?? 0)} scenarios</Badge>
                <Badge variant={Number(soakEvidenceSummary.passed_scenario_count ?? 0) ? "success" : "outline"}>
                  {String(soakEvidenceSummary.passed_scenario_count ?? 0)} passed
                </Badge>
                <Badge variant={Number(soakEvidenceSummary.blocked_scenario_count ?? 0) ? "warning" : "success"}>
                  {String(soakEvidenceSummary.blocked_scenario_count ?? 0)} blocked
                </Badge>
                <Badge variant={Number(soakEvidenceSummary.remaining_live_write_scenario_count ?? 0) ? "warning" : "success"}>
                  {String(soakEvidenceSummary.remaining_live_write_scenario_count ?? 0)} live remaining
                </Badge>
                <Badge variant={soakEvidenceSummary.mutation_gate_open ? "success" : "warning"}>
                  {soakEvidenceSummary.mutation_gate_open ? "gate open" : "gate closed"}
                </Badge>
              </div>
              {latestSoakEvidence?.name ? <div className="mt-3 truncate text-xs text-muted-foreground" title={latestSoakEvidence.name}>{latestSoakEvidence.name}</div> : null}
            </div>

            <div className="rounded-md border bg-card px-4 py-3 lg:col-span-2">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-semibold">Ticket Loop Worker Soak Artifact</div>
                  <p className="mt-1 text-sm text-muted-foreground">Local retry/resume evidence for queue processing, reliability blockers, daemon settlement, and retrospective Asset candidates.</p>
                </div>
                <Badge variant={badgeVariant(latestWorkerSoak?.status ?? "")}>{compactStatus(latestWorkerSoak?.status)}</Badge>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge variant="outline">{stringValue(workerSoakSummary.ticket_id) || "-"}</Badge>
                <Badge variant={Number(workerSoakSummary.worker_processed_delta ?? 0) ? "success" : "warning"}>
                  {String(workerSoakSummary.worker_processed_delta ?? 0)} processed
                </Badge>
                <Badge variant={Number(workerSoakSummary.worker_policy_action_delta ?? 0) ? "success" : "warning"}>
                  {String(workerSoakSummary.worker_policy_action_delta ?? 0)} policy actions
                </Badge>
                <Badge variant={Number(workerSoakSummary.asset_candidate_count ?? 0) ? "success" : "warning"}>
                  {String(workerSoakSummary.asset_candidate_count ?? 0)} retrospective assets
                </Badge>
                <Badge variant={badgeVariant(stringValue(workerSoakSummary.after_reliability_status))}>
                  {compactStatus(stringValue(workerSoakSummary.after_reliability_status))}
                </Badge>
                <Badge variant={badgeVariant(stringValue(workerSoakSummary.daemon_status))}>
                  daemon {compactStatus(stringValue(workerSoakSummary.daemon_status))}
                </Badge>
              </div>
              {stringArrayValue(workerSoakSummary.processed_statuses).length ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {stringArrayValue(workerSoakSummary.processed_statuses).map((status, index) => (
                    <Badge key={`worker-status-${status}-${index}`} variant={badgeVariant(status)}>{compactStatus(status)}</Badge>
                  ))}
                </div>
              ) : null}
              {latestWorkerSoak?.name ? <div className="mt-3 truncate text-xs text-muted-foreground" title={latestWorkerSoak.name}>{latestWorkerSoak.name}</div> : null}
            </div>

            <div className="rounded-md border bg-card px-4 py-3 lg:col-span-2">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-semibold">Employee Growth Eval Artifact</div>
                  <p className="mt-1 text-sm text-muted-foreground">Track E proof for work ledger, quality feedback, current load, handoff policy, improvement path, and profile projection state.</p>
                </div>
                <Badge variant={badgeVariant(latestEmployeeGrowth?.status ?? "")}>{compactStatus(latestEmployeeGrowth?.status)}</Badge>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge variant="outline">{stringValue(employeeGrowthSummary.employee_id) || "-"}</Badge>
                <Badge variant={badgeVariant(stringValue(employeeGrowthSummary.current_load_status))}>
                  {compactStatus(stringValue(employeeGrowthSummary.current_load_status))}
                </Badge>
                <Badge variant={Number(employeeGrowthSummary.runtime_run_count ?? 0) ? "success" : "warning"}>
                  {String(employeeGrowthSummary.runtime_run_count ?? 0)} runtime runs
                </Badge>
                <Badge variant={Number(employeeGrowthSummary.quality_feedback_count ?? 0) ? "success" : "warning"}>
                  {String(employeeGrowthSummary.quality_feedback_count ?? 0)} quality feedback
                </Badge>
                <Badge variant={Number(employeeGrowthSummary.handoff_work_history_score ?? 0) ? "success" : "warning"}>
                  work history score {String(employeeGrowthSummary.handoff_work_history_score ?? 0)}
                </Badge>
                <Badge variant={Number(employeeGrowthSummary.applied_improvement_count ?? 0) ? "success" : "warning"}>
                  {String(employeeGrowthSummary.applied_improvement_count ?? 0)} applied improvements
                </Badge>
                {stringValue(employeeGrowthSummary.improvement_loop_proof_status) ? (
                  <Badge variant={badgeVariant(stringValue(employeeGrowthSummary.improvement_loop_proof_status))}>
                    proof {compactStatus(stringValue(employeeGrowthSummary.improvement_loop_proof_status))}
                  </Badge>
                ) : null}
                {stringValue(employeeGrowthSummary.improvement_loop_application_status) ? (
                  <Badge variant={badgeVariant(stringValue(employeeGrowthSummary.improvement_loop_application_status))}>
                    application {compactStatus(stringValue(employeeGrowthSummary.improvement_loop_application_status))}
                  </Badge>
                ) : null}
                {Number(employeeGrowthSummary.improvement_loop_applied_change_count ?? 0) ? (
                  <Badge variant="success">
                    {String(employeeGrowthSummary.improvement_loop_applied_change_count ?? 0)} proof changes
                  </Badge>
                ) : null}
                {stringValue(employeeGrowthSummary.improvement_loop_ticket_report_id) ? (
                  <Badge variant="outline">{stringValue(employeeGrowthSummary.improvement_loop_ticket_report_id)}</Badge>
                ) : null}
                <Badge variant={badgeVariant(stringValue(employeeGrowthSummary.provider_projection_status))}>
                  {compactStatus(stringValue(employeeGrowthSummary.provider_projection_status))}
                </Badge>
              </div>
              {stringArrayValue(employeeGrowthSummary.warnings).length ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {stringArrayValue(employeeGrowthSummary.warnings).map((warning) => (
                    <Badge key={`employee-growth-warning-${warning}`} variant="warning">{compactStatus(warning)}</Badge>
                  ))}
                </div>
              ) : null}
              {latestEmployeeGrowth?.name ? (
                <div className="mt-3 truncate text-xs text-muted-foreground" title={latestEmployeeGrowth.name}>{latestEmployeeGrowth.name}</div>
              ) : null}
            </div>

            <div className="rounded-md border bg-card px-4 py-3 lg:col-span-2">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-semibold">Plan v8 Release Readiness Artifact</div>
                  <p className="mt-1 text-sm text-muted-foreground">Repeatable release-review proof from the Plan v8 readiness command, including blocker and evidence-ref state.</p>
                </div>
                <Badge variant={badgeVariant(latestPlanV8Readiness?.status ?? "")}>{compactStatus(latestPlanV8Readiness?.status)}</Badge>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge variant={planV8ReadinessSummary.ready_for_release ? "success" : "warning"}>
                  {planV8ReadinessSummary.ready_for_release ? "release ready" : "not release ready"}
                </Badge>
                <Badge variant="secondary">{String(planV8ReadinessSummary.check_count ?? 0)} checks</Badge>
                <Badge variant={Number(planV8ReadinessSummary.passed_count ?? 0) ? "success" : "outline"}>
                  {String(planV8ReadinessSummary.passed_count ?? 0)} passed
                </Badge>
                <Badge variant={Number(planV8ReadinessSummary.warning_count ?? 0) ? "warning" : "success"}>
                  {String(planV8ReadinessSummary.warning_count ?? 0)} warnings
                </Badge>
                <Badge variant={Number(planV8ReadinessSummary.blocked_count ?? 0) ? "warning" : "success"}>
                  {String(planV8ReadinessSummary.blocked_count ?? 0)} blocked
                </Badge>
                <Badge variant="outline">{String(stringArrayValue(planV8ReadinessSummary.evidence_refs).length)} evidence refs</Badge>
              </div>
              {stringValue(planV8ReadinessSummary.next_action) ? (
                <div className="mt-3 rounded-md border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                  {stringValue(planV8ReadinessSummary.next_action)}
                </div>
              ) : null}
              {stringArrayValue(planV8ReadinessSummary.blockers).length ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {stringArrayValue(planV8ReadinessSummary.blockers).map((blocker) => (
                    <Badge key={`plan-v8-readiness-blocker-${blocker}`} variant="warning">{compactStatus(blocker)}</Badge>
                  ))}
                </div>
              ) : null}
              {latestPlanV8Readiness?.name ? (
                <div className="mt-3 truncate text-xs text-muted-foreground" title={latestPlanV8Readiness.name}>{latestPlanV8Readiness.name}</div>
              ) : null}
            </div>

            {(evidenceGaps.length || evidenceWarnings.length || providerBlockers.length) ? (
              <div className="rounded-md border bg-card px-4 py-3 lg:col-span-2">
                <div className="mb-2 text-[10px] font-medium uppercase text-muted-foreground">Gaps, Warnings, and Provider Blockers</div>
                <div className="flex flex-wrap gap-2">
                  {evidenceGaps.map((gap) => <Badge key={`gap-${gap}`} variant="danger">{compactStatus(gap)}</Badge>)}
                  {evidenceWarnings.map((warning) => <Badge key={`warning-${warning}`} variant="warning">{compactStatus(warning)}</Badge>)}
                  {providerBlockers.map((blocker) => <Badge key={`blocker-${blocker}`} variant="warning">{compactStatus(blocker)}</Badge>)}
                </div>
              </div>
            ) : null}

            {recentRecords.length ? (
              <div className="rounded-md border bg-card px-4 py-3 lg:col-span-2">
                <div className="mb-2 text-[10px] font-medium uppercase text-muted-foreground">Recent Evidence</div>
                <div className="flex flex-wrap gap-2">
                  {recentRecords.slice(0, 6).map((record) => (
                    <Badge key={record.name} variant={badgeVariant(record.status)}>{record.name}</Badge>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </>
      )}
    </section>
  );
}

function ReleaseHygienePanel({ systemStatus }: { systemStatus: SystemStatusResponse | null }) {
  const hygiene = systemStatus?.release_hygiene ?? null;
  const summary = hygiene?.summary;
  const items = hygiene?.items ?? [];
  const categorySamples = hygiene?.category_samples ?? {};
  const [copiedCommandKey, setCopiedCommandKey] = useState("");
  const categorySampleEntries = ["source", "generated_artifact", "local_projection", "test_output", "unknown"]
    .map((category) => [category, categorySamples[category] ?? []] as const)
    .filter(([, samples]) => samples.length > 0);

  async function handleCopyCommand(key: string, command: string) {
    await copyTextToClipboard(command);
    setCopiedCommandKey(key);
  }

  function badgeVariant(status: string): "success" | "warning" | "danger" | "secondary" | "outline" {
    if (status === "ready" || status === "passed" || status === "clean") return "success";
    if (status === "warning") return "warning";
    if (status === "blocked" || status === "failed" || status === "unknown") return "danger";
    return status ? "secondary" : "outline";
  }

  function categoryVariant(category: string): "success" | "warning" | "danger" | "secondary" | "outline" {
    if (category === "source") return "success";
    if (category === "generated_artifact") return "secondary";
    if (category === "local_projection") return "warning";
    if (category === "test_output") return "outline";
    return "danger";
  }

  return (
    <section className="rounded-md border bg-background">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Release Hygiene</h3>
        </div>
        <div className="flex flex-wrap gap-2">
          {hygiene?.contract_version ? <Badge variant="outline">{hygiene.contract_version}</Badge> : null}
          <Badge variant={badgeVariant(hygiene?.status ?? "")}>{compactStatus(hygiene?.status)}</Badge>
          <Badge variant="secondary">{summary?.total_changed ?? 0} changed</Badge>
          <Badge variant={summary?.unknown_count ? "danger" : "success"}>{summary?.unknown_count ?? 0} unknown</Badge>
        </div>
      </div>
      {!hygiene ? (
        <div className="p-4">
          <EmptyDetail>No release hygiene summary is available.</EmptyDetail>
        </div>
      ) : (
        <>
          <div className="border-b bg-muted/40 px-4 py-2">
            <div className="truncate text-xs text-muted-foreground" title={hygiene.git_root}>
              {hygiene.git_root || "git root unavailable"}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">{hygiene.detail}</div>
          </div>
          <div className="grid gap-3 p-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
            <div className="rounded-md border bg-card px-4 py-3">
              <div className="mb-3 text-[10px] font-medium uppercase text-muted-foreground">Change Boundaries</div>
              <div className="grid gap-2 sm:grid-cols-2">
                <SummaryMetric label="Source" value={summary?.source_count ?? 0} tone={(summary?.source_count ?? 0) ? "warn" : undefined} />
                <SummaryMetric label="Artifacts" value={summary?.generated_artifact_count ?? 0} tone={(summary?.generated_artifact_count ?? 0) ? "ok" : undefined} />
                <SummaryMetric label="Local State" value={summary?.local_projection_count ?? 0} tone={(summary?.local_projection_count ?? 0) ? "warn" : undefined} />
                <SummaryMetric label="Test Output" value={summary?.test_output_count ?? 0} />
                <SummaryMetric label="Untracked" value={summary?.untracked_count ?? 0} tone={(summary?.untracked_count ?? 0) ? "warn" : undefined} />
                <SummaryMetric label="Modified" value={summary?.modified_count ?? 0} tone={(summary?.modified_count ?? 0) ? "warn" : undefined} />
              </div>
              {hygiene.boundary_notes.length ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {hygiene.boundary_notes.slice(0, 4).map((note) => <Badge key={note} variant="outline">{note}</Badge>)}
                </div>
              ) : null}
            </div>

            <div className="rounded-md border bg-card px-4 py-3">
              <div className="mb-3 text-[10px] font-medium uppercase text-muted-foreground">Review Commands</div>
              {hygiene.review_commands.length ? (
                <div className="space-y-2">
                  {hygiene.review_commands.slice(0, 5).map((command, index) => (
                    <CommandRow
                      key={command}
                      command={command}
                      copied={copiedCommandKey === `release-hygiene-${index}`}
                      label={`Release review command ${index + 1}`}
                      onCopy={() => void handleCopyCommand(`release-hygiene-${index}`, command)}
                    />
                  ))}
                </div>
              ) : (
                <EmptyDetail>No review commands are available.</EmptyDetail>
              )}
            </div>

            <div className="rounded-md border bg-card px-4 py-3 lg:col-span-2">
              <div className="mb-3 flex items-center justify-between gap-2">
                <div className="text-[10px] font-medium uppercase text-muted-foreground">Category Samples</div>
                <Badge variant="secondary">{categorySampleEntries.length}</Badge>
              </div>
              {categorySampleEntries.length ? (
                <div className="grid gap-2 lg:grid-cols-2">
                  {categorySampleEntries.map(([category, samples]) => (
                    <div key={`release-hygiene-category-${category}`} className="rounded-md border bg-muted/20 px-3 py-2">
                      <div className="mb-2 flex items-center justify-between gap-2">
                        <Badge variant={categoryVariant(category)} className="text-[10px]">{compactStatus(category)}</Badge>
                        <span className="text-[10px] text-muted-foreground">{samples.length} samples</span>
                      </div>
                      <div className="space-y-1">
                        {samples.slice(0, 3).map((item) => (
                          <div key={`${category}-${item.status_code}-${item.path}`} className="min-w-0 truncate font-mono text-xs" title={`${item.path} - ${compactStatus(item.review_action)}`}>
                            {item.path}
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyDetail>No categorized path samples were reported.</EmptyDetail>
              )}
            </div>

            <div className="rounded-md border bg-card px-4 py-3 lg:col-span-2">
              <div className="mb-3 flex items-center justify-between gap-2">
                <div className="text-[10px] font-medium uppercase text-muted-foreground">Changed Path Samples</div>
                <Badge variant="secondary">{items.length}</Badge>
              </div>
              {items.length ? (
                <div className="grid gap-2 lg:grid-cols-2">
                  {items.slice(0, 12).map((item: ReleaseHygieneItem) => (
                    <div key={`${item.status_code}-${item.path}`} className="rounded-md border bg-muted/20 px-3 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <div className="min-w-0 truncate font-mono text-xs" title={item.path}>{item.path}</div>
                        <Badge variant={categoryVariant(item.category)} className="shrink-0 text-[10px]">{compactStatus(item.category)}</Badge>
                      </div>
                      <div className="mt-1 flex flex-wrap gap-2 text-[10px] text-muted-foreground">
                        <span>{item.status_code.trim() || "changed"}</span>
                        <span>{compactStatus(item.review_action)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyDetail>No changed paths were reported by git.</EmptyDetail>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function SystemStatusSecretsPanel({ systemStatus }: { systemStatus: SystemStatusResponse | null }) {
  const secretItems = systemStatus?.secrets ?? [];
  const configuredSecrets = secretItems.filter((item) => item.configured).length;
  const missingSecrets = secretItems.length - configuredSecrets;
  const requiredEnvCount = secretItems.reduce((count, item) => count + item.env_vars.length, 0);
  const sortedSecretItems = [...secretItems].sort((left, right) => {
    if (left.configured !== right.configured) return left.configured ? 1 : -1;
    return left.scope.localeCompare(right.scope) || left.id.localeCompare(right.id);
  });

  return (
    <section className="rounded-md border bg-background">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <KeyRound className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Secrets Health</h3>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant={missingSecrets === 0 ? "success" : "warning"}>{configuredSecrets} configured</Badge>
          <Badge variant={missingSecrets === 0 ? "outline" : "danger"}>{missingSecrets} missing</Badge>
          <Badge variant="secondary">{requiredEnvCount} env vars</Badge>
        </div>
      </div>

      <div className="grid gap-3 p-4">
        {sortedSecretItems.length === 0 ? (
          <EmptyDetail>No secret health checks are registered.</EmptyDetail>
        ) : sortedSecretItems.map((item: SystemStatusSecretItem) => (
          <div key={item.id} className="rounded-md border bg-card px-4 py-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 space-y-2">
                <div className="flex flex-wrap gap-2">
                  {item.env_vars.map((envVar) => (
                    <Badge key={envVar} variant="outline">{envVar}</Badge>
                  ))}
                </div>
                <p className="text-sm text-muted-foreground">{item.purpose}</p>
              </div>
              <Badge variant={item.configured ? "success" : "danger"}>
                {item.configured ? "configured" : "missing"}
              </Badge>
            </div>

            <div className="mt-3 grid gap-3 text-xs text-muted-foreground md:grid-cols-[minmax(8rem,0.7fr)_minmax(12rem,1fr)_minmax(16rem,1.4fr)]">
              <div>
                <div className="font-medium uppercase">Scope</div>
                <div className="mt-1 text-foreground">{item.scope}</div>
              </div>
              <div>
                <div className="font-medium uppercase">Required For</div>
                <div className="mt-1 text-foreground">{item.required_for}</div>
              </div>
              <div>
                <div className="font-medium uppercase">Configure</div>
                <div className="mt-1 text-foreground">{item.how_to_configure}</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function SystemStatusBlockersPanel({ systemStatus }: { systemStatus: SystemStatusResponse | null }) {
  const blockers = systemStatus?.blockers ?? [];
  return (
    <section className="rounded-md border bg-background">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Operating Blockers</h3>
        </div>
        <Badge variant={blockers.length ? "warning" : "success"}>{blockers.length}</Badge>
      </div>
      <div className="grid gap-3 p-4">
        {blockers.length === 0 ? (
          <EmptyDetail>No backend setup blockers are currently reported.</EmptyDetail>
        ) : blockers.map((blocker) => (
          <div key={blocker.id} className="rounded-md border bg-card px-4 py-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-sm font-semibold">{blocker.scope}</div>
                <p className="mt-1 text-sm text-muted-foreground">{blocker.detail}</p>
              </div>
              <Badge variant="warning">{compactStatus(blocker.status)}</Badge>
            </div>
            {(() => {
              const reasons = stringArrayValue(blocker.reasons).slice(0, 5);
              const relatedBlockers = asRecordArray(blocker.related_blockers).slice(0, 4);
              const relatedCandidates = asRecordArray(blocker.related_candidates).slice(0, 4);
              const summary = asRecord(blocker.summary);
              const selectedExecutor = stringValue(summary.selected_executor_id);
              const providerSmokeStatus = stringValue(summary.provider_smoke_status);
              const repoWriteReadyCount = summary.repo_write_ready_count;
              const repoWriteCandidateCount = summary.repo_write_candidate_count;
              const mutationGateOpen = typeof summary.mutation_gate_open === "boolean" ? summary.mutation_gate_open : null;
              return (
                <>
                  {(blocker.setup_required.length || reasons.length || selectedExecutor || providerSmokeStatus || repoWriteReadyCount !== undefined) ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {selectedExecutor ? <Badge variant="outline">{selectedExecutor}</Badge> : null}
                      {repoWriteReadyCount !== undefined ? (
                        <Badge variant={Number(repoWriteReadyCount) > 0 ? "success" : "warning"}>
                          {String(repoWriteReadyCount)}/{String(repoWriteCandidateCount ?? "?")} repo-write ready
                        </Badge>
                      ) : null}
                      {mutationGateOpen !== null ? (
                        <Badge variant={mutationGateOpen ? "success" : "warning"}>
                          {mutationGateOpen ? "gate open" : "gate closed"}
                        </Badge>
                      ) : null}
                      {providerSmokeStatus ? <Badge variant="secondary">smoke {compactStatus(providerSmokeStatus)}</Badge> : null}
                      {reasons.map((reason) => (
                        <Badge key={`${blocker.id}-reason-${reason}`} variant="warning">{compactStatus(reason)}</Badge>
                      ))}
                      {blocker.setup_required.map((item) => (
                        <Badge key={`${blocker.id}-setup-${item}`} variant="outline">{item}</Badge>
                      ))}
                    </div>
                  ) : null}

                  {relatedBlockers.length ? (
                    <div className="mt-3 grid gap-2 border-t pt-3">
                      <div className="text-[10px] font-medium uppercase text-muted-foreground">Readiness Details</div>
                      {relatedBlockers.map((item, index) => {
                        const reason = stringValue(item.reason) || `blocker-${index + 1}`;
                        const setupRequired = stringArrayValue(item.setup_required).slice(0, 4);
                        const scope = stringValue(item.scope);
                        const status = stringValue(item.status) || "blocked";
                        return (
                          <div key={`${blocker.id}-related-${reason}-${index}`} className="rounded-md border bg-background px-3 py-2">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <div className="min-w-0 text-sm font-medium">{compactStatus(reason)}</div>
                              <Badge variant="warning">{compactStatus(status)}</Badge>
                            </div>
                            {scope ? <div className="mt-1 text-xs text-muted-foreground">{compactStatus(scope)}</div> : null}
                            {setupRequired.length ? (
                              <div className="mt-2 flex flex-wrap gap-2">
                                {setupRequired.map((item) => (
                                  <Badge key={`${blocker.id}-related-${reason}-${item}`} variant="outline">{item}</Badge>
                                ))}
                              </div>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                  ) : null}

                  {relatedCandidates.length ? (
                    <div className="mt-3 grid gap-2 border-t pt-3">
                      <div className="text-[10px] font-medium uppercase text-muted-foreground">Runtime Candidates</div>
                      {relatedCandidates.map((candidate, index) => {
                        const executorId = stringValue(candidate.executor_id) || `candidate-${index + 1}`;
                        const displayName = stringValue(candidate.display_name) || executorId.replace(/_/g, " ");
                        const status = stringValue(candidate.status) || "unknown";
                        const setupRequired = stringArrayValue(candidate.setup_required).slice(0, 4);
                        const ready = candidate.ready === true;
                        return (
                          <div key={`${blocker.id}-candidate-${executorId}-${index}`} className="rounded-md border bg-background px-3 py-2">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <div className="min-w-0 text-sm font-medium">{displayName}</div>
                              <Badge variant={ready ? "success" : "warning"}>{compactStatus(status)}</Badge>
                            </div>
                            {setupRequired.length ? (
                              <div className="mt-2 flex flex-wrap gap-2">
                                {setupRequired.map((item) => (
                                  <Badge key={`${blocker.id}-candidate-${executorId}-${item}`} variant="outline">{item}</Badge>
                                ))}
                              </div>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                  ) : null}
                </>
              );
            })()}
          </div>
        ))}
      </div>
    </section>
  );
}

function EnvironmentSmokePanel({
  onSmoke,
  smokeResult,
  smoking,
}: {
  onSmoke: (includeExternal?: boolean) => void;
  smokeResult: EnvironmentSmokeResponse | null;
  smoking: boolean;
}) {
  const checks = smokeResult?.checks ?? [];

  function badgeVariant(status: string): "success" | "warning" | "danger" | "secondary" {
    if (status === "passed" || status === "ready") return "success";
    if (status === "setup_blocked" || status === "disabled" || status === "not_configured" || status === "warning") return "warning";
    if (status === "failed" || status === "error") return "danger";
    return "secondary";
  }

  return (
    <section className="rounded-md border bg-background">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Environment Smoke</h3>
        </div>
        <div className="flex flex-wrap gap-2">
          {smokeResult?.summary.contract_version ? <Badge variant="outline">{smokeResult.summary.contract_version}</Badge> : null}
          <Button type="button" variant="outline" size="sm" onClick={() => onSmoke(false)} disabled={smoking}>
            <PlayCircle className="h-4 w-4" />
            {smoking ? "Smoking" : "Environment Smoke"}
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => onSmoke(true)} disabled={smoking}>
            <PlayCircle className="h-4 w-4" />
            External Environment Smoke
          </Button>
        </div>
      </div>
      {smokeResult ? (
        <div className="border-b bg-muted/30 px-4 py-2">
          <div className="flex flex-wrap gap-2">
            <Badge variant={badgeVariant(smokeResult.status)}>{compactStatus(smokeResult.status)}</Badge>
            <Badge variant="secondary">{smokeResult.summary.check_count} checks</Badge>
            <Badge variant={(smokeResult.summary.blocked_count ?? 0) ? "warning" : "success"}>{smokeResult.summary.blocked_count} blocked</Badge>
            <Badge variant={(smokeResult.summary.warning_count ?? 0) ? "warning" : "success"}>{smokeResult.summary.warning_count} warnings</Badge>
            <Badge variant={(smokeResult.summary.failed_count ?? 0) ? "danger" : "success"}>{smokeResult.summary.failed_count} failed</Badge>
            <Badge variant={smokeResult.summary.external_calls ? "warning" : "success"}>
              {smokeResult.summary.external_calls ? "external calls" : "no external calls"}
            </Badge>
            <Badge variant="outline">{smokeResult.summary.evaluation_scope}</Badge>
          </div>
          {smokeResult.summary.core_boundary ? (
            <p className="mt-2 text-xs text-muted-foreground">{smokeResult.summary.core_boundary}</p>
          ) : null}
        </div>
      ) : null}
      <div className="grid gap-3 p-4 lg:grid-cols-2">
        {checks.length === 0 ? (
          <EmptyDetail>Run a read-only environment smoke to inspect DeepSeek, providers, local fallback, and LangGraph readiness.</EmptyDetail>
        ) : checks.map((check) => {
          const visibleBlockers = asRecordArray(check.blockers).slice(0, 3);
          return (
            <div key={check.id} className="rounded-md border bg-card px-4 py-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="text-sm font-semibold">{check.scope}</div>
                    <Badge variant="outline">{check.id}</Badge>
                    {check.external_calls ? <Badge variant="warning">external calls</Badge> : <Badge variant="success">local only</Badge>}
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">{check.detail}</p>
                </div>
                <Badge variant={badgeVariant(check.status)}>{compactStatus(check.status)}</Badge>
              </div>

              {check.checks.length ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {check.checks.slice(0, 5).map((item) => (
                    <Badge key={`${check.id}-check-${item}`} variant="outline">{item}</Badge>
                  ))}
                  {check.checks.length > 5 ? <Badge variant="secondary">+{check.checks.length - 5}</Badge> : null}
                </div>
              ) : null}

              {visibleBlockers.length ? (
                <div className="mt-3 border-t pt-3">
                  <div className="text-[10px] font-medium uppercase text-muted-foreground">Blockers</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {visibleBlockers.map((blocker, index) => {
                      const setupRequired = Array.isArray(blocker.setup_required) ? blocker.setup_required.map(String).filter(Boolean) : [];
                      const blockerId = stringValue(blocker.id) || stringValue(blocker.provider_id) || `blocker-${index}`;
                      return (
                        <Badge key={`${check.id}-blocker-${blockerId}-${index}`} variant="warning">
                          {setupRequired[0] ?? blockerId}
                        </Badge>
                      );
                    })}
                  </div>
                </div>
              ) : null}

              {check.warnings.length || check.failures.length ? (
                <div className="mt-3 border-t pt-3">
                  <div className="text-[10px] font-medium uppercase text-muted-foreground">Signals</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {check.warnings.slice(0, 3).map((warning) => (
                      <Badge key={`${check.id}-warning-${warning}`} variant="secondary">{warning}</Badge>
                    ))}
                    {check.failures.slice(0, 3).map((failure) => (
                      <Badge key={`${check.id}-failure-${failure}`} variant="danger">{failure}</Badge>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function ProviderConformancePanel({
  onSmoke,
  smokeResult,
  smoking,
  systemStatus,
}: {
  onSmoke: (includeExternal?: boolean) => void;
  smokeResult: ProviderConformanceSmokeResponse | null;
  smoking: boolean;
  systemStatus: SystemStatusResponse | null;
}) {
  const conformance = systemStatus?.provider_conformance;
  const providers = [...(conformance?.providers ?? [])].sort((left, right) => {
    if (left.provider_kind !== right.provider_kind) return left.provider_kind.localeCompare(right.provider_kind);
    return left.provider_id.localeCompare(right.provider_id);
  });
  const runtimeBoundaryStatus = conformance?.summary.runtime_boundary_status ?? "";
  const runtimeBoundaryChecks = conformance?.summary.runtime_boundary_checks ?? [];
  const runtimeBoundaryWarnings = conformance?.summary.runtime_boundary_warnings ?? [];
  const runtimeBoundaryBlockers = conformance?.summary.runtime_boundary_blockers ?? [];
  const hasRuntimeBoundarySummary =
    Boolean(runtimeBoundaryStatus) ||
    runtimeBoundaryChecks.length > 0 ||
    runtimeBoundaryWarnings.length > 0 ||
    runtimeBoundaryBlockers.length > 0;
  const smokeByProvider = new Map((smokeResult?.results ?? []).map((item) => [item.provider_id, item]));

  function badgeVariant(status: string): "success" | "warning" | "danger" | "secondary" {
    if (status === "ready" || status === "passed") return "success";
    if (status === "setup_blocked" || status === "disabled" || status === "not_configured" || status === "llm_not_configured") return "warning";
    if (status === "failed" || status === "error") return "danger";
    return "secondary";
  }

  return (
    <section className="rounded-md border bg-background">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Plug className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Provider Adapter Conformance</h3>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant="secondary">{conformance?.summary.provider_count ?? providers.length} providers</Badge>
          <Badge variant={(conformance?.summary.blocked_count ?? 0) ? "warning" : "success"}>{conformance?.summary.blocked_count ?? 0} blocked</Badge>
          <Badge variant={(conformance?.summary.core_blocked_count ?? 0) ? "warning" : "success"}>{conformance?.summary.production_ready_count ?? 0} production-ready</Badge>
          {conformance?.contract_version ? <Badge variant="outline">{conformance.contract_version}</Badge> : null}
          <Button type="button" variant="outline" size="sm" onClick={() => onSmoke(false)} disabled={smoking}>
            <PlayCircle className="h-4 w-4" />
            {smoking ? "Smoking" : "Smoke"}
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => onSmoke(true)} disabled={smoking}>
            <PlayCircle className="h-4 w-4" />
            External Smoke
          </Button>
        </div>
      </div>
      {conformance?.summary.core_model_boundary ? (
        <div className="border-b bg-muted/40 px-4 py-2 text-xs text-muted-foreground">
          {conformance.summary.core_model_boundary}
        </div>
      ) : null}
      {hasRuntimeBoundarySummary ? (
        <div className="border-b bg-muted/20 px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-[10px] font-medium uppercase text-muted-foreground">Runtime Boundary</div>
              <div className="mt-1 text-sm font-medium">Chat route and runtime contract audit</div>
            </div>
            <div className="flex flex-wrap gap-2">
              {runtimeBoundaryStatus ? (
                <Badge variant={badgeVariant(runtimeBoundaryStatus)}>{compactStatus(runtimeBoundaryStatus)}</Badge>
              ) : null}
              <Badge variant={runtimeBoundaryBlockers.length ? "warning" : "success"}>
                {runtimeBoundaryBlockers.length} runtime blockers
              </Badge>
              {runtimeBoundaryWarnings.length ? (
                <Badge variant="secondary">{runtimeBoundaryWarnings.length} warnings</Badge>
              ) : null}
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {runtimeBoundaryChecks.map((check) => (
              <Badge key={`runtime-boundary-check-${check}`} variant="outline">{check}</Badge>
            ))}
            {runtimeBoundaryBlockers.map((blocker) => (
              <Badge key={`runtime-boundary-blocker-${blocker}`} variant="warning">{compactStatus(blocker)}</Badge>
            ))}
            {runtimeBoundaryWarnings.map((warning) => (
              <Badge key={`runtime-boundary-warning-${warning}`} variant="secondary">{compactStatus(warning)}</Badge>
            ))}
          </div>
        </div>
      ) : null}
      {smokeResult ? (
        <div className="flex flex-wrap gap-2 border-b bg-muted/30 px-4 py-2">
          <Badge variant={smokeResult.status === "passed" ? "success" : "danger"}>{compactStatus(smokeResult.status)}</Badge>
          <Badge variant="secondary">{smokeResult.summary.provider_count} providers</Badge>
          <Badge variant={(smokeResult.summary.blocked_count ?? 0) ? "warning" : "success"}>{smokeResult.summary.blocked_count} blocked</Badge>
          <Badge variant={(smokeResult.summary.failed_count ?? 0) ? "danger" : "success"}>{smokeResult.summary.failed_count} failed</Badge>
          <Badge variant={smokeResult.summary.external_calls ? "warning" : "success"}>
            {smokeResult.summary.external_calls ? "external calls" : "no external calls"}
          </Badge>
          <Badge variant="outline">{smokeResult.summary.evaluation_scope}</Badge>
        </div>
      ) : null}
      <div className="grid gap-3 p-4 lg:grid-cols-2">
        {providers.length === 0 ? (
          <EmptyDetail>No provider adapters are registered.</EmptyDetail>
        ) : providers.map((provider: ProviderConformanceRecord) => {
          const smoke = smokeByProvider.get(provider.provider_id);
          const smokeEndpoint = stringValue(provider.conformance_smoke.endpoint);
          const smokeMethod = stringValue(provider.conformance_smoke.method);
          const projectionEndpoints = stringArrayValue(provider.conformance_smoke.projection_endpoints);
          const visibleCapabilities = provider.capabilities.slice(0, 6);
          const visibleProjection = provider.projection_direction.slice(0, 3);
          const visibleFailures = provider.failure_semantics.slice(0, 4);
          const visibleContracts = (provider.contract_expectations ?? []).slice(0, 4);
          const production = provider.production_evaluation;
          const setupRequired = provider.setup_blockers.flatMap((blocker) => blocker.setup_required);
          return (
            <div key={provider.provider_id} className="rounded-md border bg-card px-4 py-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="text-sm font-semibold">{provider.display_name}</div>
                    <Badge variant="outline">{provider.provider_kind}</Badge>
                    {provider.fallback_provider ? <Badge variant="secondary">{provider.fallback_provider}</Badge> : null}
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">{provider.detail}</p>
                </div>
                <Badge variant={badgeVariant(provider.status)}>{compactStatus(provider.status)}</Badge>
              </div>

              {setupRequired.length ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {setupRequired.slice(0, 8).map((item) => (
                    <Badge key={`${provider.provider_id}-${item}`} variant="danger">{item}</Badge>
                  ))}
                </div>
              ) : null}

              {production ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  <Badge variant={production.production_ready ? "success" : production.blockers.length ? "warning" : "secondary"}>
                    {production.readiness_level}
                  </Badge>
                  {production.required_for_core ? <Badge variant="outline">core</Badge> : <Badge variant="secondary">optional</Badge>}
                  <Badge variant="outline">{production.migration_status}</Badge>
                </div>
              ) : null}

              <div className="mt-3 flex flex-wrap gap-2">
                {visibleCapabilities.map((capability) => (
                  <Badge key={`${provider.provider_id}-${capability}`} variant="outline">{capability}</Badge>
                ))}
                {provider.capabilities.length > visibleCapabilities.length ? (
                  <Badge variant="secondary">+{provider.capabilities.length - visibleCapabilities.length}</Badge>
                ) : null}
              </div>

              {visibleContracts.length ? (
                <div className="mt-3 border-t pt-3">
                  <div className="text-[10px] font-medium uppercase text-muted-foreground">Contract Guards</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {visibleContracts.map((expectation) => (
                      <Badge
                        key={`${provider.provider_id}-contract-${expectation.id}`}
                        variant={expectation.status === "passed" ? "success" : "danger"}
                      >
                        {expectation.id}
                      </Badge>
                    ))}
                    {(provider.contract_expectations?.length ?? 0) > visibleContracts.length ? (
                      <Badge variant="secondary">+{(provider.contract_expectations?.length ?? 0) - visibleContracts.length}</Badge>
                    ) : null}
                  </div>
                </div>
              ) : null}

              {(smokeEndpoint || projectionEndpoints.length) ? (
                <div className="mt-3 border-t pt-3">
                  <div className="text-[10px] font-medium uppercase text-muted-foreground">Conformance Smoke</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {smokeMethod ? <Badge variant="secondary">{smokeMethod}</Badge> : null}
                    {smokeEndpoint ? <Badge variant="outline">{smokeEndpoint}</Badge> : null}
                    {projectionEndpoints.slice(0, 3).map((endpoint) => (
                      <Badge key={`${provider.provider_id}-${endpoint}`} variant="outline">{endpoint}</Badge>
                    ))}
                  </div>
                </div>
              ) : null}

              {smoke ? (
                <div className="mt-3 border-t pt-3">
                  <div className="text-[10px] font-medium uppercase text-muted-foreground">Provider Smoke</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Badge variant={badgeVariant(smoke.status)}>{compactStatus(smoke.status)}</Badge>
                    <Badge variant="outline">{smoke.smoke_kind}</Badge>
                    {smoke.external_calls ? <Badge variant="warning">external calls</Badge> : <Badge variant="success">local only</Badge>}
                    {smoke.checks.slice(0, 3).map((check) => (
                      <Badge key={`${provider.provider_id}-smoke-check-${check}`} variant="outline">{check}</Badge>
                    ))}
                    {smoke.warnings.slice(0, 2).map((warning) => (
                      <Badge key={`${provider.provider_id}-smoke-warning-${warning}`} variant="secondary">{warning}</Badge>
                    ))}
                    {smoke.failures.slice(0, 2).map((failure) => (
                      <Badge key={`${provider.provider_id}-smoke-failure-${failure}`} variant="danger">{failure}</Badge>
                    ))}
                  </div>
                </div>
              ) : null}

              {visibleProjection.length ? (
                <div className="mt-3 border-t pt-3">
                  <div className="text-[10px] font-medium uppercase text-muted-foreground">Projection</div>
                  <div className="mt-2 grid gap-1 text-xs text-muted-foreground">
                    {visibleProjection.map((item) => (
                      <div key={`${provider.provider_id}-projection-${item}`} className="truncate" title={item}>{item}</div>
                    ))}
                  </div>
                </div>
              ) : null}

              {visibleFailures.length ? (
                <div className="mt-3 border-t pt-3">
                  <div className="text-[10px] font-medium uppercase text-muted-foreground">Failure Semantics</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {visibleFailures.map((item) => (
                      <Badge key={`${provider.provider_id}-failure-${item}`} variant="secondary">{item}</Badge>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function LiveProviderDogfoodReadinessPanel({ systemStatus }: { systemStatus: SystemStatusResponse | null }) {
  const readiness = systemStatus?.live_provider_dogfood;
  const blockers = asRecordArray(readiness?.blockers);
  const candidates = readiness?.repo_write_executor_candidates ?? [];
  const readyCandidateCount = Number(readiness?.summary.repo_write_ready_count ?? candidates.filter((item) => item.ready).length);
  const readinessSummary = asRecord(readiness?.summary);
  const providerPrerequisites = asRecord(readiness?.provider_prerequisites);
  const ticketBackend = asRecord(providerPrerequisites.ticket_backend);
  const planeTicketSetup = asRecord(providerPrerequisites.plane_ticket_backend_setup);
  const memoryBackend = asRecord(providerPrerequisites.memory_backend);
  const providerSmoke = asRecord(providerPrerequisites.provider_smoke);
  const mutationGate = asRecord(readiness?.mutation_gate);
  const selectedPreflight = asRecord(readiness?.selected_executor_preflight);
  const selectedCapabilities = stringArrayValue(selectedPreflight.capabilities);
  const ticketBackendMode = stringValue(readinessSummary.ticket_backend_mode) || stringValue(ticketBackend.mode);
  const ticketBackendProvider = stringValue(readinessSummary.ticket_backend_provider) || stringValue(ticketBackend.provider);
  const planeTicketBackendSelected = Boolean(readinessSummary.plane_ticket_backend_selected);
  const planeTicketSetupStatus = stringValue(readinessSummary.plane_ticket_backend_setup_status) || stringValue(planeTicketSetup.status);
  const planeTicketSetupRequired = stringArrayValue(readinessSummary.plane_ticket_backend_setup_required).length
    ? stringArrayValue(readinessSummary.plane_ticket_backend_setup_required)
    : stringArrayValue(planeTicketSetup.setup_required);
  const planeScopeCandidates = asRecordArray(planeTicketSetup.code_repository_scope_candidates);
  const planeScopeMissing = asRecordArray(planeTicketSetup.code_repository_scope_missing);
  const planeScopeStatus = stringValue(readinessSummary.plane_ticket_scope_status) || stringValue(planeTicketSetup.code_repository_scope_status);
  const planeScopeCandidateCount = numberValue(
    readinessSummary.plane_ticket_scope_candidate_count ?? planeTicketSetup.code_repository_scope_candidate_count,
    planeScopeCandidates.length,
  );
  const planeScopeMissingCount = numberValue(
    readinessSummary.plane_ticket_scope_missing_count ?? planeTicketSetup.code_repository_scope_missing_count,
    planeScopeMissing.length,
  );

  function badgeVariant(status: string): "success" | "warning" | "danger" | "secondary" {
    if (status === "ready" || status === "passed" || status === "open") return "success";
    if (status === "blocked" || status === "setup_blocked" || status === "disabled" || status === "confirmation_required") return "warning";
    if (status === "failed" || status === "error") return "danger";
    return "secondary";
  }

  return (
    <section className="rounded-md border bg-background">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <PlayCircle className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Live Provider Dogfood Readiness</h3>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant={badgeVariant(readiness?.status ?? "missing")}>{compactStatus(readiness?.status)}</Badge>
          {readiness?.selected_executor_id ? <Badge variant="outline">{readiness.selected_executor_id}</Badge> : null}
          <Badge variant={readyCandidateCount > 0 ? "success" : "warning"}>{readyCandidateCount}/{candidates.length} repo-write ready</Badge>
          <Badge variant={mutationGate.open ? "success" : "warning"}>
            {mutationGate.open ? "gate open" : "gate closed"}
          </Badge>
        </div>
      </div>
      {stringValue(readiness?.summary.anti_wheel_boundary) ? (
        <div className="border-b bg-muted/40 px-4 py-2 text-xs text-muted-foreground">
          {stringValue(readiness?.summary.anti_wheel_boundary)}
        </div>
      ) : null}
      <div className="grid gap-3 p-4 lg:grid-cols-2">
        {!readiness ? (
          <EmptyDetail>No live provider dogfood readiness contract is available.</EmptyDetail>
        ) : (
          <>
            <div className="rounded-md border bg-card px-4 py-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-semibold">Selected Runtime</div>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {readiness.selected_executor_id} must satisfy repo-write governance before live provider writes.
                  </p>
                </div>
                <Badge variant={badgeVariant(stringValue(selectedPreflight.status))}>{compactStatus(stringValue(selectedPreflight.status))}</Badge>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {selectedCapabilities.slice(0, 6).map((capability) => (
                  <Badge key={capability} variant="outline">{capability}</Badge>
                ))}
                {readiness.require_repo_write_executor ? <Badge variant="warning">repo:write required</Badge> : <Badge variant="secondary">repo:write optional</Badge>}
              </div>
            </div>

            <div className="rounded-md border bg-card px-4 py-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-semibold">Provider Preconditions</div>
                  <p className="mt-1 text-sm text-muted-foreground">Ticket and Memory providers stay the source-backed prerequisites for the live loop.</p>
                </div>
                <Badge variant={badgeVariant(stringValue(providerSmoke.status))}>{compactStatus(stringValue(providerSmoke.status) || "not run")}</Badge>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge variant={badgeVariant(stringValue(ticketBackend.status))}>Ticket {compactStatus(stringValue(ticketBackend.status))}</Badge>
                <Badge variant={badgeVariant(stringValue(memoryBackend.status))}>Memory {compactStatus(stringValue(memoryBackend.status))}</Badge>
                {ticketBackendMode ? (
                  <Badge variant={planeTicketBackendSelected ? "success" : "warning"}>Ticket mode {compactStatus(ticketBackendMode)}</Badge>
                ) : null}
                {ticketBackendProvider ? <Badge variant="outline">{ticketBackendProvider}</Badge> : null}
                {planeTicketSetupStatus ? (
                  <Badge variant={badgeVariant(planeTicketSetupStatus)}>Plane config {compactStatus(planeTicketSetupStatus)}</Badge>
                ) : null}
                {planeScopeStatus ? (
                  <Badge variant={planeScopeCandidateCount ? "success" : "warning"}>Plane scope {compactStatus(planeScopeStatus)}</Badge>
                ) : null}
                {planeScopeCandidateCount || planeScopeMissingCount ? (
                  <Badge variant="outline">{planeScopeCandidateCount}/{planeScopeCandidateCount + planeScopeMissingCount} scope candidates</Badge>
                ) : null}
                {stringValue(memoryBackend.backend) ? <Badge variant="outline">{stringValue(memoryBackend.backend)}</Badge> : null}
                {stringValue(providerSmoke.reason) ? <Badge variant="secondary">{stringValue(providerSmoke.reason)}</Badge> : null}
              </div>
              {planeTicketSetupRequired.length ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  {planeTicketSetupRequired.slice(0, 6).map((item) => (
                    <Badge key={`plane-setup-${item}`} variant="outline">{item}</Badge>
                  ))}
                </div>
              ) : null}
              <div className="mt-3 grid gap-2 sm:grid-cols-3">
                <Button type="button" variant="outline" size="sm" onClick={() => navigateTo("settings", "code-repositories")}>
                  <FolderGit2 className="h-4 w-4" />
                  Code Repositories
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={() => navigateTo("settings", "ticket-backend")}>
                  <ClipboardList className="h-4 w-4" />
                  Ticket Backend
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={() => navigateTo("settings", "memory-backend")}>
                  <Database className="h-4 w-4" />
                  Memory Backend
                </Button>
              </div>
              {planeScopeCandidates.length ? (
                <div className="mt-3 grid gap-2">
                  {planeScopeCandidates.slice(0, 3).map((candidate) => {
                    const repositoryId = stringValue(candidate.repository_id) || stringValue(candidate.repository_name);
                    return (
                      <div key={`plane-scope-candidate-${repositoryId}`} className="rounded-md border bg-background px-3 py-2">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="text-sm font-medium">{stringValue(candidate.repository_name) || repositoryId}</div>
                          <Badge variant="success">scope candidate</Badge>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          <Badge variant="outline">{stringValue(candidate.plane_workspace_slug)}</Badge>
                          <Badge variant="outline">{stringValue(candidate.plane_project_id)}</Badge>
                          <Badge variant={badgeVariant(stringValue(candidate.status))}>{compactStatus(stringValue(candidate.status))}</Badge>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : planeScopeMissing.length ? (
                <div className="mt-3 grid gap-2">
                  {planeScopeMissing.slice(0, 3).map((candidate) => {
                    const repositoryId = stringValue(candidate.repository_id) || stringValue(candidate.repository_name);
                    const workspaceConfigured = Boolean(candidate.workspace_configured);
                    const projectConfigured = Boolean(candidate.project_configured);
                    return (
                      <div key={`plane-scope-missing-${repositoryId}`} className="rounded-md border bg-background px-3 py-2">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="text-sm font-medium">{stringValue(candidate.repository_name) || repositoryId}</div>
                          <Badge variant="warning">scope incomplete</Badge>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          <Badge variant={workspaceConfigured ? "success" : "warning"}>
                            workspace {workspaceConfigured ? "set" : "missing"}
                          </Badge>
                          <Badge variant={projectConfigured ? "success" : "warning"}>
                            project {projectConfigured ? "set" : "missing"}
                          </Badge>
                          <Badge variant={badgeVariant(stringValue(candidate.status))}>{compactStatus(stringValue(candidate.status))}</Badge>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : planeScopeStatus ? (
                <div className="mt-3">
                  <EmptyDetail>No Code Repository Plane scope candidates are configured.</EmptyDetail>
                </div>
              ) : null}
            </div>

            <div className="rounded-md border bg-card px-4 py-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-semibold">Repo-Write Candidates</div>
                  <p className="mt-1 text-sm text-muted-foreground">Only mature RuntimeExecutor providers with repo-write capability can run the full live mutation loop.</p>
                </div>
                <Badge variant={readyCandidateCount > 0 ? "success" : "warning"}>{readyCandidateCount} ready</Badge>
              </div>
              <div className="mt-3 grid gap-2">
                {candidates.length === 0 ? (
                  <EmptyDetail>No repo-write RuntimeExecutor providers are registered.</EmptyDetail>
                ) : candidates.map((candidate) => (
                  <div key={candidate.executor_id} className="rounded-md border bg-background px-3 py-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="text-sm font-medium">{candidate.executor_id.replace(/_/g, " ")}</div>
                      <Badge variant={badgeVariant(candidate.status)}>{compactStatus(candidate.status)}</Badge>
                    </div>
                    {candidate.setup_required.length ? (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {candidate.setup_required.slice(0, 5).map((item) => (
                          <Badge key={`${candidate.executor_id}-${item}`} variant="outline">{item}</Badge>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-md border bg-card px-4 py-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-semibold">Readiness Blockers</div>
                  <p className="mt-1 text-sm text-muted-foreground">These blockers must clear before live Plane / Graphiti writes can be attempted.</p>
                </div>
                <Badge variant={blockers.length ? "warning" : "success"}>{blockers.length}</Badge>
              </div>
              <div className="mt-3 grid gap-2">
                {blockers.length === 0 ? (
                  <EmptyDetail>The live provider dogfood loop is ready to execute.</EmptyDetail>
                ) : blockers.map((blocker, index) => {
                  const reason = stringValue(blocker.reason) || `blocker-${index + 1}`;
                  const setupRequired = stringArrayValue(blocker.setup_required);
                  return (
                    <div key={`${reason}-${index}`} className="rounded-md border bg-background px-3 py-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="text-sm font-medium">{compactStatus(reason)}</div>
                        <Badge variant={badgeVariant(stringValue(blocker.status) || "blocked")}>{compactStatus(stringValue(blocker.status) || "blocked")}</Badge>
                      </div>
                      {stringValue(blocker.detail) ? <p className="mt-1 text-xs text-muted-foreground">{stringValue(blocker.detail)}</p> : null}
                      {setupRequired.length ? (
                        <div className="mt-2 flex flex-wrap gap-2">
                          {setupRequired.slice(0, 5).map((item) => (
                            <Badge key={`${reason}-${item}`} variant="outline">{item}</Badge>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </div>
    </section>
  );
}

function LiveProviderSoakPlanPanel({ systemStatus }: { systemStatus: SystemStatusResponse | null }) {
  const plan = systemStatus?.live_provider_soak_plan ?? null;
  const scenarios = plan?.scenarios ?? [];
  const [copiedCommandKey, setCopiedCommandKey] = useState("");

  function badgeVariant(status: string): "success" | "warning" | "danger" | "secondary" | "outline" {
    if (status === "ready" || status === "passed" || status === "completed") return "success";
    if (status === "blocked" || status === "setup_blocked" || status === "warning" || status === "retry" || status === "approval" || status === "handoff") return "warning";
    if (status === "failed" || status === "error") return "danger";
    return status ? "secondary" : "outline";
  }

  async function handleCopyCommand(key: string, command: string) {
    await copyTextToClipboard(command);
    setCopiedCommandKey(key);
  }

  return (
    <section className="rounded-md border bg-background">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <PlayCircle className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Live Provider Soak Plan</h3>
        </div>
        <div className="flex flex-wrap gap-2">
          {plan?.contract_version ? <Badge variant="outline">{plan.contract_version}</Badge> : null}
          <Badge variant={badgeVariant(plan?.status ?? "")}>{compactStatus(plan?.status)}</Badge>
          <Badge variant="secondary">{plan?.summary.scenario_count ?? 0} scenarios</Badge>
          <Badge variant={(plan?.summary.blocked_scenario_count ?? 0) ? "warning" : "success"}>
            {plan?.summary.blocked_scenario_count ?? 0} blocked
          </Badge>
          <Badge variant={plan?.summary.mutation_gate_open ? "success" : "warning"}>
            {plan?.summary.mutation_gate_open ? "gate open" : "gate closed"}
          </Badge>
        </div>
      </div>
      {!plan ? (
        <div className="p-4">
          <EmptyDetail>No live provider soak plan is available.</EmptyDetail>
        </div>
      ) : (
        <>
          <div className="border-b bg-muted/40 px-4 py-2">
            <div className="text-xs text-muted-foreground">{plan.detail}</div>
            <div className="mt-2 flex flex-wrap gap-2">
              <Badge variant="outline">{plan.summary.selected_executor_id || "-"}</Badge>
              <Badge variant={badgeVariant(plan.summary.ticket_backend_status)}>Ticket {compactStatus(plan.summary.ticket_backend_status)}</Badge>
              {plan.summary.ticket_backend_mode ? (
                <Badge variant={plan.summary.plane_ticket_backend_selected ? "success" : "warning"}>
                  Ticket mode {compactStatus(plan.summary.ticket_backend_mode)}
                </Badge>
              ) : null}
              {plan.summary.plane_ticket_backend_setup_status ? (
                <Badge variant={badgeVariant(plan.summary.plane_ticket_backend_setup_status)}>
                  Plane config {compactStatus(plan.summary.plane_ticket_backend_setup_status)}
                </Badge>
              ) : null}
              {plan.summary.plane_ticket_scope_status ? (
                <Badge variant={plan.summary.plane_ticket_scope_candidate_count ? "success" : "warning"}>
                  Plane scope {compactStatus(plan.summary.plane_ticket_scope_status)}
                </Badge>
              ) : null}
              {(plan.summary.plane_ticket_scope_candidate_count || plan.summary.plane_ticket_scope_missing_count) ? (
                <Badge variant="outline">
                  {plan.summary.plane_ticket_scope_candidate_count ?? 0}/{(plan.summary.plane_ticket_scope_candidate_count ?? 0) + (plan.summary.plane_ticket_scope_missing_count ?? 0)} scope candidates
                </Badge>
              ) : null}
              <Badge variant={badgeVariant(plan.summary.memory_backend_status)}>Memory {compactStatus(plan.summary.memory_backend_status)}</Badge>
              {(plan.summary.plane_ticket_backend_setup_required ?? []).slice(0, 4).map((item) => (
                <Badge key={`soak-plane-setup-${item}`} variant="outline">{item}</Badge>
              ))}
              {plan.summary.expected_states.map((state) => (
                <Badge key={state} variant="secondary">{compactStatus(state)}</Badge>
              ))}
            </div>
          </div>
          <div className="grid gap-3 p-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
            <div className="rounded-md border bg-card px-4 py-3">
              <div className="mb-3 text-[10px] font-medium uppercase text-muted-foreground">Repeated Soak Matrix</div>
              {scenarios.length ? (
                <div className="grid gap-2">
                  {scenarios.map((scenario: LiveProviderSoakScenario) => (
                    <div key={scenario.id} className="rounded-md border bg-background px-3 py-2">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="text-sm font-medium">{scenario.title}</div>
                          <p className="mt-1 text-xs text-muted-foreground">{scenario.detail}</p>
                        </div>
                        <div className="flex shrink-0 flex-wrap justify-end gap-2">
                          <Badge variant={badgeVariant(scenario.expected_state)}>{compactStatus(scenario.expected_state)}</Badge>
                          <Badge variant={badgeVariant(scenario.status)}>{compactStatus(scenario.status)}</Badge>
                        </div>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {scenario.required_evidence.slice(0, 5).map((item) => (
                          <Badge key={`${scenario.id}-evidence-${item}`} variant="outline">{compactStatus(item)}</Badge>
                        ))}
                        {scenario.required_evidence.length > 5 ? <Badge variant="secondary">+{scenario.required_evidence.length - 5}</Badge> : null}
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {scenario.ui_surfaces.map((surface) => (
                          <Badge key={`${scenario.id}-surface-${surface}`} variant="secondary">{surface}</Badge>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyDetail>No repeated-soak scenarios are registered.</EmptyDetail>
              )}
            </div>

            <div className="grid gap-3">
              <div className="rounded-md border bg-card px-4 py-3">
                <div className="mb-3 text-[10px] font-medium uppercase text-muted-foreground">Soak Commands</div>
                {plan.commands.length ? (
                  <div className="space-y-2">
                    {plan.commands.map((command, index) => (
                      <CommandRow
                        key={command}
                        command={command}
                        copied={copiedCommandKey === `soak-plan-${index}`}
                        label={`Soak command ${index + 1}`}
                        onCopy={() => void handleCopyCommand(`soak-plan-${index}`, command)}
                      />
                    ))}
                  </div>
                ) : (
                  <EmptyDetail>No soak commands are available.</EmptyDetail>
                )}
              </div>

              <div className="rounded-md border bg-card px-4 py-3">
                <div className="mb-3 text-[10px] font-medium uppercase text-muted-foreground">Evidence and Blockers</div>
                <div className="flex flex-wrap gap-2">
                  {plan.evidence_refs.map((ref) => <Badge key={`soak-evidence-${ref}`} variant="outline">{ref}</Badge>)}
                  {plan.blockers.map((blocker) => <Badge key={`soak-blocker-${blocker}`} variant="warning">{compactStatus(blocker)}</Badge>)}
                  {!plan.evidence_refs.length && !plan.blockers.length ? <Badge variant="success">clear</Badge> : null}
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function LiveProviderSoakEvidencePanel({ systemStatus }: { systemStatus: SystemStatusResponse | null }) {
  const evidence = systemStatus?.live_provider_soak_evidence ?? null;
  const scenarios = evidence?.scenarios ?? [];
  const [copiedCommandKey, setCopiedCommandKey] = useState("");

  function badgeVariant(status: string): "success" | "warning" | "danger" | "secondary" | "outline" {
    if (status === "passed" || status === "completed" || status === "ready") return "success";
    if (status === "blocked" || status === "warning" || status === "missing") return "warning";
    if (status === "failed" || status === "error") return "danger";
    return status ? "secondary" : "outline";
  }

  async function handleCopyCommand(key: string, command: string) {
    await copyTextToClipboard(command);
    setCopiedCommandKey(key);
  }

  return (
    <section className="rounded-md border bg-background">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Live Provider Soak Evidence</h3>
        </div>
        <div className="flex flex-wrap gap-2">
          {evidence?.contract_version ? <Badge variant="outline">{evidence.contract_version}</Badge> : null}
          <Badge variant={badgeVariant(evidence?.status ?? "")}>{compactStatus(evidence?.status)}</Badge>
          <Badge variant="secondary">{evidence?.summary.scenario_count ?? 0} scenarios</Badge>
          <Badge variant={(evidence?.summary.passed_scenario_count ?? 0) ? "success" : "outline"}>
            {evidence?.summary.passed_scenario_count ?? 0} passed
          </Badge>
          <Badge variant={(evidence?.summary.blocked_scenario_count ?? 0) ? "warning" : "success"}>
            {evidence?.summary.blocked_scenario_count ?? 0} blocked
          </Badge>
          <Badge variant={(evidence?.summary.remaining_live_write_scenario_count ?? 0) ? "warning" : "success"}>
            {evidence?.summary.remaining_live_write_scenario_count ?? 0} live remaining
          </Badge>
          <Badge variant={(evidence?.summary.missing_scenario_count ?? 0) ? "warning" : "success"}>
            {evidence?.summary.missing_scenario_count ?? 0} missing
          </Badge>
        </div>
      </div>
      {!evidence ? (
        <div className="p-4">
          <EmptyDetail>No live provider soak evidence is available.</EmptyDetail>
        </div>
      ) : (
        <>
          <div className="border-b bg-muted/40 px-4 py-2">
            <div className="text-xs text-muted-foreground">{evidence.detail}</div>
            <div className="mt-2 flex flex-wrap gap-2">
              <Badge variant={evidence.summary.mutation_gate_open ? "success" : "warning"}>
                {evidence.summary.mutation_gate_open ? "gate open" : "gate closed"}
              </Badge>
              <Badge variant={evidence.summary.ready_for_release ? "success" : "warning"}>
                {evidence.summary.ready_for_release ? "release proof ready" : "release proof incomplete"}
              </Badge>
              <Badge variant={evidence.summary.operator_action_required ? "warning" : "success"}>
                {evidence.summary.operator_action_required ? "operator action required" : "operator action clear"}
              </Badge>
              {evidence.summary.latest_generated_at ? <Badge variant="outline">{evidence.summary.latest_generated_at}</Badge> : null}
            </div>
            {evidence.summary.operator_action ? (
              <div className="mt-2 text-xs text-muted-foreground">{evidence.summary.operator_action}</div>
            ) : null}
          </div>

          <div className="grid gap-3 p-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
            <div className="rounded-md border bg-card px-4 py-3">
              <div className="mb-3 text-[10px] font-medium uppercase text-muted-foreground">Scenario Evidence</div>
              {scenarios.length ? (
                <div className="grid gap-2">
                  {scenarios.map((scenario: LiveProviderSoakEvidenceScenario) => (
                    <div key={scenario.id} className="rounded-md border bg-background px-3 py-2">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="text-sm font-medium">{scenario.title}</div>
                          <p className="mt-1 text-xs text-muted-foreground">{scenario.detail}</p>
                        </div>
                        <div className="flex shrink-0 flex-wrap justify-end gap-2">
                          {scenario.execution_kind ? <Badge variant="outline">{compactStatus(scenario.execution_kind)}</Badge> : null}
                          <Badge variant={badgeVariant(scenario.expected_state)}>{compactStatus(scenario.expected_state)}</Badge>
                          <Badge variant={badgeVariant(scenario.status)}>{compactStatus(scenario.status)}</Badge>
                        </div>
                      </div>
                      <div className="mt-2 min-w-0 truncate rounded-md border bg-muted/30 px-3 py-2 font-mono text-xs" title={scenario.artifact_path || scenario.artifact_name}>
                        {scenario.artifact_name}
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {scenario.artifact_schema ? <Badge variant="outline">{scenario.artifact_schema}</Badge> : null}
                        {scenario.artifact_status ? <Badge variant={badgeVariant(scenario.artifact_status)}>{compactStatus(scenario.artifact_status)}</Badge> : null}
                        {scenario.generated_at ? <Badge variant="secondary">{scenario.generated_at}</Badge> : null}
                        {scenario.operator_action ? <Badge variant={scenario.operator_action === "covered" ? "success" : "warning"}>{compactStatus(scenario.operator_action)}</Badge> : null}
                      </div>
                      {scenario.command ? (
                        <CommandRow
                          className="mt-2"
                          command={scenario.command}
                          copied={copiedCommandKey === `soak-evidence-scenario-${scenario.id}`}
                          label={`${scenario.title} scenario`}
                          onCopy={() => void handleCopyCommand(`soak-evidence-scenario-${scenario.id}`, scenario.command)}
                        />
                      ) : null}
                      <div className="mt-2 flex flex-wrap gap-2">
                        {scenario.observed_evidence.slice(0, 4).map((item) => (
                          <Badge key={`${scenario.id}-observed-${item}`} variant="success">{compactStatus(item)}</Badge>
                        ))}
                        {scenario.missing_evidence.slice(0, 4).map((item) => (
                          <Badge key={`${scenario.id}-missing-${item}`} variant="warning">{compactStatus(item)}</Badge>
                        ))}
                        {scenario.missing_evidence.length > 4 ? <Badge variant="secondary">+{scenario.missing_evidence.length - 4}</Badge> : null}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyDetail>No live soak evidence scenarios are registered.</EmptyDetail>
              )}
            </div>

            <div className="grid gap-3">
              <div className="rounded-md border bg-card px-4 py-3">
                <div className="mb-3 text-[10px] font-medium uppercase text-muted-foreground">Evidence Commands</div>
                {evidence.commands.length ? (
                  <div className="space-y-2">
                    {evidence.commands.map((command, index) => (
                      <CommandRow
                        key={command}
                        command={command}
                        copied={copiedCommandKey === `soak-evidence-${index}`}
                        label={`Evidence command ${index + 1}`}
                        onCopy={() => void handleCopyCommand(`soak-evidence-${index}`, command)}
                      />
                    ))}
                  </div>
                ) : (
                  <EmptyDetail>No evidence commands are available.</EmptyDetail>
                )}
              </div>

              <div className="rounded-md border bg-card px-4 py-3">
                <div className="mb-3 text-[10px] font-medium uppercase text-muted-foreground">Live Mutation Handoff</div>
                <div className="flex flex-wrap gap-2">
                  <Badge variant={(evidence.summary.live_write_scenario_count ?? 0) ? "warning" : "outline"}>
                    {evidence.summary.live_write_scenario_count ?? 0} live-write scenarios
                  </Badge>
                  <Badge variant={(evidence.summary.passed_non_mutating_scenario_count ?? 0) ? "success" : "outline"}>
                    {evidence.summary.passed_non_mutating_scenario_count ?? 0} non-mutating passed
                  </Badge>
                  <Badge variant={evidence.summary.mutation_gate_open ? "success" : "warning"}>
                    {evidence.summary.mutation_gate_env_var || "AITEAMOS_LIVE_PROVIDER_DOGFOOD"}
                  </Badge>
                </div>
                {evidence.summary.live_write_targets.length ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {evidence.summary.live_write_targets.map((target) => (
                      <Badge key={`live-target-${target}`} variant="outline">{target}</Badge>
                    ))}
                  </div>
                ) : null}
              </div>

              <div className="rounded-md border bg-card px-4 py-3">
                <div className="mb-3 text-[10px] font-medium uppercase text-muted-foreground">Evidence Refs and Blockers</div>
                <div className="flex flex-wrap gap-2">
                  {evidence.evidence_refs.map((ref) => <Badge key={`soak-proof-ref-${ref}`} variant="outline">{ref}</Badge>)}
                  {evidence.blockers.map((blocker) => <Badge key={`soak-proof-blocker-${blocker}`} variant="warning">{compactStatus(blocker)}</Badge>)}
                  {!evidence.evidence_refs.length && !evidence.blockers.length ? <Badge variant="success">clear</Badge> : null}
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function RuntimeExecutorsPanel({
  batchSmokeResult,
  dogfoodResult,
  dogfoodingExecutorId,
  onDogfood,
  onSmokeBatch,
  onSmoke,
  smokeResults,
  smokingBatch,
  smokingExecutorId,
  systemStatus,
}: {
  batchSmokeResult: RuntimeExecutorSmokeBatchResponse | null;
  dogfoodResult: RuntimeExecutorDogfoodResponse | null;
  dogfoodingExecutorId: string;
  onDogfood: (executorId: string) => void;
  onSmokeBatch: () => void;
  onSmoke: (executorId: string) => void;
  smokeResults: Record<string, RuntimeExecutorSmokeResponse>;
  smokingBatch: boolean;
  smokingExecutorId: string;
  systemStatus: SystemStatusResponse | null;
}) {
  const executors = [...(systemStatus?.runtime_executors ?? [])].sort((left, right) => {
    if (left.status !== right.status) return left.status.localeCompare(right.status);
    return left.executor_id.localeCompare(right.executor_id);
  });
  const dogfoodTicketId = stringValue(dogfoodResult?.ticket?.id);
  const dogfoodApprovalId = stringValue(dogfoodResult?.approval?.id);
  const dogfoodRun = asRecord(dogfoodResult?.approved_run);
  const dogfoodRunResult = asRecord(dogfoodRun.result);
  const dogfoodSummary = asRecord(dogfoodResult?.summary_report);
  const dogfoodEvidence = Array.isArray(dogfoodSummary.evidence) ? dogfoodSummary.evidence.map(String).filter(Boolean) : [];
  const dogfoodLearningDelta = asRecord(dogfoodResult?.learning_delta);
  const dogfoodCandidateIds = Array.isArray(dogfoodLearningDelta.memory_candidate_ids)
    ? dogfoodLearningDelta.memory_candidate_ids.map(String).filter(Boolean)
    : [];
  const dogfoodCandidateCount = Number(dogfoodLearningDelta.memory_candidate_count ?? dogfoodCandidateIds.length);

  function badgeVariant(status: string): "success" | "warning" | "danger" | "secondary" {
    if (status === "ready") return "success";
    if (status === "setup_blocked") return "warning";
    if (status === "failed") return "danger";
    return "secondary";
  }

  return (
    <section className="rounded-md border bg-background">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Cpu className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Runtime Executors</h3>
        </div>
        <div className="flex items-center gap-2">
          <Button type="button" size="sm" variant="outline" disabled={smokingBatch || executors.length === 0} onClick={onSmokeBatch}>
            <PlayCircle className="h-3.5 w-3.5" />
            {smokingBatch ? "Running" : "Smoke All"}
          </Button>
          <Badge variant="secondary">{executors.length}</Badge>
        </div>
      </div>
      {batchSmokeResult ? (
        <div className="border-b bg-muted/40 px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={batchSmokeResult.status === "completed" ? "success" : batchSmokeResult.status === "blocked" ? "warning" : "secondary"}>
              {compactStatus(batchSmokeResult.status)}
            </Badge>
            <Badge variant="outline">{String(batchSmokeResult.summary.executor_count ?? 0)} executors</Badge>
            <Badge variant="outline">{String(batchSmokeResult.summary.completed_count ?? 0)} completed</Badge>
            <Badge variant="outline">{String(batchSmokeResult.summary.blocked_count ?? 0)} blocked</Badge>
            <Badge variant="outline">{String(batchSmokeResult.summary.ingested_count ?? 0)} ingested</Badge>
            {batchSmokeResult.ingestion_blocker ? <Badge variant="warning">ingestion blocker</Badge> : null}
          </div>
        </div>
      ) : null}
      {dogfoodResult ? (
        <div className="border-b bg-muted/40 px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={dogfoodResult.status === "completed" ? "success" : dogfoodResult.status === "blocked" ? "warning" : "secondary"}>
              dogfood {compactStatus(dogfoodResult.status)}
            </Badge>
            {dogfoodTicketId ? <Badge variant="outline">Ticket {dogfoodTicketId}</Badge> : null}
            {dogfoodApprovalId ? <Badge variant="outline">Approval {dogfoodApprovalId}</Badge> : null}
            {dogfoodRunResult.status ? <Badge variant="outline">Run {compactStatus(String(dogfoodRunResult.status))}</Badge> : null}
            {dogfoodRun.ingested === true ? <Badge variant="success">ingested</Badge> : null}
            {dogfoodCandidateCount > 0 ? <Badge variant="outline">{dogfoodCandidateCount} candidates</Badge> : null}
            {dogfoodCandidateIds.slice(0, 2).map((candidateId) => (
              <Badge key={candidateId} variant="outline">Candidate {candidateId}</Badge>
            ))}
            {dogfoodEvidence.slice(0, 3).map((ref) => (
              <Badge key={ref} variant="outline">{ref}</Badge>
            ))}
            {dogfoodResult.blockers.length ? <Badge variant="warning">{dogfoodResult.blockers.length} blockers</Badge> : null}
          </div>
        </div>
      ) : null}
      <div className="grid gap-3 p-4 lg:grid-cols-2">
        {executors.length === 0 ? (
          <EmptyDetail>No runtime executors are registered.</EmptyDetail>
        ) : executors.map((executor: RuntimeExecutorStatus) => {
          const visibleCapabilities = executor.capabilities.slice(0, 6);
          const missingEnv = executor.missing_env ?? [];
          const visibleActions = (executor.supported_actions ?? []).slice(0, 4);
          const repoMutationGuard = executor.safety_policy?.repo_mutation_guard ?? [];
          const configEntries = Object.entries(executor.config ?? {}).filter(([, value]) => value !== "" && value !== false && value !== null && value !== undefined);
          const configEnvEntries = Object.entries(executor.config_env ?? {});
          const schemaEntries = Object.entries(executor.expected_output_schema ?? {});
          const supportedModes = executor.delivery?.supported_modes ?? [];
          const smokeDiagnostics = executor.diagnostics?.smoke;
          const dogfoodDiagnostics = executor.diagnostics?.dogfood;
          const smoke = smokeResults[executor.executor_id];
          const smokeResult = asRecord(smoke?.result);
          const smokeErrors = asRecordArray(smokeResult.errors);
          const smokeStatus = stringValue(smokeResult.status) || "-";
          const smokeReport = stringValue(smokeResult.report);
          return (
            <div key={executor.executor_id} className="rounded-md border bg-card px-4 py-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-semibold">{executor.executor_id.replace(/_/g, " ")}</div>
                  <p className="mt-1 text-sm text-muted-foreground">{executor.detail}</p>
                </div>
                <div className="flex items-center gap-2">
                  {dogfoodDiagnostics ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="h-7 px-2 text-xs"
                      disabled={dogfoodingExecutorId === executor.executor_id}
                      onClick={() => onDogfood(executor.executor_id)}
                    >
                      <PlayCircle className="h-3.5 w-3.5" />
                      {dogfoodingExecutorId === executor.executor_id ? "Running" : "Dogfood"}
                    </Button>
                  ) : null}
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="h-7 px-2 text-xs"
                    disabled={smokingExecutorId === executor.executor_id}
                    onClick={() => onSmoke(executor.executor_id)}
                  >
                    <PlayCircle className="h-3.5 w-3.5" />
                    {smokingExecutorId === executor.executor_id ? "Running" : "Smoke"}
                  </Button>
                  <Badge variant={badgeVariant(executor.status)}>{compactStatus(executor.status)}</Badge>
                </div>
              </div>
              {smoke ? (
                <div className="mt-3 rounded-md border bg-background px-3 py-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-[10px] font-medium uppercase text-muted-foreground">Runtime Smoke</div>
                    <Badge variant={smokeStatus === "completed" ? "success" : smokeStatus === "blocked" ? "warning" : "secondary"}>{compactStatus(smokeStatus)}</Badge>
                  </div>
                  {smokeReport ? <p className="mt-2 text-sm text-muted-foreground">{smokeReport}</p> : null}
                  {smoke.ingestion_blocker ? <p className="mt-2 text-xs text-orange-600">{smoke.ingestion_blocker}</p> : null}
                  {smokeErrors.length ? (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {smokeErrors.slice(0, 3).map((item, index) => (
                        <Badge key={`${executor.executor_id}-smoke-error-${index}`} variant="outline">
                          {compactStatus(stringValue(item.reason) || stringValue(item.detail) || "runtime_error")}
                        </Badge>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
              <div className="mt-3 flex flex-wrap gap-2">
                {visibleCapabilities.map((capability) => (
                  <Badge key={capability} variant="outline">{capability}</Badge>
                ))}
                {executor.capabilities.length > visibleCapabilities.length ? (
                  <Badge variant="secondary">+{executor.capabilities.length - visibleCapabilities.length}</Badge>
                ) : null}
              </div>
              {missingEnv.length ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {missingEnv.map((envVar) => (
                    <Badge key={envVar} variant="danger">{envVar}</Badge>
                  ))}
                </div>
              ) : null}
              {executor.delivery ? (
                <div className="mt-3 border-t pt-3">
                  <div className="text-[10px] font-medium uppercase text-muted-foreground">Delivery</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {executor.delivery.configured_mode ? (
                      <Badge variant="secondary">{executor.delivery.configured_mode}</Badge>
                    ) : null}
                    {executor.delivery.prompt_delivery ? (
                      <Badge variant="outline">{executor.delivery.prompt_delivery}</Badge>
                    ) : null}
                    {supportedModes.map((mode) => (
                      <Badge key={mode} variant="outline">{mode}</Badge>
                    ))}
                  </div>
                </div>
              ) : null}
              {visibleActions.length ? (
                <div className="mt-3 border-t pt-3">
                  <div className="text-[10px] font-medium uppercase text-muted-foreground">Actions</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {visibleActions.map((action) => (
                      <Badge key={action} variant="secondary">{action}</Badge>
                    ))}
                  </div>
                </div>
              ) : null}
              {configEntries.length ? (
                <div className="mt-3 border-t pt-3">
                  <div className="text-[10px] font-medium uppercase text-muted-foreground">Config</div>
                  <div className="mt-2 grid gap-1 text-xs text-muted-foreground">
                    {configEntries.slice(0, 5).map(([key, value]) => (
                      <div key={key} className="flex min-w-0 gap-2">
                        <span className="shrink-0 text-foreground">{key.replace(/_/g, " ")}:</span>
                        <span className="truncate" title={String(value)}>{String(value)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
              {configEnvEntries.length ? (
                <div className="mt-3 border-t pt-3">
                  <div className="text-[10px] font-medium uppercase text-muted-foreground">Config Env</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {configEnvEntries.slice(0, 8).map(([key, value]) => (
                      <Badge key={key} variant="outline">{value}</Badge>
                    ))}
                  </div>
                </div>
              ) : null}
              {schemaEntries.length ? (
                <div className="mt-3 border-t pt-3">
                  <div className="text-[10px] font-medium uppercase text-muted-foreground">Result Schema</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {schemaEntries.slice(0, 8).map(([key]) => (
                      <Badge key={key} variant="secondary">{key}</Badge>
                    ))}
                    {schemaEntries.length > 8 ? (
                      <Badge variant="outline">+{schemaEntries.length - 8}</Badge>
                    ) : null}
                  </div>
                </div>
              ) : null}
              {executor.safety_policy ? (
                <div className="mt-3 border-t pt-3">
                  <div className="text-[10px] font-medium uppercase text-muted-foreground">Governance Guard</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {executor.safety_policy.default_mode ? (
                      <Badge variant="secondary">{executor.safety_policy.default_mode}</Badge>
                    ) : null}
                    {repoMutationGuard.map((guard) => (
                      <Badge key={guard} variant="outline">{guard}</Badge>
                    ))}
                    {executor.safety_policy.completion_policy ? (
                      <Badge variant="outline">{executor.safety_policy.completion_policy}</Badge>
                    ) : null}
                  </div>
                </div>
              ) : null}
              {smokeDiagnostics ? (
                <div className="mt-3 border-t pt-3">
                  <div className="text-[10px] font-medium uppercase text-muted-foreground">Diagnostics</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {smokeDiagnostics.method ? <Badge variant="secondary">{smokeDiagnostics.method}</Badge> : null}
                    {smokeDiagnostics.endpoint ? <Badge variant="outline">{smokeDiagnostics.endpoint}</Badge> : null}
                    {smokeDiagnostics.mode ? <Badge variant="outline">{smokeDiagnostics.mode}</Badge> : null}
                    {smokeDiagnostics.dispatch_boundary ? <Badge variant="outline">{smokeDiagnostics.dispatch_boundary}</Badge> : null}
                    <Badge variant={smokeDiagnostics.default_ingest_result ? "warning" : "success"}>
                      {smokeDiagnostics.default_ingest_result ? "default ingest" : "no default ingest"}
                    </Badge>
                    {smokeDiagnostics.ingest_requires_ticket ? <Badge variant="outline">ticket-bound ingest</Badge> : null}
                    {dogfoodDiagnostics?.method ? <Badge variant="secondary">{dogfoodDiagnostics.method}</Badge> : null}
                    {dogfoodDiagnostics?.endpoint ? <Badge variant="outline">{dogfoodDiagnostics.endpoint}</Badge> : null}
                    {dogfoodDiagnostics?.creates_ticket_if_missing ? <Badge variant="outline">dogfood creates Ticket</Badge> : null}
                    {dogfoodDiagnostics?.approval_required ? <Badge variant="outline">dogfood approval</Badge> : null}
                    {(dogfoodDiagnostics?.repo_mutation_guard ?? []).map((guard) => (
                      <Badge key={`${executor.executor_id}-dogfood-${guard}`} variant="outline">{guard}</Badge>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function SystemStatusPage() {
  const [aiEngines, setAiEngines] = useState<ChatAiEngineSettings | null>(null);
  const [capabilityRegistry, setCapabilityRegistry] = useState<CapabilityRegistryResponse | null>(null);
  const [codeRepositoryStatus, setCodeRepositoryStatus] = useState<CodeRepositoryStatus | null>(null);
  const [employees, setEmployees] = useState<ChatEmployeeSummary[]>([]);
  const [knowledge, setKnowledge] = useState<KnowledgeStatusResponse | null>(null);
  const [memory, setMemory] = useState<MemoryStatusResponse | null>(null);
  const [systemStatus, setSystemStatus] = useState<SystemStatusResponse | null>(null);
  const [ticketBackendStatus, setTicketBackendStatus] = useState<TicketBackendStatus | null>(null);
  const [toolConnectorStatus, setToolConnectorStatus] = useState<ToolConnectorRegistryStatus | null>(null);
  const [runtimeSmokeBatchResult, setRuntimeSmokeBatchResult] = useState<RuntimeExecutorSmokeBatchResponse | null>(null);
  const [runtimeSmokeResults, setRuntimeSmokeResults] = useState<Record<string, RuntimeExecutorSmokeResponse>>({});
  const [runtimeDogfoodResult, setRuntimeDogfoodResult] = useState<RuntimeExecutorDogfoodResponse | null>(null);
  const [dogfoodingExecutorId, setDogfoodingExecutorId] = useState("");
  const [smokingBatch, setSmokingBatch] = useState(false);
  const [smokingExecutorId, setSmokingExecutorId] = useState("");
  const [environmentSmokeResult, setEnvironmentSmokeResult] = useState<EnvironmentSmokeResponse | null>(null);
  const [smokingEnvironment, setSmokingEnvironment] = useState(false);
  const [providerSmokeResult, setProviderSmokeResult] = useState<ProviderConformanceSmokeResponse | null>(null);
  const [smokingProviders, setSmokingProviders] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadSystemStatus() {
    setLoading(true);
    setError(null);
    try {
      const [
        loadedAiEngines,
        loadedCapabilities,
        loadedCodeRepositoryStatus,
        loadedEmployees,
        loadedKnowledge,
        loadedMemory,
        loadedSystemStatus,
        loadedTicketBackendStatus,
        loadedToolConnectorStatus,
      ] = await Promise.all([
        getChatAiEngines(),
        getCapabilities(),
        getCodeRepositoryStatus(),
        listChatEmployees(),
        getKnowledgeStatus(),
        getMemoryStatus(),
        getSystemStatus(),
        getTicketBackendStatus(),
        getToolConnectorStatus(),
      ]);
      setAiEngines(loadedAiEngines);
      setCapabilityRegistry(loadedCapabilities);
      setCodeRepositoryStatus(loadedCodeRepositoryStatus);
      setEmployees(loadedEmployees);
      setKnowledge(loadedKnowledge);
      setMemory(loadedMemory);
      setSystemStatus(loadedSystemStatus);
      setTicketBackendStatus(loadedTicketBackendStatus);
      setToolConnectorStatus(loadedToolConnectorStatus);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load system status");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadSystemStatus();
  }, []);

  async function handleRuntimeSmoke(executorId: string) {
    setSmokingExecutorId(executorId);
    setError(null);
    try {
      const response = await runRuntimeExecutorSmoke(executorId, {
        message: "Run non-destructive RuntimeExecutor smoke from System Status.",
        ingest_result: false,
      });
      setRuntimeSmokeResults((current) => ({ ...current, [executorId]: response }));
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to run ${executorId} smoke`);
    } finally {
      setSmokingExecutorId("");
    }
  }

  async function handleRuntimeSmokeBatch() {
    setSmokingBatch(true);
    setError(null);
    try {
      const executorIds = (systemStatus?.runtime_executors ?? []).map((executor) => executor.executor_id);
      const response = await runRuntimeExecutorSmokeBatch({
        message: "Run non-destructive RuntimeExecutor smoke batch from System Status.",
        executor_ids: executorIds,
        ingest_result: false,
      });
      setRuntimeSmokeBatchResult(response);
      setRuntimeSmokeResults((current) => ({
        ...current,
        ...Object.fromEntries(response.results.map((result) => [result.executor_id, result])),
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run runtime smoke batch");
    } finally {
      setSmokingBatch(false);
    }
  }

  async function handleRuntimeDogfood(executorId: string) {
    setDogfoodingExecutorId(executorId);
    setError(null);
    try {
      const response = await runRuntimeExecutorDogfood({
        executor_id: executorId,
        message: "Dogfood approved external runtime mutation from System Status.",
        employee_id: "alex",
        reviewer_employee_id: "clara",
        create_ticket_if_missing: true,
      });
      setRuntimeDogfoodResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to run ${executorId} dogfood harness`);
    } finally {
      setDogfoodingExecutorId("");
    }
  }

  async function handleProviderSmoke(includeExternal = false) {
    setSmokingProviders(true);
    setError(null);
    try {
      const response = await getProviderConformanceSmoke(includeExternal);
      setProviderSmokeResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run provider conformance smoke");
    } finally {
      setSmokingProviders(false);
    }
  }

  async function handleEnvironmentSmoke(includeExternal = false) {
    setSmokingEnvironment(true);
    setError(null);
    try {
      const response = await getEnvironmentSmoke(includeExternal);
      setEnvironmentSmokeResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run environment smoke");
    } finally {
      setSmokingEnvironment(false);
    }
  }

  if (loading) return <LoadingState />;

  return (
    <section className="space-y-3">
      <div className="rounded-md border bg-background">
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div>
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold">System Status</h3>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">Read-only system summary and environment variable health.</p>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={() => void loadSystemStatus()}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
        </div>

        {error && (
          <div className="border-t p-4">
            <ErrorState message={error} onRetry={loadSystemStatus} />
          </div>
        )}
      </div>

      <SystemSummary
        aiEngines={aiEngines}
        capabilityRegistry={capabilityRegistry}
        codeRepositoryStatus={codeRepositoryStatus}
        employees={employees}
        knowledge={knowledge}
        memory={memory}
        systemStatus={systemStatus}
        ticketBackendStatus={ticketBackendStatus}
        toolConnectorStatus={toolConnectorStatus}
      />
      <PlanV8ReadinessPanel systemStatus={systemStatus} />
      <SchemaRegistryPanel systemStatus={systemStatus} />
      <PlanV8ArtifactEvidencePanel systemStatus={systemStatus} />
      <ReleaseHygienePanel systemStatus={systemStatus} />
      <LiveProviderDogfoodReadinessPanel systemStatus={systemStatus} />
      <LiveProviderSoakPlanPanel systemStatus={systemStatus} />
      <LiveProviderSoakEvidencePanel systemStatus={systemStatus} />
      <RuntimeExecutorsPanel
        batchSmokeResult={runtimeSmokeBatchResult}
        dogfoodResult={runtimeDogfoodResult}
        dogfoodingExecutorId={dogfoodingExecutorId}
        onDogfood={(executorId) => void handleRuntimeDogfood(executorId)}
        onSmokeBatch={() => void handleRuntimeSmokeBatch()}
        onSmoke={(executorId) => void handleRuntimeSmoke(executorId)}
        smokeResults={runtimeSmokeResults}
        smokingBatch={smokingBatch}
        smokingExecutorId={smokingExecutorId}
        systemStatus={systemStatus}
      />
      <EnvironmentSmokePanel
        onSmoke={(includeExternal) => void handleEnvironmentSmoke(includeExternal)}
        smokeResult={environmentSmokeResult}
        smoking={smokingEnvironment}
      />
      <ProviderConformancePanel
        onSmoke={(includeExternal) => void handleProviderSmoke(includeExternal)}
        smokeResult={providerSmokeResult}
        smoking={smokingProviders}
        systemStatus={systemStatus}
      />
      <SystemStatusBlockersPanel systemStatus={systemStatus} />
      <SystemStatusSecretsPanel systemStatus={systemStatus} />
    </section>
  );
}
