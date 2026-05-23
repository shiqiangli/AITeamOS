from __future__ import annotations

from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

from pydantic import ValidationError

from aiteamos_schema import API_VERSION, LearningExtraction
from aiteamos_workspace import admit_learning_extraction, bootstrap_learning_extractions, index_workspace, load_workspace


REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_EXTRACTION_ID = "L-bootstrap-self-history"
BOOTSTRAP_EXTRACTION_ID = "L-bootstrap-self-history"


class LearningExtractionManifestTest(unittest.TestCase):
    def test_self_hosting_learning_extraction_loads_and_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            index = load_workspace(workspace)

            self.assertIn(REFERENCE_EXTRACTION_ID, index.learning_extractions)
            extraction = index.learning_extractions[REFERENCE_EXTRACTION_ID]
            self.assertEqual(extraction.spec.runId, "RUN-0001")
            self.assertEqual({proposal.kind for proposal in extraction.spec.proposals}, {"memory", "growth", "retrospective"})
            self.assertEqual(index.to_summary()["counts"]["learningExtractions"], len(index.learning_extractions))

            db_path = Path(temp_dir) / "aiteamos.sqlite"
            index_workspace(workspace, db_path=db_path)
            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute(
                    """
                    select run_id, project_id, member_id, assignment_id, proposal_count
                    from learning_extractions
                    where id = ?
                    """,
                    (REFERENCE_EXTRACTION_ID,),
                ).fetchone()
                self.assertEqual(row, ("RUN-0001", "aiteamos", "architect", "aiteamos-architecture", 3))
                manifest_count = conn.execute(
                    "select count(*) from manifests where kind = 'LearningExtraction' and id = ?",
                    (REFERENCE_EXTRACTION_ID,),
                ).fetchone()[0]
                self.assertEqual(manifest_count, 1)
            finally:
                conn.close()

    def test_learning_extraction_proposal_kind_matches_target_manifest(self) -> None:
        LearningExtraction(
            apiVersion=API_VERSION,
            kind="LearningExtraction",
            metadata={"id": "LEX-VALID"},
            spec={
                "runId": "RUN-1",
                "extractedAt": "2026-05-22T16:31:13.141+08:00",
                "dedupeKey": "run:RUN-1:extractor:test:v1",
                "proposals": [
                    {
                        "kind": "growth",
                        "targetManifest": {
                            "apiVersion": API_VERSION,
                            "kind": "GrowthSignal",
                            "metadata": {"id": "GROWTH-DRAFT-1"},
                            "spec": {"summary": "Draft growth signal"},
                        },
                    }
                ],
            },
        )

        with self.assertRaises(ValidationError):
            LearningExtraction(
                apiVersion=API_VERSION,
                kind="LearningExtraction",
                metadata={"id": "LEX-INVALID"},
                spec={
                    "runId": "RUN-1",
                    "extractedAt": "2026-05-22T16:31:13.141+08:00",
                    "dedupeKey": "run:RUN-1:extractor:test:v1",
                    "proposals": [{"kind": "growth", "targetManifest": {"kind": "MemoryProposal"}}],
                },
            )

    def test_learning_extraction_admission_returns_existing_manifest_for_repeated_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            existing = load_workspace(workspace).learning_extractions[REFERENCE_EXTRACTION_ID]
            initial_count = len(load_workspace(workspace).learning_extractions)
            proposal_payloads = [
                proposal.model_dump(mode="json", exclude_none=True)
                for proposal in existing.spec.proposals
            ]

            first = admit_learning_extraction(
                workspace,
                run_id=existing.spec.runId,
                extractor_id=existing.spec.extractorId,
                extractor_version=existing.spec.extractorVersion,
                proposals=proposal_payloads,
            )
            second = admit_learning_extraction(
                workspace,
                run_id=existing.spec.runId,
                extractor_id=existing.spec.extractorId,
                extractor_version=existing.spec.extractorVersion,
                proposals=proposal_payloads,
            )

            index = load_workspace(workspace)
            self.assertFalse(first["created"])
            self.assertFalse(second["created"])
            self.assertEqual(first["id"], REFERENCE_EXTRACTION_ID)
            self.assertEqual(second["id"], REFERENCE_EXTRACTION_ID)
            self.assertEqual(len(index.learning_extractions), initial_count)

    def test_learning_extraction_admission_creates_once_for_new_proposal_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            initial_count = len(load_workspace(workspace).learning_extractions)
            proposals = [
                {
                    "kind": "memory",
                    "targetManifest": {
                        "apiVersion": API_VERSION,
                        "kind": "MemoryProposal",
                        "metadata": {"id": "MP-DRAFT-UNIQUE"},
                        "spec": {
                            "project": "aiteamos",
                            "sourceRun": "RUN-0001",
                            "sourceExtractorId": "aiteamos.learning-extractor",
                            "dedupeKey": "learning:RUN-0001:memory:unique-dg-53",
                            "kind": "procedural",
                            "title": "Unique DG-5.3 draft",
                            "content": "Repeated admission should return this LearningExtraction manifest.",
                        },
                    },
                    "confidence": 0.73,
                }
            ]

            created = admit_learning_extraction(workspace, run_id="RUN-0001", proposals=proposals)
            repeated = admit_learning_extraction(workspace, run_id="RUN-0001", proposals=proposals)
            index = load_workspace(workspace)

            self.assertTrue(created["created"])
            self.assertFalse(repeated["created"])
            self.assertEqual(created["id"], repeated["id"])
            self.assertIn(created["id"], index.learning_extractions)
            self.assertEqual(len(index.learning_extractions), initial_count + 1)

    def test_bootstrap_learning_extraction_is_idempotent_and_records_class_stats(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            bootstrap_path = workspace / "learning_extractions" / f"{BOOTSTRAP_EXTRACTION_ID}.yaml"
            if bootstrap_path.exists():
                bootstrap_path.unlink()
            initial_count = len(load_workspace(workspace).learning_extractions)

            first = bootstrap_learning_extractions(workspace)
            second = bootstrap_learning_extractions(workspace)
            index = load_workspace(workspace)

            self.assertTrue(first["created"])
            self.assertFalse(second["created"])
            self.assertEqual(first["id"], BOOTSTRAP_EXTRACTION_ID)
            self.assertEqual(second["id"], BOOTSTRAP_EXTRACTION_ID)
            self.assertEqual(len(index.learning_extractions), initial_count + 1)

            extraction = index.learning_extractions[BOOTSTRAP_EXTRACTION_ID]
            stats = extraction.spec.model_extra["bootstrapStats"]
            class_stats = stats["proposalClassStats"]
            self.assertEqual(set(class_stats), {"memory", "skill", "growth", "retrospective"})
            self.assertEqual(stats["runCount"], len(index.runs))
            self.assertEqual(stats["dedupedCount"], 0)
            self.assertEqual(stats["conflictCount"], 0)
            self.assertEqual(class_stats["skill"]["admittedCount"], 0)
            self.assertEqual(class_stats["skill"]["skippedCount"], 1)
            self.assertEqual({proposal.kind for proposal in extraction.spec.proposals}, {"memory", "growth", "retrospective"})

    def test_learning_extraction_admission_rejects_cross_kind_dedupe_collision(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            proposals = [
                {
                    "kind": "memory",
                    "dedupeKey": "learning:RUN-1:shared",
                    "targetManifest": {"kind": "MemoryProposal"},
                },
                {
                    "kind": "growth",
                    "dedupeKey": "learning:RUN-1:shared",
                    "targetManifest": {"kind": "GrowthSignal"},
                },
            ]

            with self.assertRaises(ValueError):
                admit_learning_extraction(workspace, run_id="RUN-0001", proposals=proposals)

    def test_learning_extraction_admission_skips_skill_without_success_and_failure_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            proposals = [
                {
                    "kind": "skill",
                    "targetManifest": {
                        "apiVersion": API_VERSION,
                        "kind": "SkillProposal",
                        "metadata": {"id": "SKILLP-DRAFT-MISSING-FAILURE"},
                        "spec": {
                            "project": "aiteamos",
                            "dedupeKey": "learning:RUN-0001:skill:missing-failure",
                            "evidence": {"successfulRuns": ["RUN-0001"]},
                        },
                    },
                },
                {
                    "kind": "memory",
                    "targetManifest": {
                        "apiVersion": API_VERSION,
                        "kind": "MemoryProposal",
                        "metadata": {"id": "MP-DRAFT-SKILL-FALLBACK"},
                        "spec": {
                            "project": "aiteamos",
                            "sourceRun": "RUN-0001",
                            "sourceExtractorId": "aiteamos.learning-extractor",
                            "dedupeKey": "learning:RUN-0001:memory:skill-fallback",
                            "kind": "procedural",
                            "title": "Skill fallback memory",
                            "content": "A skill proposal without failure evidence stays out of the skill queue.",
                        },
                    },
                },
            ]

            result = admit_learning_extraction(workspace, run_id="RUN-0001", proposals=proposals)
            extraction = result["extraction"]

            self.assertTrue(result["created"])
            self.assertTrue(result["warnings"])
            self.assertEqual([proposal.kind for proposal in extraction.spec.proposals], ["memory"])

    def test_learning_extraction_admission_accepts_skill_with_success_and_failure_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_failed_run(workspace)
            proposals = [
                {
                    "kind": "skill",
                    "targetManifest": {
                        "apiVersion": API_VERSION,
                        "kind": "SkillProposal",
                        "metadata": {"id": "SKILLP-DRAFT-WITH-FAILURE"},
                        "spec": {
                            "project": "aiteamos",
                            "dedupeKey": "learning:RUN-0001:skill:with-failure",
                            "title": "Failure-informed task planning skill",
                            "capability": "Use both clean and failed runs before proposing a durable skill.",
                            "evidence": {
                                "successfulRuns": ["RUN-0001"],
                                "failedOrRecoveredRuns": ["RUN-FAILED-SKILL-GATE"],
                            },
                        },
                    },
                }
            ]

            result = admit_learning_extraction(workspace, run_id="RUN-0001", proposals=proposals)
            extraction = result["extraction"]

            self.assertTrue(result["created"])
            self.assertEqual(result["warnings"], [])
            self.assertEqual([proposal.kind for proposal in extraction.spec.proposals], ["skill"])


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        REPO_ROOT / ".aiteamos",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    return workspace


def _write_failed_run(workspace: Path) -> None:
    run_dir = workspace / "runs" / "RUN-FAILED-SKILL-GATE"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.yaml").write_text(
        """apiVersion: aiteamos.dev/v1alpha1
kind: Run
metadata:
  id: RUN-FAILED-SKILL-GATE
  createdAt: "2026-05-22T17:00:28.594+08:00"
spec:
  project: aiteamos
  task: TASK-20260520T101022277
  member: architect
  assignment: aiteamos-architecture
  memberKind: digital
  mode: assisted
  status: FAILED
  eventLedger: events.jsonl
  journal: journal.md
""",
        encoding="utf-8",
    )
    (run_dir / "events.jsonl").write_text(
        '{"seq":1,"ts":"2026-05-22T17:00:28.594+08:00","type":"run.failed"}\n',
        encoding="utf-8",
    )
    (run_dir / "journal.md").write_text("Failed run evidence for skill gating.\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
