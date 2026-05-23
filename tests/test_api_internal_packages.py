from __future__ import annotations

import ast
from pathlib import Path
import unittest

from tests.inline_testclient import TestClient

from aiteamos_api import create_app
from aiteamos_api.automation import execute_automation_run, trigger_automation
from aiteamos_api.connector import check_connector_health, connector_remediation_suggestions
from aiteamos_api.context import build_context_capsule, build_run_launch_plan
from aiteamos_api.git_activity import admit_local_git_activity_import, git_activity_correlation_preview
from aiteamos_api.manager import manager_input_bundle
from aiteamos_api.memory import create_memory_store, memory_proposal_review_queue
from aiteamos_api.permission import explain_effective_permissions, permission_request_records


REPO_ROOT = Path(__file__).resolve().parents[1]
APP = REPO_ROOT / "services" / "api" / "aiteamos_api" / "app.py"
ROUTES = REPO_ROOT / "services" / "api" / "aiteamos_api" / "routes.py"
WORKSPACE = REPO_ROOT / ".aiteamos"


class ApiInternalPackagesTest(unittest.TestCase):
    def test_domain_subpackages_export_stable_symbols(self) -> None:
        symbols = [
            build_context_capsule,
            build_run_launch_plan,
            create_memory_store,
            memory_proposal_review_queue,
            trigger_automation,
            execute_automation_run,
            explain_effective_permissions,
            permission_request_records,
            check_connector_health,
            connector_remediation_suggestions,
            admit_local_git_activity_import,
            git_activity_correlation_preview,
            manager_input_bundle,
        ]

        for symbol in symbols:
            self.assertTrue(callable(symbol), symbol)

    def test_app_imports_domain_functions_through_internal_packages(self) -> None:
        tree = ast.parse(ROUTES.read_text(encoding="utf-8"))
        relative_imports: dict[str, set[str]] = {}
        workspace_imports: set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            imported = {alias.name for alias in node.names}
            if node.level == 1 and node.module:
                relative_imports.setdefault(node.module, set()).update(imported)
            if node.level == 0 and node.module == "aiteamos_workspace":
                workspace_imports.update(imported)

        expected = {
            "context": {"build_context_capsule", "build_run_launch_plan"},
            "memory": {"create_memory_store", "memory_proposal_review_queue"},
            "automation": {"trigger_automation", "execute_automation_run"},
            "permission": {"explain_effective_permissions", "permission_request_records"},
            "connector": {"check_connector_health", "connector_remediation_suggestions"},
            "git_activity": {"admit_local_git_activity_import", "git_activity_correlation_preview"},
            "manager": {"manager_input_bundle"},
        }
        for module, names in expected.items():
            self.assertTrue(names <= relative_imports.get(module, set()), module)

        forbidden_direct_imports = set().union(*expected.values())
        self.assertFalse(forbidden_direct_imports.intersection(workspace_imports))

    def test_app_py_is_thin_entrypoint(self) -> None:
        text = APP.read_text(encoding="utf-8")
        lines = text.splitlines()

        self.assertLessEqual(len(lines), 800)
        self.assertLessEqual(len(text.encode("utf-8")), 30_000)
        self.assertIn("from .routes import create_app as create_routes_app", text)

    def test_external_workspace_health_api_still_works(self) -> None:
        response = TestClient(create_app(WORKSPACE)).get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"]["errors"], 0)


if __name__ == "__main__":
    unittest.main()
