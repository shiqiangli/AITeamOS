/**
 * AITeamOS Dashboard - Skill Management Page
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Plus, Trash2, Wrench } from "lucide-react";
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
  type SkillSummary,
  type SkillDetail,
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
    case "recalibrating":
      return "warning";
    case "deprecated":
    case "cancelled":
      return "danger";
    default:
      return "secondary";
  }
}

function parseList(value: string): string[] {
  return value
    .split(/\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseSideEffects(value: string): Record<string, string>[] {
  return value
    .split(/\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [resource_kind = "resource", resource_pattern = line, mutation_kind = "read"] = line
        .split(":")
        .map((part) => part.trim());
      return { resource_kind, resource_pattern, mutation_kind };
    });
}

function formatList(values: string[] | null | undefined): string {
  return values?.length ? values.join("\n") : "-";
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

  const [formName, setFormName] = useState("");
  const [formVersion, setFormVersion] = useState("1.0.0");
  const [formDescription, setFormDescription] = useState("");
  const [formDomain, setFormDomain] = useState("");
  const [formTags, setFormTags] = useState("");
  const [formInputs, setFormInputs] = useState("");
  const [formOutputs, setFormOutputs] = useState("");
  const [formPreconditions, setFormPreconditions] = useState("");
  const [formSideEffects, setFormSideEffects] = useState("");
  const [formPermissions, setFormPermissions] = useState("");
  const [formExamples, setFormExamples] = useState("");
  const [formReferences, setFormReferences] = useState("");
  const [formQualitySignals, setFormQualitySignals] = useState("");

  const columns: Column<SkillSummary>[] = [
    { key: "name", label: "Name" },
    { key: "domain", label: "Domain" },
    { key: "version", label: "Version" },
    { key: "status", label: "Status", render: (r) => <Badge variant={statusVariant(r.status)}>{r.status}</Badge> },
    { key: "circuit_state", label: "Circuit" },
    { key: "capability_tags", label: "Tags" },
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
  const openCircuitCount = skills.filter((skill) => skill.circuit_state === "open").length;

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
    } else {
      setDetail(null);
      setDetailError(null);
    }
  }, [selectedId, loadDetail]);

  function handleSelect(row: SkillSummary) {
    navigateTo("skills", row.id);
  }

  async function handleCreate() {
    if (!formName.trim()) return;
    try {
      const tags = formTags.split(",").map((t) => t.trim()).filter(Boolean);
      const qualitySignals = parseList(formQualitySignals);
      const created = await registerSkill({
        name: formName.trim(),
        version: formVersion.trim() || "1.0.0",
        description: formDescription.trim() || undefined,
        domain: formDomain.trim() || undefined,
        inputs: parseList(formInputs),
        outputs: parseList(formOutputs),
        preconditions: parseList(formPreconditions),
        side_effects: parseSideEffects(formSideEffects),
        required_permissions: parseList(formPermissions),
        capability_tags: tags.length > 0 ? tags : undefined,
        examples: parseList(formExamples),
        references: parseList(formReferences),
        quality_signals: qualitySignals.length > 0 ? { signals: qualitySignals } : undefined,
      });
      setShowCreate(false);
      setFormName("");
      setFormVersion("1.0.0");
      setFormDescription("");
      setFormDomain("");
      setFormTags("");
      setFormInputs("");
      setFormOutputs("");
      setFormPreconditions("");
      setFormSideEffects("");
      setFormPermissions("");
      setFormExamples("");
      setFormReferences("");
      setFormQualitySignals("");
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

  return (
    <div className="space-y-6">
      <Panel title="Skills">
        <div className="mb-4 flex flex-wrap items-center gap-4">
          <Status label="Published" value={publishedCount} tone={publishedCount > 0 ? "ok" : undefined} />
          <Status label="Draft" value={draftCount} tone={draftCount > 0 ? "warn" : undefined} />
          <Status label="Open Circuit" value={openCircuitCount} tone={openCircuitCount > 0 ? "warn" : undefined} />
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
              <Input value={formDomain} onChange={(e) => setFormDomain(e.target.value)} placeholder="compiler" />
            </FormField>
            <FormField label="Capability Tags">
              <Input value={formTags} onChange={(e) => setFormTags(e.target.value)} placeholder="compiler, optimization, pass" />
            </FormField>
            <FormField label="Description" wide>
              <Textarea value={formDescription} onChange={(e) => setFormDescription(e.target.value)} placeholder="What this capability means in general terms." />
            </FormField>
            <FormField label="Inputs">
              <Textarea value={formInputs} onChange={(e) => setFormInputs(e.target.value)} placeholder={"target project\nIR or pass pipeline context\noptimization goal"} />
            </FormField>
            <FormField label="Outputs">
              <Textarea value={formOutputs} onChange={(e) => setFormOutputs(e.target.value)} placeholder={"code patch\ntests\nvalidation report"} />
            </FormField>
            <FormField label="Preconditions">
              <Textarea value={formPreconditions} onChange={(e) => setFormPreconditions(e.target.value)} placeholder={"project builds locally\npass pipeline is known"} />
            </FormField>
            <FormField label="Side Effects">
              <Textarea value={formSideEffects} onChange={(e) => setFormSideEffects(e.target.value)} placeholder={"filesystem: src/**/*.cpp: write\ncommand: test suite: read"} />
            </FormField>
            <FormField label="Permissions">
              <Textarea value={formPermissions} onChange={(e) => setFormPermissions(e.target.value)} placeholder={"repo.read\nrepo.write\ncommand.run"} />
            </FormField>
            <FormField label="Quality Signals">
              <Textarea value={formQualitySignals} onChange={(e) => setFormQualitySignals(e.target.value)} placeholder={"tests pass\nIR diff is expected\nno compile-time regression"} />
            </FormField>
            <FormField label="Examples">
              <Textarea value={formExamples} onChange={(e) => setFormExamples(e.target.value)} placeholder={"add a CSE pass\nadd a dead-code cleanup pass"} />
            </FormField>
            <FormField label="References">
              <Textarea value={formReferences} onChange={(e) => setFormReferences(e.target.value)} placeholder={"docs/passes.md\ncompiler optimization guide"} />
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
        <DialogContent className="block max-h-[calc(100vh-2rem)] w-[calc(100vw-2rem)] max-w-5xl overflow-hidden p-0">
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
                    <TabsTrigger value="contract">Contract</TabsTrigger>
                    <TabsTrigger value="effects">Effects</TabsTrigger>
                    <TabsTrigger value="examples">Examples</TabsTrigger>
                    <TabsTrigger value="health">Health</TabsTrigger>
                    <TabsTrigger value="actions">Actions</TabsTrigger>
                  </TabsList>
                  <TabsContent value="overview">
                    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                      <Definition label="Name" value={detail.name} />
                      <Definition label="Domain" value={detail.domain || "-"} />
                      <Definition label="Version" value={detail.version} />
                      <Definition label="Status" value={<Badge variant={statusVariant(detail.status)}>{detail.status}</Badge>} />
                      <Definition label="Circuit State" value={detail.circuit_state} />
                      <Definition label="Tags" value={detail.capability_tags?.join(", ") || "-"} />
                      <Definition label="Created" value={formatDate(detail.created_at)} />
                    </div>
                    {detail.description && (
                      <p className="mt-4 whitespace-pre-wrap rounded-md border p-4 text-sm">{detail.description}</p>
                    )}
                  </TabsContent>
                  <TabsContent value="contract">
                    <div className="grid gap-4 md:grid-cols-3">
                      <div>
                        <h3 className="mb-2 text-sm font-medium">Inputs</h3>
                        <pre className="whitespace-pre-wrap rounded-md bg-muted p-4 font-mono text-sm">{formatList(detail.inputs)}</pre>
                      </div>
                      <div>
                        <h3 className="mb-2 text-sm font-medium">Outputs</h3>
                        <pre className="whitespace-pre-wrap rounded-md bg-muted p-4 font-mono text-sm">{formatList(detail.outputs)}</pre>
                      </div>
                      <div>
                        <h3 className="mb-2 text-sm font-medium">Preconditions</h3>
                        <pre className="whitespace-pre-wrap rounded-md bg-muted p-4 font-mono text-sm">{formatList(detail.preconditions)}</pre>
                      </div>
                    </div>
                  </TabsContent>
                  <TabsContent value="effects">
                    <div className="grid gap-4 md:grid-cols-3">
                      <div>
                        <h3 className="mb-2 text-sm font-medium">Side Effects</h3>
                        <pre className="whitespace-pre-wrap rounded-md bg-muted p-4 font-mono text-sm">
                          {detail.side_effects?.length ? JSON.stringify(detail.side_effects, null, 2) : "-"}
                        </pre>
                      </div>
                      <div>
                        <h3 className="mb-2 text-sm font-medium">Permissions</h3>
                        <pre className="whitespace-pre-wrap rounded-md bg-muted p-4 font-mono text-sm">{formatList(detail.required_permissions)}</pre>
                      </div>
                      <div>
                        <h3 className="mb-2 text-sm font-medium">Quality Signals</h3>
                        <pre className="whitespace-pre-wrap rounded-md bg-muted p-4 font-mono text-sm">
                          {Object.keys(detail.quality_signals ?? {}).length ? JSON.stringify(detail.quality_signals, null, 2) : "-"}
                        </pre>
                      </div>
                    </div>
                  </TabsContent>
                  <TabsContent value="examples">
                    <div className="grid gap-4 md:grid-cols-2">
                      <div>
                        <h3 className="mb-2 text-sm font-medium">Examples</h3>
                        <pre className="whitespace-pre-wrap rounded-md bg-muted p-4 font-mono text-sm">{formatList(detail.examples)}</pre>
                      </div>
                      <div>
                        <h3 className="mb-2 text-sm font-medium">References</h3>
                        <pre className="whitespace-pre-wrap rounded-md bg-muted p-4 font-mono text-sm">{formatList(detail.references)}</pre>
                      </div>
                    </div>
                  </TabsContent>
                  <TabsContent value="health">
                    <pre className="whitespace-pre-wrap rounded-md bg-muted p-4 font-mono text-sm">
                      {JSON.stringify(detail.health ?? {}, null, 2)}
                    </pre>
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
