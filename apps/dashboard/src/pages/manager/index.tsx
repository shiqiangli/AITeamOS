/**
 * AITeamOS Dashboard - Department Management Page
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Building2, ExternalLink, Plus, Trash2, Users } from "lucide-react";
import { Panel, DataTable, Definition, FormField, LoadingState, ErrorState, ComboInput, navigateTo, Status, type Column } from "../../components/shared";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
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
  listDepartments,
  listMembers,
  listProjects,
  createDepartment,
  deleteDepartment,
  type DepartmentSummary,
  type MemberSummary,
  type ProjectSummary,
} from "../../api/client";
import { useToast } from "../../components/ui/use-toast";

function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

export function DepartmentPage({ selectedId }: { selectedId: string | null }) {
  const [departments, setDepartments] = useState<DepartmentSummary[]>([]);
  const [members, setMembers] = useState<MemberSummary[]>([]);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [search, setSearch] = useState("");

  const [formName, setFormName] = useState("");
  const [formLeaderId, setFormLeaderId] = useState("");

  const memberName = useCallback((id: string | null) => {
    if (!id) return "-";
    const m = members.find((mem) => mem.id === id);
    return m ? m.display_name : id.length > 8 ? `${id.slice(0, 8)}...` : id;
  }, [members]);

  const selectedDepartment = useMemo(
    () => departments.find((department) => department.id === selectedId) ?? null,
    [departments, selectedId],
  );

  const selectedMembers = useMemo(
    () => members.filter((member) => member.department_id === selectedId),
    [members, selectedId],
  );

  const selectedProjects = useMemo(
    () => projects.filter((project) => project.department_id === selectedId),
    [projects, selectedId],
  );

  const filteredDepartments = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return departments.filter((department) => {
      return !needle
        || department.name.toLowerCase().includes(needle)
        || department.id.toLowerCase().includes(needle);
    });
  }, [departments, search]);

  const columns: Column<DepartmentSummary>[] = [
    { key: "name", label: "Name" },
    { key: "leader_member_id", label: "Leader", render: (r) => memberName(r.leader_member_id) },
    { key: "created_at", label: "Created", render: (r) => formatDate(r.created_at) },
  ];

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [d, m, p] = await Promise.all([
        listDepartments(0, 100),
        listMembers({ limit: 100 }),
        listProjects({ limit: 100 }),
      ]);
      setDepartments(d);
      setMembers(m);
      setProjects(p);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadList(); }, [loadList]);

  async function handleCreate() {
    if (!formName.trim()) return;
    let leaderId: string | undefined = undefined;
    if (formLeaderId) {
      const mem = members.find((m) => m.display_name === formLeaderId || m.id === formLeaderId);
      if (!mem) {
        setError("Leader member not found");
        return;
      }
      leaderId = mem.id;
    }
    try {
      const created = await createDepartment({
        name: formName.trim(),
        leader_member_id: leaderId,
      });
      setShowCreate(false);
      setFormName("");
      setFormLeaderId("");
      await loadList();
      navigateTo("departments", created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    }
  }

  const { toast } = useToast();

  async function handleDelete() {
    if (!selectedDepartment) return;
    if (!confirm(`Delete department "${selectedDepartment.name}"? This cannot be undone.`)) return;
    try {
      await deleteDepartment(selectedDepartment.id);
      navigateTo("departments");
      toast({ title: "Department deleted" });
      await loadList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  return (
    <div className="space-y-6">
      <Panel title="Departments">
        <div className="mb-4 flex flex-wrap items-center gap-4">
          <Status label="Departments" value={departments.length} tone={departments.length > 0 ? "ok" : undefined} />
          <Status label="Members" value={members.length} />
          <Status label="Projects" value={projects.length} />
          <Status label="Visible" value={filteredDepartments.length} />
        </div>

        <div className="mb-4 grid gap-3 lg:grid-cols-[minmax(16rem,1fr)_auto]">
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search departments" />
          <Button variant="recommended" onClick={() => setShowCreate(!showCreate)}>
            {showCreate ? "Cancel" : <><Plus className="h-4 w-4" />Create Department</>}
          </Button>
        </div>

        {error && <ErrorState message={error} />}

        {showCreate && (
          <div className="mb-4 grid gap-4 rounded-md border p-4 lg:grid-cols-2">
            <FormField label="Department Name">
              <Input value={formName} onChange={(e) => setFormName(e.target.value)} placeholder="Unique department name" />
            </FormField>
            <FormField label="Leader">
              <ComboInput
                value={formLeaderId}
                onChange={setFormLeaderId}
                options={members.map((m) => ({ value: m.display_name, label: `${m.display_name} (${m.kind})` }))}
                placeholder="Select or type member name"
              />
            </FormField>
            <div className="col-span-full flex items-center gap-2">
              <Button variant="recommended" disabled={!formName.trim()} onClick={handleCreate}>
                <Plus className="h-4 w-4" />Create
              </Button>
            </div>
          </div>
        )}

        {loading ? (
          <LoadingState />
        ) : (
          <DataTable data={filteredDepartments} columns={columns} selectedId={selectedId ?? undefined} onSelect={(row) => navigateTo("departments", row.id)} />
        )}
      </Panel>

      <Dialog open={Boolean(selectedId)} onOpenChange={(open) => { if (!open) navigateTo("departments"); }}>
        <DialogContent className="block max-h-[calc(100vh-2rem)] w-[calc(100vw-2rem)] max-w-5xl overflow-hidden p-0">
          {!selectedDepartment && (
            <div className="space-y-4 p-6">
              <DialogHeader>
                <DialogTitle>Department Details</DialogTitle>
                <DialogDescription>Loading department detail.</DialogDescription>
              </DialogHeader>
              <LoadingState />
            </div>
          )}
          {selectedDepartment && (
            <div className="flex max-h-[calc(100vh-2rem)] flex-col">
              <div className="border-b px-6 py-5">
                <DialogHeader>
                  <DialogTitle className="flex flex-wrap items-center gap-3 text-xl">
                    <Building2 className="h-5 w-5 text-muted-foreground" />
                    <span>{selectedDepartment.name}</span>
                  </DialogTitle>
                  <DialogDescription>{selectedMembers.length} members, {selectedProjects.length} projects</DialogDescription>
                </DialogHeader>
              </div>
              <div className="overflow-y-auto px-6 py-5">
                <Tabs defaultValue="overview" className="space-y-5">
                  <TabsList className="flex h-auto flex-wrap justify-start">
                    <TabsTrigger value="overview">Overview</TabsTrigger>
                    <TabsTrigger value="members">Members</TabsTrigger>
                    <TabsTrigger value="projects">Projects</TabsTrigger>
                    <TabsTrigger value="actions">Actions</TabsTrigger>
                  </TabsList>
                  <TabsContent value="overview">
                    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                      <Definition label="Name" value={selectedDepartment.name} />
                      <Definition label="Leader" value={memberName(selectedDepartment.leader_member_id)} />
                      <Definition label="Members" value={selectedMembers.length} />
                      <Definition label="Projects" value={selectedProjects.length} />
                      <Definition label="Created" value={formatDate(selectedDepartment.created_at)} />
                      <Definition label="Department ID" value={selectedDepartment.id} />
                    </div>
                  </TabsContent>
                  <TabsContent value="members">
                    {selectedMembers.length ? (
                      <div className="divide-y rounded-md border">
                        {selectedMembers.map((member) => (
                          <button key={member.id} type="button" className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm hover:bg-muted" onClick={() => navigateTo("members", member.id)}>
                            <span className="flex min-w-0 items-center gap-2"><Users className="h-4 w-4 text-muted-foreground" /><span className="truncate font-medium">{member.display_name}</span></span>
                            <span className="flex shrink-0 items-center gap-2"><Badge variant="secondary">{member.kind}</Badge><ExternalLink className="h-4 w-4 text-muted-foreground" /></span>
                          </button>
                        ))}
                      </div>
                    ) : (
                      <div className="rounded-md border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">No members in this department</div>
                    )}
                  </TabsContent>
                  <TabsContent value="projects">
                    {selectedProjects.length ? (
                      <div className="divide-y rounded-md border">
                        {selectedProjects.map((project) => (
                          <button key={project.id} type="button" className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm hover:bg-muted" onClick={() => navigateTo("projects", project.id)}>
                            <span className="truncate font-medium">{project.name}</span>
                            <span className="flex shrink-0 items-center gap-2"><Badge variant="secondary">{project.status}</Badge><ExternalLink className="h-4 w-4 text-muted-foreground" /></span>
                          </button>
                        ))}
                      </div>
                    ) : (
                      <div className="rounded-md border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">No projects in this department</div>
                    )}
                  </TabsContent>
                  <TabsContent value="actions">
                    <Button variant="outline" onClick={handleDelete} className="border-destructive text-destructive">
                      <Trash2 className="h-4 w-4" />Delete
                    </Button>
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
