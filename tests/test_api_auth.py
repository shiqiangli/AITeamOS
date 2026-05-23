from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tests.inline_testclient import TestClient
import yaml

from aiteamos_api import create_app
from aiteamos_api.routes import (
    SESSION_COOKIE_DEPLOYMENT_ENV,
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_PUBLIC_URL_ENV,
    SESSION_COOKIE_SAMESITE_ENV,
    SESSION_COOKIE_SECURE_ENV,
    SESSION_CSRF_HEADER,
)
from aiteamos_api.auth import API_TOKEN_ENV, MCP_READ_TOKEN_ENV, MCP_WRITE_TOKEN_ENV, VIEWER_TOKEN_MAP_ENV
from aiteamos_workspace import create_run, create_task


REPO_ROOT = Path(__file__).resolve().parents[1]
AUTH_ENV_OFF = {
    API_TOKEN_ENV: "",
    MCP_READ_TOKEN_ENV: "",
    MCP_WRITE_TOKEN_ENV: "",
    VIEWER_TOKEN_MAP_ENV: "",
    SESSION_COOKIE_DEPLOYMENT_ENV: "",
    SESSION_COOKIE_PUBLIC_URL_ENV: "",
    SESSION_COOKIE_SAMESITE_ENV: "",
    SESSION_COOKIE_SECURE_ENV: "",
}
PRODUCT_ADMIN_TOKEN_ENV = "AITEAMOS_PRODUCT_ADMIN_TOKEN"
PRODUCT_VIEWER_TOKEN_ENV = "AITEAMOS_PRODUCT_VIEWER_TOKEN"


