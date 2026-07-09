import type { ReactNode } from "react";
import { Activity, PanelRightClose } from "lucide-react";
import { Button } from "../../../components/ui/button";
import type { ChatThreadSummary } from "../../../api/chat";

function formatThreadTime(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function WorkbenchDetailsPanel({
  activeThread,
  children,
  onClose,
}: {
  activeThread: ChatThreadSummary | null;
  children: ReactNode;
  onClose: () => void;
}) {
  return (
    <aside className="flex h-full flex-col overflow-y-auto bg-sidebar">
      <section className="border-b p-2">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5">
            <Activity className="h-3.5 w-3.5 text-muted-foreground" />
            <h3 className="text-xs font-semibold">Thread Context</h3>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-7 w-7 shrink-0"
            onClick={onClose}
            title="Hide trace"
          >
            <PanelRightClose className="h-4 w-4" />
          </Button>
        </div>
        {activeThread && (
          <div className="mt-1 min-w-0 text-xs">
            <div className="truncate font-medium" title={activeThread.title}>{activeThread.title}</div>
            <div className="mt-0.5 flex min-w-0 items-center gap-2 text-[10px] text-muted-foreground">
              <span className="shrink-0">{activeThread.message_count} msgs</span>
              <span className="truncate">last {formatThreadTime(activeThread.last_message_at || activeThread.updated_at)}</span>
            </div>
          </div>
        )}
      </section>

      {children}
    </aside>
  );
}
