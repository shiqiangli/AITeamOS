/**
 * AITeamOS Dashboard - Member Management Page
 */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Activity,
  Archive,
  Brain,
  Clock,
  ExternalLink,
  FileText,
  ListTodo,
  Plus,
  Save,
  Trash2,
  UserRound,
  Wrench,
} from "lucide-react";
import { Panel, DataTable, Definition, FormField, LoadingState, ErrorState, navigateTo, ComboInput, Status, type Column } from "../../components/shared";
import { useToast } from "../../components/ui/use-toast";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import { Textarea } from "../../components/ui/textarea";
import { Badge } from "../../components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../../components/ui/tabs";
import {
  listMembers,
  listDepartments,
  listTasks,
  listSkills,
  getMemberDetail,
  getMemberProfileView,
  getMemberPromptPreview,
  createMember,
  assignSkillToMember,
  deleteMember,
  updateMemberPromptTemplate,
  type MemberSummary,
  type MemberDetail,
  type MemberProfileView,
  type DepartmentSummary,
  type TaskSummary,
  type SkillSummary,
  type PromptPreviewResponse,
} from "../../api/client";

type MemberActivity = {
  id: string;
  kind: string;
  label: string;
  at: string | null;
  targetPage?: string;
  targetId?: string;
};

function formatShortId(id: string | null | undefined): string {
  if (!id) return "-";
  return id.length > 12 ? `${id.slice(0, 8)}...` : id;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString();
}

function statusVariant(state: string): "success" | "warning" | "secondary" | "danger" {
  switch (state) {
    case "done":
      return "success";
    case "running":
    case "verifying":
    case "in_review":
      return "warning";
    case "failed":
    case "cancelled":
      return "danger";
    default:
      return "secondary";
  }
}

function activityTone(count: number): string {
  if (count >= 4) return "bg-primary";
  if (count >= 2) return "bg-primary/70";
  if (count === 1) return "bg-primary/35";
  return "bg-muted";
}

function pageForTarget(kind: string | null | undefined): string | undefined {
  switch (kind) {
    case "task":
      return "tasks";
    case "skill":
      return "skills";
    case "memory":
      return "memories";
    case "project":
      return "projects";
    default:
      return undefined;
  }
}

function buildActivityEvents(
  detail: MemberDetail,
  tasks: TaskSummary[],
  profile: MemberProfileView | null,
): MemberActivity[] {
  const events: MemberActivity[] = [];
  const seen = new Set<string>();

  for (const activity of profile?.activities ?? []) {
    const targetPage = pageForTarget(activity.target_kind);
    events.push({
      id: `activity-${activity.id}`,
      kind: activity.kind,
      label: activity.label,
      at: activity.occurred_at,
      targetPage,
      targetId: targetPage ? activity.target_id ?? undefined : undefined,
    });
    seen.add(`activity-${activity.id}`);
  }

  if (detail.created_at) {
    events.push({
      id: `profile-${detail.id}`,
      kind: "profile",
      label: "Profile created",
      at: detail.created_at,
    });
  }
  for (const task of tasks) {
    if (seen.has(`task-${task.id}`)) continue;
    events.push({
      id: `task-${task.id}`,
      kind: "task",
      label: task.title,
      at: task.created_at,
      targetPage: "tasks",
      targetId: task.id,
    });
  }
  const capabilityChanges = profile?.capability_changes ?? [];
  if (capabilityChanges.length > 0) {
    for (const change of capabilityChanges) {
      const targetPage = pageForTarget(change.target_kind);
      events.push({
        id: `change-${change.id}`,
        kind: change.kind,
        label: change.label,
        at: change.occurred_at,
        targetPage,
        targetId: targetPage ? change.target_id : undefined,
      });
    }
    return events.sort((a, b) => {
      const aTime = a.at ? new Date(a.at).getTime() : 0;
      const bTime = b.at ? new Date(b.at).getTime() : 0;
      return bTime - aTime;
    });
  }

  for (const skillId of detail.base_skill_set ?? []) {
    events.push({
      id: `skill-${skillId}`,
      kind: "skill",
      label: formatShortId(skillId),
      at: null,
      targetPage: "skills",
      targetId: skillId,
    });
  }
  for (const memoryId of detail.assigned_memories ?? []) {
    events.push({
      id: `memory-${memoryId}`,
      kind: "memory",
      label: formatShortId(memoryId),
      at: null,
      targetPage: "memories",
      targetId: memoryId,
    });
  }
  return events.sort((a, b) => {
    const aTime = a.at ? new Date(a.at).getTime() : 0;
    const bTime = b.at ? new Date(b.at).getTime() : 0;
    return bTime - aTime;
  });
}

