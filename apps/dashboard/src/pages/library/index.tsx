import { type ComponentType } from "react";
import { BookOpen, Brain, Plug, Wrench } from "lucide-react";
import { Button } from "../../components/ui/button";
import { navigateTo } from "../../components/shared";
import { CapabilitiesPage } from "../capabilities";
import { KnowledgePage } from "../knowledge";
import { SkillsPage } from "../skills";
import { cn } from "@/lib/utils";

type LibraryArea = "knowledge" | "skills" | "tools" | "connectors";

const AREAS: {
  key: LibraryArea;
  label: string;
  description: string;
  icon: ComponentType<{ className?: string }>;
}[] = [
  {
    key: "knowledge",
    label: "Knowledge",
    description: "Docs, Memories, Decisions, and Review Queue.",
    icon: Brain,
  },
  {
    key: "skills",
    label: "Skills",
    description: "Employee playbooks, methods, and role workflows.",
    icon: BookOpen,
  },
  {
    key: "tools",
    label: "Tools",
    description: "Executable actions, schemas, and agent executors.",
    icon: Wrench,
  },
  {
    key: "connectors",
    label: "Connectors",
    description: "MCP and external system capability sources.",
    icon: Plug,
  },
];

function areaFromRoute(value?: string | null): LibraryArea {
  return AREAS.some((area) => area.key === value) ? value as LibraryArea : "knowledge";
}

export function LibraryPage({
  selectedArea,
  selectedDetail,
}: {
  selectedArea?: string | null;
  selectedDetail?: string | null;
}) {
  const area = areaFromRoute(selectedArea);

  return (
    <div className="space-y-4">
      <section className="rounded-md border bg-background">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
          <div>
            <h3 className="text-sm font-semibold">Library</h3>
            <p className="text-xs text-muted-foreground">
              Shared AI Team assets: what employees know, how they work, what they can execute, and where capabilities come from.
            </p>
          </div>
        </div>
        <div className="grid gap-3 p-4 md:grid-cols-4">
          {AREAS.map((entry) => {
            const Icon = entry.icon;
            const active = entry.key === area;
            return (
              <button
                key={entry.key}
                type="button"
                onClick={() => navigateTo("library", entry.key)}
                className={cn(
                  "rounded-md border p-3 text-left transition-colors",
                  active ? "border-primary/40 bg-primary/10" : "bg-background hover:bg-muted",
                )}
              >
                <div className="mb-1 flex items-center gap-2 text-sm font-semibold">
                  <Icon className="h-4 w-4 text-muted-foreground" />
                  {entry.label}
                </div>
                <p className="text-xs leading-5 text-muted-foreground">{entry.description}</p>
              </button>
            );
          })}
        </div>
        {area === "knowledge" && (
          <div className="flex flex-wrap gap-2 border-t px-4 py-3">
            {[
              ["docs", "Docs"],
              ["memories", "Memories"],
              ["decisions", "Decisions"],
              ["review", "Review Queue"],
            ].map(([key, label]) => (
              <Button
                key={key}
                type="button"
                variant={(selectedDetail ?? "docs") === key ? "default" : "outline"}
                size="sm"
                onClick={() => navigateTo("library", "knowledge", key)}
              >
                {label}
              </Button>
            ))}
          </div>
        )}
      </section>

      {area === "knowledge" && <KnowledgePage selectedSection={selectedDetail} />}
      {area === "skills" && <SkillsPage selectedId={selectedDetail ?? null} />}
      {area === "tools" && <CapabilitiesPage view="tools" />}
      {area === "connectors" && <CapabilitiesPage view="connectors" />}
    </div>
  );
}
