from __future__ import annotations

import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

import yaml

from aiteamos_api.auth import ProductUserTokenBinding, product_user_from_authorization
from aiteamos_workspace import archive_product_user, create_product_user, index_workspace, load_workspace, update_product_user, validate_workspace


REPO_ROOT = Path(__file__).resolve().parents[1]


class UserMemberBindingTest(unittest.TestCase):
    def test_product_user_mutations_sync_team_member_user_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))

            created = create_product_user(
                workspace,
                name="Dashboard Admin",
                actor_member="frontend-human",
                display_name="Dashboard Admin",
                member="frontend-human",
                identity_provider="oauth-google",
                identity_subject_hash="sha256:dashboard-admin",
                roles=["admin", "viewer"],
                session_token_env="AITEAMOS_DASHBOARD_ADMIN_TOKEN",
                governance_scopes=["memory", "permissions"],
                reason="Bind dashboard account to frontend human.",
            )
            self.assertEqual(created["productUser"].object_id, "dashboard-admin")

            index = load_workspace(workspace)
            product_user = index.product_users["dashboard-admin"]
            self.assertEqual(product_user.spec.identityProvider, "oauth-google")
            self.assertEqual(product_user.spec.identitySubjectHash, "sha256:dashboard-admin")

            frontend_binding = index.members["frontend-human"].spec.userBinding
            self.assertIsNotNone(frontend_binding)
            assert frontend_binding is not None
            self.assertEqual(frontend_binding.productUser, "dashboard-admin")
            self.assertEqual(frontend_binding.identityProvider, "oauth-google")
            self.assertEqual(frontend_binding.identitySubjectHash, "sha256:dashboard-admin")
            self.assertEqual(frontend_binding.sessionTokenEnv, "AITEAMOS_DASHBOARD_ADMIN_TOKEN")
            self.assertEqual(frontend_binding.roles, ["admin", "viewer"])
            self.assertEqual(frontend_binding.status, "active")
            self.assertEqual(frontend_binding.boundByMember, "frontend-human")

            update_product_user(
                workspace,
                "dashboard-admin",
                actor_member="frontend-human",
                member="architect",
                identity_provider="sso-oidc",
                identity_subject_hash="sha256:dashboard-admin-rotated",
                roles=["viewer", "auditor"],
                reason="Move login account to architect projection.",
            )

            index = load_workspace(workspace)
            self.assertIsNone(index.members["frontend-human"].spec.userBinding)
            architect_binding = index.members["architect"].spec.userBinding
            self.assertIsNotNone(architect_binding)
            assert architect_binding is not None
            self.assertEqual(architect_binding.productUser, "dashboard-admin")
            self.assertEqual(architect_binding.identityProvider, "sso-oidc")
            self.assertEqual(architect_binding.identitySubjectHash, "sha256:dashboard-admin-rotated")
            self.assertEqual(architect_binding.roles, ["viewer", "auditor"])
            self.assertEqual(architect_binding.status, "active")

            archive_product_user(
                workspace,
                "dashboard-admin",
                actor_member="frontend-human",
                reason="Archive product login account.",
            )

            index = load_workspace(workspace)
            architect_binding = index.members["architect"].spec.userBinding
            self.assertIsNotNone(architect_binding)
            assert architect_binding is not None
            self.assertEqual(architect_binding.status, "archived")

            issues = validate_workspace(index)
            self.assertEqual([issue for issue in issues if issue["level"] == "error"], [])
            self.assertNotIn("frontend-admin-token", _all_member_and_user_text(workspace))

            db_path = Path(temp_dir) / "aiteamos.sqlite"
            index_workspace(workspace, db_path=db_path)
            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute(
                    "select user_binding_json from team_members where id = 'architect'"
                ).fetchone()
            finally:
                conn.close()
            self.assertIsNotNone(row)
            indexed_binding = json.loads(row[0])
            self.assertEqual(indexed_binding["productUser"], "dashboard-admin")
            self.assertEqual(indexed_binding["status"], "archived")

    def test_product_user_auth_helper_resolves_configured_token_without_workspace_secret(self) -> None:
        bindings = (
            ProductUserTokenBinding(
                product_user="dashboard-admin",
                member="frontend-human",
                token_env="AITEAMOS_DASHBOARD_ADMIN_TOKEN",
            ),
        )
        env = {"AITEAMOS_DASHBOARD_ADMIN_TOKEN": "frontend-admin-token"}

        matched = product_user_from_authorization("Bearer frontend-admin-token", bindings, environ=env)
        self.assertEqual(matched, "dashboard-admin")

        self.assertIsNone(product_user_from_authorization("Bearer wrong-token", bindings, environ=env))
        self.assertIsNone(product_user_from_authorization(None, bindings, environ=env))


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / "workspace"
    shutil.copytree(
        REPO_ROOT / ".aiteamos",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    return workspace


def _all_member_and_user_text(workspace: Path) -> str:
    texts: list[str] = []
    for directory in [workspace / "members", workspace / "product_users"]:
        if not directory.exists():
            continue
        for path in directory.glob("*.yaml"):
            parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
            texts.append(yaml.safe_dump(parsed, sort_keys=False))
    return "\n".join(texts)
