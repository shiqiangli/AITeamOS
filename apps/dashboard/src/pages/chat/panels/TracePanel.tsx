import { Activity } from "lucide-react";
import type { ChatTraceEvent } from "../../../api/chat";

function dataPreview(value: unknown): string {
  if (!value || typeof value !== "object") return "";
  const json = JSON.stringify(value);
  return json.length > 360 ? `${json.slice(0, 357)}...` : json;
}

export function TracePanel({
  savedPaths,
  traceEvents,
}: {
  savedPaths: Record<string, string>;
  traceEvents: ChatTraceEvent[];
}) {
  return (
    <section className="p-3">
      <div className="mb-2 flex items-center gap-1.5">
        <Activity className="h-3.5 w-3.5 text-muted-foreground" />
        <h3 className="text-xs font-semibold">Trace</h3>
      </div>
      {traceEvents.length === 0 ? (
        <p className="text-xs text-muted-foreground">No trace events.</p>
      ) : (
        <ol className="space-y-1.5">
          {traceEvents.map((event, index) => {
            const preview = event.event.startsWith("command.") ? dataPreview(event.data) : "";
            return (
              <li key={`${event.event}-${index}`} className="rounded border px-2 py-1.5">
                <div className="text-[10px] font-medium text-muted-foreground">{event.event}</div>
                <div className="text-xs">{event.detail}</div>
                {preview && (
                  <pre className="mt-1 max-h-28 overflow-auto rounded bg-muted p-1 text-[10px] leading-4 text-muted-foreground">
                    {preview}
                  </pre>
                )}
              </li>
            );
          })}
        </ol>
      )}
      {Object.entries(savedPaths).length > 0 && (
        <div className="mt-3 space-y-1">
          {Object.entries(savedPaths).map(([key, value]) => (
            <div key={key} className="min-w-0">
              <div className="text-[10px] uppercase text-muted-foreground">{key}</div>
              <div className="truncate text-xs font-medium" title={value}>{value}</div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
