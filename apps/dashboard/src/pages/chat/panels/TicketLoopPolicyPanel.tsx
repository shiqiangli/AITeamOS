import { GitBranch, Route } from "lucide-react";
import { Badge } from "../../../components/ui/badge";

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function asRecordArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(asRecord).filter((item) => Object.keys(item).length > 0) : [];
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter((item) => item.trim()) : [];
}

function metadataText(value: unknown): string {
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  return typeof value === "string" && value.trim() ? value : "-";
}

function metadataNumber(value: unknown): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

function metadataLabel(record: Record<string, unknown>, keys: string[], fallback: string): string {
  for (const key of keys) {
    const value = metadataText(record[key]);
    if (value !== "-") return value;
  }
  return fallback;
}

function statusVariant(status: string): "success" | "warning" | "danger" | "secondary" | "outline" {
  if (["completed", "queued", "recorded", "escalated"].includes(status)) return "success";
  if (["blocked", "failed", "error"].includes(status)) return "danger";
  if (["waiting", "pending", "proposed"].some((prefix) => status.startsWith(prefix))) return "warning";
  if (status) return "secondary";
  return "outline";
}

function policyRefLabel(ref: Record<string, unknown>): string {
  const kind = metadataText(ref.kind);
  if (kind === "ticket_handoff") {
    return `handoff:${metadataLabel(ref, ["to_employee_id", "to_role"], "-")}`;
  }
  if (kind === "ticket_loop_queue") return `queue:${metadataText(ref.queue_id)}`;
  if (kind === "ticket_loop_run") return `run:${metadataText(ref.run_id)}`;
  if (kind === "ticket_report") return `report:${metadataText(ref.report_id)}`;
  return `${kind}:${metadataLabel(ref, ["ref", "id", "source_ref"], "-")}`;
}

function actionRefs(action: Record<string, unknown>): string[] {
  const refs = [
    ...asStringArray(action.queue_ids).map((id) => `queue:${id}`),
    ...asStringArray(action.run_ids).map((id) => `run:${id}`),
    ...asStringArray(action.candidate_ids).map((id) => `candidate:${id}`),
  ];
  const reportId = metadataText(action.report_id);
  if (reportId !== "-") refs.push(`report:${reportId}`);
  for (const handoffRef of asRecordArray(action.handoff_refs)) {
    refs.push(`handoff:${metadataLabel(handoffRef, ["to_employee_id", "to_role"], "-")}`);
  }
  return refs;
}

export function TicketLoopPolicyPanel({
  actions,
  decision,
  policyRefs,
  primaryTicketId,
}: {
  actions: Record<string, unknown>[];
  decision: Record<string, unknown>;
  policyRefs: Record<string, unknown>[];
  primaryTicketId: string;
}) {
  const decisionCount = metadataNumber(decision.policy_action_count);
  const kinds = asStringArray(decision.policy_action_kinds);
  const count = actions.length || decisionCount;
  const ticketId = primaryTicketId || metadataText(decision.ticket_id);
  const visibleRefs = policyRefs.slice(0, 6);
  const shouldRender = actions.length > 0 || policyRefs.length > 0 || decisionCount > 0 || kinds.length > 0;
  if (!shouldRender) return null;

  return (
    <section className="border-b p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          <Route className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <h3 className="truncate text-xs font-semibold">Ticket Loop Policy</h3>
        </div>
        <Badge variant={count > 0 ? "secondary" : "outline"} className="px-1.5 text-[10px]">
          {count || kinds.length}
        </Badge>
      </div>

      <div className="space-y-2 text-xs">
        {ticketId && ticketId !== "-" ? (
          <div className="flex justify-between gap-2 text-[11px]">
            <span className="text-muted-foreground">Ticket</span>
            <span className="truncate text-right font-medium" title={ticketId}>{ticketId}</span>
          </div>
        ) : null}

        {actions.length > 0 ? actions.slice(0, 4).map((action, index) => {
          const kind = metadataLabel(action, ["kind"], `policy-${index + 1}`);
          const status = metadataText(action.status);
          const refs = actionRefs(action);
          return (
            <div key={`${kind}-${index}`} className="rounded border bg-background/60 px-2 py-1.5">
              <div className="flex items-center justify-between gap-2">
                <div className="truncate text-[11px] font-medium" title={kind}>{kind}</div>
                <Badge variant={statusVariant(status)} className="shrink-0 px-1.5 text-[10px]">
                  {status}
                </Badge>
              </div>
              {metadataText(action.detail) !== "-" ? (
                <p className="mt-1 line-clamp-3 text-[10px] leading-4 text-muted-foreground" title={metadataText(action.detail)}>
                  {metadataText(action.detail)}
                </p>
              ) : null}
              {refs.length > 0 ? (
                <div className="mt-1 flex flex-wrap gap-1">
                  {refs.slice(0, 5).map((ref) => (
                    <Badge key={ref} variant="outline" className="max-w-full px-1.5 text-[10px]" title={ref}>
                      <span className="truncate">{ref}</span>
                    </Badge>
                  ))}
                  {refs.length > 5 ? (
                    <Badge variant="outline" className="px-1.5 text-[10px]">+{refs.length - 5}</Badge>
                  ) : null}
                </div>
              ) : null}
            </div>
          );
        }) : (
          <div className="flex flex-wrap gap-1">
            {kinds.map((kind) => (
              <Badge key={kind} variant="outline" className="max-w-full px-1.5 text-[10px]">
                <span className="truncate">{kind}</span>
              </Badge>
            ))}
          </div>
        )}

        {actions.length > 4 ? (
          <Badge variant="outline" className="px-1.5 text-[10px]">+{actions.length - 4} actions</Badge>
        ) : null}

        {visibleRefs.length > 0 ? (
          <div className="rounded border bg-background/60 px-2 py-1.5">
            <div className="mb-1 flex items-center gap-1 text-[10px] font-medium uppercase text-muted-foreground">
              <GitBranch className="h-3 w-3" />
              Policy Refs
            </div>
            <div className="flex flex-wrap gap-1">
              {visibleRefs.map((ref, index) => {
                const label = policyRefLabel(ref);
                return (
                  <Badge key={`${label}-${index}`} variant="outline" className="max-w-full px-1.5 text-[10px]" title={label}>
                    <span className="truncate">{label}</span>
                  </Badge>
                );
              })}
              {policyRefs.length > visibleRefs.length ? (
                <Badge variant="outline" className="px-1.5 text-[10px]">+{policyRefs.length - visibleRefs.length}</Badge>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