function buildActivityCalendar(events: MemberActivity[]) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const start = new Date(today);
  start.setDate(today.getDate() - 83);

  const counts = new Map<string, number>();
  for (const event of events) {
    if (!event.at) continue;
    const date = new Date(event.at);
    if (Number.isNaN(date.getTime())) continue;
    date.setHours(0, 0, 0, 0);
    if (date < start || date > today) continue;
    const key = date.toISOString().slice(0, 10);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }

  return Array.from({ length: 12 }, (_, weekIndex) =>
    Array.from({ length: 7 }, (_, dayIndex) => {
      const date = new Date(start);
      date.setDate(start.getDate() + weekIndex * 7 + dayIndex);
      const key = date.toISOString().slice(0, 10);
      return {
        key,
        label: date.toLocaleDateString(),
        count: counts.get(key) ?? 0,
      };
    }),
  );
}

function EmptyInline({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-md border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
      {children}
    </div>
  );
}

function LinkBadge({
  id,
  page,
  label,
  meta,
  icon,
}: {
  id: string;
  page: string;
  label?: string;
  meta?: string | null;
  icon: ReactNode;
}) {
  return (
    <button
      type="button"
      className="inline-flex min-w-0 items-center gap-1 rounded-md border px-2 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted"
      onClick={() => navigateTo(page, id)}
      title={id}
    >
      {icon}
      <span className="truncate">{label || formatShortId(id)}</span>
      {meta && <span className="text-muted-foreground">{meta}</span>}
      <ExternalLink className="h-3 w-3 text-muted-foreground" />
    </button>
  );
}

