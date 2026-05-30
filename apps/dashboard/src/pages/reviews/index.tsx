/**
 * AITeamOS Dashboard — Review, Proposal & Conflict Management Page (plan.md §3.4)
 *
 * Deliverables:
 * 1. Review list + pending queue
 * 2. Memory proposal review queue
 * 3. Conflict list + resolution workflow
 */

import { useEffect, useState, useCallback } from "react";
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
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import { Textarea } from "../../components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../../components/ui/tabs";
import {
  listPendingReviews,
  createReview,
  decideReview,
  listUnresolvedConflicts,
  reportConflict,
  resolveConflict,
  listPendingProposals,
  listMembers,
  listMemories,
  type ReviewCaseSummary,
  type ConflictCaseSummary,
  type MemorySummary,
  type MemberSummary,
} from "../../api/client";

// ─── Review columns ──────────────────────────────────────────────────────────

const reviewColumns: Column<ReviewCaseSummary>[] = [
  { key: "target_kind", label: "Target Kind" },
  
  { key: "verdict", label: "Verdict", render: (r) => r.verdict ?? "pending" },
  { key: "reason", label: "Reason", render: (r) => r.reason ?? "—" },
  {
    key: "decision_at",
    label: "Decided",
    render: (r) => (r.decision_at ? new Date(r.decision_at).toLocaleDateString() : "—"),
  },
];

// ─── Conflict columns ────────────────────────────────────────────────────────

const conflictColumns: Column<ConflictCaseSummary>[] = [
  { key: "memory_a_id", label: "Memory A" },
  { key: "memory_b_id", label: "Memory B" },
  { key: "conflict_kind", label: "Kind" },
  { key: "detected_by", label: "Detector" },
  {
    key: "resolution",
    label: "Resolution",
    render: (r) => r.resolution ?? "unresolved",
  },
];

// ─── Proposal columns ──────────────────────────────────────────────────────────

const proposalColumns: Column<MemorySummary>[] = [
  { key: "title", label: "Title", render: (r) => r.title.length > 60 ? r.title.slice(0, 60) + "..." : r.title },
  { key: "tier", label: "Tier" },
  { key: "confidence_value", label: "Confidence", render: (r) => r.confidence_value.toFixed(2) },
  { key: "scope_kind", label: "Scope" },
  {
    key: "created_at",
    label: "Created",
    render: (r) => (r.created_at ? new Date(r.created_at).toLocaleDateString() : "—"),
  },
];

// ─── Verdict badge tone helper ───────────────────────────────────────────────

function verdictTone(verdict: string | null): "ok" | "warn" | undefined {
  if (!verdict) return undefined;
  if (verdict === "approve" || verdict === "merge") return "ok";
  if (verdict === "reject") return "warn";
  return undefined;
}

// ─── Review Page ─────────────────────────────────────────────────────────────

