/**
 * AITeamOS Dashboard - Memory Management Page
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Archive, Brain, CheckCircle2, FileText, GitCompareArrows, Plus, ShieldCheck, Trash2, XCircle } from "lucide-react";
import { Panel, DataTable, Definition, FormField, LoadingState, ErrorState, navigateTo, Status, ComboInput, type Column } from "../../components/shared";
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
  listMemories,
  getMemoryDetail,
  getMemoryVersions,
  createMemory,
  changeMemoryLifecycle,
  deleteMemory,
  getReviewsByTarget,
  createReview,
  decideReview,
  listMembers,
  listUnresolvedConflicts,
  reportConflict,
  resolveConflict,
  listPendingProposals,
  type MemorySummary,
  type MemoryDetail,
  type MemoryVersion,
  type MemberSummary,
  type ReviewCaseSummary,
  type ConflictCaseSummary,
} from "../../api/client";
import { useToast } from "../../components/ui/use-toast";

const MEMORY_REVIEW_TARGETS = ["memory_candidate", "memory_modification", "memory_promotion"];

function defaultReviewTargetKind(lifecycleState: string): string {
  if (lifecycleState === "candidate") return "memory_candidate";
  if (lifecycleState === "active") return "memory_modification";
  return "memory_modification";
}

function reviewTargetLabel(kind: string): string {
  switch (kind) {
    case "memory_candidate": return "Candidate";
    case "memory_modification": return "Modification";
    case "memory_promotion": return "Promotion";
    default: return kind;
  }
}

function verdictVariant(verdict: string | null): "success" | "warning" | "secondary" | "danger" {
  switch (verdict) {
    case "approve":
    case "merge":
      return "success";
    case "reject":
      return "danger";
    case "revise":
      return "warning";
    default:
      return "secondary";
  }
}

function lifecycleAfterVerdict(targetKind: string, verdict: "approve" | "reject" | "revise"): string | null {
  if (targetKind === "memory_candidate") {
    if (verdict === "approve") return "active";
    if (verdict === "reject") return "deprecated";
    return "needs_verify";
  }
  if (targetKind === "memory_modification") {
    if (verdict === "approve") return "active";
    if (verdict === "revise") return "needs_verify";
  }
  return null;
}

function formatDiff(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "string") return value || "-";
  return JSON.stringify(value, null, 2);
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

function lifecycleVariant(state: string): "success" | "warning" | "secondary" | "danger" {
  switch (state) {
    case "active": return "success";
    case "candidate":
    case "needs_verify":
    case "stale":
      return "warning";
    case "quarantined":
    case "deprecated": return "danger";
    default: return "secondary";
  }
}

export function MemoryPage({ selectedId }: { selectedId: string | null }) {
  const [memories, setMemories] = useState<MemorySummary[]>([]);
  const [detail, setDetail] = useState<MemoryDetail | null>(null);
  const [versions, setVersions] = useState<MemoryVersion[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [versionsError, setVersionsError] = useState<string | null>(null);
  const [members, setMembers] = useState<MemberSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filterLifecycle, setFilterLifecycle] = useState("");
  const [reviews, setReviews] = useState<ReviewCaseSummary[]>([]);
  const [conflicts, setConflicts] = useState<ConflictCaseSummary[]>([]);
  const [pendingProposals, setPendingProposals] = useState<MemorySummary[]>([]);
  const [governanceLoading, setGovernanceLoading] = useState(false);
  const [governanceError, setGovernanceError] = useState<string | null>(null);
  const [decisionReason, setDecisionReason] = useState("");
  const [decisionCorrection, setDecisionCorrection] = useState("");
  const [reviewerInput, setReviewerInput] = useState("");
  const [reviewTargetKind, setReviewTargetKind] = useState("memory_candidate");
  const [showReportConflict, setShowReportConflict] = useState(false);
  const [reportPeerMemory, setReportPeerMemory] = useState("");
  const [reportConflictKind, setReportConflictKind] = useState("semantic");
  const [reportDetectedBy, setReportDetectedBy] = useState("manual");

  const [formTier, setFormTier] = useState("facts");
  const [formTitle, setFormTitle] = useState("");
  const [formStatement, setFormStatement] = useState("");
  const [formScopeKind, setFormScopeKind] = useState("global");
  const [formScopeId, setFormScopeId] = useState("");
  const [formSourceKind, setFormSourceKind] = useState("manual_input");

  const columns: Column<MemorySummary>[] = [
    { key: "title", label: "Name" },
    { key: "tier", label: "Tier" },
    { key: "lifecycle_state", label: "Lifecycle", render: (r) => <Badge variant={lifecycleVariant(r.lifecycle_state)}>{r.lifecycle_state}</Badge> },
    { key: "confidence_value", label: "Confidence", render: (r) => r.confidence_value?.toFixed(2) ?? "-" },
    { key: "scope_kind", label: "Scope" },
    { key: "created_at", label: "Created", render: (r) => formatDate(r.created_at) },
  ];

  const filteredMemories = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return memories.filter((memory) => {
      const matchesSearch = !needle
        || memory.title.toLowerCase().includes(needle)
        || memory.id.toLowerCase().includes(needle);
      const matchesLifecycle = !filterLifecycle || memory.lifecycle_state === filterLifecycle;
      return matchesSearch && matchesLifecycle;
    });
  }, [filterLifecycle, memories, search]);

  const activeCount = memories.filter((m) => m.lifecycle_state === "active").length;
  const candidateCount = memories.filter((m) => m.lifecycle_state === "candidate").length;
  const deprecatedCount = memories.filter((m) => m.lifecycle_state === "deprecated").length;

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setMemories(await listMemories({ limit: 100 }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load memories");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDetail = useCallback(async (id: string) => {
    setDetail(null);
    setDetailError(null);
    try {
      setDetail(await getMemoryDetail(id));
    } catch (err) {
      setDetail(null);
      setDetailError(err instanceof Error ? err.message : "Failed to load memory detail");
    }
  }, []);

  const loadVersions = useCallback(async (id: string) => {
    setVersions([]);
    setVersionsLoading(true);
    setVersionsError(null);
    try {
      setVersions(await getMemoryVersions(id));
    } catch (err) {
      setVersionsError(err instanceof Error ? err.message : "Failed to load memory versions");
    } finally {
      setVersionsLoading(false);
    }
  }, []);

  const loadMembers = useCallback(async () => {
    try {
      const results = await listMembers({ limit: 100 });
      setMembers(results);
      setReviewerInput((current) => current || results[0]?.display_name || "");
    } catch (err) {
      setGovernanceError(err instanceof Error ? err.message : "Failed to load reviewers");
    }
  }, []);

  const loadGovernance = useCallback(async (id: string) => {
    setGovernanceLoading(true);
    setGovernanceError(null);
    try {
      const [reviewGroups, openConflicts, proposals] = await Promise.all([
        Promise.all(MEMORY_REVIEW_TARGETS.map((target) => getReviewsByTarget(target, id))),
        listUnresolvedConflicts(),
        listPendingProposals(0, 200),
      ]);
      const reviewById = new Map<string, ReviewCaseSummary>();
      reviewGroups.flat().forEach((review) => reviewById.set(review.id, review));
      setReviews(Array.from(reviewById.values()));
      setConflicts(openConflicts.filter((conflict) => (
        conflict.memory_a_id === id || conflict.memory_b_id === id
      )));
      setPendingProposals(proposals.filter((proposal) => proposal.id === id));
    } catch (err) {
      setReviews([]);
      setConflicts([]);
      setPendingProposals([]);
      setGovernanceError(err instanceof Error ? err.message : "Failed to load memory review data");
    } finally {
      setGovernanceLoading(false);
    }
  }, []);

  useEffect(() => { loadList(); }, [loadList]);
  useEffect(() => { loadMembers(); }, [loadMembers]);
  useEffect(() => {
    if (selectedId) {
      loadDetail(selectedId);
      loadVersions(selectedId);
      loadGovernance(selectedId);
    } else {
      setDetail(null);
      setDetailError(null);
      setVersions([]);
      setVersionsLoading(false);
      setVersionsError(null);
      setReviews([]);
      setConflicts([]);
      setPendingProposals([]);
      setGovernanceError(null);
    }
  }, [selectedId, loadDetail, loadVersions, loadGovernance]);

  useEffect(() => {
    if (!detail) return;
    setReviewTargetKind(defaultReviewTargetKind(detail.lifecycle_state));
    setDecisionReason("");
    setDecisionCorrection("");
  }, [detail?.id, detail?.lifecycle_state]);

  function handleSelect(row: MemorySummary) {
    navigateTo("memories", row.id);
  }

  async function handleCreate() {
    if (!formTitle.trim() || !formStatement.trim()) return;
    try {
      const created = await createMemory({
        tier: formTier,
        title: formTitle.trim(),
        statement: formStatement.trim(),
        scope_kind: formScopeKind,
        scope_id: formScopeId.trim() || "global",
        source_kind: formSourceKind,
      });
      setShowCreate(false);
      setFormTitle("");
      setFormStatement("");
      await loadList();
      navigateTo("memories", created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    }
  }

  const { toast } = useToast();

  const memoryOptions = useMemo(() => (
    memories
      .filter((memory) => memory.id !== detail?.id)
      .map((memory) => ({
        value: memory.title,
        label: `${memory.title} (${memory.lifecycle_state})`,
      }))
  ), [detail?.id, memories]);

  const memoryTitleById = useMemo(() => {
    const index = new Map<string, string>();
    memories.forEach((memory) => index.set(memory.id, memory.title));
    return index;
  }, [memories]);

  const memberOptions = useMemo(() => (
    members.map((member) => ({
      value: member.display_name,
      label: `${member.display_name} (${member.kind})`,
    }))
  ), [members]);

  const memberNameById = useMemo(() => {
    const index = new Map<string, string>();
    members.forEach((member) => index.set(member.id, member.display_name));
    return index;
  }, [members]);

  const pendingReviews = reviews.filter((review) => !review.verdict);
  const decidedReviews = reviews.filter((review) => review.verdict);
  const isPendingProposal = detail
    ? detail.lifecycle_state === "candidate" || pendingProposals.some((proposal) => proposal.id === detail.id)
    : false;

  function resolveReviewer(): MemberSummary | null {
    const needle = reviewerInput.trim();
    if (!needle) return members[0] ?? null;
    return members.find((member) => (
      member.id === needle || member.display_name === needle
    )) ?? null;
  }

  async function handleDelete() {
    if (!detail) return;
    if (!confirm(`Delete memory "${detail.title}"? This cannot be undone.`)) return;
    try {
      await deleteMemory(detail.id);
      setDetail(null);
      navigateTo("memories");
      toast({ title: "Memory deleted" });
      await loadList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  async function handleLifecycle(newState: string, reason = "Changed via dashboard") {
    if (!detail) return;
    try {
      await changeMemoryLifecycle(detail.id, newState, reason);
      await Promise.all([
        loadList(),
        loadDetail(detail.id),
        loadVersions(detail.id),
        loadGovernance(detail.id),
      ]);
      toast({ title: "Memory lifecycle updated" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lifecycle change failed");
    }
  }

  async function settleReviewedMemory(targetKind: string, verdict: "approve" | "reject" | "revise", reason: string) {
    if (!detail) return;
    const nextLifecycle = lifecycleAfterVerdict(targetKind, verdict);
    if (!nextLifecycle) return;
    await changeMemoryLifecycle(detail.id, nextLifecycle, reason);
  }

  async function handleDecideReview(review: ReviewCaseSummary, verdict: "approve" | "reject" | "revise") {
    if (!detail) return;
    const reason = decisionReason.trim() || `${verdict} via memory review`;
    const correction = decisionCorrection.trim() || undefined;
    try {
      await decideReview(review.id, {
        verdict,
        reason,
        correction,
      });
      await settleReviewedMemory(review.target_kind, verdict, reason);
      setDecisionReason("");
      setDecisionCorrection("");
      await Promise.all([
        loadList(),
        loadDetail(detail.id),
        loadVersions(detail.id),
        loadGovernance(detail.id),
      ]);
      toast({ title: "Review settled" });
    } catch (err) {
      setGovernanceError(err instanceof Error ? err.message : "Review decision failed");
    }
  }

  async function handleCreateAndDecideReview(verdict: "approve" | "reject" | "revise") {
    if (!detail) return;
    const reviewer = resolveReviewer();
    if (!reviewer) {
      setGovernanceError("Reviewer not found");
      return;
    }
    const reason = decisionReason.trim() || `${verdict} via memory review`;
    const correction = decisionCorrection.trim() || undefined;
    try {
      setGovernanceError(null);
      const created = await createReview({
        target_kind: reviewTargetKind,
        target_id: detail.id,
        reviewer_member_id: reviewer.id,
      });
      await decideReview(created.id, {
        verdict,
        reason,
        correction,
      });
      await settleReviewedMemory(reviewTargetKind, verdict, reason);
      setDecisionReason("");
      setDecisionCorrection("");
      await Promise.all([
        loadList(),
        loadDetail(detail.id),
        loadVersions(detail.id),
        loadGovernance(detail.id),
      ]);
      toast({ title: "Review settled" });
    } catch (err) {
      setGovernanceError(err instanceof Error ? err.message : "Review settlement failed");
    }
  }

  async function handleReportConflict() {
    if (!detail || !reportPeerMemory.trim()) return;
    const peer = memories.find((memory) => memory.title === reportPeerMemory || memory.id === reportPeerMemory);
    if (!peer) {
      setGovernanceError("Memory not found");
      return;
    }
    try {
      await reportConflict({
        memory_a_id: detail.id,
        memory_b_id: peer.id,
        conflict_kind: reportConflictKind,
        detected_by: reportDetectedBy,
      });
      setShowReportConflict(false);
      setReportPeerMemory("");
      await Promise.all([
        loadList(),
        loadGovernance(detail.id),
      ]);
      toast({ title: "Conflict reported" });
    } catch (err) {
      setGovernanceError(err instanceof Error ? err.message : "Report conflict failed");
    }
  }

  async function handleResolveConflict(conflict: ConflictCaseSummary, resolution: "keep_a" | "keep_b" | "deprecate_both") {
    if (!detail) return;
    const winnerId = resolution === "keep_a"
      ? conflict.memory_a_id
      : resolution === "keep_b"
        ? conflict.memory_b_id
        : undefined;
    const loserId = winnerId === conflict.memory_a_id
      ? conflict.memory_b_id
      : winnerId === conflict.memory_b_id
        ? conflict.memory_a_id
        : undefined;
    try {
      await resolveConflict(conflict.id, {
        resolution,
        winner_id: winnerId,
      });
      if (resolution === "deprecate_both") {
        await Promise.all([
          changeMemoryLifecycle(conflict.memory_a_id, "deprecated", "Conflict resolved via dashboard"),
          changeMemoryLifecycle(conflict.memory_b_id, "deprecated", "Conflict resolved via dashboard"),
        ]);
      } else if (loserId) {
        await changeMemoryLifecycle(loserId, "deprecated", "Conflict resolved via dashboard");
      }
      await Promise.all([
        loadList(),
        loadDetail(detail.id),
        loadGovernance(detail.id),
      ]);
      toast({ title: "Conflict resolved" });
    } catch (err) {
      setGovernanceError(err instanceof Error ? err.message : "Resolve conflict failed");
    }
  }

  return (
    <div className="space-y-6">
      <Panel title="Memories">
        <div className="mb-4 flex flex-wrap items-center gap-4">
          <Status label="Active" value={activeCount} tone={activeCount > 0 ? "ok" : undefined} />
          <Status label="Candidates" value={candidateCount} tone={candidateCount > 0 ? "warn" : undefined} />
          <Status label="Deprecated" value={deprecatedCount} />
          <Status label="Visible" value={filteredMemories.length} />
        </div>

        <div className="mb-4 grid gap-3 lg:grid-cols-[minmax(16rem,1fr)_12rem_auto]">
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search memories" />
          <Select value={filterLifecycle} onChange={(e) => setFilterLifecycle(e.target.value)}>
            <option value="">All Lifecycles</option>
            <option value="candidate">Candidate</option>
            <option value="active">Active</option>
            <option value="stale">Stale</option>
            <option value="needs_verify">Needs Verify</option>
            <option value="deprecated">Deprecated</option>
            <option value="archived">Archived</option>
            <option value="quarantined">Quarantined</option>
          </Select>
          <Button variant="recommended" onClick={() => setShowCreate(!showCreate)}>
            {showCreate ? "Cancel" : <><Plus className="h-4 w-4" />Create Memory</>}
          </Button>
        </div>

        {error && <ErrorState message={error} />}

        {showCreate && (
          <div className="mb-4 grid gap-4 rounded-md border p-4 lg:grid-cols-2">
            <FormField label="Tier">
              <Select value={formTier} onChange={(e) => setFormTier(e.target.value)}>
                <option value="facts">Facts</option>
                <option value="patterns">Patterns</option>
                <option value="principles">Principles</option>
              </Select>
            </FormField>
            <FormField label="Scope Kind">
              <Select value={formScopeKind} onChange={(e) => setFormScopeKind(e.target.value)}>
                <option value="project">Project</option>
                <option value="tech_stack">Tech Stack</option>
                <option value="department">Department</option>
                <option value="global">Global</option>
              </Select>
            </FormField>
            <FormField label="Source Kind">
              <Select value={formSourceKind} onChange={(e) => setFormSourceKind(e.target.value)}>
                <option value="manual_input">Manual Input</option>
                <option value="task_execution">Task Execution</option>
                <option value="review">Review</option>
                <option value="bulk_import">Bulk Import</option>
              </Select>
            </FormField>
            <FormField label="Scope ID">
              <Input value={formScopeId} onChange={(e) => setFormScopeId(e.target.value)} placeholder="global" />
            </FormField>
            <FormField label="Memory Name" wide>
              <Input value={formTitle} onChange={(e) => setFormTitle(e.target.value)} placeholder="Unique memory name" />
            </FormField>
            <FormField label="Statement" wide>
              <Textarea value={formStatement} onChange={(e) => setFormStatement(e.target.value)} placeholder="Memory statement..." />
            </FormField>
            <div className="col-span-full flex items-center gap-2">
              <Button variant="recommended" disabled={!formTitle.trim() || !formStatement.trim()} onClick={handleCreate}>
                <Plus className="h-4 w-4" />Create
              </Button>
            </div>
          </div>
        )}

        {loading ? (
          <LoadingState />
        ) : (
          <DataTable data={filteredMemories} columns={columns} selectedId={selectedId ?? undefined} onSelect={handleSelect} />
        )}
      </Panel>

      <Dialog open={Boolean(selectedId)} onOpenChange={(open) => { if (!open) navigateTo("memories"); }}>
        <DialogContent className="block max-h-[calc(100vh-2rem)] w-[calc(100vw-2rem)] max-w-5xl overflow-hidden p-0">
          {detailError && (
            <div className="space-y-4 p-6">
              <DialogHeader>
                <DialogTitle>Memory Details</DialogTitle>
                <DialogDescription>Memory detail could not be loaded.</DialogDescription>
              </DialogHeader>
              <ErrorState message={detailError} />
            </div>
          )}
          {!detail && !detailError && (
            <div className="space-y-4 p-6">
              <DialogHeader>
                <DialogTitle>Memory Details</DialogTitle>
                <DialogDescription>Loading memory detail.</DialogDescription>
              </DialogHeader>
              <LoadingState />
            </div>
          )}
          {detail && (
            <div className="flex max-h-[calc(100vh-2rem)] flex-col">
              <div className="border-b px-6 py-5">
                <DialogHeader>
                  <DialogTitle className="flex flex-wrap items-center gap-3 text-xl">
                    <Brain className="h-5 w-5 text-muted-foreground" />
                    <span>{detail.title}</span>
                    <Badge variant={lifecycleVariant(detail.lifecycle_state)}>{detail.lifecycle_state}</Badge>
                  </DialogTitle>
                  <DialogDescription>{detail.tier} memory</DialogDescription>
                </DialogHeader>
              </div>
              <div className="overflow-y-auto px-6 py-5">
                <Tabs defaultValue="overview" className="space-y-5">
                  <TabsList className="flex h-auto flex-wrap justify-start">
                    <TabsTrigger value="overview">Overview</TabsTrigger>
                    <TabsTrigger value="statement">Statement</TabsTrigger>
                    <TabsTrigger value="review">Review</TabsTrigger>
                    <TabsTrigger value="versions">Versions</TabsTrigger>
                    <TabsTrigger value="actions">Actions</TabsTrigger>
                  </TabsList>
                  <TabsContent value="overview">
                    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                      <Definition label="Name" value={detail.title} />
                      <Definition label="Tier" value={detail.tier} />
                      <Definition label="Lifecycle" value={<Badge variant={lifecycleVariant(detail.lifecycle_state)}>{detail.lifecycle_state}</Badge>} />
                      <Definition label="Confidence" value={detail.confidence_value?.toFixed(2)} />
                      <Definition label="Versions" value={detail.versions} />
                      <Definition label="Created" value={formatDate(detail.created_at)} />
                    </div>
                  </TabsContent>
                  <TabsContent value="statement">
                    <pre className="whitespace-pre-wrap rounded-md bg-muted p-4 font-mono text-sm">{detail.statement}</pre>
                  </TabsContent>
                  <TabsContent value="review" className="space-y-5">
                    <div className="flex flex-wrap items-center gap-4">
                      <Status label="Pending Reviews" value={pendingReviews.length} tone={pendingReviews.length > 0 ? "warn" : "ok"} />
                      <Status label="Decided" value={decidedReviews.length} />
                      <Status label="Conflicts" value={conflicts.length} tone={conflicts.length > 0 ? "warn" : "ok"} />
                      <Status label="Proposal" value={isPendingProposal ? "pending" : "settled"} tone={isPendingProposal ? "warn" : "ok"} />
                    </div>

                    {governanceError && <ErrorState message={governanceError} />}
                    {governanceLoading ? (
                      <LoadingState />
                    ) : (
                      <>
                        <section className="rounded-md border p-4">
                          <div className="space-y-4">
                            <div className="flex flex-wrap items-center justify-between gap-3">
                              <div className="flex items-center gap-2 text-sm font-semibold">
                                <ShieldCheck className="h-4 w-4 text-muted-foreground" />
                                Review Settlement
                              </div>
                              <Badge variant={isPendingProposal ? "warning" : "secondary"}>
                                {isPendingProposal ? "proposal" : detail.lifecycle_state}
                              </Badge>
                            </div>
                            <div className="grid gap-3 md:grid-cols-[12rem_minmax(14rem,1fr)]">
                              <FormField label="Target Kind">
                                <Select value={reviewTargetKind} onChange={(e) => setReviewTargetKind(e.target.value)}>
                                  <option value="memory_candidate">Memory Candidate</option>
                                  <option value="memory_modification">Memory Modification</option>
                                  <option value="memory_promotion">Memory Promotion</option>
                                </Select>
                              </FormField>
                              <FormField label="Reviewer">
                                <ComboInput
                                  value={reviewerInput}
                                  onChange={setReviewerInput}
                                  options={memberOptions}
                                  placeholder="Select member or type name"
                                />
                              </FormField>
                              <FormField label="Reason" wide>
                                <Textarea
                                  value={decisionReason}
                                  onChange={(e) => setDecisionReason(e.target.value)}
                                  placeholder="Decision reason"
                                />
                              </FormField>
                              <FormField label="Correction" wide>
                                <Textarea
                                  value={decisionCorrection}
                                  onChange={(e) => setDecisionCorrection(e.target.value)}
                                  placeholder="Suggested correction"
                                />
                              </FormField>
                            </div>
                            <div className="flex flex-wrap gap-2">
                              <Button
                                variant="recommended"
                                disabled={governanceLoading || members.length === 0}
                                onClick={() => handleCreateAndDecideReview("approve")}
                              >
                                <CheckCircle2 className="h-4 w-4" />Approve
                              </Button>
                              <Button
                                variant="outline"
                                disabled={governanceLoading || members.length === 0}
                                onClick={() => handleCreateAndDecideReview("revise")}
                              >
                                Revise
                              </Button>
                              <Button
                                variant="outline"
                                className="border-destructive text-destructive"
                                disabled={governanceLoading || members.length === 0}
                                onClick={() => handleCreateAndDecideReview("reject")}
                              >
                                <XCircle className="h-4 w-4" />Reject
                              </Button>
                            </div>
                          </div>
                        </section>

                        <section className="space-y-3">
                          <div className="flex items-center justify-between gap-3">
                            <h3 className="text-sm font-semibold">Review Cases</h3>
                            <Badge variant={pendingReviews.length > 0 ? "warning" : "secondary"}>{reviews.length}</Badge>
                          </div>
                          {reviews.length === 0 ? (
                            <div className="rounded-md border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
                              No review cases for this memory.
                            </div>
                          ) : (
                            <div className="space-y-3">
                              {reviews.map((review) => (
                                <div key={review.id} className="rounded-md border p-4">
                                  <div className="flex flex-wrap items-start justify-between gap-3">
                                    <div className="space-y-2">
                                      <div className="flex flex-wrap items-center gap-2">
                                        <Badge variant="outline">{reviewTargetLabel(review.target_kind)}</Badge>
                                        <Badge variant={verdictVariant(review.verdict)}>
                                          {review.verdict ?? "pending"}
                                        </Badge>
                                      </div>
                                      <div className="grid gap-2 text-sm text-muted-foreground sm:grid-cols-2">
                                        <span>Reviewer: {memberNameById.get(review.reviewer_member_id) ?? review.reviewer_member_id}</span>
                                        <span>Created: {formatDate(review.created_at)}</span>
                                      </div>
                                      {review.reason && (
                                        <p className="text-sm">{review.reason}</p>
                                      )}
                                      {review.correction && (
                                        <p className="text-sm text-muted-foreground">{review.correction}</p>
                                      )}
                                    </div>
                                  </div>
                                  {!review.verdict && (
                                    <div className="mt-4 grid gap-3">
                                      <FormField label="Reason">
                                        <Textarea
                                          value={decisionReason}
                                          onChange={(e) => setDecisionReason(e.target.value)}
                                          placeholder="Decision reason"
                                        />
                                      </FormField>
                                      <FormField label="Correction">
                                        <Textarea
                                          value={decisionCorrection}
                                          onChange={(e) => setDecisionCorrection(e.target.value)}
                                          placeholder="Suggested correction"
                                        />
                                      </FormField>
                                      <div className="flex flex-wrap gap-2">
                                        <Button
                                          variant="recommended"
                                          disabled={governanceLoading}
                                          onClick={() => handleDecideReview(review, "approve")}
                                        >
                                          <CheckCircle2 className="h-4 w-4" />Approve
                                        </Button>
                                        <Button
                                          variant="outline"
                                          disabled={governanceLoading}
                                          onClick={() => handleDecideReview(review, "revise")}
                                        >
                                          Revise
                                        </Button>
                                        <Button
                                          variant="outline"
                                          className="border-destructive text-destructive"
                                          disabled={governanceLoading}
                                          onClick={() => handleDecideReview(review, "reject")}
                                        >
                                          <XCircle className="h-4 w-4" />Reject
                                        </Button>
                                      </div>
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </section>

                        <section className="space-y-3">
                          <div className="flex flex-wrap items-center justify-between gap-3">
                            <div className="flex items-center gap-2">
                              <GitCompareArrows className="h-4 w-4 text-muted-foreground" />
                              <h3 className="text-sm font-semibold">Conflicts</h3>
                              <Badge variant={conflicts.length > 0 ? "warning" : "secondary"}>{conflicts.length}</Badge>
                            </div>
                            <Button variant="outline" onClick={() => setShowReportConflict((open) => !open)}>
                              {showReportConflict ? "Cancel" : "Report Conflict"}
                            </Button>
                          </div>

                          {showReportConflict && (
                            <div className="grid gap-3 rounded-md border p-4 md:grid-cols-[minmax(14rem,1fr)_10rem_12rem_auto]">
                              <FormField label="Peer Memory">
                                <ComboInput
                                  value={reportPeerMemory}
                                  onChange={setReportPeerMemory}
                                  options={memoryOptions}
                                  placeholder="Select memory or type name"
                                />
                              </FormField>
                              <FormField label="Kind">
                                <Select value={reportConflictKind} onChange={(e) => setReportConflictKind(e.target.value)}>
                                  <option value="semantic">Semantic</option>
                                  <option value="scope">Scope</option>
                                  <option value="temporal">Temporal</option>
                                </Select>
                              </FormField>
                              <FormField label="Detected By">
                                <Select value={reportDetectedBy} onChange={(e) => setReportDetectedBy(e.target.value)}>
                                  <option value="manual">Manual</option>
                                  <option value="auto_admission">Auto Admission</option>
                                  <option value="periodic_scan">Periodic Scan</option>
                                  <option value="recall_collision">Recall Collision</option>
                                </Select>
                              </FormField>
                              <div className="flex items-end">
                                <Button
                                  variant="recommended"
                                  disabled={!reportPeerMemory.trim()}
                                  onClick={handleReportConflict}
                                >
                                  Report
                                </Button>
                              </div>
                            </div>
                          )}

                          {conflicts.length === 0 ? (
                            <div className="rounded-md border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
                              No unresolved conflicts for this memory.
                            </div>
                          ) : (
                            <div className="space-y-3">
                              {conflicts.map((conflict) => {
                                const otherId = conflict.memory_a_id === detail.id ? conflict.memory_b_id : conflict.memory_a_id;
                                const keepThis = conflict.memory_a_id === detail.id ? "keep_a" : "keep_b";
                                const keepOther = conflict.memory_a_id === detail.id ? "keep_b" : "keep_a";
                                return (
                                  <div key={conflict.id} className="rounded-md border p-4">
                                    <div className="flex flex-wrap items-start justify-between gap-3">
                                      <div className="space-y-2">
                                        <div className="flex flex-wrap items-center gap-2">
                                          <Badge variant="warning">{conflict.conflict_kind}</Badge>
                                          <Badge variant="secondary">{conflict.detected_by}</Badge>
                                        </div>
                                        <div className="grid gap-2 text-sm text-muted-foreground sm:grid-cols-2">
                                          <span>This: {detail.title}</span>
                                          <span>Other: {memoryTitleById.get(otherId) ?? otherId}</span>
                                        </div>
                                      </div>
                                      <div className="flex flex-wrap gap-2">
                                        <Button
                                          variant="recommended"
                                          disabled={governanceLoading}
                                          onClick={() => handleResolveConflict(conflict, keepThis)}
                                        >
                                          Keep This
                                        </Button>
                                        <Button
                                          variant="outline"
                                          disabled={governanceLoading}
                                          onClick={() => handleResolveConflict(conflict, keepOther)}
                                        >
                                          Keep Other
                                        </Button>
                                        <Button
                                          variant="outline"
                                          className="border-destructive text-destructive"
                                          disabled={governanceLoading}
                                          onClick={() => handleResolveConflict(conflict, "deprecate_both")}
                                        >
                                          Deprecate Both
                                        </Button>
                                      </div>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </section>
                      </>
                    )}
                  </TabsContent>
                  <TabsContent value="versions">
                    {versionsError && <ErrorState message={versionsError} />}
                    {versionsLoading ? (
                      <LoadingState />
                    ) : versions.length === 0 ? (
                      <div className="rounded-md border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
                        No versions.
                      </div>
                    ) : (
                      <div className="space-y-3">
                        {versions.map((version) => (
                          <div key={version.version_no} className="rounded-md border p-4">
                            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                              <div className="flex items-center gap-2">
                                <Badge variant="secondary">v{version.version_no}</Badge>
                                <span className="text-sm text-muted-foreground">{formatDate(version.created_at)}</span>
                              </div>
                              <span className="text-sm text-muted-foreground">
                                {memberNameById.get(version.author_member_id ?? "") ?? version.author_member_id ?? "-"}
                              </span>
                            </div>
                            {version.reason && (
                              <p className="mb-3 text-sm">{version.reason}</p>
                            )}
                            <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded-md bg-muted p-3 font-mono text-xs">
                              {formatDiff(version.diff)}
                            </pre>
                          </div>
                        ))}
                      </div>
                    )}
                  </TabsContent>
                  <TabsContent value="actions">
                    <div className="flex flex-wrap items-center gap-2">
                      {detail.lifecycle_state === "active" && (
                        <>
                          <Button variant="outline" onClick={() => handleLifecycle("needs_verify")}><FileText className="h-4 w-4" />Needs Verify</Button>
                          <Button variant="outline" onClick={() => handleLifecycle("archived")}><Archive className="h-4 w-4" />Archive</Button>
                          <Button variant="outline" onClick={() => handleLifecycle("deprecated")}>Deprecate</Button>
                        </>
                      )}
                      {detail.lifecycle_state !== "active" && detail.lifecycle_state !== "archived" && detail.lifecycle_state !== "deprecated" && (
                        <Button variant="recommended" onClick={() => handleLifecycle("active")}><FileText className="h-4 w-4" />Activate</Button>
                      )}
                      {(detail.lifecycle_state === "archived" || detail.lifecycle_state === "deprecated") && (
                        <Button variant="recommended" onClick={() => handleLifecycle("active")}><FileText className="h-4 w-4" />Reactivate</Button>
                      )}
                      {detail.lifecycle_state !== "deprecated" && detail.lifecycle_state !== "active" && (
                        <Button variant="outline" onClick={() => handleLifecycle("deprecated")}>Deprecate</Button>
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
