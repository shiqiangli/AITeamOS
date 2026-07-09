import { useEffect, useMemo, useState } from "react";
import { Check, Link2 } from "lucide-react";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import {
  projectAssetRecordToGraphiti,
  reviewAssetCandidate,
} from "../../../api/assets";

function metadataText(value: unknown): string {
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  return typeof value === "string" && value.trim() ? value : "-";
}

function firstMetadataValue(values: unknown[]): string {
  for (const value of values) {
    const text = metadataText(value);
    if (text !== "-") return text;
  }
  return "";
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function isApprovedReviewState(value: unknown): boolean {
  return ["accepted", "approved", "validated"].includes(metadataText(value).toLowerCase());
}

function assetCandidateDisplayId(candidate: Record<string, unknown>, fallback: string): string {
  return firstMetadataValue([candidate.id, candidate.asset_candidate_id, candidate.provider_ref]) || fallback;
}

function assetCandidateMemoryId(candidate: Record<string, unknown>): string {
  return firstMetadataValue([candidate.candidate_id, candidate.source_candidate_id, candidate.memory_candidate_id]);
}

function assetCandidateAssetId(candidate: Record<string, unknown>): string {
  return firstMetadataValue([candidate.approved_asset_id, candidate.asset_id]);
}

function candidateSignature(candidates: Record<string, unknown>[]): string {
  return candidates.map((candidate, index) => assetCandidateDisplayId(candidate, `candidate-${index + 1}`)).join("|");
}

export function AssetCandidatesPanel({
  candidates,
  onError,
}: {
  candidates: Record<string, unknown>[];
  onError: (message: string) => void;
}) {
  const [assetActionId, setAssetActionId] = useState("");
  const [assetProjectionStatus, setAssetProjectionStatus] = useState<Record<string, Record<string, string>>>({});
  const [assetCandidateOverrides, setAssetCandidateOverrides] = useState<Record<string, Record<string, unknown>>>({});
  const signature = useMemo(() => candidateSignature(candidates), [candidates]);

  useEffect(() => {
    if (!signature) {
      setAssetActionId("");
      setAssetProjectionStatus({});
      setAssetCandidateOverrides({});
    }
  }, [signature]);

  const displayCandidates = useMemo(() => (
    candidates.map((candidate, index) => {
      const id = assetCandidateDisplayId(candidate, `candidate-${index + 1}`);
      return { ...candidate, ...(assetCandidateOverrides[id] ?? {}) };
    })
  ), [assetCandidateOverrides, candidates]);

  function patchWorkbenchAssetCandidate(candidateId: string, patch: Record<string, unknown>) {
    setAssetCandidateOverrides((current) => ({
      ...current,
      [candidateId]: {
        ...(current[candidateId] ?? {}),
        ...patch,
      },
    }));
  }

  async function approveWorkbenchAssetCandidate(candidate: Record<string, unknown>) {
    const candidateId = assetCandidateDisplayId(candidate, "");
    if (!candidateId) {
      onError("Asset candidate id is required for review.");
      return;
    }
    setAssetActionId(`approve:${candidateId}`);
    onError("");
    try {
      const response = await reviewAssetCandidate(candidateId, {
        status: "approved",
        reviewer_employee_id: "clara",
        reason: "Approved from Chat Workbench after LangGraph approval dogfood.",
      });
      const responseCandidate = response.candidate as unknown as Record<string, unknown>;
      const asset = response.asset ? response.asset as unknown as Record<string, unknown> : {};
      const assetId = firstMetadataValue([asset.id, responseCandidate.asset_id, candidate.asset_id]);
      const sourceCandidateId = firstMetadataValue([
        candidate.candidate_id,
        responseCandidate.source_candidate_id,
        candidate.source_candidate_id,
      ]);
      patchWorkbenchAssetCandidate(candidateId, {
        ...responseCandidate,
        id: firstMetadataValue([responseCandidate.id, candidateId]),
        candidate_id: sourceCandidateId,
        approved_asset_id: assetId,
        status: firstMetadataValue([responseCandidate.status, "approved"]),
        review_state: firstMetadataValue([responseCandidate.review_state, "approved"]),
      });
      setAssetProjectionStatus((current) => ({
        ...current,
        [candidateId]: {
          status: "approved",
          detail: "Asset candidate approved.",
          asset_id: assetId,
          graphiti_episode_id: "",
        },
      }));
    } catch (error) {
      onError(error instanceof Error ? error.message : "Failed to approve Asset candidate");
    } finally {
      setAssetActionId("");
    }
  }

  async function projectWorkbenchAssetCandidate(candidate: Record<string, unknown>) {
    const candidateId = assetCandidateDisplayId(candidate, "");
    const assetId = assetCandidateAssetId(candidate);
    if (!assetId) {
      onError("Approved Asset id is required before Graphiti projection.");
      return;
    }
    setAssetActionId(`project:${candidateId}`);
    onError("");
    try {
      const response = await projectAssetRecordToGraphiti(assetId);
      const ingestedAsset = asRecord(response.ingested_asset);
      const graphitiEpisodeId = firstMetadataValue([
        ingestedAsset.episode_id,
        ingestedAsset.graphiti_episode_id,
        ingestedAsset.uuid,
      ]);
      setAssetProjectionStatus((current) => ({
        ...current,
        [candidateId]: {
          status: response.status,
          detail: response.detail,
          asset_id: response.asset_id,
          graphiti_episode_id: graphitiEpisodeId,
        },
      }));
      patchWorkbenchAssetCandidate(candidateId, {
        projection_status: response.status,
        graphiti_episode_id: graphitiEpisodeId,
      });
    } catch (error) {
      onError(error instanceof Error ? error.message : "Failed to project Asset to Graphiti");
    } finally {
      setAssetActionId("");
    }
  }

  if (displayCandidates.length === 0) return null;

  return (
    <div className="rounded-md border bg-background/60 p-2">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="text-[10px] font-medium uppercase text-muted-foreground">Asset Candidates</span>
        <Badge variant="outline" className="px-1.5 text-[10px]">
          {displayCandidates.length}
        </Badge>
      </div>
      <div className="space-y-1">
        {displayCandidates.slice(0, 4).map((candidate, index) => {
          const candidateId = assetCandidateDisplayId(candidate, `candidate-${index + 1}`);
          const memoryCandidateId = assetCandidateMemoryId(candidate);
          const assetId = assetCandidateAssetId(candidate);
          const reviewState = firstMetadataValue([candidate.review_state, candidate.status]);
          const approved = isApprovedReviewState(reviewState);
          const sourceTicketId = firstMetadataValue([candidate.source_ticket_id, candidate.scope_ref]);
          const sourceReportId = firstMetadataValue([candidate.source_report_id, candidate.report_id]);
          const projection = assetProjectionStatus[candidateId] ?? {};
          const projectionStatus = firstMetadataValue([candidate.projection_status, projection.status]);
          const graphitiEpisodeId = firstMetadataValue([candidate.graphiti_episode_id, projection.graphiti_episode_id]);
          const approving = assetActionId === `approve:${candidateId}`;
          const projecting = assetActionId === `project:${candidateId}`;
          return (
            <div key={`${candidateId}-${index}`} className="min-w-0 rounded border bg-card px-2 py-1.5">
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate text-[11px] font-medium" title={candidateId}>
                    {candidateId}
                  </div>
                  <div className="mt-0.5 truncate text-[10px] text-muted-foreground" title={metadataText(candidate.asset_type || candidate.kind)}>
                    {metadataText(candidate.asset_type || candidate.kind)}
                  </div>
                </div>
                <Badge variant={approved ? "success" : "warning"} className="px-1.5 text-[10px]">
                  {reviewState || "proposed"}
                </Badge>
              </div>
              <div className="mt-1 grid gap-1 text-[10px] text-muted-foreground">
                <div className="flex justify-between gap-2">
                  <span>Memory</span>
                  <span className="truncate text-right" title={memoryCandidateId || "-"}>{memoryCandidateId || "-"}</span>
                </div>
                <div className="flex justify-between gap-2">
                  <span>Asset</span>
                  <span className="truncate text-right" title={assetId || "-"}>{assetId || "-"}</span>
                </div>
                <div className="flex justify-between gap-2">
                  <span>Ticket</span>
                  <span className="truncate text-right" title={sourceTicketId || "-"}>{sourceTicketId || "-"}</span>
                </div>
                <div className="flex justify-between gap-2">
                  <span>Report</span>
                  <span className="truncate text-right" title={sourceReportId || "-"}>{sourceReportId || "-"}</span>
                </div>
                {projectionStatus && (
                  <div className="flex justify-between gap-2">
                    <span>Graphiti</span>
                    <span className="truncate text-right" title={graphitiEpisodeId || projection.detail || projectionStatus}>
                      {projectionStatus}{graphitiEpisodeId ? `:${graphitiEpisodeId}` : ""}
                    </span>
                  </div>
                )}
              </div>
              <div className="mt-1 flex justify-end gap-1">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-6 gap-1 px-2 text-[10px]"
                  disabled={approved || approving || projecting}
                  aria-label={`Approve Asset candidate ${candidateId}`}
                  onClick={() => void approveWorkbenchAssetCandidate(candidate)}
                >
                  <Check className="h-3 w-3" />
                  {approving ? "Approving" : "Approve"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-6 gap-1 px-2 text-[10px]"
                  disabled={!approved || !assetId || approving || projecting || projectionStatus === "ingested"}
                  aria-label={`Project Asset ${assetId || candidateId} to Graphiti`}
                  onClick={() => void projectWorkbenchAssetCandidate(candidate)}
                >
                  <Link2 className="h-3 w-3" />
                  {projecting ? "Projecting" : "Project"}
                </Button>
              </div>
            </div>
          );
        })}
        {displayCandidates.length > 4 && (
          <Badge variant="secondary" className="px-1.5 text-[10px]">
            +{displayCandidates.length - 4} more candidates
          </Badge>
        )}
      </div>
    </div>
  );
}
