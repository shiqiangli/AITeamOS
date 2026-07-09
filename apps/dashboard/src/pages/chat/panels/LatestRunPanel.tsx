import { Activity, Archive, GitBranch, User } from "lucide-react";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { navigateTo } from "../../../components/shared";

type RunAssetLink = {
  label: string;
  area: string | null;
  detail: string | null;
};

function metadataText(value: unknown): string {
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  return typeof value === "string" && value.trim() ? value : "-";
}

function RuntimeRefList({
  emptyLabel,
  items,
  kindLabel,
}: {
  emptyLabel?: string;
  items: Record<string, unknown>[];
  kindLabel: string;
}) {
  if (items.length === 0 && emptyLabel) {
    return <Badge variant="outline" className="px-1.5 text-[10px]">{emptyLabel}</Badge>;
  }
  if (items.length === 0) return null;
  return (
    <div>
      <div className="mb-1 text-[10px] uppercase text-muted-foreground">{kindLabel}</div>
      <div className="space-y-1">
        {items.slice(0, 4).map((item, index) => (
          <div key={`${metadataText(item.ref)}-${index}`} className="min-w-0 rounded border bg-background/60 px-2 py-1">
            <div className="truncate text-[10px] font-medium" title={metadataText(item.ref)}>
              {metadataText(item.ref)}
            </div>
            <div className="mt-0.5 truncate text-[10px] text-muted-foreground">
              {metadataText(item.kind)}
              {kindLabel === "Ticket Reports" ? ` · ${metadataText(item.evidence_count)} evidence` : ""}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function LatestRunPanel({
  actionPlans,
  approvedCapabilities,
  approvalRefs,
  artifactRefs,
  assetLink,
  capabilityGrants,
  employeeId,
  engineThreadId,
  evidenceRefs,
  execution,
  executionErrors,
  executionResult,
  executionTrace,
  governanceReportRefs,
  latestReply,
  metadata,
  metadataAiEngine,
  metadataEmployee,
  primaryTicketId,
  runtimeSessionKey,
  ticketBinding,
  ticketKeys,
  ticketReportRefs,
  tracePath,
}: {
  actionPlans: Record<string, unknown>[];
  approvedCapabilities: string[];
  approvalRefs: string[];
  artifactRefs: Record<string, unknown>[];
  assetLink: RunAssetLink | null;
  capabilityGrants: string[];
  employeeId: string;
  engineThreadId: string | null;
  evidenceRefs: Record<string, unknown>[];
  execution: Record<string, unknown>;
  executionErrors: Record<string, unknown>[];
  executionResult: Record<string, unknown>;
  executionTrace: Record<string, unknown>;
  governanceReportRefs: Record<string, unknown>[];
  latestReply: string;
  metadata: Record<string, unknown>;
  metadataAiEngine: Record<string, unknown>;
  metadataEmployee: Record<string, unknown>;
  primaryTicketId: string;
  runtimeSessionKey: string;
  ticketBinding: Record<string, unknown>;
  ticketKeys: string[];
  ticketReportRefs: Record<string, unknown>[];
  tracePath: string;
}) {
  const hasExecution = Object.keys(execution).length > 0;
  return (
    <>
      <div className="text-[10px] font-medium uppercase text-muted-foreground">Latest Run</div>
      <div className="flex justify-between gap-2">
        <span className="text-muted-foreground">Run</span>
        <span className="truncate font-medium" title={metadataText(metadata.run_id)}>
          {metadataText(metadata.run_id)}
        </span>
      </div>
      <div className="flex justify-between gap-2">
        <span className="text-muted-foreground">Employee</span>
        <span className="truncate text-right font-medium" title={metadataText(metadataEmployee.role)}>
          {metadataText(metadataEmployee.display_name)}
        </span>
      </div>
      <div className="flex justify-between gap-2">
        <span className="text-muted-foreground">AI Engine</span>
        <span className="truncate text-right font-medium">
          {metadataText(metadataAiEngine.actual_ai_engine)}
        </span>
      </div>
      <div className="flex justify-between gap-2">
        <span className="text-muted-foreground">Model</span>
        <span className="truncate text-right">{metadataText(metadataAiEngine.model)}</span>
      </div>
      <div className="flex justify-between gap-2">
        <span className="text-muted-foreground">Engine thread</span>
        <span className="truncate text-right" title={metadataText(metadataAiEngine.engine_thread_id || engineThreadId)}>
          {metadataText(metadataAiEngine.engine_thread_id || engineThreadId)}
        </span>
      </div>
      <div className="flex justify-between gap-2">
        <span className="text-muted-foreground">Trace path</span>
        <span className="truncate text-right" title={tracePath}>{tracePath}</span>
      </div>
      {latestReply.trim() && (
        <div className="rounded-md border bg-muted/30 p-2">
          <div className="mb-1 text-[10px] uppercase text-muted-foreground">Reply</div>
          <p className="whitespace-pre-wrap text-xs leading-relaxed text-foreground">{latestReply}</p>
        </div>
      )}
      {(primaryTicketId || employeeId || runtimeSessionKey || assetLink) && (
        <div>
          <div className="mb-1 text-[10px] uppercase text-muted-foreground">Provenance Links</div>
          <div className="flex flex-wrap gap-1.5">
            {primaryTicketId && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 gap-1 px-2 text-[10px]"
                aria-label={`Open Ticket ${primaryTicketId}`}
                onClick={() => navigateTo("tickets", primaryTicketId)}
              >
                <GitBranch className="h-3 w-3" />
                Ticket
              </Button>
            )}
            {employeeId && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 gap-1 px-2 text-[10px]"
                aria-label={`Open Employee ${employeeId}`}
                onClick={() => navigateTo("employees", employeeId, "work")}
              >
                <User className="h-3 w-3" />
                Employee
              </Button>
            )}
            {runtimeSessionKey && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 gap-1 px-2 text-[10px]"
                aria-label={`Open Runtime Replay ${runtimeSessionKey}`}
                onClick={() => navigateTo("runtime", runtimeSessionKey)}
              >
                <Activity className="h-3 w-3" />
                Replay
              </Button>
            )}
            {assetLink && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 gap-1 px-2 text-[10px]"
                aria-label={`Open ${assetLink.label}`}
                onClick={() => {
                  if (assetLink.area) navigateTo("assets", assetLink.area, assetLink.detail);
                  else navigateTo("assets");
                }}
              >
                <Archive className="h-3 w-3" />
                {assetLink.label}
              </Button>
            )}
          </div>
        </div>
      )}
      <div>
        <div className="mb-1 text-[10px] uppercase text-muted-foreground">Tickets</div>
        <div className="flex flex-wrap gap-1">
          {ticketKeys.length ? ticketKeys.map((key) => (
            <Badge key={key} variant="secondary" className="px-1.5 text-[10px]">{key}</Badge>
          )) : (
            <Badge variant="outline" className="px-1.5 text-[10px]">none</Badge>
          )}
        </div>
      </div>
      <div>
        <div className="mb-1 text-[10px] uppercase text-muted-foreground">Action Plan</div>
        <div className="flex flex-wrap gap-1">
          {actionPlans.length ? actionPlans.map((plan, index) => {
            const action = metadataText(plan.action);
            const source = metadataText(plan.source);
            return (
              <Badge
                key={`${action}-${source}-${index}`}
                variant={action === "answer_only" ? "outline" : "secondary"}
                className="max-w-full px-1.5 text-[10px]"
                title={metadataText(plan.reason)}
              >
                <span className="truncate">{action}:{source}</span>
              </Badge>
            );
          }) : (
            <Badge variant="outline" className="px-1.5 text-[10px]">none</Badge>
          )}
        </div>
      </div>
      {hasExecution && (
        <div className="rounded-md border bg-background/60 p-2">
          <div className="mb-1 text-[10px] font-medium uppercase text-muted-foreground">Runtime Dispatch</div>
          <div className="space-y-1 text-[11px]">
            <div className="flex justify-between gap-2">
              <span className="text-muted-foreground">Executor</span>
              <span className="truncate text-right font-medium">{metadataText(execution.executor_id)}</span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-muted-foreground">Status</span>
              <span className="truncate text-right font-medium">{metadataText(execution.status)}</span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-muted-foreground">Request</span>
              <span className="truncate text-right" title={metadataText(execution.request_id)}>
                {metadataText(execution.request_id)}
              </span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-muted-foreground">Binding</span>
              <span className="truncate text-right">
                {metadataText(ticketBinding.mode)}:{metadataText(ticketBinding.ticket_id)}
              </span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-muted-foreground">Session</span>
              <span className="truncate text-right" title={metadataText(executionTrace.executor_session_ref)}>
                {metadataText(executionTrace.executor_session_ref)}
              </span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-muted-foreground">Checkpoint</span>
              <span className="truncate text-right" title={metadataText(executionTrace.checkpoint_ref)}>
                {metadataText(executionTrace.checkpoint_ref)}
              </span>
            </div>
          </div>
          <div className="mt-2 flex flex-wrap gap-1">
            <Badge variant="secondary" className="px-1.5 text-[10px]">
              {String(executionResult.tool_event_count ?? 0)} tool events
            </Badge>
            <Badge variant="outline" className="px-1.5 text-[10px]">
              {String(executionResult.artifact_count ?? 0)} artifacts
            </Badge>
            <Badge variant="outline" className="px-1.5 text-[10px]">
              {String(executionResult.evidence_count ?? 0)} evidence
            </Badge>
            <Badge variant="outline" className="px-1.5 text-[10px]">
              {String(executionResult.ticket_report_count ?? 0)} reports
            </Badge>
            <Badge variant={Number(executionResult.error_count ?? 0) > 0 ? "warning" : "outline"} className="px-1.5 text-[10px]">
              {String(executionResult.error_count ?? 0)} errors
            </Badge>
          </div>
          {(artifactRefs.length > 0 || evidenceRefs.length > 0 || ticketReportRefs.length > 0 || executionErrors.length > 0) && (
            <div className="mt-2 grid gap-2">
              <RuntimeRefList items={artifactRefs} kindLabel="Artifacts" />
              <RuntimeRefList items={evidenceRefs} kindLabel="Evidence" />
              <RuntimeRefList items={ticketReportRefs} kindLabel="Ticket Reports" />
              {executionErrors.length > 0 && (
                <div>
                  <div className="mb-1 text-[10px] uppercase text-muted-foreground">Execution Errors</div>
                  <div className="space-y-1">
                    {executionErrors.slice(0, 3).map((errorRef, index) => (
                      <div key={`${metadataText(errorRef.reason)}-${index}`} className="min-w-0 rounded border bg-background/60 px-2 py-1">
                        <div className="truncate text-[10px] font-medium" title={metadataText(errorRef.reason)}>
                          {metadataText(errorRef.reason)}
                        </div>
                        <div className="mt-0.5 truncate text-[10px] text-muted-foreground" title={metadataText(errorRef.detail)}>
                          {metadataText(errorRef.detail)}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
          {(approvalRefs.length > 0 || approvedCapabilities.length > 0 || governanceReportRefs.length > 0) && (
            <div className="mt-2 rounded border bg-background/60 px-2 py-1.5">
              <div className="mb-1 text-[10px] uppercase text-muted-foreground">Governance Refs</div>
              <div className="flex flex-wrap gap-1">
                {approvalRefs.slice(0, 5).map((ref) => (
                  <Badge key={`approval-ref-${ref}`} variant="secondary" className="px-1.5 text-[10px]">approval {ref}</Badge>
                ))}
                {approvedCapabilities.slice(0, 5).map((capability) => (
                  <Badge key={`approved-capability-${capability}`} variant="outline" className="px-1.5 text-[10px]">approved {capability}</Badge>
                ))}
                {governanceReportRefs.slice(0, 3).map((reportRef) => (
                  <Badge key={`governance-report-${metadataText(reportRef.ref)}`} variant="outline" className="px-1.5 text-[10px]">
                    report {metadataText(reportRef.ref)}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {capabilityGrants.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {capabilityGrants.slice(0, 6).map((grant) => (
                <Badge key={grant} variant="outline" className="px-1.5 text-[10px]">{grant}</Badge>
              ))}
              {capabilityGrants.length > 6 && (
                <Badge variant="secondary" className="px-1.5 text-[10px]">+{capabilityGrants.length - 6}</Badge>
              )}
            </div>
          )}
        </div>
      )}
    </>
  );
}
