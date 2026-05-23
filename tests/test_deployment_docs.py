from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT_DIR = ROOT / "docs" / "deployment"


class DeploymentDocsTest(unittest.TestCase):
    def test_deployment_mode_docs_exist_and_cover_required_boundaries(self) -> None:
        required = {
            "single-user.md": ["single-user deployment", "loopback", "open-local"],
            "self-hosted.md": ["self-hosted deployment", "single HTTPS origin", "ProductUser"],
            "multi-tenant.md": ["multi-tenant deployment", "tenant isolation", "/workspaces/{wsId}/"],
        }
        semantic_terms = [
            "source of truth",
            "derived",
            "reverse proxy",
            "secret store",
            "secret values",
            "review-first",
        ]
        exact_terms = [
            ".aiteamos/",
            "TLS",
            "OAuth",
            "SSO",
            "ProductUser",
            "TeamMember",
            "EnvVar",
        ]

        for filename, mode_terms in required.items():
            with self.subTest(filename=filename):
                path = DEPLOYMENT_DIR / filename
                self.assertTrue(path.exists(), f"{path} is missing")
                source = path.read_text(encoding="utf-8")
                source_lower = source.lower()
                for term in mode_terms + semantic_terms:
                    self.assertIn(term.lower(), source_lower)
                for term in exact_terms:
                    self.assertIn(term, source)
                self.assertNotIn("TODO", source)
                self.assertNotIn("FIXME", source)


if __name__ == "__main__":
    unittest.main()
