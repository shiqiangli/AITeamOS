import { useCallback, useEffect, useState } from "react";
import { Wrench, RefreshCw, MessageSquare } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { ErrorState, LoadingState, Status, navigateTo } from "../../components/shared";
import { ResizableDetailLayout } from "../../components/resizable-layout";
import { getCapabilities, type CapabilityRecord, type CapabilityRegistryResponse } from "../../api/capabilities";
import { cn } from "@/lib/utils";

function capabilityGroupLabel(kind: string): string {
  if (kind === "local_tool") return "Local Tools";
  if (kind === "mcp_connector") return "MCP Connectors";
  if (kind === "mcp_capability") return "MCP Capabilities";
  if (kind === "agent_executor") return "Agent Executors";
  return kind;
}

type CapabilityView = "all" | "tools" | "connectors";

function groupedCapabilities(capabilities: CapabilityRecord[], view: CapabilityView): [string, CapabilityRecord[]][] {
  const orderByView: Record<CapabilityView, string[]> = {
    all: ["local_tool", "mcp_connector", "mcp_capability", "agent_executor"],
    tools: ["local_tool", "mcp_capability", "agent_executor"],
    connectors: ["mcp_connector"],
  };
  const order = orderByView[view];
  const groups = new Map<string, CapabilityRecord[]>();
  for (const capability of capabilities.filter((item) => order.includes(item.kind))) {
    groups.set(capability.kind, [...(groups.get(capability.kind) ?? []), capability]);
  }
  return order
    .filter((kind) => groups.has(kind))
    .map((kind) => [kind, groups.get(kind) ?? []]);
}

function statusVariant(status: string): "default" | "secondary" | "warning" | "success" | "danger" | "outline" {
  if (status === "ready" || status === "configured" || status === "active" || status === "available" || status === "local") {
    return "success";
  }
  if (status === "planned" || status === "held") return "warning";
  if (status === "missing" || status === "failed" || status === "invalid") return "danger";
  return "secondary";
}

function titleForView(view: CapabilityView): string {
  if (view === "tools") return "Tools";
  if (view === "connectors") return "Connectors";
  return "Capabilities";
}

function descriptionForView(view: CapabilityView): string {
  if (view === "tools") return "Executable actions available to Clara and employees.";
  if (view === "connectors") return "External capability sources such as MCP connectors and Plane.";
  return "Capability registry for tools, connectors, MCP capabilities, and agent executors.";
}