class ApiAuthTest(unittest.TestCase):
    def test_unconfigured_tokens_keep_local_api_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            client = TestClient(create_app(workspace))

            tasks = client.get("/tasks")
            self.assertEqual(tasks.status_code, 200)

            docs = client.get("/mcp/tools/search_docs", params={"query": "versioned workspace"})
            self.assertEqual(docs.status_code, 200)

    def test_global_api_token_protects_api_and_mcp_routes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {**AUTH_ENV_OFF, API_TOKEN_ENV: API_TOKEN_ENV}):
            workspace = _copy_workspace(Path(temp_dir))
            client = TestClient(create_app(workspace))

            missing = client.get("/tasks")
            self.assertEqual(missing.status_code, 401)
            self.assertEqual(missing.json()["acceptedTokenEnvNames"], [API_TOKEN_ENV])

            wrong = client.get("/tasks", headers={"Authorization": "Bearer UNAUTHORIZED"})
            self.assertEqual(wrong.status_code, 401)
            self.assertNotIn("UNAUTHORIZED", str(wrong.json()))

            tasks = client.get("/tasks", headers=_auth_header(API_TOKEN_ENV))
            self.assertEqual(tasks.status_code, 200)

            docs = client.get(
                "/mcp/tools/search_docs",
                params={"query": "versioned workspace"},
                headers=_auth_header(API_TOKEN_ENV),
            )
            self.assertEqual(docs.status_code, 200)

    def test_mcp_read_token_allows_read_tools_only_and_protects_aliases(self) -> None:
        env = {**AUTH_ENV_OFF, MCP_READ_TOKEN_ENV: MCP_READ_TOKEN_ENV}
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, env):
            workspace = _copy_workspace(Path(temp_dir))
            run = _create_backend_run(workspace)
            client = TestClient(create_app(workspace))

            no_header = client.get("/mcp/tools/search_docs", params={"query": "versioned workspace"})
            self.assertEqual(no_header.status_code, 401)
            self.assertEqual(no_header.json()["scope"], "mcp-read")

            docs = client.get(
                "/mcp/tools/search_docs",
                params={"query": "versioned workspace"},
                headers=_auth_header(MCP_READ_TOKEN_ENV),
            )
            self.assertEqual(docs.status_code, 200)

            write = client.post(
                "/mcp/tools/record_journal",
                json={"runId": run.object_id, "actorMember": "backend-digital", "entry": "not allowed"},
                headers=_auth_header(MCP_READ_TOKEN_ENV),
            )
            self.assertEqual(write.status_code, 403)
            self.assertEqual(write.json()["acceptedTokenEnvNames"], [MCP_WRITE_TOKEN_ENV, API_TOKEN_ENV])

    def test_mcp_write_token_allows_mutating_and_read_tools(self) -> None:
        env = {**AUTH_ENV_OFF, MCP_WRITE_TOKEN_ENV: MCP_WRITE_TOKEN_ENV}
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, env):
            workspace = _copy_workspace(Path(temp_dir))
            run = _create_backend_run(workspace)
            client = TestClient(create_app(workspace))

            journal = client.post(
                "/mcp/tools/record_journal",
                json={"runId": run.object_id, "actorMember": "backend-digital", "entry": "allowed"},
                headers=_auth_header(MCP_WRITE_TOKEN_ENV),
            )
            self.assertEqual(journal.status_code, 200)

            memory = client.get(
                "/mcp/tools/search_memory",
                params={"query": "shadow workspace"},
                headers=_auth_header(MCP_WRITE_TOKEN_ENV),
            )
            self.assertEqual(memory.status_code, 200)

    def test_mcp_scoped_tokens_do_not_satisfy_global_api_token(self) -> None:
        env = {
            API_TOKEN_ENV: API_TOKEN_ENV,
            MCP_READ_TOKEN_ENV: MCP_READ_TOKEN_ENV,
            MCP_WRITE_TOKEN_ENV: MCP_WRITE_TOKEN_ENV,
            VIEWER_TOKEN_MAP_ENV: "",
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, env):
            workspace = _copy_workspace(Path(temp_dir))
            client = TestClient(create_app(workspace))

            scoped = client.get("/tasks", headers=_auth_header(MCP_READ_TOKEN_ENV))
            self.assertEqual(scoped.status_code, 401)

            global_api = client.get("/tasks", headers=_auth_header(API_TOKEN_ENV))
            self.assertEqual(global_api.status_code, 200)

            docs = client.get(
                "/mcp/tools/search_docs",
                params={"query": "versioned workspace"},
                headers=_auth_header(MCP_READ_TOKEN_ENV),
            )
            self.assertEqual(docs.status_code, 200)

    def test_api_session_projection_reports_auth_mode_and_effective_viewer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            client = TestClient(create_app(workspace))

            local = client.get("/session")
            self.assertEqual(local.status_code, 200)
            self.assertEqual(local.json()["spec"]["authMode"], "open-local")
            self.assertFalse(local.json()["spec"]["authenticated"])
            self.assertTrue(local.json()["spec"]["canSelectViewer"])

        viewer_env = {
            **AUTH_ENV_OFF,
            VIEWER_TOKEN_MAP_ENV: '{"frontend-human":"frontend-token","architect":"architect-token"}',
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, viewer_env):
            workspace = _copy_workspace(Path(temp_dir))
            client = TestClient(create_app(workspace))

            missing = client.get("/session")
            self.assertEqual(missing.status_code, 401)

            viewer = client.get("/session", headers={"Authorization": "Bearer frontend-token"})
            self.assertEqual(viewer.status_code, 200)
            viewer_spec = viewer.json()["spec"]
            self.assertEqual(viewer_spec["authMode"], "viewer-token")
            self.assertTrue(viewer_spec["authenticated"])
            self.assertTrue(viewer_spec["tokenBound"])
            self.assertFalse(viewer_spec["admin"])
            self.assertFalse(viewer_spec["canSelectViewer"])
            self.assertEqual(viewer_spec["viewerMember"], "frontend-human")
            self.assertEqual(viewer_spec["viewerMemberKind"], "human")
            self.assertEqual(viewer_spec["projectionMode"], "token-bound-viewer")

            mismatch = client.get(
                "/session",
                params={"viewerMember": "architect"},
                headers={"Authorization": "Bearer frontend-token"},
            )
            self.assertEqual(mismatch.status_code, 403)

        api_env = {**AUTH_ENV_OFF, API_TOKEN_ENV: API_TOKEN_ENV}
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, api_env):
            workspace = _copy_workspace(Path(temp_dir))
            client = TestClient(create_app(workspace))

            admin = client.get(
                "/session",
                params={"viewerMember": "architect"},
                headers=_auth_header(API_TOKEN_ENV),
            )
            self.assertEqual(admin.status_code, 200)
            admin_spec = admin.json()["spec"]
            self.assertEqual(admin_spec["authMode"], "api-token")
            self.assertTrue(admin_spec["authenticated"])
            self.assertTrue(admin_spec["admin"])
            self.assertTrue(admin_spec["canSelectViewer"])
            self.assertEqual(admin_spec["viewerMember"], "architect")
            self.assertEqual(admin_spec["projectionMode"], "admin-selected-viewer")

    def test_api_viewer_token_binds_governed_projection_identity(self) -> None:
        env = {
            **AUTH_ENV_OFF,
            VIEWER_TOKEN_MAP_ENV: '{"frontend-human":"frontend-token","architect":"architect-token"}',
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, env):
            workspace = _copy_workspace(Path(temp_dir))
            client = TestClient(create_app(workspace))

            missing = client.get("/skills")
            self.assertEqual(missing.status_code, 401)
            self.assertEqual(missing.json()["acceptedTokenEnvNames"], [API_TOKEN_ENV, VIEWER_TOKEN_MAP_ENV])

            skills = client.get("/skills", headers={"Authorization": "Bearer frontend-token"})
            self.assertEqual(skills.status_code, 200)
            self.assertTrue(skills.json())

            skill_mismatch = client.get(
                "/skills",
                params={"viewerMember": "architect"},
                headers={"Authorization": "Bearer frontend-token"},
            )
            self.assertEqual(skill_mismatch.status_code, 403)
            self.assertIn("viewerMember does not match", skill_mismatch.json()["detail"])

            scoped_skill_mismatch = client.get(
                "/members/frontend-human/skills",
                params={"viewerMember": "architect"},
                headers={"Authorization": "Bearer frontend-token"},
            )
            self.assertEqual(scoped_skill_mismatch.status_code, 403)

            scoped_skill_match = client.get(
                "/members/frontend-human/skills",
                headers={"Authorization": "Bearer frontend-token"},
            )
            self.assertEqual(scoped_skill_match.status_code, 200)

            assignment_skill_mismatch = client.get(
                "/assignments/aiteamos-dashboard/skills",
                params={"viewerMember": "architect"},
                headers={"Authorization": "Bearer frontend-token"},
            )
            self.assertEqual(assignment_skill_mismatch.status_code, 403)

            assignment_skill_match = client.get(
                "/assignments/aiteamos-dashboard/skills",
                headers={"Authorization": "Bearer frontend-token"},
            )
            self.assertEqual(assignment_skill_match.status_code, 200)

            memory_mismatch = client.get(
                "/memory/entries",
                params={"viewerMember": "architect"},
                headers={"Authorization": "Bearer frontend-token"},
            )
            self.assertEqual(memory_mismatch.status_code, 403)

            permission_mismatch = client.get(
                "/permissions",
                params={"viewerMember": "architect"},
                headers={"Authorization": "Bearer frontend-token"},
            )
            self.assertEqual(permission_mismatch.status_code, 403)

            scoped_permission_mismatch = client.get(
                "/members/frontend-human/permissions",
                params={"viewerMember": "architect"},
                headers={"Authorization": "Bearer frontend-token"},
            )
            self.assertEqual(scoped_permission_mismatch.status_code, 403)

            scoped_permission_match = client.get(
                "/members/frontend-human/permissions",
                headers={"Authorization": "Bearer frontend-token"},
            )
            self.assertEqual(scoped_permission_match.status_code, 200)

            assignment_permission_mismatch = client.get(
                "/assignments/aiteamos-dashboard/permissions",
                params={"viewerMember": "architect"},
                headers={"Authorization": "Bearer frontend-token"},
            )
            self.assertEqual(assignment_permission_mismatch.status_code, 403)

            assignment_permission_match = client.get(
                "/assignments/aiteamos-dashboard/permissions",
                headers={"Authorization": "Bearer frontend-token"},
            )
            self.assertEqual(assignment_permission_match.status_code, 200)

            explicit_match = client.get(
                "/permissions",
                params={"viewerMember": "frontend-human"},
                headers={"Authorization": "Bearer frontend-token"},
            )
            self.assertEqual(explicit_match.status_code, 200)

    def test_product_user_token_maps_admin_session_and_governed_viewer(self) -> None:
        env = {
            **AUTH_ENV_OFF,
            PRODUCT_ADMIN_TOKEN_ENV: "frontend-admin-token",
            PRODUCT_VIEWER_TOKEN_ENV: "frontend-viewer-token",
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, env):
            workspace = _copy_workspace(Path(temp_dir))
            _write_product_user(
                workspace,
                user_id="frontend-admin",
                member="frontend-human",
                roles=["admin"],
                token_env=PRODUCT_ADMIN_TOKEN_ENV,
            )
            _write_product_user(
                workspace,
                user_id="frontend-viewer",
                member="frontend-human",
                roles=["viewer"],
                token_env=PRODUCT_VIEWER_TOKEN_ENV,
            )
            client = TestClient(create_app(workspace))

            missing = client.get("/session")
            self.assertEqual(missing.status_code, 401)
            self.assertIn(PRODUCT_ADMIN_TOKEN_ENV, missing.json()["acceptedTokenEnvNames"])

            admin = client.get(
                "/session",
                params={"viewerMember": "architect"},
                headers={"Authorization": "Bearer frontend-admin-token"},
            )
            self.assertEqual(admin.status_code, 200)
            admin_spec = admin.json()["spec"]
            self.assertEqual(admin_spec["authMode"], "product-user-token")
            self.assertEqual(admin_spec["productUser"], "frontend-admin")
            self.assertEqual(admin_spec["productUserMember"], "frontend-human")
            self.assertEqual(admin_spec["productUserRoles"], ["admin"])
            self.assertTrue(admin_spec["admin"])
            self.assertTrue(admin_spec["canSelectViewer"])
            self.assertTrue(admin_spec["canApproveGovernance"])
            self.assertEqual(admin_spec["viewerMember"], "architect")
            self.assertEqual(admin_spec["projectionMode"], "admin-selected-viewer")

            memory = client.get(
                "/memory/entries",
                params={"viewerMember": "architect"},
                headers={"Authorization": "Bearer frontend-admin-token"},
            )
            self.assertEqual(memory.status_code, 200)

            viewer_default = client.get("/session", headers={"Authorization": "Bearer frontend-viewer-token"})
            self.assertEqual(viewer_default.status_code, 200)
            viewer_spec = viewer_default.json()["spec"]
            self.assertEqual(viewer_spec["productUser"], "frontend-viewer")
            self.assertFalse(viewer_spec["admin"])
            self.assertFalse(viewer_spec["canSelectViewer"])
            self.assertEqual(viewer_spec["viewerMember"], "frontend-human")

            viewer_mismatch = client.get(
                "/session",
                params={"viewerMember": "architect"},
                headers={"Authorization": "Bearer frontend-viewer-token"},
            )
            self.assertEqual(viewer_mismatch.status_code, 403)

    def test_product_user_management_requires_admin_and_writes_audited_manifest(self) -> None:
        env = {
            **AUTH_ENV_OFF,
            API_TOKEN_ENV: "root-token",
            PRODUCT_ADMIN_TOKEN_ENV: "frontend-admin-token",
            PRODUCT_VIEWER_TOKEN_ENV: "frontend-viewer-token",
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, env):
            workspace = _copy_workspace(Path(temp_dir))
            _write_product_user(
                workspace,
                user_id="frontend-admin",
                member="frontend-human",
                roles=["admin"],
                token_env=PRODUCT_ADMIN_TOKEN_ENV,
            )
            _write_product_user(
                workspace,
                user_id="frontend-viewer",
                member="frontend-human",
                roles=["viewer"],
                token_env=PRODUCT_VIEWER_TOKEN_ENV,
            )
            client = TestClient(create_app(workspace))

            missing = client.get("/product-users")
            self.assertEqual(missing.status_code, 401)

            blocked_viewer = client.post(
                "/product-users",
                headers={"Authorization": "Bearer frontend-viewer-token"},
                json={
                    "name": "Dashboard Admin",
                    "actorMember": "frontend-human",
                    "member": "frontend-human",
                    "roles": ["admin"],
                    "sessionTokenEnv": "AITEAMOS_DASHBOARD_ADMIN_TOKEN",
                },
            )
            self.assertEqual(blocked_viewer.status_code, 403)

            created = client.post(
                "/product-users",
                headers={"Authorization": "Bearer root-token"},
                json={
                    "name": "Dashboard Admin",
                    "displayName": "Dashboard Admin",
                    "actorMember": "frontend-human",
                    "member": "frontend-human",
                    "roles": ["admin", "viewer"],
                    "sessionTokenEnv": "AITEAMOS_DASHBOARD_ADMIN_TOKEN",
                    "governanceScopes": ["memory", "permissions"],
                    "reason": "Create dashboard admin mapping.",
                },
            )
            self.assertEqual(created.status_code, 200)
            created_body = created.json()
            product_user = created_body["productUser"]
            self.assertEqual(product_user["id"], "dashboard-admin")
            self.assertEqual(product_user["spec"]["sessionTokenEnv"], "AITEAMOS_DASHBOARD_ADMIN_TOKEN")
            self.assertEqual(product_user["spec"]["managementAudit"][0]["action"], "create-product-user")
            self.assertEqual(product_user["spec"]["managementAudit"][0]["decisionKind"], "human_approval")
            self.assertEqual(created_body["managementAudit"]["targetUser"], "dashboard-admin")
            manifest_text = (workspace / "product_users" / "dashboard-admin.yaml").read_text(encoding="utf-8")
            self.assertIn("sessionTokenEnv: AITEAMOS_DASHBOARD_ADMIN_TOKEN", manifest_text)
            self.assertNotIn("root-token", manifest_text)
            self.assertNotIn("frontend-admin-token", manifest_text)

            viewer_update = client.patch(
                "/product-users/dashboard-admin",
                headers={"Authorization": "Bearer frontend-viewer-token"},
                json={"actorMember": "frontend-human", "roles": ["viewer"], "reason": "Viewer cannot manage users."},
            )
            self.assertEqual(viewer_update.status_code, 403)

            admin_update = client.patch(
                "/product-users/dashboard-admin",
                headers={"Authorization": "Bearer frontend-admin-token"},
                json={
                    "actorMember": "frontend-human",
                    "displayName": "Dashboard Admin Updated",
                    "roles": ["viewer", "auditor"],
                    "reason": "Rotate ProductUser responsibilities.",
                },
            )
            self.assertEqual(admin_update.status_code, 200)
            self.assertEqual(admin_update.json()["productUser"]["spec"]["roles"], ["viewer", "auditor"])
            self.assertEqual(admin_update.json()["managementAudit"]["action"], "update-product-user")

            archived = client.post(
                "/product-users/dashboard-admin/archive",
                headers={"Authorization": "Bearer frontend-admin-token"},
                json={"actorMember": "frontend-human", "reason": "Retire dashboard admin mapping."},
            )
            self.assertEqual(archived.status_code, 200)
            self.assertEqual(archived.json()["productUser"]["spec"]["status"], "archived")
            self.assertEqual(archived.json()["managementAudit"]["action"], "archive-product-user")

    def test_product_user_cookie_login_authorizes_and_logout_clears_session(self) -> None:
        env = {
            **AUTH_ENV_OFF,
            PRODUCT_ADMIN_TOKEN_ENV: "frontend-admin-token",
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, env):
            workspace = _copy_workspace(Path(temp_dir))
            _write_product_user(
                workspace,
                user_id="frontend-admin",
                member="frontend-human",
                roles=["admin"],
                token_env=PRODUCT_ADMIN_TOKEN_ENV,
            )
            client = TestClient(create_app(workspace))

            missing = client.get("/session")
            self.assertEqual(missing.status_code, 401)

            invalid = client.post("/session/login", json={"token": "wrong-token"})
            self.assertEqual(invalid.status_code, 401)

            login = client.post("/session/login", json={"token": "frontend-admin-token"})
            self.assertEqual(login.status_code, 200)
            login_cookie = login.headers.get("set-cookie", "")
            self.assertIn(f"{SESSION_COOKIE_NAME}=", login_cookie)
            self.assertNotIn("frontend-admin-token", login_cookie)
            self.assertIn("HttpOnly", login.headers.get("set-cookie", ""))
            login_body = login.json()
            self.assertEqual(login_body["kind"], "SessionLogin")
            self.assertEqual(login_body["authMode"], "product-user-token")
            self.assertEqual(login_body["productUser"], "frontend-admin")
            self.assertTrue(login_body["admin"])
            self.assertIsInstance(login_body["csrfToken"], str)
            self.assertGreater(len(login_body["csrfToken"]), 20)
            self.assertEqual(login_body["sessionVersion"], 1)

            session = client.get("/session", params={"viewerMember": "architect"})
            self.assertEqual(session.status_code, 200)
            session_spec = session.json()["spec"]
            self.assertEqual(session_spec["authMode"], "product-user-token")
            self.assertEqual(session_spec["productUser"], "frontend-admin")
            self.assertEqual(session_spec["viewerMember"], "architect")

            logout = client.post("/session/logout")
            self.assertEqual(logout.status_code, 200)
            self.assertEqual(logout.json()["status"], "logged-out")
            self.assertIn(f"{SESSION_COOKIE_NAME}=", logout.headers.get("set-cookie", ""))

            after_logout = client.get("/session")
            self.assertEqual(after_logout.status_code, 401)

    def test_product_user_cookie_session_requires_csrf_and_can_renew(self) -> None:
        env = {
            **AUTH_ENV_OFF,
            PRODUCT_ADMIN_TOKEN_ENV: "frontend-admin-token",
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, env):
            workspace = _copy_workspace(Path(temp_dir))
            _write_product_user(
                workspace,
                user_id="frontend-admin",
                member="frontend-human",
                roles=["admin"],
                token_env=PRODUCT_ADMIN_TOKEN_ENV,
            )
            client = TestClient(create_app(workspace))

            login = client.post("/session/login", json={"token": "frontend-admin-token"})
            self.assertEqual(login.status_code, 200)
            initial_cookie = login.headers.get("set-cookie", "")
            initial_csrf = login.json()["csrfToken"]

            product_user_payload = {
                "name": "Cookie Managed",
                "actorMember": "frontend-human",
                "member": "frontend-human",
                "roles": ["viewer"],
                "sessionTokenEnv": PRODUCT_VIEWER_TOKEN_ENV,
                "reason": "Create through a hardened cookie session.",
            }
            missing_csrf = client.post("/product-users", json=product_user_payload)
            self.assertEqual(missing_csrf.status_code, 403)
            self.assertEqual(missing_csrf.json()["detail"], "missing or invalid csrf token for cookie session")

            created = client.post(
                "/product-users",
                headers={SESSION_CSRF_HEADER: initial_csrf},
                json=product_user_payload,
            )
            self.assertEqual(created.status_code, 200)
            self.assertEqual(created.json()["productUser"]["id"], "cookie-managed")

            missing_renew_csrf = client.post("/session/renew")
            self.assertEqual(missing_renew_csrf.status_code, 403)

            renewed = client.post("/session/renew", headers={SESSION_CSRF_HEADER: initial_csrf})
            self.assertEqual(renewed.status_code, 200)
            renewed_body = renewed.json()
            renewed_cookie = renewed.headers.get("set-cookie", "")
            self.assertIn(f"{SESSION_COOKIE_NAME}=", renewed_cookie)
            self.assertNotIn("frontend-admin-token", renewed_cookie)
            self.assertNotEqual(initial_cookie, renewed_cookie)
            self.assertNotEqual(initial_csrf, renewed_body["csrfToken"])

            stale_csrf = client.patch(
                "/product-users/cookie-managed",
                headers={SESSION_CSRF_HEADER: initial_csrf},
                json={"actorMember": "frontend-human", "roles": ["auditor"], "reason": "Use stale csrf."},
            )
            self.assertEqual(stale_csrf.status_code, 403)

            updated = client.patch(
                "/product-users/cookie-managed",
                headers={SESSION_CSRF_HEADER: renewed_body["csrfToken"]},
                json={"actorMember": "frontend-human", "roles": ["auditor"], "reason": "Use renewed csrf."},
            )
            self.assertEqual(updated.status_code, 200)
            self.assertEqual(updated.json()["productUser"]["spec"]["roles"], ["auditor"])

    def test_product_user_cookie_policy_is_environment_aware(self) -> None:
        def login_and_logout_cookies(env: dict[str, str]) -> tuple[str, str]:
            with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, env):
                workspace = _copy_workspace(Path(temp_dir))
                _write_product_user(
                    workspace,
                    user_id="frontend-admin",
                    member="frontend-human",
                    roles=["admin"],
                    token_env=PRODUCT_ADMIN_TOKEN_ENV,
                )
                client = TestClient(create_app(workspace))
                login = client.post("/session/login", json={"token": "frontend-admin-token"})
                self.assertEqual(login.status_code, 200)
                logout = client.post("/session/logout")
                self.assertEqual(logout.status_code, 200)
                return login.headers.get("set-cookie", ""), logout.headers.get("set-cookie", "")

        base_env = {
            **AUTH_ENV_OFF,
            PRODUCT_ADMIN_TOKEN_ENV: "frontend-admin-token",
        }

        local_cookie, local_logout_cookie = login_and_logout_cookies(base_env)
        self.assertIn("HttpOnly", local_cookie)
        self.assertIn("SameSite=lax", local_cookie)
        self.assertNotIn("; Secure", local_cookie)
        self.assertIn("SameSite=lax", local_logout_cookie)
        self.assertNotIn("; Secure", local_logout_cookie)

        production_cookie, production_logout_cookie = login_and_logout_cookies(
            {
                **base_env,
                SESSION_COOKIE_DEPLOYMENT_ENV: "production",
                SESSION_COOKIE_SECURE_ENV: "false",
            }
        )
        self.assertIn("; Secure", production_cookie)
        self.assertIn("SameSite=lax", production_cookie)
        self.assertIn("; Secure", production_logout_cookie)
        self.assertIn("SameSite=lax", production_logout_cookie)

        https_cookie, _ = login_and_logout_cookies(
            {
                **base_env,
                SESSION_COOKIE_PUBLIC_URL_ENV: "https://aiteamos.example.test",
            }
        )
        self.assertIn("; Secure", https_cookie)

        cross_site_cookie, _ = login_and_logout_cookies(
            {
                **base_env,
                SESSION_COOKIE_SAMESITE_ENV: "none",
            }
        )
        self.assertIn("; Secure", cross_site_cookie)
        self.assertIn("SameSite=none", cross_site_cookie)

        strict_local_cookie, _ = login_and_logout_cookies(
            {
                **base_env,
                SESSION_COOKIE_SAMESITE_ENV: "strict",
                SESSION_COOKIE_SECURE_ENV: "false",
            }
        )
        self.assertNotIn("; Secure", strict_local_cookie)
        self.assertIn("SameSite=strict", strict_local_cookie)

    def test_product_user_cookie_session_governs_scoped_projection_leakage(self) -> None:
        env = {
            **AUTH_ENV_OFF,
            PRODUCT_ADMIN_TOKEN_ENV: "frontend-admin-token",
            PRODUCT_VIEWER_TOKEN_ENV: "frontend-viewer-token",
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, env):
            workspace = _copy_workspace(Path(temp_dir))
            _write_product_user(
                workspace,
                user_id="frontend-admin",
                member="frontend-human",
                roles=["admin"],
                token_env=PRODUCT_ADMIN_TOKEN_ENV,
            )
            _write_product_user(
                workspace,
                user_id="frontend-viewer",
                member="frontend-human",
                roles=["viewer"],
                token_env=PRODUCT_VIEWER_TOKEN_ENV,
            )
            _write_product_session_governance_fixtures(workspace)

            viewer_client = TestClient(create_app(workspace))
            viewer_login = viewer_client.post("/session/login", json={"token": "frontend-viewer-token"})
            self.assertEqual(viewer_login.status_code, 200)
            self.assertFalse(viewer_login.json()["canSelectViewer"])
            self.assertEqual(viewer_login.json()["viewerMember"], "frontend-human")

            viewer_mismatch = viewer_client.get("/session", params={"viewerMember": "architect"})
            self.assertEqual(viewer_mismatch.status_code, 403)

            project_memory_mismatch = viewer_client.get(
                "/projects/aiteamos/memory",
                params={"query": "CUSTOMER-Y", "viewerMember": "architect"},
            )
            self.assertEqual(project_memory_mismatch.status_code, 403)

            project_memory = viewer_client.get("/projects/aiteamos/memory", params={"query": "CUSTOMER-Y"})
            self.assertEqual(project_memory.status_code, 200)
            self.assertNotIn("CUSTOMER-Y-CONFIDENTIAL", str(project_memory.json()))
            self.assertNotIn("private-product-session-confidential", _match_ids(project_memory.json()))
            self.assertGreaterEqual(project_memory.json()["excludedMatches"], 1)

            member_memory = viewer_client.get("/members/architect/memory", params={"query": "CUSTOMER-Y"})
            self.assertEqual(member_memory.status_code, 200)
            self.assertNotIn("CUSTOMER-Y-CONFIDENTIAL", str(member_memory.json()))

            project_skill_mismatch = viewer_client.get("/projects/aiteamos/skills", params={"viewerMember": "architect"})
            self.assertEqual(project_skill_mismatch.status_code, 403)
            project_skills = viewer_client.get("/projects/aiteamos/skills")
            self.assertEqual(project_skills.status_code, 200)
            self.assertNotIn("CUSTOMER_SKILL_SECRET", project_skills.text)
            self.assertNotIn("architect-private-policy", project_skills.text)

            member_skills = viewer_client.get("/members/architect/skills")
            assignment_skills = viewer_client.get("/assignments/aiteamos-architecture/skills")
            self.assertEqual(member_skills.status_code, 200)
            self.assertEqual(assignment_skills.status_code, 200)
            self.assertNotIn("CUSTOMER_SKILL_SECRET", member_skills.text)
            self.assertNotIn("CUSTOMER_SKILL_SECRET", assignment_skills.text)

            member_permission_mismatch = viewer_client.get(
                "/members/architect/permissions",
                params={"viewerMember": "architect"},
            )
            self.assertEqual(member_permission_mismatch.status_code, 403)
            member_permissions = viewer_client.get("/members/architect/permissions")
            assignment_permissions = viewer_client.get("/assignments/aiteamos-architecture/permissions")
            self.assertEqual(member_permissions.status_code, 200)
            self.assertEqual(assignment_permissions.status_code, 200)
            self.assertNotIn("CUSTOMER_SCOPED_TOKEN", member_permissions.text)
            self.assertNotIn("CUSTOMER_SCOPED_TOKEN", assignment_permissions.text)

            admin_client = TestClient(create_app(workspace))
            admin_login = admin_client.post("/session/login", json={"token": "frontend-admin-token"})
            self.assertEqual(admin_login.status_code, 200)
            self.assertTrue(admin_login.json()["canSelectViewer"])

            admin_session = admin_client.get("/session", params={"viewerMember": "architect"})
            self.assertEqual(admin_session.status_code, 200)
            self.assertEqual(admin_session.json()["spec"]["viewerMember"], "architect")

            admin_memory = admin_client.get(
                "/projects/aiteamos/memory",
                params={"query": "CUSTOMER-Y", "viewerMember": "architect"},
            )
            self.assertEqual(admin_memory.status_code, 200)
            self.assertIn("CUSTOMER-Y-CONFIDENTIAL", str(admin_memory.json()))
            self.assertIn("private-product-session-confidential", _match_ids(admin_memory.json()))

            admin_skills = admin_client.get("/projects/aiteamos/skills", params={"viewerMember": "architect"})
            self.assertEqual(admin_skills.status_code, 200)
            self.assertIn("CUSTOMER_SKILL_SECRET", admin_skills.text)
            self.assertIn("architect-private-policy", admin_skills.text)

            admin_member_permissions = admin_client.get(
                "/members/architect/permissions",
                params={"viewerMember": "architect"},
            )
            admin_assignment_permissions = admin_client.get(
                "/assignments/aiteamos-architecture/permissions",
                params={"viewerMember": "architect"},
            )
            self.assertEqual(admin_member_permissions.status_code, 200)
            self.assertEqual(admin_assignment_permissions.status_code, 200)
            self.assertIn("CUSTOMER_SCOPED_TOKEN", admin_member_permissions.text)
            self.assertIn("CUSTOMER_SCOPED_TOKEN", admin_assignment_permissions.text)


