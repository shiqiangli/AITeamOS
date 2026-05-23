from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import hashlib
import json
import re

from aiteamos_schema import LearningExtraction, LearningExtractionProposal, MemoryProposal

from .io import read_jsonl, read_text_if_exists, read_yaml, write_text, write_yaml
from .loader import load_workspace
from .mutations import propose_memory
from .run_events import append_run_event_to_ledger


EXTRACTOR_ID = "memory-engine"
LEARNING_EXTRACTOR_ID = "aiteamos.learning-extractor"
LEARNING_EXTRACTOR_VERSION = "v1"
BOOTSTRAP_LEARNING_EXTRACTION_ID = "L-bootstrap-self-history"
BOOTSTRAP_LEARNING_EXTRACTOR_VERSION = "v1-bootstrap"
MAX_CANDIDATES = 6
EXCERPT_CHARS = 1_600
SUCCESSFUL_RUN_STATUSES = {"FINISHED", "SUCCEEDED", "SUCCESS", "DONE"}
FAILED_OR_RECOVERED_RUN_STATUSES = {
    "FAILED",
    "RECOVERED",
    "RECOVERING",
    "STALLED",
    "INTERRUPTED",
    "CHANGES_REQUESTED",
}


@dataclass(frozen=True)
class MemoryCandidate:
    kind: str
    title: str
    content: str
    evidence: list[str]
    confidence: float
    review_guidance: str


def admit_learning_extraction(
    workspace_path: str | Path,
    *,
    run_id: str,
    proposals: list[dict[str, Any] | LearningExtractionProposal],
    extractor_id: str = LEARNING_EXTRACTOR_ID,
    extractor_version: str = LEARNING_EXTRACTOR_VERSION,
    extracted_at: str | None = None,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")
    normalized = [_normalize_learning_proposal(run_id, extractor_id, proposal) for proposal in proposals]
    if not normalized:
        raise ValueError("learning extraction requires at least one proposal")
    _validate_unique_learning_proposal_keys(normalized)
    normalized, warnings = _filter_skill_proposals_by_evidence(index, normalized)
    if not normalized:
        return _empty_learning_extraction_result(warnings)

    existing = _existing_learning_extraction(index, run_id, extractor_id, normalized)
    if existing is not None:
        return _learning_extraction_result(existing, created=False, warnings=warnings)

    run = index.runs[run_id]
    now = datetime.now().astimezone()
    extraction_id = _timestamp_learning_extraction_id(now)
    payload: dict[str, Any] = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "LearningExtraction",
        "metadata": {
            "id": extraction_id,
            "createdAt": now.isoformat(timespec="milliseconds"),
        },
        "spec": {
            "runId": run_id,
            "extractedAt": extracted_at or now.isoformat(timespec="milliseconds"),
            "dedupeKey": _learning_extraction_dedupe_key(run_id, extractor_id, extractor_version, normalized),
            "extractorId": extractor_id,
            "extractorVersion": extractor_version,
            "sourceContext": {
                "project": run.spec.project,
                "taskId": run.spec.task,
                "member": run.spec.member,
                "assignment": run.spec.assignment,
                "runStatus": run.spec.status,
                "sourceJournalPath": f"runs/{run_id}/{run.spec.journal}" if run.spec.journal else None,
                "sourceEventLedger": f"runs/{run_id}/{run.spec.eventLedger}" if run.spec.eventLedger else None,
            },
            "proposals": [proposal.model_dump(mode="json", exclude_none=True) for proposal in normalized],
            "warnings": warnings,
        },
    }
    extraction = LearningExtraction.model_validate(payload)
    write_yaml(
        index.workspace_root / "learning_extractions" / f"{extraction.object_id}.yaml",
        extraction.model_dump(mode="json", exclude_none=True),
    )
    return _learning_extraction_result(extraction, created=True)


