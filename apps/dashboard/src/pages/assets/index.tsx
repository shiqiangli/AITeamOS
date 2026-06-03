import { type ComponentType } from "react";
import { Archive, BookOpen, Brain, ClipboardCheck, Wrench } from "lucide-react";
import { Button } from "../../components/ui/button";
import { navigateTo } from "../../components/shared";
import { CapabilitiesPage } from "../capabilities";
import { KnowledgePage } from "../knowledge";
import { SkillsPage } from "../skills";
import { cn } from "@/lib/utils";

type AssetArea = "knowledge" | "skills" | "capabilities" | "review";

const AREAS: {
  key: AssetArea;
  label: string;
  description: string;
  icon: ComponentType<{ className?: string }>;
}[] = [
  {
    key: "knowledge",
    label: "Knowledge",
    description: "Docs, Memories, Decisions, and accepted team context.",
    icon: Brain,
  },
  {
    key: "skills",
    label: "Skills",
    description: "Employee playbooks, methods, and role workflows.",
    icon: BookOpen,
  },
  {
    key: "capabilities",
    label: "Capabilities",
    description: "Tools, MCP connectors, external systems, and agent executors.",
    icon: Wrench,
  },
  {
    key: "review",
    label: "Review Queue",
    description: "Candidate memories and knowledge updates waiting for approval.",
    icon: ClipboardCheck,
  },
];

function areaFromRoute(value?: string | null): AssetArea {
  return AREAS.some((area) => area.key === value) ? value as AssetArea : "knowledge";
}

export function AssetsPage({
  selectedArea,
  selectedDetail,
}: {
  selectedArea?: string | null;
  selectedDetail?: string | null;
}) {
  const area = areaFromRoute(selectedArea);
  const knowledgeDetail = area === "review" ? "review" : selectedDetail;

  return (
    <div className="space-y-4">
      <section className="rounded-md border bg-background">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
          <div className="flex items-center gap-2">
            <Archive className="h-4 w-4 text-muted-foreground" />
            <div>
              <h3 className="text-sm font-semibold">Assets</h3>
              <p className="text-xs text-muted-foreground">
                Team assets produced and reused through Ticket flow: knowledge, skills, capabilities, and reviewable candidates.
              </p>
            </div>
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
                onClick={() => navigateTo("assets", entry.key)}
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
        {(area === "knowledge" || area === "review") && (
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
                variant={(knowledgeDetail ?? "docs") === key ? "default" : "outline"}
                size="sm"
                onClick={() => navigateTo("assets", key === "review" ? "review" : "knowledge", key)}
              >
                {label}
              </Button>
            ))}
          </div>
        )}
      </section>

      {(area === "knowledge" || area === "review") && <KnowledgePage selectedSection={knowledgeDetail} />}
      {area === "skills" && <SkillsPage selectedId={selectedDetail ?? null} />}
      {area === "capabilities" && <CapabilitiesPage view="all" />}
    </div>
  );
}
