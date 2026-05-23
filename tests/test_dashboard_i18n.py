from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "apps" / "dashboard" / "src" / "i18n.ts"
DASHBOARD_SRC = ROOT / "apps" / "dashboard" / "src"
README = ROOT / "apps" / "dashboard" / "README.md"


def dashboard_runtime_source() -> str:
    files = [
        DASHBOARD_SRC / "main.tsx",
        DASHBOARD_SRC / "state" / "App.tsx",
        DASHBOARD_SRC / "components" / "shared.tsx",
        *sorted((DASHBOARD_SRC / "pages").glob("*/index.tsx")),
    ]
    return "\n".join(path.read_text(encoding="utf-8") for path in files)


def dashboard_interaction_source() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((DASHBOARD_SRC / "__tests__").glob("*.test.tsx"))
    )


class DashboardI18nTest(unittest.TestCase):
    def test_strings_table_defines_required_bilingual_shell_labels(self) -> None:
        source = I18N.read_text(encoding="utf-8")

        for required in [
            'export type DashboardLocale = "en" | "zh"',
            "dashboardStrings",
            "translateDashboardString",
            "Dashboard Language",
            "Projection Viewer",
            "Loading workspace data...",
            "Unavailable endpoints:",
            "No records.",
            "No record selected.",
            "首页",
            "运行",
            "投影查看者",
            "正在加载工作区数据...",
        ]:
            self.assertIn(required, source)

        for page in ["Home", "Projects", "Employees", "Tasks", "Runs", "Automations", "Memory", "Reviews", "Skills", "Permissions", "Settings"]:
            self.assertIn(f"{page}:", source)

        for forbidden in ["TODO", "FIXME"]:
            self.assertNotIn(forbidden, source)

    def test_dashboard_shell_uses_i18n_table_for_core_copy(self) -> None:
        source = dashboard_runtime_source()

        for required in [
            "translateDashboardString",
            "DashboardI18nContext",
            "readDashboardLocale",
            "writeDashboardLocale",
            "dashboardLocaleLabels",
            "Refresh",
            "Dashboard Language",
            "Projection Viewer",
            "Loading workspace data...",
            "formatDashboardColumnLabel",
        ]:
            self.assertIn(required, source)

        self.assertIn("src/i18n.ts", README.read_text(encoding="utf-8"))

    def test_interaction_test_proves_language_switch(self) -> None:
        source = dashboard_interaction_source()

        for required in [
            "switches the dashboard shell to Chinese through the i18n strings table",
            'getByLabelText("Dashboard Language")',
            "aiteamos.dashboardLocale",
        ]:
            self.assertIn(required, source)


if __name__ == "__main__":
    unittest.main()
