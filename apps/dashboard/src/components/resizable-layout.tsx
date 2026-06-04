import { ReactNode, useEffect, useState } from "react";
import { Group, Panel, Separator } from "react-resizable-panels";
import { cn } from "@/lib/utils";

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const media = window.matchMedia(query);
    const update = () => setMatches(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, [query]);

  return matches;
}

export function ResizeHandle({ className }: { className?: string }) {
  return (
    <Separator
      className={cn(
        "relative w-1 shrink-0 bg-border transition-colors hover:bg-primary/50",
        "data-[resize-handle-active]:bg-primary/60",
        className,
      )}
    />
  );
}

export function ResizableDetailLayout({
  detail,
  detailDefaultSize = 28,
  detailMaxSize = "40rem",
  detailMinSize = "18rem",
  id,
  main,
  mainDefaultSize = 72,
  mainMinSize = "30rem",
}: {
  detail: ReactNode;
  detailDefaultSize?: number | string;
  detailMaxSize?: number | string;
  detailMinSize?: number | string;
  id: string;
  main: ReactNode;
  mainDefaultSize?: number | string;
  mainMinSize?: number | string;
}) {
  const desktop = useMediaQuery("(min-width: 1280px)");

  if (!desktop) {
    return (
      <div className="grid gap-6">
        {main}
        {detail}
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-8rem)] min-h-[32rem] overflow-hidden">
      <Group id={id} orientation="horizontal" className="h-full">
        <Panel defaultSize={mainDefaultSize} minSize={mainMinSize} className="min-w-0 overflow-auto pr-3">
          {main}
        </Panel>
        <ResizeHandle className="mx-2" />
        <Panel
          defaultSize={detailDefaultSize}
          minSize={detailMinSize}
          maxSize={detailMaxSize}
          className="min-w-0 overflow-auto pl-3"
        >
          {detail}
        </Panel>
      </Group>
    </div>
  );
}
