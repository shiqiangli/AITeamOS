from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import hashlib
import json
import re

from aiteamos_schema import MemoryProposal, Run, timestamp_memory_proposal_id

from .artifacts import record_artifact_manifest
from .io import read_jsonl, read_text_if_exists, read_yaml, write_text, write_yaml
from .loader import load_workspace
from .run_events import append_run_event_to_ledger


SECRET_ASSIGNMENT_RE = re.compile(
    r"\b([A-Z][A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)[A-Z0-9_]*=)([^\s]+)"
)
SECRET_FIELD_RE = re.compile(
    r'(?i)(["\']?(?:api[_-]?key|token|secret|password|credential)["\']?\s*[:=]\s*["\']?)([^"\'\s,}]+)'
)
SECRET_TOKEN_RE = re.compile(r"\b(sk-[A-Za-z0-9_-]{8,})\b")


def ingest_run_outputs(
    workspace_path: str | Path,
    run_id: str,
    *,
    journal: str | None = None,
    diff_patch: str | None = None,
    test_log: str | None = None,
    review_target: dict[str, Any] | None = None,
    memory_proposal: dict[str, Any] | None = None,
) -> Run:
    index = load_workspace(workspace_path)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")

    payload = _normalized_payload(
        journal=journal,
        diff_patch=diff_patch,
        test_log=test_log,
        review_target=review_target,
        memory_proposal=memory_proposal,
    )
    ingest_id = _ingest_id(payload)
    run_dir = index.workspace_root / "runs" / run_id
    events = index.run_events.get(run_id, [])
    if _has_completed_ingest(events, ingest_id):
        return index.runs[run_id]

    run_path = run_dir / "run.yaml"
    data = read_yaml(run_path)
    spec = data.setdefault("spec", {})
    outputs = spec.setdefault("outputs", [])
    artifacts: list[str] = []
    artifact_manifests: list[str] = []

    if payload["journal"]:
        journal_uri = f"runs/{run_id}/journal.md"
        _append_journal_section(run_dir / (spec.get("journal") or "journal.md"), ingest_id, payload["journal"])
        artifacts.append(journal_uri)
        artifact_manifests.append(_write_artifact_manifest(index.workspace_root, run_id, ingest_id, "journal", journal_uri))

    if payload["diffPatch"]:
        diff_uri = f"runs/{run_id}/diff.patch"
        _write_ingested_artifact(run_dir / "diff.patch", payload["diffPatch"])
        artifacts.append(diff_uri)
        diff_manifest = _write_artifact_manifest(index.workspace_root, run_id, ingest_id, "diff_patch", diff_uri)
        artifact_manifests.append(diff_manifest)
        _add_unique(outputs, {"type": "diff_patch", "path": diff_uri, "source": "assisted_ingest", "artifactManifest": diff_manifest})

    if payload["testLog"]:
        test_uri = f"runs/{run_id}/test.log"
        _write_ingested_artifact(run_dir / "test.log", payload["testLog"])
        artifacts.append(test_uri)
        test_manifest = _write_artifact_manifest(index.workspace_root, run_id, ingest_id, "test_log", test_uri)
        artifact_manifests.append(test_manifest)
        _add_unique(outputs, {"type": "test_log", "path": test_uri, "source": "assisted_ingest", "artifactManifest": test_manifest})

    target = _clean_review_target(payload["reviewTarget"])
    if target:
        spec["reviewTarget"] = target

    proposal_id = _upsert_memory_proposal(
        index.workspace_root,
        run_id=run_id,
        project=spec["project"],
        member=spec.get("member"),
        assignment=spec.get("assignment"),
        source_task=spec.get("task"),
        ingest_id=ingest_id,
        proposal=payload["memoryProposal"],
    )
    if proposal_id:
        proposals = spec.setdefault("memoryProposals", [])
        _add_unique(proposals, proposal_id)

    missing = _missing_required_inputs(run_dir, spec)
    spec["status"] = "INGEST_INCOMPLETE" if missing else "REVIEW"
    spec["ingest"] = {
        "lastIngestId": ingest_id,
        "lastIngestedAt": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "member": spec.get("member"),
        "assignment": spec.get("assignment"),
        "missing": missing,
        "artifacts": artifacts,
        "artifactManifests": artifact_manifests,
    }
    if proposal_id:
        spec["ingest"]["memoryProposal"] = proposal_id

    run = Run.model_validate(data)
    write_yaml(run_path, run.model_dump(mode="json", exclude_none=True))
    if not missing:
        _mark_task_review(index.workspace_root, run.spec.task)
    _append_event(
        run_dir,
        spec.get("eventLedger") or "events.jsonl",
        {
            "type": "assisted.ingest.incomplete" if missing else "assisted.ingest.completed",
            "ingestId": ingest_id,
            "member": spec.get("member"),
            "assignment": spec.get("assignment"),
            "missing": missing,
            "artifacts": artifacts,
            "artifactManifests": artifact_manifests,
            "memoryProposal": proposal_id,
        },
    )
    return load_workspace(workspace_path).runs[run_id]


