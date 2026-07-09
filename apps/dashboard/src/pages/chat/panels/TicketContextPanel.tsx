import { Check, GitBranch, X } from "lucide-react";

export function TicketContextPanel({
  pendingApprovalRef,
  ticketKey,
  onClearApprovalRef,
  onTicketKeyChange,
}: {
  pendingApprovalRef: string;
  ticketKey: string;
  onClearApprovalRef: () => void;
  onTicketKeyChange: (value: string) => void;
}) {
  return (
    <>
      <label className="min-w-0 flex-[1_1_9rem]">
        <span className="mb-1 block text-[10px] font-medium uppercase leading-none text-muted-foreground">Ticket</span>
        <div className="flex h-9 items-center gap-1 rounded-md border border-input bg-background px-2 shadow-sm">
          <GitBranch className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <input
            aria-label="Ticket key"
            value={ticketKey}
            onChange={(event) => onTicketKeyChange(event.target.value)}
            placeholder="Ticket key"
            className="h-full min-w-0 flex-1 bg-transparent text-xs outline-none placeholder:text-muted-foreground"
          />
        </div>
      </label>

      {pendingApprovalRef && (
        <div className="min-w-0 flex-[1_1_9rem]">
          <div className="mb-1 text-[10px] font-medium uppercase leading-none text-muted-foreground">Approval</div>
          <div className="flex h-9 min-w-0 items-center gap-1 rounded-md border border-input bg-background px-2 shadow-sm">
            <Check className="h-3.5 w-3.5 shrink-0 text-green-600" />
            <span className="min-w-0 flex-1 truncate text-xs" title={pendingApprovalRef}>
              {pendingApprovalRef}
            </span>
            <button
              type="button"
              onClick={onClearApprovalRef}
              className="shrink-0 rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              title="Clear approval"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        </div>
      )}
    </>
  );
}
