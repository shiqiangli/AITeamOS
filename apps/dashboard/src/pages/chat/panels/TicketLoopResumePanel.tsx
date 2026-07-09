import { useCallback, useEffect, useMemo, useState } from "react";
import { ExternalLink, GitBranch, RefreshCw } from "lucide-react";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { navigateTo } from "../../../components/shared";
import {
  getTicketLoopTimeline,
  resumeTicketLoop,
  type TicketLoopResumeResponse,
  type TicketLoopRetryRequirement,
  type TicketLoopTimelineResponse,
} from "../../../api/tickets";

type TicketLoopResumeAction = "resume" | "retry_after_changes" | "retry_after_evidence";

function actionForStatus(status: string): TicketLoopResumeAction {
  if (status === "waiting_changes") return "retry_after_changes";
  if (status === "waiting_evidence") return "retry_after_evidence";
  return "resume";
}

function actionLabel(status: string): string {
  if (status === "waiting_changes") return "Retry after changes";
  if (status === "waiting_evidence") return "Retry after evidence";
  return "Resume loop";
}

function statusVariant(status: string): "success" | "warning" | "secondary" | "outline" {
  if (status === "in_progress" || status === "ready_to_resume") return "success";
  if (status === "waiting_changes" || status === "waiting_evidence" || status === "blocked" || status === "failed") return "warning";
  if (status) return "secondary";
  return "outline";
}

function navigateToTimelineRoute(route: string): void {
  const [page, id, detail] = route.split("/").filter(Boolean);
  if (!page) return;
  navigateTo(page, id, detail);
}

function RetryRequirementList({ requirements }: { requirements: TicketLoopRetryRequirement[] }) {
  if (requirements.length === 0) return null;
  const satisfiedCount = requirements.filter((item) => item.satisfied).length;
  return (
    <div className="rounded border bg-background/60 px-2 py-1.5">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="text-[10px] font-medium uppercase text-muted-foreground">Retry Preflight</span>
        <Badge variant={satisfiedCount === requirements.length ? "success" : "warning"} className="px-1.5 text-[10px]">
          {satisfiedCount}/{requirements.length}
        </Badge>
      </div>
      <div className="space-y-1">
        {requirements.map((requirement) => (
          <div key={requirement.id} className="min-w-0 rounded border bg-card px-2 py-1">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate text-[10px] font-medium" title={requirement.label}>{requirement.label}</div>
                {requirement.detail ? (
                  <div className="mt-0.5 truncate text-[10px] text-muted-foreground" title={requirement.detail}>
                    {requirement.detail}
                  </div>
                ) : null}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <Badge variant={requirement.satisfied ? "success" : "warning"} className="px-1.5 text-[10px]">
                  {requirement.satisfied ? "ready" : "needed"}
                </Badge>
                {requirement.target_route ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    aria-label={`Open ${requirement.label}`}
                    title={`Open ${requirement.label}`}
                    onClick={() => navigateToTimelineRoute(requirement.target_route)}
                  >
                    <ExternalLink className="h-3 w-3" />
                  </Button>
                ) : null}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function TicketLoopResumePanel({
  employeeId,
  selectedAiEngine,
  ticketId,
}: {
  employeeId: string;
  selectedAiEngine: string;
  ticketId: string;
}) {
  const [timeline, setTimeline] = useState<TicketLoopTimelineResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [resumeResult, setResumeResult] = useState<TicketLoopResumeResponse | null>(null);
  const [resumeError, setResumeError] = useState("");
  const [resuming, setResuming] = useState(false);

  const loadTimeline = useCallback(async () => {
    if (!ticketId) {
      setTimeline(null);
      return;
    }
    setLoading(true);
    try {
      setTimeline(await getTicketLoopTimeline(ticketId));
    } catch {
      setTimeline(null);
    } finally {
      setLoading(false);
    }
  }, [ticketId]);

  useEffect(() => {
    setResumeResult(null);
    setResumeError("");
    void loadTimeline();
  }, [loadTimeline]);

  const summary = timeline?.summary ?? null;
  const status = summary?.status ?? "";
  const requirements = summary?.retry_requirements ?? [];
  const retryPreflightReady = requirements.length === 0 || requirements.every((item) => item.satisfied);
  const action = useMemo(() => actionForStatus(status), [status]);
  const buttonLabel = actionLabel(status);
  const canResume = Boolean(summary?.can_resume) && retryPreflightReady;
  const shouldRender = Boolean(
    ticketId
    && (
      loading
      || resumeResult
      || resumeError
      || summary?.can_resume
      || summary?.waiting_reason
      || requirements.length > 0
    ),
  );

  async function queueResume() {
    if (!ticketId || !canResume || resuming) return;
    setResuming(true);
    setResumeError("");
    try {
      const response = await resumeTicketLoop(ticketId, {
        action,
        employee_id: employeeId || "clara",
        message: `Resume Ticket ${ticketId} from Chat Workbench.`,
        max_steps: 2,
        selected_executor: "universal_employee_agent",
        selected_ai_engine: selectedAiEngine || "universal_employee_agent",
        reason: `Chat Workbench requested governed Ticket loop ${action}.`,
      });
      setResumeResult(response);
      await loadTimeline();
    } catch (error) {
      setResumeResult(null);
      setResumeError(error instanceof Error ? error.message : "Ticket loop resume was blocked.");
    } finally {
      setResuming(false);
    }
  }

  if (!shouldRender) return null;

  return (
    <section className="border-b p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          <GitBranch className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <h3 className="truncate text-xs font-semibold">Ticket Loop</h3>
        </div>
        {status ? <Badge variant={statusVariant(status)} className="px-1.5 text-[10px]">{status}</Badge> : null}
      </div>

      <div className="space-y-2 text-xs">
        {summary?.next_action || summary?.waiting_reason ? (
          <div className="rounded border bg-background/60 px-2 py-1.5">
            {summary.next_action ? <div className="font-medium">{summary.next_action}</div> : null}
            {summary.waiting_reason ? (
              <div className="mt-0.5 text-[11px] leading-4 text-muted-foreground">{summary.waiting_reason}</div>
            ) : null}
          </div>
        ) : loading ? (
          <div className="rounded border bg-background/60 px-2 py-1.5 text-[11px] text-muted-foreground">Loading Ticket loop timeline...</div>
        ) : null}

        <RetryRequirementList requirements={requirements} />

        {resumeError ? (
          <div className="rounded border bg-background/60 px-2 py-1.5 text-[11px] text-orange-600">{resumeError}</div>
        ) : resumeResult ? (
          <div className="rounded border bg-background/60 px-2 py-1.5">
            <div className="text-[11px] text-muted-foreground">{resumeResult.detail}</div>
            <div className="mt-1 flex flex-wrap gap-1">
              <Badge variant="outline" className="px-1.5 text-[10px]">From {resumeResult.previous_status}</Badge>
              <Badge variant="secondary" className="px-1.5 text-[10px]">Queued {resumeResult.queue_item.run_id}</Badge>
            </div>
          </div>
        ) : null}

        {(summary?.can_resume || resuming) ? (
          <div className="flex justify-end">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 gap-1 px-2 text-[10px]"
              disabled={!canResume || resuming}
              aria-label={`${buttonLabel} ${ticketId}`}
              onClick={() => void queueResume()}
            >
              <RefreshCw className="h-3 w-3" />
              {resuming ? "Queueing" : buttonLabel}
            </Button>
          </div>
        ) : null}
      </div>
    </section>
  );
}
