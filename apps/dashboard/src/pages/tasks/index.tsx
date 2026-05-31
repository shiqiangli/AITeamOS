/**
 * AITeamOS Dashboard - Task Management Page
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Bot, ListTodo, Play, Plus, RotateCcw, Square, Trash2 } from "lucide-react";
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
  listAgentProfiles,
  getTaskDetail,
  createTask,
  assignTask,
  assignTaskRuntime,
  startTaskRun,
  cancelTask,
  requeueTask,
  deleteTask,
  type TaskSummary,
  type TaskDetail,
  type DepartmentSummary,
  type MemberSummary,
  type LlmModelSummary,
  type AgentProfileSummary,
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
  const [agentProfiles, setAgentProfiles] = useState<AgentProfileSummary[]>([]);
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
  const [formAgentName, setFormAgentName] = useState("");
  const [formLlmName, setFormLlmName] = useState("");
  const [formPriority, setFormPriority] = useState("P2");
  const [formDeliverableKind, setFormDeliverableKind] = useState("code_change");

  const [showAssign, setShowAssign] = useState(false);
  const [assignMemberId, setAssignMemberId] = useState("");
  const [showRuntime, setShowRuntime] = useState(false);
  const [runtimeAgentName, setRuntimeAgentName] = useState("");
  const [runtimeLlmName, setRuntimeLlmName] = useState("");

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

  const agentProfileName = useCallback((id: string | null) => {
    if (!id) return "-";
    const agent = agentProfiles.find((item) => item.id === id);
    return agent ? agent.name : id.length > 8 ? `${id.slice(0, 8)}...` : id;
  }, [agentProfiles]);

  const resolveLlm = useCallback((value: string): LlmModelSummary | null => {
    const trimmed = value.trim();
    if (!trimmed) return null;
    return llmModels.find((model) => model.name === trimmed || model.id === trimmed) ?? null;
  }, [llmModels]);

  const resolveAgent = useCallback((value: string): AgentProfileSummary | null => {
    const trimmed = value.trim();
    if (!trimmed) return null;
    return agentProfiles.find((agent) => agent.name === trimmed || agent.id === trimmed) ?? null;
  }, [agentProfiles]);

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
    { key: "assigned_member_id", label: "Assignee", render: (r) => memberName(r.assigned_member_id) },
    { key: "assigned_agent_profile_id", label: "Agent", render: (r) => agentProfileName(r.assigned_agent_profile_id) },
    { key: "assigned_llm_model_id", label: "LLM", render: (r) => llmModelName(r.assigned_llm_model_id) },
    { key: "department_id", label: "Department", render: (r) => deptName(r.department_id) },
    { key: "retry_count", label: "Retries" },
  ];

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [t, d, m, models, agents] = await Promise.all([
        listTasks({ state: filterState || undefined, limit: 100 }),
        listDepartments(0, 100),
        listMembers({ limit: 100 }),
        listLlmModels({ limit: 100 }),
        listAgentProfiles({ limit: 100 }),
      ]);
      setTasks(t);
      setDepartments(d);
      setMembers(m);
      setLlmModels(models);
      setAgentProfiles(agents);
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
    } else {
      setDetail(null);
      setDetailError(null);
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
    const agent = formAgentName.trim() ? resolveAgent(formAgentName) : null;
    if (formAgentName.trim() && !agent) {
      setError("Agent not found");
      return;
    }
    const explicitLlm = formLlmName.trim() ? resolveLlm(formLlmName) : null;
    if (formLlmName.trim() && !explicitLlm) {
      setError("LLM not found");
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
      const llmId = explicitLlm?.id ?? agent?.default_llm_model_id ?? null;
      if (agent || llmId) {
        await assignTaskRuntime(result.id, {
          agent_profile_id: agent?.id ?? null,
          llm_model_id: llmId,
        });
      }
      setShowCreate(false);
      setFormTitle("");
      setFormDescription("");
      setFormDepartmentId("");
      setFormAgentName("");
      setFormLlmName("");
      await loadList();
      navigateTo("tasks", result.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    }
  }

  async function handleAssign() {
    if (!detail || !assignMemberId) return;
    const mem = members.find((m) => m.display_name === assignMemberId || m.id === assignMemberId);
    if (!mem) {
      setError("Member not found");
      return;
    }
    try {
      await assignTask(detail.id, mem.id);
      setShowAssign(false);
      setAssignMemberId("");
      await loadList();
      await loadDetail(detail.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Assign failed");
    }
  }

  async function handleAssignRuntime() {
    if (!detail) return;
    const agent = runtimeAgentName.trim() ? resolveAgent(runtimeAgentName) : null;
    if (runtimeAgentName.trim() && !agent) {
      setError("Agent not found");
      return;
    }
    const explicitLlm = runtimeLlmName.trim() ? resolveLlm(runtimeLlmName) : null;
    if (runtimeLlmName.trim() && !explicitLlm) {
      setError("LLM not found");
      return;
    }
    const llmId = explicitLlm?.id ?? agent?.default_llm_model_id ?? null;
    try {
      await assignTaskRuntime(detail.id, {
        agent_profile_id: agent?.id ?? null,
        llm_model_id: llmId,
      });
      setShowRuntime(false);
      await loadList();
      await loadDetail(detail.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Runtime assignment failed");
    }
  }

  function openRuntimeEditor() {
    if (!detail) return;
    setRuntimeAgentName(detail.assigned_agent_profile_id ? agentProfileName(detail.assigned_agent_profile_id) : "");
    setRuntimeLlmName(detail.assigned_llm_model_id ? llmModelName(detail.assigned_llm_model_id) : "");
    setShowRuntime(true);
  }

  async function handleStart() {
    if (!detail) return;
    try {
      await startTaskRun(detail.id);
      await loadList();
      await loadDetail(detail.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Start failed");
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
            <FormField label="Agent">
              <ComboInput
                value={formAgentName}
                onChange={setFormAgentName}
                options={agentProfiles.map((agent) => ({ value: agent.name, label: agent.name }))}
                placeholder="Select or type agent name"
              />
            </FormField>
            <FormField label="LLM">
              <ComboInput
                value={formLlmName}
                onChange={setFormLlmName}
                options={llmModels.map((model) => ({ value: model.name, label: `${model.name} (${model.provider})` }))}
                placeholder="Select or type LLM name"
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
                  </DialogTitle>
                  <DialogDescription>{detail.priority} in {deptName(detail.department_id)}</DialogDescription>
                </DialogHeader>
              </div>
              <div className="overflow-y-auto px-6 py-5">
                <Tabs defaultValue="overview" className="space-y-5">
                  <TabsList className="flex h-auto flex-wrap justify-start">
                    <TabsTrigger value="overview">Overview</TabsTrigger>
                    <TabsTrigger value="description">Description</TabsTrigger>
                    <TabsTrigger value="runs">Runs</TabsTrigger>
                    <TabsTrigger value="actions">Actions</TabsTrigger>
                  </TabsList>
                  <TabsContent value="overview">
                    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                      <Definition label="Name" value={detail.title} />
                      <Definition label="State" value={<Badge variant={stateBadgeVariant(detail.state)}>{detail.state}</Badge>} />
                      <Definition label="Priority" value={detail.priority} />
                      <Definition label="Department" value={deptName(detail.department_id)} />
                      <Definition label="Assignee" value={memberName(detail.assigned_member_id)} />
                      <Definition label="Agent" value={agentProfileName(detail.assigned_agent_profile_id)} />
                      <Definition label="LLM" value={llmModelName(detail.assigned_llm_model_id)} />
                      <Definition label="Deliverable Kind" value={detail.deliverable_kind || "-"} />
                      <Definition label="Retry Count" value={`${detail.retry_count} / ${detail.max_retry_count}`} />
                      <Definition label="Review Rounds" value={`${detail.review_round} / ${detail.max_review_rounds}`} />
                      <Definition label="Created" value={formatDate(detail.created_at)} />
                      <Definition label="Task ID" value={detail.id} />
                    </div>
                  </TabsContent>
                  <TabsContent value="description">
                    {detail.description ? (
                      <pre className="whitespace-pre-wrap rounded-md bg-muted p-4 font-mono text-sm">{detail.description}</pre>
                    ) : (
                      <div className="rounded-md border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">No description</div>
                    )}
                  </TabsContent>
                  <TabsContent value="runs">
                    {detail.runs?.length ? (
                      <div className="divide-y rounded-md border">
                        {detail.runs.map((run) => (
                          <div key={run.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
                            <span className="font-medium">{run.id}</span>
                            <span className="flex items-center gap-2">
                              <Badge variant="secondary">{run.state}</Badge>
                              <span className="text-muted-foreground">{formatDate(run.started_at)}</span>
                            </span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="rounded-md border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">No runs</div>
                    )}
                  </TabsContent>
                  <TabsContent value="actions">
                    <div className="space-y-4">
                      <div className="flex flex-wrap items-center gap-2">
                        {(detail.state === "ready" || detail.state === "draft") && !showAssign && (
                          <Button variant="outline" onClick={() => setShowAssign(true)}><UsersIcon />Assign</Button>
                        )}
                        {!showRuntime && (
                          <Button variant="outline" onClick={openRuntimeEditor}><Bot className="h-4 w-4" />Runtime</Button>
                        )}
                        {detail.state === "assigned" && (
                          <Button variant="recommended" onClick={handleStart}><Play className="h-4 w-4" />Start Run</Button>
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
                      {showAssign && (
                        <div className="flex flex-wrap items-center gap-2">
                          <ComboInput
                            value={assignMemberId}
                            onChange={setAssignMemberId}
                            options={members.map((m) => ({ value: m.display_name, label: `${m.display_name} (${m.kind})` }))}
                            placeholder="Select or type member name"
                            className="w-64"
                          />
                          <Button variant="recommended" onClick={handleAssign}>Confirm</Button>
                          <Button variant="outline" onClick={() => { setShowAssign(false); setAssignMemberId(""); }}>Cancel</Button>
                        </div>
                      )}
                      {showRuntime && (
                        <div className="grid gap-3 rounded-md border p-4 lg:grid-cols-[minmax(12rem,1fr)_minmax(12rem,1fr)_auto_auto]">
                          <ComboInput
                            value={runtimeAgentName}
                            onChange={setRuntimeAgentName}
                            options={agentProfiles.map((agent) => ({ value: agent.name, label: agent.name }))}
                            placeholder="Select or type agent name"
                          />
                          <ComboInput
                            value={runtimeLlmName}
                            onChange={setRuntimeLlmName}
                            options={llmModels.map((model) => ({ value: model.name, label: `${model.name} (${model.provider})` }))}
                            placeholder="Select or type LLM name"
                          />
                          <Button variant="recommended" onClick={handleAssignRuntime}>Confirm</Button>
                          <Button variant="outline" onClick={() => { setShowRuntime(false); setRuntimeAgentName(""); setRuntimeLlmName(""); }}>Cancel</Button>
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

function UsersIcon() {
  return <ListTodo className="h-4 w-4" />;
}
