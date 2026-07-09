import { Badge } from "../../../components/ui/badge";

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function asRecordArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(asRecord).filter((item) => Object.keys(item).length > 0) : [];
}

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

function InfoMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border bg-card px-2 py-1">
      <div className="text-[10px] uppercase text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-xs font-medium">{value}</div>
    </div>
  );
}

function hintStatusVariant(status: string): "warning" | "danger" | "outline" {
  if (status === "superseded") return "warning";
  if (status === "conflicted") return "danger";
  return "outline";
}

export function ScopedContextPanel({
  contextExclusions,
  scopedContext,
  setupBlockers,
  universalContext,
  universalProvenance,
}: {
  contextExclusions: string[];
  scopedContext: Record<string, unknown>;
  setupBlockers: Record<string, unknown>[];
  universalContext: Record<string, unknown>;
  universalProvenance: Record<string, unknown>[];
}) {
  if (Object.keys(scopedContext).length === 0) return null;

  const universalSummary = asRecord(universalContext.summary);
  const backendContext = asRecord(universalContext.backend_context);
  const ticketBackend = asRecord(backendContext.ticket_backend);
  const employeeContext = asRecord(universalContext.employee_context);
  const workHistory = asRecord(employeeContext.work_history);
  const workHistorySummary = asRecord(workHistory.summary);
  const assetContext = asRecord(universalContext.asset_context);
  const relationshipHints = asRecordArray(assetContext.relationship_hints);
  const universalText = (key: string) => metadataText(universalContext[key] ?? universalSummary[key]);

  return (
    <div className="rounded-md border bg-background/60 p-2">
      <div className="mb-1 text-[10px] font-medium uppercase text-muted-foreground">Scoped Context</div>
      <div className="grid grid-cols-2 gap-2 text-[11px]">
        <InfoMetric label="Assets" value={metadataText(scopedContext.relevant_asset_count)} />
        <InfoMetric label="Recalled" value={metadataText(scopedContext.recalled_memory_count)} />
        <InfoMetric label="Evidence" value={metadataText(scopedContext.prior_evidence_count)} />
        <InfoMetric label="Setup blockers" value={metadataText(scopedContext.setup_blocker_count)} />
      </div>

      {contextExclusions.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {contextExclusions.slice(0, 4).map((item) => (
            <Badge key={item} variant="secondary" className="px-1.5 text-[10px]">{item}</Badge>
          ))}
        </div>
      )}

      {Object.keys(universalContext).length > 0 && (
        <div className="mt-2 rounded border bg-card px-2 py-1.5">
          <div className="mb-1 flex min-w-0 items-center justify-between gap-2">
            <span className="text-[10px] font-medium uppercase text-muted-foreground">Universal Context</span>
            <Badge variant="outline" className="max-w-[8rem] px-1.5 text-[10px]">
              <span className="truncate">{metadataText(universalContext.version)}</span>
            </Badge>
          </div>
          <div className="grid grid-cols-2 gap-2 text-[11px]">
            <InfoMetric label="Related tickets" value={universalText("related_ticket_count")} />
            <InfoMetric label="Assets" value={universalText("relevant_asset_count")} />
            <InfoMetric label="Memory" value={universalText("recalled_memory_count")} />
            <InfoMetric label="Blockers" value={universalText("setup_blocker_count")} />
          </div>
          <div className="mt-2 grid gap-1 text-[10px]">
            <div className="flex justify-between gap-2">
              <span className="text-muted-foreground">Employee</span>
              <span className="truncate text-right" title={universalText("employee_id")}>
                {universalText("employee_id")}
              </span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-muted-foreground">Ticket</span>
              <span className="truncate text-right" title={universalText("ticket_id")}>
                {universalText("ticket_id")}
              </span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-muted-foreground">Ticket backend</span>
              <span className="truncate text-right" title={metadataText(universalContext.ticket_backend_status ?? ticketBackend.status)}>
                {metadataText(universalContext.ticket_backend_status ?? ticketBackend.status)}
              </span>
            </div>
          </div>

          {Object.keys(workHistorySummary).length > 0 && (
            <div className="mt-2">
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="text-[10px] uppercase text-muted-foreground">Work History</span>
                <Badge variant="outline" className="px-1.5 text-[10px]">
                  {metadataText(workHistorySummary.source)}
                </Badge>
              </div>
              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <InfoMetric label="Current tickets" value={metadataText(workHistorySummary.current_ticket_count)} />
                <InfoMetric label="Reports" value={metadataText(workHistorySummary.report_count)} />
                <InfoMetric label="Runtime runs" value={metadataText(workHistorySummary.runtime_run_count)} />
                <InfoMetric label="Feedback" value={metadataText(workHistorySummary.quality_feedback_count)} />
              </div>
            </div>
          )}

          {relationshipHints.length > 0 && (
            <div className="mt-2">
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="text-[10px] uppercase text-muted-foreground">Asset Relationship Hints</span>
                <Badge variant="outline" className="px-1.5 text-[10px]">{relationshipHints.length}</Badge>
              </div>
              <div className="space-y-1">
                {relationshipHints.slice(0, 4).map((hint, index) => {
                  const sourceAssetId = metadataLabel(hint, ["source_asset_id"], `source-${index + 1}`);
                  const targetAssetId = metadataLabel(hint, ["target_asset_id", "asset_id"], `asset-${index + 1}`);
                  const relationshipType = metadataLabel(hint, ["relationship_type"], "relationship");
                  const status = metadataLabel(hint, ["status"], "excluded");
                  const reason = metadataText(hint.exclusion_reason);
                  return (
                    <div key={`${sourceAssetId}-${relationshipType}-${targetAssetId}-${index}`} className="min-w-0 rounded border bg-background/60 px-2 py-1">
                      <div className="flex min-w-0 items-center justify-between gap-2">
                        <span className="truncate text-[10px] font-medium" title={targetAssetId}>
                          {targetAssetId}
                        </span>
                        <Badge variant={hintStatusVariant(status)} className="shrink-0 px-1.5 text-[10px]">
                          {status}
                        </Badge>
                      </div>
                      <div className="mt-0.5 flex min-w-0 flex-wrap gap-x-2 gap-y-1 text-[10px] text-muted-foreground">
                        <span className="truncate" title={sourceAssetId}>By: {sourceAssetId}</span>
                        <span>{relationshipType}</span>
                        <span>Confidence: {metadataText(hint.source_confidence)}</span>
                      </div>
                      <div className="mt-0.5 truncate text-[10px] text-muted-foreground" title={reason}>
                        {reason}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {universalProvenance.length > 0 && (
            <div className="mt-2">
              <div className="mb-1 text-[10px] uppercase text-muted-foreground">Context Provenance</div>
              <div className="space-y-1">
                {universalProvenance.slice(0, 5).map((item, index) => {
                  const kind = metadataLabel(item, ["kind", "source_kind"], `context-${index + 1}`);
                  const sourceKind = metadataLabel(item, ["source_kind"], "source");
                  const sourceRef = metadataLabel(item, ["source_ref", "scope_ref"], "-");
                  const scopeKind = metadataLabel(item, ["scope_kind"], "scope");
                  const scopeRef = metadataLabel(item, ["scope_ref"], "-");
                  return (
                    <div key={`${kind}-${sourceKind}-${sourceRef}-${index}`} className="min-w-0 rounded border bg-background/60 px-2 py-1">
                      <div className="truncate text-[10px] font-medium" title={`${kind} ${sourceKind}:${sourceRef}`}>
                        {kind}
                      </div>
                      <div className="mt-0.5 truncate text-[10px] text-muted-foreground" title={`${sourceKind}:${sourceRef}`}>
                        {sourceKind}:{sourceRef}
                      </div>
                      <div className="mt-0.5 truncate text-[10px] text-muted-foreground" title={`${scopeKind}:${scopeRef}`}>
                        {scopeKind}:{scopeRef}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {setupBlockers.length > 0 && (
        <div className="mt-2 space-y-1">
          {setupBlockers.slice(0, 3).map((blocker, index) => {
            const blockerLabel = metadataLabel(blocker, ["reason", "id", "status"], `blocker-${index + 1}`);
            return (
              <div key={`${blockerLabel}-${index}`} className="rounded border bg-background/60 px-2 py-1">
                <div className="truncate text-[10px] font-medium">
                  {blockerLabel}
                </div>
                <div className="mt-0.5 truncate text-[10px] text-muted-foreground" title={metadataText(blocker.detail)}>
                  {metadataText(blocker.detail)}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
