from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs" / "dashboard" / "ux-baseline.md"
ARCHITECTURE = ROOT / "docs" / "architecture.md"
DASHBOARD_README = ROOT / "apps" / "dashboard" / "README.md"
DASHBOARD_CSS = ROOT / "apps" / "dashboard" / "src" / "styles.css"
DASHBOARD_SRC = ROOT / "apps" / "dashboard" / "src"


def dashboard_runtime_source() -> str:
    files = [
        DASHBOARD_SRC / "main.tsx",
        DASHBOARD_SRC / "state" / "App.tsx",
        DASHBOARD_SRC / "components" / "shared.tsx",
        *sorted((DASHBOARD_SRC / "pages").glob("*/index.tsx")),
    ]
    return "\n".join(path.read_text(encoding="utf-8") for path in files)


class DashboardUxBaselineTest(unittest.TestCase):
    def test_dashboard_ux_baseline_documents_required_surfaces(self) -> None:
        source = BASELINE.read_text(encoding="utf-8")

        for required in [
            "Status: Accepted",
            "Architecture Reference: `docs/architecture.md#12-dashboard-design`",
            "Keyboard Access",
            "Contrast",
            "Focus Ring",
            "Empty States",
            "Error States",
            "Loading States",
            "Light And Dark Themes",
            "Internationalization",
            "Desktop And Tablet Breakpoints",
            "Lighthouse accessibility score `>= 95`",
            "`.aiteamos/` as the durable source of truth",
            "Secret values must never be echoed",
            "minimum supported viewport width is `320px`",
            "apps/dashboard/src/i18n.ts",
        ]:
            self.assertIn(required, source)

        for forbidden in ["TODO", "FIXME"]:
            self.assertNotIn(forbidden, source)

    def test_plan_architecture_and_dashboard_readme_link_the_baseline(self) -> None:
        architecture = ARCHITECTURE.read_text(encoding="utf-8")
        self.assertIn("docs/dashboard/ux-baseline.md", DASHBOARD_README.read_text(encoding="utf-8"))
        self.assertIn("Web Dashboard", architecture)
        self.assertIn("React dashboard", architecture)
        self.assertIn("`aiteamos-bundle.json` is the portable Assisted IDE handoff contract", architecture)

    def test_dashboard_css_implements_focus_theme_and_tablet_breakpoint_baseline(self) -> None:
        source = DASHBOARD_CSS.read_text(encoding="utf-8")

        for required in [
            "min-width: 320px;",
            "button:focus-visible",
            "a:focus-visible",
            "input:focus-visible",
            "outline: 2px solid #e3b341;",
            "@media (max-width: 900px)",
            "@media (prefers-color-scheme: dark)",
            ".grid.two-wide-left",
            ".ingest-form",
            ".error-text",
            "button:disabled",
        ]:
            self.assertIn(required, source)

    def test_dashboard_shell_exposes_loading_error_and_accessible_form_state(self) -> None:
        source = dashboard_runtime_source()

        for required in [
            "Loading workspace data...",
            "Unavailable endpoints:",
            "error-text",
            "Dashboard API Session",
            "Projection Viewer",
            "Product Session Token",
            "Ingest Assisted Output",
            "Record Run Review",
            "Close Reviewed Run",
        ]:
            self.assertIn(required, source)


if __name__ == "__main__":
    unittest.main()
