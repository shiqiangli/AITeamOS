import { Brain, MessageSquare } from "lucide-react";
import { Button } from "../../components/ui/button";
import { navigateTo, Status } from "../../components/shared";

export function MemoryPage() {
  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <section className="rounded-md border bg-background">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
          <div className="flex items-center gap-2">
            <Brain className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold">Memory</h3>
          </div>
          <Button type="button" variant="outline" onClick={() => navigateTo("chat")}>
            <MessageSquare className="h-4 w-4" />
            Ask in Chat
          </Button>
        </div>
        <div className="p-4">
          <div className="rounded-md border bg-muted/30 px-4 py-8 text-center text-sm text-muted-foreground">
            No memory candidates.
          </div>
        </div>
      </section>

      <aside className="space-y-4">
        <section className="rounded-md border bg-background p-4">
          <div className="mb-3 flex items-center gap-2">
            <Brain className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold">Adapter</h3>
          </div>
          <div className="space-y-3">
            <Status label="Backend" value="LangGraph Store" />
            <Status label="Candidates" value={0} />
            <Status label="Approved" value={0} />
          </div>
        </section>
      </aside>
    </div>
  );
}
