/**
 * AITeamOS Dashboard — Home Page (PRD §3.8 value dashboard overview)
 */

import { useEffect, useState, useCallback } from "react";
import { Panel, Status, LoadingState, ErrorState, navigateTo } from "../../components/shared";
import {
  listMemories,
  listSkills,
  listMembers,
  listDepartments,
  listProjects,
  listTasks,
  fetchMemoryHealth,
  type MemorySummary,
  type SkillSummary,
  type MemberSummary,
  type DepartmentSummary,
  type ProjectSummary,
  type TaskSummary,
  type MemoryHealthResponse,
} from "../../api/client";

interface HomeData {
  memories: MemorySummary[];
  skills: SkillSummary[];
  members: MemberSummary[];
  departments: DepartmentSummary[];
  projects: ProjectSummary[];
  tasks: TaskSummary[];
  memoryHealth: MemoryHealthResponse | null;
}

export function HomePage() {
  const [data, setData] = useState<HomeData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [memories, skills, members, departments, projects, tasks, memoryHealth] =
        await Promise.all([
          listMemories({ limit: 5 }),
          listSkills({ limit: 5 }),
          listMembers({ limit: 5 }),
          listDepartments(0, 5),
          listProjects({ limit: 5 }),
          listTasks({ limit: 5 }),
          fetchMemoryHealth().catch(() => null),
        ]);
      setData({ memories, skills, members, departments, projects, tasks, memoryHealth });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={loadData} />;
  if (!data) return null;

  const runningTasks = data.tasks.filter((t) => t.state === "running").length;
  const readyTasks = data.tasks.filter((t) => t.state === "ready").length;

  return (
    <div className="grid grid-cols-1 gap-6">
      {/* Summary stats */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        <Status label="Memories" value={data.memoryHealth?.total ?? data.memories.length} />
        <Status label="Skills" value={data.skills.length} />
        <Status label="Members" value={data.members.length} />
        <Status label="Projects" value={data.projects.length} />
        <Status label="Tasks Running" value={runningTasks} tone={runningTasks > 0 ? "warn" : undefined} />
        <Status label="Tasks Ready" value={readyTasks} />
      </div>

      {/* Memory Health card */}
      {data.memoryHealth && (
        <Panel title="Memory Health">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <Status label="Active" value={data.memoryHealth.active} tone="ok" />
            <Status label="Candidate" value={data.memoryHealth.candidate} tone={data.memoryHealth.candidate > 0 ? "warn" : undefined} />
            <Status label="Needs Verify" value={data.memoryHealth.needs_verify} tone={data.memoryHealth.needs_verify > 0 ? "warn" : "ok"} />
            <Status label="Deprecated" value={data.memoryHealth.deprecated} />
          </div>
        </Panel>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Recent Memories */}
        <Panel title="Recent Memories">
          {data.memories.length === 0 ? (
            <p className="text-sm text-muted-foreground">No memories yet</p>
          ) : (
            <ul className="space-y-2 list-none">
              {data.memories.map((m) => (
                <li key={m.id} className="flex items-center justify-between text-sm cursor-pointer hover:bg-muted rounded px-2 py-1" onClick={() => navigateTo("memories", m.id)}>
                  <span className="truncate">{m.title}</span>
                  <span className="text-xs text-muted-foreground ml-2 shrink-0">{m.tier}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        {/* Recent Tasks */}
        <Panel title="Recent Tasks">
          {data.tasks.length === 0 ? (
            <p className="text-sm text-muted-foreground">No tasks yet</p>
          ) : (
            <ul className="space-y-2 list-none">
              {data.tasks.map((t) => (
                <li key={t.id} className="flex items-center justify-between text-sm cursor-pointer hover:bg-muted rounded px-2 py-1" onClick={() => navigateTo("tasks", t.id)}>
                  <span className="truncate">{t.title}</span>
                  <span className="text-xs text-muted-foreground ml-2 shrink-0">{t.state} ({t.priority})</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        {/* Recent Skills */}
        <Panel title="Recent Skills">
          {data.skills.length === 0 ? (
            <p className="text-sm text-muted-foreground">No skills yet</p>
          ) : (
            <ul className="space-y-2 list-none">
              {data.skills.map((s) => (
                <li key={s.id} className="flex items-center justify-between text-sm cursor-pointer hover:bg-muted rounded px-2 py-1" onClick={() => navigateTo("skills", s.id)}>
                  <span className="truncate">{s.name}</span>
                  <span className="text-xs text-muted-foreground ml-2 shrink-0">v{s.version} - {s.status}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        {/* Recent Members */}
        <Panel title="Recent Members">
          {data.members.length === 0 ? (
            <p className="text-sm text-muted-foreground">No members yet</p>
          ) : (
            <ul className="space-y-2 list-none">
              {data.members.map((m) => (
                <li key={m.id} className="flex items-center justify-between text-sm cursor-pointer hover:bg-muted rounded px-2 py-1" onClick={() => navigateTo("members", m.id)}>
                  <span className="truncate">{m.display_name}</span>
                  <span className="text-xs text-muted-foreground ml-2 shrink-0">{m.kind}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