function ActivityHeatmap({ events }: { events: MemberActivity[] }) {
  const weeks = useMemo(() => buildActivityCalendar(events), [events]);
  const total = events.filter((event) => event.at).length;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium">Activity</span>
        </div>
        <span className="text-xs text-muted-foreground">{total} dated events</span>
      </div>
      <div className="overflow-x-auto">
        <div className="grid w-max grid-flow-col grid-rows-7 gap-1">
          {weeks.flat().map((day) => (
            <span
              key={day.key}
              className={`h-3 w-3 rounded-[3px] ${activityTone(day.count)}`}
              title={`${day.label}: ${day.count}`}
              aria-label={`${day.label}: ${day.count} activities`}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function MemberDetailSurface({
  selectedId,
  detail,
  profile,
  tasks,
  departments,
  detailError,
  tasksLoading,
  onClose,
  onDelete,
  onAssignSkill,
  onReload,
  availableSkills,
}: {
  selectedId: string | null;
  detail: MemberDetail | null;
  profile: MemberProfileView | null;
  tasks: TaskSummary[];
  departments: DepartmentSummary[];
  detailError: string | null;
  tasksLoading: boolean;
  onClose: () => void;
  onDelete: () => void;
  onAssignSkill: (skillName: string) => Promise<void>;
  onReload: (id: string) => Promise<void>;
  availableSkills: SkillSummary[];
}) {
  const [assignSkillName, setAssignSkillName] = useState("");
  const [showAssignSkill, setShowAssignSkill] = useState(false);
  const [promptEditing, setPromptEditing] = useState(false);
  const [promptDraft, setPromptDraft] = useState("");
  const [promptPreview, setPromptPreview] = useState<PromptPreviewResponse | null>(null);
  const [promptPreviewLoading, setPromptPreviewLoading] = useState(false);
  const [promptSaving, setPromptSaving] = useState(false);
  const [promptMode, setPromptMode] = useState<"edit" | "preview">("edit");
  const { toast } = useToast();

  useEffect(() => {
    setAssignSkillName("");
    setShowAssignSkill(false);
    setPromptEditing(false);
    setPromptDraft("");
    setPromptPreview(null);
    setPromptMode("edit");
  }, [selectedId]);

  const deptName = useCallback((id: string | null) => {
    if (!id) return "-";
    const d = departments.find((dep) => dep.id === id);
    return d ? d.name : formatShortId(id);
  }, [departments]);

  const events = useMemo(() => (detail ? buildActivityEvents(detail, tasks, profile) : []), [detail, profile, tasks]);
  const doneTasks = profile?.stats.done_task_count ?? tasks.filter((task) => task.state === "done").length;
  const activeTasks = profile?.stats.active_task_count ?? tasks.filter((task) => !["done", "failed", "cancelled"].includes(task.state)).length;
  const lastDatedEvent = events.find((event) => event.at);
  const doneRate = profile?.stats.done_rate != null
    ? `${Math.round(profile.stats.done_rate * 100)}%`
    : tasks.length > 0 ? `${Math.round((doneTasks / tasks.length) * 100)}%` : "-";
  const lastActivityAt = profile?.stats.last_activity_at ?? lastDatedEvent?.at ?? null;
  const skillRecords = profile?.skills ?? [];
  const memoryRecords = profile?.memories ?? [];
  const projectRecords = profile?.projects ?? [];
  const capabilityChanges = profile?.capability_changes ?? [];

  async function handleAssignSkill() {
    if (!assignSkillName.trim()) return;
    await onAssignSkill(assignSkillName.trim());
    setAssignSkillName("");
    setShowAssignSkill(false);
  }

  async function handleSavePrompt() {
    if (!selectedId) return;
    setPromptSaving(true);
    try {
      await updateMemberPromptTemplate(selectedId, promptDraft);
      setPromptEditing(false);
      await onReload(selectedId);
      toast({ title: "Prompt template saved" });
    } catch (err) {
      toast({ title: "Save failed", description: err instanceof Error ? err.message : "Unknown error", variant: "danger" });
    } finally {
      setPromptSaving(false);
    }
  }

  async function handleLoadPreview() {
    if (!selectedId) return;
    setPromptPreviewLoading(true);
    try {
      const preview = await getMemberPromptPreview(selectedId);
      setPromptPreview(preview);
    } catch {
      setPromptPreview(null);
    } finally {
      setPromptPreviewLoading(false);
    }
  }

  function handleStartEditPrompt() {
    setPromptDraft(detail?.prompt_template ?? "");
    setPromptEditing(true);
    setPromptMode("edit");
  }

  return (
    <Dialog open={Boolean(selectedId)} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="block max-h-[calc(100vh-2rem)] w-[calc(100vw-2rem)] max-w-6xl overflow-hidden p-0">
        {detailError && (
          <div className="space-y-4 p-6">
            <DialogHeader>
              <DialogTitle>Member Details</DialogTitle>
              <DialogDescription>Member detail could not be loaded.</DialogDescription>
            </DialogHeader>
            <ErrorState message={detailError} />
          </div>
        )}

        {!detail && !detailError && (
          <div className="space-y-4 p-6">
            <DialogHeader>
              <DialogTitle>Member Details</DialogTitle>
              <DialogDescription>Loading member detail.</DialogDescription>
            </DialogHeader>
            <LoadingState />
          </div>
        )}

        {detail && (
          <div className="flex max-h-[calc(100vh-2rem)] flex-col">
            <div className="border-b px-6 py-5">
              <DialogHeader>
                <DialogTitle className="flex flex-wrap items-center gap-3 text-xl">
                  <span>{detail.display_name}</span>
                  <Badge variant={detail.is_archived ? "secondary" : "success"}>
                    {detail.is_archived ? "archived" : "active"}
                  </Badge>
                  <Badge variant="secondary">{detail.kind}</Badge>
                </DialogTitle>
                <DialogDescription>
                  {detail.role || "Member"} in {deptName(detail.department_id)}
                </DialogDescription>
              </DialogHeader>

              <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                <Status label="Active Tasks" value={activeTasks} tone={activeTasks > 0 ? "warn" : undefined} />
                <Status label="Done Rate" value={doneRate} tone={doneTasks > 0 ? "ok" : undefined} />
                <Status label="Skills" value={profile?.stats.skill_count ?? detail.base_skill_set?.length ?? 0} />
                <Status label="Memories" value={profile?.stats.memory_count ?? detail.assigned_memories?.length ?? 0} />
                <Status label="Last Activity" value={lastActivityAt ? formatDate(lastActivityAt) : "-"} />
              </div>
            </div>

            <div className="overflow-y-auto px-6 py-5">
              <Tabs defaultValue="overview" className="space-y-5">
                <TabsList className="flex h-auto flex-wrap justify-start">
                  <TabsTrigger value="overview">Overview</TabsTrigger>
                  <TabsTrigger value="knowledge">Knowledge & Skills</TabsTrigger>
                  <TabsTrigger value="work">Work</TabsTrigger>
                  <TabsTrigger value="changes">Change Log</TabsTrigger>
                  <TabsTrigger value="prompt">Prompt</TabsTrigger>
                  <TabsTrigger value="profile">Profile</TabsTrigger>
                </TabsList>

                <TabsContent value="overview" className="space-y-5">
                  <ActivityHeatmap events={events} />
                  <div className="space-y-3">
                    <div className="flex items-center gap-2">
                      <Clock className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm font-medium">Timeline</span>
                    </div>
                    {events.length === 0 ? (
                      <EmptyInline>No activity recorded</EmptyInline>
                    ) : (
                      <div className="divide-y rounded-md border">
                        {events.slice(0, 12).map((event) => (
                          <div key={event.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <Badge variant="secondary">{event.kind}</Badge>
                                <span className="truncate font-medium">{event.label}</span>
                              </div>
                              <p className="mt-1 text-xs text-muted-foreground">{formatDate(event.at)}</p>
                            </div>
                            {event.targetPage && event.targetId && (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => navigateTo(event.targetPage!, event.targetId!)}
                              >
                                <ExternalLink className="h-4 w-4" />
                              </Button>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </TabsContent>

                <TabsContent value="knowledge" className="space-y-5">
                  <section className="space-y-3">
                    <div className="flex items-center gap-2">
                      <Wrench className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm font-medium">Skills</span>
                    </div>
                    {skillRecords.length ? (
                      <div className="flex flex-wrap gap-2">
                        {skillRecords.map((skill) => (
                          <LinkBadge
                            key={skill.id}
                            id={skill.id}
                            page="skills"
                            label={skill.name}
                            meta={skill.version}
                            icon={<Wrench className="h-3 w-3" />}
                          />
                        ))}
                      </div>
                    ) : detail.base_skill_set?.length ? (
                      <div className="flex flex-wrap gap-2">
                        {detail.base_skill_set.map((skillId) => (
                          <LinkBadge key={skillId} id={skillId} page="skills" icon={<Wrench className="h-3 w-3" />} />
                        ))}
                      </div>
                    ) : (
                      <EmptyInline>No skills assigned</EmptyInline>
                    )}
                  </section>

                  <section className="space-y-3">
                    <div className="flex items-center gap-2">
                      <Brain className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm font-medium">Memories</span>
                    </div>
                    {memoryRecords.length ? (
                      <div className="flex flex-wrap gap-2">
                        {memoryRecords.map((memory) => (
                          <LinkBadge
                            key={memory.id}
                            id={memory.id}
                            page="memories"
                            label={memory.title}
                            meta={memory.lifecycle_state}
                            icon={<Brain className="h-3 w-3" />}
                          />
                        ))}
                      </div>
                    ) : detail.assigned_memories?.length ? (
                      <div className="flex flex-wrap gap-2">
                        {detail.assigned_memories.map((memoryId) => (
                          <LinkBadge key={memoryId} id={memoryId} page="memories" icon={<Brain className="h-3 w-3" />} />
                        ))}
                      </div>
                    ) : (
                      <EmptyInline>No memories assigned</EmptyInline>
                    )}
                  </section>

                  <div className="flex flex-wrap items-center gap-2 border-t pt-4">
                    {showAssignSkill ? (
                      <>
                        <ComboInput
                          value={assignSkillName}
                          onChange={setAssignSkillName}
                          options={availableSkills.map((skill) => ({
                            value: skill.name,
                            label: `${skill.name} (${skill.version})`,
                          }))}
                          placeholder="Select or type skill name"
                          className="w-64"
                        />
                        <Button variant="recommended" disabled={!assignSkillName.trim()} onClick={handleAssignSkill}>
                          <Wrench className="h-4 w-4" />
                          Confirm
                        </Button>
                        <Button variant="outline" onClick={() => { setShowAssignSkill(false); setAssignSkillName(""); }}>
                          Cancel
                        </Button>
                      </>
                    ) : (
                      <Button variant="outline" onClick={() => setShowAssignSkill(true)}>
                        <Wrench className="h-4 w-4" />
                        Assign Skill
                      </Button>
                    )}
                  </div>
                </TabsContent>

                <TabsContent value="work" className="space-y-5">
                  <section className="space-y-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <ListTodo className="h-4 w-4 text-muted-foreground" />
                        <span className="text-sm font-medium">Tasks</span>
                      </div>
                      {tasksLoading && <span className="text-xs text-muted-foreground">Loading</span>}
                    </div>
                    {tasks.length ? (
                      <div className="divide-y rounded-md border">
                        {tasks.map((task) => (
                          <button
                            key={task.id}
                            type="button"
                            className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm transition-colors hover:bg-muted"
                            onClick={() => navigateTo("tasks", task.id)}
                          >
                            <span className="min-w-0 truncate font-medium">{task.title}</span>
                            <span className="flex shrink-0 items-center gap-2">
                              <Badge variant={statusVariant(task.state)}>{task.state}</Badge>
                              <ExternalLink className="h-4 w-4 text-muted-foreground" />
                            </span>
                          </button>
                        ))}
                      </div>
                    ) : (
                      <EmptyInline>No task records</EmptyInline>
                    )}
                  </section>

                  <section className="space-y-3">
                    <div className="flex items-center gap-2">
                      <Archive className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm font-medium">Projects</span>
                    </div>
                    {projectRecords.length ? (
                      <div className="divide-y rounded-md border">
                        {projectRecords.map((project) => (
                          <button
                            key={project.id}
                            type="button"
                            className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm transition-colors hover:bg-muted"
                            onClick={() => navigateTo("projects", project.id)}
                          >
                            <span className="min-w-0">
                              <span className="block truncate font-medium">{project.name}</span>
                              <span className="block text-xs text-muted-foreground">{project.role || "contributor"}</span>
                            </span>
                            <span className="flex shrink-0 items-center gap-2">
                              {project.status && <Badge variant="secondary">{project.status}</Badge>}
                              <ExternalLink className="h-4 w-4 text-muted-foreground" />
                            </span>
                          </button>
                        ))}
                      </div>
                    ) : (
                      <EmptyInline>No linked project records</EmptyInline>
                    )}
                  </section>
                </TabsContent>

                <TabsContent value="changes" className="space-y-5">
                  <section className="space-y-3">
                    <div className="flex items-center gap-2">
                      <Activity className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm font-medium">Capability Changes</span>
                    </div>
                    {capabilityChanges.length ? (
                      <div className="divide-y rounded-md border">
                        {capabilityChanges.map((change) => (
                          <div key={change.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
                            <div className="min-w-0">
                              <Badge variant="secondary">{change.kind}</Badge>
                              <span className="ml-2 font-medium">{change.label}</span>
                              <p className="mt-1 text-xs text-muted-foreground">{formatDate(change.occurred_at)}</p>
                            </div>
                            {pageForTarget(change.target_kind) && (
                              <Button variant="outline" size="sm" onClick={() => navigateTo(pageForTarget(change.target_kind)!, change.target_id)}>
                                <ExternalLink className="h-4 w-4" />
                              </Button>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <EmptyInline>No capability changes recorded</EmptyInline>
                    )}
                  </section>
                </TabsContent>

                <TabsContent value="prompt" className="space-y-5">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm font-medium">Prompt Template</span>
                      <span className="text-xs text-muted-foreground">
                        Variables: {"{member_name}"}, {"{member_role}"}, {"{member_kind}"}, {"{skill_descriptions}"}, {"{memory_summaries}"}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant={promptMode === "edit" ? "recommended" : "outline"}
                        size="sm"
                        onClick={() => { setPromptMode("edit"); handleStartEditPrompt(); }}
                      >
                        Edit
                      </Button>
                      <Button
                        variant={promptMode === "preview" ? "recommended" : "outline"}
                        size="sm"
                        onClick={() => { setPromptMode("preview"); handleLoadPreview(); }}
                        disabled={promptPreviewLoading}
                      >
                        {promptPreviewLoading ? "Loading..." : "Preview"}
                      </Button>
                    </div>
                  </div>

                  {promptMode === "edit" && (
                    <div className="space-y-3">
                      {promptEditing ? (
                        <>
                          <Textarea
                            value={promptDraft}
                            onChange={(e) => setPromptDraft(e.target.value)}
                            className="min-h-[280px] font-mono text-sm"
                            placeholder={"You are {member_name}, a {member_role}.\n\n## Your Skills\n{skill_descriptions}\n\n## Your Knowledge\n{memory_summaries}"}
                          />
                          <div className="flex items-center gap-2">
                            <Button variant="recommended" onClick={handleSavePrompt} disabled={promptSaving}>
                              <Save className="h-4 w-4" />
                              {promptSaving ? "Saving..." : "Save"}
                            </Button>
                            <Button variant="outline" onClick={() => setPromptEditing(false)}>
                              Cancel
                            </Button>
                          </div>
                        </>
                      ) : (
                        <>
                          <pre className="whitespace-pre-wrap rounded-md bg-muted p-4 font-mono text-sm min-h-[120px]">
                            {detail?.prompt_template || (
                              <span className="text-muted-foreground italic">No prompt template configured. Click "Edit" to add one.</span>
                            )}
                          </pre>
                          <Button variant="outline" onClick={handleStartEditPrompt}>
                            <FileText className="h-4 w-4" />
                            Edit Template
                          </Button>
                        </>
                      )}
                    </div>
                  )}

                  {promptMode === "preview" && (
                    <div className="space-y-3">
                      {promptPreview ? (
                        <>
                          {promptPreview.rendered ? (
                            <>
                              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                                <span>Variables used: {promptPreview.variables_used.length > 0 ? promptPreview.variables_used.join(", ") : "none"}</span>
                                <span>~{promptPreview.token_estimate} tokens</span>
                              </div>
                              <pre className="whitespace-pre-wrap rounded-md bg-muted p-4 font-mono text-sm max-h-[400px] overflow-y-auto">
                                {promptPreview.rendered}
                              </pre>
                            </>
                          ) : (
                            <EmptyInline>No template to render. Switch to Edit and add a template first.</EmptyInline>
                          )}
                        </>
                      ) : (
                        <EmptyInline>Preview not available.</EmptyInline>
                      )}
                    </div>
                  )}
                </TabsContent>

                <TabsContent value="profile" className="space-y-5">
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    <Definition label="Display Name" value={detail.display_name} />
                    <Definition label="Kind" value={detail.kind} />
                    <Definition label="Role" value={detail.role} />
                    <Definition label="Department" value={deptName(detail.department_id)} />
                    <Definition label="Concurrency Limit" value={detail.concurrency_limit} />
                    <Definition label="Archived" value={detail.is_archived ? "Yes" : "No"} />
                    <Definition label="Created" value={detail.created_at} />
                    <Definition label="Member ID" value={detail.id} />
                  </div>

                  <div className="flex flex-wrap items-center gap-2 border-t pt-4">
                    <Button variant="outline" onClick={onDelete} className="border-destructive text-destructive">
                      <Trash2 className="h-4 w-4" />
                      Delete
                    </Button>
                  </div>
                </TabsContent>
              </Tabs>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function MemberPage({ selectedId }: { selectedId: string | null }) {
  const [members, setMembers] = useState<MemberSummary[]>([]);
  const [departments, setDepartments] = useState<DepartmentSummary[]>([]);
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [detail, setDetail] = useState<MemberDetail | null>(null);
  const [memberProfile, setMemberProfile] = useState<MemberProfileView | null>(null);
  const [memberTasks, setMemberTasks] = useState<TaskSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [formDisplayName, setFormDisplayName] = useState("");
  const [formKind, setFormKind] = useState("ai");
  const [formDepartmentId, setFormDepartmentId] = useState("");
  const [formRole, setFormRole] = useState("");
  const [formSkills, setFormSkills] = useState("");
  const [search, setSearch] = useState("");
  const [filterKind, setFilterKind] = useState("");
  const [filterDepartment, setFilterDepartment] = useState("");
  const [filterArchived, setFilterArchived] = useState("active");

  const deptName = useCallback((id: string | null) => {
    if (!id) return "-";
    const d = departments.find((dep) => dep.id === id);
    return d ? d.name : formatShortId(id);
  }, [departments]);

  const filteredMembers = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();
    return members.filter((member) => {
      const matchesSearch = !normalizedSearch
        || member.display_name.toLowerCase().includes(normalizedSearch)
        || member.id.toLowerCase().includes(normalizedSearch);
      const matchesKind = !filterKind || member.kind === filterKind;
      const matchesDepartment = !filterDepartment || member.department_id === filterDepartment;
      const matchesArchived =
        filterArchived === "all"
        || (filterArchived === "active" && !member.is_archived)
        || (filterArchived === "archived" && member.is_archived);
      return matchesSearch && matchesKind && matchesDepartment && matchesArchived;
    });
  }, [filterArchived, filterDepartment, filterKind, members, search]);

  const activeCount = members.filter((member) => !member.is_archived).length;
  const archivedCount = members.length - activeCount;
  const aiCount = members.filter((member) => member.kind === "ai").length;

  const columns: Column<MemberSummary>[] = [
    {
      key: "display_name",
      label: "Name",
      render: (r) => (
        <div className="flex min-w-0 items-center gap-2">
          <UserRound className="h-4 w-4 text-muted-foreground" />
          <span className="truncate font-medium">{r.display_name}</span>
        </div>
      ),
    },
    { key: "kind", label: "Kind", render: (r) => <Badge variant="secondary">{r.kind}</Badge> },
    { key: "department_id", label: "Department", render: (r) => deptName(r.department_id) },
    { key: "role", label: "Role", render: (r) => <span className="text-sm">{r.role || "-"}</span> },
    { key: "is_archived", label: "State", render: (r) => <Badge variant={r.is_archived ? "secondary" : "success"}>{r.is_archived ? "archived" : "active"}</Badge> },
    { key: "created_at", label: "Created", render: (r) => formatDate(r.created_at) },
  ];

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [m, d, s] = await Promise.all([
        listMembers({ limit: 100 }),
        listDepartments(0, 100),
        listSkills({ limit: 100 }),
      ]);
      setMembers(m);
      setDepartments(d);
      setSkills(s);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDetail = useCallback(async (id: string) => {
    setDetail(null);
    setMemberProfile(null);
    setMemberTasks([]);
    setDetailError(null);
    setTasksLoading(true);
    try {
      const profile = await getMemberProfileView(id);
      setMemberProfile(profile);
      setDetail(profile.member);
      setMemberTasks(profile.tasks);
    } catch {
      try {
        const [nextDetail, tasks] = await Promise.all([
          getMemberDetail(id),
          listTasks({ limit: 100 }),
        ]);
        setDetail(nextDetail);
        setMemberTasks(tasks);
      } catch (err) {
        setDetail(null);
        setMemberProfile(null);
        setMemberTasks([]);
        setDetailError(err instanceof Error ? err.message : "Failed to load member detail");
      }
    } finally {
      setTasksLoading(false);
    }
  }, []);

  useEffect(() => { loadList(); }, [loadList]);
  useEffect(() => {
    if (selectedId) {
      loadDetail(selectedId);
    } else {
      setDetail(null);
      setMemberProfile(null);
      setMemberTasks([]);
      setDetailError(null);
    }
  }, [selectedId, loadDetail]);

  function handleSelect(row: MemberSummary) {
    navigateTo("members", row.id);
  }

  const { toast } = useToast();

  async function handleDelete() {
    if (!detail) return;
    if (!confirm(`Delete member "${detail.display_name}"? This cannot be undone.`)) return;
    try {
      await deleteMember(detail.id);
      setDetail(null);
      navigateTo("members");
      toast({ title: "Member deleted" });
      await loadList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  async function handleCreate() {
    if (!formDisplayName.trim() || !formDepartmentId) return;
    const dept = departments.find((d) => d.name === formDepartmentId || d.id === formDepartmentId);
    if (!dept) {
      setError("Department not found");
      return;
    }
    try {
      const skills = formSkills.split(",").map((s) => s.trim()).filter(Boolean);
      const created = await createMember({
        kind: formKind,
        display_name: formDisplayName.trim(),
        department_id: dept.id,
        role: formRole.trim() || undefined,
        base_skill_set: skills.length > 0 ? skills : undefined,
      });
      setShowCreate(false);
      setFormDisplayName("");
      setFormDepartmentId("");
      setFormRole("");
      setFormSkills("");
      await loadList();
      navigateTo("members", created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    }
  }

  async function handleAssignSkill(skillName: string) {
    if (!detail) return;
    try {
      await assignSkillToMember(detail.id, skillName);
      await loadDetail(detail.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Assign skill failed");
    }
  }

  return (
    <div className="space-y-6">
      <Panel title="Members">
        <div className="mb-4 flex flex-wrap items-center gap-4">
          <Status label="Active" value={activeCount} tone={activeCount > 0 ? "ok" : undefined} />
          <Status label="Archived" value={archivedCount} />
          <Status label="AI" value={aiCount} />
          <Status label="Visible" value={filteredMembers.length} />
        </div>

        <div className="mb-4 grid gap-3 lg:grid-cols-[minmax(16rem,1fr)_10rem_12rem_10rem_auto]">
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search members"
          />
          <Select value={filterKind} onChange={(e) => setFilterKind(e.target.value)}>
            <option value="">All Kinds</option>
            <option value="ai">AI</option>
            <option value="human">Human</option>
          </Select>
          <Select value={filterDepartment} onChange={(e) => setFilterDepartment(e.target.value)}>
            <option value="">All Departments</option>
            {departments.map((department) => (
              <option key={department.id} value={department.id}>{department.name}</option>
            ))}
          </Select>
          <Select value={filterArchived} onChange={(e) => setFilterArchived(e.target.value)}>
            <option value="active">Active</option>
            <option value="archived">Archived</option>
            <option value="all">All States</option>
          </Select>
          <Button variant="recommended" onClick={() => setShowCreate(!showCreate)}>
            {showCreate ? (
              "Cancel"
            ) : (
              <>
                <Plus className="h-4 w-4" />
                Create Member
              </>
            )}
          </Button>
        </div>

        {error && <ErrorState message={error} />}

        {showCreate && (
          <div className="mb-4 grid gap-4 rounded-md border p-4 lg:grid-cols-2">
            <FormField label="Display Name">
              <Input value={formDisplayName} onChange={(e) => setFormDisplayName(e.target.value)} placeholder="Alice" />
            </FormField>
            <FormField label="Kind">
              <Select value={formKind} onChange={(e) => setFormKind(e.target.value)}>
                <option value="ai">AI</option>
                <option value="human">Human</option>
              </Select>
            </FormField>
            <FormField label="Department *">
              <ComboInput
                value={formDepartmentId}
                onChange={setFormDepartmentId}
                options={departments.map((d) => ({ value: d.name, label: d.name }))}
                placeholder="Select or type department name"
              />
            </FormField>
            <FormField label="Role">
              <Input value={formRole} onChange={(e) => setFormRole(e.target.value)} placeholder="developer" />
            </FormField>
            <FormField label="Base Skills" wide>
              <Input value={formSkills} onChange={(e) => setFormSkills(e.target.value)} placeholder="python, testing" />
            </FormField>
            <div className="col-span-full flex items-center gap-2">
              <Button variant="recommended" disabled={!formDisplayName.trim() || !formDepartmentId} onClick={handleCreate}>
                <Plus className="h-4 w-4" />
                Create
              </Button>
            </div>
          </div>
        )}

        {loading ? (
          <LoadingState />
        ) : (
          <DataTable data={filteredMembers} columns={columns} selectedId={selectedId ?? undefined} onSelect={handleSelect} />
        )}
      </Panel>

      <MemberDetailSurface
        selectedId={selectedId}
        detail={detail}
        profile={memberProfile}
        tasks={memberTasks}
        departments={departments}
        detailError={detailError}
        tasksLoading={tasksLoading}
        onClose={() => navigateTo("members")}
        onDelete={handleDelete}
        onAssignSkill={handleAssignSkill}
        onReload={loadDetail}
        availableSkills={skills}
      />
    </div>
  );
}
