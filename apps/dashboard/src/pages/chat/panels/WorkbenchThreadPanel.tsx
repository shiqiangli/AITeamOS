import {
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
} from "@assistant-ui/react";
import { Archive, Bot, ClipboardList, GitBranch, MonitorCog, Send, ShieldCheck, User } from "lucide-react";
import type {
  ChatAiEngineRecord,
  ChatAiEngineSettings,
  ChatAiEngineUpdateRequest,
  ChatEmployeeSummary,
} from "../../../api/chat";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { navigateTo } from "../../../components/shared";
import { cn } from "@/lib/utils";
import type { WorkbenchVisibleResponseView } from "../runtime/workbenchRunViewModel";
import { AiEngineControlPanel } from "./AiEngineControlPanel";
import { EmployeeSelectPanel } from "./EmployeeSelectPanel";
import { TicketContextPanel } from "./TicketContextPanel";

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

function statusVariant(status: string): "outline" | "secondary" | "success" | "warning" | "danger" {
  const normalized = status.toLowerCase();
  if (["completed", "done", "handoff"].includes(normalized)) return "success";
  if (["needs_approval", "waiting_approval", "provider_blocker", "partial"].includes(normalized)) return "warning";
  if (["blocked", "failed", "error"].includes(normalized)) return "danger";
  if (["running", "resuming"].includes(normalized)) return "secondary";
  return "outline";
}

function primaryRef(items: Record<string, unknown>[]): string {
  return firstMetadataValue(items.flatMap((item) => [item.ref, item.id, item.asset_id, item.memory_id, item.candidate_id]));
}

