import { type ReactNode, useEffect, useState } from "react";
import { Activity, KeyRound, RefreshCw } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { ErrorState, LoadingState } from "../../components/shared";
import { getCapabilities, type CapabilityRegistryResponse } from "../../api/capabilities";
import { getChatAiEngines, listChatEmployees, type ChatAiEngineSettings, type ChatEmployeeSummary } from "../../api/chat";
import { getKnowledgeStatus, type KnowledgeStatusResponse } from "../../api/knowledge";
import { getMemoryStatus, type MemoryStatusResponse } from "../../api/memory";
import { getCodeRepositoryStatus, type CodeRepositoryStatus } from "../../api/repositories";
import { getSystemStatus, type SystemStatusResponse, type SystemStatusSecretItem } from "../../api/systemStatus";
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
        <SummaryMetric label="Memory Backend" value={compactStatus(memory?.backend.status)} tone={memory?.backend.status === "ready" ? "ok" : "warn"} />
        <SummaryMetric label="Tools Ready" value={readyTools} tone={readyTools > 0 ? "ok" : "warn"} />
        <SummaryMetric label="Repos Ready" value={`${codeRepositoryStatus?.ready_count ?? 0}/${codeRepositoryStatus?.repository_count ?? 0}`} tone={(codeRepositoryStatus?.ready_count ?? 0) > 0 ? "ok" : "warn"} />
        <SummaryMetric label="Review Queue" value={knowledge?.review_queue_count ?? 0} tone={(knowledge?.review_queue_count ?? 0) > 0 ? "warn" : undefined} />
        <SummaryMetric label="Secrets" value={`${configuredSecrets}/${secretItems.length}`} tone={missingSecrets === 0 ? "ok" : "warn"} />
      </div>
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
            {blocker.setup_required.length ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {blocker.setup_required.map((item) => (
                  <Badge key={item} variant="outline">{item}</Badge>
                ))}
              </div>
            ) : null}
          </div>
        ))}
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
      <SystemStatusBlockersPanel systemStatus={systemStatus} />
      <SystemStatusSecretsPanel systemStatus={systemStatus} />
    </section>
  );
}