def bootstrap_learning_extractions(
    workspace_path: str | Path,
    *,
    baseline_id: str = BOOTSTRAP_LEARNING_EXTRACTION_ID,
    extracted_at: str | None = None,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    source_run_ids = _ordered_run_ids(index)
    if not source_run_ids:
        raise ValueError("bootstrap learning extraction requires at least one run")

    anchor_run_id = source_run_ids[-1]
    raw_proposals = _bootstrap_learning_proposals(index, source_run_ids)
    normalized = [
        _normalize_learning_proposal(anchor_run_id, LEARNING_EXTRACTOR_ID, proposal)
        for proposal in raw_proposals
    ]
    if not normalized:
        raise ValueError("bootstrap learning extraction requires at least one proposal")
    _validate_unique_learning_proposal_keys(normalized)
    admitted, warnings = _filter_skill_proposals_by_evidence(index, normalized)
    if not admitted:
        return _empty_learning_extraction_result(warnings)

    stats = _bootstrap_learning_stats(source_run_ids, normalized, admitted)
    dedupe_key = _bootstrap_learning_dedupe_key(source_run_ids, admitted)
    existing = _existing_bootstrap_learning_extraction(index, dedupe_key, baseline_id)
    if existing is not None:
        return _learning_extraction_result(existing, created=False)

    anchor_run = index.runs[anchor_run_id]
    now = datetime.now().astimezone()
    payload: dict[str, Any] = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "LearningExtraction",
        "metadata": {
            "id": baseline_id,
            "createdAt": now.isoformat(timespec="milliseconds"),
        },
        "spec": {
            "runId": anchor_run_id,
            "extractedAt": extracted_at or now.isoformat(timespec="milliseconds"),
            "dedupeKey": dedupe_key,
            "extractorId": LEARNING_EXTRACTOR_ID,
            "extractorVersion": BOOTSTRAP_LEARNING_EXTRACTOR_VERSION,
            "sourceContext": {
                "project": anchor_run.spec.project,
                "taskId": anchor_run.spec.task,
                "member": anchor_run.spec.member,
                "assignment": anchor_run.spec.assignment,
                "runStatus": anchor_run.spec.status,
                "sourceJournalPath": f"runs/{anchor_run_id}/{anchor_run.spec.journal}" if anchor_run.spec.journal else None,
                "sourceEventLedger": f"runs/{anchor_run_id}/{anchor_run.spec.eventLedger}" if anchor_run.spec.eventLedger else None,
                "sourceRunIds": source_run_ids,
                "sourceRunCount": len(source_run_ids),
            },
            "proposals": [proposal.model_dump(mode="json", exclude_none=True) for proposal in admitted],
            "warnings": warnings,
            "bootstrapStats": stats,
        },
    }
    extraction = LearningExtraction.model_validate(payload)
    write_yaml(
        index.workspace_root / "learning_extractions" / f"{extraction.object_id}.yaml",
        extraction.model_dump(mode="json", exclude_none=True),
    )
    return _learning_extraction_result(extraction, created=True)


def extract_memory_proposals(workspace_path: str | Path, run_id: str) -> list[MemoryProposal]:
    index = load_workspace(workspace_path)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")

    run = index.runs[run_id]
    candidates = _collect_memory_candidates(index, run_id)["candidates"]
    proposals: list[MemoryProposal] = []
    for candidate in candidates[:MAX_CANDIDATES]:
        dedupe_key = _candidate_dedupe_key(run_id, candidate)
        proposal = propose_memory(
            workspace_path,
            project=run.spec.project,
            member=run.spec.member,
            assignment=run.spec.assignment,
            source_run=run_id,
            source_task=run.spec.task,
            source_extractor_id=EXTRACTOR_ID,
            dedupe_key=dedupe_key,
            title=candidate.title,
            content=candidate.content,
            kind=candidate.kind,
            evidence=candidate.evidence,
            confidence=candidate.confidence,
            review_guidance=candidate.review_guidance,
        )
        proposals.append(proposal)

    _append_extractor_event(index.workspace_root, run_id, [proposal.object_id for proposal in proposals])
    return proposals


def preview_memory_extraction(workspace_path: str | Path, run_id: str) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")
    collected = _collect_memory_candidates(index, run_id)
    candidates: list[MemoryCandidate] = collected["candidates"]
    existing_by_key = {
        proposal.spec.dedupeKey: proposal.object_id
        for proposal in index.memory_proposals.values()
        if proposal.spec.sourceRun == run_id and proposal.spec.sourceExtractorId == EXTRACTOR_ID and proposal.spec.dedupeKey
    }
    items: list[dict[str, Any]] = []
    for candidate in candidates[:MAX_CANDIDATES]:
        dedupe_key = _candidate_dedupe_key(run_id, candidate)
        existing = existing_by_key.get(dedupe_key)
        items.append(
            {
                "dedupeKey": dedupe_key,
                "status": "existing" if existing else "new",
                "existingProposal": existing,
                "kind": candidate.kind,
                "title": candidate.title,
                "content": candidate.content,
                "evidence": candidate.evidence,
                "confidence": candidate.confidence,
                "reviewGuidance": candidate.review_guidance,
            }
        )
    return {
        "run": run_id,
        "extractorId": EXTRACTOR_ID,
        "maxCandidates": MAX_CANDIDATES,
        "candidateCount": len(candidates),
        "newCount": len([item for item in items if item["status"] == "new"]),
        "existingCount": len([item for item in items if item["status"] == "existing"]),
        "skippedCount": max(0, len(candidates) - MAX_CANDIDATES),
        "sources": collected["sources"],
        "candidates": items,
    }


