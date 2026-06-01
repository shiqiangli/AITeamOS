/**
 * AITeamOS Dashboard - Jobs Page
 *
 * Global view of all Jobs (execution attempts of Tasks).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Zap } from "lucide-react";
import {
  Panel,
  DataTable,
  Status,
  LoadingState,
  ErrorState,
  navigateTo,
  type Column,
} from "../../components/shared";
import { Badge } from "../../components/ui/badge";
import { Input } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../../components/ui/tabs";
import { Definition } from "../../components/shared";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";
import {
  listJobs,
  getJobDetail,
  listMembers,
  listLlmModels,
  listTasks,
  type JobSummary,
  type Job,
  type MemberSummary,
  type LlmModelSummary,
  type TaskSummary,
} from "../../api/client";

function phaseBadgeVariant(phase: string): "success" | "warning" | "secondary" | "danger" {
  switch (phase) {
    case "completed":
      return "success";
    case "calling":
    case "processing":
    case "assembling":
    case "rendering":
    case "validating":
      return "warning";
    case "failed":
      return "danger";
    default:
      return "secondary";
  }
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function elapsed(startedAt: string | null, finishedAt: string | null): string {
  if (!startedAt) return "-";
  const start = new Date(startedAt).getTime();
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  if (Number.isNaN(start) || Number.isNaN(end)) return "-";
  const seconds = Math.round((end - start) / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${minutes}m ${secs}s`;
}

export function JobsPage({ selectedId }: { selectedId: string | null }) {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [members, setMembers] = useState<MemberSummary[]>([]);
  const [llmModels, setLlmModels] = useState<LlmModelSummary[]>([]);
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterPhase, setFilterPhase] = useState("");
  const [filterState, setFilterState] = useState("");
  const [search, setSearch] = useState("");
  const [detail, setDetail] = useState<Job | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  const memberName = useCallback(
    (id: string | null) => {
      if (!id) return "-";
      const m = members.find((mem) => mem.id === id);
      return m ? m.display_name : id.length > 8 ? `${id.slice(0, 8)}...` : id;
    },
    [members]
  );

  const llmModelName = useCallback(
    (id: string | null) => {
      if (!id) return "-";
      const model = llmModels.find((item) => item.id === id);
      return model ? model.name : id.length > 8 ? `${id.slice(0, 8)}...` : id;
    },
    [llmModels]
  );

  const taskTitle = useCallback(
    (id: string | null) => {
      if (!id) return "-";
      const t = tasks.find((task) => task.id === id);
      return t ? (t.title.length > 40 ? `${t.title.slice(0, 40)}...` : t.title) : id.length > 12 ? `${id.slice(0, 12)}...` : id;
    },
    [tasks]
  );

  const filteredJobs = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return jobs.filter((job) => {
      const matchesSearch =
        !needle ||
        job.job_id.toLowerCase().includes(needle) ||
        job.task_id.toLowerCase().includes(needle);
      const matchesPhase = !filterPhase || job.phase === filterPhase;
      const matchesState = !filterState || job.state === filterState;
      return matchesSearch && matchesPhase && matchesState;
    });
  }, [jobs, search, filterPhase, filterState]);

  const columns: Column<JobSummary>[] = [
    {
      key: "job_id",
      label: "Job ID",
      render: (r) => (
        <span className="font-mono text-xs">{r.job_id.slice(0, 8)}...</span>
      ),
    },
    {
      key: "task_id",
      label: "Task",
      render: (r) => (
        <button
          className="text-primary underline text-sm"
          onClick={(e) => {
            e.stopPropagation();
            navigateTo("tasks", r.task_id);
          }}
        >
          {taskTitle(r.task_id)}
        </button>
      ),
    },
    { key: "phase", label: "Phase", render: (r) => <Badge variant={phaseBadgeVariant(r.phase)}>{r.phase}</Badge> },
    { key: "state", label: "State", render: (r) => <Badge variant="secondary">{r.state}</Badge> },
    { key: "member_id", label: "Assignee", render: (r) => memberName(r.member_id) },
    { key: "llm_model_id", label: "LLM", render: (r) => llmModelName(r.llm_model_id) },
    {
      key: "started_at",
      label: "Elapsed",
      render: (r) => elapsed(r.started_at, r.finished_at),
    },
  ];

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [j, m, models, t] = await Promise.all([
        listJobs(),
        listMembers({ limit: 100 }),
        listLlmModels({ limit: 100 }),
        listTasks({ limit: 200 }),
      ]);
      setJobs(j);
      setMembers(m);
      setLlmModels(models);
      setTasks(t);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDetail = useCallback(async (jobId: string) => {
    setDetail(null);
    setDetailError(null);
    try {
      setDetail(await getJobDetail(jobId));
    } catch (err) {
      setDetail(null);
      setDetailError(err instanceof Error ? err.message : "Failed to load job detail");
    }
  }, []);

  useEffect(() => {
    loadList();
  }, [loadList]);

  useEffect(() => {
    if (selectedId) {
      loadDetail(selectedId);
    } else {
      setDetail(null);
      setDetailError(null);
    }
  }, [selectedId, loadDetail]);

  function handleSelect(row: JobSummary) {
    navigateTo("jobs", row.job_id);
  }

  const queuedCount = jobs.filter((j) => j.phase === "queued").length;
  const activeCount = jobs.filter((j) => ["assembling", "rendering", "calling", "processing", "validating"].includes(j.phase)).length;
  const completedCount = jobs.filter((j) => j.phase === "completed").length;
  const failedCount = jobs.filter((j) => j.phase === "failed").length;

  return (
    <div className="space-y-6">
      <Panel title="Jobs">
        <div className="mb-4 flex flex-wrap items-center gap-4">
          <Status label="Queued" value={queuedCount} />
          <Status label="Active" value={activeCount} tone={activeCount > 0 ? "warn" : undefined} />
          <Status label="Completed" value={completedCount} tone="ok" />
          <Status label="Failed" value={failedCount} tone={failedCount > 0 ? "warn" : undefined} />
          <Status label="Visible" value={filteredJobs.length} />
        </div>

        <div className="mb-4 grid gap-3 lg:grid-cols-[minmax(16rem,1fr)_10rem_10rem_auto]">
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search jobs" />
          <Select value={filterPhase} onChange={(e) => setFilterPhase(e.target.value)}>
            <option value="">All Phases</option>
            <option value="queued">Queued</option>
            <option value="assembling">Assembling</option>
            <option value="rendering">Rendering</option>
            <option value="calling">Calling</option>
            <option value="processing">Processing</option>
            <option value="validating">Validating</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </Select>
          <Select value={filterState} onChange={(e) => setFilterState(e.target.value)}>
            <option value="">All States</option>
            <option value="pending">Pending</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </Select>
        </div>

        {error && <ErrorState message={error} />}

        {loading ? (
          <LoadingState />
        ) : (
          <DataTable data={filteredJobs} columns={columns} selectedId={selectedId ?? undefined} onSelect={handleSelect} />
        )}
      </Panel>

      <Dialog open={Boolean(selectedId)} onOpenChange={(open) => { if (!open) navigateTo("jobs"); }}>
        <DialogContent className="block max-h-[calc(100vh-2rem)] w-[calc(100vw-2rem)] max-w-4xl overflow-hidden p-0">
          {detailError && (
            <div className="space-y-4 p-6">
              <DialogHeader>
                <DialogTitle>Job Details</DialogTitle>
                <DialogDescription>Job detail could not be loaded.</DialogDescription>
              </DialogHeader>
              <ErrorState message={detailError} />
            </div>
          )}
          {!detail && !detailError && (
            <div className="space-y-4 p-6">
              <DialogHeader>
                <DialogTitle>Job Details</DialogTitle>
                <DialogDescription>Loading job detail.</DialogDescription>
              </DialogHeader>
              <LoadingState />
            </div>
          )}
          {detail && (
            <div className="flex max-h-[calc(100vh-2rem)] flex-col">
              <div className="border-b px-6 py-5">
                <DialogHeader>
                  <DialogTitle className="flex items-center gap-3 text-xl">
                    <Zap className="h-5 w-5 text-muted-foreground" />
                    <span className="font-mono text-base">{detail.job_id.slice(0, 12)}...</span>
                    <Badge variant={phaseBadgeVariant(detail.phase)}>{detail.phase}</Badge>
                    <Badge variant="secondary">{detail.state}</Badge>
                  </DialogTitle>
                  <DialogDescription>
                    Task: <button className="text-primary underline" onClick={() => navigateTo("tasks", detail.task_id)}>{detail.task_id}</button>
                    {" · "}Elapsed: {elapsed(detail.started_at, detail.finished_at)}
                  </DialogDescription>
                </DialogHeader>
              </div>
              <div className="overflow-y-auto px-6 py-5">
                <Tabs defaultValue="overview" className="space-y-5">
                  <TabsList className="flex h-auto flex-wrap justify-start">
                    <TabsTrigger value="overview">Overview</TabsTrigger>
                    <TabsTrigger value="prompt">Prompt</TabsTrigger>
                    <TabsTrigger value="result">Result</TabsTrigger>
                  </TabsList>
                  <TabsContent value="overview">
                    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                      <Definition label="Job ID" value={detail.job_id} />
                      <Definition label="Task ID" value={detail.task_id} />
                      <Definition label="Phase" value={<Badge variant={phaseBadgeVariant(detail.phase)}>{detail.phase}</Badge>} />
                      <Definition label="State" value={detail.state} />
                      <Definition label="Assignee" value={memberName(detail.member_id)} />
                      <Definition label="LLM Model" value={llmModelName(detail.llm_model_id)} />
                      <Definition label="Started" value={formatDate(detail.started_at)} />
                      <Definition label="Finished" value={formatDate(detail.finished_at)} />
                      <Definition label="Elapsed" value={elapsed(detail.started_at, detail.finished_at)} />
                      {detail.error && <Definition label="Error" value={detail.error} />}
                    </div>
                  </TabsContent>
                  <TabsContent value="prompt">
                    {detail.rendered_prompt ? (
                      <pre className="whitespace-pre-wrap rounded-md bg-muted p-4 font-mono text-sm">{detail.rendered_prompt}</pre>
                    ) : (
                      <div className="rounded-md border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
                        No rendered prompt yet
                      </div>
                    )}
                  </TabsContent>
                  <TabsContent value="result">
                    {Object.keys(detail.result_report).length > 0 ? (
                      <pre className="whitespace-pre-wrap rounded-md bg-muted p-4 font-mono text-sm">
                        {JSON.stringify(detail.result_report, null, 2)}
                      </pre>
                    ) : (
                      <div className="rounded-md border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
                        No result report yet
                      </div>
                    )}
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
