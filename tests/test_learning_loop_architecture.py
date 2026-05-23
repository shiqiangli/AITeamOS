from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE = REPO_ROOT / "docs" / "architecture.md"


class LearningLoopArchitectureTest(unittest.TestCase):
    def test_learning_loop_data_flow_is_target_only_and_read_only(self) -> None:
        text = ARCHITECTURE.read_text(encoding="utf-8")
        marker = "### Learning loop"
        self.assertIn(marker, text)
        section = text.split(marker, 1)[1].split("\nAuto-approval", 1)[0]

        for required in [
            "RunJournal[RunJournal] --> LearningExtractor[LearningExtractor]",
            "LearningExtractor --> ProposalKind{ProposalKind[]}",
            "ProposalKind --> MemoryDraft[MemoryProposal draft]",
            "ProposalKind --> SkillDraft[SkillProposal draft]",
            "ProposalKind --> GrowthDraft[GrowthSignal draft]",
            "ProposalKind --> RetrospectiveDraft[RetrospectiveCandidate draft]",
            "The LearningExtractor is a read-only projector",
            "must not write `.aiteamos` manifests",
            "Durable writes happen only through explicit proposal admission APIs",
            "dedupe key",
        ]:
            self.assertIn(required, section)

        for forbidden in [
            "Current implementation",
            "MVP",
            "next step",
            "not yet",
            "roadmap",
        ]:
            self.assertNotIn(forbidden, section)


if __name__ == "__main__":
    unittest.main()
