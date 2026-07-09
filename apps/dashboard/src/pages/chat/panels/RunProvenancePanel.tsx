import { Badge } from "../../../components/ui/badge";

function metadataText(value: unknown): string {
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  return typeof value === "string" && value.trim() ? value : "-";
}

function metadataLabel(record: Record<string, unknown>, keys: string[], fallback: string): string {
  for (const key of keys) {
    const value = metadataText(record[key]);
    if (value !== "-") return value;
  }
  return fallback;
}

function statusVariant(status: string): "success" | "warning" | "outline" {
  if (status === "completed") return "success";
  if (status === "blocked") return "warning";
  return "outline";
}

export function RunProvenancePanel({
  commands,
  graphitiEpisodeRefs,
  learningSummary,
  providerRefs,
  recalledAssets,
  recalledMemoryRefs,
  summary,
  nextGuidance,
}: {
  commands: Record<string, unknown>[];
  graphitiEpisodeRefs: Record<string, unknown>[];
  learningSummary: Record<string, unknown>;
  providerRefs: Record<string, unknown>[];
  recalledAssets: Record<string, unknown>[];
  recalledMemoryRefs: Record<string, unknown>[];
  summary: string;
  nextGuidance: string[];
}) {
  return (
    <>
      <div>
        <div className="mb-1 text-[10px] uppercase text-muted-foreground">Commands</div>
        <div className="flex flex-wrap gap-1">
          {commands.length ? commands.map((command, index) => {
            const commandId = metadataText(command.id);
            const commandStatus = metadataText(command.status);
            return (
              <Badge
                key={`${commandId}-${index}`}
                variant={statusVariant(commandStatus)}
                className="max-w-full px-1.5 text-[10px]"
                title={commandId}
              >
                <span className="truncate">{commandId}:{commandStatus}</span>
              </Badge>
            );
          }) : (
            <Badge variant="outline" className="px-1.5 text-[10px]">none</Badge>
          )}
        </div>
      </div>

      <div>
        <div className="mb-1 text-[10px] uppercase text-muted-foreground">Recalled Memories</div>
        <div className="space-y-1">
          {recalledMemoryRefs.length ? recalledMemoryRefs.slice(0, 4).map((memoryRef, index) => {
            const memoryId = metadataLabel(memoryRef, ["memory_id", "asset_id"], `memory-${index + 1}`);
            const source = metadataLabel(memoryRef, ["source_ticket_id", "source_ref", "scope"], "-");
            const graphiti = metadataText(memoryRef.graphiti_episode_id) !== "-" || memoryRef.graphiti_recalled === true;
            return (
              <div key={`${memoryId}-${index}`} className="rounded border bg-background/60 px-2 py-1">
                <div className="truncate text-[11px] font-medium" title={memoryId}>
                  {memoryId}
                </div>
                <div className="mt-0.5 flex flex-wrap gap-1 text-[10px] text-muted-foreground">
                  <span>Graphiti: {graphiti ? "yes" : "no"}</span>
                  <span className="truncate">Source: {source}</span>
                </div>
              </div>
            );
          }) : (
            <Badge variant="outline" className="px-1.5 text-[10px]">none</Badge>
          )}
          {recalledMemoryRefs.length > 4 && (
            <Badge variant="outline" className="px-1.5 text-[10px]">+{recalledMemoryRefs.length - 4}</Badge>
          )}
        </div>
      </div>

      {(graphitiEpisodeRefs.length > 0 || providerRefs.length > 0) && (
        <div className="grid gap-2 sm:grid-cols-2">
          {graphitiEpisodeRefs.length > 0 && (
            <div>
              <div className="mb-1 text-[10px] uppercase text-muted-foreground">Graphiti Episodes</div>
              <div className="flex flex-wrap gap-1">
                {graphitiEpisodeRefs.slice(0, 3).map((episodeRef, index) => (
                  <Badge
                    key={`${metadataText(episodeRef.graphiti_episode_id)}-${index}`}
                    variant="secondary"
                    className="max-w-full px-1.5 text-[10px]"
                    title={metadataText(episodeRef.graphiti_episode_id)}
                  >
                    <span className="truncate">{metadataText(episodeRef.graphiti_episode_id)}</span>
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {providerRefs.length > 0 && (
            <div>
              <div className="mb-1 text-[10px] uppercase text-muted-foreground">Provider Refs</div>
              <div className="flex flex-wrap gap-1">
                {providerRefs.slice(0, 3).map((providerRef, index) => {
                  const providerRefId = metadataLabel(providerRef, ["provider_ref", "provider_id", "external_id"], `provider-${index + 1}`);
                  const providerName = metadataLabel(providerRef, ["provider", "backend", "source"], "provider");
                  return (
                    <Badge
                      key={`${providerRefId}-${index}`}
                      variant="outline"
                      className="max-w-full px-1.5 text-[10px]"
                      title={providerRefId}
                    >
                      <span className="truncate">{providerName}</span>
                    </Badge>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {summary !== "-" && (
        <div className="rounded-md border bg-background/60 p-2">
          <div className="mb-1 text-[10px] font-medium uppercase text-muted-foreground">Learning</div>
          <p className="text-[11px] leading-5 text-muted-foreground">{summary}</p>
          <div className="mt-2 flex flex-wrap gap-1">
            <Badge variant="secondary" className="px-1.5 text-[10px]">
              {recalledAssets.length} recalled
            </Badge>
            <Badge variant="outline" className="px-1.5 text-[10px]">
              {String(learningSummary.new_candidate_count ?? 0)} candidates
            </Badge>
          </div>
          {nextGuidance.length > 0 && (
            <div className="mt-2 space-y-1">
              {nextGuidance.slice(0, 2).map((item) => (
                <div key={item} className="text-[10px] leading-4 text-muted-foreground">{item}</div>
              ))}
            </div>
          )}
        </div>
      )}
    </>
  );
}
