import { useCallback, useEffect, useMemo, useState } from "react";
import { BookOpen, FileText, MessageSquare, Users } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import {
  ErrorState,
  LoadingState,
  Status,
  navigateTo,
} from "../../components/shared";
import { ResizableDetailLayout } from "../../components/resizable-layout";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../components/ui/table";
import { listChatSkills, type ChatSkillSummary } from "../../api/chat";
import { cn } from "@/lib/utils";

export function SkillsPage({ selectedId }: { selectedId: string | null }) {
  const [skills, setSkills] = useState<ChatSkillSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadSkills = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSkills(await listChatSkills());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load skills");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSkills();
  }, [loadSkills]);

  const selectedSkill = useMemo(() => {
    return skills.find((skill) => skill.id === selectedId) ?? skills[0] ?? null;
  }, [selectedId, skills]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={loadSkills} />;

  return (
    <ResizableDetailLayout
      id="aiteamos-skills-layout"
      main={(
        <section className="rounded-md border bg-background">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
          <div className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-muted-foreground" />
            <div>
              <h3 className="text-sm font-semibold">Skills</h3>
              <p className="text-xs text-muted-foreground">
                Employee methods and workflows. Executable tools, MCP, and agent executors are in{" "}
                <button
                  type="button"
                  className="font-medium text-primary hover:underline"
                  onClick={() => navigateTo("library", "tools")}
                >
                  Library / Tools
                </button>.
              </p>
            </div>
          </div>
          <Button type="button" variant="outline" onClick={() => navigateTo("chat")}>
            <MessageSquare className="h-4 w-4" />
            Ask in Chat
          </Button>
        </div>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Description</TableHead>
              <TableHead className="text-right">Employees</TableHead>
              <TableHead className="text-right">Files</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {skills.map((skill) => {
              const active = selectedSkill?.id === skill.id;
              return (
                <TableRow
                  key={skill.id}
                  className={cn("cursor-pointer", active && "bg-muted/60")}
                  onClick={() => navigateTo("library", "skills", skill.id)}
                >
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <BookOpen className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <div className="font-medium">{skill.title}</div>
                        <div className="text-xs text-muted-foreground">{skill.id}</div>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="max-w-[32rem] truncate text-muted-foreground">
                    {skill.description || "No description configured."}
                  </TableCell>
                  <TableCell className="text-right">{skill.assigned_employees.length}</TableCell>
                  <TableCell className="text-right">{skill.resources.length + 1}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
        </section>
      )}

      detail={(
        <aside className="space-y-4">
        {selectedSkill ? (
          <>
            <section className="rounded-md border bg-background p-4">
              <div className="mb-3 flex items-center gap-2">
                <BookOpen className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-sm font-semibold">{selectedSkill.title}</h3>
              </div>
              <div className="space-y-3">
                <Status label="Employees" value={selectedSkill.assigned_employees.length} />
                <Status label="Files" value={selectedSkill.resources.length + 1} />
                <Status label="ID" value={selectedSkill.id} />
              </div>
            </section>

            <section className="rounded-md border bg-background p-4">
              <h3 className="mb-3 text-sm font-semibold">Description</h3>
              <p className="text-sm leading-6 text-muted-foreground">
                {selectedSkill.description || "No description configured."}
              </p>
            </section>

            <section className="rounded-md border bg-background p-4">
              <div className="mb-3 flex items-center gap-2">
                <Users className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-sm font-semibold">Employees</h3>
              </div>
              {selectedSkill.assigned_employees.length ? (
                <div className="flex flex-wrap gap-2">
                  {selectedSkill.assigned_employees.map((employeeId) => (
                    <button key={employeeId} type="button" onClick={() => navigateTo("employees", employeeId)}>
                      <Badge variant="secondary">{employeeId}</Badge>
                    </button>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">Unassigned.</p>
              )}
            </section>

            <section className="rounded-md border bg-background p-4">
              <div className="mb-3 flex items-center gap-2">
                <FileText className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-sm font-semibold">Files</h3>
              </div>
              <div className="space-y-2 text-sm">
                <div className="rounded-md border bg-muted/30 px-3 py-2">{selectedSkill.saved_path}</div>
                {selectedSkill.resources.map((resource) => (
                  <div key={resource} className="rounded-md border bg-muted/30 px-3 py-2">
                    {resource}
                  </div>
                ))}
              </div>
            </section>
          </>
        ) : (
          <section className="rounded-md border bg-background p-4">
            <p className="text-sm text-muted-foreground">No skills configured.</p>
          </section>
        )}
        </aside>
      )}
    />
  );
}