def _collect_memory_candidates(index: Any, run_id: str) -> dict[str, Any]:
    run_dir = index.workspace_root / "runs" / run_id
    source_texts = [
        {"path": f"runs/{run_id}/journal.md", "text": index.run_journals.get(run_id, "")},
        {"path": f"runs/{run_id}/model_output.md", "text": read_text_if_exists(run_dir / "model_output.md") or ""},
        {"path": f"runs/{run_id}/worker_output.md", "text": read_text_if_exists(run_dir / "worker_output.md") or ""},
    ]
    explicit_candidates = [
        candidate
        for source in source_texts
        for candidate in _explicit_text_candidates(run_id, source["text"], source["path"])
    ]
    test_log = read_text_if_exists(run_dir / "test.log") or ""
    events = index.run_events.get(run_id, [])
    candidates = _dedupe_candidates(
        explicit_candidates
        + _test_failure_candidates(run_id, test_log)
        + _event_failure_candidates(run_id, events)
    )
    sources = []
    for source in source_texts:
        sources.append(
            {
                "path": source["path"],
                "present": bool(source["text"].strip()),
                "candidateCount": len([candidate for candidate in candidates if source["path"] in candidate.evidence]),
            }
        )
    for path in [f"runs/{run_id}/test.log", f"runs/{run_id}/events.jsonl"]:
        sources.append(
            {
                "path": path,
                "present": (index.workspace_root / path).exists(),
                "candidateCount": len([candidate for candidate in candidates if path in candidate.evidence]),
            }
        )
    return {"candidates": candidates, "sources": sources}


def _explicit_text_candidates(run_id: str, text: str, evidence_path: str) -> list[MemoryCandidate]:
    if not text.strip():
        return []
    candidates: list[MemoryCandidate] = []
    candidates.extend(_heading_blocks(run_id, text, evidence_path))
    for line in text.splitlines():
        match = re.match(r"^\s*(memory proposal|lesson|mistake|decision)\s*:\s*(.+?)\s*$", line, flags=re.IGNORECASE)
        if not match:
            continue
        label = match.group(1).lower()
        content = match.group(2).strip()
        if not _usable_content(content):
            continue
        kind = _kind_from_label(label)
        candidates.append(
            MemoryCandidate(
                kind=kind,
                title=_title_from_content(run_id, kind, content),
                content=content,
                evidence=[evidence_path],
                confidence=_confidence_for_kind(kind),
                review_guidance=_review_guidance(kind),
            )
        )
    return candidates


