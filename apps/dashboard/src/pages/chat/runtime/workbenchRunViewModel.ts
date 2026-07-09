import type { ChatTraceEvent } from "../../../api/chat";
import type { WorkbenchSnapshot } from "./workbenchState";

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
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

function metadataCount(value: unknown): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

export interface WorkbenchRunViewModelInput {
  engineThreadId: string | null;
  latestReply: string;
  runMetadata: Record<string, unknown> | null;
  savedPaths: Record<string, string>;
  traceEvents: ChatTraceEvent[];
  workbenchSnapshot: WorkbenchSnapshot | null;
}

export interface WorkbenchVisibleResponseView {
  assistantText: string;
  status: string;
  displayState: string;
  blockedReason: string;
  retryCause: string;
  approvalRequests: Record<string, unknown>[];
  providerBlockers: Record<string, unknown>[];
  ticketRefs: Record<string, unknown>[];
  assetRefs: Record<string, unknown>[];
  memoryRefs: Record<string, unknown>[];
  handoffSummary: Record<string, unknown>;
  ticketHandoffRefs: Record<string, unknown>[];
  primaryEmployeeId: string;
  primaryTicketId: string;
  primaryAssetTarget: { area: string | null; detail: string | null; label: string } | null;
  runtimeSessionKey: string;
}

