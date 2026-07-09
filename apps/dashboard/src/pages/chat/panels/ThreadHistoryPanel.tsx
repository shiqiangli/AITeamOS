import { useMemo } from "react";
import { PanelLeftClose, Plus, Search, Trash2 } from "lucide-react";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import type { ChatThreadSummary } from "../../../api/chat";
import { cn } from "@/lib/utils";

function formatThreadTime(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function ThreadHistoryPanel({
  activeThreadId,
  deletingThreadId,
  openThreadIds,
  query,
  threads,
  threadsLoading,
  onClose,
  onCreateThread,
  onDeleteThread,
  onOpenThread,
  onQueryChange,
}: {
  activeThreadId: string;
  deletingThreadId: string | null;
  openThreadIds: string[];
  query: string;
  threads: ChatThreadSummary[];
  threadsLoading: boolean;
  onClose: () => void;
  onCreateThread: () => void;
  onDeleteThread: (thread: ChatThreadSummary) => void;
  onOpenThread: (thread: ChatThreadSummary) => void;
  onQueryChange: (value: string) => void;
}) {
  const openSet = useMemo(() => new Set(openThreadIds), [openThreadIds]);
  const filteredThreads = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return threads;
    return threads.filter((thread) => (
      thread.title.toLowerCase().includes(normalized)
      || thread.id.toLowerCase().includes(normalized)
      || thread.employee_id.toLowerCase().includes(normalized)
    ));
  }, [query, threads]);

  return (
    <aside className="flex h-full min-w-0 flex-col bg-sidebar">
      <div className="border-b p-3">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold">Thread History</h3>
            <p className="text-xs text-muted-foreground">All history, recent first</p>
          </div>
          <Button type="button" variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={onClose} title="Collapse thread history">
            <PanelLeftClose className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex items-center gap-2 rounded-md border bg-background px-2">
          <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <input
            aria-label="Search threads"
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="Search threads"
            className="h-9 min-w-0 flex-1 bg-transparent text-xs outline-none placeholder:text-muted-foreground"
          />
        </div>
        <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
          <span>{filteredThreads.length} of {threads.length}</span>
          <Button type="button" variant="outline" size="sm" className="h-7 gap-1.5 px-2 text-xs" onClick={onCreateThread}>
            <Plus className="h-3.5 w-3.5" />
            New
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {threadsLoading ? (
          <div className="p-3 text-xs text-muted-foreground">Loading threads...</div>
        ) : filteredThreads.length === 0 ? (
          <div className="p-3 text-xs text-muted-foreground">No threads found.</div>
        ) : (
          <div className="divide-y">
            {filteredThreads.map((thread) => {
              const isActive = thread.id === activeThreadId;
              const isOpen = openSet.has(thread.id);
              const isDeleting = deletingThreadId === thread.id;
              return (
                <div
                  key={thread.id}
                  className={cn(
                    "group grid grid-cols-[minmax(0,1fr)_auto] gap-1 px-2.5 py-1.5 text-left transition-colors",
                    isActive ? "bg-primary/10" : "hover:bg-muted/70",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => onOpenThread(thread)}
                    className="min-w-0 text-left"
                    title={thread.title || thread.id}
                  >
                    <div className="flex min-w-0 items-center gap-1.5">
                      <span className="truncate text-xs font-medium">{thread.title || thread.id}</span>
                      {isOpen && <Badge variant="secondary" className="shrink-0 px-1 py-0 text-[9px] leading-3">open</Badge>}
                    </div>
                    <div className="mt-0.5 flex min-w-0 items-center gap-2 text-[10px] text-muted-foreground">
                      <span className="shrink-0">{thread.message_count} msgs</span>
                      <span className="truncate">last {formatThreadTime(thread.last_message_at || thread.updated_at)}</span>
                    </div>
                  </button>
                  <button
                    type="button"
                    onClick={() => onDeleteThread(thread)}
                    disabled={isDeleting}
                    className="self-center rounded p-1 text-muted-foreground opacity-60 transition-colors hover:bg-background hover:text-destructive group-hover:opacity-100"
                    title="Delete thread"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </aside>
  );
}
