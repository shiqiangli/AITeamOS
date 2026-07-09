import { GitBranch } from "lucide-react";
import { Badge } from "../../../components/ui/badge";
import type { WorkbenchSnapshot } from "../runtime/workbenchState";
import { hasWorkbenchSnapshot } from "../runtime/workbenchState";

function metadataText(value: unknown): string {
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  return typeof value === "string" && value.trim() ? value : "-";
}

function firstMetadataValue(values: unknown[]): string {
  for (const value of values) {
    const text = metadataText(value);
    if (text !== "-") return text;
  }
  return "";
}

function InfoMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border bg-card px-2 py-1">
      <div className="text-[10px] uppercase text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-xs font-medium">{value}</div>
    </div>
  );
}

export function WorkbenchSnapshotPanel({ snapshot }: { snapshot: WorkbenchSnapshot | null }) {
  if (!hasWorkbenchSnapshot(snapshot)) return null;
  const activeTicket = snapshot.activeTicket;
  const employeeIdentity = Object.keys(snapshot.employeeIdentity).length > 0
    ? snapshot.employeeIdentity
    : snapshot.selectedEmployee;
  const runtimeStatus = snapshot.runtimeStatus;
  const handoffSummary = snapshot.handoffSummary;
  const handoffDecision = snapshot.handoffDecision;
  const primaryHandoffRef = snapshot.ticketHandoffRefs[0] ?? {};
  const ticketId = firstMetadataValue([
    activeTicket.id,
    activeTicket.ticket_id,
    snapshot.ticketBinding.ticket_id,
    snapshot.ticketBinding.id,
    handoffSummary.ticket_id,
  ]);
  const employeeName = firstMetadataValue([
    employeeIdentity.display_name,
    employeeIdentity.name,
    employeeIdentity.id,
  ]);
  const runtimeLabel = firstMetadataValue([
    runtimeStatus.current_node,
    runtimeStatus.status,
    runtimeStatus.graph,
  ]);
  const graphLabel = metadataText(runtimeStatus.graph);
  const handoffStatus = firstMetadataValue([handoffSummary.status, runtimeStatus.handoff_status]);
  const handoffTarget = firstMetadataValue([
    handoffSummary.to_employee_id,
    handoffDecision.target_employee_id,
    primaryHandoffRef.to_employee_id,
  ]);
  const handoffSource = firstMetadataValue([handoffSummary.from_employee_id, handoffDecision.from_employee_id]);
  const handoffReason = firstMetadataValue([handoffDecision.reason, handoffSummary.reason]);
  const handoffReportRef = firstMetadataValue([primaryHandoffRef.report_id, primaryHandoffRef.ref]);
  const hasHandoff = Boolean(handoffStatus || handoffTarget || snapshot.ticketHandoffRefs.length > 0);

  return (
    <section className="border-b p-3">
      <div className="mb-2 flex items-center gap-1.5">
        <GitBranch className="h-3.5 w-3.5 text-muted-foreground" />
        <h3 className="text-xs font-semibold">Workbench State</h3>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <InfoMetric label="Ticket" value={ticketId || "-"} />
        <InfoMetric label="Employee" value={employeeName || "-"} />
        <InfoMetric label="Assets" value={String(snapshot.linkedAssets.length)} />
        <InfoMetric label="Memory" value={String(snapshot.recalledMemoryRefs.length)} />
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        {graphLabel !== "-" && <Badge variant="outline" className="px-1.5 text-[10px]">{graphLabel}</Badge>}
        {runtimeLabel && <Badge variant="secondary" className="px-1.5 text-[10px]">{runtimeLabel}</Badge>}
        {hasHandoff && (
          <Badge variant="warning" className="px-1.5 text-[10px]">
            handoff {handoffStatus || "proposed"}
          </Badge>
        )}
        {snapshot.approvalRequests.length > 0 && (
          <Badge variant="warning" className="px-1.5 text-[10px]">
            {snapshot.approvalRequests.length} approvals
          </Badge>
        )}
        {snapshot.providerBlockers.length > 0 && (
          <Badge variant="warning" className="px-1.5 text-[10px]">
            {snapshot.providerBlockers.length} blockers
          </Badge>
        )}
        {snapshot.assetCandidates.length > 0 && (
          <Badge variant="outline" className="px-1.5 text-[10px]">
            {snapshot.assetCandidates.length} candidates
          </Badge>
        )}
      </div>
      {hasHandoff && (
        <div className="mt-2 rounded-md border bg-background/60 p-2">
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="text-[10px] font-medium uppercase text-muted-foreground">Employee Handoff</span>
            <Badge variant="outline" className="px-1.5 text-[10px]">
              {handoffStatus || "proposed"}
            </Badge>
          </div>
          <div className="space-y-1 text-[10px] text-muted-foreground">
            <div className="flex justify-between gap-2">
              <span>Route</span>
              <span className="truncate text-right" title={`${handoffSource || "-"} -> ${handoffTarget || "-"}`}>
                {handoffSource || "-"} -&gt; {handoffTarget || "-"}
              </span>
            </div>
            {handoffReportRef && (
              <div className="flex justify-between gap-2">
                <span>Report</span>
                <span className="truncate text-right" title={handoffReportRef}>{handoffReportRef}</span>
              </div>
            )}
            {handoffReason && (
              <p className="line-clamp-3 leading-4 text-foreground" title={handoffReason}>
                {handoffReason}
              </p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
