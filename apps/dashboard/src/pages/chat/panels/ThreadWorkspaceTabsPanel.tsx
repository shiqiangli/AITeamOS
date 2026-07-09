import {
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  X,
} from "lucide-react";
import type { ChatThreadSummary } from "../../../api/chat";
import { Button } from "../../../components/ui/button";
import { cn } from "@/lib/utils";

export function ThreadWorkspaceTabsPanel({
  activeThreadId,
  detailsPanelOpen,
  openThreads,
  threadHistoryOpen,
  threadsLoading,
  onCloseThread,
  onCreateThread,
  onOpenThread,
  onToggleDetailsPanel,
  onToggleThreadHistory,
}: {
  activeThreadId: string;
  detailsPanelOpen: boolean;
  openThreads: ChatThreadSummary[];
  threadHistoryOpen: boolean;
  threadsLoading: boolean;
  onCloseThread: (thread: ChatThreadSummary) => void;
  onCreateThread: () => void;
  onOpenThread: (thread: ChatThreadSummary) => void;
  onToggleDetailsPanel: () => void;
  onToggleThreadHistory: () => void;
}) {
  return (
    <div className="flex h-12 shrink-0 items-center gap-2 border-b px-3">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-8 w-8 shrink-0"
        onClick={onToggleThreadHistory}
        title={threadHistoryOpen ? "Hide thread history" : "Show thread history"}
      >
        {threadHistoryOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
      </Button>
      <div className="flex h-full min-w-0 flex-1 flex-nowrap items-center gap-1 overflow-hidden" role="tablist" aria-label="Chat threads">
        {threadsLoading && openThreads.length === 0 ? (
          <span className="px-2 text-xs text-muted-foreground">Loading...</span>
        ) : openThreads.length === 0 ? (
          <span className="px-2 text-xs text-muted-foreground">Open a thread from history.</span>
        ) : (
          openThreads.map((thread) => {
            const isActive = thread.id === activeThreadId;
            return (
              <div
                key={thread.id}
                className={cn(
                  "group flex h-8 min-w-0 max-w-[14rem] flex-1 basis-0 items-center rounded-md border text-xs transition-colors",
                  isActive ? "border-primary/30 bg-primary/10 text-foreground" : "bg-background text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                <button
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  onClick={() => onOpenThread(thread)}
                  className="min-w-0 flex-1 px-2 text-left"
                  title={thread.title || thread.id}
                >
                  <span className="block truncate font-medium">{thread.title || thread.id}</span>
                </button>
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    onCloseThread(thread);
                  }}
                  disabled={openThreads.length <= 1}
                  className="mr-1 shrink-0 rounded p-1 text-muted-foreground opacity-60 transition-colors hover:bg-background hover:text-foreground disabled:pointer-events-none disabled:opacity-25 group-hover:opacity-100"
                  title={openThreads.length <= 1 ? "Keep one thread open" : "Close tab"}
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            );
          })
        )}
      </div>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-8 w-8 shrink-0"
        onClick={onCreateThread}
        title="New thread"
      >
        <Plus className="h-4 w-4" />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-8 w-8 shrink-0"
        onClick={onToggleDetailsPanel}
        title={detailsPanelOpen ? "Hide trace" : "Show trace"}
      >
        {detailsPanelOpen ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}
      </Button>
    </div>
  );
}