def _normalized_payload(
    *,
    journal: str | None,
    diff_patch: str | None,
    test_log: str | None,
    review_target: dict[str, Any] | None,
    memory_proposal: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "journal": _redact_secret_values((journal or "").strip()),
        "diffPatch": _clean_diff_patch(diff_patch),
        "testLog": _redact_secret_values(_normalize_text(test_log)),
        "reviewTarget": _clean_review_target(review_target or {}),
        "memoryProposal": _clean_memory_proposal(memory_proposal or {}),
    }


def _normalize_text(value: str | None) -> str:
    text = (value or "").strip()
    return text + "\n" if text else ""


def _clean_diff_patch(value: str | None) -> str:
    text = _normalize_text(value)
    if text and _contains_secret_material(text):
        raise ValueError("diff patch appears to contain secret material")
    return text


def _ingest_id(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _has_completed_ingest(events: list[dict[str, Any]], ingest_id: str) -> bool:
    return any(event.get("type", "").startswith("assisted.ingest.") and event.get("ingestId") == ingest_id for event in events)


def _append_journal_section(path: Path, ingest_id: str, content: str) -> None:
    marker = f"## Assisted Ingest {ingest_id}"
    previous = read_text_if_exists(path) or f"# {path.parent.name} Journal\n"
    if marker in previous:
        return
    section = f"\n\n{marker}\n\n{content.strip()}\n"
    write_text(path, previous.rstrip() + section)


def _write_ingested_artifact(path: Path, content: str) -> None:
    existing = read_text_if_exists(path)
    if existing == content:
        return
    write_text(path, content)


def _write_artifact_manifest(workspace_root: Path, run_id: str, ingest_id: str, kind: str, uri: str) -> str:
    return record_artifact_manifest(
        workspace_root,
        run_id,
        kind,
        uri,
        source_id=ingest_id,
        redaction={
            "secretValues": "redacted-before-write" if kind in {"journal", "test_log"} else "rejected-before-write"
        },
    )


def _clean_review_target(target: dict[str, Any]) -> dict[str, Any] | None:
    if not target:
        return None
    target_type = (target.get("type") or "").strip() or "external_review"
    url = (target.get("url") or "").strip()
    ref = (target.get("ref") or "").strip()
    description = _redact_secret_values((target.get("description") or "").strip())
    if not url and not ref:
        return None
    if _contains_secret_material(url) or _contains_secret_material(ref):
        raise ValueError("review target appears to contain secret material")
    cleaned: dict[str, Any] = {"type": target_type}
    if url:
        cleaned["url"] = url
    if ref:
        cleaned["ref"] = ref
    if description:
        cleaned["description"] = description
    return cleaned


def _clean_memory_proposal(proposal: dict[str, Any]) -> dict[str, Any] | None:
    title = _redact_secret_values((proposal.get("title") or "").strip())
    content = _redact_secret_values((proposal.get("content") or "").strip())
    if not title or not content:
        return None
    cleaned: dict[str, Any] = {
        "title": title,
        "content": content,
        "kind": (proposal.get("kind") or "procedural").strip() or "procedural",
    }
    if proposal.get("reviewGuidance"):
        cleaned["reviewGuidance"] = _redact_secret_values(str(proposal["reviewGuidance"]).strip())
    if proposal.get("confidence") is not None:
        cleaned["confidence"] = proposal["confidence"]
    return cleaned


def _upsert_memory_proposal(
    workspace_root: Path,
    *,
    run_id: str,
    project: str,
    member: str | None,
    assignment: str | None,
    source_task: str | None,
    ingest_id: str,
    proposal: dict[str, Any] | None,
) -> str | None:
    if not proposal:
        return None

    existing = load_workspace(workspace_root).memory_proposals
    for proposal_id, item in existing.items():
        if item.spec.sourceRun == run_id and item.spec.sourceIngestId == ingest_id:
            return proposal_id

    now = datetime.now().astimezone()
    proposal_id = timestamp_memory_proposal_id(now)
    payload: dict[str, Any] = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "MemoryProposal",
        "metadata": {
            "id": proposal_id,
            "createdAt": now.isoformat(timespec="milliseconds"),
        },
        "spec": {
            "project": project,
            "member": member,
            "assignment": assignment,
            "sourceRun": run_id,
            "sourceTask": source_task,
            "sourceIngestId": ingest_id,
            "status": "pending-review",
            "kind": proposal["kind"],
            "title": proposal["title"],
            "content": proposal["content"],
            "evidence": [f"runs/{run_id}/journal.md"],
            "confidence": proposal.get("confidence"),
            "reviewGuidance": proposal.get("reviewGuidance")
            or "Assisted ingest proposal; human review required before promotion.",
        },
    }
    memory_proposal = MemoryProposal.model_validate(payload)
    write_yaml(
        workspace_root / "memory" / "proposals" / f"{proposal_id}.yaml",
        memory_proposal.model_dump(mode="json", exclude_none=True),
    )
    return proposal_id


