import { useState } from "react";
import { Archive, Check, FileQuestion, RefreshCw, X } from "lucide-react";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Textarea } from "../../../components/ui/textarea";
import { navigateTo } from "../../../components/shared";
import {
  reviewRuntimeExecutorApproval,
  type RuntimeApprovalReviewStatus,
} from "../../../api/runtimeExecutors";
import {
  delay,
  fetchLangGraphPendingInterrupt,
  fetchLangGraphThreadValues,
  langGraphApiUrl,
  langGraphAssistantId,
  readCurrentLangGraphThreadId,
  readLatestLangGraphExternalThreadId,
  sendLangGraphInputRespond,
} from "../runtime/workbenchState";

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

function firstMetadataValue(values: unknown[]): string {
  for (const value of values) {
    const text = metadataText(value);
    if (text !== "-") return text;
  }
  return "";
}

function compactRef(value: unknown): string {
  const text = metadataText(value);
  if (text === "-") return "-";
  if (text.length <= 42) return text;
  return `${text.slice(0, 18)}...${text.slice(-18)}`;
}

function formatRuntimeTime(value: unknown): string {
  const text = metadataText(value);
  if (text === "-") return "-";
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return text;
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function statusVariant(status: string): "success" | "warning" | "secondary" | "outline" {
  if (status === "approved") return "success";
  if (status === "rejected" || status === "changes_requested" || status === "evidence_requested") return "warning";
  if (status && status !== "-") return "secondary";
  return "outline";
}

function reviewStatusLabel(status: string): string {
  if (status === "changes_requested") return "changes requested";
  if (status === "evidence_requested") return "evidence requested";
  return status || "requested";
}

function approvalRecordForRef(records: Record<string, unknown>[], approvalRef: string): Record<string, unknown> {
  return records.find((record) => (
    metadataLabel(record, ["id", "approval_ref", "approval_id"], "") === approvalRef
  )) ?? {};
}

function defaultReviewReason(status: RuntimeApprovalReviewStatus): string {
  if (status === "approved") return "Approved from Chat Workbench before LangGraph resume.";
  if (status === "rejected") return "Rejected from Chat Workbench.";
  if (status === "changes_requested") return "Changes requested from Chat Workbench.";
  return "More evidence requested from Chat Workbench.";
}

function approvalActionLabel(record: Record<string, unknown>, request: Record<string, unknown>): string {
  const proposedAction = asRecord(record.proposed_action || request.proposed_action);
  const sourceRequest = asRecord(record.source_request);
  const sourceActionPlan = asRecord(sourceRequest.action_plan);
  return firstMetadataValue([
    proposedAction.action,
    sourceActionPlan.action,
    request.action,
    request.kind,
  ]) || "-";
}

function ApprovalMetaLine({ label, value, title }: { label: string; value: string; title?: string }) {
  if (!value || value === "-") return null;
  return (
    <div className="flex min-w-0 justify-between gap-2">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="truncate text-right" title={title ?? value}>{value}</span>
    </div>
  );
}

interface ApprovalResumeButtonProps {
  approvalRef: string;
  approvalReason: string;
  interruptId: string;
  interruptNamespace: string[];
  langGraphThreadId: string;
  onRuntimeValues: (values: Record<string, unknown>) => void;
  request: Record<string, unknown>;
  ticketId: string;
  onResumeIntent: (approvalRef: string, ticketId: string) => void;
  onReviewApproval: (status: RuntimeApprovalReviewStatus, reason: string) => Promise<void>;
  onError: (message: string) => void;
}

function ApprovalResumeButton({
  approvalRef,
  approvalReason,
  interruptId,
  interruptNamespace,
  langGraphThreadId,
  onRuntimeValues,
  request,
  ticketId,
  onResumeIntent,
  onReviewApproval,
  onError,
}: ApprovalResumeButtonProps) {
  const [submitting, setSubmitting] = useState(false);
  const requiredCapability = metadataLabel(request, ["required_capability", "capability"], "");
  const executorId = metadataText(request.executor_id);

  async function resumeApproval() {
    if (!approvalRef || submitting) return;
    setSubmitting(true);
    onResumeIntent(approvalRef, ticketId);
    const responsePayload = {
      source: "aiteamos_chat_workbench",
      action: "resume_after_approval",
      approval_ref: approvalRef,
      approval_refs: [approvalRef],
      approved_capabilities: requiredCapability ? [requiredCapability] : [],
      ticket_id: ticketId,
      executor_id: executorId !== "-" ? executorId : "",
    };
    try {
      await onReviewApproval("approved", approvalReason.trim() || defaultReviewReason("approved"));
      const apiUrl = langGraphApiUrl();
      const assistantId = langGraphAssistantId();
      const runtimeThreadId = (
        langGraphThreadId
        || readCurrentLangGraphThreadId()
        || readLatestLangGraphExternalThreadId(apiUrl, assistantId)
      );
      let selectedInterruptId = interruptId;
      let selectedNamespace = interruptNamespace.length > 0 ? interruptNamespace : [];
      if (runtimeThreadId && !selectedInterruptId) {
        const pendingInterrupt = await fetchLangGraphPendingInterrupt(apiUrl, runtimeThreadId, approvalRef);
        selectedInterruptId = pendingInterrupt?.id ?? "";
        selectedNamespace = pendingInterrupt?.namespace ?? selectedNamespace;
      }
      if (runtimeThreadId && selectedInterruptId) {
        await sendLangGraphInputRespond({
          apiUrl,
          threadId: runtimeThreadId,
          interruptId: selectedInterruptId,
          namespace: selectedNamespace,
          response: responsePayload,
        });
        for (const waitMs of [300, 700, 1200, 2400, 4800, 8000]) {
          await delay(waitMs);
          const values = await fetchLangGraphThreadValues(apiUrl, runtimeThreadId);
          onRuntimeValues(values);
          const runtimeStatus = asRecord(values.runtime_status);
          if (metadataText(runtimeStatus.status) === "completed") return;
        }
        return;
      }
      throw new Error(
        runtimeThreadId
          ? "LangGraph approval interrupt id is not available yet."
          : "LangGraph runtime thread id is not available yet.",
      );
    } catch (error) {
      onError(error instanceof Error ? error.message : "Failed to resume approval");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      className="h-6 gap-1 px-2 text-[10px]"
      onClick={() => void resumeApproval()}
      disabled={submitting}
      aria-label={`Resume approval ${approvalRef}`}
    >
      <Check className="h-3 w-3" />
      {submitting ? "Approving" : "Approve"}
    </Button>
  );
}

export function ApprovalPanel({
  approval,
  approvalGuards,
  approvalRefs,
  approvalRequests,
  approvalRecords,
  approvedCapabilities,
  langGraphThreadId,
  pendingInterruptId,
  pendingInterruptNamespace,
  onError,
  onResumeIntent,
  onRuntimeValues,
}: {
  approval: Record<string, unknown>;
  approvalGuards: string[];
  approvalRefs: string[];
  approvalRequests: Record<string, unknown>[];
  approvalRecords: Record<string, unknown>[];
  approvedCapabilities: string[];
  langGraphThreadId: string;
  pendingInterruptId: string;
  pendingInterruptNamespace: string[];
  onError: (message: string) => void;
  onResumeIntent: (approvalRef: string, ticketId: string) => void;
  onRuntimeValues: (values: Record<string, unknown>) => void;
}) {
  const [reviewingRef, setReviewingRef] = useState("");
  const [reviewedStatusByRef, setReviewedStatusByRef] = useState<Record<string, string>>({});
  const [reviewedRecordByRef, setReviewedRecordByRef] = useState<Record<string, Record<string, unknown>>>({});
  const [reviewReasonByRef, setReviewReasonByRef] = useState<Record<string, string>>({});
  const displayApprovalRequests: Record<string, unknown>[] = approvalRequests.length > 0
    ? approvalRequests
    : approvalRecords.map((record): Record<string, unknown> => ({
        ...record,
        approval_ref: firstMetadataValue([record.id, record.approval_ref, record.approval_id]),
      }));
  if (Object.keys(approval).length === 0 && approvalRequests.length === 0 && approvalRecords.length === 0) return null;

  async function reviewRequest(
    request: Record<string, unknown>,
    status: RuntimeApprovalReviewStatus,
    reason: string,
  ) {
    const approvalRef = metadataLabel(request, ["approval_ref", "approval_id", "id"], "");
    const executorId = metadataText(request.executor_id);
    if (!approvalRef || executorId === "-") {
      throw new Error("Runtime approval ref and executor id are required.");
    }
    setReviewingRef(`${status}:${approvalRef}`);
    try {
      const reviewed = await reviewRuntimeExecutorApproval(executorId, approvalRef, {
        status,
        reviewer_employee_id: "clara",
        reason,
      });
      setReviewedStatusByRef((current) => ({ ...current, [approvalRef]: reviewed.status }));
      setReviewedRecordByRef((current) => ({ ...current, [approvalRef]: reviewed as unknown as Record<string, unknown> }));
      setReviewReasonByRef((current) => ({ ...current, [approvalRef]: reviewed.review_reason || reason }));
    } finally {
      setReviewingRef("");
    }
  }

  async function handleReview(
    request: Record<string, unknown>,
    status: RuntimeApprovalReviewStatus,
    approvalRef: string,
  ) {
    try {
      const reason = reviewReasonByRef[approvalRef]?.trim() || defaultReviewReason(status);
      await reviewRequest(request, status, reason);
    } catch (error) {
      onError(error instanceof Error ? error.message : "Failed to review approval");
    }
  }

  return (
    <div className="rounded-md border bg-background/60 p-2">
      <div className="mb-1 text-[10px] font-medium uppercase text-muted-foreground">Approval Policy</div>
      <div className="flex flex-wrap gap-1">
        {approvalGuards.length ? approvalGuards.slice(0, 6).map((guard) => (
          <Badge key={guard} variant="outline" className="px-1.5 text-[10px]">{guard}</Badge>
        )) : (
          <Badge variant="outline" className="px-1.5 text-[10px]">none</Badge>
        )}
      </div>
      <div className="mt-2 text-[10px] text-muted-foreground">
        Requests: {approvalRequests.length} · Records: {approvalRecords.length}
      </div>
      {(approvalRefs.length > 0 || approvedCapabilities.length > 0) && (
        <div className="mt-2 flex flex-wrap gap-1">
          {approvalRefs.slice(0, 5).map((ref) => (
            <Badge key={`policy-approval-${ref}`} variant="secondary" className="px-1.5 text-[10px]">Ref: {ref}</Badge>
          ))}
          {approvedCapabilities.slice(0, 5).map((capability) => (
            <Badge key={`policy-approved-${capability}`} variant="outline" className="px-1.5 text-[10px]">Approved: {capability}</Badge>
          ))}
        </div>
      )}
      {displayApprovalRequests.length > 0 && (
        <div className="mt-2 space-y-1">
          {displayApprovalRequests.slice(0, 4).map((request, index) => {
            const kind = metadataLabel(request, ["kind", "type", "action"], `request-${index + 1}`);
            const reason = metadataText(request.reason);
            const requestApprovalRef = metadataLabel(request, ["approval_ref", "approval_id", "id"], "-");
            const approvalRecord = requestApprovalRef !== "-"
              ? (reviewedRecordByRef[requestApprovalRef] ?? approvalRecordForRef(approvalRecords, requestApprovalRef))
              : {};
            const requestTicketId = metadataText(request.ticket_id);
            const requestExecutorId = metadataText(request.executor_id);
            const reviewedStatus = reviewedStatusByRef[requestApprovalRef] || firstMetadataValue([approvalRecord.status, request.status]);
            const actionKey = (status: RuntimeApprovalReviewStatus) => `${status}:${requestApprovalRef}`;
            const riskLevel = firstMetadataValue([approvalRecord.risk_level, request.risk_level]);
            const actionLabel = approvalActionLabel(approvalRecord, request);
            const reviewer = firstMetadataValue([approvalRecord.reviewer_employee_id]);
            const reviewedAt = firstMetadataValue([approvalRecord.reviewed_at]);
            const reviewReason = firstMetadataValue([approvalRecord.review_reason]);
            const checkpointRef = firstMetadataValue([approvalRecord.checkpoint_ref, request.checkpoint_ref]);
            const stateRef = firstMetadataValue([approvalRecord.source_state_ref, request.source_state_ref]);
            const snapshotRef = firstMetadataValue([approvalRecord.source_state_snapshot_ref, request.source_state_snapshot_ref]);
            const lastRunStatus = firstMetadataValue([approvalRecord.last_run_status]);
            const lastRunRequestId = firstMetadataValue([approvalRecord.last_run_request_id]);
            const lastIngestionBlocker = firstMetadataValue([approvalRecord.last_ingestion_blocker]);
            const runHistory = asRecordArray(approvalRecord.run_history);
            const draftReason = reviewReasonByRef[requestApprovalRef] ?? reviewReason;
            return (
              <div key={`${kind}-${index}`} className="min-w-0 rounded border bg-background/60 px-2 py-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-[10px] font-medium" title={kind}>{kind}</span>
                  <div className="flex shrink-0 items-center gap-1">
                    {reviewedStatus !== "-" && (
                      <Badge variant={statusVariant(reviewedStatus)} className="px-1.5 text-[10px]">
                        {reviewStatusLabel(reviewedStatus)}
                      </Badge>
                    )}
                    <Badge variant="warning" className="px-1.5 text-[10px]">
                      {metadataLabel(request, ["required_capability", "capability"], "approval")}
                    </Badge>
                  </div>
                </div>
                {reason !== "-" && (
                  <div className="mt-0.5 truncate text-[10px] text-muted-foreground" title={reason}>
                    {reason}
                  </div>
                )}
                <div className="mt-1 flex flex-wrap gap-1 text-[10px] text-muted-foreground">
                  <span className="truncate">Executor: {metadataText(request.executor_id)}</span>
                  <span className="truncate">Ticket: {requestTicketId}</span>
                  <span className="truncate">Ref: {requestApprovalRef}</span>
                  {riskLevel && <span className="truncate">Risk: {riskLevel}</span>}
                </div>
                <div className="mt-2 grid gap-1 rounded border bg-card px-2 py-1.5 text-[10px]">
                  <ApprovalMetaLine label="Action" value={actionLabel} />
                  <ApprovalMetaLine label="Checkpoint" value={compactRef(checkpointRef)} title={checkpointRef} />
                  <ApprovalMetaLine label="State" value={compactRef(stateRef)} title={stateRef} />
                  <ApprovalMetaLine label="Snapshot" value={compactRef(snapshotRef)} title={snapshotRef} />
                  <ApprovalMetaLine label="Reviewed" value={reviewer && reviewedAt ? `${formatRuntimeTime(reviewedAt)} by ${reviewer}` : ""} title={reviewedAt} />
                  <ApprovalMetaLine label="Last run" value={lastRunRequestId ? `${compactRef(lastRunRequestId)} (${lastRunStatus || "-"})` : lastRunStatus} title={lastRunRequestId} />
                </div>
                {lastIngestionBlocker && (
                  <div className="mt-1 rounded border border-warning/40 bg-warning/10 px-2 py-1 text-[10px] text-warning-foreground">
                    <span className="font-medium">Ingestion blocker: </span>
                    <span>{lastIngestionBlocker}</span>
                  </div>
                )}
                {reviewReason && (
                  <div className="mt-1 rounded border bg-background/80 px-2 py-1 text-[10px] text-muted-foreground">
                    <span className="font-medium text-foreground">Review reason: </span>
                    <span>{reviewReason}</span>
                  </div>
                )}
                {runHistory.length > 0 && (
                  <div className="mt-2 space-y-1">
                    <div className="text-[10px] font-medium uppercase text-muted-foreground">Run History</div>
                    {runHistory.slice(-2).map((entry, attemptIndex) => {
                      const runRequestId = metadataLabel(entry, ["run_request_id", "request_id"], `attempt-${attemptIndex + 1}`);
                      const blocker = firstMetadataValue([entry.ingestion_blocker]);
                      return (
                        <div key={`${runRequestId}-${attemptIndex}`} className="rounded border bg-background/80 px-2 py-1 text-[10px]">
                          <div className="mb-1 flex min-w-0 items-center justify-between gap-2">
                            <span className="truncate font-medium" title={runRequestId}>
                              Attempt {runHistory.length - Math.min(runHistory.length, 2) + attemptIndex + 1}: {runRequestId}
                            </span>
                            <Badge variant={statusVariant(metadataText(entry.status))} className="px-1.5 text-[10px]">
                              {metadataText(entry.status)}
                            </Badge>
                          </div>
                          <div className="grid gap-1 sm:grid-cols-3">
                            <ApprovalMetaLine label="Artifacts" value={metadataText(entry.artifact_count)} />
                            <ApprovalMetaLine label="Evidence" value={metadataText(entry.evidence_count)} />
                            <ApprovalMetaLine label="Errors" value={metadataText(entry.error_count)} />
                          </div>
                          {blocker && (
                            <div className="mt-1 text-muted-foreground">
                              <span className="font-medium text-foreground">Blocker: </span>{blocker}
                            </div>
                          )}
                        </div>
                      );
                    })}
                    {runHistory.length > 2 && (
                      <Badge variant="secondary" className="px-1.5 text-[10px]">
                        +{runHistory.length - 2} earlier attempts
                      </Badge>
                    )}
                  </div>
                )}
                {requestApprovalRef !== "-" && (
                  <div className="mt-2 space-y-1">
                    <Textarea
                      aria-label={`Review reason ${requestApprovalRef}`}
                      className="min-h-[3.25rem] resize-none px-2 py-1 text-[11px]"
                      placeholder="Reason for this approval decision"
                      value={draftReason}
                      onChange={(event) => setReviewReasonByRef((current) => ({
                        ...current,
                        [requestApprovalRef]: event.target.value,
                      }))}
                    />
                    <div className="flex flex-wrap justify-end gap-1">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-6 gap-1 px-2 text-[10px]"
                        onClick={() => {
                          const target = requestExecutorId !== "-"
                            ? `runtime-approval:${requestExecutorId}:${requestApprovalRef}`
                            : `approval:${requestApprovalRef}`;
                          navigateTo("assets", "review", target);
                        }}
                      >
                        <Archive className="h-3 w-3" />
                        Review
                      </Button>
                      <ApprovalResumeButton
                        approvalRef={requestApprovalRef}
                        approvalReason={draftReason}
                        interruptId={pendingInterruptId}
                        interruptNamespace={pendingInterruptNamespace}
                        langGraphThreadId={langGraphThreadId}
                        onRuntimeValues={onRuntimeValues}
                        request={request}
                        ticketId={requestTicketId !== "-" ? requestTicketId : ""}
                        onResumeIntent={onResumeIntent}
                        onReviewApproval={(status, nextReason) => reviewRequest(request, status, nextReason)}
                        onError={onError}
                      />
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-6 gap-1 px-2 text-[10px]"
                        aria-label={`Reject approval ${requestApprovalRef}`}
                        disabled={reviewingRef === actionKey("rejected")}
                        onClick={() => void handleReview(request, "rejected", requestApprovalRef)}
                      >
                        <X className="h-3 w-3" />
                        Reject
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-6 gap-1 px-2 text-[10px]"
                        aria-label={`Request changes approval ${requestApprovalRef}`}
                        disabled={reviewingRef === actionKey("changes_requested")}
                        onClick={() => void handleReview(request, "changes_requested", requestApprovalRef)}
                      >
                        <RefreshCw className="h-3 w-3" />
                        Changes
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-6 gap-1 px-2 text-[10px]"
                        aria-label={`Ask evidence approval ${requestApprovalRef}`}
                        disabled={reviewingRef === actionKey("evidence_requested")}
                        onClick={() => void handleReview(request, "evidence_requested", requestApprovalRef)}
                      >
                        <FileQuestion className="h-3 w-3" />
                        Evidence
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
          {displayApprovalRequests.length > 4 && (
            <Badge variant="secondary" className="px-1.5 text-[10px]">
              +{displayApprovalRequests.length - 4} more requests
            </Badge>
          )}
        </div>
      )}
    </div>
  );
}