export function CapabilitiesPage({ view = "all" }: { view?: CapabilityView }) {
  const [registry, setRegistry] = useState<CapabilityRegistryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadCapabilities = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRegistry(await getCapabilities());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load capabilities");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCapabilities();
  }, [loadCapabilities]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={loadCapabilities} />;

  const capabilities = registry?.capabilities ?? [];
  const groups = groupedCapabilities(capabilities, view);
  const pageTitle = titleForView(view);
  const pageDescription = descriptionForView(view);
  const modelEntries = [
    ["Knowledge", registry?.model.knowledge ?? "Facts and history that ground reasoning."],
    ["Skill", registry?.model.skill ?? "Employee methods and workflows."],
    ["Tool", registry?.model.tool ?? "Executable deterministic actions."],
    ["MCP", registry?.model.mcp ?? "External tool and resource connector layer."],
    ["Executor", registry?.model.executor ?? "Mature agent runtime used by employees."],
  ];

  return (
    <ResizableDetailLayout
      id="aiteamos-capabilities-layout"
      main={(
        <section className="space-y-4">
        {/* Header */}
        <div className="rounded-md border bg-background">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
            <div className="flex items-center gap-2">
              <Wrench className="h-4 w-4 text-muted-foreground" />
              <div>
                <h3 className="text-sm font-semibold">{pageTitle}</h3>
                <p className="text-xs text-muted-foreground">{pageDescription}</p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" size="sm" onClick={() => void loadCapabilities()}>
                <RefreshCw className="h-4 w-4" />
                Refresh
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => navigateTo("chat")}>
                <MessageSquare className="h-4 w-4" />
                Chat
              </Button>
            </div>
          </div>
          {/* Capability Model */}
          {view === "all" && (
            <>
              <div className="border-b px-4 py-3">
                <h3 className="text-sm font-semibold">Capability Model</h3>
              </div>
              <div className="grid gap-3 p-4 md:grid-cols-5">
                {modelEntries.map(([name, description]) => (
                  <div key={name} className="rounded-md border px-3 py-3">
                    <div className="text-sm font-semibold">{name}</div>
                    <div className="mt-1 text-xs leading-5 text-muted-foreground">{description}</div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Grouped capability lists */}
        {groups.map(([kind, items]) => (
          <section key={kind} className="rounded-md border bg-background">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
              <h3 className="text-sm font-semibold">{capabilityGroupLabel(kind)}</h3>
              <Badge variant="secondary">{items.length}</Badge>
            </div>
            <div className="divide-y">
              {items.map((capability) => (
                <div key={capability.id} className="grid gap-3 px-4 py-3 text-sm xl:grid-cols-[minmax(0,1fr)_14rem]">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{capability.name}</span>
                      <Badge variant="outline">{capability.domain}</Badge>
                      <Badge variant={statusVariant(capability.status)}>{capability.status}</Badge>
                      {!capability.enabled && capability.kind !== "agent_executor" && <Badge variant="secondary">disabled</Badge>}
                    </div>
                    <div className="mt-1 text-muted-foreground">{capability.description}</div>
                    {capability.boundary && (
                      <div className="mt-2 rounded-md bg-muted px-3 py-2 text-xs leading-5 text-muted-foreground">
                        {capability.boundary}
                      </div>
                    )}
                    <div className="mt-2 flex flex-wrap gap-2">
                      {capability.permissions.slice(0, 5).map((permission) => (
                        <Badge key={permission} variant="outline">{permission}</Badge>
                      ))}
                      {capability.required_settings.slice(0, 4).map((setting) => (
                        <Badge key={setting} variant="secondary">{setting}</Badge>
                      ))}
                    </div>
                  </div>
                  <aside className="min-w-0 space-y-2 text-xs text-muted-foreground">
                    <div>
                      <div className="uppercase">Source</div>
                      <div className="truncate font-medium text-foreground" title={capability.source}>{capability.source}</div>
                    </div>
                    <div>
                      <div className="uppercase">Owner scope</div>
                      <div className="truncate font-medium text-foreground" title={capability.owner_scope}>{capability.owner_scope || "-"}</div>
                    </div>
                    {capability.deep_link && (
                      <a className="inline-flex text-sm font-medium text-primary hover:underline" href={capability.deep_link}>
                        Open surface
                      </a>
                    )}
                  </aside>
                </div>
              ))}
            </div>
          </section>
        ))}
        </section>
      )}

      detail={(
        <aside className="space-y-4">
        <section className="rounded-md border bg-background p-4">
            <div className="mb-3 flex items-center gap-2">
              <Wrench className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold">{pageTitle} Status</h3>
            </div>
          <div className="space-y-3">
            <Status label="Capabilities" value={registry?.status.capability_count ?? capabilities.length} />
            <Status label="Ready" value={registry?.status.ready_count ?? 0} tone={(registry?.status.ready_count ?? 0) > 0 ? "ok" : "warn"} />
            <Status label="Local tools" value={registry?.status.local_tool_count ?? 0} />
            <Status label="MCP capabilities" value={registry?.status.mcp_capability_count ?? 0} />
          </div>
        </section>

        <section className="rounded-md border bg-background p-4">
          <div className="mb-3 text-sm font-semibold">Files</div>
          <div className="space-y-3">
            {Object.entries(registry?.status.saved_paths ?? {}).map(([key, value]) => (
              <div key={key} className="min-w-0">
                <div className="text-xs uppercase text-muted-foreground">{key}</div>
                <div className="truncate text-sm font-medium" title={value}>{value}</div>
              </div>
            ))}
          </div>
        </section>
        </aside>
      )}
    />
  );
}
