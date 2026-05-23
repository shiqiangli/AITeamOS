from __future__ import annotations

import json
from pathlib import Path
import unittest

from aiteamos_schema import build_aiteamos_bundle_schema


REPO_ROOT = Path(__file__).resolve().parents[1]


class AiteamosBundleReferenceTest(unittest.TestCase):
    def test_published_aiteamos_bundle_schema_matches_pydantic_contract(self) -> None:
        published = json.loads((REPO_ROOT / "packages" / "schema" / "generated" / "aiteamos-bundle.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(published, build_aiteamos_bundle_schema())
        record = published["$defs"]["RunAssistanceBundleRecord"]

        self.assertEqual(record["properties"]["kind"]["const"], "AiteamosBundle")
        self.assertEqual(record["properties"]["schemaVersion"]["const"], "aiteamos-bundle.v1")
        self.assertEqual(record["properties"]["ingestInputSchema"]["const"], "RunAssistedIngestInput")
        self.assertEqual(record["properties"]["secretHandling"]["const"], "references-only-no-secret-values")

    def test_reference_extension_declares_import_and_assisted_ingest_commands(self) -> None:
        extension_root = REPO_ROOT / "extensions" / "vscode-aiteamos-bundle"
        package = json.loads((extension_root / "package.json").read_text(encoding="utf-8"))
        commands = {item["command"] for item in package["contributes"]["commands"]}
        source = (extension_root / "src" / "extension.js").read_text(encoding="utf-8")

        self.assertEqual(package["main"], "./src/extension.js")
        self.assertIn("aiteamosBundle.import", commands)
        self.assertIn("aiteamosBundle.writeIngest", commands)
        self.assertIn("RunAssistedIngestInput", source)
        self.assertIn("/assisted-ingest", source)
        self.assertIn("AITEAMOS_API_TOKEN", source)
        self.assertNotIn("bundle.token", source)
        self.assertNotIn("bundle.apiToken", source)

    def test_architecture_documents_ide_bundle_contract(self) -> None:
        architecture = (REPO_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")

        self.assertIn("`aiteamos-bundle.json` is the portable Assisted IDE handoff contract", architecture)
        self.assertIn("reference VSCode/Cursor extension", architecture)
        self.assertIn("RunAssistedIngestInput", architecture)
        self.assertIn("references-only-no-secret-values", architecture)


if __name__ == "__main__":
    unittest.main()