def _missing_required_inputs(run_dir: Path, spec: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    journal_name = spec.get("journal") or "journal.md"
    journal = read_text_if_exists(run_dir / journal_name)
    if not journal or not journal.strip():
        missing.append("journal.md")
    has_review_target = bool(_clean_review_target(spec.get("reviewTarget") or {}))
    has_diff = (run_dir / "diff.patch").exists()
    if not has_review_target and not has_diff:
        missing.append("review target or diff.patch")
    return missing


def _mark_task_review(workspace_root: Path, task_id: str) -> None:
    task_path = workspace_root / "tasks" / f"{task_id}.yaml"
    if not task_path.exists():
        return
    task_data = read_yaml(task_path)
    task_data.setdefault("spec", {})["status"] = "REVIEW"
    write_yaml(task_path, task_data)


def _append_event(run_dir: Path, ledger_name: str, event: dict[str, Any]) -> None:
    ledger_path = run_dir / ledger_name
    events = read_jsonl(ledger_path)
    ingest_id = event.get("ingestId")
    if ingest_id and _has_completed_ingest(events, str(ingest_id)):
        return
    append_run_event_to_ledger(ledger_path, read_yaml(run_dir / "run.yaml"), event)


def _add_unique(values: list[Any], value: Any) -> None:
    if value not in values:
        values.append(value)


def _redact_secret_values(text: str) -> str:
    redacted = SECRET_ASSIGNMENT_RE.sub(r"\1[REDACTED]", text)
    redacted = SECRET_FIELD_RE.sub(r"\1[REDACTED]", redacted)
    redacted = SECRET_TOKEN_RE.sub("sk-[REDACTED]", redacted)
    return redacted


def _contains_secret_material(text: str) -> bool:
    return bool(
        SECRET_ASSIGNMENT_RE.search(text)
        or SECRET_FIELD_RE.search(text)
        or SECRET_TOKEN_RE.search(text)
    )
