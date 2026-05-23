from __future__ import annotations

from pathlib import Path
import sys
import unittest

from aiteamos_connectors import ConnectorPackage, evaluate_connector_adapter_fixture


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = REPO_ROOT / "examples" / "connectors" / "slack-notification"
TEMPLATE_SRC = TEMPLATE_ROOT / "src"


class ConnectorReferenceAdapterTemplateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if str(TEMPLATE_SRC) not in sys.path:
            sys.path.insert(0, str(TEMPLATE_SRC))

    def test_slack_reference_package_exposes_entry_point_target(self) -> None:
        pyproject = (TEMPLATE_ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn('[project.entry-points."aiteamos.connectors"]', pyproject)
        self.assertIn("slack_notification = \"aiteamos_slack_notification_connector:connector_package\"", pyproject)

    def test_slack_reference_connector_package_fixture_passes(self) -> None:
        from aiteamos_slack_notification_connector import connector_package

        package = connector_package()

        self.assertIsInstance(package, ConnectorPackage)
        self.assertEqual(package.provider, "slack")
        self.assertEqual(package.connector_types, ("chat",))
        self.assertEqual(len(package.fixtures), 1)
        result = evaluate_connector_adapter_fixture(package.fixtures[0])
        self.assertTrue(result.passed, result.failures)

    def test_reference_docs_keep_example_out_of_product_catalog(self) -> None:
        examples_readme = (REPO_ROOT / "examples" / "README.md").read_text(encoding="utf-8")
        connector_readme = (REPO_ROOT / "examples" / "connectors" / "README.md").read_text(encoding="utf-8")

        self.assertIn("not product catalog entries", connector_readme)
        self.assertIn("product examples", examples_readme)
        self.assertIn("not be shown in product-facing workspace catalogs", examples_readme)


if __name__ == "__main__":
    unittest.main()
