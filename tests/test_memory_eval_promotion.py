from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from aiteamos_workspace import (
    append_run_journal,
    approve_memory_proposal,
    create_run,
    create_task,
    evaluate_memory_promotion_gate,
    load_workspace,
    memory_eval_confidence_sources,
    propose_memory,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_MEMBER = "backend-digital"
BACKEND_ASSIGNMENT = "aiteamos-backend-runtime"
EVAL_SUITE = "aiteamos-eval-suite-schema-contract"
EVAL_RESULT = "ERES-20260522T204421556"


class MemoryEvalPromotionTest(unittest.TestCase):
    def test_eval_result_pass_rate_can_supply_memory_confidence_and_entry_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="Eval-backed memory promotion",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                acceptance=["EvalSuite pass rate can supply confidence for memory promotion."],
            )
            run = create_run(workspace, task_id=task.object_id)
            evidence_path = append_run_journal(
                workspace,
                run.object_id,
                title="Eval-backed memory evidence",
                body="Local workflow hints can use a passing EvalSuite result as the confidence source.",
            )
            proposal = propose_memory(
                workspace,
                project="aiteamos",
                source_run=run.object_id,
                title="Eval-backed local workflow hint",
                content="Local workflow hints can cite a passing EvalSuite result when promoting reviewed project memory.",
                kind="procedural",
                evidence=[evidence_path],
                review_guidance="Human review checks the run evidence and EvalSuite result before approval.",
            )

            gate = evaluate_memory_promotion_gate(workspace, proposal.object_id)
            sources = memory_eval_confidence_sources(workspace, proposal.object_id)

            self.assertTrue(gate["readyForApproval"])
            self.assertEqual(gate["confidence"], None)
            self.assertEqual(gate["effectiveConfidence"], 1.0)
            self.assertEqual(sources[0]["evalSuiteId"], EVAL_SUITE)
            self.assertEqual(sources[0]["lastResultId"], EVAL_RESULT)
            self.assertEqual(sources[0]["evidenceRef"], f"eval://{EVAL_SUITE}/{EVAL_RESULT}")

            approval = approve_memory_proposal(
                workspace,
                proposal.object_id,
                reviewer_member="frontend-human",
                reason="test EvalSuite-backed confidence",
            )
            updated = load_workspace(workspace)
            memory_id = approval["spec"]["approvedMemory"]
            memory = updated.memory_entries[memory_id]

            self.assertEqual(memory.spec.confidence, 1.0)
            self.assertIn(f"eval://{EVAL_SUITE}/{EVAL_RESULT}", memory.spec.evidence)
            self.assertEqual(memory.spec.evalEvidence[0].evalSuiteId, EVAL_SUITE)
            self.assertEqual(memory.spec.evalEvidence[0].lastResultId, EVAL_RESULT)
            self.assertEqual(memory.spec.evalEvidence[0].passRate, 1.0)
            self.assertFalse([issue for issue in updated.health if issue["kind"] in {"eval_result", "memory"}])


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        REPO_ROOT / ".aiteamos",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    return workspace


if __name__ == "__main__":
    unittest.main()
