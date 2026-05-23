from __future__ import annotations

from pathlib import Path
import unittest

from aiteamos_schema.models import KIND_TO_MODEL


REPO_ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE = REPO_ROOT / "docs" / "architecture.md"


class DataLifecyclePolicyTest(unittest.TestCase):
    def test_architecture_policy_covers_every_source_manifest_kind(self) -> None:
        section = _data_lifecycle_section()
        rows = _policy_rows(section)

        self.assertEqual(sorted(rows), sorted(KIND_TO_MODEL))
        for kind, columns in rows.items():
            with self.subTest(kind=kind):
                self.assertEqual(len(columns), 5)
                self.assertTrue(all(value.strip() for value in columns))
                self.assertNotIn("TBD", " ".join(columns).upper())

    def test_architecture_policy_keeps_source_and_derived_boundaries(self) -> None:
        section = _data_lifecycle_section()

        self.assertIn("`.aiteamos/` remains the source of truth", section)
        self.assertIn("SQLite, vector indexes, dashboard caches, and export bundles are derived views", section)
        self.assertIn("decisionAudit", section)
        self.assertIn("Secrets are never retained", section)
        for export_policy in ("include", "sanitize", "manifest-only", "exclude"):
            self.assertIn(f"`{export_policy}`", section)


def _data_lifecycle_section() -> str:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    marker = "### Data lifecycle policy"
    self_hosting_marker = "Git activity import receipts under"
    start = text.index(marker)
    end = text.index(self_hosting_marker, start)
    return text[start:end]


def _policy_rows(section: str) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in section.splitlines():
        if not line.startswith("| "):
            continue
        columns = [column.strip() for column in line.strip().strip("|").split("|")]
        if columns[0] in {"Manifest kind", "---"}:
            continue
        rows[columns[0]] = columns
    return rows


if __name__ == "__main__":
    unittest.main()
