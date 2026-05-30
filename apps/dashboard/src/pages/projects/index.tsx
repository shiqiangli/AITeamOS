/**
 * AITeamOS Dashboard - Project Management Page
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { ExternalLink, FolderKanban, Plus, Trash2, Users } from "lucide-react";
import { Panel, DataTable, Definition, FormField, LoadingState, ErrorState, navigateTo, ComboInput, Status, type Column } from "../../components/shared";
import { useToast } from "../../components/ui/use-toast";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
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
  listProjects,
  listDepartments,
  listMembers,
  getProjectDetail,
  createProject,
  assignMemberToProject,
  deleteProject,
  type ProjectSummary,
  type ProjectDetail,
  type DepartmentSummary,
  type MemberSummary,
} from "../../api/client";

function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

export function ProjectPage({ selectedId }: { selectedId: string | null }) {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [departments, setDepartments] = useState<DepartmentSummary[]>([]);
  const [members, setMembers] = useState<MemberSummary[]>([]);
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState("");

  const [formName, setFormName] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formDeptId, setFormDeptId] = useState("");
  const [formRepoUrl, setFormRepoUrl] = useState("");
  const [assignMemberId, setAssignMemberId] = useState("");
  const [showAssignMember, setShowAssignMember] = useState(false);

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

  const filteredProjects = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return projects.filter((project) => {
      const matchesSearch = !needle
        || project.name.toLowerCase().includes(needle)
        || project.id.toLowerCase().includes(needle);
      const matchesStatus = !filterStatus || project.status === filterStatus;
      return matchesSearch && matchesStatus;
    });
  }, [filterStatus, projects, search]);

  const activeCount = projects.filter((project) => project.status === "active").length;
  const archivedCount = projects.filter((project) => project.status === "archived").length;

  const columns: Column<ProjectSummary>[] = [
    { key: "name", label: "Name" },
    { key: "status", label: "Status", render: (r) => <Badge variant={r.status === "active" ? "success" : "secondary"}>{r.status}</Badge> },
    { key: "department_id", label: "Department", render: (r) => deptName(r.department_id) },
    { key: "member_count", label: "Members" },
    { key: "created_at", label: "Created", render: (r) => formatDate(r.created_at) },
  ];

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [p, d, m] = await Promise.all([
        listProjects({ limit: 100 }),
        listDepartments(0, 100),
        listMembers({ limit: 100 }),
      ]);
      setProjects(p);
      setDepartments(d);
      setMembers(m);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDetail = useCallback(async (id: string) => {
    setDetail(null);
    setDetailError(null);
    try {
      setDetail(await getProjectDetail(id));
    } catch (err) {
      setDetail(null);
      setDetailError(err instanceof Error ? err.message : "Failed to load project detail");
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

  function handleSelect(row: ProjectSummary) {
    navigateTo("projects", row.id);
  }

  const { toast } = useToast();

  async function handleDelete() {
    if (!detail) return;
    if (!confirm(`Delete project "${detail.name}"? This cannot be undone.`)) return;
    try {
      await deleteProject(detail.id);
      setDetail(null);
      navigateTo("projects");
      toast({ title: "Project deleted" });
      await loadList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  async function handleCreate() {
    if (!formName.trim() || !formDeptId) return;
    const dept = departments.find((d) => d.name === formDeptId || d.id === formDeptId);
    if (!dept) {
      setError("Department not found");
      return;
    }
    try {
      const refs = formRepoUrl.trim() ? [formRepoUrl.trim()] : [];
      const created = await createProject({
        name: formName.trim(),
        description: formDescription.trim() || undefined,
        department_id: dept.id,
        repository_refs: refs.length > 0 ? refs : undefined,
      });
      setShowCreate(false);
      setFormName("");
      setFormDescription("");
      setFormDeptId("");
      setFormRepoUrl("");
      await loadList();
      navigateTo("projects", created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    }
  }

  async function handleAssignMember() {
    if (!detail || !assignMemberId) return;
    const mem = members.find((m) => m.display_name === assignMemberId || m.id === assignMemberId);
    if (!mem) {
      setError("Member not found");
      return;
    }
    try {
      await assignMemberToProject(detail.id, mem.id);
      setAssignMemberId("");
      setShowAssignMember(false);
      await loadDetail(detail.id);
      await loadList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Assign member failed");
    }
  }

  return (
    <div className="space-y-6">
      <Panel title="Projects">
        <div className="mb-4 flex flex-wrap items-center gap-4">
          <Status label="Active" value={activeCount} tone={activeCount > 0 ? "ok" : undefined} />
          <Status label="Archived" value={archivedCount} />
          <Status label="Visible" value={filteredProjects.length} />
        </div>

        <div className="mb-4 grid gap-3 lg:grid-cols-[minmax(16rem,1fr)_12rem_auto]">
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search projects" />
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
          >
            <option value="">All Statuses</option>
            <option value="active">Active</option>
            <option value="paused">Paused</option>
            <option value="archived">Archived</option>
          </select>
          <Button variant="recommended" onClick={() => setShowCreate(!showCreate)}>
            {showCreate ? "Cancel" : <><Plus className="h-4 w-4" />Create Project</>}
          </Button>
        </div>

        {error && <ErrorState message={error} />}

        {showCreate && (
          <div className="mb-4 grid gap-4 rounded-md border p-4 lg:grid-cols-2">
            <FormField label="Project Name">
              <Input value={formName} onChange={(e) => setFormName(e.target.value)} placeholder="Unique project name" />
            </FormField>
            <FormField label="Department">
              <ComboInput
                value={formDeptId}
                onChange={setFormDeptId}
                options={departments.map((d) => ({ value: d.name, label: d.name }))}
                placeholder="Select or type department name"
              />
            </FormField>
            <FormField label="Description" wide>
              <Textarea value={formDescription} onChange={(e) => setFormDescription(e.target.value)} placeholder="Project description..." />
            </FormField>
            <FormField label="Repository URL" wide>
              <Input value={formRepoUrl} onChange={(e) => setFormRepoUrl(e.target.value)} placeholder="https://github.com/org/repo or /path/to/local/repo" />
            </FormField>
            <div className="col-span-full flex items-center gap-2">
              <Button variant="recommended" disabled={!formName.trim() || !formDeptId} onClick={handleCreate}>
                <Plus className="h-4 w-4" />Create
              </Button>
            </div>
          </div>
        )}

        {loading ? (
          <LoadingState />
        ) : (
          <DataTable data={filteredProjects} columns={columns} selectedId={selectedId ?? undefined} onSelect={handleSelect} />
        )}
      </Panel>

      <Dialog open={Boolean(selectedId)} onOpenChange={(open) => { if (!open) navigateTo("projects"); }}>
        <DialogContent className="block max-h-[calc(100vh-2rem)] w-[calc(100vw-2rem)] max-w-5xl overflow-hidden p-0">
          {detailError && (
            <div className="space-y-4 p-6">
              <DialogHeader>
                <DialogTitle>Project Details</DialogTitle>
                <DialogDescription>Project detail could not be loaded.</DialogDescription>
              </DialogHeader>
              <ErrorState message={detailError} />
            </div>
          )}
          {!detail && !detailError && (
            <div className="space-y-4 p-6">
              <DialogHeader>
                <DialogTitle>Project Details</DialogTitle>
                <DialogDescription>Loading project detail.</DialogDescription>
              </DialogHeader>
              <LoadingState />
            </div>
          )}
          {detail && (
            <div className="flex max-h-[calc(100vh-2rem)] flex-col">
              <div className="border-b px-6 py-5">
                <DialogHeader>
                  <DialogTitle className="flex flex-wrap items-center gap-3 text-xl">
                    <FolderKanban className="h-5 w-5 text-muted-foreground" />
                    <span>{detail.name}</span>
                    <Badge variant={detail.status === "active" ? "success" : "secondary"}>{detail.status}</Badge>
                  </DialogTitle>
                  <DialogDescription>{deptName(detail.department_id)}</DialogDescription>
                </DialogHeader>
              </div>
              <div className="overflow-y-auto px-6 py-5">
                <Tabs defaultValue="overview" className="space-y-5">
                  <TabsList className="flex h-auto flex-wrap justify-start">
                    <TabsTrigger value="overview">Overview</TabsTrigger>
                    <TabsTrigger value="members">Members</TabsTrigger>
                    <TabsTrigger value="repositories">Repositories</TabsTrigger>
                    <TabsTrigger value="actions">Actions</TabsTrigger>
                  </TabsList>
                  <TabsContent value="overview">
                    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                      <Definition label="Name" value={detail.name} />
                      <Definition label="Description" value={detail.description} />
                      <Definition label="Status" value={<Badge variant={detail.status === "active" ? "success" : "secondary"}>{detail.status}</Badge>} />
                      <Definition label="Department" value={deptName(detail.department_id)} />
                      <Definition label="Members" value={detail.member_ids?.length ?? 0} />
                      <Definition label="Created" value={formatDate(detail.created_at)} />
                      <Definition label="Project ID" value={detail.id} />
                    </div>
                  </TabsContent>
                  <TabsContent value="members">
                    {detail.member_ids?.length ? (
                      <div className="divide-y rounded-md border">
                        {detail.member_ids.map((id) => (
                          <button key={id} type="button" className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm hover:bg-muted" onClick={() => navigateTo("members", id)}>
                            <span className="flex min-w-0 items-center gap-2"><Users className="h-4 w-4 text-muted-foreground" /><span className="truncate font-medium">{memberName(id)}</span></span>
                            <ExternalLink className="h-4 w-4 text-muted-foreground" />
                          </button>
                        ))}
                      </div>
                    ) : (
                      <div className="rounded-md border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">No members assigned</div>
                    )}
                  </TabsContent>
                  <TabsContent value="repositories">
                    {detail.repository_refs?.length ? (
                      <div className="space-y-2">
                        {detail.repository_refs.map((ref) => (
                          <div key={ref} className="rounded-md bg-muted p-3 font-mono text-sm break-all">{ref}</div>
                        ))}
                      </div>
                    ) : (
                      <div className="rounded-md border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">No repository refs</div>
                    )}
                  </TabsContent>
                  <TabsContent value="actions">
                    <div className="space-y-4">
                      <div className="flex flex-wrap items-center gap-2">
                        {showAssignMember ? (
                          <>
                            <ComboInput
                              value={assignMemberId}
                              onChange={setAssignMemberId}
                              options={members.map((m) => ({ value: m.display_name, label: m.display_name }))}
                              placeholder="Select or type member name"
                              className="w-64"
                            />
                            <Button variant="recommended" onClick={handleAssignMember}>Confirm</Button>
                            <Button variant="outline" onClick={() => { setShowAssignMember(false); setAssignMemberId(""); }}>Cancel</Button>
                          </>
                        ) : (
                          <Button variant="outline" onClick={() => setShowAssignMember(true)}><Users className="h-4 w-4" />Assign Member</Button>
                        )}
                        <Button variant="outline" onClick={handleDelete} className="border-destructive text-destructive">
                          <Trash2 className="h-4 w-4" />Delete
                        </Button>
                      </div>
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
