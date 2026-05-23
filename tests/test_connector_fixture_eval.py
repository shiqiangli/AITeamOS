from __future__ import annotations

from copy import deepcopy
import unittest

from aiteamos_connectors import connector_adapter_fixtures, evaluate_connector_adapter_fixture
from aiteamos_workspace import connector_adapter_fixture_records, load_workspace


class ConnectorFixtureEvalTest(unittest.TestCase):
    def test_builtin_fixture_passes_and_workspace_validate_runs_it(self) -> None:
        records = connector_adapter_fixture_records()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["id"], "github.issue.opened")
        self.assertTrue(records[0]["passed"])

        index = load_workspace(".aiteamos")
        fixture_issues = [issue for issue in index.health if issue["kind"] == "connector_adapter_fixture"]
        self.assertEqual(fixture_issues, [])

    def test_fixture_detects_normalization_drift(self) -> None:
        fixture = deepcopy(connector_adapter_fixtures()[0])
        expected = dict(fixture.expected_normalized_summary)
        expected["repository"] = "wrong/repo"
        tampered = type(fixture)(
            id=fixture.id,
            description=fixture.description,
            adapter=fixture.adapter,
            request=fixture.request,
            connector=fixture.connector,
            expected_normalized_summary=expected,
            env=fixture.env,
            expected_admission_status=fixture.expected_admission_status,
            expected_health_status=fixture.expected_health_status,
            forbidden_values=fixture.forbidden_values,
        )

        result = evaluate_connector_adapter_fixture(tampered)

        self.assertFalse(result.passed)
        self.assertIn("normalized summary did not match fixture expectation", result.failures)


if __name__ == "__main__":
    unittest.main()