function VisibleRuntimeResponse({
  onOpenDetails,
  response,
}: {
  onOpenDetails: () => void;
  response: WorkbenchVisibleResponseView | null;
}) {
  if (!response) return null;
  const status = firstMetadataValue([response.displayState, response.status]);
  const approval = response.approvalRequests[0] ?? {};
  const blocker = response.providerBlockers[0] ?? {};
  const handoff = response.handoffSummary;
  const handoffTarget = firstMetadataValue([handoff.to_employee_id, handoff.target_employee_id]);
  const handoffSource = firstMetadataValue([handoff.from_employee_id]);
  const approvalRef = firstMetadataValue([approval.approval_ref, approval.approval_id, approval.id]);
  const approvalReason = firstMetadataValue([approval.reason, approval.detail]);
  const blockerReason = firstMetadataValue([response.blockedReason, blocker.detail, blocker.reason]);
  const retryCause = firstMetadataValue([response.retryCause]);
  const primaryTicketRef = firstMetadataValue([response.primaryTicketId, primaryRef(response.ticketRefs)]);
  const assetTarget = response.primaryAssetTarget;
  const memoryRef = primaryRef(response.memoryRefs);
  const assetRef = primaryRef(response.assetRefs);
  const hasProviderBlocker = Boolean(blockerReason || response.providerBlockers.length > 0);
  const actionTargetCount = [
    true,
    hasProviderBlocker,
    Boolean(approvalRef),
    Boolean(primaryTicketRef),
    Boolean(handoffTarget || response.primaryEmployeeId),
    Boolean(assetTarget || assetRef || memoryRef),
    Boolean(response.runtimeSessionKey),
  ].filter(Boolean).length;
  const hasVisibleState = Boolean(
    response.assistantText
    || status
    || blockerReason
    || approvalRef
    || handoffTarget
    || response.ticketRefs.length
    || response.assetRefs.length
    || response.memoryRefs.length,
  );
  if (!hasVisibleState) return null;

  return (
    <section
      aria-label="Visible assistant response"
      aria-live="polite"
      className="mr-auto mt-4 max-w-[78ch] rounded-md border bg-card px-4 py-3 text-sm shadow-sm"
    >
      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <Bot className="h-3.5 w-3.5" />
        <span>Assistant</span>
        {status && (
          <Badge variant={statusVariant(status)} className="px-1.5 text-[10px]">
            {status}
          </Badge>
        )}
      </div>
      {response.assistantText && (
        <div className="whitespace-pre-wrap leading-6 text-foreground">
          {response.assistantText}
        </div>
      )}
      {(blockerReason || retryCause || approvalRef || handoffTarget) && (
        <div className="mt-3 space-y-1 rounded-md border bg-background/60 px-2 py-1.5 text-[11px]">
          {blockerReason && (
            <div className="flex gap-2">
              <span className="shrink-0 font-medium text-muted-foreground">Blocker</span>
              <span className="min-w-0 text-foreground">{blockerReason}</span>
            </div>
          )}
          {retryCause && (
            <div className="flex gap-2">
              <span className="shrink-0 font-medium text-muted-foreground">Retry</span>
              <span className="min-w-0 text-foreground">{retryCause}</span>
            </div>
          )}
          {approvalRef && (
            <div className="flex gap-2">
              <span className="shrink-0 font-medium text-muted-foreground">Approval</span>
              <span className="min-w-0 text-foreground">
                {approvalRef}{approvalReason ? `: ${approvalReason}` : ""}
              </span>
            </div>
          )}
          {handoffTarget && (
            <div className="flex gap-2">
              <span className="shrink-0 font-medium text-muted-foreground">Handoff</span>
              <span className="min-w-0 text-foreground">
                {handoffSource && `${handoffSource} -> `}{handoffTarget}
              </span>
            </div>
          )}
        </div>
      )}
      {(response.ticketRefs.length > 0 || response.assetRefs.length > 0 || response.memoryRefs.length > 0) && (
        <div className="mt-3 flex flex-wrap gap-1">
          {response.ticketRefs.slice(0, 4).map((ref, index) => (
            <Badge key={`visible-ticket-${metadataText(ref.ref)}-${index}`} variant="secondary" className="px-1.5 text-[10px]">
              {metadataText(ref.ref)}
            </Badge>
          ))}
          {response.assetRefs.slice(0, 4).map((ref, index) => (
            <Badge key={`visible-asset-${metadataText(ref.ref)}-${index}`} variant="outline" className="px-1.5 text-[10px]">
              {metadataText(ref.kind) !== "-" ? `${metadataText(ref.kind)}:` : ""}{metadataText(ref.ref)}
            </Badge>
          ))}
          {response.memoryRefs.slice(0, 3).map((ref, index) => (
            <Badge key={`visible-memory-${metadataText(ref.ref)}-${index}`} variant="outline" className="px-1.5 text-[10px]">
              memory:{metadataText(ref.ref)}
            </Badge>
          ))}
        </div>
      )}
      {actionTargetCount > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 gap-1 px-2 text-[10px]"
            aria-label="Open Chat run details"
            onClick={onOpenDetails}
          >
            <GitBranch className="h-3 w-3" />
            Details
          </Button>
          {hasProviderBlocker && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 gap-1 px-2 text-[10px]"
              aria-label="Open provider blocker status"
              onClick={() => navigateTo("system-status")}
            >
              <MonitorCog className="h-3 w-3" />
              Status
            </Button>
          )}
          {approvalRef && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 gap-1 px-2 text-[10px]"
              aria-label={`Open approval panel ${approvalRef}`}
              onClick={onOpenDetails}
            >
              <ShieldCheck className="h-3 w-3" />
              Approval
            </Button>
          )}
          {primaryTicketRef && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 gap-1 px-2 text-[10px]"
              aria-label={`Open visible Ticket ${primaryTicketRef}`}
              onClick={() => navigateTo("tickets", primaryTicketRef)}
            >
              <ClipboardList className="h-3 w-3" />
              Ticket
            </Button>
          )}
          {(handoffTarget || response.primaryEmployeeId) && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 gap-1 px-2 text-[10px]"
              aria-label={`Open visible Employee ${handoffTarget || response.primaryEmployeeId}`}
              onClick={() => navigateTo("employees", handoffTarget || response.primaryEmployeeId, "work")}
            >
              <User className="h-3 w-3" />
              Employee
            </Button>
          )}
          {(assetTarget || assetRef || memoryRef) && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 gap-1 px-2 text-[10px]"
              aria-label={`Open visible Asset ${assetTarget?.label || memoryRef || assetRef}`}
              onClick={() => {
                if (assetTarget?.area) navigateTo("assets", assetTarget.area, assetTarget.detail);
                else if (memoryRef) navigateTo("assets", "knowledge", `memory:${memoryRef}`);
                else if (assetRef) navigateTo("assets", "asset", assetRef);
                else navigateTo("assets");
              }}
            >
              <Archive className="h-3 w-3" />
              Assets
            </Button>
          )}
          {response.runtimeSessionKey && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 gap-1 px-2 text-[10px]"
              aria-label={`Open visible Runtime Replay ${response.runtimeSessionKey}`}
              onClick={() => navigateTo("runtime", response.runtimeSessionKey)}
            >
              <GitBranch className="h-3 w-3" />
              Replay
            </Button>
          )}
        </div>
      )}
    </section>
  );
}

function UserMessage() {
  return (
    <MessagePrimitive.Root className="ml-auto max-w-[78ch] rounded-md border bg-primary px-4 py-3 text-sm text-primary-foreground shadow-sm">
      <div className="mb-2 flex items-center gap-2 text-xs opacity-80">
        <User className="h-3.5 w-3.5" />
        <span>You</span>
      </div>
      <MessagePrimitive.Parts />
    </MessagePrimitive.Root>
  );
}

