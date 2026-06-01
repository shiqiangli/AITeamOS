/**
 * AITeamOS Dashboard - Task Management Page
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { ListTodo, Pencil, Play, Plus, RotateCcw, Save, Square, Trash2, X } from "lucide-react";
import {
  Panel,
  DataTable,
  Definition,
  FormField,
  Status,
  LoadingState,
  ErrorState,
  navigateTo,
  ComboInput,
  type Column,
} from "../../components/shared";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../../components/ui/tabs";
import {
  listTasks,
  listDepartments,
  listMembers,
  listLlmModels,
  getTaskDetail,
  createTask,
  updateTask,
  startTaskRun,
  cancelTask,
  requeueTask,
  deleteTask,
  createJob,
  listJobs,
  type TaskSummary,
  type TaskDetail,
  type DepartmentSummary,
  type MemberSummary,
  type LlmModelSummary,
  type JobSummary,
} from "../../api/client";

function stateBadgeVariant(state: string): "success" | "warning" | "secondary" | "danger" {
  switch (state) {
    case "done": return "success";
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

function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

export function TaskPage({ selectedId }: { selectedId: string | null }) {
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [departments, setDepartments] = useState<DepartmentSummary[]>([]);
  const [members, setMembers] = useState<MemberSummary[]>([]);
  const [llmModels, setLlmModels] = useState<LlmModelSummary[]>([]);
  const [detail, setDetail] = useState<TaskDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [filterState, setFilterState] = useState("");
  const [search, setSearch] = useState("");

  const [formTitle, setFormTitle] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formDepartmentId, setFormDepartmentId] = useState("");
  const [formPriority, setFormPriority] = useState("P2");
  const [formDeliverableKind, setFormDeliverableKind] = useState("code_change");

  // --- Start Job dialog ---
  const [showStartJob, setShowStartJob] = useState(false);
  const [startJobMember, setStartJobMember] = useState("");
  const [startJobLlm, setStartJobLlm] = useState("");
  const [startJobLoading, setStartJobLoading] = useState(false);

  // --- Jobs list ---
  const [jobs, setJobs] = useState<JobSummary[]>([]);

  // --- Inline edit state ---
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editPriority, setEditPriority] = useState("P2");
  const [editDeliverableKind, setEditDeliverableKind] = useState("");
  const [editMaxRetries, setEditMaxRetries] = useState(3);
  const [editMaxReviews, setEditMaxReviews] = useState(3);
  const [editSaving, setEditSaving] = useState(false);

  const deptName = useCallback((id: string | null) => {
    if (!id) return "-";
    const d = departments.find((dep) => dep.id === id);
    return d ? d.name : id.length > 8 ? `${id.slice(0, 8)}...` : id;
  }, [departments]);

  const memberName = useCallback((id: string | null) => {
    if (!id) return "-";
    const m = members.find((mem) => mem.id === id);
    return m ? m.display_name : id.length > 8 ? `${id.slice(0, 8)}...` : id;
  }, [members]);

  const llmModelName = useCallback((id: string | null) => {
    if (!id) return "-";
    const model = llmModels.find((item) => item.id === id);
    return model ? model.name : id.length > 8 ? `${id.slice(0, 8)}...` : id;
  }, [llmModels]);

  const resolveLlm = useCallback((value: string): LlmModelSummary | null => {
    const trimmed = value.trim();
    if (!trimmed) return null;
    return llmModels.find((model) => model.name === trimmed || model.id === trimmed) ?? null;
  }, [llmModels]);

  const filteredTasks = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return tasks.filter((task) => {
      const matchesSearch = !needle
        || task.title.toLowerCase().includes(needle)
        || task.id.toLowerCase().includes(needle);
      return matchesSearch;
    });
  }, [search, tasks]);

  const columns: Column<TaskSummary>[] = [
    { key: "title", label: "Name", render: (r) => r.title.length > 56 ? `${r.title.slice(0, 56)}...` : r.title },
    { key: "state", label: "State", render: (r) => <Badge variant={stateBadgeVariant(r.state)}>{r.state}</Badge> },
    { key: "priority", label: "Priority" },
    { key: "department_id", label: "Department", render: (r) => deptName(r.department_id) },
    { key: "retry_count", label: "Retries" },
  ];

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [t, d, m, models] = await Promise.all([
        listTasks({ state: filterState || undefined, limit: 100 }),
        listDepartments(0, 100),
        listMembers({ limit: 100 }),
        listLlmModels({ limit: 100 }),
      ]);
      setTasks(t);
      setDepartments(d);
      setMembers(m);
      setLlmModels(models);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [filterState]);

  const loadDetail = useCallback(async (id: string) => {
    setDetail(null);
    setDetailError(null);
    try {
      setDetail(await getTaskDetail(id));
    } catch (err) {
      setDetail(null);
      setDetailError(err instanceof Error ? err.message : "Failed to load task detail");
    }
  }, []);

  useEffect(() => { loadList(); }, [loadList]);
  useEffect(() => {
    if (selectedId) {
      loadDetail(selectedId);
      loadJobs(selectedId);
      setEditing(false);
      setShowStartJob(false);
    } else {
      setDetail(null);
      setDetailError(null);
      setEditing(false);
      setJobs([]);
    }
  }, [selectedId, loadDetail]);

  function handleSelect(row: TaskSummary) {
    navigateTo("tasks", row.id);
  }

  const { toast } = useToast();

  async function handleDelete() {
    if (!detail) return;
    if (!confirm(`Delete task "${detail.title}"? This cannot be undone.`)) return;
    try {
      await deleteTask(detail.id);
      setDetail(null);
      navigateTo("tasks");
      toast({ title: "Task deleted" });
      await loadList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  async function handleCreate() {
    if (!formTitle.trim() || !formDepartmentId) return;
    const dept = departments.find((d) => d.name === formDepartmentId || d.id === formDepartmentId);
    if (!dept) {
      setError("Department not found");
      return;
    }
    try {
      const result = await createTask({
        title: formTitle.trim(),
        description: formDescription.trim(),
        department_id: dept.id,
        priority: formPriority,
        deliverable_kind: formDeliverableKind,
      });
      setShowCreate(false);
      setFormTitle("");
      setFormDescription("");
      setFormDepartmentId("");
      await loadList();
      navigateTo("tasks", result.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    }
  }

  async function handleStartJob() {
    if (!detail) return;
    const member = startJobMember.trim()
      ? members.find((m) => m.display_name === startJobMember.trim() || m.id === startJobMember.trim())
      : null;
    const llm = startJobLlm.trim() ? resolveLlm(startJobLlm) : null;
    setStartJobLoading(true);
    try {
      // 1. Transition task to running
      await startTaskRun(detail.id);
      // 2. Create Job with member + llm
      await createJob({
        task_id: detail.id,
        member_id: member?.id,
        llm_model_id: llm?.id,
      });
      setShowStartJob(false);
      setStartJobMember("");
      setStartJobLlm("");
      toast({ title: "Job started" });
      await loadList();
      await loadDetail(detail.id);
      await loadJobs(detail.id);
    } catch (err) {
      toast({ title: "Start Job failed", description: err instanceof Error ? err.message : "Unknown error", variant: "danger" });
    } finally {
      setStartJobLoading(false);
    }
  }

  async function loadJobs(taskId: string) {
    try {
      const result = await listJobs(taskId);
      setJobs(result);
    } catch {
      setJobs([]);
    }
  }

  async function handleCancel() {
    if (!detail) return;
    try {
      await cancelTask(detail.id);
      await loadList();
      await loadDetail(detail.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cancel failed");
    }
  }

  async function handleRequeue() {
    if (!detail) return;
    try {
      await requeueTask(detail.id);
      await loadList();
      await loadDetail(detail.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Requeue failed");
    }
  }

  // --- Inline edit handlers ---

  function handleStartEdit() {
    if (!detail) return;
    setEditTitle(detail.title);
    setEditDescription(detail.description || "");
    setEditPriority(detail.priority);
    setEditDeliverableKind(detail.deliverable_kind || "");
    setEditMaxRetries(detail.max_retry_count);
    setEditMaxReviews(detail.max_review_rounds);
    setEditing(true);
  }

  function handleCancelEdit() {
    setEditing(false);
  }

  async function handleSaveEdit() {
    if (!detail) return;
    setEditSaving(true);
    try {
      await updateTask(detail.id, {
        title: editTitle.trim(),
        description: editDescription.trim(),
        priority: editPriority,
        deliverable_kind: editDeliverableKind,
        max_retry_count: editMaxRetries,
        max_review_rounds: editMaxReviews,
      });

      setEditing(false);
      toast({ title: "Task updated" });
      await loadList();
      await loadDetail(detail.id);
    } catch (err) {
      toast({ title: "Update failed", description: err instanceof Error ? err.message : "Unknown error", variant: "danger" });
    } finally {
      setEditSaving(false);
    }
  }

  const readyCount = tasks.filter((t) => t.state === "ready").length;
  const runningCount = tasks.filter((t) => t.state === "running").length;
  const doneCount = tasks.filter((t) => t.state === "done").length;

  return (
    <div className="space-y-6">
      <Panel title="Tasks">
        <div className="mb-4 flex flex-wrap items-center gap-4">
          <Status label="Ready" value={readyCount} />
          <Status label="Running" value={runningCount} tone={runningCount > 0 ? "warn" : undefined} />
          <Status label="Done" value={doneCount} tone="ok" />
          <Status label="Visible" value={filteredTasks.length} />
        </div>

        <div className="mb-4 grid gap-3 lg:grid-cols-[minmax(16rem,1fr)_12rem_auto]">
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search tasks" />
          <Select value={filterState} onChange={(e) => setFilterState(e.target.value)}>
            <option value="">All States</option>
            <option value="draft">Draft</option>
            <option value="ready">Ready</option>
            <option value="assigned">Assigned</option>
            <option value="running">Running</option>
            <option value="verifying">Verifying</option>
            <option value="in_review">In Review</option>
            <option value="done">Done</option>
            <option value="failed">Failed</option>
            <option value="cancelled">Cancelled</option>
          </Select>
          <Button variant="recommended" onClick={() => setShowCreate(!showCreate)}>
            {showCreate ? "Cancel" : <><Plus className="h-4 w-4" />Create Task</>}
          </Button>
        </div>

        {error && <ErrorState message={error} />}

        {showCreate && (
          <div className="mb-4 grid gap-4 rounded-md border p-4 lg:grid-cols-2">
            <FormField label="Task Name" wide>
              <Input value={formTitle} onChange={(e) => setFormTitle(e.target.value)} placeholder="Unique task name" />
            </FormField>
            <FormField label="Department">
              <ComboInput
                value={formDepartmentId}
                onChange={setFormDepartmentId}
                options={departments.map((d) => ({ value: d.name, label: d.name }))}
                placeholder="Select or type department name"
              />
            </FormField>
            <FormField label="Priority">
              <Select value={formPriority} onChange={(e) => setFormPriority(e.target.value)}>
                <option value="P0">P0 - Critical</option>
                <option value="P1">P1 - High</option>
                <option value="P2">P2 - Medium</option>
                <option value="P3">P3 - Low</option>
              </Select>
            </FormField>
            <FormField label="Deliverable Kind">
              <Select value={formDeliverableKind} onChange={(e) => setFormDeliverableKind(e.target.value)}>
                <option value="code_change">Code Change</option>
                <option value="document">Document</option>
                <option value="design">Design</option>
                <option value="config">Configuration</option>
              </Select>
            </FormField>
            <FormField label="Description" wide>
              <Textarea value={formDescription} onChange={(e) => setFormDescription(e.target.value)} placeholder="Describe what needs to be done..." />
            </FormField>
            <div className="col-span-full flex items-center gap-2">
              <Button variant="recommended" disabled={!formTitle.trim() || !formDepartmentId} onClick={handleCreate}>
                <Plus className="h-4 w-4" />Create
              </Button>
            </div>
          </div>
        )}

        {loading ? (
          <LoadingState />
        ) : (
          <DataTable data={filteredTasks} columns={columns} selectedId={selectedId ?? undefined} onSelect={handleSelect} />
        )}
      </Panel>

      <Dialog open={Boolean(selectedId)} onOpenChange={(open) => { if (!open) navigateTo("tasks"); }}>
        <DialogContent className="block max-h-[calc(100vh-2rem)] w-[calc(100vw-2rem)] max-w-5xl overflow-hidden p-0">
          {detailError && (
            <div className="space-y-4 p-6">
              <DialogHeader>
                <DialogTitle>Task Details</DialogTitle>
                <DialogDescription>Task detail could not be loaded.</DialogDescription>
              </DialogHeader>
              <ErrorState message={detailError} />
            </div>
          )}
          {!detail && !detailError && (
            <div className="space-y-4 p-6">
              <DialogHeader>
                <DialogTitle>Task Details</DialogTitle>
                <DialogDescription>Loading task detail.</DialogDescription>
              </DialogHeader>
              <LoadingState />
            </div>
          )}
          {detail && (
            <div className="flex max-h-[calc(100vh-2rem)] flex-col">
              <div className="border-b px-6 py-5">
                <DialogHeader>
                  <DialogTitle className="flex flex-wrap items-center gap-3 text-xl">
                    <ListTodo className="h-5 w-5 text-muted-foreground" />
                    <span>{detail.title}</span>
                    <Badge variant={stateBadgeVariant(detail.state)}>{detail.state}</Badge>
                    {!editing && !["done", "cancelled"].includes(detail.state) && (
                      <Button variant="outline" size="sm" onClick={handleStartEdit}>
                        <Pencil className="h-3.5 w-3.5" />Edit
                      </Button>
                    )}
                    {editing && (
                      <div className="flex items-center gap-2">
                        <Button variant="recommended" size="sm" onClick={handleSaveEdit} disabled={editSaving}>
                          <Save className="h-3.5 w-3.5" />
                          {editSaving ? "Saving..." : "Save"}
                        </Button>
                        <Button variant="outline" size="sm" onClick={handleCancelEdit} disabled={editSaving}>
                          <X className="h-3.5 w-3.5" />Cancel
                        </Button>
                      </div>
                    )}
                  </DialogTitle>
                  <DialogDescription>{detail.priority} in {deptName(detail.department_id)}</DialogDescription>
                </DialogHeader>
              </div>
              <div className="overflow-y-auto px-6 py-5">
                <Tabs defaultValue="overview" className="space-y-5">
                  <TabsList className="flex h-auto flex-wrap justify-start">
                    <TabsTrigger value="overview">Overview</TabsTrigger>
                    <TabsTrigger value="description">Description</TabsTrigger>
                    <TabsTrigger value="runs">Jobs</TabsTrigger>
                    <TabsTrigger value="actions">Actions</TabsTrigger>
                  </TabsList>
                  <TabsContent value="overview">
                    {!editing ? (
                      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                        <Definition label="Name" value={detail.title} />
                        <Definition label="State" value={<Badge variant={stateBadgeVariant(detail.state)}>{detail.state}</Badge>} />
                        <Definition label="Priority" value={detail.priority} />
                        <Definition label="Department" value={deptName(detail.department_id)} />
                        <Definition label="Deliverable Kind" value={detail.deliverable_kind || "-"} />
                        <Definition label="Retry Count" value={`${detail.retry_count} / ${detail.max_retry_count}`} />
                        <Definition label="Review Rounds" value={`${detail.review_round} / ${detail.max_review_rounds}`} />
                        <Definition label="Created" value={formatDate(detail.created_at)} />
                        <Definition label="Task ID" value={detail.id} />
                      </div>
                    ) : (
                      <div className="grid gap-4 sm:grid-cols-2">
                        <FormField label="Title" wide>
                          <Input value={editTitle} onChange={(e) => setEditTitle(e.target.value)} />
                        </FormField>
                        <FormField label="Priority">
                          <Select value={editPriority} onChange={(e) => setEditPriority(e.target.value)}>
                            <option value="P0">P0 - Critical</option>
                            <option value="P1">P1 - High</option>
                            <option value="P2">P2 - Medium</option>
                            <option value="P3">P3 - Low</option>
                          </Select>
                        </FormField>
                        <FormField label="Department">
                          <Input value={deptName(detail.department_id)} disabled />
                        </FormField>
                        <FormField label="Deliverable Kind">
                          <Select value={editDeliverableKind} onChange={(e) => setEditDeliverableKind(e.target.value)}>
                            <option value="">-</option>
                            <option value="code_change">Code Change</option>
                            <option value="document">Document</option>
                            <option value="design">Design</option>
                            <option value="config">Configuration</option>
                          </Select>
                        </FormField>
                        <FormField label="Max Retries">
                          <Input type="number" value={editMaxRetries} onChange={(e) => setEditMaxRetries(Number(e.target.value))} />
                        </FormField>
                        <FormField label="Max Review Rounds">
                          <Input type="number" value={editMaxReviews} onChange={(e) => setEditMaxReviews(Number(e.target.value))} />
                        </FormField>
                      </div>
                    )}
                  </TabsContent>
                  <TabsContent value="description">
                    {!editing ? (
                      detail.description ? (
                        <pre className="whitespace-pre-wrap rounded-md bg-muted p-4 font-mono text-sm">{detail.description}</pre>
                      ) : (
                        <div className="rounded-md border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">No description</div>
                      )
                    ) : (
                      <FormField label="Description" wide>
                        <Textarea
                          value={editDescription}
                          onChange={(e) => setEditDescription(e.target.value)}
                          className="min-h-[200px]"
                          placeholder="Describe what needs to be done..."
                        />
                      </FormField>
                    )}
                  </TabsContent>
                  <TabsContent value="runs">
                    {jobs.length ? (
                      <div className="divide-y rounded-md border">
                        {jobs.map((job) => (
                          <div key={job.job_id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
                            <div className="flex flex-col gap-1">
                              <span className="font-medium">{job.job_id.slice(0, 8)}...</span>
                              <span className="text-xs text-muted-foreground">
                                {job.member_id ? memberName(job.member_id) : "No assignee"} · {formatDate(job.started_at)}
                              </span>
                            </div>
                            <span className="flex items-center gap-2">
                              <Badge variant={stateBadgeVariant(job.phase)}>{job.phase}</Badge>
                              <Badge variant="secondary">{job.state}</Badge>
                            </span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="rounded-md border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">No jobs yet</div>
                    )}
                  </TabsContent>
                  <TabsContent value="actions">
                    <div className="space-y-4">
                      <div className="flex flex-wrap items-center gap-2">
                        {!showStartJob && (detail.state === "ready" || detail.state === "assigned" || detail.state === "draft") && (
                          <Button variant="recommended" onClick={() => setShowStartJob(true)}><Play className="h-4 w-4" />Start Job</Button>
                        )}
                        {detail.state === "failed" && (
                          <Button variant="outline" onClick={handleRequeue}><RotateCcw className="h-4 w-4" />Requeue</Button>
                        )}
                        {!["done", "cancelled", "failed"].includes(detail.state) && (
                          <Button variant="outline" onClick={handleCancel}><Square className="h-4 w-4" />Cancel</Button>
                        )}
                        <Button variant="outline" onClick={handleDelete} className="border-destructive text-destructive">
                          <Trash2 className="h-4 w-4" />Delete
                        </Button>
                      </div>
                      {showStartJob && (
                        <div className="rounded-md border p-4 space-y-3">
                          <p className="text-sm font-medium">Start a new Job for this Task</p>
                          <div className="flex flex-wrap items-center gap-2">
                            <FormField label="Assignee (Member)">
                              <ComboInput
                                value={startJobMember}
                                onChange={setStartJobMember}
                                options={members.map((m) => ({ value: m.display_name, label: `${m.display_name} (${m.role})` }))}
                                placeholder="Select or type member name"
                                className="w-64"
                              />
                            </FormField>
                            <FormField label="LLM Model">
                              <ComboInput
                                value={startJobLlm}
                                onChange={setStartJobLlm}
                                options={llmModels.map((model) => ({ value: model.name, label: `${model.name} (${model.provider})` }))}
                                placeholder="Select or type LLM name"
                                className="w-64"
                              />
                            </FormField>
                          </div>
                          <div className="flex items-center gap-2">
                            <Button variant="recommended" onClick={handleStartJob} disabled={startJobLoading}>
                              {startJobLoading ? "Starting..." : "Confirm Start"}
                            </Button>
                            <Button variant="outline" onClick={() => { setShowStartJob(false); setStartJobMember(""); setStartJobLlm(""); }}>Cancel</Button>
                          </div>
                        </div>
                      )}
                    </div>
                  </TabsContent>
                </Tabs>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