export function ReviewPage({ selectedId }: { selectedId: string | null }) {
  const [tab, setTab] = useState<string>("reviews");

  // ── Review state ──
  const [reviews, setReviews] = useState<ReviewCaseSummary[]>([]);
  const [selectedReview, setSelectedReview] = useState<ReviewCaseSummary | null>(null);
  const [reviewLoading, setReviewLoading] = useState(true);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [showCreateReview, setShowCreateReview] = useState(false);
  const [members, setMembers] = useState<MemberSummary[]>([]);
  const [memories, setMemories] = useState<MemorySummary[]>([]);

  // Create review form
  const [formTargetKind, setFormTargetKind] = useState("memory_candidate");
  const [formTargetId, setFormTargetId] = useState("");
  const [formReviewerId, setFormReviewerId] = useState("");

  // Decide review form
  const [decideVerdict, setDecideVerdict] = useState("approve");
  const [decideReason, setDecideReason] = useState("");
  const [decideCorrection, setDecideCorrection] = useState("");

  // ── Conflict state ──
  const [conflicts, setConflicts] = useState<ConflictCaseSummary[]>([]);
  const [selectedConflict, setSelectedConflict] = useState<ConflictCaseSummary | null>(null);
  const [conflictLoading, setConflictLoading] = useState(true);
  const [conflictError, setConflictError] = useState<string | null>(null);
  const [showReportConflict, setShowReportConflict] = useState(false);

  // Report conflict form
  const [formMemA, setFormMemA] = useState("");
  const [formMemB, setFormMemB] = useState("");
  const [formConflictKind, setFormConflictKind] = useState("semantic");
  const [formDetectedBy, setFormDetectedBy] = useState("embedding_similarity");

  // Resolve conflict form
  const [resolveKind, setResolveKind] = useState("keep_a");
  const [resolveWinner, setResolveWinner] = useState("");
  const [resolveBy, setResolveBy] = useState("");

  // ── Proposal state ──
  const [proposals, setProposals] = useState<MemorySummary[]>([]);
  const [selectedProposal, setSelectedProposal] = useState<MemorySummary | null>(null);
  const [proposalLoading, setProposalLoading] = useState(true);
  const [proposalError, setProposalError] = useState<string | null>(null);

  // ── Loaders ──

  const loadReviews = useCallback(async () => {
    setReviewLoading(true);
    setReviewError(null);
    try {
      const [r, m, mem] = await Promise.all([
        listPendingReviews(),
        listMembers({ limit: 100 }),
        listMemories({ limit: 100 }),
      ]);
      setReviews(r);
      setMembers(m);
      setMemories(mem);
    } catch (err) {
      setReviewError(err instanceof Error ? err.message : "Failed to load reviews");
    } finally {
      setReviewLoading(false);
    }
  }, []);

  const loadConflicts = useCallback(async () => {
    setConflictLoading(true);
    setConflictError(null);
    try {
      setConflicts(await listUnresolvedConflicts());
    } catch (err) {
      setConflictError(err instanceof Error ? err.message : "Failed to load conflicts");
    } finally {
      setConflictLoading(false);
    }
  }, []);

  const loadProposals = useCallback(async () => {
    setProposalLoading(true);
    setProposalError(null);
    try {
      setProposals(await listPendingProposals());
    } catch (err) {
      setProposalError(err instanceof Error ? err.message : "Failed to load proposals");
    } finally {
      setProposalLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab === "reviews") loadReviews();
    else if (tab === "conflicts") loadConflicts();
    else loadProposals();
  }, [tab, loadReviews, loadConflicts, loadProposals]);

  useEffect(() => {
    if (selectedId && tab === "reviews") {
      const found = reviews.find((r) => r.id === selectedId);
      if (found) setSelectedReview(found);
    }
  }, [selectedId, tab, reviews]);

  // ── Review handlers ──

  async function handleCreateReview() {
    if (!formTargetId.trim() || !formReviewerId.trim()) return;
    const mem = members.find((m) => m.display_name === formReviewerId || m.id === formReviewerId);
    if (!mem) {
      setReviewError("Reviewer not found");
      return;
    }
    // Look up target: could be memory title or UUID
    const memTarget = memories.find((m) => m.title === formTargetId || m.id === formTargetId);
    const targetId = memTarget ? memTarget.id : formTargetId.trim();
    try {
      const created = await createReview({
        target_kind: formTargetKind,
        target_id: targetId,
        reviewer_member_id: mem.id,
      });
      setShowCreateReview(false);
      setFormTargetId("");
      setFormReviewerId("");
      await loadReviews();
      setSelectedReview(created);
    } catch (err) {
      setReviewError(err instanceof Error ? err.message : "Create review failed");
    }
  }

  async function handleDecideReview() {
    if (!selectedReview) return;
    try {
      const decided = await decideReview(selectedReview.id, {
        verdict: decideVerdict,
        reason: decideReason.trim() || undefined,
        correction: decideCorrection.trim() || undefined,
      });
      setSelectedReview(decided);
      setDecideReason("");
      setDecideCorrection("");
      await loadReviews();
    } catch (err) {
      setReviewError(err instanceof Error ? err.message : "Decide review failed");
    }
  }

  // ── Conflict handlers ──

  async function handleReportConflict() {
    if (!formMemA.trim() || !formMemB.trim()) return;
    const memA = memories.find((m) => m.title === formMemA || m.id === formMemA);
    const memB = memories.find((m) => m.title === formMemB || m.id === formMemB);
    if (!memA || !memB) {
      setConflictError("Memory not found");
      return;
    }
    try {
      const created = await reportConflict({
        memory_a_id: memA.id,
        memory_b_id: memB.id,
        conflict_kind: formConflictKind,
        detected_by: formDetectedBy,
      });
      setShowReportConflict(false);
      setFormMemA("");
      setFormMemB("");
      await loadConflicts();
      setSelectedConflict(created);
    } catch (err) {
      setConflictError(err instanceof Error ? err.message : "Report conflict failed");
    }
  }

  async function handleResolveConflict() {
    if (!selectedConflict || !resolveBy.trim()) return;
    const resolver = members.find((m) => m.display_name === resolveBy || m.id === resolveBy);
    if (!resolver) {
      setConflictError("Resolver not found");
      return;
    }
    const winnerMem = resolveWinner ? memories.find((m) => m.title === resolveWinner || m.id === resolveWinner) : null;
    try {
      const resolved = await resolveConflict(selectedConflict.id, {
        resolution: resolveKind,
        winner_id: winnerMem ? winnerMem.id : (resolveWinner.trim() || undefined),
        resolved_by: resolver.id,
      });
      setSelectedConflict(resolved);
      setResolveWinner("");
      setResolveBy("");
      await loadConflicts();
    } catch (err) {
      setConflictError(err instanceof Error ? err.message : "Resolve conflict failed");
    }
  }

  // ── Stats ──

  const pendingCount = reviews.filter((r) => !r.verdict).length;
  const approvedCount = reviews.filter((r) => r.verdict === "approve").length;
  const conflictCount = conflicts.filter((c) => !c.resolution).length;
  const proposalCount = proposals.length;

  const panelTitle = tab === "reviews" ? "Reviews" : tab === "conflicts" ? "Conflicts" : "Memory Proposals";

  // ── Render ──

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[3fr_2fr]">
      {/* Left: Tab switcher + list */}
      <Panel title={panelTitle}>
        {/* Tabs */}
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="mb-3">
            <TabsTrigger value="reviews">Reviews</TabsTrigger>
            <TabsTrigger value="proposals">Proposals</TabsTrigger>
            <TabsTrigger value="conflicts">Conflicts</TabsTrigger>
          </TabsList>

          {/* Stats */}
          <div className="flex items-center gap-4 mb-3">
            {tab === "reviews" ? (
              <>
                <Status label="Pending" value={pendingCount} tone={pendingCount > 0 ? "warn" : "ok"} />
                <Status label="Approved" value={approvedCount} tone="ok" />
              </>
            ) : tab === "proposals" ? (
              <Status label="Pending Proposals" value={proposalCount} tone={proposalCount > 0 ? "warn" : "ok"} />
            ) : (
              <Status label="Unresolved" value={conflictCount} tone={conflictCount > 0 ? "warn" : "ok"} />
            )}
          </div>

          <TabsContent value="reviews">
            {/* Action buttons */}
            <div className="flex items-center gap-2 mb-3">
              <Button variant="outline" onClick={() => setShowCreateReview(!showCreateReview)}>
                {showCreateReview ? "Cancel" : "Create Review"}
              </Button>
            </div>

            {reviewError && <ErrorState message={reviewError} />}

            {showCreateReview && (
              <div className="space-y-4 mb-4">
                <FormField label="Target Kind">
                  <Select value={formTargetKind} onChange={(e) => setFormTargetKind(e.target.value)}>
                    <option value="memory_candidate">Memory Candidate</option>
                    <option value="task_deliverable">Task Deliverable</option>
                    <option value="memory_promotion">Memory Promotion</option>
                  </Select>
                </FormField>
                <FormField label="Target">
                  <ComboInput
                    value={formTargetId}
                    onChange={setFormTargetId}
                    options={memories.map((m) => ({ value: m.title, label: m.title }))}
                    placeholder="Select memory or type title"
                  />
                </FormField>
                <FormField label="Reviewer">
                  <ComboInput
                    value={formReviewerId}
                    onChange={setFormReviewerId}
                    options={members.map((m) => ({ value: m.display_name, label: m.display_name }))}
                    placeholder="Select member or type name"
                  />
                </FormField>
                <div className="flex items-center gap-2">
                  <Button variant="recommended" disabled={!formTargetId.trim() || !formReviewerId.trim()} onClick={handleCreateReview}>
                    Create
                  </Button>
                </div>
              </div>
            )}

            {reviewLoading ? (
              <LoadingState />
            ) : (
              <DataTable data={reviews} columns={reviewColumns} selectedId={selectedReview?.id} onSelect={(row) => { navigateTo("reviews", row.id); setSelectedReview(row); }} />
            )}
          </TabsContent>

          <TabsContent value="proposals">
            {proposalError && <ErrorState message={proposalError} />}

            {proposalLoading ? (
              <LoadingState />
            ) : proposals.length === 0 ? (
              <p className="text-sm text-muted-foreground">No pending memory proposals</p>
            ) : (
              <DataTable data={proposals} columns={proposalColumns} selectedId={selectedProposal?.id} onSelect={(row) => setSelectedProposal(row)} />
            )}
          </TabsContent>

          <TabsContent value="conflicts">
            {/* Action buttons */}
            <div className="flex items-center gap-2 mb-3">
              <Button variant="outline" onClick={() => setShowReportConflict(!showReportConflict)}>
                {showReportConflict ? "Cancel" : "Report Conflict"}
              </Button>
            </div>

            {conflictError && <ErrorState message={conflictError} />}

            {showReportConflict && (
              <div className="space-y-4 mb-4">
                <FormField label="Memory A">
                  <ComboInput
                    value={formMemA}
                    onChange={setFormMemA}
                    options={memories.map((m) => ({ value: m.title, label: m.title }))}
                    placeholder="Select memory A or type title"
                  />
                </FormField>
                <FormField label="Memory B">
                  <ComboInput
                    value={formMemB}
                    onChange={setFormMemB}
                    options={memories.map((m) => ({ value: m.title, label: m.title }))}
                    placeholder="Select memory B or type title"
                  />
                </FormField>
                <FormField label="Conflict Kind">
                  <Select value={formConflictKind} onChange={(e) => setFormConflictKind(e.target.value)}>
                    <option value="semantic">Semantic</option>
                    <option value="contradiction">Contradiction</option>
                    <option value="scope_overlap">Scope Overlap</option>
                  </Select>
                </FormField>
                <FormField label="Detected By">
                  <Select value={formDetectedBy} onChange={(e) => setFormDetectedBy(e.target.value)}>
                    <option value="embedding_similarity">Embedding Similarity</option>
                    <option value="manual_report">Manual Report</option>
                    <option value="reflection_engine">Reflection Engine</option>
                  </Select>
                </FormField>
                <div className="flex items-center gap-2">
                  <Button variant="recommended" disabled={!formMemA.trim() || !formMemB.trim()} onClick={handleReportConflict}>
                    Report
                  </Button>
                </div>
              </div>
            )}

            {conflictLoading ? (
              <LoadingState />
            ) : (
              <DataTable data={conflicts} columns={conflictColumns} selectedId={selectedConflict?.id} onSelect={(row) => setSelectedConflict(row)} />
            )}
          </TabsContent>
        </Tabs>
      </Panel>

      {/* Right: Detail panel */}
      <Panel title={tab === "reviews" ? "Review Detail" : tab === "proposals" ? "Proposal Detail" : "Conflict Detail"}>
        {tab === "reviews" ? (
          selectedReview ? (
            <div className="space-y-4">
              <Definition label="ID" value={selectedReview.id} />
              <Definition label="Target Kind" value={selectedReview.target_kind} />
              <Definition label="Target ID" value={selectedReview.target_id} />
              <Definition label="Reviewer" value={selectedReview.reviewer_member_id} />
              <Definition
                label="Verdict"
                value={
                  <Status
                    label=""
                    value={selectedReview.verdict ?? "pending"}
                    tone={verdictTone(selectedReview.verdict)}
                  />
                }
              />
              <Definition label="Reason" value={selectedReview.reason} />
              <Definition label="Decided At" value={selectedReview.decision_at} />

              {/* Decide form — only show if not yet decided */}
              {!selectedReview.verdict && (
                <div className="space-y-4 mt-4">
                  <FormField label="Verdict">
                    <Select value={decideVerdict} onChange={(e) => setDecideVerdict(e.target.value)}>
                      <option value="approve">Approve</option>
                      <option value="reject">Reject</option>
                      <option value="merge">Merge</option>
                      <option value="revise">Revise</option>
                    </Select>
                  </FormField>
                  <FormField label="Reason" wide>
                    <Textarea value={decideReason} onChange={(e) => setDecideReason(e.target.value)} placeholder="Decision reason..." />
                  </FormField>
                  {(decideVerdict === "revise" || decideVerdict === "reject") && (
                    <FormField label="Correction" wide>
                      <Textarea value={decideCorrection} onChange={(e) => setDecideCorrection(e.target.value)} placeholder="Suggested correction..." />
                    </FormField>
                  )}
                  <div className="flex items-center gap-2">
                    <Button variant="recommended" onClick={handleDecideReview}>
                      Submit Decision
                    </Button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Select a review to view details</p>
          )
        ) : tab === "proposals" ? (
          selectedProposal ? (
            <div className="space-y-4">
              <Definition label="ID" value={selectedProposal.id} />
              <Definition label="Title" value={selectedProposal.title} />
              <Definition label="Tier" value={selectedProposal.tier} />
              <Definition label="Confidence" value={selectedProposal.confidence_value.toFixed(3)} />
              <Definition label="Scope" value={selectedProposal.scope_kind} />
              <Definition label="Tags" value={selectedProposal.tags.join(", ") || "—"} />
              <Definition label="Created" value={selectedProposal.created_at ?? "—"} />
              <Definition label="Status" value="candidate" />
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Select a proposal to view details</p>
          )
        ) : selectedConflict ? (
          <div className="space-y-4">
            <Definition label="ID" value={selectedConflict.id} />
            <Definition label="Memory A" value={selectedConflict.memory_a_id} />
            <Definition label="Memory B" value={selectedConflict.memory_b_id} />
            <Definition label="Kind" value={selectedConflict.conflict_kind} />
            <Definition label="Detected By" value={selectedConflict.detected_by} />
            <Definition
              label="Resolution"
              value={
                <Status
                  label=""
                  value={selectedConflict.resolution ?? "unresolved"}
                  tone={selectedConflict.resolution ? "ok" : "warn"}
                />
              }
            />
            <Definition label="Winner" value={selectedConflict.winner_id} />
            <Definition label="Resolved By" value={selectedConflict.resolved_by} />

            {/* Resolve form — only show if not yet resolved */}
            {!selectedConflict.resolution && (
              <div className="space-y-4 mt-4">
                <FormField label="Resolution">
                  <Select value={resolveKind} onChange={(e) => setResolveKind(e.target.value)}>
                    <option value="keep_a">Keep A</option>
                    <option value="keep_b">Keep B</option>
                    <option value="merge">Merge</option>
                    <option value="deprecate_both">Deprecate Both</option>
                  </Select>
                </FormField>
                {(resolveKind === "keep_a" || resolveKind === "keep_b") && (
                  <FormField label="Winner Memory ID">
                    <Input value={resolveWinner} onChange={(e) => setResolveWinner(e.target.value)} placeholder="UUID of winning memory" />
                  </FormField>
                )}
                <FormField label="Resolved By">
                  <ComboInput
                    value={resolveBy}
                    onChange={setResolveBy}
                    options={members.map((m) => ({ value: m.display_name, label: m.display_name }))}
                    placeholder="Select member or type name"
                  />
                </FormField>
                <div className="flex items-center gap-2">
                  <Button variant="recommended" disabled={!resolveBy.trim()} onClick={handleResolveConflict}>
                    Resolve
                  </Button>
                </div>
              </div>
            )}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Select a conflict to view details</p>
        )}
      </Panel>
    </div>
  );
}