def _auth_header(env_name: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {env_name}"}


def _match_ids(payload: dict[str, object]) -> set[str]:
    return {str(record["id"]) for record in payload.get("matches", []) if isinstance(record, dict) and "id" in record}


def _write_yaml(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _write_product_user(workspace: Path, *, user_id: str, member: str, roles: list[str], token_env: str) -> None:
    users_dir = workspace / "product_users"
    users_dir.mkdir(exist_ok=True)
    users = ", ".join(roles)
    (users_dir / f"{user_id}.yaml").write_text(
        f"""apiVersion: aiteamos.dev/v1alpha1
kind: ProductUser
metadata:
  name: {user_id}
spec:
  displayName: {user_id}
  member: {member}
  status: active
  roles: [{users}]
  sessionTokenEnv: {token_env}
""",
        encoding="utf-8",
    )


def _write_product_session_governance_fixtures(workspace: Path) -> None:
    _write_yaml(
        workspace / "memory" / "entries" / "private-product-session-confidential.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "MemoryEntry",
            "metadata": {"name": "private-product-session-confidential"},
            "spec": {
                "store": "architect-personal-memory",
                "path": "private/product-session-customer-y.md",
                "title": "Product session Customer Y plan",
                "content": "CUSTOMER-Y-CONFIDENTIAL must stay scoped to architect product-session projections.",
                "kind": "decision",
                "scope": "member",
                "confidence": 0.9,
                "sensitivity": "confidential",
                "visibility": "private",
                "acl": {"read": ["member:architect"], "write": ["member:architect"]},
                "relatedProjects": ["aiteamos"],
                "relatedMembers": ["architect"],
                "relatedAssignments": ["aiteamos-architecture"],
                "version": 1,
                "lineage": {"authorMember": "architect"},
                "lifecycle": "active",
            },
        },
    )
    _write_yaml(
        workspace / "memory" / "bindings" / "bind-product-session-confidential-to-architect.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "MemoryBinding",
            "metadata": {"name": "bind-product-session-confidential-to-architect"},
            "spec": {
                "store": "architect-personal-memory",
                "entry": "private-product-session-confidential",
                "targetType": "member",
                "targetId": "architect",
                "access": ["read", "reference", "inject"],
                "reason": "Private product-session projection fixture for architect only.",
                "status": "active",
                "createdByMember": "architect",
            },
        },
    )
    _write_yaml(
        workspace / "memory" / "grants" / "grant-product-session-confidential-to-architect.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "MemoryGrant",
            "metadata": {"name": "grant-product-session-confidential-to-architect"},
            "spec": {
                "granteeMember": "architect",
                "grantorMember": "architect",
                "stores": ["architect-personal-memory"],
                "entries": ["private-product-session-confidential"],
                "access": ["read", "reference", "inject"],
                "reason": "Architect can inject the private product-session fixture.",
                "status": "active",
            },
        },
    )
    _write_yaml(
        workspace / "permissions" / "architect-private-policy.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "PermissionPolicy",
            "metadata": {"name": "architect-private-policy"},
            "spec": {
                "scope": {"member": "architect"},
                "defaultMode": "ask",
                "allow": [{"match": "EnvVar(CUSTOMER_SCOPED_TOKEN:use)"}],
                "deny": [{"match": "EnvVar(CUSTOMER_SCOPED_TOKEN:read)"}],
            },
        },
    )
    _write_yaml(
        workspace / "skills" / "architect-sensitive-ops.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "Skill",
            "metadata": {"name": "architect-sensitive-ops"},
            "spec": {
                "description": "Operate sensitive architect-only product-session projections.",
                "ownerMember": "architect",
                "projects": [],
                "capabilities": ["CUSTOMER_SKILL_SECRET"],
                "requiredPermissions": ["architect-private-policy"],
                "lifecycle": "active",
            },
        },
    )


def _create_backend_run(workspace: Path) -> object:
    task = create_task(
        workspace,
        title="Auth tool task",
        assigned_member="backend-digital",
        assignment="aiteamos-backend-runtime",
        acceptance=["auth is enforced"],
    )
    return create_run(workspace, task_id=task.object_id, member="backend-digital", assignment="aiteamos-backend-runtime")


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        REPO_ROOT / ".aiteamos",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    return workspace


if __name__ == "__main__":
    unittest.main()