function AssistantMessage() {
  return (
    <MessagePrimitive.Root className="mr-auto max-w-[78ch] rounded-md border bg-card px-4 py-3 text-sm shadow-sm">
      <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
        <Bot className="h-3.5 w-3.5" />
        <span>Assistant</span>
      </div>
      <div className="whitespace-pre-wrap leading-6">
        <MessagePrimitive.Parts />
      </div>
    </MessagePrimitive.Root>
  );
}

export function WorkbenchThreadPanel({
  aiEngineRecords,
  aiEngineReady,
  aiEngineSaving,
  aiEngines,
  employees,
  pendingApprovalRef,
  selectedEmployee,
  ticketKey,
  visibleResponse,
  onOpenDetails,
  onAiEngineChange,
  onAiEngineConfigChange,
  onClearApprovalRef,
  onSelectEmployee,
  onTicketKeyChange,
}: {
  aiEngineRecords: ChatAiEngineRecord[];
  aiEngineReady: boolean;
  aiEngineSaving: boolean;
  aiEngines: ChatAiEngineSettings | null;
  employees: ChatEmployeeSummary[];
  pendingApprovalRef: string;
  selectedEmployee: ChatEmployeeSummary | null;
  ticketKey: string;
  visibleResponse: WorkbenchVisibleResponseView | null;
  onOpenDetails: () => void;
  onAiEngineChange: (engineId: string) => void;
  onAiEngineConfigChange: (engineId: string, payload: ChatAiEngineUpdateRequest) => Promise<void>;
  onClearApprovalRef: () => void;
  onSelectEmployee: (employeeId: string) => void;
  onTicketKeyChange: (value: string) => void;
}) {
  return (
    <ThreadPrimitive.Root className="flex min-h-0 flex-1 flex-col">
      <ThreadPrimitive.Viewport className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4">
        <ThreadPrimitive.Empty>
          <div className="flex h-full min-h-[18rem] items-center justify-center text-sm text-muted-foreground">
            {selectedEmployee ? `${selectedEmployee.display_name} is ready.` : "No employees loaded."}
          </div>
        </ThreadPrimitive.Empty>
        <div className="space-y-4">
          <ThreadPrimitive.Messages components={{ UserMessage, AssistantMessage }} />
          <VisibleRuntimeResponse response={visibleResponse} onOpenDetails={onOpenDetails} />
        </div>
        <ThreadPrimitive.ViewportFooter className="sticky bottom-0 mt-auto border-t bg-background px-4 pb-4 pt-3">
          <div className="mb-2 flex flex-wrap items-end gap-2 rounded-md border bg-muted/20 p-2">
            <div className="min-w-0 flex-[1_1_11rem]">
              <div className="mb-1 text-[10px] font-medium uppercase text-muted-foreground">Employee</div>
              <EmployeeSelectPanel
                employees={employees}
                selectedEmployee={selectedEmployee}
                onSelect={onSelectEmployee}
                className="h-9 rounded-md border bg-background"
              />
            </div>

            <AiEngineControlPanel
              aiEngines={aiEngines}
              aiEngineRecords={aiEngineRecords}
              aiEngineReady={aiEngineReady}
              aiEngineSaving={aiEngineSaving}
              onAiEngineChange={onAiEngineChange}
              onAiEngineConfigChange={onAiEngineConfigChange}
            />

            <TicketContextPanel
              pendingApprovalRef={pendingApprovalRef}
              ticketKey={ticketKey}
              onClearApprovalRef={onClearApprovalRef}
              onTicketKeyChange={onTicketKeyChange}
            />
          </div>

          <ComposerPrimitive.Root className="grid gap-2 bg-background sm:grid-cols-[minmax(0,1fr)_auto]">
            <ComposerPrimitive.Input
              aria-label="Chat message"
              placeholder={selectedEmployee ? `Message ${selectedEmployee.display_name}` : "Message"}
              submitMode="enter"
              style={{ height: 44 }}
              className="h-[2.75rem] min-h-[2.75rem] max-h-32 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            <ComposerPrimitive.Send className={cn(
              "inline-flex h-[2.75rem] min-h-[2.75rem] items-center justify-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm transition-colors",
              "hover:bg-primary/90 disabled:pointer-events-none disabled:opacity-50",
            )}>
              <Send className="h-4 w-4" />
              Send
            </ComposerPrimitive.Send>
          </ComposerPrimitive.Root>
        </ThreadPrimitive.ViewportFooter>
      </ThreadPrimitive.Viewport>
    </ThreadPrimitive.Root>
  );
}