export function createWorkbenchRunViewModel({
  engineThreadId,
  latestReply,
  runMetadata,
  savedPaths,
  traceEvents,
  workbenchSnapshot,
}: WorkbenchRunViewModelInput) {
  const metadata = asRecord(runMetadata);
  const visibleContract = asRecord(metadata.visible_response);
  const visibleAssistantMessage = asRecord(visibleContract.assistant_message);
  const visibleRuntimeStatus = asRecord(visibleContract.runtime_status);
  const workbenchActiveTicket = asRecord(workbenchSnapshot?.activeTicket);
  const workbenchEmployeeIdentity = asRecord(
    Object.keys(asRecord(workbenchSnapshot?.employeeIdentity)).length > 0
      ? workbenchSnapshot?.employeeIdentity
      : workbenchSnapshot?.selectedEmployee,
  );
  const workbenchTicketBinding = asRecord(workbenchSnapshot?.ticketBinding);
  const workbenchRuntimeStatus = asRecord(workbenchSnapshot?.runtimeStatus);
  const workbenchLinkedAssets = asRecordArray(workbenchSnapshot?.linkedAssets);
  const workbenchRecalledMemoryRefs = asRecordArray(workbenchSnapshot?.recalledMemoryRefs);
  const workbenchApprovalRequests = asRecordArray(workbenchSnapshot?.approvalRequests);
  const workbenchApprovalRecords = asRecordArray(workbenchSnapshot?.approvalRecords);
  const assetCandidates = asRecordArray(workbenchSnapshot?.assetCandidates);
  const workbenchProviderBlockers = asRecordArray(workbenchSnapshot?.providerBlockers);
  const ticketLoopDecision = asRecord(workbenchSnapshot?.ticketLoopDecision);
  const ticketLoopPolicyActions = asRecordArray(workbenchSnapshot?.ticketLoopPolicyActions);
  const ticketLoopPolicyRefs = asRecordArray(ticketLoopDecision.policy_action_refs);
  const workbenchHandoffSummary = asRecord(workbenchSnapshot?.handoffSummary);
  const metadataAiEngine = asRecord(metadata.ai_engine);
  const metadataEmployee = asRecord(metadata.employee);
  const ticketKeys = Array.from(new Set([
    ...asStringArray(metadata.ticket_keys),
    ...[
      workbenchActiveTicket.id,
      workbenchActiveTicket.ticket_id,
      workbenchTicketBinding.ticket_id,
    ].map(metadataText).filter((value) => value !== "-"),
  ]));
  const commands = Array.isArray(metadata.commands) ? metadata.commands.map(asRecord) : [];
  const trace = asRecord(metadata.trace);
  const tracePath = metadataText(trace.path || savedPaths.trace || savedPaths.run);
  const providerRefs = asRecordArray(metadata.provider_refs);
  const graphitiEpisodeRefs = asRecordArray(metadata.graphiti_episode_refs);
  const recalledMemoryRefs = workbenchRecalledMemoryRefs.length > 0
    ? workbenchRecalledMemoryRefs
    : asRecordArray(metadata.recalled_memory_refs);
  const execution = asRecord(metadata.execution);
  const executionTrace = asRecord(execution.trace);
  const executionResult = asRecord(execution.result);
  const executionGovernance = asRecord(execution.governance);
  const artifactRefs = workbenchLinkedAssets.length > 0
    ? workbenchLinkedAssets
    : asRecordArray(executionResult.artifact_refs);
  const evidenceRefs = asRecordArray(executionResult.evidence_refs);
  const ticketReportRefs = asRecordArray(executionResult.ticket_report_refs);
  const executionErrors = asRecordArray(executionResult.errors);
  const ticketBinding = Object.keys(workbenchTicketBinding).length > 0
    ? workbenchTicketBinding
    : asRecord(execution.ticket_binding);
  const scopedContext = asRecord(metadata.scoped_context);
  const universalContext = asRecord(scopedContext.universal_context);
  const universalProvenance = asRecordArray(universalContext.provenance_summary);
  const approval = asRecord(metadata.approval);
  const capabilityGrants = asStringArray(execution.capability_grants);
  const approvalGuards = asStringArray(approval.require_approval_for);
  const approvalRefs = asStringArray(approval.approval_refs);
  const approvedCapabilities = asStringArray(approval.approved_capabilities);
  const governanceReportRefs = asRecordArray(executionGovernance.ticket_report_refs);
  const contextExclusions = asStringArray(scopedContext.exclusions);
  const setupBlockers = workbenchProviderBlockers.length > 0
    ? workbenchProviderBlockers
    : asRecordArray(scopedContext.setup_blockers);
  const approvalRequests = workbenchApprovalRequests.length > 0
    ? workbenchApprovalRequests
    : asRecordArray(approval.approval_requests);
  const approvalRecords = workbenchApprovalRecords.length > 0
    ? workbenchApprovalRecords
    : asRecordArray(approval.approval_records);
  const visibleProviderBlockers = asRecordArray(visibleContract.provider_blockers);
  const visibleApprovalRequests = asRecordArray(visibleContract.approval_requests);
  const visibleHandoffSummary = asRecord(visibleContract.handoff_summary);
  const visibleTicketHandoffRefs = asRecordArray(visibleContract.ticket_handoff_refs);
  const visibleTicketRefs = asRecordArray(visibleContract.ticket_refs);
  const visibleAssetRefs = asRecordArray(visibleContract.asset_refs);
  const visibleMemoryRefs = asRecordArray(visibleContract.memory_refs);
  const actionPlans = traceEvents
    .filter((event) => event.event === "chat.action_plan.completed")
    .map((event) => asRecord(event.data))
    .filter((item) => Object.keys(item).length > 0);
  const learningSummary = asRecord(metadata.learning_summary);
  const summary = metadataText(learningSummary.clara_summary);
  const recalledAssets = Array.isArray(learningSummary.recalled_assets)
    ? learningSummary.recalled_assets.map(asRecord)
    : [];
  const nextGuidance = asStringArray(learningSummary.next_round_guidance);
  const primaryTicketId = firstMetadataValue([
    workbenchActiveTicket.id,
    workbenchActiveTicket.ticket_id,
    ticketKeys[0],
    ticketBinding.ticket_id,
    executionResult.output_ticket_id,
    universalContext.ticket_id,
  ]);
  const employeeId = firstMetadataValue([workbenchEmployeeIdentity.id, metadataEmployee.id, universalContext.employee_id]);
  const threadId = firstMetadataValue([metadata.thread_id]);
  const runtimeSessionKey = firstMetadataValue([
    workbenchRuntimeStatus.session_key,
    executionTrace.session_key,
    execution.session_key,
    metadata.session_key,
  ]) || (
    employeeId && threadId
      ? `${employeeId}::${threadId}::${primaryTicketId || "none"}`
      : ""
  );
  const memoryCandidateCount = metadataCount(executionResult.memory_candidate_count)
    || metadataCount(learningSummary.new_candidate_count)
    || assetCandidates.length;
  const relevantAssetCount = metadataCount(scopedContext.relevant_asset_count)
    || metadataCount(universalContext.relevant_asset_count);
  const primaryMemoryId = firstMetadataValue([
    ...recalledMemoryRefs.flatMap((memoryRef) => [memoryRef.memory_id, memoryRef.asset_id]),
    ...universalProvenance
      .filter((item) => metadataLabel(item, ["kind", "source_kind"], "") === "memory")
      .map((item) => item.source_ref),
  ]);
  const hasRecalledMemory = recalledMemoryRefs.length > 0
    || metadataCount(scopedContext.recalled_memory_count) > 0
    || metadataCount(universalContext.recalled_memory_count) > 0;
  const assetLink = memoryCandidateCount > 0
    ? { label: "Asset Review", area: "review", detail: "memories" }
    : primaryMemoryId
      ? { label: "Memory", area: "knowledge", detail: `memory:${primaryMemoryId}` }
      : hasRecalledMemory
        ? { label: "Memories", area: "knowledge", detail: "memories" }
        : relevantAssetCount > 0
          ? { label: "Assets", area: null, detail: null }
          : null;
  const visibleResponse: WorkbenchVisibleResponseView | null = runMetadata ? {
    assistantText: firstMetadataValue([visibleAssistantMessage.content, latestReply]),
    status: firstMetadataValue([visibleRuntimeStatus.status, execution.status]),
    displayState: firstMetadataValue([visibleContract.display_state, visibleRuntimeStatus.display_state, execution.status]),
    blockedReason: firstMetadataValue([visibleContract.blocked_reason]),
    retryCause: firstMetadataValue([visibleContract.retry_cause]),
    approvalRequests: visibleApprovalRequests.length > 0 ? visibleApprovalRequests : approvalRequests,
    providerBlockers: visibleProviderBlockers.length > 0 ? visibleProviderBlockers : setupBlockers,
    ticketRefs: visibleTicketRefs.length > 0 ? visibleTicketRefs : ticketKeys.map((ref) => ({ kind: "ticket", ref })),
    assetRefs: visibleAssetRefs.length > 0 ? visibleAssetRefs : assetCandidates,
    memoryRefs: visibleMemoryRefs.length > 0 ? visibleMemoryRefs : recalledMemoryRefs,
    handoffSummary: Object.keys(visibleHandoffSummary).length > 0 ? visibleHandoffSummary : workbenchHandoffSummary,
    ticketHandoffRefs: visibleTicketHandoffRefs.length > 0 ? visibleTicketHandoffRefs : asRecordArray(workbenchSnapshot?.ticketHandoffRefs),
    primaryEmployeeId: employeeId,
    primaryTicketId,
    primaryAssetTarget: assetLink,
    runtimeSessionKey,
  } : null;

  return {
    assetCandidates,
    employeeId,
    primaryTicketId,
    visibleResponse,
    latestRunProps: {
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
    },
    scopedContextProps: {
      contextExclusions,
      scopedContext,
      setupBlockers,
      universalContext,
      universalProvenance,
    },
    approvalProps: {
      approval,
      approvalGuards,
      approvalRefs,
      approvalRequests,
      approvalRecords,
      approvedCapabilities,
    },
    ticketLoopPolicyProps: {
      actions: ticketLoopPolicyActions,
      decision: ticketLoopDecision,
      policyRefs: ticketLoopPolicyRefs,
      primaryTicketId,
    },
    provenanceProps: {
      commands,
      graphitiEpisodeRefs,
      learningSummary,
      providerRefs,
      recalledAssets,
      recalledMemoryRefs,
      summary,
      nextGuidance,
    },
  };
}