def _heading_blocks(run_id: str, text: str, evidence_path: str) -> list[MemoryCandidate]:
    pattern = re.compile(
        r"^#{1,4}\s+(memory proposal|lesson|mistake|decision)\b(.*?)(?=^#{1,4}\s+|\Z)",
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    candidates: list[MemoryCandidate] = []
    for match in pattern.finditer(text):
        label = match.group(1).lower()
        block = match.group(2).strip(" :-\n\t")
        if not _usable_content(block):
            continue
        kind = _kind_from_label(label)
        candidates.append(
            MemoryCandidate(
                kind=kind,
                title=_title_from_content(run_id, kind, block),
                content=_excerpt(block),
                evidence=[evidence_path],
                confidence=_confidence_for_kind(kind),
                review_guidance=_review_guidance(kind),
            )
        )
    return candidates


def _test_failure_candidates(run_id: str, test_log: str) -> list[MemoryCandidate]:
    if not test_log.strip() or not re.search(r"\b(error|failed|failure|traceback|exception)\b", test_log, flags=re.IGNORECASE):
        return []
    return [
        MemoryCandidate(
            kind="mistake",
            title=f"Test failure pattern from {run_id}",
            content=(
                "A test log for this run contains failure or error output. Promote only after confirming the root cause "
                "and recovery recipe.\n\n"
                + _excerpt(test_log)
            ),
            evidence=[f"runs/{run_id}/test.log"],
            confidence=0.55,
            review_guidance="Human review required: test-failure memory needs a confirmed cause and fix before approval.",
        )
    ]


def _event_failure_candidates(run_id: str, events: list[dict[str, Any]]) -> list[MemoryCandidate]:
    failed = [
        event
        for event in events
        if "failed" in str(event.get("type", "")).lower() or event.get("error")
    ]
    if not failed:
        return []
    excerpt = json.dumps(failed[-3:], sort_keys=True, ensure_ascii=True, indent=2)
    return [
        MemoryCandidate(
            kind="mistake",
            title=f"Failure events from {run_id}",
            content=(
                "The run event ledger contains failure events. Promote only if the reviewed journal identifies the "
                "cause and recovery.\n\n"
                + _excerpt(excerpt)
            ),
            evidence=[f"runs/{run_id}/events.jsonl"],
            confidence=0.5,
            review_guidance="Human review required: event-only memory is advisory until backed by a journaled fix.",
        )
    ]


def _dedupe_candidates(candidates: list[MemoryCandidate]) -> list[MemoryCandidate]:
    unique_by_key: dict[str, MemoryCandidate] = {}
    for candidate in candidates:
        key = json.dumps(
            {
                "kind": candidate.kind,
                "title": candidate.title,
                "content": candidate.content,
            },
            sort_keys=True,
            ensure_ascii=True,
        )
        previous = unique_by_key.get(key)
        if previous:
            unique_by_key[key] = MemoryCandidate(
                kind=previous.kind,
                title=previous.title,
                content=previous.content,
                evidence=_unique_strings([*previous.evidence, *candidate.evidence]),
                confidence=max(previous.confidence, candidate.confidence),
                review_guidance=previous.review_guidance,
            )
            continue
        unique_by_key[key] = candidate
    return list(unique_by_key.values())


def _candidate_dedupe_key(run_id: str, candidate: MemoryCandidate) -> str:
    raw = json.dumps(
        {
            "run": run_id,
            "extractor": EXTRACTOR_ID,
            "kind": candidate.kind,
            "title": candidate.title,
            "content": candidate.content,
        },
        sort_keys=True,
        ensure_ascii=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _ordered_run_ids(index: Any) -> list[str]:
    return [
        run_id
        for run_id, _run in sorted(
            index.runs.items(),
            key=lambda item: (item[1].metadata.createdAt or "", item[0]),
        )
    ]


def _bootstrap_learning_proposals(index: Any, source_run_ids: list[str]) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    proposals.extend(_bootstrap_memory_learning_proposals(index))
    proposals.extend(_bootstrap_growth_learning_proposals(index, source_run_ids))
    skill = _bootstrap_skill_learning_proposal(index, source_run_ids)
    if skill is not None:
        proposals.append(skill)
    proposals.append(_bootstrap_retrospective_learning_proposal(index, source_run_ids))
    return proposals


def _bootstrap_memory_learning_proposals(index: Any) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    for proposal_id, proposal in sorted(index.memory_proposals.items()):
        source_run = proposal.spec.sourceRun
        evidence = list(proposal.spec.evidence)
        if source_run:
            evidence.append(f"runs/{source_run}/run.yaml")
        proposals.append(
            {
                "kind": "memory",
                "targetKind": "MemoryProposal",
                "targetManifest": proposal.model_dump(mode="json", exclude_none=True),
                "summary": f"Bootstrap memory candidate from existing MemoryProposal {proposal_id}.",
                "confidence": proposal.spec.confidence or 0.72,
                "evidence": _unique_strings(evidence),
                "dedupeKey": f"learning:bootstrap:memory:{proposal_id}",
                "reviewGuidance": proposal.spec.reviewGuidance
                or "Human review should confirm this imported memory proposal remains durable.",
            }
        )
    return proposals


def _bootstrap_growth_learning_proposals(index: Any, source_run_ids: list[str]) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    for run_id in source_run_ids:
        run = index.runs[run_id]
        proposals.append(
            {
                "kind": "growth",
                "targetKind": "GrowthSignal",
                "targetManifest": {
                    "apiVersion": "aiteamos.dev/v1alpha1",
                    "kind": "GrowthSignal",
                    "metadata": {"id": f"GROWTH-DRAFT-bootstrap-{run_id}"},
                    "spec": {
                        "project": run.spec.project,
                        "member": run.spec.member,
                        "assignment": run.spec.assignment,
                        "sourceRun": run_id,
                        "sourceTask": run.spec.task,
                        "runStatus": run.spec.status,
                        "dedupeKey": f"learning:bootstrap:growth:{run_id}",
                        "summary": (
                            f"Self-hosting run {run_id} contributes growth evidence for "
                            f"{run.spec.member} on {run.spec.assignment or 'unassigned work'}."
                        ),
                    },
                },
                "summary": f"Bootstrap growth candidate from self-hosting run {run_id}.",
                "confidence": 0.66 if _run_is_successful(index, run_id) else 0.58,
                "evidence": _run_evidence_paths(run),
                "dedupeKey": f"learning:bootstrap:growth:{run_id}",
            }
        )
    return proposals


def _bootstrap_skill_learning_proposal(index: Any, source_run_ids: list[str]) -> dict[str, Any] | None:
    successful_runs = [run_id for run_id in source_run_ids if _run_is_successful(index, run_id)]
    failed_or_recovered_runs = [run_id for run_id in source_run_ids if _run_is_failed_or_recovered(index, run_id)]
    if not successful_runs and not failed_or_recovered_runs:
        return None
    return {
        "kind": "skill",
        "targetKind": "SkillProposal",
        "targetManifest": {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "SkillProposal",
            "metadata": {"id": "SKILLP-DRAFT-bootstrap-self-history"},
            "spec": {
                "project": index.project.object_id,
                "dedupeKey": "learning:bootstrap:skill:self-history",
                "title": "Self-hosting learning extractor skill baseline",
                "capability": (
                    "Use both successful and failed or recovered AITEAMOS runs before promoting durable skill updates."
                ),
                "evidence": {
                    "successfulRuns": successful_runs,
                    "failedOrRecoveredRuns": failed_or_recovered_runs,
                },
            },
        },
        "summary": "Bootstrap skill candidate across self-hosting run history.",
        "confidence": 0.61 if failed_or_recovered_runs else 0.49,
        "evidence": [f"runs/{run_id}/run.yaml" for run_id in _unique_strings(successful_runs + failed_or_recovered_runs)],
        "dedupeKey": "learning:bootstrap:skill:self-history",
        "reviewGuidance": "Skill promotion requires both success and failure/recovery run evidence.",
    }


def _bootstrap_retrospective_learning_proposal(index: Any, source_run_ids: list[str]) -> dict[str, Any]:
    source_tasks = _unique_strings(
        [index.runs[run_id].spec.task for run_id in source_run_ids if index.runs[run_id].spec.task]
    )
    return {
        "kind": "retrospective",
        "targetKind": "RetrospectiveCandidate",
        "targetManifest": {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "RetrospectiveCandidate",
            "metadata": {"id": "RETROC-DRAFT-bootstrap-self-history"},
            "spec": {
                "project": index.project.object_id,
                "sourceRuns": source_run_ids,
                "sourceTasks": source_tasks,
                "dedupeKey": "learning:bootstrap:retrospective:self-history",
                "summary": (
                    "Review the self-hosting run sequence as one baseline for future plan-vs-actual learning."
                ),
            },
        },
        "summary": "Bootstrap retrospective candidate from full self-hosting run history.",
        "confidence": 0.63,
        "evidence": [f"runs/{run_id}/run.yaml" for run_id in source_run_ids],
        "dedupeKey": "learning:bootstrap:retrospective:self-history",
    }


def _run_evidence_paths(run: Any) -> list[str]:
    run_id = run.object_id
    paths = [f"runs/{run_id}/run.yaml"]
    if run.spec.journal:
        paths.append(f"runs/{run_id}/{run.spec.journal}")
    if run.spec.eventLedger:
        paths.append(f"runs/{run_id}/{run.spec.eventLedger}")
    return paths


def _bootstrap_learning_stats(
    source_run_ids: list[str],
    candidates: list[LearningExtractionProposal],
    admitted: list[LearningExtractionProposal],
) -> dict[str, Any]:
    admitted_keys = _proposal_key_set(admitted)
    candidate_keys = _proposal_key_set(candidates)
    per_kind: dict[str, dict[str, Any]] = {}
    for kind in ["memory", "skill", "growth", "retrospective"]:
        kind_candidates = [proposal for proposal in candidates if proposal.kind == kind]
        kind_admitted = [proposal for proposal in admitted if proposal.kind == kind]
        unique_keys = {proposal.dedupeKey for proposal in kind_candidates if proposal.dedupeKey}
        duplicate_count = max(0, len(kind_candidates) - len(unique_keys))
        collision_count = _proposal_cross_kind_collision_count(kind_candidates, candidates)
        candidate_count = len(kind_candidates)
        per_kind[kind] = {
            "candidateCount": candidate_count,
            "admittedCount": len(kind_admitted),
            "skippedCount": max(0, candidate_count - len(kind_admitted) - duplicate_count),
            "dedupedCount": duplicate_count,
            "dedupeRate": _ratio(duplicate_count, candidate_count),
            "conflictCount": collision_count,
            "conflictRate": _ratio(collision_count, candidate_count),
        }
    duplicate_total = max(0, len(candidates) - len(candidate_keys))
    conflict_total = _proposal_cross_kind_collision_count(candidates, candidates)
    return {
        "runCount": len(source_run_ids),
        "sourceRunIds": source_run_ids,
        "candidateCount": len(candidates),
        "admittedCount": len(admitted),
        "skippedCount": max(0, len(candidates) - len(admitted) - duplicate_total),
        "dedupedCount": duplicate_total,
        "dedupeRate": _ratio(duplicate_total, len(candidates)),
        "conflictCount": conflict_total,
        "conflictRate": _ratio(conflict_total, len(candidates)),
        "proposalClassStats": per_kind,
        "admittedProposalKeys": sorted(admitted_keys),
        "candidateProposalKeys": sorted(candidate_keys),
    }


def _proposal_cross_kind_collision_count(
    proposals: list[LearningExtractionProposal],
    all_proposals: list[LearningExtractionProposal],
) -> int:
    keys = {proposal.dedupeKey for proposal in proposals if proposal.dedupeKey}
    collisions = 0
    for key in keys:
        kinds = {proposal.kind for proposal in all_proposals if proposal.dedupeKey == key}
        if len(kinds) > 1:
            collisions += 1
    return collisions


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _bootstrap_learning_dedupe_key(source_run_ids: list[str], proposals: list[LearningExtractionProposal]) -> str:
    raw = json.dumps(
        {
            "sourceRunIds": source_run_ids,
            "extractor": LEARNING_EXTRACTOR_ID,
            "version": BOOTSTRAP_LEARNING_EXTRACTOR_VERSION,
            "proposalKeys": sorted(_proposal_key_set(proposals)),
        },
        sort_keys=True,
        ensure_ascii=True,
    )
    return f"learning-bootstrap:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]}"


def _existing_bootstrap_learning_extraction(
    index: Any,
    dedupe_key: str,
    baseline_id: str,
) -> LearningExtraction | None:
    exact = index.learning_extractions.get(baseline_id)
    if exact and exact.spec.dedupeKey == dedupe_key:
        return exact
    for extraction in index.learning_extractions.values():
        if extraction.spec.dedupeKey == dedupe_key:
            return extraction
    return None


def _normalize_learning_proposal(
    run_id: str,
    extractor_id: str,
    proposal: dict[str, Any] | LearningExtractionProposal,
) -> LearningExtractionProposal:
    data = proposal.model_dump(mode="json", exclude_none=True) if isinstance(proposal, LearningExtractionProposal) else dict(proposal)
    target_manifest = data.get("targetManifest") or {}
    if not isinstance(target_manifest, dict):
        raise ValueError("learning extraction proposal targetManifest must be an object")
    if not data.get("dedupeKey"):
        target_spec = target_manifest.get("spec") if isinstance(target_manifest.get("spec"), dict) else {}
        data["dedupeKey"] = target_spec.get("dedupeKey") or _proposal_manifest_dedupe_key(
            run_id,
            extractor_id,
            str(data.get("kind")),
            target_manifest,
        )
    return LearningExtractionProposal.model_validate(data)


def _validate_unique_learning_proposal_keys(proposals: list[LearningExtractionProposal]) -> None:
    seen_dedupe: dict[str, str] = {}
    for proposal in proposals:
        if not proposal.dedupeKey:
            raise ValueError("learning extraction proposal requires dedupeKey")
        previous_kind = seen_dedupe.get(proposal.dedupeKey)
        if previous_kind is not None:
            if previous_kind == proposal.kind:
                raise ValueError(f"duplicate learning proposal dedupeKey {proposal.dedupeKey!r}")
            raise ValueError(
                f"learning proposal dedupeKey {proposal.dedupeKey!r} collides between {previous_kind} and {proposal.kind}"
            )
        seen_dedupe[proposal.dedupeKey] = proposal.kind


def _filter_skill_proposals_by_evidence(
    index: Any,
    proposals: list[LearningExtractionProposal],
) -> tuple[list[LearningExtractionProposal], list[str]]:
    accepted: list[LearningExtractionProposal] = []
    warnings: list[str] = []
    for proposal in proposals:
        if proposal.kind != "skill":
            accepted.append(proposal)
            continue
        if _skill_proposal_has_required_run_evidence(index, proposal):
            accepted.append(proposal)
            continue
        warnings.append(
            "Skipped SkillProposal draft "
            f"{proposal.dedupeKey or '<missing-dedupe-key>'}: requires at least one successful run and one failed or recovered run."
        )
    return accepted, warnings


def _skill_proposal_has_required_run_evidence(index: Any, proposal: LearningExtractionProposal) -> bool:
    successful_runs, failed_or_recovered_runs = _skill_proposal_evidence_runs(proposal)
    has_success = any(_run_is_successful(index, run_id) for run_id in successful_runs)
    has_failure_or_recovery = any(_run_is_failed_or_recovered(index, run_id) for run_id in failed_or_recovered_runs)
    return has_success and has_failure_or_recovery


def _skill_proposal_evidence_runs(proposal: LearningExtractionProposal) -> tuple[list[str], list[str]]:
    spec = proposal.targetManifest.get("spec") if isinstance(proposal.targetManifest.get("spec"), dict) else {}
    evidence = spec.get("evidence") if isinstance(spec.get("evidence"), dict) else {}
    successful_runs = _string_list(
        evidence.get("successfulRuns")
        or evidence.get("successRuns")
        or spec.get("successfulRuns")
        or spec.get("successRuns")
    )
    failed_or_recovered_runs = _string_list(
        evidence.get("failedOrRecoveredRuns")
        or evidence.get("failureRecoveryRuns")
        or spec.get("failedOrRecoveredRuns")
        or spec.get("failureRecoveryRuns")
    )
    return successful_runs, failed_or_recovered_runs


def _run_is_successful(index: Any, run_id: str) -> bool:
    run = index.runs.get(run_id)
    return bool(run and str(run.spec.status).upper() in SUCCESSFUL_RUN_STATUSES)


def _run_is_failed_or_recovered(index: Any, run_id: str) -> bool:
    run = index.runs.get(run_id)
    if run is None:
        return False
    if str(run.spec.status).upper() in FAILED_OR_RECOVERED_RUN_STATUSES:
        return True
    return any(_event_has_failure_or_recovery_signal(event) for event in index.run_events.get(run_id, []))


def _event_has_failure_or_recovery_signal(event: dict[str, Any]) -> bool:
    event_type = str(event.get("type", "")).lower()
    return bool(event.get("error") or "failed" in event_type or "recover" in event_type or "stalled" in event_type)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _existing_learning_extraction(
    index: Any,
    run_id: str,
    extractor_id: str,
    proposals: list[LearningExtractionProposal],
) -> LearningExtraction | None:
    incoming = _proposal_key_set(proposals)
    partial_matches: list[str] = []
    incoming_dedupe_to_kind = {proposal.dedupeKey: proposal.kind for proposal in proposals if proposal.dedupeKey}
    for extraction in index.learning_extractions.values():
        if extraction.spec.runId != run_id or extraction.spec.extractorId != extractor_id:
            continue
        existing = _proposal_key_set(extraction.spec.proposals)
        if incoming == existing or incoming.issubset(existing):
            return extraction
        overlap = incoming & existing
        if overlap:
            partial_matches.append(f"{extraction.object_id}:{','.join(sorted(overlap))}")
        for proposal in extraction.spec.proposals:
            if proposal.dedupeKey in incoming_dedupe_to_kind and incoming_dedupe_to_kind[proposal.dedupeKey] != proposal.kind:
                raise ValueError(
                    f"learning proposal dedupeKey {proposal.dedupeKey!r} already exists as {proposal.kind} in {extraction.object_id}"
                )
    if partial_matches:
        raise ValueError(f"learning extraction proposal key partially overlaps existing manifests: {'; '.join(partial_matches)}")
    return None


def _proposal_key_set(proposals: list[LearningExtractionProposal]) -> set[str]:
    return {f"{proposal.kind}:{proposal.dedupeKey}" for proposal in proposals if proposal.dedupeKey}


def _proposal_manifest_dedupe_key(run_id: str, extractor_id: str, kind: str, target_manifest: dict[str, Any]) -> str:
    raw = json.dumps(
        {
            "run": run_id,
            "extractor": extractor_id,
            "kind": kind,
            "targetManifest": target_manifest,
        },
        sort_keys=True,
        ensure_ascii=True,
    )
    return f"learning:{run_id}:{kind}:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def _learning_extraction_dedupe_key(
    run_id: str,
    extractor_id: str,
    extractor_version: str,
    proposals: list[LearningExtractionProposal],
) -> str:
    raw = json.dumps(
        {
            "run": run_id,
            "extractor": extractor_id,
            "version": extractor_version,
            "proposalKeys": sorted(_proposal_key_set(proposals)),
        },
        sort_keys=True,
        ensure_ascii=True,
    )
    return f"learning-extraction:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]}"


def _timestamp_learning_extraction_id(now: datetime) -> str:
    return f"LEX-{now:%Y%m%dT%H%M%S}{now.microsecond // 1000:03d}"


def _empty_learning_extraction_result(warnings: list[str]) -> dict[str, Any]:
    return {
        "extraction": None,
        "id": None,
        "created": False,
        "dedupeKey": None,
        "proposalKeys": [],
        "warnings": warnings,
    }


def _learning_extraction_result(
    extraction: LearningExtraction,
    *,
    created: bool,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    combined_warnings = [*extraction.spec.warnings, *(warnings or [])]
    return {
        "extraction": extraction,
        "id": extraction.object_id,
        "created": created,
        "dedupeKey": extraction.spec.dedupeKey,
        "proposalKeys": sorted(_proposal_key_set(extraction.spec.proposals)),
        "warnings": combined_warnings,
    }


def _append_extractor_event(workspace_root: Path, run_id: str, proposal_ids: list[str]) -> None:
    run_dir = workspace_root / "runs" / run_id
    run_yaml = read_yaml(run_dir / "run.yaml")
    ledger_name = run_yaml.get("spec", {}).get("eventLedger") or "events.jsonl"
    ledger_path = run_dir / ledger_name
    events = read_jsonl(ledger_path)
    proposal_key = ",".join(sorted(proposal_ids))
    if any(event.get("type") == "memory.extracted" and event.get("proposalKey") == proposal_key for event in events):
        return
    append_run_event_to_ledger(
        ledger_path,
        run_yaml,
        {
            "type": "memory.extracted",
            "extractorId": EXTRACTOR_ID,
            "proposalKey": proposal_key,
            "proposals": proposal_ids,
        },
    )


def _kind_from_label(label: str) -> str:
    if label == "mistake":
        return "mistake"
    if label == "decision":
        return "decision"
    return "procedural"


def _confidence_for_kind(kind: str) -> float:
    if kind == "decision":
        return 0.7
    if kind == "mistake":
        return 0.74
    return 0.78


def _review_guidance(kind: str) -> str:
    if kind == "decision":
        return "Human review required: decision memory may conflict with canonical docs or governance."
    if kind == "mistake":
        return "Human review required: confirm the mistake, cause, recovery, and evidence before approval."
    return "Human review required before promotion; verify evidence and scope."


def _title_from_content(run_id: str, kind: str, content: str) -> str:
    first_sentence = re.split(r"[.\n]", content.strip(), maxsplit=1)[0].strip()
    if len(first_sentence) > 72:
        first_sentence = first_sentence[:69].rstrip() + "..."
    label = kind.capitalize()
    return f"{label} from {run_id}: {first_sentence}" if first_sentence else f"{label} from {run_id}"


def _usable_content(content: str) -> bool:
    stripped = content.strip()
    if len(stripped) < 24:
        return False
    lowered = stripped.lower()
    return not any(marker in lowered for marker in ["no memory", "not applicable", "n/a", "none"])


def _excerpt(text: str) -> str:
    stripped = text.strip()
    if len(stripped) <= EXCERPT_CHARS:
        return stripped
    return stripped[:EXCERPT_CHARS].rstrip() + "\n...[truncated]"


def _unique_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
