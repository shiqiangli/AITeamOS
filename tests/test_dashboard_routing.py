from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_SRC = ROOT / "apps" / "dashboard" / "src"
DASHBOARD_MAIN = DASHBOARD_SRC / "main.tsx"
DASHBOARD_APP = DASHBOARD_SRC / "state" / "App.tsx"
DASHBOARD_SHARED = DASHBOARD_SRC / "components" / "shared.tsx"
DASHBOARD_PACKAGE = ROOT / "apps" / "dashboard" / "package.json"
DASHBOARD_PLAYWRIGHT_CONFIG = ROOT / "apps" / "dashboard" / "playwright.config.ts"
DASHBOARD_PRODUCT_USER_E2E = ROOT / "apps" / "dashboard" / "e2e" / "product-user-session.spec.ts"


def runtime_files() -> list[Path]:
    return [
        DASHBOARD_MAIN,
        DASHBOARD_APP,
        DASHBOARD_SHARED,
        *sorted((DASHBOARD_SRC / "pages").glob("*/index.tsx")),
    ]


def runtime_source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in runtime_files())


def interaction_source() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((DASHBOARD_SRC / "__tests__").glob("*.test.tsx"))
    )


class DashboardRoutingTest(unittest.TestCase):
    def test_dashboard_has_real_browser_product_user_e2e_harness(self) -> None:
        package = json.loads(DASHBOARD_PACKAGE.read_text(encoding="utf-8"))
        config_source = DASHBOARD_PLAYWRIGHT_CONFIG.read_text(encoding="utf-8")
        e2e_source = DASHBOARD_PRODUCT_USER_E2E.read_text(encoding="utf-8")

        self.assertEqual(package["scripts"]["test:e2e"], "playwright test")
        self.assertIn("@playwright/test", package["devDependencies"])
        self.assertIn('testDir: "./e2e"', config_source)
        for required in [
            "AITEAMOS_API_PROXY_TARGET",
            "AITEAMOS_E2E_VIEWER_TOKEN",
            "AITEAMOS_E2E_ADMIN_TOKEN",
            'const adminProductUser = "frontend-admin";',
            "viewer=architect",
            'const memberId = "frontend-human";',
            'const assignmentId = "aiteamos-dashboard";',
            "expectScopedRequestsWithViewer",
            "Login Product Session",
            "human Run Detail assisted ingest promotes reviewed memory into context in the browser",
            "/memory/proposals",
            "/context-preview",
            "Approve Proposal",
            "Selected Memory Context Injection",
            "Forgejo provider delivery retry opens replay lineage in the browser",
            "Gitea provider issue delivery retry opens replay lineage in the browser",
            "GitLab provider merge request delivery retry opens replay lineage in the browser",
            "GitHub provider issue delivery retry opens replay lineage in the browser",
            "Webhook Admission Console",
        ]:
            self.assertIn(required, e2e_source)

    def test_main_is_thin_mount_and_app_lives_in_state(self) -> None:
        main = DASHBOARD_MAIN.read_text(encoding="utf-8")
        self.assertLessEqual(len(main.splitlines()), 200)
        for required in [
            'import { App } from "./state/App";',
            "createRoot",
            "mountDashboard",
            "root.render(<App />)",
        ]:
            self.assertIn(required, main)

    def test_dashboard_pages_are_split_by_route(self) -> None:
        expected_pages = {
            "home",
            "members",
            "projects",
            "tasks",
            "runs",
            "memory",
            "operations",
            "reviews",
            "permissions",
            "skills",
            "settings",
            "workspace",
            "manager",
        }
        for page in expected_pages:
            page_file = DASHBOARD_SRC / "pages" / page / "index.tsx"
            self.assertTrue(page_file.exists(), page_file)
            self.assertLessEqual(len(page_file.read_text(encoding="utf-8").splitlines()), 800)

        source = runtime_source()
        for exported in [
            "HomePage",
            "ProjectsPage",
            "EmployeesPage",
            "TasksPage",
            "RunsPage",
            "MemoryPage",
            "AutomationsPage",
            "ReviewsPage",
            "PermissionsPage",
            "SkillsPage",
            "SettingsPage",
        ]:
            self.assertIn(exported, source)

    def test_interaction_tests_are_split_by_domain(self) -> None:
        files = sorted((DASHBOARD_SRC / "__tests__").glob("*.test.tsx"))
        self.assertGreaterEqual(len(files), 6)
        for path in files:
            self.assertLessEqual(len(path.read_text(encoding="utf-8").splitlines()), 500)

        source = interaction_source()
        for required in [
            "switches the dashboard shell to Chinese through the i18n strings table",
            "starts a ready managed worker from Run Detail without prompt gates",
            "reviews permission requests and revokes grants with form-backed payloads",
            "creates a hybrid assist automation through the Automations control plane",
            "opens a project connector incident detail with remediation follow-through links",
            "triggers and executes the demo task-planning automation then opens the created TaskPlan detail",
        ]:
            self.assertIn(required, source)

    def test_route_focus_auth_and_workspace_contracts_are_in_split_modules(self) -> None:
        source = runtime_source()
        for required in [
            "viewer",
            "workspace",
            "assignment",
            "delivery",
            "workspaceRouteCandidates",
            "defaultWorkspaceRoute",
            "Provider Delivery Detail",
            "source:\"provider-delivery-detail\"",
            "viewerScopedEndpoints",
            "endpointForViewer",
            "appendViewerMember",
            "Session Projection",
            "Projection Viewer",
            "DASHBOARD_API_TOKEN_STORAGE_KEY",
            "DASHBOARD_API_BASE_STORAGE_KEY",
            "dashboardFetch",
            "endpointForDashboardAuth",
            "endpointForDashboardBackend",
            "Workspace API Base",
            "Apply API Base",
            "Set API Token",
            "Clear API Token",
        ]:
            self.assertIn(required, source)

    def test_run_and_automation_control_planes_remain_addressable(self) -> None:
        source = runtime_source()
        for required in [
            "RunsPage",
            "/model/execute",
            "/worker/start",
            "Execute Model",
            "Managed Worker Start Console",
            "Start Managed Worker",
            "Request Selected Worker Permission",
            "Assisted Execution Package",
            "Assisted Handoff Bundle",
            "Download Bundle Archive",
            "/assisted-ingest",
            "Ingest Assisted Output",
            "Run Review Console",
            "Record Run Review",
            "Run Closeout Console",
            "Close Reviewed Run",
            "Run Source Integration Console",
            "Request Source Integration Remediation",
            "Request Provider Source Integration",
            "Automation Action Console",
            "Trigger Selected Automation",
            "Dry Run Selected Automation",
            "Webhook Admission Console",
            "Admit Webhook Delivery",
            "Scheduler Scan Console",
            "Scan Scheduler",
            "Queued Automation Execution",
            "Execute Automation Run",
            "Stage Approval",
            "Stage Execute",
            "Open Created Task",
            "Open Created TaskPlan",
            "Open Created Run",
            "Context Manifest Explorer",
            "Context Source Detail",
        ]:
            self.assertIn(required, source)

    def test_memory_reviews_permissions_skills_and_people_surfaces_remain_wired(self) -> None:
        source = runtime_source()
        for required in [
            "MemoryPage",
            "Memory Health Remediation",
            "Reviewed Memory Creation",
            "Create Reviewed Store",
            "Create Reviewed Entry",
            "Memory Proposal Review Console",
            "Approve Proposal With Review",
            "Reject Proposal With Review",
            "Verify Entry",
            "Selected Memory Context Injection",
            "ReviewsPage",
            "Memory Review Console",
            "Open Approved Memory",
            "PermissionsPage",
            "Permission Review Console",
            "Approve Permission Request",
            "Reject Permission Request",
            "Permission Grant Lifecycle Console",
            "Revoke Permission Grant",
            "SkillsPage",
            "Attach Skill To Employee",
            "Archive Skill",
            "Project Skills",
            "Employee Skills",
            "Employee Management Console",
            "Create TeamMember",
            "Update Selected TeamMember",
            "Archive Selected TeamMember",
            "Assignment Detail",
            "Project Memory Health",
            "Employee Memory Health",
            "RetrospectiveSuggestionReviewPanel",
            "Create Retrospective",
        ]:
            self.assertIn(required, source)


if __name__ == "__main__":
    unittest.main()
