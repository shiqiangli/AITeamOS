/**
 * AITeamOS Dashboard - Skill Management Page
 *
 * Skill = 角色能力标签，绑定到 Member。
 * 表存元数据索引，SKILL.md 存程序性上下文。
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Plus, Trash2, Wrench, Pencil } from "lucide-react";
import { Panel, DataTable, Definition, FormField, LoadingState, ErrorState, navigateTo, Status, type Column } from "../../components/shared";
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
  listSkills,
  getSkillDetail,
  registerSkill,
  publishSkill,
  deprecateSkill,
  deleteSkill,
  updateSkill,
  fetchSkillFile,
  type SkillSummary,
  type SkillDetail,
  type SkillFileResponse,
} from "../../api/client";
import { useToast } from "../../components/ui/use-toast";

function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

function statusVariant(status: string): "success" | "warning" | "secondary" | "danger" {
  switch (status) {
    case "published": return "success";
    case "draft":
    case "registered":
      return "warning";
    case "deprecated":
      return "danger";
    default:
      return "secondary";
  }
}

export function SkillPage({ selectedId }: { selectedId: string | null }) {
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [detail, setDetail] = useState<SkillDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState("");

  // Create form state
  const [formName, setFormName] = useState("");
  const [formVersion, setFormVersion] = useState("1.0.0");
  const [formDescription, setFormDescription] = useState("");
  const [formDomain, setFormDomain] = useState("");
  const [formTags, setFormTags] = useState("");

  // Edit form state
  const [isEditing, setIsEditing] = useState(false);
  const [editDescription, setEditDescription] = useState("");
  const [editDomain, setEditDomain] = useState("");
  const [editTags, setEditTags] = useState("");

  // SKILL.md file state
  const [skillFile, setSkillFile] = useState<SkillFileResponse | null>(null);
  const [skillFileLoading, setSkillFileLoading] = useState(false);

  const columns: Column<SkillSummary>[] = [
    { key: "name", label: "Name" },
    { key: "domain", label: "Domain" },
    { key: "version", label: "Version" },
    { key: "status", label: "Status", render: (r) => <Badge variant={statusVariant(r.status)}>{r.status}</Badge> },
    { key: "capability_tags", label: "Tags", render: (r) => r.capability_tags?.join(", ") || "-" },
    { key: "created_at", label: "Created", render: (r) => formatDate(r.created_at) },
  ];

  const filteredSkills = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return skills.filter((skill) => {
      const matchesSearch = !needle
        || skill.name.toLowerCase().includes(needle)
        || skill.id.toLowerCase().includes(needle);
      const matchesStatus = !filterStatus || skill.status === filterStatus;
      return matchesSearch && matchesStatus;
    });
  }, [filterStatus, search, skills]);

  const publishedCount = skills.filter((skill) => skill.status === "published").length;
  const draftCount = skills.filter((skill) => skill.status === "draft" || skill.status === "registered").length;

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSkills(await listSkills({ limit: 100 }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load skills");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDetail = useCallback(async (id: string) => {
    setDetail(null);
    setDetailError(null);
    try {
      setDetail(await getSkillDetail(id));
    } catch (err) {
      setDetail(null);
      setDetailError(err instanceof Error ? err.message : "Failed to load skill detail");
    }
  }, []);

  useEffect(() => { loadList(); }, [loadList]);
  useEffect(() => {
    if (selectedId) {
      loadDetail(selectedId);
      setIsEditing(false);
      // Load SKILL.md file content
      setSkillFileLoading(true);
      fetchSkillFile(selectedId)
        .then(setSkillFile)
        .catch(() => setSkillFile(null))
        .finally(() => setSkillFileLoading(false));
    } else {
      setDetail(null);
      setDetailError(null);
      setIsEditing(false);
      setSkillFile(null);
    }
  }, [selectedId, loadDetail]);

  function handleSelect(row: SkillSummary) {
    navigateTo("skills", row.id);
  }

  async function handleCreate() {
    if (!formName.trim()) return;
    try {
      const tags = formTags.split(",").map((t) => t.trim()).filter(Boolean);
      const created = await registerSkill({
        name: formName.trim(),
        version: formVersion.trim() || "1.0.0",
        description: formDescription.trim() || undefined,
        domain: formDomain.trim() || undefined,
        capability_tags: tags.length > 0 ? tags : undefined,
      });
      setShowCreate(false);
      setFormName("");
      setFormVersion("1.0.0");
      setFormDescription("");
      setFormDomain("");
      setFormTags("");
      await loadList();
      navigateTo("skills", created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    }
  }

  const { toast } = useToast();

  async function handleDelete() {
    if (!detail) return;
    if (!confirm(`Delete skill "${detail.name}"? This cannot be undone.`)) return;
    try {
      await deleteSkill(detail.id);
      setDetail(null);
      navigateTo("skills");
      toast({ title: "Skill deleted" });
      await loadList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  async function handlePublish() {
    if (!detail) return;
    try {
      await publishSkill(detail.id);
      await loadList();
      await loadDetail(detail.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Publish failed");
    }
  }

  async function handleDeprecate() {
    if (!detail) return;
    try {
      await deprecateSkill(detail.id, "Deprecated via dashboard");
      await loadList();
      await loadDetail(detail.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Deprecate failed");
    }
  }

  function startEditing() {
    if (!detail) return;
    setEditDescription(detail.description || "");
    setEditDomain(detail.domain || "");
    setEditTags(detail.capability_tags?.join(", ") || "");
    setIsEditing(true);
  }

  async function handleUpdate() {
    if (!detail) return;
    try {
      await updateSkill(detail.id, {
        description: editDescription.trim() || undefined,
        domain: editDomain.trim() || undefined,
        capability_tags: editTags.split(",").map((t) => t.trim()).filter(Boolean),
      });
      setIsEditing(false);
      await loadList();
      await loadDetail(detail.id);
      toast({ title: "Skill updated" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  return (
    <div className="space-y-6">
      <Panel title="Skills">
        <div className="mb-4 flex flex-wrap items-center gap-4">
          <Status label="Published" value={publishedCount} tone={publishedCount > 0 ? "ok" : undefined} />
          <Status label="Draft" value={draftCount} tone={draftCount > 0 ? "warn" : undefined} />
          <Status label="Visible" value={filteredSkills.length} />
        </div>

        <div className="mb-4 grid gap-3 lg:grid-cols-[minmax(16rem,1fr)_12rem_auto]">
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search skills" />
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
          >
            <option value="">All Statuses</option>
            <option value="draft">Draft</option>
            <option value="published">Published</option>
            <option value="deprecated">Deprecated</option>
          </select>
          <Button variant="recommended" onClick={() => setShowCreate(!showCreate)}>
            {showCreate ? "Cancel" : <><Plus className="h-4 w-4" />Register Skill</>}
          </Button>
        </div>

        {error && <ErrorState message={error} />}

        {showCreate && (
          <div className="mb-4 grid gap-4 rounded-md border p-4 lg:grid-cols-2">
            <FormField label="Skill Name">
              <Input value={formName} onChange={(e) => setFormName(e.target.value)} placeholder="unique-skill-name" />
            </FormField>
            <FormField label="Version">
              <Input value={formVersion} onChange={(e) => setFormVersion(e.target.value)} placeholder="1.0.0" />
            </FormField>
            <FormField label="Domain">
              <Input value={formDomain} onChange={(e) => setFormDomain(e.target.value)} placeholder="architecture" />
            </FormField>
            <FormField label="Capability Tags">
              <Input value={formTags} onChange={(e) => setFormTags(e.target.value)} placeholder="architecture, design, review" />
            </FormField>
            <FormField label="Description" wide>
              <Textarea value={formDescription} onChange={(e) => setFormDescription(e.target.value)} placeholder="What this capability means." />
            </FormField>
            <div className="col-span-full flex items-center gap-2">
              <Button variant="recommended" disabled={!formName.trim()} onClick={handleCreate}>
                <Plus className="h-4 w-4" />Register
              </Button>
            </div>
          </div>
        )}

        {loading ? (
          <LoadingState />
        ) : (
          <DataTable data={filteredSkills} columns={columns} selectedId={selectedId ?? undefined} onSelect={handleSelect} />
        )}
      </Panel>

      <Dialog open={Boolean(selectedId)} onOpenChange={(open) => { if (!open) navigateTo("skills"); }}>
        <DialogContent className="block max-h-[calc(100vh-2rem)] w-[calc(100vw-2rem)] max-w-3xl overflow-hidden p-0">
          {detailError && (
            <div className="space-y-4 p-6">
              <DialogHeader>
                <DialogTitle>Skill Details</DialogTitle>
                <DialogDescription>Skill detail could not be loaded.</DialogDescription>
              </DialogHeader>
              <ErrorState message={detailError} />
            </div>
          )}
          {!detail && !detailError && (
            <div className="space-y-4 p-6">
              <DialogHeader>
                <DialogTitle>Skill Details</DialogTitle>
                <DialogDescription>Loading skill detail.</DialogDescription>
              </DialogHeader>
              <LoadingState />
            </div>
          )}
          {detail && (
            <div className="flex max-h-[calc(100vh-2rem)] flex-col">
              <div className="border-b px-6 py-5">
                <DialogHeader>
                  <DialogTitle className="flex flex-wrap items-center gap-3 text-xl">
                    <Wrench className="h-5 w-5 text-muted-foreground" />
                    <span>{detail.name}</span>
                    <Badge variant={statusVariant(detail.status)}>{detail.status}</Badge>
                  </DialogTitle>
                  <DialogDescription>Version {detail.version}</DialogDescription>
                </DialogHeader>
              </div>
              <div className="overflow-y-auto px-6 py-5">
                <Tabs defaultValue="overview" className="space-y-5">
                  <TabsList className="flex h-auto flex-wrap justify-start">
                    <TabsTrigger value="overview">Overview</TabsTrigger>
                    <TabsTrigger value="edit">Edit</TabsTrigger>
                    <TabsTrigger value="skill-file">SKILL.md</TabsTrigger>
                    <TabsTrigger value="actions">Actions</TabsTrigger>
                  </TabsList>
                  <TabsContent value="overview">
                    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                      <Definition label="Name" value={detail.name} />
                      <Definition label="Domain" value={detail.domain || "-"} />
                      <Definition label="Version" value={detail.version} />
                      <Definition label="Status" value={<Badge variant={statusVariant(detail.status)}>{detail.status}</Badge>} />
                      <Definition label="Tags" value={detail.capability_tags?.join(", ") || "-"} />
                      <Definition label="Created" value={formatDate(detail.created_at)} />
                    </div>
                    {detail.description && (
                      <p className="mt-4 whitespace-pre-wrap rounded-md border p-4 text-sm">{detail.description}</p>
                    )}
                  </TabsContent>
                  <TabsContent value="edit">
                    {isEditing ? (
                      <div className="grid gap-4 lg:grid-cols-2">
                        <FormField label="Domain">
                          <Input value={editDomain} onChange={(e) => setEditDomain(e.target.value)} placeholder="architecture" />
                        </FormField>
                        <FormField label="Capability Tags">
                          <Input value={editTags} onChange={(e) => setEditTags(e.target.value)} placeholder="architecture, design, review" />
                        </FormField>
                        <FormField label="Description" wide>
                          <Textarea value={editDescription} onChange={(e) => setEditDescription(e.target.value)} placeholder="What this skill does..." />
                        </FormField>
                        <div className="col-span-full flex items-center gap-2">
                          <Button variant="recommended" onClick={handleUpdate}>Save Changes</Button>
                          <Button variant="outline" onClick={() => setIsEditing(false)}>Cancel</Button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center gap-3">
                        <Button variant="outline" onClick={startEditing}>
                          <Pencil className="h-4 w-4" />Edit Skill
                        </Button>
                        <span className="text-sm text-muted-foreground">Edit description, domain, and tags.</span>
                      </div>
                    )}
                  </TabsContent>
                  <TabsContent value="skill-file">
                    {skillFileLoading ? (
                      <LoadingState />
                    ) : skillFile?.exists ? (
                      <div className="space-y-2">
                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                          <span className="font-mono">{skillFile.file_path}</span>
                        </div>
                        <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-md border bg-muted p-4 font-mono text-sm leading-relaxed">
                          {skillFile.content}
                        </pre>
                        <p className="text-xs text-muted-foreground">
                          To edit this file, open it in your IDE at the path shown above.
                        </p>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <p className="text-sm text-muted-foreground">
                          No SKILL.md file found for this skill.
                        </p>
                        {skillFile && (
                          <p className="font-mono text-xs text-muted-foreground">
                            Expected path: {skillFile.file_path}
                          </p>
                        )}
                      </div>
                    )}
                  </TabsContent>
                  <TabsContent value="actions">
                    <div className="flex flex-wrap items-center gap-2">
                      {(detail.status === "registered" || detail.status === "draft") && (
                        <Button variant="recommended" onClick={handlePublish}>Publish</Button>
                      )}
                      {detail.status === "published" && (
                        <Button variant="outline" onClick={handleDeprecate}>Deprecate</Button>
                      )}
                      <Button variant="outline" onClick={handleDelete} className="border-destructive text-destructive">
                        <Trash2 className="h-4 w-4" />Delete
                      </Button>
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
